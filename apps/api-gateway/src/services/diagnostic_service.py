"""
Onboarding Diagnostic Service

Generates the 8-module AI diagnostic report for newly onboarded brands.
Called after knowledge base construction (Pipeline Stage 5) is complete.

Modules:
  1. 经营概况   — Revenue trend, AOV, customer count, profit rate
  2. 菜品健康度  — Gross margin distribution, fast/slow movers, SKU contribution
  3. 成本结构   — Food/labor/rent/marketing ratios vs industry baseline
  4. 门店效率   — Revenue per sqm, revenue per staff, table turns, store comparison
  5. 供应链风险  — Supplier concentration, payment terms, cost volatility
  6. 客群画像   — RFM segmentation, retention rate, churn warning
  7. 口碑诊断   — Rating trend, complaint root causes, top-5 negative themes
  8. 数字化成熟度 — System coverage, data completeness, automation rate

Scoring: Each module returns a 0-100 health score:
  90-100: 优秀 (green)  | 70-89: 良好 (blue)
  50-69:  需关注 (yellow) | 0-49: 风险 (red)
"""
from __future__ import annotations

import json
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.onboarding import OnboardingRawData, OnboardingTask

logger = structlog.get_logger()

_SCORE_LABELS = {
    (90, 100): ("优秀", "green"),
    (70, 89):  ("良好", "blue"),
    (50, 69):  ("需关注", "yellow"),
    (0,  49):  ("风险",  "red"),
}


def _label(score: int) -> tuple[str, str]:
    for (lo, hi), (label, color) in _SCORE_LABELS.items():
        if lo <= score <= hi:
            return label, color
    return "未知", "grey"


