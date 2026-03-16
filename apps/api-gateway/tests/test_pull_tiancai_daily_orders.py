"""
tests/test_pull_tiancai_daily_orders.py — 天财商龙日单拉取任务单元测试

覆盖：
  - TIANCAI_BASE_URL 未配置 → 直接返回 skipped，不访问 DB
  - 凭据未配置 → 返回 skipped（含 errors 说明原因）
  - 正常流程：拉取 N 条订单 → upsert → 返回正确计数
  - 门店 adapter 报错 → 降级（error 记录），其余继续
  - 两个门店，一个成功一个失败 → stores_processed=1, errors=1
  - 门店级 shopId 优先于全局 shopId
  - 空订单列表：stores_processed=1, orders_upserted=0
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ════════════════════════════════════════════════════════════════════════════
# 辅助工厂
# ════════════════════════════════════════════════════════════════════════════

def _make_store(sid: str = "S001"):
    s = MagicMock()
    s.id = sid
    s.is_active = True
    s.code = None
    return s


def _make_order_schema(order_id: str = "ORD001"):
    """返回 OrderSchema-like mock 对象。"""
    schema = MagicMock()
    schema.order_id = order_id
    schema.table_number = "T1"
    schema.order_status = MagicMock()
    schema.order_status.value = "completed"
    schema.total = Decimal("123.45")
    schema.discount = Decimal("0.00")
    schema.created_at = datetime(2026, 3, 4, 12, 0, 0)
    schema.waiter_id = "W001"
    schema.notes = None
    return schema


def _make_session(stores):
    """构造 get_db_session 兼容的异步上下文管理器 + 会话 mock。"""
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = stores
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=exec_result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx, session


def _base_env(**overrides):
    return {
        "TIANCAI_BASE_URL": "https://test.tiancai.com",
        "TIANCAI_APPID": "GLOBAL_APPID",
        "TIANCAI_ACCESSID": "GLOBAL_ACCESSID",
        "TIANCAI_CENTER_ID": "CENTER001",
        "TIANCAI_BRAND_ID": "B001",
        "TIANCAI_SHOP_ID": "SHOP001",
        **overrides,
    }


# ════════════════════════════════════════════════════════════════════════════
# 跳过逻辑
# ════════════════════════════════════════════════════════════════════════════

class TestPullTiancaiSkip:

    def test_no_base_url_returns_skipped(self):
        """TIANCAI_BASE_URL 未配置 → skipped=True，不访问 DB。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders

        with patch.dict(os.environ, {"TIANCAI_BASE_URL": ""}, clear=False):
            result = pull_tiancai_daily_orders()

        assert result["skipped"] is True
        assert result["success"] is True
        assert result["stores_processed"] == 0
        assert result["orders_upserted"] == 0
        assert result["errors"] == []

    def test_store_without_credentials_silently_skipped(self):
        """凭据未配置 → skipped=True，带 errors 说明原因。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders

        fake_db, session = _make_session([_make_store("S001")])

        with patch.dict(os.environ, _base_env(TIANCAI_APPID="", TIANCAI_ACCESSID="")), \
             patch("src.core.database.get_db_session", fake_db):
            result = pull_tiancai_daily_orders()

        assert result["skipped"] is True
        assert result["stores_processed"] == 0
        assert result["orders_upserted"] == 0
        assert len(result["errors"]) == 1
        session.commit.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# 正常流程
# ════════════════════════════════════════════════════════════════════════════

class TestPullTiancaiNormal:

    def test_pulls_and_upserts_orders(self):
        """正常流程：拉取 2 条订单 → orders_upserted=2, stores_processed=1。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders

        fake_db, session = _make_session([_make_store("S001")])
        mock_inst = MagicMock()
        mock_inst.pull_daily_orders = AsyncMock(
            return_value=[_make_order_schema("ORD001"), _make_order_schema("ORD002")]
        )

        with patch.dict(os.environ, _base_env()), \
             patch("src.core.database.get_db_session", fake_db), \
             patch(
                 "packages.api_adapters.tiancai_shanglong.src.adapter.TiancaiShanglongAdapter",
                 return_value=mock_inst,
             ):
            result = pull_tiancai_daily_orders()

        assert result["success"] is True
        assert result["stores_processed"] == 1
        assert result["orders_upserted"] == 2
        assert result["errors"] == []
        session.commit.assert_called_once()

    def test_empty_order_list(self):
        """空订单列表 → orders_upserted=0，但 stores_processed=1。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders

        fake_db, session = _make_session([_make_store("S001")])
        mock_inst = MagicMock()
        mock_inst.pull_daily_orders = AsyncMock(return_value=[])

        with patch.dict(os.environ, _base_env()), \
             patch("src.core.database.get_db_session", fake_db), \
             patch(
                 "packages.api_adapters.tiancai_shanglong.src.adapter.TiancaiShanglongAdapter",
                 return_value=mock_inst,
             ):
            result = pull_tiancai_daily_orders()

        assert result["stores_processed"] == 1
        assert result["orders_upserted"] == 0
        assert result["errors"] == []

    def test_store_level_shop_id_takes_priority(self):
        """门店级 TIANCAI_SHOP_ID_{sid} 优先于全局 TIANCAI_SHOP_ID。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders

        fake_db, _ = _make_session([_make_store("S001")])
        captured = []

        def _factory(config):
            captured.append(config)
            inst = MagicMock()
            inst.pull_daily_orders = AsyncMock(return_value=[])
            return inst

        env = _base_env(
            TIANCAI_SHOP_ID="GLOBAL_SHOP",
            TIANCAI_SHOP_ID_S001="STORE_SHOP",
        )

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch(
                 "packages.api_adapters.tiancai_shanglong.src.adapter.TiancaiShanglongAdapter",
                 side_effect=_factory,
             ):
            pull_tiancai_daily_orders()

        assert len(captured) == 1
        assert captured[0]["shop_id"] == "STORE_SHOP"

    def test_result_contains_date_field(self):
        """返回结果包含 date 字段（昨日日期字符串）。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders
        from datetime import date, timedelta

        fake_db, _ = _make_session([])

        with patch.dict(os.environ, _base_env()), \
             patch("src.core.database.get_db_session", fake_db):
            result = pull_tiancai_daily_orders()

        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert result.get("date") == yesterday


# ════════════════════════════════════════════════════════════════════════════
# 错误处理 / 降级
# ════════════════════════════════════════════════════════════════════════════

class TestPullTiancaiErrorHandling:

    def test_adapter_error_graceful_degradation(self):
        """adapter.pull_daily_orders 抛出异常 → errors=[1], success=True。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders

        fake_db, session = _make_session([_make_store("S001")])
        mock_inst = MagicMock()
        mock_inst.pull_daily_orders = AsyncMock(side_effect=Exception("API timeout"))

        with patch.dict(os.environ, _base_env()), \
             patch("src.core.database.get_db_session", fake_db), \
             patch(
                 "packages.api_adapters.tiancai_shanglong.src.adapter.TiancaiShanglongAdapter",
                 return_value=mock_inst,
             ):
            result = pull_tiancai_daily_orders()

        assert result["success"] is True
        assert result["stores_processed"] == 0
        assert result["orders_upserted"] == 0
        assert len(result["errors"]) == 1
        assert result["errors"][0]["store_id"] == "S001"
        session.rollback.assert_called_once()

    def test_two_stores_one_fails(self):
        """2 个门店：S001 报错, S002 正常 → stores_processed=1, errors=[S001]。"""
        from src.core.celery_tasks import pull_tiancai_daily_orders

        fake_db, session = _make_session([_make_store("S001"), _make_store("S002")])

        call_count = {"n": 0}

        def _factory(config):
            call_count["n"] += 1
            inst = MagicMock()
            # First call is S001 (fails), second is S002 (succeeds)
            if call_count["n"] == 1:
                inst.pull_daily_orders = AsyncMock(side_effect=Exception("S001 down"))
            else:
                inst.pull_daily_orders = AsyncMock(
                    return_value=[_make_order_schema("ORD099")]
                )
            return inst

        with patch.dict(os.environ, _base_env()), \
             patch("src.core.database.get_db_session", fake_db), \
             patch(
                 "packages.api_adapters.tiancai_shanglong.src.adapter.TiancaiShanglongAdapter",
                 side_effect=_factory,
             ):
            result = pull_tiancai_daily_orders()

        assert result["stores_processed"] == 1
        assert result["orders_upserted"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["store_id"] == "S001"
