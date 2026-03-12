"""
Banquet Agent Phase 59 — 单元测试

覆盖端点：
  - get_order_table_utilization_rate
  - get_lead_age_distribution
  - get_hall_revenue_by_slot
  - get_customer_referral_rate
  - get_payment_partial_rate
  - get_banquet_weekday_distribution
  - get_staff_multitask_rate
  - get_contract_amendment_speed
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


def _make_lead(lid="L-001", stage="new", source="微信", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = source
    l.current_stage  = LeadStageEnum(stage)
    l.created_at     = created_at or datetime.utcnow() - timedelta(days=20)
    return l


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_date=None, slot_name="dinner"):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = slot_name
    return b


def _make_task(tid="T-001", owner="U-001", order_id="O-001", created_at=None):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return t


def _make_contract(cid="CT-001", order_id="O-001", created_at=None):
    c = MagicMock()
    c.id               = cid
    c.banquet_order_id = order_id
    c.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return c


# ── TestOrderTableUtilizationRate ─────────────────────────────────────────────

class TestOrderTableUtilizationRate:

    @pytest.mark.asyncio
    async def test_utilization_computed(self):
        """2 orders: 10 and 20 tables → avg=15, max=20, util=75%"""
        from src.api.banquet_agent import get_order_table_utilization_rate

        o1 = _make_order(oid="O-001", table_count=10)
        o2 = _make_order(oid="O-002", table_count=20)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_order_table_utilization_rate(store_id="S001", months=6,
                                                         db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["avg_table_count"] == pytest.approx(15.0)
        assert result["utilization_rate_pct"] == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 utilization_rate_pct = None"""
        from src.api.banquet_agent import get_order_table_utilization_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_table_utilization_rate(store_id="S001", months=6,
                                                         db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["utilization_rate_pct"] is None


# ── TestLeadAgeDistribution ───────────────────────────────────────────────────

class TestLeadAgeDistribution:

    @pytest.mark.asyncio
    async def test_age_computed(self):
        """lead created 20d ago → in 8-30d bucket"""
        from src.api.banquet_agent import get_lead_age_distribution

        l = _make_lead(lid="L-001", created_at=datetime.utcnow() - timedelta(days=20))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l]))

        result = await get_lead_age_distribution(store_id="S001", months=6,
                                                  db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["avg_age_days"] is not None
        assert result["avg_age_days"] > 0
        assert len(result["distribution"]) >= 1

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 avg_age_days = None"""
        from src.api.banquet_agent import get_lead_age_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_age_distribution(store_id="S001", months=6,
                                                  db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_age_days"] is None


# ── TestHallRevenueBySlot ─────────────────────────────────────────────────────

class TestHallRevenueBySlot:

    @pytest.mark.asyncio
    async def test_slot_revenue_computed(self):
        """dinner booking on O-001 (300000fen) → peak_slot=dinner"""
        from src.api.banquet_agent import get_hall_revenue_by_slot

        booking = _make_booking(bid="B-001", order_id="O-001", slot_name="dinner")
        order   = _make_order(oid="O-001", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_revenue_by_slot(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_bookings"] == 1
        assert result["peak_slot"] == "dinner"
        s = next(s for s in result["by_slot"] if s["slot"] == "dinner")
        assert s["revenue_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_empty(self):
        """无预订时 peak_slot = None"""
        from src.api.banquet_agent import get_hall_revenue_by_slot

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_by_slot(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["peak_slot"] is None


# ── TestCustomerReferralRate ──────────────────────────────────────────────────

class TestCustomerReferralRate:

    @pytest.mark.asyncio
    async def test_referral_detected(self):
        """1 老客介绍 + 1 微信 → referral_rate=50%"""
        from src.api.banquet_agent import get_customer_referral_rate

        l1 = _make_lead(lid="L-001", source="老客介绍")
        l2 = _make_lead(lid="L-002", source="微信")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_customer_referral_rate(store_id="S001", months=12,
                                                   db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["referral_count"] == 1
        assert result["referral_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 referral_rate_pct = None"""
        from src.api.banquet_agent import get_customer_referral_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_referral_rate(store_id="S001", months=12,
                                                   db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["referral_rate_pct"] is None


# ── TestPaymentPartialRate ────────────────────────────────────────────────────

class TestPaymentPartialRate:

    @pytest.mark.asyncio
    async def test_partial_detected(self):
        """paid=100000 < total=300000 → partial_count=1, outstanding=2000yuan"""
        from src.api.banquet_agent import get_payment_partial_rate

        o = _make_order(total_fen=300000, paid_fen=100000, status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_payment_partial_rate(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["partial_count"] == 1
        assert result["partial_rate_pct"] == pytest.approx(100.0)
        assert result["outstanding_yuan"] == pytest.approx(2000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 partial_rate_pct = None"""
        from src.api.banquet_agent import get_payment_partial_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_partial_rate(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["partial_rate_pct"] is None


# ── TestBanquetWeekdayDistribution ────────────────────────────────────────────

class TestBanquetWeekdayDistribution:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """2 orders on Saturday → peak_weekday=周六"""
        from src.api.banquet_agent import get_banquet_weekday_distribution

        saturday = date.today()
        while saturday.weekday() != 5:
            saturday -= timedelta(days=1)

        o1 = _make_order(oid="O-001", banquet_date=saturday)
        o2 = _make_order(oid="O-002", banquet_date=saturday)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_weekday_distribution(store_id="S001", months=12,
                                                         db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["peak_weekday"] == "周六"
        assert len(result["by_weekday"]) == 7

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 peak_weekday = None"""
        from src.api.banquet_agent import get_banquet_weekday_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_weekday_distribution(store_id="S001", months=12,
                                                         db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["peak_weekday"] is None


# ── TestStaffMultitaskRate ────────────────────────────────────────────────────

class TestStaffMultitaskRate:

    @pytest.mark.asyncio
    async def test_multitask_detected(self):
        """U-001: 2 tasks on same day → multitask_staff_count=1, rate=100%"""
        from src.api.banquet_agent import get_staff_multitask_rate

        same_day = datetime.utcnow() - timedelta(days=3)
        t1 = _make_task(tid="T-001", owner="U-001", created_at=same_day)
        t2 = _make_task(tid="T-002", owner="U-001", created_at=same_day)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([t1, t2]))

        result = await get_staff_multitask_rate(store_id="S001", months=3,
                                                 db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["multitask_staff_count"] == 1
        assert result["multitask_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        """无任务时 multitask_rate_pct = None"""
        from src.api.banquet_agent import get_staff_multitask_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_multitask_rate(store_id="S001", months=3,
                                                 db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["multitask_rate_pct"] is None


# ── TestContractAmendmentSpeed ────────────────────────────────────────────────

class TestContractAmendmentSpeed:

    @pytest.mark.asyncio
    async def test_speed_computed(self):
        """O-001: 2 contracts 7d apart → avg_amendment_days=7"""
        from src.api.banquet_agent import get_contract_amendment_speed

        order  = _make_order(oid="O-001")
        dt1    = datetime.utcnow() - timedelta(days=10)
        dt2    = datetime.utcnow() - timedelta(days=3)
        ct1    = _make_contract(cid="CT-001", order_id="O-001", created_at=dt1)
        ct2    = _make_contract(cid="CT-002", order_id="O-001", created_at=dt2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([ct1, ct2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_contract_amendment_speed(store_id="S001", months=6,
                                                     db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["amended_count"] == 1
        assert result["avg_amendment_days"] == pytest.approx(7.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_amendment_days = None"""
        from src.api.banquet_agent import get_contract_amendment_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_contract_amendment_speed(store_id="S001", months=6,
                                                     db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_amendment_days"] is None
