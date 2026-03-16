"""
全渠道沽清服务

厨师长一键触发 → POS + 美团 + 小程序同步下架
"""

import os
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
        self._adapters: dict = {}  # 缓存已初始化的适配器

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

        按门店已配置的渠道逐一调用对应适配器：
        - POS: 品智(Pinzhi) / 奥琦玮(Aoqiwei) / 客如云(Keruyun)
        - 外卖: 美团(Meituan) / 饿了么(Eleme)
        - 小程序: 微信（待对接）

        失败不阻塞主流程，每个渠道独立 try/except。
        """
        results = {"local_db": "ok"}
        is_restore = action == "restore"
        dish_code = dish.code or ""

        # ── POS 通知 ──
        results["pos"] = await self._notify_pos(dish_code, is_restore)

        # ── 美团外卖 ──
        results["meituan"] = await self._notify_meituan(dish_code, is_restore)

        # ── 饿了么 ──
        results["eleme"] = await self._notify_eleme(dish_code, is_restore)

        # ── 客如云 ──
        results["keruyun"] = await self._notify_keruyun(dish_code, is_restore)

        # ── 微信小程序（待对接，需要小程序后台 API 密钥）──
        results["wechat_mini"] = "not_configured"

        return results

    async def _notify_pos(self, dish_code: str, is_restore: bool) -> str:
        """通知 POS 系统沽清/恢复"""
        pos_type = os.getenv("POS_ADAPTER_TYPE", "")
        if not pos_type:
            return "not_configured"

        try:
            if pos_type == "pinzhi":
                # 品智 POS 暂无沽清 API，记录日志等待厂商支持
                logger.info("pos.pinzhi.soldout_not_supported", dish_code=dish_code)
                return "not_supported_by_vendor"

            elif pos_type == "aoqiwei":
                # 奥琦玮 POS 暂无沽清 API
                logger.info("pos.aoqiwei.soldout_not_supported", dish_code=dish_code)
                return "not_supported_by_vendor"

            elif pos_type == "keruyun":
                adapter = await self._get_keruyun_adapter()
                if not adapter:
                    return "not_configured"
                await adapter.update_dish_status(
                    sku_id=dish_code,
                    is_sold_out=0 if is_restore else 1,
                )
                return "ok"

            return "unknown_pos_type"
        except Exception as e:
            logger.warning("pos.notify_failed", pos_type=pos_type, error=str(e))
            return f"error: {str(e)}"

    async def _notify_meituan(self, dish_code: str, is_restore: bool) -> str:
        """通知美团外卖沽清/恢复"""
        poi_id = os.getenv("MEITUAN_POI_ID", "")
        app_id = os.getenv("MEITUAN_APP_ID", "")
        app_secret = os.getenv("MEITUAN_APP_SECRET", "")
        if not (poi_id and app_id and app_secret):
            return "not_configured"

        try:
            adapter = await self._get_adapter("meituan", lambda: self._create_meituan_adapter())
            if is_restore:
                await adapter.on_sale_food(food_id=dish_code)
            else:
                await adapter.sold_out_food(food_id=dish_code)
            return "ok"
        except Exception as e:
            logger.warning("meituan.notify_failed", error=str(e))
            return f"error: {str(e)}"

    async def _notify_eleme(self, dish_code: str, is_restore: bool) -> str:
        """通知饿了么沽清/恢复"""
        eleme_app_key = os.getenv("ELEME_APP_KEY", "")
        eleme_app_secret = os.getenv("ELEME_APP_SECRET", "")
        if not (eleme_app_key and eleme_app_secret):
            return "not_configured"

        try:
            adapter = await self._get_adapter("eleme", lambda: self._create_eleme_adapter())
            if is_restore:
                await adapter.on_sale_food(food_id=dish_code)
            else:
                await adapter.sold_out_food(food_id=dish_code)
            return "ok"
        except Exception as e:
            logger.warning("eleme.notify_failed", error=str(e))
            return f"error: {str(e)}"

    async def _notify_keruyun(self, dish_code: str, is_restore: bool) -> str:
        """通知客如云 POS 沽清/恢复"""
        client_id = os.getenv("KERUYUN_CLIENT_ID", "")
        client_secret = os.getenv("KERUYUN_CLIENT_SECRET", "")
        if not (client_id and client_secret):
            return "not_configured"

        try:
            adapter = await self._get_keruyun_adapter()
            if not adapter:
                return "not_configured"
            await adapter.update_dish_status(
                sku_id=dish_code,
                is_sold_out=0 if is_restore else 1,
            )
            return "ok"
        except Exception as e:
            logger.warning("keruyun.notify_failed", error=str(e))
            return f"error: {str(e)}"

    # ── 适配器工厂 ──

    async def _get_adapter(self, key: str, factory):
        """获取或创建适配器实例（懒初始化 + 缓存）"""
        if key not in self._adapters:
            self._adapters[key] = factory()
        return self._adapters[key]

    def _create_meituan_adapter(self):
        """创建美团适配器"""
        from packages.api_adapters.meituan_saas.src.adapter import MeituanSaasAdapter
        return MeituanSaasAdapter(config={
            "app_key": os.getenv("MEITUAN_APP_ID", ""),
            "app_secret": os.getenv("MEITUAN_APP_SECRET", ""),
            "poi_id": os.getenv("MEITUAN_POI_ID", ""),
        })

    def _create_eleme_adapter(self):
        """创建饿了么适配器"""
        from packages.api_adapters.eleme.src.adapter import ElemeAdapter
        return ElemeAdapter(config={
            "app_key": os.getenv("ELEME_APP_KEY", ""),
            "app_secret": os.getenv("ELEME_APP_SECRET", ""),
        })

    async def _get_keruyun_adapter(self):
        """获取客如云适配器"""
        client_id = os.getenv("KERUYUN_CLIENT_ID", "")
        client_secret = os.getenv("KERUYUN_CLIENT_SECRET", "")
        if not (client_id and client_secret):
            return None
        if "keruyun" not in self._adapters:
            from packages.api_adapters.keruyun.src.adapter import KeruyunAdapter
            self._adapters["keruyun"] = KeruyunAdapter(config={
                "client_id": client_id,
                "client_secret": client_secret,
                "store_id": self.store_id,
            })
        return self._adapters["keruyun"]
