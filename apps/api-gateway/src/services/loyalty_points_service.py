"""
积分与会员等级服务

LoyaltyPointsService — 消费得积分/兑换/升级检查/到期清理

关键约束：
- 所有写操作使用 SELECT FOR UPDATE 防并发
- 流水记录 points_after 时点快照
- lifetime_points（历史累计）只增不减，用于等级判断
- EARN_RATE / REDEEM_RATE 为全局默认值，门店等级配置的 points_rate 在此基础上叠加
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.loyalty_points import (
    LoyaltyAccount,
    MemberLevel,
    MemberLevelConfig,
    PointsChangeReason,
    PointsTransaction,
)


class LoyaltyPointsService:
    """积分与会员等级业务服务"""

    EARN_RATE: int = 1       # 每消费1元（整元）得1积分（默认）
    REDEEM_RATE: int = 100   # 100积分抵1元（即 100积分 = 100分）

    def __init__(self, db: AsyncSession):
        self._db = db

    # ── 核心写操作 ─────────────────────────────────────────────────────────────

    async def earn_points(
        self,
        member_id: str,
        store_id: str,
        order_amount_fen: int,
        order_id: str,
    ) -> dict:
        """
        消费得积分

        1. 获取当前等级的积分倍率（从 MemberLevelConfig）
        2. 计算获得积分 = int(order_amount_fen / 100) * EARN_RATE * level_rate
        3. 更新账户（total_points + lifetime_points）+ 写流水 + 检查升级

        返回:
            points_earned  — 本次获得积分
            total_points   — 当前总积分
            level          — 当前等级
            level_changed  — 是否升级
        """
        if order_amount_fen <= 0:
            raise ValueError(f"订单金额必须大于0，当前: {order_amount_fen}")

        account = await self._get_or_create_account_for_update(member_id, store_id)

        # 获取等级倍率
        level_rate = await self._get_level_rate(store_id, account.member_level)

        # 计算积分（按整元计算，不足1元部分忽略）
        base_earn = int(order_amount_fen / 100) * self.EARN_RATE
        points_earned = max(1, int(base_earn * level_rate)) if base_earn > 0 else 0

        if points_earned == 0:
            return {
                "points_earned": 0,
                "total_points": account.total_points,
                "level": account.member_level,
                "level_changed": False,
            }

        old_level = account.member_level
        account.total_points += points_earned
        account.lifetime_points += points_earned
        account.last_earn_at = datetime.now(timezone.utc).replace(tzinfo=None)
        account.version += 1

        # 写流水
        tx = PointsTransaction(
            account_id=account.id,
            member_id=member_id,
            store_id=store_id,
            points_change=points_earned,
            points_after=account.total_points,
            change_reason=PointsChangeReason.CONSUME_EARN.value,
            order_id=order_id,
            order_amount_fen=order_amount_fen,
            note=f"消费 {order_amount_fen/100:.2f}元 得 {points_earned} 积分（倍率 {level_rate}x）",
        )
        self._db.add(tx)
        await self._db.flush()

        # 检查升级
        new_level = await self.check_and_upgrade_level(account.id)
        level_changed = new_level is not None and new_level != old_level

        return {
            "points_earned": points_earned,
            "total_points": account.total_points,
            "level": account.member_level,
            "level_changed": level_changed,
        }

    async def redeem_points(
        self,
        member_id: str,
        points_to_use: int,
        order_id: str,
    ) -> dict:
        """
        积分兑换（抵扣消费）

        1. 校验积分充足
        2. 计算抵扣金额 = int(points_to_use / REDEEM_RATE) * 100（分）
           即：100积分 = 1元 = 100分
        3. 扣减积分 + 写流水

        返回:
            deduction_fen    — 抵扣金额（分）
            points_used      — 消耗积分数
            points_remaining — 剩余积分
        """
        if points_to_use <= 0:
            raise ValueError(f"兑换积分必须大于0，当前: {points_to_use}")

        # 找会员积分账户（任意一个）
        stmt = (
            select(LoyaltyAccount)
            .where(LoyaltyAccount.member_id == member_id)
            .with_for_update()
            .limit(1)
        )
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            raise ValueError(f"未找到会员 {member_id} 的积分账户")

        if account.total_points < points_to_use:
            raise ValueError(
                f"积分不足，需要 {points_to_use}，当前 {account.total_points}"
            )

        # 计算抵扣金额（分）：100积分 = 1元 = 100分
        deduction_fen = int(points_to_use / self.REDEEM_RATE) * 100

        account.total_points -= points_to_use
        account.last_redeem_at = datetime.now(timezone.utc).replace(tzinfo=None)
        account.version += 1

        tx = PointsTransaction(
            account_id=account.id,
            member_id=member_id,
            store_id=account.store_id,
            points_change=-points_to_use,
            points_after=account.total_points,
            change_reason=PointsChangeReason.REDEEM.value,
            order_id=order_id,
            note=f"兑换 {points_to_use} 积分抵扣 {deduction_fen/100:.2f}元",
        )
        self._db.add(tx)
        await self._db.flush()

        return {
            "deduction_fen": deduction_fen,
            "points_used": points_to_use,
            "points_remaining": account.total_points,
        }

    async def check_and_upgrade_level(self, account_id: uuid.UUID) -> Optional[str]:
        """
        检查会员是否满足升级条件，满足则升级并返回新等级，否则返回 None。

        升级逻辑：遍历所有等级配置（按 min_lifetime_points 降序），
        找到 lifetime_points >= min_lifetime_points 的最高等级。
        """
        # 重新读取账户（可能刚刚更新了 lifetime_points）
        stmt = select(LoyaltyAccount).where(LoyaltyAccount.id == account_id)
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            return None

        # 获取等级配置
        level_configs = await self.get_level_config(account.store_id)
        if not level_configs:
            return None

        # 按门槛降序，找到满足的最高等级
        sorted_configs = sorted(
            level_configs, key=lambda c: c["min_lifetime_points"], reverse=True
        )

        new_level = account.member_level
        for cfg in sorted_configs:
            if account.lifetime_points >= cfg["min_lifetime_points"]:
                new_level = cfg["level"]
                break

        if new_level != account.member_level:
            account.member_level = new_level
            await self._db.flush()
            return new_level

        return None

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def get_account(self, member_id: str) -> dict:
        """
        积分账户 + 当前等级权益

        返回账户基本信息及当前等级对应的所有权益配置。
        """
        stmt = (
            select(LoyaltyAccount)
            .where(LoyaltyAccount.member_id == member_id)
            .limit(1)
        )
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            return {
                "member_id": member_id,
                "total_points": 0,
                "lifetime_points": 0,
                "member_level": MemberLevel.BRONZE.value,
                "level_benefits": {},
            }

        # 获取等级权益
        level_configs = await self.get_level_config(account.store_id)
        level_benefits = next(
            (c for c in level_configs if c["level"] == account.member_level),
            {},
        )

        return {
            "member_id": member_id,
            "store_id": account.store_id,
            "total_points": account.total_points,
            "lifetime_points": account.lifetime_points,
            "member_level": account.member_level,
            "last_earn_at": account.last_earn_at.isoformat() if account.last_earn_at else None,
            "last_redeem_at": account.last_redeem_at.isoformat() if account.last_redeem_at else None,
            "level_benefits": level_benefits,
        }

    async def get_history(
        self,
        member_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """积分流水历史（分页，倒序）"""
        offset = (page - 1) * page_size

        count_stmt = select(PointsTransaction).where(
            PointsTransaction.member_id == member_id
        )
        count_result = await self._db.execute(count_stmt)
        total = len(count_result.scalars().all())

        stmt = (
            select(PointsTransaction)
            .where(PointsTransaction.member_id == member_id)
            .order_by(PointsTransaction.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        items = [
            {
                "id": str(r.id),
                "points_change": r.points_change,
                "points_after": r.points_after,
                "change_reason": r.change_reason,
                "order_id": r.order_id,
                "note": r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── 等级配置 ──────────────────────────────────────────────────────────────

    async def get_level_config(self, store_id: str) -> list:
        """
        获取门店等级配置

        若门店没有自定义配置，返回全局默认配置（store_id='__default__'）。
        若全局配置也不存在，返回硬编码默认值。
        """
        stmt = (
            select(MemberLevelConfig)
            .where(
                MemberLevelConfig.store_id == store_id,
                MemberLevelConfig.is_active == True,  # noqa: E712
            )
            .order_by(MemberLevelConfig.level)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        if rows:
            return [self._level_config_to_dict(r) for r in rows]

        # 降级：返回硬编码默认配置
        return self._default_level_configs()

    async def upsert_level_config(
        self,
        store_id: str,
        level: str,
        config_data: dict,
    ) -> dict:
        """
        创建或更新等级配置（store_id + level 唯一）
        """
        if level not in [e.value for e in MemberLevel]:
            raise ValueError(f"无效等级: {level}，有效值: {[e.value for e in MemberLevel]}")

        stmt = (
            select(MemberLevelConfig)
            .where(
                MemberLevelConfig.store_id == store_id,
                MemberLevelConfig.level == level,
            )
        )
        result = await self._db.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            config = MemberLevelConfig(store_id=store_id, level=level)
            self._db.add(config)

        # 更新字段
        if "level_name" in config_data:
            config.level_name = config_data["level_name"]
        if "min_lifetime_points" in config_data:
            config.min_lifetime_points = config_data["min_lifetime_points"]
        if "points_rate" in config_data:
            config.points_rate = float(config_data["points_rate"])
        if "discount_rate" in config_data:
            config.discount_rate = float(config_data["discount_rate"])
        if "birthday_bonus" in config_data:
            config.birthday_bonus = int(config_data["birthday_bonus"])
        if "priority_reservation" in config_data:
            config.priority_reservation = bool(config_data["priority_reservation"])
        if "is_active" in config_data:
            config.is_active = bool(config_data["is_active"])

        await self._db.flush()
        return self._level_config_to_dict(config)

    # ── 批量维护 ──────────────────────────────────────────────────────────────

    async def expire_old_points(self, inactive_days: int = 365) -> int:
        """
        清理超过 N 天未活动的积分（批量过期）

        判断条件：last_earn_at 超过 inactive_days 天未更新（或从未获得积分）。
        过期操作：将 total_points 清零并写过期流水。

        返回：处理账户数量
        """
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=inactive_days)

        stmt = (
            select(LoyaltyAccount)
            .where(
                LoyaltyAccount.total_points > 0,
                (LoyaltyAccount.last_earn_at < cutoff)
                | (LoyaltyAccount.last_earn_at == None),  # noqa: E711
            )
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        accounts = result.scalars().all()

        count = 0
        for account in accounts:
            expired_points = account.total_points
            account.total_points = 0
            account.version += 1

            tx = PointsTransaction(
                account_id=account.id,
                member_id=account.member_id,
                store_id=account.store_id,
                points_change=-expired_points,
                points_after=0,
                change_reason=PointsChangeReason.EXPIRE.value,
                note=f"超过 {inactive_days} 天未活动，积分过期",
            )
            self._db.add(tx)
            count += 1

        if count > 0:
            await self._db.flush()

        return count

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    async def _get_level_rate(self, store_id: str, level: str) -> float:
        """获取指定等级的积分倍率"""
        level_configs = await self.get_level_config(store_id)
        for cfg in level_configs:
            if cfg["level"] == level:
                return cfg.get("points_rate", 1.0)
        return 1.0

    async def _get_or_create_account_for_update(
        self, member_id: str, store_id: str
    ) -> LoyaltyAccount:
        """
        获取积分账户（SELECT FOR UPDATE），不存在则创建。
        """
        stmt = (
            select(LoyaltyAccount)
            .where(
                LoyaltyAccount.member_id == member_id,
                LoyaltyAccount.store_id == store_id,
            )
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            account = LoyaltyAccount(
                member_id=member_id,
                store_id=store_id,
                total_points=0,
                lifetime_points=0,
                member_level=MemberLevel.BRONZE.value,
            )
            self._db.add(account)
            await self._db.flush()

        return account

    @staticmethod
    def _level_config_to_dict(config: MemberLevelConfig) -> dict:
        return {
            "id": str(config.id),
            "store_id": config.store_id,
            "level": config.level,
            "level_name": config.level_name,
            "min_lifetime_points": config.min_lifetime_points,
            "points_rate": config.points_rate,
            "discount_rate": config.discount_rate,
            "birthday_bonus": config.birthday_bonus,
            "priority_reservation": config.priority_reservation,
            "is_active": config.is_active,
        }

    @staticmethod
    def _default_level_configs() -> list:
        """硬编码默认等级配置（无数据库配置时的降级方案）"""
        return [
            {
                "level": MemberLevel.BRONZE.value,
                "level_name": "铜牌会员",
                "min_lifetime_points": 0,
                "points_rate": 1.0,
                "discount_rate": 1.0,
                "birthday_bonus": 50,
                "priority_reservation": False,
                "is_active": True,
            },
            {
                "level": MemberLevel.SILVER.value,
                "level_name": "银牌会员",
                "min_lifetime_points": 500,
                "points_rate": 1.2,
                "discount_rate": 0.98,
                "birthday_bonus": 100,
                "priority_reservation": False,
                "is_active": True,
            },
            {
                "level": MemberLevel.GOLD.value,
                "level_name": "金牌会员",
                "min_lifetime_points": 2000,
                "points_rate": 1.5,
                "discount_rate": 0.95,
                "birthday_bonus": 200,
                "priority_reservation": False,
                "is_active": True,
            },
            {
                "level": MemberLevel.PLATINUM.value,
                "level_name": "铂金会员",
                "min_lifetime_points": 5000,
                "points_rate": 2.0,
                "discount_rate": 0.92,
                "birthday_bonus": 500,
                "priority_reservation": True,
                "is_active": True,
            },
            {
                "level": MemberLevel.DIAMOND.value,
                "level_name": "钻石会员",
                "min_lifetime_points": 20000,
                "points_rate": 3.0,
                "discount_rate": 0.88,
                "birthday_bonus": 1000,
                "priority_reservation": True,
                "is_active": True,
            },
        ]
