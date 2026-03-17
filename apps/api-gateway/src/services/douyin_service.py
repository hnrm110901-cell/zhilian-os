"""
抖音生活服务集成 Service
提供团购券管理、订单同步、结算查询等业务逻辑
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class DouyinService:
    """抖音生活服务业务层"""

    def get_adapter(self, brand_id: str):
        """
        根据品牌创建抖音适配器实例

        从环境变量读取配置：DOUYIN_APP_ID, DOUYIN_APP_SECRET, DOUYIN_SANDBOX
        """
        import os as _os
        import sys

        # 兼容本地开发和 Docker 容器两种目录布局
        adapter_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../../packages/api-adapters"))
        douyin_src = _os.path.join(adapter_root, "douyin", "src")
        if not _os.path.isdir(douyin_src):
            douyin_src = "/app/packages/api-adapters/douyin/src"
        if douyin_src not in sys.path:
            sys.path.insert(0, douyin_src)

        from adapter import DouyinAdapter

        app_id = os.getenv("DOUYIN_APP_ID", "")
        app_secret = os.getenv("DOUYIN_APP_SECRET", "")
        sandbox = os.getenv("DOUYIN_SANDBOX", "false").lower() == "true"

        if not app_id or not app_secret:
            raise ValueError("缺少 DOUYIN_APP_ID 或 DOUYIN_APP_SECRET 环境变量")

        config = {
            "app_id": app_id,
            "app_secret": app_secret,
            "sandbox": sandbox,
        }
        logger.info("创建抖音适配器", brand_id=brand_id, sandbox=sandbox)
        return DouyinAdapter(config)

    async def sync_orders(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        start_time: str,
        end_time: str,
    ) -> Dict[str, Any]:
        """
        从抖音同步团购订单到本地数据库

        Args:
            db: 数据库 session
            brand_id: 品牌 ID
            store_id: 门店 ID
            start_time: 开始时间 (ISO 格式)
            end_time: 结束时间 (ISO 格式)

        Returns:
            同步结果：synced（新增）、skipped（跳过）、errors（失败）
        """
        adapter = self.get_adapter(brand_id)
        synced = 0
        skipped = 0
        errors = 0

        try:
            page = 1
            while True:
                result = await adapter.query_orders(
                    start_time=start_time,
                    end_time=end_time,
                    page=page,
                    page_size=50,
                )

                orders = result.get("order_list", [])
                if not orders:
                    break

                for order_data in orders:
                    try:
                        order_id = order_data.get("order_id", "")
                        # 检查是否已存在（通过 metadata 中的 douyin_order_id）
                        from src.models.order import Order

                        existing = await db.execute(
                            select(Order).where(
                                Order.external_order_id == f"DOUYIN_{order_id}",
                                Order.store_id == store_id,
                            )
                        )
                        if existing.scalar_one_or_none():
                            skipped += 1
                            continue

                        # 金额：抖音返回分
                        total_fen = int(order_data.get("total_amount", 0))
                        discount_fen = int(order_data.get("discount_amount", 0))
                        final_fen = total_fen - discount_fen

                        order = Order(
                            store_id=store_id,
                            brand_id=brand_id,
                            external_order_id=f"DOUYIN_{order_id}",
                            source="douyin",
                            status=order_data.get("order_status", "completed"),
                            total_amount=total_fen,
                            discount_amount=discount_fen,
                            final_amount=final_fen,
                            order_time=_parse_time(order_data.get("create_time")),
                            items_count=len(order_data.get("sku_list", [])),
                            metadata=order_data,
                        )
                        db.add(order)
                        synced += 1

                    except Exception as e:
                        logger.error("同步单条订单失败", order_id=order_data.get("order_id"), error=str(e))
                        errors += 1

                total = result.get("total", 0)
                if page * 50 >= total:
                    break
                page += 1

            await db.commit()
            logger.info(
                "抖音订单同步完成",
                brand_id=brand_id,
                store_id=store_id,
                synced=synced,
                skipped=skipped,
                errors=errors,
            )

        except Exception as e:
            logger.error("抖音订单同步失败", error=str(e))
            await db.rollback()
            raise
        finally:
            await adapter.close()

        return {"synced": synced, "skipped": skipped, "errors": errors}

    async def verify_coupon(
        self,
        brand_id: str,
        code: str,
        shop_id: str,
    ) -> Dict[str, Any]:
        """
        核销团购券

        Args:
            brand_id: 品牌 ID
            code: 券码
            shop_id: 抖音门店 ID

        Returns:
            核销结果
        """
        adapter = self.get_adapter(brand_id)
        try:
            result = await adapter.verify_coupon(code=code, shop_id=shop_id)
            logger.info("团购券核销成功", brand_id=brand_id, shop_id=shop_id)
            return result
        except Exception as e:
            logger.error("团购券核销失败", error=str(e))
            raise
        finally:
            await adapter.close()

    async def get_coupons(
        self,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        获取团购券列表

        Returns:
            包含 coupon_list 和 total 的字典
        """
        adapter = self.get_adapter(brand_id)
        try:
            result = await adapter.query_coupons(page=page, page_size=page_size)
            return result
        finally:
            await adapter.close()

    async def get_settlements(
        self,
        brand_id: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        获取结算单列表

        Args:
            brand_id: 品牌 ID
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            结算单列表
        """
        adapter = self.get_adapter(brand_id)
        try:
            result = await adapter.query_settlements(
                start_date=start_date,
                end_date=end_date,
            )
            return result
        finally:
            await adapter.close()

    async def get_stats(
        self,
        db: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """
        获取抖音业务统计数据

        Returns:
            order_count: 今日订单数
            revenue_fen: 今日营收（分）
            verified_count: 今日核销数
        """
        from src.models.order import Order

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # 今日抖音订单统计
        order_result = await db.execute(
            select(
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Order.final_amount), 0).label("revenue_fen"),
            ).where(
                Order.brand_id == brand_id,
                Order.source == "douyin",
                Order.order_time >= today_start,
            )
        )
        row = order_result.one()

        # 今日核销数（status 为 verified 的订单）
        verified_result = await db.execute(
            select(func.count(Order.id)).where(
                Order.brand_id == brand_id,
                Order.source == "douyin",
                Order.status == "verified",
                Order.order_time >= today_start,
            )
        )
        verified_count = verified_result.scalar() or 0

        return {
            "order_count": row.order_count or 0,
            "revenue_fen": int(row.revenue_fen or 0),
            "verified_count": verified_count,
        }


def _parse_time(raw: Any) -> Optional[datetime]:
    """解析抖音时间字段（支持时间戳和 ISO 格式）"""
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)) and raw > 1e9:
            return datetime.fromtimestamp(raw)
        return datetime.fromisoformat(str(raw).replace("T", " "))
    except (ValueError, TypeError, OSError):
        return None
