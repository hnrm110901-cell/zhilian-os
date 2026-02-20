"""
Tests for mobile API geolocation features
移动端API地理位置功能测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from src.api.mobile import get_nearby_stores
from src.models.user import User, UserRole
from src.models.store import Store


@pytest.fixture
def mock_user():
    """创建模拟用户"""
    user = MagicMock(spec=User)
    user.id = "user123"
    user.username = "testuser"
    user.role = UserRole.WAITER
    user.store_id = "STORE001"
    return user


@pytest.fixture
def mock_stores():
    """创建模拟门店列表"""
    stores = []

    # 门店1: 距离用户位置约1公里
    store1 = MagicMock(spec=Store)
    store1.id = "STORE001"
    store1.name = "测试门店1"
    store1.address = "北京市朝阳区测试路1号"
    store1.phone = "010-12345678"
    store1.latitude = 39.9142  # 距离(39.9042, 116.4074)约1.1公里
    store1.longitude = 116.4074
    store1.city = "北京"
    store1.district = "朝阳区"
    store1.status = "active"
    stores.append(store1)

    # 门店2: 距离用户位置约10公里
    store2 = MagicMock(spec=Store)
    store2.id = "STORE002"
    store2.name = "测试门店2"
    store2.address = "北京市海淀区测试路2号"
    store2.phone = "010-87654321"
    store2.latitude = 39.9942  # 距离(39.9042, 116.4074)约10公里
    store2.longitude = 116.4074
    store2.city = "北京"
    store2.district = "海淀区"
    store2.status = "active"
    stores.append(store2)

    # 门店3: 没有地理位置信息
    store3 = MagicMock(spec=Store)
    store3.id = "STORE003"
    store3.name = "测试门店3"
    store3.address = "北京市东城区测试路3号"
    store3.phone = "010-11111111"
    store3.latitude = None
    store3.longitude = None
    store3.city = "北京"
    store3.district = "东城区"
    store3.status = "active"
    stores.append(store3)

    return stores


@pytest.mark.asyncio
class TestGetNearbyStores:
    """测试获取附近门店API"""

    async def test_get_nearby_stores_success(self, mock_user, mock_stores):
        """测试成功获取附近门店"""
        with patch("src.api.mobile.store_service") as mock_store_service:
            mock_store_service.get_stores = AsyncMock(return_value=mock_stores)

            result = await get_nearby_stores(
                latitude=39.9042,
                longitude=116.4074,
                radius=5000,  # 5公里半径
                current_user=mock_user,
            )

            # 验证返回结果
            assert result["location"]["latitude"] == 39.9042
            assert result["location"]["longitude"] == 116.4074
            assert result["radius"] == 5000
            assert result["count"] == 1  # 只有门店1在5公里内
            assert len(result["stores"]) == 1
            assert result["stores"][0]["id"] == "STORE001"
            assert "distance" in result["stores"][0]
            assert "distance_text" in result["stores"][0]

    async def test_get_nearby_stores_sorted_by_distance(self, mock_user, mock_stores):
        """测试门店按距离排序"""
        with patch("src.api.mobile.store_service") as mock_store_service:
            mock_store_service.get_stores = AsyncMock(return_value=mock_stores)

            result = await get_nearby_stores(
                latitude=39.9042,
                longitude=116.4074,
                radius=15000,  # 15公里半径,包含两个门店
                current_user=mock_user,
            )

            # 验证门店按距离排序
            assert len(result["stores"]) == 2
            assert result["stores"][0]["distance"] < result["stores"][1]["distance"]
            assert result["stores"][0]["id"] == "STORE001"
            assert result["stores"][1]["id"] == "STORE002"

    async def test_get_nearby_stores_no_results(self, mock_user, mock_stores):
        """测试没有附近门店"""
        with patch("src.api.mobile.store_service") as mock_store_service:
            mock_store_service.get_stores = AsyncMock(return_value=mock_stores)

            result = await get_nearby_stores(
                latitude=39.9042,
                longitude=116.4074,
                radius=500,  # 500米半径,没有门店
                current_user=mock_user,
            )

            # 验证返回空列表
            assert result["count"] == 0
            assert len(result["stores"]) == 0

    async def test_get_nearby_stores_skip_no_location(self, mock_user, mock_stores):
        """测试跳过没有地理位置的门店"""
        with patch("src.api.mobile.store_service") as mock_store_service:
            mock_store_service.get_stores = AsyncMock(return_value=mock_stores)

            result = await get_nearby_stores(
                latitude=39.9042,
                longitude=116.4074,
                radius=15000,
                current_user=mock_user,
            )

            # 验证门店3(没有地理位置)被跳过
            store_ids = [s["id"] for s in result["stores"]]
            assert "STORE003" not in store_ids

    async def test_get_nearby_stores_service_error(self, mock_user):
        """测试服务错误处理"""
        with patch("src.api.mobile.store_service") as mock_store_service:
            mock_store_service.get_stores = AsyncMock(
                side_effect=Exception("Database error")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_nearby_stores(
                    latitude=39.9042,
                    longitude=116.4074,
                    radius=5000,
                    current_user=mock_user,
                )

            assert exc_info.value.status_code == 500
            assert "查询附近门店失败" in exc_info.value.detail

    async def test_get_nearby_stores_large_radius(self, mock_user, mock_stores):
        """测试大半径搜索"""
        with patch("src.api.mobile.store_service") as mock_store_service:
            mock_store_service.get_stores = AsyncMock(return_value=mock_stores)

            result = await get_nearby_stores(
                latitude=39.9042,
                longitude=116.4074,
                radius=50000,  # 50公里半径
                current_user=mock_user,
            )

            # 验证返回所有有地理位置的门店
            assert result["count"] == 2
            assert len(result["stores"]) == 2

    async def test_get_nearby_stores_includes_all_fields(self, mock_user, mock_stores):
        """测试返回结果包含所有必要字段"""
        with patch("src.api.mobile.store_service") as mock_store_service:
            mock_store_service.get_stores = AsyncMock(return_value=mock_stores)

            result = await get_nearby_stores(
                latitude=39.9042,
                longitude=116.4074,
                radius=5000,
                current_user=mock_user,
            )

            if result["stores"]:
                store = result["stores"][0]
                required_fields = [
                    "id", "name", "address", "phone", "latitude", "longitude",
                    "distance", "distance_text", "city", "district", "status"
                ]
                for field in required_fields:
                    assert field in store, f"Missing field: {field}"
