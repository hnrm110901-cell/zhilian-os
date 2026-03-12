"""
Banquet Agent Phase 56 — 单元测试

覆盖端点：
  - get_order_value_trend
  - get_lead_stage_conversion_funnel
  - get_hall_double_booking_risk
  - get_customer_vip_upgrade_rate
  - get_payment_overdue_analysis
  - get_banquet_type_review_score
  - get_staff_followup_frequency
  - get_exception_resolution_time
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


def _make_lead(lid="L-001", stage="won", owner="U-001", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = "微信"
    l.current_stage  = LeadStageEnum(stage)
    l.owner_user_id  = owner
    l.created_at     = created_at or datetime.utcnow() - timedelta(days=20)
    return l


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or date.today() - timedelta(days=10)
    b.slot_name        = "dinner"
    return b


def _make_review(rid="R-001", order_id="O-001", rating=5, created_at=None):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return r


def _make_followup(fid="F-001", lead_id="L-001", created_at=None):
    f = MagicMock()
    f.id         = fid
    f.lead_id    = lead_id
    f.created_at = created_at or datetime.utcnow() - timedelta(days=3)
    return f


def _make_exception(eid="E-001", order_id="O-001", resolved_at=None):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = "complaint"
    e.created_at       = datetime.utcnow() - timedelta(days=10)
    e.resolved_at      = resolved_at
    return e


# ── TestOrderValueTrend ───────────────────────────────────────────────────────

class TestOrderValueTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """2 orders in different months → monthly has 1-2 entries"""
        from src.api.banquet_agent import get_order_value_trend

        o1 = _make_order(oid="O-001", total_fen=200000,
                         created_at=datetime.utcnow() - timedelta(days=40))
        o2 = _make_order(oid="O-002", total_fen=400000,
                         created_at=datetime.utcnow() - timedelta(days=5))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_order_value_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert len(result["monthly"]) >= 1
        assert result["trend_direction"] is not None

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 trend_direction = None"""
        from src.api.banquet_agent import get_order_value_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_value_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["trend_direction"] is None


# ── TestLeadStageConversionFunnel ─────────────────────────────────────────────

