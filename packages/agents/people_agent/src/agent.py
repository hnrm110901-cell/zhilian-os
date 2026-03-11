"""
PeopleAgent — Phase 12B
人员智能体：排班优化 / 绩效评分 / 人力成本分析 / 考勤预警 / 人员配置建议

5个 Agent 类 + 11个纯函数
OKR:
  - 排班优化人力成本率下降 ≥2个百分点
  - 员工绩效评分覆盖率 ≥95%
  - 人力成本核算准确率 ≥98%
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.people_agent import (
    PeopleShiftRecord,
    PeoplePerformanceScore,
    PeopleLaborCostRecord,
    PeopleAttendanceAlert,
    PeopleStaffingDecision,
    PeopleAgentLog,
)

logger = logging.getLogger(__name__)

# ── LLM 开关 ─────────────────────────────────────────────────────────────────
_LLM_ENABLED: bool = os.getenv("LLM_ENABLED", "false").lower() == "true"
_LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")

# ── KPI配置 ──────────────────────────────────────────────────────────────────

# 各岗位KPI配置：{kpi_key: (weight, target_value, higher_is_better)}
ROLE_KPI_CONFIG: Dict[str, List[Dict[str, Any]]] = {
    "store_manager": [
        {"key": "revenue_achievement", "weight": 0.25, "target": 1.0, "higher": True},
        {"key": "profit_margin",       "weight": 0.25, "target": 0.20, "higher": True},
        {"key": "labor_efficiency",    "weight": 0.15, "target": 1.0,  "higher": True},
        {"key": "customer_satisfaction","weight": 0.20, "target": 4.5, "higher": True},
        {"key": "waste_rate",          "weight": 0.15, "target": 0.03, "higher": False},
    ],
    "chef": [
        {"key": "food_cost_ratio",   "weight": 0.35, "target": 0.38, "higher": False},
        {"key": "waste_rate",        "weight": 0.30, "target": 0.03, "higher": False},
        {"key": "dish_quality_score","weight": 0.25, "target": 90.0, "higher": True},
        {"key": "attendance",        "weight": 0.10, "target": 1.0,  "higher": True},
    ],
    "waiter": [
        {"key": "avg_per_table",    "weight": 0.35, "target": 200.0, "higher": True},
        {"key": "add_order_rate",   "weight": 0.25, "target": 0.30,  "higher": True},
        {"key": "good_review_rate", "weight": 0.25, "target": 0.95,  "higher": True},
        {"key": "attendance",       "weight": 0.15, "target": 1.0,   "higher": True},
    ],
    "cashier": [
        {"key": "accuracy",     "weight": 0.40, "target": 1.0,   "higher": True},
        {"key": "member_card",  "weight": 0.30, "target": 10.0,  "higher": True},
        {"key": "stored_value", "weight": 0.30, "target": 5000.0,"higher": True},
    ],
    "default": [
        {"key": "task_completion", "weight": 0.50, "target": 1.0, "higher": True},
        {"key": "attendance",      "weight": 0.30, "target": 1.0, "higher": True},
        {"key": "quality_score",   "weight": 0.20, "target": 80.0,"higher": True},
    ],
}

# 绩效等级阈值（overall_score 0-100）
PERF_RATING_THRESHOLDS = [
    (90.0, "outstanding"),
    (80.0, "exceeds"),
    (65.0, "meets"),
    (50.0, "below"),
    (0.0,  "unsatisfactory"),
]

# 排班建议模板（按人力成本率偏差）
SHIFT_SUGGESTIONS: Dict[str, List[str]] = {
    "understaffed": ["建议立即呼叫备班人员", "预计影响服务质量，考虑限制接单"],
    "overstaffed":  ["建议提前1小时安排部分员工下班", "调配人员至高峰时段"],
    "optimal":      ["当前排班符合客流预测", "保持当前配置"],
    "high_cost":    ["人力成本率超标，建议优化班次结构", "考虑压缩非高峰时段人员"],
}

# 人员配置建议模板
STAFFING_ACTIONS: Dict[str, str] = {
    "hire":     "建议招聘{gap}名{role}，以补充{reason}",
    "reduce":   "建议在{period}前减少{gap}名{role}编制",
    "transfer": "建议将{from_store}的{n}名{role}临时调配至本店",
    "train":    "建议为{role}岗位安排专项培训，提升{skill}能力",
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def compute_coverage_rate(scheduled: int, required: int) -> float:
    """排班覆盖率 = scheduled / required，上限1.5（超配不超过50%）"""
    if required <= 0:
        return 1.0
    return min(round(scheduled / required, 3), 1.5)


def classify_shift_status(coverage: float, labor_cost_ratio: float) -> str:
    """根据覆盖率和人力成本率分类排班状态"""
    if coverage < 0.80:
        return "understaffed"
    if coverage > 1.20 or labor_cost_ratio > 0.32:
        return "overstaffed"
    if labor_cost_ratio > 0.28:
        return "high_cost"
    return "optimal"


def compute_kpi_achievement(actual: float, target: float, higher_is_better: bool = True) -> float:
    """KPI达成率：higher_is_better=True时 actual/target，否则 target/actual"""
    if target <= 0:
        return 1.0
    raw = actual / target if higher_is_better else target / actual
    return round(raw, 4)


def compute_performance_score(kpi_values: Dict[str, float], role: str) -> tuple[float, List[Dict]]:
    """计算员工绩效综合分（0-100）及各KPI详情"""
    config = ROLE_KPI_CONFIG.get(role, ROLE_KPI_CONFIG["default"])
    if not kpi_values:
        return 50.0, []

    total_weight = sum(c["weight"] for c in config if c["key"] in kpi_values)
    if total_weight == 0:
        return 50.0, []

    weighted_score = 0.0
    items = []
    for cfg in config:
        key = cfg["key"]
        if key not in kpi_values:
            continue
        achievement = compute_kpi_achievement(kpi_values[key], cfg["target"], cfg["higher"])
        # 映射到0-100：achievement=1.0→80分，>1.2→100，<0.5→0
        score = min(100.0, max(0.0, round(achievement * 80, 1)))
        weighted_score += score * (cfg["weight"] / total_weight)
        items.append({
            "kpi": key, "actual": kpi_values[key],
            "target": cfg["target"], "achievement": achievement,
            "score": score, "weight": cfg["weight"],
        })

    return round(weighted_score, 1), items


def classify_performance_rating(score: float) -> str:
    """绩效评级：outstanding/exceeds/meets/below/unsatisfactory"""
    for threshold, rating in PERF_RATING_THRESHOLDS:
        if score >= threshold:
            return rating
    return "unsatisfactory"


def compute_commission(score: float, base_salary: float, role: str) -> tuple[float, float]:
    """计算基础提成和奖励提成（元）"""
    # 简单模型：基础提成 = base_salary * 绩效系数（0.8-1.2）
    perf_multiplier = max(0.8, min(1.2, score / 80.0))
    base_commission = round(base_salary * perf_multiplier * 0.1, 2)  # 底薪10%作为绩效提成
    # 超额奖励
    bonus = 0.0
    if score >= 90:
        bonus = round(base_salary * 0.05, 2)  # 5%额外奖励
    elif score >= 80:
        bonus = round(base_salary * 0.02, 2)  # 2%额外奖励
    return base_commission, bonus


def compute_labor_cost_ratio(total_labor_yuan: float, revenue_yuan: float) -> float:
    """人力成本率（%）"""
    if revenue_yuan <= 0:
        return 0.0
    return round(total_labor_yuan / revenue_yuan * 100, 2)


def compute_revenue_per_employee(revenue_yuan: float, headcount: float) -> float:
    """人效（元/人）"""
    if headcount <= 0:
        return 0.0
    return round(revenue_yuan / headcount, 2)


def compute_optimization_potential(
    current_ratio: float, target_ratio: float, revenue_yuan: float
) -> float:
    """人力成本优化空间（元）"""
    if current_ratio <= target_ratio:
        return 0.0
    excess_ratio = current_ratio - target_ratio
    return round(revenue_yuan * excess_ratio / 100, 2)


def classify_attendance_severity(alert_type: str, count_in_period: int = 1) -> str:
    """考勤预警严重度"""
    if alert_type == "absent" or count_in_period >= 3:
        return "critical"
    if alert_type in ("early_leave", "overtime") or count_in_period >= 2:
        return "warning"
    return "info"


def score_staffing_recommendation(impact_yuan: float, urgency_days: int, confidence: float) -> float:
    """人员配置建议优先级评分（0-100）"""
    impact_score = min(50.0, impact_yuan / 1000)       # 每千元 1分，上限50
    urgency_score = max(0.0, 30.0 - urgency_days * 2)  # 越紧急分越高，上限30
    conf_score = confidence * 20                         # 置信度上限20
    return round(impact_score + urgency_score + conf_score, 1)


def compute_optimal_headcount(
    revenue_yuan: float,
    target_revenue_per_person: float,
    min_headcount: int = 3,
) -> int:
    """基于人效目标反算最优人数"""
    if target_revenue_per_person <= 0:
        return min_headcount
    optimal = max(min_headcount, round(revenue_yuan / target_revenue_per_person))
    return int(optimal)


# ── LLM helper ───────────────────────────────────────────────────────────────

async def _ai_insight(system: str, user_data: dict) -> Optional[str]:
    """调用 LLM 生成人员洞察；LLM 未启用时返回 None"""
    if not _LLM_ENABLED:
        return None
    try:
        from src.core.llm import get_llm_client
        prompt = json.dumps(user_data, ensure_ascii=False, default=str)
        insight = await get_llm_client().generate(
            prompt=prompt, system_prompt=system, max_tokens=512,
        )
        return insight.strip() or None
    except Exception as exc:
        logger.warning("people_agent_llm_insight_failed: %s", str(exc))
        return None


# ── Agent 1: 排班优化 ─────────────────────────────────────────────────────────

class ShiftOptimizerAgent:
    """
    ShiftOptimizerAgent — 排班优化
    OKR: 人力成本率下降 ≥2个百分点
    """

    async def optimize(
        self,
        brand_id: str,
        store_id: str,
        shift_date: date,
        required_headcount: int,
        scheduled_headcount: int,
        estimated_labor_cost_yuan: float,
        revenue_yuan: float,
        shift_assignments: Optional[List[Dict]] = None,
        peak_hours: Optional[List[str]] = None,
        db: Optional[AsyncSession] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        labor_ratio = compute_labor_cost_ratio(estimated_labor_cost_yuan, revenue_yuan)
        coverage = compute_coverage_rate(scheduled_headcount, required_headcount)
        status_key = classify_shift_status(coverage, labor_ratio / 100)

        suggestions = SHIFT_SUGGESTIONS.get(status_key, [])

        ai = await _ai_insight(
            "你是餐饮排班优化专家。根据排班数据给出简短的人效优化建议（2-3句话）。",
            {
                "coverage_rate": coverage, "labor_cost_ratio": labor_ratio,
                "status": status_key, "scheduled": scheduled_headcount,
                "required": required_headcount,
            },
        )

        record_id = str(uuid.uuid4())
        if save and db:
            rec = PeopleShiftRecord(
                id=record_id,
                brand_id=brand_id,
                store_id=store_id,
                shift_date=shift_date,
                required_headcount=required_headcount,
                scheduled_headcount=scheduled_headcount,
                coverage_rate=coverage,
                estimated_labor_cost_yuan=Decimal(str(estimated_labor_cost_yuan)),
                labor_cost_per_revenue_pct=labor_ratio,
                shift_assignments=shift_assignments or [],
                optimization_suggestions=suggestions,
                peak_hours=peak_hours or [],
                status="draft",
                ai_insight=ai,
                confidence=0.82,
            )
            db.add(rec)
            await db.flush()

        return {
            "record_id": record_id,
            "shift_date": str(shift_date),
            "coverage_rate": coverage,
            "shift_status": status_key,
            "labor_cost_ratio_pct": labor_ratio,
            "optimization_suggestions": suggestions,
            "ai_insight": ai,
        }


# ── Agent 2: 绩效评分 ─────────────────────────────────────────────────────────

class PerformanceScoreAgent:
    """
    PerformanceScoreAgent — 员工绩效评分
    OKR: 员工绩效评分覆盖率 ≥95%
    """

    async def score(
        self,
        brand_id: str,
        store_id: str,
        employee_id: str,
        role: str,
        period: str,
        kpi_values: Dict[str, float],
        employee_name: Optional[str] = None,
        base_salary: float = 5000.0,
        db: Optional[AsyncSession] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        overall_score, kpi_items = compute_performance_score(kpi_values, role)
        rating = classify_performance_rating(overall_score)
        base_commission, bonus = compute_commission(overall_score, base_salary, role)
        total_commission = base_commission + bonus

        # 改进建议：找出得分低于60的KPI
        improvement = [
            f"提升 {item['kpi']}（当前达成率 {item['achievement']:.0%}）"
            for item in kpi_items if item["score"] < 60
        ]

        ai = await _ai_insight(
            "你是餐饮人力资源专家。根据员工绩效数据给出个性化发展建议（2-3句话）。",
            {
                "role": role, "period": period, "overall_score": overall_score,
                "rating": rating, "kpi_items": kpi_items,
            },
        )

        record_id = str(uuid.uuid4())
        if save and db:
            rec = PeoplePerformanceScore(
                id=record_id,
                brand_id=brand_id,
                store_id=store_id,
                employee_id=employee_id,
                employee_name=employee_name,
                role=role,
                period=period,
                kpi_scores=kpi_items,
                overall_score=overall_score,
                rating=rating,
                base_commission_yuan=Decimal(str(base_commission)),
                bonus_commission_yuan=Decimal(str(bonus)),
                total_commission_yuan=Decimal(str(total_commission)),
                improvement_areas=improvement,
                ai_insight=ai,
                confidence=0.85,
            )
            db.add(rec)
            await db.flush()

        return {
            "record_id": record_id,
            "employee_id": employee_id,
            "period": period,
            "overall_score": overall_score,
            "rating": rating,
            "kpi_items": kpi_items,
            "base_commission_yuan": base_commission,
            "bonus_commission_yuan": bonus,
            "total_commission_yuan": total_commission,
            "improvement_areas": improvement,
            "ai_insight": ai,
        }


# ── Agent 3: 人力成本分析 ─────────────────────────────────────────────────────

class LaborCostAgent:
    """
    LaborCostAgent — 人力成本分析
    OKR: 人力成本核算准确率 ≥98%
    """

    async def analyze(
        self,
        brand_id: str,
        store_id: str,
        period: str,
        total_labor_cost_yuan: float,
        revenue_yuan: float,
        avg_headcount: float,
        overtime_hours: float = 0.0,
        overtime_cost_yuan: float = 0.0,
        cost_breakdown: Optional[Dict[str, float]] = None,
        target_labor_cost_ratio: float = 28.0,
        db: Optional[AsyncSession] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        labor_ratio = compute_labor_cost_ratio(total_labor_cost_yuan, revenue_yuan)
        rev_per_emp = compute_revenue_per_employee(revenue_yuan, avg_headcount)
        potential = compute_optimization_potential(labor_ratio, target_labor_cost_ratio, revenue_yuan)

        ai = await _ai_insight(
            "你是餐饮成本控制专家。根据人力成本数据给出降本优化建议（2-3句话）。",
            {
                "period": period, "labor_cost_ratio": labor_ratio,
                "target_ratio": target_labor_cost_ratio,
                "revenue_per_employee": rev_per_emp,
                "optimization_potential_yuan": potential,
            },
        )

        record_id = str(uuid.uuid4())
        if save and db:
            rec = PeopleLaborCostRecord(
                id=record_id,
                brand_id=brand_id,
                store_id=store_id,
                period=period,
                total_labor_cost_yuan=Decimal(str(total_labor_cost_yuan)),
                revenue_yuan=Decimal(str(revenue_yuan)),
                labor_cost_ratio=labor_ratio,
                target_labor_cost_ratio=target_labor_cost_ratio / 100,
                revenue_per_employee_yuan=Decimal(str(rev_per_emp)),
                avg_headcount=avg_headcount,
                overtime_hours=overtime_hours,
                overtime_cost_yuan=Decimal(str(overtime_cost_yuan)),
                cost_breakdown=cost_breakdown,
                optimization_potential_yuan=Decimal(str(potential)),
                ai_insight=ai,
                confidence=0.88,
            )
            db.add(rec)
            await db.flush()

        return {
            "record_id": record_id,
            "period": period,
            "labor_cost_ratio_pct": labor_ratio,
            "target_ratio_pct": target_labor_cost_ratio,
            "deviation_pct": round(labor_ratio - target_labor_cost_ratio, 2),
            "revenue_per_employee_yuan": rev_per_emp,
            "optimization_potential_yuan": potential,
            "is_over_target": labor_ratio > target_labor_cost_ratio,
            "ai_insight": ai,
        }


# ── Agent 4: 考勤预警 ─────────────────────────────────────────────────────────

class AttendanceWarnAgent:
    """
    AttendanceWarnAgent — 考勤异常预警
    OKR: 考勤异常发现率 ≥90%
    """

    async def warn(
        self,
        brand_id: str,
        store_id: str,
        alert_date: date,
        alert_type: str,
        employee_id: Optional[str] = None,
        employee_name: Optional[str] = None,
        description: Optional[str] = None,
        estimated_impact_yuan: float = 0.0,
        count_in_period: int = 1,
        db: Optional[AsyncSession] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        severity = classify_attendance_severity(alert_type, count_in_period)

        action_map = {
            "late":        "联系员工确认到岗，超15分钟按规定处理",
            "absent":      "立即安排备班人员，并通知店长处理",
            "early_leave": "核实离岗原因，当日班次补齐",
            "overtime":    "安排补休或加班费，检查排班是否合理",
            "understaffed":"呼叫备班或临时调配人员",
        }
        recommended_action = action_map.get(alert_type, "人工核实处理")

        ai = await _ai_insight(
            "你是餐饮人力资源专家。根据考勤异常情况给出简短处置建议（1-2句话）。",
            {
                "alert_type": alert_type, "severity": severity,
                "count": count_in_period, "impact_yuan": estimated_impact_yuan,
            },
        )

        record_id = str(uuid.uuid4())
        if save and db:
            rec = PeopleAttendanceAlert(
                id=record_id,
                brand_id=brand_id,
                store_id=store_id,
                employee_id=employee_id,
                employee_name=employee_name,
                alert_date=alert_date,
                alert_type=alert_type,
                severity=severity,
                description=description,
                estimated_impact_yuan=Decimal(str(estimated_impact_yuan)) if estimated_impact_yuan else None,
                recommended_action=recommended_action,
                is_resolved=False,
                ai_insight=ai,
            )
            db.add(rec)
            await db.flush()

        return {
            "record_id": record_id,
            "alert_type": alert_type,
            "severity": severity,
            "recommended_action": recommended_action,
            "estimated_impact_yuan": estimated_impact_yuan,
            "ai_insight": ai,
        }


# ── Agent 5: 人员配置建议 ─────────────────────────────────────────────────────

class StaffingPlanAgent:
    """
    StaffingPlanAgent — 综合人员配置建议
    OKR: 配置建议采纳率 ≥65%
    """

    async def plan(
        self,
        brand_id: str,
        store_id: str,
        current_headcount: int,
        revenue_yuan: float,
        target_revenue_per_person: float = 50000.0,
        role_gaps: Optional[Dict[str, int]] = None,
        db: Optional[AsyncSession] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        optimal = compute_optimal_headcount(revenue_yuan, target_revenue_per_person)
        gap = optimal - current_headcount

        recommendations = []
        if role_gaps:
            for role, role_gap in role_gaps.items():
                if role_gap > 0:
                    impact = role_gap * target_revenue_per_person * 0.1
                    rec = {
                        "rank": len(recommendations) + 1,
                        "action": f"建议补充{role_gap}名{role}",
                        "role": role,
                        "gap": role_gap,
                        "impact_yuan": impact,
                        "urgency_days": 14,
                        "confidence": 0.75,
                    }
                    rec["priority_score"] = score_staffing_recommendation(
                        impact, rec["urgency_days"], rec["confidence"]
                    )
                    recommendations.append(rec)
                elif role_gap < 0:
                    saving = abs(role_gap) * 4000  # 估算每人节省4000元/月
                    rec = {
                        "rank": len(recommendations) + 1,
                        "action": f"建议在下季度优化{abs(role_gap)}名{role}编制",
                        "role": role,
                        "gap": role_gap,
                        "impact_yuan": saving,
                        "urgency_days": 30,
                        "confidence": 0.70,
                    }
                    rec["priority_score"] = score_staffing_recommendation(
                        saving, rec["urgency_days"], rec["confidence"]
                    )
                    recommendations.append(rec)

        if not recommendations:
            recommendations = [{
                "rank": 1,
                "action": "当前人员配置基本合理，持续跟踪人效指标" if gap == 0
                          else f"建议{'招聘' if gap > 0 else '优化'}{abs(gap)}人以达到最优人效",
                "role": "综合",
                "gap": gap,
                "impact_yuan": abs(gap) * 4000,
                "urgency_days": 30 if abs(gap) <= 1 else 14,
                "confidence": 0.75,
                "priority_score": 30.0,
            }]

        # 按 priority_score 降序排名
        recommendations.sort(key=lambda x: -x.get("priority_score", 0))
        for i, r in enumerate(recommendations):
            r["rank"] = i + 1
        recommendations = recommendations[:3]

        total_impact = sum(r["impact_yuan"] for r in recommendations)
        priority = "p0" if total_impact > 50000 else ("p1" if total_impact > 20000 else "p2")

        ai = await _ai_insight(
            "你是餐饮运营专家。根据人员配置数据给出综合人员调整建议（2-3句话）。",
            {
                "current_headcount": current_headcount,
                "optimal_headcount": optimal,
                "gap": gap,
                "recommendations": recommendations,
            },
        )

        record_id = str(uuid.uuid4())
        if save and db:
            rec = PeopleStaffingDecision(
                id=record_id,
                brand_id=brand_id,
                store_id=store_id,
                decision_date=date.today(),
                recommendations=recommendations,
                total_impact_yuan=Decimal(str(total_impact)),
                priority=priority,
                status="pending",
                current_headcount=current_headcount,
                optimal_headcount=optimal,
                headcount_gap=gap,
                ai_insight=ai,
                confidence=0.78,
            )
            db.add(rec)
            await db.flush()

        return {
            "record_id": record_id,
            "current_headcount": current_headcount,
            "optimal_headcount": optimal,
            "headcount_gap": gap,
            "top3_recommendations": recommendations,
            "total_impact_yuan": total_impact,
            "priority": priority,
            "ai_insight": ai,
        }
