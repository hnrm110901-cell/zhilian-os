"""
ModelRouter 统一模型路由层 — 单元测试

覆盖：
- 任务类型正确路由到模型
- 未知任务类型使用默认模型（MODERATE → claude-sonnet）
- 调用日志记录
- 统计数据累计
- 复杂度查询
- 按任务类型统计
"""

import pytest

from src.core.model_router import ModelRouter, TaskComplexity, model_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def router() -> ModelRouter:
    """每个测试使用独立的 ModelRouter 实例"""
    return ModelRouter()


# ---------------------------------------------------------------------------
# 任务类型 → 模型路由
# ---------------------------------------------------------------------------


class TestGetModel:
    """测试 get_model 路由逻辑"""

    def test_simple_task_routes_to_haiku(self, router: ModelRouter):
        assert router.get_model("text_formatting") == "claude-haiku-4-5"
        assert router.get_model("intent_classification") == "claude-haiku-4-5"
        assert router.get_model("data_extraction") == "claude-haiku-4-5"

    def test_moderate_task_routes_to_sonnet(self, router: ModelRouter):
        assert router.get_model("discount_analysis") == "claude-sonnet-4-6"
        assert router.get_model("kpi_summary") == "claude-sonnet-4-6"
        assert router.get_model("turnover_risk_analysis") == "claude-sonnet-4-6"

    def test_complex_task_routes_to_opus(self, router: ModelRouter):
        assert router.get_model("root_cause_analysis") == "claude-opus-4-6"
        assert router.get_model("decision_recommendation") == "claude-opus-4-6"
        assert router.get_model("financial_forecasting") == "claude-opus-4-6"

    def test_unknown_task_defaults_to_moderate(self, router: ModelRouter):
        """未注册的任务类型应回退到 MODERATE（claude-sonnet）"""
        assert router.get_model("some_future_task") == "claude-sonnet-4-6"
        assert router.get_model("") == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# 复杂度查询
# ---------------------------------------------------------------------------


class TestGetComplexity:
    def test_known_task_returns_correct_complexity(self, router: ModelRouter):
        assert router.get_complexity("text_formatting") == TaskComplexity.SIMPLE
        assert router.get_complexity("anomaly_detection") == TaskComplexity.MODERATE
        assert router.get_complexity("behavior_pattern_analysis") == TaskComplexity.COMPLEX

    def test_unknown_task_defaults_to_moderate(self, router: ModelRouter):
        assert router.get_complexity("unknown_task") == TaskComplexity.MODERATE


# ---------------------------------------------------------------------------
# 调用日志 & 统计
# ---------------------------------------------------------------------------


class TestLogCall:
    def test_single_call_updates_stats(self, router: ModelRouter):
        router.log_call(
            task_type="kpi_summary",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            latency_ms=320.5,
            success=True,
        )
        stats = router.stats
        assert stats["total_calls"] == 1
        assert stats["total_input_tokens"] == 100
        assert stats["total_output_tokens"] == 50
        assert stats["total_tokens"] == 150

    def test_multiple_calls_accumulate(self, router: ModelRouter):
        router.log_call("a", "m1", input_tokens=10, output_tokens=5)
        router.log_call("b", "m2", input_tokens=20, output_tokens=10)
        router.log_call("a", "m1", input_tokens=30, output_tokens=15)

        stats = router.stats
        assert stats["total_calls"] == 3
        assert stats["total_tokens"] == 90  # 10+5+20+10+30+15

    def test_task_stats_by_type(self, router: ModelRouter):
        router.log_call("kpi_summary", "sonnet", input_tokens=100, output_tokens=50, success=True)
        router.log_call("kpi_summary", "sonnet", input_tokens=200, output_tokens=100, success=False)
        router.log_call("text_formatting", "haiku", input_tokens=10, output_tokens=5, success=True)

        ts = router.task_stats
        assert ts["kpi_summary"]["calls"] == 2
        assert ts["kpi_summary"]["input_tokens"] == 300
        assert ts["kpi_summary"]["errors"] == 1
        assert ts["text_formatting"]["calls"] == 1
        assert ts["text_formatting"]["errors"] == 0

    def test_failed_call_tracked(self, router: ModelRouter):
        router.log_call("test", "m", success=False)
        assert router.stats["total_calls"] == 1
        assert router.task_stats["test"]["errors"] == 1

    def test_reset_stats(self, router: ModelRouter):
        router.log_call("a", "m", input_tokens=100, output_tokens=50)
        router.reset_stats()
        assert router.stats["total_calls"] == 0
        assert router.stats["total_tokens"] == 0
        assert router.task_stats == {}


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------


class TestGlobalSingleton:
    def test_model_router_singleton_importable(self):
        """确认全局单例可导入且是 ModelRouter 实例"""
        assert isinstance(model_router, ModelRouter)


# ---------------------------------------------------------------------------
# TaskComplexity 枚举
# ---------------------------------------------------------------------------


class TestTaskComplexity:
    def test_enum_values(self):
        assert TaskComplexity.SIMPLE == "simple"
        assert TaskComplexity.MODERATE == "moderate"
        assert TaskComplexity.COMPLEX == "complex"
        assert TaskComplexity.ADVANCED == "advanced"

    def test_all_complexities_have_model_mapping(self):
        """每个复杂度等级都必须有对应的模型映射"""
        router = ModelRouter()
        for complexity in TaskComplexity:
            assert complexity in router.COMPLEXITY_MODEL_MAP
