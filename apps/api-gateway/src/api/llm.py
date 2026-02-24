"""
LLM配置管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..core.dependencies import require_permission
from ..core.permissions import Permission
from ..core.config import settings
from ..core.llm import get_llm_client, set_llm_client, LLMFactory, LLMProvider
from ..models.user import User

router = APIRouter()


class LLMConfigResponse(BaseModel):
    """LLM配置响应"""
    enabled: bool
    provider: str
    model: str
    temperature: float
    max_tokens: int


class LLMConfigUpdate(BaseModel):
    """LLM配置更新"""
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class LLMTestRequest(BaseModel):
    """LLM测试请求"""
    prompt: str
    system_prompt: Optional[str] = None


@router.get("/llm/config", response_model=LLMConfigResponse)
async def get_llm_config(
    current_user: User = Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    获取LLM配置

    返回当前的LLM配置信息（不包含API密钥）。

    **认证要求**: 需要 `system:config` 权限

    **示例响应**:
    ```json
    {
        "enabled": true,
        "provider": "openai",
        "model": "gpt-4-turbo-preview",
        "temperature": 0.7,
        "max_tokens": 2000
    }
    ```
    """
    return LLMConfigResponse(
        enabled=settings.LLM_ENABLED,
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
    )


@router.put("/llm/config")
async def update_llm_config(
    config: LLMConfigUpdate,
    current_user: User = Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    更新LLM配置

    更新LLM配置参数。更改会立即生效。

    **认证要求**: 需要 `system:config` 权限

    **示例请求**:
    ```json
    {
        "enabled": true,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "api_key": "sk-ant-...",
        "temperature": 0.8,
        "max_tokens": 3000
    }
    ```

    **注意**: API密钥会被安全存储，不会在响应中返回
    """
    # 更新配置
    if config.enabled is not None:
        settings.LLM_ENABLED = config.enabled

    if config.provider is not None:
        settings.LLM_PROVIDER = config.provider

    if config.model is not None:
        settings.LLM_MODEL = config.model

    if config.temperature is not None:
        settings.LLM_TEMPERATURE = config.temperature

    if config.max_tokens is not None:
        settings.LLM_MAX_TOKENS = config.max_tokens

    # 如果提供了API密钥或更改了提供商，重新初始化LLM客户端
    if config.api_key or config.provider:
        try:
            new_client = LLMFactory.create_client(
                provider=LLMProvider(settings.LLM_PROVIDER),
                api_key=config.api_key or settings.LLM_API_KEY,
                model=settings.LLM_MODEL,
            )
            set_llm_client(new_client)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to initialize LLM client: {str(e)}"
            )

    return {
        "message": "LLM配置已更新",
        "config": {
            "enabled": settings.LLM_ENABLED,
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
        }
    }


@router.post("/llm/test")
async def test_llm(
    request: LLMTestRequest,
    current_user: User = Depends(require_permission(Permission.SYSTEM_CONFIG)),
):
    """
    测试LLM连接

    发送测试提示词到LLM，验证配置是否正确。

    **认证要求**: 需要 `system:config` 权限

    **示例请求**:
    ```json
    {
        "prompt": "你好，请介绍一下你自己",
        "system_prompt": "你是一个友好的AI助手"
    }
    ```

    **示例响应**:
    ```json
    {
        "success": true,
        "response": "你好！我是一个AI助手...",
        "provider": "openai",
        "model": "gpt-4-turbo-preview"
    }
    ```
    """
    if not settings.LLM_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="LLM未启用，请先在配置中启用LLM"
        )

    try:
        llm_client = get_llm_client()

        response = await llm_client.generate(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

        return {
            "success": True,
            "response": response,
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
        }
