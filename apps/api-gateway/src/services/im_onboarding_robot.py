"""
IM 入职引导机器人 — 新员工入职后自动推送入职任务清单

核心功能：
1. 新员工通过 IM 同步创建后，自动推送入职欢迎 + 任务清单
2. 根据岗位（waiter/chef/manager...）推送差异化任务
3. 创建 EmployeeMilestone(ONBOARD) + EmployeeGrowthPlan
4. 支持定时提醒未完成入职任务的新员工

设计原则：
- 复用 IMMessageService 发送消息，平台无关
- 复用 EmployeeGrowthPlan 追踪入职任务进度
- 复用 EmployeeMilestone 记录入职里程碑
"""
from typing import Any, Dict, List, Optional
from datetime import date, timedelta
import uuid

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.employee import Employee
from ..models.store import Store
from ..models.employee_growth import (
    EmployeeMilestone, MilestoneType,
    EmployeeGrowthPlan, GrowthPlanStatus,
)
from ..services.im_message_service import IMMessageService

logger = structlog.get_logger()

# 岗位 → 入职任务清单
ONBOARDING_TASKS_BY_POSITION = {
    "waiter": [
        {"task": "完成食品安全培训（线上）", "type": "training", "days": 3},
        {"task": "熟悉门店布局与动线", "type": "orientation", "days": 1},
        {"task": "学习点餐系统操作", "type": "training", "days": 2},
        {"task": "服务礼仪与话术培训", "type": "training", "days": 3},
        {"task": "跟师傅学习3天（师徒制）", "type": "mentor", "days": 5},
        {"task": "独立完成首次服务接待", "type": "skill_up", "days": 7},
    ],
    "chef": [
        {"task": "完成食品安全培训（线上）", "type": "training", "days": 3},
        {"task": "熟悉后厨动线与设备", "type": "orientation", "days": 1},
        {"task": "学习菜品标准化出品流程", "type": "training", "days": 3},
        {"task": "食材验收与库存管理培训", "type": "training", "days": 3},
        {"task": "跟师傅学习5天（师徒制）", "type": "mentor", "days": 7},
        {"task": "独立完成首次备菜出品", "type": "skill_up", "days": 10},
    ],
    "store_manager": [
        {"task": "完成食品安全培训（线上）", "type": "training", "days": 3},
        {"task": "熟悉屯象OS系统功能", "type": "training", "days": 2},
        {"task": "了解门店KPI指标体系", "type": "training", "days": 3},
        {"task": "排班与人力管理培训", "type": "training", "days": 3},
        {"task": "损耗管控与成本分析培训", "type": "training", "days": 5},
        {"task": "完成首周门店日报审核", "type": "skill_up", "days": 7},
    ],
    "cashier": [
        {"task": "完成食品安全培训（线上）", "type": "training", "days": 3},
        {"task": "收银系统操作培训", "type": "training", "days": 2},
        {"task": "支付方式与票据管理", "type": "training", "days": 2},
        {"task": "客诉处理流程培训", "type": "training", "days": 3},
        {"task": "独立完成首次值班收银", "type": "skill_up", "days": 5},
    ],
}

# 通用任务（所有岗位都需要）
COMMON_TASKS = [
    {"task": "完善个人信息（系统内）", "type": "admin", "days": 1},
    {"task": "阅读员工手册", "type": "orientation", "days": 2},
    {"task": "了解企业文化与价值观", "type": "orientation", "days": 3},
]


