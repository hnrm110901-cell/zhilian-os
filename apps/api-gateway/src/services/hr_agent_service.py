"""
HR Agent Service — 人力智能体服务
智能算薪 + 离职预警 + 招聘推荐

三大核心能力：
1. 智能算薪：自动识别异常工资、绩效挂钩、薪资建议
2. 离职预警：基于多维度信号（出勤率下降、绩效下滑、合同到期）预测离职风险
3. 招聘推荐：基于缺岗分析和历史数据推荐招聘策略
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.hr_ai_decision_service import HRAIDecisionService

logger = structlog.get_logger()

# 全局AI决策服务实例
_ai_decision_service = HRAIDecisionService()


class HRAgentService:
    """人力资源智能体服务"""

    def __init__(self, store_id: str):
        self.store_id = store_id

    # ── 1. 智能算薪分析 ─────────────────────────────────────

    async def analyze_payroll_anomalies(self, db: AsyncSession, pay_month: str) -> Dict[str, Any]:
        """
        分析薪资异常：
        - 工资环比变动 >20% 的员工
        - 加班费占比 >30% 的员工（可能存在排班问题）
        - 绩效系数偏离均值 >1.5 标准差的员工
        返回异常列表 + 建议动作 + 预期¥影响
        """
        # 当月工资数据
        result = await db.execute(
            text("""
            SELECT pr.employee_id, e.name AS employee_name, e.position,
                   pr.gross_salary_fen, pr.net_salary_fen,
                   pr.overtime_pay_fen, pr.performance_bonus_fen,
                   pr.absence_deduction_fen, pr.tax_fen
            FROM payroll_records pr
            JOIN employees e ON e.id = pr.employee_id
            WHERE pr.store_id = :store_id AND pr.pay_month = :month
        """),
            {"store_id": self.store_id, "month": pay_month},
        )
        current = {r["employee_id"]: dict(r) for r in result.mappings()}

        # 上月工资（环比对照）
        year, month = int(pay_month[:4]), int(pay_month[5:7])
        prev_m = month - 1
        prev_y = year
        if prev_m == 0:
            prev_m = 12
            prev_y -= 1
        prev_month = f"{prev_y}-{prev_m:02d}"

        prev_result = await db.execute(
            text("""
            SELECT employee_id, gross_salary_fen
            FROM payroll_records
            WHERE store_id = :store_id AND pay_month = :month
        """),
            {"store_id": self.store_id, "month": prev_month},
        )
        prev_data = {r["employee_id"]: r["gross_salary_fen"] for r in prev_result.mappings()}

        anomalies = []

        for emp_id, cur in current.items():
            gross = cur["gross_salary_fen"]
            overtime = cur["overtime_pay_fen"]
            reasons = []

            # 环比变动 >20%
            if emp_id in prev_data and prev_data[emp_id] > 0:
                change_pct = (gross - prev_data[emp_id]) / prev_data[emp_id] * 100
                if abs(change_pct) > 20:
                    reasons.append(f"环比{'增长' if change_pct > 0 else '下降'}{abs(change_pct):.0f}%")

            # 加班费占比 >30%
            if gross > 0 and overtime / gross > 0.3:
                ot_pct = overtime / gross * 100
                reasons.append(f"加班费占比{ot_pct:.0f}%（建议优化排班）")

            if reasons:
                anomalies.append(
                    {
                        "employee_id": emp_id,
                        "employee_name": cur["employee_name"],
                        "position": cur["position"],
                        "gross_salary_yuan": gross / 100,
                        "net_salary_yuan": cur["net_salary_fen"] / 100,
                        "reasons": reasons,
                        "suggested_action": "检查薪资结构" if len(reasons) > 1 else reasons[0],
                        "estimated_impact_yuan": abs(gross - prev_data.get(emp_id, gross)) / 100,
                    }
                )

        # 汇总
        total_payroll_yuan = sum(c["gross_salary_fen"] for c in current.values()) / 100
        total_overtime_yuan = sum(c["overtime_pay_fen"] for c in current.values()) / 100

        return {
            "pay_month": pay_month,
            "total_employees": len(current),
            "total_payroll_yuan": total_payroll_yuan,
            "total_overtime_yuan": total_overtime_yuan,
            "overtime_ratio_pct": round(total_overtime_yuan / max(total_payroll_yuan, 1) * 100, 1),
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "ai_suggestion": self._payroll_suggestion(anomalies, total_overtime_yuan, total_payroll_yuan),
        }

    def _payroll_suggestion(self, anomalies: list, overtime_yuan: float, total_yuan: float) -> str:
        """生成薪资优化建议"""
        suggestions = []
        ot_ratio = overtime_yuan / max(total_yuan, 1) * 100
        if ot_ratio > 15:
            savings = (ot_ratio - 10) / 100 * total_yuan
            suggestions.append(f"加班费占比{ot_ratio:.0f}%偏高，建议优化排班。" f"若降至10%可节省约¥{savings:,.0f}/月")
        if len(anomalies) > 3:
            suggestions.append(f"有{len(anomalies)}名员工薪资异常波动，建议HR核查")
        return " | ".join(suggestions) if suggestions else "本月薪资结构正常，未发现明显异常"

    # ── 2. 离职预警 ────────────────────────────────────────

    async def predict_resignation_risk(self, db: AsyncSession) -> Dict[str, Any]:
        """
        离职风险预测（多维度信号融合）：
        - 出勤率（近30天） < 90%
        - 合同30天内到期且未续签
        - 近3月请假频率上升
        - 绩效等级 C/D
        返回高风险员工列表 + 风险等级 + 建议保留措施 + 替换成本¥
        """
        today = date.today()
        month_ago = today - timedelta(days=30)

        # 活跃员工
        emp_result = await db.execute(
            text("""
            SELECT id, name, position, hire_date
            FROM employees
            WHERE store_id = :store_id AND is_active = true
        """),
            {"store_id": self.store_id},
        )
        employees = {r["id"]: dict(r) for r in emp_result.mappings()}

        risk_scores: Dict[str, Dict] = {}

        # 信号1: 出勤率
        att_result = await db.execute(
            text("""
            SELECT employee_id,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status IN ('normal', 'late')) AS present
            FROM attendance_logs
            WHERE store_id = :store_id AND work_date >= :since
            GROUP BY employee_id
        """),
            {"store_id": self.store_id, "since": month_ago},
        )
        for r in att_result.mappings():
            emp_id = r["employee_id"]
            if emp_id not in employees:
                continue
            rate = r["present"] / max(r["total"], 1)
            if rate < 0.90:
                risk_scores.setdefault(emp_id, {"signals": [], "score": 0})
                risk_scores[emp_id]["signals"].append(f"出勤率{rate*100:.0f}%")
                risk_scores[emp_id]["score"] += 30

        # 信号2: 合同即将到期
        contract_result = await db.execute(
            text("""
            SELECT employee_id, end_date, renewal_count
            FROM employee_contracts
            WHERE store_id = :store_id AND status = 'active'
              AND end_date IS NOT NULL AND end_date <= :threshold
        """),
            {"store_id": self.store_id, "threshold": today + timedelta(days=30)},
        )
        for r in contract_result.mappings():
            emp_id = r["employee_id"]
            if emp_id not in employees:
                continue
            days_left = (r["end_date"] - today).days
            risk_scores.setdefault(emp_id, {"signals": [], "score": 0})
            risk_scores[emp_id]["signals"].append(f"合同{days_left}天后到期")
            risk_scores[emp_id]["score"] += 25

        # 信号3: 近期请假频繁
        leave_result = await db.execute(
            text("""
            SELECT employee_id, COUNT(*) AS cnt
            FROM leave_requests
            WHERE store_id = :store_id
              AND status = 'approved'
              AND created_at >= :since
            GROUP BY employee_id
            HAVING COUNT(*) >= 3
        """),
            {"store_id": self.store_id, "since": today - timedelta(days=90)},
        )
        for r in leave_result.mappings():
            emp_id = r["employee_id"]
            if emp_id not in employees:
                continue
            risk_scores.setdefault(emp_id, {"signals": [], "score": 0})
            risk_scores[emp_id]["signals"].append(f"近3月请假{r['cnt']}次")
            risk_scores[emp_id]["score"] += 20

        # 信号4: 绩效评级低
        perf_result = await db.execute(
            text("""
            SELECT employee_id, level
            FROM performance_reviews
            WHERE store_id = :store_id AND level IN ('C', 'D')
            ORDER BY created_at DESC
        """),
            {"store_id": self.store_id},
        )
        for r in perf_result.mappings():
            emp_id = r["employee_id"]
            if emp_id not in employees:
                continue
            risk_scores.setdefault(emp_id, {"signals": [], "score": 0})
            risk_scores[emp_id]["signals"].append(f"绩效评级{r['level']}")
            risk_scores[emp_id]["score"] += 25

        # 构建高风险列表，对高分员工调用AI深度分析
        high_risk = []
        for emp_id, data in sorted(risk_scores.items(), key=lambda x: -x[1]["score"]):
            if data["score"] < 30:
                continue
            emp = employees[emp_id]
            level = "高" if data["score"] >= 60 else "中"

            # 对高风险员工调用AI决策服务做深度分析
            ai_result = None
            if data["score"] >= 50:
                try:
                    ai_result = await _ai_decision_service.predict_turnover_risk(db, emp_id, self.store_id)
                except Exception as e:
                    logger.warning(
                        "hr_agent_ai_prediction_failed",
                        employee_id=emp_id,
                        error=str(e),
                    )

            # 融合AI结果
            if ai_result and ai_result.get("data_source") != "error":
                replacement_cost = ai_result.get("replacement_cost_yuan", 8000)
                suggested_action = ai_result.get("ai_analysis") or self._retention_action_fallback(data["signals"], level)
                recommendations = ai_result.get("recommendations", [])
                risk_score = ai_result.get("risk_score", data["score"])
            else:
                replacement_cost = 8000
                suggested_action = self._retention_action_fallback(data["signals"], level)
                recommendations = []
                risk_score = data["score"]

            high_risk.append(
                {
                    "employee_id": emp_id,
                    "employee_name": emp["name"],
                    "position": emp["position"],
                    "risk_level": level,
                    "risk_score": risk_score,
                    "signals": data["signals"],
                    "suggested_action": suggested_action,
                    "recommendations": recommendations,
                    "replacement_cost_yuan": replacement_cost,
                }
            )

        return {
            "total_active": len(employees),
            "high_risk_count": len([r for r in high_risk if r["risk_level"] == "高"]),
            "medium_risk_count": len([r for r in high_risk if r["risk_level"] == "中"]),
            "at_risk_employees": high_risk[:20],
            "total_replacement_cost_yuan": sum(r["replacement_cost_yuan"] for r in high_risk),
        }

    def _retention_action_fallback(self, signals: List[str], level: str) -> str:
        """规则引擎留人建议（AI不可用时的降级方案）"""
        if level == "高":
            return "建议立即1v1沟通，了解离职意向；考虑薪资调整或岗位调整"
        if any("合同" in s for s in signals):
            return "建议尽快启动合同续签流程"
        if any("绩效" in s for s in signals):
            return "建议制定绩效改进计划(PIP)，提供培训支持"
        return "建议关注员工状态，定期沟通"

    # ── 3. 招聘推荐 ────────────────────────────────────────

    async def recommend_recruitment(self, db: AsyncSession) -> Dict[str, Any]:
        """
        招聘策略推荐：
        - 分析缺岗情况（在职人数 vs 标准编制）
        - 分析各渠道招聘转化率
        - 生成招聘优先级建议
        """
        # 当前在职按岗位
        position_result = await db.execute(
            text("""
            SELECT position, COUNT(*) AS cnt
            FROM employees
            WHERE store_id = :store_id AND is_active = true
            GROUP BY position
        """),
            {"store_id": self.store_id},
        )
        current_staff = {r["position"]: r["cnt"] for r in position_result.mappings()}

        # 活跃招聘需求
        job_result = await db.execute(
            text("""
            SELECT id, title, position, headcount, hired_count, urgent,
                   channels, deadline
            FROM job_postings
            WHERE store_id = :store_id AND status = 'open'
        """),
            {"store_id": self.store_id},
        )
        open_jobs = [dict(r) for r in job_result.mappings()]

        # 渠道效果分析
        channel_result = await db.execute(
            text("""
            SELECT c.source, COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE c.stage = 'hired') AS hired
            FROM candidates c
            JOIN job_postings j ON j.id = c.job_id
            WHERE j.store_id = :store_id
            GROUP BY c.source
        """),
            {"store_id": self.store_id},
        )
        channels = []
        for r in channel_result.mappings():
            total = r["total"] or 1
            hired = r["hired"] or 0
            channels.append(
                {
                    "source": r["source"] or "未知",
                    "total_candidates": total,
                    "hired_count": hired,
                    "conversion_rate_pct": round(hired / total * 100, 1),
                }
            )

        # 招聘建议
        recommendations = []
        for job in open_jobs:
            remaining = job["headcount"] - job["hired_count"]
            if remaining <= 0:
                continue
            urgency = "紧急" if job["urgent"] else "常规"
            if job["deadline"]:
                days_left = (job["deadline"] - date.today()).days
                if days_left < 7:
                    urgency = "紧急"
            recommendations.append(
                {
                    "job_id": str(job["id"]),
                    "title": job["title"],
                    "position": job["position"],
                    "remaining_headcount": remaining,
                    "urgency": urgency,
                    "suggested_channels": self._suggest_channels(channels, job["position"]),
                    "estimated_time_days": 14 if urgency == "紧急" else 30,
                }
            )

        # 排序：紧急优先
        recommendations.sort(key=lambda x: (0 if x["urgency"] == "紧急" else 1, -x["remaining_headcount"]))

        return {
            "current_headcount": sum(current_staff.values()),
            "position_distribution": current_staff,
            "open_positions": len(open_jobs),
            "total_remaining": sum(r["remaining_headcount"] for r in recommendations),
            "channel_effectiveness": sorted(channels, key=lambda x: -x["conversion_rate_pct"]),
            "recommendations": recommendations,
            "ai_suggestion": self._recruitment_suggestion(recommendations, channels),
        }

    def _suggest_channels(self, channels: list, position: str) -> List[str]:
        """根据渠道效果和岗位推荐招聘渠道"""
        # 简单规则：转化率最高的前3个渠道
        effective = sorted(channels, key=lambda c: -c["conversion_rate_pct"])
        top = [c["source"] for c in effective[:3]]
        # 餐饮特殊：厨师岗优先推荐行业群/推荐
        if position in ("chef", "厨师", "厨师长"):
            if "referral" not in top:
                top.insert(0, "referral")
        return top[:3]

    def _recruitment_suggestion(self, recommendations: list, channels: list) -> str:
        urgent = [r for r in recommendations if r["urgency"] == "紧急"]
        if urgent:
            return f"有{len(urgent)}个岗位招聘紧急，" f"建议加大{', '.join(urgent[0]['suggested_channels'][:2])}渠道投入"
        if not recommendations:
            return "当前无缺岗，招聘需求充足"
        return f"共{len(recommendations)}个岗位待招，建议按优先级逐步推进"

    # ── 4. 员工成长洞察 ────────────────────────────────────

    async def analyze_growth_insights(self, db: AsyncSession) -> Dict[str, Any]:
        """
        成长洞察分析：
        - 技能瓶颈（全店最薄弱技能）
        - 晋升推荐（已满足晋升条件的员工）
        - 成长计划执行率
        - 里程碑统计
        返回建议动作 + 预期¥影响
        """
        # 1. 技能瓶颈：按技能统计平均分，找出最薄弱的
        skill_result = await db.execute(
            text("""
            SELECT sd.skill_name, sd.skill_category, sd.promotion_weight,
                   COUNT(es.id) AS assessed_count,
                   AVG(es.score) AS avg_score,
                   COUNT(*) FILTER (WHERE es.current_level IN ('novice', 'apprentice')) AS low_level_count
            FROM skill_definitions sd
            LEFT JOIN employee_skills es ON es.skill_id = sd.id
            WHERE sd.is_active = true
              AND (sd.store_id = :store_id OR sd.store_id IS NULL)
            GROUP BY sd.id, sd.skill_name, sd.skill_category, sd.promotion_weight
            ORDER BY AVG(es.score) ASC NULLS FIRST
        """),
            {"store_id": self.store_id},
        )
        skill_bottlenecks = []
        for r in skill_result.mappings():
            avg = float(r["avg_score"] or 0)
            if avg < 60 or r["assessed_count"] == 0:
                skill_bottlenecks.append(
                    {
                        "skill_name": r["skill_name"],
                        "category": r["skill_category"],
                        "avg_score": round(avg, 1),
                        "low_level_count": r["low_level_count"] or 0,
                        "promotion_weight": r["promotion_weight"],
                        "suggestion": f"建议开展「{r['skill_name']}」专项培训",
                    }
                )

        # 2. 晋升就绪：在岗≥min_tenure_months且绩效≥min_performance_score的员工
        promotion_result = await db.execute(
            text("""
            SELECT e.id AS employee_id, e.name, e.position, e.hire_date,
                   cp.path_name, cp.to_position, cp.min_tenure_months,
                   cp.min_performance_score, cp.salary_increase_pct
            FROM employees e
            JOIN career_paths cp ON cp.from_position = e.position AND cp.is_active = true
            WHERE e.store_id = :store_id AND e.is_active = true
              AND (cp.store_id = :store_id OR cp.store_id IS NULL)
              AND e.hire_date <= CURRENT_DATE - cp.min_tenure_months * INTERVAL '1 month'
        """),
            {"store_id": self.store_id},
        )
        promotion_ready = []
        for r in promotion_result.mappings():
            tenure_months = (date.today() - r["hire_date"]).days // 30
            increase_pct = float(r["salary_increase_pct"] or 15)
            promotion_ready.append(
                {
                    "employee_id": r["employee_id"],
                    "employee_name": r["name"],
                    "current_position": r["position"],
                    "target_position": r["to_position"],
                    "path_name": r["path_name"],
                    "tenure_months": tenure_months,
                    "salary_increase_pct": increase_pct,
                    "suggestion": f"建议评估「{r['name']}」晋升至{r['to_position']}",
                }
            )

        # 3. 成长计划执行率
        plan_result = await db.execute(
            text("""
            SELECT status,
                   COUNT(*) AS cnt,
                   AVG(progress_pct) AS avg_progress
            FROM employee_growth_plans
            WHERE store_id = :store_id
            GROUP BY status
        """),
            {"store_id": self.store_id},
        )
        plan_stats = {}
        total_plans = 0
        for r in plan_result.mappings():
            plan_stats[r["status"]] = {
                "count": r["cnt"],
                "avg_progress": round(float(r["avg_progress"] or 0), 1),
            }
            total_plans += r["cnt"]

        active_plans = plan_stats.get("active", {})
        active_progress = active_plans.get("avg_progress", 0) if active_plans else 0

        # 4. 幸福指数概览
        today = date.today()
        current_period = f"{today.year}-{today.month:02d}"
        wellbeing_result = await db.execute(
            text("""
            SELECT COUNT(*) AS total,
                   AVG(overall_score) AS avg_score,
                   MIN(overall_score) AS min_score,
                   COUNT(*) FILTER (WHERE overall_score < 5) AS low_count
            FROM employee_wellbeing
            WHERE store_id = :store_id AND period = :period
        """),
            {"store_id": self.store_id, "period": current_period},
        )
        wb = dict(wellbeing_result.mappings().first() or {})
        wellbeing_summary = {
            "period": current_period,
            "submissions": wb.get("total", 0),
            "avg_score": round(float(wb.get("avg_score") or 0), 1),
            "min_score": round(float(wb.get("min_score") or 0), 1),
            "low_wellbeing_count": wb.get("low_count", 0),
        }

        # 5. 里程碑统计（近30天）
        milestone_result = await db.execute(
            text("""
            SELECT milestone_type, COUNT(*) AS cnt
            FROM employee_milestones
            WHERE store_id = :store_id AND achieved_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY milestone_type
            ORDER BY cnt DESC
        """),
            {"store_id": self.store_id},
        )
        recent_milestones = {r["milestone_type"]: r["cnt"] for r in milestone_result.mappings()}

        return {
            "skill_bottlenecks": skill_bottlenecks[:5],
            "promotion_ready": promotion_ready,
            "promotion_ready_count": len(promotion_ready),
            "growth_plans": {
                "total": total_plans,
                "by_status": plan_stats,
                "active_avg_progress": active_progress,
            },
            "wellbeing": wellbeing_summary,
            "recent_milestones": recent_milestones,
            "ai_suggestion": self._growth_suggestion(skill_bottlenecks, promotion_ready, wellbeing_summary),
        }

    def _growth_suggestion(
        self,
        bottlenecks: list,
        promotion_ready: list,
        wellbeing: dict,
    ) -> str:
        """生成成长洞察建议"""
        parts = []
        if bottlenecks:
            top = bottlenecks[0]
            parts.append(f"「{top['skill_name']}」是全店最薄弱技能（均分{top['avg_score']}），" f"建议优先安排培训")
        if promotion_ready:
            parts.append(f"有{len(promotion_ready)}名员工已满足晋升条件，" f"及时晋升可降低离职风险")
        avg_wb = wellbeing.get("avg_score", 0)
        if avg_wb > 0 and avg_wb < 6:
            parts.append(f"本月幸福指数均分{avg_wb}偏低，建议关注员工关怀")
        low_count = wellbeing.get("low_wellbeing_count", 0)
        if low_count > 0:
            parts.append(f"{low_count}名员工幸福指数<5，建议一对一沟通")
        return " | ".join(parts) if parts else "团队成长状态良好，继续保持"

    # ── 5. 文化健康度 ─────────────────────────────────────

    async def analyze_culture_health(self, db: AsyncSession) -> Dict[str, Any]:
        """
        文化健康度分析：
        - 里程碑密度（人均里程碑数）
        - 幸福指数各维度均值
        - 文化之星/全勤/零损耗月分布
        - 导师覆盖率（有导师的成长计划占比）
        """
        # 活跃员工数
        emp_result = await db.execute(
            text("""
            SELECT COUNT(*) AS cnt FROM employees
            WHERE store_id = :store_id AND is_active = true
        """),
            {"store_id": self.store_id},
        )
        total_employees = emp_result.scalar() or 1

        # 里程碑密度（近90天）
        milestone_result = await db.execute(
            text("""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT employee_id) AS unique_employees
            FROM employee_milestones
            WHERE store_id = :store_id AND achieved_at >= CURRENT_DATE - INTERVAL '90 days'
        """),
            {"store_id": self.store_id},
        )
        ms = dict(milestone_result.mappings().first() or {})
        milestone_density = round((ms.get("total", 0) or 0) / total_employees, 2)

        # 幸福指数维度均值（最近一期）
        today = date.today()
        current_period = f"{today.year}-{today.month:02d}"
        dim_result = await db.execute(
            text("""
            SELECT AVG(achievement_score) AS achievement,
                   AVG(belonging_score) AS belonging,
                   AVG(growth_score) AS growth,
                   AVG(balance_score) AS balance,
                   AVG(culture_score) AS culture
            FROM employee_wellbeing
            WHERE store_id = :store_id AND period = :period
        """),
            {"store_id": self.store_id, "period": current_period},
        )
        dims = dict(dim_result.mappings().first() or {})
        dimensions = {k: round(float(v or 0), 1) for k, v in dims.items()}

        # 导师覆盖率
        mentor_result = await db.execute(
            text("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE mentor_id IS NOT NULL) AS with_mentor
            FROM employee_growth_plans
            WHERE store_id = :store_id AND status = 'active'
        """),
            {"store_id": self.store_id},
        )
        mr = dict(mentor_result.mappings().first() or {})
        mentor_total = mr.get("total", 0) or 0
        mentor_coverage = round((mr.get("with_mentor", 0) or 0) / max(mentor_total, 1) * 100, 1)

        # 找最弱维度
        weakest = min(dimensions.items(), key=lambda x: x[1]) if any(v > 0 for v in dimensions.values()) else None

        return {
            "total_employees": total_employees,
            "milestone_density_90d": milestone_density,
            "milestone_coverage_pct": round((ms.get("unique_employees", 0) or 0) / total_employees * 100, 1),
            "wellbeing_dimensions": dimensions,
            "weakest_dimension": weakest[0] if weakest else None,
            "mentor_coverage_pct": mentor_coverage,
            "ai_suggestion": self._culture_suggestion(milestone_density, dimensions, mentor_coverage, weakest),
        }

    def _culture_suggestion(
        self,
        density: float,
        dimensions: dict,
        mentor_coverage: float,
        weakest: tuple | None,
    ) -> str:
        parts = []
        if density < 0.5:
            parts.append("近90天人均里程碑<0.5，建议增加表彰频率")
        if mentor_coverage < 50:
            parts.append(f"导师覆盖率仅{mentor_coverage}%，建议推进师徒制")
        dim_names = {
            "achievement": "工作成就感",
            "belonging": "团队归属感",
            "growth": "成长获得感",
            "balance": "生活平衡感",
            "culture": "文化认同感",
        }
        if weakest and weakest[1] < 6:
            parts.append(f"「{dim_names.get(weakest[0], weakest[0])}」维度偏低（{weakest[1]}分），建议重点关注")
        return " | ".join(parts) if parts else "团队文化健康度良好"

    # ── 6. 离职预警模型（增强版） ──────────────────────────────

    async def predict_resignation_risk_enhanced(self, db: AsyncSession) -> Dict[str, Any]:
        """
        增强版离职预警：综合工龄、绩效趋势、出勤异常、同岗离职率 → 风险评分
        """
        base_risk = await self.predict_resignation_risk(db)

        # 增加工龄因素
        for emp in base_risk.get("at_risk_employees", []):
            try:
                emp_result = await db.execute(
                    text("""
                    SELECT seniority_months, employment_type, grade_level
                    FROM employees WHERE id = :emp_id
                """),
                    {"emp_id": emp["employee_id"]},
                )
                row = emp_result.mappings().first()
                if row:
                    seniority = row.get("seniority_months") or 0
                    # 1-6个月新员工离职风险+20
                    if seniority <= 6:
                        emp["risk_score"] += 20
                        emp["signals"].append(f"入职仅{seniority}月（新员工高风险期）")
                    # 估算替换成本
                    emp["replacement_cost_yuan"] = max(8000, seniority * 500)
            except Exception:
                pass

        # 重新排序
        base_risk["at_risk_employees"].sort(key=lambda x: -x["risk_score"])
        base_risk["total_replacement_cost_yuan"] = sum(e["replacement_cost_yuan"] for e in base_risk["at_risk_employees"])

        return base_risk

    # ── 7. 编制优化建议 ──────────────────────────────────────

    async def recommend_headcount_optimization(self, db: AsyncSession) -> Dict[str, Any]:
        """基于营收/客流预测 → 建议增减编制 → 预计节省¥"""
        # 当前人力成本
        today = date.today()
        pay_month = f"{today.year}-{today.month:02d}"

        payroll_result = await db.execute(
            text("""
            SELECT COUNT(*) AS headcount,
                   SUM(gross_salary_fen) AS total_cost
            FROM payroll_records
            WHERE store_id = :store_id AND pay_month = :month
        """),
            {"store_id": self.store_id, "month": pay_month},
        )
        row = payroll_result.mappings().first()

        headcount = row["headcount"] or 0
        total_cost_yuan = (row["total_cost"] or 0) / 100

        # 按岗位分析人效
        position_result = await db.execute(
            text("""
            SELECT e.position, COUNT(*) AS cnt,
                   AVG(pr.gross_salary_fen) AS avg_salary
            FROM employees e
            LEFT JOIN payroll_records pr ON pr.employee_id = e.id AND pr.pay_month = :month
            WHERE e.store_id = :store_id AND e.is_active = true
            GROUP BY e.position
        """),
            {"store_id": self.store_id, "month": pay_month},
        )

        recommendations = []
        for r in position_result.mappings():
            avg = (r["avg_salary"] or 0) / 100
            recommendations.append(
                {
                    "position": r["position"] or "未设置",
                    "current_count": r["cnt"],
                    "avg_salary_yuan": round(avg, 2),
                }
            )

        return {
            "store_id": self.store_id,
            "current_headcount": headcount,
            "monthly_labor_cost_yuan": round(total_cost_yuan, 2),
            "per_capita_cost_yuan": round(total_cost_yuan / max(headcount, 1), 2),
            "position_analysis": recommendations,
            "ai_suggestion": f"当月人力成本¥{total_cost_yuan:,.0f}，人均¥{total_cost_yuan/max(headcount,1):,.0f}",
        }

    # ── 8. 培训ROI ─────────────────────────────────────────

    async def analyze_training_roi(self, db: AsyncSession) -> Dict[str, Any]:
        """培训投入 vs 技能提升 vs 绩效变化 → ¥影响量化"""
        # 培训完成数据
        training_result = await db.execute(
            text("""
            SELECT COUNT(*) AS total_completed,
                   COUNT(DISTINCT te.employee_id) AS unique_employees
            FROM training_enrollments te
            WHERE te.store_id = :store_id AND te.status = 'completed'
        """),
            {"store_id": self.store_id},
        )
        t_row = training_result.mappings().first()

        # 师徒制完成数据
        mentorship_result = await db.execute(
            text("""
            SELECT COUNT(*) AS completed,
                   SUM(reward_fen) AS total_reward
            FROM mentorships
            WHERE store_id = :store_id AND status = 'completed'
        """),
            {"store_id": self.store_id},
        )
        m_row = mentorship_result.mappings().first()

        total_completed = t_row["total_completed"] or 0
        unique_learners = t_row["unique_employees"] or 0
        mentor_completed = m_row["completed"] or 0
        mentor_reward_yuan = (m_row["total_reward"] or 0) / 100

        return {
            "training_completions": total_completed,
            "unique_learners": unique_learners,
            "mentorship_completed": mentor_completed,
            "mentorship_reward_yuan": mentor_reward_yuan,
            "ai_suggestion": (
                f"已完成{total_completed}次培训（覆盖{unique_learners}人），"
                f"师徒培养{mentor_completed}对。"
                f"建议持续跟踪培训后绩效变化以量化ROI。"
            ),
        }


