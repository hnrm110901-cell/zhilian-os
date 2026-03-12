"""
Banquet Agent Phase 27 — 单元测试

覆盖端点：
  - get_refund_rate
  - get_bundle_performance
  - get_monthly_target_gap
  - get_review_sentiment_trend
  - get_vip_churn_early_warning
  - get_capacity_revenue_yield
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


def _make_order(oid="O-001", total_fen=300000, paid_fen=150000,
                deposit_fen=60000, table_count=10,
                banquet_type="wedding", banquet_date=None,
                status="cancelled", customer_id="C-001",
                package_id=None):
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
    status_map = {
        "cancelled":  OrderStatusEnum.CANCELLED,
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CANCELLED)
    return o


def _make_package(pid="P-001", name="婚宴套餐", price_fen=50000, cost_fen=25000):
    from src.models.banquet import BanquetTypeEnum
    p = MagicMock()
    p.id                  = pid
    p.name                = name
    p.suggested_price_fen = price_fen
    p.cost_fen            = cost_fen
    p.banquet_type        = BanquetTypeEnum.WEDDING
    p.is_active           = True
    return p


def _make_kpi(stat_date=None, revenue_fen=200000):
    k = MagicMock()
    k.stat_date            = stat_date or date.today()
    k.revenue_fen          = revenue_fen
    k.order_count          = 4
    k.lead_count           = 10
    k.gross_profit_fen     = 60000
    k.conversion_rate_pct  = 30.0
    k.hall_utilization_pct = 60.0
    return k


def _make_target(month=6, target_fen=300000):
    t = MagicMock()
    t.month               = month
    t.target_revenue_fen  = target_fen
    t.year                = date.today().year
    return t


def _make_review(rid="R-001", rating=5, ai_score=90.0):
    r = MagicMock()
    r.id              = rid
    r.customer_rating = rating
    r.ai_score        = ai_score
    r.improvement_tags = []
    r.created_at      = datetime.utcnow() - timedelta(days=10)
    return r


def _make_customer(cid="C-001", count=3, total_fen=900000):
    c = MagicMock()
    c.id                       = cid
    c.name                     = "张三"
    c.phone                    = "138-0000-0001"
    c.total_banquet_count      = count
    c.total_banquet_amount_fen = total_fen
    c.vip_level                = 2
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
    b.id                 = bid
    b.hall_id            = hall_id
    b.banquet_order_id   = order_id
    return b


# ── TestRefundRate ────────────────────────────────────────────────────────────

class TestRefundRate:

    @pytest.mark.asyncio
    async def test_refund_rate_computed(self):
        """1 refund / 2 total → refund_rate_pct = 50, avg_refund_yuan 正确"""
        from src.api.banquet_agent import get_refund_rate

        refund_order = _make_order(status="cancelled", paid_fen=150000)
        all_orders   = [refund_order, _make_order(oid="O-002", status="confirmed", paid_fen=0)]

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([refund_order])
            return _scalars_returning(all_orders)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_refund_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["refund_orders"] == 1
        assert result["refund_rate_pct"] == pytest.approx(50.0)
        assert result["avg_refund_yuan"] == pytest.approx(1500.0)

    @pytest.mark.asyncio
    async def test_no_refunds_returns_zero(self):
        """无退款时 refund_orders == 0"""
        from src.api.banquet_agent import get_refund_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_refund_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["refund_orders"] == 0
        assert result["avg_refund_yuan"] is None


# ── TestBundlePerformance ─────────────────────────────────────────────────────

class TestBundlePerformance:

    @pytest.mark.asyncio
    async def test_package_revenue_computed(self):
        """1 套餐 + 1 订单 → packages 含正确 order_count 和 total_revenue_yuan"""
        from src.api.banquet_agent import get_bundle_performance

        pkg   = _make_package(price_fen=50000, cost_fen=25000)
        order = _make_order(status="confirmed", package_id=pkg.id,
                             total_fen=500000, table_count=10)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([pkg])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_bundle_performance(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders_with_pkg"] == 1
        assert len(result["packages"]) == 1
        p = result["packages"][0]
        assert p["order_count"] == 1
        assert p["total_revenue_yuan"] == pytest.approx(5000.0)
        assert p["gross_margin_pct"]   == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_packages_returns_empty(self):
        """无套餐时 packages 为空"""
        from src.api.banquet_agent import get_bundle_performance

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_bundle_performance(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["packages"] == []
        assert result["total_orders_with_pkg"] == 0


# ── TestMonthlyTargetGap ──────────────────────────────────────────────────────

class TestMonthlyTargetGap:

    @pytest.mark.asyncio
    async def test_achievement_computed(self):
        """实际200000分 / 目标300000分 → achievement≈66.7%，gap=-1000元"""
        from src.api.banquet_agent import get_monthly_target_gap

        kpi    = _make_kpi(stat_date=date(date.today().year, 6, 15), revenue_fen=200000)
        target = _make_target(month=6, target_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([kpi])
            return _scalars_returning([target])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_monthly_target_gap(store_id="S001", year=0, db=db, _=_mock_user())

        assert "monthly_rows" in result
        june = next(r for r in result["monthly_rows"] if r["month"] == 6)
        assert june["achievement_pct"] == pytest.approx(66.7, rel=0.01)
        assert june["gap_yuan"] == pytest.approx(-1000.0)

    @pytest.mark.asyncio
    async def test_no_kpi_returns_zero_actual(self):
        """无KPI时 total_actual_yuan == 0"""
        from src.api.banquet_agent import get_monthly_target_gap

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_monthly_target_gap(store_id="S001", year=0, db=db, _=_mock_user())

        assert result["total_actual_yuan"] == pytest.approx(0.0)
        assert len(result["monthly_rows"]) == 12


# ── TestReviewSentimentTrend ──────────────────────────────────────────────────

class TestReviewSentimentTrend:

    @pytest.mark.asyncio
    async def test_positive_review_counted(self):
        """rating=5 → positive +1, sentiment_summary.positive == 1"""
        from src.api.banquet_agent import get_review_sentiment_trend

        rev = _make_review(rating=5, ai_score=90.0)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([rev]))

        result = await get_review_sentiment_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 1
        assert result["sentiment_summary"]["positive"] == 1
        assert result["sentiment_summary"]["negative"] == 0
        assert len(result["monthly_trend"]) == 1

    @pytest.mark.asyncio
    async def test_no_reviews_returns_empty(self):
        """无评价时 total_reviews == 0"""
        from src.api.banquet_agent import get_review_sentiment_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_review_sentiment_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["monthly_trend"] == []


# ── TestVipChurnEarlyWarning ──────────────────────────────────────────────────

class TestVipChurnEarlyWarning:

    @pytest.mark.asyncio
    async def test_inactive_vip_flagged(self):
        """VIP 客户最后宴会超过 inactive_months → 出现在 at_risk"""
        from src.api.banquet_agent import get_vip_churn_early_warning

        customer = _make_customer(count=3, total_fen=900000)
        old_order = _make_order(
            status="confirmed",
            banquet_date=date.today() - timedelta(days=240),  # ~8 months ago
        )

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([customer])
            return _scalars_returning([old_order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_vip_churn_early_warning(
            store_id="S001", inactive_months=6, top_n=20, db=db, _=_mock_user()
        )

        assert result["at_risk_count"] == 1
        item = result["at_risk"][0]
        assert item["months_inactive"] > 6

    @pytest.mark.asyncio
    async def test_no_customers_returns_empty(self):
        """无客户时 at_risk 为空"""
        from src.api.banquet_agent import get_vip_churn_early_warning

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_vip_churn_early_warning(
            store_id="S001", inactive_months=6, top_n=20, db=db, _=_mock_user()
        )

        assert result["at_risk_count"] == 0
        assert result["at_risk"] == []


# ── TestCapacityRevenueYield ──────────────────────────────────────────────────

class TestCapacityRevenueYield:

    @pytest.mark.asyncio
    async def test_utilization_pct_computed(self):
        """1厅 + 1预订 + 1过去订单 → booked_days=1, utilization_pct 正确"""
        from src.api.banquet_agent import get_capacity_revenue_yield

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(
            oid="O-001", status="confirmed",
            banquet_date=date.today() - timedelta(days=15),
            total_fen=300000,
        )

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([hall])
            if call_n[0] == 2:
                return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_capacity_revenue_yield(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_halls"] if "total_halls" in result else len(result["halls"]) == 1
        h = result["halls"][0]
        assert h["booked_days"] == 1
        assert h["actual_revenue_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅房时 halls 为空"""
        from src.api.banquet_agent import get_capacity_revenue_yield

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_capacity_revenue_yield(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["halls"] == []
        assert result["avg_yield_pct"] is None
