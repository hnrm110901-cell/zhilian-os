"""
Banquet Agent Phase 51 — 单元测试

覆盖端点：
  - get_monthly_lead_conversion
  - get_customer_order_frequency
  - get_staff_review_avg
  - get_payment_method_monthly_trend
  - get_banquet_type_revenue_share
  - get_customer_revenue_concentration
  - get_exception_monthly_trend
  - get_order_completion_by_type
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
                status="confirmed", customer_id="C-001"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.contact_name     = "张三"
    o.created_at       = datetime.utcnow() - timedelta(days=60)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_lead(lid="L-001", stage="won", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = "微信"
    l.current_stage  = LeadStageEnum(stage)
    l.created_at     = created_at or datetime.utcnow() - timedelta(days=20)
    return l


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    return t


def _make_review(rid="R-001", order_id="O-001", rating=5):
    r = MagicMock()
    r.id               = rid
    r.banquet_order_id = order_id
    r.customer_rating  = rating
    r.created_at       = datetime.utcnow() - timedelta(days=3)
    return r


def _make_payment(pid="P-001", order_id="O-001", method="微信", created_at=None):
    p = MagicMock()
    p.id               = pid
    p.banquet_order_id = order_id
    p.amount_fen       = 30000
    p.payment_method   = method
    p.created_at       = created_at or datetime.utcnow() - timedelta(days=5)
    return p


def _make_exception(eid="E-001", order_id="O-001", exc_type="complaint"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = exc_type
    e.created_at       = datetime.utcnow() - timedelta(days=5)
    return e


# ── TestMonthlyLeadConversion ─────────────────────────────────────────────────

class TestMonthlyLeadConversion:

    @pytest.mark.asyncio
    async def test_conversion_computed(self):
        """1 won + 1 new → avg_conversion_pct=50%"""
        from src.api.banquet_agent import get_monthly_lead_conversion

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="new")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_monthly_lead_conversion(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["avg_conversion_pct"] == pytest.approx(50.0)
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_conversion_pct = None"""
        from src.api.banquet_agent import get_monthly_lead_conversion

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_monthly_lead_conversion(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_conversion_pct"] is None


# ── TestCustomerOrderFrequency ────────────────────────────────────────────────

class TestCustomerOrderFrequency:

    @pytest.mark.asyncio
    async def test_frequency_computed(self):
        """C-001 × 2 orders, C-002 × 1 order in 24 months → freq≈1.5/2yr=0.75/yr"""
        from src.api.banquet_agent import get_customer_order_frequency

        o1 = _make_order(oid="O-001", customer_id="C-001")
        o2 = _make_order(oid="O-002", customer_id="C-001")
        o3 = _make_order(oid="O-003", customer_id="C-002")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2, o3]))

        result = await get_customer_order_frequency(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_orders"] == 3
        assert result["unique_customers"] == 2
        assert result["avg_orders_per_year"] is not None

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_orders_per_year = None"""
        from src.api.banquet_agent import get_customer_order_frequency

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_order_frequency(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_orders_per_year"] is None


# ── TestStaffReviewAvg ────────────────────────────────────────────────────────

class TestStaffReviewAvg:

    @pytest.mark.asyncio
    async def test_avg_computed(self):
        """U-001 task on O-001; review rating=5 → avg=5.0, top=U-001"""
        from src.api.banquet_agent import get_staff_review_avg

        task   = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        review = _make_review(rid="R-001", order_id="O-001", rating=5)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([task])
            return _scalars_returning([review])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_review_avg(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["top_rated_staff"] == "U-001"
        assert result["staff"][0]["avg_rating"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 staff 为空"""
        from src.api.banquet_agent import get_staff_review_avg

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_review_avg(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["top_rated_staff"] is None


# ── TestPaymentMethodMonthlyTrend ─────────────────────────────────────────────

class TestPaymentMethodMonthlyTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """2 微信 + 1 现金 → overall_top_method=微信"""
        from src.api.banquet_agent import get_payment_method_monthly_trend

        p1 = _make_payment(pid="P-001", method="微信")
        p2 = _make_payment(pid="P-002", method="微信")
        p3 = _make_payment(pid="P-003", method="现金")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([p1, p2, p3]))

        result = await get_payment_method_monthly_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 3
        assert result["overall_top_method"] == "微信"
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_payments_returns_none(self):
        """无支付时 overall_top_method = None"""
        from src.api.banquet_agent import get_payment_method_monthly_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_method_monthly_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_payments"] == 0
        assert result["overall_top_method"] is None


# ── TestBanquetTypeRevenueShare ───────────────────────────────────────────────

class TestBanquetTypeRevenueShare:

    @pytest.mark.asyncio
    async def test_share_computed(self):
        """1 wedding 300000fen + 1 birthday 100000fen → wedding=75%"""
        from src.api.banquet_agent import get_banquet_type_revenue_share

        o1 = _make_order(oid="O-001", banquet_type="wedding",  total_fen=300000)
        o2 = _make_order(oid="O-002", banquet_type="birthday", total_fen=100000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_type_revenue_share(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["total_revenue_yuan"] == pytest.approx(4000.0)
        assert result["top_type"] == "wedding"
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["revenue_share_pct"] == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 top_type = None"""
        from src.api.banquet_agent import get_banquet_type_revenue_share

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_revenue_share(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["top_type"] is None


# ── TestCustomerRevenueConcentration ──────────────────────────────────────────

class TestCustomerRevenueConcentration:

    @pytest.mark.asyncio
    async def test_concentration_computed(self):
        """10 customers, top 10%(1) has highest spend → top10_count=1"""
        from src.api.banquet_agent import get_customer_revenue_concentration

        orders = [
            _make_order(oid=f"O-{i}", total_fen=v, customer_id=f"C-{i}")
            for i, v in enumerate([500000, 200000, 150000, 100000, 80000,
                                    70000,  60000,  50000,  40000, 30000])
        ]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning(orders))

        result = await get_customer_revenue_concentration(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 10
        assert result["top10_count"] == 1
        assert result["top10_revenue_pct"] is not None
        assert result["top10_revenue_pct"] > 30.0  # 500000/1280000 ≈ 39%

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 top10_revenue_pct = None"""
        from src.api.banquet_agent import get_customer_revenue_concentration

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_revenue_concentration(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["top10_revenue_pct"] is None


# ── TestExceptionMonthlyTrend ─────────────────────────────────────────────────

class TestExceptionMonthlyTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """3 exceptions → total=3, monthly has entries"""
        from src.api.banquet_agent import get_exception_monthly_trend

        e1 = _make_exception(eid="E-001", exc_type="complaint")
        e2 = _make_exception(eid="E-002", exc_type="complaint")
        e3 = _make_exception(eid="E-003", exc_type="damage")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([e1, e2, e3]))

        result = await get_exception_monthly_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_exceptions"] == 3
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_exceptions_returns_empty(self):
        """无异常时 monthly 为空"""
        from src.api.banquet_agent import get_exception_monthly_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_exception_monthly_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_exceptions"] == 0
        assert result["monthly"] == []
        assert result["trend_up"] is None


# ── TestOrderCompletionByType ─────────────────────────────────────────────────

class TestOrderCompletionByType:

    @pytest.mark.asyncio
    async def test_completion_by_type(self):
        """1 wedding completed + 1 wedding confirmed → wedding_completion=50%"""
        from src.api.banquet_agent import get_order_completion_by_type

        o1 = _make_order(oid="O-001", banquet_type="wedding", status="completed")
        o2 = _make_order(oid="O-002", banquet_type="wedding", status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_order_completion_by_type(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 2
        assert result["overall_completion_pct"] == pytest.approx(50.0)
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["completion_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 overall_completion_pct = None"""
        from src.api.banquet_agent import get_order_completion_by_type

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_completion_by_type(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["overall_completion_pct"] is None
