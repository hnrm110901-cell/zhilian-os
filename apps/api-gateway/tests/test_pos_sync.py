"""
pos_sync API 单元测试

覆盖重点：
  1. PosSyncRequest 校验（adapter 枚举、日期格式）
  2. _sync_pinzhi   — 凭证缺失跳过 / per-store config 优先级
  3. _sync_tiancai  — 凭证缺失跳过 / fetch_orders_by_date 调用（非 query_orders）
  4. _sync_chixingyun — 凭证缺失跳过
  5. _sync_weishenghuo   — 凭证缺失跳过 / 增强逻辑（mock CRM + mock DB）
  6. _ADAPTER_HANDLERS 完整注册
  7. 动态 import 助手可正确加载类
"""
import os
import sys
import unittest.mock as _mock

# ── 测试环境变量 & 依赖打桩（必须在 src.* 导入前完成）──────────────────────────

for _k, _v in {
    "DATABASE_URL":  "postgresql+asyncpg://test:test@localhost/test",
    "SECRET_KEY":    "test-secret-key",
    "REDIS_URL":     "redis://localhost:6379/0",
}.items():
    os.environ.setdefault(_k, _v)

# 打桩：防止 pos_sync 的相对 import 触发真实 DB/Redis 初始化
_mods_to_stub = [
    "src.core.database",
    "src.core.dependencies",
    "src.models.store",
    "src.models.user",
    "packages.api_adapters.tiancai_shanglong",
    "packages.api_adapters.tiancai_shanglong.src",
    "packages.api_adapters.tiancai_shanglong.src.adapter",
]
for _mod in _mods_to_stub:
    if _mod not in sys.modules:
        sys.modules[_mod] = _mock.MagicMock()

# src 路径注入（pytest 从 apps/api-gateway/ 运行）
_gw_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _gw_root not in sys.path:
    sys.path.insert(0, _gw_root)
if os.path.join(_gw_root, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_gw_root, "src"))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.pos_sync import (
    PosSyncRequest,
    PosSyncResponse,
    StoreSyncSummary,
    BackfillRequest,
    BackfillResponse,
    _ADAPTER_HANDLERS,
    _pinzhi_adapter_class,
    _weishenghuo_adapter_class,
    _chixingyun_adapter_class,
    _sync_pinzhi,
    _sync_tiancai,
    _sync_chixingyun,
    _sync_weishenghuo,
)


# ── 测试辅助 ──────────────────────────────────────────────────────────────────

def _make_store(store_id: str, name: str = "测试门店", code: str = "TST", cfg: dict = None):
    s = MagicMock()
    s.id = store_id
    s.name = name
    s.code = code
    s.config = cfg or {}
    return s


def _make_session(stores: list, extra_rows=None):
    """构造模拟的 async DB session，支持按调用顺序返回不同结果。"""
    call_idx = [0]

    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value.all.return_value = stores

    # extra_rows：后续 execute 调用返回的行（可以是列表或单个 MagicMock）
    rows = extra_rows or []

    async def _execute(query, params=None):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx == 0:
            return mock_select_result
        if idx - 1 < len(rows):
            return rows[idx - 1]
        fallback = MagicMock()
        fallback.fetchone.return_value = [0, 0]
        fallback.fetchall.return_value = []
        return fallback

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


# ── PosSyncRequest 校验 ───────────────────────────────────────────────────────

class TestPosSyncRequestValidation:
    def test_valid_adapter_pinzhi(self):
        assert PosSyncRequest(adapter="pinzhi").adapter == "pinzhi"

    def test_valid_adapter_tiancai(self):
        assert PosSyncRequest(adapter="tiancai").adapter == "tiancai"

    def test_valid_adapter_chixingyun(self):
        assert PosSyncRequest(adapter="chixingyun").adapter == "chixingyun"

    def test_valid_adapter_weishenghuo(self):
        """weishenghuo 必须在合法枚举中"""
        assert PosSyncRequest(adapter="weishenghuo").adapter == "weishenghuo"

    def test_invalid_adapter_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PosSyncRequest(adapter="unknown_pos")

    def test_valid_sync_date(self):
        req = PosSyncRequest(adapter="pinzhi", sync_date="2026-03-14")
        assert req.sync_date == "2026-03-14"

    def test_invalid_date_format_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PosSyncRequest(adapter="pinzhi", sync_date="14/03/2026")

    def test_store_ids_optional(self):
        req = PosSyncRequest(adapter="pinzhi", store_ids=["s1", "s2"])
        assert req.store_ids == ["s1", "s2"]