class IMOnboardingRobot:
    """IM 入职引导机器人"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.msg_service = IMMessageService(db)

    async def trigger_onboarding(
        self,
        employee_id: str,
        brand_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        触发新员工入职引导流程：
        1. 查询员工信息
        2. 创建入职里程碑
        3. 创建入职成长计划（含任务清单）
        4. 推送 IM 欢迎消息 + 任务清单
        """
        # 查询员工
        emp_result = await self.db.execute(
            select(Employee).where(Employee.id == employee_id)
        )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            return {"error": f"员工 {employee_id} 不存在"}

        # 查门店名称
        store_result = await self.db.execute(
            select(Store).where(Store.id == employee.store_id)
        )
        store = store_result.scalar_one_or_none()
        store_name = store.name if store else employee.store_id

        # 获取品牌ID
        if not brand_id and store:
            brand_id = store.brand_id

        # 1. 创建入职里程碑
        milestone = await self._create_onboard_milestone(employee, store_name)

        # 2. 创建入职成长计划
        plan = await self._create_onboarding_plan(employee)

        await self.db.flush()

        # 3. 推送 IM 消息
        im_userid = employee.wechat_userid or employee.dingtalk_userid
        send_result = {"sent": False}
        if im_userid:
            send_result = await self._push_onboarding_message(
                brand_id, im_userid, employee.name, store_name,
                employee.position, plan,
            )

        await self.db.commit()

        logger.info(
            "onboarding_robot.triggered",
            employee_id=employee_id,
            store_id=employee.store_id,
            position=employee.position,
            task_count=plan.total_tasks if plan else 0,
            im_sent=send_result.get("sent", False),
        )

        return {
            "employee_id": employee_id,
            "employee_name": employee.name,
            "store_name": store_name,
            "milestone_id": str(milestone.id) if milestone else None,
            "plan_id": str(plan.id) if plan else None,
            "total_tasks": plan.total_tasks if plan else 0,
            "im_sent": send_result.get("sent", False),
        }

    async def _create_onboard_milestone(
        self, employee: Employee, store_name: str,
    ) -> EmployeeMilestone:
        """创建入职里程碑"""
        milestone = EmployeeMilestone(
            id=uuid.uuid4(),
            store_id=employee.store_id,
            employee_id=employee.id,
            milestone_type=MilestoneType.ONBOARD,
            title=f"欢迎加入{store_name}",
            description=f"{employee.name} 入职 {employee.position or '岗位'}",
            achieved_at=date.today(),
            badge_icon="🎉",
            notified=True,
        )
        self.db.add(milestone)
        return milestone

    async def _create_onboarding_plan(
        self, employee: Employee,
    ) -> EmployeeGrowthPlan:
        """创建入职成长计划（含结构化任务清单）"""
        position = employee.position or "waiter"
        position_tasks = ONBOARDING_TASKS_BY_POSITION.get(position, [])
        if not position_tasks:
            # 未匹配到岗位时用服务员任务
            position_tasks = ONBOARDING_TASKS_BY_POSITION["waiter"]

        all_tasks = []
        today = date.today()

        # 通用任务
        for t in COMMON_TASKS:
            all_tasks.append({
                "task": t["task"],
                "type": t["type"],
                "due_date": (today + timedelta(days=t["days"])).isoformat(),
                "done": False,
            })

        # 岗位专属任务
        for t in position_tasks:
            all_tasks.append({
                "task": t["task"],
                "type": t["type"],
                "due_date": (today + timedelta(days=t["days"])).isoformat(),
                "done": False,
            })

        plan = EmployeeGrowthPlan(
            id=uuid.uuid4(),
            store_id=employee.store_id,
            employee_id=employee.id,
            plan_name=f"入职引导计划（{employee.name}）",
            status=GrowthPlanStatus.ACTIVE,
            tasks=all_tasks,
            total_tasks=len(all_tasks),
            completed_tasks=0,
            progress_pct=0,
            ai_generated=True,
            ai_reasoning="IM通讯录同步自动创建，基于岗位匹配的标准化入职引导",
            started_at=today,
            target_date=today + timedelta(days=14),
        )
        self.db.add(plan)
        return plan

    async def _push_onboarding_message(
        self,
        brand_id: Optional[str],
        im_userid: str,
        employee_name: str,
        store_name: str,
        position: Optional[str],
        plan: EmployeeGrowthPlan,
    ) -> Dict[str, Any]:
        """推送入职欢迎消息 + 任务清单"""
        position_label = self._position_label(position)
        tasks = plan.tasks or []

        # 构建任务清单 Markdown
        task_lines = []
        for i, t in enumerate(tasks[:8], 1):
            due = t.get("due_date", "")
            task_lines.append(f"  {i}. {t['task']}（截止 {due}）")
        if len(tasks) > 8:
            task_lines.append(f"  ... 共 {len(tasks)} 项")

        content = (
            f"### 🎉 欢迎加入 {store_name}！\n\n"
            f"**{employee_name}** 您好，恭喜您成为 **{position_label}** 的一员！\n\n"
            f"您的屯象OS系统账号已自动创建，以下是您的入职任务清单：\n\n"
            + "\n".join(task_lines) + "\n\n"
            f"请在 **14天内** 完成以上任务。\n"
            f"如有疑问，请联系您的店长或导师。\n\n"
            f"💡 回复「个人信息」查看账号 | 回复「排班」查看班次"
        )

        try:
            result = await self.msg_service.send_markdown(
                brand_id, im_userid, "入职引导", content,
            )
            return {"sent": True, **result}
        except Exception as e:
            logger.warning("onboarding_robot.send_failed", error=str(e))
            return {"sent": False, "error": str(e)}

    async def remind_incomplete_onboarding(
        self,
        brand_id: Optional[str] = None,
        days_threshold: int = 7,
    ) -> Dict[str, Any]:
        """
        提醒入职超过 N 天但任务未完成的新员工。
        由 Celery Beat 定时调用。
        """
        cutoff = date.today() - timedelta(days=days_threshold)
        result = await self.db.execute(
            select(EmployeeGrowthPlan).where(
                and_(
                    EmployeeGrowthPlan.plan_name.like("入职引导计划%"),
                    EmployeeGrowthPlan.status == GrowthPlanStatus.ACTIVE,
                    EmployeeGrowthPlan.started_at <= cutoff,
                    EmployeeGrowthPlan.progress_pct < 100,
                )
            )
        )
        plans = result.scalars().all()
        reminded = 0

        for plan in plans:
            emp_result = await self.db.execute(
                select(Employee).where(
                    and_(Employee.id == plan.employee_id, Employee.is_active.is_(True))
                )
            )
            emp = emp_result.scalar_one_or_none()
            if not emp:
                continue

            im_userid = emp.wechat_userid or emp.dingtalk_userid
            if not im_userid:
                continue

            # 获取品牌ID
            store_result = await self.db.execute(
                select(Store.brand_id).where(Store.id == emp.store_id)
            )
            store_brand = store_result.scalar_one_or_none()
            emp_brand_id = brand_id or store_brand

            pending = plan.total_tasks - plan.completed_tasks
            content = (
                f"### 入职任务提醒\n\n"
                f"**{emp.name}** 您好，您还有 **{pending}项** 入职任务待完成。\n\n"
                f"入职已满 {days_threshold} 天，请尽快完成剩余任务：\n\n"
            )
            tasks = plan.tasks or []
            for t in tasks:
                if not t.get("done"):
                    content += f"- ⬜ {t['task']}\n"

            content += f"\n如已完成，请联系店长更新状态。"

            try:
                await self.msg_service.send_markdown(
                    emp_brand_id, im_userid, "入职任务提醒", content,
                )
                reminded += 1
            except Exception as e:
                logger.warning("onboarding_remind.failed",
                               employee_id=emp.id, error=str(e))

        return {"reminded": reminded, "total_pending": len(plans)}

    @staticmethod
    def _position_label(position: Optional[str]) -> str:
        """岗位代码 → 中文标签"""
        labels = {
            "waiter": "服务员",
            "chef": "厨师",
            "head_chef": "厨师长",
            "store_manager": "店长",
            "assistant_manager": "副店长",
            "floor_manager": "楼面经理",
            "team_leader": "领班",
            "cashier": "收银员",
            "station_manager": "档口主管",
            "warehouse_manager": "库管",
            "finance": "财务",
            "procurement": "采购",
            "customer_manager": "客户经理",
        }
        return labels.get(position or "", position or "团队成员")
