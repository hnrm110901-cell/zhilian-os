"""
Banquet Agent Phase 54 — 单元测试

覆盖端点：
  - get_order_upsell_rate
  - get_lead_response_time
  - get_hall_idle_rate
  - get_vip_cancellation_rate
  - get_payment_method_preference
  - get_banquet_season_analysis
  - get_staff_revenue_contribution
  - get_contract_signing_speed
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
                status="confirmed", customer_id="C-001", created_at=None,
                package_id=None):
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


def _make_lead(lid="L-001", stage="new", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id            = lid
    l.source_channel = "微信"
    l.current_stage  = LeadStageEnum(stage)
    l.created_at     = created_at or datetime.utcnow() - timedelta(days=10)
    return l


def _make_followup(fid="F-001", lead_id="L-001", created_at=None):
    f = MagicMock()
    f.id         = fid
    f.lead_id    = lead_id
    f.created_at = created_at or datetime.utcnow() - timedelta(days=9)
    return f


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = "dinner"
    return b


def _make_customer(cid="C-001", vip_level=2, store_id="S001"):
    c = MagicMock()
    c.id        = cid
    c.store_id  = store_id
    c.vip_level = vip_level
    return c


def _make_payment(pid="P-001", order_id="O-001", method="微信", amount_fen=30000,
                  created_at=None):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.payment_method   = method
    p.amount_fen       = amount_fen
    p.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return p


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    return t


def _make_contract(cid="CT-001", order_id="O-001", created_at=None):
    c = MagicMock()
    c.id               = cid
    c.banquet_order_id = order_id
    c.created_at       = created_at or datetime.utcnow() - timedelta(days=3)
    return c


# ── TestOrderUpsellRate ───────────────────────────────────────────────────────

class TestOrderUpsellRate:

    @pytest.mark.asyncio
    async def test_upsell_computed(self):
        """package order with total_fen=350000 > threshold → upsell_count=1"""
        from src.api.banquet_agent import get_order_upsell_rate

        o1 = _make_order(oid="O-001", total_fen=350000, package_id="PKG-001")
        o2 = _make_order(oid="O-002", total_fen=150000, package_id="PKG-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_order_upsell_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["upsell_count"] == 1
        assert result["upsell_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_package_orders_returns_none(self):
        """无套餐订单时 upsell_rate_pct = None"""
        from src.api.banquet_agent import get_order_upsell_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_upsell_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["upsell_rate_pct"] is None


# ── TestLeadResponseTime ──────────────────────────────────────────────────────

class TestLeadResponseTime:

    @pytest.mark.asyncio
    async def test_response_time_computed(self):
        """lead created 10d ago, followup 1h later → avg≈0.04d"""
        from src.api.banquet_agent import get_lead_response_time

        lead_dt = datetime.utcnow() - timedelta(days=10)
        fu_dt   = lead_dt + timedelta(hours=1)
        lead = _make_lead(lid="L-001", created_at=lead_dt)
        fu   = _make_followup(fid="F-001", lead_id="L-001", created_at=fu_dt)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([fu])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_response_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["avg_response_hours"] == pytest.approx(1.0, abs=0.1)
        assert result["fast_response_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_response_hours = None"""
        from src.api.banquet_agent import get_lead_response_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_response_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_response_hours"] is None


# ── TestHallIdleRate ──────────────────────────────────────────────────────────

