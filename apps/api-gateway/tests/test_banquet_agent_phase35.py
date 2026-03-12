"""
Banquet Agent Phase 35 — 单元测试

覆盖端点：
  - get_deposit_refund_rate
  - get_banquet_repeat_interval
  - get_lead_win_loss_ratio
  - get_hall_maintenance_downtime
  - get_customer_complaint_rate
  - get_table_per_staff_ratio
  - get_seasonal_revenue_index
  - get_vip_retention_rate
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
                deposit_fen=30000, table_count=10,
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


def _make_lead(lid="L-001", stage="won"):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = "微信"
    l.current_stage  = (
        LeadStageEnum(stage)
        if stage in [e.value for e in LeadStageEnum]
        else MagicMock(value=stage)
    )
    l.expected_budget_fen = 200000
    l.created_at = datetime.utcnow() - timedelta(days=20)
    l.updated_at = datetime.utcnow() - timedelta(days=5)
    return l


def _make_customer(cid="C-001", vip_level=2):
    c = MagicMock()
    c.id        = cid
    c.vip_level = vip_level
    c.total_banquet_count = 2
    c.total_banquet_amount_fen = 600000
    c.created_at = datetime.utcnow() - timedelta(days=60)
    return c


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.due_time         = datetime.utcnow() + timedelta(hours=2)
    t.completed_at     = datetime.utcnow() + timedelta(hours=1)
    return t


def _make_exception(eid="E-001", order_id="O-001", exc_type="complaint"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = exc_type
    e.status           = "open"
    e.created_at       = datetime.utcnow() - timedelta(days=3)
    return e


# ── TestDepositRefundRate ─────────────────────────────────────────────────────

class TestDepositRefundRate:

    @pytest.mark.asyncio
    async def test_refund_detected(self):
        """1 cancelled order with deposit_fen=30000 → refund_rate=100%, avg=300元"""
        from src.api.banquet_agent import get_deposit_refund_rate

        order = _make_order(status="cancelled", deposit_fen=30000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_deposit_refund_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 1
        assert result["deposit_refund_count"] == 1
        assert result["refund_rate_pct"] == pytest.approx(100.0)
        assert result["avg_deposit_yuan"] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_no_cancellations_returns_none(self):
        """无取消订单时 refund_rate_pct = None"""
        from src.api.banquet_agent import get_deposit_refund_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_refund_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 0
        assert result["refund_rate_pct"] is None


# ── TestBanquetRepeatInterval ─────────────────────────────────────────────────

class TestBanquetRepeatInterval:

    @pytest.mark.asyncio
    async def test_interval_computed(self):
        """same customer, banquet_date 30 days apart → avg=30, median=30"""
        from src.api.banquet_agent import get_banquet_repeat_interval

        d1 = date.today() - timedelta(days=60)
        d2 = date.today() - timedelta(days=30)
        o1 = _make_order(oid="O-001", customer_id="C-001", banquet_date=d1)
        o2 = _make_order(oid="O-002", customer_id="C-001", banquet_date=d2)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_repeat_interval(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_repeat_customers"] == 1
        assert result["avg_interval_days"] == pytest.approx(30.0)
        assert result["median_interval_days"] == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_interval_days = None"""
        from src.api.banquet_agent import get_banquet_repeat_interval

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_repeat_interval(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_repeat_customers"] == 0
        assert result["avg_interval_days"] is None


# ── TestLeadWinLossRatio ──────────────────────────────────────────────────────

class TestLeadWinLossRatio:

    @pytest.mark.asyncio
    async def test_ratio_computed(self):
        """2 won + 1 lost → win_loss_ratio=2.0, win_rate=66.7%"""
        from src.api.banquet_agent import get_lead_win_loss_ratio

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="won")
        l3 = _make_lead(lid="L-003", stage="lost")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2, l3]))

        result = await get_lead_win_loss_ratio(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["won"] == 2
        assert result["lost"] == 1
        assert result["win_loss_ratio"] == pytest.approx(2.0)
        assert result["win_rate_pct"] == pytest.approx(66.7, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 win_loss_ratio = None"""
        from src.api.banquet_agent import get_lead_win_loss_ratio

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_win_loss_ratio(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["won"] == 0
        assert result["lost"] == 0
        assert result["win_loss_ratio"] is None
        assert result["win_rate_pct"] is None


# ── TestHallMaintenanceDowntime ───────────────────────────────────────────────

class TestHallMaintenanceDowntime:

    @pytest.mark.asyncio
    async def test_downtime_detected(self):
        """1 active + 1 inactive → downtime_rate=50%"""
        from src.api.banquet_agent import get_hall_maintenance_downtime

        h_active   = _make_hall(hid="H-001", is_active=True)
        h_inactive = _make_hall(hid="H-002", name="二号厅", is_active=False)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([h_active, h_inactive]))

        result = await get_hall_maintenance_downtime(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_halls"] == 2
        assert result["inactive_halls"] == 1
        assert result["downtime_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_none(self):
        """无厅房时 downtime_rate_pct = None"""
        from src.api.banquet_agent import get_hall_maintenance_downtime

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_maintenance_downtime(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_halls"] == 0
        assert result["downtime_rate_pct"] is None


# ── TestCustomerComplaintRate ─────────────────────────────────────────────────

class TestCustomerComplaintRate:

    @pytest.mark.asyncio
    async def test_complaint_detected(self):
        """1 completed order + 1 complaint exception → complaint_rate=100%"""
        from src.api.banquet_agent import get_customer_complaint_rate

        order = _make_order(status="completed")
        exc   = _make_exception(order_id=order.id, exc_type="complaint")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([exc])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_customer_complaint_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["complaint_count"] == 1
        assert result["complaint_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_completed_orders_returns_none(self):
        """无已完成订单时 complaint_rate_pct = None"""
        from src.api.banquet_agent import get_customer_complaint_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_complaint_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["complaint_rate_pct"] is None


# ── TestTablePerStaffRatio ────────────────────────────────────────────────────

class TestTablePerStaffRatio:

    @pytest.mark.asyncio
    async def test_ratio_computed(self):
        """1 order(10 tables) + 2 tasks by U-001 → avg_tasks_per_table=0.2"""
        from src.api.banquet_agent import get_table_per_staff_ratio

        order = _make_order(table_count=10)
        t1    = _make_task(tid="T-001", owner="U-001", order_id=order.id)
        t2    = _make_task(tid="T-002", owner="U-001", order_id=order.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([t1, t2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_table_per_staff_ratio(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["total_tables"] == 10
        assert result["total_tasks"] == 2
        assert result["avg_tasks_per_table"] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_tasks_per_table = None"""
        from src.api.banquet_agent import get_table_per_staff_ratio

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_table_per_staff_ratio(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_tasks_per_table"] is None


# ── TestSeasonalRevenueIndex ──────────────────────────────────────────────────

class TestSeasonalRevenueIndex:

    @pytest.mark.asyncio
    async def test_peak_month_identified(self):
        """order in June → June has seasonal_index=1.0, peak_month=6"""
        from src.api.banquet_agent import get_seasonal_revenue_index

        order = _make_order(total_fen=300000,
                            banquet_date=date(date.today().year - 1, 6, 15))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_seasonal_revenue_index(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["peak_month"] == 6
        june = next(m for m in result["monthly"] if m["month"] == 6)
        assert june["seasonal_index"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 monthly 为空列表"""
        from src.api.banquet_agent import get_seasonal_revenue_index

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_seasonal_revenue_index(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["monthly"] == []
        assert result["peak_month"] is None


# ── TestVipRetentionRate ──────────────────────────────────────────────────────

class TestVipRetentionRate:

    @pytest.mark.asyncio
    async def test_retained_detected(self):
        """1 vip customer with recent order → retention_rate=100%"""
        from src.api.banquet_agent import get_vip_retention_rate

        customer = _make_customer(cid="C-001", vip_level=2)
        order    = _make_order(customer_id="C-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([customer])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_retention_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_vip"] == 1
        assert result["retained_vip"] == 1
        assert result["retention_rate_pct"] == pytest.approx(100.0)
        assert len(result["by_level"]) == 1

    @pytest.mark.asyncio
    async def test_no_vip_returns_none(self):
        """无VIP客户时 retention_rate_pct = None"""
        from src.api.banquet_agent import get_vip_retention_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_vip_retention_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_vip"] == 0
        assert result["retention_rate_pct"] is None
        assert result["by_level"] == []
