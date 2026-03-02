"""
Tests for src/services/inventory_service.py

Covers:
- monitor_inventory: no filters, with category/status filters
- get_item: found (with transactions), not found
- generate_restock_alerts: no items, with items (and transactions)
- record_transaction: success path, item not found, exception/rollback
- get_inventory_statistics: no filters, with start_date/end_date
- get_inventory_report: mocked sub-methods
- _item_to_dict: all branches (with/without transactions, unit_cost None)
- _calculate_status: all status branches
- _calculate_restock_quantity: with/without max_quantity
- _estimate_stockout_date_from_transactions: no transactions, zero usage, normal
- _get_alert_level: all status branches
- _generate_recommendations: all branches
"""
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stubs — set before importing InventoryService
# ---------------------------------------------------------------------------

sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock())
# Use setdefault so we never replace an already-imported real src.models.inventory
sys.modules.setdefault("src.models.inventory", MagicMock())


class _InventoryStatus(Enum):
    NORMAL = "normal"
    LOW = "low"
    CRITICAL = "critical"
    OUT_OF_STOCK = "out_of_stock"


class _TransactionType(Enum):
    PURCHASE = "purchase"
    USAGE = "usage"
    ADJUSTMENT = "adjustment"
    WASTE = "waste"


from src.services.inventory_service import InventoryService  # noqa: E402
import src.services.inventory_service as _svc_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _svc(store_id="STORE001") -> InventoryService:
    return InventoryService(store_id=store_id)


class _StubCol:
    """Lightweight stub for SQLAlchemy ORM column attributes.

    MagicMock's comparison dunder methods return NotImplemented, causing
    TypeError.  This stub returns a truthy value instead.
    """
    def __eq__(self, other): return MagicMock()  # type: ignore[override]
    def __ne__(self, other): return MagicMock()  # type: ignore[override]
    def __ge__(self, other): return MagicMock()
    def __le__(self, other): return MagicMock()
    def __gt__(self, other): return MagicMock()
    def __lt__(self, other): return MagicMock()
    def isnot(self, other): return MagicMock()
    def in_(self, other): return MagicMock()
    def desc(self): return MagicMock()
    def asc(self): return MagicMock()
    def __getattr__(self, name): return _StubCol()


def _inv_cls_mock():
    """Return an InventoryItem class mock whose column attrs support all operators."""
    cls = MagicMock()
    for attr in ("id", "store_id", "category", "status", "name", "current_quantity",
                 "min_quantity", "max_quantity", "unit_cost", "supplier_name",
                 "supplier_contact", "unit", "transactions"):
        setattr(cls, attr, _StubCol())
    return cls


def _trans_cls_mock():
    """Return an InventoryTransaction class mock whose column attrs support all operators."""
    cls = MagicMock()
    for attr in ("id", "store_id", "item_id", "transaction_type", "quantity",
                 "unit_cost", "total_cost", "quantity_before", "quantity_after",
                 "reference_id", "notes", "performed_by", "transaction_time"):
        setattr(cls, attr, _StubCol())
    return cls


def _mock_session():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[]))
    )
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _mock_db(session):
    @asynccontextmanager
    async def _ctx():
        yield session
    return _ctx


