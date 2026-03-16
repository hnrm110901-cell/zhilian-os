"""
IdentityResolutionService — CDP 身份解析核心服务（Sprint 1）

CDP宪法：
1. 任何消费者记录必须经 resolve() 获取 consumer_id
2. consumer_id 不可修改，只能 merge()
3. 所有渠道消费行为必须归因到 consumer_id

核心方法：
- resolve(phone, **hints) → consumer_id   找到或创建统一身份
- merge(winner_id, loser_id)              合并两个身份（loser 标记 is_merged）
- backfill_orders(store_id)               回填存量订单的 consumer_id
- refresh_profile(consumer_id)            刷新聚合统计
"""

import logging
import uuid as uuid_mod
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_id_mapping import ConsumerIdMapping, IdType
from src.models.consumer_identity import ConsumerIdentity

logger = logging.getLogger(__name__)


class IdentityResolutionService:
    """CDP 身份解析服务 — 全系统单例"""

    # ------------------------------------------------------------------ #
    #  resolve() — 最核心方法，所有渠道调用此方法获取 consumer_id
    # ------------------------------------------------------------------ #
    async def resolve(
        self,
        db: AsyncSession,
        phone: str,
        *,
        store_id: Optional[str] = None,
        wechat_openid: Optional[str] = None,
        wechat_unionid: Optional[str] = None,
        pos_member_id: Optional[str] = None,
        source: str = "unknown",
        display_name: Optional[str] = None,
    ) -> uuid_mod.UUID:
        """
        根据手机号（必填）+ 可选 hints 解析或创建统一 consumer_id。

        策略：
        1. 先按 phone 查 ConsumerIdentity（is_merged=False）
        2. 如果找到 → 补充 hints（wechat_openid 等），返回 id
        3. 如果未找到 → 新建 ConsumerIdentity + phone mapping，返回新 id
        4. 同时为提供的 hints 创建/更新 ConsumerIdMapping

        返回：consumer_id (UUID)
        """
        phone = phone.strip()
        if not phone:
            raise ValueError("phone is required for identity resolution")

        # Step 1: 按手机号查找
        consumer = await self._find_by_phone(db, phone)

        if consumer is None:
            # Step 2: 新建
            consumer = ConsumerIdentity(
                primary_phone=phone,
                display_name=display_name,
                source=source,
            )
            if wechat_openid:
                consumer.wechat_openid = wechat_openid
            if wechat_unionid:
                consumer.wechat_unionid = wechat_unionid
            db.add(consumer)
            await db.flush()  # 拿到 consumer.id

            # 创建 phone mapping
            await self._upsert_mapping(
                db,
                consumer.id,
                IdType.PHONE,
                phone,
                store_id=store_id,
                source_system=source,
            )
            logger.info("CDP: 新建 consumer_id=%s phone=%s source=%s", consumer.id, phone, source)
        else:
            # Step 3: 补充信息
            updated = False
            if wechat_openid and not consumer.wechat_openid:
                consumer.wechat_openid = wechat_openid
                updated = True
            if wechat_unionid and not consumer.wechat_unionid:
                consumer.wechat_unionid = wechat_unionid
                updated = True
            if display_name and not consumer.display_name:
                consumer.display_name = display_name
                updated = True
            if updated:
                await db.flush()

        # Step 4: 为额外 hints 创建映射
        if wechat_openid:
            await self._upsert_mapping(
                db,
                consumer.id,
                IdType.WECHAT_OPENID,
                wechat_openid,
                store_id=store_id,
                source_system=source,
            )
        if wechat_unionid:
            await self._upsert_mapping(
                db,
                consumer.id,
                IdType.WECHAT_UNIONID,
                wechat_unionid,
                store_id=store_id,
                source_system=source,
            )
        if pos_member_id:
            await self._upsert_mapping(
                db,
                consumer.id,
                IdType.POS_MEMBER_ID,
                pos_member_id,
                store_id=store_id,
                source_system=source,
            )

        return consumer.id

    # ------------------------------------------------------------------ #
    #  resolve_by_external_id() — 按外部ID反查 consumer_id
    # ------------------------------------------------------------------ #
    async def resolve_by_external_id(
        self,
        db: AsyncSession,
        id_type: str,
        external_id: str,
    ) -> Optional[uuid_mod.UUID]:
        """按外部ID查找 consumer_id，未找到返回 None"""
        stmt = select(ConsumerIdMapping.consumer_id).where(
            ConsumerIdMapping.id_type == id_type,
            ConsumerIdMapping.external_id == external_id,
            ConsumerIdMapping.is_active.is_(True),
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    # ------------------------------------------------------------------ #
    #  merge() — 合并两个消费者身份
    # ------------------------------------------------------------------ #
    async def merge(
        self,
        db: AsyncSession,
        winner_id: uuid_mod.UUID,
        loser_id: uuid_mod.UUID,
    ) -> uuid_mod.UUID:
        """
        将 loser 合并到 winner。

        操作：
        1. loser.is_merged = True, merged_into = winner_id
        2. loser 的所有 ConsumerIdMapping 迁移到 winner
        3. loser 的聚合统计累加到 winner
        4. 所有引用 loser 的 order/reservation/queue 的 consumer_id 更新为 winner

        返回：winner_id
        """
        if winner_id == loser_id:
            return winner_id

        # 加载 winner 和 loser
        winner = await db.get(ConsumerIdentity, winner_id)
        loser = await db.get(ConsumerIdentity, loser_id)
        if not winner:
            raise ValueError(f"winner consumer_id={winner_id} not found")
        if not loser:
            raise ValueError(f"loser consumer_id={loser_id} not found")
        if loser.is_merged:
            raise ValueError(f"loser consumer_id={loser_id} already merged")

        # 1. 标记 loser 为已合并
        loser.is_merged = True
        loser.merged_into = winner_id
        loser.merged_at = datetime.utcnow()

        # 2. 迁移 mapping
        await db.execute(
            update(ConsumerIdMapping).where(ConsumerIdMapping.consumer_id == loser_id).values(consumer_id=winner_id)
        )

        # 3. 累加聚合统计
        winner.total_order_count = (winner.total_order_count or 0) + (loser.total_order_count or 0)
        winner.total_order_amount_fen = (winner.total_order_amount_fen or 0) + (loser.total_order_amount_fen or 0)
        winner.total_reservation_count = (winner.total_reservation_count or 0) + (loser.total_reservation_count or 0)
        if loser.first_order_at and (not winner.first_order_at or loser.first_order_at < winner.first_order_at):
            winner.first_order_at = loser.first_order_at
            winner.first_store_id = loser.first_store_id
        if loser.last_order_at and (not winner.last_order_at or loser.last_order_at > winner.last_order_at):
            winner.last_order_at = loser.last_order_at

        # 4. 更新 orders/reservations/queues 中的 consumer_id
        # 使用 text import 延迟，避免循环导入
        from src.models.order import Order
        from src.models.queue import Queue
        from src.models.reservation import Reservation

        for model in [Order, Reservation, Queue]:
            if hasattr(model, "consumer_id"):
                await db.execute(update(model).where(model.consumer_id == loser_id).values(consumer_id=winner_id))

        await db.flush()
        logger.info("CDP: merge loser=%s → winner=%s", loser_id, winner_id)
        return winner_id

    # ------------------------------------------------------------------ #
    #  backfill_orders() — 回填存量订单的 consumer_id
    # ------------------------------------------------------------------ #
    async def backfill_orders(
        self,
        db: AsyncSession,
        store_id: str,
        batch_size: int = 500,
    ) -> dict:
        """
        回填指定门店存量订单的 consumer_id。

        逻辑：
        1. 查找 consumer_id IS NULL 且 customer_phone IS NOT NULL 的订单
        2. 批量 resolve → 更新 consumer_id

        返回：{"total": N, "resolved": M, "failed": K}
        """
        from src.models.order import Order

        # 查询待回填订单
        stmt = (
            select(Order.id, Order.customer_phone, Order.customer_name)
            .where(
                Order.store_id == store_id,
                Order.consumer_id.is_(None),
                Order.customer_phone.isnot(None),
                Order.customer_phone != "",
            )
            .limit(batch_size)
        )
        result = await db.execute(stmt)
        rows = result.all()

        total = len(rows)
        resolved = 0
        failed = 0

        for order_id, phone, name in rows:
            try:
                consumer_id = await self.resolve(
                    db,
                    phone,
                    store_id=store_id,
                    source="backfill",
                    display_name=name,
                )
                await db.execute(update(Order).where(Order.id == order_id).values(consumer_id=consumer_id))
                resolved += 1
            except Exception as e:
                logger.warning("CDP backfill order=%s failed: %s", order_id, e)
                failed += 1

        await db.flush()
        logger.info(
            "CDP backfill store=%s: total=%d resolved=%d failed=%d",
            store_id,
            total,
            resolved,
            failed,
        )
        return {"total": total, "resolved": resolved, "failed": failed}

    # ------------------------------------------------------------------ #
    #  backfill_reservations() — 回填存量预订的 consumer_id
    # ------------------------------------------------------------------ #
    async def backfill_reservations(
        self,
        db: AsyncSession,
        store_id: str,
        batch_size: int = 500,
    ) -> dict:
        """回填指定门店存量预订的 consumer_id"""
        from src.models.reservation import Reservation

        stmt = (
            select(Reservation.id, Reservation.customer_phone, Reservation.customer_name)
            .where(
                Reservation.store_id == store_id,
                Reservation.consumer_id.is_(None),
                Reservation.customer_phone.isnot(None),
                Reservation.customer_phone != "",
            )
            .limit(batch_size)
        )
        result = await db.execute(stmt)
        rows = result.all()

        total = len(rows)
        resolved = 0
        failed = 0

        for res_id, phone, name in rows:
            try:
                consumer_id = await self.resolve(
                    db,
                    phone,
                    store_id=store_id,
                    source="backfill",
                    display_name=name,
                )
                await db.execute(update(Reservation).where(Reservation.id == res_id).values(consumer_id=consumer_id))
                resolved += 1
            except Exception as e:
                logger.warning("CDP backfill reservation=%s failed: %s", res_id, e)
                failed += 1

        await db.flush()
        return {"total": total, "resolved": resolved, "failed": failed}

    # ------------------------------------------------------------------ #
    #  refresh_profile() — 刷新消费者聚合统计
    # ------------------------------------------------------------------ #
    async def refresh_profile(
        self,
        db: AsyncSession,
        consumer_id: uuid_mod.UUID,
    ) -> None:
        """从 orders 表重新计算聚合统计并更新 ConsumerIdentity"""
        from src.models.order import Order

        stmt = select(
            func.count(Order.id).label("cnt"),
            func.sum(Order.total_amount).label("total_yuan"),
            func.min(Order.order_time).label("first_at"),
            func.max(Order.order_time).label("last_at"),
        ).where(
            Order.consumer_id == consumer_id,
            Order.status != "cancelled",
        )
        result = await db.execute(stmt)
        row = result.one()

        consumer = await db.get(ConsumerIdentity, consumer_id)
        if not consumer:
            return

        consumer.total_order_count = row.cnt or 0
        # total_amount 在 DB 中是 yuan (Numeric)，转为分存储
        total_yuan = row.total_yuan or 0
        consumer.total_order_amount_fen = int(float(total_yuan) * 100)
        consumer.first_order_at = row.first_at
        consumer.last_order_at = row.last_at

        # RFM 快照
        if row.last_at:
            consumer.rfm_recency_days = (datetime.utcnow() - row.last_at).days
        consumer.rfm_frequency = row.cnt or 0
        consumer.rfm_monetary_fen = consumer.total_order_amount_fen

        await db.flush()

    # ------------------------------------------------------------------ #
    #  get_consumer() — 查询消费者详情
    # ------------------------------------------------------------------ #
    async def get_consumer(
        self,
        db: AsyncSession,
        consumer_id: uuid_mod.UUID,
    ) -> Optional[ConsumerIdentity]:
        """获取消费者详情（含 id_mappings）"""
        return await db.get(ConsumerIdentity, consumer_id)

    async def get_consumer_by_phone(
        self,
        db: AsyncSession,
        phone: str,
    ) -> Optional[ConsumerIdentity]:
        """按手机号查找活跃消费者"""
        return await self._find_by_phone(db, phone)

    # ------------------------------------------------------------------ #
    #  统计
    # ------------------------------------------------------------------ #
    async def get_stats(self, db: AsyncSession) -> dict:
        """返回 CDP 基础统计"""
        total = await db.scalar(select(func.count(ConsumerIdentity.id)).where(ConsumerIdentity.is_merged.is_(False)))
        merged = await db.scalar(select(func.count(ConsumerIdentity.id)).where(ConsumerIdentity.is_merged.is_(True)))
        mappings = await db.scalar(select(func.count(ConsumerIdMapping.id)).where(ConsumerIdMapping.is_active.is_(True)))
        return {
            "total_consumers": total or 0,
            "merged_count": merged or 0,
            "active_mappings": mappings or 0,
        }

    # ------------------------------------------------------------------ #
    #  内部辅助
    # ------------------------------------------------------------------ #
    async def _find_by_phone(
        self,
        db: AsyncSession,
        phone: str,
    ) -> Optional[ConsumerIdentity]:
        """按手机号查找未合并的消费者"""
        stmt = select(ConsumerIdentity).where(
            ConsumerIdentity.primary_phone == phone,
            ConsumerIdentity.is_merged.is_(False),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _upsert_mapping(
        self,
        db: AsyncSession,
        consumer_id: uuid_mod.UUID,
        id_type: IdType,
        external_id: str,
        *,
        store_id: Optional[str] = None,
        source_system: Optional[str] = None,
    ) -> None:
        """插入或更新 ID 映射（PostgreSQL ON CONFLICT DO UPDATE）"""
        stmt = (
            pg_insert(ConsumerIdMapping)
            .values(
                consumer_id=consumer_id,
                id_type=id_type.value if isinstance(id_type, IdType) else id_type,
                external_id=external_id,
                store_id=store_id,
                source_system=source_system,
                is_active=True,
            )
            .on_conflict_do_update(
                constraint="uq_id_type_external_id",
                set_={
                    "consumer_id": consumer_id,
                    "is_active": True,
                    "store_id": store_id,
                    "source_system": source_system,
                },
            )
        )
        await db.execute(stmt)


# 全局单例
identity_resolution_service = IdentityResolutionService()