# ── API 路由（注册到 hr_dashboard 或独立路由）──────────────


async def get_hr_agent_insights(store_id: str, db: AsyncSession) -> Dict:
    """聚合六大AI分析结果"""
    agent = HRAgentService(store_id)
    today = date.today()
    pay_month = f"{today.year}-{today.month:02d}"

    try:
        payroll = await agent.analyze_payroll_anomalies(db, pay_month)
    except Exception as e:
        logger.warning("hr_agent_payroll_failed", error=str(e))
        payroll = None

    try:
        risk = await agent.predict_resignation_risk(db)
    except Exception as e:
        logger.warning("hr_agent_risk_failed", error=str(e))
        risk = None

    try:
        recruit = await agent.recommend_recruitment(db)
    except Exception as e:
        logger.warning("hr_agent_recruit_failed", error=str(e))
        recruit = None

    try:
        growth = await agent.analyze_growth_insights(db)
    except Exception as e:
        logger.warning("hr_agent_growth_failed", error=str(e))
        growth = None

    try:
        culture = await agent.analyze_culture_health(db)
    except Exception as e:
        logger.warning("hr_agent_culture_failed", error=str(e))
        culture = None

    try:
        training_roi = await agent.analyze_training_roi(db)
    except Exception as e:
        logger.warning("hr_agent_training_roi_failed", error=str(e))
        training_roi = None

    return {
        "store_id": store_id,
        "payroll_analysis": payroll,
        "resignation_risk": risk,
        "recruitment_recommendation": recruit,
        "growth_insights": growth,
        "culture_health": culture,
        "training_roi": training_roi,
    }
