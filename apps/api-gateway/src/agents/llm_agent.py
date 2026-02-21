"""
增强的Agent基类 - 支持LLM集成
"""
from typing import Dict, Any, Optional
import json
import structlog

from ..core.llm import get_llm_client
from ..core.prompts import AgentPrompts
from ..core.config import settings
from ..core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

logger = structlog.get_logger()


class LLMEnhancedAgent:
    """
    LLM增强的Agent基类

    提供LLM集成能力，可以在模拟模式和LLM模式之间切换
    """

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.llm_enabled = settings.LLM_ENABLED
        self.system_prompt = AgentPrompts.get_prompt(agent_type)

    async def execute_with_llm(
        self,
        action: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        使用LLM执行Agent操作

        Args:
            action: 操作类型
            params: 参数
            context: 上下文信息

        Returns:
            执行结果
        """
        try:
            # 格式化用户提示词
            user_prompt = AgentPrompts.format_user_prompt(
                action=action,
                params=params,
                context=context
            )

            logger.info(
                "Executing agent with LLM",
                agent_type=self.agent_type,
                action=action,
                llm_enabled=self.llm_enabled,
            )

            # 调用LLM
            llm_client = get_llm_client()
            response_text = await llm_client.generate(
                prompt=user_prompt,
                system_prompt=self.system_prompt,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )

            # 解析JSON响应
            try:
                response_data = json.loads(response_text)
            except json.JSONDecodeError:
                # 如果LLM返回的不是有效JSON，尝试提取JSON部分
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    response_data = json.loads(json_match.group())
                else:
                    # 如果无法解析，返回原始文本
                    response_data = {
                        "success": True,
                        "data": {"raw_response": response_text},
                        "message": "LLM响应已生成",
                    }

            logger.info(
                "LLM execution completed",
                agent_type=self.agent_type,
                action=action,
                success=response_data.get("success", True),
            )

            return response_data

        except Exception as e:
            logger.error(
                "LLM execution failed",
                agent_type=self.agent_type,
                action=action,
                error=str(e),
                exc_info=e,
            )

            # 记录错误到监控系统
            error_monitor.log_error(
                message=f"LLM execution failed for {self.agent_type}",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.AGENT,
                exception=e,
                context={
                    "agent_type": self.agent_type,
                    "action": action,
                    "params": params,
                },
            )

            # 返回错误响应
            return {
                "success": False,
                "data": None,
                "error": str(e),
                "message": "Agent执行失败",
            }

    async def execute_with_fallback(
        self,
        action: str,
        params: Dict[str, Any],
        fallback_handler: callable,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        使用LLM执行，失败时回退到模拟模式

        Args:
            action: 操作类型
            params: 参数
            fallback_handler: 回退处理函数
            context: 上下文信息

        Returns:
            执行结果
        """
        if not self.llm_enabled:
            logger.info(
                "LLM disabled, using fallback handler",
                agent_type=self.agent_type,
                action=action,
            )
            return await fallback_handler(action, params)

        try:
            result = await self.execute_with_llm(action, params, context)

            # 检查LLM执行是否成功
            if result.get("success", False):
                return result
            else:
                logger.warning(
                    "LLM execution unsuccessful, falling back",
                    agent_type=self.agent_type,
                    action=action,
                )
                return await fallback_handler(action, params)

        except Exception as e:
            logger.warning(
                "LLM execution error, falling back",
                agent_type=self.agent_type,
                action=action,
                error=str(e),
            )
            return await fallback_handler(action, params)

    def format_response(
        self,
        success: bool,
        data: Any,
        message: str = "",
        recommendations: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        格式化Agent响应

        Args:
            success: 是否成功
            data: 数据
            message: 消息
            recommendations: 建议列表

        Returns:
            格式化的响应
        """
        response = {
            "success": success,
            "data": data,
            "message": message,
        }

        if recommendations:
            response["recommendations"] = recommendations

        return response
