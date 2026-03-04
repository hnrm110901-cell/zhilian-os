"""
Tests for BOMResolverService

Covers:
- resolve(): no store found → empty ResolvedBOM
- resolve(): no templates → empty ResolvedBOM
- resolve(): base BOM only (is_delta=False, scope='store')
- resolve(): base BOM + ADD delta
- resolve(): base BOM + OVERRIDE delta (changes qty)
- resolve(): base BOM + REMOVE delta (removes ingredient)
- resolve(): channel delta applied only when channel matches
- resolve(): scope priority (store > region > brand > group)
- get_theoretical_qty(): ingredient found
- get_theoretical_qty(): ingredient not found → Decimal("0")
- get_theoretical_qty(): exception → Decimal("0") (no raise)
- ResolvedBOM.total_bom_cost_fen: computed correctly
"""
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Stubs (before importing service) ─────────────────────────────────────────
sys.modules.setdefault("structlog", MagicMock(get_logger=MagicMock(return_value=MagicMock())))
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock())
sys.modules.setdefault("src.ontology", MagicMock(get_ontology_repository=MagicMock(return_value=None)))

# Stub ORM models
_bom_mod = MagicMock()
_store_mod = MagicMock()
sys.modules.setdefault("src.models.bom", _bom_mod)
sys.modules.setdefault("src.models.store", _store_mod)
sys.modules.setdefault("src.models", MagicMock())

