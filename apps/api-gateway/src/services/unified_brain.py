"""
Unified Brain — 每日1决策引擎

核心理念：
  不是给老板3-5个建议让他选，而是每天只给1个最高ROI的可执行决策。
  信息过载 = 不行动。1个决策 + 明确操作步骤 = 行动。

决策来源（内部函数，不暴露为独立Agent）：
  1. 食材成本真相引擎 → 成本率偏高时的改善动作
  2. 人力成本分析 → 排班优化/减人增效
  3. 库存预警 → 紧急采购/清理临期
  4. 营收异常 → 促销/菜品调整
  5. 损耗卫士 → 高损耗食材改善

排序公式：
  score = expected_saving_yuan × confidence × urgency_multiplier

设计原则：
  - 纯函数，可单元测试
  - 每天只输出1个最高分决策
  - 决策必须包含：操作步骤 + 预期¥ + 执行人 + 截止时间
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActionCard:
    """一张可执行的决策卡片 — 30秒内能看完、能行动"""
    title: str                        # ≤20字标题
    action: str                       # 具体操作步骤
    expected_saving_yuan: float       # 预计月度节省¥
    confidence_pct: int               # 置信度 0-100
    source: str                       # 来源标识
    severity: str                     # ok/watch/warning/critical
    detail: str = ""                  # 补充说明
    executor: str = "店长"            # 执行人
    deadline_hours: int = 48          # 建议完成时间(小时)
    category: str = "cost"            # cost/labor/inventory/revenue/waste


@dataclass
class BrainInput:
    """Brain的输入上下文"""
    store_id: str
    date: str

    # 食材成本（来自 cost_truth_engine）
    cost_actual_pct: float = 0.0
    cost_target_pct: float = 32.0
    cost_variance_pct: float = 0.0
    cost_top_factor: str = ""
    cost_top_action: str = ""
    cost_saving_yuan: float = 0.0

    # 人力成本
    labor_cost_rate: float = 0.0
    labor_target_rate: float = 25.0
    labor_saving_yuan: float = 0.0
    labor_suggestion: str = ""

    # 库存预警
    critical_inventory_count: int = 0
    inventory_items: list[dict] = field(default_factory=list)  # [{name, qty, reorder_point}]
    inventory_risk_yuan: float = 0.0

    # 营收
    revenue_yesterday_yuan: float = 0.0
    revenue_change_pct: float = 0.0  # vs 上周同天
    revenue_suggestion: str = ""

    # 损耗
    waste_rate_pct: float = 0.0
    waste_target_pct: float = 3.0
    waste_top_item: str = ""
    waste_saving_yuan: float = 0.0
    waste_action: str = ""

    # 上一次建议的执行效果
    last_advice_adopted: bool = False
    last_advice_saving_yuan: float = 0.0


def _score_candidate(card: ActionCard) -> float:
    """
    计算候选决策的综合得分。
    score = saving × confidence × urgency_multiplier
    urgency: critical=2.0, warning=1.5, watch=1.0, ok=0.5
    """
    urgency_map = {"critical": 2.0, "warning": 1.5, "watch": 1.0, "ok": 0.5}
    urgency = urgency_map.get(card.severity, 1.0)
    return card.expected_saving_yuan * (card.confidence_pct / 100) * urgency


def generate_candidates(ctx: BrainInput) -> list[ActionCard]:
    """
    从各维度生成候选决策。每个维度最多1个候选。
    """
    candidates = []

    # ── 1. 食材成本 ──
    if ctx.cost_variance_pct > 1.0 and ctx.cost_saving_yuan > 0:
        severity = "critical" if ctx.cost_variance_pct > 3 else "warning" if ctx.cost_variance_pct > 2 else "watch"
        candidates.append(ActionCard(
            title=f"食材成本超标 {ctx.cost_variance_pct:.1f}pp",
            action=ctx.cost_top_action or f"排查成本偏高原因（主因：{ctx.cost_top_factor}）",
            expected_saving_yuan=ctx.cost_saving_yuan,
            confidence_pct=75 if severity == "critical" else 60,
            source="cost_truth",
            severity=severity,
            detail=f"实际成本率 {ctx.cost_actual_pct:.1f}% vs 目标 {ctx.cost_target_pct:.1f}%",
            category="cost",
        ))

    # ── 2. 人力成本 ──
    labor_gap = ctx.labor_cost_rate - ctx.labor_target_rate
    if labor_gap > 2.0 and ctx.labor_saving_yuan > 0:
        severity = "critical" if labor_gap > 5 else "warning"
        candidates.append(ActionCard(
            title=f"人工成本率偏高 {labor_gap:.1f}pp",
            action=ctx.labor_suggestion or "优化明日排班，减少低效时段人力",
            expected_saving_yuan=ctx.labor_saving_yuan,
            confidence_pct=65,
            source="labor_analysis",
            severity=severity,
            detail=f"当前 {ctx.labor_cost_rate:.1f}% vs 目标 {ctx.labor_target_rate:.1f}%",
            category="labor",
        ))

    # ── 3. 库存紧急 ──
    if ctx.critical_inventory_count > 0:
        items_str = "、".join(i["name"] for i in ctx.inventory_items[:3])
        candidates.append(ActionCard(
            title=f"{ctx.critical_inventory_count}种食材库存告急",
            action=f"立即补货：{items_str}",
            expected_saving_yuan=ctx.inventory_risk_yuan,
            confidence_pct=90,
            source="inventory_alert",
            severity="critical",
            detail=f"缺货可能影响今日营业",
            executor="采购员",
            deadline_hours=4,
            category="inventory",
        ))

    # ── 4. 损耗偏高 ──
    waste_gap = ctx.waste_rate_pct - ctx.waste_target_pct
    if waste_gap > 1.0 and ctx.waste_saving_yuan > 0:
        severity = "warning" if waste_gap > 2 else "watch"
        candidates.append(ActionCard(
            title=f"损耗率偏高（{ctx.waste_top_item}）",
            action=ctx.waste_action or f"排查{ctx.waste_top_item}的存储和操作流程",
            expected_saving_yuan=ctx.waste_saving_yuan,
            confidence_pct=70,
            source="waste_guard",
            severity=severity,
            detail=f"损耗率 {ctx.waste_rate_pct:.1f}% vs 目标 {ctx.waste_target_pct:.1f}%",
            category="waste",
        ))

    # ── 5. 营收异常下降 ──
    if ctx.revenue_change_pct < -15:
        candidates.append(ActionCard(
            title=f"营收同比下降 {abs(ctx.revenue_change_pct):.0f}%",
            action=ctx.revenue_suggestion or "分析客流变化原因，考虑午市引流活动",
            expected_saving_yuan=abs(ctx.revenue_change_pct) * ctx.revenue_yesterday_yuan / 100 * 0.3,
            confidence_pct=50,
            source="revenue_analysis",
            severity="warning",
            detail=f"昨日营收 ¥{ctx.revenue_yesterday_yuan:.0f}",
            category="revenue",
        ))

    return candidates


def pick_top_decision(ctx: BrainInput) -> Optional[ActionCard]:
    """
    每日最重要的1个决策。
    如果没有值得推的决策（全部ok），返回None。
    """
    candidates = generate_candidates(ctx)
    if not candidates:
        return None

    # 按得分排序
    candidates.sort(key=_score_candidate, reverse=True)
    return candidates[0]


def format_push_message(card: ActionCard, cumulative_saving_yuan: float = 0) -> str:
    """
    格式化为30秒可读的推送消息。
    """
    lines = [
        f"🎯 {card.title}",
        "",
        f"📋 操作：{card.action}",
        f"💰 预计月省：¥{card.expected_saving_yuan:,.0f}",
        f"📊 置信度：{card.confidence_pct}%",
        f"👤 执行人：{card.executor}",
        f"⏰ 建议 {card.deadline_hours}h 内完成",
    ]
    if cumulative_saving_yuan > 0:
        lines.append("")
        lines.append(f"✅ 本月AI累计帮您省：¥{cumulative_saving_yuan:,.0f}")

    return "\n".join(lines)
