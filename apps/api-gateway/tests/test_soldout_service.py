"""
沽清服务 — 全渠道通知集成测试
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.soldout_service import SoldoutService


def _make_dish(dish_id=None, name="宫保鸡丁", code="GBJ001", is_available=True):
    d = MagicMock()
    d.id = dish_id or uuid.uuid4()
    d.name = name
    d.code = code
    d.is_available = is_available
    d.store_id = "S001"
    d.category_id = None
    d.price = 38.0
    d.kitchen_station = "hot"
    d.sort_order = 1
    d.tags = ["川菜"]
    return d


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return [self._value] if self._value else []


class FakeSession:
    def __init__(self, dish=None):
        self._dish = dish
        self.flushed = False

    async def execute(self, _stmt):
        return FakeScalarResult(self._dish)

    async def flush(self):
        self.flushed = True


@pytest.fixture
def dish():
    return _make_dish()


@pytest.fixture
def session(dish):
    return FakeSession(dish)


@pytest.fixture
def service(session):
    return SoldoutService(db=session, store_id="S001")


# ── 渠道通知测试 ──


@pytest.mark.asyncio
async def test_notify_channels_all_not_configured(service, dish):
    """所有渠道环境变量未配置时，返回 not_configured"""
    with patch.dict("os.environ", {}, clear=True):
        results = await service._notify_channels(dish, action="soldout")

    assert results["local_db"] == "ok"
    assert results["pos"] == "not_configured"
    assert results["meituan"] == "not_configured"
    assert results["eleme"] == "not_configured"
    assert results["keruyun"] == "not_configured"
    assert results["wechat_mini"] == "not_configured"


@pytest.mark.asyncio
async def test_notify_meituan_soldout(service, dish):
    """美团渠道配置正确时，调用 sold_out_food"""
    env = {
        "MEITUAN_APP_ID": "test_app",
        "MEITUAN_APP_SECRET": "test_secret",
        "MEITUAN_POI_ID": "test_poi",
    }
    mock_adapter = MagicMock()
    mock_adapter.sold_out_food = AsyncMock(return_value={})

    with patch.dict("os.environ", env, clear=True):
        service._adapters["meituan"] = mock_adapter
        result = await service._notify_meituan(dish.code, is_restore=False)

    assert result == "ok"
    mock_adapter.sold_out_food.assert_called_once_with(food_id=dish.code)


@pytest.mark.asyncio
async def test_notify_meituan_restore(service, dish):
    """美团恢复上架调用 on_sale_food"""
    env = {
        "MEITUAN_APP_ID": "test_app",
        "MEITUAN_APP_SECRET": "test_secret",
        "MEITUAN_POI_ID": "test_poi",
    }
    mock_adapter = MagicMock()
    mock_adapter.on_sale_food = AsyncMock(return_value={})

    with patch.dict("os.environ", env, clear=True):
        service._adapters["meituan"] = mock_adapter
        result = await service._notify_meituan(dish.code, is_restore=True)

    assert result == "ok"
    mock_adapter.on_sale_food.assert_called_once_with(food_id=dish.code)


@pytest.mark.asyncio
async def test_notify_meituan_error_returns_error_string(service, dish):
    """美团 API 调用失败时返回 error 字符串"""
    env = {
        "MEITUAN_APP_ID": "test_app",
        "MEITUAN_APP_SECRET": "test_secret",
        "MEITUAN_POI_ID": "test_poi",
    }
    mock_adapter = MagicMock()
    mock_adapter.sold_out_food = AsyncMock(side_effect=Exception("网络超时"))

    with patch.dict("os.environ", env, clear=True):
        service._adapters["meituan"] = mock_adapter
        result = await service._notify_meituan(dish.code, is_restore=False)

    assert result.startswith("error:")
    assert "网络超时" in result


@pytest.mark.asyncio
async def test_notify_eleme_soldout(service, dish):
    """饿了么沽清调用 sold_out_food"""
    env = {
        "ELEME_APP_KEY": "test_key",
        "ELEME_APP_SECRET": "test_secret",
    }
    mock_adapter = MagicMock()
    mock_adapter.sold_out_food = AsyncMock(return_value={})

    with patch.dict("os.environ", env, clear=True):
        service._adapters["eleme"] = mock_adapter
        result = await service._notify_eleme(dish.code, is_restore=False)

    assert result == "ok"
    mock_adapter.sold_out_food.assert_called_once_with(food_id=dish.code)


@pytest.mark.asyncio
async def test_notify_keruyun_soldout(service, dish):
    """客如云 POS 沽清调用 update_dish_status(is_sold_out=1)"""
    env = {
        "KERUYUN_CLIENT_ID": "test_id",
        "KERUYUN_CLIENT_SECRET": "test_secret",
    }
    mock_adapter = MagicMock()
    mock_adapter.update_dish_status = AsyncMock(return_value={})

    with patch.dict("os.environ", env):
        service._adapters["keruyun"] = mock_adapter
        result = await service._notify_keruyun(dish.code, is_restore=False)

    assert result == "ok"
    mock_adapter.update_dish_status.assert_called_once_with(sku_id=dish.code, is_sold_out=1)


@pytest.mark.asyncio
async def test_notify_keruyun_restore(service, dish):
    """客如云恢复上架调用 update_dish_status(is_sold_out=0)"""
    env = {
        "KERUYUN_CLIENT_ID": "test_id",
        "KERUYUN_CLIENT_SECRET": "test_secret",
    }
    mock_adapter = MagicMock()
    mock_adapter.update_dish_status = AsyncMock(return_value={})

    with patch.dict("os.environ", env):
        service._adapters["keruyun"] = mock_adapter
        result = await service._notify_keruyun(dish.code, is_restore=True)

    assert result == "ok"
    mock_adapter.update_dish_status.assert_called_once_with(sku_id=dish.code, is_sold_out=0)


@pytest.mark.asyncio
async def test_notify_pos_pinzhi_not_supported(service, dish):
    """品智 POS 沽清 API 未支持"""
    with patch.dict("os.environ", {"POS_ADAPTER_TYPE": "pinzhi"}, clear=True):
        result = await service._notify_pos(dish.code, is_restore=False)

    assert result == "not_supported_by_vendor"


@pytest.mark.asyncio
async def test_notify_pos_aoqiwei_not_supported(service, dish):
    """奥琦玮 POS 沽清 API 未支持"""
    with patch.dict("os.environ", {"POS_ADAPTER_TYPE": "aoqiwei"}, clear=True):
        result = await service._notify_pos(dish.code, is_restore=False)

    assert result == "not_supported_by_vendor"


# ── 主流程测试 ──


@pytest.mark.asyncio
async def test_soldout_dish_success(service, dish, session):
    """沽清菜品成功"""
    with patch.dict("os.environ", {}, clear=True):
        result = await service.soldout_dish(str(dish.id))

    assert result["success"] is True
    assert "已沽清" in result["message"]
    assert dish.is_available is False
    assert session.flushed


@pytest.mark.asyncio
async def test_soldout_already_soldout(service, dish):
    """菜品已沽清时跳过"""
    dish.is_available = False
    result = await service.soldout_dish(str(dish.id))

    assert result["success"] is True
    assert "已处于沽清状态" in result["message"]


@pytest.mark.asyncio
async def test_restore_dish_success(service, dish, session):
    """恢复上架成功"""
    dish.is_available = False
    with patch.dict("os.environ", {}, clear=True):
        result = await service.restore_dish(str(dish.id))

    assert result["success"] is True
    assert "已恢复上架" in result["message"]
    assert dish.is_available is True


@pytest.mark.asyncio
async def test_soldout_nonexistent_dish():
    """菜品不存在时返回错误"""
    session = FakeSession(dish=None)
    svc = SoldoutService(db=session, store_id="S001")
    result = await svc.soldout_dish(str(uuid.uuid4()))
    assert result["success"] is False
    assert "不存在" in result["error"]
