"""
储值卡服务

StoredValueService — 充值/消费/退款/查询/活动管理

关键约束：
- 所有写操作使用 SELECT FOR UPDATE（行级锁）防止并发超扣
- 流水记录 balance_after 时点快照
- 金额统一用分（Integer），服务层不做元/分转换（调用方负责）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.stored_value import (
    RechargePromotion,
    StoredValueAccount,
    StoredValueTransaction,
    TransactionType,
)


class StoredValueService:
    """储值卡业务服务"""

    def __init__(self, db: AsyncSession):
        self._db = db

    # ── 核心写操作 ─────────────────────────────────────────────────────────────

    async def recharge(
        self,
        member_id: str,
        store_id: str,
        amount_fen: int,
        payment_method: str,
        operator_id: str,
    ) -> dict:
        """
        充值

        1. 查找最优赠送规则（gift_amount 最大的活跃规则）
        2. 计算赠送金额（固定赠送 + 比例赠送）
        3. SELECT FOR UPDATE 锁定账户行防并发
        4. 在同一事务内：更新账户余额 + 写流水

        返回:
            balance_fen       — 充值后本金余额（分）
            gift_balance_fen  — 充值后赠送金余额（分）
            recharged_fen     — 本次充值本金（分）
            gifted_fen        — 本次赠送金额（分）
        """
        if amount_fen <= 0:
            raise ValueError(f"充值金额必须大于0，当前: {amount_fen}")

        # 查找最优赠送规则
        promotion = await self._find_best_promotion(store_id, amount_fen)
        gifted_fen = 0
        promotion_id = None

        if promotion:
            gifted_fen = promotion["gift_amount_fen"]
            promotion_id = promotion["id"]

        # 获取或创建账户（SELECT FOR UPDATE）
        account = await self._get_or_create_account_for_update(member_id, store_id)

        # 更新余额
        account.balance_fen += amount_fen
        account.gift_balance_fen += gifted_fen
        account.last_recharge_at = datetime.now(timezone.utc).replace(tzinfo=None)
        account.version += 1

        # 写充值本金流水
        recharge_tx = StoredValueTransaction(
            account_id=account.id,
            member_id=member_id,
            store_id=store_id,
            transaction_type=TransactionType.RECHARGE.value,
            amount_fen=amount_fen,
            gift_amount_fen=0,
            balance_after=account.balance_fen,
            gift_balance_after=account.gift_balance_fen,
            payment_method=payment_method,
            operator_id=operator_id,
            promotion_id=promotion_id,
            note=f"充值 {amount_fen/100:.2f}元",
        )
        self._db.add(recharge_tx)

        # 写赠送金流水
        if gifted_fen > 0:
            gift_tx = StoredValueTransaction(
                account_id=account.id,
                member_id=member_id,
                store_id=store_id,
                transaction_type=TransactionType.GIFT.value,
                amount_fen=0,
                gift_amount_fen=gifted_fen,
                balance_after=account.balance_fen,
                gift_balance_after=account.gift_balance_fen,
                payment_method=payment_method,
                operator_id=operator_id,
                promotion_id=promotion_id,
                note=f"充值赠送 {gifted_fen/100:.2f}元",
            )
            self._db.add(gift_tx)

        await self._db.flush()

        return {
            "balance_fen": account.balance_fen,
            "gift_balance_fen": account.gift_balance_fen,
            "recharged_fen": amount_fen,
            "gifted_fen": gifted_fen,
        }

    async def consume(
        self,
        member_id: str,
        store_id: str,
        amount_fen: int,
        order_id: str,
        use_gift_first: bool = True,
    ) -> dict:
        """
        消费扣款

        1. 校验余额充足（本金 + 赠送金合计）
        2. use_gift_first=True 时，先扣赠送金再扣本金
        3. SELECT FOR UPDATE 锁账户，原子事务更新 + 写流水
        4. 余额不足时 raise ValueError

        返回:
            balance_fen          — 消费后本金余额（分）
            gift_balance_fen     — 消费后赠送金余额（分）
            deducted_fen         — 本次扣除总金额（分）
            deducted_gift_fen    — 其中赠送金扣除部分（分）
            deducted_balance_fen — 其中本金扣除部分（分）
        """
        if amount_fen <= 0:
            raise ValueError(f"消费金额必须大于0，当前: {amount_fen}")

        account = await self._get_or_create_account_for_update(member_id, store_id)

        total_available = account.balance_fen + account.gift_balance_fen
        if total_available < amount_fen:
            total_yuan = total_available / 100
            raise ValueError(f"余额不足，当前余额: {total_yuan:.2f}元")

        if account.is_frozen:
            raise ValueError("账户已冻结，无法消费")

        # 计算扣减逻辑
        remaining = amount_fen
        deducted_gift_fen = 0
        deducted_balance_fen = 0

        if use_gift_first and account.gift_balance_fen > 0:
            deducted_gift_fen = min(account.gift_balance_fen, remaining)
            remaining -= deducted_gift_fen

        deducted_balance_fen = remaining

        # 更新账户
        account.gift_balance_fen -= deducted_gift_fen
        account.balance_fen -= deducted_balance_fen
        account.last_consume_at = datetime.now(timezone.utc).replace(tzinfo=None)
        account.version += 1

        # 写消费流水
        consume_tx = StoredValueTransaction(
            account_id=account.id,
            member_id=member_id,
            store_id=store_id,
            transaction_type=TransactionType.CONSUME.value,
            amount_fen=-deducted_balance_fen,
            gift_amount_fen=-deducted_gift_fen,
            balance_after=account.balance_fen,
            gift_balance_after=account.gift_balance_fen,
            order_id=order_id,
            note=(
                f"消费 {amount_fen/100:.2f}元"
                f"（赠送金 {deducted_gift_fen/100:.2f}元"
                f" + 本金 {deducted_balance_fen/100:.2f}元）"
            ),
        )
        self._db.add(consume_tx)
        await self._db.flush()

        return {
            "balance_fen": account.balance_fen,
            "gift_balance_fen": account.gift_balance_fen,
            "deducted_fen": amount_fen,
            "deducted_gift_fen": deducted_gift_fen,
            "deducted_balance_fen": deducted_balance_fen,
        }

    async def refund_to_card(
        self,
        member_id: str,
        amount_fen: int,
        order_id: str,
        note: str = "",
    ) -> dict:
        """
        退款回储值账户（退回本金）

        退款不依赖 store_id 查找账户；通过 member_id 找最近活跃账户。
        退款金额加回本金（不加赠送金）。
        """
        if amount_fen <= 0:
            raise ValueError(f"退款金额必须大于0，当前: {amount_fen}")

        # 查找该会员的账户（按最后消费时间找最近活跃的）
        stmt = (
            select(StoredValueAccount)
            .where(StoredValueAccount.member_id == member_id)
            .order_by(StoredValueAccount.last_consume_at.desc().nullslast())
            .limit(1)
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            raise ValueError(f"未找到会员 {member_id} 的储值账户")

        account.balance_fen += amount_fen
        account.version += 1

        refund_tx = StoredValueTransaction(
            account_id=account.id,
            member_id=member_id,
            store_id=account.store_id,
            transaction_type=TransactionType.REFUND.value,
            amount_fen=amount_fen,
            gift_amount_fen=0,
            balance_after=account.balance_fen,
            gift_balance_after=account.gift_balance_fen,
            order_id=order_id,
            note=note or f"退款 {amount_fen/100:.2f}元",
        )
        self._db.add(refund_tx)
        await self._db.flush()

        return {
            "balance_fen": account.balance_fen,
            "gift_balance_fen": account.gift_balance_fen,
            "refunded_fen": amount_fen,
        }

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def get_balance(self, member_id: str) -> dict:
        """
        余额查询

        返回:
            balance_yuan       — 本金余额（元，2位小数）
            gift_balance_yuan  — 赠送金余额（元）
            total_yuan         — 合计可用余额（元）
        """
        stmt = (
            select(StoredValueAccount)
            .where(StoredValueAccount.member_id == member_id)
        )
        result = await self._db.execute(stmt)
        accounts = result.scalars().all()

        total_balance = sum(a.balance_fen for a in accounts)
        total_gift = sum(a.gift_balance_fen for a in accounts)

        return {
            "balance_yuan": round(total_balance / 100, 2),
            "gift_balance_yuan": round(total_gift / 100, 2),
            "total_yuan": round((total_balance + total_gift) / 100, 2),
            # 原始分值（方便内部使用）
            "balance_fen": total_balance,
            "gift_balance_fen": total_gift,
        }

    async def get_transactions(
        self,
        member_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        流水列表（分页，按时间倒序）

        返回:
            items     — 流水列表
            total     — 总记录数
            page      — 当前页
            page_size — 每页条数
        """
        offset = (page - 1) * page_size

        # 总数
        count_stmt = (
            select(StoredValueTransaction)
            .where(StoredValueTransaction.member_id == member_id)
        )
        count_result = await self._db.execute(count_stmt)
        all_rows = count_result.scalars().all()
        total = len(all_rows)

        # 分页查询
        stmt = (
            select(StoredValueTransaction)
            .where(StoredValueTransaction.member_id == member_id)
            .order_by(StoredValueTransaction.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        items = [
            {
                "id": str(r.id),
                "transaction_type": r.transaction_type,
                "amount_yuan": round(r.amount_fen / 100, 2),
                "gift_amount_yuan": round(r.gift_amount_fen / 100, 2),
                "balance_after_yuan": round(r.balance_after / 100, 2),
                "gift_balance_after_yuan": round(r.gift_balance_after / 100, 2),
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

    # ── 活动管理 ──────────────────────────────────────────────────────────────

    async def create_promotion(
        self,
        store_id: str,
        name: str,
        min_recharge_fen: int,
        gift_amount_fen: int = 0,
        gift_rate: float = 0.0,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
    ) -> dict:
        """
        创建充值活动

        gift_amount_fen 和 gift_rate 至少填一个，两者可叠加。
        """
        if min_recharge_fen <= 0:
            raise ValueError("充值门槛必须大于0")
        if gift_amount_fen == 0 and gift_rate == 0.0:
            raise ValueError("固定赠送额和比例赠送率至少填一个")
        if gift_rate < 0 or gift_rate > 1:
            raise ValueError("比例赠送率必须在 0.0~1.0 之间")

        promotion = RechargePromotion(
            store_id=store_id,
            name=name,
            min_recharge_fen=min_recharge_fen,
            gift_amount_fen=gift_amount_fen,
            gift_rate=gift_rate,
            is_active=True,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        self._db.add(promotion)
        await self._db.flush()

        return {
            "id": str(promotion.id),
            "store_id": store_id,
            "name": name,
            "min_recharge_fen": min_recharge_fen,
            "gift_amount_fen": gift_amount_fen,
            "gift_rate": gift_rate,
            "is_active": True,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
        }

    async def list_promotions(self, store_id: str) -> list:
        """获取门店所有充值活动"""
        stmt = (
            select(RechargePromotion)
            .where(RechargePromotion.store_id == store_id)
            .order_by(RechargePromotion.sort_order.desc(), RechargePromotion.created_at.desc())
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "name": r.name,
                "min_recharge_fen": r.min_recharge_fen,
                "min_recharge_yuan": round(r.min_recharge_fen / 100, 2),
                "gift_amount_fen": r.gift_amount_fen,
                "gift_amount_yuan": round(r.gift_amount_fen / 100, 2),
                "gift_rate": r.gift_rate,
                "is_active": r.is_active,
                "valid_from": r.valid_from.isoformat() if r.valid_from else None,
                "valid_until": r.valid_until.isoformat() if r.valid_until else None,
            }
            for r in rows
        ]

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    async def _find_best_promotion(self, store_id: str, amount_fen: int) -> Optional[dict]:
        """
        找最优赠送规则

        规则：
        1. is_active=True
        2. min_recharge_fen <= amount_fen（满足门槛）
        3. 在有效期内（valid_from/valid_until 为 NULL 则不限期）
        4. 计算 effective_gift = gift_amount_fen + int(amount_fen * gift_rate)
        5. 返回 effective_gift 最大的规则

        返回 None 表示无适用规则。
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        stmt = (
            select(RechargePromotion)
            .where(
                RechargePromotion.store_id == store_id,
                RechargePromotion.is_active == True,  # noqa: E712
                RechargePromotion.min_recharge_fen <= amount_fen,
            )
        )
        result = await self._db.execute(stmt)
        candidates = result.scalars().all()

        # 过滤有效期 + 计算最优赠送额
        best = None
        best_gift = -1

        for p in candidates:
            if p.valid_from and p.valid_from > now:
                continue
            if p.valid_until and p.valid_until < now:
                continue

            effective_gift = p.gift_amount_fen + int(amount_fen * p.gift_rate)
            if effective_gift > best_gift:
                best_gift = effective_gift
                best = {
                    "id": p.id,
                    "name": p.name,
                    "gift_amount_fen": effective_gift,
                }

        return best

    async def _get_or_create_account_for_update(
        self, member_id: str, store_id: str
    ) -> StoredValueAccount:
        """
        获取账户（SELECT FOR UPDATE），不存在则创建。

        SELECT FOR UPDATE 锁定行，防止并发充值/消费时超扣。
        """
        stmt = (
            select(StoredValueAccount)
            .where(
                StoredValueAccount.member_id == member_id,
                StoredValueAccount.store_id == store_id,
            )
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        if account is None:
            account = StoredValueAccount(
                member_id=member_id,
                store_id=store_id,
                balance_fen=0,
                gift_balance_fen=0,
            )
            self._db.add(account)
            await self._db.flush()

        return account
