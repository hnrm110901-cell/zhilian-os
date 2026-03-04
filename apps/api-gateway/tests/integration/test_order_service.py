"""
Tests for src/services/order_service.py

Covers:
- create_order: success path and exception/rollback
- get_order: found and not-found
- list_orders: no filters, with status/table/date filters
- update_order_status: CONFIRMED / COMPLETED timestamps, not-found
- add_items: success and not-found
- cancel_order: with/without reason, not-found
- get_order_statistics: with/without orders
- _order_to_dict: items from list, items from order.items, no items
"""
import sys
from contextlib import asynccontextmanager
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stubs — must be set before importing OrderService
# ---------------------------------------------------------------------------

sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock())
# Use setdefault so we never replace an already-imported real src.models.order
# (test_store_memory_service.py needs the real OrderItem for its dish_id patch).
sys.modules.setdefault("src.models.order", MagicMock())


class _OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PAID = "paid"


from src.services.order_service import OrderService  # noqa: E402
import src.services.order_service as _svc_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _svc(store_id="S1") -> OrderService:
    return OrderService(store_id=store_id)


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


def _order_cls_mock():
    """Return an Order class mock whose column attrs support all operators."""
    cls = MagicMock()
    for attr in ("id", "store_id", "table_number", "status", "order_time", "items"):
        setattr(cls, attr, _StubCol())
    return cls


def _mock_session(scalar=None, scalars_all=None):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar)
    result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=scalars_all or []))
    )
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _mock_db(session):
    @asynccontextmanager
    async def _ctx():
        yield session
    return _ctx


def _make_order(status=_OrderStatus.PENDING, store_id="S1",
                table_number="T1", final_amount=10000, notes=None):
    order = MagicMock()
    order.id = "ORD_001"
    order.store_id = store_id
    order.table_number = table_number
    order.customer_name = "Test"
    order.customer_phone = "123"
    order.status = status
    order.total_amount = 10000
    order.discount_amount = 0
    order.final_amount = final_amount
    order.order_time = MagicMock()
    order.order_time.isoformat = MagicMock(return_value="2024-01-01T00:00:00")
    order.confirmed_at = None
    order.completed_at = None
    order.notes = notes
    order.order_metadata = {}
    order.items = []
    return order


# ---------------------------------------------------------------------------
# _order_to_dict (pure function — no DB needed)
# ---------------------------------------------------------------------------

class TestOrderToDict:

    def test_minimal_order_no_items(self):
        svc = _svc()
        order = _make_order()
        result = svc._order_to_dict(order)
        assert result["order_id"] == "ORD_001"
        assert result["status"] == "pending"
        assert result["items"] == []

    def test_with_items_list_passed_directly(self):
        svc = _svc()
        order = _make_order()
        items = [{"item_id": "I1", "item_name": "饺子", "quantity": 2, "unit_price": 500}]
        result = svc._order_to_dict(order, items=items)
        assert result["items"] == items

    def test_with_items_from_order_relationship(self):
        svc = _svc()
        order = _make_order()
        item_mock = MagicMock()
        item_mock.item_id = "I1"
        item_mock.item_name = "鸡翅"
        item_mock.quantity = 3
        item_mock.unit_price = 800
        item_mock.subtotal = 2400
        item_mock.notes = None
        item_mock.customizations = {}
        order.items = [item_mock]
        result = svc._order_to_dict(order)
        assert len(result["items"]) == 1
        assert result["items"][0]["item_name"] == "鸡翅"

    def test_confirmed_at_and_completed_at_isoformat(self):
        svc = _svc()
        order = _make_order()
        order.confirmed_at = MagicMock()
        order.confirmed_at.isoformat = MagicMock(return_value="2024-01-01T10:00:00")
        order.completed_at = MagicMock()
        order.completed_at.isoformat = MagicMock(return_value="2024-01-01T11:00:00")
        result = svc._order_to_dict(order)
        assert result["confirmed_at"] == "2024-01-01T10:00:00"
        assert result["completed_at"] == "2024-01-01T11:00:00"

    def test_none_timestamps_become_none(self):
        svc = _svc()
        order = _make_order()
        order.order_time = None
        result = svc._order_to_dict(order)
        assert result["order_time"] is None


