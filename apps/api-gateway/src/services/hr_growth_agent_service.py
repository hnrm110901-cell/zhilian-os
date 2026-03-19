"""
HR Growth Agent Service — 员工成长旅程AI引擎
让专业和品牌文化及幸福的人生哲学陪伴员工的工作生命周期全旅程

核心能力：
1. 技能差距分析 → 自动生成成长计划
2. 晋升就绪度评估 → 职业路径推荐
3. 里程碑自动触发 → 企微庆祝推送
4. 幸福指数趋势 → 关怀预警
5. 业人效能关联 → 让员工创造的价值可见
"""

import json
import uuid as uuid_mod
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.attendance import AttendanceLog
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.employee_growth import (
    CareerPath,
    EmployeeGrowthPlan,
    EmployeeMilestone,
    EmployeeSkill,
    EmployeeWellbeing,
    GrowthPlanStatus,
    MilestoneType,
    SkillDefinition,
    SkillLevel,
)
from src.models.employee_lifecycle import ChangeType, EmployeeChange
from src.models.payroll import PayrollRecord
from src.models.performance_review import PerformanceReview
from src.models.reward_penalty import RewardPenaltyRecord, RewardPenaltyStatus, RewardPenaltyType

logger = structlog.get_logger()

# 技能等级数值映射（用于计算差距）
LEVEL_NUMERIC = {
    SkillLevel.NOVICE: 1,
    SkillLevel.APPRENTICE: 2,
    SkillLevel.JOURNEYMAN: 3,
    SkillLevel.EXPERT: 4,
    SkillLevel.MASTER: 5,
    "novice": 1,
    "apprentice": 2,
    "journeyman": 3,
    "expert": 4,
    "master": 5,
}

# 餐饮行业默认技能体系
DEFAULT_SKILLS = {
    "服务": [
        ("客户接待", ["waiter", "cashier", "manager"]),
        ("菜品推荐", ["waiter"]),
        ("投诉处理", ["waiter", "manager", "shift_leader"]),
        ("宴会服务", ["waiter", "manager"]),
    ],
    "烹饪": [
        ("基本烹饪", ["chef", "kitchen"]),
        ("菜品出品", ["chef"]),
        ("食材管理", ["chef", "kitchen"]),
        ("菜品创新", ["chef"]),
    ],
    "管理": [
        ("团队管理", ["manager", "shift_leader", "store_manager"]),
        ("排班调度", ["manager", "store_manager"]),
        ("成本控制", ["manager", "store_manager", "chef"]),
        ("目标管理", ["manager", "store_manager"]),
    ],
    "安全": [
        ("食品安全", ["chef", "kitchen", "waiter", "manager"]),
        ("消防安全", ["manager", "store_manager"]),
        ("设备操作", ["chef", "kitchen"]),
    ],
    "文化": [
        ("品牌文化", ["waiter", "chef", "cashier", "manager", "store_manager"]),
        ("服务理念", ["waiter", "cashier", "manager"]),
        ("团队协作", ["waiter", "chef", "cashier", "manager"]),
    ],
}


