"""TransferService — 调岗/晋升/外派流程服务

WF流程：
pending → (approve) → approved → (execute) → active（新在岗关系创建，旧关系关闭）
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.transfer_process import TransferProcess
from ...models.hr.employment_assignment import EmploymentAssignment

logger = structlog.get_logger()

# 基准月薪占位值（元）— WF-6 实装前使用固定值
_STUB_BASE_MONTHLY_YUAN = 5000.0

# 晋升/调岗的预期¥影响系数（相对当前岗位月薪的比例）
_REVENUE_IMPACT_RATIO: dict[str, float] = {
    "promotion": 0.20,     # 晋升：+20% 预期产能提升
    "demotion": -0.15,     # 降职：-15% 预期产能降低
    "internal_transfer": 0.05,  # 平调：+5%（熟悉新岗位后轻微提升）
    "secondment": 0.0,     # 外派：影响中性
}


class TransferService:

    async def apply(
        self,
        person_id: uuid.UUID,
        from_assignment_id: uuid.UUID,
        to_org_node_id: str,
        transfer_type: str,
        effective_date: date,
        reason: str,
        created_by: str,
        to_employment_type: str,
        session: AsyncSession,
        new_pay_scheme: Optional[dict] = None,
    ) -> TransferProcess:
        """提交调岗申请"""
        if transfer_type not in ("internal_transfer", "promotion", "demotion", "secondment"):
            raise ValueError(f"Invalid transfer_type: {transfer_type!r}")

        # AI预测¥影响
        revenue_impact = await self._predict_revenue_impact(person_id, to_org_node_id, transfer_type, session)

        process = TransferProcess(
            person_id=person_id,
            from_assignment_id=from_assignment_id,
            to_org_node_id=to_org_node_id,
            to_employment_type=to_employment_type,
            transfer_type=transfer_type,
            effective_date=effective_date,
            reason=reason,
            created_by=created_by,
            new_pay_scheme=new_pay_scheme or {},
            status="pending",
            revenue_impact_yuan=Decimal(str(revenue_impact)),
        )
        session.add(process)
        await session.flush()
        logger.info(
            "transfer.applied",
            process_id=str(process.id),
            person_id=str(person_id),
            transfer_type=transfer_type,
        )
        return process

    async def approve(
        self,
        process_id: uuid.UUID,
        approved_by: str,
        session: AsyncSession,
    ) -> TransferProcess:
        """审批通过调岗申请"""
        result = await session.execute(
            select(TransferProcess).where(TransferProcess.id == process_id)
        )
        process = result.scalar_one_or_none()
        if process is None:
            raise ValueError(f"TransferProcess {process_id} not found")
        if process.status != "pending":
            raise ValueError(f"Cannot approve transfer in status {process.status!r}")

        await session.execute(
            update(TransferProcess)
            .where(TransferProcess.id == process_id)
            .values(status="approved", updated_at=datetime.now(timezone.utc))
        )
        await session.flush()
        logger.info("transfer.approved", process_id=str(process_id), approved_by=approved_by)
        return process

    async def execute(
        self,
        process_id: uuid.UUID,
        session: AsyncSession,
    ) -> EmploymentAssignment:
        """执行调岗：创建新在岗关系，关闭旧在岗关系"""
        result = await session.execute(
            select(TransferProcess).where(TransferProcess.id == process_id)
        )
        process = result.scalar_one_or_none()
        if process is None:
            raise ValueError(f"TransferProcess {process_id} not found")
        if process.status != "approved":
            raise ValueError(f"Cannot execute transfer in status {process.status!r}")

        # 关闭旧在岗关系
        await session.execute(
            update(EmploymentAssignment)
            .where(EmploymentAssignment.id == process.from_assignment_id)
            .values(status="ended", end_date=process.effective_date)
        )

        # 创建新在岗关系
        new_assignment = EmploymentAssignment(
            person_id=process.person_id,
            org_node_id=process.to_org_node_id,
            employment_type=process.to_employment_type,
            start_date=process.effective_date,
            status="active",
        )
        session.add(new_assignment)

        # 推进调岗流程状态
        await session.execute(
            update(TransferProcess)
            .where(TransferProcess.id == process_id)
            .values(status="active", updated_at=datetime.now(timezone.utc))
        )
        await session.flush()
        logger.info(
            "transfer.executed",
            process_id=str(process_id),
            new_assignment_id=str(new_assignment.id),
            from_assignment_id=str(process.from_assignment_id),
        )
        return new_assignment

    async def _predict_revenue_impact(
        self,
        person_id: uuid.UUID,
        to_org_node_id: str,
        transfer_type: str,
        session: AsyncSession,
    ) -> float:
        """估算调岗¥影响（元）= 基准月薪 × 影响系数（WF-6实装前为固定值）"""
        ratio = _REVENUE_IMPACT_RATIO.get(transfer_type, 0.0)
        return round(_STUB_BASE_MONTHLY_YUAN * ratio, 2)
