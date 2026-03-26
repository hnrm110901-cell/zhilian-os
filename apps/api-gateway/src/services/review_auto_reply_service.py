"""
大众点评评价自动回复服务（Review Auto-Reply Service）

核心功能：
- 评价分类（好评/中评/差评/恶意）+ 情感分析
- AI 起草回复（基于模板 + 关键词匹配）
- 差评紧急度判定 + 告警推送
- 店长审核发布
- 回复统计

金额单位：分（fen），API 返回时 /100 转元
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class ReviewClassification(str, Enum):
    """评价分类"""
    POSITIVE = "好评"
    NEUTRAL = "中评"
    NEGATIVE = "差评"
    MALICIOUS = "恶意"


class UrgencyLevel(str, Enum):
    """紧急度"""
    P1 = "P1"  # 1星，立即处理
    P2 = "P2"  # 2-3星，当日处理
    P3 = "P3"  # 4星，常规回复
    P4 = "P4"  # 5星，批量回复即可


class ReviewCategory(str, Enum):
    """评价类别"""
    FOOD = "菜品"
    SERVICE = "服务"
    ENVIRONMENT = "环境"
    PRICE = "价格"
    WAIT_TIME = "等位"
    HYGIENE = "卫生"
    OTHER = "其他"


class ReplyStatus(str, Enum):
    """回复状态"""
    DRAFT = "草稿"
    PENDING = "待审核"
    APPROVED = "已审核"
    PUBLISHED = "已发布"
    REJECTED = "已驳回"


# ── 情感关键词库 ─────────────────────────────────────────────────────────

POSITIVE_KEYWORDS = [
    "好吃", "美味", "新鲜", "热情", "周到", "不错", "推荐", "满意",
    "惊喜", "超值", "环境好", "干净", "回头客", "强烈推荐", "五星",
    "赞", "棒", "喜欢", "服务好", "味道好", "性价比高", "点赞",
]

NEGATIVE_KEYWORDS = [
    "难吃", "不新鲜", "态度差", "服务差", "脏", "贵", "坑",
    "等太久", "冷了", "不卫生", "失望", "后悔", "投诉", "退款",
    "差评", "恶心", "不会再来", "上菜慢", "苍蝇", "头发",
    "拉肚子", "食物中毒", "过期", "变质",
]

MALICIOUS_KEYWORDS = [
    "敲诈", "同行", "刷差评", "威胁", "勒索",
]

# ── 评价类别关键词 ─────────────────────────────────────────────────────────

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "菜品": ["菜", "味道", "好吃", "难吃", "新鲜", "不新鲜", "口味", "量", "份量", "食材"],
    "服务": ["服务", "态度", "热情", "冷淡", "服务员", "上菜", "催菜", "忽视"],
    "环境": ["环境", "装修", "氛围", "噪音", "位置", "停车", "空间"],
    "价格": ["价格", "贵", "便宜", "性价比", "值", "不值", "坑"],
    "等位": ["等位", "排队", "等了", "等太久", "预约"],
    "卫生": ["卫生", "干净", "脏", "苍蝇", "头发", "异物"],
}

# ── 回复模板库（按评分 × 类别组合） ─────────────────────────────────────────

REPLY_TEMPLATES: Dict[str, Dict[str, List[str]]] = {
    "5星": {
        "菜品": [
            "感谢您对我们菜品的认可！{store_name}坚持使用新鲜食材，您的好评是我们最大的动力。期待您再次光临，品尝更多特色菜品~",
            "非常感谢您的五星好评！我们的厨师团队一直精益求精，很高兴您喜欢我们的出品。欢迎下次带朋友一起来{store_name}~",
        ],
        "服务": [
            "感谢您对{store_name}服务的肯定！我们会将您的表扬转达给服务团队，期待为您提供更好的用餐体验~",
        ],
        "默认": [
            "感谢您的好评！{store_name}全体员工期待您再次光临~",
        ],
    },
    "4星": {
        "菜品": [
            "感谢光临{store_name}！很高兴您喜欢我们的菜品。如果有任何建议，我们非常愿意倾听，持续为您改进~",
        ],
        "服务": [
            "感谢您的评价！我们会继续提升服务品质。如有未尽完善之处，欢迎随时告诉我们~",
        ],
        "默认": [
            "感谢您的四星评价！我们会继续努力，争取下次获得您的满分认可~",
        ],
    },
    "3星": {
        "菜品": [
            "感谢您的中肯评价。关于菜品体验，我们非常重视您的反馈。能否告诉我们具体哪道菜需要改进？我们一定认真对待~",
        ],
        "服务": [
            "感谢您的反馈。对于服务方面的不足，我们深感抱歉。已安排店长复盘并改进，希望下次能给您更好的体验~",
        ],
        "默认": [
            "感谢您抽出时间评价{store_name}。您的建议对我们非常重要，我们会认真改进，欢迎您再给我们一次机会~",
        ],
    },
    "2星": {
        "菜品": [
            "非常抱歉给您带来不好的用餐体验！关于菜品问题，店长已高度重视，会立即排查。方便的话请联系我们（电话/微信），我们希望当面向您致歉并解决问题。",
        ],
        "服务": [
            "对于服务体验不佳，我们深表歉意！已对当班员工进行培训提升。为表诚意，下次光临请出示此评价，我们将赠送甜品一份~",
        ],
        "默认": [
            "非常抱歉让您失望了！{store_name}店长亲自关注了您的评价，我们一定改进。期待有机会重新为您服务~",
        ],
    },
    "1星": {
        "菜品": [
            "非常抱歉！看到您的评价我们非常痛心。关于菜品问题，店长已第一时间介入排查。诚邀您联系我们（店长电话：XXX），我们希望当面致歉并给您一个满意的解决方案。",
        ],
        "服务": [
            "对于如此糟糕的服务体验，我们深感歉疚！店长已对此事进行严肃处理。请您联系我们，我们愿意全额补偿并重新为您提供一次完美的用餐体验。",
        ],
        "卫生": [
            "看到您反映的卫生问题，我们非常重视！已立即安排全面检查和整改。请您联系店长（电话：XXX），我们会给您一个负责任的答复。食品安全是我们的底线。",
        ],
        "默认": [
            "非常抱歉给您带来如此不愉快的体验！店长已亲自关注此事。请联系我们，我们会认真对待每一个问题，给您一个满意的答复。",
        ],
    },
}


@dataclass
class ReviewData:
    """评价数据"""
    review_id: str
    content: str
    rating: int  # 1-5
    customer_name: str = ""
    platform: str = "大众点评"
    created_at: str = ""
    images: List[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    """分类结果"""
    classification: str  # 好评/中评/差评/恶意
    category: str  # 菜品/服务/环境/价格/等位/卫生/其他
    sentiment_score: float  # -1.0 ~ 1.0
    positive_keywords: List[str]
    negative_keywords: List[str]
    confidence: float


@dataclass
class ReplyDraft:
    """回复草稿"""
    review_id: str
    draft_text: str
    template_source: str  # 使用的模板类别
    personalization_notes: str  # 个性化说明
    suggested_urgency: str


@dataclass
class AlertInfo:
    """差评告警"""
    alert_id: str
    review_id: str
    urgency: str
    store_name: str
    review_content: str
    rating: int
    classification: str
    category: str
    suggested_action: str
    created_at: str
    notify_channels: List[str]


@dataclass
class ReplyRecord:
    """回复记录"""
    review_id: str
    reply_text: str
    status: str
    approver_id: Optional[str] = None
    approved_at: Optional[str] = None
    response_time_minutes: int = 0


@dataclass
class ReplyStats:
    """回复统计"""
    total_reviews: int
    replied_count: int
    reply_rate: float  # 回复率 %
    avg_response_minutes: float
    positive_count: int
    neutral_count: int
    negative_count: int
    malicious_count: int
    by_category: Dict[str, int]
    urgency_distribution: Dict[str, int]
    rating_trend: str  # 上升/下降/平稳


class ReviewAutoReplyService:
    """
    大众点评评价自动回复服务

    管理评价分类、自动回复起草、差评告警、审核发布全流程。
    """

    def __init__(self) -> None:
        self._logger = logger.bind(service="review_auto_reply")
        # 回复记录：review_id → ReplyRecord
        self._replies: Dict[str, ReplyRecord] = {}
        # 告警记录：alert_id → AlertInfo
        self._alerts: Dict[str, AlertInfo] = {}

    def classify_review(
        self, content: str, rating: int
    ) -> ClassificationResult:
        """
        评价分类 + 情感分析

        Args:
            content: 评价文本
            rating: 评分 1-5
        """
        # 关键词匹配
        pos_found = [kw for kw in POSITIVE_KEYWORDS if kw in content]
        neg_found = [kw for kw in NEGATIVE_KEYWORDS if kw in content]
        mal_found = [kw for kw in MALICIOUS_KEYWORDS if kw in content]

        # 情感分数：基于评分 + 关键词
        base_sentiment = (rating - 3) / 2.0  # 映射到 -1.0 ~ 1.0
        keyword_sentiment = (len(pos_found) - len(neg_found)) / max(
            1, len(pos_found) + len(neg_found)
        )
        sentiment_score = round(base_sentiment * 0.6 + keyword_sentiment * 0.4, 2)
        sentiment_score = max(-1.0, min(1.0, sentiment_score))

        # 分类
        if mal_found:
            classification = ReviewClassification.MALICIOUS.value
        elif rating >= 4 and sentiment_score >= 0:
            classification = ReviewClassification.POSITIVE.value
        elif rating <= 2 or sentiment_score <= -0.3:
            classification = ReviewClassification.NEGATIVE.value
        else:
            classification = ReviewClassification.NEUTRAL.value

        # 类别检测
        category = self._detect_category(content)

        # 置信度
        total_keywords = len(pos_found) + len(neg_found) + len(mal_found)
        confidence = min(0.95, 0.5 + total_keywords * 0.08)

        self._logger.info(
            "评价分类完成",
            rating=rating,
            classification=classification,
            category=category,
            sentiment=sentiment_score,
        )

        return ClassificationResult(
            classification=classification,
            category=category,
            sentiment_score=sentiment_score,
            positive_keywords=pos_found,
            negative_keywords=neg_found,
            confidence=round(confidence, 2),
        )

    def generate_reply_draft(
        self,
        review: ReviewData,
        store_name: str,
        classification: ClassificationResult,
    ) -> ReplyDraft:
        """
        AI 起草回复（基于模板 + 关键词匹配）

        Args:
            review: 评价数据
            store_name: 门店名称
            classification: 分类结果
        """
        rating_key = f"{review.rating}星"
        category = classification.category

        # 查找模板
        rating_templates = REPLY_TEMPLATES.get(rating_key, REPLY_TEMPLATES.get("3星", {}))
        category_templates = rating_templates.get(category, rating_templates.get("默认", []))

        if not category_templates:
            category_templates = REPLY_TEMPLATES["3星"]["默认"]

        # 选择模板（简单轮转，基于review_id的hash）
        idx = hash(review.review_id) % len(category_templates)
        template = category_templates[idx]

        # 替换变量
        draft_text = template.replace("{store_name}", store_name)

        # 针对差评添加个性化元素
        personalization = ""
        if classification.negative_keywords:
            mentioned_issues = "、".join(classification.negative_keywords[:3])
            personalization = f"顾客提到：{mentioned_issues}"
            # 在回复中加入针对性说明
            if review.rating <= 2 and classification.negative_keywords:
                draft_text += f"\n\n针对您提到的{mentioned_issues}问题，我们已记录并安排专项改进。"

        # 针对好评提及的亮点强化
        if classification.positive_keywords and review.rating >= 4:
            highlights = "、".join(classification.positive_keywords[:2])
            personalization = f"顾客亮点：{highlights}"

        urgency = self.check_urgency(review).get("urgency", "P4")

        self._logger.info(
            "回复草稿生成",
            review_id=review.review_id,
            rating=review.rating,
            urgency=urgency,
        )

        return ReplyDraft(
            review_id=review.review_id,
            draft_text=draft_text,
            template_source=f"{rating_key}/{category}",
            personalization_notes=personalization,
            suggested_urgency=urgency,
        )

    def check_urgency(self, review: ReviewData) -> Dict[str, Any]:
        """
        差评紧急度判定

        规则：
        - 1星 → P1 立即处理
        - 2-3星 → P2 当日处理
        - 4星 → P3 常规回复
        - 5星 → P4 批量回复即可

        Args:
            review: 评价数据
        """
        if review.rating == 1:
            urgency = UrgencyLevel.P1.value
            action = "立即处理：店长15分钟内响应，优先联系顾客挽回"
            deadline_hours = 1
        elif review.rating in (2, 3):
            urgency = UrgencyLevel.P2.value
            action = "当日处理：4小时内回复，安排店长跟进"
            deadline_hours = 4
        elif review.rating == 4:
            urgency = UrgencyLevel.P3.value
            action = "常规回复：24小时内回复"
            deadline_hours = 24
        else:
            urgency = UrgencyLevel.P4.value
            action = "批量回复：48小时内统一回复好评"
            deadline_hours = 48

        # 特殊关键词升级（食品安全相关直接升P1）
        food_safety_keywords = ["食物中毒", "拉肚子", "过期", "变质", "苍蝇", "异物"]
        for kw in food_safety_keywords:
            if kw in review.content:
                urgency = UrgencyLevel.P1.value
                action = "【食品安全】立即处理：店长+区域经理同时响应"
                deadline_hours = 1
                break

        return {
            "review_id": review.review_id,
            "rating": review.rating,
            "urgency": urgency,
            "action": action,
            "deadline_hours": deadline_hours,
            "is_food_safety": urgency == UrgencyLevel.P1.value and review.rating > 1,
        }

    def create_alert(
        self,
        review: ReviewData,
        urgency: str,
        store_name: str = "",
    ) -> AlertInfo:
        """
        生成差评告警

        Args:
            review: 评价数据
            urgency: 紧急度（P1/P2/P3/P4）
            store_name: 门店名称
        """
        alert_id = str(uuid.uuid4())[:12]

        classification = self.classify_review(review.content, review.rating)

        # 通知渠道
        if urgency == "P1":
            channels = ["企业微信", "短信", "电话"]
            action = f"【紧急】{store_name}收到1星差评，请立即处理"
        elif urgency == "P2":
            channels = ["企业微信"]
            action = f"【注意】{store_name}收到差评（{review.rating}星），请当日处理"
        else:
            channels = ["企业微信"]
            action = f"{store_name}收到{review.rating}星评价，请安排回复"

        alert = AlertInfo(
            alert_id=alert_id,
            review_id=review.review_id,
            urgency=urgency,
            store_name=store_name,
            review_content=review.content[:200],  # 截断防过长
            rating=review.rating,
            classification=classification.classification,
            category=classification.category,
            suggested_action=action,
            created_at=datetime.now().isoformat(),
            notify_channels=channels,
        )

        self._alerts[alert_id] = alert

        self._logger.info(
            "差评告警已创建",
            alert_id=alert_id,
            urgency=urgency,
            rating=review.rating,
            channels=channels,
        )

        return alert

    def approve_reply(
        self,
        review_id: str,
        approver_id: str,
        final_text: str,
    ) -> Dict[str, Any]:
        """
        店长审核发布回复

        Args:
            review_id: 评价ID
            approver_id: 审核人ID
            final_text: 最终回复文本
        """
        if not final_text or not final_text.strip():
            return {"error": "回复内容不能为空"}

        if len(final_text) > 500:
            return {"error": "回复内容不能超过500字"}

        record = ReplyRecord(
            review_id=review_id,
            reply_text=final_text.strip(),
            status=ReplyStatus.APPROVED.value,
            approver_id=approver_id,
            approved_at=datetime.now().isoformat(),
        )

        self._replies[review_id] = record

        self._logger.info(
            "回复已审核通过",
            review_id=review_id,
            approver=approver_id,
        )

        return {
            "review_id": review_id,
            "status": "approved",
            "approver_id": approver_id,
            "reply_text": final_text.strip(),
            "message": "回复已审核通过，可发布到点评平台",
        }

    def get_reply_stats(
        self,
        reviews: List[ReviewData],
        period: str = "7d",
    ) -> ReplyStats:
        """
        回复统计

        Args:
            reviews: 评价列表
            period: 统计周期（7d/30d/90d）
        """
        total = len(reviews)
        if total == 0:
            return ReplyStats(
                total_reviews=0, replied_count=0, reply_rate=0.0,
                avg_response_minutes=0.0, positive_count=0, neutral_count=0,
                negative_count=0, malicious_count=0, by_category={},
                urgency_distribution={}, rating_trend="数据不足",
            )

        # 分类统计
        positive = neutral = negative = malicious = 0
        categories: Dict[str, int] = {}
        urgencies: Dict[str, int] = {}

        for review in reviews:
            cls = self.classify_review(review.content, review.rating)
            if cls.classification == "好评":
                positive += 1
            elif cls.classification == "中评":
                neutral += 1
            elif cls.classification == "差评":
                negative += 1
            else:
                malicious += 1

            categories[cls.category] = categories.get(cls.category, 0) + 1

            urg = self.check_urgency(review)
            u = urg["urgency"]
            urgencies[u] = urgencies.get(u, 0) + 1

        # 回复率
        replied = sum(1 for r in reviews if r.review_id in self._replies)
        reply_rate = round(replied / total * 100, 1)

        # 平均响应时间（模拟）
        response_times = []
        for r in reviews:
            if r.review_id in self._replies:
                rec = self._replies[r.review_id]
                response_times.append(rec.response_time_minutes)
        avg_response = round(_mean(response_times), 1) if response_times else 0.0

        # 评分趋势（前半 vs 后半）
        if len(reviews) >= 4:
            mid = len(reviews) // 2
            first_avg = _mean([r.rating for r in reviews[:mid]])
            second_avg = _mean([r.rating for r in reviews[mid:]])
            if second_avg - first_avg > 0.2:
                trend = "上升"
            elif first_avg - second_avg > 0.2:
                trend = "下降"
            else:
                trend = "平稳"
        else:
            trend = "数据不足"

        self._logger.info(
            "回复统计完成",
            total=total,
            reply_rate=reply_rate,
            negative=negative,
        )

        return ReplyStats(
            total_reviews=total,
            replied_count=replied,
            reply_rate=reply_rate,
            avg_response_minutes=avg_response,
            positive_count=positive,
            neutral_count=neutral,
            negative_count=negative,
            malicious_count=malicious,
            by_category=categories,
            urgency_distribution=urgencies,
            rating_trend=trend,
        )

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _detect_category(self, content: str) -> str:
        """检测评价类别（基于关键词匹配得分）"""
        scores: Dict[str, int] = {}
        for cat, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                scores[cat] = score

        if not scores:
            return ReviewCategory.OTHER.value

        return max(scores, key=scores.get)


def _mean(values: List[float]) -> float:
    """计算平均值"""
    if not values:
        return 0.0
    return sum(values) / len(values)
