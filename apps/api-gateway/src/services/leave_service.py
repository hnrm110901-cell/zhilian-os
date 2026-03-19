"""
Leave Service — 假勤管理服务
请假、加班申请及假期余额管理
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.hr.person import Person
from src.models.leave import (
    LeaveBalance,
    LeaveCategory,
    LeaveRequest,
    LeaveRequestStatus,
    LeaveTypeConfig,
    OvertimeRequest,
    OvertimeRequestStatus,
    OvertimeType,
)
from src.services.base_service import BaseService
from src.services.hr_approval_service import HRApprovalService

logger = structlog.get_logger()


class LeaveService(BaseService):
    """假勤管理服务"""

    async def submit_leave(self, db: AsyncSession, data: Dict[str, Any]) -> LeaveRequest:
        """提交请假申请"""
        store_id = data.get("store_id") or self.store_id
        employee_id = data["employee_id"]
        category = data["leave_category"]
        leave_days = Decimal(str(data["leave_days"]))

        # 检查余额
        year = int(data["start_date"][:4]) if isinstance(data["start_date"], str) else data["start_date"].year
        balance = await self._get_balance(db, employee_id, year, category)
        if balance and balance.remaining_days < float(leave_days):
            raise ValueError(f"假期余额不足: 剩余 {balance.remaining_days} 天, 申请 {leave_days} 天")

        start_date = data["start_date"] if isinstance(data["start_date"], date) else date.fromisoformat(data["start_date"])
        end_date = data["end_date"] if isinstance(data["end_date"], date) else date.fromisoformat(data["end_date"])

        request = LeaveRequest(
            store_id=store_id,
            employee_id=employee_id,
            leave_category=category,
            status=LeaveRequestStatus.PENDING,
            start_date=start_date,
            end_date=end_date,
            start_half=data.get("start_half", "am"),
            end_half=data.get("end_half", "pm"),
            leave_days=leave_days,
            leave_hours=data.get("leave_hours"),
            reason=data.get("reason", ""),
            attachment_urls=data.get("attachment_urls"),
            substitute_employee_id=data.get("substitute_employee_id"),
        )
        db.add(request)

        # 更新待审批天数
        if balance:
            balance.pending_days = Decimal(str(float(balance.pending_days) + float(leave_days)))

        await db.flush()

        # 发起审批（通过 Person.legacy_employee_id 桥接查询姓名）
        approval_svc = HRApprovalService(store_id=store_id)
        person_result = await db.execute(
            select(Person.name).where(Person.legacy_employee_id == str(employee_id))
        )
        emp_name = person_result.scalar_one_or_none() or str(employee_id)

        instance = await approval_svc.create_instance(
            db,
            approval_type="leave",
            applicant_id=employee_id,
            applicant_name=emp_name,
            business_type="leave_request",
            business_id=str(request.id),
            title=f"{emp_name} 请假 {leave_days} 天（{category}）",
            summary=data.get("reason", ""),
            business_data={"leave_days": float(leave_days), "category": category},
            store_id=store_id,
        )
        request.approval_instance_id = instance.id

        await db.flush()
        logger.info("leave_submitted", employee_id=employee_id, days=float(leave_days))
        return request

    async def approve_leave(
        self, db: AsyncSession, request_id: str, approver_id: str, approver_name: str = ""
    ) -> LeaveRequest:
        """审批通过请假"""
        request = await db.get(LeaveRequest, request_id)
        if not request:
            raise ValueError("请假单不存在")

        request.status = LeaveRequestStatus.APPROVED
        request.approved_by = approver_id
        request.approved_at = datetime.utcnow()

        # 更新余额：pending → used
        year = request.start_date.year
        balance = await self._get_balance(db, request.employee_id, year, request.leave_category.value)
        if balance:
            balance.pending_days = max(Decimal("0"), Decimal(str(float(balance.pending_days) - float(request.leave_days))))
            balance.used_days = Decimal(str(float(balance.used_days) + float(request.leave_days)))

        # 审批通过
        if request.approval_instance_id:
            approval_svc = HRApprovalService(store_id=request.store_id)
            await approval_svc.approve(db, str(request.approval_instance_id), approver_id, approver_name)

        await db.flush()
        return request

    async def reject_leave(self, db: AsyncSession, request_id: str, approver_id: str, reason: str = "") -> LeaveRequest:
        """驳回请假"""
        request = await db.get(LeaveRequest, request_id)
        if not request:
            raise ValueError("请假单不存在")

        request.status = LeaveRequestStatus.REJECTED
        request.rejection_reason = reason

        # 释放pending余额
        year = request.start_date.year
        balance = await self._get_balance(db, request.employee_id, year, request.leave_category.value)
        if balance:
            balance.pending_days = max(Decimal("0"), Decimal(str(float(balance.pending_days) - float(request.leave_days))))

        if request.approval_instance_id:
            approval_svc = HRApprovalService(store_id=request.store_id)
            await approval_svc.reject(db, str(request.approval_instance_id), approver_id, reason=reason)

        await db.flush()
        return request

    async def submit_overtime(self, db: AsyncSession, data: Dict[str, Any]) -> OvertimeRequest:
        """提交加班申请"""
        store_id = data.get("store_id") or self.store_id
        overtime_type = data.get("overtime_type", "weekday")

        # 自动计算倍率
        rate_map = {"weekday": 1.5, "weekend": 2.0, "holiday": 3.0}
        pay_rate = rate_map.get(overtime_type, 1.5)

        work_date = data["work_date"] if isinstance(data["work_date"], date) else date.fromisoformat(data["work_date"])

        request = OvertimeRequest(
            store_id=store_id,
            employee_id=data["employee_id"],
            overtime_type=overtime_type,
            status=OvertimeRequestStatus.PENDING,
            work_date=work_date,
            start_time=data["start_time"],
            end_time=data["end_time"],
            hours=Decimal(str(data["hours"])),
            pay_rate=Decimal(str(pay_rate)),
            reason=data.get("reason", ""),
            compensatory=data.get("compensatory", False),
        )
        db.add(request)
        await db.flush()

        logger.info("overtime_submitted", employee_id=data["employee_id"], hours=data["hours"])
        return request

    async def get_leave_list(
        self, db: AsyncSession, store_id: str, status: str = None, month: str = None
    ) -> List[Dict[str, Any]]:
        """获取请假列表"""
        conditions = [LeaveRequest.store_id == store_id]
        if status:
            conditions.append(LeaveRequest.status == status)
        if month:
            year, m = int(month[:4]), int(month[5:7])
            conditions.append(LeaveRequest.start_date >= date(year, m, 1))

        result = await db.execute(
            select(LeaveRequest, Person.name)
            .join(Person, Person.legacy_employee_id == LeaveRequest.employee_id, isouter=True)
            .where(and_(*conditions))
            .order_by(LeaveRequest.created_at.desc())
            .limit(100)
        )
        rows = result.all()
        return [
            {
                "id": str(req.id),
                "employee_id": req.employee_id,
                "employee_name": name or req.employee_id,
                "leave_category": req.leave_category.value if req.leave_category else "",
                "status": req.status.value if req.status else "",
                "start_date": str(req.start_date),
                "end_date": str(req.end_date),
                "leave_days": float(req.leave_days),
                "reason": req.reason,
                "created_at": req.created_at.isoformat() if req.created_at else None,
            }
            for req, name in rows
        ]

    async def get_leave_balance(self, db: AsyncSession, employee_id: str, year: int) -> List[Dict[str, Any]]:
        """获取员工假期余额"""
        result = await db.execute(
            select(LeaveBalance).where(
                and_(
                    LeaveBalance.employee_id == employee_id,
                    LeaveBalance.year == year,
                )
            )
        )
        balances = result.scalars().all()
        return [
            {
                "category": b.leave_category.value if b.leave_category else "",
                "total_days": float(b.total_days),
                "used_days": float(b.used_days),
                "pending_days": float(b.pending_days),
                "remaining_days": b.remaining_days,
            }
            for b in balances
        ]

    async def init_annual_balance(self, db: AsyncSession, store_id: str, employee_id: str, year: int):
        """初始化年度假期余额"""
        # 查询配置
        result = await db.execute(
            select(LeaveTypeConfig).where(
                and_(
                    LeaveTypeConfig.is_active.is_(True),
                )
            )
        )
        configs = result.scalars().all()

        for config in configs:
            existing = await self._get_balance(db, employee_id, year, config.category.value)
            if not existing:
                balance = LeaveBalance(
                    store_id=store_id,
                    employee_id=employee_id,
                    year=year,
                    leave_category=config.category,
                    total_days=config.max_days_per_year or 0,
                )
                db.add(balance)

        await db.flush()

    async def _get_balance(self, db: AsyncSession, employee_id: str, year: int, category: str) -> Optional[LeaveBalance]:
        """获取假期余额"""
        result = await db.execute(
            select(LeaveBalance).where(
                and_(
                    LeaveBalance.employee_id == employee_id,
                    LeaveBalance.year == year,
                    LeaveBalance.leave_category == category,
                )
            )
        )
        return result.scalar_one_or_none()
