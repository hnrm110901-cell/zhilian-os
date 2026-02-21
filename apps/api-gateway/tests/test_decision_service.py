"""
决策服务测试
Tests for Decision Service
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.services.decision_service import DecisionService


class TestDecisionService:
    """DecisionService测试类"""

    def test_init(self):
        """测试初始化"""
        service = DecisionService(store_id="STORE001")
        assert service.store_id == "STORE001"

    def test_init_default_store(self):
        """测试默认门店初始化"""
        service = DecisionService()
        assert service.store_id == "STORE001"

    @pytest.mark.asyncio
    @patch('src.services.decision_service.get_db_session')
    @patch('src.services.decision_service.KPIRepository')
    async def test_get_decision_report_with_dates(self, mock_kpi_repo, mock_get_session):
        """测试获取决策报告（指定日期）"""
        service = DecisionService()

        # Mock database session
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock KPI repository - make it async
        async def mock_get_all_active(session):
            return []
        mock_kpi_repo.get_all_active = mock_get_all_active

        start_date = "2024-01-01"
        end_date = "2024-01-31"

        result = await service.get_decision_report(start_date, end_date)

        assert result["store_id"] == "STORE001"
        assert result["period_start"] == "2024-01-01"
        assert result["period_end"] == "2024-01-31"
        assert "kpi_summary" in result
        assert "insights_summary" in result
        assert "recommendations_summary" in result
        assert "overall_health_score" in result

    @pytest.mark.asyncio
    @patch('src.services.decision_service.get_db_session')
    @patch('src.services.decision_service.KPIRepository')
    async def test_get_decision_report_no_dates(self, mock_kpi_repo, mock_get_session):
        """测试获取决策报告（无日期参数）"""
        service = DecisionService()

        # Mock database session
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock KPI repository - make it async
        async def mock_get_all_active(session):
            return []
        mock_kpi_repo.get_all_active = mock_get_all_active

        result = await service.get_decision_report()

        assert result["store_id"] == "STORE001"
        assert "period_start" in result
        assert "period_end" in result

    def test_calculate_kpi_summary_empty(self):
        """测试计算KPI摘要（空数据）"""
        service = DecisionService()
        kpis = []

        result = service._calculate_kpi_summary(kpis)

        assert result["total_kpis"] == 0
        assert result["on_track_rate"] == 0
        assert result["key_kpis"] == []

    def test_calculate_kpi_summary_with_data(self):
        """测试计算KPI摘要（有数据）"""
        service = DecisionService()
        kpis = [
            {"metric_id": "1", "metric_name": "KPI1", "status": "on_track"},
            {"metric_id": "2", "metric_name": "KPI2", "status": "on_track"},
            {"metric_id": "3", "metric_name": "KPI3", "status": "off_track"},
            {"metric_id": "4", "metric_name": "KPI4", "status": "at_risk"},
        ]

        result = service._calculate_kpi_summary(kpis)

        assert result["total_kpis"] == 4
        assert result["status_distribution"]["on_track"] == 2
        assert result["status_distribution"]["off_track"] == 1
        assert result["status_distribution"]["at_risk"] == 1
        assert result["on_track_rate"] == 0.5
        assert len(result["key_kpis"]) == 4

    def test_calculate_health_score_all_on_track(self):
        """测试计算健康分数（全部达标）"""
        service = DecisionService()
        kpis = [
            {"status": "on_track", "achievement_rate": 1.0},
            {"status": "on_track", "achievement_rate": 1.0},
        ]

        result = service._calculate_health_score(kpis)

        assert result >= 80  # Should be high score

    def test_calculate_health_score_mixed(self):
        """测试计算健康分数（混合状态）"""
        service = DecisionService()
        kpis = [
            {"status": "on_track", "achievement_rate": 1.0},
            {"status": "off_track", "achievement_rate": 0.5},
            {"status": "at_risk", "achievement_rate": 0.7},
        ]

        result = service._calculate_health_score(kpis)

        assert 0 <= result <= 100

    def test_calculate_health_score_empty(self):
        """测试计算健康分数（空数据）"""
        service = DecisionService()
        kpis = []

        result = service._calculate_health_score(kpis)

        assert result == 0.0  # Empty returns 0

    def test_generate_recommendations_empty(self):
        """测试生成建议（空数据）"""
        service = DecisionService()
        kpis = []
        insights = []

        result = service._generate_recommendations(kpis, insights)

        assert isinstance(result, list)

    def test_generate_recommendations_with_off_track_kpis(self):
        """测试生成建议（有未达标KPI）"""
        service = DecisionService()
        kpis = [
            {
                "metric_id": "1",
                "metric_name": "销售额",
                "status": "off_track",
                "achievement_rate": 0.6,
                "current_value": 60000,
                "target_value": 100000,
                "unit": "元",
                "category": "sales",
            }
        ]
        insights = []

        result = service._generate_recommendations(kpis, insights)

        assert len(result) > 0
        # Should have recommendations for off-track KPIs

    def test_count_by_priority(self):
        """测试按优先级统计"""
        service = DecisionService()
        recommendations = [
            {"priority": "critical"},
            {"priority": "high"},
            {"priority": "high"},
            {"priority": "medium"},
        ]

        result = service._count_by_priority(recommendations)

        assert result["critical"] == 1
        assert result["high"] == 2
        assert result["medium"] == 1

    @pytest.mark.asyncio
    @patch('src.services.decision_service.KPIRepository')
    async def test_get_kpis_from_db_no_kpis(self, mock_kpi_repo):
        """测试从数据库获取KPI（无KPI定义）"""
        service = DecisionService()

        mock_session = AsyncMock(spec=AsyncSession)

        # Make it async
        async def mock_get_all_active(session):
            return []
        mock_kpi_repo.get_all_active = mock_get_all_active

        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)

        result = await service._get_kpis_from_db(mock_session, start_date, end_date)

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_insights_from_db_empty(self):
        """测试生成洞察（空数据）"""
        service = DecisionService()

        mock_session = AsyncMock(spec=AsyncSession)
        kpis = []

        result = await service._generate_insights_from_db(mock_session, kpis)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_generate_insights_from_db_with_off_track(self):
        """测试生成洞察（有未达标KPI）"""
        service = DecisionService()

        mock_session = AsyncMock(spec=AsyncSession)
        kpis = [
            {
                "metric_id": "1",
                "metric_name": "销售额",
                "status": "off_track",
                "current_value": 60000,
                "target_value": 100000,
                "achievement_rate": 0.6,
                "unit": "元",
                "category": "sales",
            }
        ]

        result = await service._generate_insights_from_db(mock_session, kpis)

        assert len(result) > 0
        assert result[0]["title"] == "销售额未达标"

