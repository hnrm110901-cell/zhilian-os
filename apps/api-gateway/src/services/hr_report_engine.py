"""
月度人事报表引擎 — 自动生成7张月报
1. 工资异动表 — 新进/调薪/离职工资变动明细
2. 月末编制盘存 — 按部门的编制vs实际人数、缺岗统计
3. 核心岗位培养统计 — 师徒制进展汇总
4. 小时工/灵活用工考勤 — 按日出勤+发薪统计
5. 离职回访汇总 — 本月回访+离职原因分析
6. 人事工作总结与计划 — AI生成（Claude驱动，规则兜底）
7. 社保/保险变动 — 本月增减明细
"""

import calendar
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.models.employee import Employee
from src.models.employee_lifecycle import ChangeType, EmployeeChange
from src.models.exit_interview import ExitInterview
from src.models.mentorship import Mentorship
from src.models.payroll import PayrollRecord
from src.models.social_insurance import EmployeeSocialInsurance

logger = structlog.get_logger()

# AI人事分析系统提示词
HR_SUMMARY_SYSTEM_PROMPT = """你是一位服务于连锁餐饮企业的高级人力资源分析师。
请基于以下月度人事数据，生成结构化的人事工作总结报告。

报告要求：
1. 核心发现（3-5条）：识别数据中的关键模式和异常，不是简单复述数字
2. 风险预警（1-3条）：基于数据趋势识别潜在问题
3. 行动建议（2-4条）：每个建议必须包含具体措施和预期¥影响
4. 下月工作计划（3-5条）：优先级排序

要求：
- 不要复述原始数据，要分析"为什么"和"然后呢"
- 每个建议都要量化预期影响（节省¥X或增加¥Y）
- 语言简洁专业，适合HR经理和老板阅读
- 以JSON格式返回，结构如下：
{
  "key_findings": ["发现1", "发现2", ...],
  "risk_warnings": ["风险1", "风险2", ...],
  "action_recommendations": [
    {"action": "具体措施", "expected_impact_yuan": -5000, "confidence": 0.8, "priority": "high"},
    ...
  ],
  "next_month_plan": [
    {"task": "任务描述", "priority": "high/medium/low"},
    ...
  ]
}"""

HR_INSIGHTS_SYSTEM_PROMPT = """你是一位服务于连锁餐饮企业的资深人力资源数据分析专家。
请基于以下月度人事数据，生成深度人力分析洞察。

分析维度：
1. 离职模式识别 — 哪些岗位/工龄段离职率异常，是否存在季节性规律
2. 人力成本异常检测 — 人均产出是否偏低，加班费占比是否过高
3. 排班效率分析 — 加班费vs营业额比率，是否存在人力浪费
4. 薪资竞争力评估 — 对比餐饮行业数据，当前薪资水平是否有竞争力
5. 培养体系评估 — 师徒制完成率，新人留存率

要求：
- 每个洞察都要有数据支撑和具体¥影响估算
- 标注置信度（0.0-1.0）
- 给出可执行的改善建议
- 以JSON格式返回，结构如下：
{
  "turnover_analysis": {
    "pattern": "描述离职模式",
    "high_risk_positions": ["岗位1", "岗位2"],
    "estimated_replacement_cost_yuan": 15000
  },
  "cost_efficiency": {
    "per_capita_assessment": "描述",
    "overtime_ratio_assessment": "描述",
    "potential_saving_yuan": 5000
  },
  "scheduling_efficiency": {
    "assessment": "描述",
    "recommendations": ["建议1"]
  },
  "salary_competitiveness": {
    "assessment": "描述",
    "risk_level": "high/medium/low"
  },
  "training_effectiveness": {
    "completion_rate_assessment": "描述",
    "retention_impact": "描述"
  },
  "top_recommendations": [
    {"action": "措施", "expected_impact_yuan": -3000, "confidence": 0.7, "priority": "high"}
  ]
}"""


