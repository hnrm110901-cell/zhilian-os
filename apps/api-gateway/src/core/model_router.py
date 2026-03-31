"""
屯象OS 统一模型路由层

所有AI模型调用必须通过此层，不允许直接调用API。
职责：
1. 根据任务类型路由到合适的模型
2. 统一成本追踪和调用日志
3. 为未来模型切换预留接口（Mythos等）

兼容现有配置：
- 读取 config.py 中的 LLM_PROVIDER / LLM_MODEL / LLM_ENABLED
- 与 core/llm.py 的 LLMModel / LLMFactory 保持一致
"""

import time
from enum import Enum
from typing import Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# 任务复杂度分级
# ---------------------------------------------------------------------------


class TaskComplexity(str, Enum):
    """任务复杂度分级"""

    SIMPLE = "simple"  # 简单格式化/分类/提取
    MODERATE = "moderate"  # 中等推理/分析/汇总
    COMPLEX = "complex"  # 复杂归因/决策/预测
    ADVANCED = "advanced"  # 未来: 跨模态预测（预留 Mythos）


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


class ModelRouter:
    """
    根据任务复杂度路由到合适的模型。

    v1: 静态配置字典版，不做动态路由。
    后续演进方向：
      - v2: 按 token 价格 + 响应延迟动态选择
      - v3: 接入 Mythos 等自训练模型
    """

    # ── 任务类型 → 复杂度映射 ─────────────────────────────────────────────────
    DEFAULT_TASK_MODEL_MAP: Dict[str, TaskComplexity] = {
        # 简单任务 → 最经济模型
        "text_formatting": TaskComplexity.SIMPLE,
        "intent_classification": TaskComplexity.SIMPLE,
        "data_extraction": TaskComplexity.SIMPLE,
        "knowledge_summary": TaskComplexity.SIMPLE,
        "journey_message": TaskComplexity.SIMPLE,
        # 中等任务
        "discount_analysis": TaskComplexity.MODERATE,
        "anomaly_detection": TaskComplexity.MODERATE,
        "kpi_summary": TaskComplexity.MODERATE,
        "menu_recommendation": TaskComplexity.MODERATE,
        "turnover_risk_analysis": TaskComplexity.MODERATE,
        "store_risk_scan": TaskComplexity.MODERATE,
        "supplier_insight": TaskComplexity.MODERATE,
        "hr_report_generation": TaskComplexity.MODERATE,
        "cypher_generation": TaskComplexity.MODERATE,
        # 复杂任务
        "root_cause_analysis": TaskComplexity.COMPLEX,
        "decision_recommendation": TaskComplexity.COMPLEX,
        "financial_forecasting": TaskComplexity.COMPLEX,
        "behavior_pattern_analysis": TaskComplexity.COMPLEX,
        "growth_plan_generation": TaskComplexity.COMPLEX,
        "salary_competitiveness": TaskComplexity.COMPLEX,
        "calibration_insight": TaskComplexity.COMPLEX,
    }

    # ── 复杂度 → 模型映射 ────────────────────────────────────────────────────
    # 使用 core/llm.py 中 LLMModel 的实际 model ID
    COMPLEXITY_MODEL_MAP: Dict[TaskComplexity, str] = {
        TaskComplexity.SIMPLE: "claude-haiku-4-5",
        TaskComplexity.MODERATE: "claude-sonnet-4-6",
        TaskComplexity.COMPLEX: "claude-opus-4-6",
        TaskComplexity.ADVANCED: "claude-opus-4-6",  # 未来切换为 mythos
    }

    def __init__(self) -> None:
        self._call_count: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._cost_cents: float = 0.0
        # 按任务类型统计
        self._task_stats: Dict[str, Dict] = {}

    # ── 公开方法 ──────────────────────────────────────────────────────────────

    def get_model(self, task_type: str) -> str:
        """根据任务类型返回推荐模型 ID"""
        complexity = self.DEFAULT_TASK_MODEL_MAP.get(
            task_type, TaskComplexity.MODERATE
        )
        model = self.COMPLEXITY_MODEL_MAP[complexity]
        logger.debug(
            "model_router_resolve",
            task_type=task_type,
            complexity=complexity.value,
            model=model,
        )
        return model

    def get_complexity(self, task_type: str) -> TaskComplexity:
        """返回任务复杂度（供调用方决定是否需要 Tool Use 等高级能力）"""
        return self.DEFAULT_TASK_MODEL_MAP.get(
            task_type, TaskComplexity.MODERATE
        )

    def log_call(
        self,
        task_type: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0,
        success: bool = True,
    ) -> None:
        """
        记录一次模型调用，用于成本追踪和运营可观测性。

        调用方在每次 LLM 请求完成后调用此方法。
        """
        self._call_count += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        # 按任务类型累计
        if task_type not in self._task_stats:
            self._task_stats[task_type] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "errors": 0,
            }
        ts = self._task_stats[task_type]
        ts["calls"] += 1
        ts["input_tokens"] += input_tokens
        ts["output_tokens"] += output_tokens
        if not success:
            ts["errors"] += 1

        logger.info(
            "model_call",
            task_type=task_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 2),
            success=success,
            total_calls=self._call_count,
        )

    @property
    def stats(self) -> dict:
        """返回全局调用统计"""
        return {
            "total_calls": self._call_count,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
        }

    @property
    def task_stats(self) -> Dict[str, Dict]:
        """返回按任务类型的调用统计"""
        return dict(self._task_stats)

    def reset_stats(self) -> None:
        """重置统计（主要用于测试）"""
        self._call_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._cost_cents = 0.0
        self._task_stats.clear()


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
model_router = ModelRouter()
