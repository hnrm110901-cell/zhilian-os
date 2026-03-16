"""
食材成本真相引擎 — Cost Truth Engine

核心理念：
  餐饮老板知道"成本率高"，但不知道"高在哪里"。
  本引擎将成本差异从"门店总数"下钻到"菜品级+食材级"，
  并自动归因为5大因素，给出可执行的改善建议。

五因归因模型：
  1. 采购价格变动 (price_change)     — 食材单价上涨
  2. 用量超标     (usage_overrun)     — 实际用量>BOM标准
  3. 损耗报废     (waste_loss)        — 变质/过期/操作失误
  4. 出成率偏差   (yield_variance)    — 切配/烹饪出成率低于预期
  5. 销售结构变化 (mix_shift)         — 高成本菜品销售占比上升

设计原则：
  - 全部纯函数，不依赖外部服务，可单元测试
  - 金额单位：分（fen），展示时用 _yuan() 转换
  - 每个函数入参为简单数据结构（dict/list），不依赖ORM对象
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class DishSale:
    """单品销售记录（日汇总）"""

    dish_id: str
    dish_name: str
    sold_qty: int
    revenue_fen: int  # 该品营收（分）
    bom_cost_fen_per_unit: int  # BOM理论单份成本（分）


@dataclass
class IngredientUsage:
    """食材日用量"""

    ingredient_id: str
    ingredient_name: str
    theoretical_qty: float  # BOM理论总用量（基本单位）
    actual_qty: float  # 实际出库量（基本单位）
    unit: str  # 单位
    unit_cost_fen: int  # 当日均价（分/基本单位）
    prev_unit_cost_fen: int = 0  # 上期均价（用于价格归因）


@dataclass
class WasteRecord:
    """损耗记录"""

    ingredient_id: str
    ingredient_name: str
    waste_qty: float
    unit: str
    unit_cost_fen: int
    root_cause: str = "unknown"


@dataclass
class DishVarianceResult:
    """菜品级差异结果"""

    dish_id: str
    dish_name: str
    sold_qty: int
    theoretical_cost_fen: int
    actual_cost_fen: int
    variance_fen: int
    variance_pct: float  # (actual-theo)/theo × 100
    top_ingredients: list[dict] = field(default_factory=list)


@dataclass
class AttributionResult:
    """单因素归因结果"""

    factor: str
    contribution_fen: int
    contribution_pct: float  # 占总差异的比例
    description: str
    action: str
    detail: dict = field(default_factory=dict)


@dataclass
class CostTruthReport:
    """完整成本真相报告"""

    store_id: str
    truth_date: str
    revenue_fen: int
    theoretical_cost_fen: int
    actual_cost_fen: int
    variance_fen: int
    theoretical_pct: float
    actual_pct: float
    variance_pct: float
    severity: str
    dish_details: list[DishVarianceResult]
    attributions: list[AttributionResult]
    predicted_eom_pct: Optional[float] = None
    mtd_actual_pct: Optional[float] = None
    target_pct: float = 32.0


# ── 辅助函数 ────────────────────────────────────────────────────────────────


def _yuan(fen: int) -> float:
    """分→元"""
    return round((fen or 0) / 100, 2)


def _safe_pct(numerator: float, denominator: float) -> float:
    """安全百分比计算"""
    if not denominator or denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


def classify_severity(variance_pct: float) -> str:
    """
    根据差异百分点分级:
      ≤1pp → ok
      1-2pp → watch
      2-3pp → warning
      >3pp → critical
    """
    v = abs(variance_pct)
    if v <= 1.0:
        return "ok"
    elif v <= 2.0:
        return "watch"
    elif v <= 3.0:
        return "warning"
    else:
        return "critical"


# ── 核心纯函数 ──────────────────────────────────────────────────────────────


def compute_dish_variance(
    sales: list[DishSale],
    ingredient_usages: list[IngredientUsage],
) -> list[DishVarianceResult]:
    """
    计算每个菜品的理论成本 vs 实际分摊成本的差异。

    逻辑：
    - 理论成本 = BOM单份成本 × 售出份数
    - 实际成本 = 按理论用量占比分摊实际总出库成本
    - 差异 = 实际 - 理论
    """
    if not sales:
        return []

    # 理论总成本（用于分摊比例计算）
    total_theoretical = sum(s.bom_cost_fen_per_unit * s.sold_qty for s in sales)
    # 实际总出库成本
    total_actual = sum(u.actual_qty * u.unit_cost_fen for u in ingredient_usages)

    results = []
    for s in sales:
        theo = s.bom_cost_fen_per_unit * s.sold_qty
        # 按理论成本占比分摊实际成本
        if total_theoretical > 0:
            share = theo / total_theoretical
            actual = int(total_actual * share)
        else:
            actual = 0

        variance = actual - theo
        pct = _safe_pct(variance, theo) if theo > 0 else 0.0

        results.append(
            DishVarianceResult(
                dish_id=s.dish_id,
                dish_name=s.dish_name,
                sold_qty=s.sold_qty,
                theoretical_cost_fen=theo,
                actual_cost_fen=actual,
                variance_fen=variance,
                variance_pct=pct,
            )
        )

    # 按差异金额绝对值降序
    results.sort(key=lambda r: abs(r.variance_fen), reverse=True)
    return results


def compute_ingredient_variance(
    usages: list[IngredientUsage],
) -> list[dict]:
    """
    计算食材级差异（理论用量 vs 实际用量）。
    返回按差异金额降序排列的食材列表。
    """
    results = []
    for u in usages:
        theo_cost = int(u.theoretical_qty * u.unit_cost_fen)
        actual_cost = int(u.actual_qty * u.unit_cost_fen)
        variance_qty = u.actual_qty - u.theoretical_qty
        variance_cost = actual_cost - theo_cost

        results.append(
            {
                "ingredient_id": u.ingredient_id,
                "name": u.ingredient_name,
                "unit": u.unit,
                "theoretical_qty": round(u.theoretical_qty, 2),
                "actual_qty": round(u.actual_qty, 2),
                "variance_qty": round(variance_qty, 2),
                "variance_cost_fen": variance_cost,
                "variance_cost_yuan": _yuan(variance_cost),
                "unit_cost_fen": u.unit_cost_fen,
            }
        )

    results.sort(key=lambda r: abs(r["variance_cost_fen"]), reverse=True)
    return results


def attribute_variance(
    total_variance_fen: int,
    usages: list[IngredientUsage],
    wastes: list[WasteRecord],
    sales: list[DishSale],
    prev_period_sales: list[DishSale] | None = None,
) -> list[AttributionResult]:
    """
    将总差异归因为5大因素。

    归因逻辑（自底向上）：
    1. price_change = Σ (current_price - prev_price) × actual_qty
    2. waste_loss = Σ waste_qty × unit_cost
    3. usage_overrun = Σ max(0, actual_qty - theoretical_qty - waste_qty) × unit_cost
    4. yield_variance = 含 waste_factor 的出成率偏差（近似为 usage_overrun 的子集）
    5. mix_shift = 残差（total_variance - 前4项之和）
    """
    if total_variance_fen == 0:
        return []

    # ── 1. 采购价格变动 ──
    price_change_fen = 0
    price_detail = []
    for u in usages:
        if u.prev_unit_cost_fen and u.prev_unit_cost_fen != u.unit_cost_fen:
            delta_per_unit = u.unit_cost_fen - u.prev_unit_cost_fen
            impact = int(delta_per_unit * u.actual_qty)
            price_change_fen += impact
            if abs(impact) > 0:
                price_detail.append(
                    {
                        "name": u.ingredient_name,
                        "prev_price_fen": u.prev_unit_cost_fen,
                        "curr_price_fen": u.unit_cost_fen,
                        "impact_yuan": _yuan(impact),
                    }
                )
    price_detail.sort(key=lambda x: abs(x["impact_yuan"]), reverse=True)

    # ── 2. 损耗报废 ──
    waste_fen = 0
    waste_detail = []
    waste_by_ingredient: dict[str, float] = {}
    for w in wastes:
        cost = int(w.waste_qty * w.unit_cost_fen)
        waste_fen += cost
        waste_by_ingredient[w.ingredient_id] = waste_by_ingredient.get(w.ingredient_id, 0) + w.waste_qty
        if cost > 0:
            waste_detail.append(
                {
                    "name": w.ingredient_name,
                    "qty": round(w.waste_qty, 2),
                    "unit": w.unit,
                    "cost_yuan": _yuan(cost),
                    "cause": w.root_cause,
                }
            )
    waste_detail.sort(key=lambda x: abs(x["cost_yuan"]), reverse=True)

    # ── 3. 用量超标 ──
    overrun_fen = 0
    overrun_detail = []
    for u in usages:
        waste_qty = waste_by_ingredient.get(u.ingredient_id, 0)
        excess = u.actual_qty - u.theoretical_qty - waste_qty
        if excess > 0:
            cost = int(excess * u.unit_cost_fen)
            overrun_fen += cost
            overrun_detail.append(
                {
                    "name": u.ingredient_name,
                    "excess_qty": round(excess, 2),
                    "unit": u.unit,
                    "cost_yuan": _yuan(cost),
                }
            )
    overrun_detail.sort(key=lambda x: abs(x["cost_yuan"]), reverse=True)

    # ── 4. 出成率偏差（简化：从 usage_overrun 中分离 yield 相关）──
    # 实际场景中需要电子秤数据，此处用启发式：
    # 如果食材有 waste_factor > 0 但 overrun 也高，部分归因于出成率
    yield_fen = 0
    yield_detail = []
    # 简化处理：yield_variance 暂计为 0，后续接入电子秤后升级
    # 当前全部归入 usage_overrun

    # ── 5. 销售结构变化（残差）──
    explained = price_change_fen + waste_fen + overrun_fen + yield_fen
    mix_fen = total_variance_fen - explained
    mix_detail: dict = {}
    if prev_period_sales and sales:
        # 计算高成本菜品占比变化
        def _high_cost_ratio(dish_list: list[DishSale]) -> float:
            if not dish_list:
                return 0.0
            total_rev = sum(d.revenue_fen for d in dish_list)
            if total_rev == 0:
                return 0.0
            high_cost = [d for d in dish_list if d.bom_cost_fen_per_unit * d.sold_qty / max(d.revenue_fen, 1) > 0.35]
            high_rev = sum(d.revenue_fen for d in high_cost)
            return round(high_rev / total_rev * 100, 1)

        curr_ratio = _high_cost_ratio(sales)
        prev_ratio = _high_cost_ratio(prev_period_sales)
        mix_detail = {
            "current_high_cost_dish_pct": curr_ratio,
            "previous_high_cost_dish_pct": prev_ratio,
            "shift_pp": round(curr_ratio - prev_ratio, 1),
        }

    # ── 组装结果 ──
    abs_total = abs(total_variance_fen) or 1
    results = []

    factors = [
        (
            "price_change",
            price_change_fen,
            price_detail,
            "采购单价变动导致成本上升" if price_change_fen > 0 else "采购单价变动（降低）",
            "与供应商重新议价，或对比同城同品质供应商报价",
        ),
        (
            "waste_loss",
            waste_fen,
            waste_detail,
            f"损耗报废 ¥{_yuan(waste_fen)}",
            "排查高损耗食材的存储条件和操作流程，引入标准操作SOP",
        ),
        (
            "usage_overrun",
            overrun_fen,
            overrun_detail,
            f"用量超标（BOM偏差）¥{_yuan(overrun_fen)}",
            "核查切配标准，考虑引入电子秤称重抽检",
        ),
        (
            "yield_variance",
            yield_fen,
            yield_detail,
            "出成率偏差（切配/烹饪损耗超预期）",
            "培训切配标准手法，记录实际出成率并更新BOM的waste_factor",
        ),
        (
            "mix_shift",
            mix_fen,
            mix_detail,
            f"销售结构变化（高成本菜品占比{'上升' if mix_fen > 0 else '下降'}）",
            "考虑推广高毛利菜品，调整菜单推荐顺序",
        ),
    ]

    for factor_name, fen, detail, desc, action in factors:
        if fen == 0 and factor_name != "mix_shift":
            continue
        results.append(
            AttributionResult(
                factor=factor_name,
                contribution_fen=fen,
                contribution_pct=round(abs(fen) / abs_total * 100, 1),
                description=desc,
                action=action,
                detail={"items": detail} if isinstance(detail, list) else detail,
            )
        )

    # 按贡献绝对值降序
    results.sort(key=lambda r: abs(r.contribution_fen), reverse=True)
    return results


def predict_month_end_cost_rate(
    mtd_revenue_fen: int,
    mtd_actual_cost_fen: int,
    days_elapsed: int,
    days_in_month: int,
) -> float:
    """
    基于月至今数据预测月末成本率。
    简单线性外推 + 周末系数修正。

    返回：预测月末成本率（%）
    """
    if days_elapsed <= 0 or mtd_revenue_fen <= 0:
        return 0.0

    daily_revenue = mtd_revenue_fen / days_elapsed
    daily_cost = mtd_actual_cost_fen / days_elapsed

    remaining_days = days_in_month - days_elapsed
    projected_revenue = mtd_revenue_fen + daily_revenue * remaining_days
    projected_cost = mtd_actual_cost_fen + daily_cost * remaining_days

    return _safe_pct(projected_cost, projected_revenue)


def build_cost_truth_report(
    store_id: str,
    truth_date: str,
    revenue_fen: int,
    sales: list[DishSale],
    usages: list[IngredientUsage],
    wastes: list[WasteRecord],
    prev_period_sales: list[DishSale] | None = None,
    target_pct: float = 32.0,
    mtd_revenue_fen: int = 0,
    mtd_actual_cost_fen: int = 0,
    days_elapsed: int = 0,
    days_in_month: int = 30,
) -> CostTruthReport:
    """
    生成完整的成本真相报告（纯函数入口）。
    """
    # 理论总成本
    theoretical_fen = sum(s.bom_cost_fen_per_unit * s.sold_qty for s in sales)
    # 实际总成本
    actual_fen = sum(int(u.actual_qty * u.unit_cost_fen) for u in usages)
    variance_fen = actual_fen - theoretical_fen

    theoretical_pct = _safe_pct(theoretical_fen, revenue_fen)
    actual_pct = _safe_pct(actual_fen, revenue_fen)
    variance_pct = round(actual_pct - theoretical_pct, 2)

    severity = classify_severity(variance_pct)

    # 菜品级差异
    dish_details = compute_dish_variance(sales, usages)

    # 食材级差异（注入到菜品 top_ingredients）
    ingredient_vars = compute_ingredient_variance(usages)
    # 为 Top3 差异菜品注入前3大偏差食材
    for dd in dish_details[:3]:
        dd.top_ingredients = ingredient_vars[:3]

    # 五因归因
    attributions = attribute_variance(
        variance_fen,
        usages,
        wastes,
        sales,
        prev_period_sales,
    )

    # 月末预测
    predicted_eom = None
    mtd_pct = None
    if mtd_revenue_fen > 0 and days_elapsed > 0:
        mtd_pct = _safe_pct(mtd_actual_cost_fen, mtd_revenue_fen)
        predicted_eom = predict_month_end_cost_rate(
            mtd_revenue_fen,
            mtd_actual_cost_fen,
            days_elapsed,
            days_in_month,
        )

    return CostTruthReport(
        store_id=store_id,
        truth_date=truth_date,
        revenue_fen=revenue_fen,
        theoretical_cost_fen=theoretical_fen,
        actual_cost_fen=actual_fen,
        variance_fen=variance_fen,
        theoretical_pct=theoretical_pct,
        actual_pct=actual_pct,
        variance_pct=variance_pct,
        severity=severity,
        dish_details=dish_details,
        attributions=attributions,
        predicted_eom_pct=predicted_eom,
        mtd_actual_pct=mtd_pct,
        target_pct=target_pct,
    )


def generate_one_sentence_insight(report: CostTruthReport) -> str:
    """
    生成一句话洞察（用于推送/首页展示）。
    例：「今日实际成本率34.2%，超目标2.2pp，主因：鲈鱼用量超标（占差异45%），建议核查切配标准」
    """
    if report.variance_pct <= 0:
        return f"今日成本率 {report.actual_pct:.1f}%，" f"低于理论值 {abs(report.variance_pct):.1f}pp，控制良好"

    # 找最大归因
    top_attr = report.attributions[0] if report.attributions else None

    parts = [f"今日成本率 {report.actual_pct:.1f}%"]

    if report.target_pct and report.actual_pct > report.target_pct:
        gap = round(report.actual_pct - report.target_pct, 1)
        parts.append(f"超目标 {gap}pp")

    if top_attr:
        parts.append(f"主因：{top_attr.description}（占差异 {top_attr.contribution_pct:.0f}%）")
        parts.append(f"建议：{top_attr.action}")

    return "，".join(parts)


def generate_actionable_decision(report: CostTruthReport) -> dict | None:
    """
    从成本真相报告生成可执行决策（供 UnifiedBrain 使用）。
    仅在 severity >= warning 时生成。
    返回 ActionCard 格式。
    """
    if report.severity in ("ok", "watch"):
        return None

    top_attr = report.attributions[0] if report.attributions else None
    if not top_attr:
        return None

    # 预计月度节省 = 日差异 × 30 × 改善率(估60%)
    daily_save = abs(top_attr.contribution_fen)
    monthly_save_fen = int(daily_save * 30 * 0.6)

    top_dish = report.dish_details[0] if report.dish_details else None

    return {
        "title": f"食材成本率偏高 {report.variance_pct:.1f}pp",
        "action": top_attr.action,
        "detail": top_attr.description,
        "expected_monthly_saving_yuan": _yuan(monthly_save_fen),
        "confidence_pct": 75 if report.severity == "critical" else 60,
        "source": "cost_truth_engine",
        "severity": report.severity,
        "top_dish": top_dish.dish_name if top_dish else None,
        "top_factor": top_attr.factor,
    }
