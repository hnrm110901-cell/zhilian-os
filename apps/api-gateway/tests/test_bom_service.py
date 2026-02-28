"""
BOM 服务单元测试

覆盖：
  - BOMTemplate CRUD（创建/查询/停用）
  - 版本激活时自动停用旧版本
  - BOMItem 增删改
  - BOMTemplate.total_cost 属性
  - Neo4j 同步失败不阻断业务
"""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.bom import BOMItem, BOMTemplate
from src.services.bom_service import BOMService


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_bom(
    dish_id: str = None,
    version: str = "v1",
    is_active: bool = True,
    is_approved: bool = False,
) -> BOMTemplate:
    bom = BOMTemplate()
    bom.id = uuid.uuid4()
    bom.store_id = "store-001"
    bom.dish_id = uuid.UUID(dish_id) if dish_id else uuid.uuid4()
    bom.version = version
    bom.effective_date = datetime.utcnow()
    bom.expiry_date = None
    bom.yield_rate = Decimal("1.0")
    bom.is_active = is_active
    bom.is_approved = is_approved
    bom.items = []
    return bom


def _make_item(
    bom: BOMTemplate,
    ingredient_id: str = "ING-001",
    standard_qty: float = 100.0,
    unit_cost: int = 50,
) -> BOMItem:
    item = BOMItem()
    item.id = uuid.uuid4()
    item.bom_id = bom.id
    item.store_id = bom.store_id
    item.ingredient_id = ingredient_id
    item.standard_qty = Decimal(str(standard_qty))
    item.unit = "g"
    item.unit_cost = unit_cost
    item.waste_factor = Decimal("0.0")
    item.is_key_ingredient = False
    item.is_optional = False
    return item


def _mock_db() -> AsyncMock:
    """构造最小化 AsyncSession mock"""
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ── BOMTemplate.total_cost ────────────────────────────────────────────────────

class TestBOMTemplateTotalCost:
    def test_no_items(self):
        bom = _make_bom()
        assert bom.total_cost == 0

    def test_single_item(self):
        bom = _make_bom()
        item = _make_item(bom, standard_qty=200.0, unit_cost=30)
        bom.items = [item]
        assert bom.total_cost == 200.0 * 30  # 6000

    def test_multiple_items(self):
        bom = _make_bom()
        item1 = _make_item(bom, ingredient_id="ING-001", standard_qty=100.0, unit_cost=50)
        item2 = _make_item(bom, ingredient_id="ING-002", standard_qty=50.0, unit_cost=20)
        bom.items = [item1, item2]
        assert bom.total_cost == 100.0 * 50 + 50.0 * 20  # 6000

    def test_item_with_none_unit_cost(self):
        bom = _make_bom()
        item = _make_item(bom, unit_cost=None)
        item.unit_cost = None
        bom.items = [item]
        assert bom.total_cost == 0


# ── BOMService.create_bom ─────────────────────────────────────────────────────

class TestCreateBOM:
    @pytest.mark.asyncio
    async def test_create_active_bom_deactivates_previous(self):
        db = _mock_db()
        svc = BOMService(db)

        # flush + refresh で bom.id 等を返す用に refresh をセット
        created_bom = _make_bom(version="v2")

        async def fake_refresh(obj):
            pass

        db.refresh = fake_refresh

        # execute が 2 回呼ばれる（update旧版 + flush後 select）は AsyncMock で対応
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        dish_id = str(uuid.uuid4())
        bom = await svc.create_bom(
            store_id="store-001",
            dish_id=dish_id,
            version="v2",
            activate=True,
        )

        # db.execute should be called (for the update deactivate query)
        assert db.execute.called
        # db.add should be called with a BOMTemplate
        db.add.assert_called_once()
        added_obj = db.add.call_args[0][0]
        assert isinstance(added_obj, BOMTemplate)
        assert added_obj.is_active is True
        assert added_obj.version == "v2"

    @pytest.mark.asyncio
    async def test_create_inactive_bom_skips_deactivation(self):
        db = _mock_db()
        svc = BOMService(db)
        db.refresh = AsyncMock()

        dish_id = str(uuid.uuid4())
        bom = await svc.create_bom(
            store_id="store-001",
            dish_id=dish_id,
            version="v1",
            activate=False,
        )

        # No execute call for deactivating old version
        assert not db.execute.called
        db.add.assert_called_once()
        added_obj = db.add.call_args[0][0]
        assert added_obj.is_active is False


# ── BOMService.approve_bom ────────────────────────────────────────────────────