async def analyze_skill_gaps(db: AsyncSession, store_id: str, employee_id: str) -> Dict[str, Any]:
    """
    技能差距分析：对比员工当前技能等级与岗位要求。
    返回差距列表 + AI成长建议。
    """
    # 获取员工信息（三层模型：Person）
    person_result = await db.execute(
        select(Person).where(Person.legacy_employee_id == str(employee_id))
    )
    person = person_result.scalar_one_or_none()
    if not person:
        return {"error": "员工不存在"}

    # 查当前岗位（EmploymentAssignment）
    assign_result = await db.execute(
        select(EmploymentAssignment)
        .where(and_(EmploymentAssignment.person_id == person.id, EmploymentAssignment.status == "active"))
        .order_by(EmploymentAssignment.start_date.desc())
        .limit(1)
    )
    assignment = assign_result.scalar_one_or_none()
    position = assignment.position if assignment else None

    # 获取岗位要求的技能
    skill_defs = await db.execute(
        select(SkillDefinition).where(
            and_(
                SkillDefinition.is_active.is_(True),
                SkillDefinition.applicable_positions.op("@>")(f'["{position}"]') if position else True,
            )
        )
    )
    required_skills = skill_defs.scalars().all()

    # 获取员工当前技能
    emp_skills = await db.execute(
        select(EmployeeSkill).where(
            EmployeeSkill.employee_id == employee_id,
        )
    )
    current_skills = {str(s.skill_id): s for s in emp_skills.scalars().all()}

    gaps = []
    strengths = []
    for skill_def in required_skills:
        sid = str(skill_def.id)
        required_level = LEVEL_NUMERIC.get(skill_def.required_level, 3)
        current = current_skills.get(sid)
        current_level = LEVEL_NUMERIC.get(current.current_level, 0) if current else 0

        gap = required_level - current_level
        item = {
            "skill_id": sid,
            "skill_name": skill_def.skill_name,
            "category": skill_def.skill_category,
            "required_level": (
                skill_def.required_level.value if hasattr(skill_def.required_level, "value") else str(skill_def.required_level)
            ),
            "current_level": current.current_level.value if current else "未评估",
            "current_score": current.score if current else 0,
            "gap": gap,
            "promotion_weight": skill_def.promotion_weight,
        }
        if gap > 0:
            gaps.append(item)
        elif gap <= 0 and current:
            strengths.append(item)

    # 按权重排序（优先补最重要的差距）
    gaps.sort(key=lambda x: (-x["promotion_weight"], -x["gap"]))

    # 生成AI建议
    total_weight = sum(s.promotion_weight for s in required_skills) or 1
    achieved_weight = sum(s["promotion_weight"] for s in strengths)
    readiness_pct = round(achieved_weight / total_weight * 100, 1)

    suggestions = []
    for g in gaps[:3]:
        suggestions.append(
            f"【{g['category']}】{g['skill_name']}：当前{g['current_level']}，"
            f"需要达到{g['required_level']}，"
            f"建议通过实践+师傅带教提升"
        )

    return {
        "employee_id": employee_id,
        "employee_name": person.name,
        "position": position,
        "readiness_pct": readiness_pct,
        "gap_count": len(gaps),
        "strength_count": len(strengths),
        "gaps": gaps,
        "strengths": strengths,
        "suggestions": suggestions,
    }


