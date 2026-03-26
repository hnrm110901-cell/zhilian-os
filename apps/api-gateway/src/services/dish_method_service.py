"""
菜品做法变体服务 — 管理同一菜品的不同做法（清蒸/红烧/刺身等）

核心能力：
  - 获取菜品所有可选做法
  - 计算含做法的总成本（菜品基础成本 + 做法附加费）
  - 路由到对应 KDS 工位
  - CRUD 操作
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, update

from src.models.bom import BOMTemplate
from src.models.dish import Dish
from src.models.dish_method_variant import DishMethodVariant
from src.services.base_service import BaseService

logger = structlog.get_logger()


class DishMethodService(BaseService):
    """菜品做法变体服务"""

    async def get_methods_for_dish(self, dish_id: UUID) -> List[DishMethodVariant]:
        """
        获取菜品所有可选做法（按 display_order 排序）

        Args:
            dish_id: 菜品ID

        Returns:
            做法变体列表
        """
        async with self.get_session() as session:
            stmt = (
                select(DishMethodVariant)
                .where(
                    DishMethodVariant.dish_id == dish_id,
                    DishMethodVariant.is_available.is_(True),
                )
                .order_by(DishMethodVariant.display_order)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_all_methods_for_dish(self, dish_id: UUID) -> List[DishMethodVariant]:
        """
        获取菜品所有做法（含不可用的，管理后台用）

        Args:
            dish_id: 菜品ID

        Returns:
            做法变体列表
        """
        async with self.get_session() as session:
            stmt = (
                select(DishMethodVariant)
                .where(DishMethodVariant.dish_id == dish_id)
                .order_by(DishMethodVariant.display_order)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_default_method(self, dish_id: UUID) -> Optional[DishMethodVariant]:
        """
        获取菜品默认做法

        Args:
            dish_id: 菜品ID

        Returns:
            默认做法变体，无则返回 None
        """
        async with self.get_session() as session:
            stmt = select(DishMethodVariant).where(
                DishMethodVariant.dish_id == dish_id,
                DishMethodVariant.is_default.is_(True),
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_method_by_name(
        self, dish_id: UUID, method_name: str
    ) -> Optional[DishMethodVariant]:
        """
        按名称获取做法

        Args:
            dish_id: 菜品ID
            method_name: 做法名称

        Returns:
            做法变体
        """
        async with self.get_session() as session:
            stmt = select(DishMethodVariant).where(
                DishMethodVariant.dish_id == dish_id,
                DishMethodVariant.method_name == method_name,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def calculate_cost_with_method(
        self, dish_id: UUID, method_name: str
    ) -> Dict[str, Any]:
        """
        计算含做法的总成本

        Args:
            dish_id: 菜品ID
            method_name: 做法名称

        Returns:
            {
                "base_cost_fen": int,       # 菜品基础成本（分）
                "extra_cost_fen": int,      # 做法附加费（分）
                "bom_cost_fen": int | None, # BOM 食材成本（分）
                "total_cost_fen": int,      # 总成本（分）
                "total_cost_yuan": float,   # 总成本（元，¥）
                "method_name": str,
                "kitchen_station": str,
                "prep_time_minutes": int,
            }
        """
        async with self.get_session() as session:
            # 获取做法变体
            stmt = select(DishMethodVariant).where(
                DishMethodVariant.dish_id == dish_id,
                DishMethodVariant.method_name == method_name,
            )
            result = await session.execute(stmt)
            method = result.scalar_one_or_none()
            if method is None:
                raise ValueError(
                    f"做法 '{method_name}' 不存在于菜品 {dish_id}"
                )

            # 获取菜品基础成本
            dish_stmt = select(Dish).where(Dish.id == dish_id)
            dish_result = await session.execute(dish_stmt)
            dish = dish_result.scalar_one_or_none()
            if dish is None:
                raise ValueError(f"菜品 {dish_id} 不存在")

            # 基础成本（Dish.cost 存的是 Numeric 元，转为分）
            base_cost_fen = int((dish.cost or Decimal("0")) * 100)

            # BOM 成本（如果关联了 BOM 模板）
            bom_cost_fen = None
            if method.bom_template_id:
                bom_stmt = select(BOMTemplate).where(
                    BOMTemplate.id == method.bom_template_id
                )
                bom_result = await session.execute(bom_stmt)
                bom = bom_result.scalar_one_or_none()
                if bom:
                    bom_cost_fen = int(bom.total_cost)

            # 总成本 = 基础成本 + 做法附加费
            # 如果有 BOM 成本，以 BOM 成本替代基础成本
            effective_base = bom_cost_fen if bom_cost_fen is not None else base_cost_fen
            total_cost_fen = effective_base + method.extra_cost_fen

            return {
                "base_cost_fen": base_cost_fen,
                "extra_cost_fen": method.extra_cost_fen,
                "bom_cost_fen": bom_cost_fen,
                "total_cost_fen": total_cost_fen,
                "total_cost_yuan": round(total_cost_fen / 100, 2),
                "method_name": method.method_name,
                "kitchen_station": method.kitchen_station,
                "prep_time_minutes": method.prep_time_minutes,
            }

    async def route_to_kitchen_station(
        self, dish_id: UUID, method_name: str
    ) -> Dict[str, Any]:
        """
        返回做法对应的 KDS 工位信息

        Args:
            dish_id: 菜品ID
            method_name: 做法名称

        Returns:
            {"kitchen_station": str, "prep_time_minutes": int, "method_name": str}
        """
        method = await self.get_method_by_name(dish_id, method_name)
        if method is None:
            raise ValueError(
                f"做法 '{method_name}' 不存在于菜品 {dish_id}"
            )
        return {
            "kitchen_station": method.kitchen_station,
            "prep_time_minutes": method.prep_time_minutes,
            "method_name": method.method_name,
        }

    async def create_method_variant(
        self, dish_id: UUID, data: Dict[str, Any]
    ) -> DishMethodVariant:
        """
        创建做法变体

        Args:
            dish_id: 菜品ID
            data: 做法数据

        Returns:
            创建的做法变体
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            # 验证菜品存在
            dish_stmt = select(Dish).where(Dish.id == dish_id)
            dish_result = await session.execute(dish_stmt)
            dish = dish_result.scalar_one_or_none()
            if dish is None:
                raise ValueError(f"菜品 {dish_id} 不存在")

            # 如果设为默认，先取消其他默认
            if data.get("is_default", False):
                await session.execute(
                    update(DishMethodVariant)
                    .where(
                        DishMethodVariant.dish_id == dish_id,
                        DishMethodVariant.is_default.is_(True),
                    )
                    .values(is_default=False)
                )

            variant = DishMethodVariant(dish_id=dish_id, **data)
            session.add(variant)
            await session.flush()

            logger.info(
                "菜品做法变体已创建",
                store_id=store_id,
                dish_id=str(dish_id),
                method_name=variant.method_name,
                kitchen_station=variant.kitchen_station,
            )
            return variant

    async def update_method_variant(
        self, variant_id: UUID, data: Dict[str, Any]
    ) -> Optional[DishMethodVariant]:
        """
        更新做法变体

        Args:
            variant_id: 做法变体ID
            data: 更新数据

        Returns:
            更新后的做法变体
        """
        async with self.get_session() as session:
            stmt = select(DishMethodVariant).where(DishMethodVariant.id == variant_id)
            result = await session.execute(stmt)
            variant = result.scalar_one_or_none()
            if variant is None:
                return None

            # 如果设为默认，先取消其他默认
            if data.get("is_default", False) and not variant.is_default:
                await session.execute(
                    update(DishMethodVariant)
                    .where(
                        DishMethodVariant.dish_id == variant.dish_id,
                        DishMethodVariant.is_default.is_(True),
                    )
                    .values(is_default=False)
                )

            for key, value in data.items():
                if hasattr(variant, key):
                    setattr(variant, key, value)

            await session.flush()

            logger.info(
                "菜品做法变体已更新",
                variant_id=str(variant_id),
                method_name=variant.method_name,
            )
            return variant
