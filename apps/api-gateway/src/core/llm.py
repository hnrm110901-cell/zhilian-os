"""
LLM集成模块
支持多种LLM提供商 (OpenAI, Anthropic, Azure OpenAI, DeepSeek)

Anthropic 客户端已升级为完整 Tool Use 支持：
  - generate()                  : 单轮文本生成
  - generate_with_context()     : 多轮对话
  - generate_with_tools()       : Tool Use agentic loop（核心）
  - generate_stream()           : 流式输出
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# 枚举
# ─────────────────────────────────────────────────────────────────────────────

class LLMProvider(str):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    DEEPSEEK = "deepseek"


class LLMModel(str):
    # OpenAI
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo-preview"
    GPT_35_TURBO = "gpt-3.5-turbo"

    # Anthropic — 使用精确 model ID，不附加日期后缀
    CLAUDE_OPUS = "claude-opus-4-6"
    CLAUDE_SONNET = "claude-sonnet-4-6"
    CLAUDE_HAIKU = "claude-haiku-4-5"

    # DeepSeek
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_CODER = "deepseek-coder"

    # 向后兼容别名
    CLAUDE_3_OPUS = "claude-opus-4-6"
    CLAUDE_3_SONNET = "claude-sonnet-4-6"
    CLAUDE_3_HAIKU = "claude-haiku-4-5"


# ─────────────────────────────────────────────────────────────────────────────
# 基类
# ─────────────────────────────────────────────────────────────────────────────

class BaseLLMClient(ABC):
    """LLM客户端基类"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
        **kwargs,
    ) -> str:
        """单轮文本生成"""
        pass

    @abstractmethod
    async def generate_with_context(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
        **kwargs,
    ) -> str:
        """多轮对话生成"""
        pass

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Any],
        system_prompt: Optional[str] = None,
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096")),
        max_iterations: int = 10,
    ) -> Dict[str, Any]:
        """
        Tool Use agentic loop（默认实现：不支持工具，直接调用 generate）

        子类（AnthropicClient）会覆盖此方法提供完整实现。
        """
        prompt = messages[-1]["content"] if messages else ""
        text = await self.generate(
            prompt=str(prompt),
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        return {
            "text": text,
            "tool_calls": [],
            "iterations": 1,
            "stop_reason": "end_turn",
        }

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
    ) -> AsyncIterator[str]:
        """流式输出（默认实现：一次性返回）"""
        text = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        yield text


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI / DeepSeek 客户端（兼容 OpenAI SDK）
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIClient(BaseLLMClient):
    """OpenAI 及 DeepSeek（OpenAI 兼容）客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = LLMModel.GPT_4_TURBO,
        base_url: Optional[str] = None,
    ):
        super().__init__(api_key, model)
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.api_key or os.getenv("OPENAI_API_KEY"),
                    base_url=self.base_url,
                )
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
        **kwargs,
    ) -> str:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return await self.generate_with_context(messages, temperature, max_tokens, **kwargs)

    async def generate_with_context(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
        **kwargs,
    ) -> str:
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            content = response.choices[0].message.content
            logger.info(
                "openai_generation_completed",
                model=self.model,
                tokens_used=response.usage.total_tokens,
            )
            return content
        except Exception as e:
            logger.error("openai_generation_failed", error=str(e), exc_info=e)
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic 客户端 — 完整 Tool Use 实现
# ─────────────────────────────────────────────────────────────────────────────

class AnthropicClient(BaseLLMClient):
    """
    Anthropic Claude 客户端

    核心能力：
    - generate()              : 单轮文本生成（adaptive thinking 可选）
    - generate_with_context() : 多轮对话
    - generate_with_tools()   : 完整 Tool Use agentic loop
    - generate_stream()       : 流式输出
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = LLMModel.CLAUDE_SONNET,
    ):
        super().__init__(api_key, model)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(
                    api_key=self.api_key or os.getenv("ANTHROPIC_API_KEY"),
                )
            except ImportError:
                raise ImportError(
                    "Anthropic package not installed. Run: pip install anthropic"
                )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
        **kwargs,
    ) -> str:
        """单轮文本生成"""
        messages = [{"role": "user", "content": prompt}]
        return await self.generate_with_context(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            **kwargs,
        )

    async def generate_with_context(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> str:
        """多轮对话生成"""
        try:
            client = self._get_client()
            api_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs,
            }
            if system_prompt:
                api_kwargs["system"] = system_prompt

            response = await client.messages.create(**api_kwargs)
            # 取第一个 text block
            content = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            logger.info(
                "anthropic_generation_completed",
                model=self.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            return content
        except Exception as e:
            logger.error("anthropic_generation_failed", error=str(e), exc_info=e)
            raise

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Any],
        system_prompt: Optional[str] = None,
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096")),
        max_iterations: int = 10,
    ) -> Dict[str, Any]:
        """
        Claude Tool Use 完整 agentic loop

        流程：
          1. 调用 Claude（携带 tools 定义）
          2. 若 stop_reason == "tool_use"：执行所有 tool_use block → 回传 tool_result
          3. 循环直到 stop_reason == "end_turn" 或达到 max_iterations
          4. 返回最终文本 + 完整工具调用记录 + reasoning_trace

        Args:
            messages:       对话历史（[{"role": "user", "content": "..."}]）
            tools:          Claude Tool Use 格式的工具定义列表
            tool_executor:  async callable(tool_name, tool_input) -> Any
            system_prompt:  系统提示词
            max_tokens:     最大输出 token 数
            max_iterations: 最大循环次数（防止无限循环）

        Returns:
            {
                "text":          最终回复文本,
                "tool_calls":    [{"name": ..., "input": ..., "result": ...}, ...],
                "iterations":    循环次数,
                "stop_reason":   最终停止原因,
                "usage":         {"input_tokens": ..., "output_tokens": ...},
                "reasoning_trace": [...],  # 每轮决策记录
            }
        """
        client = self._get_client()

        # 深拷贝，避免污染调用方的 messages
        conversation: List[Dict[str, Any]] = list(messages)
        tool_calls_log: List[Dict[str, Any]] = []
        reasoning_trace: List[Dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0

        for iteration in range(max_iterations):
            api_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": conversation,
                "tools": tools,
                "max_tokens": max_tokens,
            }
            if system_prompt:
                api_kwargs["system"] = system_prompt

            logger.info(
                "claude_tool_use_iteration",
                iteration=iteration + 1,
                model=self.model,
                message_count=len(conversation),
            )

            response = await client.messages.create(**api_kwargs)
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # 记录本轮推理
            text_in_turn = " ".join(
                b.text for b in response.content if b.type == "text"
            )
            reasoning_trace.append({
                "iteration": iteration + 1,
                "stop_reason": response.stop_reason,
                "text": text_in_turn,
                "tool_uses": [
                    {"name": b.name, "input": b.input}
                    for b in response.content
                    if b.type == "tool_use"
                ],
            })

            # 将 assistant 回复追加到对话历史
            conversation.append({
                "role": "assistant",
                "content": response.content,
            })

            # ── 终止条件 ──────────────────────────────────────────────────────
            if response.stop_reason == "end_turn":
                final_text = text_in_turn
                logger.info(
                    "claude_tool_use_completed",
                    iterations=iteration + 1,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )
                return {
                    "text": final_text,
                    "tool_calls": tool_calls_log,
                    "iterations": iteration + 1,
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                    },
                    "reasoning_trace": reasoning_trace,
                }

            # ── 执行工具调用 ──────────────────────────────────────────────────
            if response.stop_reason == "tool_use":
                tool_results: List[Dict[str, Any]] = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    logger.info(
                        "claude_executing_tool",
                        tool=tool_name,
                        tool_use_id=tool_use_id,
                    )

                    try:
                        result = await tool_executor(tool_name, tool_input)
                        # 确保结果可序列化为字符串
                        result_str = (
                            json.dumps(result, ensure_ascii=False)
                            if not isinstance(result, str)
                            else result
                        )
                        is_error = False
                    except Exception as exc:
                        result_str = f"工具执行失败: {exc}"
                        is_error = True
                        logger.warning(
                            "claude_tool_execution_error",
                            tool=tool_name,
                            error=str(exc),
                        )

                    tool_calls_log.append({
                        "name": tool_name,
                        "input": tool_input,
                        "result": result_str,
                        "is_error": is_error,
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_str,
                        "is_error": is_error,
                    })

                # 将工具结果作为 user 消息回传
                conversation.append({
                    "role": "user",
                    "content": tool_results,
                })
                continue  # 进入下一轮

            # 其他 stop_reason（max_tokens 等）直接退出
            logger.warning(
                "claude_unexpected_stop_reason",
                stop_reason=response.stop_reason,
                iteration=iteration + 1,
            )
            break

        # 超出最大迭代次数
        final_text = " ".join(
            b.text
            for b in (response.content if "response" in dir() else [])
            if b.type == "text"
        )
        logger.warning(
            "claude_tool_use_max_iterations_reached",
            max_iterations=max_iterations,
        )
        return {
            "text": final_text,
            "tool_calls": tool_calls_log,
            "iterations": max_iterations,
            "stop_reason": "max_iterations",
            "usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            },
            "reasoning_trace": reasoning_trace,
        }

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000")),
    ) -> AsyncIterator[str]:
        """
        流式输出 — 逐 token 产出文本 delta

        用法：
            async for chunk in client.generate_stream(prompt, system_prompt):
                print(chunk, end="", flush=True)
        """
        client = self._get_client()
        api_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if system_prompt:
            api_kwargs["system"] = system_prompt

        async with client.messages.stream(**api_kwargs) as stream:
            async for text_chunk in stream.text_stream:
                yield text_chunk

        final = await stream.get_final_message()
        logger.info(
            "anthropic_stream_completed",
            model=self.model,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 工厂 & 全局单例
# ─────────────────────────────────────────────────────────────────────────────

class LLMFactory:
    """LLM 工厂类"""

    @staticmethod
    def create_client(
        provider: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> BaseLLMClient:
        if provider == LLMProvider.ANTHROPIC:
            return AnthropicClient(
                api_key=api_key,
                model=model or LLMModel.CLAUDE_SONNET,
            )
        elif provider == LLMProvider.OPENAI:
            return OpenAIClient(
                api_key=api_key,
                model=model or LLMModel.GPT_4_TURBO,
                **kwargs,
            )
        elif provider == LLMProvider.AZURE_OPENAI:
            return OpenAIClient(
                api_key=api_key,
                model=model or LLMModel.GPT_4_TURBO,
                base_url=kwargs.get("base_url"),
            )
        elif provider == LLMProvider.DEEPSEEK:
            return OpenAIClient(
                api_key=api_key,
                model=model or LLMModel.DEEPSEEK_CHAT,
                base_url=kwargs.get("base_url", "https://api.deepseek.com"),
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


# 全局单例
_llm_client: Optional[BaseLLMClient] = None


def get_llm_client() -> BaseLLMClient:
    """获取全局 LLM 客户端（懒初始化）"""
    global _llm_client
    if _llm_client is None:
        provider = os.getenv("LLM_PROVIDER", LLMProvider.OPENAI)
        model = os.getenv("LLM_MODEL")
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")

        kwargs: Dict[str, Any] = {}
        if base_url:
            kwargs["base_url"] = base_url

        _llm_client = LLMFactory.create_client(
            provider=provider,
            api_key=api_key,
            model=model,
            **kwargs,
        )
        logger.info(
            "llm_client_initialized",
            provider=provider,
            model=model or "default",
        )
    return _llm_client


def set_llm_client(client: BaseLLMClient) -> None:
    """替换全局 LLM 客户端（测试 / 热切换用）"""
    global _llm_client
    _llm_client = client
    logger.info("llm_client_updated", client_type=type(client).__name__)
