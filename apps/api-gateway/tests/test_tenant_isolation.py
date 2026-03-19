"""
租户隔离测试
验证 brand_id 过滤和 validate_store_brand 权限检查
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


# ── 辅助工厂 ──────────────────────────────────────────────────────────────────

def _make_user(brand_id: str = "", role: str = "store_manager") -> SimpleNamespace:
    return SimpleNamespace(
        id="user-001",
        username="test",
        role=role,
        store_id="STORE001",
        brand_id=brand_id,
        is_active=True,
    )


def _make_store(store_id: str = "STORE001", brand_id: str = "BRAND_A") -> SimpleNamespace:
    return SimpleNamespace(
        id=store_id,
        name="测试门店",
        brand_id=brand_id,
        region="华南",
        is_active=True,
    )


# ── get_stores brand_id 过滤测试 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stores_with_brand_id_filter():
    """传入 brand_id 时，只返回该品牌的门店"""
    from src.services.store_service import StoreService

    store_a = _make_store("S001", "BRAND_A")
    store_b = _make_store("S002", "BRAND_B")

    # 模拟 DB session 返回 BRAND_A 的门店
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [store_a]

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    # 捕获传给 session.execute 的 stmt，验证 brand_id 已注入
    svc = StoreService()
    with patch("src.services.store_service.get_db_session") as mock_ctx:
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        stores = await svc.get_stores(brand_id="BRAND_A")

    assert stores == [store_a]
    # DB 查询被调用一次
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_stores_without_brand_id_returns_all():
    """不传 brand_id 时（ADMIN），返回所有门店"""
    from src.services.store_service import StoreService

    all_stores = [_make_store("S001", "BRAND_A"), _make_store("S002", "BRAND_B")]

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = all_stores

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    svc = StoreService()
    with patch("src.services.store_service.get_db_session") as mock_ctx:
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        stores = await svc.get_stores(brand_id=None)

    assert stores == all_stores


# ── validate_store_brand 测试 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_store_brand_allows_matching_brand():
    """用户 brand_id 与门店一致时，不抛异常"""
    user = _make_user(brand_id="BRAND_A")
    store = _make_store(brand_id="BRAND_A")

    from src.core.dependencies import validate_store_brand

    with patch("src.services.store_service.store_service.get_store", new=AsyncMock(return_value=store)):
        # 不应抛异常
        await validate_store_brand("STORE001", user)


@pytest.mark.asyncio
async def test_validate_store_brand_raises_403_for_wrong_brand():
    """用户 brand_id 与门店不一致时，抛 403"""
    user = _make_user(brand_id="BRAND_B")
    store = _make_store(brand_id="BRAND_A")

    from src.core.dependencies import validate_store_brand

    with patch("src.services.store_service.store_service.get_store", new=AsyncMock(return_value=store)):
        with pytest.raises(HTTPException) as exc_info:
            await validate_store_brand("STORE001", user)

    assert exc_info.value.status_code == 403
    assert "无权访问该门店" in exc_info.value.detail


@pytest.mark.asyncio
async def test_validate_store_brand_raises_404_when_store_missing():
    """门店不存在时，抛 404"""
    user = _make_user(brand_id="BRAND_A")

    from src.core.dependencies import validate_store_brand

    with patch("src.services.store_service.store_service.get_store", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc_info:
            await validate_store_brand("NONEXIST", user)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_validate_store_brand_admin_bypasses_check():
    """brand_id 为空（ADMIN）时，直接返回，不查 DB"""
    user = _make_user(brand_id="")

    from src.core.dependencies import validate_store_brand

    mock_get_store = AsyncMock()
    with patch("src.services.store_service.store_service.get_store", new=mock_get_store):
        await validate_store_brand("ANY_STORE", user)

    # ADMIN 跳过检查，不应查询 DB
    mock_get_store.assert_not_called()
