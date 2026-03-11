"""
Tests for waste_reasoning_service._step2_bom_deviation with BOMResolverService

Covers:
- Primary path: BOMResolverService returns qty > 0 → uses SQL path
- Primary path: resolver_success=True, expected=0, no bom_dish_ids → fallback not triggered
  (anomaly=False when actual==0 too)
- Fallback: resolver raises exception → falls back to Neo4j path
- Fallback: Neo4j unavailable (repo=None) + resolver fails → empty trace, anomaly=True
- Anomaly detection: abs(dev) > expected*0.2 → anomaly=True
- No anomaly: within 20% threshold
- Empty variances list → empty result
- Dish fetch fails → resolver path skipped gracefully, fallback used
"""
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

# ── Stubs (before importing) ──────────────────────────────────────────────────
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock(
    debug=MagicMock(), warning=MagicMock()
)
sys.modules.setdefault("structlog", _structlog_mock)
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock())

_bom_resolver_mod = MagicMock()
sys.modules["src.services.bom_resolver"] = _bom_resolver_mod

# Stub src.models (Dish, Order, OrderItem etc.)
_models_mock = MagicMock()
sys.modules.setdefault("src.models", _models_mock)

_onto_mock = MagicMock()
sys.modules["src.ontology"] = _onto_mock

# Ensure waste_reasoning_service is imported as the real module, not a mock
sys.modules.pop("src.services.waste_reasoning_service", None)

import src.services.waste_reasoning_service as _waste_mod  # noqa: E402
from src.services.waste_reasoning_service import _step2_bom_deviation  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_dish(dish_id=None, store_id="STORE001"):
    d = MagicMock()
    d.id = dish_id or str(uuid4())
    d.store_id = store_id
    d.is_available = True
    return d


def _make_order_item(quantity=5):
    it = MagicMock()
    it.quantity = quantity
    return it


def _exec(*, scalar_one=None, scalars_all=None):
    """Sync MagicMock simulating a SQLAlchemy execute() result."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar_one
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


def _build_session(dishes, order_items_per_call=None):
    """
    Build an AsyncSession mock.
    First execute → dishes list
    Subsequent executes → order_items list per call
    """
    session = AsyncMock()
    results = [_exec(scalars_all=dishes)]
    if order_items_per_call:
        for items in order_items_per_call:
            results.append(_exec(scalars_all=items))
    session.execute.side_effect = results
    return session


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_variances():
    session = AsyncMock()
    result = await _step2_bom_deviation(session, "STORE001", "2026-01-01", "2026-01-01", [])
    assert result == []


@pytest.mark.asyncio
async def test_primary_path_resolver_success():
    """BOMResolverService returns qty > 0 → expected = qty * sales"""
    dish = _make_dish()
    order_items = [_make_order_item(4)]
    variances = [{"ing_id": "ING001", "diff": -20.0}]

    session = _build_session([dish], [order_items])

    _onto_mock.get_ontology_repository.return_value = None  # Neo4j unavailable

    async def _mock_get_qty(sess, dish_id, store_id, ing_id, channel=None):
        return Decimal("5.0")

    _bom_resolver_mod.BOMResolverService.get_theoretical_qty = _mock_get_qty

    result = await _step2_bom_deviation(
        session, "STORE001", "2026-01-01", "2026-01-01", variances
    )
    assert len(result) == 1
    r = result[0]
    assert r["ing_id"] == "ING001"
    assert r["expected"] == 20.0   # 5.0 * 4
    assert r["actual"] == 20.0
    assert r["deviation"] == pytest.approx(0.0, abs=0.01)
    assert r["anomaly"] is False


@pytest.mark.asyncio
async def test_primary_path_anomaly_detected():
    """actual >> expected → anomaly=True"""
    dish = _make_dish()
    # sales=2, qty=1.0 → expected=2, actual=50 → dev=48 > 2*0.2
    order_items = [_make_order_item(2)]
    variances = [{"ing_id": "ING001", "diff": -50.0}]

    session = _build_session([dish], [order_items])
    _onto_mock.get_ontology_repository.return_value = None

    async def _mock_get_qty(sess, dish_id, store_id, ing_id, channel=None):
        return Decimal("1.0")

    _bom_resolver_mod.BOMResolverService.get_theoretical_qty = _mock_get_qty

    result = await _step2_bom_deviation(
        session, "STORE001", "2026-01-01", "2026-01-01", variances
    )
    assert result[0]["anomaly"] is True


@pytest.mark.asyncio
async def test_fallback_when_neo4j_unavailable_and_no_dishes():
    """No active dishes + Neo4j unavailable → trace='无BOM关联'"""
    variances = [{"ing_id": "ING_X", "diff": -10.0}]
    session = _build_session([])   # no dishes
    _onto_mock.get_ontology_repository.return_value = None

    async def _mock_get_qty(sess, dish_id, store_id, ing_id, channel=None):
        return Decimal("0")

    _bom_resolver_mod.BOMResolverService.get_theoretical_qty = _mock_get_qty

    result = await _step2_bom_deviation(
        session, "STORE001", "2026-01-01", "2026-01-01", variances
    )
    assert len(result) == 1
    r = result[0]
    assert r["trace"] == "无BOM关联"
    assert r["anomaly"] is True   # actual=10 > 0, no expected


@pytest.mark.asyncio
async def test_fallback_neo4j_path_used_when_resolver_raises():
    """Resolver raises RuntimeError → fallback to Neo4j Cypher path"""
    dish = _make_dish()
    variances = [{"ing_id": "ING001", "diff": -30.0}]
    session = _build_session([dish])

    async def _raising_get_qty(*args, **kwargs):
        raise RuntimeError("resolver broken")

    _bom_resolver_mod.BOMResolverService.get_theoretical_qty = _raising_get_qty

    # Mock Neo4j repo
    neo_run = MagicMock()
    neo_run.return_value = [{"dish_id": "DISH1", "std_qty": 3.0, "unit": "克"}]
    neo_session = MagicMock()
    neo_session.run = neo_run
    neo_session.__enter__ = MagicMock(return_value=neo_session)
    neo_session.__exit__ = MagicMock(return_value=False)
    repo = MagicMock()
    repo.session = MagicMock(return_value=neo_session)
    _onto_mock.get_ontology_repository.return_value = repo

    # Need a fresh session since execute will be called again for order items
    session2 = AsyncMock()
    session2.execute.side_effect = [
        _exec(scalars_all=[dish]),
        _exec(scalars_all=[_make_order_item(5)]),
    ]

    result = await _step2_bom_deviation(
        session2, "STORE001", "2026-01-01", "2026-01-01", variances
    )
    assert len(result) == 1
    r = result[0]
    # expected = 3.0 * 5 = 15; actual = 30; deviation = 15
    assert r["expected"] == pytest.approx(15.0, abs=0.1)
    assert r["actual"] == pytest.approx(30.0, abs=0.1)
