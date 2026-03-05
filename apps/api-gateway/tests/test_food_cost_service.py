"""
食材成本分析服务单元测试

覆盖：
  - FoodCostService.get_bom_cost_report（BOM 标准成本报告）
  - FoodCostService.get_store_food_cost_variance（门店差异分析）
  - FoodCostService.get_hq_food_cost_ranking（跨店排名）
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.bom import BOMItem, BOMTemplate
from src.services.food_cost_service import FoodCostService


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_bom(dish_id: str = None, version: str = "v1") -> BOMTemplate:
    bom = BOMTemplate()
    bom.id = uuid.uuid4()
    bom.store_id = "store-001"
    bom.dish_id = uuid.UUID(dish_id) if dish_id else uuid.uuid4()
    bom.version = version
    bom.effective_date = datetime.utcnow()
    bom.expiry_date = None
    bom.yield_rate = Decimal("1.0")
    bom.is_active = True
    bom.is_approved = False
    bom.items = []
    return bom


def _make_item(
    bom: BOMTemplate,
    ingredient_id: str = "ING-001",
    standard_qty: float = 100.0,
    unit_cost: int = 50,
) -> BOMItem:
    item = BOMItem()
    item.id = uuid.uuid4()
    item.bom_id = bom.id
    item.store_id = bom.store_id
    item.ingredient_id = ingredient_id
    item.standard_qty = Decimal(str(standard_qty))
    item.unit = "g"
    item.unit_cost = unit_cost
    item.waste_factor = Decimal("0.0")
    item.is_key_ingredient = False
    item.is_optional = False
    return item


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_dish(price_yuan: float) -> MagicMock:
    dish = MagicMock()
    dish.price = Decimal(str(price_yuan))
    return dish


# ── FoodCostService.get_bom_cost_report ──────────────────────────────────────

class TestBOMCostReport:

    @pytest.mark.asyncio
    async def test_bom_cost_report_no_items(self):
        """BOM 无 items 时 food_cost_pct = 0"""
        db = _mock_db()
        bom = _make_bom()
        bom.items = []

        with patch("src.services.food_cost_service.BOMService") as MockBOMService:
            mock_svc = MagicMock()
            mock_svc.get_bom = AsyncMock(return_value=bom)
            MockBOMService.return_value = mock_svc
            db.get = AsyncMock(return_value=_make_dish(50.0))

            report = await FoodCostService.get_bom_cost_report(str(bom.id), db)

        assert report is not None
        assert report["food_cost_pct"] == 0.0
        assert report["total_cost_fen"] == 0.0
        assert report["items"] == []

    @pytest.mark.asyncio
    async def test_bom_cost_report_single_item(self):
        """标准单食材成本计算正确

        price = 100元 = 10000分
        item: qty=100, unit_cost=25 → item_cost_fen=2500
        food_cost_pct = 2500 / (100 * 100) * 100 = 25%
        """
        db = _mock_db()
        bom = _make_bom()
        item = _make_item(bom, standard_qty=100.0, unit_cost=25)
        bom.items = [item]

        with patch("src.services.food_cost_service.BOMService") as MockBOMService:
            mock_svc = MagicMock()
            mock_svc.get_bom = AsyncMock(return_value=bom)
            MockBOMService.return_value = mock_svc
            db.get = AsyncMock(return_value=_make_dish(100.0))

            report = await FoodCostService.get_bom_cost_report(str(bom.id), db)

        assert report["total_cost_fen"] == 2500.0
        assert report["food_cost_pct"] == 25.0
        assert len(report["items"]) == 1
        assert report["items"][0]["item_cost_fen"] == 2500.0

    @pytest.mark.asyncio
    async def test_bom_cost_report_items_sorted_by_cost(self):
        """items 按成本降序排列"""
        db = _mock_db()
        bom = _make_bom()
        cheap = _make_item(bom, "ING-CHEAP", standard_qty=10.0, unit_cost=5)    # 50
        expensive = _make_item(bom, "ING-EXP", standard_qty=100.0, unit_cost=80)  # 8000
        mid = _make_item(bom, "ING-MID", standard_qty=50.0, unit_cost=20)      # 1000
        bom.items = [cheap, mid, expensive]

        with patch("src.services.food_cost_service.BOMService") as MockBOMService:
            mock_svc = MagicMock()
            mock_svc.get_bom = AsyncMock(return_value=bom)
            MockBOMService.return_value = mock_svc
            db.get = AsyncMock(return_value=_make_dish(200.0))

            report = await FoodCostService.get_bom_cost_report(str(bom.id), db)

        costs = [it["item_cost_fen"] for it in report["items"]]
        assert costs == sorted(costs, reverse=True)
        assert costs[0] == 8000.0  # expensive first

    @pytest.mark.asyncio
    async def test_bom_cost_report_bom_not_found(self):
        """BOM 不存在时返回 None"""
        db = _mock_db()

        with patch("src.services.food_cost_service.BOMService") as MockBOMService:
            mock_svc = MagicMock()
            mock_svc.get_bom = AsyncMock(return_value=None)
            MockBOMService.return_value = mock_svc

            report = await FoodCostService.get_bom_cost_report(str(uuid.uuid4()), db)

        assert report is None


# ── FoodCostService.get_store_food_cost_variance ─────────────────────────────

class TestStoreFoodCostVariance:

    @pytest.mark.asyncio
    async def test_store_variance_no_revenue(self):
        """收入为 0 时 actual_cost_pct = 0，不除零"""
        db = _mock_db()

        results_iter = iter([
            _make_scalar_result(0),       # SQL1: actual_cost = 0
            _make_scalar_result(0),       # SQL2: revenue = 0
            _make_fetchall_result([]),    # SQL3: no bom rows
            _make_fetchall_result([]),    # SQL4: no top items
        ])
        db.execute = AsyncMock(side_effect=lambda *a, **kw: next(results_iter))

        variance = await FoodCostService.get_store_food_cost_variance(
            store_id="store-001",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            db=db,
        )

        assert variance["actual_cost_pct"] == 0.0
        assert variance["variance_pct"] == 0.0
        assert variance["variance_status"] == "ok"

    @pytest.mark.asyncio
    async def test_store_variance_calculation(self):
        """已知数值验证 actual_cost_pct / theoretical_pct / variance 计算

        actual_cost = 30000 分, revenue = 100000 分
          → actual_pct = 30%

        BOM: price = 50元, computed_cost = 1000 分
          → theoretical_pct = 1000 / (50 * 100) * 100 = 20%

        variance = 30 - 20 = 10% → critical (≥5%)
        """
        db = _mock_db()

        bom_row = MagicMock()
        bom_row.price = Decimal("50.00")
        bom_row.computed_cost = Decimal("1000")

        results_iter = iter([
            _make_scalar_result(30000),           # SQL1: actual_cost
            _make_scalar_result(100000),          # SQL2: revenue
            _make_fetchall_result([bom_row]),     # SQL3: bom rows
            _make_fetchall_result([]),            # SQL4: top items
        ])
        db.execute = AsyncMock(side_effect=lambda *a, **kw: next(results_iter))

        variance = await FoodCostService.get_store_food_cost_variance(
            store_id="store-001",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            db=db,
        )

        assert variance["actual_cost_pct"] == 30.0
        assert variance["theoretical_pct"] == 20.0
        assert variance["variance_pct"] == 10.0
        assert variance["variance_status"] == "critical"


# ── FoodCostService.get_hq_food_cost_ranking ─────────────────────────────────

class TestHQFoodCostRanking:

    @pytest.mark.asyncio
    async def test_hq_ranking_sorted_by_variance(self):
        """排名按 variance_pct 倒序；全局摘要正确"""
        db = _mock_db()

        store_a = MagicMock(id="S001", name="店A", is_active=True)
        store_b = MagicMock(id="S002", name="店B", is_active=True)
        store_c = MagicMock(id="S003", name="店C", is_active=True)

        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[store_a, store_b, store_c])
        execute_result = MagicMock()
        execute_result.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=execute_result)

        # 三家门店差异数据
        def _variance(sid, actual_cost_pct, theoretical_pct, variance_pct, status):
            return {
                "store_id": sid,
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "actual_cost_fen": 0.0,
                "actual_cost_yuan": 0.0,
                "revenue_fen": 100000.0,
                "revenue_yuan": 1000.0,
                "actual_cost_pct": actual_cost_pct,
                "theoretical_pct": theoretical_pct,
                "variance_pct": variance_pct,
                "variance_status": status,
                "top_ingredients": [],
            }

        variance_a = _variance("S001", 25.0, 22.0, 3.0, "warning")   # rank 2
        variance_b = _variance("S002", 38.0, 22.0, 16.0, "critical")  # rank 1
        variance_c = _variance("S003", 21.0, 22.0, -1.0, "ok")        # rank 3

        with patch.object(
            FoodCostService,
            "get_store_food_cost_variance",
            new_callable=AsyncMock,
            side_effect=[variance_a, variance_b, variance_c],
        ):
            ranking = await FoodCostService.get_hq_food_cost_ranking(
                start_date=date(2026, 2, 1),
                end_date=date(2026, 2, 28),
                db=db,
            )

        variances = [s["variance_pct"] for s in ranking["stores"]]
        assert variances == sorted(variances, reverse=True)
        assert ranking["stores"][0]["store_id"] == "S002"   # highest variance
        assert ranking["stores"][0]["rank"] == 1
        assert ranking["summary"]["store_count"] == 3
        assert ranking["summary"]["over_budget_count"] == 2  # warning + critical


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_scalar_result(value):
    """构造返回单值的 execute mock 结果"""
    r = MagicMock()
    r.scalar = MagicMock(return_value=value)
    return r


def _make_fetchall_result(rows):
    """构造返回行列表的 execute mock 结果"""
    r = MagicMock()
    r.fetchall = MagicMock(return_value=rows)
    return r
