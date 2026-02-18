"""
报表导出服务
支持PDF和Excel格式导出
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import io
import csv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.models.finance import FinancialTransaction, FinancialReport
from src.services.finance_service import FinanceService


class ReportExportService:
    """报表导出服务"""

    def __init__(self):
        self.finance_service = FinanceService()

    async def export_to_csv(
        self,
        report_type: str,
        start_date: datetime,
        end_date: datetime,
        store_id: Optional[int] = None,
        db: Optional[AsyncSession] = None
    ) -> bytes:
        """
        导出报表为CSV格式

        Args:
            report_type: 报表类型 (income_statement, cash_flow, balance_sheet)
            start_date: 开始日期
            end_date: 结束日期
            store_id: 门店ID
            db: 数据库会话

        Returns:
            CSV文件字节流
        """
        # 获取报表数据
        if report_type == "income_statement":
            data = await self.finance_service.get_income_statement(
                start_date, end_date, store_id, db
            )
            return self._generate_income_statement_csv(data, start_date, end_date)
        elif report_type == "cash_flow":
            data = await self.finance_service.get_cash_flow_statement(
                start_date, end_date, store_id, db
            )
            return self._generate_cash_flow_csv(data, start_date, end_date)
        elif report_type == "transactions":
            data = await self._get_transactions(start_date, end_date, store_id, db)
            return self._generate_transactions_csv(data)
        else:
            raise ValueError(f"不支持的报表类型: {report_type}")

    def _generate_income_statement_csv(
        self, data: Dict[str, Any], start_date: datetime, end_date: datetime
    ) -> bytes:
        """生成损益表CSV"""
        output = io.StringIO()
        writer = csv.writer(output)

        # 写入标题
        writer.writerow(["损益表"])
        writer.writerow([f"期间: {start_date.date()} 至 {end_date.date()}"])
        writer.writerow([])

        # 写入收入部分
        writer.writerow(["收入"])
        writer.writerow(["营业收入", f"¥{data['revenue']:,.2f}"])
        writer.writerow(["其他收入", f"¥{data.get('other_income', 0):,.2f}"])
        writer.writerow(["总收入", f"¥{data['total_revenue']:,.2f}"])
        writer.writerow([])

        # 写入成本部分
        writer.writerow(["成本"])
        writer.writerow(["营业成本", f"¥{data['cost_of_goods_sold']:,.2f}"])
        writer.writerow(["毛利润", f"¥{data['gross_profit']:,.2f}"])
        writer.writerow(["毛利率", f"{data['gross_profit_margin']:.2f}%"])
        writer.writerow([])

        # 写入费用部分
        writer.writerow(["费用"])
        writer.writerow(["人工成本", f"¥{data['labor_cost']:,.2f}"])
        writer.writerow(["租金", f"¥{data['rent']:,.2f}"])
        writer.writerow(["水电费", f"¥{data['utilities']:,.2f}"])
        writer.writerow(["营销费用", f"¥{data['marketing']:,.2f}"])
        writer.writerow(["其他费用", f"¥{data['other_expenses']:,.2f}"])
        writer.writerow(["总费用", f"¥{data['total_expenses']:,.2f}"])
        writer.writerow([])

        # 写入利润部分
        writer.writerow(["利润"])
        writer.writerow(["营业利润", f"¥{data['operating_profit']:,.2f}"])
        writer.writerow(["营业利润率", f"{data['operating_profit_margin']:.2f}%"])
        writer.writerow(["净利润", f"¥{data['net_profit']:,.2f}"])
        writer.writerow(["净利润率", f"{data['net_profit_margin']:.2f}%"])

        return output.getvalue().encode('utf-8-sig')

    def _generate_cash_flow_csv(
        self, data: Dict[str, Any], start_date: datetime, end_date: datetime
    ) -> bytes:
        """生成现金流量表CSV"""
        output = io.StringIO()
        writer = csv.writer(output)

        # 写入标题
        writer.writerow(["现金流量表"])
        writer.writerow([f"期间: {start_date.date()} 至 {end_date.date()}"])
        writer.writerow([])

        # 经营活动现金流
        writer.writerow(["经营活动现金流"])
        writer.writerow(["销售收入", f"¥{data['cash_from_sales']:,.2f}"])
        writer.writerow(["采购支出", f"¥{data['cash_for_purchases']:,.2f}"])
        writer.writerow(["工资支出", f"¥{data['cash_for_salaries']:,.2f}"])
        writer.writerow(["其他经营支出", f"¥{data['cash_for_operations']:,.2f}"])
        writer.writerow(["经营活动净现金流", f"¥{data['operating_cash_flow']:,.2f}"])
        writer.writerow([])

        # 投资活动现金流
        writer.writerow(["投资活动现金流"])
        writer.writerow(["设备采购", f"¥{data['cash_for_investments']:,.2f}"])
        writer.writerow(["投资活动净现金流", f"¥{data['investing_cash_flow']:,.2f}"])
        writer.writerow([])

        # 筹资活动现金流
        writer.writerow(["筹资活动现金流"])
        writer.writerow(["融资收入", f"¥{data['cash_from_financing']:,.2f}"])
        writer.writerow(["筹资活动净现金流", f"¥{data['financing_cash_flow']:,.2f}"])
        writer.writerow([])

        # 现金净变动
        writer.writerow(["现金净变动", f"¥{data['net_cash_flow']:,.2f}"])
        writer.writerow(["期初现金", f"¥{data['beginning_cash']:,.2f}"])
        writer.writerow(["期末现金", f"¥{data['ending_cash']:,.2f}"])

        return output.getvalue().encode('utf-8-sig')

    def _generate_transactions_csv(self, transactions: List[Dict[str, Any]]) -> bytes:
        """生成交易明细CSV"""
        output = io.StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow([
            "日期", "类型", "分类", "金额", "描述", "门店ID", "参考编号"
        ])

        # 写入数据
        for trans in transactions:
            writer.writerow([
                trans['transaction_date'].strftime('%Y-%m-%d %H:%M:%S'),
                trans['transaction_type'],
                trans['category'],
                f"¥{trans['amount']:,.2f}",
                trans.get('description', ''),
                trans.get('store_id', ''),
                trans.get('reference_number', '')
            ])

        return output.getvalue().encode('utf-8-sig')

    async def _get_transactions(
        self,
        start_date: datetime,
        end_date: datetime,
        store_id: Optional[int],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """获取交易明细"""
        query = select(FinancialTransaction).where(
            and_(
                FinancialTransaction.transaction_date >= start_date,
                FinancialTransaction.transaction_date <= end_date
            )
        )

        if store_id:
            query = query.where(FinancialTransaction.store_id == store_id)

        query = query.order_by(FinancialTransaction.transaction_date.desc())

        result = await db.execute(query)
        transactions = result.scalars().all()

        return [
            {
                "transaction_date": t.transaction_date,
                "transaction_type": t.transaction_type,
                "category": t.category,
                "amount": t.amount,
                "description": t.description,
                "store_id": t.store_id,
                "reference_number": t.reference_number
            }
            for t in transactions
        ]


# 全局实例
report_export_service = ReportExportService()
