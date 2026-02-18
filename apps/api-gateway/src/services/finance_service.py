"""
财务服务
管理财务交易、预算、发票、报表
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from calendar import monthrange
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, extract

from src.models import (
    FinancialTransaction, Budget, Invoice, FinancialReport,
    Store, Supplier
)
from src.core.exceptions import NotFoundError, ValidationError

logger = structlog.get_logger()


class FinanceService:
    """财务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_transaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建财务交易记录"""
        transaction = FinancialTransaction(
            store_id=data["store_id"],
            transaction_date=data["transaction_date"],
            transaction_type=data["transaction_type"],
            category=data["category"],
            subcategory=data.get("subcategory"),
            amount=data["amount"],
            description=data.get("description"),
            reference_id=data.get("reference_id"),
            payment_method=data.get("payment_method"),
            created_by=data.get("created_by"),
        )

        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info("transaction_created", transaction_id=transaction.id, amount=transaction.amount)

        return {
            "id": transaction.id,
            "transaction_type": transaction.transaction_type,
            "category": transaction.category,
            "amount": transaction.amount,
        }

    async def get_transactions(
        self,
        store_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        transaction_type: Optional[str] = None,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """获取财务交易记录列表"""
        query = select(FinancialTransaction)

        if store_id:
            query = query.where(FinancialTransaction.store_id == store_id)
        if start_date:
            query = query.where(FinancialTransaction.transaction_date >= start_date)
        if end_date:
            query = query.where(FinancialTransaction.transaction_date <= end_date)
        if transaction_type:
            query = query.where(FinancialTransaction.transaction_type == transaction_type)
        if category:
            query = query.where(FinancialTransaction.category == category)

        query = query.order_by(FinancialTransaction.transaction_date.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        transactions = result.scalars().all()

        return {
            "transactions": [
                {
                    "id": t.id,
                    "store_id": t.store_id,
                    "transaction_date": t.transaction_date.isoformat(),
                    "transaction_type": t.transaction_type,
                    "category": t.category,
                    "subcategory": t.subcategory,
                    "amount": t.amount,
                    "description": t.description,
                    "payment_method": t.payment_method,
                }
                for t in transactions
            ],
            "total": len(transactions),
        }

    async def generate_income_statement(
        self, store_id: str, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """生成损益表"""
        # 查询收入
        income_query = select(
            func.sum(FinancialTransaction.amount)
        ).where(
            and_(
                FinancialTransaction.store_id == store_id,
                FinancialTransaction.transaction_date >= start_date,
                FinancialTransaction.transaction_date <= end_date,
                FinancialTransaction.transaction_type == "income",
            )
        )
        income_result = await self.db.execute(income_query)
        total_revenue = income_result.scalar() or 0

        # 查询各类成本
        categories = ["food_cost", "labor_cost", "rent", "utilities", "marketing", "other_expense"]
        expenses = {}
        total_expenses = 0

        for category in categories:
            expense_query = select(
                func.sum(FinancialTransaction.amount)
            ).where(
                and_(
                    FinancialTransaction.store_id == store_id,
                    FinancialTransaction.transaction_date >= start_date,
                    FinancialTransaction.transaction_date <= end_date,
                    FinancialTransaction.transaction_type == "expense",
                    FinancialTransaction.category == category,
                )
            )
            expense_result = await self.db.execute(expense_query)
            amount = expense_result.scalar() or 0
            expenses[category] = amount
            total_expenses += amount

        # 计算利润
        gross_profit = total_revenue - expenses.get("food_cost", 0)
        operating_profit = total_revenue - total_expenses
        net_profit = operating_profit  # 简化版，实际应考虑税费等

        # 计算比率
        gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        operating_margin = (operating_profit / total_revenue * 100) if total_revenue > 0 else 0
        net_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0

        return {
            "store_id": store_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "revenue": {
                "total": total_revenue,
            },
            "expenses": expenses,
            "total_expenses": total_expenses,
            "profit": {
                "gross_profit": gross_profit,
                "operating_profit": operating_profit,
                "net_profit": net_profit,
            },
            "margins": {
                "gross_margin": round(gross_margin, 2),
                "operating_margin": round(operating_margin, 2),
                "net_margin": round(net_margin, 2),
            },
        }

    async def generate_cash_flow(
        self, store_id: str, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """生成现金流量表"""
        # 按日期分组统计现金流入和流出
        query = select(
            FinancialTransaction.transaction_date,
            FinancialTransaction.transaction_type,
            func.sum(FinancialTransaction.amount).label("total")
        ).where(
            and_(
                FinancialTransaction.store_id == store_id,
                FinancialTransaction.transaction_date >= start_date,
                FinancialTransaction.transaction_date <= end_date,
            )
        ).group_by(
            FinancialTransaction.transaction_date,
            FinancialTransaction.transaction_type
        ).order_by(FinancialTransaction.transaction_date)

        result = await self.db.execute(query)
        rows = result.all()

        # 组织数据
        cash_flow_data = {}
        for row in rows:
            date_str = row.transaction_date.isoformat()
            if date_str not in cash_flow_data:
                cash_flow_data[date_str] = {"inflow": 0, "outflow": 0, "net": 0}

            if row.transaction_type == "income":
                cash_flow_data[date_str]["inflow"] = row.total
            else:
                cash_flow_data[date_str]["outflow"] = row.total

            cash_flow_data[date_str]["net"] = (
                cash_flow_data[date_str]["inflow"] - cash_flow_data[date_str]["outflow"]
            )

        # 计算累计现金流
        cumulative = 0
        for date_str in sorted(cash_flow_data.keys()):
            cumulative += cash_flow_data[date_str]["net"]
            cash_flow_data[date_str]["cumulative"] = cumulative

        return {
            "store_id": store_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "cash_flow": cash_flow_data,
        }

    async def create_budget(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建预算"""
        budget = Budget(
            store_id=data["store_id"],
            year=data["year"],
            month=data["month"],
            category=data["category"],
            budgeted_amount=data["budgeted_amount"],
            notes=data.get("notes"),
            created_by=data.get("created_by"),
        )

        self.db.add(budget)
        await self.db.commit()
        await self.db.refresh(budget)

        logger.info("budget_created", budget_id=budget.id, category=budget.category)

        return {
            "id": budget.id,
            "category": budget.category,
            "budgeted_amount": budget.budgeted_amount,
        }

    async def get_budget_analysis(
        self, store_id: str, year: int, month: int
    ) -> Dict[str, Any]:
        """获取预算分析"""
        # 查询预算
        budget_query = select(Budget).where(
            and_(
                Budget.store_id == store_id,
                Budget.year == year,
                Budget.month == month,
            )
        )
        budget_result = await self.db.execute(budget_query)
        budgets = budget_result.scalars().all()

        # 查询实际支出
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        analysis = []
        for budget in budgets:
            # 查询该类别的实际金额
            actual_query = select(
                func.sum(FinancialTransaction.amount)
            ).where(
                and_(
                    FinancialTransaction.store_id == store_id,
                    FinancialTransaction.transaction_date >= start_date,
                    FinancialTransaction.transaction_date <= end_date,
                    FinancialTransaction.category == budget.category,
                )
            )
            actual_result = await self.db.execute(actual_query)
            actual_amount = actual_result.scalar() or 0

            # 更新预算记录
            budget.actual_amount = actual_amount
            budget.variance = actual_amount - budget.budgeted_amount
            budget.variance_percentage = (
                (budget.variance / budget.budgeted_amount * 100)
                if budget.budgeted_amount > 0 else 0
            )

            analysis.append({
                "category": budget.category,
                "budgeted_amount": budget.budgeted_amount,
                "actual_amount": actual_amount,
                "variance": budget.variance,
                "variance_percentage": round(budget.variance_percentage, 2),
                "status": "over" if budget.variance > 0 else "under" if budget.variance < 0 else "on_track",
            })

        await self.db.commit()

        return {
            "store_id": store_id,
            "year": year,
            "month": month,
            "analysis": analysis,
        }

    async def get_financial_metrics(
        self, store_id: str, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """获取财务指标"""
        # 生成损益表
        income_statement = await self.generate_income_statement(store_id, start_date, end_date)

        # 计算额外指标
        total_revenue = income_statement["revenue"]["total"]
        food_cost = income_statement["expenses"].get("food_cost", 0)
        labor_cost = income_statement["expenses"].get("labor_cost", 0)

        # 食材成本率
        food_cost_ratio = (food_cost / total_revenue * 100) if total_revenue > 0 else 0

        # 人力成本率
        labor_cost_ratio = (labor_cost / total_revenue * 100) if total_revenue > 0 else 0

        # 综合成本率
        prime_cost = food_cost + labor_cost
        prime_cost_ratio = (prime_cost / total_revenue * 100) if total_revenue > 0 else 0

        return {
            "store_id": store_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "metrics": {
                "total_revenue": total_revenue,
                "net_profit": income_statement["profit"]["net_profit"],
                "gross_margin": income_statement["margins"]["gross_margin"],
                "net_margin": income_statement["margins"]["net_margin"],
                "food_cost_ratio": round(food_cost_ratio, 2),
                "labor_cost_ratio": round(labor_cost_ratio, 2),
                "prime_cost_ratio": round(prime_cost_ratio, 2),
            },
        }


# 全局服务实例
def get_finance_service(db: AsyncSession) -> FinanceService:
    """获取财务服务实例"""
    return FinanceService(db)
