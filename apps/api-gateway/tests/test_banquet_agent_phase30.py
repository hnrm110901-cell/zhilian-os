"""
Banquet Agent Phase 30 — 单元测试

覆盖端点：
  - get_table_utilization_rate
  - get_lead_dropout_stage
  - get_upsell_rate
  - get_no_show_rate
  - get_multi_hall_booking_rate
  - get_customer_satisfaction_score
  - get_peak_day_revenue
  - get_referral_rate
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
                deposit_fen=30000, table_count=10,
                banquet_type="wedding", banquet_date=None,
                status="confirmed", customer_id="C-001",
                package_id=None, created_at=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.deposit_fen      = deposit_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.package_id       = package_id
    o.contact_name     = "张三"
    o.created_at       = created_at or (datetime.utcnow() - timedelta(days=60))
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_hall(hid="H-001", name="一号厅", max_tables=30):
    h = MagicMock()
    h.id         = hid
    h.name       = name
    h.max_tables = max_tables
    h.is_active  = True
    return h


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001"):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    return b


def _make_lead(lid="L-001", stage="signed", source="微信", budget_fen=200000):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = (
        LeadStageEnum(stage)
        if stage in [e.value for e in LeadStageEnum]
        else MagicMock(value=stage)
    )
    l.expected_budget_fen = budget_fen
    l.created_at          = datetime.utcnow() - timedelta(days=20)
    return l


def _make_review(rid="R-001", rating=5, ai_score=90.0):
    r = MagicMock()
    r.id              = rid
    r.customer_rating = rating
    r.ai_score        = ai_score
    r.improvement_tags = []
    r.created_at      = datetime.utcnow() - timedelta(days=10)
    return r


def _make_package(pid="P-001", price_fen=25000, cost_fen=12000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    p.cost_fen            = cost_fen
    return p


# ── TestTableUtilizationRate ──────────────────────────────────────────────────

class TestTableUtilizationRate:

    @pytest.mark.asyncio
    async def test_utilization_computed(self):
        """1厅(30桌) + 1预订(10桌) → utilization = 10/30*100 ≈ 33.3%"""
        from src.api.banquet_agent import get_table_utilization_rate

        hall    = _make_hall(max_tables=30)
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(oid="O-001", table_count=10)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_table_utilization_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert len(result["halls"]) == 1
        h = result["halls"][0]
        assert h["booking_count"] == 1
        assert h["total_used_tables"] == 10
        assert h["utilization_pct"] == pytest.approx(33.3, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_table_utilization_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_table_utilization_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["overall_utilization_pct"] is None


# ── TestLeadDropoutStage ──────────────────────────────────────────────────────

class TestLeadDropoutStage:

    @pytest.mark.asyncio
    async def test_dropout_identified(self):
        """1 quoted lead (未签约) → quoted 阶段 dropout_count=1"""
        from src.api.banquet_agent import get_lead_dropout_stage

        lead = _make_lead(stage="quoted")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_dropout_stage(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        quoted = next(s for s in result["stages"] if s["stage"] == "quoted")
        assert quoted["dropout_count"] == 1
        assert quoted["dropout_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 stages 为空列表"""
        from src.api.banquet_agent import get_lead_dropout_stage

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_dropout_stage(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["stages"] == []
        assert result["max_dropout_stage"] is None


# ── TestUpsellRate ────────────────────────────────────────────────────────────

class TestUpsellRate:

    @pytest.mark.asyncio
    async def test_upsell_detected(self):
        """套餐价=25000/桌×10=250000, 实际=300000 → upsell=1, avg=500元"""
        from src.api.banquet_agent import get_upsell_rate

        pkg   = _make_package(price_fen=25000)
        order = _make_order(total_fen=300000, table_count=10,
                            package_id=pkg.id, status="confirmed")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_upsell_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 1
        assert result["upsell_count"] == 1
        assert result["upsell_rate_pct"] == pytest.approx(100.0)
        assert result["avg_upsell_yuan"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无套餐订单时 upsell_rate_pct = None"""
        from src.api.banquet_agent import get_upsell_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_upsell_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["upsell_rate_pct"] is None


# ── TestNoShowRate ────────────────────────────────────────────────────────────

class TestNoShowRate:

    @pytest.mark.asyncio
    async def test_no_show_computed(self):
        """1 cancelled + deposit > 0 / 2 total → no_show_rate=50%"""
        from src.api.banquet_agent import get_no_show_rate

        cancelled = _make_order(status="cancelled", deposit_fen=30000,
                                total_fen=300000, paid_fen=30000)
        confirmed = _make_order(oid="O-002", status="confirmed",
                                deposit_fen=30000, total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([cancelled])
            return _scalars_returning([cancelled, confirmed])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_no_show_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["no_show_count"] == 1
        assert result["no_show_rate_pct"] == pytest.approx(50.0)
        assert result["total_lost_yuan"] == pytest.approx(2700.0)

    @pytest.mark.asyncio
    async def test_no_cancellations_returns_zero(self):
        """无取消时 no_show_count == 0"""
        from src.api.banquet_agent import get_no_show_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_no_show_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["no_show_count"] == 0
        assert result["no_show_rate_pct"] is None


# ── TestMultiHallBookingRate ──────────────────────────────────────────────────

class TestMultiHallBookingRate:

    @pytest.mark.asyncio
    async def test_multi_hall_detected(self):
        """1 order with 2 hall bookings → multi_hall_count=1, rate=100%"""
        from src.api.banquet_agent import get_multi_hall_booking_rate

        order = _make_order()
        bk1   = _make_booking(bid="B-001", hall_id="H-001", order_id=order.id)
        bk2   = _make_booking(bid="B-002", hall_id="H-002", order_id=order.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([bk1, bk2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_multi_hall_booking_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["multi_hall_count"] == 1
        assert result["multi_hall_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none_rate(self):
        """无订单时 multi_hall_rate_pct = None"""
        from src.api.banquet_agent import get_multi_hall_booking_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_multi_hall_booking_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["multi_hall_rate_pct"] is None


# ── TestCustomerSatisfactionScore ─────────────────────────────────────────────

class TestCustomerSatisfactionScore:

    @pytest.mark.asyncio
    async def test_avg_rating_computed(self):
        """rating=5, ai_score=90 → avg_rating=5, nps=100"""
        from src.api.banquet_agent import get_customer_satisfaction_score

        rev = _make_review(rating=5, ai_score=90.0)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([rev]))

        result = await get_customer_satisfaction_score(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 1
        assert result["avg_rating"] == pytest.approx(5.0)
        assert result["avg_ai_score"] == pytest.approx(90.0)
        assert result["nps_estimate"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_reviews_returns_none(self):
        """无评价时 avg_rating = None"""
        from src.api.banquet_agent import get_customer_satisfaction_score

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_satisfaction_score(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["avg_rating"] is None
        assert result["by_month"] == []


# ── TestPeakDayRevenue ────────────────────────────────────────────────────────

class TestPeakDayRevenue:

    @pytest.mark.asyncio
    async def test_peak_weekday_identified(self):
        """周六宴会订单 → peak_weekday = '周六'"""
        from src.api.banquet_agent import get_peak_day_revenue

        # Find next Saturday
        today = date.today()
        days_until_sat = (5 - today.weekday()) % 7 or 7
        saturday = today - timedelta(days=(today.weekday() - 5) % 7 + 7)
        # Use a past Saturday
        last_sat = today - timedelta(days=(today.weekday() + 2) % 7 + 1)
        # Simpler: use a fixed date known to be Saturday
        # 2026-03-07 is Saturday
        sat_date = date(2026, 3, 7)

        order = _make_order(total_fen=500000, banquet_date=sat_date)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_peak_day_revenue(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["peak_weekday"] == "周六"
        sat_row = next(r for r in result["by_weekday"] if r["weekday"] == "周六")
        assert sat_row["total_revenue_yuan"] == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none_peak(self):
        """无订单时 peak_weekday = None"""
        from src.api.banquet_agent import get_peak_day_revenue

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_peak_day_revenue(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["peak_weekday"] is None
        assert result["by_weekday"] == []


# ── TestReferralRate ──────────────────────────────────────────────────────────

class TestReferralRate:

    @pytest.mark.asyncio
    async def test_referral_rate_computed(self):
        """1 转介绍 signed + 1 微信 quoted → referral_rate=50%, referral_win=100%"""
        from src.api.banquet_agent import get_referral_rate

        ref_lead   = _make_lead(lid="L-001", stage="signed", source="转介绍")
        other_lead = _make_lead(lid="L-002", stage="quoted", source="微信")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([ref_lead, other_lead]))

        result = await get_referral_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["referral_count"] == 1
        assert result["referral_rate_pct"] == pytest.approx(50.0)
        assert result["referral_win_rate_pct"] == pytest.approx(100.0)
        assert result["non_referral_win_rate_pct"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 referral_rate_pct = None"""
        from src.api.banquet_agent import get_referral_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_referral_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["referral_rate_pct"] is None
