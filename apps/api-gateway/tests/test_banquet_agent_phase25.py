"""
Banquet Agent Phase 25 — 单元测试

覆盖端点：
  - get_period_comparison
  - get_lead_weekly_funnel
  - get_top_spenders
  - get_task_completion_trend
  - get_quote_conversion
  - get_deposit_risk
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
              conversion_rate_pct=30.0):
    k = MagicMock()
    k.stat_date            = stat_date or date.today()
    k.revenue_fen          = revenue_fen
    k.order_count          = order_count
    k.lead_count           = lead_count
    k.gross_profit_fen     = gross_profit_fen
    k.conversion_rate_pct  = conversion_rate_pct
    k.hall_utilization_pct = 60.0
    return k


def _make_order(oid="O-001", total_fen=300000, deposit_fen=30000,
                paid_fen=30000, table_count=10,
                banquet_type="wedding", banquet_date=None,
                status="confirmed", customer_id="C-001"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.deposit_fen      = deposit_fen
    o.paid_fen         = paid_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() + timedelta(days=30))
    o.order_status     = OrderStatusEnum.CONFIRMED if status == "confirmed" else OrderStatusEnum.COMPLETED
    o.customer_id      = customer_id
    o.contact_name     = "张三"
    return o


def _make_customer(cid="C-001", total_fen=500000, count=3, name="张三"):
    c = MagicMock()
    c.id                       = cid
    c.name                     = name
    c.phone                    = "138-0000-0001"
    c.total_banquet_amount_fen = total_fen
    c.total_banquet_count      = count
    c.vip_level                = 1
    return c


def _make_lead(lid="L-001", stage="quoted", source_channel="微信"):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id              = lid
    l.current_stage   = LeadStageEnum(stage) if hasattr(LeadStageEnum, stage) else MagicMock(value=stage)
    l.source_channel  = source_channel
    l.expected_budget_fen = 200000
    l.created_at      = datetime.utcnow() - timedelta(days=10)
    return l


def _make_task(tid="T-001", status="done"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id          = tid
    t.task_status = TaskStatusEnum(status)
    t.created_at  = datetime.utcnow() - timedelta(days=3)
    return t


# ── TestPeriodComparison ──────────────────────────────────────────────────────

class TestPeriodComparison:

    @pytest.mark.asyncio
    async def test_metrics_returned_for_both_periods(self):
        """两期都有KPI时，metrics 包含 revenue_yuan 且 delta_pct 正确"""
        from src.api.banquet_agent import get_period_comparison

        kpi_a = _make_kpi(revenue_fen=600000, order_count=8, lead_count=20)
        kpi_b = _make_kpi(revenue_fen=400000, order_count=5, lead_count=20)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([kpi_a])
            return _scalars_returning([kpi_b])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        today = date.today()
        result = await get_period_comparison(
            store_id="S001",
            period_a_start=(today - timedelta(days=60)).isoformat(),
            period_a_end=(today - timedelta(days=31)).isoformat(),
            period_b_start=(today - timedelta(days=120)).isoformat(),
            period_b_end=(today - timedelta(days=91)).isoformat(),
            db=db, _=_mock_user(),
        )

        assert "metrics" in result
        rev = next(m for m in result["metrics"] if m["metric"] == "revenue_yuan")
        assert rev["period_a"] == pytest.approx(6000.0)
        assert rev["period_b"] == pytest.approx(4000.0)
        assert rev["delta_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_data_returns_zero_metrics(self):
        """无KPI数据时两期均为0"""
        from src.api.banquet_agent import get_period_comparison

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        today = date.today()
        result = await get_period_comparison(
            store_id="S001",
            period_a_start=(today - timedelta(days=60)).isoformat(),
            period_a_end=(today - timedelta(days=31)).isoformat(),
            period_b_start=(today - timedelta(days=120)).isoformat(),
            period_b_end=(today - timedelta(days=91)).isoformat(),
            db=db, _=_mock_user(),
        )

        assert "metrics" in result
        rev = next(m for m in result["metrics"] if m["metric"] == "revenue_yuan")
        assert rev["period_a"] == pytest.approx(0.0)
        assert rev["period_b"] == pytest.approx(0.0)


# ── TestLeadWeeklyFunnel ──────────────────────────────────────────────────────

class TestLeadWeeklyFunnel:

    @pytest.mark.asyncio
    async def test_lead_grouped_by_week(self):
        """有线索时 series 非空，total_leads 正确"""
        from src.api.banquet_agent import get_lead_weekly_funnel

        lead = _make_lead()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_weekly_funnel(store_id="S001", weeks=8, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert len(result["series"]) >= 1

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty_series(self):
        """无线索时 series 为空"""
        from src.api.banquet_agent import get_lead_weekly_funnel

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_weekly_funnel(store_id="S001", weeks=8, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["series"] == []


# ── TestTopSpenders ───────────────────────────────────────────────────────────

class TestTopSpenders:

    @pytest.mark.asyncio
    async def test_ranking_by_total_yuan(self):
        """有客户+订单时 ranking 包含正确 total_yuan"""
        from src.api.banquet_agent import get_top_spenders

        customer = _make_customer(total_fen=600000)
        order    = _make_order(total_fen=600000, customer_id=customer.id,
                               status="confirmed")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([customer])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_top_spenders(store_id="S001", months=12, top_n=20, db=db, _=_mock_user())

        assert result["total"] == 1
        assert result["ranking"][0]["total_yuan"] == pytest.approx(6000.0)

    @pytest.mark.asyncio
    async def test_no_customers_returns_empty(self):
        """无客户时 ranking 为空"""
        from src.api.banquet_agent import get_top_spenders

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_top_spenders(store_id="S001", months=12, top_n=20, db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["ranking"] == []


# ── TestTaskCompletionTrend ───────────────────────────────────────────────────

class TestTaskCompletionTrend:

    @pytest.mark.asyncio
    async def test_completion_rate_computed(self):
        """1个completed任务 → avg_completion_rate_pct = 100"""
        from src.api.banquet_agent import get_task_completion_trend

        task = _make_task(status="done")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_task_completion_trend(store_id="S001", weeks=8, db=db, _=_mock_user())

        assert result["total_tasks"] == 1
        assert result["total_completed"] == 1
        assert result["avg_completion_rate_pct"] == pytest.approx(100.0)
        assert len(result["series"]) >= 1

    @pytest.mark.asyncio
    async def test_no_tasks_returns_zero(self):
        """无任务时 avg_completion_rate_pct == 0"""
        from src.api.banquet_agent import get_task_completion_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_task_completion_trend(store_id="S001", weeks=8, db=db, _=_mock_user())

        assert result["total_tasks"] == 0
        assert result["avg_completion_rate_pct"] == pytest.approx(0.0)
        assert result["series"] == []


# ── TestQuoteConversion ───────────────────────────────────────────────────────

class TestQuoteConversion:

    @pytest.mark.asyncio
    async def test_win_rate_computed(self):
        """1 quoted lead with stage=signed → win_rate_pct = 100"""
        from src.api.banquet_agent import get_quote_conversion
        from src.models.banquet import LeadStageEnum

        lead = MagicMock()
        lead.current_stage = LeadStageEnum("signed") if "signed" in [e.value for e in LeadStageEnum] else MagicMock(value="signed")
        lead.expected_budget_fen = 200000
        lead.created_at = datetime.utcnow() - timedelta(days=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_quote_conversion(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["quoted_leads"] == 1
        assert result["won_count"] == 1
        assert result["win_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none_win_rate(self):
        """无报价线索时 win_rate_pct = None"""
        from src.api.banquet_agent import get_quote_conversion

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_quote_conversion(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["quoted_leads"] == 0
        assert result["win_rate_pct"] is None


# ── TestDepositRisk ───────────────────────────────────────────────────────────

class TestDepositRisk:

    @pytest.mark.asyncio
    async def test_low_deposit_order_flagged(self):
        """定金比例10% < 30% → 列入 items"""
        from src.api.banquet_agent import get_deposit_risk

        # deposit=30000, total=300000 → 10%
        o = _make_order(total_fen=300000, deposit_fen=30000,
                        banquet_date=date.today() + timedelta(days=20))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_deposit_risk(store_id="S001", min_risk_pct=30.0, db=db, _=_mock_user())

        assert result["risky_count"] == 1
        assert result["items"][0]["deposit_ratio_pct"] == pytest.approx(10.0)
        assert result["total_exposed_yuan"] == pytest.approx(2700.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 risky_count == 0"""
        from src.api.banquet_agent import get_deposit_risk

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_risk(store_id="S001", min_risk_pct=30.0, db=db, _=_mock_user())

        assert result["risky_count"] == 0
        assert result["items"] == []
        assert result["total_exposed_yuan"] == pytest.approx(0.0)
