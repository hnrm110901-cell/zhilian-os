"""
CDP Sync Service — POS订单同步后自动 resolve consumer_id

Sprint 1 地基层：
- POS 每5分钟同步订单后，触发此服务为新订单 resolve consumer_id
- 也支持全量回填（backfill）模式

调用方式：
1. Celery 定时任务（每5分钟，紧跟 POS 同步之后）
2. 手动触发 API（/api/v1/cdp/backfill/orders）
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.order import Order
from src.models.queue import Queue
from src.models.reservation import Reservation
from src.services.identity_resolution_service import identity_resolution_service

logger = logging.getLogger(__name__)


class CDPSyncService:
    """CDP 同步服务 — 为POS导入的订单自动解析 consumer_id"""

    async def sync_store_orders(
        self,
        db: AsyncSession,
        store_id: str,
        batch_size: int = 500,
    ) -> dict:
        """
        为指定门店的新订单（consumer_id IS NULL）解析 consumer_id

        返回：{"total": N, "resolved": M, "failed": K, "skipped": S}
        """
        result = await identity_resolution_service.backfill_orders(
            db,
            store_id,
            batch_size=batch_size,
        )
        # 额外统计跳过的（无手机号）
        skipped = await db.scalar(
            select(func.count(Order.id)).where(
                Order.store_id == store_id,
                Order.consumer_id.is_(None),
                (Order.customer_phone.is_(None) | (Order.customer_phone == "")),
            )
        )
        result["skipped"] = skipped or 0
        return result

    async def sync_store_reservations(
        self,
        db: AsyncSession,
        store_id: str,
        batch_size: int = 500,
    ) -> dict:
        """为指定门店的新预订解析 consumer_id"""
        return await identity_resolution_service.backfill_reservations(
            db,
            store_id,
            batch_size=batch_size,
        )

    async def sync_all_stores(
        self,
        db: AsyncSession,
        batch_size: int = 500,
    ) -> dict:
        """
        遍历所有门店，回填 consumer_id。
        适用于 Celery 定时任务。
        """
        # 获取有未解析订单的门店列表
        stmt = (
            select(Order.store_id)
            .where(
                Order.consumer_id.is_(None),
                Order.customer_phone.isnot(None),
                Order.customer_phone != "",
            )
            .group_by(Order.store_id)
        )
        result = await db.execute(stmt)
        store_ids = [row[0] for row in result.all()]

        total_stats = {"stores": 0, "total": 0, "resolved": 0, "failed": 0}
        for sid in store_ids:
            try:
                r = await self.sync_store_orders(db, sid, batch_size=batch_size)
                total_stats["stores"] += 1
                total_stats["total"] += r.get("total", 0)
                total_stats["resolved"] += r.get("resolved", 0)
                total_stats["failed"] += r.get("failed", 0)
            except Exception as e:
                logger.warning("CDP sync store=%s failed: %s", sid, e)
                total_stats["failed"] += 1

        await db.flush()
        logger.info("CDP sync_all_stores: %s", total_stats)
        return total_stats

    async def get_fill_rate(self, db: AsyncSession, store_id: Optional[str] = None) -> dict:
        """
        计算 consumer_id 填充率（Sprint 1 KPI：≥80%）

        返回：
        {
            "orders": {"total": N, "filled": M, "rate": 0.85},
            "reservations": {"total": N, "filled": M, "rate": 0.90},
            "queues": {"total": N, "filled": M, "rate": 0.75},
        }
        """
        results = {}
        # Queue 的主键是 queue_id 而非 id
        pk_map = {
            "orders": Order.id,
            "reservations": Reservation.id,
            "queues": Queue.queue_id,
        }
        for model, name in [
            (Order, "orders"),
            (Reservation, "reservations"),
            (Queue, "queues"),
        ]:
            pk_col = pk_map[name]

            # total
            total_q = select(func.count(pk_col))
            if store_id:
                total_q = total_q.where(model.store_id == store_id)
            total = await db.scalar(total_q) or 0

            # filled (consumer_id IS NOT NULL)
            filled_q = select(func.count(pk_col)).where(model.consumer_id.isnot(None))
            if store_id:
                filled_q = filled_q.where(model.store_id == store_id)
            filled = await db.scalar(filled_q) or 0

            rate = round(filled / total, 4) if total > 0 else 0.0
            results[name] = {"total": total, "filled": filled, "rate": rate}

        return results


# 全局单例
cdp_sync_service = CDPSyncService()
