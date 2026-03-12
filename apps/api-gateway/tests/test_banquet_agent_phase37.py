"""
Banquet Agent Phase 37 — 单元测试

覆盖端点：
  - get_banquet_revenue_per_table
  - get_lead_source_volume
  - get_task_completion_speed
  - get_hall_slot_popularity
  - get_customer_average_spend
  - get_monthly_order_growth
  - get_deposit_collection_speed
  - get_review_sentiment_breakdown
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
                deposit_fen=30000, table_count=10, people_count=100,
                banquet_type="wedding", banquet_date=None,
                status="confirmed", customer_id="C-001",
                package_id=None, created_at=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.deposit_fen      = deposit_fen
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


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_name="dinner", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_name        = slot_name
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    return b


def _make_lead(lid="L-001", source="微信", budget_fen=200000):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum("won")
    l.expected_budget_fen = budget_fen
    l.created_at = datetime.utcnow() - timedelta(days=20)
    l.updated_at = datetime.utcnow() - timedelta(days=5)
    return l


def _make_task(tid="T-001", owner="U-001", order_id="O-001",
               hours_to_complete=12):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(hours=hours_to_complete)
    t.due_time         = datetime.utcnow() + timedelta(hours=2)
    t.completed_at     = datetime.utcnow()
    return t


def _make_payment(pid="P-001", order_id="O-001", days_after_order=2):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = 30000
    p.created_at       = datetime.utcnow() - timedelta(days=58) + timedelta(days=days_after_order)
    return p


def _make_review(rid="R-001", order_id="O-001", rating=5, ai_score=90.0,
                 improvement_tags=None):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.ai_score         = ai_score
    r.improvement_tags = improvement_tags or []
    r.created_at       = datetime.utcnow() - timedelta(days=10)
    return r


# ── TestBanquetRevenuePerTable ────────────────────────────────────────────────

class TestBanquetRevenuePerTable:

    @pytest.mark.asyncio
    async def test_rev_per_table_computed(self):
        """300000fen / 10 tables = 300元/桌"""
        from src.api.banquet_agent import get_banquet_revenue_per_table

        order = _make_order(total_fen=300000, table_count=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["overall_rev_per_table"] == pytest.approx(300.0)
        assert len(result["by_type"]) == 1
        assert result["by_type"][0]["rev_per_table_yuan"] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_rev_per_table = None"""
        from src.api.banquet_agent import get_banquet_revenue_per_table

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_rev_per_table"] is None


# ── TestLeadSourceVolume ──────────────────────────────────────────────────────

