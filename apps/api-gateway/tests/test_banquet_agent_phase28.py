"""
Banquet Agent Phase 28 — 单元测试

覆盖端点：
  - get_seasonal_revenue_pattern
  - get_hall_occupancy_forecast
  - get_staff_exception_rate
  - get_customer_lifetime_value
  - get_banquet_size_revenue_correlation
  - get_follow_up_effectiveness
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


def _make_kpi(stat_date=None, revenue_fen=400000):
    k = MagicMock()
    k.stat_date   = stat_date or date.today()
    k.revenue_fen = revenue_fen
    k.order_count = 5
    k.lead_count  = 12
    k.gross_profit_fen    = 120000
    k.conversion_rate_pct = 30.0
    k.hall_utilization_pct = 60.0
    return k


def _make_order(oid="O-001", total_fen=300000, table_count=10,
                banquet_type="wedding", banquet_date=None,
                status="confirmed", customer_id="C-001"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.paid_fen         = total_fen
    o.contact_name     = "张三"
    status_map = {
        "confirmed": OrderStatusEnum.CONFIRMED,
        "completed": OrderStatusEnum.COMPLETED,
        "cancelled": OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_exception(eid="E-001", owner="U-001", status="open"):
    e = MagicMock()
    e.id              = eid
    e.owner_user_id   = owner
    e.exception_type  = "late"
    e.severity        = "medium"
    e.status          = status
    e.created_at      = datetime.utcnow() - timedelta(days=5)
    return e


def _make_customer(cid="C-001", total_fen=600000, count=3):
    c = MagicMock()
    c.id                       = cid
    c.total_banquet_amount_fen = total_fen
    c.total_banquet_count      = count
    c.vip_level                = 1
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


def _make_lead(lid="L-001", stage="signed", source="微信"):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id              = lid
    l.source_channel  = source
    l.current_stage   = LeadStageEnum(stage) if stage in [e.value for e in LeadStageEnum] else MagicMock(value=stage)
    l.expected_budget_fen = 200000
    l.created_at      = datetime.utcnow() - timedelta(days=20)
    l.updated_at      = datetime.utcnow() - timedelta(days=3)
    return l


def _make_followup(fid="F-001", lead_id="L-001"):
    f = MagicMock()
    f.id         = fid
    f.lead_id    = lead_id
    f.created_at = datetime.utcnow() - timedelta(days=10)
    return f


# ── TestSeasonalRevenuePattern ────────────────────────────────────────────────

class TestSeasonalRevenuePattern:

    @pytest.mark.asyncio
    async def test_monthly_pattern_returned(self):
        """有KPI数据时 monthly_pattern 包含12条，peak_month 不为空"""
        from src.api.banquet_agent import get_seasonal_revenue_pattern

        kpi = _make_kpi(stat_date=date(date.today().year, 6, 15), revenue_fen=500000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([kpi]))

        result = await get_seasonal_revenue_pattern(store_id="S001", years=1, db=db, _=_mock_user())

        assert len(result["monthly_pattern"]) == 12
        assert result["peak_month"] == 6
        june = next(r for r in result["monthly_pattern"] if r["month"] == 6)
        assert june["is_peak"] is True
        assert june["avg_revenue_yuan"] == pytest.approx(5000.0)

    @pytest.mark.asyncio
    async def test_no_kpi_returns_zero_avgs(self):
        """无KPI时所有月份 avg_revenue_yuan == 0"""
        from src.api.banquet_agent import get_seasonal_revenue_pattern

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_seasonal_revenue_pattern(store_id="S001", years=1, db=db, _=_mock_user())

        assert len(result["monthly_pattern"]) == 12
        assert all(r["avg_revenue_yuan"] == 0.0 for r in result["monthly_pattern"])


# ── TestHallOccupancyForecast ──────────────────────────────────────────────────

class TestHallOccupancyForecast:

    @pytest.mark.asyncio
    async def test_occupancy_pct_computed(self):
        """1厅 + 1未来预订 → booked_days=1, occupancy_pct 正确"""
        from src.api.banquet_agent import get_hall_occupancy_forecast

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(
            oid="O-001", status="confirmed",
            banquet_date=date.today() + timedelta(days=5),
        )

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([hall])
            if call_n[0] == 2: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_occupancy_forecast(
            store_id="S001", days_ahead=30, db=db, _=_mock_user()
        )

        assert len(result["halls"]) == 1
        h = result["halls"][0]
        assert h["booked_days"] == 1
        assert h["occupancy_pct"] == pytest.approx(1 / 30 * 100, abs=0.2)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_hall_occupancy_forecast

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_occupancy_forecast(
            store_id="S001", days_ahead=30, db=db, _=_mock_user()
        )

        assert result["halls"] == []
        assert result["overall_occupancy_pct"] is None


# ── TestStaffExceptionRate ────────────────────────────────────────────────────

class TestStaffExceptionRate:

    @pytest.mark.asyncio
    async def test_resolution_rate_per_staff(self):
        """1 resolved exception → resolution_rate_pct = 100"""
        from src.api.banquet_agent import get_staff_exception_rate

        exc = _make_exception(owner="U-001", status="resolved")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([exc]))

        result = await get_staff_exception_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_exceptions"] == 1
        assert result["total_resolved"] == 1
        assert result["overall_resolution_rate_pct"] == pytest.approx(100.0)
        assert len(result["by_staff"]) == 1

    @pytest.mark.asyncio
    async def test_no_exceptions_returns_none_rate(self):
        """无异常时 overall_resolution_rate_pct = None"""
        from src.api.banquet_agent import get_staff_exception_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_exception_rate(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_exceptions"] == 0
        assert result["overall_resolution_rate_pct"] is None


# ── TestCustomerLifetimeValue ─────────────────────────────────────────────────

class TestCustomerLifetimeValue:

    @pytest.mark.asyncio
    async def test_ltv_computed_correctly(self):
        """600000分 → ltv=6000元，avg_ltv == 6000"""
        from src.api.banquet_agent import get_customer_lifetime_value

        c = _make_customer(total_fen=600000, count=3)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c]))

        result = await get_customer_lifetime_value(store_id="S001", top_n=20, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["avg_ltv_yuan"] == pytest.approx(6000.0)
        assert result["top"][0]["ltv_yuan"] == pytest.approx(6000.0)

    @pytest.mark.asyncio
    async def test_no_customers_returns_none(self):
        """无客户时 avg_ltv_yuan = None"""
        from src.api.banquet_agent import get_customer_lifetime_value

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_lifetime_value(store_id="S001", top_n=20, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["avg_ltv_yuan"] is None


# ── TestBanquetSizeRevenueCorrelation ─────────────────────────────────────────

class TestBanquetSizeRevenueCorrelation:

    @pytest.mark.asyncio
    async def test_size_group_classified(self):
        """15桌订单 → 中型组，avg_per_table 正确"""
        from src.api.banquet_agent import get_banquet_size_revenue_correlation

        o = _make_order(total_fen=300000, table_count=15, status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_banquet_size_revenue_correlation(
            store_id="S001", months=12, db=db, _=_mock_user()
        )

        assert result["total_orders"] == 1
        mid = next(g for g in result["size_groups"] if "11-20" in g["label"])
        assert mid["order_count"] == 1
        assert mid["avg_per_table_yuan"] == pytest.approx(200.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty_groups(self):
        """无订单时 total_orders == 0，inflection_point = None"""
        from src.api.banquet_agent import get_banquet_size_revenue_correlation

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_size_revenue_correlation(
            store_id="S001", months=12, db=db, _=_mock_user()
        )

        assert result["total_orders"] == 0
        assert result["inflection_point"] is None


# ── TestFollowUpEffectiveness ─────────────────────────────────────────────────

class TestFollowUpEffectiveness:

    @pytest.mark.asyncio
    async def test_optimal_bucket_found(self):
        """1 lead + 2 followups + signed → 2-3次桶 win_rate=100"""
        from src.api.banquet_agent import get_follow_up_effectiveness

        lead = _make_lead(stage="signed")
        f1   = _make_followup(fid="F-001", lead_id=lead.id)
        f2   = _make_followup(fid="F-002", lead_id=lead.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([lead])
            return _scalars_returning([f1, f2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_follow_up_effectiveness(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["optimal_followup_bucket"] == "2-3次"
        row = next(r for r in result["rows"] if r["followup_bucket"] == "2-3次")
        assert row["win_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 rows 为空"""
        from src.api.banquet_agent import get_follow_up_effectiveness

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_follow_up_effectiveness(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["rows"] == []
        assert result["optimal_followup_bucket"] is None
