"""
企业微信告警服务
用于发送各类业务告警到企业微信
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import os
import structlog

from ..core.config import settings
from .wechat_work_message_service import wechat_work_message_service

logger = structlog.get_logger()


class WeChatAlertService:
    """
    企业微信告警服务

    功能:
    - 营收异常告警
    - 库存预警
    - 订单异常告警
    - 系统错误告警
    """

    def __init__(self):
        self.message_service = wechat_work_message_service

    async def send_revenue_alert(
        self,
        store_id: str,
        store_name: str,
        current_revenue: float,
        expected_revenue: float,
        deviation: float,
        analysis: str,
        recipient_ids: List[str]
    ) -> Dict[str, Any]:
        """
        发送营收异常告警

        Args:
            store_id: 门店ID
            store_name: 门店名称
            current_revenue: 当前营收
            expected_revenue: 预期营收
            deviation: 偏差百分比
            analysis: AI分析结果
            recipient_ids: 接收人企微ID列表

        Returns:
            发送结果
        """
        try:
            # 确定告警级别和emoji
            _critical_threshold = float(os.getenv("REVENUE_ALERT_CRITICAL_THRESHOLD", "30"))
            _warning_threshold = float(os.getenv("REVENUE_ALERT_WARNING_THRESHOLD", "20"))
            if abs(deviation) > _critical_threshold:
                level = "严重"
                emoji = "🚨"
            elif abs(deviation) > _warning_threshold:
                level = "警告"
                emoji = "⚠️"
            else:
                level = "提示"
                emoji = "📊"

            # 构建告警消息
            message = f"""{emoji} 营收异常告警 [{level}]

门店: {store_name}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 数据对比:
• 当前营收: ¥{current_revenue:,.2f}
• 预期营收: ¥{expected_revenue:,.2f}
• 偏差: {deviation:+.1f}%

🤖 AI分析:
{analysis}

---
智链OS实时监控 | 每15分钟自动检测
"""

            logger.info(
                "Sending revenue alert",
                store_id=store_id,
                deviation=deviation,
                recipient_count=len(recipient_ids)
            )

            # 发送给所有接收人
            sent_count = 0
            failed_count = 0

            for recipient_id in recipient_ids:
                try:
                    result = await self.message_service.send_text_message(
                        user_id=recipient_id,
                        content=message
                    )
                    if result.get("success"):
                        sent_count += 1
                    else:
                        failed_count += 1
                        logger.warning(
                            "Failed to send revenue alert",
                            recipient_id=recipient_id,
                            error=result.get("error")
                        )
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        "Error sending revenue alert",
                        recipient_id=recipient_id,
                        error=str(e)
                    )

            logger.info(
                "Revenue alert sent",
                store_id=store_id,
                sent_count=sent_count,
                failed_count=failed_count
            )

            return {
                "success": True,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "total_recipients": len(recipient_ids)
            }

        except Exception as e:
            logger.error(
                "Revenue alert sending failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def send_inventory_alert(
        self,
        store_id: str,
        store_name: str,
        alert_items: List[Dict[str, Any]],
        analysis: str,
        recipient_ids: List[str]
    ) -> Dict[str, Any]:
        """
        发送库存预警

        Args:
            store_id: 门店ID
            store_name: 门店名称
            alert_items: 预警项目列表 [{"dish_name": "宫保鸡丁", "quantity": 10, "risk": "high"}]
            analysis: AI分析结果
            recipient_ids: 接收人企微ID列表

        Returns:
            发送结果
        """
        try:
            # 按风险等级分组
            high_risk = [item for item in alert_items if item.get("risk") == "high"]
            medium_risk = [item for item in alert_items if item.get("risk") == "medium"]

            # 确定告警级别
            if high_risk:
                level = "紧急"
                emoji = "🔴"
            elif medium_risk:
                level = "警告"
                emoji = "🟡"
            else:
                level = "提示"
                emoji = "🟢"

            # 构建库存列表
            inventory_list = []
            if high_risk:
                inventory_list.append("🔴 高风险:")
                for item in high_risk:
                    inventory_list.append(
                        f"  • {item['dish_name']}: 剩余{item['quantity']}份"
                    )
            if medium_risk:
                inventory_list.append("🟡 中风险:")
                for item in medium_risk:
                    inventory_list.append(
                        f"  • {item['dish_name']}: 剩余{item['quantity']}份"
                    )

            # 构建告警消息
            message = f"""{emoji} 库存预警 [{level}]

门店: {store_name}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📦 库存状态:
{chr(10).join(inventory_list)}

🤖 AI分析:
{analysis}

💡 建议: 请及时补货，确保午高峰供应充足

