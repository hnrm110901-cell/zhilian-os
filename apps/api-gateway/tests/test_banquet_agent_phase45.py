"""
Banquet Agent Phase 45 — 单元测试

覆盖端点：
  - get_banquet_peak_day_analysis
  - get_hall_revenue_per_sqm
  - get_lead_nurturing_effectiveness
  - get_customer_complaint_rate
  - get_payment_channel_trend
  - get_banquet_table_utilization
  - get_staff_rating_by_order
  - get_order_early_warning
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
                contact_name="张三", created_at=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.contact_name     = contact_name
    o.created_at       = created_at or datetime.utcnow() - timedelta(days=60)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_hall(hid="H-001", name="一号厅", max_tables=30,
               is_active=True, floor_area=200.0):
    h = MagicMock()
    h.id            = hid
    h.name          = name
    h.max_tables    = max_tables
    h.is_active     = is_active
    h.floor_area_m2 = floor_area
    return h


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_date=None, slot_name="dinner"):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = slot_name
    return b


def _make_lead(lid="L-001", stage="won", source="微信"):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = source
    l.current_stage  = LeadStageEnum(stage)
    l.created_at     = datetime.utcnow() - timedelta(days=20)
    l.updated_at     = datetime.utcnow() - timedelta(days=5)
    return l


def _make_followup(fid="F-001", lead_id="L-001"):
    f = MagicMock()
    f.id      = fid
    f.lead_id = lead_id
    f.created_at = datetime.utcnow() - timedelta(days=3)
    return f


def _make_exception(eid="E-001", order_id="O-001", exc_type="complaint"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = exc_type
    e.created_at       = datetime.utcnow() - timedelta(days=2)
    return e


def _make_payment(pid="P-001", order_id="O-001", amount_fen=30000, method="微信"):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.payment_method   = method
    p.created_at       = datetime.utcnow() - timedelta(days=5)
    return p


def _make_review(rid="R-001", order_id="O-001", rating=5):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.ai_score         = 90.0
    r.created_at       = datetime.utcnow() - timedelta(days=5)
    return r


# ── TestBanquetPeakDayAnalysis ────────────────────────────────────────────────

class TestBanquetPeakDayAnalysis:

    @pytest.mark.asyncio
    async def test_peak_day_computed(self):
        """2 Saturday orders → peak_weekday=周六"""
        from src.api.banquet_agent import get_banquet_peak_day_analysis

        # Find most recent Saturday
        today = date.today()
        days_since_sat = (today.weekday() - 5) % 7
        sat = today - timedelta(days=days_since_sat + 7)
        o1 = _make_order(oid="O-001", banquet_date=sat)
        o2 = _make_order(oid="O-002", banquet_date=sat - timedelta(weeks=1))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_peak_day_analysis(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["peak_weekday"] == "周六"
        sat_day = next(d for d in result["by_weekday"] if d["weekday"] == 5)
        assert sat_day["order_count"] == 2

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 peak_weekday = None"""
        from src.api.banquet_agent import get_banquet_peak_day_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_peak_day_analysis(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["peak_weekday"] is None


# ── TestHallRevenuePerSqm ─────────────────────────────────────────────────────

class TestHallRevenuePerSqm:

    @pytest.mark.asyncio
    async def test_per_sqm_computed(self):
        """hall area=200, 1 booking → order 3000yuan / 200m² = 15/m²"""
        from src.api.banquet_agent import get_hall_revenue_per_sqm

        hall    = _make_hall(floor_area=200.0)
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(oid="O-001", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_revenue_per_sqm(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_halls"] == 1
        assert result["halls"][0]["per_sqm_yuan"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_none(self):
        """无厅房时 overall_per_sqm = None"""
        from src.api.banquet_agent import get_hall_revenue_per_sqm

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_per_sqm(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_halls"] == 0
        assert result["overall_per_sqm"] is None


# ── TestLeadNurturingEffectiveness ────────────────────────────────────────────

class TestLeadNurturingEffectiveness:

    @pytest.mark.asyncio
    async def test_nurturing_compared(self):
        """won lead 3 followups, lost lead 1 → won_avg=3, lost_avg=1"""
        from src.api.banquet_agent import get_lead_nurturing_effectiveness

        l_won  = _make_lead(lid="L-001", stage="won")
        l_lost = _make_lead(lid="L-002", stage="lost")
        fu1 = _make_followup(fid="F-001", lead_id="L-001")
        fu2 = _make_followup(fid="F-002", lead_id="L-001")
        fu3 = _make_followup(fid="F-003", lead_id="L-001")
        fu4 = _make_followup(fid="F-004", lead_id="L-002")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([l_won, l_lost])
            if call_n[0] == 2: return _scalars_returning([fu1, fu2, fu3])
            return _scalars_returning([fu4])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_nurturing_effectiveness(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["won_avg_followups"] == pytest.approx(3.0)
        assert result["lost_avg_followups"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 won_avg_followups = None"""
        from src.api.banquet_agent import get_lead_nurturing_effectiveness

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_nurturing_effectiveness(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["won_avg_followups"] is None


# ── TestCustomerComplaintRate ─────────────────────────────────────────────────

class TestCustomerComplaintRate:

    @pytest.mark.asyncio
    async def test_complaint_detected(self):
        """1 completed order with complaint → complaint_rate=100%"""
        from src.api.banquet_agent import get_customer_complaint_rate

        order = _make_order(status="completed")
        exc   = _make_exception(order_id=order.id, exc_type="complaint")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([exc])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_customer_complaint_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["complaint_count"] == 1
        assert result["complaint_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无已完成订单时 complaint_rate_pct = None"""
        from src.api.banquet_agent import get_customer_complaint_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_complaint_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["complaint_rate_pct"] is None


# ── TestPaymentChannelTrend ───────────────────────────────────────────────────

class TestPaymentChannelTrend:

    @pytest.mark.asyncio
    async def test_channel_grouped(self):
        """2 微信 + 1 现金 → dominant=微信, pct=66.7%"""
        from src.api.banquet_agent import get_payment_channel_trend

        p1 = _make_payment(pid="P-001", method="微信")
        p2 = _make_payment(pid="P-002", method="微信")
        p3 = _make_payment(pid="P-003", method="现金")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([p1, p2, p3]))

        result = await get_payment_channel_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 3
        assert result["dominant_channel"] == "微信"
        wx = next(c for c in result["channels"] if c["channel"] == "微信")
        assert wx["pct"] == pytest.approx(66.7, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_payments_returns_empty(self):
        """无支付记录时 channels 为空"""
        from src.api.banquet_agent import get_payment_channel_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_channel_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 0
        assert result["channels"] == []
        assert result["dominant_channel"] is None


# ── TestBanquetTableUtilization ───────────────────────────────────────────────

class TestBanquetTableUtilization:

    @pytest.mark.asyncio
    async def test_utilization_computed(self):
        """1 hall max=30, 1 order 10 tables → util=10/30=33.3%"""
        from src.api.banquet_agent import get_banquet_table_utilization

        hall  = _make_hall(max_tables=30)
        order = _make_order(table_count=10)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_table_utilization(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_utilization_pct"] == pytest.approx(33.3, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_utilization_pct = None"""
        from src.api.banquet_agent import get_banquet_table_utilization

        hall = _make_hall(max_tables=30)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_table_utilization(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_utilization_pct"] is None


# ── TestStaffRatingByOrder ────────────────────────────────────────────────────

class TestStaffRatingByOrder:

    @pytest.mark.asyncio
    async def test_rating_computed(self):
        """张三: 1 order, review rating=5 → avg_rating=5.0, top_rated=张三"""
        from src.api.banquet_agent import get_staff_rating_by_order

        order  = _make_order(status="completed", contact_name="张三")
        review = _make_review(order_id=order.id, rating=5)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([review])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_rating_by_order(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["top_rated"] == "张三"
        assert result["staff"][0]["avg_rating"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无已完成订单时 staff 为空"""
        from src.api.banquet_agent import get_staff_rating_by_order

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_rating_by_order(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["top_rated"] is None


# ── TestOrderEarlyWarning ─────────────────────────────────────────────────────

class TestOrderEarlyWarning:

    @pytest.mark.asyncio
    async def test_warning_detected(self):
        """confirmed order, banquet in 7 days, paid<total → at_risk=1"""
        from src.api.banquet_agent import get_order_early_warning

        future_date = date.today() + timedelta(days=7)
        order = _make_order(
            status="confirmed",
            banquet_date=future_date,
            total_fen=300000,
            paid_fen=30000,   # underpaid
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_early_warning(store_id="S001", days_ahead=14, db=db, _=_mock_user())

        assert result["total_confirmed"] == 1
        assert result["at_risk_count"] == 1
        assert result["warnings"][0]["days_until"] == 7
        assert result["warnings"][0]["unpaid_yuan"] == pytest.approx(2700.0)

    @pytest.mark.asyncio
    async def test_fully_paid_not_at_risk(self):
        """confirmed order, fully paid → at_risk=0"""
        from src.api.banquet_agent import get_order_early_warning

        future_date = date.today() + timedelta(days=7)
        order = _make_order(
            status="confirmed",
            banquet_date=future_date,
            total_fen=300000,
            paid_fen=300000,  # fully paid
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_early_warning(store_id="S001", days_ahead=14, db=db, _=_mock_user())

        assert result["total_confirmed"] == 1
        assert result["at_risk_count"] == 0
        assert result["warnings"] == []
