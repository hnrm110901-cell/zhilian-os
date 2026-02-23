"""
边缘节点服务
支持边缘计算和弱网环境下的降级运行
确保门店在网络中断时仍能正常运营
"""
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import structlog
from enum import Enum
import json

logger = structlog.get_logger()


class OperationMode(str, Enum):
    """运行模式"""
    ONLINE = "online"  # 在线模式 (云端LLM)
    OFFLINE = "offline"  # 离线模式 (本地规则)
    HYBRID = "hybrid"  # 混合模式 (优先云端，降级本地)


class NetworkStatus(str, Enum):
    """网络状态"""
    CONNECTED = "connected"  # 已连接
    DISCONNECTED = "disconnected"  # 已断开
    UNSTABLE = "unstable"  # 不稳定


class EdgeNodeService:
    """边缘节点服务"""

    def __init__(self):
        self.mode = OperationMode.HYBRID
        self.network_status = NetworkStatus.CONNECTED
        self.local_cache = {}
        self.pending_sync_queue = []
        self.offline_rules = self._initialize_offline_rules()

    def _initialize_offline_rules(self) -> Dict[str, Any]:
        """初始化离线规则引擎"""
        return {
            "inventory_alert": {
                "low_stock_threshold": 0.2,  # 库存低于20%预警
                "critical_threshold": 0.1,  # 库存低于10%严重预警
                "auto_order_threshold": 0.15  # 库存低于15%自动下单
            },
            "revenue_anomaly": {
                "deviation_threshold": 0.3,  # 偏差超过30%预警
                "comparison_days": 7  # 对比最近7天平均值
            },
            "order_timeout": {
                "warning_minutes": 20,  # 20分钟预警
                "critical_minutes": 30  # 30分钟严重预警
            },
            "schedule": {
                "min_staff_ratio": 0.8,  # 最低人员配置比例
                "peak_hour_buffer": 1.2  # 高峰时段人员缓冲
            }
        }

    async def check_network_status(self) -> NetworkStatus:
        """
        检查网络状态

        Returns:
            NetworkStatus: 网络状态
        """
        try:
            # 实际实现应该ping云端服务器或检查网络连接
            # 这里简化为返回当前状态
            return self.network_status

        except Exception as e:
            logger.error("check_network_status_failed", error=str(e))
            return NetworkStatus.DISCONNECTED

    async def switch_mode(self, target_mode: OperationMode) -> Dict[str, Any]:
        """
        切换运行模式

        Args:
            target_mode: 目标模式

        Returns:
            Dict: 切换结果
        """
        try:
            old_mode = self.mode
            self.mode = target_mode

            logger.info(
                "mode_switched",
                old_mode=old_mode.value,
                new_mode=target_mode.value
            )

            return {
                "success": True,
                "old_mode": old_mode.value,
                "new_mode": target_mode.value,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error("switch_mode_failed", error=str(e))
            raise

    async def handle_network_change(self, new_status: NetworkStatus):
        """
        处理网络状态变化

        Args:
            new_status: 新的网络状态
        """
        try:
            old_status = self.network_status
            self.network_status = new_status

            # 根据网络状态自动切换模式
            if new_status == NetworkStatus.DISCONNECTED:
                await self.switch_mode(OperationMode.OFFLINE)
                logger.warning("network_disconnected_switching_to_offline")

            elif new_status == NetworkStatus.CONNECTED and old_status == NetworkStatus.DISCONNECTED:
                await self.switch_mode(OperationMode.HYBRID)
                logger.info("network_reconnected_switching_to_hybrid")
                # 同步离线期间的数据
                await self.sync_offline_data()

            elif new_status == NetworkStatus.UNSTABLE:
                await self.switch_mode(OperationMode.HYBRID)
                logger.warning("network_unstable_using_hybrid_mode")

        except Exception as e:
            logger.error("handle_network_change_failed", error=str(e))

    async def process_decision_offline(
        self,
        decision_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        离线模式下处理决策

        Args:
            decision_type: 决策类型
            context: 决策上下文

        Returns:
            Dict: 决策结果
        """
        try:
            rules = self.offline_rules.get(decision_type, {})

            if decision_type == "inventory_alert":
                return await self._offline_inventory_alert(context, rules)

            elif decision_type == "revenue_anomaly":
                return await self._offline_revenue_anomaly(context, rules)

            elif decision_type == "order_timeout":
                return await self._offline_order_timeout(context, rules)

            elif decision_type == "schedule":
                return await self._offline_schedule_check(context, rules)

            else:
                return {
                    "success": False,
                    "error": f"Unsupported decision type in offline mode: {decision_type}",
                    "mode": "offline"
                }

        except Exception as e:
            logger.error("process_decision_offline_failed", error=str(e))
            raise

    async def _offline_inventory_alert(
        self,
        context: Dict[str, Any],
        rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """离线模式库存预警"""
        current_stock = context.get("current_stock", 0)
        max_stock = context.get("max_stock", 100)
        stock_ratio = current_stock / max_stock if max_stock > 0 else 0

        if stock_ratio < rules["critical_threshold"]:
            alert_level = "critical"
            action = "immediate_order"
        elif stock_ratio < rules["auto_order_threshold"]:
            alert_level = "warning"
            action = "auto_order"
        elif stock_ratio < rules["low_stock_threshold"]:
            alert_level = "info"
            action = "monitor"
        else:
            alert_level = "normal"
            action = "none"

        return {
            "success": True,
            "mode": "offline",
            "decision_type": "inventory_alert",
            "alert_level": alert_level,
            "action": action,
            "stock_ratio": round(stock_ratio, 2),
            "recommendation": f"库存比例{stock_ratio*100:.1f}%，建议{action}"
        }

    async def _offline_revenue_anomaly(
        self,
        context: Dict[str, Any],
        rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """离线模式营收异常检测"""
        current_revenue = context.get("current_revenue", 0)
        average_revenue = context.get("average_revenue", 0)

        if average_revenue > 0:
            deviation = abs(current_revenue - average_revenue) / average_revenue
        else:
            deviation = 0

        if deviation > rules["deviation_threshold"]:
            alert_level = "critical"
            action = "investigate"
        elif deviation > rules["deviation_threshold"] * 0.7:
            alert_level = "warning"
            action = "monitor"
        else:
            alert_level = "normal"
            action = "none"

        return {
            "success": True,
            "mode": "offline",
            "decision_type": "revenue_anomaly",
            "alert_level": alert_level,
            "action": action,
            "deviation": round(deviation, 2),
            "recommendation": f"营收偏差{deviation*100:.1f}%，建议{action}"
        }

    async def _offline_order_timeout(
        self,
        context: Dict[str, Any],
        rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """离线模式订单超时检测"""
        wait_time = context.get("wait_time_minutes", 0)

        if wait_time > rules["critical_minutes"]:
            alert_level = "critical"
            action = "urgent_attention"
        elif wait_time > rules["warning_minutes"]:
            alert_level = "warning"
            action = "check_status"
        else:
            alert_level = "normal"
            action = "none"

        return {
            "success": True,
            "mode": "offline",
            "decision_type": "order_timeout",
            "alert_level": alert_level,
            "action": action,
            "wait_time": wait_time,
            "recommendation": f"等待时间{wait_time}分钟，建议{action}"
        }

    async def _offline_schedule_check(
        self,
        context: Dict[str, Any],
        rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """离线模式排班检查"""
        current_staff = context.get("current_staff", 0)
        required_staff = context.get("required_staff", 0)
        is_peak_hour = context.get("is_peak_hour", False)

        if required_staff > 0:
            staff_ratio = current_staff / required_staff
        else:
            staff_ratio = 1.0

        min_ratio = rules["min_staff_ratio"]
        if is_peak_hour:
            min_ratio *= rules["peak_hour_buffer"]

        if staff_ratio < min_ratio:
            alert_level = "critical"
            action = "call_backup"
        elif staff_ratio < min_ratio * float(os.getenv("EDGE_STAFF_WARNING_FACTOR", "1.1")):
            alert_level = "warning"
            action = "monitor"
        else:
            alert_level = "normal"
            action = "none"

        return {
            "success": True,
            "mode": "offline",
            "decision_type": "schedule",
            "alert_level": alert_level,
            "action": action,
            "staff_ratio": round(staff_ratio, 2),
            "recommendation": f"人员配置{staff_ratio*100:.1f}%，建议{action}"
        }

    async def cache_data(self, key: str, data: Any, ttl: int = int(os.getenv("EDGE_CACHE_TTL", "3600"))):
        """
        缓存数据到本地

        Args:
            key: 缓存键
            data: 数据
            ttl: 过期时间（秒）
        """
        try:
            self.local_cache[key] = {
                "data": data,
                "timestamp": datetime.utcnow(),
                "ttl": ttl
            }

            logger.debug("data_cached", key=key, ttl=ttl)

        except Exception as e:
            logger.error("cache_data_failed", error=str(e))

    async def get_cached_data(self, key: str) -> Optional[Any]:
        """
        从本地缓存获取数据

        Args:
            key: 缓存键

        Returns:
            Optional[Any]: 缓存的数据，如果不存在或过期则返回None
        """
        try:
            if key not in self.local_cache:
                return None

            cache_entry = self.local_cache[key]
            timestamp = cache_entry["timestamp"]
            ttl = cache_entry["ttl"]

            # 检查是否过期
            age = (datetime.utcnow() - timestamp).total_seconds()
            if age > ttl:
                del self.local_cache[key]
                return None

            return cache_entry["data"]

        except Exception as e:
            logger.error("get_cached_data_failed", error=str(e))
            return None

    async def queue_for_sync(self, operation: Dict[str, Any]):
        """
        将操作加入同步队列

        Args:
            operation: 操作数据
        """
        try:
            operation["queued_at"] = datetime.utcnow().isoformat()
            operation["sync_id"] = str(uuid.uuid4())
            self.pending_sync_queue.append(operation)

            logger.info(
                "operation_queued_for_sync",
                sync_id=operation["sync_id"],
                operation_type=operation.get("type")
            )

        except Exception as e:
            logger.error("queue_for_sync_failed", error=str(e))

    async def sync_offline_data(self) -> Dict[str, Any]:
        """
        同步离线期间的数据到云端

        Returns:
            Dict: 同步结果
        """
        try:
            if not self.pending_sync_queue:
                return {
                    "success": True,
                    "synced_count": 0,
                    "message": "No data to sync"
                }

            synced_count = 0
            failed_count = 0
            failed_operations = []

            for operation in self.pending_sync_queue[:]:
                try:
                    # 实际实现应该调用云端API同步数据
                    # 这里简化为标记为已同步
                    synced_count += 1
                    self.pending_sync_queue.remove(operation)

                    logger.info(
                        "operation_synced",
                        sync_id=operation["sync_id"],
                        operation_type=operation.get("type")
                    )

                except Exception as e:
                    failed_count += 1
                    failed_operations.append({
                        "sync_id": operation["sync_id"],
                        "error": str(e)
                    })
                    logger.error(
                        "operation_sync_failed",
                        sync_id=operation["sync_id"],
                        error=str(e)
                    )

            return {
                "success": True,
                "synced_count": synced_count,
                "failed_count": failed_count,
                "failed_operations": failed_operations,
                "remaining_queue_size": len(self.pending_sync_queue)
            }

        except Exception as e:
            logger.error("sync_offline_data_failed", error=str(e))
            raise

    async def get_status(self) -> Dict[str, Any]:
        """
        获取边缘节点状态

        Returns:
            Dict: 状态信息
        """
        return {
            "mode": self.mode.value,
            "network_status": self.network_status.value,
            "cache_size": len(self.local_cache),
            "pending_sync_count": len(self.pending_sync_queue),
            "offline_rules_loaded": len(self.offline_rules),
            "timestamp": datetime.utcnow().isoformat()
        }


# 全局实例
edge_node_service = EdgeNodeService()
