"""
易订适配器测试 - YiDing Adapter Tests

基于真实易订API格式编写
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.adapter import YiDingAdapter
from src.client import YiDingAPIError
from src.mapper import YiDingMapper
from src.types import (
    YiDingConfig,
    ReservationStatus,
)


@pytest.fixture
def config():
    """测试配置"""
    return YiDingConfig(
        base_url="https://open.zhidianfan.com/yidingopen/",
        appid="test_appid",
        secret="test_secret",
        timeout=5,
        max_retries=2,
        cache_ttl=60,
    )


@pytest.fixture
def adapter(config):
    """测试适配器实例"""
    return YiDingAdapter(config)


class TestYiDingAdapter:
    """易订适配器测试"""

    def test_get_system_name(self, adapter):
        assert adapter.get_system_name() == "yiding"

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter):
        with patch.object(adapter.client, "ping", return_value=True):
            assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, adapter):
        with patch.object(adapter.client, "ping", side_effect=Exception("fail")):
            assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_get_order_list(self, adapter):
        """测试订单列表（5.2）"""
        mock_response = {
            "error_code": "0",
            "error_msg": "",
            "data": [
                {
                    "hotel_id": "30",
                    "hotel_name": "尝在一起闲鲜餐厅",
                    "resv_order": "16655654654765465",
                    "resv_date": "2026-03-17",
                    "area_code": "01",
                    "table_code": "001",
                    "resv_num": 8,
                    "vip_phone": "18667872695",
                    "vip_name": "张三",
                    "meal_type_code": "3",
                    "meal_type_name": "晚市",
                    "app_user_code": "1001",
                    "app_user_name": "李经理",
                    "dest_time": "18:00",
                    "remark": "靠窗位置",
                    "is_dish": 1,
                    "deposit": 1,
                    "deposit_amount": "100",
                    "order_type": 1,
                    "pay_type": 1,
                    "paymount": 800,
                    "status": 1,
                },
            ],
        }

        with patch.object(adapter.client, "get", return_value=mock_response):
            orders = await adapter.get_order_list(
                start_date="2026-03-17", end_date="2026-03-17"
            )

            assert len(orders) == 1
            o = orders[0]
            assert o["external_id"] == "16655654654765465"
            assert o["customer_name"] == "张三"
            assert o["customer_phone"] == "18667872695"
            assert o["party_size"] == 8
            assert o["status"] == ReservationStatus.PENDING
            assert o["raw_status"] == 1
            assert o["meal_type_name"] == "晚市"
            assert o["deposit_amount"] == "100"
            assert o["pay_amount"] == 800

    @pytest.mark.asyncio
    async def test_get_member_info(self, adapter):
        """测试会员信息查询（4.1）"""
        mock_response = {
            "error_code": 0,
            "error_msg": "",
            "data": {
                "sum_amount": 4732,
                "vip_sex": "男",
                "vip_name": "邱琪潇",
                "vip_company": "某公司",
                "remark": "",
                "first_class_value": "沉睡用户",
                "sub_value": "vip",
                "per_person": 3.87,
                "last_ordered": "2026-01-12",
                "vip_address": "",
                "vip_phone": "13777575146",
                "short_phone_num": "",
                "sum_ordered": 298,
                "detest": "辣椒",
                "tag": "常客",
                "hobby": "海鲜",
                "created_at": "2025-05-27 13:59:42",
            },
        }

        with patch.object(adapter.client, "get", return_value=mock_response):
            member = await adapter.get_member_info("13777575146")

            assert member is not None
            assert member["phone"] == "13777575146"
            assert member["name"] == "邱琪潇"
            assert member["total_amount"] == 4732
            assert member["total_visits"] == 298
            assert member["first_class_value"] == "沉睡用户"
            assert member["detest"] == "辣椒"
            assert member["hobby"] == "海鲜"

    @pytest.mark.asyncio
    async def test_get_member_info_not_found(self, adapter):
        """测试查询不存在的会员"""
        mock_response = {
            "error_code": 0,
            "error_msg": "",
            "data": None,
        }

        with patch.object(adapter.client, "get", return_value=mock_response):
            member = await adapter.get_member_info("99999999999")
            assert member is None

    @pytest.mark.asyncio
    async def test_get_pending_orders(self, adapter):
        """测试获取待处理订单（2.1轮询）"""
        mock_response = {
            "error_code": "0",
            "error_msg": "",
            "requestId": 1234,
            "data": [
                {
                    "resv_order": "ORDER001",
                    "resv_date": "2026-03-18",
                    "resv_num": 4,
                    "vip_phone": "13800138000",
                    "vip_name": "王五",
                    "status": 1,
                    "dest_time": "12:00",
                    "is_dish": 0,
                    "deposit": 0,
                    "order_type": 1,
                },
            ],
        }

        with patch.object(adapter.client, "get", return_value=mock_response):
            orders = await adapter.get_pending_orders()
            assert len(orders) == 1
            assert orders[0]["customer_name"] == "王五"

    @pytest.mark.asyncio
    async def test_check_table_status(self, adapter):
        """测试桌位预订状态检查（2.3）"""
        mock_response = {
            "error_code": 0,
            "error_msg": "",
            "data": {"status": 1},
        }

        with patch.object(adapter.client, "get", return_value=mock_response):
            is_reserved = await adapter.check_table_status(
                table_code="001",
                meal_type_code="3",
                resv_date="2026-03-18",
            )
            assert is_reserved is True

    @pytest.mark.asyncio
    async def test_get_order_list_v2(self, adapter):
        """测试订单列表V2（5.3）"""
        mock_response = {
            "error_code": "0",
            "error_msg": "",
            "data": [
                {
                    "hotel_id": "30",
                    "hotel_name": "尝在一起",
                    "resv_order": "V2_ORDER_001",
                    "resv_date": "2026-03-15",
                    "table_area_name": "大厅",
                    "table_name": "A03",
                    "resv_num": 6,
                    "vip_phone": "13900139000",
                    "vip_name": "赵六",
                    "meal_type_name": "午市",
                    "app_user_name": "李经理",
                    "dest_time": "11:30",
                    "remark": "",
                    "is_dish": 1,
                    "deposit": 0,
                    "deposit_amount": "0",
                    "order_type": 1,
                    "status": 3,
                    "paymount": 1200,
                    "sourceName": "大众点评",
                    "resvOrderTypeName": "普通预订",
                    "billNo": "224355",
                    "inTableTime": "2026-03-15 11:37:08",
                },
            ],
        }

        with patch.object(adapter.client, "get", return_value=mock_response):
            orders = await adapter.get_order_list_v2(
                start_date="2026-03-15", end_date="2026-03-18"
            )

            assert len(orders) == 1
            o = orders[0]
            assert o["status"] == ReservationStatus.COMPLETED
            assert o["raw_status"] == 3
            assert o["pay_amount"] == 1200
            assert o["source_name"] == "大众点评"
            assert o["table_area_name"] == "大厅"
            assert o["in_table_time"] == "2026-03-15 11:37:08"


class TestYiDingMapper:
    """数据映射器测试"""

    def test_map_status_numeric(self):
        """测试数字状态码映射"""
        mapper = YiDingMapper()

        assert mapper._map_status(1) == ReservationStatus.PENDING
        assert mapper._map_status(2) == ReservationStatus.SEATED
        assert mapper._map_status(3) == ReservationStatus.COMPLETED
        assert mapper._map_status(4) == ReservationStatus.CANCELLED
        assert mapper._map_status(6) == ReservationStatus.TABLE_CHANGE

    def test_map_status_string(self):
        """测试字符串状态码映射"""
        mapper = YiDingMapper()

        assert mapper._map_status("1") == ReservationStatus.PENDING
        assert mapper._map_status("2") == ReservationStatus.SEATED
        assert mapper._map_status("3") == ReservationStatus.COMPLETED

    def test_compute_reservation_stats(self):
        """测试预订统计计算"""
        mapper = YiDingMapper()

        reservations = [
            {
                "status": ReservationStatus.PENDING,
                "party_size": 4,
                "deposit_amount": "100",
                "pay_amount": 0,
            },
            {
                "status": ReservationStatus.COMPLETED,
                "party_size": 8,
                "deposit_amount": "200",
                "pay_amount": 1500,
            },
            {
                "status": ReservationStatus.COMPLETED,
                "party_size": 6,
                "deposit_amount": "0",
                "pay_amount": 1000,
            },
        ]

        stats = mapper.compute_reservation_stats(
            reservations, "S001", "2026-03-01", "2026-03-18"
        )

        assert stats["total_reservations"] == 3
        assert stats["average_party_size"] == 6.0
        assert stats["total_deposit"] == 300.0
        assert stats["total_pay_amount"] == 2500.0
        assert stats["status_breakdown"]["pending"] == 1
        assert stats["status_breakdown"]["completed"] == 2


class TestYiDingCache:
    """缓存测试"""

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        from src.cache import YiDingCache

        cache = YiDingCache(ttl=60)
        test_data = {"id": "test123", "name": "Test"}
        await cache.set_reservation("test123", test_data)

        cached = await cache.get_reservation("test123")
        assert cached == test_data

    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        from src.cache import YiDingCache

        cache = YiDingCache(ttl=60)
        test_data = {"id": "test123", "name": "Test"}
        await cache.set_reservation("test123", test_data)

        await cache.invalidate_reservation("test123")

        cached = await cache.get_reservation("test123")
        assert cached is None