# ---------------------------------------------------------------------------
# create_order
# ---------------------------------------------------------------------------

class TestCreateOrder:

    @pytest.mark.asyncio
    async def test_success_returns_order_dict(self):
        svc = _svc()
        session = _mock_session()
        created_order = _make_order()
        mock_order_cls = MagicMock(return_value=created_order)

        items = [{"item_id": "I1", "item_name": "面", "quantity": 2, "unit_price": 500}]
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "Order", mock_order_cls), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.create_order("T1", items)

        session.add.assert_called()
        session.commit.assert_awaited_once()
        assert "order_id" in result

    @pytest.mark.asyncio
    async def test_calculates_total_from_items(self):
        svc = _svc()
        session = _mock_session()
        mock_order_cls = MagicMock()
        mock_order_cls.return_value = _make_order()

        items = [
            {"item_id": "I1", "item_name": "A", "quantity": 2, "unit_price": 300},
            {"item_id": "I2", "item_name": "B", "quantity": 1, "unit_price": 400},
        ]
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "Order", mock_order_cls), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            await svc.create_order("T1", items, discount_amount=100)

        # Order constructor is called with total_amount=1000, discount_amount=100
        call_kwargs = mock_order_cls.call_args[1]
        assert call_kwargs["total_amount"] == 1000
        assert call_kwargs["discount_amount"] == 100
        assert call_kwargs["final_amount"] == 900

    @pytest.mark.asyncio
    async def test_exception_triggers_rollback_and_reraises(self):
        svc = _svc()
        session = _mock_session()
        session.flush = AsyncMock(side_effect=RuntimeError("db error"))

        items = [{"item_id": "I1", "item_name": "A", "quantity": 1, "unit_price": 100}]
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            with pytest.raises(RuntimeError, match="db error"):
                await svc.create_order("T1", items)

        session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_order
# ---------------------------------------------------------------------------

class TestGetOrder:

    @pytest.mark.asyncio
    async def test_found_returns_dict(self):
        svc = _svc()
        order = _make_order()
        session = _mock_session(scalar=order)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.get_order("ORD_001")
        assert result is not None
        assert result["order_id"] == "ORD_001"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        svc = _svc()
        session = _mock_session(scalar=None)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.get_order("NONEXISTENT")
        assert result is None


# ---------------------------------------------------------------------------
# list_orders
# ---------------------------------------------------------------------------

