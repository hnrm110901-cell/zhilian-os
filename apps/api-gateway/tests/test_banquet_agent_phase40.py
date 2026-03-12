"""
Banquet Agent Phase 40 — 单元测试

覆盖端点：
  - get_banquet_booking_conversion_rate
  - get_menu_customization_rate
  - get_lead_age_distribution
  - get_hall_revenue_seasonality
  - get_customer_reorder_rate
  - get_staff_performance_score
  - get_banquet_cancellation_lead_time
  - get_deposit_ratio_analysis
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


def _make_order(oid="O-001", total_fen=300000, deposit_fen=30000,
                table_count=10, banquet_type="wedding", banquet_date=None,
                status="confirmed", customer_id="C-001",
                package_id=None, created_at=None, updated_at=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
    o.deposit_fen      = deposit_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() - timedelta(days=30))
    o.customer_id      = customer_id
    o.package_id       = package_id
    o.contact_name     = "张三"
    o.created_at       = created_at or datetime.utcnow() - timedelta(days=60)
    o.updated_at       = updated_at or datetime.utcnow() - timedelta(days=35)
    status_map = {
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "completed":  OrderStatusEnum.COMPLETED,
        "cancelled":  OrderStatusEnum.CANCELLED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    return o


def _make_lead(lid="L-001", stage="won", days_ago=20):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.source_channel = "微信"
    l.current_stage  = LeadStageEnum(stage) if stage in [e.value for e in LeadStageEnum] else MagicMock(value=stage)
    l.created_at     = datetime.utcnow() - timedelta(days=days_ago)
    l.updated_at     = datetime.utcnow() - timedelta(days=5)
    return l


def _make_task(tid="T-001", owner="U-001", order_id="O-001",
               status="done", ontime=True):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum(status)
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    t.due_time         = datetime.utcnow() + timedelta(hours=2)
    t.completed_at     = (datetime.utcnow() + timedelta(hours=1)
                          if ontime else datetime.utcnow() + timedelta(hours=5))
    return t


def _make_package(pid="PKG-001", price_fen=25000):
    p = MagicMock()
    p.id                  = pid
    p.suggested_price_fen = price_fen
    return p


# ── TestBanquetBookingConversionRate ──────────────────────────────────────────

class TestBanquetBookingConversionRate:

    @pytest.mark.asyncio
    async def test_conversion_computed(self):
        """1 won + 1 new → conversion_rate=50%"""
        from src.api.banquet_agent import get_banquet_booking_conversion_rate

        l1 = _make_lead(lid="L-001", stage="won")
        l2 = _make_lead(lid="L-002", stage="new")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_banquet_booking_conversion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["converted_count"] == 1
        assert result["conversion_rate_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 conversion_rate_pct = None"""
        from src.api.banquet_agent import get_banquet_booking_conversion_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_booking_conversion_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["conversion_rate_pct"] is None


# ── TestMenuCustomizationRate ─────────────────────────────────────────────────