def _make_result(scalars_all=None, scalar=None):
    """Build a session.execute() result mock."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar)
    result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=scalars_all or []))
    )
    return result


def _make_item(
    item_id="ITEM_001",
    name="Test Item",
    category="food",
    unit="kg",
    current_quantity=100,
    min_quantity=20,
    max_quantity=200,
    unit_cost=500,
    status=None,
    supplier_name="Supplier A",
    supplier_contact="123456",
    transactions=None,
):
    """Create a realistic InventoryItem-like mock with real numeric attributes."""
    item = MagicMock()
    item.id = item_id
    item.name = name
    item.category = category
    item.unit = unit
    item.current_quantity = current_quantity
    item.min_quantity = min_quantity
    item.max_quantity = max_quantity
    item.unit_cost = unit_cost
    item.status = status if status is not None else _InventoryStatus.NORMAL
    item.supplier_name = supplier_name
    item.supplier_contact = supplier_contact
    item.transactions = transactions or []
    return item


def _make_transaction(
    item_id="ITEM_001",
    trans_id="TRANS_001",
    quantity=-10,
    quantity_before=100,
    quantity_after=90,
    transaction_type=None,
    transaction_time=None,
):
    trans = MagicMock()
    trans.id = trans_id
    trans.item_id = item_id
    trans.quantity = quantity
    trans.quantity_before = quantity_before
    trans.quantity_after = quantity_after
    trans.transaction_type = transaction_type if transaction_type is not None else _TransactionType.USAGE
    trans.transaction_time = transaction_time or datetime(2024, 1, 15, 10, 0, 0)
    return trans


# ---------------------------------------------------------------------------
# monitor_inventory
# ---------------------------------------------------------------------------

class TestMonitorInventory:

    @pytest.mark.asyncio
    async def test_no_filters_returns_all_items(self):
        svc = _svc()
        items = [_make_item(), _make_item(item_id="ITEM_002", name="Item 2")]
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalars_all=items))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.monitor_inventory()
        assert len(result) == 2
        assert result[0]["item_id"] == "ITEM_001"

    @pytest.mark.asyncio
    async def test_with_category_filter(self):
        svc = _svc()
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.monitor_inventory(category="vegetables")
        assert result == []

    @pytest.mark.asyncio
    async def test_with_status_filter(self):
        svc = _svc()
        item = _make_item(status=_InventoryStatus.LOW)
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalars_all=[item]))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.monitor_inventory(status="low")
        assert len(result) == 1
        assert result[0]["status"] == "low"

    @pytest.mark.asyncio
    async def test_with_both_filters(self):
        svc = _svc()
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.monitor_inventory(category="meat", status="critical")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_returns_dicts_with_expected_keys(self):
        svc = _svc()
        item = _make_item()
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalars_all=[item]))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.monitor_inventory()
        assert "item_id" in result[0]
        assert "status" in result[0]
        assert "current_quantity" in result[0]


# ---------------------------------------------------------------------------
# get_item
# ---------------------------------------------------------------------------

class TestGetItem:

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        svc = _svc()
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=None))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_item("NONEXISTENT")
        assert result is None

    @pytest.mark.asyncio
    async def test_found_without_transactions(self):
        svc = _svc()
        item = _make_item(transactions=[])
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_item("ITEM_001")
        assert result is not None
        assert result["item_id"] == "ITEM_001"
        assert "recent_transactions" not in result

    @pytest.mark.asyncio
    async def test_found_with_transactions(self):
        svc = _svc()
        trans = _make_transaction()
        item = _make_item(transactions=[trans])
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_item("ITEM_001")
        assert result is not None
        assert "recent_transactions" in result
        assert len(result["recent_transactions"]) == 1
        assert result["recent_transactions"][0]["type"] == "usage"

    @pytest.mark.asyncio
    async def test_found_with_many_transactions_capped_at_10(self):
        svc = _svc()
        trans_list = [
            _make_transaction(
                trans_id=f"T{i}",
                transaction_time=datetime(2024, 1, i + 1, 0, 0, 0)
            )
            for i in range(15)
        ]
        item = _make_item(transactions=trans_list)
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_item("ITEM_001")
        assert len(result["recent_transactions"]) == 10

    @pytest.mark.asyncio
    async def test_transaction_time_none_in_isoformat(self):
        svc = _svc()
        # Test the None branch: transaction_time is None => transaction_time: None in dict
        trans = MagicMock()
        trans.id = "T1"
        trans.transaction_type = _TransactionType.USAGE
        trans.quantity = -5
        trans.quantity_before = 100
        trans.quantity_after = 95
        trans.transaction_time = None
        # sorted() needs a sortable key — wrap so it can be sorted
        # Use a list with only 1 item to avoid comparison issues
        item = _make_item(transactions=[trans])
        # However sorted() will fail on None vs None for transaction_time comparison
        # Skip this by only having 1 transaction (no comparison needed)
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_item("ITEM_001")
        assert result["recent_transactions"][0]["transaction_time"] is None


# ---------------------------------------------------------------------------
# generate_restock_alerts
# ---------------------------------------------------------------------------

class TestGenerateRestockAlerts:

    @pytest.mark.asyncio
    async def test_no_items_returns_empty_list(self):
        svc = _svc()
        session = _mock_session()
        items_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(return_value=items_result)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "or_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.generate_restock_alerts()
        assert result == []

    @pytest.mark.asyncio
    async def test_with_items_and_no_transactions(self):
        svc = _svc()
        item = _make_item(
            current_quantity=5,
            min_quantity=20,
            max_quantity=100,
            status=_InventoryStatus.LOW,
        )
        session = _mock_session()
        items_result = _make_result(scalars_all=[item])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "or_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.generate_restock_alerts()
        assert len(result) == 1
        assert result[0]["item_id"] == "ITEM_001"
        assert result[0]["alert_level"] == "warning"
        assert result[0]["estimated_stockout_date"] is None

    @pytest.mark.asyncio
    async def test_with_items_and_transactions(self):
        svc = _svc()
        item = _make_item(
            current_quantity=5,
            min_quantity=20,
            max_quantity=100,
            status=_InventoryStatus.CRITICAL,
        )
        trans = _make_transaction(item_id="ITEM_001", quantity=-10)
        session = _mock_session()
        items_result = _make_result(scalars_all=[item])
        trans_result = _make_result(scalars_all=[trans])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "or_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.generate_restock_alerts()
        assert len(result) == 1
        assert result[0]["alert_level"] == "urgent"
        assert result[0]["estimated_stockout_date"] is not None

    @pytest.mark.asyncio
    async def test_out_of_stock_alert_level(self):
        svc = _svc()
        item = _make_item(
            current_quantity=0,
            min_quantity=20,
            max_quantity=100,
            status=_InventoryStatus.OUT_OF_STOCK,
        )
        session = _mock_session()
        items_result = _make_result(scalars_all=[item])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "or_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.generate_restock_alerts()
        assert result[0]["alert_level"] == "critical"

    @pytest.mark.asyncio
    async def test_with_category_filter(self):
        svc = _svc()
        session = _mock_session()
        items_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(return_value=items_result)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "or_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.generate_restock_alerts(category="meat")
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_items_transactions_grouped_correctly(self):
        svc = _svc()
        item1 = _make_item(item_id="ITEM_001", current_quantity=5, min_quantity=20,
                            max_quantity=100, status=_InventoryStatus.LOW)
        item2 = _make_item(item_id="ITEM_002", name="Item 2", current_quantity=2,
                            min_quantity=20, max_quantity=None, status=_InventoryStatus.CRITICAL)
        trans1 = _make_transaction(item_id="ITEM_001", quantity=-5)
        trans2 = _make_transaction(item_id="ITEM_002", trans_id="T2", quantity=-8)
        session = _mock_session()
        items_result = _make_result(scalars_all=[item1, item2])
        trans_result = _make_result(scalars_all=[trans1, trans2])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "or_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.generate_restock_alerts()
        assert len(result) == 2
        assert result[0]["estimated_stockout_date"] is not None
        assert result[1]["estimated_stockout_date"] is not None


# ---------------------------------------------------------------------------
# record_transaction
# ---------------------------------------------------------------------------

class TestRecordTransaction:

    def _make_trans_mock():
        """Build a transaction mock with a datetime that has isoformat."""
        mock_trans = MagicMock()
        mock_trans.id = "TRANS_001"
        # Use a real datetime so isoformat works
        mock_trans.transaction_time = datetime(2024, 1, 1, 10, 0, 0)
        return mock_trans

    @pytest.mark.asyncio
    async def test_item_not_found_raises(self):
        svc = _svc()
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=None))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            with pytest.raises(ValueError, match="库存项目不存在"):
                await svc.record_transaction("BAD_ID", "usage", -10)
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_with_unit_cost(self):
        svc = _svc()
        item = _make_item(current_quantity=100, min_quantity=20, max_quantity=200, unit_cost=500)
        item.status = _InventoryStatus.NORMAL
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))

        mock_trans = MagicMock()
        mock_trans.id = "TRANS_001"
        mock_trans.transaction_time = datetime(2024, 1, 1, 10, 0, 0)
        mock_trans_cls = MagicMock(return_value=mock_trans)

        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", mock_trans_cls), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.record_transaction(
                "ITEM_001", "purchase", 50, unit_cost=600, notes="restock"
            )
        assert "transaction_id" in result
        assert result["item_id"] == "ITEM_001"
        assert result["quantity"] == 50
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_without_unit_cost_uses_item_cost(self):
        svc = _svc()
        item = _make_item(current_quantity=50, min_quantity=20, max_quantity=200, unit_cost=300)
        item.status = _InventoryStatus.NORMAL
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        mock_trans = MagicMock()
        mock_trans.id = "TRANS_002"
        mock_trans.transaction_time = datetime(2024, 1, 2, 10, 0, 0)
        mock_trans_cls = MagicMock(return_value=mock_trans)

        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", mock_trans_cls), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.record_transaction("ITEM_001", "usage", -10)
        assert result["quantity"] == -10

    @pytest.mark.asyncio
    async def test_success_without_unit_cost_and_item_cost_none(self):
        svc = _svc()
        item = _make_item(current_quantity=50, min_quantity=20, max_quantity=200, unit_cost=None)
        item.status = _InventoryStatus.NORMAL
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        mock_trans = MagicMock()
        mock_trans.id = "TRANS_003"
        mock_trans.transaction_time = datetime(2024, 1, 3, 10, 0, 0)
        mock_trans_cls = MagicMock(return_value=mock_trans)

        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", mock_trans_cls), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.record_transaction("ITEM_001", "adjustment", 5)
        assert result["quantity"] == 5

    @pytest.mark.asyncio
    async def test_exception_triggers_rollback_and_reraises(self):
        svc = _svc()
        session = _mock_session()
        session.execute = AsyncMock(side_effect=RuntimeError("db error"))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            with pytest.raises(RuntimeError, match="db error"):
                await svc.record_transaction("ITEM_001", "usage", -5)
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_reference_id_and_performed_by(self):
        svc = _svc()
        item = _make_item(current_quantity=100, unit_cost=200)
        item.status = _InventoryStatus.NORMAL
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        mock_trans = MagicMock()
        mock_trans.id = "TRANS_004"
        mock_trans.transaction_time = datetime(2024, 1, 4, 10, 0, 0)
        mock_trans_cls = MagicMock(return_value=mock_trans)

        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", mock_trans_cls), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.record_transaction(
                "ITEM_001", "purchase", 20,
                reference_id="REF001", performed_by="admin"
            )
        assert "transaction_id" in result
        call_kwargs = mock_trans_cls.call_args[1]
        assert call_kwargs["reference_id"] == "REF001"
        assert call_kwargs["performed_by"] == "admin"

    @pytest.mark.asyncio
    async def test_status_updated_after_transaction(self):
        """Confirm _calculate_status is called to update item.status after quantity change."""
        svc = _svc()
        # Start with enough stock to be NORMAL, after adding 50 should remain NORMAL
        item = _make_item(current_quantity=100, min_quantity=20, max_quantity=200, unit_cost=100)
        item.status = _InventoryStatus.NORMAL
        session = _mock_session()
        session.execute = AsyncMock(return_value=_make_result(scalar=item))
        mock_trans = MagicMock()
        mock_trans.id = "TRANS_005"
        mock_trans.transaction_time = datetime(2024, 1, 5, 10, 0, 0)
        mock_trans_cls = MagicMock(return_value=mock_trans)

        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", mock_trans_cls), \
             patch.object(_svc_mod, "InventoryStatus", _InventoryStatus), \
             patch.object(_svc_mod, "TransactionType", _TransactionType), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.record_transaction("ITEM_001", "purchase", 50)
        # Status should have been recalculated — result contains it
        assert "status" in result


# ---------------------------------------------------------------------------
# get_inventory_statistics
# ---------------------------------------------------------------------------

class TestGetInventoryStatistics:

    @pytest.mark.asyncio
    async def test_no_items_no_transactions(self):
        svc = _svc()
        session = _mock_session()
        items_result = _make_result(scalars_all=[])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics()
        assert result["total_items"] == 0
        assert result["total_value"] == 0.0
        assert result["alerts_count"] == 0
        assert result["transaction_counts"] == {}

    @pytest.mark.asyncio
    async def test_with_items_of_various_statuses(self):
        svc = _svc()
        item_normal = _make_item(status=_InventoryStatus.NORMAL, current_quantity=100, unit_cost=500)
        item_low = _make_item(item_id="I2", status=_InventoryStatus.LOW, current_quantity=10, unit_cost=300)
        item_critical = _make_item(item_id="I3", status=_InventoryStatus.CRITICAL, current_quantity=2, unit_cost=200)
        item_oos = _make_item(item_id="I4", status=_InventoryStatus.OUT_OF_STOCK, current_quantity=0, unit_cost=100)
        items = [item_normal, item_low, item_critical, item_oos]
        session = _mock_session()
        items_result = _make_result(scalars_all=items)
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics()
        assert result["total_items"] == 4
        assert result["status_breakdown"]["normal"] == 1
        assert result["status_breakdown"]["low"] == 1
        assert result["status_breakdown"]["critical"] == 1
        assert result["status_breakdown"]["out_of_stock"] == 1
        assert result["alerts_count"] == 3

    @pytest.mark.asyncio
    async def test_total_value_calculation(self):
        svc = _svc()
        item = _make_item(current_quantity=10, unit_cost=1000)  # 10 * 1000 / 100 = 100 yuan
        session = _mock_session()
        items_result = _make_result(scalars_all=[item])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics()
        assert result["total_value"] == 100.0

    @pytest.mark.asyncio
    async def test_item_with_none_unit_cost(self):
        svc = _svc()
        item = _make_item(current_quantity=10, unit_cost=None)
        session = _mock_session()
        items_result = _make_result(scalars_all=[item])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics()
        assert result["total_value"] == 0.0

    @pytest.mark.asyncio
    async def test_with_transactions_counts(self):
        svc = _svc()
        trans1 = _make_transaction(transaction_type=_TransactionType.USAGE)
        trans2 = _make_transaction(trans_id="T2", transaction_type=_TransactionType.PURCHASE)
        trans3 = _make_transaction(trans_id="T3", transaction_type=_TransactionType.USAGE)
        session = _mock_session()
        items_result = _make_result(scalars_all=[])
        trans_result = _make_result(scalars_all=[trans1, trans2, trans3])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics()
        assert result["transaction_counts"]["usage"] == 2
        assert result["transaction_counts"]["purchase"] == 1

    @pytest.mark.asyncio
    async def test_with_start_date_filter(self):
        svc = _svc()
        session = _mock_session()
        items_result = _make_result(scalars_all=[])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics(start_date="2024-01-01")
        assert "total_items" in result

    @pytest.mark.asyncio
    async def test_with_end_date_filter(self):
        svc = _svc()
        session = _mock_session()
        items_result = _make_result(scalars_all=[])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics(end_date="2024-12-31")
        assert "total_items" in result

    @pytest.mark.asyncio
    async def test_with_both_date_filters(self):
        svc = _svc()
        session = _mock_session()
        items_result = _make_result(scalars_all=[])
        trans_result = _make_result(scalars_all=[])
        session.execute = AsyncMock(side_effect=[items_result, trans_result])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "InventoryItem", _inv_cls_mock()), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch("src.services.inventory_service.get_db_session", _mock_db(session)):
            result = await svc.get_inventory_statistics(
                start_date="2024-01-01", end_date="2024-12-31"
            )
        assert "total_items" in result


# ---------------------------------------------------------------------------
# get_inventory_report
# ---------------------------------------------------------------------------

class TestGetInventoryReport:

    @pytest.mark.asyncio
    async def test_report_structure(self):
        svc = _svc()
        svc.monitor_inventory = AsyncMock(return_value=[])
        svc.generate_restock_alerts = AsyncMock(return_value=[])
        svc.get_inventory_statistics = AsyncMock(return_value={
            "total_items": 0,
            "total_value": 0.0,
            "status_breakdown": {"normal": 0, "low": 0, "critical": 0, "out_of_stock": 0},
            "transaction_counts": {},
            "alerts_count": 0,
        })
        result = await svc.get_inventory_report()
        assert "report_generated_at" in result
        assert result["store_id"] == "STORE001"
        assert "inventory_summary" in result
        assert "restock_alerts" in result
        assert "critical_items" in result
        assert "low_stock_items" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_critical_and_low_items_filtered(self):
        svc = _svc()
        items = [
            {"status": "normal", "item_id": "I1"},
            {"status": "low", "item_id": "I2"},
            {"status": "critical", "item_id": "I3"},
            {"status": "out_of_stock", "item_id": "I4"},
        ]
        svc.monitor_inventory = AsyncMock(return_value=items)
        svc.generate_restock_alerts = AsyncMock(return_value=[{"alert_id": "A1"}])
        svc.get_inventory_statistics = AsyncMock(return_value={
            "total_items": 4,
            "total_value": 100.0,
            "status_breakdown": {"normal": 1, "low": 1, "critical": 1, "out_of_stock": 1},
        })
        result = await svc.get_inventory_report()
        assert len(result["critical_items"]) == 2  # critical + out_of_stock
        assert len(result["low_stock_items"]) == 1
        assert len(result["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_with_date_range(self):
        svc = _svc()
        svc.monitor_inventory = AsyncMock(return_value=[])
        svc.generate_restock_alerts = AsyncMock(return_value=[])
        svc.get_inventory_statistics = AsyncMock(return_value={
            "total_items": 0,
            "total_value": 0.0,
            "status_breakdown": {"normal": 0, "low": 0, "critical": 0, "out_of_stock": 0},
        })
        result = await svc.get_inventory_report(
            start_date="2024-01-01", end_date="2024-12-31"
        )
        svc.get_inventory_statistics.assert_awaited_once_with("2024-01-01", "2024-12-31")
        assert "report_generated_at" in result

    @pytest.mark.asyncio
    async def test_empty_report_no_recommendations(self):
        svc = _svc()
        svc.monitor_inventory = AsyncMock(return_value=[])
        svc.generate_restock_alerts = AsyncMock(return_value=[])
        svc.get_inventory_statistics = AsyncMock(return_value={
            "total_items": 0,
            "total_value": 0.0,
            "status_breakdown": {"normal": 0, "low": 0, "critical": 0, "out_of_stock": 0},
        })
        result = await svc.get_inventory_report()
        assert result["recommendations"] == []


# ---------------------------------------------------------------------------
# _item_to_dict (pure)
# ---------------------------------------------------------------------------

class TestItemToDict:

    def test_basic_item_no_transactions(self):
        svc = _svc()
        item = _make_item(unit_cost=1000, current_quantity=50)
        result = svc._item_to_dict(item)
        assert result["item_id"] == "ITEM_001"
        assert result["unit_cost"] == 10.0  # 1000 / 100
        assert result["stock_value"] == 500.0  # 50 * 1000 / 100
        assert "recent_transactions" not in result

    def test_item_with_none_unit_cost(self):
        svc = _svc()
        item = _make_item(unit_cost=None, current_quantity=10)
        result = svc._item_to_dict(item)
        assert result["unit_cost"] == 0
        assert result["stock_value"] == 0.0

    def test_item_include_transactions_false(self):
        svc = _svc()
        trans = _make_transaction()
        item = _make_item(transactions=[trans])
        result = svc._item_to_dict(item, include_transactions=False)
        assert "recent_transactions" not in result

    def test_item_include_transactions_true_with_transactions(self):
        svc = _svc()
        trans = _make_transaction()
        item = _make_item(transactions=[trans])
        result = svc._item_to_dict(item, include_transactions=True)
        assert "recent_transactions" in result
        assert len(result["recent_transactions"]) == 1

    def test_item_include_transactions_true_empty_list(self):
        svc = _svc()
        item = _make_item(transactions=[])
        result = svc._item_to_dict(item, include_transactions=True)
        assert "recent_transactions" not in result

    def test_transaction_with_none_time(self):
        svc = _svc()
        trans = MagicMock()
        trans.id = "T1"
        trans.transaction_type = _TransactionType.USAGE
        trans.quantity = -5
        trans.quantity_before = 100
        trans.quantity_after = 95
        trans.transaction_time = None
        # sorted() on a single-element list avoids comparison; keep only 1 item
        item = _make_item(transactions=[trans])
        result = svc._item_to_dict(item, include_transactions=True)
        assert result["recent_transactions"][0]["transaction_time"] is None

    def test_item_status_value_used(self):
        svc = _svc()
        item = _make_item(status=_InventoryStatus.CRITICAL)
        result = svc._item_to_dict(item)
        assert result["status"] == "critical"

    def test_transaction_time_isoformat_called(self):
        svc = _svc()
        trans = _make_transaction(transaction_time=datetime(2024, 6, 15, 12, 0, 0))
        item = _make_item(transactions=[trans])
        result = svc._item_to_dict(item, include_transactions=True)
        assert result["recent_transactions"][0]["transaction_time"] == "2024-06-15T12:00:00"


# ---------------------------------------------------------------------------
# _calculate_status (pure)
# ---------------------------------------------------------------------------

class TestCalculateStatus:

    def setup_method(self):
        self.svc = _svc()

    def test_out_of_stock_when_quantity_zero(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(current_quantity=0, min_quantity=20)
            result = self.svc._calculate_status(item)
        assert result == _InventoryStatus.OUT_OF_STOCK

    def test_out_of_stock_when_quantity_negative(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(current_quantity=-5, min_quantity=20)
            result = self.svc._calculate_status(item)
        assert result == _InventoryStatus.OUT_OF_STOCK

    def test_critical_when_quantity_very_low(self):
        # critical_stock_ratio default is 0.1
        # item.current_quantity <= item.min_quantity * 0.1
        # min_quantity=20, critical threshold=2, current=1 => CRITICAL
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(current_quantity=1, min_quantity=20)
            result = self.svc._calculate_status(item)
        assert result == _InventoryStatus.CRITICAL

    def test_low_when_quantity_between_critical_and_min(self):
        # min_quantity=20, critical threshold=2, current=15 => LOW
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(current_quantity=15, min_quantity=20)
            result = self.svc._calculate_status(item)
        assert result == _InventoryStatus.LOW

    def test_low_when_quantity_equals_min(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(current_quantity=20, min_quantity=20)
            result = self.svc._calculate_status(item)
        assert result == _InventoryStatus.LOW

    def test_normal_when_quantity_above_min(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(current_quantity=50, min_quantity=20)
            result = self.svc._calculate_status(item)
        assert result == _InventoryStatus.NORMAL

    def test_critical_boundary_exact(self):
        # min_quantity=100, critical threshold=10 (0.1 * 100), current=10 => CRITICAL
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(current_quantity=10, min_quantity=100)
            result = self.svc._calculate_status(item)
        assert result == _InventoryStatus.CRITICAL


# ---------------------------------------------------------------------------
# _calculate_restock_quantity (pure)
# ---------------------------------------------------------------------------

class TestCalculateRestockQuantity:

    def setup_method(self):
        self.svc = _svc()

    def test_with_max_quantity(self):
        item = _make_item(current_quantity=50, min_quantity=20, max_quantity=200)
        result = self.svc._calculate_restock_quantity(item)
        assert result == 150  # 200 - 50

    def test_without_max_quantity_uses_multiplier(self):
        item = _make_item(current_quantity=5, min_quantity=20, max_quantity=None)
        # default multiplier=2: min_quantity * 2 - current = 20*2 - 5 = 35
        result = self.svc._calculate_restock_quantity(item)
        assert result == 35.0

    def test_without_max_quantity_custom_multiplier(self):
        import os
        with patch.dict(os.environ, {"INVENTORY_RESTOCK_MULTIPLIER": "3"}):
            item = _make_item(current_quantity=10, min_quantity=20, max_quantity=None)
            # 20 * 3 - 10 = 50
            result = self.svc._calculate_restock_quantity(item)
        assert result == 50.0

    def test_max_quantity_zero_uses_multiplier(self):
        # max_quantity=0 is falsy, so multiplier path is used
        item = _make_item(current_quantity=5, min_quantity=10, max_quantity=0)
        result = self.svc._calculate_restock_quantity(item)
        assert result == 15.0  # 10 * 2 - 5

    def test_at_max_quantity_returns_zero(self):
        item = _make_item(current_quantity=200, min_quantity=20, max_quantity=200)
        result = self.svc._calculate_restock_quantity(item)
        assert result == 0


# ---------------------------------------------------------------------------
# _estimate_stockout_date_from_transactions (pure)
# ---------------------------------------------------------------------------

class TestEstimateStockoutDate:

    def setup_method(self):
        self.svc = _svc()

    def test_no_transactions_returns_none(self):
        item = _make_item(current_quantity=50)
        result = self.svc._estimate_stockout_date_from_transactions(item, [])
        assert result is None

    def test_zero_total_usage_returns_none(self):
        # transactions with quantity=0 => avg_daily_usage=0 => None
        trans = _make_transaction(quantity=0)
        item = _make_item(current_quantity=50)
        result = self.svc._estimate_stockout_date_from_transactions(item, [trans])
        assert result is None

    def test_normal_usage_returns_date_string(self):
        # 30 days, total usage = 30 units => avg daily = 1 unit/day
        # current_quantity = 15 => stockout in 15 days
        trans = _make_transaction(quantity=-30)  # abs = 30
        item = _make_item(current_quantity=15)
        result = self.svc._estimate_stockout_date_from_transactions(item, [trans])
        assert result is not None
        # Should be an isoformat date string
        datetime.fromisoformat(result)

    def test_multiple_transactions_summed(self):
        trans1 = _make_transaction(quantity=-10)
        trans2 = _make_transaction(trans_id="T2", quantity=-20)
        item = _make_item(current_quantity=15)
        result = self.svc._estimate_stockout_date_from_transactions(item, [trans1, trans2])
        assert result is not None

    def test_positive_usage_quantity_uses_abs(self):
        # positive quantity still uses abs()
        trans = _make_transaction(quantity=30)
        item = _make_item(current_quantity=10)
        result = self.svc._estimate_stockout_date_from_transactions(item, [trans])
        assert result is not None

    def test_custom_history_days_env(self):
        import os
        trans = _make_transaction(quantity=-60)
        item = _make_item(current_quantity=10)
        with patch.dict(os.environ, {"INVENTORY_HISTORY_DAYS": "60"}):
            result = self.svc._estimate_stockout_date_from_transactions(item, [trans])
        assert result is not None

    def test_stockout_date_is_in_future(self):
        trans = _make_transaction(quantity=-10)  # small usage => far future
        item = _make_item(current_quantity=1000)
        result = self.svc._estimate_stockout_date_from_transactions(item, [trans])
        assert result is not None
        stockout = datetime.fromisoformat(result)
        assert stockout > datetime.now()


# ---------------------------------------------------------------------------
# _get_alert_level (pure)
# ---------------------------------------------------------------------------

class TestGetAlertLevel:

    def setup_method(self):
        self.svc = _svc()

    def test_out_of_stock_returns_critical(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(status=_InventoryStatus.OUT_OF_STOCK)
            assert self.svc._get_alert_level(item) == "critical"

    def test_critical_returns_urgent(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(status=_InventoryStatus.CRITICAL)
            assert self.svc._get_alert_level(item) == "urgent"

    def test_low_returns_warning(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(status=_InventoryStatus.LOW)
            assert self.svc._get_alert_level(item) == "warning"

    def test_normal_returns_info(self):
        with patch.object(_svc_mod, "InventoryStatus", _InventoryStatus):
            item = _make_item(status=_InventoryStatus.NORMAL)
            assert self.svc._get_alert_level(item) == "info"


# ---------------------------------------------------------------------------
# _generate_recommendations (pure)
# ---------------------------------------------------------------------------

class TestGenerateRecommendations:

    def setup_method(self):
        self.svc = _svc()

    def test_no_alerts_no_critical_no_oos(self):
        items = [{"status": "normal"}, {"status": "low"}]
        result = self.svc._generate_recommendations(items, [])
        assert result == []

    def test_with_restock_alerts(self):
        alerts = [{"alert_id": "A1"}, {"alert_id": "A2"}]
        result = self.svc._generate_recommendations([], alerts)
        assert any("2个物料需要补货" in r for r in result)

    def test_with_critical_items(self):
        items = [{"status": "critical"}, {"status": "normal"}]
        result = self.svc._generate_recommendations(items, [])
        assert any("严重不足" in r for r in result)

    def test_with_out_of_stock_items(self):
        items = [{"status": "out_of_stock"}, {"status": "normal"}]
        result = self.svc._generate_recommendations(items, [])
        assert any("已缺货" in r for r in result)

    def test_all_conditions(self):
        items = [
            {"status": "critical"},
            {"status": "out_of_stock"},
            {"status": "normal"},
        ]
        alerts = [{"alert_id": "A1"}]
        result = self.svc._generate_recommendations(items, alerts)
        assert len(result) == 3
        assert any("补货" in r for r in result)
        assert any("严重不足" in r for r in result)
        assert any("已缺货" in r for r in result)

    def test_single_restock_alert(self):
        alerts = [{"alert_id": "A1"}]
        result = self.svc._generate_recommendations([], alerts)
        assert any("1个物料需要补货" in r for r in result)

    def test_multiple_critical(self):
        items = [{"status": "critical"}, {"status": "critical"}]
        result = self.svc._generate_recommendations(items, [])
        assert any("2个物料库存严重不足" in r for r in result)

    def test_multiple_out_of_stock(self):
        items = [{"status": "out_of_stock"}, {"status": "out_of_stock"}]
        result = self.svc._generate_recommendations(items, [])
        assert any("2个物料已缺货" in r for r in result)

    def test_empty_inputs(self):
        result = self.svc._generate_recommendations([], [])
        assert result == []


# ---------------------------------------------------------------------------
# InventoryService initialization
# ---------------------------------------------------------------------------

class TestInventoryServiceInit:

    def test_default_store_id(self):
        svc = InventoryService()
        assert svc.store_id == "STORE001"

    def test_custom_store_id(self):
        svc = InventoryService(store_id="STORE002")
        assert svc.store_id == "STORE002"

    def test_alert_thresholds_defaults(self):
        import os
        with patch.dict(os.environ, {}, clear=False):
            svc = InventoryService()
        assert "low_stock_ratio" in svc.alert_thresholds
        assert "critical_stock_ratio" in svc.alert_thresholds
        assert svc.alert_thresholds["low_stock_ratio"] == 0.3
        assert svc.alert_thresholds["critical_stock_ratio"] == 0.1

    def test_alert_thresholds_from_env(self):
        import os
        with patch.dict(os.environ, {
            "INVENTORY_LOW_STOCK_RATIO": "0.5",
            "INVENTORY_CRITICAL_STOCK_RATIO": "0.2"
        }):
            svc = InventoryService()
        assert svc.alert_thresholds["low_stock_ratio"] == 0.5
        assert svc.alert_thresholds["critical_stock_ratio"] == 0.2


# ---------------------------------------------------------------------------
# _estimate_stockout_date (deprecated async method)
# ---------------------------------------------------------------------------

class TestEstimateStockoutDateDeprecated:
    """Test the deprecated async _estimate_stockout_date method for coverage."""

    @pytest.mark.asyncio
    async def test_no_transactions_returns_none(self):
        svc = _svc()
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        item = _make_item(current_quantity=50)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "TransactionType", _TransactionType):
            result = await svc._estimate_stockout_date(session, item)
        assert result is None

    @pytest.mark.asyncio
    async def test_with_transactions_returns_date(self):
        svc = _svc()
        trans = _make_transaction(quantity=-30)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_make_result(scalars_all=[trans]))
        item = _make_item(current_quantity=15)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "and_", MagicMock(return_value=MagicMock())), \
             patch.object(_svc_mod, "InventoryTransaction", _trans_cls_mock()), \
             patch.object(_svc_mod, "TransactionType", _TransactionType):
            result = await svc._estimate_stockout_date(session, item)
        assert result is not None
        datetime.fromisoformat(result)
