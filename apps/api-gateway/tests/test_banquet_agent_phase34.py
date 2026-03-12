"""
Banquet Agent Phase 34 — 单元测试

覆盖端点：
  - get_loyalty_points_redemption_rate
  - get_menu_upgrade_rate
  - get_hall_double_booking_risk
  - get_post_event_followup_rate
  - get_banquet_forecast_accuracy
  - get_channel_conversion_funnel
  - get_staff_utilization_heatmap
  - get_customer_lifetime_event_count
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


def _make_customer(cid="C-001", vip_level=1, points_redeemed=0):
    c = MagicMock()
    c.id              = cid
    c.vip_level       = vip_level
    c.points_redeemed = points_redeemed
    c.total_banquet_count = 1
    c.created_at      = datetime.utcnow() - timedelta(days=30)
    return c


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


def _make_lead(lid="L-001", stage="signed", source="微信", created_days_ago=20):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = source
    l.current_stage  = (
        LeadStageEnum(stage)
        if stage in [e.value for e in LeadStageEnum]
        else MagicMock(value=stage)
    )
    l.expected_budget_fen = 200000
    l.customer_id    = "C-001"
    l.created_at     = datetime.utcnow() - timedelta(days=created_days_ago)
    l.updated_at     = datetime.utcnow() - timedelta(days=5)
    return l


def _make_task(tid="T-001", owner="U-001", status="done"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = "O-001"
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.due_time         = datetime.utcnow() + timedelta(hours=2)
    t.completed_at     = datetime.utcnow() + timedelta(hours=1)
    return t


def _make_package(pid="PKG-001", price_fen=25000, cost_fen=10000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    p.cost_fen            = cost_fen
    return p


def _make_target(year=2025, month=6, target_fen=500000):
    t = MagicMock()
    t.year               = year
    t.month              = month
    t.target_revenue_fen = target_fen
    return t


# ── TestLoyaltyPointsRedemptionRate ──────────────────────────────────────────

class TestLoyaltyPointsRedemptionRate:

    @pytest.mark.asyncio
    async def test_redemption_detected(self):
        """1 customer with points_redeemed=500 → redemption_rate=100%"""
        from src.api.banquet_agent import get_loyalty_points_redemption_rate

        c = _make_customer(cid="C-001", points_redeemed=500)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c]))

        result = await get_loyalty_points_redemption_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["redemption_customers"] == 1
        assert result["redemption_rate_pct"] == pytest.approx(100.0)
        assert result["avg_points_redeemed"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_no_customers_returns_none(self):
        """无客户时 redemption_rate_pct = None"""
        from src.api.banquet_agent import get_loyalty_points_redemption_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_loyalty_points_redemption_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["redemption_rate_pct"] is None


# ── TestMenuUpgradeRate ───────────────────────────────────────────────────────

class TestMenuUpgradeRate:

    @pytest.mark.asyncio
    async def test_upgrade_detected(self):
        """套餐价25000/桌×10=250000, 实际=300000 → upgrade=1, avg=500元"""
        from src.api.banquet_agent import get_menu_upgrade_rate

        pkg   = _make_package(price_fen=25000)
        order = _make_order(total_fen=300000, table_count=10, package_id=pkg.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_menu_upgrade_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 1
        assert result["upgrade_count"] == 1
        assert result["upgrade_rate_pct"] == pytest.approx(100.0)
        assert result["avg_upgrade_yuan"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无套餐订单时 upgrade_rate_pct = None"""
        from src.api.banquet_agent import get_menu_upgrade_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_menu_upgrade_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["upgrade_rate_pct"] is None


# ── TestHallDoubleBookingRisk ─────────────────────────────────────────────────

