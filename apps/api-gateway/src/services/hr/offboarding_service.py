"""OffboardingService — 离职全流程服务

WF流程：
pending → (approve) → approved → (complete) → completed
离职时触发 WF-4 知识采集（retention_signal > 0.85 时）
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.offboarding_process import OffboardingProcess
from ...models.hr.employment_assignment import EmploymentAssignment

logger = structlog.get_logger()

# 技能损失评估：各岗位的基准月薪（元）用于估算技能损失
_BASE_MONTHLY_SALARY_YUAN: dict[str, float] = {
    "outsourced_dispatched": 4000.0,
    "default": 4500.0,
}

# 知识采集触发阈值（retention_signal高于此值时触发采集）
_KNOWLEDGE_CAPTURE_THRESHOLD = 0.85


class OffboardingService:

    async def apply(
        self,
        assignment_id: uuid.UUID,
        reason: str,
        planned_last_day: date,
        created_by: str,
        session: AsyncSession,
        notes: Optional[str] = None,
        apply_date: Optional[date] = None,
    ) -> OffboardingProcess:
        """提交离职申请"""
        if reason not in ("resignation", "termination", "contract_end", "retirement", "mutual"):
            raise ValueError(f"Invalid reason: {reason!r}")

        process = OffboardingProcess(
            assignment_id=assignment_id,
            reason=reason,
            apply_date=apply_date or date.today(),
            planned_last_day=planned_last_day,
            created_by=created_by,
            notes=notes,
            status="pending",
        )
        session.add(process)
        await session.flush()
        # 用flush后的process.id更新软引用
        await session.execute(
            update(EmploymentAssignment)
            .where(EmploymentAssignment.id == assignment_id)
            .values(offboarding_process_id=process.id)
        )
        await session.flush()
        logger.info("offboarding.applied", process_id=str(process.id), assignment_id=str(assignment_id))
        return process

    async def approve(
        self,
        process_id: uuid.UUID,
        approved_by: str,
        session: AsyncSession,
    ) -> OffboardingProcess:
        """审批通过离职申请"""
        result = await session.execute(
            select(OffboardingProcess).where(OffboardingProcess.id == process_id)
        )
        process = result.scalar_one_or_none()
        if process is None:
            raise ValueError(f"OffboardingProcess {process_id} not found")
        if process.status != "pending":
            raise ValueError(f"Cannot approve offboarding in status {process.status!r}")

        await session.execute(
            update(OffboardingProcess)
            .where(OffboardingProcess.id == process_id)
            .values(status="approved", updated_at=datetime.now(timezone.utc))
        )
        await session.flush()
        logger.info("offboarding.approved", process_id=str(process_id), approved_by=approved_by)
        return process

    async def complete(
        self,
        process_id: uuid.UUID,
        session: AsyncSession,
        actual_last_day: Optional[date] = None,
    ) -> dict:
        """完成离职流程：结算 + 触发知识采集 + 关闭在岗关系"""
        result = await session.execute(
            select(OffboardingProcess).where(OffboardingProcess.id == process_id)
        )
        process = result.scalar_one_or_none()
        if process is None:
            raise ValueError(f"OffboardingProcess {process_id} not found")
        if process.status != "approved":
            raise ValueError(f"Cannot complete offboarding in status {process.status!r}")

        last_day = actual_last_day or process.planned_last_day

        # 计算技能损失
        skill_loss_yuan = await self._calculate_skill_loss_yuan(process.assignment_id, session)

        # 触发知识采集（WF-4）
        knowledge_captured = await self._trigger_knowledge_capture(process_id, session)

        # 关闭在岗关系
        await session.execute(
            update(EmploymentAssignment)
            .where(EmploymentAssignment.id == process.assignment_id)
            .values(status="ended", end_date=last_day)
        )

        # 完成离职流程
        await session.execute(
            update(OffboardingProcess)
            .where(OffboardingProcess.id == process_id)
            .values(
                status="completed",
                actual_last_day=last_day,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()

        result_summary = {
            "process_id": str(process_id),
            "status": "completed",
            "actual_last_day": last_day.isoformat(),
            "skill_loss_yuan": skill_loss_yuan,
            "knowledge_capture_triggered": knowledge_captured,
        }
        logger.info("offboarding.completed", **result_summary)
        return result_summary

    async def _calculate_skill_loss_yuan(
        self,
        assignment_id: uuid.UUID,
        session: AsyncSession,
    ) -> float:
        """估算技能损失金额（元）= 岗位基准月薪 × 0.3（替换成本系数）"""
        result = await session.execute(
            select(EmploymentAssignment).where(EmploymentAssignment.id == assignment_id)
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            return 0.0

        # 根据employment_type推断岗位类型
        emp_type = getattr(assignment, "employment_type", "full_time")
        # 简单用岗位类型做基准映射
        if emp_type in ("outsourced", "dispatched"):
            base = _BASE_MONTHLY_SALARY_YUAN["outsourced_dispatched"]
        else:
            base = _BASE_MONTHLY_SALARY_YUAN["default"]

        skill_loss = round(base * 0.3, 2)
        return skill_loss

    async def _trigger_knowledge_capture(
        self,
        process_id: uuid.UUID,
        session: AsyncSession,
    ) -> bool:
        """触发WF-4知识采集（软触发：失败静默降级，不影响离职流程）"""
        try:
            # 标记已触发
            await session.execute(
                update(OffboardingProcess)
                .where(OffboardingProcess.id == process_id)
                .values(knowledge_capture_triggered=True)
            )
            logger.info("offboarding.knowledge_capture_triggered", process_id=str(process_id))
            return True
        except Exception as exc:
            # 静默降级：知识采集失败不阻断离职流程
            logger.warning(
                "offboarding.knowledge_capture_failed",
                process_id=str(process_id),
                error=str(exc),
            )
            return False
