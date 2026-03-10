"""
Banquet Agent Phase 23 — 单元测试

覆盖端点：
  - get_exception_summary
  - get_satisfaction_trend
  - get_deposit_forecast
  - get_review_tags
  - get_order_size_distribution
  - get_hall_revenue_correlation
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


def _scalar_returning(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _rows_returning(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_exception(eid="E-001", exception_type="late", severity="medium", status="open"):
    e = MagicMock()
    e.id             = eid
    e.exception_type = exception_type
    e.severity       = severity
    e.status         = status
    e.created_at     = datetime.utcnow()
    return e


def _make_review(rid="R-001", rating=4, ai_score=80.0, tags=None):
    r = MagicMock()
    r.id               = rid
    r.customer_rating  = rating
    r.ai_score         = ai_score
    r.improvement_tags = tags or ["延误", "菜量不足"]
    r.revenue_yuan     = 5000.0
    r.gross_profit_yuan = 1500.0
    r.gross_margin_pct = 30.0
    return r


def _make_order(oid="O-001", store_id="S001", total_fen=300000,
                paid_fen=150000, deposit_fen=100000, table_count=15,
                banquet_date=None, status="confirmed"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.store_id         = store_id
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.deposit_fen      = deposit_fen
    o.table_count      = table_count
    o.banquet_date     = banquet_date or (date.today() + timedelta(days=30))
    o.customer_id      = "C-001"
    o.banquet_type     = BanquetTypeEnum.WEDDING
    o.order_status     = OrderStatusEnum.CONFIRMED if status == "confirmed" else OrderStatusEnum.COMPLETED
    o.contact_name     = "张三"
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
    b.id                 = bid
    b.hall_id            = hall_id
    b.banquet_order_id   = order_id
    return b


# ── TestExceptionSummary ──────────────────────────────────────────────────────

class TestExceptionSummary:

    @pytest.mark.asyncio
    async def test_resolution_rate_computed(self):
        """1 resolved / 2 total → 50% 解决率"""
        from src.api.banquet_agent import get_exception_summary

        e1 = _make_exception(eid="E-001", status="resolved", exception_type="late", severity="high")
        e2 = _make_exception(eid="E-002", status="open",     exception_type="quality", severity="medium")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([e1, e2]))

        result = await get_exception_summary(store_id="S001", days=90, db=db, _=_mock_user())

        assert result["total"]               == 2
        assert result["resolved"]            == 1
        assert result["resolution_rate_pct"] == pytest.approx(50.0)
        assert len(result["by_type"])        >= 1

    @pytest.mark.asyncio
    async def test_no_exceptions_returns_zero(self):
        """无异常时返回 total=0"""
        from src.api.banquet_agent import get_exception_summary

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_exception_summary(store_id="S001", days=90, db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["by_type"] == []


# ── TestSatisfactionTrend ─────────────────────────────────────────────────────

class TestSatisfactionTrend:

    @pytest.mark.asyncio
    async def test_avg_rating_computed(self):
        """2 条评分（4+5）→ avg_rating = 4.5"""
        from src.api.banquet_agent import get_satisfaction_trend

        r1 = _make_review(rating=4)
        r2 = _make_review(rating=5)
        bd = date.today() - timedelta(days=10)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([(r1, bd), (r2, bd)]))

        result = await get_satisfaction_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_reviews"] == 2
        assert result["avg_rating"]    == pytest.approx(4.5)
        assert len(result["monthly_trend"]) >= 1

    @pytest.mark.asyncio
    async def test_no_reviews_returns_none(self):
        """无评价时 avg_rating = None"""
        from src.api.banquet_agent import get_satisfaction_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_satisfaction_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_reviews"] == 0
        assert result["avg_rating"] is None


# ── TestDepositForecast ───────────────────────────────────────────────────────

class TestDepositForecast:

    @pytest.mark.asyncio
    async def test_unpaid_balance_summed(self):
        """total_amount=3000, paid=1500 → expected_yuan 含1500"""
        from src.api.banquet_agent import get_deposit_forecast

        o = _make_order(total_fen=300000, paid_fen=150000,
                        banquet_date=date.today() + timedelta(days=20))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_deposit_forecast(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["total_expected_yuan"] == pytest.approx(1500.0)

    @pytest.mark.asyncio
    async def test_no_future_orders_returns_zero(self):
        """无未来订单时 total_expected_yuan == 0"""
        from src.api.banquet_agent import get_deposit_forecast

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_forecast(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["total_expected_yuan"] == pytest.approx(0.0)


# ── TestReviewTags ────────────────────────────────────────────────────────────

class TestReviewTags:

    @pytest.mark.asyncio
    async def test_tag_frequency_counted(self):
        """同一标签出现2次 → count=2"""
        from src.api.banquet_agent import get_review_tags

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([
            (["延误", "菜量不足"],),
            (["延误", "服务态度"],),
        ]))

        result = await get_review_tags(store_id="S001", db=db, _=_mock_user())

        top_tag = result["tags"][0]
        assert top_tag["tag"]   == "延误"
        assert top_tag["count"] == 2

    @pytest.mark.asyncio
    async def test_no_reviews_returns_empty(self):
        """无评价时 tags 为空"""
        from src.api.banquet_agent import get_review_tags

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_review_tags(store_id="S001", db=db, _=_mock_user())

        assert result["tags"] == []


# ── TestOrderSizeDistribution ─────────────────────────────────────────────────

class TestOrderSizeDistribution:

    @pytest.mark.asyncio
    async def test_mid_size_bucket_counted(self):
        """15桌订单 → 落入「中型（11-20桌）」"""
        from src.api.banquet_agent import get_order_size_distribution

        o = _make_order(table_count=15)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_order_size_distribution(store_id="S001", db=db, _=_mock_user())

        assert result["total"] == 1
        mid = next(b for b in result["buckets"] if "11-20" in b["label"])
        assert mid["count"] == 1
        assert mid["pct"]   == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty_buckets(self):
        """无订单时各桶 count=0"""
        from src.api.banquet_agent import get_order_size_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_size_distribution(store_id="S001", db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["buckets"] == []


# ── TestHallRevenueCorrelation ────────────────────────────────────────────────

class TestHallRevenueCorrelation:

    @pytest.mark.asyncio
    async def test_hall_revenue_computed(self):
        """1厅 + 1预订 + 1订单 → revenue_yuan 正确"""
        from src.api.banquet_agent import get_hall_revenue_correlation

        hall    = _make_hall()
        booking = _make_booking(hall_id=hall.id, order_id="O-001")
        order   = _make_order(oid="O-001", total_fen=300000, table_count=10,
                              status="completed")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([hall])      # halls
            if n == 2: return _scalars_returning([booking])   # bookings for hall
            return _scalars_returning([order])                 # orders for booking

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_revenue_correlation(store_id="S001", db=db, _=_mock_user())

        assert result["total_halls"] == 1
        h = result["halls"][0]
        assert h["revenue_yuan"]        == pytest.approx(3000.0)
        assert h["avg_price_per_table"] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty(self):
        """无厅时返回空 halls"""
        from src.api.banquet_agent import get_hall_revenue_correlation

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_correlation(store_id="S001", db=db, _=_mock_user())

        assert result["halls"] == []
