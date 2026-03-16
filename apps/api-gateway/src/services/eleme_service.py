"""
饿了么集成服务
负责订单同步、菜单同步、门店管理、配送追踪、Webhook 事件处理等业务逻辑
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 确保 adapter 包可导入
_this_dir = os.path.dirname(__file__)
_repo_root = os.path.abspath(os.path.join(_this_dir, "../../../.."))
_adapters_dir = os.path.join(_repo_root, "packages", "api-adapters")
if _adapters_dir not in sys.path:
    sys.path.insert(0, _adapters_dir)


class ElemeService:
    """饿了么集成服务"""

    def __init__(self):
        self._adapters: Dict[str, Any] = {}

    def get_adapter(self, brand_id: str):
        """
        获取指定品牌的饿了么适配器实例（缓存复用）

        Args:
            brand_id: 品牌ID

        Returns:
            ElemeAdapter 实例

        Raises:
            ValueError: 未找到饿了么配置
        """
        if brand_id in self._adapters:
            return self._adapters[brand_id]

        app_key = os.getenv(f"ELEME_APP_KEY_{brand_id}", os.getenv("ELEME_APP_KEY"))
        app_secret = os.getenv(f"ELEME_APP_SECRET_{brand_id}", os.getenv("ELEME_APP_SECRET"))
        sandbox = os.getenv("ELEME_SANDBOX", "false").lower() == "true"

        if not app_key or not app_secret:
            raise ValueError(f"品牌 {brand_id} 未配置饿了么 app_key/app_secret")

        from eleme.src.adapter import ElemeAdapter

        adapter = ElemeAdapter(
            {
                "app_key": app_key,
                "app_secret": app_secret,
                "sandbox": sandbox,
            }
        )
        self._adapters[brand_id] = adapter
        return adapter

    # ── 订单管理 ──────────────────────────────────────────────────

    async def sync_orders(
        self,
        session: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从饿了么拉取订单并 upsert 到本地 orders 表

        Args:
            session: 数据库会话
            brand_id: 品牌ID
            store_id: 门店ID（可选）
            start_time: 开始时间 ISO8601
            end_time: 结束时间 ISO8601

        Returns:
            同步结果 {synced, skipped, errors}
        """
        adapter = self.get_adapter(brand_id)

        if not start_time or not end_time:
            today = datetime.utcnow().date()
            start_time = datetime(today.year, today.month, today.day).isoformat()
            end_time = (datetime(today.year, today.month, today.day) + timedelta(days=1)).isoformat()

        synced = 0
        skipped = 0
        errors = 0
        page = 1

        while True:
            try:
                result = await adapter.query_orders(
                    start_time=start_time,
                    end_time=end_time,
                    page=page,
                    page_size=50,
                )

                orders = result.get("orders", result.get("list", []))
                if not orders:
                    break

                for raw_order in orders:
                    try:
                        order_id = str(raw_order.get("order_id", raw_order.get("eleme_order_id", "")))
                        if not order_id:
                            errors += 1
                            continue

                        from src.models.order import Order

                        existing = await session.execute(select(Order).where(Order.id == f"ELEME_{order_id}"))
                        if existing.scalar_one_or_none():
                            skipped += 1
                            continue

                        # 转换为标准 OrderSchema
                        effective_store_id = store_id or str(raw_order.get("shop_id", ""))
                        std_order = adapter.to_order(
                            raw_order,
                            store_id=effective_store_id,
                            brand_id=brand_id,
                        )

                        db_order = Order(
                            id=f"ELEME_{order_id}",
                            store_id=std_order.store_id,
                            status=std_order.order_status.value,
                            total_amount=int(std_order.total * 100),
                            discount_amount=int(std_order.discount * 100),
                            final_amount=int(std_order.total * 100),
                            order_time=std_order.created_at,
                            notes=std_order.notes,
                            sales_channel="eleme",
                            order_metadata={
                                "source": "eleme",
                                "external_order_id": order_id,
                                "items_count": len(std_order.items),
                                "raw": raw_order,
                            },
                        )
                        session.add(db_order)
                        synced += 1

                    except Exception as e:
                        logger.error(
                            "饿了么订单写入失败",
                            order_id=raw_order.get("order_id"),
                            error=str(e),
                        )
                        errors += 1

                total = result.get("total", 0)
                if page * 50 >= total:
                    break
                page += 1

            except Exception as e:
                logger.error("饿了么订单拉取失败", page=page, error=str(e))
                errors += 1
                break

        if synced > 0:
            await session.commit()

        logger.info(
            "饿了么订单同步完成",
            brand_id=brand_id,
            synced=synced,
            skipped=skipped,
            errors=errors,
        )
        return {"synced": synced, "skipped": skipped, "errors": errors}

    async def get_order(self, brand_id: str, order_id: str) -> Dict[str, Any]:
        """获取单个饿了么订单详情"""
        adapter = self.get_adapter(brand_id)
        return await adapter.get_order_detail(order_id)

    async def confirm_order(self, brand_id: str, order_id: str) -> Dict[str, Any]:
        """确认接单"""
        adapter = self.get_adapter(brand_id)
        result = await adapter.confirm_order(order_id)
        logger.info("饿了么确认订单", order_id=order_id)
        return result

    async def cancel_order(self, brand_id: str, order_id: str, reason_code: int, reason: str) -> Dict[str, Any]:
        """取消订单"""
        adapter = self.get_adapter(brand_id)
        result = await adapter.cancel_order(order_id, reason_code, reason)
        logger.info("饿了么取消订单", order_id=order_id, reason=reason)
        return result

    # ── 菜单管理 ──────────────────────────────────────────────────

    async def sync_menu(
        self,
        brand_id: str,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从饿了么拉取菜品列表

        Returns:
            {foods: List[Dict], total: int}
        """
        adapter = self.get_adapter(brand_id)
        all_foods: List[Dict[str, Any]] = []
        page = 1

        while True:
            try:
                foods = await adapter.query_foods(page=page, page_size=50)
                if not foods:
                    break
                all_foods.extend(foods)
                if len(foods) < 50:
                    break
                page += 1
            except Exception as e:
                logger.error("饿了么菜品拉取失败", page=page, error=str(e))
                break

        logger.info("饿了么菜单同步完成", brand_id=brand_id, total=len(all_foods))
        return {"foods": all_foods, "total": len(all_foods)}

    async def update_stock(self, brand_id: str, food_id: str, stock: int) -> Dict[str, Any]:
        """更新商品库存"""
        adapter = self.get_adapter(brand_id)
        result = await adapter.update_food_stock(food_id, stock)
        logger.info("饿了么更新库存", food_id=food_id, stock=stock)
        return result

    async def toggle_food(self, brand_id: str, food_id: str, on_sale: bool) -> Dict[str, Any]:
        """上架/下架商品"""
        adapter = self.get_adapter(brand_id)
        if on_sale:
            result = await adapter.on_sale_food(food_id)
        else:
            result = await adapter.sold_out_food(food_id)
        logger.info("饿了么商品切换", food_id=food_id, on_sale=on_sale)
        return result

    # ── 门店管理 ──────────────────────────────────────────────────

    async def get_shop_info(self, brand_id: str, shop_id: Optional[str] = None) -> Dict[str, Any]:
        """获取门店信息"""
        adapter = self.get_adapter(brand_id)
        return await adapter.get_shop_info(shop_id)

    async def toggle_shop_status(self, brand_id: str, status: int, shop_id: Optional[str] = None) -> Dict[str, Any]:
        """切换门店营业状态（1=营业中, 0=休息中）"""
        adapter = self.get_adapter(brand_id)
        result = await adapter.update_shop_status(status, shop_id)
        logger.info("饿了么门店状态切换", status=status, shop_id=shop_id)
        return result

    # ── 配送追踪 ──────────────────────────────────────────────────

    async def get_delivery_status(self, brand_id: str, order_id: str) -> Dict[str, Any]:
        """查询配送状态"""
        adapter = self.get_adapter(brand_id)
        return await adapter.query_delivery_status(order_id)

    # ── Webhook 处理 ──────────────────────────────────────────────

    async def handle_webhook(
        self,
        payload: bytes,
        signature: str,
        timestamp: str,
    ) -> Dict[str, Any]:
        """
        验证签名并分发 Webhook 事件

        Args:
            payload: 原始请求体
            signature: 饿了么签名
            timestamp: 饿了么时间戳

        Returns:
            处理结果
        """
        app_secret = os.getenv("ELEME_APP_SECRET", "")
        if not app_secret:
            logger.warning("ELEME_APP_SECRET 未配置，跳过签名验证")
        else:
            from eleme.src.webhook import ElemeWebhookHandler

            handler = ElemeWebhookHandler(app_secret)
            if not handler.verify_signature(payload.decode("utf-8"), signature, timestamp):
                raise ValueError("签名验证失败")

        return {"verified": True}

    async def handle_webhook_event(
        self,
        session: AsyncSession,
        event_type: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        处理饿了么 Webhook 推送事件

        支持事件: order.created, order.paid, order.cancelled,
                  order.refunded, delivery.status_changed, food.stock_warning
        """
        logger.info("处理饿了么Webhook事件", event_type=event_type)

        if event_type == "order.created":
            return await self._handle_order_created(session, data)
        elif event_type == "order.paid":
            return await self._handle_order_status_change(session, data, "paid")
        elif event_type == "order.cancelled":
            return await self._handle_order_status_change(session, data, "cancelled")
        elif event_type == "order.refunded":
            return await self._handle_order_status_change(session, data, "refunded")
        elif event_type == "delivery.status_changed":
            return await self._handle_delivery_update(session, data)
        elif event_type == "food.stock_warning":
            return await self._handle_stock_warning(data)
        else:
            logger.warning("未知饿了么事件类型", event_type=event_type)
            return {"handled": False, "reason": f"unknown event type: {event_type}"}

    async def _handle_order_created(self, session: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理新订单事件"""
        order_id = str(data.get("order_id", ""))
        if not order_id:
            return {"handled": False, "reason": "missing order_id"}

        from src.models.order import Order

        existing = await session.execute(select(Order).where(Order.id == f"ELEME_{order_id}"))
        if existing.scalar_one_or_none():
            return {"handled": True, "action": "skipped", "order_id": order_id}

        db_order = Order(
            id=f"ELEME_{order_id}",
            store_id=str(data.get("shop_id", "")),
            status="pending",
            total_amount=int(float(data.get("total_price", 0)) * 100),
            discount_amount=int(float(data.get("discount_price", 0)) * 100),
            final_amount=int(float(data.get("total_price", 0)) * 100),
            order_time=datetime.utcnow(),
            sales_channel="eleme",
            order_metadata={
                "source": "eleme",
                "external_order_id": order_id,
                "raw": data,
            },
        )
        session.add(db_order)
        await session.commit()

        logger.info("饿了么新订单已写入", order_id=order_id)
        return {"handled": True, "action": "created", "order_id": order_id}

    async def _handle_order_status_change(
        self, session: AsyncSession, data: Dict[str, Any], new_status: str
    ) -> Dict[str, Any]:
        """处理订单状态变更"""
        order_id = str(data.get("order_id", ""))
        from src.models.order import Order

        result = await session.execute(select(Order).where(Order.id == f"ELEME_{order_id}"))
        order = result.scalar_one_or_none()
        if not order:
            logger.warning("饿了么订单不存在，跳过状态更新", order_id=order_id)
            return {"handled": False, "reason": "order not found"}

        status_map = {
            "paid": "confirmed",
            "cancelled": "cancelled",
            "refunded": "cancelled",
        }
        order.status = status_map.get(new_status, order.status)
        await session.commit()

        logger.info("饿了么订单状态更新", order_id=order_id, status=new_status)
        return {"handled": True, "action": "status_updated", "order_id": order_id}

    async def _handle_delivery_update(self, session: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理配送状态变更"""
        order_id = str(data.get("order_id", ""))
        from src.models.order import Order

        result = await session.execute(select(Order).where(Order.id == f"ELEME_{order_id}"))
        order = result.scalar_one_or_none()
        if order and order.order_metadata:
            metadata = dict(order.order_metadata)
            metadata["delivery_status"] = data.get("status")
            metadata["rider_name"] = data.get("rider_name")
            metadata["rider_phone"] = data.get("rider_phone")
            order.order_metadata = metadata
            await session.commit()

        return {"handled": True, "action": "delivery_updated", "order_id": order_id}

    async def _handle_stock_warning(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理库存预警"""
        food_id = data.get("food_id")
        food_name = data.get("food_name")
        current_stock = data.get("current_stock")

        logger.warning(
            "饿了么库存预警",
            food_id=food_id,
            food_name=food_name,
            current_stock=current_stock,
        )
        return {
            "handled": True,
            "action": "stock_warning_logged",
            "food_id": food_id,
        }


# 全局单例
eleme_service = ElemeService()
