"""
顾客评论情感分析服务（移植自 BettaFish SentimentAnalysisModel，适配屯象OS）

BettaFish原版：WeiboMultilingualSentiment（PyTorch + Transformers 本地模型）
屯象OS改造要点：
  - 用 LLM 替代 PyTorch 模型，零额外依赖
  - 批量处理（8条/次调用），平衡速度与成本
  - 输入：CustomerReview（美团/大众点评/外卖评价/WeCom消息）
  - 输出：SentimentResult（单条）→ DishSentimentSummary（按菜品聚合）
  - 结果注入 dish_health_service.enrich_with_sentiment() 作为第5评分维度
  - SENTIMENT_ENABLED=false 可一键关闭，不阻塞主流程

数据流：
  美团/点评评论
       ↓
  analyze_batch() → List[SentimentResult]
       ↓
  aggregate_by_dish() → Dict[dish_name, DishSentimentSummary]
       ↓
  dish_health_service.enrich_with_sentiment(records, dish_sentiment)
       ↓
  health_record 新增: sentiment_score / sentiment_label / top_complaints
       ↓
  厨师长Agent: "鱼香肉丝 差评率↑23%，主要吐槽：偏咸、份量少"
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import structlog

from ..core.llm import get_llm_client
from ..utils.retry_helper import HTTP_RETRY_CONFIG, async_graceful_retry

logger = structlog.get_logger()

# 功能开关（环境变量 SENTIMENT_ENABLED=false 可运行时关闭）
_ENABLED: bool = os.getenv("SENTIMENT_ENABLED", "true").lower() != "false"

# 每次 LLM 调用处理的评论条数（平衡延迟与 token 成本）
_BATCH_SIZE: int = int(os.getenv("SENTIMENT_BATCH_SIZE", "8"))

# 差评预警阈值：negative_rate 超过此值标为"差评预警"
_NEGATIVE_ALERT_THRESHOLD: float = float(os.getenv("SENTIMENT_NEGATIVE_THRESHOLD", "0.3"))


# ─────────────────────────────────────────────────────────────────────────────
# 数据类（参考 BettaFish SentimentResult / BatchSentimentResult）
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CustomerReview:
    """单条顾客评论"""
    text: str
    source: str = "unknown"          # meituan / dianping / waimai / wecom
    dish_name: Optional[str] = None  # 预标注菜品（None 时由 LLM 从文本提取）
    platform_rating: Optional[float] = None  # 平台星级 1-5（辅助参考）
    review_id: Optional[str] = None


@dataclass
class SentimentResult:
    """单条评论的情感分析结果（对标 BettaFish SentimentResult）"""
    review_id: Optional[str]
    text: str
    dish_mentions: List[str]          # 评论中提到的菜品
    sentiment: str                    # "positive" / "negative" / "neutral"
    confidence: float                 # 0.0–1.0
    key_points: List[str]             # 关键点：["偏咸", "份量少"] / ["鲜嫩", "够味"]
    success: bool = True
    error_message: str = ""
    analysis_performed: bool = True   # False 表示服务关闭或降级


@dataclass
class DishSentimentSummary:
    """按菜品聚合的情感摘要（屯象OS新增，BettaFish无此概念）"""
    dish_name: str
    total_reviews: int
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_rate: float              # 好评率 0.0–1.0
    negative_rate: float              # 差评率 0.0–1.0
    sentiment_score: float            # 综合情感分 0.0–1.0（用于健康评分加权）
    top_complaints: List[str]         # 高频差评关键词
    top_praises: List[str]            # 高频好评关键词
    sentiment_label: str              # "好评为主" / "差评预警" / "口碑中性" / "数据不足"

    @property
    def sentiment_score_25(self) -> float:
        """0–25 分制，与 dish_health_service 4个维度对齐"""
        return round(self.sentiment_score * 25, 1)


# ─────────────────────────────────────────────────────────────────────────────
# LLM Prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的餐饮评论分析师，帮助餐厅分析顾客评价的情感倾向和关键信息。

你会收到一批餐厅顾客评论（JSON数组），每条包含 id 和 text 字段。
对每条评论，你需要分析：

1. dish_mentions：评论中提到的菜品名称列表（无则为空数组）
2. sentiment：情感倾向，只能是 "positive"、"negative"、"neutral" 之一
3. confidence：置信度 0.0–1.0
4. key_points：2–4个关键词，负面评价提取吐槽点（如"偏咸"、"份量少"），正面评价提取亮点（如"鲜嫩"、"够味"）

输出格式（严格JSON数组，不要有其他文字）：
[
  {{"id": "原始id", "dish_mentions": ["菜品A"], "sentiment": "positive", "confidence": 0.85, "key_points": ["鲜嫩", "入味"]}},
  ...
]

注意：
- key_points 每个词不超过6个字，要具体（"肉偏老"比"口感不好"更有价值）
- 只有清楚提到菜品名时才加入 dish_mentions，不要猜测
- 完全没有实质内容的评论（如"好好好"）标 neutral，confidence=0.5
"""


