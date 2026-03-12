"""
Banquet Agent Phase 42 — 单元测试

覆盖端点：
  - get_banquet_revenue_per_guest
  - get_hall_booking_density
  - get_lead_budget_accuracy
  - get_customer_feedback_response_rate
  - get_banquet_addon_revenue
  - get_staff_task_overdue_rate
  - get_deposit_to_final_payment_gap
  - get_vip_upgrade_rate
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
                table_count=10, people_count=100,
                banquet_type="wedding", banquet_date=None,
                status="confirmed", customer_id="C-001",
                package_id=None, created_at=None):
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
    o.contact_name     = "张三"
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


def _make_booking(bid="B-001", hall_id="H-001", slot_date=None):
    b = MagicMock()
    b.id       = bid
    b.hall_id  = hall_id
    b.slot_date = slot_date or (date.today() - timedelta(days=10))
    return b


def _make_lead(lid="L-001", stage="won", customer_id="C-001", budget_fen=300000):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = "微信"
    l.current_stage       = LeadStageEnum(stage)
    l.customer_id         = customer_id
    l.expected_budget_fen = budget_fen
    l.created_at          = datetime.utcnow() - timedelta(days=30)
    l.updated_at          = datetime.utcnow() - timedelta(days=5)
    return l


def _make_exception(eid="E-001", order_id="O-001", exc_type="complaint",
                    status="resolved"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = exc_type
    e.status           = status
    e.created_at       = datetime.utcnow() - timedelta(days=5)
    return e


def _make_package(pid="PKG-001", price_fen=25000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    return p


def _make_task(tid="T-001", owner="U-001", order_id="O-001",
               status="done", overdue=False):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.due_time         = datetime.utcnow() - timedelta(hours=1)
    t.completed_at     = (datetime.utcnow() + timedelta(hours=1)
                          if overdue else datetime.utcnow() - timedelta(hours=2))
    return t


def _make_payment(pid="P-001", order_id="O-001", amount_fen=30000, days_ago=10):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.created_at       = datetime.utcnow() - timedelta(days=days_ago)
    return p


def _make_customer(cid="C-001", vip_level=2):
    c = MagicMock()
    c.id        = cid
    c.vip_level = vip_level
    c.total_banquet_count = 2
    c.created_at = datetime.utcnow() - timedelta(days=60)
    return c


# ── TestBanquetRevenuePerGuest ────────────────────────────────────────────────

class TestBanquetRevenuePerGuest:

    @pytest.mark.asyncio
    async def test_per_guest_computed(self):
        """300000fen / 100 people = 30元/人"""
        from src.api.banquet_agent import get_banquet_revenue_per_guest

        order = _make_order(total_fen=300000, people_count=100)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_revenue_per_guest(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["overall_per_guest_yuan"] == pytest.approx(30.0)
        assert len(result["by_type"]) == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_per_guest_yuan = None"""
        from src.api.banquet_agent import get_banquet_revenue_per_guest

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_revenue_per_guest(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_per_guest_yuan"] is None


# ── TestHallBookingDensity ────────────────────────────────────────────────────

class TestHallBookingDensity:

    @pytest.mark.asyncio
    async def test_density_computed(self):
        """1 hall, 1 booking in 3 months → density=1/(3*30/7)≈0.08"""
        from src.api.banquet_agent import get_hall_booking_density

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            return _scalars_returning([booking])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_booking_density(store_id="S001", months=3, db=db, _=_mock_user())

        assert len(result["halls"]) == 1
        assert result["halls"][0]["booking_count"] == 1
        assert result["overall_weekly_density"] == pytest.approx(1 / (3 * 30 / 7), abs=0.01)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_booking_density

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_booking_density(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["overall_weekly_density"] is None


# ── TestLeadBudgetAccuracy ────────────────────────────────────────────────────

class TestLeadBudgetAccuracy:

    @pytest.mark.asyncio
    async def test_accuracy_computed(self):
        """budget=300000, actual=300000 → deviation=0%, accurate=100%"""
        from src.api.banquet_agent import get_lead_budget_accuracy

        lead  = _make_lead(stage="won", customer_id="C-001", budget_fen=300000)
        order = _make_order(total_fen=300000, customer_id="C-001", status="confirmed")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_budget_accuracy(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won"] == 1
        assert result["avg_deviation_pct"] == pytest.approx(0.0)
        assert result["accurate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无成单线索时 avg_deviation_pct = None"""
        from src.api.banquet_agent import get_lead_budget_accuracy

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_budget_accuracy(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won"] == 0
        assert result["avg_deviation_pct"] is None


# ── TestCustomerFeedbackResponseRate ─────────────────────────────────────────

class TestCustomerFeedbackResponseRate:

    @pytest.mark.asyncio
    async def test_response_computed(self):
        """1 complaint resolved → response_rate=100%"""
        from src.api.banquet_agent import get_customer_feedback_response_rate

        exc = _make_exception(exc_type="complaint", status="resolved")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([exc]))

        result = await get_customer_feedback_response_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_complaints"] == 1
        assert result["resolved_count"] == 1
        assert result["response_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_complaints_returns_none(self):
        """无投诉时 response_rate_pct = None"""
        from src.api.banquet_agent import get_customer_feedback_response_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_feedback_response_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_complaints"] == 0
        assert result["response_rate_pct"] is None


# ── TestBanquetAddonRevenue ───────────────────────────────────────────────────

class TestBanquetAddonRevenue:

    @pytest.mark.asyncio
    async def test_addon_computed(self):
        """pkg 25000*10=250000, actual=300000 → addon=500元"""
        from src.api.banquet_agent import get_banquet_addon_revenue

        pkg   = _make_package(price_fen=25000)
        order = _make_order(total_fen=300000, table_count=10, package_id=pkg.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_addon_revenue(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 1
        assert result["addon_orders"] == 1
        assert result["total_addon_yuan"] == pytest.approx(500.0)
        assert result["avg_addon_yuan"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无套餐订单时 total_addon_yuan = None"""
        from src.api.banquet_agent import get_banquet_addon_revenue

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_addon_revenue(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["total_addon_yuan"] is None


# ── TestStaffTaskOverdueRate ──────────────────────────────────────────────────

class TestStaffTaskOverdueRate:

    @pytest.mark.asyncio
    async def test_overdue_detected(self):
        """1 task completed after due_time → overdue=1, rate=100%"""
        from src.api.banquet_agent import get_staff_task_overdue_rate

        task = _make_task(status="done", overdue=True)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_task_overdue_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["overdue_count"] == 1
        assert result["overdue_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        """无已完成任务时 overdue_rate_pct = None"""
        from src.api.banquet_agent import get_staff_task_overdue_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_task_overdue_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["overdue_rate_pct"] is None


# ── TestDepositToFinalPaymentGap ──────────────────────────────────────────────

class TestDepositToFinalPaymentGap:

    @pytest.mark.asyncio
    async def test_gap_computed(self):
        """first payment 10d ago, last payment 3d ago → gap=7d, quick=100%(≤7d)"""
        from src.api.banquet_agent import get_deposit_to_final_payment_gap

        order = _make_order(status="completed", paid_fen=300000, total_fen=300000)
        p1 = _make_payment(pid="P-001", order_id=order.id, days_ago=10)
        p2 = _make_payment(pid="P-002", order_id=order.id, days_ago=3)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([p1, p2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_deposit_to_final_payment_gap(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_gap_days"] == pytest.approx(7.0, abs=0.5)
        assert result["quick_payment_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无已完成订单时 avg_gap_days = None"""
        from src.api.banquet_agent import get_deposit_to_final_payment_gap

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_to_final_payment_gap(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_gap_days"] is None


# ── TestVipUpgradeRate ────────────────────────────────────────────────────────

class TestVipUpgradeRate:

    @pytest.mark.asyncio
    async def test_vip_counted(self):
        """1 vip_level=2, 1 vip_level=1 → vip_rate=50%, by_level len=2"""
        from src.api.banquet_agent import get_vip_upgrade_rate

        c1 = _make_customer(cid="C-001", vip_level=2)
        c2 = _make_customer(cid="C-002", vip_level=1)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c1, c2]))

        result = await get_vip_upgrade_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 2
        assert result["vip_count"] == 1
        assert result["vip_rate_pct"] == pytest.approx(50.0)
        assert len(result["by_level"]) == 2

    @pytest.mark.asyncio
    async def test_no_customers_returns_none(self):
        """无客户时 vip_rate_pct = None"""
        from src.api.banquet_agent import get_vip_upgrade_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_vip_upgrade_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["vip_rate_pct"] is None
        assert result["by_level"] == []
