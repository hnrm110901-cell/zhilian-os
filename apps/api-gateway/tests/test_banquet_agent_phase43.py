"""
Banquet Agent Phase 43 — 单元测试

覆盖端点：
  - get_banquet_revenue_per_table
  - get_hall_double_booking_risk
  - get_lead_source_roi
  - get_customer_lifetime_value
  - get_seasonal_revenue_index
  - get_staff_order_load
  - get_payment_completion_rate
  - get_banquet_repeat_venue_rate
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock


# ── helpers ─────────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id       = "user-001"
    u.brand_id = "BRAND-001"
    return u


def _scalars_returning(items):
    r = MagicMock()
    r.scalars.return_value.first.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value   = items
    return r


def _make_order(oid="O-001", total_fen=300000, paid_fen=300000,
                table_count=10, banquet_type="wedding", banquet_date=None,
                status="confirmed", customer_id="C-001",
                package_id=None, created_at=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.package_id       = package_id
    o.contact_name     = "张三"
    o.created_at       = created_at or datetime.utcnow() - timedelta(days=60)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_booking(bid="B-001", hall_id="H-001", slot_date=None,
                  slot_name="dinner", order_id="O-001"):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = slot_name
    b.banquet_order_id = order_id
    return b


def _make_lead(lid="L-001", stage="won", source="微信", budget_fen=200000):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum(stage)
    l.expected_budget_fen = budget_fen
    l.created_at          = datetime.utcnow() - timedelta(days=20)
    l.updated_at          = datetime.utcnow() - timedelta(days=5)
    return l


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    return t


# ── TestBanquetRevenuePerTable ────────────────────────────────────────────────

class TestBanquetRevenuePerTable:

    @pytest.mark.asyncio
    async def test_per_table_computed(self):
        """300000fen / 10 tables = 300元/桌"""
        from src.api.banquet_agent import get_banquet_revenue_per_table

        order = _make_order(total_fen=300000, table_count=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["overall_per_table_yuan"] == pytest.approx(300.0)
        assert len(result["by_type"]) == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_per_table_yuan = None"""
        from src.api.banquet_agent import get_banquet_revenue_per_table

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_per_table_yuan"] is None


# ── TestHallDoubleBookingRisk ──────────────────────────────────────────────────

