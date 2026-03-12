"""
Banquet Agent Phase 50 — 单元测试

覆盖端点：
  - get_cancellation_notice_days
  - get_package_adoption_rate
  - get_weekend_vs_weekday_orders
  - get_quarterly_revenue
  - get_vip_booking_lead_time
  - get_hall_turnover_rate
  - get_order_full_payment_speed
  - get_exception_type_breakdown
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


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = "dinner"
    return b


def _make_customer(cid="C-001", vip_level=2):
    c = MagicMock()
    c.id        = cid
    c.vip_level = vip_level
    return c


def _make_payment(pid="P-001", order_id="O-001", amount_fen=300000, created_at=None):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.payment_method   = "微信"
    p.created_at       = created_at or datetime.utcnow() - timedelta(days=3)
    return p


def _make_exception(eid="E-001", order_id="O-001", exc_type="complaint"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = exc_type
    e.created_at       = datetime.utcnow() - timedelta(days=5)
    return e


# ── TestCancellationNoticeDays ─────────────────────────────────────────────────

class TestCancellationNoticeDays:

    @pytest.mark.asyncio
    async def test_notice_days_computed(self):
        """cancelled order: banquet 60d after created → avg_notice=60d"""
        from src.api.banquet_agent import get_cancellation_notice_days

        created   = datetime.utcnow() - timedelta(days=90)
        banquet_d = date.today() - timedelta(days=30)   # 60 days after created
        order = _make_order(status="cancelled", banquet_date=banquet_d, created_at=created)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_cancellation_notice_days(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_cancelled"] == 1
        assert result["avg_notice_days"] == pytest.approx(60.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_no_cancellations_returns_none(self):
        """无取消订单时 avg_notice_days = None"""
        from src.api.banquet_agent import get_cancellation_notice_days

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_cancellation_notice_days(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_cancelled"] == 0
        assert result["avg_notice_days"] is None


# ── TestPackageAdoptionRate ───────────────────────────────────────────────────

class TestPackageAdoptionRate:

    @pytest.mark.asyncio
    async def test_adoption_computed(self):
        """1 with package + 1 without → adoption_rate=50%"""
        from src.api.banquet_agent import get_package_adoption_rate

        o1 = _make_order(oid="O-001", total_fen=350000, package_id="PKG-001")
        o2 = _make_order(oid="O-002", total_fen=300000, package_id=None)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_package_adoption_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["package_count"] == 1
        assert result["adoption_rate_pct"] == pytest.approx(50.0)
        assert result["pkg_avg_yuan"] == pytest.approx(3500.0)
        assert result["no_pkg_avg_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 adoption_rate_pct = None"""
        from src.api.banquet_agent import get_package_adoption_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_package_adoption_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["adoption_rate_pct"] is None


# ── TestWeekendVsWeekdayOrders ────────────────────────────────────────────────

