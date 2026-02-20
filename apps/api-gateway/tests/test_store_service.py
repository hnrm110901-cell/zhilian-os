"""
Tests for Store Service
门店服务测试 - 业务逻辑测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from src.services.store_service import StoreService, store_service
from src.models.store import Store, StoreStatus


@pytest.fixture
def mock_store():
    """创建模拟门店"""
    store = MagicMock(spec=Store)
    store.id = "STORE001"
    store.name = "测试门店"
    store.code = "TEST001"
    store.address = "北京市朝阳区测试路1号"
    store.city = "北京"
    store.district = "朝阳区"
    store.phone = "010-12345678"
    store.email = "test@example.com"
    store.manager_id = None
    store.region = "华北"
    store.status = StoreStatus.ACTIVE.value
    store.is_active = True
    store.area = 200.0
    store.seats = 50
    store.floors = 2
    store.opening_date = "2024-01-01"
    store.business_hours = {"monday": "09:00-22:00"}
    store.monthly_revenue_target = 100000.0
    store.latitude = 39.9042
    store.longitude = 116.4074
    store.created_at = datetime.now()
    store.updated_at = datetime.now()
    return store


@pytest.fixture
def service():
    """创建服务实例"""
    return StoreService()


@pytest.mark.asyncio
class TestCompareStores:
    """测试门店对比"""

    async def test_compare_stores_success(self, service):
        """测试成功对比门店"""
        store1 = MagicMock(spec=Store)
        store1.id = "STORE001"
        store1.name = "门店1"
        store1.region = "华北"

        store2 = MagicMock(spec=Store)
        store2.id = "STORE002"
        store2.name = "门店2"
        store2.region = "华东"

        with patch.object(service, "get_store") as mock_get_store:
            with patch.object(service, "get_store_stats") as mock_get_stats:
                mock_get_store.side_effect = [store1, store2]
                mock_get_stats.side_effect = [
                    {"today_revenue": 10000, "today_customers": 50, "today_orders": 20},
                    {"today_revenue": 15000, "today_customers": 60, "today_orders": 25},
                ]

                result = await service.compare_stores(
                    ["STORE001", "STORE002"],
                    ["revenue", "customers", "orders"]
                )

                assert len(result["stores"]) == 2
                assert "revenue" in result["data"]
                assert "customers" in result["data"]
                assert "orders" in result["data"]
                assert result["data"]["revenue"]["STORE001"] == 10000
                assert result["data"]["revenue"]["STORE002"] == 15000

    async def test_compare_stores_with_monthly_revenue(self, service):
        """测试对比门店月营收"""
        store1 = MagicMock(spec=Store)
        store1.id = "STORE001"
        store1.name = "门店1"
        store1.region = "华北"

        with patch.object(service, "get_store") as mock_get_store:
            with patch.object(service, "get_store_stats") as mock_get_stats:
                mock_get_store.return_value = store1
                mock_get_stats.return_value = {"monthly_revenue": 500000}

                result = await service.compare_stores(
                    ["STORE001"],
                    ["monthly_revenue"]
                )

                assert result["data"]["monthly_revenue"]["STORE001"] == 500000


@pytest.mark.asyncio
class TestGetRegionalSummary:
    """测试获取区域汇总"""

    async def test_get_regional_summary(self, service):
        """测试获取区域汇总数据"""
        store1 = MagicMock(spec=Store)
        store1.id = "STORE001"
        store1.name = "门店1"
        store1.region = "华北"
        store1.city = "北京"
        store1.status = "active"
        store1.is_active = True
        store1.seats = 50
        store1.area = 200.0

        store2 = MagicMock(spec=Store)
        store2.id = "STORE002"
        store2.name = "门店2"
        store2.region = "华北"
        store2.city = "天津"
        store2.status = "active"
        store2.is_active = True
        store2.seats = 40
        store2.area = 150.0

        with patch.object(service, "get_stores_by_region") as mock_get_stores:
            mock_get_stores.return_value = {
                "华北": [store1, store2]
            }

            result = await service.get_regional_summary()

            assert "华北" in result
            assert result["华北"]["store_count"] == 2
            assert result["华北"]["active_stores"] == 2
            assert result["华北"]["total_seats"] == 90
            assert result["华北"]["total_area"] == 350.0

    async def test_get_regional_summary_multiple_regions(self, service):
        """测试多个区域的汇总"""
        store1 = MagicMock(spec=Store)
        store1.id = "STORE001"
        store1.name = "门店1"
        store1.region = "华北"
        store1.city = "北京"
        store1.status = "active"
        store1.is_active = True
        store1.seats = 50
        store1.area = 200.0

        store2 = MagicMock(spec=Store)
        store2.id = "STORE002"
        store2.name = "门店2"
        store2.region = "华东"
        store2.city = "上海"
        store2.status = "active"
        store2.is_active = True
        store2.seats = 60
        store2.area = 250.0

        with patch.object(service, "get_stores_by_region") as mock_get_stores:
            mock_get_stores.return_value = {
                "华北": [store1],
                "华东": [store2]
            }

            result = await service.get_regional_summary()

            assert len(result) == 2
            assert "华北" in result
            assert "华东" in result
            assert result["华北"]["store_count"] == 1
            assert result["华东"]["store_count"] == 1


@pytest.mark.asyncio
class TestGetPerformanceRanking:
    """测试获取业绩排名"""

    async def test_get_performance_ranking_by_revenue(self, service):
        """测试按营收排名"""
        store1 = MagicMock(spec=Store)
        store1.id = "STORE001"
        store1.name = "门店1"
        store1.region = "华北"
        store1.city = "北京"

        store2 = MagicMock(spec=Store)
        store2.id = "STORE002"
        store2.name = "门店2"
        store2.region = "华东"
        store2.city = "上海"

        with patch.object(service, "get_stores") as mock_get_stores:
            with patch.object(service, "get_store_stats") as mock_get_stats:
                mock_get_stores.return_value = [store1, store2]
                mock_get_stats.side_effect = [
                    {"today_revenue": 15000},
                    {"today_revenue": 20000},
                ]

                result = await service.get_performance_ranking(metric="revenue", limit=10)

                assert len(result) == 2
                assert result[0]["rank"] == 1
                assert result[0]["store_id"] == "STORE002"  # 营收更高
                assert result[0]["value"] == 20000
                assert result[1]["rank"] == 2
                assert result[1]["store_id"] == "STORE001"
                assert result[1]["value"] == 15000

    async def test_get_performance_ranking_by_customers(self, service):
        """测试按客户数排名"""
        store1 = MagicMock(spec=Store)
        store1.id = "STORE001"
        store1.name = "门店1"
        store1.region = "华北"
        store1.city = "北京"

        store2 = MagicMock(spec=Store)
        store2.id = "STORE002"
        store2.name = "门店2"
        store2.region = "华东"
        store2.city = "上海"

        with patch.object(service, "get_stores") as mock_get_stores:
            with patch.object(service, "get_store_stats") as mock_get_stats:
                mock_get_stores.return_value = [store1, store2]
                mock_get_stats.side_effect = [
                    {"today_customers": 100},
                    {"today_customers": 150},
                ]

                result = await service.get_performance_ranking(metric="customers", limit=10)

                assert len(result) == 2
                assert result[0]["metric"] == "customers"
                assert result[0]["value"] == 150
                assert result[1]["value"] == 100

    async def test_get_performance_ranking_limit(self, service):
        """测试排名限制"""
        stores = [MagicMock(spec=Store) for _ in range(15)]
        for i, store in enumerate(stores):
            store.id = f"STORE{i:03d}"
            store.name = f"门店{i}"
            store.region = "华北"
            store.city = "北京"

        with patch.object(service, "get_stores") as mock_get_stores:
            with patch.object(service, "get_store_stats") as mock_get_stats:
                mock_get_stores.return_value = stores
                mock_get_stats.return_value = {"today_revenue": 10000}

                result = await service.get_performance_ranking(metric="revenue", limit=5)

                assert len(result) == 5
                assert all("rank" in item for item in result)
                assert result[0]["rank"] == 1
                assert result[4]["rank"] == 5

    async def test_get_performance_ranking_by_orders(self, service):
        """测试按订单数排名"""
        store1 = MagicMock(spec=Store)
        store1.id = "STORE001"
        store1.name = "门店1"
        store1.region = "华北"
        store1.city = "北京"

        with patch.object(service, "get_stores") as mock_get_stores:
            with patch.object(service, "get_store_stats") as mock_get_stats:
                mock_get_stores.return_value = [store1]
                mock_get_stats.return_value = {"today_orders": 50}

                result = await service.get_performance_ranking(metric="orders", limit=10)

                assert len(result) == 1
                assert result[0]["metric"] == "orders"
                assert result[0]["value"] == 50


@pytest.mark.asyncio
class TestStoreServiceIntegration:
    """测试门店服务集成功能"""

    async def test_store_service_singleton(self):
        """测试门店服务单例"""
        from src.services.store_service import store_service as service1
        from src.services.store_service import store_service as service2

        assert service1 is service2

    async def test_compare_stores_empty_list(self, service):
        """测试对比空门店列表"""
        result = await service.compare_stores([], ["revenue"])

        assert result["stores"] == []
        assert result["metrics"] == ["revenue"]
        assert result["data"] == {}

    async def test_compare_stores_nonexistent_store(self, service):
        """测试对比不存在的门店"""
        with patch.object(service, "get_store") as mock_get_store:
            mock_get_store.return_value = None

            result = await service.compare_stores(["NONEXISTENT"], ["revenue"])

            assert len(result["stores"]) == 0

    async def test_performance_ranking_empty_stores(self, service):
        """测试空门店列表的排名"""
        with patch.object(service, "get_stores") as mock_get_stores:
            mock_get_stores.return_value = []

            result = await service.get_performance_ranking(metric="revenue", limit=10)

            assert len(result) == 0

    async def test_regional_summary_empty(self, service):
        """测试空区域汇总"""
        with patch.object(service, "get_stores_by_region") as mock_get_stores:
            mock_get_stores.return_value = {}

            result = await service.get_regional_summary()

            assert result == {}
