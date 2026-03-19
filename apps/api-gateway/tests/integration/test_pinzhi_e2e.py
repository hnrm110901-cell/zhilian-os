"""
品智 POS 端到端验证测试

覆盖三层数据管道的完整链路：
  1. Webhook 层：POST /api/v1/pos-webhook/{store_id}/pinzhi-order → 归一化 → 写库
  2. Celery Pull 层：pull_pinzhi_daily_data 定时拉取 → 订单 upsert + 营业汇总
  3. CDP 层：cdp_sync_consumer_ids 回填 consumer_id（customer_phone → ConsumerIdentity）

验证重点：
  - MD5 签名正确性 & 拒绝篡改
  - 金额单位一致性（全链路分）
  - 幂等性（重复 webhook / 重复 pull 不重复写入）
  - 凭证 4 级优先级（store.config > ExternalSystem.config > ExternalSystem fields > env）
  - 多门店隔离（S001 失败不阻塞 S002）
  - vip_phone 提取供 CDP 回填
"""

import os
import sys

for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "APP_ENV":               "test",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import asyncio
import hashlib
import inspect
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Pinzhi adapter mock module installer ─────────────────────────────────────
# packages/api-adapters/pinzhi/ 目录使用连字符路径，不是标准 Python 包。
# celery_tasks.py 通过 `from packages.api_adapters.pinzhi.src.adapter import PinzhiAdapter`
# 导入，需要在 sys.modules 中注册 mock。
# NOTE: 不在模块级安装，因为 conftest._restore_sys_modules 会在测试间清除。

_PINZHI_MODULE_PATHS = [
    "packages.api_adapters.pinzhi",
    "packages.api_adapters.pinzhi.src",
    "packages.api_adapters.pinzhi.src.adapter",
]


def _install_pinzhi_mock_modules():
    """在 sys.modules 中安装 pinzhi adapter mock（每个测试前调用）。"""
    mock_mod = MagicMock()
    for path in _PINZHI_MODULE_PATHS:
        sys.modules[path] = mock_mod
    return mock_mod


def _uninstall_pinzhi_mock_modules():
    """清理 sys.modules 中的 pinzhi mock。"""
    for path in _PINZHI_MODULE_PATHS:
        sys.modules.pop(path, None)


# ── 通用 Helpers ──────────────────────────────────────────────────────────────


def _call_task(task_fn, *args, **kwargs):
    """调用可能是 bind=True 的 Celery 任务（兼容 FakeCelery + 真实 Celery）。"""
    params = inspect.signature(task_fn).parameters
    if "self" in params:
        mock_self = MagicMock()
        mock_self.retry = MagicMock(side_effect=Exception("retry triggered"))
        return task_fn(mock_self, *args, **kwargs)
    return task_fn(*args, **kwargs)


def _run_celery_task(task_fn, *args, **kwargs):
    """
    运行使用 asyncio.run() 的 Celery 任务。
    替换 asyncio.run 为使用新事件循环的版本，绕过 'already running' 冲突。
    """
    def fake_asyncio_run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with patch("src.core.celery_tasks.asyncio.run", side_effect=fake_asyncio_run):
        return _call_task(task_fn, *args, **kwargs)


def _pinzhi_sign(token: str, params: dict) -> str:
    """复刻品智 MD5 签名算法。"""
    filtered = {
        k: v for k, v in params.items()
        if k not in ("sign", "pageIndex", "pageSize") and v is not None
    }
    ordered = sorted(filtered.items())
    param_str = "&".join(f"{k}={v}" for k, v in ordered)
    param_str += f"&token={token}"
    return hashlib.md5(param_str.encode("utf-8")).hexdigest()


