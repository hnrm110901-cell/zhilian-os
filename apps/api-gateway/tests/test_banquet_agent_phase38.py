"""
Banquet Agent Phase 38 — 单元测试

覆盖端点：
  - get_upsell_success_rate
  - get_banquet_capacity_utilization
  - get_referral_conversion_rate
  - get_contract_signing_speed
  - get_event_coordinator_performance
  - get_post_event_review_rate
  - get_banquet_revenue_trend
  - get_hall_booking_lead_time
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
                package_id=None, created_at=None, contact_name="张三",
                people_count=100):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.table_count      = table_count
    o.people_count     = people_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.package_id       = package_id
    o.contact_name     = contact_name
    o.created_at       = created_at or datetime.utcnow() - timedelta(days=60)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_hall(hid="H-001", name="一号厅", max_tables=30, is_active=True):
    h = MagicMock()
    h.id         = hid
    h.name       = name
    h.max_tables = max_tables
    h.is_active  = is_active
    return h


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    return b


def _make_lead(lid="L-001", stage="won", source="转介绍",
               days_ago=20, days_to_sign=10):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = source
    l.current_stage  = LeadStageEnum(stage) if stage in [e.value for e in LeadStageEnum] else MagicMock(value=stage)
    l.expected_budget_fen = 200000
    l.created_at = datetime.utcnow() - timedelta(days=days_ago)
    l.updated_at = datetime.utcnow() - timedelta(days=days_ago - days_to_sign)
    return l


def _make_package(pid="PKG-001", price_fen=25000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    return p


def _make_review(rid="R-001", order_id="O-001", rating=5):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.ai_score         = 90.0
    r.improvement_tags = []
    r.created_at       = datetime.utcnow() - timedelta(days=5)
    return r


# ── TestUpsellSuccessRate ─────────────────────────────────────────────────────

class TestUpsellSuccessRate:

    @pytest.mark.asyncio
    async def test_upsell_detected(self):
        """pkg 25000*10=250000, actual=300000 → upsell=1, avg=500元"""
        from src.api.banquet_agent import get_upsell_success_rate

        pkg   = _make_package(price_fen=25000)
        order = _make_order(total_fen=300000, table_count=10, package_id=pkg.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_upsell_success_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 1
        assert result["upsell_count"] == 1
        assert result["upsell_rate_pct"] == pytest.approx(100.0)
        assert result["avg_upsell_yuan"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无套餐订单时 upsell_rate_pct = None"""
        from src.api.banquet_agent import get_upsell_success_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_upsell_success_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["upsell_rate_pct"] is None


# ── TestBanquetCapacityUtilization ────────────────────────────────────────────

