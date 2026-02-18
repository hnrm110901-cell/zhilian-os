"""
LLM集成模块
支持多种LLM提供商 (OpenAI, Anthropic, Azure OpenAI)
"""
from typing import Optional, Dict, Any, List
from enum import Enum
import os
from abc import ABC, abstractmethod
import structlog

logger = structlog.get_logger()


class LLMProvider(str, Enum):
    """LLM提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"


class LLMModel(str, Enum):
    """LLM模型"""
    # OpenAI models
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo-preview"
    GPT_35_TURBO = "gpt-3.5-turbo"

    # Anthropic models
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"


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
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """
        生成文本

        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数

        Returns:
            生成的文本
        """
        pass

    @abstractmethod
    async def generate_with_context(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """
        基于对话历史生成文本

        Args:
            messages: 对话历史 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数

        Returns:
            生成的文本
        """
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = LLMModel.GPT_4_TURBO.value,
        base_url: Optional[str] = None,
    ):
        super().__init__(api_key, model)
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        """获取OpenAI客户端（延迟初始化）"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key or os.getenv("OPENAI_API_KEY"),
                    base_url=self.base_url,
                )
            except ImportError:
                raise ImportError(
                    "OpenAI package not installed. Install with: pip install openai"
                )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """生成文本"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return await self.generate_with_context(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    async def generate_with_context(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """基于对话历史生成文本"""
        try:
            client = self._get_client()

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            content = response.choices[0].message.content

            logger.info(
                "OpenAI generation completed",
                model=self.model,
                tokens_used=response.usage.total_tokens,
            )

            return content

        except Exception as e:
            logger.error("OpenAI generation failed", error=str(e), exc_info=e)
            raise


class AnthropicClient(BaseLLMClient):
    """Anthropic客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = LLMModel.CLAUDE_3_SONNET.value,
    ):
        super().__init__(api_key, model)
        self._client = None

    def _get_client(self):
        """获取Anthropic客户端（延迟初始化）"""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(
                    api_key=self.api_key or os.getenv("ANTHROPIC_API_KEY"),
                )
            except ImportError:
                raise ImportError(
                    "Anthropic package not installed. Install with: pip install anthropic"
                )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """生成文本"""
        messages = [{"role": "user", "content": prompt}]

        return await self.generate_with_context(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            **kwargs
        )

    async def generate_with_context(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """基于对话历史生成文本"""
        try:
            client = self._get_client()

            # Anthropic API需要单独的system参数
            api_kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

            if system_prompt:
                api_kwargs["system"] = system_prompt

            response = await client.messages.create(**api_kwargs)

            content = response.content[0].text

            logger.info(
                "Anthropic generation completed",
                model=self.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            )

            return content

        except Exception as e:
            logger.error("Anthropic generation failed", error=str(e), exc_info=e)
            raise


class LLMFactory:
    """LLM工厂类"""

    @staticmethod
    def create_client(
        provider: LLMProvider,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> BaseLLMClient:
        """
        创建LLM客户端

        Args:
            provider: LLM提供商
            api_key: API密钥
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            LLM客户端实例
        """
        if provider == LLMProvider.OPENAI:
            return OpenAIClient(
                api_key=api_key,
                model=model or LLMModel.GPT_4_TURBO.value,
                **kwargs
            )
        elif provider == LLMProvider.ANTHROPIC:
            return AnthropicClient(
                api_key=api_key,
                model=model or LLMModel.CLAUDE_3_SONNET.value,
                **kwargs
            )
        elif provider == LLMProvider.AZURE_OPENAI:
            # Azure OpenAI使用OpenAI客户端，但需要不同的base_url
            return OpenAIClient(
                api_key=api_key,
                model=model or LLMModel.GPT_4_TURBO.value,
                base_url=kwargs.get("base_url"),
                **kwargs
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


# 全局LLM客户端实例（可配置）
_llm_client: Optional[BaseLLMClient] = None


def get_llm_client() -> BaseLLMClient:
    """
    获取全局LLM客户端

    Returns:
        LLM客户端实例
    """
    global _llm_client

    if _llm_client is None:
        # 从环境变量读取配置
        provider = os.getenv("LLM_PROVIDER", LLMProvider.OPENAI.value)
        model = os.getenv("LLM_MODEL")
        api_key = os.getenv("LLM_API_KEY")

        _llm_client = LLMFactory.create_client(
            provider=LLMProvider(provider),
            api_key=api_key,
            model=model,
        )

        logger.info(
            "LLM client initialized",
            provider=provider,
            model=model or "default",
        )

    return _llm_client


def set_llm_client(client: BaseLLMClient):
    """
    设置全局LLM客户端

    Args:
        client: LLM客户端实例
    """
    global _llm_client
    _llm_client = client
    logger.info("LLM client updated", client_type=type(client).__name__)
