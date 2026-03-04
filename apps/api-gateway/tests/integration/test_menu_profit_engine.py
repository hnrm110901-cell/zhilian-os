"""
Tests for MenuProfitEngine

Covers:
- get_dish_channel_profit(): no DishChannelConfig → None
- get_dish_channel_profit(): no SalesChannelConfig → defaults (0 commission, 0 costs)
- get_dish_channel_profit(): with brand-level SalesChannelConfig
- get_dish_channel_profit(): label "赚钱" (margin > 30%)
- get_dish_channel_profit(): label "勉强" (0 < margin ≤ 30%)
- get_dish_channel_profit(): label "亏钱" (margin ≤ 0)
- get_dish_channel_profit(): zero price edge case
- get_store_channel_report(): returns list of DishChannelProfit
- _resolve_channel_config(): brand config preferred over default
- _resolve_channel_config(): inactive config ignored
"""
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Stubs ─────────────────────────────────────────────────────────────────────
sys.modules.setdefault("structlog", MagicMock(get_logger=MagicMock(return_value=MagicMock())))
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock())
sys.modules.setdefault("src.ontology", MagicMock(get_ontology_repository=MagicMock(return_value=None)))
sys.modules.setdefault("src.models.bom", MagicMock())
sys.modules.setdefault("src.models.store", MagicMock())
sys.modules.setdefault("src.models", MagicMock())

from src.services.menu_profit_engine import MenuProfitEngine, _resolve_channel_config  # noqa: E402
from src.services.bom_resolver import ResolvedBOM, ResolvedBOMItem  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_dcc(dish_id=None, channel="meituan", price_fen=3000, is_available=True):
    d = MagicMock()
    d.dish_id = dish_id or str(uuid4())
    d.channel = channel
    d.price_fen = price_fen
    d.is_available = is_available
    return d


def _make_dish(dish_id=None, name="宫保鸡丁", store_id="STORE001"):
    d = MagicMock()
    d.id = dish_id or str(uuid4())
    d.name = name
    d.store_id = store_id
    return d


def _make_store(brand_id="BRAND01"):
    s = MagicMock()
    s.brand_id = brand_id
    return s


def _make_ch_cfg(brand_id=None, channel="meituan", commission=Decimal("0.18"),
                 packaging=50, delivery=100, is_active=True):
    c = MagicMock()
    c.brand_id = brand_id
    c.channel = channel
    c.platform_commission_pct = commission
    c.packaging_cost_fen = packaging
    c.delivery_cost_fen = delivery
    c.is_active = is_active
    return c


