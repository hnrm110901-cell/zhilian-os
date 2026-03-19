"""PayrollService — 薪资核算引擎

按月生成工资单，从考勤数据 + 合同薪酬方案计算基本工资/加班/扣款。
集成社保计算（SocialInsuranceService）和个税计算（TaxService）。
支持4种薪酬类型：fixed_monthly / hourly / base_plus_commission / piecework。
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.payroll_batch import PayrollBatch
from ...models.hr.payroll_item import PayrollItem
from ...models.hr.cost_allocation import CostAllocation
from ...models.hr.employment_assignment import EmploymentAssignment
from ...models.hr.employment_contract import EmploymentContract
from ...models.hr.daily_attendance import DailyAttendance
from .social_insurance_service import SocialInsuranceService
from .tax_service import TaxService

logger = structlog.get_logger()

# 行业默认回退参数（仅在合同缺失时使用）
_FALLBACK_BASE_FEN = 400000  # 4000元
_FALLBACK_OVERTIME_RATE_FEN = 2500  # 25元/时
_FALLBACK_LATE_DEDUCTION_FEN = 5000  # 50元/次
_FALLBACK_ABSENT_DEDUCTION_FEN = 20000  # 200元/天


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

        # 计算当月工作日数（简化：按22天）
        work_days_in_month = 22

        si_svc = SocialInsuranceService()
        tax_svc = TaxService()

        items = []
        total_gross = 0
        total_net = 0

        for asn in assignments:
            # 1. 查询当期有效合同
            contract = await self._get_active_contract(
                asn.id, batch.period_year, batch.period_month, session
            )
            pay_scheme = contract.pay_scheme if contract and contract.pay_scheme else {}

            # 2. 查考勤数据
            att_rows = await self._get_attendance(asn.id, first_day, last_day, session)

            # 3. 按薪酬类型计算基本工资
            base_fen = self._calculate_base(pay_scheme, att_rows, work_days_in_month)

            # 4. 计算加班费/迟到扣款/缺勤扣款
            overtime_fen, deduction_late_fen, deduction_absent_fen = (
                self._calculate_adjustments(pay_scheme, att_rows)
            )

            # 5. 税前合计
            gross_fen = max(0, base_fen + overtime_fen - deduction_late_fen - deduction_absent_fen)

            # 6. 社保计算
            gross_yuan = gross_fen / 100
            si = si_svc.calculate_employee_portion(gross_yuan)
            social_insurance_fen = round(si["total_yuan"] * 100)

            # 7. 个税计算（累计预扣法）
            taxable_yuan = max(0, gross_yuan - si["total_yuan"] - 5000)
            ytd_taxable = await self._get_ytd_taxable(
                asn.id, batch.period_year, batch.period_month, session
            )
            tax_yuan = tax_svc.calculate_monthly_tax(ytd_taxable, taxable_yuan)
            tax_fen = round(tax_yuan * 100)

            # 8. 实发工资
            net_fen = gross_fen - social_insurance_fen - tax_fen

            item = PayrollItem(
                batch_id=batch_id,
                assignment_id=asn.id,
                base_salary_fen=base_fen,
                overtime_fen=overtime_fen,
                deduction_late_fen=deduction_late_fen,
                deduction_absent_fen=deduction_absent_fen,
                gross_fen=gross_fen,
                social_insurance_fen=social_insurance_fen,
                tax_fen=tax_fen,
                net_fen=net_fen,
            )
            session.add(item)
            items.append(item)
            total_gross += gross_fen
            total_net += net_fen

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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_active_contract(
        self,
        assignment_id: uuid.UUID,
        year: int,
        month: int,
        session: AsyncSession,
    ) -> Optional[EmploymentContract]:
        """查询当期有效合同"""
        period_date = date(year, month, 1)
        result = await session.execute(
            select(EmploymentContract).where(
                EmploymentContract.assignment_id == assignment_id,
                EmploymentContract.valid_from <= period_date,
                (
                    (EmploymentContract.valid_to.is_(None))
                    | (EmploymentContract.valid_to >= period_date)
                ),
            ).order_by(EmploymentContract.valid_from.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_attendance(
        self,
        assignment_id: uuid.UUID,
        first_day: date,
        last_day: date,
        session: AsyncSession,
    ) -> list[DailyAttendance]:
        """查询指定日期范围的考勤数据"""
        att_result = await session.execute(
            select(DailyAttendance).where(
                DailyAttendance.assignment_id == assignment_id,
                DailyAttendance.date >= first_day,
                DailyAttendance.date < last_day,
            )
        )
        return list(att_result.scalars().all())

    def _calculate_base(
        self,
        pay_scheme: dict,
        att_rows: list[DailyAttendance],
        work_days_in_month: int,
    ) -> int:
        """按薪酬类型计算基本工资（分）"""
        pay_type = pay_scheme.get("type", "fixed_monthly")

        if pay_type == "fixed_monthly":
            return pay_scheme.get("base_salary_fen", _FALLBACK_BASE_FEN)

        elif pay_type == "hourly":
            hours = sum(r.work_minutes for r in att_rows) / 60
            return round(pay_scheme.get("hourly_rate_fen", 2200) * hours)

        elif pay_type == "base_plus_commission":
            # 底薪部分；提成需要销售数据，暂不可用时返回0
            return pay_scheme.get("base_salary_fen", _FALLBACK_BASE_FEN)

        elif pay_type == "piecework":
            return round(
                pay_scheme.get("unit_rate_fen", 500)
                * pay_scheme.get("monthly_units", 0)
            )

        # 未知类型：回退到固定月薪
        return _FALLBACK_BASE_FEN

    def _calculate_adjustments(
        self,
        pay_scheme: dict,
        att_rows: list[DailyAttendance],
    ) -> tuple[int, int, int]:
        """计算加班费/迟到扣款/缺勤扣款

        Returns:
            (overtime_fen, deduction_late_fen, deduction_absent_fen)
        """
        overrides = pay_scheme.get("overrides", {})
        overtime_rate = overrides.get(
            "overtime_rate_per_hour_fen", _FALLBACK_OVERTIME_RATE_FEN
        )
        late_deduction = overrides.get(
            "late_deduction_per_time_fen", _FALLBACK_LATE_DEDUCTION_FEN
        )
        absent_deduction = overrides.get(
            "absent_deduction_per_day_fen", _FALLBACK_ABSENT_DEDUCTION_FEN
        )

        overtime_hours = sum(r.overtime_minutes for r in att_rows) / 60
        late_count = sum(1 for r in att_rows if r.status == "late")
        absent_count = sum(1 for r in att_rows if r.status == "absent")

        return (
            round(overtime_hours * overtime_rate),
            late_count * late_deduction,
            absent_count * absent_deduction,
        )

    async def _get_ytd_taxable(
        self,
        assignment_id: uuid.UUID,
        year: int,
        month: int,
        session: AsyncSession,
    ) -> float:
        """查询本年截至上月的累计应纳税所得额（元）"""
        result = await session.execute(
            select(
                func.coalesce(
                    func.sum(PayrollItem.gross_fen - PayrollItem.social_insurance_fen),
                    0,
                )
            )
            .join(PayrollBatch, PayrollItem.batch_id == PayrollBatch.id)
            .where(
                PayrollItem.assignment_id == assignment_id,
                PayrollBatch.period_year == year,
                PayrollBatch.period_month < month,
            )
        )
        ytd_gross_minus_si_fen = result.scalar() or 0
        prior_months = max(0, month - 1)
        # 扣除每月5000元起征点（5000元 = 500000分）
        ytd_taxable_fen = ytd_gross_minus_si_fen - (prior_months * 500000)
        return max(0, ytd_taxable_fen / 100)