class TestBanquetCapacityUtilization:

    @pytest.mark.asyncio
    async def test_utilization_computed(self):
        """1 hall max=30, 1 booking order=10 tables → utilization=33.3%"""
        from src.api.banquet_agent import get_banquet_capacity_utilization

        hall    = _make_hall(max_tables=30)
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(table_count=10)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_capacity_utilization(store_id="S001", months=6, db=db, _=_mock_user())

        assert len(result["halls"]) == 1
        assert result["halls"][0]["utilization_pct"] == pytest.approx(33.3, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_banquet_capacity_utilization

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_capacity_utilization(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["overall_utilization_pct"] is None


# ── TestReferralConversionRate ────────────────────────────────────────────────

class TestReferralConversionRate:

    @pytest.mark.asyncio
    async def test_conversion_computed(self):
        """2 referrals, 1 won → conversion_rate=50%"""
        from src.api.banquet_agent import get_referral_conversion_rate

        l1 = _make_lead(lid="L-001", stage="won",  source="转介绍")
        l2 = _make_lead(lid="L-002", stage="lost", source="转介绍")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_referral_conversion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_referrals"] == 2
        assert result["won_count"] == 1
        assert result["conversion_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_referrals_returns_none(self):
        """无转介绍线索时 conversion_rate_pct = None"""
        from src.api.banquet_agent import get_referral_conversion_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_referral_conversion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_referrals"] == 0
        assert result["conversion_rate_pct"] is None


# ── TestContractSigningSpeed ──────────────────────────────────────────────────

class TestContractSigningSpeed:

    @pytest.mark.asyncio
    async def test_avg_days_computed(self):
        """created 20d ago, won 10d after → avg=10d, fast_sign=100%(≤14d)"""
        from src.api.banquet_agent import get_contract_signing_speed

        lead = _make_lead(stage="won", days_ago=20, days_to_sign=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_contract_signing_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won"] == 1
        assert result["avg_days_to_sign"] == pytest.approx(10.0, abs=0.5)
        assert result["fast_sign_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_won_leads_returns_none(self):
        """无成单线索时 avg_days_to_sign = None"""
        from src.api.banquet_agent import get_contract_signing_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_contract_signing_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won"] == 0
        assert result["avg_days_to_sign"] is None


# ── TestEventCoordinatorPerformance ──────────────────────────────────────────

class TestEventCoordinatorPerformance:

    @pytest.mark.asyncio
    async def test_coordinator_ranked(self):
        """1 completed order + 1 review(5★) → top=张三, avg_rating=5.0"""
        from src.api.banquet_agent import get_event_coordinator_performance

        order  = _make_order(status="completed", contact_name="张三")
        review = _make_review(order_id=order.id, rating=5)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([review])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_event_coordinator_performance(store_id="S001", months=3, db=db, _=_mock_user())

        assert len(result["coordinators"]) == 1
        assert result["top_coordinator"] == "张三"
        assert result["coordinators"][0]["avg_rating"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无已完成订单时 coordinators 为空"""
        from src.api.banquet_agent import get_event_coordinator_performance

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_event_coordinator_performance(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["coordinators"] == []
        assert result["top_coordinator"] is None


# ── TestPostEventReviewRate ───────────────────────────────────────────────────

class TestPostEventReviewRate:

    @pytest.mark.asyncio
    async def test_review_rate_computed(self):
        """1 completed order + 1 review → review_rate=100%"""
        from src.api.banquet_agent import get_post_event_review_rate

        order  = _make_order(status="completed")
        review = _make_review(order_id=order.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([review])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_post_event_review_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["reviewed_count"] == 1
        assert result["review_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_completed_orders_returns_none(self):
        """无已完成订单时 review_rate_pct = None"""
        from src.api.banquet_agent import get_post_event_review_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_post_event_review_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["review_rate_pct"] is None


# ── TestBanquetRevenueTrend ───────────────────────────────────────────────────

class TestBanquetRevenueTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """2 orders same month → monthly has 1 entry, total=600元"""
        from src.api.banquet_agent import get_banquet_revenue_trend

        now = datetime.utcnow()
        bd  = date.today() - timedelta(days=10)
        o1 = _make_order(oid="O-001", total_fen=300000, banquet_date=bd)
        o2 = _make_order(oid="O-002", total_fen=300000, banquet_date=bd)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_revenue_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert len(result["monthly"]) >= 1
        assert result["total_revenue_yuan"] == pytest.approx(6000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 monthly 为空"""
        from src.api.banquet_agent import get_banquet_revenue_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_revenue_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["monthly"] == []
        assert result["total_revenue_yuan"] is None


# ── TestHallBookingLeadTime ───────────────────────────────────────────────────

class TestHallBookingLeadTime:

    @pytest.mark.asyncio
    async def test_lead_time_computed(self):
        """order created 60d ago, banquet 30d ago → lead_time=30d"""
        from src.api.banquet_agent import get_hall_booking_lead_time

        banquet_d = date.today() - timedelta(days=30)
        order = _make_order(
            banquet_date=banquet_d,
            created_at=datetime.utcnow() - timedelta(days=60),
        )
        # Make created_at.date() work
        order.created_at = datetime.utcnow() - timedelta(days=60)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_hall_booking_lead_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_lead_days"] == pytest.approx(30.0, abs=1.0)
        assert len(result["distribution"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_lead_days = None"""
        from src.api.banquet_agent import get_hall_booking_lead_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_booking_lead_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_lead_days"] is None
        assert result["distribution"] == []
