"""
Banquet Agent Phase 26 — 单元测试

覆盖端点：
  - get_cancellation_analysis
  - get_package_upgrade_rate
  - get_staff_workload
  - get_lead_aging
  - get_revenue_per_table
  - get_waitlist_conversion
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


def _rows_returning(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_order(oid="O-001", store_id="S001", total_fen=300000,
                paid_fen=150000, deposit_fen=60000, table_count=10,
                banquet_type="wedding", banquet_date=None,
                status="cancelled", customer_id="C-001",
                package_id=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.store_id         = store_id
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.deposit_fen      = deposit_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.package_id       = package_id
    o.contact_name     = "张三"
    status_map = {
        "cancelled":  OrderStatusEnum.CANCELLED,
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CANCELLED)
    return o


def _make_package(pid="P-001", name="婚宴套餐", price_fen=60000, cost_fen=30000,
                  banquet_type="wedding"):
    from src.models.banquet import BanquetTypeEnum
    p = MagicMock()
    p.id                  = pid
    p.name                = name
    p.suggested_price_fen = price_fen
    p.cost_fen            = cost_fen
    p.banquet_type        = BanquetTypeEnum(banquet_type)
    p.is_active           = True
    p.target_people_min   = 1
    p.target_people_max   = 999
    return p


def _make_task(tid="T-001", owner="U-001", task_type="setup",
               status="done", due_time=None, completed_at=None):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id            = tid
    t.owner_user_id = owner
    t.task_type     = task_type
    t.task_status   = TaskStatusEnum(status)
    t.due_time      = due_time or (datetime.utcnow() + timedelta(hours=2))
    t.completed_at  = completed_at
    t.created_at    = datetime.utcnow() - timedelta(days=5)
    return t


def _make_lead(lid="L-001", stage="waiting_decision",
               created_days_ago=30, updated_days_ago=5):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id            = lid
    l.current_stage = LeadStageEnum(stage) if stage in [e.value for e in LeadStageEnum] else MagicMock(value=stage)
    l.contact_name  = "李四"
    l.created_at    = datetime.utcnow() - timedelta(days=created_days_ago)
    l.updated_at    = datetime.utcnow() - timedelta(days=updated_days_ago)
    return l


# ── TestCancellationAnalysis ──────────────────────────────────────────────────

class TestCancellationAnalysis:

    @pytest.mark.asyncio
    async def test_cancel_rate_and_lost_yuan(self):
        """1 取消 / 2 总订单 → cancel_rate_pct=50, total_lost_yuan 正确"""
        from src.api.banquet_agent import get_cancellation_analysis

        cancelled = _make_order(status="cancelled", total_fen=300000, paid_fen=100000)
        all_orders = [
            cancelled,
            _make_order(oid="O-002", status="confirmed"),
        ]

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([cancelled])   # cancelled query
            return _scalars_returning(all_orders)        # all orders query

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_cancellation_analysis(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_cancelled"] == 1
        assert result["cancel_rate_pct"] == pytest.approx(50.0)
        # total_lost = total - paid = 3000 - 1000 = 2000
        assert result["total_lost_yuan"] == pytest.approx(2000.0)
        assert len(result["by_type"]) >= 1

    @pytest.mark.asyncio
    async def test_no_cancelled_orders_returns_zero(self):
        """无取消订单时 total_cancelled == 0"""
        from src.api.banquet_agent import get_cancellation_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_cancellation_analysis(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_cancelled"] == 0
        assert result["by_type"] == []


# ── TestPackageUpgradeRate ─────────────────────────────────────────────────────

class TestPackageUpgradeRate:

    @pytest.mark.asyncio
    async def test_upgrade_rate_computed(self):
        """1 高价包含的订单 → upgrade_count=1, upgrade_rate_pct=100"""
        from src.api.banquet_agent import get_package_upgrade_rate

        # 2 packages: cheap(20000) and premium(80000), median=50000
        cheap   = _make_package(pid="P-CHEAP",   price_fen=20000)
        premium = _make_package(pid="P-PREMIUM", price_fen=80000)
        order   = _make_order(status="confirmed", package_id="P-PREMIUM",
                               total_fen=800000, table_count=10)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([cheap, premium])   # packages
            return _scalars_returning([order])                 # orders

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_package_upgrade_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["upgrade_count"] == 1
        assert result["upgrade_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_packages_returns_empty(self):
        """无套餐时返回 upgrade_count=0"""
        from src.api.banquet_agent import get_package_upgrade_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_package_upgrade_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["upgrade_count"] == 0
        assert result["packages"] == []


# ── TestStaffWorkload ─────────────────────────────────────────────────────────

class TestStaffWorkload:

    @pytest.mark.asyncio
    async def test_workload_grouped_by_owner(self):
        """1 done 任务 → owner 的 completion_rate_pct = 100"""
        from src.api.banquet_agent import get_staff_workload

        task = _make_task(owner="U-001", status="done")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_workload(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 1
        assert len(result["workload"]) == 1
        assert result["workload"][0]["completion_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 workload 为空"""
        from src.api.banquet_agent import get_staff_workload

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_workload(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 0
        assert result["workload"] == []


# ── TestLeadAging ─────────────────────────────────────────────────────────────

class TestLeadAging:

    @pytest.mark.asyncio
    async def test_stale_lead_detected(self):
        """updated_at 超过 30 天的线索应出现在 stale_leads"""
        from src.api.banquet_agent import get_lead_aging

        lead = _make_lead(stage="quoted", updated_days_ago=45)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_aging(store_id="S001", db=db, _=_mock_user())

        assert result["total_active_leads"] == 1
        assert result["stale_count"] == 1
        assert result["stale_leads"][0]["days_idle"] >= 45

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 stale_count == 0"""
        from src.api.banquet_agent import get_lead_aging

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_aging(store_id="S001", db=db, _=_mock_user())

        assert result["total_active_leads"] == 0
        assert result["stale_count"] == 0


# ── TestRevenuePerTable ───────────────────────────────────────────────────────

class TestRevenuePerTable:

    @pytest.mark.asyncio
    async def test_avg_per_table_computed(self):
        """300000分 / 10桌 = 300元/桌"""
        from src.api.banquet_agent import get_revenue_per_table

        o = _make_order(status="confirmed", total_fen=300000, table_count=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["overall_avg_yuan"] == pytest.approx(300.0)
        assert len(result["by_type"]) >= 1
        assert len(result["by_month"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_avg_yuan = None"""
        from src.api.banquet_agent import get_revenue_per_table

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_revenue_per_table(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["overall_avg_yuan"] is None
        assert result["by_type"] == []


# ── TestWaitlistConversion ────────────────────────────────────────────────────

class TestWaitlistConversion:

    @pytest.mark.asyncio
    async def test_conversion_rate_computed(self):
        """1 signed / 1 waitlisted → conversion_rate_pct = 100"""
        from src.api.banquet_agent import get_waitlist_conversion

        lead = _make_lead(stage="signed", created_days_ago=20, updated_days_ago=2)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_waitlist_conversion(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["waitlisted_count"] == 1
        assert result["converted_count"] == 1
        assert result["conversion_rate_pct"] == pytest.approx(100.0)
        assert result["avg_wait_days"] is not None

    @pytest.mark.asyncio
    async def test_no_leads_returns_none_rate(self):
        """无线索时 conversion_rate_pct = None"""
        from src.api.banquet_agent import get_waitlist_conversion

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_waitlist_conversion(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["waitlisted_count"] == 0
        assert result["conversion_rate_pct"] is None