# ── _ADAPTER_HANDLERS 注册 ────────────────────────────────────────────────────

class TestAdapterHandlersRegistry:
    def test_all_four_adapters_registered(self):
        for key in ("pinzhi", "tiancai", "chixingyun", "weishenghuo"):
            assert key in _ADAPTER_HANDLERS, f"{key} 未在 _ADAPTER_HANDLERS 中注册"

    def test_all_handlers_callable(self):
        for key, fn in _ADAPTER_HANDLERS.items():
            assert callable(fn), f"{key} handler 不可调用"


# ── 动态 import 助手 ──────────────────────────────────────────────────────────

class TestDynamicImports:
    def test_pinzhi_adapter_class_loads(self):
        cls = _pinzhi_adapter_class()
        assert cls.__name__ == "PinzhiAdapter"

    def test_weishenghuo_adapter_class_loads(self):
        cls = _weishenghuo_adapter_class()
        assert cls.__name__ == "AoqiweiCrmAdapter"

    def test_chixingyun_adapter_class_loads(self):
        cls = _chixingyun_adapter_class()
        assert cls.__name__ == "AoqiweiAdapter"


# ── _sync_pinzhi ──────────────────────────────────────────────────────────────

class TestSyncPinzhi:
    @pytest.mark.asyncio
    async def test_skipped_when_no_credentials(self, monkeypatch):
        """全局 + per-store 凭证都缺失时，门店被跳过并返回 error（非异常）"""
        monkeypatch.delenv("PINZHI_BASE_URL", raising=False)
        monkeypatch.delenv("PINZHI_TOKEN", raising=False)

        store = _make_store("s001", cfg={})
        session = _make_session([store])

        with patch("src.api.pos_sync.get_db_session", return_value=session):
            resp = await _sync_pinzhi("2026-03-13", None)

        assert resp.adapter == "pinzhi"
        assert len(resp.stores) == 1
        assert resp.stores[0].error is not None
        assert "凭证未配置" in resp.stores[0].error

    @pytest.mark.asyncio
    async def test_per_store_config_overrides_global(self, monkeypatch):
        """store.config 的 pinzhi_token 应优先于全局环境变量"""
        monkeypatch.setenv("PINZHI_BASE_URL", "https://global.pinzhi.com")
        monkeypatch.setenv("PINZHI_TOKEN", "global-token")

        store = _make_store("s-czyz", "尝在一起总店", cfg={
            "pinzhi_base_url": "https://czyz.pinzhi.com",
            "pinzhi_token": "czyz-token",
            "pinzhi_ognid": "czyz_001",
        })

        db_row = MagicMock()
        db_row.fetchone.return_value = [0, 0]
        session = _make_session([store], extra_rows=[db_row])

        captured = {}

        def mock_adapter_cls(config):
            captured.update(config)
            inst = MagicMock()
            inst.query_orders = AsyncMock(return_value=[])
            return inst

        with patch("src.api.pos_sync.get_db_session", return_value=session), \
             patch("src.api.pos_sync._pinzhi_adapter_class", return_value=mock_adapter_cls):
            await _sync_pinzhi("2026-03-13", None)

        assert captured.get("base_url") == "https://czyz.pinzhi.com"
        assert captured.get("token") == "czyz-token"

    @pytest.mark.asyncio
    async def test_multiple_stores_each_get_own_adapter(self, monkeypatch):
        """三家门店（尝在一起/最黔线/尚宫厨）各自使用独立 token"""
        monkeypatch.delenv("PINZHI_BASE_URL", raising=False)
        monkeypatch.delenv("PINZHI_TOKEN", raising=False)

        stores = [
            _make_store("s-czyz", "尝在一起", cfg={"pinzhi_base_url": "https://api.pz.cn", "pinzhi_token": "t-czyz"}),
            _make_store("s-zqx",  "最黔线",   cfg={"pinzhi_base_url": "https://api.pz.cn", "pinzhi_token": "t-zqx"}),
            _make_store("s-sgc",  "尚宫厨",   cfg={"pinzhi_base_url": "https://api.pz.cn", "pinzhi_token": "t-sgc"}),
        ]

        db_row = MagicMock()
        db_row.fetchone.return_value = [0, 0]
        session = _make_session(stores, extra_rows=[db_row, db_row, db_row])

        created_tokens = []

        def mock_adapter_cls(config):
            created_tokens.append(config.get("token"))
            inst = MagicMock()
            inst.query_orders = AsyncMock(return_value=[])
            return inst

        with patch("src.api.pos_sync.get_db_session", return_value=session), \
             patch("src.api.pos_sync._pinzhi_adapter_class", return_value=mock_adapter_cls):
            resp = await _sync_pinzhi("2026-03-13", None)

        assert len(resp.stores) == 3
        assert set(created_tokens) == {"t-czyz", "t-zqx", "t-sgc"}


