"""
报表导出服务测试
Tests for Report Export Service
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.report_export_service import ReportExportService


class TestReportExportService:
    """ReportExportService测试类"""

    def test_init(self):
        """测试初始化"""
        service = ReportExportService()
        assert service is not None

    @pytest.mark.asyncio
    @patch('src.services.report_export_service.FinanceService')
    async def test_export_to_csv_income_statement(self, mock_finance_service_cls):
        """测试导出损益表CSV"""
        service = ReportExportService()

        # Mock FinanceService
        mock_finance_service = MagicMock()
        mock_finance_service.get_income_statement = AsyncMock(return_value={
            "revenue": 100000,
            "other_income": 5000,
            "total_revenue": 105000,
            "cost_of_goods": 60000,
            "gross_profit": 45000,
            "operating_expenses": 20000,
            "net_profit": 25000,
        })
        mock_finance_service_cls.return_value = mock_finance_service

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        result = await service.export_to_csv(
            "income_statement", start_date, end_date
        )

        assert isinstance(result, bytes)
        content = result.decode('utf-8-sig')
        assert "损益表" in content
        assert "100,000" in content

    @pytest.mark.asyncio
    @patch('src.services.report_export_service.FinanceService')
    async def test_export_to_csv_cash_flow(self, mock_finance_service_cls):
        """测试导出现金流量表CSV"""
        service = ReportExportService()

        # Mock FinanceService
        mock_finance_service = MagicMock()
        mock_finance_service.get_cash_flow_statement = AsyncMock(return_value={
            "operating_cash_flow": 50000,
            "investing_cash_flow": -20000,
            "financing_cash_flow": 10000,
            "net_cash_flow": 40000,
        })
        mock_finance_service_cls.return_value = mock_finance_service

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        result = await service.export_to_csv(
            "cash_flow", start_date, end_date
        )

        assert isinstance(result, bytes)
        content = result.decode('utf-8-sig')
        assert "现金流量表" in content

    @pytest.mark.asyncio
    async def test_export_to_csv_invalid_type(self):
        """测试导出无效报表类型"""
        service = ReportExportService()

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        with pytest.raises(ValueError, match="不支持的报表类型"):
            await service.export_to_csv(
                "invalid_type", start_date, end_date
            )

    def test_generate_income_statement_csv(self):
        """测试生成损益表CSV"""
        service = ReportExportService()

        data = {
            "revenue": 100000,
            "other_income": 5000,
            "total_revenue": 105000,
            "cost_of_goods": 60000,
            "gross_profit": 45000,
            "operating_expenses": 20000,
            "net_profit": 25000,
        }
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        result = service._generate_income_statement_csv(data, start_date, end_date)

        assert isinstance(result, bytes)
        content = result.decode('utf-8-sig')
        assert "损益表" in content
        assert "营业收入" in content

    def test_generate_cash_flow_csv(self):
        """测试生成现金流量表CSV"""
        service = ReportExportService()

        data = {
            "operating_cash_flow": 50000,
            "investing_cash_flow": -20000,
            "financing_cash_flow": 10000,
            "net_cash_flow": 40000,
        }
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        result = service._generate_cash_flow_csv(data, start_date, end_date)

        assert isinstance(result, bytes)
        content = result.decode('utf-8-sig')
        assert "现金流量表" in content

    def test_generate_transactions_csv(self):
        """测试生成交易记录CSV"""
        service = ReportExportService()

        data = [
            {
                "id": 1,
                "transaction_date": datetime(2024, 1, 15),
                "type": "income",
                "amount": 1000,
                "description": "销售收入",
            },
            {
                "id": 2,
                "transaction_date": datetime(2024, 1, 16),
                "type": "expense",
                "amount": 500,
                "description": "采购支出",
            },
        ]

        result = service._generate_transactions_csv(data)

        assert isinstance(result, bytes)
        content = result.decode('utf-8-sig')
        assert "交易记录" in content
        assert "销售收入" in content

    @pytest.mark.asyncio
    @patch('src.services.report_export_service.FinanceService')
    async def test_export_to_csv_with_store_id(self, mock_finance_service_cls):
        """测试指定门店导出"""
        service = ReportExportService()

        mock_finance_service = MagicMock()
        mock_finance_service.get_income_statement = AsyncMock(return_value={
            "revenue": 50000,
            "total_revenue": 50000,
            "cost_of_goods": 30000,
            "gross_profit": 20000,
            "operating_expenses": 10000,
            "net_profit": 10000,
        })
        mock_finance_service_cls.return_value = mock_finance_service

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        result = await service.export_to_csv(
            "income_statement", start_date, end_date, store_id=1
        )

        assert isinstance(result, bytes)
