"""
Banquet Agent Phase 32 — 单元测试

覆盖端点：
  - get_order_amendment_rate
  - get_vip_upgrade_trend
  - get_banquet_type_profitability
  - get_lead_stage_duration
  - get_hall_peak_season_rate
  - get_package_attach_rate
  - get_customer_reactivation_rate
  - get_event_execution_score
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


def _make_customer(cid="C-001", vip_level=1, total_fen=600000, count=3):
    c = MagicMock()
    c.id                       = cid
    c.vip_level                = vip_level
    c.total_banquet_amount_fen = total_fen
    c.total_banquet_count      = count
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


def _make_lead(lid="L-001", stage="quoted", created_days_ago=20, updated_days_ago=5):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id            = lid
    l.current_stage = (
        LeadStageEnum(stage)
        if stage in [e.value for e in LeadStageEnum]
        else MagicMock(value=stage)
    )
    l.source_channel      = "微信"
    l.expected_budget_fen = 200000
    l.created_at  = datetime.utcnow() - timedelta(days=created_days_ago)
    l.updated_at  = datetime.utcnow() - timedelta(days=updated_days_ago)
    return l


def _make_payment(pid="P-001", order_id="O-001"):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = 50000
    p.created_at       = datetime.utcnow() - timedelta(days=10)
    return p


def _make_package(pid="P-001", price_fen=25000, cost_fen=10000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    p.cost_fen            = cost_fen
    return p


def _make_task(tid="T-001", status="done", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = "U-001"
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    return t


def _make_exception(eid="E-001", order_id="O-001"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.status           = "open"
    e.created_at       = datetime.utcnow() - timedelta(days=3)
    return e


def _make_review(rid="R-001", order_id="O-001", rating=5, ai_score=90.0):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.ai_score         = ai_score
    return r


# ── TestOrderAmendmentRate ────────────────────────────────────────────────────

class TestOrderAmendmentRate:

    @pytest.mark.asyncio
    async def test_amendment_detected(self):
        """1 order with 2 payments → amended=1, rate=100%"""
        from src.api.banquet_agent import get_order_amendment_rate

        order = _make_order()
        pay1  = _make_payment(pid="P-001", order_id=order.id)
        pay2  = _make_payment(pid="P-002", order_id=order.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pay1, pay2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_order_amendment_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["amended_orders"] == 1
        assert result["amendment_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 amendment_rate_pct = None"""
        from src.api.banquet_agent import get_order_amendment_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_amendment_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["amendment_rate_pct"] is None


# ── TestVipUpgradeTrend ───────────────────────────────────────────────────────