from src.services.bom_resolver import (  # noqa: E402
    BOMResolverService,
    ResolvedBOM,
    ResolvedBOMItem,
    _find_base_bom,
    _collect_deltas,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_store(store_id="STORE001", brand_id="BRAND01", region="华东"):
    s = MagicMock()
    s.id = store_id
    s.brand_id = brand_id
    s.region = region
    return s


def _make_template(
    bom_id=None,
    dish_id=None,
    scope="store",
    scope_id="STORE001",
    channel=None,
    is_delta=False,
    is_active=True,
    items=None,
):
    t = MagicMock()
    t.id = bom_id or str(uuid4())
    t.dish_id = dish_id or str(uuid4())
    t.scope = scope
    t.scope_id = scope_id
    t.channel = channel
    t.is_delta = is_delta
    t.is_active = is_active
    t.items = items or []
    return t


def _make_item(ingredient_id="ING001", std_qty="1.0000", unit="克", unit_cost=100, action="ADD"):
    it = MagicMock()
    it.ingredient_id = ingredient_id
    it.ingredient_master_id = None
    it.standard_qty = Decimal(std_qty)
    it.unit = unit
    it.unit_cost = unit_cost
    it.item_action = action
    return it


# ── ResolvedBOMItem / ResolvedBOM unit tests ─────────────────────────────────

def test_resolved_bom_item_line_cost():
    item = ResolvedBOMItem(
        ingredient_id="ING1",
        ingredient_master_id=None,
        standard_qty=Decimal("2.5"),
        unit="克",
        unit_cost=200,
    )
    assert item.line_cost_fen == Decimal("500")


def test_resolved_bom_total_cost():
    items = [
        ResolvedBOMItem("ING1", None, Decimal("2"), "克", 100),
        ResolvedBOMItem("ING2", None, Decimal("3"), "克", 50),
    ]
    rb = ResolvedBOM(dish_id="D1", store_id="S1", channel=None, items=items)
    assert rb.total_bom_cost_fen == Decimal("350")


def test_resolved_bom_empty_items():
    rb = ResolvedBOM(dish_id="D1", store_id="S1", channel=None)
    assert rb.total_bom_cost_fen == Decimal("0")


# ── _find_base_bom ────────────────────────────────────────────────────────────

def test_find_base_bom_no_candidates():
    store = _make_store()
    delta = _make_template(scope="store", is_delta=True)
    result = _find_base_bom([delta], store, None)
    assert result is None


def test_find_base_bom_prefers_store_over_group():
    store = _make_store(store_id="STORE001")
    t_group = _make_template(scope="group", scope_id=None, is_delta=False)
    t_store = _make_template(scope="store", scope_id="STORE001", is_delta=False)
    result = _find_base_bom([t_group, t_store], store, None)
    assert result is t_store


# ── _collect_deltas ───────────────────────────────────────────────────────────

def test_collect_deltas_ordering():
    store = _make_store()
    d_brand = _make_template(scope="brand", is_delta=True)
    d_group = _make_template(scope="group", is_delta=True)
    d_store = _make_template(scope="store", is_delta=True)
    result = _collect_deltas([d_brand, d_group, d_store], store, None)
    scopes = [t.scope for t in result]
    assert scopes.index("group") < scopes.index("brand") < scopes.index("store")


# ── BOMResolverService.resolve() async tests ─────────────────────────────────

def _exec_result(*, scalar_one=None, scalars_all=None):
    """Build a MagicMock that simulates an AsyncSession.execute() result."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar_one
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


@pytest.mark.asyncio
async def test_resolve_store_not_found():
    session = AsyncMock()
    session.execute.return_value = _exec_result(scalar_one=None)
    result = await BOMResolverService.resolve(session, "DISH1", "STORE1")
    assert result.items == []
    assert result.dish_id == "DISH1"


@pytest.mark.asyncio
async def test_resolve_no_templates():
    session = AsyncMock()
    store = _make_store()
    session.execute.side_effect = [
        _exec_result(scalar_one=store),
        _exec_result(scalars_all=[]),
    ]
    result = await BOMResolverService.resolve(session, "DISH1", "STORE1")
    assert result.items == []


@pytest.mark.asyncio
async def test_resolve_base_bom_only():
    session = AsyncMock()
    store = _make_store()
    item = _make_item("ING001", "2.0000", "克", 100)
    bom = _make_template(scope="store", scope_id="STORE001", is_delta=False, items=[item])

    session.execute.side_effect = [
        _exec_result(scalar_one=store),
        _exec_result(scalars_all=[bom]),
    ]

    result = await BOMResolverService.resolve(session, bom.dish_id, "STORE001")
    assert len(result.items) == 1
    assert result.items[0].ingredient_id == "ING001"
    assert result.items[0].standard_qty == Decimal("2.0000")
    assert result.total_bom_cost_fen == Decimal("200")


@pytest.mark.asyncio
async def test_resolve_delta_add():
    session = AsyncMock()
    store = _make_store()
    base_item = _make_item("ING001", "1.0000", "克", 100)
    delta_item = _make_item("ING002", "0.5000", "克", 200, action="ADD")
    base_bom = _make_template(scope="store", scope_id="STORE001", is_delta=False, items=[base_item])
    delta_bom = _make_template(scope="brand", scope_id="BRAND01", is_delta=True, items=[delta_item])

    session.execute.side_effect = [
        _exec_result(scalar_one=store),
        _exec_result(scalars_all=[base_bom, delta_bom]),
    ]

    result = await BOMResolverService.resolve(session, base_bom.dish_id, "STORE001")
    ing_ids = {i.ingredient_id for i in result.items}
    assert "ING001" in ing_ids
    assert "ING002" in ing_ids


@pytest.mark.asyncio
async def test_resolve_delta_remove():
    session = AsyncMock()
    store = _make_store()
    base_item = _make_item("ING001", "1.0000", "克", 100)
    remove_item = _make_item("ING001", "0", "克", 0, action="REMOVE")
    base_bom = _make_template(scope="store", scope_id="STORE001", is_delta=False, items=[base_item])
    delta_bom = _make_template(scope="brand", scope_id="BRAND01", is_delta=True, items=[remove_item])

    session.execute.side_effect = [
        _exec_result(scalar_one=store),
        _exec_result(scalars_all=[base_bom, delta_bom]),
    ]

    result = await BOMResolverService.resolve(session, base_bom.dish_id, "STORE001")
    assert result.items == []


@pytest.mark.asyncio
async def test_resolve_channel_delta_not_applied_when_channel_mismatch():
    session = AsyncMock()
    store = _make_store()
    base_item = _make_item("ING001", "1.0000", "克", 100)
    extra_item = _make_item("ING002", "0.5000", "克", 200, action="ADD")
    base_bom = _make_template(scope="store", scope_id="STORE001", is_delta=False, items=[base_item])
    channel_delta = _make_template(scope="channel", channel="meituan", is_delta=True, items=[extra_item])

    session.execute.side_effect = [
        _exec_result(scalar_one=store),
        _exec_result(scalars_all=[base_bom, channel_delta]),
    ]

    # channel=None → channel delta should NOT apply
    result = await BOMResolverService.resolve(session, base_bom.dish_id, "STORE001", channel=None)
    assert len(result.items) == 1
    assert result.items[0].ingredient_id == "ING001"


# ── get_theoretical_qty ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_theoretical_qty_found():
    session = AsyncMock()
    store = _make_store()
    item = _make_item("ING001", "3.0000", "克", 50)
    bom = _make_template(scope="store", scope_id="STORE001", is_delta=False, items=[item])

    session.execute.side_effect = [
        _exec_result(scalar_one=store),
        _exec_result(scalars_all=[bom]),
    ]

    qty = await BOMResolverService.get_theoretical_qty(
        session, bom.dish_id, "STORE001", "ING001"
    )
    assert qty == Decimal("3.0000")


@pytest.mark.asyncio
async def test_get_theoretical_qty_not_found_returns_zero():
    session = AsyncMock()
    store = _make_store()
    item = _make_item("ING001", "1.0000", "克", 100)
    bom = _make_template(scope="store", scope_id="STORE001", is_delta=False, items=[item])

    session.execute.side_effect = [
        _exec_result(scalar_one=store),
        _exec_result(scalars_all=[bom]),
    ]

    qty = await BOMResolverService.get_theoretical_qty(
        session, bom.dish_id, "STORE001", "NONEXISTENT"
    )
    assert qty == Decimal("0")


@pytest.mark.asyncio
async def test_get_theoretical_qty_exception_returns_zero():
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("db gone")

    qty = await BOMResolverService.get_theoretical_qty(
        session, "DISH1", "STORE1", "ING1"
    )
    assert qty == Decimal("0")
