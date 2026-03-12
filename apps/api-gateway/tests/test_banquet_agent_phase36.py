"""
Banquet Agent Phase 36 — 单元测试

覆盖端点：
  - get_banquet_cancellation_reasons
  - get_quote_acceptance_rate
  - get_staff_overtime_rate
  - get_package_revenue_contribution
  - get_customer_churn_risk
  - get_hall_revenue_per_sqm
  - get_lead_nurture_effectiveness
  - get_banquet_day_of_week_pattern
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


def _make_hall(hid="H-001", name="一号厅", max_tables=30,
               is_active=True, floor_area_m2=200.0):
    h = MagicMock()
    h.id            = hid
    h.name          = name
    h.max_tables    = max_tables
    h.is_active     = is_active
    h.floor_area_m2 = floor_area_m2
    return h


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001",
                  slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    return b


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


def _make_customer(cid="C-001"):
    c = MagicMock()
    c.id        = cid
    c.vip_level = 1
    c.total_banquet_count = 1
    c.created_at = datetime.utcnow() - timedelta(days=60)
    return c


def _make_task(tid="T-001", owner="U-001", order_id="O-001",
               overtime=False):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.due_time         = datetime.utcnow() - timedelta(hours=1)
    # overtime: completed 30 min after due
    t.completed_at     = datetime.utcnow() + timedelta(minutes=30 if overtime else -30)
    return t


def _make_followup(fid="F-001", lead_id="L-001"):
    f = MagicMock()
    f.id      = fid
    f.lead_id = lead_id
    f.created_at = datetime.utcnow() - timedelta(days=3)
    return f


# ── TestBanquetCancellationReasons ────────────────────────────────────────────

class TestBanquetCancellationReasons:

    @pytest.mark.asyncio
    async def test_cancellation_grouped(self):
        """1 cancelled wedding → by_type=[{wedding,count=1}], top=wedding"""
        from src.api.banquet_agent import get_banquet_cancellation_reasons

        order = _make_order(status="cancelled", banquet_type="wedding", deposit_fen=30000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_cancellation_reasons(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 1
        assert result["top_cancel_type"] == "wedding"
        assert result["total_deposit_lost_yuan"] == pytest.approx(300.0)
        assert len(result["by_type"]) == 1

    @pytest.mark.asyncio
    async def test_no_cancellations_returns_empty(self):
        """无取消订单时 by_type 为空"""
        from src.api.banquet_agent import get_banquet_cancellation_reasons

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_cancellation_reasons(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 0
        assert result["by_type"] == []
        assert result["top_cancel_type"] is None


# ── TestQuoteAcceptanceRate ───────────────────────────────────────────────────

class TestQuoteAcceptanceRate:

    @pytest.mark.asyncio
    async def test_acceptance_computed(self):
        """1 won + 1 lost from quoted pool → acceptance_rate=50%"""
        from src.api.banquet_agent import get_quote_acceptance_rate

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="lost")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_quote_acceptance_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_quoted"] == 2
        assert result["won_count"] == 1
        assert result["acceptance_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 acceptance_rate_pct = None"""
        from src.api.banquet_agent import get_quote_acceptance_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_quote_acceptance_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_quoted"] == 0
        assert result["acceptance_rate_pct"] is None


# ── TestStaffOvertimeRate ─────────────────────────────────────────────────────

