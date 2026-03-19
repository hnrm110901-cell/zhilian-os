"""
SkillRegistry — 行业知识结构化层

在现有 _AGENT_TOOLS_REGISTRY（agent_tools.py）之上叠加业务语义层。
每个 Tool 包装成 SkillDescriptor，带上业务意图、影响品类、效果指标、可组合声明。
SkillRegistry 是单例，启动时从 legacy registry bootstrap。

设计原则：
  - 不替换现有 registry：get_tools_for_agent() 继续返回原始 Claude Tool Use Schema
  - 渐进式填充：_bootstrap_from_legacy() 先用默认值，再从 SKILL_BUSINESS_METADATA 覆盖
  - 运行时可查询：Agent 可调用 query(intent=...) 发现跨 Agent 的相关能力
  - 连接 P2：evaluation_delay_hours 和 effect_metric 被 EffectEvaluator 读取

用法：
    registry = SkillRegistry.get()
    skills = registry.query(agent_type="schedule")
    cost_skills = registry.query(intent="cost_optimization")
    chain = registry.get_composition_chain("schedule.query_staff_availability")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class SkillDescriptor:
    """Agent Tool 的业务语义描述符。"""

    skill_id: str  # "schedule.query_staff_availability"
    agent_type: str  # "schedule"
    tool_name: str  # "query_staff_availability"

    # 业务语义（SAP Skill 核心）
    business_intent: str = ""  # "查询员工排班可用性，用于排班优化"
    impact_category: str = ""  # "cost_optimization" | "revenue_growth" | "risk_mitigation"
    estimated_impact_yuan: Optional[float] = None

    # 可组合性
    requires: List[str] = field(default_factory=list)  # 前置 skill_ids
    provides: List[str] = field(default_factory=list)  # 输出标签
    chains_with: List[str] = field(default_factory=list)  # 可组合的 skill_ids

    # 效果度量（连接 P2 EffectEvaluator）
    effect_metric: Optional[str] = None  # "labor_cost_ratio" | "waste_rate"
    evaluation_delay_hours: int = 72  # 默认 3 天后评估

    # 原始 Tool Schema（保持兼容）
    tool_schema: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "agent_type": self.agent_type,
            "tool_name": self.tool_name,
            "business_intent": self.business_intent,
            "impact_category": self.impact_category,
            "estimated_impact_yuan": self.estimated_impact_yuan,
            "requires": self.requires,
            "provides": self.provides,
            "chains_with": self.chains_with,
            "effect_metric": self.effect_metric,
            "evaluation_delay_hours": self.evaluation_delay_hours,
        }


class SkillRegistry:
    """
    Agent 技能注册表单例。

    在 _AGENT_TOOLS_REGISTRY 之上叠加业务语义层。
    """

    _instance: Optional["SkillRegistry"] = None

    def __init__(self) -> None:
        self._skills: Dict[str, SkillDescriptor] = {}
        self._bootstrapped = False

    @classmethod
    def get(cls) -> "SkillRegistry":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅供测试）。"""
        cls._instance = None

    def register(self, descriptor: SkillDescriptor) -> None:
        """注册或更新一个 SkillDescriptor。"""
        self._skills[descriptor.skill_id] = descriptor

    def get_skill(self, skill_id: str) -> Optional[SkillDescriptor]:
        """按 skill_id 获取。"""
        self._ensure_bootstrapped()
        return self._skills.get(skill_id)

    def query(
        self,
        agent_type: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> List[SkillDescriptor]:
        """
        查询技能列表。

        Args:
            agent_type: 按 Agent 类型筛选
            intent: 按业务意图/影响品类搜索（模糊匹配 business_intent 或精确匹配 impact_category）
        """
        self._ensure_bootstrapped()
        results = list(self._skills.values())

        if agent_type:
            results = [s for s in results if s.agent_type == agent_type]

        if intent:
            results = [s for s in results if s.impact_category == intent or intent.lower() in s.business_intent.lower()]

        return results

    def get_composition_chain(self, skill_id: str) -> List[SkillDescriptor]:
        """
        获取某个技能的组合链（chains_with 引用的技能）。

        返回当前技能 + 可链接的技能列表。
        """
        self._ensure_bootstrapped()
        skill = self._skills.get(skill_id)
        if not skill:
            return []

        chain = [skill]
        for chained_id in skill.chains_with:
            chained = self._skills.get(chained_id)
            if chained:
                chain.append(chained)
        return chain

    def all_skills(self) -> List[SkillDescriptor]:
        """返回所有已注册技能。"""
        self._ensure_bootstrapped()
        return list(self._skills.values())

    def _ensure_bootstrapped(self) -> None:
        """确保已从 legacy registry 初始化。"""
        if not self._bootstrapped:
            self._bootstrap_from_legacy()

    def _bootstrap_from_legacy(self) -> None:
        """从 _AGENT_TOOLS_REGISTRY 初始化 SkillDescriptor。"""
        try:
            from src.core.agent_tools import _AGENT_TOOLS_REGISTRY
        except ImportError:
            logger.warning("skill_registry.bootstrap_failed", reason="agent_tools not importable")
            self._bootstrapped = True
            return

        # 加载业务元数据
        try:
            from src.core.skill_metadata import SKILL_BUSINESS_METADATA
        except ImportError:
            SKILL_BUSINESS_METADATA = {}
            logger.debug("skill_registry.no_metadata", reason="skill_metadata not found")

        for agent_type, tools in _AGENT_TOOLS_REGISTRY.items():
            for tool in tools:
                tool_name = tool.get("name", "")
                skill_id = f"{agent_type}.{tool_name}"

                # 默认值
                descriptor = SkillDescriptor(
                    skill_id=skill_id,
                    agent_type=agent_type,
                    tool_name=tool_name,
                    business_intent=tool.get("description", ""),
                    tool_schema=tool,
                )

                # 从业务元数据覆盖
                meta = SKILL_BUSINESS_METADATA.get(skill_id, {})
                if meta:
                    descriptor.business_intent = meta.get("business_intent", descriptor.business_intent)
                    descriptor.impact_category = meta.get("impact_category", "")
                    descriptor.estimated_impact_yuan = meta.get("estimated_impact_yuan")
                    descriptor.requires = meta.get("requires", [])
                    descriptor.provides = meta.get("provides", [])
                    descriptor.chains_with = meta.get("chains_with", [])
                    descriptor.effect_metric = meta.get("effect_metric")
                    descriptor.evaluation_delay_hours = meta.get("evaluation_delay_hours", 72)

                self._skills[skill_id] = descriptor

        self._bootstrapped = True
        logger.info("skill_registry.bootstrapped", total_skills=len(self._skills))
