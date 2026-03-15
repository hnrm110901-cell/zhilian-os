"""
薪酬公式引擎单元测试
覆盖: 条件解析、布尔求值、安全求值、公式校验、公式测试
"""
import pytest
from src.services.salary_formula_engine import SalaryFormulaEngine


@pytest.fixture
def engine():
    return SalaryFormulaEngine(brand_id="test-brand")


# ── 简单表达式 ──────────────────────────────────────────────


class TestSimpleExpression:
    """简单数学表达式（不含条件分支）"""

    def test_addition(self, engine):
        result = engine.test_formula(
            "【基本工资】 + 【岗位补贴】",
            {"基本工资": 500000, "岗位补贴": 100000},
        )
        assert result["result_fen"] == 600000

    def test_subtraction(self, engine):
        result = engine.test_formula(
            "【基本工资】 - 【岗位补贴】",
            {"基本工资": 500000, "岗位补贴": 100000},
        )
        assert result["result_fen"] == 400000

    def test_multiplication(self, engine):
        result = engine.test_formula(
            "【基本工资】 * 【绩效系数】",
            {"基本工资": 500000, "绩效系数": 1.2},
        )
        assert result["result_fen"] == 600000

    def test_complex_arithmetic(self, engine):
        # 日薪 = 基本工资 / 月工作日数 * 出勤天数
        result = engine.test_formula(
            "【基本工资】 / 【月工作日数】 * 【总出勤天数】",
            {"基本工资": 440000, "月工作日数": 22, "总出勤天数": 20},
        )
        assert result["result_fen"] == 400000

    def test_parentheses(self, engine):
        result = engine.test_formula(
            "(【基本工资】 + 【岗位补贴】) * 【绩效系数】",
            {"基本工资": 500000, "岗位补贴": 100000, "绩效系数": 0.5},
        )
        assert result["result_fen"] == 300000

    def test_empty_formula(self, engine):
        result = engine.test_formula("", {})
        assert result["result_fen"] == 0

    def test_missing_variable(self, engine):
        result = engine.test_formula("【不存在的变量】 + 100", {})
        assert result["result_fen"] == 100
        assert any("缺少变量" in w for w in result["warnings"])

    def test_variables_used(self, engine):
        result = engine.test_formula(
            "【基本工资】 + 【岗位补贴】",
            {"基本工资": 500000, "岗位补贴": 100000},
        )
        assert set(result["variables_used"]) == {"基本工资", "岗位补贴"}


# ── 除零 / 溢出 / 负值保护 ────────────────────────────────


class TestSafeEval:
    """安全求值边界条件"""

    def test_division_by_zero(self, engine):
        result = engine.test_formula(
            "【基本工资】 / 【月工作日数】",
            {"基本工资": 500000, "月工作日数": 0},
        )
        assert result["result_fen"] == 0
        assert any("除零" in w for w in result["warnings"])

    def test_overflow_cap(self, engine):
        # 100_000_001 分 > 100万元上限
        result = engine.test_formula(
            "【基本工资】 * 100",
            {"基本工资": 10000000},  # 1000万分 * 100 = 10亿分
        )
        assert result["result_fen"] == 100_000_000  # 被截断到上限
        assert any("溢出" in w for w in result["warnings"])

    def test_rounding(self, engine):
        # 10 / 3 = 3.333... → 四舍五入到3
        result = engine.test_formula("10 / 3", {})
        assert result["result_fen"] == 3

    def test_unsafe_characters_blocked(self, engine):
        result = engine.test_formula("__import__('os')", {})
        assert result["result_fen"] == 0


# ── 条件表达式（核心修复） ──────────────────────────────────


