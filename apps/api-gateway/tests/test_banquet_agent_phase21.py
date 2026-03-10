"""
Banquet Agent Phase 21 — 单元测试

覆盖端点：
  - get_customer_segmentation
  - get_vip_ranking
  - get_capacity_gaps
  - get_acquisition_funnel
  - get_churn_risk
  - get_upsell_opportunities
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


def _make_customer(cid="C-001", store_id="S001", name="张三",
                   phone="138-0000-0001", total_fen=600000, count=3):
    c = MagicMock()
    c.id                        = cid
    c.store_id                  = store_id
    c.name                      = name
    c.phone                     = phone
    c.total_banquet_amount_fen  = total_fen
    c.total_banquet_count       = count
    c.vip_level                 = 1
    c.tags                      = []
    return c


def _make_hall(hid="H-001", store_id="S001"):
    h = MagicMock()
    h.id       = hid
    h.store_id = store_id
    h.is_active = True
    return h


def _make_order(oid="O-001", store_id="S001", total_fen=300000,
                table_count=10, banquet_type="wedding",
                banquet_date=None, contact_name="王五"):
    from src.models.banquet import BanquetTypeEnum, OrderStatusEnum
    o = MagicMock()
    o.id               = oid
    o.store_id         = store_id
    o.total_amount_fen = total_fen
    o.table_count      = table_count
    o.banquet_type     = BanquetTypeEnum(banquet_type)
    o.banquet_date     = banquet_date or (date.today() + timedelta(days=7))
    o.contact_name     = contact_name
    o.order_status     = OrderStatusEnum.CONFIRMED
    return o


# ── TestCustomerSegmentation ──────────────────────────────────────────────────

class TestCustomerSegmentation:

    @pytest.mark.asyncio
    async def test_vip_segment_counted(self):
        """total_banquet_amount_fen >= 500000 → vip 段 customer_count >= 1"""
        from src.api.banquet_agent import get_customer_segmentation

        c = _make_customer(total_fen=600000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c]))

        result = await get_customer_segmentation(store_id="S001", db=db, _=_mock_user())

        assert "segments" in result
        vip_seg = next((s for s in result["segments"] if s["segment"] == "vip"), None)
        assert vip_seg is not None
        assert vip_seg["customer_count"] >= 1

    @pytest.mark.asyncio
    async def test_empty_store_returns_zero_totals(self):
        """无客户时 total_customers == 0，各段 customer_count 均为 0"""
        from src.api.banquet_agent import get_customer_segmentation

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_customer_segmentation(store_id="S001", db=db, _=_mock_user())

        assert result["total_customers"] == 0
        total = sum(s["customer_count"] for s in result["segments"])
        assert total == 0


# ── TestVipRanking ─────────────────────────────────────────────────────────────

class TestVipRanking:

    @pytest.mark.asyncio
    async def test_ranking_sorted_by_amount(self):
        """VIP 排行应含 total_yuan 字段，第1条金额正确"""
        from src.api.banquet_agent import get_vip_ranking

        customer = _make_customer(total_fen=1000000)
        last_date = date.today()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([(customer, last_date)]))

        result = await get_vip_ranking(store_id="S001", top_n=20, db=db, _=_mock_user())

        assert result["total"] == 1
        assert result["ranking"][0]["total_yuan"] == pytest.approx(10000.0)

    @pytest.mark.asyncio
    async def test_no_customers_returns_empty_list(self):
        """无客户时返回空 ranking"""
        from src.api.banquet_agent import get_vip_ranking

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_vip_ranking(store_id="S001", top_n=20, db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["ranking"] == []


# ── TestCapacityGaps ───────────────────────────────────────────────────────────

class TestCapacityGaps:

    @pytest.mark.asyncio
    async def test_low_utilization_slot_included(self):
        """存在大厅时，低利用率日期应出现在 gaps 中"""
        from src.api.banquet_agent import get_capacity_gaps

        hall = _make_hall()

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                # First call: BanquetHall query
                return _scalars_returning([hall])
            else:
                # Second call: bookings by date (no bookings → all gaps)
                return _rows_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_capacity_gaps(
            store_id="S001", days=3, threshold_pct=30.0, db=db, _=_mock_user()
        )

        # 3 days, 0 bookings each → all 3 are gaps
        assert result["summary"]["gap_days"] == 3
        assert result["gaps"][0]["utilization_pct"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_no_halls_returns_empty_gaps(self):
        """无厅时直接返回空"""
        from src.api.banquet_agent import get_capacity_gaps

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_capacity_gaps(
            store_id="S001", days=30, threshold_pct=30.0, db=db, _=_mock_user()
        )

        assert result["gaps"] == []
        assert result["summary"]["gap_days"] == 0


# ── TestAcquisitionFunnel ──────────────────────────────────────────────────────

class TestAcquisitionFunnel:

    @pytest.mark.asyncio
    async def test_funnel_stages_computed(self):
        """漏斗各阶段计数正确，total_leads 汇总正确"""
        from src.api.banquet_agent import get_acquisition_funnel
        from src.models.banquet import LeadStageEnum

        row = MagicMock()
        row.current_stage = LeadStageEnum.CONTACTED
        row.cnt           = 5

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([row]))

        result = await get_acquisition_funnel(store_id="S001", months=6, db=db, _=_mock_user())

        assert "stages" in result
        assert result["total_leads"] == 5

    @pytest.mark.asyncio
    async def test_empty_funnel_returns_zero(self):
        """无线索时漏斗 total_leads == 0"""
        from src.api.banquet_agent import get_acquisition_funnel

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_acquisition_funnel(store_id="S001", months=6, db=db, _=_mock_user())

        assert result["total_leads"] == 0


# ── TestChurnRisk ──────────────────────────────────────────────────────────────

class TestChurnRisk:

    @pytest.mark.asyncio
    async def test_inactive_customer_flagged(self):
        """超过 months_inactive 未消费的高频客户应出现在 items 中"""
        from src.api.banquet_agent import get_churn_risk

        customer = _make_customer(total_fen=300000, count=3)
        last_date = date.today() - timedelta(days=400)
        order_cnt = 3

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([(customer, last_date, order_cnt)]))

        result = await get_churn_risk(
            store_id="S001", months_inactive=12, min_banquets=2, top_n=20,
            db=db, _=_mock_user()
        )

        assert result["total"] >= 1
        item = result["items"][0]
        assert item["months_inactive"] is not None
        assert item["months_inactive"] > 12

    @pytest.mark.asyncio
    async def test_no_churn_risk_returns_empty(self):
        """无符合条件客户时返回空 items"""
        from src.api.banquet_agent import get_churn_risk

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_churn_risk(
            store_id="S001", months_inactive=12, min_banquets=2, top_n=20,
            db=db, _=_mock_user()
        )

        assert result["total"] == 0
        assert result["items"] == []


# ── TestUpsellOpportunities ───────────────────────────────────────────────────

class TestUpsellOpportunities:

    @pytest.mark.asyncio
    async def test_upsell_candidates_returned(self):
        """已确认订单价格低于套餐中位价 → 出现在 opportunities"""
        from src.api.banquet_agent import get_upsell_opportunities

        # table_count=10, total=300000 → price_per_table=30000
        # median_pkg_price=50000 → gap exists
        order = _make_order(total_fen=300000, table_count=10)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                # First call: MenuPackage prices → list of (price,) tuples
                r = MagicMock()
                r.all.return_value = [(50000,)]
                return r
            else:
                # Second call: BanquetOrder scalars
                return _scalars_returning([order])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_upsell_opportunities(store_id="S001", top_n=10, db=db, _=_mock_user())

        assert result["total"] >= 1
        opp = result["opportunities"][0]
        assert opp["price_per_table_yuan"] == pytest.approx(300.0)
        assert opp["median_price_yuan"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_no_packages_returns_empty(self):
        """无套餐价格数据时直接返回空 opportunities"""
        from src.api.banquet_agent import get_upsell_opportunities

        db = AsyncMock()
        # First call: MenuPackage prices → empty
        pkg_result = MagicMock()
        pkg_result.all.return_value = []
        db.execute = AsyncMock(return_value=pkg_result)

        result = await get_upsell_opportunities(store_id="S001", top_n=10, db=db, _=_mock_user())

        assert result["opportunities"] == []
        assert result["median_price_yuan"] is None