class TestListOrders:

    @pytest.mark.asyncio
    async def test_no_filters_returns_all(self):
        svc = _svc()
        orders = [_make_order(), _make_order()]
        session = _mock_session(scalars_all=orders)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.list_orders()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_with_all_filters(self):
        svc = _svc()
        session = _mock_session(scalars_all=[])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "Order", _order_cls_mock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.list_orders(
                status="completed",
                table_number="T1",
                start_date="2024-01-01",
                end_date="2024-01-31",
                limit=10,
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_returns_dicts(self):
        svc = _svc()
        session = _mock_session(scalars_all=[_make_order()])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.list_orders()
        assert "order_id" in result[0]


# ---------------------------------------------------------------------------
# update_order_status
# ---------------------------------------------------------------------------

class TestUpdateOrderStatus:

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        svc = _svc()
        session = _mock_session(scalar=None)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            with pytest.raises(ValueError, match="订单不存在"):
                await svc.update_order_status("BAD_ID", "confirmed")
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirmed_sets_confirmed_at(self):
        svc = _svc()
        order = _make_order()
        session = _mock_session(scalar=order)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            await svc.update_order_status("ORD_001", "confirmed")
        assert order.confirmed_at is not None

    @pytest.mark.asyncio
    async def test_completed_sets_completed_at(self):
        svc = _svc()
        order = _make_order()
        session = _mock_session(scalar=order)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            await svc.update_order_status("ORD_001", "completed")
        assert order.completed_at is not None

    @pytest.mark.asyncio
    async def test_notes_updated_when_provided(self):
        svc = _svc()
        order = _make_order()
        session = _mock_session(scalar=order)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            await svc.update_order_status("ORD_001", "preparing", notes="rush order")
        assert order.notes == "rush order"

    @pytest.mark.asyncio
    async def test_exception_triggers_rollback_and_reraises(self):
        svc = _svc()
        session = _mock_session(scalar=None)
        session.rollback = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db error"))
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            with pytest.raises(RuntimeError, match="db error"):
                await svc.update_order_status("ORD_001", "confirmed")
        session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# add_items
# ---------------------------------------------------------------------------

class TestAddItems:

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        svc = _svc()
        session = _mock_session(scalar=None)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            with pytest.raises(ValueError, match="订单不存在"):
                await svc.add_items("BAD_ID", [])
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_adds_items_and_commits(self):
        svc = _svc()
        order = _make_order()
        session = _mock_session(scalar=order)
        items = [{"item_id": "I2", "item_name": "鸡翅", "quantity": 2, "unit_price": 400}]
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.add_items("ORD_001", items)
        session.add.assert_called()
        session.commit.assert_awaited_once()
        assert "order_id" in result


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------

class TestCancelOrder:

    @pytest.mark.asyncio
    async def test_cancels_order(self):
        svc = _svc()
        order = _make_order()
        session = _mock_session(scalar=order)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "OrderStatus", _OrderStatus), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            await svc.cancel_order("ORD_001")
        assert order.status == _OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_with_reason_appends_note(self):
        svc = _svc()
        order = _make_order(notes="original note")
        session = _mock_session(scalar=order)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            await svc.cancel_order("ORD_001", reason="顾客取消")
        assert "顾客取消" in order.notes

    @pytest.mark.asyncio
    async def test_not_found_raises_and_rollbacks(self):
        svc = _svc()
        session = _mock_session(scalar=None)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            with pytest.raises(ValueError, match="订单不存在"):
                await svc.cancel_order("BAD_ID")
        session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_order_statistics
# ---------------------------------------------------------------------------

class TestGetOrderStatistics:

    @pytest.mark.asyncio
    async def test_empty_store_returns_zeros(self):
        svc = _svc()
        session = _mock_session(scalars_all=[])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "OrderStatus", _OrderStatus), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.get_order_statistics()
        assert result["total_orders"] == 0
        assert result["total_revenue"] == 0

    @pytest.mark.asyncio
    async def test_with_completed_orders(self):
        svc = _svc()
        # get_order_statistics compares o.status == OrderStatus.COMPLETED.value ("completed")
        # so status must be the string value, not the enum member
        def _stats_order(status_val, final_amount):
            o = MagicMock()
            o.status = status_val
            o.final_amount = final_amount
            return o

        orders = [
            _stats_order("completed", 5000),
            _stats_order("completed", 3000),
            _stats_order("cancelled", 2000),
        ]
        session = _mock_session(scalars_all=orders)
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "OrderStatus", _OrderStatus), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.get_order_statistics()
        assert result["total_orders"] == 3
        assert result["completed_orders"] == 2
        assert result["cancelled_orders"] == 1
        # total_revenue = (5000 + 3000) / 100 = 80.0
        assert result["total_revenue"] == 80.0

    @pytest.mark.asyncio
    async def test_with_date_filters(self):
        svc = _svc()
        session = _mock_session(scalars_all=[])
        with patch.object(_svc_mod, "select", MagicMock()), \
             patch.object(_svc_mod, "selectinload", MagicMock()), \
             patch.object(_svc_mod, "Order", _order_cls_mock()), \
             patch.object(_svc_mod, "OrderStatus", _OrderStatus), \
             patch("src.services.order_service.get_db_session", _mock_db(session)):
            result = await svc.get_order_statistics(
                start_date="2024-01-01",
                end_date="2024-01-31",
            )
        assert "status_breakdown" in result
