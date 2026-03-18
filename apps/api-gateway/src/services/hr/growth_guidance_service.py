"""GrowthGuidanceService — WF-6 入职智能引导

触发：OnboardingProcess approved → Celery → generate_plan
能力：按岗位本体生成90天成长计划，每周推送目标，30/60/90天里程碑评估
"""
import uuid
from datetime import date, timedelta
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 岗位→技能路线图（餐饮行业内置语义）
_ROLE_SKILL_MAPS: dict[str, list[dict]] = {
    "server": [
        {"week": 1, "skill": "服务标准流程", "target": "独立完成点单"},
        {"week": 2, "skill": "菜品知识", "target": "能介绍全部招牌菜"},
        {"week": 4, "skill": "客诉处理", "target": "独立处理简单客诉"},
        {"week": 8, "skill": "VIP接待", "target": "独立完成VIP桌服务"},
        {"week": 12, "skill": "带新人", "target": "可辅导1名新人"},
    ],
    "chef": [
        {"week": 1, "skill": "厨房安全规范", "target": "通过安全考核"},
        {"week": 2, "skill": "基础备料", "target": "独立完成日常备料"},
        {"week": 4, "skill": "标准菜品制作", "target": "独立出品3道招牌菜"},
        {"week": 8, "skill": "菜品质量把控", "target": "出品合格率≥95%"},
        {"week": 12, "skill": "新菜研发", "target": "参与1道新菜研发"},
    ],
    "manager": [
        {"week": 1, "skill": "门店运营SOP", "target": "掌握开闭店流程"},
        {"week": 2, "skill": "POS/ERP系统", "target": "熟练操作全部功能"},
        {"week": 4, "skill": "排班管理", "target": "独立完成周排班"},
        {"week": 8, "skill": "成本控制", "target": "食材成本率下降0.5%"},
        {"week": 12, "skill": "团队管理", "target": "团队满意度≥80%"},
    ],
    "default": [
        {"week": 1, "skill": "岗位基础培训", "target": "通过入职培训考核"},
        {"week": 4, "skill": "独立上岗", "target": "可独立完成岗位工作"},
        {"week": 12, "skill": "技能提升", "target": "掌握1项额外技能"},
    ],
}

# 岗位基准月薪（用于¥预测）
_ROLE_BASE_YUAN: dict[str, float] = {
    "server": 4000.0,
    "chef": 6000.0,
    "manager": 8000.0,
    "default": 4500.0,
}


def _match_role(job_title: str) -> str:
    """模糊匹配岗位类型"""
    jt = job_title.lower()
    if any(k in jt for k in ["server", "服务", "楼面", "waiter"]):
        return "server"
    if any(k in jt for k in ["chef", "厨师", "cook", "烹饪"]):
        return "chef"
    if any(k in jt for k in ["manager", "店长", "经理", "主管"]):
        return "manager"
    return "default"


class GrowthGuidanceService:

    async def generate_plan(
        self,
        assignment_id: uuid.UUID,
        job_title: str,
        session: AsyncSession,
        start_date: Optional[date] = None,
    ) -> dict:
        """生成90天个性化成长计划"""
        role = _match_role(job_title)
        skills = _ROLE_SKILL_MAPS.get(role, _ROLE_SKILL_MAPS["default"])
        base_yuan = _ROLE_BASE_YUAN.get(role, _ROLE_BASE_YUAN["default"])
        plan_start = start_date or date.today()

        weekly_goals = []
        for s in skills:
            goal_date = plan_start + timedelta(weeks=s["week"])
            weekly_goals.append({
                "week": s["week"],
                "target_date": goal_date.isoformat(),
                "skill": s["skill"],
                "target": s["target"],
                "completed": False,
            })

        # AI预测：按技能习得进度估算90天后¥收益
        skill_count = len(skills)
        expected_revenue_yuan = round(base_yuan * 0.05 * skill_count, 2)

        plan = {
            "assignment_id": str(assignment_id),
            "job_title": job_title,
            "role_type": role,
            "plan_start": plan_start.isoformat(),
            "plan_end": (plan_start + timedelta(days=90)).isoformat(),
            "weekly_goals": weekly_goals,
            "milestones": [
                {"day": 30, "date": (plan_start + timedelta(days=30)).isoformat(), "review": "month_1"},
                {"day": 60, "date": (plan_start + timedelta(days=60)).isoformat(), "review": "month_2"},
                {"day": 90, "date": (plan_start + timedelta(days=90)).isoformat(), "review": "probation_end"},
            ],
            "expected_revenue_by_day90_yuan": expected_revenue_yuan,
        }

        logger.info(
            "growth.plan_generated",
            assignment_id=str(assignment_id),
            role=role,
            goal_count=len(weekly_goals),
            expected_yuan=expected_revenue_yuan,
        )
        return plan

    async def weekly_checkin(
        self,
        assignment_id: uuid.UUID,
        week_num: int,
        job_title: str,
        session: AsyncSession,
    ) -> dict:
        """每周检查进度，返回本周目标和激励消息"""
        role = _match_role(job_title)
        skills = _ROLE_SKILL_MAPS.get(role, _ROLE_SKILL_MAPS["default"])

        current_goals = [s for s in skills if s["week"] <= week_num]
        upcoming = [s for s in skills if s["week"] == week_num]

        progress_pct = round(len(current_goals) / max(len(skills), 1) * 100, 1)

        message = f"第{week_num}周进度：{progress_pct}%。"
        if upcoming:
            message += f"本周目标：{upcoming[0]['target']}"
        if progress_pct < 50 and week_num >= 4:
            message += "（进度偏慢，建议加强辅导）"

        return {
            "assignment_id": str(assignment_id),
            "week": week_num,
            "progress_pct": progress_pct,
            "current_goal": upcoming[0] if upcoming else None,
            "message": message,
        }

    async def milestone_review(
        self,
        assignment_id: uuid.UUID,
        day: int,
        job_title: str,
        session: AsyncSession,
    ) -> dict:
        """30/60/90天里程碑评估"""
        if day not in (30, 60, 90):
            raise ValueError(f"Invalid milestone day: {day}, must be 30/60/90")

        role = _match_role(job_title)
        skills = _ROLE_SKILL_MAPS.get(role, _ROLE_SKILL_MAPS["default"])
        base_yuan = _ROLE_BASE_YUAN.get(role, _ROLE_BASE_YUAN["default"])

        weeks_elapsed = day // 7
        expected_skills = [s for s in skills if s["week"] <= weeks_elapsed]

        # 预测¥贡献
        progress_ratio = len(expected_skills) / max(len(skills), 1)
        current_value_yuan = round(base_yuan * 0.05 * len(expected_skills), 2)

        return {
            "assignment_id": str(assignment_id),
            "milestone_day": day,
            "skills_expected": len(expected_skills),
            "skills_total": len(skills),
            "progress_pct": round(progress_ratio * 100, 1),
            "current_value_yuan": current_value_yuan,
            "recommendation": "继续当前进度" if progress_ratio >= 0.5 else "建议加强辅导",
        }