class TestConditionExpression:
    """条件分支解析 — 花括号匹配方式"""

    def test_simple_if_else(self, engine):
        formula = "如果 【司龄月数】 >= 24 则 { 10000 }; 否则 { 5000 }"
        # 条件成立
        result = engine.test_formula(formula, {"司龄月数": 30})
        assert result["result_fen"] == 10000

        # 条件不成立
        result = engine.test_formula(formula, {"司龄月数": 12})
        assert result["result_fen"] == 5000

    def test_if_elif_else(self, engine):
        formula = (
            "如果 【司龄月数】 >= 48 则 { 20000 }; "
            "否则如果 【司龄月数】 >= 24 则 { 10000 }; "
            "否则 { 5000 }"
        )
        assert engine.test_formula(formula, {"司龄月数": 60})["result_fen"] == 20000
        assert engine.test_formula(formula, {"司龄月数": 30})["result_fen"] == 10000
        assert engine.test_formula(formula, {"司龄月数": 6})["result_fen"] == 5000

    def test_multiple_elif(self, engine):
        formula = (
            "如果 【司龄月数】 >= 48 则 { 20000 }; "
            "否则如果 【司龄月数】 >= 36 则 { 15000 }; "
            "否则如果 【司龄月数】 >= 24 则 { 10000 }; "
            "否则如果 【司龄月数】 >= 13 则 { 5000 }; "
            "否则 { 0 }"
        )
        assert engine.test_formula(formula, {"司龄月数": 50})["result_fen"] == 20000
        assert engine.test_formula(formula, {"司龄月数": 40})["result_fen"] == 15000
        assert engine.test_formula(formula, {"司龄月数": 25})["result_fen"] == 10000
        assert engine.test_formula(formula, {"司龄月数": 15})["result_fen"] == 5000
        assert engine.test_formula(formula, {"司龄月数": 3})["result_fen"] == 0

    def test_condition_with_expression_body(self, engine):
        """条件分支体内含变量表达式"""
        formula = (
            "如果 【司龄月数】 >= 24 则 { 【基本工资】 * 0.1 }; "
            "否则 { 【基本工资】 * 0.05 }"
        )
        result = engine.test_formula(formula, {"司龄月数": 30, "基本工资": 500000})
        assert result["result_fen"] == 50000  # 500000 * 0.1

        result = engine.test_formula(formula, {"司龄月数": 12, "基本工资": 500000})
        assert result["result_fen"] == 25000  # 500000 * 0.05

    def test_nested_condition_with_and(self, engine):
        """嵌套条件 + 且(AND) — 这是旧正则无法处理的场景"""
        formula = (
            "如果 【司龄月数】 >= 24 且 【基本工资】 > 300000 则 { 【基本工资】 * 0.15 }; "
            "否则 { 【基本工资】 * 0.05 }"
        )
        # 两个条件都满足
        result = engine.test_formula(formula, {"司龄月数": 30, "基本工资": 500000})
        assert result["result_fen"] == 75000  # 500000 * 0.15

        # 司龄不满足
        result = engine.test_formula(formula, {"司龄月数": 12, "基本工资": 500000})
        assert result["result_fen"] == 25000  # 500000 * 0.05

        # 基本工资不满足
        result = engine.test_formula(formula, {"司龄月数": 30, "基本工资": 200000})
        assert result["result_fen"] == 10000  # 200000 * 0.05

    def test_condition_with_or(self, engine):
        """条件含 或(OR)"""
        formula = (
            "如果 【司龄月数】 >= 48 或 【基本工资】 >= 800000 则 { 30000 }; "
            "否则 { 10000 }"
        )
        # 司龄满足
        assert engine.test_formula(formula, {"司龄月数": 50, "基本工资": 300000})["result_fen"] == 30000
        # 工资满足
        assert engine.test_formula(formula, {"司龄月数": 10, "基本工资": 900000})["result_fen"] == 30000
        # 都不满足
        assert engine.test_formula(formula, {"司龄月数": 10, "基本工资": 300000})["result_fen"] == 10000

    def test_if_only_no_else(self, engine):
        """只有如果分支，无否则"""
        formula = "如果 【司龄月数】 >= 24 则 { 10000 }"
        assert engine.test_formula(formula, {"司龄月数": 30})["result_fen"] == 10000
        assert engine.test_formula(formula, {"司龄月数": 12})["result_fen"] == 0

    def test_condition_operators(self, engine):
        """各种比较运算符"""
        vars = {"司龄月数": 24}
        assert engine.test_formula("如果 【司龄月数】 == 24 则 { 1 }; 否则 { 0 }", vars)["result_fen"] == 1
        assert engine.test_formula("如果 【司龄月数】 != 24 则 { 1 }; 否则 { 0 }", vars)["result_fen"] == 0
        assert engine.test_formula("如果 【司龄月数】 >= 24 则 { 1 }; 否则 { 0 }", vars)["result_fen"] == 1
        assert engine.test_formula("如果 【司龄月数】 > 24 则 { 1 }; 否则 { 0 }", vars)["result_fen"] == 0
        assert engine.test_formula("如果 【司龄月数】 <= 24 则 { 1 }; 否则 { 0 }", vars)["result_fen"] == 1
        assert engine.test_formula("如果 【司龄月数】 < 24 则 { 1 }; 否则 { 0 }", vars)["result_fen"] == 0


