"""
DemandForecaster 单元测试

覆盖：
- 无 DB → rule_based，items=[]
- 无 BOM 数据 → items=[]
- 正常 BOM 数据 → items 按 suggested_quantity 降序，含 waste_factor
- 多菜品共享食材 → 需求量正确累加
- _fetch_bom_items DB 异常 → 返回空列表（不抛出）
- 周末系数（1.3×）生效
"""
import sys
import uuid
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# Pre-stub agent_service singleton to prevent import-time crash
sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.services.demand_forecaster import DemandForecaster, ForecastItem, ForecastResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bom_row(bom_id: str, price_fen: int = 5000):
    """Simulate a row returned from the BOM template + Dish join query."""
    row = MagicMock()
    row.id = bom_id
    row.price = price_fen
    return row


def _make_item_row(
    ingredient_id: str,
    name: str,
    unit: str,
    standard_qty: float,
    waste_factor: float = 0.0,
):
    row = MagicMock()
    row.ingredient_id = ingredient_id
    row.name = name
    row.unit = unit
    row.standard_qty = Decimal(str(standard_qty))
    row.waste_factor = Decimal(str(waste_factor))
    return row


def _make_db(bom_rows=None, item_rows=None, history_days: int = 0):
    """Build a mock async DB session."""
    db = MagicMock()

    async def execute(stmt):
        result = MagicMock()
        # _get_history_days query returns a scalar
        result.scalar = MagicMock(return_value=history_days)
        # bom_stmt vs items_stmt distinguished by call order
        result.all = MagicMock(return_value=[])
        return result

    # We need different results per call, use a counter
    call_count = [0]
    bom_rows = bom_rows or []
    item_rows = item_rows or []

    async def execute_sequence(stmt):
        result = MagicMock()
        n = call_count[0]
        call_count[0] += 1
        if n == 0:
            # _get_history_days: scalar
            result.scalar = MagicMock(return_value=history_days)
            result.all = MagicMock(return_value=[])
        elif n == 1:
            # bom_stmt
            result.all = MagicMock(return_value=bom_rows)
            result.scalar = MagicMock(return_value=None)
        else:
            # items_stmt
            result.all = MagicMock(return_value=item_rows)
            result.scalar = MagicMock(return_value=None)
        return result

    db.execute = execute_sequence
    return db


# ---------------------------------------------------------------------------
# 1. 无 DB → rule_based 降级，items=[]
# ---------------------------------------------------------------------------

class TestNoDB:
    @pytest.mark.asyncio
    async def test_no_db_returns_rule_based(self):
        fc = DemandForecaster(db_session=None)
        result = await fc.predict("S1", date(2026, 3, 3))  # Monday
        assert result.basis == "rule_based"
        assert result.confidence == "low"
        assert result.items == []

    @pytest.mark.asyncio
    async def test_no_db_weekday_revenue_is_3000(self):
        fc = DemandForecaster(db_session=None)
        result = await fc.predict("S1", date(2026, 3, 2))  # Monday
        assert result.estimated_revenue == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_no_db_weekend_revenue_is_3900(self):
        fc = DemandForecaster(db_session=None)
        result = await fc.predict("S1", date(2026, 3, 7))  # Saturday
        assert result.estimated_revenue == pytest.approx(3900.0)

    @pytest.mark.asyncio
    async def test_no_db_note_contains_hint(self):
        fc = DemandForecaster(db_session=None)
        result = await fc.predict("S1", date(2026, 3, 2))
        assert result.note is not None
        assert "14天" in result.note


# ---------------------------------------------------------------------------
# 2. 有 DB 但 BOM 表无数据 → items=[]
# ---------------------------------------------------------------------------

class TestEmptyBOM:
    @pytest.mark.asyncio
    async def test_empty_bom_returns_empty_items(self):
        db = _make_db(bom_rows=[], item_rows=[], history_days=0)
        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))
        assert result.items == []
        assert result.basis == "rule_based"


# ---------------------------------------------------------------------------
# 3. 正常 BOM 数据 → items 正确计算
# ---------------------------------------------------------------------------

