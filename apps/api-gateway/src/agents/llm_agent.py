"""
增强的Agent基类 - 支持 Claude Tool Use 完整 agentic loop

核心升级：
  - execute_with_tools()   : 调用 Claude Tool Use，自动执行工具，循环直到 end_turn
  - execute_with_llm()     : 保留原有单轮 LLM 调用（向后兼容）
  - execute_with_fallback(): 优先 Tool Use，失败降级到规则引擎
  - stream_response()      : 流式输出支持
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import structlog

from ..core.agent_tools import ToolExecutor, get_tools_for_agent
from ..core.config import settings
from ..core.llm import get_llm_client
from ..core.monitoring import ErrorCategory, ErrorSeverity, error_monitor
from ..core.prompts import AgentPrompts

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# 标准输出结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    """
    Agent 输出标准结构 — 每条决策必须可追溯

    Attributes:
        success:         是否成功
        data:            业务数据
        message:         人类可读消息
        reasoning:       推理过程（必填）
        confidence:      置信度 0.0-1.0（必填）
        source_data:     原始输入数据快照（必填）
        recommendations: 建议列表（可选）
        tool_calls:      本次调用的工具记录（Tool Use 模式下填充）
        reasoning_trace: 完整推理链（每轮 Claude 思考记录）
        iterations:      Tool Use 循环次数
        tokens_used:     消耗的 token 数
    """
    success: bool
    data: Any
    message: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    source_data: Dict[str, Any] = field(default_factory=dict)
    recommendations: Optional[List[Any]] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_trace: List[Dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    tokens_used: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "source_data": self.source_data,
            "tool_calls": self.tool_calls,
            "reasoning_trace": self.reasoning_trace,
            "iterations": self.iterations,
            "tokens_used": self.tokens_used,
        }
        if self.recommendations is not None:
            result["recommendations"] = self.recommendations
        return result

    # 向后兼容：支持 result["success"] 等字典访问
    def __getitem__(self, key: str):
        return self.to_dict()[key]

    def get(self, key: str, default=None):
        return self.to_dict().get(key, default)


# ─────────────────────────────────────────────────────────────────────────────
# LLMEnhancedAgent 基类
# ─────────────────────────────────────────────────────────────────────────────

class LLMEnhancedAgent:
    """
    LLM 增强的 Agent 基类

    支持三种执行模式：
    1. Tool Use 模式（推荐）: execute_with_tools()
       Claude 自主决定调用哪些工具，完整 agentic loop
    2. 单轮 LLM 模式: execute_with_llm()
       直接调用 LLM，适合简单问答场景
    3. 降级模式: execute_with_fallback()
       优先 Tool Use，失败时回退到规则引擎
    """

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.llm_enabled = settings.LLM_ENABLED
        self.system_prompt = AgentPrompts.get_prompt(agent_type)
        # 从注册表加载该 Agent 的工具集
        self._tools = get_tools_for_agent(agent_type)

    # ── 核心方法：Tool Use agentic loop ──────────────────────────────────────

    async def execute_with_tools(
        self,
        user_message: str,
        store_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        services: Optional[Dict[str, Any]] = None,
        extra_tools: Optional[List[Dict[str, Any]]] = None,
        max_iterations: int = 10,
    ) -> AgentResult:
        """
        使用 Claude Tool Use 执行 Agent 任务（完整 agentic loop）

        Claude 会自主决定：
          1. 需要调用哪些工具获取数据
          2. 如何分析工具返回的结果
          3. 何时停止并给出最终答案

        Args:
            user_message:   用户请求（自然语言）
            store_id:       门店ID（自动注入到工具调用中）
            context:        额外上下文（注入到 system prompt）
            services:       业务服务依赖注入字典
            extra_tools:    额外工具定义（追加到默认工具集）
            max_iterations: 最大循环次数

        Returns:
            AgentResult（含完整 tool_calls 记录和 reasoning_trace）
        """
        if not self.llm_enabled:
            return self.format_response(
                success=False,
                data=None,
                message="LLM 未启用，请设置 LLM_ENABLED=true",
                reasoning="LLM disabled",
            )

        try:
            llm_client = get_llm_client()

            # 检查当前 LLM 客户端是否支持 Tool Use
            # AnthropicClient 有完整实现，其他客户端使用基类降级实现
            from ..core.llm import AnthropicClient
            is_anthropic = isinstance(llm_client, AnthropicClient)

            if not is_anthropic:
                logger.warning(
                    "tool_use_not_supported_by_provider",
                    provider=type(llm_client).__name__,
                    fallback="single_llm_call",
                )
                # 非 Anthropic 提供商降级为单轮调用
                return await self.execute_with_llm(
                    action="tool_use_fallback",
                    params={"message": user_message, "context": context},
                )

            # 构建工具集（默认 + 额外）
            tools = list(self._tools)
            if extra_tools:
                tools.extend(extra_tools)

            # 构建增强的 system prompt（注入上下文）
            system_prompt = self._build_system_prompt(context)

            # 构建初始消息
            messages = [{"role": "user", "content": user_message}]

            # 初始化工具执行器
            executor = ToolExecutor(
                agent_type=self.agent_type,
                store_id=store_id,
                services=services or {},
            )

            logger.info(
                "agent_tool_use_start",
                agent=self.agent_type,
                store_id=store_id,
                tools_count=len(tools),
                message_preview=user_message[:100],
            )

            # 执行 Tool Use agentic loop
            result = await llm_client.generate_with_tools(
                messages=messages,
                tools=tools,
                tool_executor=executor.execute,
                system_prompt=system_prompt,
                max_tokens=settings.LLM_MAX_TOKENS,
                max_iterations=max_iterations,
            )

            # 解析最终文本（尝试提取 JSON）
            final_data = self._parse_llm_response(result["text"])

            # 计算置信度（基于工具调用成功率和迭代次数）
            confidence = self._calc_confidence(result)

            logger.info(
                "agent_tool_use_completed",
                agent=self.agent_type,
                iterations=result["iterations"],
                tool_calls=len(result["tool_calls"]),
                stop_reason=result["stop_reason"],
                confidence=confidence,
            )

            # 发布到 Agent Memory Bus（供其他 Agent 感知）
            if store_id:
                await self.publish_finding(
                    store_id=store_id,
                    action="tool_use_completed",
                    summary=result["text"][:200],
                    confidence=confidence,
                    data={"tool_calls": len(result["tool_calls"])},
                )

            return AgentResult(
                success=True,
                data=final_data,
                message=result["text"][:500] if isinstance(result["text"], str) else "执行完成",
                reasoning=self._build_reasoning_summary(result),
                confidence=confidence,
                source_data={"user_message": user_message, "store_id": store_id, "context": context},
                tool_calls=result["tool_calls"],
                reasoning_trace=result["reasoning_trace"],
                iterations=result["iterations"],
                tokens_used=result.get("usage", {}),
            )

        except Exception as e:
            logger.error(
                "agent_tool_use_failed",
                agent=self.agent_type,
                error=str(e),
                exc_info=e,
            )
            error_monitor.log_error(
                message=f"Tool Use execution failed for {self.agent_type}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"agent_type": self.agent_type, "store_id": store_id},
            )
            return AgentResult(
                success=False,
                data=None,
                message=f"Agent 执行失败: {e}",
                reasoning=f"Tool Use 执行异常: {e}",
                confidence=0.0,
                source_data={"user_message": user_message, "store_id": store_id},
            )

    # ── 单轮 LLM 调用（向后兼容）────────────────────────────────────────────

    async def execute_with_llm(
        self,
        action: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        单轮 LLM 调用（不使用 Tool Use）

        保留此方法以向后兼容现有 Agent 代码。
        新代码推荐使用 execute_with_tools()。
        """
        try:
            user_prompt = AgentPrompts.format_user_prompt(
                action=action, params=params, context=context
            )
            logger.info(
                "agent_single_llm_call",
                agent=self.agent_type,
                action=action,
            )
            llm_client = get_llm_client()
            response_text = await llm_client.generate(
                prompt=user_prompt,
                system_prompt=self.system_prompt,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
            response_data = self._parse_llm_response(response_text)
            logger.info(
                "agent_single_llm_completed",
                agent=self.agent_type,
                action=action,
                success=response_data.get("success", True),
            )
            return response_data

        except Exception as e:
            logger.error(
                "agent_single_llm_failed",
                agent=self.agent_type,
                action=action,
                error=str(e),
                exc_info=e,
            )
            error_monitor.log_error(
                message=f"LLM execution failed for {self.agent_type}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={"agent_type": self.agent_type, "action": action, "params": params},
            )
            return {
                "success": False,
                "data": None,
                "error": str(e),
                "message": "Agent 执行失败",
            }

    # ── 降级执行（Tool Use → 规则引擎）──────────────────────────────────────

    async def execute_with_fallback(
        self,
        action: str,
        params: Dict[str, Any],
        fallback_handler: Callable,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        优先使用 LLM 执行，失败时回退到规则引擎

        Args:
            action:           操作类型
            params:           参数
            fallback_handler: 规则引擎回退函数 async(action, params) -> dict
            context:          上下文
        """
        if not self.llm_enabled:
            logger.info("llm_disabled_using_fallback", agent=self.agent_type, action=action)
            return await fallback_handler(action, params)

        try:
            result = await self.execute_with_llm(action, params, context)
            if result.get("success", False):
                return result
            logger.warning(
                "llm_unsuccessful_falling_back",
                agent=self.agent_type,
                action=action,
            )
            return await fallback_handler(action, params)
        except Exception as e:
            logger.warning(
                "llm_error_falling_back",
                agent=self.agent_type,
                action=action,
                error=str(e),
            )
            return await fallback_handler(action, params)

    # ── 流式输出 ─────────────────────────────────────────────────────────────

    async def stream_response(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        流式输出 Agent 响应（适用于实时对话场景）

        用法：
            async for chunk in agent.stream_response("分析本周营收"):
                websocket.send(chunk)
        """
        llm_client = get_llm_client()
        async for chunk in llm_client.generate_stream(
            prompt=user_message,
            system_prompt=system_prompt or self.system_prompt,
        ):
            yield chunk

    # ── 格式化响应 ────────────────────────────────────────────────────────────

    def format_response(
        self,
        success: bool,
        data: Any,
        message: str = "",
        recommendations: Optional[List[Any]] = None,
        reasoning: str = "",
        confidence: float = 0.0,
        source_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        """格式化 Agent 响应，返回带可追溯字段的 AgentResult"""
        return AgentResult(
            success=success,
            data=data,
            message=message,
            reasoning=reasoning,
            confidence=confidence,
            source_data=source_data or {},
            recommendations=recommendations,
        )

    # ── Agent Memory Bus helpers ──────────────────────────────────────────────

    async def publish_finding(
        self,
        store_id: str,
        action: str,
        summary: str,
        confidence: float = 0.0,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发布洞察到共享 Agent Memory Bus，供其他 Agent 感知"""
        try:
            from ..services.agent_memory_bus import agent_memory_bus
            await agent_memory_bus.publish(
                store_id=store_id,
                agent_id=self.agent_type,
                action=action,
                summary=summary,
                confidence=confidence,
                data=data,
            )
        except Exception as e:
            logger.warning(
                "agent_publish_finding_failed",
                agent=self.agent_type,
                store_id=store_id,
                error=str(e),
            )

    async def get_peer_context(self, store_id: str, last_n: int = 10) -> str:
        """获取其他 Agent 的最近洞察，注入到 LLM 上下文"""
        try:
            from ..services.agent_memory_bus import agent_memory_bus
            return await agent_memory_bus.get_peer_context(
                store_id=store_id,
                requesting_agent=self.agent_type,
                last_n=last_n,
            )
        except Exception as e:
            logger.warning(
                "agent_get_peer_context_failed",
                agent=self.agent_type,
                store_id=store_id,
                error=str(e),
            )
            return ""

    # ── 私有辅助方法 ──────────────────────────────────────────────────────────

    def _build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """构建增强的 system prompt（注入上下文和工具使用指引）"""
        base_prompt = self.system_prompt
        tool_guide = (
            "\n\n## 工具使用指引\n"
            "你有权调用以下工具获取实时业务数据。请按需调用，不要猜测数据。\n"
            "每次决策必须基于工具返回的真实数据，并在最终回复中说明推理依据。\n"
            "最终回复请使用结构化 JSON 格式，包含：success、data、message、reasoning、confidence（0-1）。"
        )
        if context:
            ctx_str = json.dumps(context, ensure_ascii=False, indent=2)
            return f"{base_prompt}{tool_guide}\n\n## 当前上下文\n```json\n{ctx_str}\n```"
        return f"{base_prompt}{tool_guide}"

    def _parse_llm_response(self, text: str) -> Any:
        """尝试从 LLM 响应中提取 JSON，失败则返回原始文本"""
        if not text:
            return {"raw_response": ""}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 ```json ... ``` 代码块
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            # 尝试提取裸 JSON 对象
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"raw_response": text}

    def _calc_confidence(self, tool_result: Dict[str, Any]) -> float:
        """基于工具调用结果计算置信度"""
        tool_calls = tool_result.get("tool_calls", [])
        if not tool_calls:
            return 0.5  # 无工具调用，中等置信度

        error_count = sum(1 for t in tool_calls if t.get("is_error", False))
        success_rate = 1.0 - (error_count / len(tool_calls))
        # 迭代次数越少，置信度越高（说明 Claude 更确定）
        iteration_penalty = min(0.1 * (tool_result.get("iterations", 1) - 1), 0.3)
        return round(max(0.1, min(0.95, success_rate * 0.9 - iteration_penalty)), 2)

    def _build_reasoning_summary(self, tool_result: Dict[str, Any]) -> str:
        """从 reasoning_trace 构建可读的推理摘要"""
        trace = tool_result.get("reasoning_trace", [])
        tool_calls = tool_result.get("tool_calls", [])
        tools_used = list({t["name"] for t in tool_calls})

        summary_parts = [
            f"共执行 {tool_result.get('iterations', 0)} 轮推理",
            f"调用工具: {', '.join(tools_used) if tools_used else '无'}",
            f"停止原因: {tool_result.get('stop_reason', 'unknown')}",
        ]
        if trace:
            last_thought = trace[-1].get("text", "")
            if last_thought:
                summary_parts.append(f"最终推理: {last_thought[:200]}")

        return " | ".join(summary_parts)
