"""
Banquet Agent Phase 57 — 单元测试

覆盖端点：
  - get_order_cancellation_timing
  - get_customer_source_revenue
  - get_hall_peak_utilization
  - get_lead_budget_accuracy
  - get_payment_deposit_gap
  - get_banquet_type_lead_time
  - get_staff_task_overdue_rate
  - get_review_response_rate
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


def _make_lead(lid="L-001", stage="won", source="微信", budget_fen=200000,
               customer_id="C-001", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum(stage)
    l.expected_budget_fen = budget_fen
    l.customer_id         = customer_id
    l.created_at          = created_at or datetime.utcnow() - timedelta(days=20)
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


def _make_task(tid="T-001", owner="U-001", order_id="O-001", overdue=False):
    """overdue=True → completed_at > due_time; False → completed_at <= due_time"""
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    now = datetime.utcnow()
    t.due_time         = now - timedelta(days=5)
    if overdue:
        t.completed_at = now - timedelta(days=1)   # completed after due
    else:
        t.completed_at = now - timedelta(days=7)   # completed before due
    t.created_at = now - timedelta(days=10)
    return t


def _make_review(rid="R-001", order_id="O-001", rating=5, created_at=None):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return r


# ── TestOrderCancellationTiming ───────────────────────────────────────────────

class TestOrderCancellationTiming:

    @pytest.mark.asyncio
    async def test_timing_computed(self):
        """cancelled order → distribution computed, avg_days_before returned"""
        from src.api.banquet_agent import get_order_cancellation_timing

        created_at = datetime.utcnow() - timedelta(days=60)
        banquet_dt = date.today() - timedelta(days=30)
        order = _make_order(status="cancelled", created_at=created_at,
                            banquet_date=banquet_dt)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_cancellation_timing(store_id="S001", months=12,
                                                      db=db, _=_mock_user())

        assert result["total_cancelled"] == 1
        assert result["avg_days_before"] is not None
        assert len(result["distribution"]) >= 1

    @pytest.mark.asyncio
    async def test_no_cancelled_returns_none(self):
        """无取消订单时 avg_days_before = None"""
        from src.api.banquet_agent import get_order_cancellation_timing

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_cancellation_timing(store_id="S001", months=12,
                                                      db=db, _=_mock_user())

        assert result["total_cancelled"] == 0
        assert result["avg_days_before"] is None


# ── TestCustomerSourceRevenue ─────────────────────────────────────────────────

class TestCustomerSourceRevenue:

    @pytest.mark.asyncio
    async def test_source_revenue_computed(self):
        """微信 won lead → 300000fen → top_channel=微信"""
        from src.api.banquet_agent import get_customer_source_revenue

        lead  = _make_lead(lid="L-001", stage="won", source="微信",
                           customer_id="C-001")
        order = _make_order(oid="O-001", total_fen=300000, customer_id="C-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_customer_source_revenue(store_id="S001", months=12,
                                                    db=db, _=_mock_user())

        assert result["total_won"] == 1
        assert result["top_channel"] == "微信"
        ch = next(c for c in result["by_channel"] if c["channel"] == "微信")
        assert ch["revenue_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 top_channel = None"""
        from src.api.banquet_agent import get_customer_source_revenue

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_source_revenue(store_id="S001", months=12,
                                                    db=db, _=_mock_user())

        assert result["total_won"] == 0
        assert result["top_channel"] is None


# ── TestHallPeakUtilization ───────────────────────────────────────────────────