class TestLeadSourceVolume:

    @pytest.mark.asyncio
    async def test_source_grouped(self):
        """2 微信 + 1 转介绍 → top_source=微信, 微信pct=66.7%"""
        from src.api.banquet_agent import get_lead_source_volume

        l1 = _make_lead(lid="L-001", source="微信", budget_fen=200000)
        l2 = _make_lead(lid="L-002", source="微信", budget_fen=300000)
        l3 = _make_lead(lid="L-003", source="转介绍", budget_fen=400000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2, l3]))

        result = await get_lead_source_volume(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 3
        assert result["top_source"] == "微信"
        wx = next(s for s in result["sources"] if s["channel"] == "微信")
        assert wx["count"] == 2
        assert wx["avg_budget_yuan"] == pytest.approx(2500.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 sources 为空"""
        from src.api.banquet_agent import get_lead_source_volume

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_source_volume(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["sources"] == []
        assert result["top_source"] is None


# ── TestTaskCompletionSpeed ───────────────────────────────────────────────────

class TestTaskCompletionSpeed:

    @pytest.mark.asyncio
    async def test_avg_hours_computed(self):
        """task created 12h ago, completed now → avg=12h, fast=100%(≤24h)"""
        from src.api.banquet_agent import get_task_completion_speed

        task = _make_task(hours_to_complete=12)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_task_completion_speed(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["avg_hours"] == pytest.approx(12.0, rel=0.05)
        assert result["fast_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        """无已完成任务时 avg_hours = None"""
        from src.api.banquet_agent import get_task_completion_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_task_completion_speed(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["avg_hours"] is None


# ── TestHallSlotPopularity ────────────────────────────────────────────────────

class TestHallSlotPopularity:

    @pytest.mark.asyncio
    async def test_slot_counted(self):
        """1 dinner booking → overall_peak_slot=dinner"""
        from src.api.banquet_agent import get_hall_slot_popularity

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id, slot_name="dinner")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            return _scalars_returning([booking])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_slot_popularity(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["overall_peak_slot"] == "dinner"
        assert result["overall_slot_counts"]["dinner"] == 1

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_slot_popularity

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_slot_popularity(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["halls"] == []


# ── TestCustomerAverageSpend ──────────────────────────────────────────────────

class TestCustomerAverageSpend:

    @pytest.mark.asyncio
    async def test_avg_spend_computed(self):
        """300000fen / 100 people = 30元/人; / 10 tables = 300元/桌"""
        from src.api.banquet_agent import get_customer_average_spend

        order = _make_order(total_fen=300000, table_count=10, people_count=100)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_customer_average_spend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_spend_per_person_yuan"] == pytest.approx(30.0)
        assert result["avg_spend_per_table_yuan"] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_spend_per_person_yuan = None"""
        from src.api.banquet_agent import get_customer_average_spend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_average_spend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_spend_per_person_yuan"] is None


# ── TestMonthlyOrderGrowth ────────────────────────────────────────────────────

class TestMonthlyOrderGrowth:

    @pytest.mark.asyncio
    async def test_growth_computed(self):
        """2 orders same month → monthly has 1 entry, no mom_growth for first"""
        from src.api.banquet_agent import get_monthly_order_growth

        now = datetime.utcnow()
        o1 = _make_order(oid="O-001", created_at=now - timedelta(days=10))
        o2 = _make_order(oid="O-002", created_at=now - timedelta(days=5))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_monthly_order_growth(store_id="S001", months=12, db=db, _=_mock_user())

        assert len(result["monthly"]) >= 1
        assert result["monthly"][0]["order_count"] >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 monthly 为空"""
        from src.api.banquet_agent import get_monthly_order_growth

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_monthly_order_growth(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["monthly"] == []
        assert result["avg_growth_pct"] is None


# ── TestDepositCollectionSpeed ────────────────────────────────────────────────

class TestDepositCollectionSpeed:

    @pytest.mark.asyncio
    async def test_avg_days_computed(self):
        """order created 60 days ago, first payment 2 days later → avg=2 days"""
        from src.api.banquet_agent import get_deposit_collection_speed

        order   = _make_order(created_at=datetime.utcnow() - timedelta(days=60))
        payment = _make_payment(order_id=order.id, days_after_order=2)
        # payment.created_at = order.created_at + 2 days
        payment.created_at = order.created_at + timedelta(days=2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([payment])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_deposit_collection_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["paid_orders"] == 1
        assert result["avg_days_to_first_payment"] == pytest.approx(2.0, abs=0.1)
        assert result["fast_collection_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_days_to_first_payment = None"""
        from src.api.banquet_agent import get_deposit_collection_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_collection_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_days_to_first_payment"] is None


# ── TestReviewSentimentBreakdown ──────────────────────────────────────────────

class TestReviewSentimentBreakdown:

    @pytest.mark.asyncio
    async def test_sentiment_bucketed(self):
        """2 positive(5★) + 1 negative(1★) → positive_pct=66.7%, top_tag from neg"""
        from src.api.banquet_agent import get_review_sentiment_breakdown

        r1 = _make_review(rid="R-001", rating=5, improvement_tags=[])
        r2 = _make_review(rid="R-002", rating=5, improvement_tags=[])
        r3 = _make_review(rid="R-003", rating=1, improvement_tags=["延误", "菜量不足"])

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([r1, r2, r3]))

        result = await get_review_sentiment_breakdown(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 3
        assert result["positive_pct"] == pytest.approx(66.7, rel=0.01)
        assert result["negative_pct"] == pytest.approx(33.3, rel=0.01)
        assert len(result["top_improvement_tags"]) == 2

    @pytest.mark.asyncio
    async def test_no_reviews_returns_none(self):
        """无评价时 positive_pct = None"""
        from src.api.banquet_agent import get_review_sentiment_breakdown

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_review_sentiment_breakdown(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["positive_pct"] is None
        assert result["top_improvement_tags"] == []
