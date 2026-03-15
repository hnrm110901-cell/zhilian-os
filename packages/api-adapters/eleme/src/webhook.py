"""
饿了么 Webhook 回调处理器
处理饿了么开放平台推送的各类业务事件
"""
import hashlib
import hmac
import time
from typing import Any, Callable, Coroutine, Dict, Optional

import structlog

logger = structlog.get_logger()

# 签名验证容许的时间偏差（秒）
TIMESTAMP_TOLERANCE = 300


class ElemeWebhookHandler:
    """饿了么 Webhook 事件处理器"""

    def __init__(self, app_secret: str):
        """
        初始化 Webhook 处理器

        Args:
            app_secret: 饿了么应用密钥，用于签名验证
        """
        self.app_secret = app_secret
        self._handlers: Dict[
            str, Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
        ] = {}

    def verify_signature(
        self,
        payload: str,
        signature: str,
        timestamp: str,
    ) -> bool:
        """
        验证回调签名

        饿了么签名规则：
          sign = SHA256(app_secret + payload + timestamp + app_secret)
          取大写hex

        Args:
            payload: 原始请求体字符串
            signature: 饿了么传入的签名
            timestamp: 饿了么传入的时间戳

        Returns:
            签名是否合法
        """
        # 时间戳防重放
        try:
            ts = int(timestamp)
            now = int(time.time())
            if abs(now - ts) > TIMESTAMP_TOLERANCE:
                logger.warning(
                    "饿了么Webhook时间戳过期",
                    timestamp=timestamp,
                    diff=abs(now - ts),
                )
                return False
        except (ValueError, TypeError):
            logger.warning("饿了么Webhook时间戳格式错误", timestamp=timestamp)
            return False

        sign_str = f"{self.app_secret}{payload}{timestamp}{self.app_secret}"
        expected = hashlib.sha256(sign_str.encode("utf-8")).hexdigest().upper()
        return hmac.compare_digest(expected, signature.upper())

    def on(
        self,
        event_type: str,
        handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """
        注册事件处理函数

        Args:
            event_type: 事件类型
            handler: 异步处理函数
        """
        self._handlers[event_type] = handler
        logger.info("注册饿了么Webhook处理器", event_type=event_type)

    async def handle_event(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        分发事件到对应处理器

        支持的事件类型：
          - order.created      新订单创建
          - order.paid         订单已支付
          - order.cancelled    订单已取消
          - order.refunded     订单已退款
          - delivery.status_changed  配送状态变更
          - food.stock_warning       库存预警

        Args:
            event_type: 事件类型
            data: 事件数据

        Returns:
            处理结果
        """
        logger.info("饿了么Webhook事件", event_type=event_type)

        handler = self._handlers.get(event_type)
        if handler:
            try:
                await handler(data)
                return {"success": True, "event_type": event_type}
            except Exception as e:
                logger.error(
                    "饿了么Webhook处理异常",
                    event_type=event_type,
                    error=str(e),
                )
                return {
                    "success": False,
                    "event_type": event_type,
                    "error": str(e),
                }
        else:
            logger.warning("饿了么Webhook未注册处理器", event_type=event_type)
            return {
                "success": True,
                "event_type": event_type,
                "message": "no handler registered, event acknowledged",
            }
