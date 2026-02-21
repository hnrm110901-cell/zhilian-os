"""
预定服务测试
Tests for Reservation Service
"""
import pytest
from datetime import date, time, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.reservation_service import ReservationService, reservation_service
from src.models.reservation import Reservation, ReservationStatus, ReservationType


class TestReservationService:
    """ReservationService测试类"""

    def test_init(self):
        """测试服务初始化"""
        service = ReservationService()
        assert service.store_id == "STORE001"

        service_custom = ReservationService(store_id="STORE002")
        assert service_custom.store_id == "STORE002"

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_create_reservation_success(self, mock_get_session):
        """测试创建预定成功"""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock session.add to set created_at and updated_at
        def mock_add(reservation):
            reservation.created_at = datetime.now()
            reservation.updated_at = datetime.now()

        mock_session.add = mock_add
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.create_reservation(
            customer_name="张三",
            customer_phone="13800138000",
            reservation_date="2026-03-01",
            reservation_time="18:00",
            party_size=4
        )

        assert "reservation_id" in result
        assert result["customer_name"] == "张三"
        assert result["customer_phone"] == "13800138000"
        assert result["reservation_date"] == "2026-03-01"
        assert result["reservation_time"] == "18:00:00"
        assert result["party_size"] == 4
        assert result["status"] == "pending"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_create_reservation_with_optional_fields(self, mock_get_session):
        """测试创建带可选字段的预定"""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock session.add to set created_at and updated_at
        def mock_add(reservation):
            reservation.created_at = datetime.now()
            reservation.updated_at = datetime.now()

        mock_session.add = mock_add
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.create_reservation(
            customer_name="李四",
            customer_phone="13900139000",
            reservation_date="2026-03-01",
            reservation_time="19:00",
            party_size=6,
            reservation_type="banquet",
            customer_email="lisi@example.com",
            table_number="A01",
            special_requests="靠窗座位",
            dietary_restrictions="无辣",
            estimated_budget=2000.0
        )

        assert result["customer_name"] == "李四"
        assert result["party_size"] == 6
        assert result["reservation_type"] == "banquet"

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_get_reservations_all(self, mock_get_session):
        """测试获取所有预定"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        # 创建模拟预定对象
        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.id = "RES_001"
        mock_reservation.store_id = "STORE001"
        mock_reservation.customer_name = "张三"
        mock_reservation.customer_phone = "13800138000"
        mock_reservation.customer_email = None
        mock_reservation.reservation_type = ReservationType.REGULAR
        mock_reservation.reservation_date = date(2026, 3, 1)
        mock_reservation.reservation_time = time(18, 0)
        mock_reservation.party_size = 4
        mock_reservation.table_number = None
        mock_reservation.room_name = None
        mock_reservation.status = ReservationStatus.PENDING
        mock_reservation.special_requests = None
        mock_reservation.dietary_restrictions = None
        mock_reservation.banquet_details = {}
        mock_reservation.estimated_budget = None
        mock_reservation.notes = None
        mock_reservation.created_at = datetime(2026, 2, 20, 10, 0)
        mock_reservation.updated_at = datetime(2026, 2, 20, 10, 0)

        mock_result.scalars.return_value.all.return_value = [mock_reservation]
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.get_reservations()

        assert len(result) == 1
        assert result[0]["reservation_id"] == "RES_001"
        assert result[0]["customer_name"] == "张三"

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_get_reservations_by_date(self, mock_get_session):
        """测试按日期筛选预定"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.get_reservations(reservation_date="2026-03-01")

        assert isinstance(result, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_get_reservations_by_status(self, mock_get_session):
        """测试按状态筛选预定"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.get_reservations(status="confirmed")

        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_get_reservation_by_id_found(self, mock_get_session):
        """测试根据ID获取预定（找到）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.id = "RES_001"
        mock_reservation.store_id = "STORE001"
        mock_reservation.customer_name = "张三"
        mock_reservation.customer_phone = "13800138000"
        mock_reservation.customer_email = None
        mock_reservation.reservation_type = ReservationType.REGULAR
        mock_reservation.reservation_date = date(2026, 3, 1)
        mock_reservation.reservation_time = time(18, 0)
        mock_reservation.party_size = 4
        mock_reservation.table_number = None
        mock_reservation.room_name = None
        mock_reservation.status = ReservationStatus.PENDING
        mock_reservation.special_requests = None
        mock_reservation.dietary_restrictions = None
        mock_reservation.banquet_details = {}
        mock_reservation.estimated_budget = None
        mock_reservation.notes = None
        mock_reservation.created_at = datetime(2026, 2, 20, 10, 0)
        mock_reservation.updated_at = datetime(2026, 2, 20, 10, 0)

        mock_result.scalar_one_or_none.return_value = mock_reservation
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.get_reservation_by_id("RES_001")

        assert result is not None
        assert result["reservation_id"] == "RES_001"
        assert result["customer_name"] == "张三"

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_get_reservation_by_id_not_found(self, mock_get_session):
        """测试根据ID获取预定（未找到）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.get_reservation_by_id("RES_999")

        assert result is None

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_update_reservation_status_success(self, mock_get_session):
        """测试更新预定状态成功"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.id = "RES_001"
        mock_reservation.store_id = "STORE001"
        mock_reservation.customer_name = "张三"
        mock_reservation.customer_phone = "13800138000"
        mock_reservation.customer_email = None
        mock_reservation.reservation_type = ReservationType.REGULAR
        mock_reservation.reservation_date = date(2026, 3, 1)
        mock_reservation.reservation_time = time(18, 0)
        mock_reservation.party_size = 4
        mock_reservation.table_number = None
        mock_reservation.room_name = None
        mock_reservation.status = ReservationStatus.PENDING
        mock_reservation.special_requests = None
        mock_reservation.dietary_restrictions = None
        mock_reservation.banquet_details = {}
        mock_reservation.estimated_budget = None
        mock_reservation.notes = None
        mock_reservation.created_at = datetime(2026, 2, 20, 10, 0)
        mock_reservation.updated_at = datetime(2026, 2, 20, 10, 0)

        mock_result.scalar_one_or_none.return_value = mock_reservation
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.update_reservation_status("RES_001", "confirmed")

        assert result["reservation_id"] == "RES_001"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_update_reservation_status_not_found(self, mock_get_session):
        """测试更新不存在的预定状态"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()

        with pytest.raises(ValueError, match="not found"):
            await service.update_reservation_status("RES_999", "confirmed")

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_assign_table_success(self, mock_get_session):
        """测试分配桌号成功"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.id = "RES_001"
        mock_reservation.store_id = "STORE001"
        mock_reservation.customer_name = "张三"
        mock_reservation.customer_phone = "13800138000"
        mock_reservation.customer_email = None
        mock_reservation.reservation_type = ReservationType.REGULAR
        mock_reservation.reservation_date = date(2026, 3, 1)
        mock_reservation.reservation_time = time(18, 0)
        mock_reservation.party_size = 4
        mock_reservation.table_number = "A01"
        mock_reservation.room_name = None
        mock_reservation.status = ReservationStatus.CONFIRMED
        mock_reservation.special_requests = None
        mock_reservation.dietary_restrictions = None
        mock_reservation.banquet_details = {}
        mock_reservation.estimated_budget = None
        mock_reservation.notes = None
        mock_reservation.created_at = datetime(2026, 2, 20, 10, 0)
        mock_reservation.updated_at = datetime(2026, 2, 20, 10, 0)

        mock_result.scalar_one_or_none.return_value = mock_reservation
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.assign_table("RES_001", "A01")

        assert result["table_number"] == "A01"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_assign_table_not_found(self, mock_get_session):
        """测试为不存在的预定分配桌号"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()

        with pytest.raises(ValueError, match="not found"):
            await service.assign_table("RES_999", "A01")

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_get_upcoming_reservations(self, mock_get_session):
        """测试获取即将到来的预定"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.get_upcoming_reservations(days=7)

        assert isinstance(result, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_cancel_reservation_success(self, mock_get_session):
        """测试取消预定成功"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.id = "RES_001"
        mock_reservation.store_id = "STORE001"
        mock_reservation.customer_name = "张三"
        mock_reservation.customer_phone = "13800138000"
        mock_reservation.customer_email = None
        mock_reservation.reservation_type = ReservationType.REGULAR
        mock_reservation.reservation_date = date(2026, 3, 1)
        mock_reservation.reservation_time = time(18, 0)
        mock_reservation.party_size = 4
        mock_reservation.table_number = None
        mock_reservation.room_name = None
        mock_reservation.status = ReservationStatus.CANCELLED
        mock_reservation.special_requests = None
        mock_reservation.dietary_restrictions = None
        mock_reservation.banquet_details = {}
        mock_reservation.estimated_budget = None
        mock_reservation.notes = "取消原因: 临时有事"
        mock_reservation.created_at = datetime(2026, 2, 20, 10, 0)
        mock_reservation.updated_at = datetime(2026, 2, 20, 10, 0)

        mock_result.scalar_one_or_none.return_value = mock_reservation
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.cancel_reservation("RES_001", "临时有事")

        assert result["status"] == "cancelled"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_cancel_reservation_not_found(self, mock_get_session):
        """测试取消不存在的预定"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()

        with pytest.raises(ValueError, match="not found"):
            await service.cancel_reservation("RES_999")

    @pytest.mark.asyncio
    @patch('src.services.reservation_service.get_db_session')
    async def test_get_reservation_statistics(self, mock_get_session):
        """测试获取预定统计"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()

        # 创建多个模拟预定
        reservations = []
        for i in range(5):
            mock_res = MagicMock(spec=Reservation)
            mock_res.status = ReservationStatus.CONFIRMED if i < 3 else ReservationStatus.CANCELLED
            mock_res.reservation_type = ReservationType.REGULAR
            mock_res.party_size = 4
            reservations.append(mock_res)

        mock_result.scalars.return_value.all.return_value = reservations
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session

        service = ReservationService()
        result = await service.get_reservation_statistics()

        assert result["total_reservations"] == 5
        assert result["total_guests"] == 20
        assert result["average_party_size"] == 4.0
        assert "by_status" in result
        assert "by_type" in result
        assert "confirmed_rate" in result
        assert "cancellation_rate" in result


class TestGlobalInstance:
    """测试全局实例"""

    def test_reservation_service_instance(self):
        """测试reservation_service全局实例"""
        assert reservation_service is not None
        assert isinstance(reservation_service, ReservationService)
        assert reservation_service.store_id == "STORE001"
