"""OnboardingService — 入职全流程服务

WF流程：
draft → (generate_checklist) → pending_review → (approve) → active → (实际入职完成)
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.onboarding_process import OnboardingProcess
from ...models.hr.onboarding_checklist_item import OnboardingChecklistItem
from ...models.hr.employment_assignment import EmploymentAssignment

logger = structlog.get_logger()

# 按岗位类别的标准清单模板（岗位前缀 → 清单类型列表）
_CHECKLIST_TEMPLATES: dict[str, list[dict]] = {
    "manager": [
        {"item_type": "document", "title": "签署劳动合同", "sort_order": 1},
        {"item_type": "document", "title": "提交个人证件复印件", "sort_order": 2},
        {"item_type": "system_setup", "title": "配置ERP/POS系统账号", "sort_order": 3},
        {"item_type": "training", "title": "完成管理岗位培训", "sort_order": 4},
        {"item_type": "equipment", "title": "领取办公设备", "sort_order": 5},
        {"item_type": "contract_sign", "title": "签署保密协议", "sort_order": 6},
    ],
    "chef": [
        {"item_type": "document", "title": "签署劳动合同", "sort_order": 1},
        {"item_type": "document", "title": "提交健康证", "sort_order": 2},
        {"item_type": "training", "title": "完成食品安全培训", "sort_order": 3},
        {"item_type": "equipment", "title": "领取厨师服装", "sort_order": 4},
        {"item_type": "system_setup", "title": "录入考勤系统", "sort_order": 5},
    ],
    "server": [  # 服务员/楼面
        {"item_type": "document", "title": "签署劳动合同", "sort_order": 1},
        {"item_type": "document", "title": "提交个人证件复印件", "sort_order": 2},
        {"item_type": "training", "title": "完成服务标准培训", "sort_order": 3},
        {"item_type": "equipment", "title": "领取工服", "sort_order": 4},
        {"item_type": "system_setup", "title": "录入考勤系统", "sort_order": 5},
    ],
    "default": [
        {"item_type": "document", "title": "签署劳动合同", "sort_order": 1},
        {"item_type": "document", "title": "提交个人证件复印件", "sort_order": 2},
        {"item_type": "system_setup", "title": "录入考勤系统", "sort_order": 3},
        {"item_type": "training", "title": "完成岗位培训", "sort_order": 4},
    ],
}


def _get_checklist_template(job_title: str) -> list[dict]:
    """根据岗位标题匹配清单模板（模糊匹配前缀）"""
    job_title_lower = job_title.lower()
    if any(k in job_title_lower for k in ["manager", "店长", "经理", "主管", "mgr"]):
        return _CHECKLIST_TEMPLATES["manager"]
    if any(k in job_title_lower for k in ["chef", "厨师", "厨长", "cook", "烹饪"]):
        return _CHECKLIST_TEMPLATES["chef"]
    if any(k in job_title_lower for k in ["server", "服务", "楼面", "waiter", "waitress"]):
        return _CHECKLIST_TEMPLATES["server"]
    return _CHECKLIST_TEMPLATES["default"]


class OnboardingService:

    async def create_process(
        self,
        person_id: uuid.UUID,
        org_node_id: str,
        planned_start_date: date,
        created_by: str,
        session: AsyncSession,
        offer_date: Optional[date] = None,
        extra_data: Optional[dict] = None,
    ) -> OnboardingProcess:
        """创建入职流程（draft状态）"""
        process = OnboardingProcess(
            person_id=person_id,
            org_node_id=org_node_id,
            planned_start_date=planned_start_date,
            created_by=created_by,
            offer_date=offer_date,
            extra_data=extra_data or {},
            status="draft",
        )
        session.add(process)
        await session.flush()
        logger.info("onboarding.create", process_id=str(process.id), person_id=str(person_id))
        return process

    async def generate_checklist(
        self,
        process_id: uuid.UUID,
        job_title: str,
        session: AsyncSession,
    ) -> list[OnboardingChecklistItem]:
        """根据岗位生成标准清单，推进状态到 pending_review"""
        template = _get_checklist_template(job_title)
        items = []
        for t in template:
            item = OnboardingChecklistItem(
                process_id=process_id,
                item_type=t["item_type"],
                title=t["title"],
                sort_order=t["sort_order"],
                required=True,
            )
            session.add(item)
            items.append(item)

        # 状态推进：draft → pending_review
        await session.execute(
            update(OnboardingProcess)
            .where(OnboardingProcess.id == process_id)
            .values(status="pending_review", updated_at=datetime.now(timezone.utc))
        )
        await session.flush()
        logger.info("onboarding.checklist_generated", process_id=str(process_id), item_count=len(items))
        return items

    async def complete_item(
        self,
        item_id: uuid.UUID,
        completed_by: str,
        session: AsyncSession,
        file_url: Optional[str] = None,
    ) -> OnboardingChecklistItem:
        """标记清单项完成"""
        result = await session.execute(
            select(OnboardingChecklistItem).where(OnboardingChecklistItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"ChecklistItem {item_id} not found")
        item.completed_at = datetime.now(timezone.utc)
        item.completed_by = completed_by
        item.file_url = file_url
        await session.flush()
        return item

    async def approve(
        self,
        process_id: uuid.UUID,
        approved_by: str,
        employment_type: str,
        session: AsyncSession,
    ) -> EmploymentAssignment:
        """审批通过：创建 EmploymentAssignment，状态推进到 active"""
        result = await session.execute(
            select(OnboardingProcess).where(OnboardingProcess.id == process_id)
        )
        process = result.scalar_one_or_none()
        if process is None:
            raise ValueError(f"OnboardingProcess {process_id} not found")
        if process.status not in ("pending_review", "draft"):
            raise ValueError(f"Cannot approve process in status {process.status!r}")

        # 创建在岗关系
        assignment = EmploymentAssignment(
            person_id=process.person_id,
            org_node_id=process.org_node_id,
            employment_type=employment_type,
            start_date=process.planned_start_date,
            status="active",
            onboarding_process_id=process_id,
        )
        session.add(assignment)

        # 更新入职流程状态
        await session.execute(
            update(OnboardingProcess)
            .where(OnboardingProcess.id == process_id)
            .values(
                status="active",
                actual_start_date=process.planned_start_date,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
        logger.info(
            "onboarding.approved",
            process_id=str(process_id),
            assignment_id=str(assignment.id),
            approved_by=approved_by,
        )
        return assignment

    async def _generate_ai_growth_plan(
        self,
        person_id: uuid.UUID,
        job_title: str,
        session: AsyncSession,
    ) -> dict:
        """生成AI成长计划（占位实现，WF-6实现后替换）"""
        return {
            "job_title": job_title,
            "recommended_skills": [],
            "estimated_growth_months": 6,
            "note": "AI成长计划生成功能待WF-6实现",
        }