class DiagnosticService:

    def __init__(self, store_id: str, db: AsyncSession):
        self.store_id = store_id
        self.db = db
        self._raw: Dict[str, List[Dict]] = {}

    # ── Entry point ────────────────────────────────────────────────────────────

    @classmethod
    async def generate(cls, store_id: str, db: AsyncSession) -> Dict[str, Any]:
        svc = cls(store_id=store_id, db=db)
        await svc._load_raw_data()

        modules = await svc._build_all_modules()
        total_score = round(
            sum(m["health_score"] for m in modules.values()) / len(modules)
        )
        label, color = _label(total_score)

        # Store report in onboarding_tasks
        await svc._persist_report(modules, total_score)

        return {
            "store_id":    store_id,
            "generated_at": datetime.utcnow().isoformat(),
            "total_score":  total_score,
            "total_label":  label,
            "total_color":  color,
            "modules":      modules,
            "agent_init_params": svc._build_agent_init_params(modules),
        }

    @classmethod
    async def generate_pdf(cls, store_id: str, db: AsyncSession) -> bytes:
        """Generate PDF version of the diagnostic report."""
        report = await cls.generate(store_id=store_id, db=db)
        return _render_pdf(report)

    # ── Module builders ────────────────────────────────────────────────────────

    async def _build_all_modules(self) -> Dict[str, Dict]:
        return {
            "经营概况":    await self._module_revenue_overview(),
            "菜品健康度":   await self._module_menu_health(),
            "成本结构":    await self._module_cost_structure(),
            "门店效率":    await self._module_store_efficiency(),
            "供应链风险":   await self._module_supply_chain(),
            "客群画像":    await self._module_customer_portrait(),
            "口碑诊断":    await self._module_reputation(),
            "数字化成熟度":  await self._module_digital_maturity(),
        }

    async def _module_revenue_overview(self) -> Dict:
        """Module 1: Revenue trend, AOV, profit rate."""
        rows = self._raw.get("D04", [])
        if not rows:
            return self._empty_module("经营概况", 50, "暂无财务月报数据（请导入D04）")

        revenues = [float(r.get("营收", 0) or 0) for r in rows]
        profits = [float(r.get("利润", 0) or 0) for r in rows]
        food_costs = [float(r.get("食材成本", 0) or 0) for r in rows]

        avg_revenue = sum(revenues) / len(revenues) if revenues else 0
        profit_pcts = [p / r * 100 for p, r in zip(profits, revenues) if r > 0]
        avg_profit_pct = sum(profit_pcts) / len(profit_pcts) if profit_pcts else 0
        food_cost_pcts = [f / r * 100 for f, r in zip(food_costs, revenues) if r > 0]
        avg_food_pct = sum(food_cost_pcts) / len(food_cost_pcts) if food_cost_pcts else 0

        # Score: profit rate vs industry baseline (8%)
        if avg_profit_pct >= 12:
            score = 90
        elif avg_profit_pct >= 8:
            score = 75
        elif avg_profit_pct >= 4:
            score = 58
        elif avg_profit_pct >= 0:
            score = 42
        else:
            score = 25

        label, color = _label(score)
        return {
            "health_score":   score,
            "label":          label,
            "color":          color,
            "metrics": {
                "avg_monthly_revenue_yuan":  round(avg_revenue, 2),
                "avg_profit_pct":            round(avg_profit_pct, 2),
                "avg_food_cost_pct":         round(avg_food_pct, 2),
                "months_of_data":            len(rows),
            },
            "insight": f"月均营收 ¥{avg_revenue:,.0f}，利润率 {avg_profit_pct:.1f}%",
            "suggestions": self._revenue_suggestions(avg_profit_pct, avg_food_pct),
        }

    async def _module_menu_health(self) -> Dict:
        """Module 2: SKU gross margin distribution."""
        rows = self._raw.get("D01", [])
        if not rows:
            return self._empty_module("菜品健康度", 50, "暂无菜品主数据（请导入D01）")

        margins = []
        for r in rows:
            price = float(r.get("售价", 0) or 0)
            cost = float(r.get("成本价", 0) or 0)
            if price > 0 and cost > 0:
                margins.append((r.get("菜名", ""), (price - cost) / price * 100))

        if not margins:
            return self._empty_module("菜品健康度", 50, "菜品缺少成本价数据")

        avg_margin = sum(m for _, m in margins) / len(margins)
        low_margin_items = [n for n, m in margins if m < 40]
        high_margin_items = [n for n, m in margins if m >= 65]

        score = min(95, max(20, int(avg_margin * 1.3)))
        label, color = _label(score)

        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics": {
                "total_sku":           len(rows),
                "avg_gross_margin_pct": round(avg_margin, 2),
                "high_margin_count":   len(high_margin_items),
                "low_margin_count":    len(low_margin_items),
                "low_margin_items":    low_margin_items[:5],
            },
            "insight": f"均毛利率 {avg_margin:.1f}%，{len(low_margin_items)} 个SKU毛利低于40%",
            "suggestions": [
                f"检视低毛利菜品定价策略（{', '.join(low_margin_items[:3])}等）" if low_margin_items else None,
                f"强推高毛利菜品（{', '.join(high_margin_items[:3])}等）进入推荐位" if high_margin_items else None,
            ],
        }

    async def _module_cost_structure(self) -> Dict:
        """Module 3: Cost breakdown vs industry baseline."""
        rows = self._raw.get("D04", [])
        if not rows:
            return self._empty_module("成本结构", 50, "暂无财务月报数据")

        revenues = [float(r.get("营收", 0) or 0) for r in rows]
        total_revenue = sum(revenues)

        if total_revenue == 0:
            return self._empty_module("成本结构", 50, "营收数据为零")

        food_pct = sum(float(r.get("食材成本", 0) or 0) for r in rows) / total_revenue * 100
        labor_pct = sum(float(r.get("人力成本", 0) or 0) for r in rows) / total_revenue * 100
        rent_pct = sum(float(r.get("租金", 0) or 0) for r in rows) / total_revenue * 100
        marketing_pct = sum(float(r.get("营销", 0) or 0) for r in rows) / total_revenue * 100

        # Industry baselines
        BASELINE = {"food": 35.0, "labor": 25.0, "rent": 10.0, "marketing": 3.0}
        anomalies = []
        score = 75
        if food_pct > BASELINE["food"] * 1.1:
            anomalies.append(f"食材成本率 {food_pct:.1f}% 高于行业基线 {BASELINE['food']}%")
            score -= 15
        if labor_pct > BASELINE["labor"] * 1.15:
            anomalies.append(f"人力成本率 {labor_pct:.1f}% 高于行业基线 {BASELINE['labor']}%")
            score -= 10

        score = max(20, min(95, score))
        label, color = _label(score)

        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics": {
                "food_cost_pct":     round(food_pct, 2),
                "labor_cost_pct":    round(labor_pct, 2),
                "rent_cost_pct":     round(rent_pct, 2),
                "marketing_cost_pct": round(marketing_pct, 2),
                "baseline":          BASELINE,
            },
            "insight": f"食材{food_pct:.1f}% 人力{labor_pct:.1f}% 租金{rent_pct:.1f}%",
            "suggestions": anomalies or ["成本结构处于合理范围"],
        }

    async def _module_store_efficiency(self) -> Dict:
        """Module 4: Revenue per sqm, store comparison."""
        d03_rows = self._raw.get("D03", [])
        d04_rows = self._raw.get("D04", [])

        if not d03_rows:
            return self._empty_module("门店效率", 50, "暂无门店信息数据（请导入D03）")

        total_revenue = sum(float(r.get("营收", 0) or 0) for r in d04_rows) / max(len(d04_rows), 1)

        store_metrics = []
        for s in d03_rows:
            area = float(s.get("面积", 0) or 0)
            tables = float(s.get("桌台数", 0) or 0)
            rent = float(s.get("月租金", 0) or 0)
            rev_per_sqm = total_revenue / area if area > 0 else None
            rent_to_rev = rent / total_revenue * 100 if total_revenue > 0 else None
            store_metrics.append({
                "name":            s.get("门店名", ""),
                "area":            area,
                "tables":          tables,
                "monthly_rent_yuan": rent,
                "rev_per_sqm_yuan": round(rev_per_sqm, 2) if rev_per_sqm else None,
                "rent_to_rev_pct":  round(rent_to_rev, 2) if rent_to_rev else None,
            })

        avg_rev_sqm = [m["rev_per_sqm_yuan"] for m in store_metrics if m["rev_per_sqm_yuan"]]
        score = 72 if avg_rev_sqm else 50
        label, color = _label(score)

        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics":      {"stores": store_metrics, "store_count": len(d03_rows)},
            "insight":      f"{len(d03_rows)} 家门店数据已分析",
            "suggestions":  ["对比各店坪效，优化低效门店运营策略"],
        }

    async def _module_supply_chain(self) -> Dict:
        """Module 5: Supplier concentration risk."""
        rows = self._raw.get("D02", [])
        if not rows:
            return self._empty_module("供应链风险", 60, "暂无供应商台账数据（可选D02）", is_warning=False)

        categories = [r.get("主供品类", "未知") for r in rows]
        category_counts: Dict[str, int] = {}
        for c in categories:
            category_counts[c] = category_counts.get(c, 0) + 1

        top_category_pct = max(category_counts.values()) / len(rows) * 100 if rows else 0
        score = 80 if top_category_pct < 50 else (60 if top_category_pct < 70 else 40)
        label, color = _label(score)

        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics": {
                "total_supplier_count":   len(rows),
                "category_distribution":  category_counts,
                "top_category_pct":       round(top_category_pct, 1),
            },
            "insight":      f"共 {len(rows)} 家供应商，品类集中度 {top_category_pct:.0f}%",
            "suggestions":  ["分散供应商风险，避免单一品类依赖超过50%"] if top_category_pct > 50 else ["供应链集中度合理"],
        }

    async def _module_customer_portrait(self) -> Dict:
        """Module 6: RFM segmentation from member data."""
        rows = self._raw.get("D05", [])
        if not rows:
            return self._empty_module("客群画像", 50, "暂无会员数据（可选D05）", is_warning=False)

        spends = [float(r.get("累计消费", 0) or 0) for r in rows]
        avg_spend = sum(spends) / len(spends) if spends else 0

        # Simple RFM segmentation based on cumulative spend
        high_value = sum(1 for s in spends if s > avg_spend * 2)
        mid_value = sum(1 for s in spends if avg_spend * 0.5 <= s <= avg_spend * 2)
        low_value = sum(1 for s in spends if s < avg_spend * 0.5)

        score = 75 if len(rows) > 100 else 55
        label, color = _label(score)

        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics": {
                "total_member_count":  len(rows),
                "avg_total_spend_yuan": round(avg_spend, 2),
                "rfm_segments": {
                    "high_value":  high_value,
                    "mid_value":   mid_value,
                    "low_value":   low_value,
                },
            },
            "insight":      f"{len(rows)} 名会员，人均历史消费 ¥{avg_spend:,.0f}",
            "suggestions":  [
                f"高价值会员 {high_value} 名，建议制定专属VIP维系策略",
                f"低活跃会员 {low_value} 名，建议激活唤醒活动",
            ],
        }

    async def _module_reputation(self) -> Dict:
        """Module 7: Review sentiment and complaint analysis."""
        rows = self._raw.get("D09", [])
        if not rows:
            return self._empty_module("口碑诊断", 65, "暂无评价数据（可选D09）", is_warning=False)

        ratings = [float(r.get("评分", 0) or 0) for r in rows if r.get("评分")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        negative = [r.get("评价内容", "") for r in rows if float(r.get("评分", 5) or 5) < 3]

        score = 85 if avg_rating >= 4.5 else (70 if avg_rating >= 4.0 else (50 if avg_rating >= 3.5 else 35))
        label, color = _label(score)

        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics": {
                "total_reviews":    len(rows),
                "avg_rating":       round(avg_rating, 2),
                "negative_count":   len(negative),
                "negative_pct":     round(len(negative) / len(rows) * 100, 1) if rows else 0,
            },
            "insight":      f"{len(rows)} 条评价，均分 {avg_rating:.1f}，差评 {len(negative)} 条",
            "suggestions":  [
                "分析差评主题，重点关注服务和出品速度" if negative else "口碑良好，保持当前服务水准"
            ],
        }

    async def _module_digital_maturity(self) -> Dict:
        """Module 8: Data completeness and system coverage."""
        imported = {dt: bool(rows) for dt, rows in self._raw.items()}
        required_types = {"D01", "D03", "D04", "D08"}
        optional_types = {"D02", "D05", "D06", "D07", "D09", "D10"}

        required_done = sum(1 for dt in required_types if imported.get(dt))
        optional_done = sum(1 for dt in optional_types if imported.get(dt))

        completeness = (required_done / len(required_types) * 60 +
                        optional_done / len(optional_types) * 40)
        score = int(completeness)
        label, color = _label(score)

        missing_required = [dt for dt in required_types if not imported.get(dt)]
        missing_optional = [dt for dt in optional_types if not imported.get(dt)]

        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics": {
                "required_completed":  required_done,
                "required_total":      len(required_types),
                "optional_completed":  optional_done,
                "optional_total":      len(optional_types),
                "data_completeness_pct": round(completeness, 1),
            },
            "insight":      f"数据完整度 {completeness:.0f}%（必填 {required_done}/{len(required_types)}）",
            "suggestions":  (
                [f"补充必填数据: {', '.join(missing_required)}"] if missing_required
                else [f"可补充更多数据提升诊断精度: {', '.join(missing_optional[:3])}"]
            ),
        }

    # ── Agent init params ──────────────────────────────────────────────────────

    def _build_agent_init_params(self, modules: Dict) -> Dict[str, Any]:
        """Extract module findings as Agent initialization parameters."""
        params: Dict[str, Any] = {}

        menu = modules.get("菜品健康度", {})
        if menu.get("metrics"):
            params["inventory_agent"] = {
                "low_margin_items": menu["metrics"].get("low_margin_items", []),
                "avg_gross_margin_pct": menu["metrics"].get("avg_gross_margin_pct"),
            }

        cost = modules.get("成本结构", {})
        if cost.get("metrics"):
            params["decision_agent"] = {
                "food_cost_pct_baseline": cost["metrics"].get("food_cost_pct"),
                "labor_cost_pct_baseline": cost["metrics"].get("labor_cost_pct"),
            }

        members = modules.get("客群画像", {})
        if members.get("metrics"):
            params["private_domain_agent"] = {
                "total_members": members["metrics"].get("total_member_count", 0),
                "rfm_segments": members["metrics"].get("rfm_segments", {}),
            }

        reputation = modules.get("口碑诊断", {})
        if reputation.get("metrics"):
            params["quality_agent"] = {
                "avg_rating_baseline": reputation["metrics"].get("avg_rating"),
                "negative_count": reputation["metrics"].get("negative_count", 0),
            }

        return params

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _load_raw_data(self) -> None:
        """Load all valid raw data into memory, grouped by data_type."""
        res = await self.db.execute(
            select(OnboardingRawData).where(
                OnboardingRawData.store_id == self.store_id,
                OnboardingRawData.is_valid == True,
            )
        )
        for row in res.scalars().all():
            self._raw.setdefault(row.data_type, []).append(row.row_data)

    async def _persist_report(self, modules: Dict, total_score: int) -> None:
        """Save report summary in onboarding_tasks for caching."""
        res = await self.db.execute(
            select(OnboardingTask).where(
                OnboardingTask.store_id == self.store_id,
                OnboardingTask.step == "diagnose",
            )
        )
        task = res.scalar_one_or_none()
        report_summary = {
            "total_score": total_score,
            "generated_at": datetime.utcnow().isoformat(),
            "module_scores": {name: m["health_score"] for name, m in modules.items()},
        }
        if task:
            task.status = "completed"
            task.extra = report_summary
            task.updated_at = datetime.utcnow()
        else:
            self.db.add(OnboardingTask(
                store_id=self.store_id, step="diagnose", status="completed",
                extra=report_summary,
            ))
        await self.db.commit()

    @staticmethod
    def _empty_module(name: str, score: int, reason: str, is_warning: bool = True) -> Dict:
        label, color = _label(score)
        return {
            "health_score": score,
            "label":        label,
            "color":        color,
            "metrics":      {},
            "insight":      reason,
            "suggestions":  [reason] if is_warning else [],
        }

    @staticmethod
    def _revenue_suggestions(profit_pct: float, food_cost_pct: float) -> List[str]:
        tips = []
        if profit_pct < 8:
            tips.append(f"利润率 {profit_pct:.1f}% 低于行业8%基线，建议优化成本结构")
        if food_cost_pct > 38:
            tips.append(f"食材成本率 {food_cost_pct:.1f}% 偏高，建议审查BOM配方和损耗")
        if not tips:
            tips.append("经营数据健康，保持当前策略")
        return tips


