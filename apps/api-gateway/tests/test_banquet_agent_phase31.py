"""
Banquet Agent Phase 31 — 单元测试

覆盖端点：
  - get_quote_turnaround_time
  - get_deposit_to_full_payment_days
  - get_hall_booking_gap
  - get_contract_signed_rate
  - get_staff_task_overdue_rate
  - get_monthly_new_vs_repeat
  - get_lead_response_speed
  - get_banquet_day_weather_impact
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
    o.created_at       = created_at or (datetime.utcnow() - timedelta(days=60))
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


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


def _make_lead(lid="L-001", stage="quoted", source="微信",
               created_days_ago=20, updated_days_ago=5):
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
    l.created_at  = datetime.utcnow() - timedelta(days=created_days_ago)
    l.updated_at  = datetime.utcnow() - timedelta(days=updated_days_ago)
    return l


def _make_task(tid="T-001", owner="U-001", status="overdue"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id            = tid
    t.owner_user_id = owner
    t.task_status   = TaskStatusEnum(status)
    t.created_at    = datetime.utcnow() - timedelta(days=10)
    return t


def _make_payment(pid="P-001", order_id="O-001", amount_fen=50000, days_ago=0):
    p = MagicMock()
    p.id                 = pid
    p.banquet_order_id   = order_id
    p.amount_fen         = amount_fen
    p.created_at         = datetime.utcnow() - timedelta(days=days_ago)
    return p


def _make_contract(cid="C-001", order_id="O-001"):
    c = MagicMock()
    c.id                = cid
    c.banquet_order_id  = order_id
    return c


def _make_followup(fid="F-001", lead_id="L-001", hours_after_lead=1):
    f = MagicMock()
    f.id      = fid
    f.lead_id = lead_id
    f.created_at = datetime.utcnow()
    return f


# ── TestQuoteTurnaroundTime ───────────────────────────────────────────────────

class TestQuoteTurnaroundTime:

    @pytest.mark.asyncio
    async def test_avg_days_computed(self):
        """quoted lead updated 5 days after create → avg_days=5"""
        from src.api.banquet_agent import get_quote_turnaround_time

        lead = _make_lead(stage="quoted", created_days_ago=10, updated_days_ago=5)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_quote_turnaround_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["quoted_leads"] == 1
        assert result["avg_days"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_days = None"""
        from src.api.banquet_agent import get_quote_turnaround_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_quote_turnaround_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_days"] is None
        assert result["buckets"] == []


# ── TestDepositToFullPaymentDays ──────────────────────────────────────────────

