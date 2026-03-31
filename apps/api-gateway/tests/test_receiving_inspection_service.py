"""
tests/test_receiving_inspection_service.py

ReceivingInspectionService 单元测试 — Phase 2b 收货验收

覆盖（12个测试）：
  - 开始收货（正常）
  - 录入条目（正常 + 自动检测 shortage/quality_issue）
  - 录入条目（质检 reject 标记为 has_quality_issue）
  - complete_receiving（pass 条目入库）
  - complete_receiving（reject 条目不入库 + 创建争议）
  - complete_receiving（shortage 自动创建争议）
  - complete_receiving（conditional 自动创建 quality 争议）
  - complete_receiving（状态不可重复 complete）
  - complete_receiving（无条目应拒绝）
  - file_dispute（手动提交争议）
  - get_receiving_stats（统计计算）
  - _auto_detect_issues_inline（纯逻辑单元测试）
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-xx")

from src.models.receiving_inspection import (
    DisputeResolution,
    DisputeType,
    PurchaseReceiving,
    PurchaseReceivingItem,
    QualityStatus,
    ReceivingDispute,
    ReceivingStatus,
)
from src.models.inventory import InventoryItem, InventoryTransaction
from src.services.receiving_inspection_service import ReceivingInspectionService


# ── 辅助工厂 ──────────────────────────────────────────────────────────────────

STORE_ID = uuid.uuid4()
RECEIVER_ID = uuid.uuid4()
RECEIVING_ID = uuid.uuid4()
ITEM_ID = uuid.uuid4()
ING_ID = uuid.uuid4()


def _make_receiving(
    status: ReceivingStatus = ReceivingStatus.IN_PROGRESS,
    store_id=STORE_ID,
) -> MagicMock:
    r = MagicMock(spec=PurchaseReceiving)
    r.id = RECEIVING_ID
    r.receiving_no = "REC-20260331-0001"
    r.store_id = store_id
    r.status = status
    r.received_by = RECEIVER_ID
    r.received_at = datetime.utcnow()
    r.supplier_name = "测试供应商"
    r.total_amount_fen = 0
    r.created_at = datetime.utcnow()
    return r


def _make_item(
    quality_status: QualityStatus = QualityStatus.PASS,
    received_qty: float = 10.0,
    ordered_qty: float = 10.0,
    rejected_qty: float = 0.0,
    has_shortage: bool = False,
    has_quality_issue: bool = False,
    unit_price_fen: int = 2000,
    ingredient_name: str = "猪肉",
) -> MagicMock:
    item = MagicMock(spec=PurchaseReceivingItem)
    item.id = ITEM_ID
    item.receiving_id = RECEIVING_ID
    item.ingredient_id = ING_ID
    item.ingredient_name = ingredient_name
    item.unit = "kg"
    item.ordered_qty = ordered_qty
    item.received_qty = received_qty
    item.rejected_qty = rejected_qty
    item.unit_price_fen = unit_price_fen
    item.quality_status = quality_status
    item.quality_notes = None
    item.has_shortage = has_shortage
    item.has_quality_issue = has_quality_issue
    item.temperature = None
    item.expiry_date = None
    item.batch_no = None
    return item


def _make_inv(name: str = "猪肉", qty: float = 50.0) -> MagicMock:
    inv = MagicMock(spec=InventoryItem)
    inv.id = "INV_001"
    inv.store_id = str(STORE_ID)
    inv.name = name
    inv.current_quantity = qty
    inv.unit_cost = None
    return inv


# ── 测试 ──────────────────────────────────────────────────────────────────────

class TestStartReceiving:

    @pytest.mark.asyncio
    async def test_start_success(self):
        """正常开始收货"""
        svc = ReceivingInspectionService()
        svc._generate_receiving_no = AsyncMock(return_value="REC-20260331-0001")

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            session = AsyncMock()
            session.add = MagicMock()
            session.commit = AsyncMock()
            session.refresh = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.start_receiving(
                store_id=str(STORE_ID),
                receiver_id=str(RECEIVER_ID),
                supplier_name="测试供应商",
            )

        assert result["receiving_no"] == "REC-20260331-0001"
        assert result["status"] == ReceivingStatus.IN_PROGRESS.value


class TestRecordItem:

    @pytest.mark.asyncio
    async def test_record_item_pass(self):
        """录入 pass 条目，无 shortage 无 quality_issue"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving()

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=receiving)
            return result

        session = AsyncMock()
        session.execute = fake_execute
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.record_item(
                receiving_id=str(RECEIVING_ID),
                ingredient_id=str(ING_ID),
                ingredient_name="猪肉",
                unit="kg",
                received_qty=10.0,
                quality_status="pass",
                ordered_qty=10.0,
            )

        assert result["has_shortage"] is False
        assert result["has_quality_issue"] is False

    @pytest.mark.asyncio
    async def test_record_item_detects_shortage(self):
        """ordered_qty > received_qty 时自动检测 shortage"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving()

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=receiving)
            return result

        session = AsyncMock()
        session.execute = fake_execute
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.record_item(
                receiving_id=str(RECEIVING_ID),
                ingredient_id=str(ING_ID),
                ingredient_name="猪肉",
                unit="kg",
                received_qty=8.0,
                quality_status="pass",
                ordered_qty=10.0,  # 订单 10 但只收到 8
            )

        assert result["has_shortage"] is True

    @pytest.mark.asyncio
    async def test_record_item_detects_quality_issue_on_reject(self):
        """quality_status=reject 时自动标记 has_quality_issue"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving()

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=receiving)
            return result

        session = AsyncMock()
        session.execute = fake_execute
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.record_item(
                receiving_id=str(RECEIVING_ID),
                ingredient_id=str(ING_ID),
                ingredient_name="猪肉",
                unit="kg",
                received_qty=10.0,
                quality_status="reject",
            )

        assert result["has_quality_issue"] is True


