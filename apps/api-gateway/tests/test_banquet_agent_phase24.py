"""
Banquet Agent Phase 24 — 单元测试

覆盖端点：
  - get_year_over_year
  - get_annual_summary
  - get_active_alerts
  - get_banquet_type_trend
  - get_pricing_ladder
  - get_customer_frequency
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


def _make_kpi(stat_date=None, revenue_fen=300000, order_count=4,
              lead_count=8, gross_profit_fen=90000,
              conversion_rate_pct=30.0, hall_utilization_pct=60.0):
    k = MagicMock()
    k.stat_date             = stat_date or date.today()
    k.revenue_fen           = revenue_fen
    k.order_count           = order_count
    k.lead_count            = lead_count
    k.gross_profit_fen      = gross_profit_fen
    k.conversion_rate_pct   = conversion_rate_pct
    k.hall_utilization_pct  = hall_utilization_pct
    return k


def _make_order(oid="O-001", total_fen=300000, table_count=10,
                banquet_type="wedding", banquet_date=None, status="confirmed"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.order_status     = OrderStatusEnum.CONFIRMED if status == "confirmed" else OrderStatusEnum.COMPLETED
    return o


def _make_customer(cid="C-001", count=2, total_fen=400000):
    c = MagicMock()
    c.id                       = cid
    c.total_banquet_count      = count
    c.total_banquet_amount_fen = total_fen
    c.vip_level                = 1
    return c


def _make_exception(eid="E-001", status="open", severity="medium", exc_type="late"):
    e = MagicMock()
    e.id             = eid
    e.exception_type = exc_type
    e.severity       = severity
    e.status         = status
    e.description    = "测试异常描述"
    e.created_at     = datetime.utcnow()
    return e


# ── TestYearOverYear ──────────────────────────────────────────────────────────

class TestYearOverYear:

    @pytest.mark.asyncio
    async def test_yoy_metrics_returned(self):
        """有本年和去年KPI时，metrics 包含 revenue 同比"""
        from src.api.banquet_agent import get_year_over_year

        kpi_this = _make_kpi(revenue_fen=600000, order_count=8)
        kpi_last = _make_kpi(revenue_fen=500000, order_count=6)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([kpi_this])
            return _scalars_returning([kpi_last])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_year_over_year(store_id="S001", db=db, _=_mock_user())

        assert "metrics" in result
        rev = next(m for m in result["metrics"] if m["metric"] == "revenue_fen")
        assert rev["this_year"] == pytest.approx(6000.0)
        assert rev["last_year"] == pytest.approx(5000.0)
        assert rev["yoy_pct"]   == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_no_data_returns_zero_metrics(self):
        """无KPI数据时 this_year/last_year 均为 0"""
        from src.api.banquet_agent import get_year_over_year

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_year_over_year(store_id="S001", db=db, _=_mock_user())

        assert "metrics" in result
        rev = next(m for m in result["metrics"] if m["metric"] == "revenue_fen")
        assert rev["this_year"] == 0.0
        assert rev["yoy_pct"] is None


# ── TestAnnualSummary ─────────────────────────────────────────────────────────

class TestAnnualSummary:

    @pytest.mark.asyncio
    async def test_monthly_rows_aggregated(self):
        """KPI 按月聚合，gross_margin_pct 正确"""
        from src.api.banquet_agent import get_annual_summary

        kpi = _make_kpi(
            stat_date=date(date.today().year, 6, 15),
            revenue_fen=400000, gross_profit_fen=120000,
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([kpi]))

        result = await get_annual_summary(store_id="S001", year=0, db=db, _=_mock_user())

        assert len(result["monthly_rows"]) == 1
        row = result["monthly_rows"][0]
        assert row["revenue_yuan"]     == pytest.approx(4000.0)
        assert row["gross_margin_pct"] == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_no_kpi_returns_zero(self):
        """无KPI时 total_revenue_yuan == 0"""
        from src.api.banquet_agent import get_annual_summary

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_annual_summary(store_id="S001", year=0, db=db, _=_mock_user())

        assert result["total_revenue_yuan"] == 0.0
        assert result["monthly_rows"] == []


# ── TestActiveAlerts ──────────────────────────────────────────────────────────

class TestActiveAlerts:

    @pytest.mark.asyncio
    async def test_open_exception_appears_in_alerts(self):
        """open 状态的异常 → 出现在 alerts 中"""
        from src.api.banquet_agent import get_active_alerts

        exc = _make_exception(status="open", severity="high")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([exc])   # exceptions
            if call_n[0] == 2: return _scalars_returning([])       # overdue tasks
            return _scalars_returning([])                           # stale leads

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_active_alerts(store_id="S001", db=db, _=_mock_user())

        assert result["total"] >= 1
        assert result["alerts"][0]["type"] == "exception"

    @pytest.mark.asyncio
    async def test_no_alerts_returns_empty(self):
        """无异常/逾期/停滞时 alerts 为空"""
        from src.api.banquet_agent import get_active_alerts

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_active_alerts(store_id="S001", db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["alerts"] == []


# ── TestBanquetTypeTrend ──────────────────────────────────────────────────────

class TestBanquetTypeTrend:

    @pytest.mark.asyncio
    async def test_series_grouped_by_type(self):
        """订单按类型分组，series 中有 wedding"""
        from src.api.banquet_agent import get_banquet_type_trend

        o = _make_order(banquet_type="wedding", banquet_date=date(2025, 10, 5))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_banquet_type_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert "series" in result
        types = [s["type"] for s in result["series"]]
        assert "wedding" in types

    @pytest.mark.asyncio
    async def test_empty_orders_returns_empty_series(self):
        """无订单时 series 为空"""
        from src.api.banquet_agent import get_banquet_type_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["series"] == []


# ── TestPricingLadder ─────────────────────────────────────────────────────────

class TestPricingLadder:

    @pytest.mark.asyncio
    async def test_median_computed_correctly(self):
        """20桌 300000分 → 桌单价=15000分=150元 → 经济型桶"""
        from src.api.banquet_agent import get_pricing_ladder

        o = _make_order(total_fen=300000, table_count=20)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_pricing_ladder(store_id="S001", db=db, _=_mock_user())

        assert result["total"] == 1
        assert result["median_yuan"] == pytest.approx(150.0)
        econ = next(b for b in result["buckets"] if "经济型" in b["label"])
        assert econ["count"] == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none_median(self):
        """无订单时 median_yuan = None"""
        from src.api.banquet_agent import get_pricing_ladder

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_pricing_ladder(store_id="S001", db=db, _=_mock_user())

        assert result["median_yuan"] is None


# ── TestCustomerFrequency ─────────────────────────────────────────────────────

class TestCustomerFrequency:

    @pytest.mark.asyncio
    async def test_frequency_buckets_correct(self):
        """count=2 → 落入「2-3次」桶"""
        from src.api.banquet_agent import get_customer_frequency

        c = _make_customer(count=2, total_fen=400000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c]))

        result = await get_customer_frequency(store_id="S001", db=db, _=_mock_user())

        assert result["total"] == 1
        b = next(x for x in result["buckets"] if "2-3" in x["label"])
        assert b["customer_count"] == 1
        assert b["pct"]            == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_customers_returns_empty(self):
        """无客户时 buckets 为空"""
        from src.api.banquet_agent import get_customer_frequency

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_frequency(store_id="S001", db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["buckets"] == []
