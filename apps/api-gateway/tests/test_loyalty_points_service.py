"""
tests/test_loyalty_points_service.py

LoyaltyPointsService 单元测试

覆盖场景：
  1.  消费积分按 EARN_RATE 计算
  2.  消费积分按等级倍率（gold 1.5x）计算
  3.  积分兑换计算抵扣金额（分）
  4.  积分不足时 raise ValueError
  5.  升级检查触发 — lifetime_points 达到银牌门槛升级
  6.  升级检查 — 未达门槛不升级
  7.  等级倍率影响积分计算（silver 1.2x）
  8.  expire 清理逻辑 — 超过 N 天未活动积分清零
  9.  expire 不影响活跃账户
 10.  获取账户信息含等级权益
 11.  积分历史分页
 12.  upsert_level_config 更新正常/无效等级 raise
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-xx")

from src.models.loyalty_points import (
    LoyaltyAccount,
    MemberLevel,
    MemberLevelConfig,
    PointsChangeReason,
    PointsTransaction,
)
from src.services.loyalty_points_service import LoyaltyPointsService


# ── 辅助构造 ───────────────────────────────────────────────────────────────────


def _make_account(
    member_id: str = "M001",
    store_id: str = "S001",
    total_points: int = 0,
    lifetime_points: int = 0,
    level: str = MemberLevel.BRONZE.value,
) -> LoyaltyAccount:
    acc = MagicMock(spec=LoyaltyAccount)
    acc.id = uuid.uuid4()
    acc.member_id = member_id
    acc.store_id = store_id
    acc.total_points = total_points
    acc.lifetime_points = lifetime_points
    acc.member_level = level
    acc.last_earn_at = None
    acc.last_redeem_at = None
    acc.version = 0
    return acc


def _make_level_config_row(
    level: str,
    min_pts: int,
    rate: float = 1.0,
    discount: float = 1.0,
    birthday: int = 0,
    priority: bool = False,
) -> MemberLevelConfig:
    cfg = MagicMock(spec=MemberLevelConfig)
    cfg.id = uuid.uuid4()
    cfg.store_id = "S001"
    cfg.level = level
    cfg.level_name = f"{level}会员"
    cfg.min_lifetime_points = min_pts
    cfg.points_rate = rate
    cfg.discount_rate = discount
    cfg.birthday_bonus = birthday
    cfg.priority_reservation = priority
    cfg.is_active = True
    return cfg


def _default_configs():
    """返回默认等级配置列表（dict格式）"""
    return LoyaltyPointsService._default_level_configs()


def _make_db_for_earn(account, level_configs=None):
    """构建用于 earn_points 的 mock db"""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    level_config_rows = level_configs or []

    call_count = [0]

    async def mock_execute(stmt, *args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # _get_or_create_account_for_update (SELECT FOR UPDATE)
            result.scalar_one_or_none = MagicMock(return_value=account)
        elif call_count[0] == 2:
            # get_level_config query
            result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=level_config_rows))
            )
        elif call_count[0] == 3:
            # check_and_upgrade_level: reload account
            result.scalar_one_or_none = MagicMock(return_value=account)
        elif call_count[0] == 4:
            # check_and_upgrade_level: get_level_config
            result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=level_config_rows))
            )
        else:
            result.scalar_one_or_none = MagicMock(return_value=account)
            result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[]))
            )
        return result

    db.execute = mock_execute
    return db


# ── 测试用例 ───────────────────────────────────────────────────────────────────


class TestEarnPoints:
    """消费得积分"""

    @pytest.mark.asyncio
    async def test_earn_default_rate(self):
        """TC-1: 消费100元按默认1倍率得100积分"""
        account = _make_account(total_points=0, lifetime_points=0)
        db = _make_db_for_earn(account)
        svc = LoyaltyPointsService(db)

        result = await svc.earn_points(
            member_id="M001",
            store_id="S001",
            order_amount_fen=10000,
            order_id="ORD001",
        )

        # 10000 / 100 * 1 * 1.0 = 100
        assert result["points_earned"] == 100
        assert account.total_points == 100
        assert account.lifetime_points == 100

    @pytest.mark.asyncio
    async def test_earn_with_gold_rate(self):
        """TC-2: 金牌等级（1.5x）消费100元得150积分"""
        account = _make_account(
            total_points=0, lifetime_points=2000, level=MemberLevel.GOLD.value
        )
        gold_config = _make_level_config_row(MemberLevel.GOLD.value, 2000, rate=1.5)
        db = _make_db_for_earn(account, level_configs=[gold_config])
        svc = LoyaltyPointsService(db)

        result = await svc.earn_points(
            member_id="M001",
            store_id="S001",
            order_amount_fen=10000,
            order_id="ORD002",
        )

        # 10000 / 100 * 1 * 1.5 = 150
        assert result["points_earned"] == 150

    @pytest.mark.asyncio
    async def test_earn_with_silver_rate(self):
        """TC-7: 银牌等级（1.2x）消费50元得60积分"""
        account = _make_account(
            total_points=0, lifetime_points=500, level=MemberLevel.SILVER.value
        )
        silver_config = _make_level_config_row(MemberLevel.SILVER.value, 500, rate=1.2)
        db = _make_db_for_earn(account, level_configs=[silver_config])
        svc = LoyaltyPointsService(db)

        result = await svc.earn_points(
            member_id="M001",
            store_id="S001",
            order_amount_fen=5000,
            order_id="ORD007",
        )

        # 5000 / 100 * 1 * 1.2 = 60
        assert result["points_earned"] == 60


class TestRedeemPoints:
    """积分兑换"""

    @pytest.mark.asyncio
    async def test_redeem_calculates_deduction_fen(self):
        """TC-3: 100积分 = 1元 = 100分"""
        account = _make_account(total_points=500)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none = MagicMock(return_value=account)
        db.execute = AsyncMock(return_value=scalar_mock)

        svc = LoyaltyPointsService(db)
        result = await svc.redeem_points(
            member_id="M001",
            points_to_use=200,
            order_id="ORD003",
        )

        # 200 / 100 * 100 = 200分 = 2元
        assert result["deduction_fen"] == 200
        assert result["points_used"] == 200
        assert result["points_remaining"] == 300
        assert account.total_points == 300

    @pytest.mark.asyncio
    async def test_redeem_insufficient_raises(self):
        """TC-4: 积分不足时 raise ValueError"""
        account = _make_account(total_points=50)

        db = AsyncMock()
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none = MagicMock(return_value=account)
        db.execute = AsyncMock(return_value=scalar_mock)

        svc = LoyaltyPointsService(db)

        with pytest.raises(ValueError, match="积分不足"):
            await svc.redeem_points(
                member_id="M001",
                points_to_use=100,
                order_id="ORD004",
            )

    @pytest.mark.asyncio
    async def test_redeem_500_points_equals_500_fen(self):
        """TC-3b: 500积分兑换500分（5元）"""
        account = _make_account(total_points=1000)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none = MagicMock(return_value=account)
        db.execute = AsyncMock(return_value=scalar_mock)

        svc = LoyaltyPointsService(db)
        result = await svc.redeem_points(
            member_id="M001",
            points_to_use=500,
            order_id="ORD_500",
        )

        assert result["deduction_fen"] == 500  # 500积分 = 5元 = 500分
        assert result["points_remaining"] == 500


class TestLevelUpgrade:
    """等级升级检查"""

    @pytest.mark.asyncio
    async def test_upgrade_triggered_when_reaching_silver_threshold(self):
        """TC-5: lifetime_points 达到银牌门槛，升级为 silver"""
        account = _make_account(
            total_points=500,
            lifetime_points=500,
            level=MemberLevel.BRONZE.value,
        )

        db = AsyncMock()
        db.flush = AsyncMock()

        silver_config = _make_level_config_row(MemberLevel.SILVER.value, 500)
        bronze_config = _make_level_config_row(MemberLevel.BRONZE.value, 0)

        call_count = [0]

        async def mock_execute(stmt, *args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # reload account
                result.scalar_one_or_none = MagicMock(return_value=account)
            else:
                # get_level_config
                result.scalars = MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[silver_config, bronze_config])
                    )
                )
            return result

        db.execute = mock_execute

        svc = LoyaltyPointsService(db)
        new_level = await svc.check_and_upgrade_level(account.id)

        assert new_level == MemberLevel.SILVER.value
        assert account.member_level == MemberLevel.SILVER.value

    @pytest.mark.asyncio
    async def test_no_upgrade_when_below_threshold(self):
        """TC-6: lifetime_points 未达门槛，不升级返回 None"""
        account = _make_account(
            total_points=100,
            lifetime_points=100,
            level=MemberLevel.BRONZE.value,
        )

        db = AsyncMock()
        db.flush = AsyncMock()

        silver_config = _make_level_config_row(MemberLevel.SILVER.value, 500)
        bronze_config = _make_level_config_row(MemberLevel.BRONZE.value, 0)

        call_count = [0]

        async def mock_execute(stmt, *args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none = MagicMock(return_value=account)
            else:
                result.scalars = MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[silver_config, bronze_config])
                    )
                )
            return result

        db.execute = mock_execute

        svc = LoyaltyPointsService(db)
        new_level = await svc.check_and_upgrade_level(account.id)

        assert new_level is None


class TestExpirePoints:
    """积分过期清理"""

    @pytest.mark.asyncio
    async def test_expire_inactive_accounts(self):
        """TC-8: 超过 365 天未活动的积分清零"""
        stale_account = _make_account(total_points=200)
        stale_account.last_earn_at = datetime(2020, 1, 1)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[stale_account]))
        )
        db.execute = AsyncMock(return_value=scalars_mock)

        svc = LoyaltyPointsService(db)
        count = await svc.expire_old_points(inactive_days=365)

        assert count == 1
        assert stale_account.total_points == 0
        db.add.assert_called_once()  # 过期流水写入

    @pytest.mark.asyncio
    async def test_expire_skips_active_accounts(self):
        """TC-9: 活跃账户（近期有积分）不被过期"""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        scalars_mock = MagicMock()
        # 返回空列表：无需过期的账户
        scalars_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        db.execute = AsyncMock(return_value=scalars_mock)

        svc = LoyaltyPointsService(db)
        count = await svc.expire_old_points(inactive_days=365)

        assert count == 0
        db.add.assert_not_called()


class TestGetAccount:
    """积分账户查询"""

    @pytest.mark.asyncio
    async def test_get_account_returns_level_benefits(self):
        """TC-10: 获取账户时包含等级权益"""
        account = _make_account(
            total_points=300,
            lifetime_points=700,
            level=MemberLevel.SILVER.value,
        )

        db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt, *args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none = MagicMock(return_value=account)
            else:
                # get_level_config 返回空（使用默认配置）
                result.scalars = MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[]))
                )
            return result

        db.execute = mock_execute

        svc = LoyaltyPointsService(db)
        result = await svc.get_account(member_id="M001")

        assert result["member_id"] == "M001"
        assert result["total_points"] == 300
        assert result["member_level"] == MemberLevel.SILVER.value
        assert "level_benefits" in result


class TestGetHistory:
    """积分历史分页"""

    @pytest.mark.asyncio
    async def test_history_pagination(self):
        """TC-11: 积分历史分页返回正确结构"""
        tx = MagicMock(spec=PointsTransaction)
        tx.id = uuid.uuid4()
        tx.points_change = 100
        tx.points_after = 100
        tx.change_reason = PointsChangeReason.CONSUME_EARN.value
        tx.order_id = "ORD001"
        tx.note = "消费得积分"
        tx.created_at = datetime(2026, 1, 15, 10, 0, 0)

        db = AsyncMock()
        all_mock = MagicMock()
        all_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[tx]))
        )
        page_mock = MagicMock()
        page_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[tx]))
        )
        db.execute = AsyncMock(side_effect=[all_mock, page_mock])

        svc = LoyaltyPointsService(db)
        result = await svc.get_history(member_id="M001", page=1, page_size=20)

        assert result["total"] == 1
        assert result["page"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["points_change"] == 100


class TestUpsertLevelConfig:
    """等级配置管理"""

    @pytest.mark.asyncio
    async def test_upsert_invalid_level_raises(self):
        """TC-12: 无效等级 raise ValueError"""
        db = AsyncMock()
        svc = LoyaltyPointsService(db)

        with pytest.raises(ValueError, match="无效等级"):
            await svc.upsert_level_config(
                store_id="S001",
                level="legendary",  # 不存在的等级
                config_data={"min_lifetime_points": 100000},
            )

    @pytest.mark.asyncio
    async def test_upsert_creates_new_config(self):
        """TC-12b: 不存在时创建新配置"""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_mock)

        svc = LoyaltyPointsService(db)

        # 使用 patch 避免真实 MemberLevelConfig 初始化问题
        from unittest.mock import patch as _patch
        with _patch("src.services.loyalty_points_service.MemberLevelConfig") as MockConfig:
            new_cfg = _make_level_config_row(MemberLevel.GOLD.value, 2000, rate=1.5)
            MockConfig.return_value = new_cfg
            result = await svc.upsert_level_config(
                store_id="S001",
                level=MemberLevel.GOLD.value,
                config_data={"min_lifetime_points": 2000, "points_rate": 1.5},
            )

        db.add.assert_called_once()
        db.flush.assert_called_once()
