"""
Integration tests for ChannelProfit API (B4)

Covers:
1. GET /channel-profit/{store_id} → 200，返回列表
2. GET /channel-profit/{store_id} → 200，空列表（无菜品/配置）
3. GET /channel-profit/{store_id}/dish/{dish_id}?channel=meituan → 200
4. GET /channel-profit/{store_id}/dish/{dish_id}?channel=meituan → 404（无定价）
5. GET /channel-profit/{store_id}/labels?label=亏钱 → 200，过滤正确
6. GET /channel-profit/{store_id}/labels?label=invalid → 400
7. DishChannelProfitResponse.from_dataclass → 分→元转换正确（/100）
8. GET /channel-profit/{store_id}/labels?label=赚钱 → 只返回 label=赚钱 的记录
"""
import sys
from decimal import Decimal
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Module stubs ──────────────────────────────────────────────────────────────
sys.modules.setdefault("structlog", MagicMock(get_logger=MagicMock(return_value=MagicMock(
    info=MagicMock(), warning=MagicMock(), error=MagicMock(), debug=MagicMock()
))))
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock(get_db=MagicMock()))
sys.modules.setdefault("src.core.dependencies", MagicMock(get_current_user=MagicMock()))
sys.modules.setdefault("src.models.user", MagicMock(User=MagicMock()))

for mod in [
    "src.models.dish", "src.models.dish_channel",
    "src.models.channel_config", "src.models.store",
    "src.services.bom_resolver",
]:
    sys.modules.setdefault(mod, MagicMock())

from src.services.menu_profit_engine import DishChannelProfit  # noqa: E402
from src.api.channel_profit import DishChannelProfitResponse  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_profit(
    dish_id=None,
    dish_name="招牌红烧肉",
    channel="meituan",
    store_id="S001",
    price_fen=5000,
    gross_margin_pct=0.35,
    label="赚钱",
) -> DishChannelProfit:
    return DishChannelProfit(
        dish_id=dish_id or str(uuid4()),
        dish_name=dish_name,
        channel=channel,
        store_id=store_id,
        price_fen=price_fen,
        revenue_fen=Decimal("4750"),    # 5000 × (1 - 0.05)
        bom_cost_fen=Decimal("2000"),
        packaging_cost_fen=300,
        delivery_cost_fen=200,
        total_cost_fen=Decimal("2500"),
        gross_profit_fen=Decimal("2250"),
        gross_margin_pct=gross_margin_pct,
        label=label,
        bom_source_ids=["BOM001"],
    )


def _make_db_session():
    db = MagicMock()
    db.execute = AsyncMock()
    return db


# ── Tests: DishChannelProfitResponse.from_dataclass ──────────────────────────

def test_response_conversion_fen_to_yuan():
    """分→元转换：5000 分 = 50.00 元"""
    profit = _make_profit(price_fen=5000)
    resp = DishChannelProfitResponse.from_dataclass(profit)
    assert resp.price_yuan == 50.00
    assert resp.bom_cost_yuan == 20.00
    assert resp.packaging_cost_yuan == 3.00
    assert resp.delivery_cost_yuan == 2.00
    assert resp.total_cost_yuan == 25.00
    assert resp.gross_profit_yuan == 22.50
    assert resp.gross_margin_pct == profit.gross_margin_pct
    assert resp.label == profit.label


def test_response_label_preserved():
    """标注字段原样保留"""
    for label in ["赚钱", "勉强", "亏钱"]:
        profit = _make_profit(label=label)
        resp = DishChannelProfitResponse.from_dataclass(profit)
        assert resp.label == label


# ── Tests: GET /channel-profit/{store_id} ────────────────────────────────────

@pytest.mark.asyncio
async def test_get_store_channel_report_returns_list():
    """正常返回菜品毛利列表"""
    from src.api.channel_profit import get_store_channel_report

    profits = [_make_profit(), _make_profit(dish_name="清蒸鲈鱼", label="勉强")]
    db = _make_db_session()

    with patch("src.api.channel_profit.MenuProfitEngine.get_store_channel_report",
               new=AsyncMock(return_value=profits)):
        result = await get_store_channel_report(
            store_id="S001",
            db=db,
            current_user=MagicMock(),
        )

    assert len(result) == 2
    assert all(isinstance(r, DishChannelProfitResponse) for r in result)


