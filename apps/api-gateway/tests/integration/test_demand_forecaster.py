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


# ---------------------------------------------------------------------------
# 7. _get_history_days exception path (lines 103-105)
# ---------------------------------------------------------------------------

class TestGetHistoryDaysException:
    """Lines 103-105: exception handler in _get_history_days → returns 0."""

    @pytest.mark.asyncio
    async def test_db_execute_raises_returns_zero(self):
        """When db.execute raises, _get_history_days returns 0 → rule_based path."""
        db = MagicMock()

        async def execute_raises(stmt):
            raise RuntimeError("DB unavailable")

        db.execute = execute_raises
        fc = DemandForecaster(db_session=db)
        result = await fc.predict("S1", date(2026, 3, 2))

        # history_days == 0 → rule_based
        assert result.basis == "rule_based"
        assert result.confidence == "low"
        assert result.items == []


# ---------------------------------------------------------------------------
# 8. _statistical() when no DB → delegates to _rule_based (line 148)
# ---------------------------------------------------------------------------

class TestStatisticalNoDB:
    """Line 148: _statistical() checks if not self._db → _rule_based."""

    @pytest.mark.asyncio
    async def test_statistical_without_db_falls_back_to_rule_based(self):
        """
        Force entry into _statistical() by mocking _get_history_days to return
        a value in [14, 60), then let _db be None so line 148 fires.
        """
        fc = DemandForecaster(db_session=None)
        # Monkey-patch _get_history_days to return 30 (would normally require DB)
        async def fake_history(store_id):
            return 30
        fc._get_history_days = fake_history

        result = await fc._statistical("S1", date(2026, 3, 2), history_days=30)

        assert result.basis == "rule_based"
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# 9. _ml_prophet() ImportError → fallback to statistical (lines 214-253)
# ---------------------------------------------------------------------------

class TestMLProphetImportError:
    """Lines 214-253: when prophet is not installed, _ml_prophet falls back."""

    @pytest.mark.asyncio
    async def test_prophet_import_error_falls_back_to_statistical(self):
        """
        patch.dict sys.modules with {"prophet": None} forces ImportError on
        `from prophet import Prophet`, which triggers the except ImportError
        branch → falls back to _statistical (or _rule_based if no rows).
        """
        db = MagicMock()
        call_count = [0]
        stat_row = MagicMock()
        stat_row.revenue = 4500.0

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            if n == 0:
                # _get_history_days: scalar ≥ 60 → ML path
                r.scalar = MagicMock(return_value=80)
                r.all = MagicMock(return_value=[])
            elif n == 1:
                # _statistical revenue query
                r.all = MagicMock(return_value=[stat_row])
                r.scalar = MagicMock(return_value=None)
            else:
                # BOM queries → empty
                r.all = MagicMock(return_value=[])
                r.scalar = MagicMock(return_value=None)
            return r

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)

        with patch.dict("sys.modules", {"prophet": None}):
            result = await fc.predict("S1", date(2026, 3, 2))

        assert result.basis in ("statistical", "rule_based")

    @pytest.mark.asyncio
    async def test_ml_prophet_direct_import_error_falls_back(self):
        """Call _ml_prophet directly with prophet blocked."""
        db = MagicMock()
        call_count = [0]
        stat_row = MagicMock()
        stat_row.revenue = 3500.0

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            r.all = MagicMock(return_value=[stat_row])
            r.scalar = MagicMock(return_value=None)
            return r

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)

        with patch.dict("sys.modules", {"prophet": None}):
            result = await fc._ml_prophet("S1", date(2026, 3, 2), history_days=80)

        assert result.basis in ("statistical", "rule_based")


# ---------------------------------------------------------------------------
# 10. _ml_prophet() non-ImportError exception → fallback (lines 265-267)
# ---------------------------------------------------------------------------

