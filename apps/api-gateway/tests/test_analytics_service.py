"""
高级分析服务测试
Tests for Analytics Service
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.services.analytics_service import AnalyticsService, get_analytics_service
from src.models.finance import FinancialTransaction
from src.models.order import Order
from src.core.exceptions import ValidationError


class TestAnalyticsService:
    """AnalyticsService测试类"""

    def test_init(self):
        """测试服务初始化"""
        mock_db = AsyncMock(spec=AsyncSession)
        service = AnalyticsService(mock_db)
        assert service.db == mock_db

    @pytest.mark.asyncio
    async def test_predict_sales_with_data(self):
        """测试销售预测（有数据）"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock historical data
        mock_data = []
        for i in range(30):
            mock_row = MagicMock()
            mock_row.date = date.today() - timedelta(days=30-i)
            mock_row.revenue = 1000.0 + i * 10
            mock_row.transactions = 50 + i
            mock_data.append(mock_row)

        mock_result = MagicMock()
        mock_result.all.return_value = mock_data
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.predict_sales("STORE001", days_ahead=7)

        assert result["store_id"] == "STORE001"
        assert len(result["predictions"]) == 7
        assert "trend" in result
        assert "average_daily_revenue" in result
        assert result["predictions"][0]["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_predict_sales_no_data(self):
        """测试销售预测（无数据）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.predict_sales("STORE001", days_ahead=7)

        assert result["store_id"] == "STORE001"
        assert result["predictions"] == []
        assert result["confidence"] == "low"
        assert "历史数据不足" in result["message"]

    @pytest.mark.asyncio
    async def test_detect_anomalies_revenue(self):
        """测试异常检测（收入）"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock data with one anomaly
        mock_data = []
        for i in range(30):
            mock_row = MagicMock()
            mock_row.date = date.today() - timedelta(days=30-i)
            # Normal values around 1000, with one spike
            mock_row.value = 5000.0 if i == 15 else 1000.0
            mock_data.append(mock_row)

        mock_result = MagicMock()
        mock_result.all.return_value = mock_data
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.detect_anomalies("STORE001", metric="revenue", days=30)

        assert result["store_id"] == "STORE001"
        assert result["metric"] == "revenue"
        assert "statistics" in result
        assert "anomalies" in result
        assert result["anomaly_count"] >= 0

    @pytest.mark.asyncio
    async def test_detect_anomalies_cost(self):
        """测试异常检测（成本）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_data = []
        for i in range(30):
            mock_row = MagicMock()
            mock_row.date = date.today() - timedelta(days=30-i)
            mock_row.value = 500.0
            mock_data.append(mock_row)

        mock_result = MagicMock()
        mock_result.all.return_value = mock_data
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.detect_anomalies("STORE001", metric="cost", days=30)

        assert result["metric"] == "cost"
        assert "statistics" in result

    @pytest.mark.asyncio
    async def test_detect_anomalies_insufficient_data(self):
        """测试异常检测（数据不足）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.all.return_value = [MagicMock(date=date.today(), value=100.0)]
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.detect_anomalies("STORE001", metric="revenue", days=30)

        assert result["anomalies"] == []
        assert "数据不足" in result["message"]

    @pytest.mark.asyncio
    async def test_detect_anomalies_invalid_metric(self):
        """测试异常检测（无效指标）"""
        mock_db = AsyncMock(spec=AsyncSession)
        service = AnalyticsService(mock_db)

        with pytest.raises(ValidationError, match="不支持的指标类型"):
            await service.detect_anomalies("STORE001", metric="invalid", days=30)

    @pytest.mark.asyncio
    async def test_analyze_associations_with_data(self):
        """测试关联分析（有数据）"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock orders with items
        mock_orders = []
        for i in range(20):
            mock_order = MagicMock(spec=Order)
            mock_order.items = [
                {"name": "汉堡", "quantity": 1},
                {"name": "可乐", "quantity": 1}
            ]
            mock_orders.append(mock_order)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_orders
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.analyze_associations("STORE001", min_support=0.1)

        assert result["store_id"] == "STORE001"
        assert result["total_orders"] == 20
        assert "associations" in result
        assert result["unique_items"] == 2

    @pytest.mark.asyncio
    async def test_analyze_associations_insufficient_orders(self):
        """测试关联分析（订单不足）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.analyze_associations("STORE001")

        assert result["associations"] == []
        assert "订单数据不足" in result["message"]

    @pytest.mark.asyncio
    async def test_analyze_time_patterns(self):
        """测试时段分析"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock time pattern data
        mock_data = []
        for hour in range(8, 22):  # 8am to 10pm
            mock_row = MagicMock()
            mock_row.hour = hour
            mock_row.day_of_week = 1
            mock_row.revenue = 500.0 if 11 <= hour < 14 else 300.0
            mock_row.transactions = 20 if 11 <= hour < 14 else 10
            mock_data.append(mock_row)

        mock_result = MagicMock()
        mock_result.all.return_value = mock_data
        mock_db.execute.return_value = mock_result

        service = AnalyticsService(mock_db)
        result = await service.analyze_time_patterns("STORE001", days=30)

        assert result["store_id"] == "STORE001"
        assert "hourly_analysis" in result
        assert "peak_hours" in result
        assert "insights" in result

    def test_generate_time_insights_no_data(self):
        """测试生成时段洞察（无数据）"""
        service = AnalyticsService(AsyncMock())
        insights = service._generate_time_insights([])

        assert len(insights) == 1
        assert "数据不足" in insights[0]

    def test_generate_time_insights_with_data(self):
        """测试生成时段洞察（有数据）"""
        service = AnalyticsService(AsyncMock())

        hourly_analysis = [
            {"hour": 12, "period": "午餐", "avg_revenue": 1000, "avg_transactions": 50},
            {"hour": 19, "period": "晚餐", "avg_revenue": 1500, "avg_transactions": 60},
            {"hour": 15, "period": "下午茶", "avg_revenue": 300, "avg_transactions": 10}
        ]

        insights = service._generate_time_insights(hourly_analysis)

        assert len(insights) >= 2
        assert any("最繁忙时段" in i for i in insights)
        assert any("最清闲时段" in i for i in insights)


class TestGlobalFunction:
    """测试全局函数"""

    def test_get_analytics_service(self):
        """测试get_analytics_service函数"""
        mock_db = AsyncMock(spec=AsyncSession)
        service = get_analytics_service(mock_db)
        assert isinstance(service, AnalyticsService)
        assert service.db == mock_db
