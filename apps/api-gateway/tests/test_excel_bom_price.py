"""
Tests for ExcelBOMImporter price column handling
"""
import os

for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.excel_bom_importer import ExcelBOMImporter, COLUMN_ALIASES, ImportRow


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_importer() -> ExcelBOMImporter:
    db = AsyncMock()
    return ExcelBOMImporter(db, store_id="S1")


def _col_map(*headers):
    """Build a col_map dict from a header tuple the same way the importer does."""
    importer = _make_importer()
    return importer._parse_header(headers)


def _row_tuple(col_map, **kwargs):
    """Build a row tuple aligned to col_map's column indices."""
    max_idx = max(col_map.values()) + 1
    row = [None] * max_idx
    for field, val in kwargs.items():
        idx = col_map.get(field)
        if idx is not None:
            row[idx] = val
    return tuple(row)


# ── COLUMN_ALIASES price aliases ─────────────────────────────────────────────

class TestColumnAliases:
    def test_chinese_price_aliases_mapped(self):
        assert COLUMN_ALIASES["售价"]  == "dish_price"
        assert COLUMN_ALIASES["价格"]  == "dish_price"
        assert COLUMN_ALIASES["单价"]  == "dish_price"

    def test_english_price_aliases_mapped(self):
        assert COLUMN_ALIASES["dish_price"] == "dish_price"
        assert COLUMN_ALIASES["price"]      == "dish_price"


# ── _parse_header / _parse_row with price ────────────────────────────────────

class TestParseRowPrice:

    def _base_col_map(self, price_header="售价"):
        return _col_map("菜品编码", "菜品名称", "食材名称", "标准用量", "单位", price_header)

    def test_price_parsed_from_售价(self):
        importer = _make_importer()
        col_map  = self._base_col_map("售价")
        row      = _row_tuple(col_map,
                              dish_code="D001", dish_name="红烧肉",
                              ingredient_name="五花肉", standard_qty=200, unit="克",
                              dish_price=58.0)
        result = importer._parse_row(row, col_map, 2)
        assert result is not None
        assert result.dish_price == Decimal("58.00")

    def test_price_parsed_from_价格(self):
        importer = _make_importer()
        col_map  = self._base_col_map("价格")
        row      = _row_tuple(col_map,
                              dish_code="D002", dish_name="糖醋排骨",
                              ingredient_name="排骨", standard_qty=300, unit="克",
                              dish_price="128.50")
        result = importer._parse_row(row, col_map, 3)
        assert result.dish_price == Decimal("128.50")

    def test_price_absent_yields_none(self):
        """No price column → dish_price is None (not 0.00)."""
        importer = _make_importer()
        col_map  = _col_map("菜品编码", "菜品名称", "食材名称", "标准用量", "单位")
        row      = _row_tuple(col_map,
                              dish_code="D003", dish_name="清蒸鱼",
                              ingredient_name="鲈鱼", standard_qty=500, unit="克")
        result = importer._parse_row(row, col_map, 4)
        assert result is not None
        assert result.dish_price is None

    def test_price_zero_yields_none(self):
        """Explicit 0 treated as absent (not a valid selling price)."""
        importer = _make_importer()
        col_map  = self._base_col_map()
        row      = _row_tuple(col_map,
                              dish_code="D004", dish_name="白饭",
                              ingredient_name="大米", standard_qty=100, unit="克",
                              dish_price=0)
        result = importer._parse_row(row, col_map, 5)
        assert result.dish_price is None

    def test_price_invalid_string_yields_none(self):
        """Non-numeric price string → None (no crash)."""
        importer = _make_importer()
        col_map  = self._base_col_map()
        row      = _row_tuple(col_map,
                              dish_code="D005", dish_name="茶水",
                              ingredient_name="茶叶", standard_qty=5, unit="克",
                              dish_price="待定")
        result = importer._parse_row(row, col_map, 6)
        assert result.dish_price is None

    def test_price_integer_value_works(self):
        importer = _make_importer()
        col_map  = self._base_col_map()
        row      = _row_tuple(col_map,
                              dish_code="D006", dish_name="炒饭",
                              ingredient_name="米饭", standard_qty=200, unit="克",
                              dish_price=38)
        result = importer._parse_row(row, col_map, 7)
        assert result.dish_price == Decimal("38.00")


# ── _ensure_dish price usage ──────────────────────────────────────────────────

class TestEnsureDishPrice:

    def _mock_db_no_existing(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        db.add    = MagicMock()
        db.flush  = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_price_from_excel_used_when_provided(self):
        db      = self._mock_db_no_existing()
        imp     = ExcelBOMImporter(db, store_id="S1")
        dish    = await imp._ensure_dish("D001", "红烧肉", Decimal("58.00"))

        assert dish.price == Decimal("58.00")
        db.add.assert_called_once_with(dish)

    @pytest.mark.asyncio
    async def test_price_zero_fallback_when_none(self):
        db   = self._mock_db_no_existing()
        imp  = ExcelBOMImporter(db, store_id="S1")
        dish = await imp._ensure_dish("D002", "无价菜品", None)

        assert dish.price == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_existing_dish_returned_unchanged(self):
        """If dish already exists, price is not overwritten."""
        existing = MagicMock()
        existing.price = Decimal("99.00")

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        db.execute.return_value = result

        imp  = ExcelBOMImporter(db, store_id="S1")
        dish = await imp._ensure_dish("D003", "已存在菜品", Decimal("1.00"))

        assert dish.price == Decimal("99.00")   # not overwritten
        db.add.assert_not_called()