class TestHallDoubleBookingRisk:

    @pytest.mark.asyncio
    async def test_conflict_detected(self):
        """同厅同日2条booking → conflict_days=1, rate=100%"""
        from src.api.banquet_agent import get_hall_double_booking_risk

        slot_d = date.today() - timedelta(days=5)
        b1 = _make_booking(bid="B-001", hall_id="H-001", slot_date=slot_d, slot_name="dinner")
        b2 = _make_booking(bid="B-002", hall_id="H-001", slot_date=slot_d, slot_name="dinner")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2]))

        result = await get_hall_double_booking_risk(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_bookings"] == 2
        assert result["conflict_days"] == 1
        assert result["conflict_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 conflict_rate_pct = None"""
        from src.api.banquet_agent import get_hall_double_booking_risk

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_double_booking_risk(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["conflict_rate_pct"] is None


# ── TestLeadSourceRoi ──────────────────────────────────────────────────────────

class TestLeadSourceRoi:

    @pytest.mark.asyncio
    async def test_roi_computed(self):
        """2 微信 leads, 1 won → win_rate=50%, best=微信"""
        from src.api.banquet_agent import get_lead_source_roi

        l1 = _make_lead(lid="L-001", stage="won",  source="微信", budget_fen=200000)
        l2 = _make_lead(lid="L-002", stage="lost", source="微信", budget_fen=200000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_lead_source_roi(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["best_channel"] == "微信"
        wx = next(c for c in result["channels"] if c["channel"] == "微信")
        assert wx["win_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 channels 为空"""
        from src.api.banquet_agent import get_lead_source_roi

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_source_roi(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["channels"] == []
        assert result["best_channel"] is None


# ── TestCustomerLifetimeValue ─────────────────────────────────────────────────

class TestCustomerLifetimeValue:

    @pytest.mark.asyncio
    async def test_ltv_computed(self):
        """C-001 两笔订单共600元 → avg_ltv=600"""
        from src.api.banquet_agent import get_customer_lifetime_value

        o1 = _make_order(oid="O-001", total_fen=300000, customer_id="C-001")
        o2 = _make_order(oid="O-002", total_fen=300000, customer_id="C-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_lifetime_value(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["avg_ltv_yuan"] == pytest.approx(6000.0)
        assert result["top_customers"][0]["customer_id"] == "C-001"

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_ltv_yuan = None"""
        from src.api.banquet_agent import get_customer_lifetime_value

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_lifetime_value(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["avg_ltv_yuan"] is None


# ── TestSeasonalRevenueIndex ──────────────────────────────────────────────────

class TestSeasonalRevenueIndex:

    @pytest.mark.asyncio
    async def test_quarterly_computed(self):
        """1 order in Q2 → Q2 seasonal_index=4.0 (only quarter with revenue)"""
        from src.api.banquet_agent import get_seasonal_revenue_index

        order = _make_order(total_fen=300000,
                            banquet_date=date(date.today().year - 1, 5, 15))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_seasonal_revenue_index(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["peak_quarter"] == 2
        assert len(result["quarterly"]) == 4
        q2 = next(q for q in result["quarterly"] if q["quarter"] == 2)
        assert q2["seasonal_index"] == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 quarterly 为空"""
        from src.api.banquet_agent import get_seasonal_revenue_index

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_seasonal_revenue_index(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["quarterly"] == []
        assert result["peak_quarter"] is None


# ── TestStaffOrderLoad ────────────────────────────────────────────────────────

class TestStaffOrderLoad:

    @pytest.mark.asyncio
    async def test_load_computed(self):
        """U-001: 2 tasks on 1 order → task_count=2, order_count=1"""
        from src.api.banquet_agent import get_staff_order_load

        t1 = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        t2 = _make_task(tid="T-002", owner="U-001", order_id="O-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([t1, t2]))

        result = await get_staff_order_load(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 2
        assert result["busiest_staff"] == "U-001"
        staff = result["staff"][0]
        assert staff["task_count"] == 2
        assert staff["order_count"] == 1

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 staff 为空"""
        from src.api.banquet_agent import get_staff_order_load

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_order_load(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 0
        assert result["staff"] == []
        assert result["busiest_staff"] is None


# ── TestPaymentCompletionRate ──────────────────────────────────────────────────

class TestPaymentCompletionRate:

    @pytest.mark.asyncio
    async def test_completion_computed(self):
        """paid=total → completion_rate=100%"""
        from src.api.banquet_agent import get_payment_completion_rate

        order = _make_order(total_fen=300000, paid_fen=300000, status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_payment_completion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["fully_paid_count"] == 1
        assert result["completion_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 completion_rate_pct = None"""
        from src.api.banquet_agent import get_payment_completion_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_completion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["completion_rate_pct"] is None


# ── TestBanquetRepeatVenueRate ──────────────────────────────────────────────────

class TestBanquetRepeatVenueRate:

    @pytest.mark.asyncio
    async def test_repeat_detected(self):
        """H-001 booked twice → repeat_hall_count=1, repeat_rate=100%"""
        from src.api.banquet_agent import get_banquet_repeat_venue_rate

        b1 = _make_booking(bid="B-001", hall_id="H-001")
        b2 = _make_booking(bid="B-002", hall_id="H-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2]))

        result = await get_banquet_repeat_venue_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_bookings"] == 2
        assert result["repeat_hall_count"] == 1
        assert result["repeat_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 repeat_rate_pct = None"""
        from src.api.banquet_agent import get_banquet_repeat_venue_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_repeat_venue_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["repeat_rate_pct"] is None
