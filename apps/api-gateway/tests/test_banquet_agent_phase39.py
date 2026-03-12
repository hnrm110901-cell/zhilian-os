"""
Banquet Agent Phase 39 — 单元测试

覆盖端点：
  - get_banquet_profit_margin
  - get_hall_turnover_rate
  - get_lead_response_time
  - get_customer_satisfaction_score
  - get_staff_task_distribution
  - get_banquet_type_trend
  - get_payment_method_breakdown
  - get_order_size_distribution
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
                package_id=None, created_at=None, contact_name="张三"):
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
    o.contact_name     = contact_name
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


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    return b


def _make_lead(lid="L-001", days_ago=20):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = "微信"
    l.current_stage  = LeadStageEnum("new")
    l.created_at     = datetime.utcnow() - timedelta(days=days_ago)
    l.updated_at     = datetime.utcnow() - timedelta(days=5)
    return l


def _make_followup(fid="F-001", lead_id="L-001", hours_after_lead=1):
    f = MagicMock()
    f.id      = fid
    f.lead_id = lead_id
    f.created_at = datetime.utcnow() - timedelta(days=20) + timedelta(hours=hours_after_lead)
    return f


def _make_review(rid="R-001", order_id="O-001", rating=5, ai_score=90.0):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.ai_score         = ai_score
    r.improvement_tags = []
    r.created_at       = datetime.utcnow() - timedelta(days=10)
    return r


def _make_task(tid="T-001", owner="U-001", order_id="O-001", status="done"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.due_time         = datetime.utcnow() + timedelta(hours=2)
    t.completed_at     = datetime.utcnow()
    return t


def _make_package(pid="PKG-001", price_fen=25000, cost_fen=10000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    p.cost_fen            = cost_fen
    return p


def _make_payment(pid="P-001", order_id="O-001", amount_fen=30000, method="微信"):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = amount_fen
    p.payment_method   = method
    p.created_at       = datetime.utcnow() - timedelta(days=5)
    return p


# ── TestBanquetProfitMargin ───────────────────────────────────────────────────

class TestBanquetProfitMargin:

    @pytest.mark.asyncio
    async def test_margin_computed(self):
        """pkg cost=10000*10=100000fen, rev=300000 → margin=66.7%"""
        from src.api.banquet_agent import get_banquet_profit_margin

        pkg   = _make_package(cost_fen=10000)
        order = _make_order(total_fen=300000, table_count=10, package_id=pkg.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_profit_margin(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["profit_margin_pct"] == pytest.approx(66.7, rel=0.01)
        assert result["total_cost_yuan"] == pytest.approx(1000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 profit_margin_pct = None"""
        from src.api.banquet_agent import get_banquet_profit_margin

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_profit_margin(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["profit_margin_pct"] is None


# ── TestHallTurnoverRate ──────────────────────────────────────────────────────

class TestHallTurnoverRate:

    @pytest.mark.asyncio
    async def test_turnover_computed(self):
        """1 hall, 1 booking in 180 days → rate=1/180≈0.006"""
        from src.api.banquet_agent import get_hall_turnover_rate

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            return _scalars_returning([booking])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_turnover_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert len(result["halls"]) == 1
        assert result["halls"][0]["booking_count"] == 1
        assert result["overall_turnover_rate"] == pytest.approx(1/180, abs=0.002)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_turnover_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_turnover_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["overall_turnover_rate"] is None


# ── TestLeadResponseTime ──────────────────────────────────────────────────────

class TestLeadResponseTime:

    @pytest.mark.asyncio
    async def test_response_time_computed(self):
        """lead created 20d ago, followup 1h later → avg=1h, fast=100%(≤2h)"""
        from src.api.banquet_agent import get_lead_response_time

        lead    = _make_lead(days_ago=20)
        followup = _make_followup(lead_id=lead.id, hours_after_lead=1)
        followup.created_at = lead.created_at + timedelta(hours=1)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([followup])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_response_time(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["avg_response_hours"] == pytest.approx(1.0, abs=0.1)
        assert result["fast_response_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_response_hours = None"""
        from src.api.banquet_agent import get_lead_response_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_response_time(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_response_hours"] is None


# ── TestCustomerSatisfactionScore ─────────────────────────────────────────────

class TestCustomerSatisfactionScore:

    @pytest.mark.asyncio
    async def test_score_computed(self):
        """rating=5, ai_score=90 → score = 5*20*0.5 + 90*0.5 = 95.0"""
        from src.api.banquet_agent import get_customer_satisfaction_score

        review = _make_review(rating=5, ai_score=90.0)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([review]))

        result = await get_customer_satisfaction_score(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 1
        assert result["overall_score"] == pytest.approx(95.0)
        assert len(result["monthly"]) == 1

    @pytest.mark.asyncio
    async def test_no_reviews_returns_none(self):
        """无评价时 overall_score = None"""
        from src.api.banquet_agent import get_customer_satisfaction_score

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_satisfaction_score(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["overall_score"] is None
        assert result["monthly"] == []


# ── TestStaffTaskDistribution ─────────────────────────────────────────────────

class TestStaffTaskDistribution:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """U-001: 2 tasks, both done → completion=100%"""
        from src.api.banquet_agent import get_staff_task_distribution

        t1 = _make_task(tid="T-001", owner="U-001", status="done")
        t2 = _make_task(tid="T-002", owner="U-001", status="done")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([t1, t2]))

        result = await get_staff_task_distribution(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 2
        assert len(result["staff"]) == 1
        assert result["busiest_staff"] == "U-001"
        assert result["staff"][0]["completion_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 staff 为空"""
        from src.api.banquet_agent import get_staff_task_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_task_distribution(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 0
        assert result["staff"] == []
        assert result["busiest_staff"] is None


# ── TestBanquetTypeTrend ──────────────────────────────────────────────────────

class TestBanquetTypeTrend:

    @pytest.mark.asyncio
    async def test_type_grouped(self):
        """2 wedding orders → top_type=wedding, by_type len=1"""
        from src.api.banquet_agent import get_banquet_type_trend

        o1 = _make_order(oid="O-001", banquet_type="wedding")
        o2 = _make_order(oid="O-002", banquet_type="wedding")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_type_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["top_type"] == "wedding"
        assert len(result["by_type"]) == 1
        assert result["by_type"][0]["total"] == 2

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 by_type 为空"""
        from src.api.banquet_agent import get_banquet_type_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["by_type"] == []
        assert result["top_type"] is None


# ── TestPaymentMethodBreakdown ────────────────────────────────────────────────

class TestPaymentMethodBreakdown:

    @pytest.mark.asyncio
    async def test_methods_grouped(self):
        """2 微信 + 1 现金 → top=微信, 微信 pct=66.7%"""
        from src.api.banquet_agent import get_payment_method_breakdown

        p1 = _make_payment(pid="P-001", amount_fen=30000, method="微信")
        p2 = _make_payment(pid="P-002", amount_fen=30000, method="微信")
        p3 = _make_payment(pid="P-003", amount_fen=30000, method="现金")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([p1, p2, p3]))

        result = await get_payment_method_breakdown(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 3
        assert result["top_method"] == "微信"
        wx = next(m for m in result["methods"] if m["method"] == "微信")
        assert wx["count"] == 2
        assert wx["pct"] == pytest.approx(66.7, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_payments_returns_empty(self):
        """无支付记录时 methods 为空"""
        from src.api.banquet_agent import get_payment_method_breakdown

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_method_breakdown(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 0
        assert result["methods"] == []
        assert result["top_method"] is None


# ── TestOrderSizeDistribution ─────────────────────────────────────────────────

class TestOrderSizeDistribution:

    @pytest.mark.asyncio
    async def test_distribution_bucketed(self):
        """10-table order → bucket=6-10桌, avg_tables=10"""
        from src.api.banquet_agent import get_order_size_distribution

        order = _make_order(table_count=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_size_distribution(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_tables"] == pytest.approx(10.0)
        bucket = next(b for b in result["distribution"] if b["bucket"] == "6-10桌")
        assert bucket["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 distribution 为空"""
        from src.api.banquet_agent import get_order_size_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_size_distribution(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_tables"] is None
        assert result["distribution"] == []