# ── PDF rendering ──────────────────────────────────────────────────────────────

def _render_pdf(report: Dict) -> bytes:
    """
    Render diagnostic report as PDF.
    Uses WeasyPrint if available, falls back to plain text PDF via fpdf2.
    """
    try:
        from weasyprint import HTML
        html = _report_to_html(report)
        return HTML(string=html).write_pdf()
    except ImportError:
        pass

    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, f"Diagnostic Report — {report['store_id']}", ln=True)
        pdf.cell(0, 10, f"Total Score: {report['total_score']} ({report['total_label']})", ln=True)
        pdf.ln(5)
        for module_name, module_data in report.get("modules", {}).items():
            score = module_data.get("health_score", 0)
            label = module_data.get("label", "")
            insight = module_data.get("insight", "")
            pdf.set_font("Helvetica", style="B", size=10)
            pdf.cell(0, 8, f"{module_name}: {score}分 ({label})", ln=True)
            pdf.set_font("Helvetica", size=9)
            pdf.multi_cell(0, 6, insight)
            pdf.ln(2)
        return pdf.output()
    except ImportError:
        pass

    # Last resort: UTF-8 text
    lines = [
        f"屯象OS 企业诊断报告",
        f"门店: {report['store_id']}",
        f"综合健康分: {report['total_score']} ({report['total_label']})",
        f"生成时间: {report['generated_at']}",
        "",
    ]
    for name, m in report.get("modules", {}).items():
        lines.append(f"[{name}] {m.get('health_score')}分 — {m.get('insight', '')}")
    return "\n".join(lines).encode("utf-8")


def _report_to_html(report: Dict) -> str:
    modules_html = ""
    for name, m in report.get("modules", {}).items():
        score = m.get("health_score", 0)
        color = m.get("color", "grey")
        insight = m.get("insight", "")
        suggestions = m.get("suggestions", [])
        sugg_html = "".join(f"<li>{s}</li>" for s in suggestions if s)
        modules_html += f"""
        <div class="module" style="border-left: 4px solid {color}; padding: 12px; margin: 12px 0;">
          <h3>{name} <span style="color:{color}">{score}分</span></h3>
          <p>{insight}</p>
          <ul>{sugg_html}</ul>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
      body {{ font-family: sans-serif; padding: 24px; }}
      .header {{ background: #1a1a2e; color: white; padding: 24px; border-radius: 8px; }}
      .score {{ font-size: 48px; font-weight: bold; }}
    </style></head><body>
    <div class="header">
      <h1>屯象OS 企业诊断报告</h1>
      <p>门店: {report['store_id']} | 生成时间: {report['generated_at']}</p>
      <div class="score">{report['total_score']}分</div>
      <p>{report['total_label']}</p>
    </div>
    {modules_html}
    </body></html>"""
