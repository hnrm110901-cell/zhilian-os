"""
中央厨房服务
生产计划、排产、配送单生成、配送追踪
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class PlanStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    IN_PRODUCTION = "in_production"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    REJECTED = "rejected"


@dataclass
class ProductionItem:
    """生产明细"""
    item_id: str = ""
    item_name: str = ""
    qty: float = 0
    unit: str = ""
    cost_fen: int = 0  # 单位成本（分）

    @property
    def total_cost_fen(self) -> int:
        return int(self.cost_fen * self.qty)

    @property
    def cost_yuan(self) -> float:
        return round(self.cost_fen / 100, 2)


@dataclass
class ProductionPlan:
    """生产计划"""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plan_date: date = field(default_factory=date.today)
    status: PlanStatus = PlanStatus.DRAFT
    items: List[ProductionItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""

    @property
    def total_cost_fen(self) -> int:
        return sum(item.total_cost_fen for item in self.items)

    @property
    def total_cost_yuan(self) -> float:
        return round(self.total_cost_fen / 100, 2)


@dataclass
class DistributionOrder:
    """配送单"""
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = ""
    store_id: str = ""          # 目标门店
    store_name: str = ""
    items: List[Dict] = field(default_factory=list)  # [{"item_name", "qty", "unit"}]
    status: DeliveryStatus = DeliveryStatus.PENDING
    scheduled_date: Optional[date] = None
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    driver: str = ""
    note: str = ""


class CentralKitchenService:
    """中央厨房服务"""

    def __init__(self):
        self._plans: Dict[str, ProductionPlan] = {}
        self._distributions: Dict[str, DistributionOrder] = {}

    def create_plan(
        self,
        plan_date: date,
        items: List[ProductionItem],
        note: str = "",
    ) -> ProductionPlan:
        """创建生产计划"""
        if not items:
            raise ValueError("生产计划不能为空")
        plan = ProductionPlan(
            plan_date=plan_date,
            items=items,
            note=note,
        )
        self._plans[plan.plan_id] = plan
        logger.info("创建生产计划", plan_id=plan.plan_id, date=str(plan_date),
                     items=len(items), cost_yuan=plan.total_cost_yuan)
        return plan

    def schedule_production(self, plan_id: str) -> ProductionPlan:
        """确认排产"""
        plan = self._get_plan(plan_id)
        if plan.status != PlanStatus.DRAFT:
            raise ValueError(f"计划状态不允许排产: {plan.status.value}")
        plan.status = PlanStatus.CONFIRMED
        logger.info("排产确认", plan_id=plan_id)
        return plan

    def start_production(self, plan_id: str) -> ProductionPlan:
        """开始生产"""
        plan = self._get_plan(plan_id)
        if plan.status != PlanStatus.CONFIRMED:
            raise ValueError("计划未确认")
        plan.status = PlanStatus.IN_PRODUCTION
        return plan

    def complete_production(self, plan_id: str) -> ProductionPlan:
        """完成生产"""
        plan = self._get_plan(plan_id)
        if plan.status != PlanStatus.IN_PRODUCTION:
            raise ValueError("计划未在生产中")
        plan.status = PlanStatus.COMPLETED
        logger.info("生产完成", plan_id=plan_id)
        return plan

    def create_distribution(
        self,
        plan_id: str,
        store_id: str,
        store_name: str,
        items: List[Dict],
        scheduled_date: Optional[date] = None,
    ) -> DistributionOrder:
        """创建配送单"""
        plan = self._get_plan(plan_id)
        order = DistributionOrder(
            plan_id=plan_id,
            store_id=store_id,
            store_name=store_name,
            items=items,
            scheduled_date=scheduled_date or date.today(),
        )
        self._distributions[order.order_id] = order
        logger.info("创建配送单", order_id=order.order_id, store=store_name)
        return order

    def dispatch(self, order_id: str, driver: str = "") -> DistributionOrder:
        """发车"""
        order = self._get_distribution(order_id)
        if order.status != DeliveryStatus.PENDING:
            raise ValueError("配送单状态不允许发车")
        order.status = DeliveryStatus.DISPATCHED
        order.dispatched_at = datetime.now(timezone.utc)
        order.driver = driver
        return order

    def track_delivery(self, order_id: str) -> Dict:
        """追踪配送状态"""
        order = self._get_distribution(order_id)
        return {
            "order_id": order_id,
            "store_name": order.store_name,
            "status": order.status.value,
            "scheduled_date": order.scheduled_date.isoformat() if order.scheduled_date else "",
            "dispatched_at": order.dispatched_at.isoformat() if order.dispatched_at else "",
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else "",
            "driver": order.driver,
            "items_count": len(order.items),
        }

    def confirm_delivery(self, order_id: str) -> DistributionOrder:
        """确认收货"""
        order = self._get_distribution(order_id)
        if order.status not in (DeliveryStatus.DISPATCHED, DeliveryStatus.IN_TRANSIT):
            raise ValueError("配送单未发出")
        order.status = DeliveryStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
        logger.info("确认收货", order_id=order_id, store=order.store_name)
        return order

    def _get_plan(self, plan_id: str) -> ProductionPlan:
        if plan_id not in self._plans:
            raise ValueError(f"生产计划不存在: {plan_id}")
        return self._plans[plan_id]

    def _get_distribution(self, order_id: str) -> DistributionOrder:
        if order_id not in self._distributions:
            raise ValueError(f"配送单不存在: {order_id}")
        return self._distributions[order_id]