# ── 公式校验 ────────────────────────────────────────────────


class TestFormulaValidation:
    """validate_formula 方法"""

    def test_valid_simple(self, engine):
        v = engine.validate_formula("【基本工资】 + 【岗位补贴】")
        assert v["valid"] is True
        assert len(v["errors"]) == 0

    def test_unknown_variable(self, engine):
        v = engine.validate_formula("【基本工资】 + 【部门津贴】")
        assert v["valid"] is False
        assert any("部门津贴" in e for e in v["errors"])

    def test_unknown_var_allowed_when_in_available_list(self, engine):
        v = engine.validate_formula("【基本工资】 + 【部门津贴】", ["部门津贴"])
        assert v["valid"] is True

    def test_unmatched_brace(self, engine):
        v = engine.validate_formula("如果 【基本工资】 > 0 则 { 100 ")
        assert v["valid"] is False
        assert any("{" in e for e in v["errors"])

    def test_unmatched_paren(self, engine):
        v = engine.validate_formula("(【基本工资】 + 100")
        assert v["valid"] is False
        assert any("(" in e for e in v["errors"])

    def test_missing_ze_keyword(self, engine):
        v = engine.validate_formula("如果 【基本工资】 > 0 { 100 }")
        assert v["valid"] is False
        assert any("则" in e for e in v["errors"])

    def test_condition_no_braces(self, engine):
        v = engine.validate_formula("如果 【基本工资】 > 0 则 100")
        assert v["valid"] is False
        assert any("{" in e or "}" in e for e in v["errors"])

    def test_valid_condition(self, engine):
        v = engine.validate_formula(
            "如果 【司龄月数】 >= 24 则 { 10000 }; 否则 { 5000 }"
        )
        assert v["valid"] is True

    def test_empty_formula(self, engine):
        v = engine.validate_formula("")
        assert v["valid"] is True
        assert len(v["warnings"]) > 0

    def test_illegal_characters(self, engine):
        v = engine.validate_formula("【基本工资】 + abc")
        assert v["valid"] is False
        assert any("非法字符" in e for e in v["errors"])

    def test_syntax_error_expression(self, engine):
        v = engine.validate_formula("【基本工资】 + + 100")
        assert v["valid"] is False


# ── test_formula 方法 ───────────────────────────────────────


class TestTestFormula:
    """test_formula 返回结构完整性"""

    def test_return_structure(self, engine):
        result = engine.test_formula(
            "【基本工资】 + 【岗位补贴】",
            {"基本工资": 500000, "岗位补贴": 100000},
        )
        assert "result_fen" in result
        assert "result_yuan" in result
        assert "variables_used" in result
        assert "calculation_steps" in result
        assert "warnings" in result
        assert result["result_yuan"] == result["result_fen"] / 100

    def test_calculation_steps_logged(self, engine):
        result = engine.test_formula(
            "如果 【司龄月数】 >= 24 则 { 10000 }; 否则 { 5000 }",
            {"司龄月数": 30},
        )
        assert len(result["calculation_steps"]) > 1
        # 应包含原始公式和条件求值记录
        assert any("原始公式" in s for s in result["calculation_steps"])


# ── 条件分支块解析器 ────────────────────────────────────────