# ── _sync_tiancai ─────────────────────────────────────────────────────────────

class TestSyncTiancai:
    @pytest.mark.asyncio
    async def test_skipped_when_no_credentials(self, monkeypatch):
        """TIANCAI_APP_ID / APP_SECRET 未配置时立即返回 skipped_reason"""
        monkeypatch.delenv("TIANCAI_APP_ID", raising=False)
        monkeypatch.delenv("TIANCAI_APP_SECRET", raising=False)

        resp = await _sync_tiancai("2026-03-13", None)

        assert resp.success is False
        assert resp.adapter == "tiancai"
        assert resp.skipped_reason is not None
        assert "APP_ID" in resp.skipped_reason or "APP_SECRET" in resp.skipped_reason

    @pytest.mark.asyncio
    async def test_calls_fetch_orders_by_date_not_query_orders(self, monkeypatch):
        """
        核心 Bug 修复验证：必须调用 fetch_orders_by_date，
        不能调用旧的（不存在的）query_orders 方法。
        """
        monkeypatch.setenv("TIANCAI_APP_ID", "test_app_id")
        monkeypatch.setenv("TIANCAI_APP_SECRET", "test_secret")

        store = _make_store("s-tc-001")
        db_row = MagicMock()
        db_row.fetchone.return_value = [0, 0]
        session = _make_session([store], extra_rows=[db_row])

        fetch_calls = []

        mock_adapter = MagicMock()
        mock_adapter.query_orders = MagicMock(
            side_effect=AttributeError("❌ query_orders 不应被调用")
        )

        async def mock_fetch(date_str, page=1, page_size=100, status=None):
            fetch_calls.append({"date_str": date_str, "page": page})
            return {"items": [], "page": page, "page_size": 100, "total": 0, "has_more": False}

        mock_adapter.fetch_orders_by_date = mock_fetch
        mock_adapter_cls = MagicMock(return_value=mock_adapter)

        # 替换 sys.modules 中已打桩的 TiancaiShanglongAdapter
        sys.modules["packages.api_adapters.tiancai_shanglong.src.adapter"].TiancaiShanglongAdapter = mock_adapter_cls

        with patch("src.api.pos_sync.get_db_session", return_value=session):
            resp = await _sync_tiancai("2026-03-13", None)

        assert len(fetch_calls) >= 1, "fetch_orders_by_date 未被调用"
        assert fetch_calls[0]["date_str"] == "2026-03-13"
        assert fetch_calls[0]["page"] == 1
        assert resp.adapter == "tiancai"

    @pytest.mark.asyncio
    async def test_pagination_stops_when_has_more_false(self, monkeypatch):
        """has_more=False 时只调用第 1 页，不翻页"""
        monkeypatch.setenv("TIANCAI_APP_ID", "app_id")
        monkeypatch.setenv("TIANCAI_APP_SECRET", "app_secret")

        store = _make_store("s-tc-002")
        db_row = MagicMock()
        db_row.fetchone.return_value = [0, 0]
        session = _make_session([store], extra_rows=[db_row])

        pages = []
        mock_adapter = MagicMock()

        async def mock_fetch(date_str, page=1, page_size=100, status=None):
            pages.append(page)
            return {"items": [], "page": page, "page_size": 100, "total": 0, "has_more": False}

        mock_adapter.fetch_orders_by_date = mock_fetch
        sys.modules["packages.api_adapters.tiancai_shanglong.src.adapter"].TiancaiShanglongAdapter = MagicMock(return_value=mock_adapter)

        with patch("src.api.pos_sync.get_db_session", return_value=session):
            await _sync_tiancai("2026-03-13", None)

        assert pages == [1]


