"""
BrandConsumerProfileRepo — 品牌维度消费档案 Repository

提供：
- upsert_profile     : 创建或更新品牌消费档案（INSERT ON CONFLICT DO UPDATE）
- get_by_consumer_and_brand : 获取单条档案
- get_one_id_view    : 获取消费者在同一集团内的跨品牌全景聚合视图
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

import structlog
from sqlalchemy import and_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.brand_consumer_profile import BrandConsumerProfile

logger = structlog.get_logger()


class BrandConsumerProfileRepo:
    """品牌消费档案 Repository

    所有方法均要求显式传入 group_id / brand_id，不依赖隐式上下文，
    遵循「所有新增数据库查询必须传入显式租户ID」的约束。
    """

    @staticmethod
    async def upsert_profile(
        session: AsyncSession,
        consumer_id: uuid.UUID,
        brand_id: str,
        group_id: str,
        **kwargs: Any,
    ) -> BrandConsumerProfile:
        """
        创建或更新品牌消费档案（基于 UNIQUE(consumer_id, brand_id) 冲突键）。

        冲突时：更新 kwargs 中提供的字段 + updated_at。
        新建时：以 kwargs 为初始值创建记录。

        Args:
            session    : 异步 SQLAlchemy Session
            consumer_id: One ID 锚点（consumer_identities.id）
            brand_id   : 品牌ID
            group_id   : 集团ID（必须显式传入，不从上下文推断）
            **kwargs   : 其他可选字段（brand_level / brand_points / lifecycle_state 等）

        Returns:
            更新后的 BrandConsumerProfile 实例

        Raises:
            ValueError: 如果 consumer_id / brand_id / group_id 为空
        """
        if not consumer_id or not brand_id or not group_id:
            raise ValueError(
                "consumer_id, brand_id, group_id 均为必填字段，不得为空"
            )

        now = datetime.utcnow()

        # 构建插入数据
        insert_data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "group_id": group_id,
            "created_at": now,
            "updated_at": now,
            **kwargs,
        }

        # 冲突时可更新的字段（排除主键和不可变身份字段）
        _immutable = {"id", "consumer_id", "brand_id", "group_id", "created_at"}
        update_data: dict[str, Any] = {
            k: v for k, v in insert_data.items() if k not in _immutable
        }
        update_data["updated_at"] = now  # 强制更新时间戳

        stmt = (
            pg_insert(BrandConsumerProfile)
            .values(**insert_data)
            .on_conflict_do_update(
                constraint="uq_brand_consumer_profile_consumer_brand",
                set_=update_data,
            )
            .returning(BrandConsumerProfile)
        )

        result = await session.execute(stmt)
        profile = result.scalar_one()

        logger.info(
            "BrandConsumerProfile upserted",
            consumer_id=str(consumer_id),
            brand_id=brand_id,
            group_id=group_id,
        )
        return profile

    @staticmethod
    async def get_by_consumer_and_brand(
        session: AsyncSession,
        consumer_id: uuid.UUID,
        brand_id: str,
    ) -> Optional[BrandConsumerProfile]:
        """
        获取某消费者在某品牌的单条档案。

        Args:
            session    : 异步 SQLAlchemy Session
            consumer_id: One ID 锚点
            brand_id   : 品牌ID

        Returns:
            BrandConsumerProfile 或 None（若不存在）
        """
        result = await session.execute(
            select(BrandConsumerProfile).where(
                and_(
                    BrandConsumerProfile.consumer_id == consumer_id,
                    BrandConsumerProfile.brand_id == brand_id,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_one_id_view(
        session: AsyncSession,
        consumer_id: uuid.UUID,
        group_id: str,
    ) -> dict[str, Any]:
        """
        获取消费者在同一集团内的跨品牌全景聚合视图（One ID 视图）。

        聚合内容：
        - 各品牌档案列表
        - 集团维度总计（总订单数、总消费金额、总积分、总余额）
        - 最早/最近消费时间
        - 最高品牌等级
        - 活跃品牌数

        Args:
            session    : 异步 SQLAlchemy Session
            consumer_id: One ID 锚点
            group_id   : 集团ID（必须显式传入）

        Returns:
            {
              "consumer_id": str,
              "group_id": str,
              "brand_profiles": [...],   # 各品牌档案列表
              "summary": {               # 集团维度聚合
                "total_order_count": int,
                "total_order_amount_fen": int,
                "total_points": int,
                "total_balance_fen": int,
                "first_order_at": datetime | None,
                "last_order_at": datetime | None,
                "active_brand_count": int,
                "highest_level": str,
              }
            }
        """
        if not consumer_id or not group_id:
            raise ValueError("consumer_id 和 group_id 均为必填字段")

        result = await session.execute(
            select(BrandConsumerProfile).where(
                and_(
                    BrandConsumerProfile.consumer_id == consumer_id,
                    BrandConsumerProfile.group_id == group_id,
                    BrandConsumerProfile.is_active.is_(True),
                )
            ).order_by(BrandConsumerProfile.brand_id)
        )
        profiles = list(result.scalars().all())

        # 构建品牌档案列表
        brand_profiles = []
        for p in profiles:
            brand_profiles.append(
                {
                    "brand_id": p.brand_id,
                    "brand_member_no": p.brand_member_no,
                    "brand_level": p.brand_level,
                    "brand_points": p.brand_points,
                    "brand_balance_fen": p.brand_balance_fen,
                    "brand_order_count": p.brand_order_count,
                    "brand_order_amount_fen": p.brand_order_amount_fen,
                    "brand_first_order_at": p.brand_first_order_at,
                    "brand_last_order_at": p.brand_last_order_at,
                    "lifecycle_state": p.lifecycle_state,
                    "registration_channel": p.registration_channel,
                }
            )

        # 集团维度聚合
        _level_rank = {"普通": 0, "银卡": 1, "金卡": 2, "钻石": 3}
        highest_level = "普通"
        highest_rank = -1

        total_order_count = 0
        total_order_amount_fen = 0
        total_points = 0
        total_balance_fen = 0
        first_order_at: Optional[datetime] = None
        last_order_at: Optional[datetime] = None

        for p in profiles:
            total_order_count += p.brand_order_count or 0
            total_order_amount_fen += p.brand_order_amount_fen or 0
            total_points += p.brand_points or 0
            total_balance_fen += p.brand_balance_fen or 0

            if p.brand_first_order_at:
                if first_order_at is None or p.brand_first_order_at < first_order_at:
                    first_order_at = p.brand_first_order_at

            if p.brand_last_order_at:
                if last_order_at is None or p.brand_last_order_at > last_order_at:
                    last_order_at = p.brand_last_order_at

            rank = _level_rank.get(p.brand_level or "普通", 0)
            if rank > highest_rank:
                highest_rank = rank
                highest_level = p.brand_level or "普通"

        logger.debug(
            "One ID view built",
            consumer_id=str(consumer_id),
            group_id=group_id,
            brand_count=len(profiles),
        )

        return {
            "consumer_id": str(consumer_id),
            "group_id": group_id,
            "brand_profiles": brand_profiles,
            "summary": {
                "total_order_count": total_order_count,
                "total_order_amount_fen": total_order_amount_fen,
                "total_points": total_points,
                "total_balance_fen": total_balance_fen,
                "first_order_at": first_order_at,
                "last_order_at": last_order_at,
                "active_brand_count": len(profiles),
                "highest_level": highest_level,
            },
        }
