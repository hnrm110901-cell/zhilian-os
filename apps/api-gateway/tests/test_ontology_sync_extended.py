"""
本体同步扩展功能单元测试

覆盖：
  - sync_suppliers_to_graph：供应商同步到图谱
  - sync_boms_to_graph：BOM 批量同步（含 HAS_BOM + REQUIRES 关系）
  - sync_waste_events_to_graph：损耗事件同步（含 TRIGGERED_BY 关系）
  - sync_ontology_from_pg：统一入口返回 8 类计数
  - Settings 中 NEO4J_* 配置项存在
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_db_session(query_results=None):
    """构造 async session mock，execute 返回 query_results 列表中的结果。"""
    session = AsyncMock()
    session.commit = AsyncMock()
    results = list(query_results or [])
    call_idx = {"n": 0}

    async def _execute(stmt, params=None):
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(results):
            return results[idx]
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    session.execute = _execute

    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx, session


def _scalar_result(items):
    """构造 scalars().all() 返回 items 的 mock result。"""
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_supplier(sid="SUP001"):
    s = MagicMock()
    s.id = sid
    s.name = "测试供应商"
    s.category = "food"
    s.phone = "13800138000"
    s.delivery_time = 2
    s.rating = 4.5
    s.status = "active"
    return s


def _make_bom_template(dish_id="DISH001", version="v1"):
    bom = MagicMock()
    bom.dish_id = dish_id
    bom.version = version
    bom.store_id = "S001"
    bom.is_active = True
    bom.effective_date = datetime(2026, 3, 1)
    bom.yield_rate = Decimal("0.85")
    bom.notes = "test"
    # items
    item1 = MagicMock()
    item1.ingredient_id = "ING001"
    item1.standard_qty = Decimal("500")
    item1.unit = "g"
    item1.waste_factor = Decimal("0.05")
    item2 = MagicMock()
    item2.ingredient_id = "ING002"
    item2.standard_qty = Decimal("200")
    item2.unit = "ml"
    item2.waste_factor = Decimal("0.02")
    bom.items = [item1, item2]
    return bom


def _make_waste_event(event_id="WE-001"):
    ev = MagicMock()
    ev.event_id = event_id
    ev.store_id = "S001"
    ev.ingredient_id = "ING001"
    ev.quantity = Decimal("2.5")
    ev.unit = "kg"
    ev.occurred_at = datetime(2026, 3, 15, 10, 30)
    ev.event_type = MagicMock()
    ev.event_type.value = "spoilage"
    ev.root_cause = "food_quality"
    ev.confidence = 0.85
    ev.assigned_staff_id = "STAFF001"
    return ev


# ════════════════════════════════════════════════════════════════════════════════
# Settings 配置项
# ════════════════════════════════════════════════════════════════════════════════


class TestNeo4jSettings:

    def test_settings_has_neo4j_uri(self):
        from src.core.config import Settings
        assert hasattr(Settings, "model_fields") or hasattr(Settings, "__fields__")
        s = Settings(
            DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
            REDIS_URL="redis://localhost",
            CELERY_BROKER_URL="redis://localhost",
            CELERY_RESULT_BACKEND="redis://localhost",
            SECRET_KEY="test",
            JWT_SECRET="test",
        )
        assert s.NEO4J_URI == "bolt://localhost:7687"
        assert s.NEO4J_USER == "neo4j"
        assert s.NEO4J_PASSWORD == "changeme"

    def test_settings_neo4j_override(self):
        with patch.dict(os.environ, {
            "NEO4J_URI": "bolt://custom:7687",
            "NEO4J_USER": "admin",
            "NEO4J_PASSWORD": "secret123",
        }):
            from src.core.config import Settings
            s = Settings(
                DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
                REDIS_URL="redis://localhost",
                CELERY_BROKER_URL="redis://localhost",
                CELERY_RESULT_BACKEND="redis://localhost",
                SECRET_KEY="test",
                JWT_SECRET="test",
            )
            assert s.NEO4J_URI == "bolt://custom:7687"
            assert s.NEO4J_USER == "admin"
            assert s.NEO4J_PASSWORD == "secret123"


# ════════════════════════════════════════════════════════════════════════════════
# sync_suppliers_to_graph
# ════════════════════════════════════════════════════════════════════════════════


class TestSyncSuppliersToGraph:

    @pytest.mark.asyncio
    async def test_syncs_active_suppliers(self):
        suppliers = [_make_supplier("SUP001"), _make_supplier("SUP002")]
        _, session = _make_db_session([_scalar_result(suppliers)])

        mock_repo = MagicMock()
        with patch("src.services.ontology_sync_service.get_ontology_repository", return_value=mock_repo):
            from src.services.ontology_sync_service import sync_suppliers_to_graph
            count = await sync_suppliers_to_graph(session, "tenant1")

        assert count == 2
        assert mock_repo.merge_node.call_count == 2
        # 验证第一个调用的节点类型和属性
        call_args = mock_repo.merge_node.call_args_list[0]
        assert call_args[0][0] == "Supplier"
        assert call_args[0][1] == "sup_id"

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_repo(self):
        _, session = _make_db_session()
        with patch("src.services.ontology_sync_service.get_ontology_repository", return_value=None):
            from src.services.ontology_sync_service import sync_suppliers_to_graph
            count = await sync_suppliers_to_graph(session, "t1")
        assert count == 0


# ════════════════════════════════════════════════════════════════════════════════
# sync_boms_to_graph
# ════════════════════════════════════════════════════════════════════════════════


class TestSyncBomsToGraph:

    @pytest.mark.asyncio
    async def test_syncs_bom_with_ingredients(self):
        bom = _make_bom_template("DISH001", "v1")
        _, session = _make_db_session([_scalar_result([bom])])

        mock_repo = MagicMock()
        with patch("src.services.ontology_sync_service.get_ontology_repository", return_value=mock_repo):
            from src.services.ontology_sync_service import sync_boms_to_graph
            count = await sync_boms_to_graph(session, "tenant1")

        assert count == 1
        # 1 BOM node + 1 HAS_BOM relation + 2 REQUIRES relations = 4 calls
        assert mock_repo.merge_node.call_count == 1
        assert mock_repo.merge_relation.call_count == 3  # 1 HAS_BOM + 2 REQUIRES

    @pytest.mark.asyncio
    async def test_bom_requires_has_waste_factor(self):
        bom = _make_bom_template()
        _, session = _make_db_session([_scalar_result([bom])])

        mock_repo = MagicMock()
        with patch("src.services.ontology_sync_service.get_ontology_repository", return_value=mock_repo):
            from src.services.ontology_sync_service import sync_boms_to_graph
            await sync_boms_to_graph(session, "tenant1")

        # 找到 REQUIRES 关系调用
        requires_calls = [
            c for c in mock_repo.merge_relation.call_args_list
            if c[0][3] == "REQUIRES"
        ]
        assert len(requires_calls) == 2
        # 检查 rel_props 包含 waste_factor
        props = requires_calls[0][1].get("rel_props", requires_calls[0][0][-1] if len(requires_calls[0][0]) > 7 else None)
        # merge_relation 的 rel_props 是 kwarg
        for call in requires_calls:
            assert "rel_props" in call[1]
            assert "waste_factor" in call[1]["rel_props"]


# ════════════════════════════════════════════════════════════════════════════════
# sync_waste_events_to_graph
# ════════════════════════════════════════════════════════════════════════════════


class TestSyncWasteEventsToGraph:

    @pytest.mark.asyncio
    async def test_syncs_waste_events_with_triggered_by(self):
        ev = _make_waste_event("WE-001")
        _, session = _make_db_session([_scalar_result([ev])])

        mock_repo = MagicMock()
        with patch("src.services.ontology_sync_service.get_ontology_repository", return_value=mock_repo):
            from src.services.ontology_sync_service import sync_waste_events_to_graph
            count = await sync_waste_events_to_graph(session, "tenant1")

        assert count == 1
        assert mock_repo.merge_node.call_count == 1
        # 验证 WasteEvent 节点包含 root_cause
        node_props = mock_repo.merge_node.call_args[0][3]
        assert node_props["root_cause"] == "food_quality"
        assert node_props["confidence"] == 0.85
        # 验证 TRIGGERED_BY 关系
        assert mock_repo.merge_relation.call_count == 1
        rel_call = mock_repo.merge_relation.call_args
        assert rel_call[0][3] == "TRIGGERED_BY"

    @pytest.mark.asyncio
    async def test_waste_event_without_staff_skips_relation(self):
        ev = _make_waste_event("WE-002")
        ev.assigned_staff_id = None
        _, session = _make_db_session([_scalar_result([ev])])

        mock_repo = MagicMock()
        with patch("src.services.ontology_sync_service.get_ontology_repository", return_value=mock_repo):
            from src.services.ontology_sync_service import sync_waste_events_to_graph
            count = await sync_waste_events_to_graph(session, "tenant1")

        assert count == 1
        assert mock_repo.merge_node.call_count == 1
        assert mock_repo.merge_relation.call_count == 0  # 无责任人，不建 TRIGGERED_BY


# ════════════════════════════════════════════════════════════════════════════════
# sync_ontology_from_pg 统一入口
# ════════════════════════════════════════════════════════════════════════════════


class TestSyncOntologyFromPgExtended:

    @pytest.mark.asyncio
    async def test_returns_all_eight_categories(self):
        """统一入口返回 8 类同步计数。"""
        mock_repo = MagicMock()

        # 为所有 8 个 select 查询准备空结果
        results = [_scalar_result([]) for _ in range(8)]
        _, session = _make_db_session(results)

        with patch("src.services.ontology_sync_service.get_ontology_repository", return_value=mock_repo):
            from src.services.ontology_sync_service import sync_ontology_from_pg
            result = await sync_ontology_from_pg(session, "tenant1")

        expected_keys = {"stores", "dishes", "ingredients", "staff", "orders", "suppliers", "boms", "waste_events"}
        assert set(result.keys()) == expected_keys
        # 全部空结果，所有计数为 0
        for key in expected_keys:
            assert result[key] == 0


# ════════════════════════════════════════════════════════════════════════════════
# Beat 调度注册校验
# ════════════════════════════════════════════════════════════════════════════════


class TestOntologyBeatSchedule:

    def test_ontology_sync_in_beat_schedule(self):
        from src.core.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "sync-ontology-graph" in schedule

    def test_ontology_sync_uses_correct_task_name(self):
        from src.core.celery_app import celery_app
        entry = celery_app.conf.beat_schedule["sync-ontology-graph"]
        assert entry["task"] == "tasks.daily_ontology_sync"

    def test_ontology_sync_uses_low_priority_queue(self):
        from src.core.celery_app import celery_app
        entry = celery_app.conf.beat_schedule["sync-ontology-graph"]
        assert entry["options"]["queue"] == "low_priority"
