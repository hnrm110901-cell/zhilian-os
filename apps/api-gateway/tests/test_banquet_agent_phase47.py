"""
Banquet Agent Phase 47 — 单元测试

覆盖端点：
  - get_hall_preference_by_type
  - get_customer_multi_order_rate
  - get_monthly_revenue_trend
  - get_staff_overtime_rate
  - get_partial_payment_rate
  - get_vip_order_value_premium
  - get_banquet_type_growth
  - get_lead_contact_speed
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


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_date=None, slot_name="dinner"):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = slot_name
    return b


def _make_task(tid="T-001", owner="U-001", order_id="O-001",
               completed_at=None, due_time=None):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.completed_at     = completed_at or datetime.utcnow()
    t.due_time         = due_time or datetime.utcnow() + timedelta(hours=24)
    return t


def _make_customer(cid="C-001", vip_level=2):
    c = MagicMock()
    c.id        = cid
    c.vip_level = vip_level
    c.created_at = datetime.utcnow() - timedelta(days=365)
    return c


def _make_lead(lid="L-001", store_id="S001"):
    l = MagicMock()
    l.id         = lid
    l.store_id   = store_id
    l.created_at = datetime.utcnow() - timedelta(days=10)
    return l


def _make_followup(fid="F-001", lead_id="L-001", days_after_lead=2):
    f = MagicMock()
    f.id         = fid
    f.lead_id    = lead_id
    f.created_at = datetime.utcnow() - timedelta(days=10) + timedelta(days=days_after_lead)
    return f


# ── TestHallPreferenceByType ──────────────────────────────────────────────────

class TestHallPreferenceByType:

    @pytest.mark.asyncio
    async def test_preference_computed(self):
        """wedding order booked to H-001 → preferred_hall=H-001"""
        from src.api.banquet_agent import get_hall_preference_by_type

        order   = _make_order(oid="O-001", banquet_type="wedding")
        booking = _make_booking(hall_id="H-001", order_id="O-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([booking])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_preference_by_type(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["top_hall"] == "H-001"
        w = next((t for t in result["by_type"] if t["banquet_type"] == "wedding"), None)
        assert w is not None
        assert w["preferred_hall"] == "H-001"

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 top_hall = None"""
        from src.api.banquet_agent import get_hall_preference_by_type

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_preference_by_type(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["top_hall"] is None


# ── TestCustomerMultiOrderRate ─────────────────────────────────────────────────

class TestCustomerMultiOrderRate:

    @pytest.mark.asyncio
    async def test_multi_order_computed(self):
        """C-001 has 2 orders → multi_order_rate=50% (1/2 customers)"""
        from src.api.banquet_agent import get_customer_multi_order_rate

        o1 = _make_order(oid="O-001", customer_id="C-001")
        o2 = _make_order(oid="O-002", customer_id="C-001")
        o3 = _make_order(oid="O-003", customer_id="C-002")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2, o3]))

        result = await get_customer_multi_order_rate(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 2
        assert result["multi_order_customers"] == 1
        assert result["multi_order_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 multi_order_rate_pct = None"""
        from src.api.banquet_agent import get_customer_multi_order_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_multi_order_rate(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["multi_order_rate_pct"] is None


# ── TestMonthlyRevenueTrend ────────────────────────────────────────────────────

class TestMonthlyRevenueTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """2 orders → monthly trend has 1 or 2 entries, total_revenue correct"""
        from src.api.banquet_agent import get_monthly_revenue_trend

        d1 = date.today() - timedelta(days=40)
        d2 = date.today() - timedelta(days=10)
        o1 = _make_order(oid="O-001", total_fen=200000, banquet_date=d1)
        o2 = _make_order(oid="O-002", total_fen=300000, banquet_date=d2)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_monthly_revenue_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["total_revenue_yuan"] == pytest.approx(5000.0)
        assert len(result["monthly"]) >= 1
        assert result["peak_month"] is not None

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 monthly 为空"""
        from src.api.banquet_agent import get_monthly_revenue_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_monthly_revenue_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["monthly"] == []
        assert result["peak_month"] is None


# ── TestStaffOvertimeRate ─────────────────────────────────────────────────────

class TestStaffOvertimeRate:

    @pytest.mark.asyncio
    async def test_overtime_detected(self):
        """task completed 2h after due_time → overtime_count=1, rate=100%"""
        from src.api.banquet_agent import get_staff_overtime_rate

        due  = datetime.utcnow() - timedelta(hours=3)
        comp = datetime.utcnow() - timedelta(hours=1)   # 2h late
        task = _make_task(completed_at=comp, due_time=due)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_overtime_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["overtime_count"] == 1
        assert result["overtime_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        """无已完成任务时 overtime_rate_pct = None"""
        from src.api.banquet_agent import get_staff_overtime_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_overtime_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["overtime_rate_pct"] is None


# ── TestPartialPaymentRate ─────────────────────────────────────────────────────

class TestPartialPaymentRate:

    @pytest.mark.asyncio
    async def test_partial_detected(self):
        """1 partial (paid=100000, total=300000) + 1 full → rate=50%"""
        from src.api.banquet_agent import get_partial_payment_rate

        o1 = _make_order(oid="O-001", total_fen=300000, paid_fen=100000)
        o2 = _make_order(oid="O-002", total_fen=300000, paid_fen=300000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_partial_payment_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["partial_count"] == 1
        assert result["partial_rate_pct"] == pytest.approx(50.0)
        assert result["avg_unpaid_yuan"] == pytest.approx(2000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 partial_rate_pct = None"""
        from src.api.banquet_agent import get_partial_payment_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_partial_payment_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["partial_rate_pct"] is None


# ── TestVipOrderValuePremium ──────────────────────────────────────────────────

class TestVipOrderValuePremium:

    @pytest.mark.asyncio
    async def test_premium_computed(self):
        """VIP order 6000yuan, normal 3000yuan → premium=100%"""
        from src.api.banquet_agent import get_vip_order_value_premium

        vip    = _make_customer(cid="C-VIP", vip_level=2)
        o_vip  = _make_order(oid="O-001", total_fen=600000, customer_id="C-VIP")
        o_norm = _make_order(oid="O-002", total_fen=300000, customer_id="C-NORM")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([vip])
            return _scalars_returning([o_vip, o_norm])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_order_value_premium(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["vip_avg_yuan"] == pytest.approx(6000.0)
        assert result["normal_avg_yuan"] == pytest.approx(3000.0)
        assert result["premium_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 premium_pct = None"""
        from src.api.banquet_agent import get_vip_order_value_premium

        vip = _make_customer(cid="C-VIP", vip_level=2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([vip])
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_order_value_premium(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["premium_pct"] is None


# ── TestBanquetTypeGrowth ─────────────────────────────────────────────────────

class TestBanquetTypeGrowth:

    @pytest.mark.asyncio
    async def test_growth_computed(self):
        """current: 2 wedding; prior: 1 wedding → growth=100%"""
        from src.api.banquet_agent import get_banquet_type_growth

        cur1 = _make_order(oid="O-001", banquet_type="wedding",
                           banquet_date=date.today() - timedelta(days=10))
        cur2 = _make_order(oid="O-002", banquet_type="wedding",
                           banquet_date=date.today() - timedelta(days=20))
        prior1 = _make_order(oid="O-003", banquet_type="wedding",
                             banquet_date=date.today() - timedelta(days=200))

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([cur1, cur2])
            return _scalars_returning([prior1])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_type_growth(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_current"] == 2
        assert result["total_prior"] == 1
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["growth_pct"] == pytest.approx(100.0)
        assert result["fastest_growing"] == "wedding"

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 fastest_growing = None"""
        from src.api.banquet_agent import get_banquet_type_growth

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_growth(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_current"] == 0
        assert result["fastest_growing"] is None


# ── TestLeadContactSpeed ──────────────────────────────────────────────────────

class TestLeadContactSpeed:

    @pytest.mark.asyncio
    async def test_speed_computed(self):
        """lead created 10 days ago, followup 2 days later → avg=2d, fast_pct=0%"""
        from src.api.banquet_agent import get_lead_contact_speed

        lead = _make_lead(lid="L-001")
        fu   = _make_followup(fid="F-001", lead_id="L-001", days_after_lead=2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([fu])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_contact_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["avg_contact_days"] == pytest.approx(2.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_contact_days = None"""
        from src.api.banquet_agent import get_lead_contact_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_contact_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_contact_days"] is None