async def assess_promotion_readiness(db: AsyncSession, store_id: str, employee_id: str) -> Dict[str, Any]:
    """
    晋升就绪度评估：综合技能、绩效、工龄判断是否可以晋升。
    """
    person_result = await db.execute(
        select(Person).where(Person.legacy_employee_id == str(employee_id))
    )
    person = person_result.scalar_one_or_none()
    if not person:
        return {"error": "员工不存在"}

    # 查当前岗位和最早入职日期
    assign_result = await db.execute(
        select(EmploymentAssignment)
        .where(and_(EmploymentAssignment.person_id == person.id, EmploymentAssignment.status == "active"))
        .order_by(EmploymentAssignment.start_date.asc())
        .limit(1)
    )
    assignment = assign_result.scalar_one_or_none()
    position = assignment.position if assignment else None
    hire_date = assignment.start_date if assignment else None

    # 查找可用的晋升路径
    paths = await db.execute(
        select(CareerPath)
        .where(
            and_(
                CareerPath.from_position == position,
                CareerPath.is_active.is_(True),
            )
        )
        .order_by(CareerPath.sequence)
    )
    available_paths = paths.scalars().all()

    if not available_paths:
        return {
            "employee_id": employee_id,
            "employee_name": person.name,
            "current_position": position,
            "paths": [],
            "message": "暂无可用晋升路径配置",
        }

    # 计算在岗月数
    tenure_months = 0
    if hire_date:
        delta = date.today() - hire_date
        tenure_months = delta.days // 30

    # 获取最近绩效
    perf_result = await db.execute(
        select(PerformanceReview)
        .where(
            PerformanceReview.employee_id == employee_id,
        )
        .order_by(PerformanceReview.created_at.desc())
        .limit(1)
    )
    latest_perf = perf_result.scalar_one_or_none()
    perf_score = float(latest_perf.total_score) if latest_perf and latest_perf.total_score else 0
    perf_level = latest_perf.level if latest_perf else None

    # 技能差距分析
    skill_analysis = await analyze_skill_gaps(db, store_id, employee_id)

    results = []
    for path in available_paths:
        checks = []

        # 检查1：在岗时间
        tenure_ok = tenure_months >= path.min_tenure_months
        checks.append(
            {
                "condition": f"在岗≥{path.min_tenure_months}个月",
                "met": tenure_ok,
                "current": f"{tenure_months}个月",
            }
        )

        # 检查2：绩效
        perf_ok = perf_score >= path.min_performance_score
        checks.append(
            {
                "condition": f"绩效≥{path.min_performance_score}分",
                "met": perf_ok,
                "current": f"{perf_score:.0f}分" if perf_score else "未评估",
            }
        )

        # 检查3：技能就绪
        skill_ready = skill_analysis.get("readiness_pct", 0) >= 80
        checks.append(
            {
                "condition": "技能就绪度≥80%",
                "met": skill_ready,
                "current": f"{skill_analysis.get('readiness_pct', 0)}%",
            }
        )

        met_count = sum(1 for c in checks if c["met"])
        readiness = round(met_count / len(checks) * 100)

        results.append(
            {
                "path_name": path.path_name,
                "target_position": path.to_position,
                "salary_increase_pct": float(path.salary_increase_pct or 0),
                "readiness_pct": readiness,
                "checks": checks,
                "all_met": met_count == len(checks),
                "suggestion": (
                    f"已满足全部条件，建议启动晋升流程"
                    if met_count == len(checks)
                    else f"还需满足{len(checks) - met_count}项条件"
                ),
            }
        )

    return {
        "employee_id": employee_id,
        "employee_name": person.name,
        "current_position": position,
        "tenure_months": tenure_months,
        "performance_score": perf_score,
        "paths": results,
    }


