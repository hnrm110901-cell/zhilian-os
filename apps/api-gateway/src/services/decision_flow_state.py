"""
决策推送流程状态（移植自 BettaFish state.py，适配智链OS决策域）

BettaFish 原版：Search / Research / State 三层数据类，记录舆情研究全流程
智链OS改造：DecisionFlowState 记录一次完整决策推送流程的状态快照

核心价值：
  1. 追溯性  — 每次推送生成唯一 flow_id，可查询"今天推了什么、推成功了吗"
  2. 链路完整 — scenario → top3 → narrative → push 结果全程记录，不再散落各变量
  3. P3预留  — debate_rounds / mediator_guidance 槽位为 ForumEngine 仲裁预留
  4. Redis持久 — save_to_redis() 存 24h，支持"今日推送记录"API

用法::

    state = DecisionFlowState.new(store_id="S001", push_window="08:00晨推")
    state.top3_decisions = await engine.get_top3(db=db)
    state.push_sent = True
    state.mark_completed()
    await state.save_to_redis()

    # 后续查询
    state = await DecisionFlowState.load_from_redis("S001", "08:00晨推")
    print(state.flow_id, state.push_sent, state.top3_decisions)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# Redis Key 模板：decision_flow:{store_id}:{date}:{window_slug}
_KEY_TPL = "decision_flow:{store_id}:{date}:{window}"
_TTL_SECONDS = int(86400)   # 默认保留 24 小时


def _window_slug(push_window: str) -> str:
    """'08:00晨推' → '0800_morning'，规范化为 Redis key 安全字符串"""
    return push_window.replace(":", "").replace("·", "_").replace(" ", "_")


# ─────────────────────────────────────────────────────────────────────────────
# 子状态：单条决策的执行记录
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DecisionRecord:
    """
    一条 Top3 决策的执行记录（对标 BettaFish Search 数据类）

    BettaFish Search 记录单次搜索的 query/url/content/score；
    DecisionRecord 记录单条决策的 title/action/saving/approved 状态。
    """
    rank: int                          # 1-3
    title: str
    action: str
    source: str                        # "inventory" / "food_cost" / "reasoning"
    expected_saving_yuan: float
    confidence_pct: float
    approved: Optional[bool] = None    # None=待审批, True=已通过, False=已拒绝
    approved_at: Optional[str] = None  # ISO datetime

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DecisionRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_engine_dict(cls, d: Dict[str, Any], rank: int) -> "DecisionRecord":
        """从 decision_priority_engine.get_top3() 的输出 dict 构建"""
        return cls(
            rank=rank,
            title=d.get("title", ""),
            action=d.get("action", ""),
            source=d.get("source", ""),
            expected_saving_yuan=float(d.get("expected_saving_yuan", 0.0)),
            confidence_pct=float(d.get("confidence_pct", d.get("confidence", 0.0))),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 主状态类
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DecisionFlowState:
    """
    一次完整决策推送流程的状态快照（对标 BettaFish State 数据类）

    BettaFish State 包含 report_structure / researches / final_report；
    DecisionFlowState 包含 scenario / decisions / narrative / push_result。

    生命周期：
        new() → [填充各步骤] → mark_completed() → save_to_redis()
    """

    # ── 标识 ──────────────────────────────────────────────────────────────────
    flow_id: str                           # UUID，本次流程唯一标识
    store_id: str
    push_window: str                       # "08:00晨推" / "12:00午推" / "17:30战前" / "20:30晚推"
    trigger_time: str                      # ISO datetime

    # ── 步骤1：场景识别（scenario_matcher）───────────────────────────────────
    scenario_type: Optional[str] = None    # "peak_hour_surge" / "cost_overrun" / ...
    scenario_label: Optional[str] = None   # "高峰超负荷" / "成本超标" / ...

    # ── 步骤2：Top3 决策（decision_priority_engine）──────────────────────────
    decisions: List[DecisionRecord] = field(default_factory=list)
    total_candidates: int = 0             # 参与评分的候选决策总数

    # ── 步骤3：叙事生成（narrative_engine，可选）──────────────────────────────
    narrative: Optional[str] = None

    # ── 步骤4：推送结果 ────────────────────────────────────────────────────────
    push_sent: bool = False
    push_message_id: Optional[str] = None
    push_error: Optional[str] = None

    # ── 审批追踪 ───────────────────────────────────────────────────────────────
    pending_count: int = 0               # 待审批决策数
    approved_count: int = 0

    # ── P3 ForumEngine 预留槽位 ────────────────────────────────────────────────
    debate_rounds: int = 0
    mediator_guidance: Optional[str] = None   # 主持人 LLM 的仲裁意见

    # ── 完成标记 ───────────────────────────────────────────────────────────────
    completed_at: Optional[str] = None    # ISO datetime，None 表示流程未结束

    # ─────────────────────────────────────────────────────────────────────────
    # 工厂方法
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def new(cls, store_id: str, push_window: str) -> "DecisionFlowState":
        """创建一个新的空白流程状态。"""
        return cls(
            flow_id=str(uuid.uuid4()),
            store_id=store_id,
            push_window=push_window,
            trigger_time=datetime.now().isoformat(),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 状态填充辅助
    # ─────────────────────────────────────────────────────────────────────────

    def set_decisions_from_engine(
        self, engine_output: List[Dict[str, Any]], total_candidates: int = 0
    ) -> None:
        """从 decision_priority_engine.get_top3() 的输出填充 decisions 列表。"""
        self.decisions = [
            DecisionRecord.from_engine_dict(d, rank=i + 1)
            for i, d in enumerate(engine_output)
        ]
        self.total_candidates = total_candidates
        self.pending_count = len(self.decisions)

    def mark_completed(self) -> None:
        """标记流程完成，记录完成时间。"""
        self.completed_at = datetime.now().isoformat()

    # ─────────────────────────────────────────────────────────────────────────
    # 序列化（对标 BettaFish to_dict / from_dict）
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # decisions 已被 asdict 递归处理为 List[dict]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionFlowState":
        decisions_raw = data.pop("decisions", [])
        state = cls(**{
            k: v for k, v in data.items()
            if k in cls.__dataclass_fields__
        })
        state.decisions = [DecisionRecord.from_dict(d) for d in decisions_raw]
        return state

    def summary(self) -> Dict[str, Any]:
        """
        精简摘要，适合 API 响应（不含大型列表详情）。

        对标 BettaFish State.get_summary()，返回流程关键指标。
        """
        return {
            "flow_id":          self.flow_id,
            "store_id":         self.store_id,
            "push_window":      self.push_window,
            "trigger_time":     self.trigger_time,
            "scenario":         self.scenario_label or self.scenario_type,
            "decision_count":   len(self.decisions),
            "total_saving_yuan": sum(d.expected_saving_yuan for d in self.decisions),
            "push_sent":        self.push_sent,
            "push_message_id":  self.push_message_id,
            "pending_count":    self.pending_count,
            "completed_at":     self.completed_at,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Redis 持久化
    # ─────────────────────────────────────────────────────────────────────────

    def _redis_key(self, target_date: Optional[date] = None) -> str:
        d = (target_date or date.today()).isoformat()
        return _KEY_TPL.format(
            store_id=self.store_id,
            date=d,
            window=_window_slug(self.push_window),
        )

    async def save_to_redis(
        self,
        ttl_seconds: int = _TTL_SECONDS,
        target_date: Optional[date] = None,
    ) -> bool:
        """
        将当前状态序列化后存入 Redis。

        失败时静默记录日志，不抛异常（不阻塞推送主流程）。
        """
        try:
            from .redis_cache_service import redis_cache
            key = self._redis_key(target_date)
            await redis_cache.set(key, self.to_dict(), expire=ttl_seconds)
            logger.info(
                "decision_flow_state.saved",
                flow_id=self.flow_id,
                key=key,
            )
            return True
        except Exception as exc:
            logger.warning(
                "decision_flow_state.save_failed",
                flow_id=self.flow_id,
                error=str(exc),
            )
            return False

    @classmethod
    async def load_from_redis(
        cls,
        store_id: str,
        push_window: str,
        target_date: Optional[date] = None,
    ) -> Optional["DecisionFlowState"]:
        """
        从 Redis 读取指定门店、推送窗口、日期的流程状态。

        Returns:
            DecisionFlowState 实例，不存在或失败时返回 None。
        """
        try:
            from .redis_cache_service import redis_cache
            key = _KEY_TPL.format(
                store_id=store_id,
                date=(target_date or date.today()).isoformat(),
                window=_window_slug(push_window),
            )
            data = await redis_cache.get(key)
            if data is None:
                return None
            return cls.from_dict(data)
        except Exception as exc:
            logger.warning(
                "decision_flow_state.load_failed",
                store_id=store_id,
                push_window=push_window,
                error=str(exc),
            )
            return None