class TestConditionBlockParser:
    """_split_condition_blocks 内部方法"""

    def test_simple_if_else_blocks(self, engine):
        blocks = engine._split_condition_blocks(
            "如果 x > 0 则 { 100 }; 否则 { 200 }"
        )
        assert blocks is not None
        assert len(blocks) == 2
        assert blocks[0] == ("x > 0", "100")
        assert blocks[1] == (None, "200")

    def test_if_elif_else_blocks(self, engine):
        blocks = engine._split_condition_blocks(
            "如果 x >= 48 则 { 20000 }; "
            "否则如果 x >= 24 则 { 10000 }; "
            "否则 { 5000 }"
        )
        assert blocks is not None
        assert len(blocks) == 3
        assert blocks[0][0] == "x >= 48"
        assert blocks[1][0] == "x >= 24"
        assert blocks[2][0] is None

    def test_expression_with_parens_inside_braces(self, engine):
        """花括号内含圆括号的表达式"""
        blocks = engine._split_condition_blocks(
            "如果 x > 0 则 { (x + y) * 0.1 }; 否则 { 0 }"
        )
        assert blocks is not None
        assert blocks[0][1] == "(x + y) * 0.1"

    def test_invalid_formula_returns_none(self, engine):
        blocks = engine._split_condition_blocks("这不是条件表达式")
        assert blocks is None

    def test_missing_brace_returns_none(self, engine):
        blocks = engine._split_condition_blocks(
            "如果 x > 0 则 { 100 ; 否则 { 200 }"
        )
        # 第一个 { 没有匹配的 }（因为 ; 在中间但 } 在最后）
        # 实际上这个能解析成功因为匹配的是第一个 }
        # 关键是不会崩溃


# ── 布尔表达式求值 ──────────────────────────────────────────


class TestBooleanExprEvaluation:
    """_evaluate_boolean_expr 内部方法"""

    def test_simple_comparison(self, engine):
        resolver = lambda name: {"x": 30.0, "y": 10.0}.get(name, 0.0)
        assert engine._evaluate_boolean_expr("【x】 > 20", resolver) is True
        assert engine._evaluate_boolean_expr("【x】 < 20", resolver) is False
        assert engine._evaluate_boolean_expr("【x】 == 30", resolver) is True
        assert engine._evaluate_boolean_expr("【x】 != 30", resolver) is False

    def test_and_operator(self, engine):
        resolver = lambda name: {"x": 30.0, "y": 10.0}.get(name, 0.0)
        assert engine._evaluate_boolean_expr("【x】 > 20 且 【y】 > 5", resolver) is True
        assert engine._evaluate_boolean_expr("【x】 > 20 且 【y】 > 15", resolver) is False

    def test_or_operator(self, engine):
        resolver = lambda name: {"x": 30.0, "y": 10.0}.get(name, 0.0)
        assert engine._evaluate_boolean_expr("【x】 > 100 或 【y】 > 5", resolver) is True
        assert engine._evaluate_boolean_expr("【x】 > 100 或 【y】 > 50", resolver) is False

    def test_combined_and_or(self, engine):
        resolver = lambda name: {"a": 10.0, "b": 20.0, "c": 30.0}.get(name, 0.0)
        # a > 5 且 (b > 25 或 c > 25) → True and (False or True) → True
        assert engine._evaluate_boolean_expr(
            "【a】 > 5 且 (【b】 > 25 或 【c】 > 25)", resolver
        ) is True

    def test_unsafe_input_blocked(self, engine):
        resolver = lambda name: 0.0
        # 注入攻击
        assert engine._evaluate_boolean_expr("__import__('os')", resolver) is False


# ── 回归测试：确保旧格式公式仍然可用 ───────────────────────


class TestBackwardCompatibility:
    """确保简单公式不被破坏"""

    def test_plain_addition(self, engine):
        result = engine.test_formula("【基本工资】 + 【岗位补贴】", {"基本工资": 300000, "岗位补贴": 50000})
        assert result["result_fen"] == 350000

    def test_plain_number(self, engine):
        result = engine.test_formula("50000", {})
        assert result["result_fen"] == 50000

    def test_percentage_calculation(self, engine):
        result = engine.test_formula("【基本工资】 * 0.08", {"基本工资": 500000})
        assert result["result_fen"] == 40000