async def generate_growth_plan(db: AsyncSession, store_id: str, employee_id: str) -> Dict[str, Any]:
    """
    AI自动生成成长计划：基于技能差距+职业路径+绩效结果。
    当 LLM 可用时使用 Claude 生成个性化计划，否则回退到规则引擎。
    """
    skill_analysis = await analyze_skill_gaps(db, store_id, employee_id)
    if "error" in skill_analysis:
        return skill_analysis

    promotion = await assess_promotion_readiness(db, store_id, employee_id)

    # 获取员工详情（用于 LLM 上下文）
    person_result = await db.execute(
        select(Person).where(Person.legacy_employee_id == str(employee_id))
    )
    person = person_result.scalar_one_or_none()
    tenure_months = 0
    if person:
        assign_result = await db.execute(
            select(EmploymentAssignment)
            .where(and_(EmploymentAssignment.person_id == person.id, EmploymentAssignment.status == "active"))
            .order_by(EmploymentAssignment.start_date.asc())
            .limit(1)
        )
        asgn = assign_result.scalar_one_or_none()
        if asgn and asgn.start_date:
            tenure_months = (date.today() - asgn.start_date).days // 30

    # 获取最近绩效分数
    perf_scores = []
    try:
        perf_result = await db.execute(
            select(PerformanceReview.total_score)
            .where(
                PerformanceReview.employee_id == employee_id,
            )
            .order_by(PerformanceReview.created_at.desc())
            .limit(3)
        )
        perf_scores = [float(r) for r in perf_result.scalars().all() if r is not None]
    except Exception:
        pass

    # 获取可用课程（从技能定义的描述字段提取）
    available_courses = []
    for gap in skill_analysis.get("gaps", [])[:5]:
        available_courses.append(
            {
                "title": f"{gap['skill_name']}提升课程",
                "category": gap["category"],
                "credits": gap.get("promotion_weight", 50) // 20 + 1,
            }
        )

    # 构建晋升路径信息
    career_paths = []
    for path in promotion.get("paths", [])[:3]:
        career_paths.append(
            {
                "target_position": path.get("target_position"),
                "readiness_pct": path.get("readiness_pct", 0),
                "salary_increase_pct": path.get("salary_increase_pct", 0),
                "checks": path.get("checks", []),
            }
        )

    target_position = None
    if promotion.get("paths"):
        target_position = promotion["paths"][0].get("target_position")

    # ── 尝试使用 LLM 生成个性化成长计划 ──────────────────────
    tasks = None
    ai_reasoning = ""
    llm_used = False

    try:
        from src.core.config import settings

        if settings.LLM_ENABLED:
            from src.core.llm import get_llm_client

            growth_context = {
                "employee": {
                    "name": skill_analysis["employee_name"],
                    "position": skill_analysis.get("position", "未知"),
                    "tenure_months": tenure_months,
                    "performance_scores": perf_scores,
                },
                "skill_gaps": [
                    {
                        "skill": g["skill_name"],
                        "category": g["category"],
                        "current": g["current_level"],
                        "required": g["required_level"],
                        "gap": g["gap"],
                    }
                    for g in skill_analysis.get("gaps", [])[:5]
                ],
                "strengths": [s["skill_name"] for s in skill_analysis.get("strengths", [])[:5]],
                "career_paths": career_paths,
                "available_courses": available_courses,
                "readiness_pct": skill_analysis.get("readiness_pct", 0),
            }

            system_prompt = (
                "你是一位餐饮连锁企业的人才发展顾问。\n"
                "基于员工当前状况和发展目标，生成个性化的成长计划。\n\n"
                "要求：\n"
                '1. 不要千篇一律的"提升XX到X级" — 要具体到行动步骤\n'
                "2. 每个任务要有：明确的完成标准、建议时间节点、推荐导师/课程\n"
                "3. 考虑员工当前水平和学习曲线，不要设不切实际的目标\n"
                "4. 给出预期晋升时间线和薪资增长预期\n"
                "5. 包含里程碑检查点（1个月/3个月/6个月）\n\n"
                "以JSON格式返回，结构如下：\n"
                "{\n"
                '  "tasks": [\n'
                '    {"task": "具体任务描述", "type": "skill_up|promotion_prep|culture|mentoring",\n'
                '     "category": "分类", "priority": "high|medium|low",\n'
                '     "completion_criteria": "完成标准",\n'
                '     "target_date": "建议完成日期如2026-04-15",\n'
                '     "recommended_course": "推荐课程或活动",\n'
                '     "done": false}\n'
                "  ],\n"
                '  "milestones": [\n'
                '    {"month": 1, "checkpoint": "1个月检查点描述"},\n'
                '    {"month": 3, "checkpoint": "3个月检查点描述"},\n'
                '    {"month": 6, "checkpoint": "6个月检查点描述"}\n'
                "  ],\n"
                '  "expected_promotion_months": 12,\n'
                '  "expected_salary_increase_pct": 15,\n'
                '  "ai_reasoning": "生成此计划的核心逻辑说明"\n'
                "}\n"
                "只返回JSON，不要其他文字。"
            )

            logger.info(
                "growth_plan_llm_request",
                employee_id=employee_id,
                store_id=store_id,
                gaps_count=len(growth_context["skill_gaps"]),
            )

            response = await get_llm_client().generate(
                prompt=json.dumps(growth_context, ensure_ascii=False, default=str),
                system_prompt=system_prompt,
                max_tokens=1500,
                temperature=0.4,
            )

            # 解析 LLM 返回的 JSON
            # 尝试提取 JSON（可能包裹在 ```json ... ``` 中）
            raw = response.strip()
            if raw.startswith("```"):
                # 去掉 markdown 代码块
                lines = raw.split("\n")
                raw = "\n".join(l for l in lines if not l.strip().startswith("```"))
            parsed = json.loads(raw)
            tasks = parsed.get("tasks", [])
            ai_reasoning = parsed.get("ai_reasoning", "Claude AI 生成个性化成长计划")
            llm_used = True

            logger.info(
                "growth_plan_llm_success",
                employee_id=employee_id,
                tasks_count=len(tasks),
            )

    except Exception as e:
        logger.warning(
            "growth_plan_llm_fallback",
            employee_id=employee_id,
            error=str(e),
        )
        tasks = None

    # ── 回退到规则引擎 ──────────────────────────────────────
    if tasks is None:
        tasks = []
        for gap in skill_analysis.get("gaps", [])[:5]:
            tasks.append(
                {
                    "task": f"提升{gap['skill_name']}到{gap['required_level']}级",
                    "type": "skill_up",
                    "category": gap["category"],
                    "priority": "high" if gap["gap"] >= 2 else "medium",
                    "done": False,
                }
            )
        for path in promotion.get("paths", [])[:1]:
            for check in path.get("checks", []):
                if not check["met"]:
                    tasks.append(
                        {
                            "task": f"达成晋升条件：{check['condition']}（当前{check['current']}）",
                            "type": "promotion_prep",
                            "priority": "high",
                            "done": False,
                        }
                    )
        tasks.append(
            {
                "task": "参加品牌文化培训并通过考核",
                "type": "culture",
                "priority": "medium",
                "done": False,
            }
        )
        ai_reasoning = f"基于技能差距分析（{skill_analysis['gap_count']}项待提升）" f"和职业路径评估自动生成（规则引擎）"

    plan_name = f"{skill_analysis['employee_name']}成长计划（{date.today().strftime('%Y年%m月')}）"

    plan = EmployeeGrowthPlan(
        id=uuid_mod.uuid4(),
        store_id=store_id,
        employee_id=employee_id,
        plan_name=plan_name,
        status=GrowthPlanStatus.ACTIVE,
        target_position=target_position,
        target_date=date.today() + timedelta(days=180),
        tasks=tasks,
        total_tasks=len(tasks),
        completed_tasks=0,
        progress_pct=Decimal("0"),
        ai_generated=True,
        ai_reasoning=ai_reasoning,
        started_at=date.today(),
    )
    db.add(plan)
    await db.flush()

    logger.info(
        "growth_plan_generated",
        employee_id=employee_id,
        tasks=len(tasks),
        llm_used=llm_used,
    )

    return {
        "plan_id": str(plan.id),
        "plan_name": plan_name,
        "employee_id": employee_id,
        "employee_name": skill_analysis["employee_name"],
        "target_position": target_position,
        "total_tasks": len(tasks),
        "tasks": tasks,
        "ai_reasoning": ai_reasoning,
        "llm_used": llm_used,
    }


