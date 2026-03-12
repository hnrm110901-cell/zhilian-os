"""
Banquet Agent Phase 33 — 单元测试

覆盖端点：
  - get_cross_sell_rate
  - get_banquet_size_trend
  - get_lead_budget_accuracy
  - get_payment_overdue_aging
  - get_staff_coverage_rate
  - get_vip_spending_trend
  - get_early_checkin_rate
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
                status="confirmed", customer_id="C-001", package_id=None,
                created_at=None):
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


def _make_customer(cid="C-001", vip_level=2, total_fen=600000):
    c = MagicMock()
    c.id                       = cid
    c.vip_level                = vip_level
    c.total_banquet_amount_fen = total_fen
    c.total_banquet_count      = 3
    return c


def _make_lead(lid="L-001", stage="signed", budget_fen=200000,
               customer_id="C-001", contact_name="张三",
               created_days_ago=20, updated_days_ago=5):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.customer_id         = customer_id
    l.contact_name        = contact_name
    l.source_channel      = "微信"
    l.current_stage       = (
        LeadStageEnum(stage)
        if stage in [e.value for e in LeadStageEnum]
        else MagicMock(value=stage)
    )
    l.expected_budget_fen = budget_fen
    l.created_at  = datetime.utcnow() - timedelta(days=created_days_ago)
    l.updated_at  = datetime.utcnow() - timedelta(days=updated_days_ago)
    return l


def _make_task(tid="T-001", owner="U-001", status="done",
               order_id="O-001", due_hours_ahead=2, completed_hours_before_due=1):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.due_time         = datetime.utcnow() + timedelta(hours=due_hours_ahead)
    t.completed_at     = datetime.utcnow() + timedelta(hours=due_hours_ahead - completed_hours_before_due)
    return t


# ── TestCrossSellRate ─────────────────────────────────────────────────────────

class TestCrossSellRate:

    @pytest.mark.asyncio
    async def test_cross_sell_detected(self):
        """same customer, 2 different banquet types → cross_sell=1, rate=100%"""
        from src.api.banquet_agent import get_cross_sell_rate

        o1 = _make_order(oid="O-001", customer_id="C-001", banquet_type="wedding")
        o2 = _make_order(oid="O-002", customer_id="C-001", banquet_type="birthday")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_cross_sell_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["cross_sell_customers"] == 1
        assert result["cross_sell_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 cross_sell_rate_pct = None"""
        from src.api.banquet_agent import get_cross_sell_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_cross_sell_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["cross_sell_rate_pct"] is None


# ── TestBanquetSizeTrend ──────────────────────────────────────────────────────

class TestBanquetSizeTrend:

    @pytest.mark.asyncio
    async def test_avg_tables_computed(self):
        """10-table order → overall_avg_tables = 10"""
        from src.api.banquet_agent import get_banquet_size_trend

        o = _make_order(table_count=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_banquet_size_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["overall_avg_tables"] == pytest.approx(10.0)
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_avg_tables = None"""
        from src.api.banquet_agent import get_banquet_size_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_size_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["overall_avg_tables"] is None
        assert result["monthly"] == []


# ── TestLeadBudgetAccuracy ────────────────────────────────────────────────────

class TestLeadBudgetAccuracy:

    @pytest.mark.asyncio
    async def test_avg_budget_computed(self):
        """1 signed lead, budget=200000 → avg_budget_yuan=2000"""
        from src.api.banquet_agent import get_lead_budget_accuracy

        lead = _make_lead(stage="signed", budget_fen=200000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_budget_accuracy(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_signed"] == 1
        assert result["avg_budget_yuan"] == pytest.approx(2000.0)

    @pytest.mark.asyncio
    async def test_no_signed_leads_returns_none(self):
        """无签约线索时 avg_budget_yuan = None"""
        from src.api.banquet_agent import get_lead_budget_accuracy

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_budget_accuracy(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_signed"] == 0
        assert result["avg_budget_yuan"] is None


# ── TestPaymentOverdueAging ───────────────────────────────────────────────────

class TestPaymentOverdueAging:

    @pytest.mark.asyncio
    async def test_overdue_aging_bucketed(self):
        """order with outstanding 1500 yuan, 15 days past → 0-30天 bucket"""
        from src.api.banquet_agent import get_payment_overdue_aging

        o = _make_order(
            total_fen=300000, paid_fen=150000,
            banquet_date=date.today() - timedelta(days=15),
            status="confirmed",
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_payment_overdue_aging(store_id="S001", db=db, _=_mock_user())

        assert result["total_overdue"] == 1
        assert result["total_overdue_yuan"] == pytest.approx(1500.0)
        assert result["buckets"][0]["bucket"] == "0-30天"

    @pytest.mark.asyncio
    async def test_no_overdue_returns_empty(self):
        """无欠款时 total_overdue = 0"""
        from src.api.banquet_agent import get_payment_overdue_aging

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_overdue_aging(store_id="S001", db=db, _=_mock_user())

        assert result["total_overdue"] == 0
        assert result["buckets"] == []


# ── TestStaffCoverageRate ─────────────────────────────────────────────────────

class TestStaffCoverageRate:

    @pytest.mark.asyncio
    async def test_coverage_computed(self):
        """1 task assigned to U-001 → total_staff=1, coverage_rate=100%"""
        from src.api.banquet_agent import get_staff_coverage_rate

        task = _make_task(owner="U-001", status="done")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_coverage_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["active_staff"] == 1
        assert result["coverage_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        """无任务时 coverage_rate_pct = None"""
        from src.api.banquet_agent import get_staff_coverage_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_coverage_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["coverage_rate_pct"] is None


# ── TestVipSpendingTrend ──────────────────────────────────────────────────────

class TestVipSpendingTrend:

    @pytest.mark.asyncio
    async def test_vip_spending_grouped(self):
        """vip_level=2 customer + 1 order 300000fen → avg_order=3000元"""
        from src.api.banquet_agent import get_vip_spending_trend

        customer = _make_customer(cid="C-001", vip_level=2)
        order    = _make_order(customer_id="C-001", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([customer])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_spending_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_vip"] == 1
        assert len(result["by_level"]) == 1
        assert result["by_level"][0]["avg_order_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_vip_returns_empty(self):
        """无VIP客户时 by_level 为空"""
        from src.api.banquet_agent import get_vip_spending_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_vip_spending_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_vip"] == 0
        assert result["by_level"] == []


# ── TestEarlyCheckinRate ──────────────────────────────────────────────────────

class TestEarlyCheckinRate:

    @pytest.mark.asyncio
    async def test_early_completion_detected(self):
        """task completed 1h before due → early_count=1, rate=100%"""
        from src.api.banquet_agent import get_early_checkin_rate

        task = _make_task(status="done", due_hours_ahead=3, completed_hours_before_due=1)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_early_checkin_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["early_count"] == 1
        assert result["early_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        """无已完成任务时 early_rate_pct = None"""
        from src.api.banquet_agent import get_early_checkin_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_early_checkin_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["early_rate_pct"] is None
