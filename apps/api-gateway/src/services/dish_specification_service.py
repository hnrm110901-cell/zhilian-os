"""
菜品规格服务 — 管理同一菜品的多规格多单位定价

核心能力：
  - 获取菜品所有规格
  - 获取指定规格价格
  - 计算 BOM 扣减量（规格系数 × 基础 BOM 用量 × 数量）
  - CRUD + 可用性切换
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, update

from src.models.bom import BOMItem, BOMTemplate
from src.models.dish import Dish
from src.models.dish_specification import DishSpecification
from src.services.base_service import BaseService

logger = structlog.get_logger()


class DishSpecificationService(BaseService):
    """菜品规格服务"""

    async def get_specs_for_dish(self, dish_id: UUID) -> List[DishSpecification]:
        """
        获取菜品所有可用规格（按 display_order 排序）

        Args:
            dish_id: 菜品ID

        Returns:
            规格列表
        """
        async with self.get_session() as session:
            stmt = (
                select(DishSpecification)
                .where(
                    DishSpecification.dish_id == dish_id,
                    DishSpecification.is_available.is_(True),
                )
                .order_by(DishSpecification.display_order)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_all_specs_for_dish(self, dish_id: UUID) -> List[DishSpecification]:
        """
        获取菜品所有规格（含不可用的，管理后台用）

        Args:
            dish_id: 菜品ID

        Returns:
            规格列表
        """
        async with self.get_session() as session:
            stmt = (
                select(DishSpecification)
                .where(DishSpecification.dish_id == dish_id)
                .order_by(DishSpecification.display_order)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_price(self, dish_id: UUID, spec_id: UUID) -> Dict[str, Any]:
        """
        获取指定规格价格

        Args:
            dish_id: 菜品ID
            spec_id: 规格ID

        Returns:
            {
                "spec_name": str,
                "price_fen": int,
                "price_yuan": float,  # ¥金额
                "cost_fen": int | None,
                "cost_yuan": float | None,  # ¥金额
                "profit_margin": float | None,
                "unit": str,
                "min_order_qty": int,
            }
        """
        async with self.get_session() as session:
            stmt = select(DishSpecification).where(
                DishSpecification.id == spec_id,
                DishSpecification.dish_id == dish_id,
            )
            result = await session.execute(stmt)
            spec = result.scalar_one_or_none()
            if spec is None:
                raise ValueError(
                    f"规格 {spec_id} 不存在于菜品 {dish_id}"
                )

            return {
                "spec_name": spec.spec_name,
                "price_fen": spec.price_fen,
                "price_yuan": spec.price_yuan,
                "cost_fen": spec.cost_fen,
                "cost_yuan": spec.cost_yuan,
                "profit_margin": spec.profit_margin,
                "unit": spec.unit,
                "min_order_qty": spec.min_order_qty,
            }

    async def calculate_bom_deduction(
        self, dish_id: UUID, spec_id: UUID, quantity: int
    ) -> Dict[str, Any]:
        """
        计算 BOM 扣减量

        扣减公式：每种食材扣减量 = BOM标准用量 × 规格系数 × 点单数量

        Args:
            dish_id: 菜品ID
            spec_id: 规格ID
            quantity: 点单数量

        Returns:
            {
                "spec_name": str,
                "bom_multiplier": float,
                "quantity": int,
                "deductions": [
                    {
                        "ingredient_id": str,
                        "standard_qty": float,
                        "deduction_qty": float,  # 实际扣减量
                        "unit": str,
                    }
                ],
                "total_cost_fen": int,
                "total_cost_yuan": float,  # ¥金额
            }
        """
        if quantity < 1:
            raise ValueError("点单数量必须 >= 1")

        async with self.get_session() as session:
            # 获取规格
            spec_stmt = select(DishSpecification).where(
                DishSpecification.id == spec_id,
                DishSpecification.dish_id == dish_id,
            )
            spec_result = await session.execute(spec_stmt)
            spec = spec_result.scalar_one_or_none()
            if spec is None:
                raise ValueError(f"规格 {spec_id} 不存在于菜品 {dish_id}")

            if quantity < spec.min_order_qty:
                raise ValueError(
                    f"规格 '{spec.spec_name}' 最小点单量为 {spec.min_order_qty}"
                )

            # 查找当前生效的 BOM
            bom_stmt = (
                select(BOMTemplate)
                .where(
                    BOMTemplate.dish_id == dish_id,
                    BOMTemplate.is_active.is_(True),
                )
                .limit(1)
            )
            bom_result = await session.execute(bom_stmt)
            bom = bom_result.scalar_one_or_none()

            deductions = []
            total_cost_fen = 0

            if bom:
                # 获取 BOM 明细
                items_stmt = select(BOMItem).where(BOMItem.bom_id == bom.id)
                items_result = await session.execute(items_stmt)
                bom_items = items_result.scalars().all()

                multiplier = float(spec.bom_multiplier)

                for item in bom_items:
                    std_qty = float(item.standard_qty)
                    deduction_qty = round(std_qty * multiplier * quantity, 4)
                    unit_cost = item.unit_cost or 0
                    item_cost = int(deduction_qty * unit_cost)
                    total_cost_fen += item_cost

                    deductions.append({
                        "ingredient_id": item.ingredient_id,
                        "standard_qty": std_qty,
                        "deduction_qty": deduction_qty,
                        "unit": item.unit,
                        "unit_cost_fen": unit_cost,
                        "item_cost_fen": item_cost,
                    })

            return {
                "spec_name": spec.spec_name,
                "bom_multiplier": float(spec.bom_multiplier),
                "quantity": quantity,
                "deductions": deductions,
                "total_cost_fen": total_cost_fen,
                "total_cost_yuan": round(total_cost_fen / 100, 2),
            }

    async def create_spec(
        self, dish_id: UUID, data: Dict[str, Any]
    ) -> DishSpecification:
        """
        创建规格

        Args:
            dish_id: 菜品ID
            data: 规格数据

        Returns:
            创建的规格
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
                    update(DishSpecification)
                    .where(
                        DishSpecification.dish_id == dish_id,
                        DishSpecification.is_default.is_(True),
                    )
                    .values(is_default=False)
                )

            spec = DishSpecification(dish_id=dish_id, **data)
            session.add(spec)
            await session.flush()

            logger.info(
                "菜品规格已创建",
                store_id=store_id,
                dish_id=str(dish_id),
                spec_name=spec.spec_name,
                price_fen=spec.price_fen,
            )
            return spec

    async def update_spec(
        self, spec_id: UUID, data: Dict[str, Any]
    ) -> Optional[DishSpecification]:
        """
        更新规格

        Args:
            spec_id: 规格ID
            data: 更新数据

        Returns:
            更新后的规格
        """
        async with self.get_session() as session:
            stmt = select(DishSpecification).where(DishSpecification.id == spec_id)
            result = await session.execute(stmt)
            spec = result.scalar_one_or_none()
            if spec is None:
                return None

            # 如果设为默认，先取消其他默认
            if data.get("is_default", False) and not spec.is_default:
                await session.execute(
                    update(DishSpecification)
                    .where(
                        DishSpecification.dish_id == spec.dish_id,
                        DishSpecification.is_default.is_(True),
                    )
                    .values(is_default=False)
                )

            for key, value in data.items():
                if hasattr(spec, key):
                    setattr(spec, key, value)

            await session.flush()

            logger.info(
                "菜品规格已更新",
                spec_id=str(spec_id),
                spec_name=spec.spec_name,
            )
            return spec

    async def toggle_availability(
        self, spec_id: UUID, is_available: bool
    ) -> Optional[DishSpecification]:
        """
        切换规格可用性

        Args:
            spec_id: 规格ID
            is_available: 是否可用

        Returns:
            更新后的规格
        """
        return await self.update_spec(spec_id, {"is_available": is_available})
