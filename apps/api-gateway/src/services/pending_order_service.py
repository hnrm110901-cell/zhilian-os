"""
挂单服务
支持收银员暂挂订单（如顾客去拿东西/找零），后续恢复继续结账
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 默认挂单过期时间（分钟）
DEFAULT_EXPIRE_MINUTES = 120


class PendingStatus(str, Enum):
    PENDING = "pending"
    RESUMED = "resumed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class PendingOrder:
    """挂单记录"""
    pending_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    register_id: str = ""  # 收银台
    cashier_id: str = ""
    # 订单快照
    items: List[Dict] = field(default_factory=list)  # [{"dish_id", "name", "qty", "price_fen"}]
    total_fen: int = 0
    customer_note: str = ""
    # 状态
    status: PendingStatus = PendingStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expire_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None

    @property
    def total_yuan(self) -> float:
        return round(self.total_fen / 100, 2)


class PendingOrderService:
    """挂单服务"""

    def __init__(self, expire_minutes: int = DEFAULT_EXPIRE_MINUTES):
        self._orders: Dict[str, PendingOrder] = {}
        self._expire_minutes = expire_minutes

    def park_order(
        self,
        store_id: str,
        register_id: str,
        cashier_id: str,
        items: List[Dict],
        customer_note: str = "",
    ) -> PendingOrder:
        """
        挂单：暂存当前订单
        自动计算总额，设置过期时间
        """
        total_fen = sum(item.get("price_fen", 0) * item.get("qty", 1) for item in items)
        order = PendingOrder(
            store_id=store_id,
            register_id=register_id,
            cashier_id=cashier_id,
            items=items,
            total_fen=total_fen,
            customer_note=customer_note,
            expire_at=datetime.now(timezone.utc) + timedelta(minutes=self._expire_minutes),
        )
        self._orders[order.pending_id] = order
        logger.info("订单已挂起", pending_id=order.pending_id, total_yuan=order.total_yuan,
                     items_count=len(items))
        return order

    def resume_order(self, pending_id: str) -> PendingOrder:
        """恢复挂单，继续结账"""
        order = self._get_order(pending_id)
        if order.status != PendingStatus.PENDING:
            raise ValueError(f"挂单状态不允许恢复: {order.status.value}")
        # 检查是否已过期
        if order.expire_at and datetime.now(timezone.utc) > order.expire_at:
            order.status = PendingStatus.EXPIRED
            raise ValueError("挂单已过期")
        order.status = PendingStatus.RESUMED
        order.resumed_at = datetime.now(timezone.utc)
        logger.info("挂单已恢复", pending_id=pending_id)
        return order

    def list_pending(self, store_id: str, register_id: Optional[str] = None) -> List[PendingOrder]:
        """列出门店（或指定收银台）的待处理挂单"""
        self._auto_expire()
        result = []
        for order in self._orders.values():
            if order.store_id != store_id:
                continue
            if register_id and order.register_id != register_id:
                continue
            if order.status == PendingStatus.PENDING:
                result.append(order)
        # 按创建时间排序
        result.sort(key=lambda x: x.created_at)
        return result

    def auto_expire(self) -> List[str]:
        """手动触发过期检查，返回过期的挂单ID列表"""
        return self._auto_expire()

    def cancel(self, pending_id: str, reason: str = "") -> PendingOrder:
        """取消挂单"""
        order = self._get_order(pending_id)
        if order.status != PendingStatus.PENDING:
            raise ValueError(f"挂单状态不允许取消: {order.status.value}")
        order.status = PendingStatus.CANCELLED
        logger.info("挂单已取消", pending_id=pending_id, reason=reason)
        return order

    def _auto_expire(self) -> List[str]:
        """检查并标记过期挂单"""
        now = datetime.now(timezone.utc)
        expired_ids = []
        for order in self._orders.values():
            if order.status == PendingStatus.PENDING and order.expire_at and now > order.expire_at:
                order.status = PendingStatus.EXPIRED
                expired_ids.append(order.pending_id)
        if expired_ids:
            logger.info("挂单自动过期", count=len(expired_ids))
        return expired_ids

    def _get_order(self, pending_id: str) -> PendingOrder:
        if pending_id not in self._orders:
            raise ValueError(f"挂单不存在: {pending_id}")
        return self._orders[pending_id]
