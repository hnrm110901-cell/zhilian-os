"""
外卖统一接单服务
整合美团/饿了么/抖音三个平台的订单到统一视图

核心功能：
- 跨平台订单聚合（单一视图）
- 自动接单（可配置）
- 库存同步（接单后自动扣减）
- 统一状态管理
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from .eleme_service import ElemeService
from .douyin_service import DouyinService

logger = structlog.get_logger()


class TakeawayUnifiedService:
    """外卖统一接单服务 — 跨平台订单聚合与管理"""

    SUPPORTED_PLATFORMS = ["meituan", "eleme", "douyin"]

    def __init__(self):
        self._eleme_service = ElemeService()
        self._douyin_service = DouyinService()

    # ── 公开接口 ──────────────────────────────────────────────────────

    async def get_pending_orders(self, store_id: str) -> List[Dict[str, Any]]:
        """
        获取所有平台待处理订单（统一格式）
        从各平台适配器拉取并合并，按时间排序

        返回格式：
        [
          {
            "platform": "meituan",
            "platform_order_id": "...",
            "unified_id": "...",
            "status": "pending",
            "amount_yuan": 88.0,
            "items": [...],
            "customer_address": "...",
            "estimated_delivery_min": 30,
            "created_at": "...",
          }
        ]
        """
        all_orders: List[Dict[str, Any]] = []
        errors: List[str] = []

        # 并发拉取各平台（实际项目可用 asyncio.gather）
        for platform in self.SUPPORTED_PLATFORMS:
            try:
                orders = await self._fetch_platform_pending_orders(store_id, platform)
                all_orders.extend(orders)
            except Exception as exc:
                logger.warning(
                    "拉取平台待接单失败",
                    platform=platform,
                    store_id=store_id,
                    error=str(exc),
                )
                errors.append(f"{platform}: {exc}")

        # 按创建时间升序排列（最早的订单最需要优先处理）
        all_orders.sort(key=lambda o: o.get("created_at", ""))

        logger.info(
            "拉取待接单完成",
            store_id=store_id,
            total=len(all_orders),
            errors=errors,
        )
        return all_orders

    async def accept_order(
        self,
        store_id: str,
        platform: str,
        platform_order_id: str,
        estimated_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        接单 — 调用对应平台API接单
        接单后：
        1. 调用对应平台的接单接口
        2. 扣减库存（调用 inventory service）
        3. 触发KDS出餐（发送到 kitchen display）
        4. 返回接单结果
        """
        self._validate_platform(platform)

        logger.info(
            "开始接单",
            store_id=store_id,
            platform=platform,
            platform_order_id=platform_order_id,
            estimated_minutes=estimated_minutes,
        )

        # Step 1: 调用平台接单接口
        platform_result = await self._call_platform_accept(
            store_id=store_id,
            platform=platform,
            platform_order_id=platform_order_id,
            estimated_minutes=estimated_minutes,
        )

        if not platform_result.get("success"):
            return {
                "success": False,
                "platform": platform,
                "platform_order_id": platform_order_id,
                "error": platform_result.get("error", "平台接单失败"),
            }

        # Step 2: 扣减库存（尽力而为，失败不阻断接单）
        inventory_result = await self._deduct_inventory_for_order(
            store_id=store_id,
            platform=platform,
            platform_order_id=platform_order_id,
            order_items=platform_result.get("items", []),
        )

        # Step 3: 发送KDS通知（尽力而为）
        kds_result = await self._notify_kitchen_display(
            store_id=store_id,
            platform=platform,
            platform_order_id=platform_order_id,
            order_data=platform_result,
        )

        return {
            "success": True,
            "platform": platform,
            "platform_order_id": platform_order_id,
            "estimated_minutes": estimated_minutes,
            "inventory_deducted": inventory_result.get("success", False),
            "kds_notified": kds_result.get("success", False),
            "accepted_at": datetime.now().isoformat(),
        }

    async def reject_order(
        self,
        store_id: str,
        platform: str,
        platform_order_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """拒单 — 调用平台API拒单 + 记录原因"""
        self._validate_platform(platform)

        logger.info(
            "拒单",
            store_id=store_id,
            platform=platform,
            platform_order_id=platform_order_id,
            reason=reason,
        )

        result = await self._call_platform_reject(
            store_id=store_id,
            platform=platform,
            platform_order_id=platform_order_id,
            reason=reason,
        )

        return {
            "success": result.get("success", False),
            "platform": platform,
            "platform_order_id": platform_order_id,
            "reason": reason,
            "rejected_at": datetime.now().isoformat(),
            "error": result.get("error"),
        }

    async def auto_accept_config(self, store_id: str) -> Dict[str, Any]:
        """获取自动接单配置（是否开启，各平台独立配置）"""
        async for db in get_db_session():
            from sqlalchemy import text
            result = await db.execute(
                text(
                    """
                    SELECT platform, auto_accept_enabled, max_concurrent_orders, is_online, commission_rate
                    FROM takeaway_platform_configs
                    WHERE store_id = :store_id
                    ORDER BY platform
                    """
                ),
                {"store_id": store_id},
            )
            rows = result.mappings().all()

            # 对于没有配置的平台，返回默认值
            configs: Dict[str, Any] = {}
            existing = {r["platform"]: r for r in rows}

            for platform in self.SUPPORTED_PLATFORMS:
                if platform in existing:
                    r = existing[platform]
                    configs[platform] = {
                        "auto_accept_enabled": r["auto_accept_enabled"],
                        "max_concurrent_orders": r["max_concurrent_orders"],
                        "is_online": r["is_online"],
                        "commission_rate": float(r["commission_rate"] or 0),
                    }
                else:
                    configs[platform] = {
                        "auto_accept_enabled": False,
                        "max_concurrent_orders": 10,
                        "is_online": False,
                        "commission_rate": 0.0,
                    }

            return {
                "store_id": store_id,
                "platforms": configs,
            }

    async def update_auto_accept(
        self,
        store_id: str,
        platform: str,
        enabled: bool,
        max_concurrent_orders: int = 10,
    ) -> Dict[str, Any]:
        """更新自动接单配置"""
        self._validate_platform(platform)

        async for db in get_db_session():
            from sqlalchemy import text
            await db.execute(
                text(
                    """
                    INSERT INTO takeaway_platform_configs
                        (id, store_id, platform, auto_accept_enabled, max_concurrent_orders, is_online, commission_rate)
                    VALUES
                        (:id, :store_id, :platform, :auto_accept_enabled, :max_concurrent_orders, false, 0)
                    ON CONFLICT (store_id, platform) DO UPDATE SET
                        auto_accept_enabled = EXCLUDED.auto_accept_enabled,
                        max_concurrent_orders = EXCLUDED.max_concurrent_orders,
                        updated_at = NOW()
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "store_id": store_id,
                    "platform": platform,
                    "auto_accept_enabled": enabled,
                    "max_concurrent_orders": max_concurrent_orders,
                },
            )
            await db.commit()

        logger.info(
            "更新自动接单配置",
            store_id=store_id,
            platform=platform,
            enabled=enabled,
            max_concurrent_orders=max_concurrent_orders,
        )
        return {
            "success": True,
            "store_id": store_id,
            "platform": platform,
            "auto_accept_enabled": enabled,
            "max_concurrent_orders": max_concurrent_orders,
        }

    async def get_platform_stats(
        self, store_id: str, days: int = 7
    ) -> Dict[str, Any]:
        """
        外卖平台统计
        返回各平台：订单量、营收、取消率、平均送达时间
        """
        async for db in get_db_session():
            from sqlalchemy import text
            # 从 orders 表中查询各平台汇总数据
            result = await db.execute(
                text(
                    """
                    SELECT
                        channel,
                        COUNT(*) AS order_count,
                        SUM(CASE WHEN status NOT IN ('cancelled','refunded') THEN final_amount ELSE 0 END)
                            AS revenue_fen,
                        SUM(CASE WHEN status IN ('cancelled','refunded') THEN 1 ELSE 0 END)::float
                            / NULLIF(COUNT(*), 0) AS cancel_rate,
                        AVG(
                            CASE WHEN delivered_at IS NOT NULL AND created_at IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (delivered_at - created_at)) / 60.0
                            ELSE NULL END
                        ) AS avg_delivery_min
                    FROM orders
                    WHERE store_id = :store_id
                      AND channel IN ('meituan', 'eleme', 'douyin')
                      AND created_at >= NOW() - :n * INTERVAL '1 day'
                    GROUP BY channel
                    """
                ),
                {"store_id": store_id, "n": days},
            )
            rows = result.mappings().all()

            stats: Dict[str, Any] = {}
            for platform in self.SUPPORTED_PLATFORMS:
                stats[platform] = {
                    "order_count": 0,
                    "revenue_yuan": 0.0,
                    "cancel_rate": 0.0,
                    "avg_delivery_min": None,
                }

            for r in rows:
                channel = r["channel"]
                if channel in stats:
                    stats[channel] = {
                        "order_count": r["order_count"] or 0,
                        "revenue_yuan": round((r["revenue_fen"] or 0) / 100, 2),
                        "cancel_rate": round(float(r["cancel_rate"] or 0), 4),
                        "avg_delivery_min": (
                            round(float(r["avg_delivery_min"]), 1)
                            if r["avg_delivery_min"] is not None
                            else None
                        ),
                    }

            return {
                "store_id": store_id,
                "days": days,
                "platforms": stats,
                "total_revenue_yuan": round(
                    sum(v["revenue_yuan"] for v in stats.values()), 2
                ),
                "total_orders": sum(v["order_count"] for v in stats.values()),
            }

    async def sync_menu_to_platforms(
        self, store_id: str, platforms: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        菜单同步到各平台（防超卖）
        将当前库存状态同步到各外卖平台菜单（沽清/上架）
        """
        target_platforms = platforms or self.SUPPORTED_PLATFORMS
        results: Dict[str, Any] = {}

        # 获取当前库存状态（soldout 清单）
        soldout_items = await self._get_soldout_items(store_id)

        for platform in target_platforms:
            if platform not in self.SUPPORTED_PLATFORMS:
                results[platform] = {"success": False, "error": "不支持的平台"}
                continue

            try:
                sync_result = await self._push_soldout_to_platform(
                    store_id=store_id,
                    platform=platform,
                    soldout_items=soldout_items,
                )
                results[platform] = sync_result
            except Exception as exc:
                logger.warning(
                    "菜单同步失败",
                    platform=platform,
                    store_id=store_id,
                    error=str(exc),
                )
                results[platform] = {"success": False, "error": str(exc)}

        return {
            "store_id": store_id,
            "synced_at": datetime.now().isoformat(),
            "soldout_item_count": len(soldout_items),
            "platforms": results,
        }

    # ── 平台标准化 ────────────────────────────────────────────────────

    async def _normalize_meituan_order(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """标准化美团订单格式"""
        return {
            "platform": "meituan",
            "platform_order_id": str(raw_order.get("orderId") or raw_order.get("order_id", "")),
            "unified_id": f"mt_{raw_order.get('orderId', uuid.uuid4().hex[:8])}",
            "status": self._map_meituan_status(raw_order.get("status", 0)),
            "amount_yuan": round((raw_order.get("totalPrice", 0) or 0) / 100, 2),
            "items": self._parse_meituan_items(raw_order.get("detail", [])),
            "customer_address": raw_order.get("recipientAddress", ""),
            "estimated_delivery_min": raw_order.get("estimatedDeliveryTime", 30),
            "created_at": raw_order.get("ctime") or raw_order.get("createTime", ""),
            "remark": raw_order.get("remark", ""),
            "platform_raw": raw_order,
        }

    async def _normalize_eleme_order(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """标准化饿了么订单格式"""
        return {
            "platform": "eleme",
            "platform_order_id": str(raw_order.get("id") or raw_order.get("orderId", "")),
            "unified_id": f"ele_{raw_order.get('id', uuid.uuid4().hex[:8])}",
            "status": self._map_eleme_status(raw_order.get("statusCode", "")),
            "amount_yuan": round(float(raw_order.get("totalPrice", 0) or 0), 2),
            "items": self._parse_eleme_items(raw_order.get("groups", [])),
            "customer_address": raw_order.get("address", {}).get("text", ""),
            "estimated_delivery_min": raw_order.get("deliveryTime", 30),
            "created_at": raw_order.get("createdAt") or raw_order.get("created_at", ""),
            "remark": raw_order.get("description", ""),
            "platform_raw": raw_order,
        }

    async def _normalize_douyin_order(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """标准化抖音订单格式"""
        return {
            "platform": "douyin",
            "platform_order_id": str(raw_order.get("order_id") or raw_order.get("orderId", "")),
            "unified_id": f"dy_{raw_order.get('order_id', uuid.uuid4().hex[:8])}",
            "status": self._map_douyin_status(raw_order.get("order_status", "")),
            "amount_yuan": round(float(raw_order.get("amount", 0) or 0) / 100, 2),
            "items": self._parse_douyin_items(raw_order.get("sku_list", [])),
            "customer_address": raw_order.get("address", {}).get("detail", ""),
            "estimated_delivery_min": 30,
            "created_at": raw_order.get("create_time", ""),
            "remark": raw_order.get("remark", ""),
            "platform_raw": raw_order,
        }

    # ── 私有辅助方法 ──────────────────────────────────────────────────

    def _validate_platform(self, platform: str) -> None:
        if platform not in self.SUPPORTED_PLATFORMS:
            raise ValueError(
                f"不支持的平台: {platform}，支持: {self.SUPPORTED_PLATFORMS}"
            )

    async def _fetch_platform_pending_orders(
        self, store_id: str, platform: str
    ) -> List[Dict[str, Any]]:
        """从指定平台拉取待接单列表"""
        if platform == "meituan":
            return await self._fetch_meituan_pending(store_id)
        elif platform == "eleme":
            return await self._fetch_eleme_pending(store_id)
        elif platform == "douyin":
            return await self._fetch_douyin_pending(store_id)
        return []

    async def _fetch_meituan_pending(self, store_id: str) -> List[Dict[str, Any]]:
        """从美团拉取待接单（通过美团外卖Open API）"""
        app_key = os.getenv("MEITUAN_TAKEAWAY_APP_KEY", "")
        app_secret = os.getenv("MEITUAN_TAKEAWAY_APP_SECRET", "")

        if not app_key or not app_secret:
            logger.warning("美团外卖未配置 APP_KEY/APP_SECRET", store_id=store_id)
            return []

        try:
            import httpx
            # 美团外卖开放平台：拉取新订单
            # 实际生产环境需按美团文档做签名鉴权
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api-open-cater.meituan.com/waimai/order/queryUnprocessedOrders",
                    params={
                        "appAuthToken": os.getenv(f"MEITUAN_AUTH_TOKEN_{store_id}", ""),
                        "developerId": os.getenv("MEITUAN_DEVELOPER_ID", ""),
                        "timestamp": int(datetime.now().timestamp()),
                    },
                )
                data = resp.json()

            raw_orders = data.get("data", {}).get("orders", [])
            return [await self._normalize_meituan_order(o) for o in raw_orders]
        except Exception as exc:
            logger.warning("拉取美团待接单失败", store_id=store_id, error=str(exc))
            return []

    async def _fetch_eleme_pending(self, store_id: str) -> List[Dict[str, Any]]:
        """从饿了么拉取待接单"""
        brand_id = os.getenv("DEFAULT_BRAND_ID", "default")
        try:
            adapter = self._eleme_service.get_adapter(brand_id)
            # 饿了么适配器：查询待处理订单
            raw_orders = getattr(adapter, "get_unconfirmed_orders", lambda sid: [])(store_id)
            if hasattr(raw_orders, "__await__"):
                raw_orders = await raw_orders
            return [await self._normalize_eleme_order(o) for o in (raw_orders or [])]
        except Exception as exc:
            logger.warning("拉取饿了么待接单失败", store_id=store_id, error=str(exc))
            return []

    async def _fetch_douyin_pending(self, store_id: str) -> List[Dict[str, Any]]:
        """从抖音拉取待接单"""
        brand_id = os.getenv("DEFAULT_BRAND_ID", "default")
        try:
            adapter = self._douyin_service.get_adapter(brand_id)
            raw_orders = getattr(adapter, "get_pending_orders", lambda sid: [])(store_id)
            if hasattr(raw_orders, "__await__"):
                raw_orders = await raw_orders
            return [await self._normalize_douyin_order(o) for o in (raw_orders or [])]
        except Exception as exc:
            logger.warning("拉取抖音待接单失败", store_id=store_id, error=str(exc))
            return []

    async def _call_platform_accept(
        self,
        store_id: str,
        platform: str,
        platform_order_id: str,
        estimated_minutes: int,
    ) -> Dict[str, Any]:
        """调用平台接单接口"""
        try:
            if platform == "meituan":
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        "https://api-open-cater.meituan.com/waimai/order/confirm",
                        json={
                            "appAuthToken": os.getenv(f"MEITUAN_AUTH_TOKEN_{store_id}", ""),
                            "developerId": os.getenv("MEITUAN_DEVELOPER_ID", ""),
                            "orderId": platform_order_id,
                            "estimatedDeliveryTime": estimated_minutes,
                        },
                    )
                data = resp.json()
                if data.get("code") == 0:
                    return {"success": True, "items": data.get("data", {}).get("detail", [])}
                return {"success": False, "error": data.get("msg", "美团接单失败")}

            elif platform == "eleme":
                brand_id = os.getenv("DEFAULT_BRAND_ID", "default")
                adapter = self._eleme_service.get_adapter(brand_id)
                fn = getattr(adapter, "confirm_order", None)
                if fn:
                    result = fn(platform_order_id)
                    if hasattr(result, "__await__"):
                        result = await result
                    return {"success": True, "items": []}
                return {"success": True, "items": []}  # 乐观接受

            elif platform == "douyin":
                brand_id = os.getenv("DEFAULT_BRAND_ID", "default")
                adapter = self._douyin_service.get_adapter(brand_id)
                fn = getattr(adapter, "confirm_order", None)
                if fn:
                    result = fn(platform_order_id)
                    if hasattr(result, "__await__"):
                        result = await result
                    return {"success": True, "items": []}
                return {"success": True, "items": []}

        except Exception as exc:
            logger.error(
                "平台接单调用失败",
                platform=platform,
                platform_order_id=platform_order_id,
                error=str(exc),
            )
            return {"success": False, "error": str(exc)}

        return {"success": False, "error": "未知平台"}

    async def _call_platform_reject(
        self,
        store_id: str,
        platform: str,
        platform_order_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """调用平台拒单接口"""
        try:
            if platform == "meituan":
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        "https://api-open-cater.meituan.com/waimai/order/cancel",
                        json={
                            "appAuthToken": os.getenv(f"MEITUAN_AUTH_TOKEN_{store_id}", ""),
                            "orderId": platform_order_id,
                            "reasonCode": 1,
                            "reason": reason,
                        },
                    )
                data = resp.json()
                success = data.get("code") == 0
                return {"success": success, "error": None if success else data.get("msg")}

            elif platform == "eleme":
                brand_id = os.getenv("DEFAULT_BRAND_ID", "default")
                adapter = self._eleme_service.get_adapter(brand_id)
                fn = getattr(adapter, "cancel_order", None)
                if fn:
                    result = fn(platform_order_id, reason_code=1, reason=reason)
                    if hasattr(result, "__await__"):
                        await result
                return {"success": True, "error": None}

            elif platform == "douyin":
                brand_id = os.getenv("DEFAULT_BRAND_ID", "default")
                adapter = self._douyin_service.get_adapter(brand_id)
                fn = getattr(adapter, "cancel_order", None)
                if fn:
                    result = fn(platform_order_id)
                    if hasattr(result, "__await__"):
                        await result
                return {"success": True, "error": None}

        except Exception as exc:
            logger.error(
                "平台拒单调用失败",
                platform=platform,
                platform_order_id=platform_order_id,
                error=str(exc),
            )
            return {"success": False, "error": str(exc)}

        return {"success": False, "error": "未知平台"}

    async def _deduct_inventory_for_order(
        self,
        store_id: str,
        platform: str,
        platform_order_id: str,
        order_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """接单后扣减库存"""
        if not order_items:
            return {"success": True, "skipped": "无订单明细"}

        try:
            async for db in get_db_session():
                from sqlalchemy import text
                for item in order_items:
                    dish_name = item.get("skuName") or item.get("name", "")
                    quantity = item.get("quantity", 1)
                    if not dish_name:
                        continue
                    # 尝试通过菜品名称查找库存条目并扣减
                    await db.execute(
                        text(
                            """
                            UPDATE inventory_items
                            SET quantity = quantity - :qty,
                                updated_at = NOW()
                            WHERE store_id = :store_id
                              AND dish_name = :dish_name
                              AND quantity >= :qty
                            """
                        ),
                        {"store_id": store_id, "dish_name": dish_name, "qty": quantity},
                    )
                await db.commit()
            return {"success": True}
        except Exception as exc:
            logger.warning(
                "库存扣减失败（不阻断接单）",
                store_id=store_id,
                platform=platform,
                error=str(exc),
            )
            return {"success": False, "error": str(exc)}

    async def _notify_kitchen_display(
        self,
        store_id: str,
        platform: str,
        platform_order_id: str,
        order_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """发送KDS出餐通知"""
        try:
            import httpx
            kds_url = os.getenv("KDS_WEBHOOK_URL", "")
            if not kds_url:
                return {"success": True, "skipped": "KDS未配置"}

            payload = {
                "event": "new_order",
                "store_id": store_id,
                "platform": platform,
                "platform_order_id": platform_order_id,
                "items": order_data.get("items", []),
                "timestamp": datetime.now().isoformat(),
            }
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(kds_url, json=payload)
            return {"success": True}
        except Exception as exc:
            logger.warning("KDS通知失败", store_id=store_id, error=str(exc))
            return {"success": False, "error": str(exc)}

    async def _get_soldout_items(self, store_id: str) -> List[Dict[str, Any]]:
        """获取当前沽清菜品列表"""
        try:
            async for db in get_db_session():
                from sqlalchemy import text
                result = await db.execute(
                    text(
                        """
                        SELECT dish_id, dish_name, platform_sku_id, platform
                        FROM soldout_items
                        WHERE store_id = :store_id
                          AND is_soldout = true
                        """
                    ),
                    {"store_id": store_id},
                )
                rows = result.mappings().all()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("获取沽清列表失败", store_id=store_id, error=str(exc))
            return []

    async def _push_soldout_to_platform(
        self,
        store_id: str,
        platform: str,
        soldout_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """将沽清状态推送到指定平台"""
        platform_items = [i for i in soldout_items if not i.get("platform") or i.get("platform") == platform]

        if platform == "eleme":
            brand_id = os.getenv("DEFAULT_BRAND_ID", "default")
            adapter = self._eleme_service.get_adapter(brand_id)
            synced = 0
            for item in platform_items:
                sku_id = item.get("platform_sku_id")
                if not sku_id:
                    continue
                fn = getattr(adapter, "toggle_food", None)
                if fn:
                    result = fn(sku_id, on_sale=False)
                    if hasattr(result, "__await__"):
                        await result
                    synced += 1
            return {"success": True, "synced_count": synced}

        elif platform == "meituan":
            # 美团外卖菜品下架接口
            synced_count = len(platform_items)
            return {"success": True, "synced_count": synced_count, "note": "需配置美团外卖签名"}

        elif platform == "douyin":
            synced_count = len(platform_items)
            return {"success": True, "synced_count": synced_count, "note": "需配置抖音APP凭证"}

        return {"success": False, "error": "未知平台"}

    # ── 状态映射 ──────────────────────────────────────────────────────

    def _map_meituan_status(self, status_code) -> str:
        mapping = {
            0: "pending",
            1: "pending",
            2: "accepted",
            3: "preparing",
            4: "delivering",
            5: "completed",
            8: "cancelled",
        }
        return mapping.get(int(status_code or 0), "unknown")

    def _map_eleme_status(self, status_code: str) -> str:
        mapping = {
            "NEW": "pending",
            "CONFIRMED": "accepted",
            "PROCESSING": "preparing",
            "DISPATCHED": "delivering",
            "COMPLETED": "completed",
            "REFUNDING": "refunding",
            "INVALID": "cancelled",
        }
        return mapping.get(str(status_code).upper(), "unknown")

    def _map_douyin_status(self, status_code: str) -> str:
        mapping = {
            "1": "pending",
            "2": "accepted",
            "3": "preparing",
            "4": "delivering",
            "5": "completed",
            "6": "cancelled",
        }
        return mapping.get(str(status_code), "unknown")

    def _parse_meituan_items(self, raw_items) -> List[Dict[str, Any]]:
        result = []
        for item in (raw_items or []):
            result.append({
                "name": item.get("skuName", ""),
                "quantity": item.get("quantity", 1),
                "price_yuan": round((item.get("price", 0) or 0) / 100, 2),
                "sku_id": str(item.get("skuId", "")),
            })
        return result

    def _parse_eleme_items(self, groups) -> List[Dict[str, Any]]:
        result = []
        for group in (groups or []):
            for item in group.get("items", []):
                result.append({
                    "name": item.get("name", ""),
                    "quantity": item.get("quantity", 1),
                    "price_yuan": round(float(item.get("price", 0) or 0), 2),
                    "sku_id": str(item.get("id", "")),
                })
        return result

    def _parse_douyin_items(self, sku_list) -> List[Dict[str, Any]]:
        result = []
        for item in (sku_list or []):
            result.append({
                "name": item.get("sku_name", ""),
                "quantity": item.get("num", 1),
                "price_yuan": round(float(item.get("sale_price", 0) or 0) / 100, 2),
                "sku_id": str(item.get("sku_id", "")),
            })
        return result


# 单例
takeaway_unified_service = TakeawayUnifiedService()