class TestVipUpgradeTrend:

    @pytest.mark.asyncio
    async def test_vip_levels_grouped(self):
        """2 vip_level=1 + 1 vip_level=2 → by_level len=2"""
        from src.api.banquet_agent import get_vip_upgrade_trend

        c1 = _make_customer(cid="C-001", vip_level=1)
        c2 = _make_customer(cid="C-002", vip_level=1)
        c3 = _make_customer(cid="C-003", vip_level=2)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c1, c2, c3]))

        result = await get_vip_upgrade_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 3
        assert len(result["by_level"]) == 2
        lvl1 = next(l for l in result["by_level"] if l["vip_level"] == 1)
        assert lvl1["count"] == 2
        assert result["avg_vip_level"] == pytest.approx(4/3, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_customers_returns_empty(self):
        """无客户时 by_level 为空"""
        from src.api.banquet_agent import get_vip_upgrade_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_vip_upgrade_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["by_level"] == []
        assert result["avg_vip_level"] is None


# ── TestBanquetTypeProfitability ──────────────────────────────────────────────

class TestBanquetTypeProfitability:

    @pytest.mark.asyncio
    async def test_profit_computed(self):
        """wedding: rev=300000, cost=100000 → gross_profit=2000元"""
        from src.api.banquet_agent import get_banquet_type_profitability

        pkg   = _make_package(cost_fen=10000)
        order = _make_order(total_fen=300000, table_count=10,
                            package_id=pkg.id, banquet_type="wedding")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_type_profitability(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["most_profitable_type"] == "wedding"
        t = result["types"][0]
        assert t["gross_profit_yuan"] == pytest.approx(2000.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 types 为空"""
        from src.api.banquet_agent import get_banquet_type_profitability

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_profitability(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["types"] == []
        assert result["most_profitable_type"] is None


# ── TestLeadStageDuration ─────────────────────────────────────────────────────

class TestLeadStageDuration:

    @pytest.mark.asyncio
    async def test_stage_duration_computed(self):
        """quoted lead: created 20 days ago, updated 5 days ago → avg=15 days"""
        from src.api.banquet_agent import get_lead_stage_duration

        lead = _make_lead(stage="quoted", created_days_ago=20, updated_days_ago=5)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_stage_duration(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert len(result["by_stage"]) == 1
        assert result["by_stage"][0]["avg_days"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 by_stage 为空"""
        from src.api.banquet_agent import get_lead_stage_duration

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_stage_duration(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["by_stage"] == []


# ── TestHallPeakSeasonRate ────────────────────────────────────────────────────

class TestHallPeakSeasonRate:

    @pytest.mark.asyncio
    async def test_peak_booking_counted(self):
        """hall with June booking (month 6) → peak_total=1"""
        from src.api.banquet_agent import get_hall_peak_season_rate

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(oid="O-001", banquet_date=date(date.today().year - 1, 6, 15))

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_peak_season_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["peak_total"] == 1
        assert result["offpeak_total"] == 0
        assert result["peak_ratio"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_peak_season_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_peak_season_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["peak_ratio"] is None


# ── TestPackageAttachRate ─────────────────────────────────────────────────────

class TestPackageAttachRate:

    @pytest.mark.asyncio
    async def test_attach_rate_computed(self):
        """1 order with package → attach_rate=100%"""
        from src.api.banquet_agent import get_package_attach_rate

        order = _make_order(package_id="P-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_package_attach_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["with_package"] == 1
        assert result["attach_rate_pct"] == pytest.approx(100.0)
        assert result["top_packages"][0]["package_id"] == "P-001"

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 attach_rate_pct = None"""
        from src.api.banquet_agent import get_package_attach_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_package_attach_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["attach_rate_pct"] is None


# ── TestCustomerReactivationRate ──────────────────────────────────────────────

class TestCustomerReactivationRate:

    @pytest.mark.asyncio
    async def test_reactivation_detected(self):
        """old order 18 months ago + recent order 1 month ago → reactivated=1"""
        from src.api.banquet_agent import get_customer_reactivation_rate

        old_order    = _make_order(oid="O-001", customer_id="C-001",
                                   banquet_date=date.today() - timedelta(days=540))
        recent_order = _make_order(oid="O-002", customer_id="C-001",
                                   banquet_date=date.today() - timedelta(days=30))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([old_order, recent_order]))

        result = await get_customer_reactivation_rate(
            store_id="S001", months=12, inactive_threshold_months=12,
            db=db, _=_mock_user()
        )

        assert result["reactivated_count"] == 1
        assert result["reactivation_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 reactivation_rate_pct = None"""
        from src.api.banquet_agent import get_customer_reactivation_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_reactivation_rate(
            store_id="S001", months=12, db=db, _=_mock_user()
        )

        assert result["reactivated_count"] == 0
        assert result["reactivation_rate_pct"] is None


# ── TestEventExecutionScore ───────────────────────────────────────────────────

class TestEventExecutionScore:

    @pytest.mark.asyncio
    async def test_score_computed(self):
        """done task + no exceptions + rating=5 → score > 0"""
        from src.api.banquet_agent import get_event_execution_score

        order  = _make_order(status="completed")
        task   = _make_task(status="done", order_id=order.id)
        review = _make_review(order_id=order.id, rating=5)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:  return _scalars_returning([order])  # orders
            if call_n[0] == 2:  return _scalars_returning([task])   # tasks
            if call_n[0] == 3:  return _scalars_returning([])       # exceptions
            return _scalars_returning([review])                      # review

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_event_execution_score(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_events"] == 1
        assert result["avg_execution_score"] is not None
        assert result["avg_execution_score"] > 0

    @pytest.mark.asyncio
    async def test_no_events_returns_none(self):
        """无已完成宴会时 avg_execution_score = None"""
        from src.api.banquet_agent import get_event_execution_score

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_event_execution_score(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_events"] == 0
        assert result["avg_execution_score"] is None