class TestMLProphetException:
    """Lines 265-267: non-ImportError exception in _ml_prophet → _statistical."""

    @pytest.mark.asyncio
    async def test_non_import_error_falls_back_to_statistical(self):
        """
        When prophet import succeeds but a later step raises a non-ImportError
        exception, the except Exception branch (lines 265-267) fires and
        falls back to _statistical.
        """
        db = MagicMock()
        call_count = [0]
        stat_row = MagicMock()
        stat_row.revenue = 5000.0

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            if n == 0:
                # _get_history_days: ≥ 60 → ML path
                r.scalar = MagicMock(return_value=90)
                r.all = MagicMock(return_value=[])
            elif n == 1:
                # _statistical fallback revenue query
                r.all = MagicMock(return_value=[stat_row])
                r.scalar = MagicMock(return_value=None)
            else:
                r.all = MagicMock(return_value=[])
                r.scalar = MagicMock(return_value=None)
            return r

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)

        # Create a fake prophet module whose Prophet class raises on instantiation
        fake_prophet_module = MagicMock()
        fake_prophet_module.Prophet = MagicMock(side_effect=RuntimeError("prophet crash"))

        with patch.dict("sys.modules", {"prophet": fake_prophet_module, "pandas": MagicMock()}):
            result = await fc.predict("S1", date(2026, 3, 2))

        assert result.basis in ("statistical", "rule_based")

    @pytest.mark.asyncio
    async def test_ml_prophet_db_execute_raises_falls_back(self):
        """
        _ml_prophet DB execute raises RuntimeError → except Exception branch
        → falls back to _statistical.
        """
        db = MagicMock()
        call_count = [0]
        stat_row = MagicMock()
        stat_row.revenue = 4200.0

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            if n == 0:
                # _get_history_days: ≥ 60
                r.scalar = MagicMock(return_value=70)
                r.all = MagicMock(return_value=[])
            elif n == 1:
                # ML query raises
                raise RuntimeError("ML DB crash")
            else:
                # Statistical fallback
                r.all = MagicMock(return_value=[stat_row])
                r.scalar = MagicMock(return_value=None)
            return r

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)

        # Provide a working prophet stub so ImportError branch is NOT taken
        fake_prophet_module = MagicMock()

        with patch.dict("sys.modules", {"prophet": fake_prophet_module, "pandas": MagicMock()}):
            result = await fc.predict("S1", date(2026, 3, 2))

        assert result.basis in ("statistical", "rule_based")


# ---------------------------------------------------------------------------
# 11. _ml_prophet() with db=None after prophet import (line 217)
# ---------------------------------------------------------------------------

class TestMLProphetNoDBAfterImport:
    """Line 217: prophet imports OK, but self._db is None → _statistical fallback."""

    @pytest.mark.asyncio
    async def test_ml_prophet_no_db_after_import(self):
        """
        Directly call _ml_prophet with db=None and a fake prophet module that
        imports successfully. Line 217 (`if not self._db`) fires → _rule_based.
        """
        fc = DemandForecaster(db_session=None)

        fake_prophet_module = MagicMock()
        fake_pandas_module = MagicMock()

        with patch.dict("sys.modules", {
            "prophet": fake_prophet_module,
            "pandas": fake_pandas_module,
        }):
            result = await fc._ml_prophet("S1", date(2026, 3, 2), history_days=80)

        # No DB → _statistical → no DB → _rule_based
        assert result.basis == "rule_based"


# ---------------------------------------------------------------------------
# 12. _ml_prophet() full success path (lines 236-253)
# ---------------------------------------------------------------------------