class TestStaffOvertimeRate:

    @pytest.mark.asyncio
    async def test_overtime_detected(self):
        """1 overtime task → overtime_rate=100%"""
        from src.api.banquet_agent import get_staff_overtime_rate

        task = _make_task(overtime=True)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_overtime_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 1
        assert result["overtime_count"] == 1
        assert result["overtime_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        """无已完成任务时 overtime_rate_pct = None"""
        from src.api.banquet_agent import get_staff_overtime_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_overtime_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_completed"] == 0
        assert result["overtime_rate_pct"] is None


# ── TestPackageRevenueContribution ────────────────────────────────────────────

class TestPackageRevenueContribution:

    @pytest.mark.asyncio
    async def test_contribution_computed(self):
        """1 pkg order(300000) + 1 no-pkg(100000) → pkg_rev_pct=75%"""
        from src.api.banquet_agent import get_package_revenue_contribution

        o_pkg    = _make_order(oid="O-001", total_fen=300000, package_id="PKG-001")
        o_no_pkg = _make_order(oid="O-002", total_fen=100000, package_id=None)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o_pkg, o_no_pkg]))

        result = await get_package_revenue_contribution(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["pkg_orders"] == 1
        assert result["pkg_revenue_pct"] == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 pkg_revenue_pct = None"""
        from src.api.banquet_agent import get_package_revenue_contribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_package_revenue_contribution(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["pkg_revenue_pct"] is None


# ── TestCustomerChurnRisk ─────────────────────────────────────────────────────

class TestCustomerChurnRisk:

    @pytest.mark.asyncio
    async def test_churn_detected(self):
        """C-001 with no recent order → at_risk=1, churn_risk=100%"""
        from src.api.banquet_agent import get_customer_churn_risk

        customer = _make_customer(cid="C-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([customer])
            return _scalars_returning([])  # no recent orders

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_customer_churn_risk(store_id="S001", inactive_months=6, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["at_risk_count"] == 1
        assert result["churn_risk_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_customers_returns_none(self):
        """无客户时 churn_risk_pct = None"""
        from src.api.banquet_agent import get_customer_churn_risk

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_churn_risk(store_id="S001", inactive_months=6, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["churn_risk_pct"] is None


# ── TestHallRevenuePerSqm ─────────────────────────────────────────────────────

class TestHallRevenuePerSqm:

    @pytest.mark.asyncio
    async def test_rev_per_sqm_computed(self):
        """200m² hall + order 300000fen → rev_per_sqm = 15.0元"""
        from src.api.banquet_agent import get_hall_revenue_per_sqm

        hall    = _make_hall(floor_area_m2=200.0)
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_revenue_per_sqm(store_id="S001", months=12, db=db, _=_mock_user())

        assert len(result["halls"]) == 1
        assert result["halls"][0]["revenue_per_sqm"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_revenue_per_sqm

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_per_sqm(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["top_hall"] is None


# ── TestLeadNurtureEffectiveness ──────────────────────────────────────────────

class TestLeadNurtureEffectiveness:

    @pytest.mark.asyncio
    async def test_nurture_win_rate_higher(self):
        """nurtured lead (won) + bare lead (lost) → nurtured_win=100%, bare_win=0%"""
        from src.api.banquet_agent import get_lead_nurture_effectiveness

        l_nurtured = _make_lead(lid="L-001", stage="won")
        l_bare     = _make_lead(lid="L-002", stage="lost")
        followup   = _make_followup(lead_id="L-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([l_nurtured, l_bare])
            if call_n[0] == 2: return _scalars_returning([followup])
            return _scalars_returning([])  # no followup for l_bare

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_nurture_effectiveness(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["nurtured_win_rate_pct"] == pytest.approx(100.0)
        assert result["non_nurtured_win_rate_pct"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 nurtured_win_rate_pct = None"""
        from src.api.banquet_agent import get_lead_nurture_effectiveness

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_nurture_effectiveness(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["nurtured_win_rate_pct"] is None


# ── TestBanquetDayOfWeekPattern ───────────────────────────────────────────────

class TestBanquetDayOfWeekPattern:

    @pytest.mark.asyncio
    async def test_weekday_pattern_computed(self):
        """order on Saturday (weekday=5) → peak_weekday=周六"""
        from src.api.banquet_agent import get_banquet_day_of_week_pattern

        sat_date = date(2026, 3, 7)  # Known Saturday
        order = _make_order(banquet_date=sat_date, total_fen=500000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_day_of_week_pattern(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["peak_weekday"] == "周六"
        sat_row = next(r for r in result["by_weekday"] if r["weekday"] == "周六")
        assert sat_row["order_count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 by_weekday 为空"""
        from src.api.banquet_agent import get_banquet_day_of_week_pattern

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_day_of_week_pattern(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["by_weekday"] == []
        assert result["peak_weekday"] is None
