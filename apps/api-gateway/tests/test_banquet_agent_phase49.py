"""
Banquet Agent Phase 49 — 单元测试

覆盖端点：
  - get_banquet_completion_rate
  - get_slot_revenue_analysis
  - get_lead_source_monthly_trend
  - get_customer_satisfaction_trend
  - get_order_size_distribution
  - get_payment_to_event_gap
  - get_banquet_type_avg_tables
  - get_review_score_distribution
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
                status="confirmed", customer_id="C-001"):
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
    o.created_at       = datetime.utcnow() - timedelta(days=60)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_date=None, slot_name="dinner"):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = slot_name
    return b


def _make_lead(lid="L-001", source="微信"):
    l = MagicMock()
    l.id             = lid
    l.source_channel = source
    l.created_at     = datetime.utcnow() - timedelta(days=15)
    return l


def _make_review(rid="R-001", order_id="O-001", rating=5, created_at=None):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.ai_score         = 90.0
    r.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return r


def _make_payment(pid="P-001", order_id="O-001", amount_fen=300000,
                  created_at=None):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.payment_method   = "微信"
    p.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return p


# ── TestBanquetCompletionRate ─────────────────────────────────────────────────

class TestBanquetCompletionRate:

    @pytest.mark.asyncio
    async def test_completion_computed(self):
        """1 completed + 1 confirmed → completion_rate=50%"""
        from src.api.banquet_agent import get_banquet_completion_rate

        o1 = _make_order(oid="O-001", status="completed")
        o2 = _make_order(oid="O-002", status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_completion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["completed_count"] == 1
        assert result["completion_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 completion_rate_pct = None"""
        from src.api.banquet_agent import get_banquet_completion_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_completion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["completion_rate_pct"] is None


# ── TestSlotRevenueAnalysis ───────────────────────────────────────────────────

class TestSlotRevenueAnalysis:

    @pytest.mark.asyncio
    async def test_slot_grouped(self):
        """2 dinner bookings → top_slot=dinner"""
        from src.api.banquet_agent import get_slot_revenue_analysis

        b1 = _make_booking(bid="B-001", order_id="O-001", slot_name="dinner")
        b2 = _make_booking(bid="B-002", order_id="O-002", slot_name="dinner")
        o1 = _make_order(oid="O-001", total_fen=300000)
        o2 = _make_order(oid="O-002", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([b1, b2])
            return _scalars_returning([o1, o2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_slot_revenue_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 2
        assert result["top_slot"] == "dinner"
        d = next(s for s in result["by_slot"] if s["slot"] == "dinner")
        assert d["revenue_yuan"] == pytest.approx(6000.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_empty(self):
        """无预订时 top_slot = None"""
        from src.api.banquet_agent import get_slot_revenue_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_slot_revenue_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["top_slot"] is None


# ── TestLeadSourceMonthlyTrend ────────────────────────────────────────────────

class TestLeadSourceMonthlyTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """2 微信 leads → top_channel=微信"""
        from src.api.banquet_agent import get_lead_source_monthly_trend

        l1 = _make_lead(lid="L-001", source="微信")
        l2 = _make_lead(lid="L-002", source="微信")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_lead_source_monthly_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["top_channel"] == "微信"
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 top_channel = None"""
        from src.api.banquet_agent import get_lead_source_monthly_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_source_monthly_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["top_channel"] is None


# ── TestCustomerSatisfactionTrend ─────────────────────────────────────────────

class TestCustomerSatisfactionTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """2 reviews rating=5 → overall_avg=5.0"""
        from src.api.banquet_agent import get_customer_satisfaction_trend

        r1 = _make_review(rid="R-001", rating=5)
        r2 = _make_review(rid="R-002", rating=5)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([r1, r2]))

        result = await get_customer_satisfaction_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 2
        assert result["overall_avg"] == pytest.approx(5.0)
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_reviews_returns_none(self):
        """无评价时 overall_avg = None"""
        from src.api.banquet_agent import get_customer_satisfaction_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_satisfaction_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["overall_avg"] is None


# ── TestOrderSizeDistribution ─────────────────────────────────────────────────

class TestOrderSizeDistribution:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """10 tables → 6-10桌 bucket"""
        from src.api.banquet_agent import get_order_size_distribution

        order = _make_order(table_count=10)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_size_distribution(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_tables"] == pytest.approx(10.0)
        b = next(b for b in result["distribution"] if "6" in b["bucket"])
        assert b["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_tables = None"""
        from src.api.banquet_agent import get_order_size_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_size_distribution(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_tables"] is None


# ── TestPaymentToEventGap ─────────────────────────────────────────────────────

class TestPaymentToEventGap:

    @pytest.mark.asyncio
    async def test_gap_computed(self):
        """last payment 7 days before banquet → avg_days=7, on_time=100%"""
        from src.api.banquet_agent import get_payment_to_event_gap

        banquet_d = date.today() + timedelta(days=7)
        pay_dt    = datetime.utcnow()          # today
        order     = _make_order(banquet_date=banquet_d, total_fen=300000, paid_fen=300000)
        payment   = _make_payment(order_id=order.id, created_at=pay_dt)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([payment])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_payment_to_event_gap(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 1
        assert result["avg_days_before_event"] == pytest.approx(7.0, abs=1.0)
        assert result["on_time_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_paid_orders_returns_none(self):
        """无全额付款订单时 avg_days_before_event = None"""
        from src.api.banquet_agent import get_payment_to_event_gap

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_to_event_gap(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 0
        assert result["avg_days_before_event"] is None


# ── TestBanquetTypeAvgTables ──────────────────────────────────────────────────

class TestBanquetTypeAvgTables:

    @pytest.mark.asyncio
    async def test_avg_computed(self):
        """2 wedding orders, 10+20 tables → avg=15"""
        from src.api.banquet_agent import get_banquet_type_avg_tables

        o1 = _make_order(oid="O-001", banquet_type="wedding", table_count=10)
        o2 = _make_order(oid="O-002", banquet_type="wedding", table_count=20)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_type_avg_tables(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["overall_avg_tables"] == pytest.approx(15.0)
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["avg_tables"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_avg_tables = None"""
        from src.api.banquet_agent import get_banquet_type_avg_tables

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_avg_tables(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_avg_tables"] is None


# ── TestReviewScoreDistribution ───────────────────────────────────────────────

class TestReviewScoreDistribution:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """2 five-star + 1 three-star → five_star_pct=66.7%, avg=4.33"""
        from src.api.banquet_agent import get_review_score_distribution

        r1 = _make_review(rid="R-001", rating=5)
        r2 = _make_review(rid="R-002", rating=5)
        r3 = _make_review(rid="R-003", rating=3)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([r1, r2, r3]))

        result = await get_review_score_distribution(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_reviews"] == 3
        assert result["five_star_pct"] == pytest.approx(66.7, rel=0.01)
        assert result["avg_score"] == pytest.approx(4.33, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_reviews_returns_none(self):
        """无评价时 five_star_pct = None"""
        from src.api.banquet_agent import get_review_score_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_review_score_distribution(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["five_star_pct"] is None
