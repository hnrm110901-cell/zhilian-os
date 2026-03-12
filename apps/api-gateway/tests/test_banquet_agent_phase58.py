"""
Banquet Agent Phase 58 — 单元测试

覆盖端点：
  - get_order_completion_rate
  - get_lead_monthly_conversion_trend
  - get_hall_booking_density
  - get_customer_avg_order_value
  - get_payment_on_time_rate
  - get_banquet_type_revenue_growth
  - get_staff_satisfaction_score
  - get_exception_type_distribution
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


def _make_lead(lid="L-001", stage="won", source="微信", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = source
    l.current_stage  = LeadStageEnum(stage)
    l.created_at     = created_at or datetime.utcnow() - timedelta(days=20)
    return l


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = "dinner"
    return b


def _make_payment(pid="P-001", order_id="O-001", amount_fen=30000, created_at=None):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return p


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    return t


def _make_review(rid="R-001", order_id="O-001", rating=5):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.created_at       = datetime.utcnow() - timedelta(days=5)
    return r


def _make_exception(eid="E-001", order_id="O-001", exc_type="complaint"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = exc_type
    e.created_at       = datetime.utcnow() - timedelta(days=10)
    e.resolved_at      = None
    return e


# ── TestOrderCompletionRate ───────────────────────────────────────────────────

class TestOrderCompletionRate:

    @pytest.mark.asyncio
    async def test_completion_rate_computed(self):
        """1 completed / 2 non-cancelled → completion_rate=50%"""
        from src.api.banquet_agent import get_order_completion_rate

        o1 = _make_order(oid="O-001", status="completed")
        o2 = _make_order(oid="O-002", status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_order_completion_rate(store_id="S001", months=12,
                                                  db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["completed_count"] == 1
        assert result["completion_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 completion_rate_pct = None"""
        from src.api.banquet_agent import get_order_completion_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_completion_rate(store_id="S001", months=12,
                                                  db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["completion_rate_pct"] is None


# ── TestLeadMonthlyConversionTrend ────────────────────────────────────────────

class TestLeadMonthlyConversionTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """1 won + 1 new → monthly entry with conversion_pct=50%"""
        from src.api.banquet_agent import get_lead_monthly_conversion_trend

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="new")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_lead_monthly_conversion_trend(store_id="S001", months=6,
                                                          db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert len(result["monthly"]) >= 1
        assert result["monthly"][0]["conversion_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 trend_direction = None"""
        from src.api.banquet_agent import get_lead_monthly_conversion_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_monthly_conversion_trend(store_id="S001", months=6,
                                                          db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["trend_direction"] is None


# ── TestHallBookingDensity ────────────────────────────────────────────────────

class TestHallBookingDensity:

    @pytest.mark.asyncio
    async def test_density_computed(self):
        """H-001 booked 1 day → density_pct > 0"""
        from src.api.banquet_agent import get_hall_booking_density

        b = _make_booking(bid="B-001", hall_id="H-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b]))

        result = await get_hall_booking_density(store_id="S001", months=3,
                                                 db=db, _=_mock_user())

        assert result["total_halls"] == 1
        assert result["busiest_hall"] == "H-001"
        assert result["halls"][0]["density_pct"] > 0

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 busiest_hall = None"""
        from src.api.banquet_agent import get_hall_booking_density

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_booking_density(store_id="S001", months=3,
                                                 db=db, _=_mock_user())

        assert result["total_halls"] == 0
        assert result["busiest_hall"] is None


# ── TestCustomerAvgOrderValue ─────────────────────────────────────────────────

class TestCustomerAvgOrderValue:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """C-001: 600000fen=6000yuan(高价值), C-002: 100000fen=1000yuan(低价值)"""
        from src.api.banquet_agent import get_customer_avg_order_value

        o1 = _make_order(oid="O-001", total_fen=600000, customer_id="C-001")
        o2 = _make_order(oid="O-002", total_fen=100000, customer_id="C-002")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_avg_order_value(store_id="S001", months=12,
                                                     db=db, _=_mock_user())

        assert result["total_customers"] == 2
        assert result["avg_order_value_yuan"] == pytest.approx(3500.0)
        assert len(result["distribution"]) == 3   # all 3 tiers listed

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_order_value_yuan = None"""
        from src.api.banquet_agent import get_customer_avg_order_value

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_avg_order_value(store_id="S001", months=12,
                                                     db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["avg_order_value_yuan"] is None


# ── TestPaymentOnTimeRate ─────────────────────────────────────────────────────

class TestPaymentOnTimeRate:

    @pytest.mark.asyncio
    async def test_on_time_computed(self):
        """payment 5d before banquet → on_time_count=1, rate=100%"""
        from src.api.banquet_agent import get_payment_on_time_rate

        banquet_dt = date.today() + timedelta(days=5)
        order = _make_order(oid="O-001", total_fen=300000, paid_fen=300000,
                            banquet_date=banquet_dt)
        pay_dt = datetime.utcnow() - timedelta(days=1)
        payment = _make_payment(pid="P-001", order_id="O-001", created_at=pay_dt)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([payment])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_payment_on_time_rate(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_fully_paid"] == 1
        assert result["on_time_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无全款订单时 on_time_rate_pct = None"""
        from src.api.banquet_agent import get_payment_on_time_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_on_time_rate(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_fully_paid"] == 0
        assert result["on_time_rate_pct"] is None


# ── TestBanquetTypeRevenueGrowth ──────────────────────────────────────────────

class TestBanquetTypeRevenueGrowth:

    @pytest.mark.asyncio
    async def test_growth_computed(self):
        """wedding order in current period only → growth_pct = None (prev=0)"""
        from src.api.banquet_agent import get_banquet_type_revenue_growth

        o = _make_order(oid="O-001", banquet_type="wedding", total_fen=300000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_banquet_type_revenue_growth(store_id="S001", months=12,
                                                        db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert len(result["by_type"]) >= 1
        assert result["fastest_growing_type"] is not None

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 fastest_growing_type = None"""
        from src.api.banquet_agent import get_banquet_type_revenue_growth

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_revenue_growth(store_id="S001", months=12,
                                                        db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["fastest_growing_type"] is None


# ── TestStaffSatisfactionScore ────────────────────────────────────────────────

class TestStaffSatisfactionScore:

    @pytest.mark.asyncio
    async def test_score_computed(self):
        """U-001 task on O-001, review rating=5 → avg_score=5.0"""
        from src.api.banquet_agent import get_staff_satisfaction_score

        task   = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        review = _make_review(rid="R-001", order_id="O-001", rating=5)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([task])
            return _scalars_returning([review])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_satisfaction_score(store_id="S001", months=6,
                                                     db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["top_rated_staff"] == "U-001"
        assert result["staff"][0]["avg_score"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 top_rated_staff = None"""
        from src.api.banquet_agent import get_staff_satisfaction_score

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_satisfaction_score(store_id="S001", months=6,
                                                     db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["top_rated_staff"] is None


# ── TestExceptionTypeDistribution ────────────────────────────────────────────

class TestExceptionTypeDistribution:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """2 complaint + 1 facility → most_common=complaint"""
        from src.api.banquet_agent import get_exception_type_distribution

        e1 = _make_exception(eid="E-001", exc_type="complaint")
        e2 = _make_exception(eid="E-002", exc_type="complaint")
        e3 = _make_exception(eid="E-003", exc_type="facility")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([e1, e2, e3]))

        result = await get_exception_type_distribution(store_id="S001", months=6,
                                                        db=db, _=_mock_user())

        assert result["total_exceptions"] == 3
        assert result["most_common_type"] == "complaint"
        comp = next(t for t in result["by_type"] if t["type"] == "complaint")
        assert comp["count"] == 2
        assert comp["pct"] == pytest.approx(66.7, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_exceptions_returns_empty(self):
        """无异常时 most_common_type = None"""
        from src.api.banquet_agent import get_exception_type_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_exception_type_distribution(store_id="S001", months=6,
                                                        db=db, _=_mock_user())

        assert result["total_exceptions"] == 0
        assert result["most_common_type"] is None
