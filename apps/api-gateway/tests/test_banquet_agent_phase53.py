"""
Banquet Agent Phase 53 — 单元测试

覆盖端点：
  - get_advance_deposit_rate
  - get_order_amendment_rate
  - get_cross_hall_booking_rate
  - get_lead_channel_roi
  - get_banquet_date_popularity
  - get_customer_lifetime_value
  - get_staff_order_load
  - get_revenue_forecast_accuracy
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
                status="confirmed", customer_id="C-001", created_at=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.contact_name     = "张三"
    o.created_at       = created_at or datetime.utcnow() - timedelta(days=60)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_lead(lid="L-001", stage="won", source="微信", budget_fen=200000,
               customer_id="C-001", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum(stage)
    l.expected_budget_fen = budget_fen
    l.customer_id         = customer_id
    l.created_at          = created_at or datetime.utcnow() - timedelta(days=20)
    return l


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = "dinner"
    return b


def _make_contract(cid="C-001", order_id="O-001"):
    c = MagicMock()
    c.id               = cid
    c.banquet_order_id = order_id
    c.version          = 1
    c.created_at       = datetime.utcnow() - timedelta(days=5)
    return c


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    return t


# ── TestAdvanceDepositRate ─────────────────────────────────────────────────────

class TestAdvanceDepositRate:

    @pytest.mark.asyncio
    async def test_deposit_rate_computed(self):
        """paid=150000, total=300000 → avg_deposit_ratio=50%"""
        from src.api.banquet_agent import get_advance_deposit_rate

        order = _make_order(total_fen=300000, paid_fen=150000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_advance_deposit_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_deposit_ratio_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_deposit_ratio_pct = None"""
        from src.api.banquet_agent import get_advance_deposit_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_advance_deposit_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_deposit_ratio_pct"] is None


# ── TestOrderAmendmentRate ─────────────────────────────────────────────────────

class TestOrderAmendmentRate:

    @pytest.mark.asyncio
    async def test_amendment_computed(self):
        """O-001 has 2 contracts → amended=1, rate=50% (out of 2 orders)"""
        from src.api.banquet_agent import get_order_amendment_rate

        o1 = _make_order(oid="O-001")
        o2 = _make_order(oid="O-002")
        c1a = _make_contract(cid="C-1A", order_id="O-001")
        c1b = _make_contract(cid="C-1B", order_id="O-001")   # 2nd version

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([o1, o2])
            return _scalars_returning([c1a, c1b])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_order_amendment_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["amended_count"] == 1
        assert result["amendment_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 amendment_rate_pct = None"""
        from src.api.banquet_agent import get_order_amendment_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_amendment_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["amendment_rate_pct"] is None


# ── TestCrossHallBookingRate ───────────────────────────────────────────────────

class TestCrossHallBookingRate:

    @pytest.mark.asyncio
    async def test_cross_hall_detected(self):
        """O-001 booked H-001 + H-002 → cross_hall_rate=100%"""
        from src.api.banquet_agent import get_cross_hall_booking_rate

        b1 = _make_booking(bid="B-001", hall_id="H-001", order_id="O-001")
        b2 = _make_booking(bid="B-002", hall_id="H-002", order_id="O-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2]))

        result = await get_cross_hall_booking_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 2
        assert result["cross_hall_orders"] == 1
        assert result["cross_hall_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 cross_hall_rate_pct = None"""
        from src.api.banquet_agent import get_cross_hall_booking_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_cross_hall_booking_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["cross_hall_rate_pct"] is None


# ── TestLeadChannelRoi ────────────────────────────────────────────────────────

class TestLeadChannelRoi:

    @pytest.mark.asyncio
    async def test_roi_computed(self):
        """微信: 1 won / 1 total = 100% win rate → top_roi_channel=微信"""
        from src.api.banquet_agent import get_lead_channel_roi

        lead  = _make_lead(lid="L-001", stage="won", source="微信", customer_id="C-001")
        order = _make_order(oid="O-001", total_fen=300000, customer_id="C-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_channel_roi(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["top_roi_channel"] == "微信"
        ch = next(c for c in result["by_channel"] if c["channel"] == "微信")
        assert ch["win_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 top_roi_channel = None"""
        from src.api.banquet_agent import get_lead_channel_roi

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_channel_roi(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["top_roi_channel"] is None


# ── TestBanquetDatePopularity ─────────────────────────────────────────────────

class TestBanquetDatePopularity:

    @pytest.mark.asyncio
    async def test_popularity_computed(self):
        """2 orders in same month → peak_month = that month"""
        from src.api.banquet_agent import get_banquet_date_popularity

        bd = date(date.today().year, 6, 15)
        o1 = _make_order(oid="O-001", banquet_date=bd)
        o2 = _make_order(oid="O-002", banquet_date=bd)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_date_popularity(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["peak_month"] is not None
        assert len(result["by_month"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 peak_month = None"""
        from src.api.banquet_agent import get_banquet_date_popularity

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_date_popularity(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["peak_month"] is None


# ── TestCustomerLifetimeValue ─────────────────────────────────────────────────

class TestCustomerLifetimeValue:

    @pytest.mark.asyncio
    async def test_clv_computed(self):
        """C-001: 300000fen; C-002: 100000fen → avg_clv=2000yuan"""
        from src.api.banquet_agent import get_customer_lifetime_value

        o1 = _make_order(oid="O-001", total_fen=300000, customer_id="C-001")
        o2 = _make_order(oid="O-002", total_fen=100000, customer_id="C-002")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_lifetime_value(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 2
        assert result["avg_clv_yuan"] == pytest.approx(2000.0)
        assert result["top_customer"] == "C-001"

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_clv_yuan = None"""
        from src.api.banquet_agent import get_customer_lifetime_value

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_lifetime_value(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["avg_clv_yuan"] is None


# ── TestStaffOrderLoad ────────────────────────────────────────────────────────

class TestStaffOrderLoad:

    @pytest.mark.asyncio
    async def test_load_computed(self):
        """U-001 has tasks on O-001 + O-002 → order_count=2"""
        from src.api.banquet_agent import get_staff_order_load

        t1 = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        t2 = _make_task(tid="T-002", owner="U-001", order_id="O-002")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([t1, t2]))

        result = await get_staff_order_load(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["busiest_staff"] == "U-001"
        assert result["staff"][0]["order_count"] == 2

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 busiest_staff = None"""
        from src.api.banquet_agent import get_staff_order_load

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_order_load(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["busiest_staff"] is None


# ── TestRevenueForecastAccuracy ───────────────────────────────────────────────

class TestRevenueForecastAccuracy:

    @pytest.mark.asyncio
    async def test_accuracy_computed(self):
        """budget=200000fen, actual=200000fen → accuracy=100%"""
        from src.api.banquet_agent import get_revenue_forecast_accuracy

        lead  = _make_lead(lid="L-001", stage="won", budget_fen=200000, customer_id="C-001")
        order = _make_order(oid="O-001", total_fen=200000, customer_id="C-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_revenue_forecast_accuracy(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won"] == 1
        assert result["avg_accuracy_pct"] == pytest.approx(100.0)
        assert result["avg_deviation_yuan"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_no_won_leads_returns_none(self):
        """无赢单时 avg_accuracy_pct = None"""
        from src.api.banquet_agent import get_revenue_forecast_accuracy

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_revenue_forecast_accuracy(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won"] == 0
        assert result["avg_accuracy_pct"] is None