async def check_and_trigger_milestones(db: AsyncSession, store_id: str) -> List[Dict[str, Any]]:
    """
    自动检测并触发里程碑：扫描全店员工，发现新的里程碑事件。
    """
    today = date.today()
    triggered = []

    # 获取在职员工（Person）
    person_result = await db.execute(
        select(Person).where(and_(Person.store_id == store_id, Person.is_active.is_(True)))
    )
    persons = person_result.scalars().all()

    for person in persons:
        legacy_id = person.legacy_employee_id or str(person.id)

        # 查最早入职日期（EmploymentAssignment.start_date）
        hire_assign = await db.execute(
            select(EmploymentAssignment)
            .where(EmploymentAssignment.person_id == person.id)
            .order_by(EmploymentAssignment.start_date.asc())
            .limit(1)
        )
        hire_assignment = hire_assign.scalar_one_or_none()
        hire_date = hire_assignment.start_date if hire_assignment else None

        # 1. 周年纪念（入职满N年）
        if hire_date:
            years = (today - hire_date).days // 365
            if years > 0:
                existing = await db.execute(
                    select(func.count(EmployeeMilestone.id)).where(
                        and_(
                            EmployeeMilestone.employee_id == legacy_id,
                            EmployeeMilestone.milestone_type == MilestoneType.ANNIVERSARY,
                            EmployeeMilestone.title.ilike(f"%{years}周年%"),
                        )
                    )
                )
                if existing.scalar() == 0:
                    ms = EmployeeMilestone(
                        id=uuid_mod.uuid4(),
                        store_id=store_id,
                        employee_id=legacy_id,
                        milestone_type=MilestoneType.ANNIVERSARY,
                        title=f"入职{years}周年",
                        description=f"{person.name}入职已满{years}年，感谢一路同行",
                        achieved_at=today,
                        badge_icon="anniversary",
                    )
                    db.add(ms)
                    triggered.append(
                        {
                            "employee_id": legacy_id,
                            "employee_name": person.name,
                            "milestone": f"入职{years}周年",
                            "type": "anniversary",
                        }
                    )

        # 2. 全勤月（上月无缺勤/迟到）
        last_month = today.replace(day=1) - timedelta(days=1)
        lm_start = last_month.replace(day=1)
        att_result = await db.execute(
            select(func.count(AttendanceLog.id)).where(
                and_(
                    AttendanceLog.employee_id == legacy_id,
                    AttendanceLog.work_date >= lm_start,
                    AttendanceLog.work_date <= last_month,
                    AttendanceLog.status.in_(["absent", "late"]),
                )
            )
        )
        bad_days = att_result.scalar() or 0
        if bad_days == 0:
            # 检查是否有出勤记录（避免无数据时误判）
            total_att = await db.execute(
                select(func.count(AttendanceLog.id)).where(
                    and_(
                        AttendanceLog.employee_id == legacy_id,
                        AttendanceLog.work_date >= lm_start,
                        AttendanceLog.work_date <= last_month,
                    )
                )
            )
            if (total_att.scalar() or 0) >= 20:
                period = f"{lm_start.year}-{lm_start.month:02d}"
                existing_pa = await db.execute(
                    select(func.count(EmployeeMilestone.id)).where(
                        and_(
                            EmployeeMilestone.employee_id == legacy_id,
                            EmployeeMilestone.milestone_type == MilestoneType.PERFECT_ATTENDANCE,
                            EmployeeMilestone.title.ilike(f"%{period}%"),
                        )
                    )
                )
                if existing_pa.scalar() == 0:
                    ms = EmployeeMilestone(
                        id=uuid_mod.uuid4(),
                        store_id=store_id,
                        employee_id=legacy_id,
                        milestone_type=MilestoneType.PERFECT_ATTENDANCE,
                        title=f"{period}全勤之星",
                        description=f"{person.name}在{period}保持全勤，表现优秀",
                        achieved_at=today,
                        badge_icon="perfect_attendance",
                    )
                    db.add(ms)
                    triggered.append(
                        {
                            "employee_id": legacy_id,
                            "employee_name": person.name,
                            "milestone": f"{period}全勤之星",
                            "type": "perfect_attendance",
                        }
                    )

    await db.flush()

    # 企业微信批量通知
    if triggered:
        try:
            from src.services.wechat_service import WeChatService

            wechat = WeChatService()
            if wechat.is_configured():
                names = [t["employee_name"] for t in triggered[:5]]
                msg = f"### 里程碑庆祝\n" f"本次共{len(triggered)}位员工达成新里程碑：\n" + "\n".join(
                    f"- **{t['employee_name']}**: {t['milestone']}" for t in triggered[:5]
                )
                await wechat.send_markdown_message(content=msg, touser="@all")
        except Exception as e:
            logger.warning("milestone_wechat_failed", error=str(e))

    return triggered