class TestCompleteReceiving:

    def _make_session_with_items(
        self, receiving, items, inv_item=None
    ):
        """构建用于 complete_receiving 的 session mock"""
        added_objects = []

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock()
            result.scalars.return_value.all = MagicMock(return_value=[])

            stmt_str = str(stmt)
            if "purchase_receivings" in stmt_str:
                result.scalar_one_or_none = MagicMock(return_value=receiving)
            elif "purchase_receiving_items" in stmt_str:
                result.scalars.return_value.all = MagicMock(return_value=items)
            elif "inventory_items" in stmt_str and inv_item:
                result.scalar_one_or_none = MagicMock(return_value=inv_item)
            return result

        session = AsyncMock()
        session.execute = fake_execute
        session.add = lambda obj: added_objects.append(obj)
        session.commit = AsyncMock()
        session._added = added_objects
        return session

    @pytest.mark.asyncio
    async def test_complete_pass_item_enters_inventory(self):
        """pass 条目完成后入库"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving()
        item = _make_item(quality_status=QualityStatus.PASS)
        inv = _make_inv(qty=20.0)

        session = self._make_session_with_items(receiving, [item], inv_item=inv)

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.complete_receiving(
                receiving_id=str(RECEIVING_ID),
                receiver_id=str(RECEIVER_ID),
            )

        assert result["items_received"] == 1
        assert result["items_rejected"] == 0
        assert inv.current_quantity == 30.0  # 20 + 10
        assert receiving.status == ReceivingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_complete_reject_item_not_entered(self):
        """reject 条目不入库，创建 quality 争议"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving()
        item = _make_item(quality_status=QualityStatus.REJECT)
        inv = _make_inv(qty=20.0)

        session = self._make_session_with_items(receiving, [item], inv_item=inv)

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.complete_receiving(
                receiving_id=str(RECEIVING_ID),
                receiver_id=str(RECEIVER_ID),
            )

        assert result["items_rejected"] == 1
        assert result["disputes_created"] == 1
        # reject 不入库，库存不变
        assert inv.current_quantity == 20.0

    @pytest.mark.asyncio
    async def test_complete_shortage_creates_dispute(self):
        """has_shortage=True 自动创建 shortage 争议"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving()
        item = _make_item(
            quality_status=QualityStatus.PASS,
            received_qty=8.0,
            ordered_qty=10.0,
            has_shortage=True,
        )
        inv = _make_inv(qty=20.0)

        session = self._make_session_with_items(receiving, [item], inv_item=inv)

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.complete_receiving(
                receiving_id=str(RECEIVING_ID),
                receiver_id=str(RECEIVER_ID),
            )

        assert result["disputes_created"] == 1

    @pytest.mark.asyncio
    async def test_complete_fails_already_completed(self):
        """状态不是 in_progress 时应拒绝（防止重复 complete）"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving(status=ReceivingStatus.COMPLETED)

        session = self._make_session_with_items(receiving, [])

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="无法重复完成"):
                await svc.complete_receiving(
                    receiving_id=str(RECEIVING_ID),
                    receiver_id=str(RECEIVER_ID),
                )

    @pytest.mark.asyncio
    async def test_complete_fails_no_items(self):
        """没有录入任何条目应拒绝"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving(status=ReceivingStatus.IN_PROGRESS)

        session = self._make_session_with_items(receiving, items=[])

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="没有录入任何条目"):
                await svc.complete_receiving(
                    receiving_id=str(RECEIVING_ID),
                    receiver_id=str(RECEIVER_ID),
                )

    @pytest.mark.asyncio
    async def test_complete_conditional_creates_quality_dispute(self):
        """has_quality_issue=True + conditional 自动创建 quality 争议"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving()
        item = _make_item(
            quality_status=QualityStatus.CONDITIONAL,
            has_quality_issue=True,
        )
        inv = _make_inv(qty=20.0)

        session = self._make_session_with_items(receiving, [item], inv_item=inv)

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.complete_receiving(
                receiving_id=str(RECEIVING_ID),
                receiver_id=str(RECEIVER_ID),
            )

        # conditional 条目入库但创建争议
        assert result["items_received"] == 1
        assert result["disputes_created"] == 1