@pytest.mark.asyncio
async def test_get_store_channel_report_empty():
    """无菜品时返回空列表"""
    from src.api.channel_profit import get_store_channel_report

    db = _make_db_session()

    with patch("src.api.channel_profit.MenuProfitEngine.get_store_channel_report",
               new=AsyncMock(return_value=[])):
        result = await get_store_channel_report(
            store_id="S001",
            db=db,
            current_user=MagicMock(),
        )

    assert result == []


# ── Tests: GET /channel-profit/{store_id}/dish/{dish_id} ─────────────────────

@pytest.mark.asyncio
async def test_get_dish_channel_profit_found():
    """菜品存在 → 返回 200 响应"""
    from src.api.channel_profit import get_dish_channel_profit

    profit = _make_profit()
    db = _make_db_session()

    with patch("src.api.channel_profit.MenuProfitEngine.get_dish_channel_profit",
               new=AsyncMock(return_value=profit)):
        result = await get_dish_channel_profit(
            store_id="S001",
            dish_id=profit.dish_id,
            channel="meituan",
            db=db,
            current_user=MagicMock(),
        )

    assert isinstance(result, DishChannelProfitResponse)
    assert result.dish_id == profit.dish_id


@pytest.mark.asyncio
async def test_get_dish_channel_profit_not_found():
    """无定价配置 → 抛 404"""
    from fastapi import HTTPException
    from src.api.channel_profit import get_dish_channel_profit

    db = _make_db_session()

    with patch("src.api.channel_profit.MenuProfitEngine.get_dish_channel_profit",
               new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc_info:
            await get_dish_channel_profit(
                store_id="S001",
                dish_id="DISH_NONEXISTENT",
                channel="meituan",
                db=db,
                current_user=MagicMock(),
            )

    assert exc_info.value.status_code == 404


# ── Tests: GET /channel-profit/{store_id}/labels ─────────────────────────────

@pytest.mark.asyncio
async def test_get_by_label_filters_correctly():
    """label=亏钱 → 只返回 label=亏钱 的记录"""
    from src.api.channel_profit import get_by_label

    profits = [
        _make_profit(label="赚钱"),
        _make_profit(label="亏钱"),
        _make_profit(label="勉强"),
        _make_profit(label="亏钱"),
    ]
    db = _make_db_session()

    with patch("src.api.channel_profit.MenuProfitEngine.get_store_channel_report",
               new=AsyncMock(return_value=profits)):
        result = await get_by_label(
            store_id="S001",
            label="亏钱",
            db=db,
            current_user=MagicMock(),
        )

    assert len(result) == 2
    assert all(r.label == "亏钱" for r in result)


@pytest.mark.asyncio
async def test_get_by_label_invalid_label_returns_400():
    """非法 label → 400"""
    from fastapi import HTTPException
    from src.api.channel_profit import get_by_label

    db = _make_db_session()

    with pytest.raises(HTTPException) as exc_info:
        await get_by_label(
            store_id="S001",
            label="超级赚钱",
            db=db,
            current_user=MagicMock(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_by_label_zhuan_qian():
    """label=赚钱 → 只返回高毛利菜品"""
    from src.api.channel_profit import get_by_label

    profits = [
        _make_profit(label="赚钱", gross_margin_pct=0.40),
        _make_profit(label="赚钱", gross_margin_pct=0.35),
        _make_profit(label="勉强", gross_margin_pct=0.10),
    ]
    db = _make_db_session()

    with patch("src.api.channel_profit.MenuProfitEngine.get_store_channel_report",
               new=AsyncMock(return_value=profits)):
        result = await get_by_label(
            store_id="S001",
            label="赚钱",
            db=db,
            current_user=MagicMock(),
        )

    assert len(result) == 2
    assert all(r.gross_margin_pct > 0.30 for r in result)