class TestMLProphetSuccessPath:
    """Lines 236-253: prophet imports and generates a forecast."""

    @pytest.mark.asyncio
    async def test_ml_prophet_full_success_path(self):
        """
        Mock prophet + pandas so the full ML path runs through to ForecastResult
        with basis='ml'. Requires 30+ rows returned from DB.
        """
        import pandas as real_pd
        from datetime import date as date_type

        # Build 35 fake rows with realistic ds/y attributes
        rows = []
        for i in range(35):
            row = MagicMock()
            row.ds = date(2026, 1, 1) + __import__('datetime').timedelta(days=i)
            row.y = 3000.0 + i * 10
            rows.append(row)

        db = MagicMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            if n == 0:
                # _get_history_days → ≥ 60
                r.scalar = MagicMock(return_value=80)
                r.all = MagicMock(return_value=[])
            elif n == 1:
                # ML historical data query
                r.all = MagicMock(return_value=rows)
                r.scalar = MagicMock(return_value=None)
            else:
                # BOM queries → empty
                r.all = MagicMock(return_value=[])
                r.scalar = MagicMock(return_value=None)
            return r

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)

        # Build a mock forecast DataFrame that contains the target date
        target = date(2026, 3, 2)
        import datetime as _dt
        forecast_df = real_pd.DataFrame({
            "ds": [real_pd.Timestamp(target)],
            "yhat": [4200.0],
        })

        mock_model = MagicMock()
        mock_model.fit = MagicMock()
        mock_model.make_future_dataframe = MagicMock(return_value=MagicMock())
        mock_model.predict = MagicMock(return_value=forecast_df)

        mock_prophet_cls = MagicMock(return_value=mock_model)
        fake_prophet_module = MagicMock()
        fake_prophet_module.Prophet = mock_prophet_cls

        # We need real pandas for DataFrame operations; only stub prophet
        with patch.dict("sys.modules", {"prophet": fake_prophet_module}):
            result = await fc.predict("S1", target)

        assert result.basis == "ml"
        assert result.confidence == "high"
        assert result.estimated_revenue == pytest.approx(4200.0)


# ---------------------------------------------------------------------------
# 13. _ml_prophet() row.empty path (line 248)
# ---------------------------------------------------------------------------

class TestMLProphetRowEmpty:
    """Line 248: prophet forecast result doesn't contain the target date → statistical."""

    @pytest.mark.asyncio
    async def test_ml_prophet_row_empty_falls_back_to_statistical(self):
        """
        Prophet returns a forecast DataFrame that does NOT contain the target date,
        so row.empty is True and line 248 fires → _statistical fallback.
        """
        import pandas as real_pd

        # Build 35 fake rows
        rows = []
        for i in range(35):
            row = MagicMock()
            row.ds = date(2026, 1, 1) + __import__('datetime').timedelta(days=i)
            row.y = 3000.0 + i * 10
            rows.append(row)

        stat_row = MagicMock()
        stat_row.revenue = 3500.0

        db = MagicMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            r = MagicMock()
            if n == 0:
                r.scalar = MagicMock(return_value=80)
                r.all = MagicMock(return_value=[])
            elif n == 1:
                # ML historical data query
                r.all = MagicMock(return_value=rows)
                r.scalar = MagicMock(return_value=None)
            elif n == 2:
                # _statistical revenue query
                r.all = MagicMock(return_value=[stat_row])
                r.scalar = MagicMock(return_value=None)
            else:
                # BOM queries
                r.all = MagicMock(return_value=[])
                r.scalar = MagicMock(return_value=None)
            return r

        db.execute = execute_seq
        fc = DemandForecaster(db_session=db)

        # Forecast DataFrame has NO row matching the target date (empty result)
        target = date(2026, 3, 2)
        forecast_df = real_pd.DataFrame({
            "ds": [real_pd.Timestamp("2025-01-01")],  # different date
            "yhat": [4000.0],
        })

        mock_model = MagicMock()
        mock_model.fit = MagicMock()
        mock_model.make_future_dataframe = MagicMock(return_value=MagicMock())
        mock_model.predict = MagicMock(return_value=forecast_df)

        mock_prophet_cls = MagicMock(return_value=mock_model)
        fake_prophet_module = MagicMock()
        fake_prophet_module.Prophet = mock_prophet_cls

        with patch.dict("sys.modules", {"prophet": fake_prophet_module}):
            result = await fc.predict("S1", target)

        # row.empty → _statistical fallback
        assert result.basis in ("statistical", "rule_based")