class TestApproveBOM:
    @pytest.mark.asyncio
    async def test_approve_sets_flag(self):
        db = _mock_db()
        svc = BOMService(db)

        bom = _make_bom(is_approved=False)
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=bom)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.approve_bom(str(bom.id), approver="manager-001")

        assert result is not None
        assert result.is_approved is True
        assert result.approved_by == "manager-001"
        assert result.approved_at is not None

    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_none(self):
        db = _mock_db()
        svc = BOMService(db)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.approve_bom(str(uuid.uuid4()), approver="admin")
        assert result is None


# ── BOMService.delete_bom ─────────────────────────────────────────────────────

class TestDeleteBOM:
    @pytest.mark.asyncio
    async def test_delete_unapproved_bom(self):
        db = _mock_db()
        svc = BOMService(db)
        db.delete = AsyncMock()

        bom = _make_bom(is_approved=False)
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=bom)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.delete_bom(str(bom.id))
        assert result is True
        db.delete.assert_called_once_with(bom)

    @pytest.mark.asyncio
    async def test_cannot_delete_approved_bom(self):
        db = _mock_db()
        svc = BOMService(db)

        bom = _make_bom(is_approved=True)
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=bom)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.delete_bom(str(bom.id))
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self):
        db = _mock_db()
        svc = BOMService(db)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.delete_bom(str(uuid.uuid4()))
        assert result is False


# ── BOMService.add_bom_item ───────────────────────────────────────────────────

class TestAddBOMItem:
    @pytest.mark.asyncio
    async def test_add_item_to_existing_bom(self):
        db = _mock_db()
        svc = BOMService(db)

        bom = _make_bom()
        db.refresh = AsyncMock()

        # get_bom calls db.execute → returns bom
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=bom)
        db.execute = AsyncMock(return_value=scalar_result)

        item = await svc.add_bom_item(
            bom_id=str(bom.id),
            ingredient_id="ING-TOMATO",
            standard_qty=150.0,
            unit="g",
            unit_cost=25,
        )

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, BOMItem)
        assert added.ingredient_id == "ING-TOMATO"
        assert float(added.standard_qty) == 150.0
        assert added.unit_cost == 25

    @pytest.mark.asyncio
    async def test_add_item_to_nonexistent_bom_raises(self):
        db = _mock_db()
        svc = BOMService(db)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        with pytest.raises(ValueError, match="不存在"):
            await svc.add_bom_item(
                bom_id=str(uuid.uuid4()),
                ingredient_id="ING-001",
                standard_qty=100.0,
                unit="g",
            )


# ── BOMService.update_bom_item ────────────────────────────────────────────────

class TestUpdateBOMItem:
    @pytest.mark.asyncio
    async def test_update_qty_and_unit(self):
        db = _mock_db()
        svc = BOMService(db)

        bom = _make_bom()
        item = _make_item(bom)
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=item)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.update_bom_item(
            item_id=str(item.id),
            standard_qty=200.0,
            unit="ml",
        )

        assert result is not None
        assert float(result.standard_qty) == 200.0
        assert result.unit == "ml"

    @pytest.mark.asyncio
    async def test_update_nonexistent_item(self):
        db = _mock_db()
        svc = BOMService(db)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.update_bom_item(str(uuid.uuid4()), standard_qty=99.0)
        assert result is None


# ── BOMService.remove_bom_item ────────────────────────────────────────────────

class TestRemoveBOMItem:
    @pytest.mark.asyncio
    async def test_remove_existing_item(self):
        db = _mock_db()
        svc = BOMService(db)
        db.delete = AsyncMock()

        bom = _make_bom()
        item = _make_item(bom)
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=item)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.remove_bom_item(str(item.id))
        assert result is True
        db.delete.assert_called_once_with(item)

    @pytest.mark.asyncio
    async def test_remove_nonexistent_item(self):
        db = _mock_db()
        svc = BOMService(db)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.remove_bom_item(str(uuid.uuid4()))
        assert result is False


# ── BOMService.sync_to_neo4j ──────────────────────────────────────────────────

class TestSyncToNeo4j:
    @pytest.mark.asyncio
    async def test_sync_failure_does_not_raise(self):
        """Neo4j 不可用时同步失败不抛异常，仅记录 warning"""
        import sys
        from unittest.mock import patch as mpatch

        db = _mock_db()
        svc = BOMService(db)

        bom = _make_bom()
        bom.items = [_make_item(bom)]

        # neo4j 包未安装时，使用 sys.modules mock 绕过 import
        fake_data_sync = MagicMock()
        fake_data_sync.OntologyDataSync.side_effect = RuntimeError("no neo4j connection")

        with mpatch.dict(
            sys.modules,
            {
                "neo4j": MagicMock(),
                "src.ontology": MagicMock(),
                "src.ontology.data_sync": fake_data_sync,
            },
        ):
            with mpatch("src.services.bom_service.logger") as mock_logger:
                await svc.sync_to_neo4j(bom)
                mock_logger.warning.assert_called_once()
