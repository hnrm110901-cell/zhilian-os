"""
Custom exceptions for the application

屯象OS 异常层级体系：
- 保留原有 NotFoundError / ValidationError / AuthenticationError / AuthorizationError
- 新增 TunxiangBaseError 及其子类，用于逐步替换宽泛的 except Exception
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# 原有异常（保持向后兼容）
# ---------------------------------------------------------------------------


class NotFoundError(Exception):
    """Resource not found exception"""

    pass


class ValidationError(Exception):
    """Validation error exception"""

    pass


class AuthenticationError(Exception):
    """Authentication error exception"""

    pass


class AuthorizationError(Exception):
    """Authorization error exception"""

    pass


# ---------------------------------------------------------------------------
# 屯象OS 异常层级体系
# ---------------------------------------------------------------------------


class TunxiangBaseError(Exception):
    """屯象OS 基础异常类

    所有业务异常的根类，提供统一的 context 属性和序列化能力。
    """

    def __init__(
        self,
        message: str = "",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = context or {}
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """将异常序列化为字典，便于日志记录和 API 响应。"""
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# 外部 API 调用相关异常
# ---------------------------------------------------------------------------


class ExternalAPIError(TunxiangBaseError):
    """外部 API 调用失败"""

    pass


class POSAdapterError(ExternalAPIError):
    """POS 适配器调用失败"""

    pass


class PinzhiAPIError(POSAdapterError):
    """品智 POS API 调用失败"""

    pass


class AoqiweiAPIError(POSAdapterError):
    """奥琦玮 POS API 调用失败"""

    pass


class MeituanAPIError(POSAdapterError):
    """美团 SaaS API 调用失败"""

    pass


class WeComWebhookError(ExternalAPIError):
    """企业微信 Webhook 调用失败"""

    pass


class FeishuWebhookError(ExternalAPIError):
    """飞书 Webhook 调用失败"""

    pass


class SMSServiceError(ExternalAPIError):
    """短信服务调用失败"""

    pass


# ---------------------------------------------------------------------------
# 数据校验相关异常
# ---------------------------------------------------------------------------


class DataValidationError(TunxiangBaseError):
    """数据校验失败"""

    pass


class ReconciliationMismatchError(DataValidationError):
    """对账数据不一致"""

    pass


# ---------------------------------------------------------------------------
# 安全相关异常
# ---------------------------------------------------------------------------


class TenantIsolationError(TunxiangBaseError):
    """租户隔离被突破（安全事件）

    构造时自动记录 critical 级别日志，因为跨租户访问属于严重安全事件。
    """

    def __init__(
        self,
        message: str = "",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, context=context)
        logger.critical(
            "tenant_isolation_violation",
            error_message=message,
            context=self.context,
        )


# ---------------------------------------------------------------------------
# 业务规则相关异常
# ---------------------------------------------------------------------------


class BusinessRuleError(TunxiangBaseError):
    """业务规则违反"""

    pass


class MarginViolationError(BusinessRuleError):
    """毛利率低于底线阈值"""

    pass


class FoodSafetyError(BusinessRuleError):
    """食品安全合规违规"""

    pass


class ServiceTimeoutError(BusinessRuleError):
    """出餐时限超时"""

    pass


# ---------------------------------------------------------------------------
# 基础设施相关异常
# ---------------------------------------------------------------------------


class InfrastructureError(TunxiangBaseError):
    """基础设施层错误"""

    pass


class CacheConnectionError(InfrastructureError):
    """缓存连接失败（Redis 等）"""

    pass


class VectorDBError(InfrastructureError):
    """向量数据库操作失败（Qdrant 等）"""

    pass


class ModelRouterError(InfrastructureError):
    """模型路由失败（LLM 调用路由）"""

    pass


# ---------------------------------------------------------------------------
# Agent 相关异常
# ---------------------------------------------------------------------------


class AgentError(TunxiangBaseError):
    """Agent 运行时错误"""

    pass


class AgentDecisionError(AgentError):
    """Agent 决策失败"""

    pass


class AgentConstraintViolation(AgentError):
    """Agent 约束被违反"""

    pass
