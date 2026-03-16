"""
决策优先级引擎（Decision Priority Engine）

职责：
  每天从库存告警、食材成本差异和推理引擎建议中汇总候选决策，
  按优先级评分排序后输出 Top 3 推送给老板。

优先级评分公式（v2.0 Toast 建议）：
  score = 0.40 × financial_score
        + 0.30 × urgency_score
        + 0.20 × confidence_score
        + 0.10 × execution_score

  financial_score  = min(100, 预期节省¥ / 月营收 × 10000)
  urgency_score    = 100 / (1 + urgency_hours)
  confidence_score = confidence × 100
  execution_score  = {"easy": 100, "medium": 60, "hard": 30}[execution_difficulty]

决策来源：
  - inventory：InventoryItem 状态为 CRITICAL 或 OUT_OF_STOCK 的补货决策
  - food_cost：FoodCostService 差异分析（warning/critical 级别触发）
  - reasoning：UniversalReasoningEngine 诊断结论（需调用方传入 kpi_context）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.inventory import InventoryItem, InventoryStatus
from src.services.financial_impact_calculator import FinancialImpactCalculator
from src.services.food_cost_service import FoodCostService

logger = structlog.get_logger()

# ── 四个决策推送窗口 ────────────────────────────────────────────────────────────
_DECISION_WINDOWS: List[Tuple[int, int, str]] = [
    (8, 0, "08:00晨推"),
    (12, 0, "12:00午推"),
    (17, 30, "17:30战前"),
    (20, 30, "20:30晚推"),
]

# ── 执行难度 → 执行分映射 ────────────────────────────────────────────────────
_EXECUTION_SCORES: Dict[str, float] = {
    "easy": 100.0,
    "medium": 60.0,
    "hard": 30.0,
}


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DecisionCandidate:
    """单条决策候选（汇总自各数据源）"""

    title: str
    action: str
    source: str  # "inventory" | "food_cost" | "reasoning"
    expected_saving_yuan: float  # 预期节省 ¥
    expected_cost_yuan: float  # 预期成本 ¥（采购/执行成本）
    confidence: float  # 0.0 – 1.0
    urgency_hours: float  # 距最近决策窗口的小时数
    execution_difficulty: str  # "easy" | "medium" | "hard"
    decision_window_label: str  # 推送窗口标签
    context: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数（无 IO，可单元测试）
# ═══════════════════════════════════════════════════════════════════════════════


def _hours_to_next_window(now: datetime) -> Tuple[float, str]:
    """
    计算当前时刻距离最近决策推送窗口的小时数。

    Returns:
        (hours, window_label)：0 表示当前就在窗口内或刚过
    """
    for h, m, label in _DECISION_WINDOWS:
        window = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if window > now:
            delta = (window - now).total_seconds() / 3600
            return round(delta, 2), label
    # 当天所有窗口已过，下一个为明天 08:00晨推
    tomorrow_8 = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    delta = (tomorrow_8 - now).total_seconds() / 3600
    return round(delta, 2), "08:00晨推"


def _score_financial(
    expected_saving_yuan: float,
    monthly_revenue_yuan: float,
) -> float:
    """
    财务影响分（0-100）。

    公式：min(100, 预期节省¥ / 月营收 × 10000)
    含义：节省1%月营收 = 100分
    """
    if monthly_revenue_yuan <= 0 or expected_saving_yuan <= 0:
        return 0.0
    raw = expected_saving_yuan / monthly_revenue_yuan * 10000
    return min(100.0, round(raw, 2))


def _score_urgency(urgency_hours: float) -> float:
    """
    紧急度分（0-100）。

    urgency_hours=0 → 100分；urgency_hours=12 → 约8分
    公式：100 / (1 + urgency_hours)
    """
    if urgency_hours <= 0:
        return 100.0
    return round(100.0 / (1.0 + urgency_hours), 2)


def _score_confidence(confidence: float) -> float:
    """置信度分（0-100）"""
    return round(max(0.0, min(1.0, confidence)) * 100, 2)


def _score_execution(execution_difficulty: str) -> float:
    """执行难度分（0-100）"""
    return _EXECUTION_SCORES.get(execution_difficulty, 60.0)


def compute_priority_score(
    candidate: DecisionCandidate,
    monthly_revenue_yuan: float = 0.0,
) -> float:
    """
    计算候选决策的综合优先级分（0-100）。

    权重：财务40% + 紧急度30% + 置信度20% + 执行10%
    """
    f = _score_financial(candidate.expected_saving_yuan, monthly_revenue_yuan)
    u = _score_urgency(candidate.urgency_hours)
    c = _score_confidence(candidate.confidence)
    e = _score_execution(candidate.execution_difficulty)
    score = 0.40 * f + 0.30 * u + 0.20 * c + 0.10 * e
    return round(score, 2)


def _format_decision(
    candidate: DecisionCandidate,
    priority_score: float,
    rank: int,
) -> dict:
    """将候选决策格式化为推送就绪的 dict（含 ¥ 字段）"""
    roi = FinancialImpactCalculator.decision_roi(
        candidate.expected_saving_yuan,
        candidate.expected_cost_yuan,
    )
    return {
        "rank": rank,
        "title": candidate.title,
        "action": candidate.action,
        "source": candidate.source,
        "expected_saving_yuan": round(candidate.expected_saving_yuan, 2),
        "expected_cost_yuan": round(candidate.expected_cost_yuan, 2),
        "net_benefit_yuan": roi["net_benefit_yuan"],
        "confidence_pct": round(candidate.confidence * 100, 1),
        "urgency_hours": candidate.urgency_hours,
        "execution_difficulty": candidate.execution_difficulty,
        "decision_window_label": candidate.decision_window_label,
        "priority_score": priority_score,
        "context": candidate.context,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DecisionPriorityEngine
# ═══════════════════════════════════════════════════════════════════════════════


class DecisionPriorityEngine:
    """
    决策优先级引擎

    使用方式::

        engine = DecisionPriorityEngine(store_id="S001")
        top3 = await engine.get_top3(db=session)

    每天调用一次，返回最多3条老板需要关注的决策。
    """

    def __init__(self, store_id: str):
        self.store_id = store_id
        self.logger = logger.bind(store_id=store_id, engine="DecisionPriorityEngine")

    # ── 数据源1：库存告警 ───────────────────────────────────────────────────────

    async def _collect_inventory_candidates(
        self,
        urgency_hours: float,
        window_label: str,
        db: AsyncSession,
    ) -> List[DecisionCandidate]:
        """
        从库存告警生成采购决策候选。
        仅处理 CRITICAL 和 OUT_OF_STOCK 状态（最多5项）。
        """
        stmt = (
            select(InventoryItem)
            .where(
                and_(
                    InventoryItem.store_id == self.store_id,
                    or_(
                        InventoryItem.status == InventoryStatus.CRITICAL,
                        InventoryItem.status == InventoryStatus.OUT_OF_STOCK,
                    ),
                )
            )
            .limit(5)
        )
        result = await db.execute(stmt)
        items = result.scalars().all()

        candidates: List[DecisionCandidate] = []
        for item in items:
            unit_cost_yuan = (item.unit_cost or 0) / 100  # fen → yuan
            restock_qty = max(0.0, (item.min_quantity or 0) * 2 - (item.current_quantity or 0))

            purchase = FinancialImpactCalculator.purchase_decision(
                unit_cost_yuan=unit_cost_yuan,
                quantity=restock_qty,
            )

            # 节省估算：缺货导致的收入损失约为补货成本的2倍（保守估计）
            saving_est = round(purchase["total_cost_yuan"] * 2.0, 2)

            is_stockout = item.status == InventoryStatus.OUT_OF_STOCK
            item_urgency = 0.0 if is_stockout else urgency_hours

            candidates.append(
                DecisionCandidate(
                    title=f"{'紧急补货' if is_stockout else '建议补货'}：{item.name}",
                    action=(
                        f"建议立即采购 {restock_qty:.1f} {item.unit or '单位'}，"
                        f"预计成本 ¥{purchase['total_cost_yuan']:.2f}"
                    ),
                    source="inventory",
                    expected_saving_yuan=saving_est,
                    expected_cost_yuan=purchase["total_cost_yuan"],
                    confidence=0.92 if is_stockout else 0.80,
                    urgency_hours=item_urgency,
                    execution_difficulty="easy",
                    decision_window_label="立即" if is_stockout else window_label,
                    context={
                        "item_id": str(item.id),
                        "item_name": item.name,
                        "status": item.status.value if hasattr(item.status, "value") else item.status,
                        "current_quantity": item.current_quantity,
                        "min_quantity": item.min_quantity,
                        "restock_quantity": restock_qty,
                    },
                )
            )
        return candidates

    # ── 数据源2：食材成本差异 ────────────────────────────────────────────────────

    async def _collect_food_cost_candidates(
        self,
        urgency_hours: float,
        window_label: str,
        target_date: date,
        db: AsyncSession,
    ) -> List[DecisionCandidate]:
        """
        从食材成本差异分析生成成本控制决策候选。
        仅处理 warning 或 critical 级别。
        """
        end_date = target_date
        start_date = target_date - timedelta(days=6)  # 过去7天

        try:
            variance = await FoodCostService.get_store_food_cost_variance(
                store_id=self.store_id,
                start_date=start_date,
                end_date=end_date,
                db=db,
            )
        except Exception as exc:
            self.logger.warning("food_cost_variance_failed", error=str(exc))
            return []

        status = variance.get("variance_status", "ok")
        actual_pct = variance.get("actual_cost_pct", 0.0)
        revenue_yuan = variance.get("revenue_yuan", 0.0)

        # 当 BOM/库存流水缺失（actual_pct=0），回退读 kpi_records
        if status == "ok" and actual_pct == 0.0:
            variance = await self._food_cost_from_kpi_records(target_date, db)
            status = variance.get("variance_status", "ok")
            actual_pct = variance.get("actual_cost_pct", 0.0)
            revenue_yuan = variance.get("revenue_yuan", 0.0)

        if status == "ok":
            return []

        variance_pct = variance.get("variance_pct", 0.0)
        monthly_rev = revenue_yuan / 7 * 30  # 周转月营收估算

        # 预期节省：本月内将差异修正到0可节省的¥
        expected_saving = round(monthly_rev * max(0, variance_pct) / 100, 2)
        confidence = 0.85 if status == "critical" else 0.70

        top3_items = variance.get("top_ingredients", [])[:3]
        top3_str = "、".join(i["name"] for i in top3_items) if top3_items else "（无数据）"

        candidates = [
            DecisionCandidate(
                title=f"食材成本率超标 {variance_pct:+.1f}%（当前 {actual_pct:.1f}%）",
                action=(f"关注主要损耗食材：{top3_str}；" f"本月可节省 ¥{expected_saving:.2f}"),
                source="food_cost",
                expected_saving_yuan=expected_saving,
                expected_cost_yuan=0.0,
                confidence=confidence,
                urgency_hours=urgency_hours,
                execution_difficulty="medium",
                decision_window_label=window_label,
                context={
                    "actual_food_cost_pct": actual_pct,
                    "theoretical_food_cost_pct": variance.get("theoretical_pct", 0.0),
                    "variance_pct": variance_pct,
                    "variance_status": status,
                    "start_date": variance.get("start_date"),
                    "end_date": variance.get("end_date"),
                    "top_ingredients": top3_items,
                },
            )
        ]
        return candidates

    # ── 数据源2b：kpi_records 回退（BOM 未配置时） ──────────────────────────────

    async def _food_cost_from_kpi_records(
        self,
        target_date: date,
        db: AsyncSession,
    ) -> dict:
        """
        当 inventory_transactions 为空（BOM 未录入）时，
        直接从 kpi_records 读取 KPI_COST_RATE 最近30天均值，
        与 stores.cost_ratio_target 对比生成 variance。
        """
        try:
            r = await db.execute(
                text(
                    "SELECT AVG(value) AS avg_cost_pct, "
                    "       AVG(kr.previous_value) AS prev_pct "
                    "FROM kpi_records kr "
                    "WHERE kr.store_id = :sid "
                    "  AND kr.kpi_id = 'KPI_COST_RATE' "
                    "  AND kr.record_date >= :start "
                    "  AND kr.record_date <= :end"
                ),
                {
                    "sid": self.store_id,
                    "start": target_date - timedelta(days=29),
                    "end": target_date,
                },
            )
            row = r.fetchone()
            if not row or row[0] is None:
                return {"variance_status": "ok"}

            actual_pct = float(row[0])

            # 读取门店目标成本率
            r2 = await db.execute(
                text("SELECT cost_ratio_target FROM stores WHERE id = :sid"),
                {"sid": self.store_id},
            )
            row2 = r2.fetchone()
            target_pct = float(row2[0]) * 100 if (row2 and row2[0]) else 33.0

            variance_pct = round(actual_pct - target_pct, 2)

            # 读取月营收估算
            r3 = await db.execute(
                text(
                    "SELECT AVG(value) FROM kpi_records "
                    "WHERE store_id = :sid AND kpi_id = 'KPI_REVENUE' "
                    "  AND record_date >= :start AND record_date <= :end"
                ),
                {
                    "sid": self.store_id,
                    "start": target_date - timedelta(days=29),
                    "end": target_date,
                },
            )
            row3 = r3.fetchone()
            avg_daily_revenue = float(row3[0]) if (row3 and row3[0]) else 0.0
            monthly_revenue = avg_daily_revenue * 30

            if variance_pct <= 1.0:
                status = "ok"
            elif variance_pct <= 3.0:
                status = "warning"
            else:
                status = "critical"

            return {
                "variance_status": status,
                "actual_cost_pct": actual_pct,
                "theoretical_pct": target_pct,
                "variance_pct": variance_pct,
                "revenue_yuan": monthly_revenue / 30 * 7,  # 模拟7天营收
                "top_ingredients": [],
                "period_label": "近30天KPI",
            }
        except Exception as exc:
            self.logger.warning("kpi_records_fallback_failed", error=str(exc))
            return {"variance_status": "ok"}

    # ── 数据源3：推理引擎（可选） ─────────────────────────────────────────────────

    async def _collect_reasoning_candidates(
        self,
        urgency_hours: float,
        window_label: str,
        kpi_context: Dict[str, Any],
        db: AsyncSession,
    ) -> List[DecisionCandidate]:
        """
        从 UniversalReasoningEngine 诊断结论生成决策候选。
        仅处理 P1/P2 级别维度。
        """
        try:
            from src.services.reasoning_engine import ReasoningContext, UniversalReasoningEngine

            engine = UniversalReasoningEngine(db)
            ctx = ReasoningContext(
                store_id=self.store_id,
                kpi_context=kpi_context,
            )
            report = await engine.diagnose(ctx)
        except Exception as exc:
            self.logger.warning("reasoning_engine_failed", error=str(exc))
            return []

        candidates: List[DecisionCandidate] = []
        for dim_name, conclusion in (report.dimensions or {}).items():
            if conclusion.severity not in ("P1", "P2"):
                continue
            if not conclusion.recommended_actions:
                continue

            top_action = conclusion.recommended_actions[0]
            # P1 = ¥ 影响更大；P2 稍低
            saving_est = 500.0 if conclusion.severity == "P1" else 200.0
            confidence = conclusion.confidence if conclusion.confidence else 0.75

            candidates.append(
                DecisionCandidate(
                    title=f"[{conclusion.severity}] {dim_name} 维度异常",
                    action=top_action,
                    source="reasoning",
                    expected_saving_yuan=saving_est,
                    expected_cost_yuan=0.0,
                    confidence=confidence,
                    urgency_hours=urgency_hours,
                    execution_difficulty="medium",
                    decision_window_label=window_label,
                    context={
                        "dimension": dim_name,
                        "severity": conclusion.severity,
                        "evidence_chain": (conclusion.evidence_chain or [])[:3],
                        "root_cause": conclusion.root_cause,
                    },
                )
            )
            if len(candidates) >= 3:
                break

        return candidates

    # ── 主入口 ──────────────────────────────────────────────────────────────────

    async def get_top3(
        self,
        db: AsyncSession,
        target_date: Optional[date] = None,
        monthly_revenue_yuan: float = 0.0,
        kpi_context: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        """
        聚合所有数据源的候选决策，按优先级排序后返回 Top 3。

        Args:
            db:                    数据库会话
            target_date:           分析日期（默认今天）
            monthly_revenue_yuan:  月营收估算（用于财务影响分计算，默认0则按绝对金额排序）
            kpi_context:           KPI 上下文字典（可选，用于推理引擎数据源）

        Returns:
            最多3条决策 dict，每条含 title/action/expected_saving_yuan/confidence_pct 等字段
        """
        if target_date is None:
            target_date = date.today()

        now = datetime.now()
        urgency_hours, window_label = _hours_to_next_window(now)

        self.logger.info(
            "get_top3_started",
            target_date=target_date.isoformat(),
            next_window=window_label,
            urgency_hours=urgency_hours,
        )

        # ── 收集所有候选 ──────────────────────────────────────────────────────
        all_candidates: List[DecisionCandidate] = []

        # 源1：库存
        try:
            inv_candidates = await self._collect_inventory_candidates(
                urgency_hours=urgency_hours,
                window_label=window_label,
                db=db,
            )
            all_candidates.extend(inv_candidates)
        except Exception as exc:
            self.logger.warning("inventory_candidates_failed", error=str(exc))

        # 源2：食材成本
        try:
            fc_candidates = await self._collect_food_cost_candidates(
                urgency_hours=urgency_hours,
                window_label=window_label,
                target_date=target_date,
                db=db,
            )
            all_candidates.extend(fc_candidates)
        except Exception as exc:
            self.logger.warning("food_cost_candidates_failed", error=str(exc))

        # 源3：推理引擎（仅当 kpi_context 传入时）
        if kpi_context:
            try:
                rz_candidates = await self._collect_reasoning_candidates(
                    urgency_hours=urgency_hours,
                    window_label=window_label,
                    kpi_context=kpi_context,
                    db=db,
                )
                all_candidates.extend(rz_candidates)
            except Exception as exc:
                self.logger.warning("reasoning_candidates_failed", error=str(exc))

        if not all_candidates:
            self.logger.info("no_candidates_found")
            return []

        # ── 评分 & 排序 ─────────────────────────────────────────────────────
        scored = [(candidate, compute_priority_score(candidate, monthly_revenue_yuan)) for candidate in all_candidates]
        scored.sort(key=lambda x: x[1], reverse=True)

        # ── 格式化 Top 3 ────────────────────────────────────────────────────
        top3 = [_format_decision(candidate, score, rank + 1) for rank, (candidate, score) in enumerate(scored[:3])]

        self.logger.info(
            "get_top3_completed",
            total_candidates=len(all_candidates),
            top3_sources=[d["source"] for d in top3],
        )
        return top3