class TestLeadStageConversionFunnel:

    @pytest.mark.asyncio
    async def test_funnel_computed(self):
        """1 won + 1 new → overall_conversion=50%"""
        from src.api.banquet_agent import get_lead_stage_conversion_funnel

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="new")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_lead_stage_conversion_funnel(store_id="S001", months=6,
                                                         db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["overall_conversion_pct"] == pytest.approx(50.0)
        assert len(result["funnel"]) == 5   # all 5 stages listed

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 overall_conversion_pct = None"""
        from src.api.banquet_agent import get_lead_stage_conversion_funnel

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_stage_conversion_funnel(store_id="S001", months=6,
                                                         db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["overall_conversion_pct"] is None


# ── TestHallDoubleBookingRisk ──────────────────────────────────────────────────

class TestHallDoubleBookingRisk:

    @pytest.mark.asyncio
    async def test_conflict_detected(self):
        """H-001 booked twice on same date → conflict_count=1"""
        from src.api.banquet_agent import get_hall_double_booking_risk

        same_date = date.today() - timedelta(days=5)
        b1 = _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                            slot_date=same_date)
        b2 = _make_booking(bid="B-002", hall_id="H-001", order_id="O-002",
                            slot_date=same_date)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2]))

        result = await get_hall_double_booking_risk(store_id="S001", months=3,
                                                     db=db, _=_mock_user())

        assert result["total_bookings"] == 2
        assert result["conflict_count"] == 1
        assert result["conflict_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 conflict_rate_pct = None"""
        from src.api.banquet_agent import get_hall_double_booking_risk

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_double_booking_risk(store_id="S001", months=3,
                                                     db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["conflict_rate_pct"] is None


# ── TestCustomerVipUpgradeRate ─────────────────────────────────────────────────

class TestCustomerVipUpgradeRate:

    @pytest.mark.asyncio
    async def test_upgrade_rate_computed(self):
        """C-001: 600000fen ≥ 500000 threshold → eligible=1, rate=50%"""
        from src.api.banquet_agent import get_customer_vip_upgrade_rate

        o1 = _make_order(oid="O-001", total_fen=600000, customer_id="C-001")
        o2 = _make_order(oid="O-002", total_fen=200000, customer_id="C-002")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_vip_upgrade_rate(store_id="S001", months=12,
                                                      db=db, _=_mock_user())

        assert result["total_customers"] == 2
        assert result["vip_eligible_count"] == 1
        assert result["upgrade_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 upgrade_rate_pct = None"""
        from src.api.banquet_agent import get_customer_vip_upgrade_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_vip_upgrade_rate(store_id="S001", months=12,
                                                      db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["upgrade_rate_pct"] is None


# ── TestPaymentOverdueAnalysis ─────────────────────────────────────────────────

class TestPaymentOverdueAnalysis:

    @pytest.mark.asyncio
    async def test_overdue_detected(self):
        """banquet 10d ago, paid < total → overdue_count=1"""
        from src.api.banquet_agent import get_payment_overdue_analysis

        past_date = date.today() - timedelta(days=10)
        order = _make_order(banquet_date=past_date, total_fen=300000,
                            paid_fen=100000, status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_payment_overdue_analysis(store_id="S001", months=6,
                                                     db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["overdue_count"] == 1
        assert result["total_overdue_yuan"] == pytest.approx(2000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overdue_rate_pct = None"""
        from src.api.banquet_agent import get_payment_overdue_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_overdue_analysis(store_id="S001", months=6,
                                                     db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overdue_rate_pct"] is None


# ── TestBanquetTypeReviewScore ────────────────────────────────────────────────

class TestBanquetTypeReviewScore:

    @pytest.mark.asyncio
    async def test_score_by_type(self):
        """wedding review rating=5 → top_type=wedding"""
        from src.api.banquet_agent import get_banquet_type_review_score

        review = _make_review(rid="R-001", order_id="O-001", rating=5)
        order  = _make_order(oid="O-001", banquet_type="wedding")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([review])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_type_review_score(store_id="S001", months=12,
                                                      db=db, _=_mock_user())

        assert result["total_reviews"] == 1
        assert result["top_type"] == "wedding"
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["avg_score"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_no_reviews_returns_empty(self):
        """无评价时 top_type = None"""
        from src.api.banquet_agent import get_banquet_type_review_score

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_review_score(store_id="S001", months=12,
                                                      db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["top_type"] is None


# ── TestStaffFollowupFrequency ────────────────────────────────────────────────

class TestStaffFollowupFrequency:

    @pytest.mark.asyncio
    async def test_frequency_computed(self):
        """U-001: 1 lead, 2 followups → avg_followups=2.0"""
        from src.api.banquet_agent import get_staff_followup_frequency

        lead = _make_lead(lid="L-001", stage="contacted", owner="U-001")
        fu1  = _make_followup(fid="F-001", lead_id="L-001")
        fu2  = _make_followup(fid="F-002", lead_id="L-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([fu1, fu2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_followup_frequency(store_id="S001", months=3,
                                                     db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["most_active"] == "U-001"
        assert result["staff"][0]["avg_followups"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 most_active = None"""
        from src.api.banquet_agent import get_staff_followup_frequency

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_followup_frequency(store_id="S001", months=3,
                                                     db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["most_active"] is None


# ── TestExceptionResolutionTime ───────────────────────────────────────────────

class TestExceptionResolutionTime:

    @pytest.mark.asyncio
    async def test_resolution_time_computed(self):
        """exception created 10d ago, resolved 3d ago → avg=7d"""
        from src.api.banquet_agent import get_exception_resolution_time

        resolved_dt = datetime.utcnow() - timedelta(days=3)
        exc = _make_exception(eid="E-001", resolved_at=resolved_dt)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([exc]))

        result = await get_exception_resolution_time(store_id="S001", months=6,
                                                      db=db, _=_mock_user())

        assert result["total_exceptions"] == 1
        assert result["resolved_count"] == 1
        assert result["avg_resolution_days"] == pytest.approx(7.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_exceptions_returns_none(self):
        """无异常时 avg_resolution_days = None"""
        from src.api.banquet_agent import get_exception_resolution_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_exception_resolution_time(store_id="S001", months=6,
                                                      db=db, _=_mock_user())

        assert result["total_exceptions"] == 0
        assert result["avg_resolution_days"] is None
