"""
排班服务测试
Tests for Schedule Service
"""
import pytest
from datetime import datetime, date, time
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.services.schedule_service import ScheduleService, schedule_service
from src.models.schedule import Schedule, Shift


class TestScheduleService:
    """ScheduleService测试类"""

    def test_init(self):
        """测试服务初始化"""
        service = ScheduleService()
        assert service.store_id == "STORE001"

        service_custom = ScheduleService(store_id="STORE002")
        assert service_custom.store_id == "STORE002"

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_create_schedule_new(self, mock_get_session):
        """测试创建新排班"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock schedule object
        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.id = uuid.uuid4()
        mock_schedule.store_id = "STORE001"
        mock_schedule.schedule_date = date(2026, 3, 1)
        mock_schedule.total_employees = "2"
        mock_schedule.total_hours = "16.0"
        mock_schedule.is_published = False
        mock_schedule.published_by = None
        mock_schedule.shifts = []

        # Mock session.add to set the schedule
        def mock_add(obj):
            if isinstance(obj, Schedule):
                obj.id = mock_schedule.id

        mock_session.add = mock_add

        service = ScheduleService()
        shifts = [
            {
                "employee_id": "EMP001",
                "shift_type": "morning",
                "start_time": "2026-03-01T08:00:00",
                "end_time": "2026-03-01T16:00:00",
                "position": "服务员"
            },
            {
                "employee_id": "EMP002",
                "shift_type": "evening",
                "start_time": "2026-03-01T16:00:00",
                "end_time": "2026-03-02T00:00:00",
                "position": "厨师"
            }
        ]

        # Mock refresh to set shifts
        async def mock_refresh(obj, attrs):
            obj.shifts = mock_schedule.shifts

        mock_session.refresh = mock_refresh

        result = await service.create_schedule("2026-03-01", shifts)

        assert "schedule_id" in result
        assert result["schedule_date"] == "2026-03-01"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_create_schedule_update_existing(self, mock_get_session):
        """测试更新已存在的排班"""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock existing schedule
        existing_schedule = MagicMock(spec=Schedule)
        existing_schedule.id = uuid.uuid4()
        existing_schedule.store_id = "STORE001"
        existing_schedule.schedule_date = date(2026, 3, 1)
        existing_schedule.shifts = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_schedule
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        async def mock_refresh(obj, attrs):
            pass

        mock_session.refresh = mock_refresh

        service = ScheduleService()
        shifts = [
            {
                "employee_id": "EMP001",
                "shift_type": "morning",
                "start_time": "2026-03-01T08:00:00",
                "end_time": "2026-03-01T16:00:00"
            }
        ]

        result = await service.create_schedule("2026-03-01", shifts)

        assert "schedule_id" in result
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_get_schedule(self, mock_get_session):
        """测试获取排班列表"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        # Create mock schedules
        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.id = uuid.uuid4()
        mock_schedule.store_id = "STORE001"
        mock_schedule.schedule_date = date(2026, 3, 1)
        mock_schedule.total_employees = "2"
        mock_schedule.total_hours = "16.0"
        mock_schedule.is_published = True
        mock_schedule.published_by = "ADMIN001"
        mock_schedule.shifts = []

        mock_result.scalars.return_value.all.return_value = [mock_schedule]
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()
        result = await service.get_schedule("2026-03-01", "2026-03-07")

        assert len(result) == 1
        assert result[0]["schedule_date"] == "2026-03-01"
        assert result[0]["is_published"] is True

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_get_schedule_by_date_found(self, mock_get_session):
        """测试获取指定日期的排班（找到）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.id = uuid.uuid4()
        mock_schedule.store_id = "STORE001"
        mock_schedule.schedule_date = date(2026, 3, 1)
        mock_schedule.total_employees = "2"
        mock_schedule.total_hours = "16.0"
        mock_schedule.is_published = False
        mock_schedule.published_by = None
        mock_schedule.shifts = []

        mock_result.scalar_one_or_none.return_value = mock_schedule
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()
        result = await service.get_schedule_by_date("2026-03-01")

        assert result is not None
        assert result["schedule_date"] == "2026-03-01"

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_get_schedule_by_date_not_found(self, mock_get_session):
        """测试获取指定日期的排班（未找到）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()
        result = await service.get_schedule_by_date("2026-03-01")

        assert result is None

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_update_schedule_success(self, mock_get_session):
        """测试更新排班成功"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        mock_schedule = MagicMock(spec=Schedule)
        schedule_id = uuid.uuid4()
        mock_schedule.id = schedule_id
        mock_schedule.store_id = "STORE001"
        mock_schedule.schedule_date = date(2026, 3, 1)
        mock_schedule.total_employees = "2"
        mock_schedule.total_hours = "16.0"
        mock_schedule.is_published = False
        mock_schedule.published_by = None
        mock_schedule.shifts = []

        mock_result.scalar_one_or_none.return_value = mock_schedule
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()
        result = await service.update_schedule(
            str(schedule_id),
            is_published=True,
            published_by="ADMIN001"
        )

        assert result["is_published"] is True
        assert result["published_by"] == "ADMIN001"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_update_schedule_not_found(self, mock_get_session):
        """测试更新不存在的排班"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()

        with pytest.raises(ValueError, match="排班不存在"):
            await service.update_schedule(str(uuid.uuid4()), is_published=True)

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_delete_schedule_success(self, mock_get_session):
        """测试删除排班成功"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        mock_schedule = MagicMock(spec=Schedule)
        schedule_id = uuid.uuid4()
        mock_schedule.id = schedule_id

        mock_result.scalar_one_or_none.return_value = mock_schedule
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()
        result = await service.delete_schedule(str(schedule_id))

        assert result["deleted"] is True
        assert result["schedule_id"] == str(schedule_id)
        mock_session.delete.assert_called_once_with(mock_schedule)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_delete_schedule_not_found(self, mock_get_session):
        """测试删除不存在的排班"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()

        with pytest.raises(ValueError, match="排班不存在"):
            await service.delete_schedule(str(uuid.uuid4()))

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_get_employee_schedules(self, mock_get_session):
        """测试获取员工排班"""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock shift
        mock_shift = MagicMock(spec=Shift)
        mock_shift.id = uuid.uuid4()
        mock_shift.schedule_id = uuid.uuid4()
        mock_shift.employee_id = "EMP001"
        mock_shift.shift_type = "morning"
        mock_shift.start_time = time(8, 0)
        mock_shift.end_time = time(16, 0)
        mock_shift.position = "服务员"
        mock_shift.is_confirmed = True
        mock_shift.notes = None

        # Mock schedule
        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.id = mock_shift.schedule_id
        mock_schedule.schedule_date = date(2026, 3, 1)

        # First execute returns shifts
        mock_shifts_result = MagicMock()
        mock_shifts_result.scalars.return_value.all.return_value = [mock_shift]

        # Second execute returns schedule
        mock_schedule_result = MagicMock()
        mock_schedule_result.scalar_one.return_value = mock_schedule

        mock_session.execute.side_effect = [mock_shifts_result, mock_schedule_result]
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()
        result = await service.get_employee_schedules("EMP001", "2026-03-01", "2026-03-07")

        assert len(result) == 1
        assert result[0]["shift_type"] == "morning"
        assert result[0]["schedule_date"] == "2026-03-01"

    @pytest.mark.asyncio
    @patch('src.services.schedule_service.get_db_session')
    async def test_get_schedule_statistics(self, mock_get_session):
        """测试获取排班统计"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        # Create mock schedules with shifts
        mock_shift1 = MagicMock(spec=Shift)
        mock_shift1.employee_id = "EMP001"
        mock_shift1.shift_type = "morning"
        mock_shift1.start_time = time(8, 0)
        mock_shift1.end_time = time(16, 0)

        mock_shift2 = MagicMock(spec=Shift)
        mock_shift2.employee_id = "EMP002"
        mock_shift2.shift_type = "evening"
        mock_shift2.start_time = time(16, 0)
        mock_shift2.end_time = time(23, 59)

        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.id = uuid.uuid4()
        mock_schedule.store_id = "STORE001"
        mock_schedule.schedule_date = date(2026, 3, 1)
        mock_schedule.is_published = True
        mock_schedule.shifts = [mock_shift1, mock_shift2]

        mock_result.scalars.return_value.all.return_value = [mock_schedule]
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ScheduleService()
        result = await service.get_schedule_statistics("2026-03-01", "2026-03-07")

        assert result["total_schedules"] == 1
        assert result["published_schedules"] == 1
        assert result["total_shifts"] == 2
        assert result["employee_count"] == 2
        assert "shift_type_breakdown" in result
        assert result["shift_type_breakdown"]["morning"] == 1
        assert result["shift_type_breakdown"]["evening"] == 1

    def test_schedule_to_dict_with_shifts(self):
        """测试将排班转换为字典（包含班次）"""
        service = ScheduleService()

        mock_shift = MagicMock(spec=Shift)
        mock_shift.id = uuid.uuid4()
        mock_shift.employee_id = "EMP001"
        mock_shift.shift_type = "morning"
        mock_shift.start_time = time(8, 0)
        mock_shift.end_time = time(16, 0)
        mock_shift.position = "服务员"
        mock_shift.is_confirmed = True
        mock_shift.is_completed = False
        mock_shift.notes = None

        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.id = uuid.uuid4()
        mock_schedule.store_id = "STORE001"
        mock_schedule.schedule_date = date(2026, 3, 1)
        mock_schedule.total_employees = "1"
        mock_schedule.total_hours = "8.0"
        mock_schedule.is_published = True
        mock_schedule.published_by = "ADMIN001"
        mock_schedule.shifts = [mock_shift]

        result = service._schedule_to_dict(mock_schedule)

        assert result["schedule_id"] == str(mock_schedule.id)
        assert result["schedule_date"] == "2026-03-01"
        assert len(result["shifts"]) == 1
        assert result["shifts"][0]["employee_id"] == "EMP001"

    def test_schedule_to_dict_without_shifts(self):
        """测试将排班转换为字典（无班次）"""
        service = ScheduleService()

        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.id = uuid.uuid4()
        mock_schedule.store_id = "STORE001"
        mock_schedule.schedule_date = date(2026, 3, 1)
        mock_schedule.total_employees = "0"
        mock_schedule.total_hours = "0.0"
        mock_schedule.is_published = False
        mock_schedule.published_by = None

        # No shifts attribute
        if hasattr(mock_schedule, 'shifts'):
            delattr(mock_schedule, 'shifts')

        result = service._schedule_to_dict(mock_schedule)

        assert result["schedule_id"] == str(mock_schedule.id)
        assert result["shifts"] == []


class TestGlobalInstance:
    """测试全局实例"""

    def test_schedule_service_instance(self):
        """测试schedule_service全局实例"""
        assert schedule_service is not None
        assert isinstance(schedule_service, ScheduleService)
        assert schedule_service.store_id == "STORE001"
