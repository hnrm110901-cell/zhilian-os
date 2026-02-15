"""
易订适配器测试 - YiDing Adapter Tests
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.adapter import YiDingAdapter
from src.types import (
    YiDingConfig,
    CreateReservationDTO,
    TableType,
    ReservationStatus
)


@pytest.fixture
def config():
    """测试配置"""
    return YiDingConfig(
        base_url="https://api-test.yiding.com",
        app_id="test_app_id",
        app_secret="test_app_secret",
        timeout=5,
        max_retries=2,
        cache_ttl=60
    )


@pytest.fixture
def adapter(config):
    """测试适配器实例"""
    return YiDingAdapter(config)


class TestYiDingAdapter:
    """易订适配器测试"""

    def test_get_system_name(self, adapter):
        """测试获取系统名称"""
        assert adapter.get_system_name() == "yiding"

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter):
        """测试健康检查成功"""
        with patch.object(adapter.client, 'ping', return_value=True):
            result = await adapter.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, adapter):
        """测试健康检查失败"""
        with patch.object(adapter.client, 'ping', side_effect=Exception("Connection failed")):
            result = await adapter.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_create_reservation(self, adapter):
        """测试创建预订"""
        # Mock数据
        reservation_data: CreateReservationDTO = {
            "store_id": "STORE001",
            "customer_name": "张三",
            "customer_phone": "13800138000",
            "reservation_date": "2026-02-20",
            "reservation_time": "18:00",
            "party_size": 4,
            "table_type": TableType.MEDIUM,
            "special_requests": "靠窗位置"
        }

        mock_response = {
            "success": True,
            "data": {
                "id": "12345",
                "store_id": "STORE001",
                "customer_id": "CUST001",
                "customer_name": "张三",
                "customer_phone": "13800138000",
                "reservation_date": "2026-02-20",
                "reservation_time": "18:00",
                "party_size": 4,
                "table_type": "medium",
                "table_number": "M001",
                "status": "pending",
                "deposit_amount": 10000,
                "estimated_amount": 40000,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }

        with patch.object(adapter.client, 'post', return_value=mock_response):
            reservation = await adapter.create_reservation(reservation_data)

            assert reservation["external_id"] == "12345"
            assert reservation["customer_name"] == "张三"
            assert reservation["party_size"] == 4
            assert reservation["status"] == ReservationStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_reservation(self, adapter):
        """测试查询预订"""
        mock_response = {
            "success": True,
            "data": {
                "id": "12345",
                "store_id": "STORE001",
                "customer_id": "CUST001",
                "customer_name": "张三",
                "customer_phone": "13800138000",
                "reservation_date": "2026-02-20",
                "reservation_time": "18:00",
                "party_size": 4,
                "table_type": "medium",
                "status": "confirmed",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }

        with patch.object(adapter.client, 'get', return_value=mock_response):
            reservation = await adapter.get_reservation("12345")

            assert reservation["external_id"] == "12345"
            assert reservation["status"] == ReservationStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_get_customer_by_phone(self, adapter):
        """测试根据手机号查询客户"""
        mock_response = {
            "success": True,
            "data": {
                "id": "CUST001",
                "phone": "13800138000",
                "name": "张三",
                "member_level": "VIP",
                "points": 1000,
                "visit_count": 15,
                "total_spent": 480000,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }

        with patch.object(adapter.client, 'get', return_value=mock_response):
            customer = await adapter.get_customer_by_phone("13800138000")

            assert customer is not None
            assert customer["phone"] == "13800138000"
            assert customer["name"] == "张三"
            assert customer["member_level"] == "VIP"

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self, adapter):
        """测试查询不存在的客户"""
        from src.client import YiDingAPIError

        with patch.object(
            adapter.client,
            'get',
            side_effect=YiDingAPIError("Not found", status_code=404)
        ):
            customer = await adapter.get_customer_by_phone("99999999999")
            assert customer is None

    @pytest.mark.asyncio
    async def test_get_available_tables(self, adapter):
        """测试查询可用桌台"""
        mock_response = {
            "success": True,
            "data": [
                {
                    "id": "T001",
                    "table_number": "M001",
                    "table_type": "medium",
                    "capacity": 4,
                    "min_capacity": 2,
                    "status": "available",
                    "location": "大厅"
                },
                {
                    "id": "T002",
                    "table_number": "M002",
                    "table_type": "medium",
                    "capacity": 4,
                    "min_capacity": 2,
                    "status": "available",
                    "location": "大厅"
                }
            ]
        }

        with patch.object(adapter.client, 'get', return_value=mock_response):
            tables = await adapter.get_available_tables(
                store_id="STORE001",
                date="2026-02-20",
                time="18:00",
                party_size=4
            )

            assert len(tables) == 2
            assert tables[0]["table_number"] == "M001"
            assert tables[0]["capacity"] == 4

    @pytest.mark.asyncio
    async def test_cancel_reservation(self, adapter):
        """测试取消预订"""
        mock_response = {"success": True}

        with patch.object(adapter.client, 'delete', return_value=mock_response):
            await adapter.cancel_reservation("12345", reason="客户临时有事")
            # 验证没有抛出异常

    @pytest.mark.asyncio
    async def test_cache_hit(self, adapter):
        """测试缓存命中"""
        # 第一次调用,设置缓存
        mock_response = {
            "success": True,
            "data": {
                "id": "12345",
                "store_id": "STORE001",
                "customer_id": "CUST001",
                "customer_name": "张三",
                "customer_phone": "13800138000",
                "reservation_date": "2026-02-20",
                "reservation_time": "18:00",
                "party_size": 4,
                "table_type": "medium",
                "status": "confirmed",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }

        with patch.object(adapter.client, 'get', return_value=mock_response) as mock_get:
            # 第一次调用
            reservation1 = await adapter.get_reservation("12345")
            assert mock_get.call_count == 1

            # 第二次调用应该命中缓存
            reservation2 = await adapter.get_reservation("12345")
            assert mock_get.call_count == 1  # 没有增加

            assert reservation1["id"] == reservation2["id"]


class TestYiDingMapper:
    """数据映射器测试"""

    def test_map_status(self):
        """测试状态映射"""
        from src.mapper import YiDingMapper

        mapper = YiDingMapper()

        assert mapper._map_status("pending") == ReservationStatus.PENDING
        assert mapper._map_status("confirmed") == ReservationStatus.CONFIRMED
        assert mapper._map_status("arrived") == ReservationStatus.SEATED
        assert mapper._map_status("finished") == ReservationStatus.COMPLETED
        assert mapper._map_status("cancelled") == ReservationStatus.CANCELLED
        assert mapper._map_status("noshow") == ReservationStatus.NO_SHOW

    def test_map_table_type(self):
        """测试桌型映射"""
        from src.mapper import YiDingMapper

        mapper = YiDingMapper()

        assert mapper._map_table_type("small") == TableType.SMALL
        assert mapper._map_table_type("medium") == TableType.MEDIUM
        assert mapper._map_table_type("large") == TableType.LARGE
        assert mapper._map_table_type("round") == TableType.ROUND
        assert mapper._map_table_type("private") == TableType.PRIVATE_ROOM


class TestYiDingCache:
    """缓存测试"""

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """测试缓存设置和获取"""
        from src.cache import YiDingCache

        cache = YiDingCache(ttl=60)

        test_data = {"id": "test123", "name": "Test"}
        await cache.set_reservation("test123", test_data)

        cached = await cache.get_reservation("test123")
        assert cached == test_data

    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        """测试缓存失效"""
        from src.cache import YiDingCache

        cache = YiDingCache(ttl=60)

        test_data = {"id": "test123", "name": "Test"}
        await cache.set_reservation("test123", test_data)

        # 验证缓存存在
        cached = await cache.get_reservation("test123")
        assert cached is not None

        # 清除缓存
        await cache.invalidate_reservation("test123")

        # 验证缓存已清除
        cached = await cache.get_reservation("test123")
        assert cached is None