class HRReportEngine:
    """月度人事报表引擎"""

    def __init__(self, store_id: str, brand_id: str):
        self.store_id = store_id
        self.brand_id = brand_id

    async def generate_monthly_report(self, db: AsyncSession, pay_month: str) -> Dict[str, Any]:
        """生成完整月报（7张表）"""
        year, month = int(pay_month[:4]), int(pay_month[5:7])
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])

        report = {
            "store_id": self.store_id,
            "brand_id": self.brand_id,
            "pay_month": pay_month,
            "generated_at": date.today().isoformat(),
        }

        # 1. 工资异动表
        report["salary_changes"] = await self._salary_changes(db, pay_month, month_start, month_end)

        # 2. 月末编制盘存
        report["headcount_inventory"] = await self._headcount_inventory(db, month_end)

        # 3. 核心岗位培养统计
        report["mentorship_summary"] = await self._mentorship_summary(db, month_start, month_end)

        # 4. 小时工考勤
        report["hourly_worker_attendance"] = await self._hourly_worker_attendance(db, pay_month, month_start, month_end)

        # 5. 离职回访汇总
        report["exit_interview_summary"] = await self._exit_interview_summary(db, month_start, month_end)

        # 6. 人事工作总结（AI生成，LLM不可用时规则兜底）
        report["hr_summary"] = await self._generate_hr_summary(report, pay_month)

        # 7. 社保变动
        report["insurance_changes"] = await self._insurance_changes(db, year, month_start, month_end)

        return report

    async def _salary_changes(self, db: AsyncSession, pay_month: str, month_start: date, month_end: date) -> Dict[str, Any]:
        """工资异动表"""
        # 新进员工
        new_result = await db.execute(
            select(Employee).where(
                and_(
                    Employee.store_id == self.store_id,
                    Employee.hire_date >= month_start,
                    Employee.hire_date <= month_end,
                )
            )
        )
        new_employees = new_result.scalars().all()

        # 离职员工
        resign_result = await db.execute(
            select(EmployeeChange, Employee.name)
            .join(Employee, EmployeeChange.employee_id == Employee.id)
            .where(
                and_(
                    EmployeeChange.store_id == self.store_id,
                    EmployeeChange.change_type == ChangeType.RESIGN,
                    EmployeeChange.effective_date >= month_start,
                    EmployeeChange.effective_date <= month_end,
                )
            )
        )
        resignations = resign_result.all()

        # 调薪（本月有生效薪资方案变更的）
        from src.models.payroll import SalaryStructure

        adjustment_result = await db.execute(
            select(SalaryStructure, Employee.name)
            .join(Employee, SalaryStructure.employee_id == Employee.id)
            .where(
                and_(
                    SalaryStructure.store_id == self.store_id,
                    SalaryStructure.effective_date >= month_start,
                    SalaryStructure.effective_date <= month_end,
                    SalaryStructure.is_active.is_(True),
                )
            )
        )
        adjustments = adjustment_result.all()

        return {
            "new_employees": [
                {"id": e.id, "name": e.name, "position": e.position, "hire_date": str(e.hire_date)} for e in new_employees
            ],
            "new_count": len(new_employees),
            "resignations": [
                {"employee_id": lc.employee_id, "name": name, "effective_date": str(lc.effective_date)}
                for lc, name in resignations
            ],
            "resignation_count": len(resignations),
            "salary_adjustments": [
                {
                    "employee_id": ss.employee_id,
                    "name": name,
                    "base_salary_yuan": ss.base_salary_fen / 100,
                    "effective_date": str(ss.effective_date),
                }
                for ss, name in adjustments
            ],
            "adjustment_count": len(adjustments),
        }

    async def _headcount_inventory(self, db: AsyncSession, month_end: date) -> Dict[str, Any]:
        """月末编制盘存"""
        result = await db.execute(
            select(
                Employee.position,
                Employee.employment_type,
                func.count(Employee.id).label("count"),
            )
            .where(
                and_(
                    Employee.store_id == self.store_id,
                    Employee.is_active.is_(True),
                )
            )
            .group_by(Employee.position, Employee.employment_type)
        )
        rows = result.all()

        by_position = {}
        by_type = {}
        total = 0
        for position, emp_type, count in rows:
            pos = position or "未设置"
            by_position[pos] = by_position.get(pos, 0) + count
            t = emp_type or "regular"
            by_type[t] = by_type.get(t, 0) + count
            total += count

        return {
            "total_headcount": total,
            "by_position": by_position,
            "by_employment_type": by_type,
            "date": str(month_end),
        }

    async def _mentorship_summary(self, db: AsyncSession, month_start: date, month_end: date) -> Dict[str, Any]:
        """师徒制进展汇总"""
        result = await db.execute(
            select(Mentorship).where(
                and_(
                    Mentorship.store_id == self.store_id,
                    Mentorship.status.in_(["active", "completed"]),
                )
            )
        )
        mentorships = result.scalars().all()

        active = [m for m in mentorships if m.status == "active"]
        completed_this_month = [
            m
            for m in mentorships
            if m.status == "completed" and m.actual_review_date and month_start <= m.actual_review_date <= month_end
        ]

        return {
            "active_count": len(active),
            "completed_this_month": len(completed_this_month),
            "active_pairs": [
                {
                    "mentor": m.mentor_name,
                    "apprentice": m.apprentice_name,
                    "position": m.target_position,
                    "expected_review": str(m.expected_review_date) if m.expected_review_date else None,
                }
                for m in active
            ],
            "total_reward_yuan": sum(m.reward_fen for m in completed_this_month) / 100,
        }

    async def _hourly_worker_attendance(
        self, db: AsyncSession, pay_month: str, month_start: date, month_end: date
    ) -> Dict[str, Any]:
        """小时工/灵活用工考勤统计"""
        # 查找非正式员工
        result = await db.execute(
            select(Employee).where(
                and_(
                    Employee.store_id == self.store_id,
                    Employee.is_active.is_(True),
                    Employee.employment_type.in_(["part_time", "temp", "outsource_flex"]),
                )
            )
        )
        workers = result.scalars().all()

        items = []
        for w in workers:
            # 查找考勤记录
            from src.models.attendance import AttendanceLog

            att_result = await db.execute(
                select(func.count(AttendanceLog.id)).where(
                    and_(
                        AttendanceLog.employee_id == w.id,
                        AttendanceLog.work_date >= month_start,
                        AttendanceLog.work_date <= month_end,
                        AttendanceLog.status.in_(["normal", "late"]),
                    )
                )
            )
            days = att_result.scalar() or 0

            daily_wage = w.daily_wage_standard_fen or 0
            total_pay = days * daily_wage

            items.append(
                {
                    "employee_id": w.id,
                    "name": w.name,
                    "employment_type": w.employment_type,
                    "attendance_days": days,
                    "daily_wage_yuan": daily_wage / 100,
                    "total_pay_yuan": total_pay / 100,
                }
            )

        return {
            "workers": items,
            "total_workers": len(items),
            "total_days": sum(i["attendance_days"] for i in items),
            "total_pay_yuan": sum(i["total_pay_yuan"] for i in items),
        }

    async def _exit_interview_summary(self, db: AsyncSession, month_start: date, month_end: date) -> Dict[str, Any]:
        """离职回访汇总"""
        result = await db.execute(
            select(ExitInterview).where(
                and_(
                    ExitInterview.store_id == self.store_id,
                    ExitInterview.resign_date >= month_start,
                    ExitInterview.resign_date <= month_end,
                )
            )
        )
        interviews = result.scalars().all()

        reason_dist = {}
        willing_count = 0
        for i in interviews:
            reason_dist[i.resign_reason] = reason_dist.get(i.resign_reason, 0) + 1
            if i.willing_to_return == "yes":
                willing_count += 1

        return {
            "total_exits": len(interviews),
            "interviewed_count": sum(1 for i in interviews if i.interview_date),
            "reason_distribution": reason_dist,
            "willing_to_return_count": willing_count,
            "interview_rate_pct": round(sum(1 for i in interviews if i.interview_date) / max(len(interviews), 1) * 100, 1),
        }

    async def _generate_hr_summary(self, report: Dict, pay_month: str) -> Dict[str, Any]:
        """AI生成人事工作总结 — Claude驱动，规则兜底"""
        # 组装报表上下文
        report_context = self._build_report_context(report, pay_month)

        # 尝试AI生成
        ai_report = None
        if settings.LLM_ENABLED:
            ai_report = await self._call_llm_for_summary(report_context)

        if ai_report is not None:
            # AI生成成功，附加原始离职率
            sc = report.get("salary_changes", {})
            hc = report.get("headcount_inventory", {})
            resignation_rate = sc.get("resignation_count", 0) / max(hc.get("total_headcount", 1), 1) * 100
            ai_report["turnover_rate_pct"] = round(resignation_rate, 1)
            ai_report["source"] = "ai"
            return ai_report

        # LLM不可用或调用失败，回退到规则引擎
        logger.info("hr_summary_fallback_to_rules", store_id=self.store_id)
        return self._generate_rule_based_summary(report_context)

    def _build_report_context(self, report: Dict, pay_month: str) -> Dict[str, Any]:
        """将月报数据组装为AI分析所需的结构化上下文"""
        sc = report.get("salary_changes", {})
        hc = report.get("headcount_inventory", {})
        ms = report.get("mentorship_summary", {})
        ei = report.get("exit_interview_summary", {})
        hw = report.get("hourly_worker_attendance", {})
        ins = report.get("insurance_changes", {})

        total_headcount = hc.get("total_headcount", 0)
        new_count = sc.get("new_count", 0)
        resign_count = sc.get("resignation_count", 0)
        adjustment_count = sc.get("adjustment_count", 0)

        return {
            "store_id": self.store_id,
            "month": pay_month,
            "headcount": {
                "end": total_headcount,
                "new_hire": new_count,
                "resigned": resign_count,
                "by_position": hc.get("by_position", {}),
                "by_employment_type": hc.get("by_employment_type", {}),
            },
            "salary_changes": {
                "adjustment_count": adjustment_count,
                "adjustments": sc.get("salary_adjustments", []),
            },
            "turnover": {
                "rate_pct": round(resign_count / max(total_headcount, 1) * 100, 1),
                "reasons": ei.get("reason_distribution", {}),
                "exit_interview_rate_pct": ei.get("interview_rate_pct", 0),
                "willing_to_return_count": ei.get("willing_to_return_count", 0),
                "total_exits": ei.get("total_exits", 0),
            },
            "training": {
                "active_mentorships": ms.get("active_count", 0),
                "completed_this_month": ms.get("completed_this_month", 0),
                "total_reward_yuan": ms.get("total_reward_yuan", 0),
            },
            "hourly_workers": {
                "total_workers": hw.get("total_workers", 0),
                "total_days": hw.get("total_days", 0),
                "total_pay_yuan": hw.get("total_pay_yuan", 0),
            },
            "insurance": {
                "new_enrollments": ins.get("new_enrollments", 0),
            },
        }

    async def _call_llm_for_summary(self, report_context: Dict) -> Optional[Dict[str, Any]]:
        """调用LLM生成人事工作总结"""
        try:
            from src.core.llm import get_llm_client

            prompt = json.dumps(report_context, ensure_ascii=False, default=str)
            response = await get_llm_client().generate(
                prompt=prompt,
                system_prompt=HR_SUMMARY_SYSTEM_PROMPT,
                max_tokens=1500,
                temperature=0.4,
            )

            logger.info(
                "hr_summary_llm_completed",
                store_id=self.store_id,
                month=report_context.get("month"),
                response_length=len(response),
            )

            # 解析LLM返回的JSON
            return self._parse_llm_response(response)

        except Exception as e:
            logger.error(
                "hr_summary_llm_failed",
                store_id=self.store_id,
                error=str(e),
                exc_info=e,
            )
            return None

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的JSON响应，容错处理"""
        try:
            # 尝试直接解析
            parsed = json.loads(response)
        except json.JSONDecodeError:
            # LLM可能返回了markdown包裹的JSON，尝试提取
            import re

            json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    logger.warning("hr_summary_llm_json_parse_failed", response_preview=response[:200])
                    return None
            else:
                # 最后尝试：找第一个 { 到最后一个 }
                start = response.find("{")
                end = response.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        parsed = json.loads(response[start : end + 1])
                    except json.JSONDecodeError:
                        logger.warning("hr_summary_llm_json_parse_failed", response_preview=response[:200])
                        return None
                else:
                    logger.warning("hr_summary_llm_no_json_found", response_preview=response[:200])
                    return None

        # 验证必要字段存在
        required_keys = {"key_findings", "risk_warnings", "action_recommendations", "next_month_plan"}
        if not required_keys.issubset(set(parsed.keys())):
            missing = required_keys - set(parsed.keys())
            logger.warning("hr_summary_llm_missing_fields", missing=list(missing))
            # 补充缺失字段为空列表
            for key in missing:
                parsed[key] = []

        return parsed

    def _generate_rule_based_summary(self, context: Dict) -> Dict[str, Any]:
        """规则引擎兜底 — 当LLM不可用时生成基础总结"""
        hc = context.get("headcount", {})
        turnover = context.get("turnover", {})
        training = context.get("training", {})
        hw = context.get("hourly_workers", {})

        new_count = hc.get("new_hire", 0)
        resign_count = hc.get("resigned", 0)
        total = hc.get("end", 0)
        turnover_rate = turnover.get("rate_pct", 0)

        # 核心发现
        key_findings = []
        if new_count > 0:
            key_findings.append(f"本月新入职{new_count}人")
        if resign_count > 0:
            key_findings.append(f"离职{resign_count}人")
        if training.get("completed_this_month", 0) > 0:
            key_findings.append(f"完成师徒培养{training['completed_this_month']}对")
        if total > 0:
            key_findings.append(f"月末在编{total}人")

        # 风险预警
        risk_warnings = []
        if turnover_rate > 5:
            risk_warnings.append(f"本月离职率{turnover_rate:.1f}%偏高，建议关注员工满意度和薪资竞争力")
        if turnover.get("exit_interview_rate_pct", 0) < 80:
            risk_warnings.append(
                f"离职回访率{turnover.get('exit_interview_rate_pct', 0)}%，" f"建议加强回访以获取真实离职原因"
            )

        # 行动建议
        action_recommendations = []
        if resign_count > 0:
            avg_replacement_cost = 5000  # 餐饮行业平均招聘+培训成本
            action_recommendations.append(
                {
                    "action": "启动离职岗位补招，优先内部推荐降低招聘成本",
                    "expected_impact_yuan": -(resign_count * avg_replacement_cost),
                    "confidence": 0.6,
                    "priority": "high",
                }
            )
        if training.get("active_mentorships", 0) > 0:
            action_recommendations.append(
                {
                    "action": f"跟进{training['active_mentorships']}对师徒培养进度，确保按期评审",
                    "expected_impact_yuan": -(training["active_mentorships"] * 500),
                    "confidence": 0.5,
                    "priority": "medium",
                }
            )

        # 下月计划
        next_month_plan = []
        if resign_count > 0:
            next_month_plan.append({"task": "补充离职岗位招聘", "priority": "high"})
        if training.get("active_mentorships", 0) > 0:
            next_month_plan.append(
                {
                    "task": f"跟进{training['active_mentorships']}对师徒培养进度",
                    "priority": "medium",
                }
            )
        next_month_plan.append({"task": "完成下月薪酬核算准备", "priority": "medium"})

        return {
            "key_findings": key_findings,
            "risk_warnings": risk_warnings,
            "action_recommendations": action_recommendations,
            "next_month_plan": next_month_plan,
            "turnover_rate_pct": round(turnover_rate, 1),
            "source": "rules_only",
        }

    # ── AI深度洞察 ─────────────────────────────────────────────────

    async def generate_ai_insights(self, db: AsyncSession, pay_month: str) -> Dict[str, Any]:
        """
        独立的AI洞察接口 — 生成深度人力分析

        区别于月报的"总结"，这里是"洞察"：
        - 离职模式识别（哪些岗位/工龄段离职率异常）
        - 人力成本异常检测（哪些门店的人均产出偏低）
        - 排班效率分析（加班费vs营业额比率趋势）
        - 薪资竞争力评估（对比行业数据）
        """
        # 先生成完整月报以获取基础数据
        report = await self.generate_monthly_report(db, pay_month)
        report_context = self._build_report_context(report, pay_month)

        # 补充洞察所需的额外数据
        year, month = int(pay_month[:4]), int(pay_month[5:7])
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])

        # 查询各岗位离职分布
        position_turnover = await self._query_position_turnover(db, month_start, month_end)
        report_context["position_turnover"] = position_turnover

        # 查询加班情况
        overtime_data = await self._query_overtime_data(db, month_start, month_end)
        report_context["overtime"] = overtime_data

        result = {
            "generated_at": datetime.utcnow().isoformat(),
            "store_id": self.store_id,
            "month": pay_month,
            "raw_metrics": report_context,
        }

        # 尝试AI洞察
        ai_insights = None
        if settings.LLM_ENABLED:
            ai_insights = await self._call_llm_for_insights(report_context)

        if ai_insights is not None:
            result["data_source"] = "ai+data"
            result["summary"] = ai_insights
        else:
            # 规则兜底洞察
            result["data_source"] = "rules_only"
            result["summary"] = self._generate_rule_based_insights(report_context)

        return result

    async def _query_position_turnover(self, db: AsyncSession, month_start: date, month_end: date) -> Dict[str, Any]:
        """按岗位查询离职分布"""
        result = await db.execute(
            select(
                Employee.position,
                func.count(EmployeeChange.id).label("resign_count"),
            )
            .join(EmployeeChange, EmployeeChange.employee_id == Employee.id)
            .where(
                and_(
                    EmployeeChange.store_id == self.store_id,
                    EmployeeChange.change_type == ChangeType.RESIGN,
                    EmployeeChange.effective_date >= month_start,
                    EmployeeChange.effective_date <= month_end,
                )
            )
            .group_by(Employee.position)
        )
        rows = result.all()
        return {(pos or "未设置"): count for pos, count in rows}

    async def _query_overtime_data(self, db: AsyncSession, month_start: date, month_end: date) -> Dict[str, Any]:
        """查询加班相关数据"""
        from src.models.attendance import AttendanceLog

        # 统计迟到和加班记录
        result = await db.execute(
            select(
                AttendanceLog.status,
                func.count(AttendanceLog.id).label("count"),
            )
            .where(
                and_(
                    AttendanceLog.store_id == self.store_id,
                    AttendanceLog.work_date >= month_start,
                    AttendanceLog.work_date <= month_end,
                )
            )
            .group_by(AttendanceLog.status)
        )
        rows = result.all()
        status_dist = {status: count for status, count in rows}

        return {
            "total_records": sum(status_dist.values()),
            "normal_count": status_dist.get("normal", 0),
            "late_count": status_dist.get("late", 0),
            "absent_count": status_dist.get("absent", 0),
            "overtime_count": status_dist.get("overtime", 0),
        }

    async def _call_llm_for_insights(self, report_context: Dict) -> Optional[Dict[str, Any]]:
        """调用LLM生成深度人力洞察"""
        try:
            from src.core.llm import get_llm_client

            prompt = json.dumps(report_context, ensure_ascii=False, default=str)
            response = await get_llm_client().generate(
                prompt=prompt,
                system_prompt=HR_INSIGHTS_SYSTEM_PROMPT,
                max_tokens=2000,
                temperature=0.4,
            )

            logger.info(
                "hr_insights_llm_completed",
                store_id=self.store_id,
                month=report_context.get("month"),
                response_length=len(response),
            )

            parsed = self._parse_llm_response(response)
            if parsed is None:
                return None

            # 确保top_recommendations有¥影响
            recommendations = parsed.get("top_recommendations", [])
            for rec in recommendations:
                if "expected_impact_yuan" not in rec:
                    rec["expected_impact_yuan"] = 0
                if "confidence" not in rec:
                    rec["confidence"] = 0.5
                if "priority" not in rec:
                    rec["priority"] = "medium"

            return parsed

        except Exception as e:
            logger.error(
                "hr_insights_llm_failed",
                store_id=self.store_id,
                error=str(e),
                exc_info=e,
            )
            return None

    def _generate_rule_based_insights(self, context: Dict) -> Dict[str, Any]:
        """规则兜底的深度洞察"""
        hc = context.get("headcount", {})
        turnover = context.get("turnover", {})
        training = context.get("training", {})
        overtime = context.get("overtime", {})
        position_turnover = context.get("position_turnover", {})

        total = hc.get("end", 0)
        resign_count = hc.get("resigned", 0)
        turnover_rate = turnover.get("rate_pct", 0)

        # 离职分析
        high_risk_positions = [pos for pos, count in position_turnover.items() if count >= 2]

        # 成本分析
        replacement_cost = resign_count * 5000  # 餐饮行业平均招聘+培训成本

        # 排班效率
        late_count = overtime.get("late_count", 0)
        total_records = overtime.get("total_records", 1)
        late_rate = round(late_count / max(total_records, 1) * 100, 1)

        top_recommendations = []
        if turnover_rate > 5:
            top_recommendations.append(
                {
                    "action": "开展员工满意度调查，针对高离职岗位制定专项留人方案",
                    "expected_impact_yuan": -replacement_cost,
                    "confidence": 0.6,
                    "priority": "high",
                }
            )
        if late_rate > 10:
            top_recommendations.append(
                {
                    "action": "优化排班制度，减少迟到率，考虑弹性上班时间",
                    "expected_impact_yuan": -2000,
                    "confidence": 0.5,
                    "priority": "medium",
                }
            )
        if training.get("active_mentorships", 0) > 0:
            top_recommendations.append(
                {
                    "action": "加速师徒培养进度，降低新人流失带来的重复培训成本",
                    "expected_impact_yuan": -(training["active_mentorships"] * 800),
                    "confidence": 0.5,
                    "priority": "medium",
                }
            )

        return {
            "turnover_analysis": {
                "pattern": f"本月离职率{turnover_rate}%，共{resign_count}人离职",
                "high_risk_positions": high_risk_positions,
                "estimated_replacement_cost_yuan": replacement_cost,
            },
            "cost_efficiency": {
                "per_capita_assessment": f"当前在编{total}人",
                "overtime_ratio_assessment": f"迟到记录{late_count}次，迟到率{late_rate}%",
                "potential_saving_yuan": replacement_cost if turnover_rate > 5 else 0,
            },
            "scheduling_efficiency": {
                "assessment": f"出勤记录{total_records}条，正常{overtime.get('normal_count', 0)}条",
                "recommendations": ["优化高峰时段排班密度"] if late_rate > 10 else [],
            },
            "salary_competitiveness": {
                "assessment": "需补充行业薪资数据进行对比分析",
                "risk_level": "high" if turnover_rate > 10 else ("medium" if turnover_rate > 5 else "low"),
            },
            "training_effectiveness": {
                "completion_rate_assessment": (
                    f"本月完成{training.get('completed_this_month', 0)}对师徒培养，"
                    f"当前{training.get('active_mentorships', 0)}对进行中"
                ),
                "retention_impact": "师徒制有助于降低新人3个月内离职率",
            },
            "top_recommendations": top_recommendations,
        }

    async def _insurance_changes(self, db: AsyncSession, year: int, month_start: date, month_end: date) -> Dict[str, Any]:
        """社保/保险变动"""
        # 本月新增参保
        new_result = await db.execute(
            select(func.count(EmployeeSocialInsurance.id)).where(
                and_(
                    EmployeeSocialInsurance.effective_year == year,
                    EmployeeSocialInsurance.created_at >= month_start,
                )
            )
        )
        new_count = new_result.scalar() or 0

        return {
            "new_enrollments": new_count,
            "year": year,
        }
