"""
Banquet Agent Phase 41 — 单元测试

覆盖端点：
  - get_banquet_no_show_rate
  - get_quote_revision_count
  - get_hall_peak_booking_slots
  - get_customer_acquisition_cost
  - get_order_amendment_frequency
  - get_lead_touchpoint_count
  - get_staff_specialization_index
  - get_banquet_package_popularity
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


def _make_order(oid="O-001", total_fen=300000, table_count=10,
                banquet_type="wedding", banquet_date=None,
                status="completed", customer_id="C-001",
                package_id=None, created_at=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id               = oid
    o.total_amount_fen = total_fen
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
    o.order_status = status_map.get(status, OrderStatusEnum.COMPLETED)
    return o


def _make_lead(lid="L-001", stage="won", source="微信", budget_fen=200000):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id                  = lid
    l.source_channel      = source
    l.current_stage       = LeadStageEnum(stage) if stage in [e.value for e in LeadStageEnum] else MagicMock(value=stage)
    l.expected_budget_fen = budget_fen
    l.created_at          = datetime.utcnow() - timedelta(days=20)
    l.updated_at          = datetime.utcnow() - timedelta(days=5)
    return l


def _make_booking(bid="B-001", hall_id="H-001", slot_name="dinner", slot_date=None):
    b = MagicMock()
    b.id       = bid
    b.hall_id  = hall_id
    b.slot_name = slot_name
    b.slot_date = slot_date or (date.today() - timedelta(days=10))
    return b


def _make_quote(qid="Q-001", lead_id="L-001"):
    q = MagicMock()
    q.id      = qid
    q.lead_id = lead_id
    q.created_at = datetime.utcnow() - timedelta(days=10)
    return q


def _make_task(tid="T-001", owner="U-001", order_id="O-001"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id               = tid
    t.banquet_order_id = order_id
    t.owner_user_id    = owner
    t.task_status      = TaskStatusEnum("done")
    t.created_at       = datetime.utcnow() - timedelta(days=5)
    return t


def _make_followup(fid="F-001", lead_id="L-001"):
    f = MagicMock()
    f.id      = fid
    f.lead_id = lead_id
    f.created_at = datetime.utcnow() - timedelta(days=3)
    return f


def _make_exception(eid="E-001", order_id="O-001", exc_type="amendment"):
    e = MagicMock()
    e.id               = eid
    e.banquet_order_id = order_id
    e.exception_type   = exc_type
    e.created_at       = datetime.utcnow() - timedelta(days=2)
    return e


# ── TestBanquetNoShowRate ─────────────────────────────────────────────────────

class TestBanquetNoShowRate:

    @pytest.mark.asyncio
    async def test_no_show_detected(self):
        """1 confirmed past order → no_show=1, rate=100%"""
        from src.api.banquet_agent import get_banquet_no_show_rate

        # banquet_date in the past, status still confirmed
        order = _make_order(
            status="confirmed",
            banquet_date=date.today() - timedelta(days=5),
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_banquet_no_show_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_past_orders"] == 1
        assert result["no_show_count"] == 1
        assert result["no_show_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无历史订单时 no_show_rate_pct = None"""
        from src.api.banquet_agent import get_banquet_no_show_rate

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_no_show_rate(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_past_orders"] == 0
        assert result["no_show_rate_pct"] is None


# ── TestQuoteRevisionCount ────────────────────────────────────────────────────

class TestQuoteRevisionCount:

    @pytest.mark.asyncio
    async def test_revisions_counted(self):
        """2 quotes same lead → avg=2, multi_revision=100%"""
        from src.api.banquet_agent import get_quote_revision_count

        q1 = _make_quote(qid="Q-001", lead_id="L-001")
        q2 = _make_quote(qid="Q-002", lead_id="L-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([q1, q2]))

        result = await get_quote_revision_count(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_quotes"] == 2
        assert result["avg_revisions_per_lead"] == pytest.approx(2.0)
        assert result["multi_revision_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_quotes_returns_none(self):
        """无报价时 avg_revisions_per_lead = None"""
        from src.api.banquet_agent import get_quote_revision_count

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_quote_revision_count(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_quotes"] == 0
        assert result["avg_revisions_per_lead"] is None


# ── TestHallPeakBookingSlots ──────────────────────────────────────────────────

class TestHallPeakBookingSlots:

    @pytest.mark.asyncio
    async def test_peak_slot_detected(self):
        """2 dinner + 1 lunch → peak=dinner"""
        from src.api.banquet_agent import get_hall_peak_booking_slots

        b1 = _make_booking(bid="B-001", slot_name="dinner")
        b2 = _make_booking(bid="B-002", slot_name="dinner")
        b3 = _make_booking(bid="B-003", slot_name="lunch")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([b1, b2, b3]))

        result = await get_hall_peak_booking_slots(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 3
        assert result["peak_slot"] == "dinner"
        dinner = next(s for s in result["slots"] if s["slot"] == "dinner")
        assert dinner["count"] == 2

    @pytest.mark.asyncio
    async def test_no_bookings_returns_empty(self):
        """无预订时 slots 为空"""
        from src.api.banquet_agent import get_hall_peak_booking_slots

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_hall_peak_booking_slots(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_bookings"] == 0
        assert result["slots"] == []
        assert result["peak_slot"] is None


# ── TestCustomerAcquisitionCost ───────────────────────────────────────────────

class TestCustomerAcquisitionCost:

    @pytest.mark.asyncio
    async def test_cost_computed(self):
        """2 won leads from 微信, budget=200000fen each → avg=2000元"""
        from src.api.banquet_agent import get_customer_acquisition_cost

        l1 = _make_lead(lid="L-001", stage="won", source="微信", budget_fen=200000)
        l2 = _make_lead(lid="L-002", stage="won", source="微信", budget_fen=200000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([l1, l2]))

        result = await get_customer_acquisition_cost(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won_leads"] == 2
        assert result["avg_budget_yuan"] == pytest.approx(2000.0)
        wx = next(c for c in result["channels"] if c["channel"] == "微信")
        assert wx["won_count"] == 2

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无成单线索时 avg_budget_yuan = None"""
        from src.api.banquet_agent import get_customer_acquisition_cost

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_acquisition_cost(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_won_leads"] == 0
        assert result["avg_budget_yuan"] is None


# ── TestOrderAmendmentFrequency ───────────────────────────────────────────────

class TestOrderAmendmentFrequency:

    @pytest.mark.asyncio
    async def test_amendment_detected(self):
        """1 order + 1 non-complaint exception → amended=1, rate=100%"""
        from src.api.banquet_agent import get_order_amendment_frequency

        order = _make_order(status="confirmed")
        exc   = _make_exception(order_id=order.id, exc_type="amendment")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([order])
            return _scalars_returning([exc])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_order_amendment_frequency(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 1
        assert result["amended_count"] == 1
        assert result["amendment_rate_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_none(self):
        """无订单时 amendment_rate_pct = None"""
        from src.api.banquet_agent import get_order_amendment_frequency

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_order_amendment_frequency(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_orders"] == 0
        assert result["amendment_rate_pct"] is None


# ── TestLeadTouchpointCount ───────────────────────────────────────────────────

class TestLeadTouchpointCount:

    @pytest.mark.asyncio
    async def test_touchpoints_compared(self):
        """won lead with 3 followups, lost lead with 1 → won_avg=3, lost_avg=1"""
        from src.api.banquet_agent import get_lead_touchpoint_count

        l_won  = _make_lead(lid="L-001", stage="won")
        l_lost = _make_lead(lid="L-002", stage="lost")
        fu1 = _make_followup(fid="F-001", lead_id="L-001")
        fu2 = _make_followup(fid="F-002", lead_id="L-001")
        fu3 = _make_followup(fid="F-003", lead_id="L-001")
        fu4 = _make_followup(fid="F-004", lead_id="L-002")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([l_won, l_lost])
            if call_n[0] == 2: return _scalars_returning([fu1, fu2, fu3])
            return _scalars_returning([fu4])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_lead_touchpoint_count(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 2
        assert result["won_avg"] == pytest.approx(3.0)
        assert result["lost_avg"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_leads_returns_none(self):
        """无线索时 avg_touchpoints = None"""
        from src.api.banquet_agent import get_lead_touchpoint_count

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_lead_touchpoint_count(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0
        assert result["avg_touchpoints"] is None


# ── TestStaffSpecializationIndex ──────────────────────────────────────────────

class TestStaffSpecializationIndex:

    @pytest.mark.asyncio
    async def test_specialization_computed(self):
        """U-001: 2 tasks both wedding → spec_idx=1.0"""
        from src.api.banquet_agent import get_staff_specialization_index

        task1  = _make_task(tid="T-001", owner="U-001", order_id="O-001")
        task2  = _make_task(tid="T-002", owner="U-001", order_id="O-002")
        order1 = _make_order(oid="O-001", banquet_type="wedding")
        order2 = _make_order(oid="O-002", banquet_type="wedding")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning([task1, task2])
            if call_n[0] == 2: return _scalars_returning([order1])
            return _scalars_returning([order2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_staff_specialization_index(store_id="S001", months=6, db=db, _=_mock_user())

        assert len(result["staff"]) == 1
        assert result["most_specialized"] == "U-001"
        assert result["staff"][0]["specialization_idx"] == pytest.approx(1.0)
        assert result["staff"][0]["top_banquet_type"] == "wedding"

    @pytest.mark.asyncio
    async def test_no_tasks_returns_empty(self):
        """无任务时 staff 为空"""
        from src.api.banquet_agent import get_staff_specialization_index

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_staff_specialization_index(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["staff"] == []
        assert result["most_specialized"] is None


# ── TestBanquetPackagePopularity ──────────────────────────────────────────────

class TestBanquetPackagePopularity:

    @pytest.mark.asyncio
    async def test_popularity_computed(self):
        """2 orders with PKG-001 → top_package=PKG-001, pct=100%"""
        from src.api.banquet_agent import get_banquet_package_popularity

        o1 = _make_order(oid="O-001", total_fen=300000, package_id="PKG-001")
        o2 = _make_order(oid="O-002", total_fen=300000, package_id="PKG-001")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_banquet_package_popularity(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 2
        assert result["top_package_id"] == "PKG-001"
        assert result["packages"][0]["pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self):
        """无套餐订单时 packages 为空"""
        from src.api.banquet_agent import get_banquet_package_popularity

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_banquet_package_popularity(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_pkg_orders"] == 0
        assert result["packages"] == []
        assert result["top_package_id"] is None