class TestBOMItems:
    @pytest.mark.asyncio
    async def test_single_dish_single_ingredient(self):
        bom_id = str(uuid.uuid4())
        # 1 dish, price 50元(5000分), standard_qty=0.5kg, no waste
        bom_rows = [_make_bom_row(bom_id, price_fen=5000)]
        item_rows = [_make_item_row("ING_001", "猪肉", "kg", 0.5, waste_factor=0.0)]
        db = _make_db(bom_rows, item_rows, history_days=0)

        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))  # weekday → 3000 revenue

        # portions_per_dish = (3000 / 50) / 1 = 60
        # qty = 0.5 * 1.0 * 60 = 30.0
        assert len(result.items) == 1
        item = result.items[0]
        assert item.sku_id == "ING_001"
        assert item.name == "猪肉"
        assert item.unit == "kg"
        assert item.suggested_quantity == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_waste_factor_applied(self):
        bom_id = str(uuid.uuid4())
        bom_rows = [_make_bom_row(bom_id, price_fen=5000)]
        # waste_factor = 0.1 → effective qty per portion = 0.5 * 1.1
        item_rows = [_make_item_row("ING_001", "猪肉", "kg", 0.5, waste_factor=0.1)]
        db = _make_db(bom_rows, item_rows, history_days=0)

        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))  # weekday → 3000

        # portions_per_dish = (3000/50)/1 = 60
        # qty = 0.5 * 1.1 * 60 = 33.0
        assert result.items[0].suggested_quantity == pytest.approx(33.0)

    @pytest.mark.asyncio
    async def test_items_sorted_by_quantity_descending(self):
        bom_id = str(uuid.uuid4())
        bom_rows = [_make_bom_row(bom_id, price_fen=5000)]
        item_rows = [
            _make_item_row("ING_001", "猪肉", "kg", 0.2),
            _make_item_row("ING_002", "蔬菜", "kg", 1.0),
            _make_item_row("ING_003", "豆腐", "块", 0.5),
        ]
        db = _make_db(bom_rows, item_rows, history_days=0)

        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        quantities = [i.suggested_quantity for i in result.items]
        assert quantities == sorted(quantities, reverse=True)

    @pytest.mark.asyncio
    async def test_shared_ingredient_across_two_dishes(self):
        """两道菜共用同一食材时，需求量应累加"""
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
        bom_rows = [
            _make_bom_row(id1, price_fen=5000),  # 50元
            _make_bom_row(id2, price_fen=5000),  # 50元
        ]
        # Both dishes use ING_001 (0.5 kg each)
        item_rows = [
            _make_item_row("ING_001", "猪肉", "kg", 0.5),
            _make_item_row("ING_001", "猪肉", "kg", 0.5),
        ]
        db = _make_db(bom_rows, item_rows, history_days=0)

        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))  # 3000 revenue

        # avg_price = 50, num_dishes = 2
        # portions_per_dish = (3000/50)/2 = 30
        # ING_001 total = 0.5*30 + 0.5*30 = 30.0
        assert len(result.items) == 1
        assert result.items[0].suggested_quantity == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_reason_field_set(self):
        bom_id = str(uuid.uuid4())
        bom_rows = [_make_bom_row(bom_id, price_fen=5000)]
        item_rows = [_make_item_row("ING_001", "猪肉", "kg", 0.5)]
        db = _make_db(bom_rows, item_rows, history_days=0)

        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        assert result.items[0].reason == "基于BOM配方及预估营收"


# ---------------------------------------------------------------------------
# 4. DB 异常 → items=[] 不抛出
# ---------------------------------------------------------------------------

class TestDBException:
    @pytest.mark.asyncio
    async def test_fetch_bom_items_db_error_returns_empty(self):
        db = MagicMock()
        call_count = [0]

        async def execute_with_error(stmt):
            result = MagicMock()
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                result.scalar = MagicMock(return_value=0)  # history_days
            else:
                raise RuntimeError("DB connection lost")
            return result

        db.execute = execute_with_error
        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        assert result.items == []
        assert result.basis == "rule_based"
