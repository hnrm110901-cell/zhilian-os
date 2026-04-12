"""金额转换工具函数测试"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from decimal import Decimal
from utils.amount import fen_to_yuan, fen_to_yuan_str, yuan_to_fen, format_yuan, amount_dict


class TestFenToYuan:
    def test_basic(self):
        assert fen_to_yuan(5800) == Decimal("58.00")

    def test_zero(self):
        assert fen_to_yuan(0) == Decimal("0.00")

    def test_one_fen(self):
        assert fen_to_yuan(1) == Decimal("0.01")

    def test_large(self):
        assert fen_to_yuan(9999999) == Decimal("99999.99")

    def test_str_format(self):
        assert fen_to_yuan_str(9999) == "99.99"
        assert fen_to_yuan_str(100) == "1.00"
        assert fen_to_yuan_str(1) == "0.01"
        assert fen_to_yuan_str(0) == "0.00"


class TestYuanToFen:
    def test_basic(self):
        assert yuan_to_fen(58.00) == 5800

    def test_decimal_input(self):
        assert yuan_to_fen(Decimal("99.99")) == 9999

    def test_string_input(self):
        assert yuan_to_fen("123.45") == 12345

    def test_rounding(self):
        assert yuan_to_fen(1.005) == 101  # 四舍五入
        assert yuan_to_fen(1.004) == 100


class TestFormatYuan:
    def test_basic(self):
        assert format_yuan(5800) == "¥58.00"

    def test_zero(self):
        assert format_yuan(0) == "¥0.00"

    def test_small(self):
        assert format_yuan(1) == "¥0.01"


class TestAmountDict:
    def test_default_prefix(self):
        d = amount_dict(5800)
        assert d["amount_fen"] == 5800
        assert d["amount_yuan"] == "58.00"

    def test_custom_prefix(self):
        d = amount_dict(10000, "total")
        assert d["total_fen"] == 10000
        assert d["total_yuan"] == "100.00"

    def test_precision(self):
        d = amount_dict(12345, "subtotal")
        assert d["subtotal_yuan"] == "123.45"
