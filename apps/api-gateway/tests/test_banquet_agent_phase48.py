"""
Banquet Agent Phase 48 — 单元测试

覆盖端点：
  - get_deposit_ratio_by_type
  - get_hall_booking_frequency
  - get_lead_budget_vs_actual
  - get_high_value_order_threshold
  - get_customer_age_segments
  - get_deposit_collection_rate
  - get_staff_tasks_per_order
  - get_referral_lead_rate
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


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = "dinner"
    return b


def _make_lead(lid="L-001", stage="won", source="微信", budget_fen=200000,
               customer_id=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum(stage)
    l.expected_budget_fen = budget_fen
    l.customer_id         = customer_id
    l.created_at          = datetime.utcnow() - timedelta(days=20)
    l.updated_at          = datetime.utcnow() - timedelta(days=5)
    return l


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.completed_at     = datetime.utcnow()
    t.due_time         = datetime.utcnow() + timedelta(hours=24)
    return t


# ── TestDepositRatioByType ────────────────────────────────────────────────────

class TestDepositRatioByType:

    @pytest.mark.asyncio
    async def test_deposit_ratio_computed(self):
        """wedding: paid=150000, total=300000 → ratio=50%"""
        from src.api.banquet_agent import get_deposit_ratio_by_type

        order = _make_order(banquet_type="wedding", total_fen=300000, paid_fen=150000)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_deposit_ratio_by_type(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["overall_deposit_ratio_pct"] == pytest.approx(50.0)
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["deposit_ratio_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_deposit_ratio_pct = None"""
        from src.api.banquet_agent import get_deposit_ratio_by_type

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_ratio_by_type(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_deposit_ratio_pct"] is None


# ── TestHallBookingFrequency ──────────────────────────────────────────────────

class TestHallBookingFrequency:

    @pytest.mark.asyncio
    async def test_frequency_computed(self):
        """H-001 booked 3 times in 6 months → avg_per_month=0.5"""
        from src.api.banquet_agent import get_hall_booking_frequency

        b1 = _make_booking(bid="B-001", hall_id="H-001")
        b2 = _make_booking(bid="B-002", hall_id="H-001")
        b3 = _make_booking(bid="B-003", hall_id="H-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2, b3]))

        result = await get_hall_booking_frequency(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 3
        assert result["busiest_hall"] == "H-001"
        h = result["halls"][0]
        assert h["total_bookings"] == 3
        assert h["avg_per_month"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_empty(self):
        """无预订时 busiest_hall = None"""
        from src.api.banquet_agent import get_hall_booking_frequency

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_booking_frequency(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["busiest_hall"] is None


# ── TestLeadBudgetVsActual ────────────────────────────────────────────────────

class TestLeadBudgetVsActual:

    @pytest.mark.asyncio
    async def test_accuracy_computed(self):
        """won lead budget=200000fen; order actual=200000fen → accuracy=100%"""
        from src.api.banquet_agent import get_lead_budget_vs_actual

        lead  = _make_lead(lid="L-001", stage="won", budget_fen=200000, customer_id="C-001")
        order = _make_order(oid="O-001", total_fen=200000, customer_id="C-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_budget_vs_actual(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_won"] == 1
        assert result["accuracy_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_won_leads_returns_none(self):
        """无 won 线索时 accuracy_pct = None"""
        from src.api.banquet_agent import get_lead_budget_vs_actual

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_budget_vs_actual(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_won"] == 0
        assert result["accuracy_pct"] is None


# ── TestHighValueOrderThreshold ───────────────────────────────────────────────

class TestHighValueOrderThreshold:

    @pytest.mark.asyncio
    async def test_threshold_computed(self):
        """5 orders; top 20% (1 order) = 500000fen → threshold=5000yuan"""
        from src.api.banquet_agent import get_high_value_order_threshold

        orders = [
            _make_order(oid=f"O-{i}", total_fen=v)
            for i, v in enumerate([500000, 300000, 200000, 150000, 100000])
        ]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning(orders))

        result = await get_high_value_order_threshold(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 5
        assert result["top20_threshold_yuan"] == pytest.approx(5000.0)
        assert result["top20_revenue_pct"] > 30.0  # 500000/1250000 = 40%

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 top20_threshold_yuan = None"""
        from src.api.banquet_agent import get_high_value_order_threshold

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_high_value_order_threshold(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["top20_threshold_yuan"] is None


# ── TestCustomerAgeSegments ───────────────────────────────────────────────────

class TestCustomerAgeSegments:

    @pytest.mark.asyncio
    async def test_segments_computed(self):
        """order 30 days ago → 新客户; order 400 days ago → 老客户"""
        from src.api.banquet_agent import get_customer_age_segments

        new_date = date.today() - timedelta(days=30)
        old_date = date.today() - timedelta(days=400)
        o1 = _make_order(oid="O-001", customer_id="C-NEW", banquet_date=new_date)
        o2 = _make_order(oid="O-002", customer_id="C-OLD", banquet_date=old_date)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_age_segments(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 2
        seg_names = [s["segment"] for s in result["segments"]]
        assert any("新客户" in s for s in seg_names)
        assert any("老客户" in s for s in seg_names)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 segments 为空"""
        from src.api.banquet_agent import get_customer_age_segments

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_age_segments(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["segments"] == []


# ── TestDepositCollectionRate ─────────────────────────────────────────────────

class TestDepositCollectionRate:

    @pytest.mark.asyncio
    async def test_collection_rate_computed(self):
        """1 confirmed with deposit + 1 without → collection_rate=50%"""
        from src.api.banquet_agent import get_deposit_collection_rate

        o1 = _make_order(oid="O-001", status="confirmed", paid_fen=50000)
        o2 = _make_order(oid="O-002", status="confirmed", paid_fen=0)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_deposit_collection_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_confirmed"] == 2
        assert result["with_deposit"] == 1
        assert result["deposit_collection_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无已确认订单时 deposit_collection_rate_pct = None"""
        from src.api.banquet_agent import get_deposit_collection_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_collection_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_confirmed"] == 0
        assert result["deposit_collection_rate_pct"] is None


# ── TestStaffTasksPerOrder ────────────────────────────────────────────────────

class TestStaffTasksPerOrder:

    @pytest.mark.asyncio
    async def test_tasks_per_order_computed(self):
        """U-001 has 2 tasks on same order → tasks_per_order=2"""
        from src.api.banquet_agent import get_staff_tasks_per_order

        t1 = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        t2 = _make_task(tid="T-002", owner="U-001", order_id="O-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([t1, t2]))

        result = await get_staff_tasks_per_order(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        s = result["staff"][0]
        assert s["task_count"] == 2
        assert s["tasks_per_order"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 avg_tasks_per_order = None"""
        from src.api.banquet_agent import get_staff_tasks_per_order

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_tasks_per_order(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["avg_tasks_per_order"] is None


# ── TestReferralLeadRate ──────────────────────────────────────────────────────

class TestReferralLeadRate:

    @pytest.mark.asyncio
    async def test_referral_rate_computed(self):
        """1 转介绍 won + 1 微信 → referral_rate=50%, win_rate=100%"""
        from src.api.banquet_agent import get_referral_lead_rate

        l1 = _make_lead(lid="L-001", stage="won",  source="转介绍")
        l2 = _make_lead(lid="L-002", stage="lost", source="微信")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_referral_lead_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["referral_count"] == 1
        assert result["referral_rate_pct"] == pytest.approx(50.0)
        assert result["referral_win_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 referral_rate_pct = None"""
        from src.api.banquet_agent import get_referral_lead_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_referral_lead_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["referral_rate_pct"] is None
