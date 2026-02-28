"""
L4 通用推理引擎（Universal Reasoning Engine）

设计原则（Naval Knowledge Compounding 复利哲学）：
  - 每次推理消耗已有知识（规则库 + 图谱），而非从零计算
  - 推理结论持久化后可被后续推理引用（知识复利）
  - 多层证据融合：规则命中 + Neo4j 图谱路径 + 同伴组对比

推理流程（L4 五步）：
  Step 1  ContextAssembly    — 组装推理上下文（KPI + 同伴组 + 因果提示）
  Step 2  RuleMatching       — 从规则库匹配所有维度规则（250+ 条）
  Step 3  CrossStoreRules    — 跨店规则匹配（peer.p75 语义解析）
  Step 4  ScoreFusion        — 置信度融合 + 维度严重程度计算
  Step 5  ConclusionOutput   — 输出结构化结论 + 证据链 + 行动建议 + 持久化

与 WasteReasoningEngine 的关系：
  WasteReasoningEngine    = 损耗维度专项引擎（Phase 2，已实现）
  UniversalReasoningEngine = 全维度通用引擎（Phase 4，本模块）
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.knowledge_rule import RuleCategory, RuleStatus
from src.models.reasoning import ReasoningReport, SeverityLevel, ReasoningDimension
from src.services.knowledge_rule_service import KnowledgeRuleService

logger = structlog.get_logger()


# ── 维度 → 规则品类映射 ────────────────────────────────────────────────────────

DIMENSION_CATEGORIES: Dict[str, List[RuleCategory]] = {
    "waste":       [RuleCategory.WASTE],
    "efficiency":  [RuleCategory.EFFICIENCY],
    "quality":     [RuleCategory.QUALITY],
    "cost":        [RuleCategory.COST],
    "inventory":   [RuleCategory.INVENTORY],
    "cross_store": [RuleCategory.CROSS_STORE, RuleCategory.BENCHMARK],
}

ALL_DIMENSIONS = list(DIMENSION_CATEGORIES.keys())

# ── 严重程度阈值（置信度 → P1/P2/P3） ────────────────────────────────────────

SEVERITY_THRESHOLDS = {
    SeverityLevel.P1: 0.80,   # 立即处理
    SeverityLevel.P2: 0.65,   # 本日内处理
    SeverityLevel.P3: 0.50,   # 本周内处理
}

# ── 维度权重（整体健康评分） ──────────────────────────────────────────────────

DIMENSION_WEIGHTS = {
    "waste":       0.30,
    "efficiency":  0.25,
    "cost":        0.20,
    "quality":     0.15,
    "inventory":   0.10,
    "cross_store": 0.00,   # 不计入整体分（作为修正因子）
}

# ── 维度关联 KPI 集合 ─────────────────────────────────────────────────────────

_DIMENSION_METRICS: Dict[str, List[str]] = {
    "waste":       ["waste_rate", "waste_cost_ratio", "spoilage_rate", "bom_compliance"],
    "efficiency":  ["labor_cost_ratio", "revenue_per_staff", "table_turnover",
                    "revenue_per_seat"],
    "cost":        ["food_cost_ratio", "total_cost_ratio", "gross_margin",
                    "cost_ratio"],
    "quality":     ["complaint_rate", "return_rate", "negative_review_rate"],
    "inventory":   ["inventory_turnover_days", "stockout_count", "overstock_cost"],
    "cross_store": ["waste_rate", "cost_ratio", "bom_compliance", "labor_ratio",
                    "menu_coverage", "revenue_per_seat"],
}


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ReasoningContext:
    """推理输入上下文"""
    store_id:     str
    kpi_context:  Dict[str, Any]
    peer_context: Dict[str, float]  = field(default_factory=dict)
    peer_group:   Optional[str]     = None
    causal_hints: List[str]         = field(default_factory=list)
    event_ids:    List[str]         = field(default_factory=list)
    report_date:  date              = field(default_factory=date.today)


@dataclass
class DimensionConclusion:
    """单维度推理结论"""
    dimension:           str
    severity:            str               # P1 / P2 / P3 / OK
    root_cause:          Optional[str]
    confidence:          float
    evidence_chain:      List[str]
    triggered_rules:     List[str]         # rule_codes
    recommended_actions: List[str]
    peer_percentile:     Optional[float]
    peer_context:        Dict[str, float]
    kpi_values:          Dict[str, float]  # 本维度相关 KPI


@dataclass
class StoreHealthReport:
    """门店整体健康报告"""
    store_id:         str
    report_date:      date
    overall_score:    float               # 0-100
    severity_summary: str                 # 全维度中最高严重程度
    dimensions:       Dict[str, DimensionConclusion]
    priority_actions: List[str]           # Top-5 优先行动
    causal_insights:  List[str]           # Neo4j 因果图谱发现
    cross_store_hints: List[str]          # 跨店改善线索
    peer_group:       Optional[str]


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数（无 IO，可单元测试）
# ═══════════════════════════════════════════════════════════════════════════════

def _determine_severity(max_confidence: float) -> str:
    """根据最高规则置信度确定维度严重程度"""
    for level in (SeverityLevel.P1, SeverityLevel.P2, SeverityLevel.P3):
        if max_confidence >= SEVERITY_THRESHOLDS[level]:
            return level.value
    return SeverityLevel.OK.value


def _dimension_health_score(conclusion: DimensionConclusion) -> float:
    """
    维度健康分（0-100）

    基础分 = 100 - 严重程度惩罚
    同伴百分位修正：低于 p50 的门店额外扣分（最多 15 分）
    """
    base = 100.0
    penalty = {"P1": 40.0, "P2": 20.0, "P3": 8.0, "OK": 0.0}
    score = base - penalty.get(conclusion.severity, 0.0)

    if conclusion.peer_percentile is not None:
        pct = float(conclusion.peer_percentile)
        if pct < 25:
            score -= 15.0
        elif pct < 50:
            score -= (50.0 - pct) / 25.0 * 15.0

    return max(0.0, min(100.0, score))


def _calculate_overall_score(dimensions: Dict[str, DimensionConclusion]) -> float:
    """加权计算门店整体健康分"""
    weighted_sum = 0.0
    total_weight = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        if weight <= 0:
            continue
        score = _dimension_health_score(dimensions[dim]) if dim in dimensions else 85.0
        weighted_sum += score * weight
        total_weight += weight
    return round(weighted_sum / total_weight, 1) if total_weight > 0 else 85.0


def _extract_dimension_kpis(
    dimension: str,
    kpi_context: Dict[str, Any],
) -> Dict[str, float]:
    """提取本维度相关 KPI 子集"""
    relevant = _DIMENSION_METRICS.get(dimension, [])
    return {
        k: float(v)
        for k, v in kpi_context.items()
        if k in relevant and isinstance(v, (int, float))
    }


# ═══════════════════════════════════════════════════════════════════════════════
# UniversalReasoningEngine — L4 核心
# ═══════════════════════════════════════════════════════════════════════════════

class UniversalReasoningEngine:
    """
    L4 通用推理引擎

    使用方式::

        async with get_db_session() as session:
            engine = UniversalReasoningEngine(session)
            report = await engine.diagnose(
                store_id="STORE001",
                kpi_context={"waste_rate": 0.15, "labor_cost_ratio": 0.38},
            )
            # report.overall_score  → 72.5
            # report.severity_summary → "P2"
            # report.dimensions["waste"].evidence_chain → [...]
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.rule_svc = KnowledgeRuleService(db)

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    async def diagnose(
        self,
        store_id:     str,
        kpi_context:  Dict[str, Any],
        dimensions:   Optional[List[str]] = None,
        peer_context: Optional[Dict[str, float]] = None,
        causal_hints: Optional[List[str]] = None,
    ) -> StoreHealthReport:
        """
        全维度推理诊断主入口。

        Args:
            store_id:     目标门店 ID
            kpi_context:  KPI 实际值字典（如 {"waste_rate": 0.15, ...}）
            dimensions:   指定推理维度，默认全部 6 维度
            peer_context: 同伴组百分位（{"peer.p50": 0.10, "peer.p75": 0.14, ...}）
            causal_hints: Neo4j 因果提示文本列表（由 CausalGraphService 提供）

        Returns:
            StoreHealthReport — 整体分 / 分维度结论 / 优先行动 / 因果洞察
        """
        target_dims = dimensions or ALL_DIMENSIONS
        peer_ctx    = peer_context or {}
        hints       = causal_hints or []

        ctx = ReasoningContext(
            store_id=store_id,
            kpi_context=kpi_context,
            peer_context=peer_ctx,
            causal_hints=hints,
        )

        conclusions: Dict[str, DimensionConclusion] = {}
        for dim in target_dims:
            conclusions[dim] = await self._reason_dimension(ctx, dim)

        # 持久化 reasoning_reports（upsert）
        await self._persist_conclusions(store_id, conclusions)

        overall_score    = _calculate_overall_score(conclusions)
        severity_summary = self._overall_severity(conclusions)
        priority_actions = self._collect_priority_actions(conclusions)

        return StoreHealthReport(
            store_id=store_id,
            report_date=ctx.report_date,
            overall_score=overall_score,
            severity_summary=severity_summary,
            dimensions=conclusions,
            priority_actions=priority_actions[:5],
            causal_insights=hints,
            cross_store_hints=[
                ev
                for c in conclusions.values()
                if c.dimension == "cross_store"
                for ev in c.evidence_chain
            ],
            peer_group=peer_ctx.get("peer_group"),
        )

    async def reason_single(
        self,
        store_id:     str,
        dimension:    str,
        kpi_context:  Dict[str, Any],
        peer_context: Optional[Dict[str, float]] = None,
    ) -> DimensionConclusion:
        """单维度轻量推理（不全量持久化）"""
        ctx = ReasoningContext(
            store_id=store_id,
            kpi_context=kpi_context,
            peer_context=peer_context or {},
        )
        conclusion = await self._reason_dimension(ctx, dimension)
        # 仅持久化该维度
        await self._persist_conclusions(store_id, {dimension: conclusion})
        return conclusion

    async def list_reports(
        self,
        store_id:   str,
        start_date: Optional[date] = None,
        end_date:   Optional[date] = None,
        dimension:  Optional[str]  = None,
        severity:   Optional[str]  = None,
        limit:      int = 50,
    ) -> List[ReasoningReport]:
        """查询历史推理报告"""
        conditions = [ReasoningReport.store_id == store_id]
        if start_date:
            conditions.append(ReasoningReport.report_date >= start_date)
        if end_date:
            conditions.append(ReasoningReport.report_date <= end_date)
        if dimension:
            conditions.append(ReasoningReport.dimension == dimension)
        if severity:
            conditions.append(ReasoningReport.severity == severity)

        stmt = (
            select(ReasoningReport)
            .where(and_(*conditions))
            .order_by(ReasoningReport.report_date.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def mark_actioned(self, report_id: str, actioned_by: str) -> bool:
        """标记报告已行动（Human-in-the-Loop 闭环）"""
        from sqlalchemy import update
        await self.db.execute(
            update(ReasoningReport)
            .where(ReasoningReport.id == uuid.UUID(report_id))
            .values(
                is_actioned=True,
                actioned_by=actioned_by,
                actioned_at=datetime.utcnow(),
            )
        )
        return True

    # ── 内部推理逻辑（Step 2-4） ───────────────────────────────────────────────

    async def _reason_dimension(
        self,
        ctx: ReasoningContext,
        dimension: str,
    ) -> DimensionConclusion:
        """
        单维度推理核心流程

        Step 2: 从规则库匹配适用规则
        Step 3: 跨店规则匹配（cross_store 维度额外处理 peer.p75 语义）
        Step 4: 置信度融合，确定严重程度，构建证据链
        """
        categories = DIMENSION_CATEGORIES.get(dimension, [])
        matched: List[Dict] = []

        # Step 2: 规则匹配（各规则品类）
        for cat in categories:
            hits = await self.rule_svc.match_rules(ctx.kpi_context, category=cat)
            matched.extend(hits)

        # Step 3: 跨店规则匹配（peer_context 注入）
        if dimension == "cross_store" and ctx.peer_context:
            cross_hits = await self.rule_svc.match_cross_store_rules(
                ctx.kpi_context, ctx.peer_context
            )
            matched.extend(cross_hits)

        if not matched:
            return DimensionConclusion(
                dimension=dimension,
                severity=SeverityLevel.OK.value,
                root_cause=None,
                confidence=0.0,
                evidence_chain=self._build_ok_evidence(dimension, ctx),
                triggered_rules=[],
                recommended_actions=[],
                peer_percentile=ctx.peer_context.get("peer.percentile"),
                peer_context=ctx.peer_context,
                kpi_values=_extract_dimension_kpis(dimension, ctx.kpi_context),
            )

        # Step 4: 置信度融合
        # 按置信度排序，取 Top-1 作为主结论
        matched.sort(key=lambda h: h["confidence"], reverse=True)
        top_rule = matched[0]
        severity = _determine_severity(top_rule["confidence"])

        evidence_chain      = self._build_evidence_chain(matched, ctx)
        recommended_actions = self._collect_actions(matched)

        return DimensionConclusion(
            dimension=dimension,
            severity=severity,
            root_cause=top_rule.get("conclusion", {}).get("root_cause"),
            confidence=top_rule["confidence"],
            evidence_chain=evidence_chain,
            triggered_rules=[h["rule_code"] for h in matched[:5]],
            recommended_actions=recommended_actions,
            peer_percentile=ctx.peer_context.get("peer.percentile"),
            peer_context=ctx.peer_context,
            kpi_values=_extract_dimension_kpis(dimension, ctx.kpi_context),
        )

    # ── 证据链构建 ────────────────────────────────────────────────────────────

    def _build_evidence_chain(
        self,
        matched_rules: List[Dict],
        ctx: ReasoningContext,
    ) -> List[str]:
        """从命中规则 + 同伴组对比 + Neo4j 提示构建可读证据链"""
        evidence: List[str] = []

        # 1. 规则命中证据
        for hit in matched_rules[:3]:
            root_cause = hit.get("conclusion", {}).get("root_cause", "unknown")
            evidence.append(
                f"[{hit['rule_code']}] {hit['name']} "
                f"→ 根因: {root_cause} (置信度: {hit['confidence']:.0%})"
            )

        # 2. 同伴组对比证据
        for metric, val in ctx.kpi_context.items():
            if not isinstance(val, (int, float)):
                continue
            p75 = ctx.peer_context.get("peer.p75")
            p50 = ctx.peer_context.get("peer.p50")
            if p75 and float(val) > float(p75):
                evidence.append(
                    f"[PEER] {metric}={val:.3f} 超过同伴组 p75={p75:.3f}，"
                    f"处于底部 25% 区间"
                )
            elif p50 and float(val) > float(p50):
                evidence.append(
                    f"[PEER] {metric}={val:.3f} 超过同伴组 p50={p50:.3f}，"
                    f"低于中位数水平"
                )

        # 3. Neo4j 因果提示
        for hint in ctx.causal_hints[:2]:
            evidence.append(f"[GRAPH] {hint}")

        return evidence

    def _build_ok_evidence(
        self,
        dimension: str,
        ctx: ReasoningContext,
    ) -> List[str]:
        """无异常时的简短说明"""
        kpi_vals = _extract_dimension_kpis(dimension, ctx.kpi_context)
        if kpi_vals:
            vals_str = ", ".join(f"{k}={v:.3f}" for k, v in list(kpi_vals.items())[:3])
            return [f"[OK] {dimension} 指标正常: {vals_str}"]
        return [f"[OK] {dimension} 维度无规则触发"]

    def _collect_actions(self, matched_rules: List[Dict]) -> List[str]:
        """从命中规则提取行动建议（去重）"""
        seen: set = set()
        actions: List[str] = []
        for hit in matched_rules:
            conclusion = hit.get("conclusion", {})
            action = (
                conclusion.get("action") or
                conclusion.get("recommended_action") or
                conclusion.get("conclusion")
            )
            if action and action not in seen:
                seen.add(action)
                actions.append(action)
        return actions[:5]

    def _collect_priority_actions(
        self,
        conclusions: Dict[str, DimensionConclusion],
    ) -> List[str]:
        """从所有维度结论提取优先行动（P1 → P2 → P3 排序）"""
        order = {"P1": 0, "P2": 1, "P3": 2, "OK": 3}
        sorted_dims = sorted(
            conclusions.values(),
            key=lambda c: order.get(c.severity, 99),
        )
        actions: List[str] = []
        for c in sorted_dims:
            for a in c.recommended_actions:
                if a not in actions:
                    actions.append(a)
        return actions

    def _overall_severity(
        self,
        conclusions: Dict[str, DimensionConclusion],
    ) -> str:
        """取全维度最高严重程度"""
        order = {"P1": 0, "P2": 1, "P3": 2, "OK": 3}
        worst = "OK"
        for c in conclusions.values():
            if order.get(c.severity, 99) < order.get(worst, 99):
                worst = c.severity
        return worst

    # ── 持久化 ────────────────────────────────────────────────────────────────

    async def _persist_conclusions(
        self,
        store_id:    str,
        conclusions: Dict[str, DimensionConclusion],
    ) -> None:
        """
        幂等写入 reasoning_reports（upsert on unique constraint）

        同一 store_id + report_date + dimension 只保留最新一份。
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        today = date.today()
        for dim, c in conclusions.items():
            stmt = (
                pg_insert(ReasoningReport)
                .values(
                    id=uuid.uuid4(),
                    store_id=store_id,
                    report_date=today,
                    dimension=dim,
                    severity=c.severity,
                    root_cause=c.root_cause,
                    confidence=c.confidence,
                    evidence_chain=c.evidence_chain,
                    triggered_rule_codes=c.triggered_rules,
                    recommended_actions=c.recommended_actions,
                    peer_percentile=c.peer_percentile,
                    peer_context=c.peer_context,
                    kpi_snapshot=c.kpi_values,
                )
                .on_conflict_do_update(
                    constraint="uq_reasoning_report_store_date_dim",
                    set_={
                        "severity":              c.severity,
                        "root_cause":            c.root_cause,
                        "confidence":            c.confidence,
                        "evidence_chain":        c.evidence_chain,
                        "triggered_rule_codes":  c.triggered_rules,
                        "recommended_actions":   c.recommended_actions,
                        "peer_percentile":       c.peer_percentile,
                        "peer_context":          c.peer_context,
                        "kpi_snapshot":          c.kpi_values,
                        "updated_at":            datetime.utcnow(),
                    },
                )
            )
            await self.db.execute(stmt)

        await self.db.flush()
        logger.info(
            "推理报告已持久化",
            store_id=store_id,
            dimensions=list(conclusions.keys()),
        )