class TestHallPeakUtilization:

    @pytest.mark.asyncio
    async def test_utilization_computed(self):
        """H-001 weekend booking → weekend_pct=100%"""
        from src.api.banquet_agent import get_hall_peak_utilization

        saturday = date.today()
        while saturday.weekday() != 5:   # 5 = Saturday
            saturday -= timedelta(days=1)
        b = _make_booking(bid="B-001", hall_id="H-001", slot_date=saturday)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b]))

        result = await get_hall_peak_utilization(store_id="S001", months=6,
                                                  db=db, _=_mock_user())

        assert result["total_bookings"] == 1
        assert result["weekend_pct"] == pytest.approx(100.0)
        assert result["halls"][0]["weekend_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 weekend_pct = None"""
        from src.api.banquet_agent import get_hall_peak_utilization

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_peak_utilization(store_id="S001", months=6,
                                                  db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["weekend_pct"] is None


# ── TestLeadBudgetAccuracy ────────────────────────────────────────────────────

class TestLeadBudgetAccuracy:

    @pytest.mark.asyncio
    async def test_accuracy_computed(self):
        """budget=200000fen, actual=200000fen → within_10pct bucket = 1"""
        from src.api.banquet_agent import get_lead_budget_accuracy

        lead  = _make_lead(lid="L-001", stage="won", budget_fen=200000,
                           customer_id="C-001")
        order = _make_order(oid="O-001", total_fen=200000, customer_id="C-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_budget_accuracy(store_id="S001", months=12,
                                                 db=db, _=_mock_user())

        assert result["total_won"] == 1
        assert result["avg_error_pct"] == pytest.approx(0.0)
        assert len(result["distribution"]) >= 1

    @pytest.mark.asyncio
    async def test_no_won_leads_returns_none(self):
        """无赢单时 avg_error_pct = None"""
        from src.api.banquet_agent import get_lead_budget_accuracy

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_budget_accuracy(store_id="S001", months=12,
                                                 db=db, _=_mock_user())

        assert result["total_won"] == 0
        assert result["avg_error_pct"] is None


# ── TestPaymentDepositGap ─────────────────────────────────────────────────────

class TestPaymentDepositGap:

    @pytest.mark.asyncio
    async def test_gap_computed(self):
        """fully-paid order with 2 payments 10d apart → avg_gap=10d"""
        from src.api.banquet_agent import get_payment_deposit_gap

        # Fully paid order (paid_fen >= total_amount_fen)
        order = _make_order(oid="O-001", total_fen=300000, paid_fen=300000)
        dt1   = datetime.utcnow() - timedelta(days=20)
        dt2   = datetime.utcnow() - timedelta(days=10)
        p1    = _make_payment(pid="P-001", order_id="O-001", created_at=dt1)
        p2    = _make_payment(pid="P-002", order_id="O-001", created_at=dt2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([p1, p2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_payment_deposit_gap(store_id="S001", months=6,
                                               db=db, _=_mock_user())

        assert result["total_fully_paid"] == 1
        assert result["avg_gap_days"] == pytest.approx(10.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_no_payments_returns_none(self):
        """无全款订单时 avg_gap_days = None"""
        from src.api.banquet_agent import get_payment_deposit_gap

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_deposit_gap(store_id="S001", months=6,
                                               db=db, _=_mock_user())

        assert result["total_fully_paid"] == 0
        assert result["avg_gap_days"] is None


# ── TestBanquetTypeLeadTime ───────────────────────────────────────────────────

class TestBanquetTypeLeadTime:

    @pytest.mark.asyncio
    async def test_lead_time_computed(self):
        """wedding: created 60d ago, banquet 10d from now → avg_lead_days > 0"""
        from src.api.banquet_agent import get_banquet_type_lead_time

        created_at = datetime.utcnow() - timedelta(days=60)
        bd         = date.today() + timedelta(days=10)
        order = _make_order(banquet_type="wedding", banquet_date=bd,
                            created_at=created_at)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_type_lead_time(store_id="S001", months=12,
                                                   db=db, _=_mock_user())

        assert result["total_orders"] == 1
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["avg_lead_days"] > 0

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 earliest_type = None"""
        from src.api.banquet_agent import get_banquet_type_lead_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_lead_time(store_id="S001", months=12,
                                                   db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["earliest_type"] is None


# ── TestStaffTaskOverdueRate ──────────────────────────────────────────────────

class TestStaffTaskOverdueRate:

    @pytest.mark.asyncio
    async def test_overdue_rate_computed(self):
        """U-001: 1 overdue / 2 tasks → overdue_pct=50%"""
        from src.api.banquet_agent import get_staff_task_overdue_rate

        t1 = _make_task(tid="T-001", owner="U-001", overdue=True)
        t2 = _make_task(tid="T-002", owner="U-001", overdue=False)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([t1, t2]))

        result = await get_staff_task_overdue_rate(store_id="S001", months=3,
                                                    db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["staff"][0]["overdue_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 highest_overdue_staff = None"""
        from src.api.banquet_agent import get_staff_task_overdue_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_task_overdue_rate(store_id="S001", months=3,
                                                    db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["highest_overdue_staff"] is None


# ── TestReviewResponseRate ─────────────────────────────────────────────────────

class TestReviewResponseRate:

    @pytest.mark.asyncio
    async def test_response_rate_computed(self):
        """1 completed order with review → review_rate_pct=100%"""
        from src.api.banquet_agent import get_review_response_rate

        order  = _make_order(oid="O-001", status="completed")
        review = _make_review(rid="R-001", order_id="O-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([review])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_review_response_rate(store_id="S001", months=12,
                                                 db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["reviewed_count"] == 1
        assert result["review_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_completed_orders_returns_none(self):
        """无已完成订单时 review_rate_pct = None"""
        from src.api.banquet_agent import get_review_response_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_review_response_rate(store_id="S001", months=12,
                                                 db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["review_rate_pct"] is None