class TestWeekendVsWeekdayOrders:

    @pytest.mark.asyncio
    async def test_weekend_detected(self):
        """Saturday order + Monday order → weekend_ratio=50%"""
        from src.api.banquet_agent import get_weekend_vs_weekday_orders

        # Find next Saturday
        today = date.today()
        days_to_sat = (5 - today.weekday()) % 7 or 7
        sat = today - timedelta(days=(today.weekday() - 5) % 7 + 7)
        mon = today - timedelta(days=today.weekday() + 7)   # last Monday

        o1 = _make_order(oid="O-001", banquet_date=sat, total_fen=300000)
        o2 = _make_order(oid="O-002", banquet_date=mon, total_fen=300000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_weekend_vs_weekday_orders(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["weekend_ratio_pct"] == pytest.approx(50.0)
        assert result["weekend"]["count"] == 1
        assert result["weekday"]["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 weekend = None"""
        from src.api.banquet_agent import get_weekend_vs_weekday_orders

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_weekend_vs_weekday_orders(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["weekend"] is None


# ── TestQuarterlyRevenue ──────────────────────────────────────────────────────

class TestQuarterlyRevenue:

    @pytest.mark.asyncio
    async def test_quarterly_computed(self):
        """1 order in Q2 → quarters has Q2 entry"""
        from src.api.banquet_agent import get_quarterly_revenue

        order = _make_order(total_fen=300000, banquet_date=date(date.today().year, 5, 15))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_quarterly_revenue(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert any("Q2" in q["quarter"] for q in result["quarters"])
        assert result["best_quarter"] is not None

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 quarters 为空"""
        from src.api.banquet_agent import get_quarterly_revenue

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_quarterly_revenue(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["quarters"] == []
        assert result["best_quarter"] is None


# ── TestVipBookingLeadTime ────────────────────────────────────────────────────

class TestVipBookingLeadTime:

    @pytest.mark.asyncio
    async def test_lead_time_compared(self):
        """VIP plans 90d ahead, normal 30d ahead"""
        from src.api.banquet_agent import get_vip_booking_lead_time

        vip = _make_customer(cid="C-VIP", vip_level=2)

        vip_created = datetime.utcnow() - timedelta(days=120)
        vip_banquet = date.today() - timedelta(days=30)   # 90d lead
        norm_created = datetime.utcnow() - timedelta(days=60)
        norm_banquet = date.today() - timedelta(days=30)  # 30d lead

        o_vip  = _make_order(oid="O-001", customer_id="C-VIP",
                             banquet_date=vip_banquet, created_at=vip_created)
        o_norm = _make_order(oid="O-002", customer_id="C-NORM",
                             banquet_date=norm_banquet, created_at=norm_created)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([vip])
            return _scalars_returning([o_vip, o_norm])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_booking_lead_time(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["vip_avg_days"] == pytest.approx(90.0, abs=1.0)
        assert result["normal_avg_days"] == pytest.approx(30.0, abs=1.0)
        assert result["vip_plans_earlier"] is True

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 vip_avg_days = None"""
        from src.api.banquet_agent import get_vip_booking_lead_time

        vip = _make_customer(cid="C-VIP", vip_level=2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([vip])
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_booking_lead_time(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["vip_avg_days"] is None


# ── TestHallTurnoverRate ──────────────────────────────────────────────────────

class TestHallTurnoverRate:

    @pytest.mark.asyncio
    async def test_turnover_computed(self):
        """H-001 booked 3 times in 3 months → per_month=1.0"""
        from src.api.banquet_agent import get_hall_turnover_rate

        b1 = _make_booking(bid="B-001", hall_id="H-001")
        b2 = _make_booking(bid="B-002", hall_id="H-001")
        b3 = _make_booking(bid="B-003", hall_id="H-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2, b3]))

        result = await get_hall_turnover_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_bookings"] == 3
        assert result["hall_count"] == 1
        assert result["avg_turnover_per_month"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 avg_turnover_per_month = None"""
        from src.api.banquet_agent import get_hall_turnover_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_turnover_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["avg_turnover_per_month"] is None


# ── TestOrderFullPaymentSpeed ─────────────────────────────────────────────────

class TestOrderFullPaymentSpeed:

    @pytest.mark.asyncio
    async def test_speed_computed(self):
        """order created 10d ago, last payment 3d ago → avg=7d"""
        from src.api.banquet_agent import get_order_full_payment_speed

        order_created = datetime.utcnow() - timedelta(days=10)
        pay_created   = datetime.utcnow() - timedelta(days=3)
        order   = _make_order(total_fen=300000, paid_fen=300000, created_at=order_created)
        payment = _make_payment(order_id=order.id, created_at=pay_created)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([payment])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_order_full_payment_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 1
        assert result["avg_days_to_full_payment"] == pytest.approx(7.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无全额付款订单时 avg_days_to_full_payment = None"""
        from src.api.banquet_agent import get_order_full_payment_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_full_payment_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 0
        assert result["avg_days_to_full_payment"] is None


# ── TestExceptionTypeBreakdown ────────────────────────────────────────────────

class TestExceptionTypeBreakdown:

    @pytest.mark.asyncio
    async def test_breakdown_computed(self):
        """2 complaint + 1 damage → most_common=complaint"""
        from src.api.banquet_agent import get_exception_type_breakdown

        e1 = _make_exception(eid="E-001", exc_type="complaint")
        e2 = _make_exception(eid="E-002", exc_type="complaint")
        e3 = _make_exception(eid="E-003", exc_type="damage")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([e1, e2, e3]))

        result = await get_exception_type_breakdown(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_exceptions"] == 3
        assert result["most_common_type"] == "complaint"
        c = next(t for t in result["by_type"] if t["type"] == "complaint")
        assert c["count"] == 2
        assert c["pct"] == pytest.approx(66.7, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_exceptions_returns_none(self):
        """无异常时 most_common_type = None"""
        from src.api.banquet_agent import get_exception_type_breakdown

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_exception_type_breakdown(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_exceptions"] == 0
        assert result["most_common_type"] is None
