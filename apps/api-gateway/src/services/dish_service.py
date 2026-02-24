"""
菜品服务
管理菜品主档的业务逻辑
"""
import os
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import joinedload
import structlog

from src.models.dish import Dish, DishCategory, DishIngredient
from src.models.inventory import InventoryItem
from src.services.base_service import BaseService
from src.core.database import get_db_session

logger = structlog.get_logger()


class DishService(BaseService):
    """菜品服务"""

    async def create_dish(self, dish_data: Dict[str, Any]) -> Dish:
        """
        创建菜品

        Args:
            dish_data: 菜品数据

        Returns:
            创建的菜品对象
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            # 创建菜品
            dish = Dish(
                store_id=store_id,
                **dish_data
            )

            # 计算毛利率
            if dish.price and dish.cost:
                dish.calculate_profit_margin()

            session.add(dish)
            await session.flush()

            logger.info(
                "Dish created",
                store_id=store_id,
                dish_id=str(dish.id),
                dish_name=dish.name,
            )

            return dish

    async def get_dish(self, dish_id: str) -> Optional[Dish]:
        """
        获取菜品详情

        Args:
            dish_id: 菜品ID

        Returns:
            菜品对象
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            stmt = (
                select(Dish)
                .options(
                    joinedload(Dish.category),
                    joinedload(Dish.ingredients).joinedload(DishIngredient.ingredient)
                )
                .where(
                    and_(
                        Dish.id == dish_id,
                        Dish.store_id == store_id
                    )
                )
            )

            result = await session.execute(stmt)
            dish = result.scalar_one_or_none()

            return dish

    async def list_dishes(
        self,
        category_id: Optional[str] = None,
        is_available: Optional[bool] = None,
        is_recommended: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dish]:
        """
        获取菜品列表

        Args:
            category_id: 分类ID
            is_available: 是否可售
            is_recommended: 是否推荐
            search: 搜索关键词
            limit: 限制数量
            offset: 偏移量

        Returns:
            菜品列表
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            stmt = (
                select(Dish)
                .options(joinedload(Dish.category))
                .where(Dish.store_id == store_id)
            )

            # 应用过滤条件
            if category_id:
                stmt = stmt.where(Dish.category_id == category_id)

            if is_available is not None:
                stmt = stmt.where(Dish.is_available == is_available)

            if is_recommended is not None:
                stmt = stmt.where(Dish.is_recommended == is_recommended)

            if search:
                stmt = stmt.where(
                    or_(
                        Dish.name.ilike(f"%{search}%"),
                        Dish.code.ilike(f"%{search}%"),
                        Dish.description.ilike(f"%{search}%"),
                    )
                )

            # 排序
            stmt = stmt.order_by(Dish.sort_order, Dish.name)

            # 分页
            stmt = stmt.limit(limit).offset(offset)

            result = await session.execute(stmt)
            dishes = result.scalars().all()

            logger.info(
                "Dishes listed",
                store_id=store_id,
                count=len(dishes),
                category_id=category_id,
            )

            return list(dishes)

    async def update_dish(self, dish_id: str, dish_data: Dict[str, Any]) -> Optional[Dish]:
        """
        更新菜品

        Args:
            dish_id: 菜品ID
            dish_data: 更新数据

        Returns:
            更新后的菜品对象
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            stmt = select(Dish).where(
                and_(
                    Dish.id == dish_id,
                    Dish.store_id == store_id
                )
            )

            result = await session.execute(stmt)
            dish = result.scalar_one_or_none()

            if not dish:
                return None

            # 更新字段
            for key, value in dish_data.items():
                if hasattr(dish, key):
                    setattr(dish, key, value)

            # 重新计算毛利率
            if "price" in dish_data or "cost" in dish_data:
                dish.calculate_profit_margin()

            await session.flush()

            logger.info(
                "Dish updated",
                store_id=store_id,
                dish_id=str(dish.id),
                dish_name=dish.name,
            )

            return dish

    async def delete_dish(self, dish_id: str) -> bool:
        """
        删除菜品

        Args:
            dish_id: 菜品ID

        Returns:
            是否删除成功
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            stmt = select(Dish).where(
                and_(
                    Dish.id == dish_id,
                    Dish.store_id == store_id
                )
            )

            result = await session.execute(stmt)
            dish = result.scalar_one_or_none()

            if not dish:
                return False

            await session.delete(dish)
            await session.flush()

            logger.info(
                "Dish deleted",
                store_id=store_id,
                dish_id=str(dish.id),
                dish_name=dish.name,
            )

            return True

    async def add_ingredient(
        self,
        dish_id: str,
        ingredient_id: str,
        quantity: float,
        unit: str,
        **kwargs
    ) -> DishIngredient:
        """
        为菜品添加食材

        Args:
            dish_id: 菜品ID
            ingredient_id: 食材ID
            quantity: 用量
            unit: 单位
            **kwargs: 其他参数

        Returns:
            菜品食材关联对象
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            # 验证菜品存在
            dish_stmt = select(Dish).where(
                and_(
                    Dish.id == dish_id,
                    Dish.store_id == store_id
                )
            )
            dish_result = await session.execute(dish_stmt)
            dish = dish_result.scalar_one_or_none()

            if not dish:
                raise ValueError(f"Dish {dish_id} not found")

            # 验证食材存在
            ingredient_stmt = select(InventoryItem).where(
                and_(
                    InventoryItem.id == ingredient_id,
                    InventoryItem.store_id == store_id
                )
            )
            ingredient_result = await session.execute(ingredient_stmt)
            ingredient = ingredient_result.scalar_one_or_none()

            if not ingredient:
                raise ValueError(f"Ingredient {ingredient_id} not found")

            # 创建关联
            dish_ingredient = DishIngredient(
                store_id=store_id,
                dish_id=dish_id,
                ingredient_id=ingredient_id,
                quantity=quantity,
                unit=unit,
                **kwargs
            )

            session.add(dish_ingredient)
            await session.flush()

            logger.info(
                "Ingredient added to dish",
                store_id=store_id,
                dish_id=str(dish_id),
                ingredient_id=str(ingredient_id),
            )

            return dish_ingredient

    async def get_dish_cost_breakdown(self, dish_id: str) -> Dict[str, Any]:
        """
        获取菜品成本分解

        Args:
            dish_id: 菜品ID

        Returns:
            成本分解信息
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            # 获取菜品及其食材
            stmt = (
                select(Dish)
                .options(
                    joinedload(Dish.ingredients).joinedload(DishIngredient.ingredient)
                )
                .where(
                    and_(
                        Dish.id == dish_id,
                        Dish.store_id == store_id
                    )
                )
            )

            result = await session.execute(stmt)
            dish = result.scalar_one_or_none()

            if not dish:
                return {}

            # 计算食材成本
            ingredients_cost = []
            total_ingredient_cost = 0

            for dish_ingredient in dish.ingredients:
                ingredient = dish_ingredient.ingredient
                cost = (
                    Decimal(str(dish_ingredient.quantity)) *
                    Decimal(str(ingredient.unit_price or 0))
                )
                total_ingredient_cost += cost

                ingredients_cost.append({
                    "ingredient_name": ingredient.name,
                    "quantity": float(dish_ingredient.quantity),
                    "unit": dish_ingredient.unit,
                    "unit_price": str(Decimal(str(ingredient.unit_price or 0))),
                    "cost": str(cost),
                })

            # 成本分解
            breakdown = {
                "dish_id": str(dish.id),
                "dish_name": dish.name,
                "price": str(Decimal(str(dish.price))),
                "recorded_cost": str(Decimal(str(dish.cost or 0))),
                "calculated_ingredient_cost": str(total_ingredient_cost),
                "ingredients": ingredients_cost,
                "profit_margin": float(dish.profit_margin or 0),
                "profit_amount": str(Decimal(str(dish.price)) - total_ingredient_cost),
            }

            return breakdown

    async def get_popular_dishes(self, limit: int = int(os.getenv("DISH_POPULAR_LIMIT", "10"))) -> List[Dict[str, Any]]:
        """
        获取热门菜品

        Args:
            limit: 限制数量

        Returns:
            热门菜品列表
        """
        store_id = self.require_store_id()

        async with self.get_session() as session:
            stmt = (
                select(Dish)
                .where(
                    and_(
                        Dish.store_id == store_id,
                        Dish.is_available == True
                    )
                )
                .order_by(Dish.total_sales.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            dishes = result.scalars().all()

            popular_dishes = [
                {
                    "id": str(dish.id),
                    "name": dish.name,
                    "price": str(Decimal(str(dish.price))),
                    "total_sales": dish.total_sales,
                    "total_revenue": str(Decimal(str(dish.total_revenue or 0))),
                    "rating": float(dish.rating or 0),
                }
                for dish in dishes
            ]

            return popular_dishes


class DishCategoryService(BaseService):
    """菜品分类服务"""

    async def create_category(self, category_data: Dict[str, Any]) -> DishCategory:
        """创建分类"""
        store_id = self.require_store_id()

        async with self.get_session() as session:
            category = DishCategory(
                store_id=store_id,
                **category_data
            )

            session.add(category)
            await session.flush()

            logger.info(
                "Dish category created",
                store_id=store_id,
                category_id=str(category.id),
                category_name=category.name,
            )

            return category

    async def list_categories(self) -> List[DishCategory]:
        """获取分类列表"""
        store_id = self.require_store_id()

        async with self.get_session() as session:
            stmt = (
                select(DishCategory)
                .where(
                    and_(
                        DishCategory.store_id == store_id,
                        DishCategory.is_active == True
                    )
                )
                .order_by(DishCategory.sort_order, DishCategory.name)
            )

            result = await session.execute(stmt)
            categories = result.scalars().all()

            return list(categories)
