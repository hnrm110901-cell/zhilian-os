"""LeaveService — 假期管理服务

支持：请假申请/审批/余额查询/自动发放/模拟计算
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.leave_request import LeaveRequest
from ...models.hr.leave_balance import LeaveBalance

logger = structlog.get_logger()

# 假期类型对应的默认年度配额（天）
_DEFAULT_ANNUAL_QUOTAS: dict[str, float] = {
    "annual": 5.0,
    "sick": 15.0,
    "personal": 5.0,
    "marriage": 3.0,
    "maternity": 98.0,
    "paternity": 15.0,
    "bereavement": 3.0,
}

_VALID_LEAVE_TYPES = set(_DEFAULT_ANNUAL_QUOTAS.keys())


class LeaveService:

    async def apply(
        self,
        assignment_id: uuid.UUID,
        leave_type: str,
        start_datetime: datetime,
        end_datetime: datetime,
        days: float,
        reason: str,
        created_by: str,
        session: AsyncSession,
    ) -> LeaveRequest:
        """提交请假申请"""
        if leave_type not in _VALID_LEAVE_TYPES:
            raise ValueError(f"Invalid leave_type: {leave_type!r}")
        if end_datetime <= start_datetime:
            raise ValueError("end_datetime must be after start_datetime")
        if days <= 0:
            raise ValueError("days must be positive")

        request = LeaveRequest(
            assignment_id=assignment_id,
            leave_type=leave_type,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            days=Decimal(str(days)),
            reason=reason,
            created_by=created_by,
            status="pending",
        )
        session.add(request)
        await session.flush()
        logger.info(
            "leave.applied",
            request_id=str(request.id),
            assignment_id=str(assignment_id),
            leave_type=leave_type,
            days=days,
        )
        return request

    async def approve(
        self,
        request_id: uuid.UUID,
        approved_by: str,
        session: AsyncSession,
    ) -> LeaveRequest:
        """审批通过请假，扣减余额"""
        result = await session.execute(
            select(LeaveRequest).where(LeaveRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise ValueError(f"LeaveRequest {request_id} not found")
        if request.status != "pending":
            raise ValueError(f"Cannot approve request in status {request.status!r}")

        # 扣减余额
        year = request.start_datetime.year
        balance_result = await session.execute(
            select(LeaveBalance).where(
                LeaveBalance.assignment_id == request.assignment_id,
                LeaveBalance.leave_type == request.leave_type,
                LeaveBalance.year == year,
            )
        )
        balance = balance_result.scalar_one_or_none()
        if balance:
            new_used = float(balance.used_days) + float(request.days)
            new_remaining = float(balance.total_days) - new_used
            if new_remaining < 0:
                raise ValueError(
                    f"余额不足：{request.leave_type} 剩余 {float(balance.remaining_days)} 天，"
                    f"申请 {float(request.days)} 天"
                )
            balance.used_days = Decimal(str(new_used))
            balance.remaining_days = Decimal(str(new_remaining))

        # 更新申请状态
        request.status = "approved"
        request.approved_by = approved_by
        await session.flush()
        logger.info("leave.approved", request_id=str(request_id), approved_by=approved_by)
        return request

    async def get_balance(
        self,
        assignment_id: uuid.UUID,
        leave_type: str,
        year: int,
        session: AsyncSession,
    ) -> Optional[LeaveBalance]:
        """查询假期余额"""
        result = await session.execute(
            select(LeaveBalance).where(
                LeaveBalance.assignment_id == assignment_id,
                LeaveBalance.leave_type == leave_type,
                LeaveBalance.year == year,
            )
        )
        return result.scalar_one_or_none()

    async def accrue_annual_leave(
        self,
        assignment_id: uuid.UUID,
        year: int,
        session: AsyncSession,
    ) -> LeaveBalance:
        """自动发放年假（按默认配额）"""
        existing = await self.get_balance(assignment_id, "annual", year, session)
        if existing:
            return existing  # 已发放则不重复

        quota = _DEFAULT_ANNUAL_QUOTAS["annual"]
        balance = LeaveBalance(
            assignment_id=assignment_id,
            leave_type="annual",
            year=year,
            total_days=Decimal(str(quota)),
            used_days=Decimal("0"),
            remaining_days=Decimal(str(quota)),
        )
        session.add(balance)
        await session.flush()
        logger.info("leave.accrued", assignment_id=str(assignment_id), year=year, quota=quota)
        return balance

    async def simulate(
        self,
        assignment_id: uuid.UUID,
        leave_type: str,
        days: float,
        year: int,
        session: AsyncSession,
    ) -> dict:
        """模拟请假：检查余额是否足够，返回模拟结果"""
        balance = await self.get_balance(assignment_id, leave_type, year, session)
        remaining = float(balance.remaining_days) if balance else 0.0
        sufficient = remaining >= days

        return {
            "leave_type": leave_type,
            "requested_days": days,
            "current_remaining": remaining,
            "sufficient": sufficient,
            "shortfall": max(0, days - remaining) if not sufficient else 0,
        }