# ─────────────────────────────────────────────────────────────────────────────
# 服务类
# ─────────────────────────────────────────────────────────────────────────────

class CustomerSentimentService:
    """
    顾客评论情感分析服务

    核心方法：
      analyze_and_aggregate(reviews) → Dict[dish_name, DishSentimentSummary]
        一步完成：批量分析 + 按菜品聚合

      analyze_batch(reviews) → List[SentimentResult]
        仅做情感分析，不聚合

      aggregate_by_dish(results, reviews) → Dict[dish_name, DishSentimentSummary]
        将 SentimentResult 列表聚合为菜品维度摘要
    """

    def __init__(self) -> None:
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    # ── 主入口 ────────────────────────────────────────────────────────────────

    async def analyze_and_aggregate(
        self,
        reviews: List[CustomerReview],
    ) -> Dict[str, DishSentimentSummary]:
        """
        一步完成：批量分析评论 + 按菜品聚合。

        Returns:
            Dict[dish_name, DishSentimentSummary]，失败时返回空字典
        """
        if not _ENABLED or not reviews:
            return {}

        results = await self.analyze_batch(reviews)
        return self.aggregate_by_dish(results, reviews)

    # ── 批量分析 ──────────────────────────────────────────────────────────────

    async def analyze_batch(
        self,
        reviews: List[CustomerReview],
    ) -> List[SentimentResult]:
        """
        批量分析，每 _BATCH_SIZE 条调用一次 LLM。

        任何批次失败时该批次所有评论降级为 neutral/success=False。
        """
        if not _ENABLED:
            return [self._disabled_result(r) for r in reviews]

        all_results: List[SentimentResult] = []
        for i in range(0, len(reviews), _BATCH_SIZE):
            batch = reviews[i: i + _BATCH_SIZE]
            batch_results = await self._analyze_single_batch(batch)
            all_results.extend(batch_results)

        logger.info(
            "sentiment.batch_done",
            total=len(reviews),
            success=sum(1 for r in all_results if r.success),
        )
        return all_results

    @async_graceful_retry(HTTP_RETRY_CONFIG, default_return=None)
    async def _call_llm_batch(self, payload: str) -> Optional[str]:
        """实际 LLM 调用（被 graceful_retry 包裹）。"""
        llm = self._get_llm()
        return await llm.generate(
            prompt=payload,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=512,
        )

    async def _analyze_single_batch(
        self, batch: List[CustomerReview]
    ) -> List[SentimentResult]:
        """处理单个批次，返回与 batch 等长的 SentimentResult 列表。"""
        # 构建输入 payload
        payload_items = [
            {"id": r.review_id or str(i), "text": r.text}
            for i, r in enumerate(batch)
        ]
        payload = json.dumps(payload_items, ensure_ascii=False)

        raw = await self._call_llm_batch(payload)

        if raw is None:
            # graceful_retry 耗尽，全批降级
            logger.warning("sentiment.batch_llm_failed", batch_size=len(batch))
            return [self._fallback_result(r) for r in batch]

        parsed = self._parse_batch_response(raw, batch)
        return parsed

    # ── 聚合 ──────────────────────────────────────────────────────────────────

    def aggregate_by_dish(
        self,
        results: List[SentimentResult],
        reviews: List[CustomerReview],
    ) -> Dict[str, DishSentimentSummary]:
        """
        将 SentimentResult 列表聚合为 Dict[dish_name, DishSentimentSummary]。

        菜品来源优先级：
          1. review.dish_name（预标注）
          2. result.dish_mentions（LLM 提取）
        """
        # dish_name → list of SentimentResult
        dish_results: Dict[str, List[SentimentResult]] = {}

        for res, rev in zip(results, reviews):
            dishes: List[str] = []
            if rev.dish_name:
                dishes = [rev.dish_name]
            elif res.dish_mentions:
                dishes = res.dish_mentions

            for dish in dishes:
                dish_results.setdefault(dish, []).append(res)

        summaries: Dict[str, DishSentimentSummary] = {}
        for dish_name, dish_res_list in dish_results.items():
            summaries[dish_name] = self._build_summary(dish_name, dish_res_list)

        return summaries

    # ── 解析 ──────────────────────────────────────────────────────────────────

    def _parse_batch_response(
        self,
        raw: str,
        batch: List[CustomerReview],
    ) -> List[SentimentResult]:
        """解析 LLM 返回的 JSON 数组，失败时降级。"""
        try:
            json_match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON array found")

            items: List[dict] = json.loads(json_match.group())
            id_to_item: Dict[str, dict] = {str(item.get("id", "")): item for item in items}

            results = []
            for i, rev in enumerate(batch):
                rid = rev.review_id or str(i)
                item = id_to_item.get(rid)
                if item:
                    results.append(SentimentResult(
                        review_id=rev.review_id,
                        text=rev.text,
                        dish_mentions=self._clean_list(item.get("dish_mentions", [])),
                        sentiment=item.get("sentiment", "neutral"),
                        confidence=float(item.get("confidence", 0.5)),
                        key_points=self._clean_list(item.get("key_points", []))[:4],
                        success=True,
                    ))
                else:
                    results.append(self._fallback_result(rev))

            return results

        except Exception as exc:
            logger.warning("sentiment.parse_failed", error=str(exc))
            return [self._fallback_result(r) for r in batch]

    # ── 聚合辅助 ─────────────────────────────────────────────────────────────

    def _build_summary(
        self, dish_name: str, results: List[SentimentResult]
    ) -> DishSentimentSummary:
        total = len(results)
        pos = sum(1 for r in results if r.sentiment == "positive")
        neg = sum(1 for r in results if r.sentiment == "negative")
        neu = total - pos - neg

        pos_rate = pos / total if total else 0.0
        neg_rate = neg / total if total else 0.0

        # 情感综合分：正面加权 1.0，中性 0.5，负面 0.0
        sentiment_score = (pos * 1.0 + neu * 0.5) / total if total else 0.5

        # 高频关键词
        complaint_counter: Counter = Counter()
        praise_counter: Counter = Counter()
        for r in results:
            if r.sentiment == "negative":
                complaint_counter.update(r.key_points)
            elif r.sentiment == "positive":
                praise_counter.update(r.key_points)

        top_complaints = [kw for kw, _ in complaint_counter.most_common(3)]
        top_praises = [kw for kw, _ in praise_counter.most_common(3)]

        # 标签
        if total < 3:
            label = "数据不足"
        elif neg_rate >= _NEGATIVE_ALERT_THRESHOLD:
            label = "差评预警"
        elif pos_rate >= 0.7:
            label = "好评为主"
        else:
            label = "口碑中性"

        return DishSentimentSummary(
            dish_name=dish_name,
            total_reviews=total,
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            positive_rate=round(pos_rate, 3),
            negative_rate=round(neg_rate, 3),
            sentiment_score=round(sentiment_score, 3),
            top_complaints=top_complaints,
            top_praises=top_praises,
            sentiment_label=label,
        )

    # ── 降级辅助 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_result(rev: CustomerReview) -> SentimentResult:
        return SentimentResult(
            review_id=rev.review_id,
            text=rev.text,
            dish_mentions=[rev.dish_name] if rev.dish_name else [],
            sentiment="neutral",
            confidence=0.5,
            key_points=[],
            success=False,
            error_message="LLM分析失败，降级为中性",
        )

    @staticmethod
    def _disabled_result(rev: CustomerReview) -> SentimentResult:
        return SentimentResult(
            review_id=rev.review_id,
            text=rev.text,
            dish_mentions=[rev.dish_name] if rev.dish_name else [],
            sentiment="neutral",
            confidence=0.0,
            key_points=[],
            success=True,
            analysis_performed=False,
        )

    @staticmethod
    def _clean_list(items: list) -> List[str]:
        return [str(x).strip() for x in items if x and str(x).strip()]


# ─────────────────────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────────────────────
customer_sentiment_service = CustomerSentimentService()