class TestHallDoubleBookingRisk:

    @pytest.mark.asyncio
    async def test_conflict_detected(self):
        """同厅房同日期 2 订单 → total_conflicts=1"""
        from src.api.banquet_agent import get_hall_double_booking_risk

        hall = _make_hall()
        bk1  = _make_booking(bid="B-001", hall_id=hall.id, order_id="O-001")
        bk2  = _make_booking(bid="B-002", hall_id=hall.id, order_id="O-002")
        same_date = date.today() - timedelta(days=10)
        o1 = _make_order(oid="O-001", banquet_date=same_date)
        o2 = _make_order(oid="O-002", banquet_date=same_date)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([bk1, bk2])
            if call_n[0] == 3: return _scalars_returning([o1])
            return _scalars_returning([o2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_double_booking_risk(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_conflicts"] == 1
        assert len(result["halls"]) == 1

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_double_booking_risk

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_double_booking_risk(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["total_conflicts"] == 0


# ── TestPostEventFollowupRate ─────────────────────────────────────────────────

class TestPostEventFollowupRate:

    @pytest.mark.asyncio
    async def test_followup_detected(self):
        """1 completed order + 1 followup record → followup_rate=100%"""
        from src.api.banquet_agent import get_post_event_followup_rate

        order = _make_order(status="completed",
                            banquet_date=date.today() - timedelta(days=5))
        followup = MagicMock()
        followup.id         = "F-001"
        followup.lead_id    = "L-001"
        followup.created_at = datetime.utcnow() - timedelta(days=3)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([followup])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_post_event_followup_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["followup_count"] == 1
        assert result["followup_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_completed_orders_returns_none(self):
        """无已完成订单时 followup_rate_pct = None"""
        from src.api.banquet_agent import get_post_event_followup_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_post_event_followup_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["followup_rate_pct"] is None


# ── TestBanquetForecastAccuracy ───────────────────────────────────────────────

class TestBanquetForecastAccuracy:

    @pytest.mark.asyncio
    async def test_accuracy_computed(self):
        """target=5000元, actual=5000元 → accuracy=100%, deviation=0%"""
        from src.api.banquet_agent import get_banquet_forecast_accuracy

        target = _make_target(target_fen=500000)
        order  = _make_order(total_fen=500000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            # alternating: target query, orders query, target, orders...
            if call_n[0] % 2 == 1: return _scalars_returning([target])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_forecast_accuracy(store_id="S001", months=1, db=db, _=_mock_user())

        assert len(result["monthly"]) == 1
        assert result["monthly"][0]["accuracy_pct"] == pytest.approx(100.0)
        assert result["monthly"][0]["deviation_pct"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_no_targets_returns_none(self):
        """无目标数据时 avg_accuracy_pct = None"""
        from src.api.banquet_agent import get_banquet_forecast_accuracy

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_forecast_accuracy(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["monthly"] == []
        assert result["avg_accuracy_pct"] is None


# ── TestChannelConversionFunnel ───────────────────────────────────────────────

class TestChannelConversionFunnel:

    @pytest.mark.asyncio
    async def test_channel_funnel_computed(self):
        """1 signed 微信 + 1 quoted 转介绍 → 微信 conv=100%, best=微信"""
        from src.api.banquet_agent import get_channel_conversion_funnel

        l1 = _make_lead(lid="L-001", stage="won", source="微信")
        l2 = _make_lead(lid="L-002", stage="quoted", source="转介绍")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_channel_conversion_funnel(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert len(result["channels"]) == 2
        wx = next(c for c in result["channels"] if c["channel"] == "微信")
        assert wx["conversion_rate_pct"] == pytest.approx(100.0)
        assert result["best_channel"] == "微信"

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 channels 为空"""
        from src.api.banquet_agent import get_channel_conversion_funnel

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_channel_conversion_funnel(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["channels"] == []


# ── TestStaffUtilizationHeatmap ───────────────────────────────────────────────

class TestStaffUtilizationHeatmap:

    @pytest.mark.asyncio
    async def test_heatmap_computed(self):
        """1 task by U-001 on Monday → total=1, staff len=1"""
        from src.api.banquet_agent import get_staff_utilization_heatmap

        task = _make_task(owner="U-001")
        # Force created_at to a known Monday
        monday = datetime(2026, 3, 9, 10, 0, 0)  # March 9 2026 is Monday
        task.created_at = monday

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_utilization_heatmap(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 1
        assert len(result["staff"]) == 1
        assert result["staff"][0]["user_id"] == "U-001"
        assert result["staff"][0]["peak_weekday"] == "周一"

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 staff 为空"""
        from src.api.banquet_agent import get_staff_utilization_heatmap

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_utilization_heatmap(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 0
        assert result["staff"] == []


# ── TestCustomerLifetimeEventCount ────────────────────────────────────────────

class TestCustomerLifetimeEventCount:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """C-001 has 2 orders → avg=2, median=2, distribution has '2次'"""
        from src.api.banquet_agent import get_customer_lifetime_event_count

        o1 = _make_order(oid="O-001", customer_id="C-001")
        o2 = _make_order(oid="O-002", customer_id="C-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_lifetime_event_count(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["avg_events"] == pytest.approx(2.0)
        assert result["median_events"] == pytest.approx(2.0)
        bucket_2 = next((b for b in result["distribution"] if b["bucket"] == "2次"), None)
        assert bucket_2 is not None
        assert bucket_2["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_events = None"""
        from src.api.banquet_agent import get_customer_lifetime_event_count

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_lifetime_event_count(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["avg_events"] is None
        assert result["distribution"] == []
