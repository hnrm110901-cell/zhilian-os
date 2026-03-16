"""
全渠道沽清服务

厨师长一键触发 → POS + 美团 + 小程序同步下架
"""

import uuid
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.dish import Dish

logger = structlog.get_logger()


class SoldoutService:
    """全渠道沽清调度器"""

    def __init__(self, db: AsyncSession, store_id: str):
        self.db = db
        self.store_id = store_id

    async def soldout_dish(
        self,
        dish_id: str,
        reason: str = "",
        operator: str = "",
    ) -> dict:
        """
        沽清菜品：
        1. 更新本地 Dish.is_available = False
        2. 异步通知各渠道（POS/美团/小程序）
        """
        dish = await self._get_dish(dish_id)
        if not dish:
            return {"success": False, "error": "菜品不存在"}

        if not dish.is_available:
            return {"success": True, "message": "菜品已处于沽清状态", "dish_id": str(dish.id), "dish_name": dish.name}

        # 1. 本地状态更新
        dish.is_available = False
        await self.db.flush()

        # 2. 通知各渠道（异步，失败不阻塞主流程）
        channel_results = await self._notify_channels(dish, action="soldout")

        # 3. 记录沽清事件
        event = {
            "event_id": f"SO_{uuid.uuid4().hex[:12].upper()}",
            "dish_id": str(dish.id),
            "dish_name": dish.name,
            "action": "soldout",
            "reason": reason,
            "operator": operator,
            "timestamp": datetime.utcnow().isoformat(),
            "channel_results": channel_results,
        }

        logger.info("dish_soldout", **event)

        return {
            "success": True,
            "message": f"「{dish.name}」已沽清",
            "dish_id": str(dish.id),
            "dish_name": dish.name,
            "channel_results": channel_results,
        }

    async def restore_dish(
        self,
        dish_id: str,
        operator: str = "",
    ) -> dict:
        """恢复上架"""
        dish = await self._get_dish(dish_id)
        if not dish:
            return {"success": False, "error": "菜品不存在"}

        if dish.is_available:
            return {"success": True, "message": "菜品已处于可售状态", "dish_id": str(dish.id), "dish_name": dish.name}

        dish.is_available = True
        await self.db.flush()

        channel_results = await self._notify_channels(dish, action="restore")

        logger.info("dish_restored", dish_id=str(dish.id), dish_name=dish.name, operator=operator)

        return {
            "success": True,
            "message": f"「{dish.name}」已恢复上架",
            "dish_id": str(dish.id),
            "dish_name": dish.name,
            "channel_results": channel_results,
        }

    async def list_soldout(self) -> list[dict]:
        """获取当前沽清菜品列表"""
        stmt = (
            select(Dish)
            .where(
                Dish.store_id == self.store_id,
                Dish.is_available == False,
            )
            .order_by(Dish.name)
        )
        result = await self.db.execute(stmt)
        dishes = result.scalars().all()

        return [
            {
                "dish_id": str(d.id),
                "dish_name": d.name,
                "dish_code": d.code,
                "category_id": str(d.category_id) if d.category_id else None,
                "price_yuan": float(d.price) if d.price else 0,
                "kitchen_station": d.kitchen_station,
            }
            for d in dishes
        ]

    async def list_available(self, keyword: str = "") -> list[dict]:
        """获取可售菜品列表（供沽清选择用）"""
        stmt = (
            select(Dish)
            .where(
                Dish.store_id == self.store_id,
                Dish.is_available == True,
            )
            .order_by(Dish.sort_order, Dish.name)
        )
        result = await self.db.execute(stmt)
        dishes = result.scalars().all()

        items = []
        for d in dishes:
            if keyword and keyword.lower() not in (d.name or "").lower():
                continue
            items.append(
                {
                    "dish_id": str(d.id),
                    "dish_name": d.name,
                    "dish_code": d.code,
                    "category_id": str(d.category_id) if d.category_id else None,
                    "price_yuan": float(d.price) if d.price else 0,
                    "kitchen_station": d.kitchen_station,
                    "tags": d.tags or [],
                }
            )
        return items

    async def batch_soldout(
        self,
        dish_ids: list[str],
        reason: str = "",
        operator: str = "",
    ) -> dict:
        """批量沽清"""
        results = []
        for did in dish_ids:
            r = await self.soldout_dish(did, reason=reason, operator=operator)
            results.append(r)
        success_count = sum(1 for r in results if r.get("success"))
        return {
            "total": len(dish_ids),
            "success": success_count,
            "failed": len(dish_ids) - success_count,
            "details": results,
        }

    # ======================== 内部方法 ========================

    async def _get_dish(self, dish_id: str) -> Optional[Dish]:
        """获取本店菜品"""
        try:
            dish_uuid = uuid.UUID(dish_id)
        except ValueError:
            return None
        stmt = select(Dish).where(Dish.id == dish_uuid, Dish.store_id == self.store_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _notify_channels(self, dish: Dish, action: str) -> dict:
        """
        通知各渠道沽清/恢复。
        目前仅更新本地数据库，POS/美团/小程序 的实际 API 调用在对接后启用。
        """
        results = {"local_db": "ok"}

        # POS 通知（通过 POS adapter）
        try:
            # TODO: 对接实际 POS API（正品/奥琦玮 G10）
            # await pos_adapter.set_dish_availability(dish.code, available=(action == "restore"))
            results["pos"] = "pending_integration"
        except Exception as e:
            results["pos"] = f"error: {str(e)}"

        # 美团通知
        try:
            # TODO: 对接美团开放平台 API
            results["meituan"] = "pending_integration"
        except Exception as e:
            results["meituan"] = f"error: {str(e)}"

        # 微信小程序通知
        try:
            # TODO: 对接微信小程序后台
            results["wechat_mini"] = "pending_integration"
        except Exception as e:
            results["wechat_mini"] = f"error: {str(e)}"

        return results
