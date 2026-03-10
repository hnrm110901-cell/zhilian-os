"""
Banquet Agent Phase 19 — 单元测试

覆盖端点：
  - get_cost_breakdown
  - get_post_event_summary
  - get_event_performance_ranking
  - generate_collection_message
  - get_payment_aging
  - get_quarterly_summary
  - get_operations_health_score
  - get_monthly_benchmark
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


def _make_order(oid="O-001", store_id="S001", status="completed",
                days_ago=10, total_fen=500000, paid_fen=500000,
                table_count=20, people_count=200, btype="wedding",
                deposit_status="paid", deposit_fen=100000):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum, DepositStatusEnum
    o = MagicMock()
    o.id = oid
    o.store_id = store_id
    o.order_status = (
        OrderStatusEnum.COMPLETED  if status == "completed"  else
        OrderStatusEnum.CONFIRMED  if status == "confirmed"  else
        OrderStatusEnum.CANCELLED
    )
    o.banquet_date   = date.today() - timedelta(days=days_ago)
    o.banquet_type   = BanquetTypeEnum.WEDDING if btype == "wedding" else BanquetTypeEnum.BIRTHDAY
    o.total_amount_fen = total_fen
    o.paid_fen         = paid_fen
    o.deposit_fen      = deposit_fen
    o.deposit_status   = DepositStatusEnum.PAID if deposit_status == "paid" else DepositStatusEnum.UNPAID
    o.table_count      = table_count
    o.people_count     = people_count
    o.contact_name     = "张三"
    o.contact_phone    = "138-0000-0000"
    o.remark           = None
    o.created_at       = datetime.utcnow() - timedelta(days=days_ago + 5)
    return o


def _make_snap(oid="O-001", rev=500000, ingredient=100000, labor=50000,
               material=20000, other=10000):
    s = MagicMock()
    s.banquet_order_id     = oid
    s.revenue_fen          = rev
    s.ingredient_cost_fen  = ingredient
    s.labor_cost_fen       = labor
    s.material_cost_fen    = material
    s.other_cost_fen       = other
    s.gross_profit_fen     = rev - ingredient - labor - material - other
    s.gross_margin_pct     = round((rev - ingredient - labor - material - other) / rev * 100, 1)
    return s


def _make_review(oid="O-001", rating=5, summary="非常满意"):
    r = MagicMock()
    r.banquet_order_id = oid
    r.customer_rating  = rating
    r.ai_score         = rating * 20.0
    r.ai_summary       = summary
    r.improvement_tags = []
    r.created_at       = datetime.utcnow()
    return r


def _make_task(tid="T-001", oid="O-001", status="done"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id = tid
    t.banquet_order_id = oid
    t.task_status = TaskStatusEnum.DONE if status == "done" else TaskStatusEnum.PENDING
    return t


def _make_contract(oid="O-001", status="signed"):
    c = MagicMock()
    c.banquet_order_id = oid
    c.contract_status  = status
    c.signed_at        = datetime.utcnow() if status == "signed" else None
    return c


def _make_hall(hid="H-001", store_id="S001"):
    h = MagicMock()
    h.id         = hid
    h.store_id   = store_id
    h.is_active  = True
    h.max_tables = 30
    return h


def _make_lead(lid="L-001", store_id="S001", source="微信", converted_oid=None):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id             = lid
    l.store_id       = store_id
    l.source_channel = source
    l.current_stage  = LeadStageEnum.WON if converted_oid else LeadStageEnum.NEW
    l.converted_order_id = converted_oid
    return l


# ── TestCostBreakdown ────────────────────────────────────────────────────────

class TestCostBreakdown:

    @pytest.mark.asyncio
    async def test_returns_by_type_sorted_by_revenue(self):
        """有成本快照时按宴会类型返回并按收入降序排序"""
        from src.api.banquet_agent import get_cost_breakdown
        from src.models.banquet import BanquetTypeEnum

        row1 = MagicMock()
        row1.banquet_type   = BanquetTypeEnum.WEDDING
        row1.rev            = 1000000
        row1.ingredient     = 200000
        row1.labor          = 100000
        row1.material       = 50000
        row1.other          = 30000
        row1.profit         = 620000
        row1.cnt            = 5

        row2 = MagicMock()
        row2.banquet_type   = BanquetTypeEnum.BIRTHDAY
        row2.rev            = 300000
        row2.ingredient     = 80000
        row2.labor          = 40000
        row2.material       = 10000
        row2.other          = 5000
        row2.profit         = 165000
        row2.cnt            = 2

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([row1, row2]))

        result = await get_cost_breakdown(store_id="S001", db=db, _=_mock_user())

        assert len(result["by_type"]) == 2
        assert result["by_type"][0]["banquet_type"] == "wedding"
        assert result["by_type"][0]["revenue_yuan"] == pytest.approx(10000.0)
        assert result["by_type"][0]["gross_margin_pct"] == pytest.approx(62.0)

    @pytest.mark.asyncio
    async def test_empty_returns_zero_totals(self):
        """无快照时返回空列表，合计为零"""
        from src.api.banquet_agent import get_cost_breakdown

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_cost_breakdown(store_id="S001", db=db, _=_mock_user())

        assert result["by_type"] == []
        assert result["total_revenue_yuan"] == 0.0


# ── TestPostEventSummary ─────────────────────────────────────────────────────

class TestPostEventSummary:

    @pytest.mark.asyncio
    async def test_completion_rate_computed(self):
        """4个任务 3个完成 → 75%"""
        from src.api.banquet_agent import get_post_event_summary

        order = _make_order("O-001", paid_fen=500000, total_fen=500000)
        snap  = _make_snap("O-001")
        tasks = [
            _make_task("T-1", status="done"),
            _make_task("T-2", status="done"),
            _make_task("T-3", status="done"),
            _make_task("T-4", status="pending"),
        ]
        review = _make_review("O-001", rating=5)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([order])
            if n == 2: return _scalars_returning([snap])
            if n == 3: return _scalars_returning(tasks)
            if n == 4: return _scalars_returning([review])
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_post_event_summary(store_id="S001", order_id="O-001", db=db, _=_mock_user())

        assert result["tasks"]["total"]   == 4
        assert result["tasks"]["done"]    == 3
        assert result["tasks"]["completion_rate_pct"] == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_no_snapshot_financials_none(self):
        """无利润快照时 financials 中收入/毛利为 None"""
        from src.api.banquet_agent import get_post_event_summary

        order = _make_order("O-001")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([order])
            if n == 2: return _scalars_returning([])    # no snap
            if n == 3: return _scalars_returning([])    # no tasks
            if n == 4: return _scalars_returning([])    # no review
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_post_event_summary(store_id="S001", order_id="O-001", db=db, _=_mock_user())

        assert result["financials"]["revenue_yuan"]      is None
        assert result["financials"]["gross_profit_yuan"] is None


# ── TestEventPerformanceRanking ───────────────────────────────────────────────

class TestEventPerformanceRanking:

    @pytest.mark.asyncio
    async def test_sorted_by_margin_desc(self):
        """按毛利率降序排列"""
        from src.api.banquet_agent import get_event_performance_ranking
        from src.models.banquet import BanquetTypeEnum, OrderStatusEnum

        order_a = _make_order("O-A", total_fen=1000000)
        order_b = _make_order("O-B", total_fen=500000)

        row_a = (order_a, 75.0, 750000, 5)
        row_b = (order_b, 40.0, 200000, 4)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([row_b, row_a]))  # out of order

        result = await get_event_performance_ranking(store_id="S001", db=db, _=_mock_user())

        ranking = result["ranking"]
        assert len(ranking) == 2
        assert ranking[0]["order_id"] == "O-A"   # higher margin first
        assert ranking[0]["gross_margin_pct"] == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_empty_orders_returns_empty(self):
        """无订单时返回空列表"""
        from src.api.banquet_agent import get_event_performance_ranking

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_event_performance_ranking(store_id="S001", db=db, _=_mock_user())

        assert result["ranking"] == []
        assert result["total"]   == 0


# ── TestPaymentAging ─────────────────────────────────────────────────────────

class TestPaymentAging:

    @pytest.mark.asyncio
    async def test_overdue_45days_lands_in_31_60_bucket(self):
        """逾期 45 天的未付款订单落在 31-60 桶"""
        from src.api.banquet_agent import get_payment_aging

        overdue_order = _make_order("O-001", status="completed",
                                    total_fen=300000, paid_fen=0,
                                    days_ago=45)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([overdue_order]))

        result = await get_payment_aging(store_id="S001", db=db, _=_mock_user())

        buckets = {b["label"]: b for b in result["buckets"]}
        assert buckets["31-60天"]["count"]       == 1
        assert buckets["31-60天"]["amount_yuan"] == pytest.approx(3000.0)
        assert result["total_overdue_yuan"]      == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_fully_paid_orders_excluded(self):
        """全额付清的订单不计入逾期"""
        from src.api.banquet_agent import get_payment_aging

        paid_order = _make_order("O-002", status="completed",
                                  total_fen=200000, paid_fen=200000,
                                  days_ago=20)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([paid_order]))

        result = await get_payment_aging(store_id="S001", db=db, _=_mock_user())

        assert result["total_overdue_yuan"] == pytest.approx(0.0)
        assert all(b["count"] == 0 for b in result["buckets"])


# ── TestOperationsHealthScore ─────────────────────────────────────────────────

class TestOperationsHealthScore:

    @pytest.mark.asyncio
    async def test_all_perfect_scores_100(self):
        """全部满分条件 → 总分 = 100"""
        from src.api.banquet_agent import get_operations_health_score

        order = _make_order("O-001", status="completed", total_fen=300000, paid_fen=300000)
        hall  = _make_hall()

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([order])   # orders
            if n == 2: return _scalar_returning(1)           # signed contracts
            if n == 3: return _scalar_returning(5.0)         # avg rating
            if n == 4: return _scalars_returning([hall])     # halls
            if n == 5: return _scalar_returning(1000)        # booked slots (>capacity → capped at 100%)
            if n == 6: return _scalar_returning(10)          # total leads
            if n == 7: return _scalar_returning(3)           # won leads (30% → full conv score)
            return _scalar_returning(0)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_operations_health_score(store_id="S001", months=3, db=db, _=_mock_user())

        assert result["total_score"] == pytest.approx(100.0)
        assert result["grade"] == "A"

    @pytest.mark.asyncio
    async def test_dimension_scores_sum_to_total(self):
        """分项得分之和 = 总分"""
        from src.api.banquet_agent import get_operations_health_score

        order = _make_order("O-001", status="completed", total_fen=200000, paid_fen=100000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([order])
            if n == 2: return _scalar_returning(0)    # no signed contracts
            if n == 3: return _scalar_returning(3.0)  # avg rating 3/5 = 60% → 12pts
            if n == 4: return _scalars_returning([])  # no halls
            if n == 5: return _scalar_returning(0)    # 0 booked
            if n == 6: return _scalar_returning(5)    # 5 leads
            if n == 7: return _scalar_returning(0)    # 0 won
            return _scalar_returning(0)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_operations_health_score(store_id="S001", months=3, db=db, _=_mock_user())

        dim_sum = sum(d["score"] for d in result["dimensions"])
        assert dim_sum == pytest.approx(result["total_score"])


# ── TestMonthlyBenchmark ──────────────────────────────────────────────────────

class TestMonthlyBenchmark:

    @pytest.mark.asyncio
    async def test_returns_data_list(self):
        """有历史订单时返回 data 列表"""
        from src.api.banquet_agent import get_monthly_benchmark

        row = MagicMock()
        row.yr        = 2026
        row.mo        = 1
        row.cnt       = 3
        row.rev_fen   = 600000
        row.profit_fen = 200000

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([row]))

        result = await get_monthly_benchmark(store_id="S001", months=12, db=db, _=_mock_user())

        assert len(result["data"]) == 1
        assert result["data"][0]["label"]          == "2026-01"
        assert result["data"][0]["revenue_yuan"]   == pytest.approx(6000.0)
        assert result["data"][0]["event_count"]    == 3

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty_data(self):
        """无历史数据时 data = []"""
        from src.api.banquet_agent import get_monthly_benchmark

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning([]))

        result = await get_monthly_benchmark(store_id="S001", months=12, db=db, _=_mock_user())

        assert result["data"] == []
