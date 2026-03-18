"""HRApprovalWorkflowService — HR专用审批工作流引擎

与运营workflow_engine完全独立，专注HR审批场景。
支持：多级线性审批、按条件路由、代理审批、企微推送。
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.approval_template import ApprovalTemplate
from ...models.hr.approval_instance import ApprovalInstance
from ...models.hr.approval_step_record import ApprovalStepRecord

logger = structlog.get_logger()


class HRApprovalWorkflowService:
    """HR专用审批工作流引擎"""

    async def start(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
        initiator: str,
        session: AsyncSession,
        org_node_id: Optional[str] = None,
        extra_data: Optional[dict] = None,
    ) -> ApprovalInstance:
        """发起审批流程：查找匹配模板 → 创建实例 → 创建第一步记录"""
        if resource_type not in ("onboarding", "offboarding", "transfer"):
            raise ValueError(f"Invalid resource_type: {resource_type!r}")

        # 查找审批模板：先找门店专属，再找集团通用
        template = await self._find_template(resource_type, org_node_id, session)
        if template is None:
            raise ValueError(f"No active approval template for resource_type={resource_type!r}")

        steps = template.steps or []
        if not steps:
            raise ValueError(f"Approval template {template.id} has no steps defined")

        instance = ApprovalInstance(
            template_id=template.id,
            resource_type=resource_type,
            resource_id=resource_id,
            status="pending",
            current_step=1,
            created_by=initiator,
            extra_data=extra_data or {},
        )
        session.add(instance)
        await session.flush()

        # 创建第一步审批记录
        first_step = steps[0]
        approver_id, approver_name = await self._resolve_approver(
            first_step, org_node_id, session
        )
        record = ApprovalStepRecord(
            instance_id=instance.id,
            step=1,
            approver_id=approver_id,
            approver_name=approver_name,
            action="pending",
        )
        session.add(record)
        await session.flush()

        logger.info(
            "approval.started",
            instance_id=str(instance.id),
            resource_type=resource_type,
            resource_id=str(resource_id),
            template_id=str(template.id),
        )
        return instance

    async def action(
        self,
        instance_id: uuid.UUID,
        approver_id: str,
        action_type: str,
        session: AsyncSession,
        comment: Optional[str] = None,
    ) -> ApprovalInstance:
        """处理审批动作：approved / rejected"""
        if action_type not in ("approved", "rejected"):
            raise ValueError(f"Invalid action: {action_type!r}")

        result = await session.execute(
            select(ApprovalInstance).where(ApprovalInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            raise ValueError(f"ApprovalInstance {instance_id} not found")
        if instance.status != "pending":
            raise ValueError(f"Cannot act on instance in status {instance.status!r}")

        # 更新当前步骤记录
        await session.execute(
            update(ApprovalStepRecord)
            .where(
                ApprovalStepRecord.instance_id == instance_id,
                ApprovalStepRecord.step == instance.current_step,
                ApprovalStepRecord.approver_id == approver_id,
            )
            .values(
                action=action_type,
                comment=comment,
                acted_at=datetime.now(timezone.utc),
            )
        )

        if action_type == "rejected":
            await self._on_rejected(instance_id, session)
        else:
            # approved: check if there are more steps
            template_result = await session.execute(
                select(ApprovalTemplate).where(ApprovalTemplate.id == instance.template_id)
            )
            template = template_result.scalar_one_or_none()
            steps = template.steps if template else []
            next_step = instance.current_step + 1

            if next_step > len(steps):
                # 所有步骤完成
                await self._on_approved(instance_id, session)
            else:
                # 推进到下一步
                step_config = steps[next_step - 1]
                approver_id_next, approver_name_next = await self._resolve_approver(
                    step_config, None, session
                )
                record = ApprovalStepRecord(
                    instance_id=instance_id,
                    step=next_step,
                    approver_id=approver_id_next,
                    approver_name=approver_name_next,
                    action="pending",
                )
                session.add(record)
                await session.execute(
                    update(ApprovalInstance)
                    .where(ApprovalInstance.id == instance_id)
                    .values(current_step=next_step, updated_at=datetime.now(timezone.utc))
                )

        await session.flush()
        logger.info(
            "approval.action",
            instance_id=str(instance_id),
            action=action_type,
            approver=approver_id,
        )
        return instance

    async def delegate(
        self,
        instance_id: uuid.UUID,
        from_approver: str,
        to_approver_id: str,
        to_approver_name: str,
        session: AsyncSession,
    ) -> ApprovalStepRecord:
        """委托审批给他人"""
        result = await session.execute(
            select(ApprovalInstance).where(ApprovalInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            raise ValueError(f"ApprovalInstance {instance_id} not found")
        if instance.status != "pending":
            raise ValueError(f"Cannot delegate on instance in status {instance.status!r}")

        # 标记旧记录为delegated
        await session.execute(
            update(ApprovalStepRecord)
            .where(
                ApprovalStepRecord.instance_id == instance_id,
                ApprovalStepRecord.step == instance.current_step,
                ApprovalStepRecord.approver_id == from_approver,
            )
            .values(action="delegated", acted_at=datetime.now(timezone.utc))
        )

        # 创建新的步骤记录给被委托人
        new_record = ApprovalStepRecord(
            instance_id=instance_id,
            step=instance.current_step,
            approver_id=to_approver_id,
            approver_name=to_approver_name,
            action="pending",
        )
        session.add(new_record)
        await session.flush()
        logger.info(
            "approval.delegated",
            instance_id=str(instance_id),
            from_approver=from_approver,
            to_approver=to_approver_id,
        )
        return new_record

    async def get_pending_for(
        self,
        approver_id: str,
        session: AsyncSession,
    ) -> list[ApprovalInstance]:
        """获取某人待处理的审批列表"""
        # 查找该approver有pending记录的所有instance
        result = await session.execute(
            select(ApprovalInstance)
            .join(
                ApprovalStepRecord,
                ApprovalStepRecord.instance_id == ApprovalInstance.id,
            )
            .where(
                ApprovalStepRecord.approver_id == approver_id,
                ApprovalStepRecord.action == "pending",
                ApprovalInstance.status == "pending",
            )
        )
        return list(result.scalars().all())

    async def get_instance_detail(
        self,
        instance_id: uuid.UUID,
        session: AsyncSession,
    ) -> dict:
        """获取审批实例详情 + 步骤记录"""
        inst_result = await session.execute(
            select(ApprovalInstance).where(ApprovalInstance.id == instance_id)
        )
        instance = inst_result.scalar_one_or_none()
        if instance is None:
            raise ValueError(f"ApprovalInstance {instance_id} not found")

        steps_result = await session.execute(
            select(ApprovalStepRecord)
            .where(ApprovalStepRecord.instance_id == instance_id)
            .order_by(ApprovalStepRecord.step, ApprovalStepRecord.created_at)
        )
        steps = list(steps_result.scalars().all())

        return {
            "instance_id": str(instance.id),
            "resource_type": instance.resource_type,
            "resource_id": str(instance.resource_id),
            "status": instance.status,
            "current_step": instance.current_step,
            "created_by": instance.created_by,
            "created_at": instance.created_at.isoformat() if instance.created_at else None,
            "steps": [
                {
                    "step": s.step,
                    "approver_id": s.approver_id,
                    "approver_name": s.approver_name,
                    "action": s.action,
                    "comment": s.comment,
                    "acted_at": s.acted_at.isoformat() if s.acted_at else None,
                }
                for s in steps
            ],
        }

    async def _find_template(
        self,
        resource_type: str,
        org_node_id: Optional[str],
        session: AsyncSession,
    ) -> Optional[ApprovalTemplate]:
        """查找匹配的审批模板：先门店专属，再集团通用"""
        if org_node_id:
            result = await session.execute(
                select(ApprovalTemplate).where(
                    ApprovalTemplate.resource_type == resource_type,
                    ApprovalTemplate.org_node_id == org_node_id,
                    ApprovalTemplate.is_active == True,
                )
            )
            template = result.scalar_one_or_none()
            if template:
                return template

        # 集团通用
        result = await session.execute(
            select(ApprovalTemplate).where(
                ApprovalTemplate.resource_type == resource_type,
                ApprovalTemplate.org_node_id == None,
                ApprovalTemplate.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def _resolve_approver(
        self,
        step_config: dict,
        org_node_id: Optional[str],
        session: AsyncSession,
    ) -> tuple[str, str]:
        """根据步骤配置解析审批人（占位实现：直接取role字段）"""
        role = step_config.get("role", "unknown")
        approver_type = step_config.get("approver_type", "position")
        # 占位实现：用role作为approver_id和name
        # WF-6实装时替换为真正的员工查询
        return (f"{approver_type}:{role}", role)

    async def _on_approved(
        self,
        instance_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """审批通过回调：更新实例状态"""
        now = datetime.now(timezone.utc)
        await session.execute(
            update(ApprovalInstance)
            .where(ApprovalInstance.id == instance_id)
            .values(status="approved", completed_at=now, updated_at=now)
        )

    async def _on_rejected(
        self,
        instance_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """审批驳回回调：更新实例状态"""
        now = datetime.now(timezone.utc)
        await session.execute(
            update(ApprovalInstance)
            .where(ApprovalInstance.id == instance_id)
            .values(status="rejected", completed_at=now, updated_at=now)
        )