class TestMenuCustomizationRate:

    @pytest.mark.asyncio
    async def test_customization_detected(self):
        """pkg 25000*10=250000, actual=300000 → customized=1, rate=100%"""
        from src.api.banquet_agent import get_menu_customization_rate

        pkg   = _make_package(price_fen=25000)
        order = _make_order(total_fen=300000, table_count=10, package_id=pkg.id)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([pkg])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_menu_customization_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 1
        assert result["customized_count"] == 1
        assert result["customization_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无套餐订单时 customization_rate_pct = None"""
        from src.api.banquet_agent import get_menu_customization_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_menu_customization_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["customization_rate_pct"] is None


# ── TestLeadAgeDistribution ───────────────────────────────────────────────────

class TestLeadAgeDistribution:

    @pytest.mark.asyncio
    async def test_age_bucketed(self):
        """lead 20 days old → bucket=8-30天"""
        from src.api.banquet_agent import get_lead_age_distribution

        lead = _make_lead(days_ago=20)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead]))

        result = await get_lead_age_distribution(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 1
        assert result["avg_age_days"] == pytest.approx(20.0, abs=1.0)
        bucket = next(b for b in result["distribution"] if b["bucket"] == "8-30天")
        assert bucket["count"] == 1

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_age_days = None"""
        from src.api.banquet_agent import get_lead_age_distribution

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_age_distribution(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_age_days"] is None
        assert result["distribution"] == []


# ── TestHallRevenueSeasonality ────────────────────────────────────────────────

class TestHallRevenueSeasonality:

    @pytest.mark.asyncio
    async def test_seasonality_computed(self):
        """1 order in June → June seasonal_index=1.0, peak=6"""
        from src.api.banquet_agent import get_hall_revenue_seasonality

        order = _make_order(total_fen=300000,
                            banquet_date=date(date.today().year - 1, 6, 15))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_hall_revenue_seasonality(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["peak_month"] == 6
        june = next(m for m in result["monthly"] if m["month"] == 6)
        assert june["seasonal_index"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无订单时 monthly 为空"""
        from src.api.banquet_agent import get_hall_revenue_seasonality

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_revenue_seasonality(store_id="S001", months=24, db=db, _=_mock_user())

        assert result["monthly"] == []
        assert result["peak_month"] is None


# ── TestCustomerReorderRate ───────────────────────────────────────────────────

class TestCustomerReorderRate:

    @pytest.mark.asyncio
    async def test_reorder_detected(self):
        """C-001 has 2 orders → reorder_customers=1, rate=100%"""
        from src.api.banquet_agent import get_customer_reorder_rate

        o1 = _make_order(oid="O-001", customer_id="C-001")
        o2 = _make_order(oid="O-002", customer_id="C-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_customer_reorder_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 1
        assert result["reorder_customers"] == 1
        assert result["reorder_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 reorder_rate_pct = None"""
        from src.api.banquet_agent import get_customer_reorder_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_reorder_rate(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["total_customers"] == 0
        assert result["reorder_rate_pct"] is None


# ── TestStaffPerformanceScore ─────────────────────────────────────────────────

class TestStaffPerformanceScore:

    @pytest.mark.asyncio
    async def test_score_computed(self):
        """U-001: 1 done ontime → completion=100%, ontime=100% → score=100"""
        from src.api.banquet_agent import get_staff_performance_score

        task = _make_task(owner="U-001", status="done", ontime=True)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([task]))

        result = await get_staff_performance_score(store_id="S001", months=3, db=db, _=_mock_user())

        assert len(result["staff"]) == 1
        assert result["top_performer"] == "U-001"
        assert result["staff"][0]["performance_score"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 staff 为空"""
        from src.api.banquet_agent import get_staff_performance_score

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_performance_score(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["staff"] == []
        assert result["top_performer"] is None


# ── TestBanquetCancellationLeadTime ──────────────────────────────────────────

class TestBanquetCancellationLeadTime:

    @pytest.mark.asyncio
    async def test_lead_time_computed(self):
        """banquet_date 30 days away from cancel → avg=30, bucket=8-30天"""
        from src.api.banquet_agent import get_banquet_cancellation_lead_time

        # cancel date = today-35d; banquet_date = today-5d → 30 days diff
        banquet_d  = date.today() - timedelta(days=5)
        cancel_dt  = datetime.utcnow() - timedelta(days=35)
        order = _make_order(
            status="cancelled",
            banquet_date=banquet_d,
            updated_at=cancel_dt,
        )
        order.updated_at = cancel_dt

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_cancellation_lead_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 1
        assert result["avg_days_before_event"] == pytest.approx(30.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无取消订单时 avg_days_before_event = None"""
        from src.api.banquet_agent import get_banquet_cancellation_lead_time

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_cancellation_lead_time(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_cancelled"] == 0
        assert result["avg_days_before_event"] is None


# ── TestDepositRatioAnalysis ──────────────────────────────────────────────────

class TestDepositRatioAnalysis:

    @pytest.mark.asyncio
    async def test_ratio_computed(self):
        """deposit=30000, total=300000 → ratio=10%, bucket=10-20%"""
        from src.api.banquet_agent import get_deposit_ratio_analysis

        order = _make_order(total_fen=300000, deposit_fen=30000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_deposit_ratio_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["avg_deposit_ratio_pct"] == pytest.approx(10.0)
        assert len(result["distribution"]) >= 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 avg_deposit_ratio_pct = None"""
        from src.api.banquet_agent import get_deposit_ratio_analysis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_deposit_ratio_analysis(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["avg_deposit_ratio_pct"] is None
