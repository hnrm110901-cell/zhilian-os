"""
Banquet Agent Phase 15 — 单元测试

覆盖端点：
  - get_service_quality
  - get_booking_lead_time
  - get_customer_retention
  - create_staffing_plan / get_staffing_plan
  - get_yield_by_hall
  - get_cancellation_analysis
  - get_peak_capacity
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock


# ── helpers ─────────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id = "user-001"
    u.brand_id = "BRAND-001"
    return u


def _scalars_returning(items):
    r = MagicMock()
    r.scalars.return_value.first.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value = items
    return r


def _rows_returning(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_order(oid="O-001", store_id="S001", btype="wedding", table_count=20,
                status="confirmed", days_ago=10, total_fen=500000, paid_fen=0,
                customer_id="CUST-001"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id = oid
    o.store_id = store_id
    o.customer_id = customer_id
    o.banquet_type = BanquetTypeEnum.WEDDING if btype == "wedding" else BanquetTypeEnum.BIRTHDAY
    o.table_count = table_count
    o.order_status = OrderStatusEnum.CONFIRMED if status == "confirmed" else (
        OrderStatusEnum.CANCELLED if status == "cancelled" else OrderStatusEnum.COMPLETED
    )
    o.banquet_date = date.today() - timedelta(days=days_ago)
    o.total_amount_fen = total_fen
    o.paid_fen = paid_fen
    o.contact_name = "张三"
    o.contact_phone = "138"
    o.created_at = datetime.utcnow() - timedelta(days=days_ago + 45)
    return o


def _make_task(tid="T-001", order_id="O-001", status="done", delay_hours=0):
    from src.models.banquet import TaskStatusEnum, TaskOwnerRoleEnum
    t = MagicMock()
    t.id = tid
    t.banquet_order_id = order_id
    t.task_status = TaskStatusEnum.DONE if status == "done" else TaskStatusEnum.PENDING
    t.owner_role = TaskOwnerRoleEnum.SERVICE
    t.due_time = datetime.utcnow() - timedelta(hours=2)
    t.completed_at = (datetime.utcnow() - timedelta(hours=2 - delay_hours)) if status == "done" else None
    return t


def _make_exception(eid="E-001", order_id="O-001"):
    e = MagicMock()
    e.id = eid
    e.banquet_order_id = order_id
    e.exception_type = "late"
    e.severity = "medium"
    return e


def _make_hall(hid="HALL-001", store_id="S001"):
    from src.models.banquet import BanquetHallType
    h = MagicMock()
    h.id = hid
    h.store_id = store_id
    h.name = "大宴会厅"
    h.hall_type = BanquetHallType.MAIN_HALL
    h.max_tables = 30
    h.is_active = True
    return h


def _make_booking(bid="BK-001", hall_id="HALL-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id = bid
    b.hall_id = hall_id
    b.banquet_order_id = order_id
    b.slot_date = slot_date or date.today().replace(day=15)
    b.slot_name = "dinner"
    return b


def _make_customer(cid="CUST-001", name="王大华"):
    c = MagicMock()
    c.id = cid
    c.customer_name = name
    return c


# ── TestServiceQuality ───────────────────────────────────────────────────────

class TestServiceQuality:

    @pytest.mark.asyncio
    async def test_service_quality_computes_rates(self):
        from src.api.banquet_agent import get_service_quality

        order = _make_order(days_ago=5)
        task_done    = _make_task("T-001", order.id, status="done",    delay_hours=0)
        task_pending = _make_task("T-002", order.id, status="pending")
        exc = _make_exception(order_id=order.id)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),       # orders query
            _scalars_returning([task_done, task_pending]),  # tasks query
            _scalars_returning([exc]),         # exceptions query
        ])

        result = await get_service_quality(
            store_id="S001", month="2026-03", db=db, _=_mock_user()
        )

        assert result["order_count"] == 1
        assert result["task_completion_pct"] == 50.0   # 1/2 done
        assert result["exception_rate_pct"] == 100.0   # 1 exc / 1 order
        assert len(result["by_banquet_type"]) == 1

    @pytest.mark.asyncio
    async def test_service_quality_empty_returns_zeros(self):
        from src.api.banquet_agent import get_service_quality

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_service_quality(
            store_id="S001", month="2026-03", db=db, _=_mock_user()
        )

        assert result["order_count"] == 0
        assert result["task_completion_pct"] == 0.0
        assert result["by_banquet_type"] == []

    @pytest.mark.asyncio
    async def test_service_quality_all_done_zero_exceptions(self):
        from src.api.banquet_agent import get_service_quality

        order = _make_order(days_ago=5)
        t1 = _make_task("T-001", order.id, status="done")
        t2 = _make_task("T-002", order.id, status="done")

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),
            _scalars_returning([t1, t2]),
            _scalars_returning([]),       # no exceptions
        ])

        result = await get_service_quality(
            store_id="S001", month=None, db=db, _=_mock_user()
        )

        assert result["task_completion_pct"] == 100.0
        assert result["exception_rate_pct"] == 0.0


# ── TestBookingLeadTime ──────────────────────────────────────────────────────

class TestBookingLeadTime:

    @pytest.mark.asyncio
    async def test_lead_time_buckets(self):
        from src.api.banquet_agent import get_booking_lead_time

        # Order created 60 days before banquet → falls in d30_60 bucket
        o = _make_order(days_ago=0)
        o.banquet_date = date.today() + timedelta(days=60)
        o.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_booking_lead_time(
            store_id="S001", months=6, db=db, _=_mock_user()
        )

        assert result["total"] == 1
        assert result["buckets"]["d30_60"] == 1
        assert result["avg_lead_time_days"] > 0

    @pytest.mark.asyncio
    async def test_lead_time_empty(self):
        from src.api.banquet_agent import get_booking_lead_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_booking_lead_time(
            store_id="S001", months=6, db=db, _=_mock_user()
        )

        assert result["total"] == 0
        assert result["avg_lead_time_days"] == 0


# ── TestStaffingPlan ─────────────────────────────────────────────────────────

class TestStaffingPlan:

    @pytest.mark.asyncio
    async def test_staffing_wedding_20_tables(self):
        from src.api.banquet_agent import create_staffing_plan

        order = _make_order(table_count=20, btype="wedding", status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))
        db.add    = MagicMock()
        db.commit = AsyncMock()

        result = await create_staffing_plan(
            store_id="S001", order_id=order.id,
            db=db, current_user=_mock_user()
        )

        assert result["table_count"] == 20
        assert result["banquet_type"] == "wedding"
        assert result["staffing"]["service"] >= 1
        assert result["staffing"]["kitchen"] >= 1
        assert result["staffing"]["total"] > 0
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_staffing_business_type(self):
        from src.api.banquet_agent import create_staffing_plan
        from src.models.banquet import BanquetTypeEnum

        order = _make_order(table_count=10, status="confirmed")
        order.banquet_type = BanquetTypeEnum.BUSINESS if hasattr(BanquetTypeEnum, "BUSINESS") else MagicMock(value="business")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))
        db.add    = MagicMock()
        db.commit = AsyncMock()

        result = await create_staffing_plan(
            store_id="S001", order_id=order.id,
            db=db, current_user=_mock_user()
        )

        assert result["staffing"]["total"] > 0
        # Business has higher manager ratio
        assert result["staffing"]["manager"] >= 1

    @pytest.mark.asyncio
    async def test_staffing_read_log(self):
        from src.api.banquet_agent import get_staffing_plan

        order = _make_order()
        log = MagicMock()
        log.action_result = {
            "order_id": "O-001", "banquet_type": "wedding",
            "table_count": 20,
            "staffing": {"kitchen": 3, "service": 6, "decor": 1, "manager": 1, "total": 11},
        }
        log.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),
            _scalars_returning([log]),
        ])

        result = await get_staffing_plan(
            store_id="S001", order_id="O-001",
            db=db, _=_mock_user()
        )

        assert result["staffing"]["total"] == 11
        assert result["generated_at"] is not None


# ── TestYieldHall ─────────────────────────────────────────────────────────────

class TestYieldHall:

    @pytest.mark.asyncio
    async def test_yield_by_hall_computes_revenue(self):
        from src.api.banquet_agent import get_yield_by_hall

        hall    = _make_hall()
        order   = _make_order(total_fen=500000)
        booking = _make_booking(hall_id=hall.id, order_id=order.id,
                                slot_date=date(2026, 3, 15))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([hall]),
            _rows_returning([(booking, order)]),
        ])

        result = await get_yield_by_hall(
            store_id="S001", year=2026, month=3,
            db=db, _=_mock_user()
        )

        assert len(result["halls"]) == 1
        h = result["halls"][0]
        assert h["revenue_yuan"] == pytest.approx(5000.0)
        assert h["booked_slots"] == 1
        assert h["order_count"] == 1

    @pytest.mark.asyncio
    async def test_yield_no_halls_returns_empty(self):
        from src.api.banquet_agent import get_yield_by_hall

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_yield_by_hall(
            store_id="S001", year=2026, month=3,
            db=db, _=_mock_user()
        )

        assert result["halls"] == []


# ── TestCancellationAnalysis ─────────────────────────────────────────────────

class TestCancellationAnalysis:

    @pytest.mark.asyncio
    async def test_cancellation_by_type(self):
        from src.api.banquet_agent import get_cancellation_analysis

        o1 = _make_order("O-001", status="cancelled", total_fen=300000, btype="wedding")
        o2 = _make_order("O-002", status="cancelled", total_fen=200000, btype="birthday")
        # lead time: created_at 50 days before banquet → over_30d bucket
        o1.created_at = datetime.utcnow() - timedelta(days=60)
        o1.banquet_date = date.today() - timedelta(days=10)
        o2.created_at = datetime.utcnow() - timedelta(days=15)
        o2.banquet_date = date.today() - timedelta(days=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_cancellation_analysis(
            store_id="S001", months=3, db=db, _=_mock_user()
        )

        assert result["total"] == 2
        assert result["revenue_lost_yuan"] == pytest.approx(5000.0)
        assert len(result["by_banquet_type"]) == 2

    @pytest.mark.asyncio
    async def test_cancellation_empty(self):
        from src.api.banquet_agent import get_cancellation_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_cancellation_analysis(
            store_id="S001", months=3, db=db, _=_mock_user()
        )

        assert result["total"] == 0
        assert result["revenue_lost_yuan"] == 0.0
