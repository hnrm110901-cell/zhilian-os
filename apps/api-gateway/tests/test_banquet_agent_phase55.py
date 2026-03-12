"""
Banquet Agent Phase 55 — 单元测试

覆盖端点：
  - get_order_lead_time_distribution
  - get_customer_repeat_type_preference
  - get_hall_revenue_per_day
  - get_lead_win_loss_ratio
  - get_payment_collection_efficiency
  - get_banquet_type_table_trend
  - get_staff_lead_conversion
  - get_monthly_new_customers
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
                status="confirmed", customer_id="C-001", created_at=None):
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
    o.created_at       = created_at or datetime.utcnow() - timedelta(days=60)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_lead(lid="L-001", stage="won", owner="U-001", created_at=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = "微信"
    l.current_stage  = LeadStageEnum(stage)
    l.owner_user_id  = owner
    l.created_at     = created_at or datetime.utcnow() - timedelta(days=20)
    return l


def _make_booking(bid="B-001", hall_id="H-001", order_id="O-001", slot_date=None):
    b = MagicMock()
    b.id               = bid
    b.hall_id          = hall_id
    b.banquet_order_id = order_id
    b.slot_date        = slot_date or (date.today() - timedelta(days=10))
    b.slot_name        = "dinner"
    return b


# ── TestOrderLeadTimeDistribution ─────────────────────────────────────────────

class TestOrderLeadTimeDistribution:

    @pytest.mark.asyncio
    async def test_distribution_computed(self):
        """order created 60d ago, banquet 10d from today → lead_days=70"""
        from src.api.banquet_agent import get_order_lead_time_distribution

        created   = datetime.utcnow() - timedelta(days=60)
        bd        = date.today() + timedelta(days=10)   # 70d lead
        order = _make_order(banquet_date=bd, created_at=created)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_lead_time_distribution(store_id="S001", months=12,
                                                         db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_lead_days"] is not None
        assert result["avg_lead_days"] > 0
        assert len(result["distribution"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_lead_days = None"""
        from src.api.banquet_agent import get_order_lead_time_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_lead_time_distribution(store_id="S001", months=12,
                                                         db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_lead_days"] is None


# ── TestCustomerRepeatTypePreference ──────────────────────────────────────────

class TestCustomerRepeatTypePreference:

    @pytest.mark.asyncio
    async def test_repeat_preference_computed(self):
        """C-001 has 2 wedding orders → top_type=wedding"""
        from src.api.banquet_agent import get_customer_repeat_type_preference

        o1 = _make_order(oid="O-001", banquet_type="wedding", customer_id="C-001")
        o2 = _make_order(oid="O-002", banquet_type="wedding", customer_id="C-001")
        o3 = _make_order(oid="O-003", banquet_type="birthday", customer_id="C-002")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2, o3]))

        result = await get_customer_repeat_type_preference(store_id="S001", months=24,
                                                            db=db, _=_mock_user())

        assert result["repeat_customers"] == 1
        assert result["top_type"] == "wedding"

    @pytest.mark.asyncio
    async def test_no_repeat_customers(self):
        """无复购客户时 top_type = None"""
        from src.api.banquet_agent import get_customer_repeat_type_preference

        o1 = _make_order(oid="O-001", customer_id="C-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1]))

        result = await get_customer_repeat_type_preference(store_id="S001", months=24,
                                                            db=db, _=_mock_user())

        assert result["repeat_customers"] == 0
        assert result["top_type"] is None


# ── TestHallRevenuePerDay ──────────────────────────────────────────────────────

class TestHallRevenuePerDay:

    @pytest.mark.asyncio
    async def test_rev_per_day_computed(self):
        """H-001 1 booking × 300000fen on 1 day → rev_per_day=3000yuan"""
        from src.api.banquet_agent import get_hall_revenue_per_day

        booking = _make_booking(bid="B-001", hall_id="H-001", order_id="O-001")
        order   = _make_order(oid="O-001", total_fen=300000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([booking])
            return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_hall_revenue_per_day(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_halls"] == 1
        assert result["top_hall"] == "H-001"
        h = result["halls"][0]
        assert h["rev_per_day_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_bookings_returns_empty(self):
        """无预订时 top_hall = None"""
        from src.api.banquet_agent import get_hall_revenue_per_day

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_per_day(store_id="S001", months=6,
                                                 db=db, _=_mock_user())

        assert result["total_halls"] == 0
        assert result["top_hall"] is None


# ── TestLeadWinLossRatio ──────────────────────────────────────────────────────

class TestLeadWinLossRatio:

    @pytest.mark.asyncio
    async def test_ratio_computed(self):
        """2 won + 1 lost → ratio=2.0, win_pct=66.7%"""
        from src.api.banquet_agent import get_lead_win_loss_ratio

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="won")
        l3 = _make_lead(lid="L-003", stage="lost")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2, l3]))

        result = await get_lead_win_loss_ratio(store_id="S001", months=6,
                                                db=db, _=_mock_user())

        assert result["total_leads"] == 3
        assert result["won"] == 2
        assert result["lost"] == 1
        assert result["win_loss_ratio"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 win_loss_ratio = None"""
        from src.api.banquet_agent import get_lead_win_loss_ratio

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_win_loss_ratio(store_id="S001", months=6,
                                                db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["win_loss_ratio"] is None


# ── TestPaymentCollectionEfficiency ──────────────────────────────────────────

class TestPaymentCollectionEfficiency:

    @pytest.mark.asyncio
    async def test_efficiency_computed(self):
        """total=300000fen, paid=150000fen → collection_rate=50%"""
        from src.api.banquet_agent import get_payment_collection_efficiency

        o1 = _make_order(oid="O-001", total_fen=300000, paid_fen=150000, status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1]))

        result = await get_payment_collection_efficiency(store_id="S001", months=6,
                                                          db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["collection_rate_pct"] == pytest.approx(50.0)
        assert result["outstanding_yuan"] == pytest.approx(1500.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 collection_rate_pct = None"""
        from src.api.banquet_agent import get_payment_collection_efficiency

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_payment_collection_efficiency(store_id="S001", months=6,
                                                          db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["collection_rate_pct"] is None


# ── TestBanquetTypeTableTrend ─────────────────────────────────────────────────

class TestBanquetTypeTableTrend:

    @pytest.mark.asyncio
    async def test_trend_computed(self):
        """2 wedding orders, 10+20 tables → overall_avg=15"""
        from src.api.banquet_agent import get_banquet_type_table_trend

        o1 = _make_order(oid="O-001", banquet_type="wedding", table_count=10)
        o2 = _make_order(oid="O-002", banquet_type="wedding", table_count=20)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_type_table_trend(store_id="S001", months=12,
                                                     db=db, _=_mock_user())

        assert result["total_orders"] == 2
        w = next(t for t in result["by_type"] if t["banquet_type"] == "wedding")
        assert w["overall_avg"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 growing_type = None"""
        from src.api.banquet_agent import get_banquet_type_table_trend

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_type_table_trend(store_id="S001", months=12,
                                                     db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["growing_type"] is None


# ── TestStaffLeadConversion ───────────────────────────────────────────────────

class TestStaffLeadConversion:

    @pytest.mark.asyncio
    async def test_conversion_computed(self):
        """U-001: 1 won / 1 total → conversion_pct=100%"""
        from src.api.banquet_agent import get_staff_lead_conversion

        lead = _make_lead(lid="L-001", stage="won", owner="U-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_staff_lead_conversion(store_id="S001", months=6,
                                                  db=db, _=_mock_user())

        assert result["total_staff"] == 1
        assert result["top_converter"] == "U-001"
        assert result["staff"][0]["conversion_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_empty(self):
        """无线索时 top_converter = None"""
        from src.api.banquet_agent import get_staff_lead_conversion

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_lead_conversion(store_id="S001", months=6,
                                                  db=db, _=_mock_user())

        assert result["total_staff"] == 0
        assert result["top_converter"] is None


# ── TestMonthlyNewCustomers ───────────────────────────────────────────────────

class TestMonthlyNewCustomers:

    @pytest.mark.asyncio
    async def test_new_customers_computed(self):
        """C-001 first order + C-002 first order → total_new=2"""
        from src.api.banquet_agent import get_monthly_new_customers

        o1 = _make_order(oid="O-001", customer_id="C-001",
                         created_at=datetime.utcnow() - timedelta(days=40))
        o2 = _make_order(oid="O-002", customer_id="C-002",
                         created_at=datetime.utcnow() - timedelta(days=10))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_monthly_new_customers(store_id="S001", months=12,
                                                  db=db, _=_mock_user())

        assert result["total_new_customers"] == 2
        assert result["peak_month"] is not None
        assert len(result["monthly"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 total_new_customers=0"""
        from src.api.banquet_agent import get_monthly_new_customers

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_monthly_new_customers(store_id="S001", months=12,
                                                  db=db, _=_mock_user())

        assert result["total_new_customers"] == 0
        assert result["peak_month"] is None