async def compute_wellbeing_insights(db: AsyncSession, store_id: str) -> Dict[str, Any]:
    """
    全店幸福指数洞察：趋势、维度分析、关怀预警。
    """
    today = date.today()
    current_period = f"{today.year}-{today.month:02d}"

    # 最近3个月数据
    periods = []
    for i in range(2, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        periods.append(f"{y}-{m:02d}")

    trend = []
    for period in periods:
        result = await db.execute(
            select(
                func.count(EmployeeWellbeing.id).label("count"),
                func.avg(EmployeeWellbeing.overall_score).label("avg_score"),
                func.avg(EmployeeWellbeing.achievement_score).label("avg_achievement"),
                func.avg(EmployeeWellbeing.belonging_score).label("avg_belonging"),
                func.avg(EmployeeWellbeing.growth_score).label("avg_growth"),
                func.avg(EmployeeWellbeing.balance_score).label("avg_balance"),
                func.avg(EmployeeWellbeing.culture_score).label("avg_culture"),
            ).where(
                and_(
                    EmployeeWellbeing.store_id == store_id,
                    EmployeeWellbeing.period == period,
                )
            )
        )
        row = result.one()
        trend.append(
            {
                "period": period,
                "respondents": row.count or 0,
                "overall_score": float(row.avg_score or 0),
                "dimensions": {
                    "achievement": float(row.avg_achievement or 0),
                    "belonging": float(row.avg_belonging or 0),
                    "growth": float(row.avg_growth or 0),
                    "balance": float(row.avg_balance or 0),
                    "culture": float(row.avg_culture or 0),
                },
            }
        )

    # 找出需要关怀的员工（幸福指数<5分）
    concern_result = await db.execute(
        select(EmployeeWellbeing, Person.name)
        .join(Person, Person.legacy_employee_id == EmployeeWellbeing.employee_id)
        .where(
            and_(
                EmployeeWellbeing.store_id == store_id,
                EmployeeWellbeing.period == current_period,
                EmployeeWellbeing.overall_score < 5,
                EmployeeWellbeing.is_anonymous.is_(False),
            )
        )
    )
    concerns = [
        {
            "employee_name": row.name,
            "overall_score": float(row.EmployeeWellbeing.overall_score),
            "lowest_dimension": min(
                [
                    ("工作成就", row.EmployeeWellbeing.achievement_score),
                    ("团队归属", row.EmployeeWellbeing.belonging_score),
                    ("成长获得", row.EmployeeWellbeing.growth_score),
                    ("生活平衡", row.EmployeeWellbeing.balance_score),
                    ("文化认同", row.EmployeeWellbeing.culture_score),
                ],
                key=lambda x: x[1],
            )[0],
            "concerns": row.EmployeeWellbeing.concerns,
        }
        for row in concern_result.all()
    ]

    # 计算总体健康度
    latest = trend[-1] if trend else {}
    overall = latest.get("overall_score", 0)
    health_level = "excellent" if overall >= 8 else "good" if overall >= 6.5 else "attention" if overall >= 5 else "warning"

    return {
        "store_id": store_id,
        "health_level": health_level,
        "current_period": current_period,
        "overall_score": overall,
        "trend": trend,
        "needs_care_count": len(concerns),
        "needs_care": concerns[:10],
        "suggestions": _wellbeing_suggestions(latest.get("dimensions", {})),
    }


def _wellbeing_suggestions(dims: Dict[str, float]) -> List[str]:
    """根据各维度分数生成改善建议"""
    suggestions = []
    if dims.get("balance", 10) < 6:
        suggestions.append("生活平衡感偏低，建议优化排班避免连续长班，关注加班时长")
    if dims.get("growth", 10) < 6:
        suggestions.append("成长获得感不足，建议为员工制定个性化成长计划，增加培训机会")
    if dims.get("belonging", 10) < 6:
        suggestions.append("团队归属感待提升，建议组织团建活动，加强师徒制带教")
    if dims.get("culture", 10) < 6:
        suggestions.append("文化认同感偏低，建议加强品牌故事分享，让员工参与文化建设")
    if dims.get("achievement", 10) < 6:
        suggestions.append("工作成就感不足，建议设立更多即时认可机制，让优秀表现被看见")
    if not suggestions:
        suggestions.append("团队整体状态良好，继续保持关怀和认可")
    return suggestions


async def get_employee_journey(db: AsyncSession, employee_id: str) -> Dict[str, Any]:
    """
    获取员工全旅程视图：时间线 + 技能 + 里程碑 + 成长计划 + 幸福指数。
    """
    person_result = await db.execute(
        select(Person).where(Person.legacy_employee_id == str(employee_id))
    )
    person = person_result.scalar_one_or_none()
    if not person:
        return {"error": "员工不存在"}

    # 查当前岗位和入职日期（EmploymentAssignment）
    assign_result = await db.execute(
        select(EmploymentAssignment)
        .where(and_(EmploymentAssignment.person_id == person.id, EmploymentAssignment.status == "active"))
        .order_by(EmploymentAssignment.start_date.asc())
        .limit(1)
    )
    assignment = assign_result.scalar_one_or_none()
    position = assignment.position if assignment else None
    hire_date = assignment.start_date if assignment else None

    # 1. 变动时间线
    changes = await db.execute(
        select(EmployeeChange).where(EmployeeChange.employee_id == employee_id).order_by(EmployeeChange.effective_date.asc())
    )
    timeline = [
        {
            "date": str(c.effective_date),
            "type": c.change_type.value,
            "description": c.remark or c.change_type.value,
            "from_position": c.from_position,
            "to_position": c.to_position,
        }
        for c in changes.scalars().all()
    ]

    # 2. 里程碑
    milestones = await db.execute(
        select(EmployeeMilestone)
        .where(EmployeeMilestone.employee_id == employee_id)
        .order_by(EmployeeMilestone.achieved_at.desc())
    )
    milestone_list = [
        {
            "type": m.milestone_type.value,
            "title": m.title,
            "date": str(m.achieved_at),
            "badge_icon": m.badge_icon,
            "reward_yuan": (m.reward_fen or 0) / 100,
        }
        for m in milestones.scalars().all()
    ]

    # 3. 技能雷达
    skills = await db.execute(
        select(EmployeeSkill, SkillDefinition.skill_name, SkillDefinition.skill_category)
        .join(SkillDefinition, EmployeeSkill.skill_id == SkillDefinition.id)
        .where(EmployeeSkill.employee_id == employee_id)
    )
    skill_radar = [
        {
            "skill_name": row.skill_name,
            "category": row.skill_category,
            "level": (
                row.EmployeeSkill.current_level.value
                if hasattr(row.EmployeeSkill.current_level, "value")
                else str(row.EmployeeSkill.current_level)
            ),
            "score": row.EmployeeSkill.score,
            "level_numeric": LEVEL_NUMERIC.get(row.EmployeeSkill.current_level, 0),
        }
        for row in skills.all()
    ]

    # 4. 活跃成长计划
    plans = await db.execute(
        select(EmployeeGrowthPlan).where(
            and_(
                EmployeeGrowthPlan.employee_id == employee_id,
                EmployeeGrowthPlan.status == GrowthPlanStatus.ACTIVE,
            )
        )
    )
    growth_plans = [
        {
            "id": str(p.id),
            "plan_name": p.plan_name,
            "progress_pct": float(p.progress_pct or 0),
            "target_position": p.target_position,
            "total_tasks": p.total_tasks,
            "completed_tasks": p.completed_tasks,
            "mentor_name": p.mentor_name,
        }
        for p in plans.scalars().all()
    ]

    # 5. 最近幸福指数
    wb_result = await db.execute(
        select(EmployeeWellbeing)
        .where(EmployeeWellbeing.employee_id == employee_id)
        .order_by(EmployeeWellbeing.period.desc())
        .limit(3)
    )
    wellbeing_trend = [
        {
            "period": w.period,
            "overall": float(w.overall_score or 0),
            "achievement": w.achievement_score,
            "belonging": w.belonging_score,
            "growth": w.growth_score,
            "balance": w.balance_score,
            "culture": w.culture_score,
        }
        for w in wb_result.scalars().all()
    ]

    # 6. 计算在岗天数和价值贡献
    tenure_days = (date.today() - hire_date).days if hire_date else 0

    return {
        "employee": {
            "id": person.legacy_employee_id or str(person.id),
            "name": person.name,
            "position": position,
            "hire_date": str(hire_date) if hire_date else None,
            "employment_status": person.career_stage or "regular",
            "tenure_days": tenure_days,
            "is_active": person.is_active,
        },
        "timeline": timeline,
        "milestones": milestone_list,
        "skill_radar": skill_radar,
        "growth_plans": growth_plans,
        "wellbeing_trend": wellbeing_trend,
    }