---
智链OS智能预警 | 每天10AM自动检测
"""

            logger.info(
                "Sending inventory alert",
                store_id=store_id,
                alert_count=len(alert_items),
                recipient_count=len(recipient_ids)
            )

            # 发送给所有接收人
            sent_count = 0
            failed_count = 0

            for recipient_id in recipient_ids:
                try:
                    result = await self.message_service.send_text_message(
                        user_id=recipient_id,
                        content=message
                    )
                    if result.get("success"):
                        sent_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        "Error sending inventory alert",
                        recipient_id=recipient_id,
                        error=str(e)
                    )

            logger.info(
                "Inventory alert sent",
                store_id=store_id,
                sent_count=sent_count,
                failed_count=failed_count
            )

            return {
                "success": True,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "total_recipients": len(recipient_ids)
            }

        except Exception as e:
            logger.error(
                "Inventory alert sending failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def send_order_alert(
        self,
        store_id: str,
        store_name: str,
        anomaly_type: str,
        anomaly_data: Dict[str, Any],
        analysis: str,
        recipient_ids: List[str]
    ) -> Dict[str, Any]:
        """
        发送订单异常告警

        Args:
            store_id: 门店ID
            store_name: 门店名称
            anomaly_type: 异常类型 (refund_rate/complaint_rate/timeout_rate)
            anomaly_data: 异常数据 {"current": 15, "normal": 5, "threshold": 10}
            analysis: AI分析结果
            recipient_ids: 接收人企微ID列表

        Returns:
            发送结果
        """
        try:
            # 异常类型映射
            anomaly_names = {
                "refund_rate": "退单率",
                "complaint_rate": "投诉率",
                "timeout_rate": "超时率",
                "bad_review_rate": "差评率"
            }

            anomaly_name = anomaly_names.get(anomaly_type, anomaly_type)
            current = anomaly_data.get("current", 0)
            normal = anomaly_data.get("normal", 0)
            threshold = anomaly_data.get("threshold", 0)

            # 确定告警级别
            if current > threshold * 2:
                level = "严重"
                emoji = "🚨"
            elif current > threshold:
                level = "警告"
                emoji = "⚠️"
            else:
                level = "提示"
                emoji = "📊"

            # 构建告警消息
            message = f"""{emoji} 订单异常告警 [{level}]

门店: {store_name}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 异常指标:
• 异常类型: {anomaly_name}
• 当前值: {current}%
• 正常值: {normal}%
• 告警阈值: {threshold}%

🤖 AI分析:
{analysis}

💡 建议: 请立即关注并采取改进措施

---
智链OS实时监控 | 异常自动检测
"""

            logger.info(
                "Sending order alert",
                store_id=store_id,
                anomaly_type=anomaly_type,
                recipient_count=len(recipient_ids)
            )

            # 发送给所有接收人
            sent_count = 0
            failed_count = 0

            for recipient_id in recipient_ids:
                try:
                    result = await self.message_service.send_text_message(
                        user_id=recipient_id,
                        content=message
                    )
                    if result.get("success"):
                        sent_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        "Error sending order alert",
                        recipient_id=recipient_id,
                        error=str(e)
                    )

            logger.info(
                "Order alert sent",
                store_id=store_id,
                sent_count=sent_count,
                failed_count=failed_count
            )

            return {
                "success": True,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "total_recipients": len(recipient_ids)
            }

        except Exception as e:
            logger.error(
                "Order alert sending failed",
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def send_system_alert(
        self,
        alert_type: str,
        title: str,
        message: str,
        severity: str,
        recipient_ids: List[str]
    ) -> Dict[str, Any]:
        """
        发送系统告警

        Args:
            alert_type: 告警类型
            title: 告警标题
            message: 告警内容
            severity: 严重程度 (critical/error/warning/info)
            recipient_ids: 接收人企微ID列表

        Returns:
            发送结果
        """
        try:
            # 严重程度映射
            severity_emojis = {
                "critical": "🚨",
                "error": "❌",
                "warning": "⚠️",
                "info": "ℹ️"
            }

            emoji = severity_emojis.get(severity, "📢")

            # 构建告警消息
            full_message = f"""{emoji} {title}

{message}

时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
类型: {alert_type}
级别: {severity.upper()}

---
智链OS系统监控
"""

            logger.info(
                "Sending system alert",
                alert_type=alert_type,
                severity=severity,
                recipient_count=len(recipient_ids)
            )

            # 发送给所有接收人
            sent_count = 0
            failed_count = 0

            for recipient_id in recipient_ids:
                try:
                    result = await self.message_service.send_text_message(
                        user_id=recipient_id,
                        content=full_message
                    )
                    if result.get("success"):
                        sent_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        "Error sending system alert",
                        recipient_id=recipient_id,
                        error=str(e)
                    )

            logger.info(
                "System alert sent",
                alert_type=alert_type,
                sent_count=sent_count,
                failed_count=failed_count
            )

            return {
                "success": True,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "total_recipients": len(recipient_ids)
            }

        except Exception as e:
            logger.error(
                "System alert sending failed",
                alert_type=alert_type,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }


# 全局实例
wechat_alert_service = WeChatAlertService()
