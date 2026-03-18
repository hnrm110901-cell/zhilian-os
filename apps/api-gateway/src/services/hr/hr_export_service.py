"""HRExportService — HR数据Excel导出"""
from io import BytesIO
import uuid
import structlog
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.payroll_batch import PayrollBatch
from ...models.hr.payroll_item import PayrollItem

logger = structlog.get_logger()


class HRExportService:

    async def export_payroll_batch(
        self,
        batch_id: uuid.UUID,
        session: AsyncSession,
    ) -> BytesIO:
        """导出薪资批次为Excel（3个sheet）"""
        # Get batch
        batch_result = await session.execute(
            select(PayrollBatch).where(PayrollBatch.id == batch_id)
        )
        batch = batch_result.scalar_one_or_none()
        if batch is None:
            raise ValueError(f"PayrollBatch {batch_id} not found")

        # Get items
        items_result = await session.execute(
            select(PayrollItem).where(PayrollItem.batch_id == batch_id)
        )
        items = list(items_result.scalars().all())

        wb = Workbook()

        # Sheet 1: 月度汇总
        ws_summary = wb.active
        ws_summary.title = "月度汇总"
        ws_summary.append(["薪资核算期间", f"{batch.period_year}年{batch.period_month}月"])
        ws_summary.append(["员工人数", len(items)])
        ws_summary.append(["税前总额（元）", batch.total_gross_fen / 100])
        ws_summary.append(["税后总额（元）", batch.total_net_fen / 100])
        ws_summary.append([])

        # Sheet 2: 个人工资条
        ws_detail = wb.create_sheet("个人工资条")
        ws_detail.append([
            "员工ID", "基本工资", "加班费", "迟到扣款", "缺勤扣款",
            "税前合计", "社保", "个税", "实发工资",
        ])
        for item in items:
            ws_detail.append([
                str(item.assignment_id)[:8],
                item.base_salary_fen / 100,
                item.overtime_fen / 100,
                item.deduction_late_fen / 100,
                item.deduction_absent_fen / 100,
                item.gross_fen / 100,
                item.social_insurance_fen / 100,
                item.tax_fen / 100,
                item.net_fen / 100,
            ])

        # Sheet 3: 部门成本
        ws_cost = wb.create_sheet("部门成本")
        ws_cost.append(["部门", "总成本（元）"])
        ws_cost.append([batch.org_node_id, batch.total_gross_fen / 100])

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf
