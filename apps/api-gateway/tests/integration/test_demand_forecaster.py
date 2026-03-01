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


# ---------------------------------------------------------------------------
# 5. _statistical() 路径（14-60 天历史数据）
# ---------------------------------------------------------------------------

class TestStatistical:
    """
    覆盖 _statistical() 移动加权平均路径:
    - 3行数据验证权重算术（最新权重最高）
    - 单行数据时结果等于该行营收
    - DB返回空行时降级到 rule_based
    - DB抛出异常时降级到 rule_based
    """

    @staticmethod
    def _make_stat_row(revenue: float):
        row = MagicMock()
        row.revenue = revenue
        return row

    @staticmethod
    def _make_db(history_days: int = 30, stat_rows=None, bom_rows=None, item_rows=None):
        """
        Call sequence:
          0: _get_history_days  → scalar(history_days)
          1: statistical query  → all(stat_rows)
          2: BOM template       → all(bom_rows)
          3: BOM items          → all(item_rows)
        """
        db = MagicMock()
        stat_rows = stat_rows or []
        bom_rows = bom_rows or []
        item_rows = item_rows or []
        call_count = [0]

        async def execute_sequence(stmt):
            result = MagicMock()
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                result.scalar = MagicMock(return_value=history_days)
                result.all = MagicMock(return_value=[])
            elif n == 1:
                result.all = MagicMock(return_value=stat_rows)
                result.scalar = MagicMock(return_value=None)
            elif n == 2:
                result.all = MagicMock(return_value=bom_rows)
                result.scalar = MagicMock(return_value=None)
            else:
                result.all = MagicMock(return_value=item_rows)
                result.scalar = MagicMock(return_value=None)
            return result

        db.execute = execute_sequence
        return db

    @pytest.mark.asyncio
    async def test_weighted_average_three_rows(self):
        """weights=[1,2,3], (1000×1 + 2000×2 + 3000×3) / 6 ≈ 2333.33"""
        stat_rows = [
            self._make_stat_row(1000.0),
            self._make_stat_row(2000.0),
            self._make_stat_row(3000.0),
        ]
        db = self._make_db(history_days=30, stat_rows=stat_rows)
        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        expected = (1000 * 1 + 2000 * 2 + 3000 * 3) / 6
        assert result.estimated_revenue == pytest.approx(expected, rel=1e-6)
        assert result.basis == "statistical"
        assert result.confidence == "medium"

    @pytest.mark.asyncio
    async def test_single_row_returns_that_revenue(self):
        """1行数据时权重=1，结果等于该行营收"""
        stat_rows = [self._make_stat_row(5500.0)]
        db = self._make_db(history_days=20, stat_rows=stat_rows)
        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        assert result.estimated_revenue == pytest.approx(5500.0)
        assert result.basis == "statistical"

    @pytest.mark.asyncio
    async def test_empty_rows_fallback_to_rule_based(self):
        """DB返回空行时降级到 rule_based（低置信度）"""
        db = self._make_db(history_days=30, stat_rows=[])
        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        assert result.basis == "rule_based"
        assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_db_exception_fallback_to_rule_based(self):
        """DB抛出异常时降级到 rule_based"""
        db = MagicMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            if n == 0:
                r.scalar = MagicMock(return_value=30)  # 14-60 → _statistical
                return r
            raise RuntimeError("connection lost")

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        assert result.basis == "rule_based"
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# 6. _ml_prophet() ImportError → 降级到 _statistical
# ---------------------------------------------------------------------------

class TestMLProphet:
    """prophet 包缺失时 ImportError 被捕获，降级到 statistical（或 rule_based）"""

    @pytest.mark.asyncio
    async def test_prophet_import_error_fallback(self):
        """sys.modules["prophet"]=None 触发 ImportError → 降级到 statistical"""
        db = MagicMock()
        call_count = [0]
        stat_row = MagicMock()
        stat_row.revenue = 4000.0

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            if n == 0:
                r.scalar = MagicMock(return_value=70)  # ≥60 → ML path
                r.all = MagicMock(return_value=[])
            elif n == 1:
                # _statistical revenue query → 1 sampled row
                r.all = MagicMock(return_value=[stat_row])
                r.scalar = MagicMock(return_value=None)
            else:
                # BOM queries → empty
                r.all = MagicMock(return_value=[])
                r.scalar = MagicMock(return_value=None)
            return r

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)

        # Setting prophet to None makes "from prophet import Prophet" raise ImportError
        with patch.dict("sys.modules", {"prophet": None}):
            result = await fc.predict("S1", date(2026, 3, 2))

        assert result.basis in ("statistical", "rule_based")
        assert result.confidence in ("medium", "low")