class TestDepositToFullPaymentDays:

    @pytest.mark.asyncio
    async def test_avg_days_computed(self):
        """2 payments: first 30 days ago, last today → diff=30 → 8-30天桶"""
        from src.api.banquet_agent import get_deposit_to_full_payment_days

        order = _make_order(paid_fen=300000, total_fen=300000)
        pay1  = _make_payment(pid="P-001", order_id=order.id, days_ago=30)
        pay2  = _make_payment(pid="P-002", order_id=order.id, days_ago=0)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pay1, pay2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_deposit_to_full_payment_days(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 1
        assert result["avg_days"] == pytest.approx(30.0)
        bucket = next(b for b in result["buckets"] if b["bucket"] == "8-30天")
        assert bucket["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无全额付款订单时 avg_days = None"""
        from src.api.banquet_agent import get_deposit_to_full_payment_days

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_to_full_payment_days(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_fully_paid"] == 0
        assert result["avg_days"] is None


# ── TestHallBookingGap ────────────────────────────────────────────────────────

class TestHallBookingGap:

    @pytest.mark.asyncio
    async def test_gap_computed(self):
        """2 bookings 7 days apart → avg_gap_days=7"""
        from src.api.banquet_agent import get_hall_booking_gap

        hall = _make_hall()
        bk1  = _make_booking(bid="B-001", hall_id=hall.id, order_id="O-001")
        bk2  = _make_booking(bid="B-002", hall_id=hall.id, order_id="O-002")
        o1   = _make_order(oid="O-001", banquet_date=date.today() - timedelta(days=14))
        o2   = _make_order(oid="O-002", banquet_date=date.today() - timedelta(days=7))

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([bk1, bk2])
            if call_n[0] == 3: return _scalars_returning([o1])
            return _scalars_returning([o2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_booking_gap(store_id="S001", months=3, db=db, _=_mock_user())

        assert len(result["halls"]) == 1
        assert result["halls"][0]["avg_gap_days"] == pytest.approx(7.0)
        assert result["overall_avg_gap_days"] == pytest.approx(7.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_booking_gap

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_booking_gap(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["overall_avg_gap_days"] is None


# ── TestContractSignedRate ────────────────────────────────────────────────────

class TestContractSignedRate:

    @pytest.mark.asyncio
    async def test_contract_rate_computed(self):
        """1 order with contract → contract_rate_pct = 100"""
        from src.api.banquet_agent import get_contract_signed_rate

        order    = _make_order()
        contract = _make_contract(order_id=order.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([contract])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_contract_signed_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["with_contract"] == 1
        assert result["contract_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 contract_rate_pct = None"""
        from src.api.banquet_agent import get_contract_signed_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_contract_signed_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["contract_rate_pct"] is None


# ── TestStaffTaskOverdueRate ──────────────────────────────────────────────────

class TestStaffTaskOverdueRate:

    @pytest.mark.asyncio
    async def test_overdue_rate_computed(self):
        """1 overdue task for U-001 → overdue_rate_pct = 100"""
        from src.api.banquet_agent import get_staff_task_overdue_rate

        task = _make_task(owner="U-001", status="overdue")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_task_overdue_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 1
        assert result["overdue_tasks"] == 1
        assert result["overall_overdue_rate_pct"] == pytest.approx(100.0)
        assert result["by_staff"][0]["user_id"] == "U-001"

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none_rate(self):
        """无任务时 overall_overdue_rate_pct = None"""
        from src.api.banquet_agent import get_staff_task_overdue_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_task_overdue_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_tasks"] == 0
        assert result["overall_overdue_rate_pct"] is None


# ── TestMonthlyNewVsRepeat ────────────────────────────────────────────────────

class TestMonthlyNewVsRepeat:

    @pytest.mark.asyncio
    async def test_new_vs_repeat_split(self):
        """同一客户 2 笔订单 → 第1笔new, 第2笔repeat"""
        from src.api.banquet_agent import get_monthly_new_vs_repeat

        month_ago = date.today().replace(day=1) - timedelta(days=1)
        first_day = month_ago.replace(day=1)
        o1 = _make_order(oid="O-001", customer_id="C-001",
                         banquet_date=first_day, total_fen=200000)
        o2 = _make_order(oid="O-002", customer_id="C-001",
                         banquet_date=first_day + timedelta(days=5),
                         total_fen=200000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_monthly_new_vs_repeat(store_id="S001", months=12, db=db, _=_mock_user())

        assert len(result["monthly"]) >= 1
        total_new = sum(m["new_orders"] for m in result["monthly"])
        total_rep = sum(m["repeat_orders"] for m in result["monthly"])
        assert total_new == 1
        assert total_rep == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 monthly 为空"""
        from src.api.banquet_agent import get_monthly_new_vs_repeat

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_monthly_new_vs_repeat(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["monthly"] == []


# ── TestLeadResponseSpeed ─────────────────────────────────────────────────────

class TestLeadResponseSpeed:

    @pytest.mark.asyncio
    async def test_response_speed_computed(self):
        """lead created 2h before followup → avg_response_hours=2, fast_response=100%"""
        from src.api.banquet_agent import get_lead_response_speed

        lead = _make_lead()
        fu   = MagicMock()
        fu.id       = "F-001"
        fu.lead_id  = lead.id
        fu.created_at = lead.created_at + timedelta(hours=1)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([fu])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_response_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["responded_leads"] == 1
        assert result["avg_response_hours"] == pytest.approx(1.0, abs=0.1)
        assert result["fast_response_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_response_hours = None"""
        from src.api.banquet_agent import get_lead_response_speed

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_response_speed(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_response_hours"] is None


# ── TestBanquetDayWeatherImpact ───────────────────────────────────────────────

class TestBanquetDayWeatherImpact:

    @pytest.mark.asyncio
    async def test_high_risk_months_identified(self):
        """month 7 has 100% cancel vs month 1 has 0% → avg=50%, month 7 in high_risk"""
        from src.api.banquet_agent import get_banquet_day_weather_impact

        o_cancelled = _make_order(
            oid="O-001",
            banquet_date=date(date.today().year - 1, 7, 15),
            status="cancelled",
        )
        o_confirmed = _make_order(
            oid="O-002",
            banquet_date=date(date.today().year - 1, 1, 15),
            status="confirmed",
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o_cancelled, o_confirmed]))

        result = await get_banquet_day_weather_impact(store_id="S001", months=12, db=db, _=_mock_user())

        assert len(result["by_month"]) == 12
        assert 7 in result["high_risk_months"]

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 by_month 全为0，high_risk_months 为空"""
        from src.api.banquet_agent import get_banquet_day_weather_impact

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_day_weather_impact(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["by_month"] == []
        assert result["high_risk_months"] == []
