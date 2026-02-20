"""
培训服务测试
Tests for Training Service
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.training_service import TrainingService


class TestTrainingService:
    """TrainingService测试类"""

    def test_init(self):
        """测试初始化"""
        service = TrainingService(store_id="STORE001")
        assert service.store_id == "STORE001"
        assert service.training_config["min_passing_score"] == 70

    @pytest.mark.asyncio
    @patch('src.services.training_service.get_db_session')
    async def test_assess_training_needs_no_filters(self, mock_get_session):
        """测试评估培训需求（无过滤）"""
        service = TrainingService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock employees
        mock_employee = MagicMock()
        mock_employee.id = "EMP001"
        mock_employee.name = "张三"
        mock_employee.position = "服务员"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_employee]
        mock_session.execute.return_value = mock_result

        result = await service.assess_training_needs()

        assert isinstance(result, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.training_service.get_db_session')
    async def test_assess_training_needs_with_staff_id(self, mock_get_session):
        """测试评估培训需求（指定员工）"""
        service = TrainingService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.assess_training_needs(staff_id="EMP001")

        assert isinstance(result, list)

    def test_identify_training_needs(self):
        """测试识别培训需求"""
        service = TrainingService()

        mock_employee = MagicMock()
        mock_employee.id = "EMP001"
        mock_employee.name = "张三"
        mock_employee.position = "服务员"

        result = service._identify_training_needs(mock_employee)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch('src.services.training_service.get_db_session')
    async def test_record_training_completion(self, mock_get_session):
        """测试记录培训完成"""
        service = TrainingService()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock KPI query
        mock_kpi_result = MagicMock()
        mock_kpi_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_kpi_result

        result = await service.record_training_completion(
            staff_id="EMP001",
            course_name="服务技能培训",
            completion_date="2024-01-15",
            score=85
        )

        assert result["success"] is True
        assert result["staff_id"] == "EMP001"
