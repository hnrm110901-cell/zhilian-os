"""PayrollService — 薪资核算引擎

按月生成工资单，从考勤数据计算出勤天/加班/扣款。
社保/个税留空等三方填入。支持多门店分摊。
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.payroll_batch import PayrollBatch
from ...models.hr.payroll_item import PayrollItem
from ...models.hr.cost_allocation import CostAllocation
from ...models.hr.employment_assignment import EmploymentAssignment
from ...models.hr.daily_attendance import DailyAttendance

logger = structlog.get_logger()

# 默认薪资参数
_DEFAULT_BASE_SALARY_FEN = 400000  # 4000元
_OVERTIME_RATE_PER_HOUR_FEN = 2500  # 25元/时
_LATE_DEDUCTION_PER_TIME_FEN = 5000  # 50元/次
_ABSENT_DEDUCTION_PER_DAY_FEN = 20000  # 200元/天


class PayrollService:

    async def create_batch(
        self,
        org_node_id: str,
        year: int,
        month: int,
        created_by: str,
        session: AsyncSession,
    ) -> PayrollBatch:
        """创建薪资核算批次"""
        batch = PayrollBatch(
            org_node_id=org_node_id,
            period_year=year,
            period_month=month,
            created_by=created_by,
            status="draft",
        )
        session.add(batch)
        await session.flush()
        logger.info("payroll.batch_created", batch_id=str(batch.id), period=f"{year}-{month}")
        return batch

    async def calculate(
        self,
        batch_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[PayrollItem]:
        """计算批次内所有员工的薪资"""
        result = await session.execute(
            select(PayrollBatch).where(PayrollBatch.id == batch_id)
        )
        batch = result.scalar_one_or_none()
        if batch is None:
            raise ValueError(f"PayrollBatch {batch_id} not found")
        if batch.status not in ("draft", "calculating"):
            raise ValueError(f"Cannot calculate batch in status {batch.status!r}")

        # 更新状态
        batch.status = "calculating"
        await session.flush()

        # 查找该org_node下所有active在岗关系
        assignments_result = await session.execute(
            select(EmploymentAssignment).where(
                EmploymentAssignment.org_node_id == batch.org_node_id,
                EmploymentAssignment.status == "active",
            )
        )
        assignments = list(assignments_result.scalars().all())

        # 日期范围
        first_day = date(batch.period_year, batch.period_month, 1)
        if batch.period_month == 12:
            last_day = date(batch.period_year + 1, 1, 1)
        else:
            last_day = date(batch.period_year, batch.period_month + 1, 1)

        items = []
        total_gross = 0
        total_net = 0

        for asn in assignments:
            # 查考勤数据
            att_result = await session.execute(
                select(DailyAttendance).where(
                    DailyAttendance.assignment_id == asn.id,
                    DailyAttendance.date >= first_day,
                    DailyAttendance.date < last_day,
                )
            )
            att_rows = list(att_result.scalars().all())

            late_count = sum(1 for r in att_rows if r.status == "late")
            absent_count = sum(1 for r in att_rows if r.status == "absent")
            overtime_hours = sum(r.overtime_minutes for r in att_rows) / 60

            base = _DEFAULT_BASE_SALARY_FEN
            overtime_fen = round(overtime_hours * _OVERTIME_RATE_PER_HOUR_FEN)
            deduction_late = late_count * _LATE_DEDUCTION_PER_TIME_FEN
            deduction_absent = absent_count * _ABSENT_DEDUCTION_PER_DAY_FEN

            gross = base + overtime_fen - deduction_late - deduction_absent
            gross = max(0, gross)  # 不能为负
            # social_insurance_fen和tax_fen留0（等三方填入）
            net = gross  # 暂时=gross

            item = PayrollItem(
                batch_id=batch_id,
                assignment_id=asn.id,
                base_salary_fen=base,
                overtime_fen=overtime_fen,
                deduction_late_fen=deduction_late,
                deduction_absent_fen=deduction_absent,
                gross_fen=gross,
                net_fen=net,
            )
            session.add(item)
            items.append(item)
            total_gross += gross
            total_net += net

        # 更新批次汇总
        batch.status = "review"
        batch.total_gross_fen = total_gross
        batch.total_net_fen = total_net
        await session.flush()

        logger.info(
            "payroll.calculated",
            batch_id=str(batch_id),
            item_count=len(items),
            total_gross_fen=total_gross,
        )
        return items

    async def approve(
        self,
        batch_id: uuid.UUID,
        approved_by: str,
        session: AsyncSession,
    ) -> PayrollBatch:
        """审批薪资批次"""
        result = await session.execute(
            select(PayrollBatch).where(PayrollBatch.id == batch_id)
        )
        batch = result.scalar_one_or_none()
        if batch is None:
            raise ValueError(f"PayrollBatch {batch_id} not found")
        if batch.status != "review":
            raise ValueError(f"Cannot approve batch in status {batch.status!r}")

        batch.status = "approved"
        batch.approved_by = approved_by
        await session.flush()
        return batch

    async def get_payslip(
        self,
        item_id: uuid.UUID,
        viewer_id: str,
        session: AsyncSession,
    ) -> dict:
        """获取工资条（阅后即焚：记录查看时间）"""
        result = await session.execute(
            select(PayrollItem).where(PayrollItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"PayrollItem {item_id} not found")

        # 检查是否过期
        if item.view_expires_at and datetime.now(timezone.utc) > item.view_expires_at:
            return {"error": "工资条已过期", "expired": True}

        # 记录查看时间
        if item.viewed_at is None:
            item.viewed_at = datetime.now(timezone.utc)
            await session.flush()

        return {
            "id": str(item.id),
            "base_salary_yuan": item.base_salary_fen / 100,
            "overtime_yuan": item.overtime_fen / 100,
            "deduction_late_yuan": item.deduction_late_fen / 100,
            "deduction_absent_yuan": item.deduction_absent_fen / 100,
            "gross_yuan": item.gross_fen / 100,
            "social_insurance_yuan": item.social_insurance_fen / 100,
            "tax_yuan": item.tax_fen / 100,
            "net_yuan": item.net_fen / 100,
            "viewed_at": item.viewed_at.isoformat() if item.viewed_at else None,
        }

    async def allocate_cost(
        self,
        batch_id: uuid.UUID,
        session: AsyncSession,
    ) -> dict:
        """按CostAllocation比例拆分到各门店成本中心"""
        items_result = await session.execute(
            select(PayrollItem).where(PayrollItem.batch_id == batch_id)
        )
        items = list(items_result.scalars().all())

        allocations: dict[str, int] = {}  # org_node_id -> total_fen

        for item in items:
            # 查分摊配置
            alloc_result = await session.execute(
                select(CostAllocation).where(
                    CostAllocation.assignment_id == item.assignment_id
                )
            )
            allocs = list(alloc_result.scalars().all())

            if not allocs:
                # 无分摊配置：全部计入当前批次org_node
                result2 = await session.execute(
                    select(PayrollBatch.org_node_id).where(PayrollBatch.id == batch_id)
                )
                batch_org = result2.scalar_one_or_none() or "unknown"
                allocations[batch_org] = allocations.get(batch_org, 0) + item.gross_fen
            else:
                for a in allocs:
                    share = round(item.gross_fen * float(a.ratio))
                    org = a.org_node_id
                    allocations[org] = allocations.get(org, 0) + share

        return {
            "batch_id": str(batch_id),
            "allocations": [
                {"org_node_id": k, "total_fen": v, "total_yuan": round(v / 100, 2)}
                for k, v in sorted(allocations.items())
            ],
        }
