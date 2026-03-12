"""
Banquet Agent Phase 44 — 单元测试

覆盖端点：
  - get_banquet_lead_conversion_funnel
  - get_hall_slot_availability_ratio
  - get_customer_spend_growth
  - get_menu_upgrade_rate
  - get_task_completion_speed
  - get_banquet_refund_rate
  - get_lead_win_loss_ratio
  - get_order_value_concentration
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


def _make_lead(lid="L-001", stage="won", source="微信", budget_fen=200000):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum(stage)
    l.expected_budget_fen = budget_fen
    l.created_at          = datetime.utcnow() - timedelta(days=20)
    l.updated_at          = datetime.utcnow() - timedelta(days=5)
    return l


def _make_hall(hid="H-001", name="一号厅", max_tables=30, is_active=True):
    h = MagicMock()
    h.id         = hid
    h.name       = name
    h.max_tables = max_tables
    h.is_active  = is_active
    return h


def _make_booking(bid="B-001", hall_id="H-001", slot_date=None, slot_name="dinner"):
    b = MagicMock()
    b.id        = bid
    b.hall_id   = hall_id
    b.slot_date = slot_date or (date.today() - timedelta(days=10))
    b.slot_name = slot_name
    b.banquet_order_id = "O-001"
    return b


def _make_task(tid="T-001", owner="U-001", order_id="O-001",
               status="done", hrs_to_complete=2):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(hours=hrs_to_complete)
    t.completed_at     = datetime.utcnow()
    t.due_time         = datetime.utcnow() + timedelta(hours=24)
    return t


def _make_package(pid="PKG-001", price_fen=25000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    return p


# ── TestBanquetLeadConversionFunnel ───────────────────────────────────────────

class TestBanquetLeadConversionFunnel:

    @pytest.mark.asyncio
    async def test_funnel_computed(self):
        """1 won + 1 new → win_rate=50%, stages有won和new"""
        from src.api.banquet_agent import get_banquet_lead_conversion_funnel

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="new")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_banquet_lead_conversion_funnel(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["win_rate_pct"] == pytest.approx(50.0)
        won_stage = next(s for s in result["stages"] if s["stage"] == "won")
        assert won_stage["count"] == 1

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 win_rate_pct = None"""
        from src.api.banquet_agent import get_banquet_lead_conversion_funnel

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_lead_conversion_funnel(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["win_rate_pct"] is None


# ── TestHallSlotAvailabilityRatio ─────────────────────────────────────────────

class TestHallSlotAvailabilityRatio:

    @pytest.mark.asyncio
    async def test_occupancy_computed(self):
        """1 hall, 1 booking day in 90d → occupancy=1/90≈1.1%"""
        from src.api.banquet_agent import get_hall_slot_availability_ratio

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            return _scalars_returning([booking])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_slot_availability_ratio(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_halls"] == 1
        assert result["halls"][0]["booked_days"] == 1
        assert result["overall_occupancy_pct"] == pytest.approx(1/90*100, abs=0.1)

    @pytest.mark.asyncio
    async def test_no_halls_returns_none(self):
        """无活跃厅房时 overall_occupancy_pct = None"""
        from src.api.banquet_agent import get_hall_slot_availability_ratio

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_slot_availability_ratio(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_halls"] == 0
        assert result["overall_occupancy_pct"] is None


# ── TestCustomerSpendGrowth ────────────────────────────────────────────────────

class TestCustomerSpendGrowth:

    @pytest.mark.asyncio
    async def test_growth_computed(self):
        """C-001 two orders: 200000→300000 → growth=50%"""
        from src.api.banquet_agent import get_customer_spend_growth

        d1 = date.today() - timedelta(days=60)
        d2 = date.today() - timedelta(days=10)
        o1 = _make_order(oid="O-001", total_fen=200000, customer_id="C-001", banquet_date=d1)
        o2 = _make_order(oid="O-002", total_fen=300000, customer_id="C-001", banquet_date=d2)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_spend_growth(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["growing_customers"] == 1
        assert result["avg_growth_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_growth_pct = None"""
        from src.api.banquet_agent import get_customer_spend_growth

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_spend_growth(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["avg_growth_pct"] is None


# ── TestMenuUpgradeRate ────────────────────────────────────────────────────────

class TestMenuUpgradeRate:

    @pytest.mark.asyncio
    async def test_upgrade_detected(self):
        """pkg 25000*10=250000, actual=350000 > 250000*1.3=325000 → upgraded"""
        from src.api.banquet_agent import get_menu_upgrade_rate

        pkg   = _make_package(price_fen=25000)
        order = _make_order(total_fen=350000, table_count=10, package_id=pkg.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_menu_upgrade_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 1
        assert result["upgraded_count"] == 1
        assert result["upgrade_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无套餐订单时 upgrade_rate_pct = None"""
        from src.api.banquet_agent import get_menu_upgrade_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_menu_upgrade_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["upgrade_rate_pct"] is None


# ── TestTaskCompletionSpeed ────────────────────────────────────────────────────

class TestTaskCompletionSpeed:

    @pytest.mark.asyncio
    async def test_speed_computed(self):
        """task completed in 2h → avg_hours=2, fast_pct=100%(≤24h)"""
        from src.api.banquet_agent import get_task_completion_speed

        task = _make_task(status="done", hrs_to_complete=2)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_task_completion_speed(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["avg_hours"] == pytest.approx(2.0, abs=0.1)
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


# ── TestBanquetRefundRate ──────────────────────────────────────────────────────

class TestBanquetRefundRate:

    @pytest.mark.asyncio
    async def test_refund_computed(self):
        """1 cancelled order with paid=30000fen → refund_rate=100%, refund=300元"""
        from src.api.banquet_agent import get_banquet_refund_rate

        order = _make_order(status="cancelled", paid_fen=30000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_refund_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 1
        assert result["refund_needed"] == 1
        assert result["refund_rate_pct"] == pytest.approx(100.0)
        assert result["total_refund_yuan"] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_no_cancellations_returns_none(self):
        """无取消订单时 refund_rate_pct = None"""
        from src.api.banquet_agent import get_banquet_refund_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_refund_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 0
        assert result["refund_rate_pct"] is None


# ── TestLeadWinLossRatio ───────────────────────────────────────────────────────

class TestLeadWinLossRatio:

    @pytest.mark.asyncio
    async def test_ratio_computed(self):
        """2 won + 1 lost → ratio=2.0"""
        from src.api.banquet_agent import get_lead_win_loss_ratio

        l1 = _make_lead(lid="L-001", stage="won",  source="微信")
        l2 = _make_lead(lid="L-002", stage="won",  source="微信")
        l3 = _make_lead(lid="L-003", stage="lost", source="微信")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2, l3]))

        result = await get_lead_win_loss_ratio(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_closed"] == 3
        assert result["won"] == 2
        assert result["lost"] == 1
        assert result["win_loss_ratio"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_no_closed_leads_returns_none(self):
        """无已关闭线索时 win_loss_ratio = None"""
        from src.api.banquet_agent import get_lead_win_loss_ratio

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_win_loss_ratio(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_closed"] == 0
        assert result["win_loss_ratio"] is None


# ── TestOrderValueConcentration ────────────────────────────────────────────────

class TestOrderValueConcentration:

    @pytest.mark.asyncio
    async def test_concentration_computed(self):
        """5 orders, top 20%(1 order) = highest value → top20_pct computed"""
        from src.api.banquet_agent import get_order_value_concentration

        orders = [
            _make_order(oid=f"O-{i}", total_fen=v)
            for i, v in enumerate([500000, 300000, 200000, 150000, 100000])
        ]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning(orders))

        result = await get_order_value_concentration(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 5
        assert result["top20_pct_revenue"] is not None
        assert result["top20_pct_revenue"] > 30.0  # top order is 500k of 1250k = 40%

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 top20_pct_revenue = None"""
        from src.api.banquet_agent import get_order_value_concentration

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_value_concentration(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["top20_pct_revenue"] is None