def _make_resolved_bom(cost_fen=1000, dish_id="D1", store_id="S1"):
    items = [ResolvedBOMItem("ING1", None, Decimal("10"), "克", cost_fen // 10)]
    return ResolvedBOM(dish_id=dish_id, store_id=store_id, channel=None, items=items)


# ── _resolve_channel_config unit tests ────────────────────────────────────────

def test_resolve_channel_config_brand_preferred():
    brand_cfg = _make_ch_cfg(brand_id="B1", commission=Decimal("0.20"))
    default_cfg = _make_ch_cfg(brand_id=None, commission=Decimal("0.10"))
    result = _resolve_channel_config([brand_cfg], [default_cfg], "meituan")
    assert result is brand_cfg


def test_resolve_channel_config_fallback_to_default():
    default_cfg = _make_ch_cfg(brand_id=None, commission=Decimal("0.10"))
    result = _resolve_channel_config([], [default_cfg], "meituan")
    assert result is default_cfg


def test_resolve_channel_config_inactive_skipped():
    inactive = _make_ch_cfg(brand_id="B1", is_active=False)
    default_cfg = _make_ch_cfg(brand_id=None, is_active=True)
    result = _resolve_channel_config([inactive], [default_cfg], "meituan")
    assert result is default_cfg


def test_resolve_channel_config_none_when_empty():
    result = _resolve_channel_config([], [], "meituan")
    assert result is None


# ── get_dish_channel_profit async tests ──────────────────────────────────────

def _exec(*, scalar_one=None, scalars_all=None):
    """Sync MagicMock simulating a SQLAlchemy execute() result."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar_one
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


@pytest.mark.asyncio
async def test_profit_no_dish_channel_config_returns_none():
    session = AsyncMock()
    session.execute.return_value = _exec(scalar_one=None)
    result = await MenuProfitEngine.get_dish_channel_profit(session, "D1", "meituan", "S1")
    assert result is None


@pytest.mark.asyncio
async def test_profit_no_channel_config_uses_zero_defaults():
    session = AsyncMock()
    dish_id = str(uuid4())
    dcc = _make_dcc(dish_id=dish_id, price_fen=2000, channel="meituan")
    dish = _make_dish(dish_id=dish_id, name="宫保鸡丁", store_id="S1")
    store = _make_store(brand_id="BRAND01")
    resolved = _make_resolved_bom(cost_fen=500, dish_id=dish_id, store_id="S1")

    session.execute.side_effect = [
        _exec(scalar_one=dcc),
        _exec(scalar_one=dish),
        _exec(scalar_one=store),
        _exec(scalars_all=[]),   # no channel configs
    ]

    with patch(
        "src.services.menu_profit_engine.BOMResolverService.resolve",
        return_value=resolved,
    ):
        result = await MenuProfitEngine.get_dish_channel_profit(session, dish_id, "meituan", "S1")

    assert result is not None
    assert result.price_fen == 2000
    assert result.revenue_fen == Decimal("2000")   # 0% commission
    assert result.bom_cost_fen == Decimal("500")
    assert result.packaging_cost_fen == 0
    assert result.delivery_cost_fen == 0
    assert result.gross_profit_fen == Decimal("1500")


@pytest.mark.asyncio
async def test_profit_label_zhuanqian():
    """毛利率 > 30% → 赚钱"""
    session = AsyncMock()
    dish_id = str(uuid4())
    dcc = _make_dcc(dish_id=dish_id, price_fen=10000, channel="dine_in")
    dish = _make_dish(dish_id=dish_id, name="龙虾")
    store = _make_store()
    # No channel configs; bom cost very low
    resolved = _make_resolved_bom(cost_fen=100, dish_id=dish_id)

    session.execute.side_effect = [
        _exec(scalar_one=dcc),
        _exec(scalar_one=dish),
        _exec(scalar_one=store),
        _exec(scalars_all=[]),
    ]

    with patch("src.services.menu_profit_engine.BOMResolverService.resolve", return_value=resolved):
        result = await MenuProfitEngine.get_dish_channel_profit(session, dish_id, "dine_in", "S1")

    assert result.label == "赚钱"
    assert result.gross_margin_pct > 0.30


@pytest.mark.asyncio
async def test_profit_label_mankuai():
    """0 < 毛利率 ≤ 30% → 勉强"""
    session = AsyncMock()
    dish_id = str(uuid4())
    dcc = _make_dcc(dish_id=dish_id, price_fen=1000, channel="dine_in")
    dish = _make_dish(dish_id=dish_id)
    store = _make_store()
    # bom_cost = 800 → gross_profit = 200 → margin = 20%
    resolved = _make_resolved_bom(cost_fen=800, dish_id=dish_id)

    session.execute.side_effect = [
        _exec(scalar_one=dcc),
        _exec(scalar_one=dish),
        _exec(scalar_one=store),
        _exec(scalars_all=[]),
    ]

    with patch("src.services.menu_profit_engine.BOMResolverService.resolve", return_value=resolved):
        result = await MenuProfitEngine.get_dish_channel_profit(session, dish_id, "dine_in", "S1")

    assert result.label == "勉强"
    assert 0 < result.gross_margin_pct <= 0.30


@pytest.mark.asyncio
async def test_profit_label_kuiqian():
    """毛利率 ≤ 0 → 亏钱"""
    session = AsyncMock()
    dish_id = str(uuid4())
    dcc = _make_dcc(dish_id=dish_id, price_fen=500, channel="meituan")
    dish = _make_dish(dish_id=dish_id)
    store = _make_store()
    ch_cfg = _make_ch_cfg(brand_id=None, commission=Decimal("0.18"), packaging=100, delivery=200)
    # revenue = 500 * 0.82 = 410; bom_cost = 500; total = 500+100+200=800; gp = 410-800 < 0
    resolved = _make_resolved_bom(cost_fen=500, dish_id=dish_id)

    session.execute.side_effect = [
        _exec(scalar_one=dcc),
        _exec(scalar_one=dish),
        _exec(scalar_one=store),
        _exec(scalars_all=[ch_cfg]),
    ]

    with patch("src.services.menu_profit_engine.BOMResolverService.resolve", return_value=resolved):
        result = await MenuProfitEngine.get_dish_channel_profit(session, dish_id, "meituan", "S1")

    assert result.label == "亏钱"
    assert result.gross_margin_pct <= 0


@pytest.mark.asyncio
async def test_profit_zero_price_edge_case():
    """price_fen=0 → revenue=0, margin=0, label=亏钱"""
    session = AsyncMock()
    dish_id = str(uuid4())
    dcc = _make_dcc(dish_id=dish_id, price_fen=0)
    dish = _make_dish(dish_id=dish_id)
    store = _make_store()
    resolved = ResolvedBOM(dish_id=dish_id, store_id="S1", channel=None)

    session.execute.side_effect = [
        _exec(scalar_one=dcc),
        _exec(scalar_one=dish),
        _exec(scalar_one=store),
        _exec(scalars_all=[]),
    ]

    with patch("src.services.menu_profit_engine.BOMResolverService.resolve", return_value=resolved):
        result = await MenuProfitEngine.get_dish_channel_profit(session, dish_id, "dine_in", "S1")

    assert result.gross_margin_pct == 0.0
    assert result.label == "亏钱"


# ── get_store_channel_report ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_store_channel_report_returns_list():
    session = AsyncMock()
    dish_id = str(uuid4())
    dcc = _make_dcc(dish_id=dish_id, channel="dine_in", price_fen=2000)
    dcc.dish_id = dish_id

    session.execute.side_effect = [_exec(scalars_all=[dcc])]

    profit = MagicMock()
    with patch.object(
        MenuProfitEngine, "get_dish_channel_profit", new_callable=lambda: lambda self: AsyncMock(return_value=profit)
    ):
        with patch(
            "src.services.menu_profit_engine.MenuProfitEngine.get_dish_channel_profit",
            new=AsyncMock(return_value=profit),
        ):
            results = await MenuProfitEngine.get_store_channel_report(session, "STORE001")

    assert results == [profit]
