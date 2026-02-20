"""
服务质量服务测试
Tests for Service Quality Service
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.service_service import ServiceQualityService


class TestServiceQualityService:
    """ServiceQualityService测试类"""

    def test_init(self):
        """测试初始化"""
        service = ServiceQualityService(store_id="STORE001")
        assert service.store_id == "STORE001"

    def test_init_default_store(self):
        """测试默认门店初始化"""
        service = ServiceQualityService()
        assert service.store_id == "STORE001"

    @pytest.mark.asyncio
    @patch('src.services.service_service.get_db_session')
    async def test_get_service_quality_metrics_with_dates(self, mock_get_session):
        """测试获取服务质量指标（指定日期）"""
        service = ServiceQualityService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock satisfaction records
        mock_satisfaction_result = MagicMock()
        mock_satisfaction_result.scalars.return_value.all.return_value = []

        # Mock orders
        mock_orders_result = MagicMock()
        mock_orders_result.scalars.return_value.all.return_value = []

        # Mock employee performance
        mock_employee_result = MagicMock()
        mock_employee_result.all.return_value = []

        mock_session.execute.side_effect = [
            mock_satisfaction_result,
            mock_orders_result,
            mock_employee_result
        ]

        start_date = "2024-01-01T00:00:00"
        end_date = "2024-01-07T23:59:59"

        result = await service.get_service_quality_metrics(start_date, end_date)

        assert "customer_satisfaction" in result
        assert "service_efficiency" in result
        assert "employee_performance" in result

    @pytest.mark.asyncio
    @patch('src.services.service_service.get_db_session')
    async def test_get_service_quality_metrics_no_dates(self, mock_get_session):
        """测试获取服务质量指标（无日期参数）"""
        service = ServiceQualityService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_satisfaction_result = MagicMock()
        mock_satisfaction_result.scalars.return_value.all.return_value = []

        mock_orders_result = MagicMock()
        mock_orders_result.scalars.return_value.all.return_value = []

        mock_employee_result = MagicMock()
        mock_employee_result.all.return_value = []

        mock_session.execute.side_effect = [
            mock_satisfaction_result,
            mock_orders_result,
            mock_employee_result
        ]

        result = await service.get_service_quality_metrics()

        assert isinstance(result, dict)
        assert "customer_satisfaction" in result

    def test_calculate_trend_increasing(self):
        """测试计算趋势（上升）"""
        service = ServiceQualityService()
        values = [70, 75, 80, 85, 90]

        result = service._calculate_trend(values)

        assert result == "increasing"

    def test_calculate_trend_decreasing(self):
        """测试计算趋势（下降）"""
        service = ServiceQualityService()
        values = [90, 85, 80, 75, 70]

        result = service._calculate_trend(values)

        assert result == "decreasing"

    def test_calculate_trend_stable(self):
        """测试计算趋势（稳定）"""
        service = ServiceQualityService()
        values = [80, 81, 80, 79, 80]

        result = service._calculate_trend(values)

        assert result == "stable"

    def test_calculate_trend_empty(self):
        """测试计算趋势（空数据）"""
        service = ServiceQualityService()
        values = []

        result = service._calculate_trend(values)

        assert result == "stable"

    def test_calculate_trend_single_value(self):
        """测试计算趋势（单个值）"""
        service = ServiceQualityService()
        values = [80]

        result = service._calculate_trend(values)

        assert result == "stable"

    @pytest.mark.asyncio
    @patch('src.services.service_service.get_db_session')
    async def test_analyze_customer_feedback(self, mock_get_session):
        """测试分析客户反馈"""
        service = ServiceQualityService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock KPI records
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.analyze_customer_feedback()

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    @patch('src.services.service_service.get_db_session')
    async def test_get_employee_service_performance(self, mock_get_session):
        """测试获取员工服务表现"""
        service = ServiceQualityService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock employee data
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.get_employee_service_performance()

        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch('src.services.service_service.get_db_session')
    async def test_identify_service_issues(self, mock_get_session):
        """测试识别服务问题"""
        service = ServiceQualityService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock KPI records with low values
        mock_kpi_record = MagicMock()
        mock_kpi_record.value = 60
        mock_kpi_record.target_value = 80
        mock_kpi_record.kpi = MagicMock()
        mock_kpi_record.kpi.name = "客户满意度"
        mock_kpi_record.kpi.category = "customer"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_kpi_record]
        mock_session.execute.return_value = mock_result

        result = await service.identify_service_issues()

        assert isinstance(result, list)
