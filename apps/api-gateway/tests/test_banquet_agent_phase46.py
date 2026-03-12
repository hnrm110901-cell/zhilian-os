"""
Banquet Agent Phase 46 — 单元测试

覆盖端点：
  - get_banquet_advance_booking_rate
  - get_hall_multi_event_day_rate
  - get_lead_lost_reason_analysis
  - get_vip_reorder_interval
  - get_banquet_menu_cost_ratio
  - get_staff_cross_type_experience
  - get_payment_delay_analysis
  - get_order_cancellation_by_type
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


def _make_booking(bid="B-001", hall_id="H-001", slot_date=None, slot_name="dinner"):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = slot_name
    b.banquet_order_id = "O-001"
    return b


def _make_lead(lid="L-001", stage="lost", source="微信"):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = source
    l.current_stage  = LeadStageEnum(stage)
    l.created_at     = datetime.utcnow() - timedelta(days=20)
    l.updated_at     = datetime.utcnow() - timedelta(days=5)
    return l


def _make_customer(cid="C-001", vip_level=2):
    c = MagicMock()
    c.id        = cid
    c.vip_level = vip_level
    c.created_at = datetime.utcnow() - timedelta(days=365)
    return c


def _make_package(pid="PKG-001", price_fen=25000, cost_fen=12000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    p.cost_fen            = cost_fen
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


def _make_payment(pid="P-001", order_id="O-001", amount_fen=30000, method="微信",
                  created_at=None):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.payment_method   = method
    p.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return p


# ── TestBanquetAdvanceBookingRate ─────────────────────────────────────────────

class TestBanquetAdvanceBookingRate:

    @pytest.mark.asyncio
    async def test_advance_rate_computed(self):
        """banquet_date 60 days ahead of created_at → 30-90d bucket"""
        from src.api.banquet_agent import get_banquet_advance_booking_rate

        created = datetime.utcnow() - timedelta(days=90)
        banquet_d = date.today() - timedelta(days=30)   # 60 days after created
        order = _make_order(banquet_date=banquet_d, created_at=created)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_advance_booking_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_advance_days"] is not None
        # 60 days advance → falls in 31-90 bucket
        bucket_30_90 = next((b for b in result["distribution"] if "31" in b["bucket"]), None)
        assert bucket_30_90 is not None
        assert bucket_30_90["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_advance_days = None"""
        from src.api.banquet_agent import get_banquet_advance_booking_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_advance_booking_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_advance_days"] is None


# ── TestHallMultiEventDayRate ─────────────────────────────────────────────────

