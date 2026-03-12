"""
Banquet Agent Phase 52 — 单元测试

覆盖端点：
  - get_lead_stage_duration
  - get_order_revenue_per_table
  - get_staff_task_completion_rate
  - get_customer_retention_trend
  - get_banquet_type_cancellation_rate
  - get_payment_installment_analysis
  - get_hall_revenue_efficiency
  - get_peak_booking_hour
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


def _make_lead(lid="L-001", stage="won", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id            = lid
    l.source_channel = "微信"
    l.current_stage  = LeadStageEnum(stage)
    l.created_at     = created_at or datetime.utcnow() - timedelta(days=20)
    return l


def _make_task(tid="T-001", owner="U-001", order_id="O-001", status="done"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.completed_at     = datetime.utcnow()
    t.due_time         = datetime.utcnow() + timedelta(hours=24)
    return t


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = "dinner"
    return b


def _make_payment(pid="P-001", order_id="O-001", amount_fen=300000, created_at=None):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.payment_method   = "微信"
    p.created_at       = created_at or datetime.utcnow() - timedelta(days=3)
    return p


# ── TestLeadStageDuration ─────────────────────────────────────────────────────

class TestLeadStageDuration:

    @pytest.mark.asyncio
    async def test_duration_computed(self):
        """1 won lead created 30d ago → avg_days_to_close≈30"""
        from src.api.banquet_agent import get_lead_stage_duration

        lead = _make_lead(lid="L-001", stage="won",
                          created_at=datetime.utcnow() - timedelta(days=30))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_stage_duration(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["avg_days_to_close"] is not None
        assert result["avg_days_to_close"] > 0

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_days_to_close = None"""
        from src.api.banquet_agent import get_lead_stage_duration

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_stage_duration(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_days_to_close"] is None


# ── TestOrderRevenuePerTable ──────────────────────────────────────────────────

class TestOrderRevenuePerTable:

    @pytest.mark.asyncio
    async def test_revenue_per_table_computed(self):
        """300000fen / 10 tables = 3000yuan/table"""
        from src.api.banquet_agent import get_order_revenue_per_table

        order = _make_order(total_fen=300000, table_count=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["overall_rev_per_table_yuan"] == pytest.approx(300.0)
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["rev_per_table_yuan"] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_rev_per_table_yuan = None"""
        from src.api.banquet_agent import get_order_revenue_per_table

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_rev_per_table_yuan"] is None


# ── TestStaffTaskCompletionRate ───────────────────────────────────────────────

class TestStaffTaskCompletionRate:

    @pytest.mark.asyncio
    async def test_completion_computed(self):
        """U-001: 2 done tasks → completion_pct=100%"""
        from src.api.banquet_agent import get_staff_task_completion_rate

        t1 = _make_task(tid="T-001", owner="U-001", status="done")
        t2 = _make_task(tid="T-002", owner="U-001", status="done")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([t1, t2]))

        result = await get_staff_task_completion_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["top_performer"] == "U-001"
        assert result["staff"][0]["completion_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 top_performer = None"""
        from src.api.banquet_agent import get_staff_task_completion_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_task_completion_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["top_performer"] is None


# ── TestCustomerRetentionTrend ────────────────────────────────────────────────

class TestCustomerRetentionTrend:

    @pytest.mark.asyncio
    async def test_retention_computed(self):
        """C-001 has 2 orders (first + returning) → retention_rate > 0"""
        from src.api.banquet_agent import get_customer_retention_trend

        now = datetime.utcnow()
        o1 = _make_order(oid="O-001", customer_id="C-001",
                         created_at=now - timedelta(days=60))
        o2 = _make_order(oid="O-002", customer_id="C-001",
                         created_at=now - timedelta(days=10))
        o3 = _make_order(oid="O-003", customer_id="C-002",
                         created_at=now - timedelta(days=20))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2, o3]))

        result = await get_customer_retention_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 3
        assert result["retention_rate_pct"] is not None
        assert result["retention_rate_pct"] > 0
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 retention_rate_pct = None"""
        from src.api.banquet_agent import get_customer_retention_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_retention_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["retention_rate_pct"] is None


# ── TestBanquetTypeCancellationRate ───────────────────────────────────────────

class TestBanquetTypeCancellationRate:

    @pytest.mark.asyncio
    async def test_cancellation_computed(self):
        """1 cancelled + 1 confirmed wedding → cancellation_rate=50%"""
        from src.api.banquet_agent import get_banquet_type_cancellation_rate

        o1 = _make_order(oid="O-001", banquet_type="wedding", status="cancelled")
        o2 = _make_order(oid="O-002", banquet_type="wedding", status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_type_cancellation_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["overall_cancellation_pct"] == pytest.approx(50.0)
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["cancellation_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_cancellation_pct = None"""
        from src.api.banquet_agent import get_banquet_type_cancellation_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_cancellation_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_cancellation_pct"] is None


# ── TestPaymentInstallmentAnalysis ────────────────────────────────────────────

class TestPaymentInstallmentAnalysis:

    @pytest.mark.asyncio
    async def test_installments_computed(self):
        """1 fully-paid order with 1 payment → 1次 group"""
        from src.api.banquet_agent import get_payment_installment_analysis

        order   = _make_order(total_fen=300000, paid_fen=300000)
        payment = _make_payment(order_id=order.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([payment])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_payment_installment_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 1
        assert result["avg_installments"] is not None
        g = next(g for g in result["installment_groups"] if g["installments"] == "1次")
        assert g["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无全额付款订单时 avg_installments = None"""
        from src.api.banquet_agent import get_payment_installment_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_installment_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 0
        assert result["avg_installments"] is None


# ── TestHallRevenueEfficiency ─────────────────────────────────────────────────

class TestHallRevenueEfficiency:

    @pytest.mark.asyncio
    async def test_efficiency_computed(self):
        """H-001 1 booking × 300000fen → rev_per_booking=3000yuan"""
        from src.api.banquet_agent import get_hall_revenue_efficiency

        booking = _make_booking(bid="B-001", hall_id="H-001", order_id="O-001")
        order   = _make_order(oid="O-001", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_revenue_efficiency(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 1
        assert result["top_hall"] == "H-001"
        h = result["halls"][0]
        assert h["rev_per_booking_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_empty(self):
        """无预订时 top_hall = None"""
        from src.api.banquet_agent import get_hall_revenue_efficiency

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_efficiency(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["top_hall"] is None


# ── TestPeakBookingHour ───────────────────────────────────────────────────────

class TestPeakBookingHour:

    @pytest.mark.asyncio
    async def test_peak_hour_found(self):
        """3 orders created at 14:xx → peak_hour=14"""
        from src.api.banquet_agent import get_peak_booking_hour

        now = datetime.utcnow().replace(hour=14, minute=0, second=0, microsecond=0)
        o1 = _make_order(oid="O-001", created_at=now - timedelta(days=5))
        o2 = _make_order(oid="O-002", created_at=now - timedelta(days=10))
        o3 = _make_order(oid="O-003", created_at=now - timedelta(days=15))
        # set hour explicitly
        for o in (o1, o2, o3):
            o.created_at = o.created_at.replace(hour=14)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2, o3]))

        result = await get_peak_booking_hour(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_orders"] == 3
        assert result["peak_hour"] == 14
        assert any(b["hour"] == 14 for b in result["by_hour"])

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 peak_hour = None"""
        from src.api.banquet_agent import get_peak_booking_hour

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_peak_booking_hour(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["peak_hour"] is None
