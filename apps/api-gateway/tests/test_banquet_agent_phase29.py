"""
Banquet Agent Phase 29 — 单元测试

覆盖端点：
  - get_repeat_customer_rate
  - get_hall_revenue_rank
  - get_staff_performance_score
  - get_lead_source_roi
  - get_banquet_type_trend
  - get_payment_collection_rate
  - get_advance_booking_lead_time
  - get_event_cost_breakdown
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


def _make_task(tid="T-001", owner="U-001", status="done"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id            = tid
    t.owner_user_id = owner
    t.task_status   = TaskStatusEnum(status)
    t.created_at    = datetime.utcnow() - timedelta(days=10)
    return t


def _make_exception(eid="E-001", owner="U-001", status="resolved"):
    e = MagicMock()
    e.id            = eid
    e.owner_user_id = owner
    e.status        = status
    e.created_at    = datetime.utcnow() - timedelta(days=5)
    return e


def _make_lead(lid="L-001", stage="signed", source="微信",
               budget_fen=200000):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum(stage) if stage in [e.value for e in LeadStageEnum] else MagicMock(value=stage)
    l.expected_budget_fen = budget_fen
    l.created_at          = datetime.utcnow() - timedelta(days=20)
    return l


def _make_package(pid="P-001", cost_fen=20000):
    p = MagicMock()
    p.id       = pid
    p.cost_fen = cost_fen
    return p


# ── TestRepeatCustomerRate ────────────────────────────────────────────────────

class TestRepeatCustomerRate:

    @pytest.mark.asyncio
    async def test_repeat_rate_computed(self):
        """2 orders same customer → repeat_customers=1, repeat_rate=100%"""
        from src.api.banquet_agent import get_repeat_customer_rate

        o1 = _make_order(oid="O-001", customer_id="C-001", total_fen=300000)
        o2 = _make_order(oid="O-002", customer_id="C-001", total_fen=200000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_repeat_customer_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["repeat_customers"] == 1
        assert result["repeat_rate_pct"] == pytest.approx(100.0)
        assert result["repeat_customer_revenue_yuan"] == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none_rate(self):
        """无订单时 repeat_rate_pct = None"""
        from src.api.banquet_agent import get_repeat_customer_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_repeat_customer_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["repeat_rate_pct"] is None


# ── TestHallRevenueRank ───────────────────────────────────────────────────────

class TestHallRevenueRank:

    @pytest.mark.asyncio
    async def test_hall_ranked_by_revenue(self):
        """1厅 + 1预订 + 1订单 → halls 长度1, total_revenue_yuan 正确"""
        from src.api.banquet_agent import get_hall_revenue_rank

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(oid="O-001", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])   # halls
            if call_n[0] == 2: return _scalars_returning([booking]) # bookings
            return _scalars_returning([order])                       # order

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_revenue_rank(store_id="S001", months=6, db=db, _=_mock_user())

        assert len(result["halls"]) == 1
        assert result["halls"][0]["bookings"] == 1
        assert result["halls"][0]["total_revenue_yuan"] == pytest.approx(3000.0)
        assert result["top_hall_id"] == hall.id

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_revenue_rank

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_rank(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["top_hall_id"] is None


# ── TestStaffPerformanceScore ─────────────────────────────────────────────────

class TestStaffPerformanceScore:

    @pytest.mark.asyncio
    async def test_score_computed(self):
        """1 done task + 1 resolved exception → composite_score = 100"""
        from src.api.banquet_agent import get_staff_performance_score

        task = _make_task(owner="U-001", status="done")
        exc  = _make_exception(owner="U-001", status="resolved")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([task])
            return _scalars_returning([exc])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_performance_score(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["scores"][0]["composite_score"] == pytest.approx(100.0)
        assert result["top_performer_id"] == "U-001"

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务无异常时 total_staff = 0"""
        from src.api.banquet_agent import get_staff_performance_score

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_performance_score(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["scores"] == []
        assert result["top_performer_id"] is None


# ── TestLeadSourceRoi ─────────────────────────────────────────────────────────

class TestLeadSourceRoi:

    @pytest.mark.asyncio
    async def test_source_conversion_computed(self):
        """1 signed 微信 lead → 微信 conversion=100%, won=1"""
        from src.api.banquet_agent import get_lead_source_roi

        lead = _make_lead(stage="signed", source="微信", budget_fen=200000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_source_roi(store_id="S001", months=6, db=db, _=_mock_user())

        assert len(result["sources"]) == 1
        s = result["sources"][0]
        assert s["source"] == "微信"
        assert s["won_count"] == 1
        assert s["conversion_rate_pct"] == pytest.approx(100.0)
        assert result["best_source"] == "微信"

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 sources 为空"""
        from src.api.banquet_agent import get_lead_source_roi

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_source_roi(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["sources"] == []
        assert result["best_source"] is None


# ── TestBanquetTypeTrend ──────────────────────────────────────────────────────

class TestBanquetTypeTrend:

    @pytest.mark.asyncio
    async def test_dominant_type_identified(self):
        """2 wedding orders → dominant_type='wedding'"""
        from src.api.banquet_agent import get_banquet_type_trend

        o1 = _make_order(oid="O-001", banquet_type="wedding", total_fen=300000)
        o2 = _make_order(oid="O-002", banquet_type="birthday", total_fen=200000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o1]))

        result = await get_banquet_type_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["dominant_type"] == "wedding"

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 types 为空"""
        from src.api.banquet_agent import get_banquet_type_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["types"] == []
        assert result["dominant_type"] is None


# ── TestPaymentCollectionRate ─────────────────────────────────────────────────

class TestPaymentCollectionRate:

    @pytest.mark.asyncio
    async def test_collection_rate_computed(self):
        """paid=150000 / total=300000 → rate=50%, outstanding order 1"""
        from src.api.banquet_agent import get_payment_collection_rate

        o = _make_order(total_fen=300000, paid_fen=150000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_payment_collection_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["collection_rate_pct"] == pytest.approx(50.0)
        assert result["total_receivable_yuan"] == pytest.approx(3000.0)
        assert result["total_collected_yuan"] == pytest.approx(1500.0)
        assert result["overdue_count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none_rate(self):
        """无订单时 collection_rate_pct = None"""
        from src.api.banquet_agent import get_payment_collection_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_collection_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["collection_rate_pct"] is None
        assert result["overdue_orders"] == []


# ── TestAdvanceBookingLeadTime ────────────────────────────────────────────────

class TestAdvanceBookingLeadTime:

    @pytest.mark.asyncio
    async def test_lead_days_computed(self):
        """banquet_date = today+45, created_at = today-15 → 60天 → 31-60天桶"""
        from src.api.banquet_agent import get_advance_booking_lead_time

        o = _make_order(
            banquet_date=date.today() + timedelta(days=45),
            created_at=datetime.utcnow() - timedelta(days=15),
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_advance_booking_lead_time(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_lead_days"] is not None
        bucket_31_60 = next(b for b in result["buckets"] if b["bucket"] == "31-60天")
        assert bucket_31_60["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_lead_days = None"""
        from src.api.banquet_agent import get_advance_booking_lead_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_advance_booking_lead_time(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_lead_days"] is None
        assert result["buckets"] == []