class TestHallMultiEventDayRate:

    @pytest.mark.asyncio
    async def test_multi_event_detected(self):
        """同厅同日不同时段2条booking → multi_event_days=1"""
        from src.api.banquet_agent import get_hall_multi_event_day_rate

        slot_d = date.today() - timedelta(days=5)
        b1 = _make_booking(bid="B-001", hall_id="H-001", slot_date=slot_d, slot_name="lunch")
        b2 = _make_booking(bid="B-002", hall_id="H-001", slot_date=slot_d, slot_name="dinner")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2]))

        result = await get_hall_multi_event_day_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_booking_days"] >= 1
        assert result["multi_event_days"] >= 1

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 multi_event_rate_pct = None"""
        from src.api.banquet_agent import get_hall_multi_event_day_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_multi_event_day_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_booking_days"] == 0
        assert result["multi_event_rate_pct"] is None


# ── TestLeadLostReasonAnalysis ────────────────────────────────────────────────

class TestLeadLostReasonAnalysis:

    @pytest.mark.asyncio
    async def test_lost_by_channel(self):
        """2 微信 lost + 1 抖音 lost → top_lost_channel=微信"""
        from src.api.banquet_agent import get_lead_lost_reason_analysis

        l1 = _make_lead(lid="L-001", stage="lost", source="微信")
        l2 = _make_lead(lid="L-002", stage="lost", source="微信")
        l3 = _make_lead(lid="L-003", stage="lost", source="抖音")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2, l3]))

        result = await get_lead_lost_reason_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_lost"] == 3
        assert result["highest_loss_channel"] == "微信"
        wx = next(c for c in result["by_channel"] if c["channel"] == "微信")
        assert wx["count"] == 2

    @pytest.mark.asyncio
    async def test_no_lost_leads_returns_none(self):
        """无丢失线索时 highest_loss_channel = None"""
        from src.api.banquet_agent import get_lead_lost_reason_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_lost_reason_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_lost"] == 0
        assert result["highest_loss_channel"] is None


# ── TestVipReorderInterval ─────────────────────────────────────────────────────

class TestVipReorderInterval:

    @pytest.mark.asyncio
    async def test_interval_computed(self):
        """VIP C-001 two orders 30 days apart → avg_interval=30"""
        from src.api.banquet_agent import get_vip_reorder_interval

        vip = _make_customer(cid="C-001", vip_level=2)
        d1  = date.today() - timedelta(days=60)
        d2  = date.today() - timedelta(days=30)
        o1  = _make_order(oid="O-001", customer_id="C-001", banquet_date=d1)
        o2  = _make_order(oid="O-002", customer_id="C-001", banquet_date=d2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([vip])
            return _scalars_returning([o1, o2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_reorder_interval(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_vip"] == 1
        assert result["avg_interval_days"] == pytest.approx(30.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_no_vip_returns_none(self):
        """无VIP客户时 avg_interval_days = None"""
        from src.api.banquet_agent import get_vip_reorder_interval

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_vip_reorder_interval(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_vip"] == 0
        assert result["avg_interval_days"] is None


# ── TestBanquetMenuCostRatio ──────────────────────────────────────────────────

class TestBanquetMenuCostRatio:

    @pytest.mark.asyncio
    async def test_cost_ratio_computed(self):
        """pkg cost=12000, tables=10 → cost=120000fen; total=300000fen → ratio=40%"""
        from src.api.banquet_agent import get_banquet_menu_cost_ratio

        pkg   = _make_package(price_fen=25000, cost_fen=12000)
        order = _make_order(total_fen=300000, table_count=10, package_id=pkg.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_menu_cost_ratio(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 1
        assert result["avg_cost_ratio_pct"] == pytest.approx(40.0, rel=0.05)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无套餐订单时 avg_cost_ratio_pct = None"""
        from src.api.banquet_agent import get_banquet_menu_cost_ratio

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_menu_cost_ratio(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["avg_cost_ratio_pct"] is None


# ── TestStaffCrossTypeExperience ──────────────────────────────────────────────

class TestStaffCrossTypeExperience:

    @pytest.mark.asyncio
    async def test_cross_type_computed(self):
        """U-001 tasks on 2 orders (wedding + birthday) → unique_types=2"""
        from src.api.banquet_agent import get_staff_cross_type_experience

        t1 = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        t2 = _make_task(tid="T-002", owner="U-001", order_id="O-002")
        o1 = _make_order(oid="O-001", banquet_type="wedding")
        o2 = _make_order(oid="O-002", banquet_type="birthday")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([t1, t2])
            if call_n[0] == 2: return _scalars_returning([o1])
            return _scalars_returning([o2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_cross_type_experience(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        s = result["staff"][0]
        assert s["type_count"] == 2

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 staff 为空"""
        from src.api.banquet_agent import get_staff_cross_type_experience

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_cross_type_experience(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["staff"] == []
        assert result["most_versatile"] is None


# ── TestPaymentDelayAnalysis ──────────────────────────────────────────────────

class TestPaymentDelayAnalysis:

    @pytest.mark.asyncio
    async def test_delay_computed(self):
        """order created 10 days ago, payment 5 days ago → delay=5d"""
        from src.api.banquet_agent import get_payment_delay_analysis

        order_created = datetime.utcnow() - timedelta(days=10)
        pay_created   = datetime.utcnow() - timedelta(days=5)
        order   = _make_order(created_at=order_created)
        payment = _make_payment(order_id=order.id, created_at=pay_created)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([payment])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_payment_delay_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_delay_days"] == pytest.approx(5.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_delay_days = None"""
        from src.api.banquet_agent import get_payment_delay_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_delay_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_delay_days"] is None


# ── TestOrderCancellationByType ───────────────────────────────────────────────

class TestOrderCancellationByType:

    @pytest.mark.asyncio
    async def test_cancel_by_type(self):
        """1 wedding cancelled + 1 wedding confirmed → wedding_cancel_rate=50%"""
        from src.api.banquet_agent import get_order_cancellation_by_type

        o1 = _make_order(oid="O-001", banquet_type="wedding", status="cancelled")
        o2 = _make_order(oid="O-002", banquet_type="wedding", status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_order_cancellation_by_type(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["cancel_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_cancel_rate_pct = None"""
        from src.api.banquet_agent import get_order_cancellation_by_type

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_cancellation_by_type(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_cancel_rate_pct"] is None
