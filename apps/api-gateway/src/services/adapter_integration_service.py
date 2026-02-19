"""
智链OS API适配器集成服务
统一管理所有第三方API适配器，并与神经系统集成
"""
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime
import asyncio

logger = structlog.get_logger()


class AdapterIntegrationService:
    """API适配器集成服务"""

    def __init__(self, neural_system=None):
        """
        初始化集成服务

        Args:
            neural_system: 神经系统实例
        """
        self.neural_system = neural_system
        self.adapters: Dict[str, Any] = {}
        self.adapter_configs: Dict[str, Dict[str, Any]] = {}

        logger.info("API适配器集成服务初始化")

    def register_adapter(
        self,
        adapter_name: str,
        adapter_instance: Any,
        config: Dict[str, Any],
    ) -> None:
        """
        注册适配器

        Args:
            adapter_name: 适配器名称 (tiancai, meituan, aoqiwei, pinzhi)
            adapter_instance: 适配器实例
            config: 适配器配置
        """
        self.adapters[adapter_name] = adapter_instance
        self.adapter_configs[adapter_name] = config

        logger.info("注册适配器", adapter_name=adapter_name)

    def get_adapter(self, adapter_name: str) -> Optional[Any]:
        """
        获取适配器实例

        Args:
            adapter_name: 适配器名称

        Returns:
            适配器实例
        """
        return self.adapters.get(adapter_name)

    # ==================== 订单同步 ====================

    async def sync_order_from_tiancai(
        self,
        order_id: str,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        从天财商龙同步订单到智链OS

        Args:
            order_id: 订单ID
            store_id: 门店ID

        Returns:
            同步结果
        """
        adapter = self.get_adapter("tiancai")
        if not adapter:
            raise ValueError("天财商龙适配器未注册")

        try:
            # 从天财商龙获取订单
            order_data = await adapter.query_order(order_id=order_id)

            # 转换为标准格式
            standard_order = self._convert_tiancai_order(order_data)

            # 发送到神经系统
            if self.neural_system:
                await self.neural_system.emit_event(
                    event_type="order.created",
                    event_source="tiancai",
                    data=standard_order,
                    store_id=store_id,
                    priority=1,
                )

            logger.info("天财商龙订单同步成功", order_id=order_id)
            return {"status": "success", "order": standard_order}

        except Exception as e:
            logger.error("天财商龙订单同步失败", order_id=order_id, error=str(e))
            raise

    async def sync_order_from_meituan(
        self,
        order_id: str,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        从美团同步订单到智链OS

        Args:
            order_id: 订单ID
            store_id: 门店ID

        Returns:
            同步结果
        """
        adapter = self.get_adapter("meituan")
        if not adapter:
            raise ValueError("美团适配器未注册")

        try:
            # 从美团获取订单
            order_data = await adapter.query_order(order_id=order_id)

            # 转换为标准格式
            standard_order = self._convert_meituan_order(order_data)

            # 发送到神经系统
            if self.neural_system:
                await self.neural_system.emit_event(
                    event_type="order.created",
                    event_source="meituan",
                    data=standard_order,
                    store_id=store_id,
                    priority=1,
                )

            logger.info("美团订单同步成功", order_id=order_id)
            return {"status": "success", "order": standard_order}

        except Exception as e:
            logger.error("美团订单同步失败", order_id=order_id, error=str(e))
            raise

    # ==================== 菜品同步 ====================

    async def sync_dishes_from_tiancai(
        self,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        从天财商龙同步菜品到智链OS

        Args:
            store_id: 门店ID

        Returns:
            同步结果
        """
        adapter = self.get_adapter("tiancai")
        if not adapter:
            raise ValueError("天财商龙适配器未注册")

        try:
            # 从天财商龙获取菜品列表
            dishes = await adapter.query_dish()

            # 转换为标准格式并发送到神经系统
            synced_count = 0
            for dish in dishes:
                standard_dish = self._convert_tiancai_dish(dish)

                if self.neural_system:
                    await self.neural_system.emit_event(
                        event_type="dish.updated",
                        event_source="tiancai",
                        data=standard_dish,
                        store_id=store_id,
                        priority=0,
                    )
                synced_count += 1

            logger.info("天财商龙菜品同步成功", count=synced_count)
            return {"status": "success", "synced_count": synced_count}

        except Exception as e:
            logger.error("天财商龙菜品同步失败", error=str(e))
            raise

    async def sync_dishes_from_meituan(
        self,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        从美团同步菜品到智链OS

        Args:
            store_id: 门店ID

        Returns:
            同步结果
        """
        adapter = self.get_adapter("meituan")
        if not adapter:
            raise ValueError("美团适配器未注册")

        try:
            # 从美团获取商品列表
            foods = await adapter.query_food()

            # 转换为标准格式并发送到神经系统
            synced_count = 0
            for food in foods:
                standard_dish = self._convert_meituan_food(food)

                if self.neural_system:
                    await self.neural_system.emit_event(
                        event_type="dish.updated",
                        event_source="meituan",
                        data=standard_dish,
                        store_id=store_id,
                        priority=0,
                    )
                synced_count += 1

            logger.info("美团菜品同步成功", count=synced_count)
            return {"status": "success", "synced_count": synced_count}

        except Exception as e:
            logger.error("美团菜品同步失败", error=str(e))
            raise

    # ==================== 库存同步 ====================

    async def sync_inventory_to_meituan(
        self,
        food_id: str,
        stock: int,
    ) -> Dict[str, Any]:
        """
        将库存同步到美团

        Args:
            food_id: 商品ID
            stock: 库存数量

        Returns:
            同步结果
        """
        adapter = self.get_adapter("meituan")
        if not adapter:
            raise ValueError("美团适配器未注册")

        try:
            result = await adapter.update_food_stock(food_id=food_id, stock=stock)
            logger.info("库存同步到美团成功", food_id=food_id, stock=stock)
            return {"status": "success", "result": result}

        except Exception as e:
            logger.error("库存同步到美团失败", food_id=food_id, error=str(e))
            raise

    async def sync_inventory_to_tiancai(
        self,
        material_id: str,
        quantity: float,
        operation_type: int,
    ) -> Dict[str, Any]:
        """
        将库存同步到天财商龙

        Args:
            material_id: 原料ID
            quantity: 数量
            operation_type: 操作类型

        Returns:
            同步结果
        """
        adapter = self.get_adapter("tiancai")
        if not adapter:
            raise ValueError("天财商龙适配器未注册")

        try:
            result = await adapter.update_inventory(
                material_id=material_id,
                quantity=quantity,
                operation_type=operation_type,
            )
            logger.info("库存同步到天财商龙成功", material_id=material_id)
            return {"status": "success", "result": result}

        except Exception as e:
            logger.error("库存同步到天财商龙失败", material_id=material_id, error=str(e))
            raise

    # ==================== 数据转换方法 ====================

    def _convert_tiancai_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换天财商龙订单为标准格式

        Args:
            order_data: 天财商龙订单数据

        Returns:
            标准格式订单
        """
        return {
            "order_id": order_data.get("order_id"),
            "order_no": order_data.get("order_no"),
            "source_system": "tiancai",
            "store_id": order_data.get("store_id"),
            "table_no": order_data.get("table_no"),
            "order_time": order_data.get("order_time"),
            "total_amount": order_data.get("total_amount", 0) / 100,  # 分转元
            "discount_amount": order_data.get("discount_amount", 0) / 100,
            "real_amount": order_data.get("real_amount", 0) / 100,
            "status": order_data.get("status"),
            "dishes": [
                {
                    "dish_id": dish.get("dish_id"),
                    "dish_name": dish.get("dish_name"),
                    "price": dish.get("price", 0) / 100,
                    "quantity": dish.get("quantity"),
                    "amount": dish.get("amount", 0) / 100,
                }
                for dish in order_data.get("dishes", [])
            ],
        }

    def _convert_meituan_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换美团订单为标准格式

        Args:
            order_data: 美团订单数据

        Returns:
            标准格式订单
        """
        return {
            "order_id": order_data.get("order_id"),
            "day_seq": order_data.get("day_seq"),
            "source_system": "meituan",
            "poi_id": order_data.get("poi_id"),
            "order_time": datetime.fromtimestamp(order_data.get("order_time", 0)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "delivery_time": datetime.fromtimestamp(order_data.get("delivery_time", 0)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "recipient_name": order_data.get("recipient_name"),
            "recipient_phone": order_data.get("recipient_phone"),
            "recipient_address": order_data.get("recipient_address"),
            "total_amount": order_data.get("total", 0) / 100,  # 分转元
            "original_price": order_data.get("original_price", 0) / 100,
            "shipping_fee": order_data.get("shipping_fee", 0) / 100,
            "package_fee": order_data.get("package_fee", 0) / 100,
            "status": order_data.get("status"),
            "dishes": [
                {
                    "food_name": item.get("food_name"),
                    "quantity": item.get("quantity"),
                    "price": item.get("price", 0) / 100,
                    "box_num": item.get("box_num"),
                    "box_price": item.get("box_price", 0) / 100,
                }
                for item in order_data.get("detail", [])
            ],
        }

    def _convert_tiancai_dish(self, dish_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换天财商龙菜品为标准格式

        Args:
            dish_data: 天财商龙菜品数据

        Returns:
            标准格式菜品
        """
        return {
            "dish_id": dish_data.get("dish_id"),
            "dish_name": dish_data.get("dish_name"),
            "source_system": "tiancai",
            "category_id": dish_data.get("category_id"),
            "category_name": dish_data.get("category_name"),
            "price": dish_data.get("price", 0) / 100,  # 分转元
            "unit": dish_data.get("unit"),
            "status": dish_data.get("status"),
        }

    def _convert_meituan_food(self, food_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换美团商品为标准格式

        Args:
            food_data: 美团商品数据

        Returns:
            标准格式菜品
        """
        return {
            "dish_id": food_data.get("food_id"),
            "dish_name": food_data.get("food_name"),
            "source_system": "meituan",
            "category_id": food_data.get("category_id"),
            "category_name": food_data.get("category_name"),
            "price": food_data.get("price", 0) / 100,  # 分转元
            "unit": food_data.get("unit"),
            "stock": food_data.get("stock"),
            "is_sold_out": food_data.get("is_sold_out"),
        }

    # ==================== 批量同步 ====================

    async def sync_all_from_tiancai(self, store_id: str) -> Dict[str, Any]:
        """
        从天财商龙同步所有数据

        Args:
            store_id: 门店ID

        Returns:
            同步结果
        """
        results = {}

        try:
            # 同步菜品
            dish_result = await self.sync_dishes_from_tiancai(store_id)
            results["dishes"] = dish_result

            logger.info("天财商龙全量同步完成", store_id=store_id)
            return {"status": "success", "results": results}

        except Exception as e:
            logger.error("天财商龙全量同步失败", store_id=store_id, error=str(e))
            raise

    async def sync_all_from_meituan(self, store_id: str) -> Dict[str, Any]:
        """
        从美团同步所有数据

        Args:
            store_id: 门店ID

        Returns:
            同步结果
        """
        results = {}

        try:
            # 同步商品
            food_result = await self.sync_dishes_from_meituan(store_id)
            results["foods"] = food_result

            logger.info("美团全量同步完成", store_id=store_id)
            return {"status": "success", "results": results}

        except Exception as e:
            logger.error("美团全量同步失败", store_id=store_id, error=str(e))
            raise

    async def close(self):
        """关闭所有适配器"""
        logger.info("关闭所有适配器")
        for adapter_name, adapter in self.adapters.items():
            try:
                await adapter.close()
                logger.info("适配器已关闭", adapter_name=adapter_name)
            except Exception as e:
                logger.error("关闭适配器失败", adapter_name=adapter_name, error=str(e))
