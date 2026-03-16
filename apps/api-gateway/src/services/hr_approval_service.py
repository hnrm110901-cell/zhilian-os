"""
HR Approval Service — 人事审批引擎
支持请假、加班、调岗等HR审批流程
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.approval_flow import (
    ApprovalFlowTemplate,
    ApprovalInstance,
    ApprovalNodeRecord,
    ApprovalNodeType,
    ApprovalStatus,
    ApprovalType,
)
from src.services.base_service import BaseService

logger = structlog.get_logger()


class HRApprovalService(BaseService):
    """人事审批引擎"""

    async def create_instance(
        self,
        db: AsyncSession,
        approval_type: str,
        applicant_id: str,
        applicant_name: str,
        business_type: str,
        business_id: str,
        title: str,
        summary: str = "",
        business_data: Dict = None,
        store_id: str = None,
    ) -> ApprovalInstance:
        """发起审批"""
        sid = store_id or self.store_id

        template = await self._find_template(db, approval_type, sid)
        nodes = (
            template.nodes if template else [{"step": 1, "node_type": "single", "role": "store_manager", "label": "店长审批"}]
        )

        instance = ApprovalInstance(
            store_id=sid,
            template_id=template.id if template else None,
            approval_type=approval_type,
            status=ApprovalStatus.PENDING,
            applicant_id=applicant_id,
            applicant_name=applicant_name,
            business_type=business_type,
            business_id=business_id,
            title=title,
            summary=summary,
            business_data=business_data,
            current_step=1,
            total_steps=len(nodes),
        )
        db.add(instance)
        await db.flush()
        logger.info("hr_approval_created", instance_id=str(instance.id), type=approval_type)
        return instance

    async def approve(
        self,
        db: AsyncSession,
        instance_id: str,
        approver_id: str,
        approver_name: str = "",
        comment: str = "",
    ) -> ApprovalInstance:
        """审批通过"""
        instance = await db.get(ApprovalInstance, instance_id)
        if not instance:
            raise ValueError(f"审批实例 {instance_id} 不存在")
        if instance.status != ApprovalStatus.PENDING:
            raise ValueError(f"审批状态为 {instance.status}，不可审批")

        node = ApprovalNodeRecord(
            instance_id=instance.id,
            step=instance.current_step,
            node_type=ApprovalNodeType.SINGLE,
            approver_id=approver_id,
            approver_name=approver_name,
            action="approved",
            comment=comment,
            acted_at=datetime.utcnow(),
        )
        db.add(node)

        if instance.current_step >= instance.total_steps:
            instance.status = ApprovalStatus.APPROVED
            instance.final_approver_id = approver_id
            instance.final_approver_name = approver_name
            instance.approved_at = datetime.utcnow()
        else:
            instance.current_step += 1

        await db.flush()
        return instance

    async def reject(
        self,
        db: AsyncSession,
        instance_id: str,
        approver_id: str,
        approver_name: str = "",
        reason: str = "",
    ) -> ApprovalInstance:
        """审批驳回"""
        instance = await db.get(ApprovalInstance, instance_id)
        if not instance:
            raise ValueError(f"审批实例 {instance_id} 不存在")
        if instance.status != ApprovalStatus.PENDING:
            raise ValueError(f"审批状态为 {instance.status}，不可驳回")

        node = ApprovalNodeRecord(
            instance_id=instance.id,
            step=instance.current_step,
            node_type=ApprovalNodeType.SINGLE,
            approver_id=approver_id,
            approver_name=approver_name,
            action="rejected",
            comment=reason,
            acted_at=datetime.utcnow(),
        )
        db.add(node)

        instance.status = ApprovalStatus.REJECTED
        instance.final_approver_id = approver_id
        instance.rejection_reason = reason
        instance.rejected_at = datetime.utcnow()

        await db.flush()
        return instance

    async def withdraw(self, db: AsyncSession, instance_id: str, applicant_id: str) -> ApprovalInstance:
        """撤回审批"""
        instance = await db.get(ApprovalInstance, instance_id)
        if not instance:
            raise ValueError("审批实例不存在")
        if instance.applicant_id != applicant_id:
            raise ValueError("只有申请人可以撤回")
        if instance.status != ApprovalStatus.PENDING:
            raise ValueError("当前状态不可撤回")

        instance.status = ApprovalStatus.WITHDRAWN
        await db.flush()
        return instance

    async def get_pending_list(self, db: AsyncSession, store_id: str = None) -> List[Dict[str, Any]]:
        """获取待审批列表"""
        sid = store_id or self.store_id
        result = await db.execute(
            select(ApprovalInstance)
            .where(
                and_(
                    ApprovalInstance.status == ApprovalStatus.PENDING,
                    ApprovalInstance.store_id == sid,
                )
            )
            .order_by(ApprovalInstance.created_at.desc())
        )
        return [
            {
                "id": str(inst.id),
                "type": inst.approval_type.value if inst.approval_type else "",
                "title": inst.title,
                "summary": inst.summary,
                "applicant_id": inst.applicant_id,
                "applicant_name": inst.applicant_name,
                "current_step": inst.current_step,
                "total_steps": inst.total_steps,
                "created_at": inst.created_at.isoformat() if inst.created_at else None,
            }
            for inst in result.scalars().all()
        ]

    async def get_my_approvals(self, db: AsyncSession, applicant_id: str, status: str = None) -> List[Dict[str, Any]]:
        """获取我发起的审批"""
        conditions = [ApprovalInstance.applicant_id == applicant_id]
        if status:
            conditions.append(ApprovalInstance.status == status)

        result = await db.execute(
            select(ApprovalInstance).where(and_(*conditions)).order_by(ApprovalInstance.created_at.desc()).limit(50)
        )
        return [
            {
                "id": str(inst.id),
                "type": inst.approval_type.value if inst.approval_type else "",
                "title": inst.title,
                "status": inst.status.value if inst.status else "",
                "created_at": inst.created_at.isoformat() if inst.created_at else None,
                "approved_at": inst.approved_at.isoformat() if inst.approved_at else None,
            }
            for inst in result.scalars().all()
        ]

    async def _find_template(self, db: AsyncSession, approval_type: str, store_id: str) -> Optional[ApprovalFlowTemplate]:
        """查找审批模板（门店级 > 全局）"""
        result = await db.execute(
            select(ApprovalFlowTemplate)
            .where(
                and_(
                    ApprovalFlowTemplate.approval_type == approval_type,
                    ApprovalFlowTemplate.is_active.is_(True),
                )
            )
            .order_by(ApprovalFlowTemplate.priority.desc())
        )
        templates = result.scalars().all()
        for t in templates:
            if t.store_id == store_id:
                return t
        for t in templates:
            if t.store_id is None:
                return t
        return None