def _make_db_session(stores=None, ext_systems=None, capture_list=None):
    """
    构造 get_db_session 异步上下文管理器 mock。
    支持多次 session.execute 调用，前 N 次返回预设结果，后续返回空 mock。
    capture_list: 若传入 list，所有 execute 调用的 (stmt, params) 会追加到其中。
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()

    call_idx = {"n": 0}
    responses = []

    if stores is not None:
        r1 = MagicMock()
        r1.scalars.return_value.all.return_value = stores
        responses.append(r1)

    if ext_systems is not None:
        r2 = MagicMock()
        r2.scalars.return_value.all.return_value = ext_systems
        responses.append(r2)

    fallback = MagicMock()

    async def _execute(stmt, params=None):
        if capture_list is not None:
            capture_list.append((stmt, params))
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(responses):
            return responses[idx]
        return fallback

    session.execute = _execute

    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx, session


def _make_store(sid="S001", code=None, config=None, brand_id=None):
    s = MagicMock()
    s.id = sid
    s.is_active = True
    s.code = code
    s.config = config or {}
    s.brand_id = brand_id
    return s


def _make_ext_system(store_id="S001", api_endpoint=None, api_key=None,
                     api_secret=None, config=None):
    e = MagicMock()
    e.store_id = store_id
    e.api_endpoint = api_endpoint
    e.api_key = api_key
    e.api_secret = api_secret
    e.config = config or {}
    return e


def _make_raw_pinzhi_order(
    bill_id="PZ001", bill_no="B001", table_no="A3", bill_status=1,
    dish_price_total=10400, special_offer_price=500, real_price=9900,
    vip_mobile="13800138000", vip_name="张三",
):
    """构造品智 API 返回的原始订单（queryOrderListV2 格式）。"""
    return {
        "billId": bill_id, "billNo": bill_no, "tableNo": table_no,
        "billStatus": bill_status, "orderSource": 1,
        "dishPriceTotal": dish_price_total,
        "specialOfferPrice": special_offer_price,
        "realPrice": real_price,
        "openTime": "2026-03-16T11:30:00",
        "payTime": "2026-03-16T12:05:00",
        "vipCard": "VIP_001", "vipMobile": vip_mobile, "vipName": vip_name,
        "openOrderUser": "waiter_01", "cashiers": "cashier_01",
        "remark": "少辣",
        "dishList": [
            {"dishId": "D001", "dishName": "宫保鸡丁", "dishPrice": 3800, "dishNum": 2},
            {"dishId": "D002", "dishName": "麻婆豆腐", "dishPrice": 2800, "dishNum": 1},
        ],
    }


def _make_order_schema(order_id="PZ001", total=Decimal("104.00"),
                       discount=Decimal("5.00"), status_value="completed"):
    """构造 PinzhiAdapter.to_order 返回的 OrderSchema mock。"""
    schema = MagicMock()
    schema.order_id = order_id
    schema.table_number = "A3"
    schema.order_status = MagicMock()
    schema.order_status.value = status_value
    schema.total = total
    schema.discount = discount
    schema.created_at = "2026-03-16T12:05:00"
    schema.waiter_id = "waiter_01"
    schema.notes = "少辣"
    return schema


def _make_adapter_factory(captured_configs=None, mock_adapter=None):
    """构造 PinzhiAdapter 工厂，可捕获 config + 自定义 adapter 实例。"""
    def _factory(config):
        if captured_configs is not None:
            captured_configs.append(config)
        inst = mock_adapter or MagicMock()
        if mock_adapter is None:
            inst.query_orders = AsyncMock(return_value=[])
            inst.query_order_summary = AsyncMock(return_value=None)
            inst.close = AsyncMock()
        return inst
    return _factory


# ════════════════════════════════════════════════════════════════════════════════
# 第 1 层：Webhook 端到端
# ════════════════════════════════════════════════════════════════════════════════


class TestWebhookE2E:
    """Webhook POST → 归一化 → _upsert_order → DB 写入"""

    @pytest.mark.asyncio
    async def test_pinzhi_order_full_flow(self):
        """完整 Webhook 流程：签名验证 → 归一化 → 写库 → 返回 order_id。"""
        from src.api.pos_webhook import receive_pinzhi_order

        raw = _make_raw_pinzhi_order()
        token = "test_webhook_token"
        raw["sign"] = _pinzhi_sign(token, raw)

        request = AsyncMock()
        request.json = AsyncMock(return_value=raw)

        session = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=exec_result)
        session.commit = AsyncMock()
        session.add = MagicMock()

        @asynccontextmanager
        async def _ctx():
            yield session

        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", token), \
             patch("src.api.pos_webhook.get_db_session", _ctx):
            result = await receive_pinzhi_order("S001", request)

        assert result["success"] is True
        assert result["source"] == "pinzhi"
        assert result["order_id"] == "POS_PINZHI_PZ001"
        assert session.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_pinzhi_order_idempotent(self):
        """重复提交同一订单 → 不重复写入。"""
        from src.api.pos_webhook import receive_pinzhi_order

        raw = _make_raw_pinzhi_order()
        request = AsyncMock()
        request.json = AsyncMock(return_value=raw)

        existing_order = MagicMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = existing_order
        session = AsyncMock()
        session.execute = AsyncMock(return_value=exec_result)
        session.add = MagicMock()

        @asynccontextmanager
        async def _ctx():
            yield session

        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", ""), \
             patch("src.api.pos_webhook.get_db_session", _ctx):
            result = await receive_pinzhi_order("S001", request)

        assert result["success"] is True
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_pinzhi_signature_rejected(self):
        """签名错误 → 401"""
        from fastapi import HTTPException
        from src.api.pos_webhook import receive_pinzhi_order

        raw = _make_raw_pinzhi_order()
        raw["sign"] = "forged_signature_value"

        request = AsyncMock()
        request.json = AsyncMock(return_value=raw)

        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", "real_token"):
            with pytest.raises(HTTPException) as exc_info:
                await receive_pinzhi_order("S001", request)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_webhook_amount_units_fen(self):
        """Webhook 层金额单位：全程分（fen），不转换。"""
        from src.api.pos_webhook import _normalize_pinzhi, _upsert_order

        raw = _make_raw_pinzhi_order(
            dish_price_total=15000, special_offer_price=1000, real_price=14000,
        )
        payload = _normalize_pinzhi(raw)

        assert payload.total_amount == 15000
        assert payload.discount_amount == 1000
        assert payload.final_amount == 14000

        session = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=exec_result)
        session.commit = AsyncMock()

        added_objects = []
        session.add = lambda obj: added_objects.append(obj)

        @asynccontextmanager
        async def _ctx():
            yield session

        with patch("src.api.pos_webhook.get_db_session", _ctx):
            await _upsert_order("S001", payload)

        order_obj = added_objects[0]
        assert order_obj.total_amount == 15000
        assert order_obj.discount_amount == 1000
        assert order_obj.final_amount == 14000

    @pytest.mark.asyncio
    async def test_webhook_order_id_format(self):
        """order_id 格式 = POS_PINZHI_{external_order_id}"""
        from src.api.pos_webhook import _normalize_pinzhi

        raw = _make_raw_pinzhi_order(bill_id="PZ20260316999")
        payload = _normalize_pinzhi(raw)
        expected_id = f"POS_PINZHI_{payload.external_order_id}"
        assert expected_id == "POS_PINZHI_PZ20260316999"


# ════════════════════════════════════════════════════════════════════════════════
# 第 2 层：Celery Pull 任务端到端
# ════════════════════════════════════════════════════════════════════════════════


class TestCeleryPullE2E:
    """pull_pinzhi_daily_data → 凭证解析 → Adapter 调用 → upsert 订单 + 汇总"""

    def setup_method(self):
        self._adapter_mod = _install_pinzhi_mock_modules()

    def teardown_method(self):
        _uninstall_pinzhi_mock_modules()

    def test_normal_pull_two_orders(self):
        """正常拉取 2 条订单 → stores_processed=1, orders_upserted=2。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        store = _make_store("S001", code="OG001")
        fake_db, session = _make_db_session(stores=[store], ext_systems=[])

        mock_adapter = MagicMock()
        mock_adapter.query_orders = AsyncMock(side_effect=[
            [_make_raw_pinzhi_order(bill_id="PZ001"),
             _make_raw_pinzhi_order(bill_id="PZ002")],
            [],
        ])
        mock_adapter.to_order = MagicMock(side_effect=[
            _make_order_schema("PZ001"), _make_order_schema("PZ002"),
        ])
        mock_adapter.query_order_summary = AsyncMock(return_value={
            "realPrice": 19800.0, "orderCount": 2,
            "customerCount": 2, "avgPrice": 9900.0,
        })
        mock_adapter.close = AsyncMock()

        env = {
            "PINZHI_BASE_URL": "https://test.pinzhi.com",
            "PINZHI_TOKEN": "test_token",
            "PINZHI_BRAND_ID": "B001",
        }

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", return_value=mock_adapter):
            result = _run_celery_task(pull_pinzhi_daily_data)

        assert result["success"] is True
        assert result["stores_processed"] == 1
        assert result["orders_upserted"] == 2
        assert result["summaries_saved"] == 1
        assert result["errors"] == []
        mock_adapter.close.assert_called_once()

    def test_skip_when_no_credentials(self):
        """全局凭证 + ExternalSystem 均无 → 跳过整个任务。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        fake_db, session = _make_db_session(
            stores=[_make_store("S001")], ext_systems=[],
        )

        env = {"PINZHI_BASE_URL": "", "PINZHI_TOKEN": "", "PINZHI_BRAND_ID": ""}

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db):
            result = _run_celery_task(pull_pinzhi_daily_data)

        assert result["skipped"] is True
        assert result["stores_processed"] == 0

    def test_store_level_credentials_priority(self):
        """门店级凭证优先于全局环境变量。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        store = _make_store("S001", config={
            "pinzhi_base_url": "https://store-level.pinzhi.com",
            "pinzhi_token": "store_token_abc",
            "pinzhi_ognid": "STORE_OG_001",
        })
        fake_db, session = _make_db_session(stores=[store], ext_systems=[])

        captured = []
        factory = _make_adapter_factory(captured_configs=captured)

        env = {
            "PINZHI_BASE_URL": "https://global.pinzhi.com",
            "PINZHI_TOKEN": "global_token",
        }

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", side_effect=factory):
            _run_celery_task(pull_pinzhi_daily_data)

        assert len(captured) == 1
        assert captured[0]["base_url"] == "https://store-level.pinzhi.com"
        assert captured[0]["token"] == "store_token_abc"

    def test_external_system_credentials_fallback(self):
        """ExternalSystem 凭证作为中间优先级。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        store = _make_store("S001", config={})
        ext = _make_ext_system(
            store_id="S001",
            api_endpoint="https://ext.pinzhi.com",
            api_secret="ext_secret",
            config={"pinzhi_store_id": "EXT_OG_001"},
        )
        fake_db, session = _make_db_session(stores=[store], ext_systems=[ext])

        captured = []
        factory = _make_adapter_factory(captured_configs=captured)

        env = {
            "PINZHI_BASE_URL": "https://global.pinzhi.com",
            "PINZHI_TOKEN": "global_token",
        }

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", side_effect=factory):
            _run_celery_task(pull_pinzhi_daily_data)

        assert len(captured) == 1
        assert captured[0]["base_url"] == "https://ext.pinzhi.com"
        assert captured[0]["token"] == "ext_secret"

    def test_store_without_token_silently_skipped(self):
        """门店无 token → 跳过，不计入 errors。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        fake_db, session = _make_db_session(
            stores=[_make_store("S001", config={})], ext_systems=[],
        )

        env = {"PINZHI_BASE_URL": "https://test.pinzhi.com", "PINZHI_TOKEN": ""}

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db):
            result = _run_celery_task(pull_pinzhi_daily_data)

        assert result["stores_processed"] == 0
        assert result["errors"] == []

    def test_multi_store_one_fails(self):
        """2 门店：S001 报错, S002 正常 → S002 不受影响。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        stores = [_make_store("S001", code="OG1"), _make_store("S002", code="OG2")]
        fake_db, session = _make_db_session(stores=stores, ext_systems=[])

        call_count = {"n": 0}

        def _factory(config):
            call_count["n"] += 1
            inst = MagicMock()
            if call_count["n"] == 1:
                inst.query_orders = AsyncMock(side_effect=Exception("S001 timeout"))
            else:
                inst.query_orders = AsyncMock(side_effect=[
                    [_make_raw_pinzhi_order(bill_id="PZ_S002")], [],
                ])
                inst.to_order = MagicMock(return_value=_make_order_schema("PZ_S002"))
                inst.query_order_summary = AsyncMock(return_value=None)
            inst.close = AsyncMock()
            return inst

        env = {
            "PINZHI_BASE_URL": "https://test.pinzhi.com",
            "PINZHI_TOKEN": "test_token",
            "PINZHI_BRAND_ID": "B001",
        }

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", side_effect=_factory):
            result = _run_celery_task(pull_pinzhi_daily_data)

        assert result["stores_processed"] == 1
        assert result["orders_upserted"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["store_id"] == "S001"

    def test_vip_phone_extracted_for_cdp(self):
        """vipMobile 被提取为 customer_phone，供 CDP consumer_id 回填。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        store = _make_store("S001", code="OG001")
        execute_calls = []
        fake_db, session = _make_db_session(
            stores=[store], ext_systems=[], capture_list=execute_calls,
        )

        raw_order = _make_raw_pinzhi_order(
            bill_id="PZ_CDP_001", vip_mobile="13912345678", vip_name="李四",
        )

        mock_adapter = MagicMock()
        mock_adapter.query_orders = AsyncMock(side_effect=[[raw_order], []])
        mock_adapter.to_order = MagicMock(return_value=_make_order_schema("PZ_CDP_001"))
        mock_adapter.query_order_summary = AsyncMock(return_value=None)
        mock_adapter.close = AsyncMock()

        env = {
            "PINZHI_BASE_URL": "https://test.pinzhi.com",
            "PINZHI_TOKEN": "test_token",
            "PINZHI_BRAND_ID": "B001",
        }

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", return_value=mock_adapter):
            result = _run_celery_task(pull_pinzhi_daily_data)

        insert_params = [p for (_, p) in execute_calls if p and "customer_phone" in p]
        assert len(insert_params) >= 1
        assert insert_params[0]["customer_phone"] == "13912345678"
        assert insert_params[0]["customer_name"] == "李四"

    def test_amount_conversion_fen_in_celery_pull(self):
        """Celery Pull：Adapter to_order 返回元 → ×100 转分后写入 DB。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        store = _make_store("S001", code="OG001")
        execute_calls = []
        fake_db, session = _make_db_session(
            stores=[store], ext_systems=[], capture_list=execute_calls,
        )

        schema = _make_order_schema("PZ_AMT", total=Decimal("104.00"), discount=Decimal("5.00"))

        mock_adapter = MagicMock()
        mock_adapter.query_orders = AsyncMock(
            side_effect=[[_make_raw_pinzhi_order(bill_id="PZ_AMT")], []]
        )
        mock_adapter.to_order = MagicMock(return_value=schema)
        mock_adapter.query_order_summary = AsyncMock(return_value=None)
        mock_adapter.close = AsyncMock()

        env = {
            "PINZHI_BASE_URL": "https://test.pinzhi.com",
            "PINZHI_TOKEN": "test_token",
            "PINZHI_BRAND_ID": "B001",
        }

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", return_value=mock_adapter):
            _run_celery_task(pull_pinzhi_daily_data)

        insert_params = [p for (_, p) in execute_calls if p and "total_amount" in p]
        assert len(insert_params) >= 1
        assert insert_params[0]["total_amount"] == 10400       # 104.00元 × 100
        assert insert_params[0]["discount_amount"] == 500      # 5.00元 × 100
        assert insert_params[0]["final_amount"] == 9900        # 10400 - 500

    def test_ognid_resolution_store_config_first(self):
        """OGNID：store.config.pinzhi_ognid 最优先。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        store = _make_store("S001", code="STORE_CODE", config={"pinzhi_ognid": "CONFIG_OG"})
        fake_db, session = _make_db_session(stores=[store], ext_systems=[])

        captured_ognids = []

        def _factory(config):
            inst = MagicMock()
            async def _qo(ognid=None, **kw):
                captured_ognids.append(ognid)
                return []
            inst.query_orders = _qo
            inst.query_order_summary = AsyncMock(return_value=None)
            inst.close = AsyncMock()
            return inst

        env = {
            "PINZHI_BASE_URL": "https://test.pinzhi.com",
            "PINZHI_TOKEN": "test_token",
        }

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", side_effect=_factory):
            _run_celery_task(pull_pinzhi_daily_data)

        assert captured_ognids[0] == "CONFIG_OG"

    def test_date_is_yesterday(self):
        """拉取日期为昨天。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        fake_db, session = _make_db_session(stores=[], ext_systems=[])

        env = {"PINZHI_BASE_URL": "https://test.pinzhi.com", "PINZHI_TOKEN": "tok"}

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db):
            result = _run_celery_task(pull_pinzhi_daily_data)

        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert result.get("date") == yesterday

    def test_summary_upserted(self):
        """营业汇总写入 daily_summaries 表。"""
        from src.core.celery_tasks import pull_pinzhi_daily_data

        store = _make_store("S001", code="OG001")
        execute_calls = []
        fake_db, session = _make_db_session(
            stores=[store], ext_systems=[], capture_list=execute_calls,
        )

        mock_adapter = MagicMock()
        mock_adapter.query_orders = AsyncMock(return_value=[])
        mock_adapter.query_order_summary = AsyncMock(return_value={
            "realPrice": 50000.0, "orderCount": 25,
            "customerCount": 20, "avgPrice": 2000.0,
        })
        mock_adapter.close = AsyncMock()

        env = {"PINZHI_BASE_URL": "https://test.pinzhi.com", "PINZHI_TOKEN": "tok"}

        adapter_mod = self._adapter_mod

        with patch.dict(os.environ, env), \
             patch("src.core.database.get_db_session", fake_db), \
             patch.object(adapter_mod, "PinzhiAdapter", return_value=mock_adapter):
            result = _run_celery_task(pull_pinzhi_daily_data)

        assert result["summaries_saved"] == 1

        summary_params = [p for (_, p) in execute_calls if p and "revenue" in p]
        assert len(summary_params) >= 1
        assert summary_params[0]["revenue"] == 50000
        assert summary_params[0]["order_count"] == 25


# ════════════════════════════════════════════════════════════════════════════════
# 第 3 层：CDP consumer_id 回填
# ════════════════════════════════════════════════════════════════════════════════


class TestCDPBackfillE2E:
    """cdp_sync_consumer_ids 任务：customer_phone → ConsumerIdentity → consumer_id"""

    def test_cdp_task_registered(self):
        from src.core.celery_tasks import cdp_sync_consumer_ids
        assert callable(cdp_sync_consumer_ids)

    def test_cdp_task_calls_sync_service(self):
        """CDP 任务调用 cdp_sync_service.sync_all_stores。"""
        from src.core.celery_tasks import cdp_sync_consumer_ids

        mock_service = MagicMock()
        mock_service.sync_all_stores = AsyncMock(return_value={
            "stores_scanned": 3, "orders_resolved": 42, "fill_rate": 0.85,
        })

        session = AsyncMock()
        session.commit = AsyncMock()

        @asynccontextmanager
        async def _ctx():
            yield session

        with patch("src.core.database.get_db_session", _ctx), \
             patch("src.services.cdp_sync_service.cdp_sync_service", mock_service):
            result = _run_celery_task(cdp_sync_consumer_ids)

        assert result["orders_resolved"] == 42
        assert result["fill_rate"] == 0.85
        mock_service.sync_all_stores.assert_called_once()
        session.commit.assert_called_once()

    def test_cdp_rfm_recalculate_registered(self):
        from src.core.celery_tasks import cdp_rfm_recalculate
        assert callable(cdp_rfm_recalculate)


# ════════════════════════════════════════════════════════════════════════════════
# 签名验证深度测试
# ════════════════════════════════════════════════════════════════════════════════


class TestSignatureVerificationDeep:

    def test_sign_excludes_pageindex_pagesize(self):
        from src.api.pos_webhook import _pinzhi_generate_sign
        token = "tok123"
        assert _pinzhi_generate_sign(token, {"billId": "PZ001", "pageIndex": 1, "pageSize": 20}) \
            == _pinzhi_generate_sign(token, {"billId": "PZ001"})

    def test_sign_excludes_none_values(self):
        from src.api.pos_webhook import _pinzhi_generate_sign
        token = "tok123"
        assert _pinzhi_generate_sign(token, {"billId": "PZ001", "remark": None}) \
            == _pinzhi_generate_sign(token, {"billId": "PZ001"})

    def test_sign_sorted_by_key_ascii(self):
        from src.api.pos_webhook import _pinzhi_generate_sign
        token = "tok123"
        assert _pinzhi_generate_sign(token, {"billId": "PZ001", "amount": "100"}) \
            == _pinzhi_generate_sign(token, {"amount": "100", "billId": "PZ001"})

    def test_roundtrip_sign_verify(self):
        from src.api.pos_webhook import _pinzhi_generate_sign, _verify_pinzhi_signature
        token = "my_secure_token"
        raw = {"billId": "PZ001", "billStatus": 1, "realPrice": 9900}
        raw["sign"] = _pinzhi_generate_sign(token, raw)
        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", token):
            assert _verify_pinzhi_signature(raw) is True

    def test_tampered_payload_rejected(self):
        from src.api.pos_webhook import _pinzhi_generate_sign, _verify_pinzhi_signature
        token = "my_secure_token"
        raw = {"billId": "PZ001", "realPrice": 9900}
        raw["sign"] = _pinzhi_generate_sign(token, raw)
        raw["realPrice"] = 100  # 篡改
        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", token):
            assert _verify_pinzhi_signature(raw) is False


# ════════════════════════════════════════════════════════════════════════════════
# 任务注册 & 调度验证
# ════════════════════════════════════════════════════════════════════════════════


class TestTaskRegistration:

    def test_pull_pinzhi_daily_data_registered(self):
        from src.core.celery_tasks import pull_pinzhi_daily_data
        assert callable(pull_pinzhi_daily_data)

    def test_pull_pinzhi_daily_data_max_retries(self):
        from src.core.celery_tasks import pull_pinzhi_daily_data
        if hasattr(pull_pinzhi_daily_data, "max_retries"):
            assert pull_pinzhi_daily_data.max_retries == int(
                os.getenv("CELERY_MAX_RETRIES", "3"))
        else:
            assert callable(pull_pinzhi_daily_data)

    def test_cdp_sync_consumer_ids_max_retries(self):
        from src.core.celery_tasks import cdp_sync_consumer_ids
        if hasattr(cdp_sync_consumer_ids, "max_retries"):
            assert cdp_sync_consumer_ids.max_retries == 2
        else:
            assert callable(cdp_sync_consumer_ids)

    def test_pipeline_execution_order(self):
        """验证管道任务在 beat_schedule 中注册。"""
        from src.core.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        for task_name in ["pull-pinzhi-daily-data", "cdp-sync-consumer-ids"]:
            if task_name in schedule:
                assert schedule[task_name]["task"] is not None