class TestFileDispute:

    @pytest.mark.asyncio
    async def test_file_dispute_success(self):
        """手动提交争议"""
        svc = ReceivingInspectionService()
        receiving = _make_receiving(status=ReceivingStatus.COMPLETED)
        item = _make_item()

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            stmt_str = str(stmt)
            if "purchase_receivings" in stmt_str:
                result.scalar_one_or_none = MagicMock(return_value=receiving)
            elif "purchase_receiving_items" in stmt_str:
                result.scalar_one_or_none = MagicMock(return_value=item)
            else:
                result.scalar_one_or_none = MagicMock(return_value=None)
            return result

        session = AsyncMock()
        session.execute = fake_execute
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        with patch("src.services.receiving_inspection_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.file_dispute(
                receiving_id=str(RECEIVING_ID),
                item_id=str(ITEM_ID),
                dispute_type="price",
                claimed_amount_fen=5000,
                notes="发票价格与协议价不符",
            )

        assert result["dispute_type"] == "price"
        assert result["resolution"] == DisputeResolution.PENDING.value


class TestAutoDetectIssues:

    def test_no_issues(self):
        """ordered == received，质检通过，无问题"""
        svc = ReceivingInspectionService()
        shortage, quality = svc._auto_detect_issues_inline(
            ordered_qty=10.0, received_qty=10.0, quality_status="pass"
        )
        assert shortage is False
        assert quality is False

    def test_detects_shortage(self):
        """received < ordered 时检测 shortage"""
        svc = ReceivingInspectionService()
        shortage, quality = svc._auto_detect_issues_inline(
            ordered_qty=10.0, received_qty=8.0, quality_status="pass"
        )
        assert shortage is True
        assert quality is False

    def test_detects_quality_issue_on_reject(self):
        """quality_status=reject 检测 quality_issue"""
        svc = ReceivingInspectionService()
        shortage, quality = svc._auto_detect_issues_inline(
            ordered_qty=None, received_qty=10.0, quality_status="reject"
        )
        assert shortage is False
        assert quality is True

    def test_detects_quality_issue_on_rejected_qty(self):
        """rejected_qty > 0 也检测 quality_issue"""
        svc = ReceivingInspectionService()
        shortage, quality = svc._auto_detect_issues_inline(
            ordered_qty=None, received_qty=10.0, quality_status="pass", rejected_qty=2.0
        )
        assert quality is True
