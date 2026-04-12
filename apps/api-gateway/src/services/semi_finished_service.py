"""
半成品管理服务
半成品配方、生产批次、订单消耗、库存跟踪
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class BatchStatus(str, Enum):
    PRODUCED = "produced"
    IN_STOCK = "in_stock"
    DEPLETED = "depleted"
    EXPIRED = "expired"
    SCRAPPED = "scrapped"


@dataclass
class SemiFinishedIngredient:
    """半成品配方原料"""
    ingredient_id: str = ""
    ingredient_name: str = ""
    qty: float = 0
    unit: str = ""
    cost_fen: int = 0  # 单位成本（分）


@dataclass
class SemiFinished:
    """半成品"""
    semi_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    # 配方（生产1个标准批次需要的原料）
    recipe: List[SemiFinishedIngredient] = field(default_factory=list)
    standard_batch_qty: float = 1.0  # 标准批次产量
    unit: str = ""  # 份/kg/盒
    shelf_life_hours: int = 24  # 保质期（小时）
    store_id: str = ""

    @property
    def unit_cost_fen(self) -> int:
        """单位成本（分）"""
        total = sum(int(i.cost_fen * i.qty) for i in self.recipe)
        if self.standard_batch_qty > 0:
            return int(total / self.standard_batch_qty)
        return total

    @property
    def unit_cost_yuan(self) -> float:
        return round(self.unit_cost_fen / 100, 2)


@dataclass
class ProductionBatch:
    """生产批次"""
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    semi_id: str = ""
    semi_name: str = ""
    produced_qty: float = 0
    remaining_qty: float = 0
    unit: str = ""
    cost_fen: int = 0  # 批次总成本（分）
    status: BatchStatus = BatchStatus.PRODUCED
    produced_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    operator: str = ""
    store_id: str = ""

    @property
    def cost_yuan(self) -> float:
        return round(self.cost_fen / 100, 2)


class SemiFinishedService:
    """半成品管理服务"""

    def __init__(self):
        self._recipes: Dict[str, SemiFinished] = {}
        self._batches: Dict[str, ProductionBatch] = {}

    def create_recipe(
        self,
        name: str,
        recipe: List[SemiFinishedIngredient],
        standard_batch_qty: float = 1.0,
        unit: str = "份",
        shelf_life_hours: int = 24,
        store_id: str = "",
    ) -> SemiFinished:
        """创建半成品配方"""
        if not recipe:
            raise ValueError("配方原料不能为空")
        semi = SemiFinished(
            name=name,
            recipe=recipe,
            standard_batch_qty=standard_batch_qty,
            unit=unit,
            shelf_life_hours=shelf_life_hours,
            store_id=store_id,
        )
        self._recipes[semi.semi_id] = semi
        logger.info("创建半成品配方", semi_id=semi.semi_id, name=name,
                     unit_cost_yuan=semi.unit_cost_yuan)
        return semi

    def produce_batch(
        self,
        semi_id: str,
        qty: float,
        operator: str = "",
        store_id: str = "",
    ) -> ProductionBatch:
        """
        生产一个批次
        根据配方计算成本
        """
        semi = self._get_recipe(semi_id)
        if qty <= 0:
            raise ValueError("生产数量必须大于0")

        # 按比例计算成本
        ratio = qty / semi.standard_batch_qty if semi.standard_batch_qty > 0 else 1
        batch_cost = sum(int(i.cost_fen * i.qty * ratio) for i in semi.recipe)

        batch = ProductionBatch(
            semi_id=semi_id,
            semi_name=semi.name,
            produced_qty=qty,
            remaining_qty=qty,
            unit=semi.unit,
            cost_fen=batch_cost,
            status=BatchStatus.IN_STOCK,
            operator=operator,
            store_id=store_id or semi.store_id,
        )
        self._batches[batch.batch_id] = batch
        logger.info("生产批次", batch_id=batch.batch_id, semi=semi.name,
                     qty=qty, cost_yuan=batch.cost_yuan)
        return batch

    def consume_in_order(
        self,
        semi_id: str,
        qty: float,
        order_id: str = "",
        store_id: str = "",
    ) -> Dict:
        """
        订单消耗半成品（FIFO：先进先出）
        返回消耗详情和成本
        """
        remaining = qty
        consumed_batches = []
        total_cost_fen = 0

        # 按生产时间排序（FIFO）
        available = sorted(
            [b for b in self._batches.values()
             if b.semi_id == semi_id and b.status == BatchStatus.IN_STOCK and b.remaining_qty > 0
             and (not store_id or b.store_id == store_id)],
            key=lambda b: b.produced_at,
        )

        for batch in available:
            if remaining <= 0:
                break
            take = min(remaining, batch.remaining_qty)
            # 按比例计算成本
            unit_cost = batch.cost_fen / batch.produced_qty if batch.produced_qty > 0 else 0
            cost = int(unit_cost * take)

            batch.remaining_qty -= take
            if batch.remaining_qty <= 0:
                batch.status = BatchStatus.DEPLETED

            consumed_batches.append({
                "batch_id": batch.batch_id,
                "qty": take,
                "cost_fen": cost,
                "cost_yuan": round(cost / 100, 2),
            })
            total_cost_fen += cost
            remaining -= take

        if remaining > 0:
            logger.warning("半成品库存不足", semi_id=semi_id, shortage=remaining)

        return {
            "semi_id": semi_id,
            "requested_qty": qty,
            "consumed_qty": qty - remaining,
            "shortage_qty": remaining,
            "total_cost_fen": total_cost_fen,
            "total_cost_yuan": round(total_cost_fen / 100, 2),
            "batches": consumed_batches,
            "order_id": order_id,
        }

    def get_inventory(self, store_id: str = "", semi_id: Optional[str] = None) -> List[Dict]:
        """获取半成品库存"""
        batches = [
            b for b in self._batches.values()
            if b.status == BatchStatus.IN_STOCK and b.remaining_qty > 0
        ]
        if store_id:
            batches = [b for b in batches if b.store_id == store_id]
        if semi_id:
            batches = [b for b in batches if b.semi_id == semi_id]

        # 按半成品汇总
        summary: Dict[str, Dict] = {}
        for b in batches:
            if b.semi_id not in summary:
                summary[b.semi_id] = {
                    "semi_id": b.semi_id,
                    "name": b.semi_name,
                    "total_qty": 0,
                    "unit": b.unit,
                    "batch_count": 0,
                    "total_cost_fen": 0,
                }
            summary[b.semi_id]["total_qty"] += b.remaining_qty
            summary[b.semi_id]["batch_count"] += 1
            # 按剩余比例分摊成本
            ratio = b.remaining_qty / b.produced_qty if b.produced_qty > 0 else 0
            summary[b.semi_id]["total_cost_fen"] += int(b.cost_fen * ratio)

        result = list(summary.values())
        for item in result:
            item["total_cost_yuan"] = round(item["total_cost_fen"] / 100, 2)
        return result

    def _get_recipe(self, semi_id: str) -> SemiFinished:
        if semi_id not in self._recipes:
            raise ValueError(f"半成品配方不存在: {semi_id}")
        return self._recipes[semi_id]
