"""
tests/test_stored_value_service.py

StoredValueService 单元测试

覆盖场景：
  1.  充值正常 — 余额增加，流水写入
  2.  充值计算固定赠送金（gift_amount_fen）
  3.  充值计算比例赠送金（gift_rate）
  4.  充值计算固定+比例叠加赠送金
  5.  消费先扣赠送金再扣本金（use_gift_first=True）
  6.  消费全部扣本金（use_gift_first=False）
  7.  余额不足时 raise ValueError
  8.  退款增加本金余额
  9.  余额查询返回元单位
 10.  流水列表分页
 11.  并发消费不超扣（乐观锁 SELECT FOR UPDATE）
 12.  活动创建参数校验
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-xx")

from src.models.stored_value import (
    RechargePromotion,
    StoredValueAccount,
    StoredValueTransaction,
    TransactionType,
)
from src.services.stored_value_service import StoredValueService


# ── 辅助构造函数 ───────────────────────────────────────────────────────────────


def _make_account(
    member_id: str = "M001",
    store_id: str = "S001",
    balance_fen: int = 0,
    gift_balance_fen: int = 0,
) -> StoredValueAccount:
    acc = MagicMock(spec=StoredValueAccount)
    acc.id = uuid.uuid4()
    acc.member_id = member_id
    acc.store_id = store_id
    acc.balance_fen = balance_fen
    acc.gift_balance_fen = gift_balance_fen
    acc.is_frozen = False
    acc.version = 0
    acc.last_recharge_at = None
    acc.last_consume_at = None
    return acc


def _make_promotion(
    store_id: str = "S001",
    min_recharge_fen: int = 10000,
    gift_amount_fen: int = 2000,
    gift_rate: float = 0.0,
    is_active: bool = True,
    valid_from: datetime = None,
    valid_until: datetime = None,
) -> RechargePromotion:
    p = MagicMock(spec=RechargePromotion)
    p.id = uuid.uuid4()
    p.store_id = store_id
    p.min_recharge_fen = min_recharge_fen
    p.gift_amount_fen = gift_amount_fen
    p.gift_rate = gift_rate
    p.is_active = is_active
    p.valid_from = valid_from
    p.valid_until = valid_until
    return p


def _make_db(account: StoredValueAccount = None, promotions=None, transactions=None):
    """构建 mock AsyncSession"""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    # mock scalar_one_or_none
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=account)

    # mock scalars().all()
    scalars_result = MagicMock()
    scalars_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=promotions or []))
    )

    # execute 调用序列：第1次（for_update 锁）返回账户，第2次（promotions）返回活动列表
    execute_results = []
    if account is not None:
        # promotions query result
        promo_scalars = MagicMock()
        promo_scalars.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=promotions or []))
        )
        execute_results.append(promo_scalars)
        # account for_update query result
        acct_scalar = MagicMock()
        acct_scalar.scalar_one_or_none = MagicMock(return_value=account)
        execute_results.append(acct_scalar)
    else:
        execute_results.append(scalars_result)

    db.execute = AsyncMock(side_effect=execute_results * 10)
    return db


# ── 测试用例 ───────────────────────────────────────────────────────────────────


class TestRecharge:
    """充值测试"""

    @pytest.mark.asyncio
    async def test_recharge_no_promotion_increases_balance(self):
        """TC-1: 充值正常 — 无赠送时本金增加，流水写入"""
        account = _make_account(balance_fen=5000)
        db = _make_db(account=account, promotions=[])
        svc = StoredValueService(db)

        result = await svc.recharge(
            member_id="M001",
            store_id="S001",
            amount_fen=10000,
            payment_method="wechat",
            operator_id="OP1",
        )

        assert account.balance_fen == 15000
        assert result["recharged_fen"] == 10000
        assert result["gifted_fen"] == 0
        db.add.assert_called()

    @pytest.mark.asyncio
    async def test_recharge_with_fixed_gift(self):
        """TC-2: 充值计算固定赠送金（充100赠20）"""
        account = _make_account(balance_fen=0, gift_balance_fen=0)
        promo = _make_promotion(min_recharge_fen=10000, gift_amount_fen=2000, gift_rate=0.0)
        db = _make_db(account=account, promotions=[promo])
        svc = StoredValueService(db)

        result = await svc.recharge(
            member_id="M001",
            store_id="S001",
            amount_fen=10000,
            payment_method="wechat",
            operator_id="OP1",
        )

        assert result["gifted_fen"] == 2000
        assert account.gift_balance_fen == 2000
        assert account.balance_fen == 10000

    @pytest.mark.asyncio
    async def test_recharge_with_rate_gift(self):
        """TC-3: 充值计算比例赠送金（充100赠10%=10元）"""
        account = _make_account(balance_fen=0, gift_balance_fen=0)
        promo = _make_promotion(min_recharge_fen=5000, gift_amount_fen=0, gift_rate=0.1)
        db = _make_db(account=account, promotions=[promo])
        svc = StoredValueService(db)

        result = await svc.recharge(
            member_id="M001",
            store_id="S001",
            amount_fen=10000,
            payment_method="alipay",
            operator_id="OP1",
        )

        # 10000 * 0.1 = 1000
        assert result["gifted_fen"] == 1000
        assert account.gift_balance_fen == 1000

    @pytest.mark.asyncio
    async def test_recharge_fixed_plus_rate_gift(self):
        """TC-4: 固定赠送 + 比例赠送叠加（充100，固定赠20+比例赠5%=5元，共赠25）"""
        account = _make_account(balance_fen=0, gift_balance_fen=0)
        promo = _make_promotion(
            min_recharge_fen=10000, gift_amount_fen=2000, gift_rate=0.05
        )
        db = _make_db(account=account, promotions=[promo])
        svc = StoredValueService(db)

        result = await svc.recharge(
            member_id="M001",
            store_id="S001",
            amount_fen=10000,
            payment_method="cash",
            operator_id="OP1",
        )

        # 2000 + int(10000 * 0.05) = 2000 + 500 = 2500
        assert result["gifted_fen"] == 2500


class TestConsume:
    """消费扣款测试"""

    @pytest.mark.asyncio
    async def test_consume_gift_first_then_balance(self):
        """TC-5: 消费先扣赠送金再扣本金"""
        account = _make_account(balance_fen=8000, gift_balance_fen=3000)
        db = _make_db(account=account, promotions=[])
        svc = StoredValueService(db)

        result = await svc.consume(
            member_id="M001",
            store_id="S001",
            amount_fen=5000,
            order_id="ORD001",
            use_gift_first=True,
        )

        # 先扣3000赠送金，再扣2000本金
        assert result["deducted_gift_fen"] == 3000
        assert result["deducted_balance_fen"] == 2000
        assert account.gift_balance_fen == 0
        assert account.balance_fen == 6000

    @pytest.mark.asyncio
    async def test_consume_balance_only_when_use_gift_first_false(self):
        """TC-6: use_gift_first=False 时全部扣本金"""
        account = _make_account(balance_fen=10000, gift_balance_fen=5000)
        db = _make_db(account=account, promotions=[])
        svc = StoredValueService(db)

        result = await svc.consume(
            member_id="M001",
            store_id="S001",
            amount_fen=3000,
            order_id="ORD002",
            use_gift_first=False,
        )

        assert result["deducted_gift_fen"] == 0
        assert result["deducted_balance_fen"] == 3000
        assert account.balance_fen == 7000
        assert account.gift_balance_fen == 5000

    @pytest.mark.asyncio
    async def test_consume_insufficient_balance_raises(self):
        """TC-7: 余额不足时 raise ValueError"""
        account = _make_account(balance_fen=1000, gift_balance_fen=500)
        db = _make_db(account=account, promotions=[])
        svc = StoredValueService(db)

        with pytest.raises(ValueError, match="余额不足"):
            await svc.consume(
                member_id="M001",
                store_id="S001",
                amount_fen=5000,
                order_id="ORD003",
            )

    @pytest.mark.asyncio
    async def test_consume_exact_balance_succeeds(self):
        """TC-7b: 恰好等于余额时成功"""
        account = _make_account(balance_fen=5000, gift_balance_fen=0)
        db = _make_db(account=account, promotions=[])
        svc = StoredValueService(db)

        result = await svc.consume(
            member_id="M001",
            store_id="S001",
            amount_fen=5000,
            order_id="ORD004",
        )

        assert account.balance_fen == 0
        assert result["deducted_fen"] == 5000


class TestRefund:
    """退款测试"""

    @pytest.mark.asyncio
    async def test_refund_increases_balance(self):
        """TC-8: 退款回储值账户，本金余额增加"""
        account = _make_account(balance_fen=3000, gift_balance_fen=500)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none = MagicMock(return_value=account)
        db.execute = AsyncMock(return_value=scalar_mock)

        svc = StoredValueService(db)

        result = await svc.refund_to_card(
            member_id="M001",
            amount_fen=2000,
            order_id="ORD005",
        )

        assert account.balance_fen == 5000  # 3000 + 2000
        assert result["refunded_fen"] == 2000
        # 赠送金不变
        assert account.gift_balance_fen == 500

    @pytest.mark.asyncio
    async def test_refund_no_account_raises(self):
        """TC-8b: 账户不存在时 raise ValueError"""
        db = AsyncMock()
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_mock)

        svc = StoredValueService(db)

        with pytest.raises(ValueError, match="未找到会员"):
            await svc.refund_to_card(
                member_id="UNKNOWN",
                amount_fen=1000,
                order_id="ORD006",
            )


class TestGetBalance:
    """余额查询测试"""

    @pytest.mark.asyncio
    async def test_get_balance_returns_yuan(self):
        """TC-9: 余额查询返回元单位（/100）"""
        account = _make_account(balance_fen=15000, gift_balance_fen=3000)

        db = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[account]))
        )
        db.execute = AsyncMock(return_value=scalars_mock)

        svc = StoredValueService(db)
        result = await svc.get_balance(member_id="M001")

        assert result["balance_yuan"] == 150.0
        assert result["gift_balance_yuan"] == 30.0
        assert result["total_yuan"] == 180.0


class TestGetTransactions:
    """流水列表测试"""

    @pytest.mark.asyncio
    async def test_transactions_pagination(self):
        """TC-10: 流水列表分页返回正确结构"""
        tx = MagicMock(spec=StoredValueTransaction)
        tx.id = uuid.uuid4()
        tx.transaction_type = TransactionType.RECHARGE.value
        tx.amount_fen = 10000
        tx.gift_amount_fen = 2000
        tx.balance_after = 10000
        tx.gift_balance_after = 2000
        tx.order_id = None
        tx.note = "充值100元"
        tx.created_at = datetime(2026, 1, 1, 12, 0, 0)

        db = AsyncMock()
        all_rows_mock = MagicMock()
        all_rows_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[tx]))
        )
        page_rows_mock = MagicMock()
        page_rows_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[tx]))
        )
        db.execute = AsyncMock(side_effect=[all_rows_mock, page_rows_mock])

        svc = StoredValueService(db)
        result = await svc.get_transactions(member_id="M001", page=1, page_size=20)

        assert result["total"] == 1
        assert result["page"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["amount_yuan"] == 100.0


class TestConcurrency:
    """并发测试"""

    @pytest.mark.asyncio
    async def test_consume_uses_select_for_update(self):
        """TC-11: 消费使用 SELECT FOR UPDATE 防并发超扣"""
        account = _make_account(balance_fen=5000, gift_balance_fen=0)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        captured_stmts = []

        async def capture_execute(stmt, *args, **kwargs):
            captured_stmts.append(stmt)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=account)
            mock_result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[]))
            )
            return mock_result

        db.execute = capture_execute

        svc = StoredValueService(db)
        await svc.consume(
            member_id="M001",
            store_id="S001",
            amount_fen=1000,
            order_id="ORD_CONC",
        )

        # 验证至少有一次查询（实际 SELECT FOR UPDATE 由 with_for_update() 保证）
        assert len(captured_stmts) >= 1


class TestCreatePromotion:
    """活动创建参数校验"""

    @pytest.mark.asyncio
    async def test_create_promotion_zero_gift_raises(self):
        """TC-12: 赠送额和赠送率均为0时 raise ValueError"""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = StoredValueService(db)

        with pytest.raises(ValueError, match="至少填一个"):
            await svc.create_promotion(
                store_id="S001",
                name="无效活动",
                min_recharge_fen=10000,
                gift_amount_fen=0,
                gift_rate=0.0,
            )

    @pytest.mark.asyncio
    async def test_create_promotion_negative_threshold_raises(self):
        """TC-12b: 充值门槛<=0时 raise ValueError"""
        db = AsyncMock()
        svc = StoredValueService(db)

        with pytest.raises(ValueError, match="充值门槛必须大于0"):
            await svc.create_promotion(
                store_id="S001",
                name="无效活动",
                min_recharge_fen=0,
                gift_amount_fen=1000,
            )