# ── _sync_chixingyun ─────────────────────────────────────────────────────

class TestSyncAoqiweiSupply:
    @pytest.mark.asyncio
    async def test_skipped_when_no_credentials(self, monkeypatch):
        monkeypatch.delenv("AOQIWEI_APP_KEY", raising=False)
        monkeypatch.delenv("AOQIWEI_APP_SECRET", raising=False)

        resp = await _sync_chixingyun("2026-03-13", None)

        assert resp.success is False
        assert resp.adapter == "chixingyun"
        assert resp.skipped_reason is not None


# ── _sync_weishenghuo ─────────────────────────────────────────────────────────

class TestSyncAoqiweiCrm:
    @pytest.mark.asyncio
    async def test_skipped_when_no_credentials(self, monkeypatch):
        monkeypatch.delenv("AOQIWEI_CRM_APPID", raising=False)
        monkeypatch.delenv("AOQIWEI_CRM_APPKEY", raising=False)

        # 实现先查 DB (stores + ExternalSystem)，再判断凭证，需提供空结果的 mock session
        empty_ext = MagicMock()
        empty_ext.scalars.return_value.all.return_value = []

        idx = [0]

        async def _execute(q, p=None):
            i = idx[0]; idx[0] += 1
            r = MagicMock()
            r.scalars.return_value.all.return_value = []  # stores 和 ExternalSystem 均为空
            return r

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=_execute)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        with patch("src.api.pos_sync.get_db_session", return_value=session):
            resp = await _sync_weishenghuo("2026-03-13", None)

        assert resp.success is False
        assert resp.adapter == "weishenghuo"
        assert resp.skipped_reason is not None
        assert "AOQIWEI_CRM_APPID" in resp.skipped_reason

    @pytest.mark.asyncio
    async def test_enriches_two_phones_per_store(self, monkeypatch):
        """2 个手机号各调用一次 CRM API，返回正确 totals"""
        monkeypatch.setenv("AOQIWEI_CRM_APPID", "crm_appid")
        monkeypatch.setenv("AOQIWEI_CRM_APPKEY", "crm_appkey")

        store = _make_store("s-crm-001", "CRM测试门店")

        mock_phones_result = MagicMock()
        mock_phones_result.fetchall.return_value = [("13800138000",), ("13900139000",)]

        mock_update_result = MagicMock()

        db_row_idx = [0]

        # 实现的 DB 调用顺序：
        #   idx=0  SELECT stores
        #   idx=1  SELECT ExternalSystem（凭证来源查询）
        #   idx=2  SELECT DISTINCT customer_phone（每个 store 一次）
        #   idx=3+ UPDATE orders（每个 phone 一次）

        mock_ext_result = MagicMock()
        mock_ext_result.scalars.return_value.all.return_value = []  # 无 ExternalSystem 记录

        async def _execute(query, params=None):
            idx = db_row_idx[0]
            db_row_idx[0] += 1
            if idx == 0:
                # SELECT stores
                r = MagicMock()
                r.scalars.return_value.all.return_value = [store]
                return r
            elif idx == 1:
                # SELECT ExternalSystem
                return mock_ext_result
            elif idx == 2:
                # SELECT DISTINCT customer_phone
                return mock_phones_result
            else:
                # UPDATE orders（每个 phone 一次）
                return mock_update_result

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=_execute)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        mock_crm = AsyncMock()
        mock_crm.get_member_info = AsyncMock(return_value={
            "level_name": "金卡", "balance": 5000, "point": 200, "cno": "MBR_X",
        })
        mock_crm.aclose = AsyncMock()
        mock_crm_cls = MagicMock(return_value=mock_crm)

        with patch("src.api.pos_sync.get_db_session", return_value=session), \
             patch("src.api.pos_sync._weishenghuo_adapter_class", return_value=mock_crm_cls):
            resp = await _sync_weishenghuo("2026-03-13", None)

        assert resp.adapter == "weishenghuo"
        assert resp.success is True
        assert mock_crm.get_member_info.call_count == 2
        assert resp.stores[0].pos_orders == 2    # 增强会员数
        assert resp.totals["members_enriched"] == 2
        assert resp.totals["unique_phones_found"] == 2

    @pytest.mark.asyncio
    async def test_crm_exception_captured_in_store_error(self, monkeypatch):
        """CRM API 异常被捕获，store.error 有值，整体 success=False"""
        monkeypatch.setenv("AOQIWEI_CRM_APPID", "x")
        monkeypatch.setenv("AOQIWEI_CRM_APPKEY", "y")

        store = _make_store("s-crm-002", "错误门店")

        mock_phones_result = MagicMock()
        mock_phones_result.fetchall.return_value = [("13800000001",)]

        idx = [0]

        mock_ext_result = MagicMock()
        mock_ext_result.scalars.return_value.all.return_value = []

        async def _execute(q, p=None):
            i = idx[0]; idx[0] += 1
            if i == 0:
                r = MagicMock(); r.scalars.return_value.all.return_value = [store]; return r
            if i == 1:
                return mock_ext_result  # SELECT ExternalSystem
            return mock_phones_result

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=_execute)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        mock_crm = AsyncMock()
        mock_crm.get_member_info = AsyncMock(side_effect=Exception("CRM网络超时"))
        mock_crm.aclose = AsyncMock()

        with patch("src.api.pos_sync.get_db_session", return_value=session), \
             patch("src.api.pos_sync._weishenghuo_adapter_class", return_value=MagicMock(return_value=mock_crm)):
            resp = await _sync_weishenghuo("2026-03-13", None)

        assert resp.stores[0].error is not None
        assert "超时" in resp.stores[0].error

    @pytest.mark.asyncio
    async def test_totals_contain_note(self, monkeypatch):
        """totals 包含无批量 API 的说明 note"""
        monkeypatch.setenv("AOQIWEI_CRM_APPID", "x")
        monkeypatch.setenv("AOQIWEI_CRM_APPKEY", "y")

        session = AsyncMock()
        r = MagicMock(); r.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=r)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        with patch("src.api.pos_sync.get_db_session", return_value=session), \
             patch("src.api.pos_sync._weishenghuo_adapter_class", return_value=MagicMock()):
            resp = await _sync_weishenghuo("2026-03-13", None)

        assert "note" in resp.totals
        assert resp.totals["stores_processed"] == 0