class TestHallIdleRate:

    @pytest.mark.asyncio
    async def test_idle_rate_computed(self):
        """H-001 booked 1 day in 90 days → idle_rate ≈ 98.9%"""
        from src.api.banquet_agent import get_hall_idle_rate

        b1 = _make_booking(bid="B-001", hall_id="H-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1]))

        result = await get_hall_idle_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_halls"] == 1
        assert result["avg_idle_rate_pct"] is not None
        assert result["avg_idle_rate_pct"] > 90.0

    @pytest.mark.asyncio
    async def test_no_bookings_returns_none(self):
        """无预订时 avg_idle_rate_pct = None"""
        from src.api.banquet_agent import get_hall_idle_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_idle_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_halls"] == 0
        assert result["avg_idle_rate_pct"] is None


# ── TestVipCancellationRate ───────────────────────────────────────────────────

class TestVipCancellationRate:

    @pytest.mark.asyncio
    async def test_cancellation_compared(self):
        """VIP C-001 cancelled + normal C-002 confirmed → vip_pct=100%, normal_pct=0%"""
        from src.api.banquet_agent import get_vip_cancellation_rate

        vip    = _make_customer(cid="C-001", vip_level=2)
        o_vip  = _make_order(oid="O-001", customer_id="C-001", status="cancelled")
        o_norm = _make_order(oid="O-002", customer_id="C-002", status="confirmed")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([vip])
            return _scalars_returning([o_vip, o_norm])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_cancellation_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["vip_cancellation_pct"] == pytest.approx(100.0)
        assert result["normal_cancellation_pct"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 vip_cancellation_pct = None"""
        from src.api.banquet_agent import get_vip_cancellation_rate

        vip = _make_customer(cid="C-001", vip_level=2)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([vip])
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_cancellation_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["vip_cancellation_pct"] is None


# ── TestPaymentMethodPreference ───────────────────────────────────────────────

class TestPaymentMethodPreference:

    @pytest.mark.asyncio
    async def test_preference_computed(self):
        """2 微信 + 1 现金 → preferred_method=微信"""
        from src.api.banquet_agent import get_payment_method_preference

        p1 = _make_payment(pid="P-001", method="微信")
        p2 = _make_payment(pid="P-002", method="微信")
        p3 = _make_payment(pid="P-003", method="现金")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([p1, p2, p3]))

        result = await get_payment_method_preference(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 3
        assert result["preferred_method"] == "微信"
        wx = next(m for m in result["by_method"] if m["method"] == "微信")
        assert wx["count_pct"] == pytest.approx(66.7, rel=0.01)

    @pytest.mark.asyncio
    async def test_no_payments_returns_none(self):
        """无支付记录时 preferred_method = None"""
        from src.api.banquet_agent import get_payment_method_preference

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_method_preference(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 0
        assert result["preferred_method"] is None


# ── TestBanquetSeasonAnalysis ─────────────────────────────────────────────────

class TestBanquetSeasonAnalysis:

    @pytest.mark.asyncio
    async def test_season_computed(self):
        """order in May (spring) → peak_season=春季"""
        from src.api.banquet_agent import get_banquet_season_analysis

        o1 = _make_order(oid="O-001", banquet_date=date(date.today().year, 5, 10))
        o2 = _make_order(oid="O-002", banquet_date=date(date.today().year, 4, 20))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_season_analysis(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["peak_season"] == "春季"
        spring = next(s for s in result["by_season"] if s["season"] == "春季")
        assert spring["count"] == 2

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 peak_season = None"""
        from src.api.banquet_agent import get_banquet_season_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_season_analysis(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["peak_season"] is None


# ── TestStaffRevenueContribution ──────────────────────────────────────────────

class TestStaffRevenueContribution:

    @pytest.mark.asyncio
    async def test_contribution_computed(self):
        """U-001 task on O-001 (300000fen) → revenue=3000yuan"""
        from src.api.banquet_agent import get_staff_revenue_contribution

        task  = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        order = _make_order(oid="O-001", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([task])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_revenue_contribution(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["top_contributor"] == "U-001"
        assert result["staff"][0]["revenue_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 top_contributor = None"""
        from src.api.banquet_agent import get_staff_revenue_contribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_revenue_contribution(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["top_contributor"] is None


# ── TestContractSigningSpeed ──────────────────────────────────────────────────

class TestContractSigningSpeed:

    @pytest.mark.asyncio
    async def test_speed_computed(self):
        """order created 10d ago, contract 7d ago → avg=3d"""
        from src.api.banquet_agent import get_contract_signing_speed

        order_dt    = datetime.utcnow() - timedelta(days=10)
        contract_dt = datetime.utcnow() - timedelta(days=7)
        order    = _make_order(status="confirmed", created_at=order_dt)
        contract = _make_contract(order_id=order.id, created_at=contract_dt)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([contract])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_contract_signing_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_confirmed"] == 1
        assert result["with_contract"] == 1
        assert result["avg_signing_days"] == pytest.approx(3.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_confirmed_orders_returns_none(self):
        """无已确认订单时 avg_signing_days = None"""
        from src.api.banquet_agent import get_contract_signing_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_contract_signing_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_confirmed"] == 0
        assert result["avg_signing_days"] is None
