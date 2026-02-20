"""
财务服务测试
Tests for Finance Service
"""
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.services.finance_service import FinanceService, get_finance_service
from src.models.finance import FinancialTransaction, Budget


class TestFinanceService:
    """FinanceService测试类"""

    def test_init(self):
        """测试服务初始化"""
        mock_db = AsyncMock(spec=AsyncSession)
        service = FinanceService(mock_db)
        assert service.db == mock_db

    @pytest.mark.asyncio
    async def test_create_transaction(self):
        """测试创建财务交易"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock transaction
        mock_transaction = MagicMock(spec=FinancialTransaction)
        mock_transaction.id = uuid.uuid4()
        mock_transaction.transaction_type = "income"
        mock_transaction.category = "sales"
        mock_transaction.amount = 1000.0

        # Mock refresh to set attributes
        async def mock_refresh(obj):
            obj.id = mock_transaction.id
            obj.transaction_type = mock_transaction.transaction_type
            obj.category = mock_transaction.category
            obj.amount = mock_transaction.amount

        mock_db.refresh = mock_refresh

        service = FinanceService(mock_db)
        data = {
            "store_id": "STORE001",
            "transaction_date": date(2026, 3, 1),
            "transaction_type": "income",
            "category": "sales",
            "amount": 1000.0,
            "description": "Daily sales",
            "payment_method": "cash"
        }

        result = await service.create_transaction(data)

        assert "id" in result
        assert result["transaction_type"] == "income"
        assert result["category"] == "sales"
        assert result["amount"] == 1000.0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transactions_no_filters(self):
        """测试获取交易列表（无过滤）"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock transactions
        mock_transaction = MagicMock(spec=FinancialTransaction)
        mock_transaction.id = uuid.uuid4()
        mock_transaction.store_id = "STORE001"
        mock_transaction.transaction_date = date(2026, 3, 1)
        mock_transaction.transaction_type = "income"
        mock_transaction.category = "sales"
        mock_transaction.subcategory = None
        mock_transaction.amount = 1000.0
        mock_transaction.description = "Daily sales"
        mock_transaction.payment_method = "cash"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_transaction]
        mock_db.execute.return_value = mock_result

        service = FinanceService(mock_db)
        result = await service.get_transactions()

        assert "transactions" in result
        assert len(result["transactions"]) == 1
        assert result["transactions"][0]["transaction_type"] == "income"
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_get_transactions_with_filters(self):
        """测试获取交易列表（带过滤）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = FinanceService(mock_db)
        result = await service.get_transactions(
            store_id="STORE001",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            transaction_type="income",
            category="sales"
        )

        assert result["transactions"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_generate_income_statement(self):
        """测试生成损益表"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock income query result
        income_result = MagicMock()
        income_result.scalar.return_value = 10000.0

        # Mock expense query results
        expense_results = [
            MagicMock(scalar=lambda: 3000.0),  # food_cost
            MagicMock(scalar=lambda: 2000.0),  # labor_cost
            MagicMock(scalar=lambda: 1000.0),  # rent
            MagicMock(scalar=lambda: 500.0),   # utilities
            MagicMock(scalar=lambda: 300.0),   # marketing
            MagicMock(scalar=lambda: 200.0),   # other_expense
        ]

        mock_db.execute.side_effect = [income_result] + expense_results

        service = FinanceService(mock_db)
        result = await service.generate_income_statement(
            "STORE001",
            date(2026, 3, 1),
            date(2026, 3, 31)
        )

        assert result["store_id"] == "STORE001"
        assert result["revenue"]["total"] == 10000.0
        assert result["total_expenses"] == 7000.0
        assert result["profit"]["gross_profit"] == 7000.0
        assert result["profit"]["operating_profit"] == 3000.0
        assert result["margins"]["gross_margin"] == 70.0

    @pytest.mark.asyncio
    async def test_generate_cash_flow(self):
        """测试生成现金流量表"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock cash flow data
        mock_row1 = MagicMock()
        mock_row1.transaction_date = date(2026, 3, 1)
        mock_row1.transaction_type = "income"
        mock_row1.total = 5000.0

        mock_row2 = MagicMock()
        mock_row2.transaction_date = date(2026, 3, 1)
        mock_row2.transaction_type = "expense"
        mock_row2.total = 2000.0

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row1, mock_row2]
        mock_db.execute.return_value = mock_result

        service = FinanceService(mock_db)
        result = await service.generate_cash_flow(
            "STORE001",
            date(2026, 3, 1),
            date(2026, 3, 31)
        )

        assert result["store_id"] == "STORE001"
        assert "cash_flow" in result
        assert "2026-03-01" in result["cash_flow"]
        assert result["cash_flow"]["2026-03-01"]["inflow"] == 5000.0
        assert result["cash_flow"]["2026-03-01"]["outflow"] == 2000.0
        assert result["cash_flow"]["2026-03-01"]["net"] == 3000.0

    @pytest.mark.asyncio
    async def test_create_budget(self):
        """测试创建预算"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock budget
        mock_budget = MagicMock(spec=Budget)
        mock_budget.id = uuid.uuid4()
        mock_budget.category = "food_cost"
        mock_budget.budgeted_amount = 5000.0

        async def mock_refresh(obj):
            obj.id = mock_budget.id
            obj.category = mock_budget.category
            obj.budgeted_amount = mock_budget.budgeted_amount

        mock_db.refresh = mock_refresh

        service = FinanceService(mock_db)
        data = {
            "store_id": "STORE001",
            "year": 2026,
            "month": 3,
            "category": "food_cost",
            "budgeted_amount": 5000.0,
            "notes": "Monthly food budget"
        }

        result = await service.create_budget(data)

        assert "id" in result
        assert result["category"] == "food_cost"
        assert result["budgeted_amount"] == 5000.0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_budget_analysis(self):
        """测试获取预算分析"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock budget
        mock_budget = MagicMock(spec=Budget)
        mock_budget.category = "food_cost"
        mock_budget.budgeted_amount = 5000.0
        mock_budget.actual_amount = 0
        mock_budget.variance = 0
        mock_budget.variance_percentage = 0

        # Mock budget query result
        budget_result = MagicMock()
        budget_result.scalars.return_value.all.return_value = [mock_budget]

        # Mock actual amount query result
        actual_result = MagicMock()
        actual_result.scalar.return_value = 4500.0

        mock_db.execute.side_effect = [budget_result, actual_result]

        service = FinanceService(mock_db)
        result = await service.get_budget_analysis("STORE001", 2026, 3)

        assert result["store_id"] == "STORE001"
        assert result["year"] == 2026
        assert result["month"] == 3
        assert len(result["analysis"]) == 1
        assert result["analysis"][0]["category"] == "food_cost"
        assert result["analysis"][0]["budgeted_amount"] == 5000.0
        assert result["analysis"][0]["actual_amount"] == 4500.0

    @pytest.mark.asyncio
    async def test_get_financial_metrics(self):
        """测试获取财务指标"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock income statement data
        income_result = MagicMock()
        income_result.scalar.return_value = 10000.0

        expense_results = [
            MagicMock(scalar=lambda: 3000.0),  # food_cost
            MagicMock(scalar=lambda: 2000.0),  # labor_cost
            MagicMock(scalar=lambda: 1000.0),  # rent
            MagicMock(scalar=lambda: 500.0),   # utilities
            MagicMock(scalar=lambda: 300.0),   # marketing
            MagicMock(scalar=lambda: 200.0),   # other_expense
        ]

        mock_db.execute.side_effect = [income_result] + expense_results

        service = FinanceService(mock_db)
        result = await service.get_financial_metrics(
            "STORE001",
            date(2026, 3, 1),
            date(2026, 3, 31)
        )

        assert result["store_id"] == "STORE001"
        assert "metrics" in result
        assert result["metrics"]["total_revenue"] == 10000.0
        assert result["metrics"]["food_cost_ratio"] == 30.0
        assert result["metrics"]["labor_cost_ratio"] == 20.0
        assert result["metrics"]["prime_cost_ratio"] == 50.0


class TestGlobalFunction:
    """测试全局函数"""

    def test_get_finance_service(self):
        """测试get_finance_service函数"""
        mock_db = AsyncMock(spec=AsyncSession)
        service = get_finance_service(mock_db)
        assert isinstance(service, FinanceService)
        assert service.db == mock_db