# ── BackfillRequest 校验 ──────────────────────────────────────────────────────

class TestBackfillRequestValidation:
    def test_valid_adapter_pinzhi(self):
        req = BackfillRequest(adapter="pinzhi", start_date="2026-02-14", end_date="2026-03-14")
        assert req.adapter == "pinzhi"
        assert req.max_days == 30

    def test_invalid_adapter_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BackfillRequest(adapter="unknown", start_date="2026-02-14", end_date="2026-03-14")

    def test_max_days_default_30(self):
        req = BackfillRequest(adapter="pinzhi", start_date="2026-02-14", end_date="2026-03-14")
        assert req.max_days == 30

    def test_max_days_custom(self):
        req = BackfillRequest(adapter="pinzhi", start_date="2026-01-01", end_date="2026-03-14", max_days=90)
        assert req.max_days == 90

    def test_store_ids_optional(self):
        req = BackfillRequest(
            adapter="pinzhi", start_date="2026-02-14", end_date="2026-03-14",
            store_ids=["CZYZ-2461", "ZQX-20529"],
        )
        assert req.store_ids == ["CZYZ-2461", "ZQX-20529"]


# ── BackfillResponse 结构 ─────────────────────────────────────────────────────

class TestBackfillResponseStructure:
    def test_all_required_fields_present(self):
        resp = BackfillResponse(
            adapter="pinzhi",
            start_date="2026-03-01",
            end_date="2026-03-02",
            days_requested=2,
            days_processed=2,
            total_orders_written=50,
            total_revenue_yuan=3000.00,
            days=[],
            triggered_at="2026-03-15T00:00:00",
        )
        assert resp.adapter == "pinzhi"
        assert resp.days_requested == 2
        assert resp.total_orders_written == 50

    def test_days_list_contains_day_summaries(self):
        from src.api.pos_sync import BackfillDaySummary
        day = BackfillDaySummary(
            date="2026-03-01", success=True, stores_processed=3,
            total_orders=20, total_revenue_yuan=1500.00,
        )
        assert day.success is True
        assert day.error is None
