"""
tests/test_inter_store_transfer_service.py

InterStoreTransferService 单元测试 — Phase 2b 门店间调拨

覆盖（12个测试）：
  - 创建调拨申请（正常流程）
  - 创建调拨申请（from == to 应拒绝）
  - 创建调拨申请（items 为空应拒绝）
  - 创建调拨申请（库存不足应拒绝）
  - 审批通过（正常）
  - 审批（非 pending 状态应拒绝）
  - 确认发货（正常 + 扣减库存）
  - 确认发货（非 approved 状态应拒绝）
  - 确认收货（正常 + 库存变动原子性）
  - 确认收货（差异量自动创建损耗记录）
  - 确认收货（部分收货状态 partial）
  - 获取待处理列表（inbound / outbound）
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-xx")

from src.models.inter_store_transfer import (
    InterStoreTransferRequest,
    InterStoreTransferItem,
    TransferStatus,
)
from src.models.inventory import InventoryItem, InventoryTransaction
from src.services.inter_store_transfer_service import InterStoreTransferService


# ── 辅助工厂 ──────────────────────────────────────────────────────────────────

STORE_A = uuid.uuid4()
STORE_B = uuid.uuid4()
BRAND_ID = uuid.uuid4()
TRANSFER_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
ING_ID = uuid.uuid4()


def _make_transfer(
    status: TransferStatus = TransferStatus.PENDING,
    from_store_id=STORE_A,
    to_store_id=STORE_B,
) -> MagicMock:
    t = MagicMock(spec=InterStoreTransferRequest)
    t.id = TRANSFER_ID
    t.transfer_no = "IST-20260331-0001"
    t.from_store_id = from_store_id
    t.to_store_id = to_store_id
    t.brand_id = BRAND_ID
    t.status = status
    t.requested_by = USER_ID
    t.approved_by = None
    t.approved_at = None
    t.dispatched_at = None
    t.received_at = None
    t.notes = None
    t.created_at = datetime.utcnow()
    return t


def _make_inv_item(name: str = "猪肉", qty: float = 50.0) -> MagicMock:
    inv = MagicMock(spec=InventoryItem)
    inv.id = "INV_001"
    inv.store_id = str(STORE_A)
    inv.name = name
    inv.current_quantity = qty
    inv.unit_cost = 2000
    return inv


def _make_transfer_item(
    ingredient_name: str = "猪肉",
    requested_qty: float = 10.0,
    dispatched_qty: float = 10.0,
) -> MagicMock:
    item = MagicMock(spec=InterStoreTransferItem)
    item.id = uuid.uuid4()
    item.transfer_id = TRANSFER_ID
    item.ingredient_id = ING_ID
    item.ingredient_name = ingredient_name
    item.unit = "kg"
    item.requested_qty = requested_qty
    item.dispatched_qty = dispatched_qty
    item.received_qty = None
    item.qty_variance = None
    item.variance_reason = None
    item.unit_cost_fen = 2000
    return item


def _make_session(
    transfer: MagicMock | None = None,
    inv_item: MagicMock | None = None,
    transfer_items: list | None = None,
    last_transfer_no: str | None = None,
) -> AsyncMock:
    """构造最小可用的 AsyncSession mock。"""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def fake_execute(stmt, *args, **kwargs):
        result = AsyncMock()
        result_mock = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=result_mock)
        result.scalars = MagicMock()
        result.scalars.return_value.all = MagicMock(return_value=[])
        result.scalar_one = MagicMock(return_value=0)

        # 根据语句类型返回不同 mock
        stmt_str = str(stmt)

        if transfer is not None and "inter_store_transfer_requests" in stmt_str:
            # 可能是查单条 transfer 或查 transfer_no
            if last_transfer_no is not None and "transfer_no" in stmt_str:
                result.scalar_one_or_none = MagicMock(return_value=last_transfer_no)
            else:
                result.scalar_one_or_none = MagicMock(return_value=transfer)

        if inv_item is not None and "inventory_items" in stmt_str:
            result.scalar_one_or_none = MagicMock(return_value=inv_item)

        if transfer_items is not None and "inter_store_transfer_items" in stmt_str:
            result.scalars.return_value.all = MagicMock(return_value=transfer_items)

        return result

    session.execute = fake_execute
    return session


# ── 测试 ──────────────────────────────────────────────────────────────────────

class TestCreateTransferRequest:

    @pytest.mark.asyncio
    async def test_create_success(self):
        """正常创建调拨申请"""
        svc = InterStoreTransferService()
        inv_item = _make_inv_item(qty=50.0)

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = _make_session(inv_item=inv_item)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # 覆盖 _generate_transfer_no
            svc._generate_transfer_no = AsyncMock(return_value="IST-20260331-0001")

            result = await svc.create_transfer_request(
                from_store_id=str(STORE_A),
                to_store_id=str(STORE_B),
                brand_id=str(BRAND_ID),
                items=[
                    {
                        "ingredient_id": str(ING_ID),
                        "ingredient_name": "猪肉",
                        "unit": "kg",
                        "requested_qty": 10.0,
                    }
                ],
                requester_id=str(USER_ID),
            )

        assert result["transfer_no"] == "IST-20260331-0001"
        assert result["items_count"] == 1

    @pytest.mark.asyncio
    async def test_create_fails_same_store(self):
        """from == to 应拒绝"""
        svc = InterStoreTransferService()

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="不能相同"):
                await svc.create_transfer_request(
                    from_store_id=str(STORE_A),
                    to_store_id=str(STORE_A),
                    brand_id=str(BRAND_ID),
                    items=[{"ingredient_id": str(ING_ID), "ingredient_name": "猪肉",
                            "unit": "kg", "requested_qty": 10.0}],
                    requester_id=str(USER_ID),
                )

    @pytest.mark.asyncio
    async def test_create_fails_empty_items(self):
        """items 为空应拒绝"""
        svc = InterStoreTransferService()

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="不能为空"):
                await svc.create_transfer_request(
                    from_store_id=str(STORE_A),
                    to_store_id=str(STORE_B),
                    brand_id=str(BRAND_ID),
                    items=[],
                    requester_id=str(USER_ID),
                )

    @pytest.mark.asyncio
    async def test_create_fails_insufficient_inventory(self):
        """库存不足应拒绝"""
        svc = InterStoreTransferService()
        inv_item = _make_inv_item(qty=5.0)  # 只有 5kg，但要求 10kg

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = _make_session(inv_item=inv_item)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="库存不足"):
                await svc.create_transfer_request(
                    from_store_id=str(STORE_A),
                    to_store_id=str(STORE_B),
                    brand_id=str(BRAND_ID),
                    items=[{"ingredient_id": str(ING_ID), "ingredient_name": "猪肉",
                            "unit": "kg", "requested_qty": 10.0}],
                    requester_id=str(USER_ID),
                )


class TestApproveTransfer:

    @pytest.mark.asyncio
    async def test_approve_success(self):
        """审批通过正常流程"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.PENDING)

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = _make_session(transfer=transfer)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.approve_transfer(
                transfer_id=str(TRANSFER_ID),
                approver_id=str(USER_ID),
            )

        assert transfer.status == TransferStatus.APPROVED
        assert transfer.approved_by is not None

    @pytest.mark.asyncio
    async def test_approve_fails_wrong_status(self):
        """非 pending 状态应拒绝"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.APPROVED)

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = _make_session(transfer=transfer)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="只有 pending 状态可审批"):
                await svc.approve_transfer(
                    transfer_id=str(TRANSFER_ID),
                    approver_id=str(USER_ID),
                )


class TestDispatchTransfer:

    @pytest.mark.asyncio
    async def test_dispatch_success_deducts_inventory(self):
        """确认发货扣减 from_store 库存"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.APPROVED)
        inv_item = _make_inv_item(qty=50.0)
        t_item = _make_transfer_item(requested_qty=10.0)

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = _make_session(
                transfer=transfer, inv_item=inv_item, transfer_items=[t_item]
            )
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.dispatch_transfer(
                transfer_id=str(TRANSFER_ID),
                actual_items=[{"ingredient_name": "猪肉", "dispatched_qty": 10.0}],
            )

        assert transfer.status == TransferStatus.DISPATCHED
        # 库存应被扣减
        assert inv_item.current_quantity == 40.0

    @pytest.mark.asyncio
    async def test_dispatch_fails_wrong_status(self):
        """非 approved 状态应拒绝发货"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.PENDING)

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = _make_session(transfer=transfer)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="只有 approved 状态可发货"):
                await svc.dispatch_transfer(
                    transfer_id=str(TRANSFER_ID),
                    actual_items=[{"ingredient_name": "猪肉", "dispatched_qty": 10.0}],
                )


class TestReceiveTransfer:

    def _make_to_inv(self, name: str = "猪肉", qty: float = 20.0) -> MagicMock:
        inv = MagicMock(spec=InventoryItem)
        inv.id = "INV_002"
        inv.store_id = str(STORE_B)
        inv.name = name
        inv.current_quantity = qty
        return inv

    @pytest.mark.asyncio
    async def test_receive_success_updates_inventory(self):
        """收货后 to_store 库存增加，from_store 无损耗"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.DISPATCHED)
        t_item = _make_transfer_item(dispatched_qty=10.0)
        to_inv = self._make_to_inv(qty=20.0)

        call_count = [0]

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock()
            result.scalars.return_value.all = MagicMock(return_value=[])

            stmt_str = str(stmt)
            if "inter_store_transfer_requests" in stmt_str:
                result.scalar_one_or_none = MagicMock(return_value=transfer)
            elif "inter_store_transfer_items" in stmt_str:
                result.scalars.return_value.all = MagicMock(return_value=[t_item])
            elif "inventory_items" in stmt_str:
                # 第一次调用返回 to_inv，之后返回 None
                call_count[0] += 1
                if call_count[0] <= 1:
                    result.scalar_one_or_none = MagicMock(return_value=to_inv)

            return result

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.execute = fake_execute

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.receive_transfer(
                transfer_id=str(TRANSFER_ID),
                received_items=[{"ingredient_name": "猪肉", "received_qty": 10.0}],
            )

        assert transfer.status == TransferStatus.RECEIVED
        assert to_inv.current_quantity == 30.0  # 20 + 10

    @pytest.mark.asyncio
    async def test_receive_creates_waste_record_on_variance(self):
        """收货量 < 发货量时，差异量在 from_store 创建损耗流水"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.DISPATCHED)
        t_item = _make_transfer_item(dispatched_qty=10.0)
        from_inv = _make_inv_item(qty=0.0)
        to_inv = self._make_to_inv(qty=20.0)
        added_txs = []

        call_count = [0]

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock()
            result.scalars.return_value.all = MagicMock(return_value=[])

            stmt_str = str(stmt)
            if "inter_store_transfer_requests" in stmt_str:
                result.scalar_one_or_none = MagicMock(return_value=transfer)
            elif "inter_store_transfer_items" in stmt_str:
                result.scalars.return_value.all = MagicMock(return_value=[t_item])
            elif "inventory_items" in stmt_str:
                call_count[0] += 1
                if call_count[0] == 1:
                    result.scalar_one_or_none = MagicMock(return_value=to_inv)
                else:
                    result.scalar_one_or_none = MagicMock(return_value=from_inv)
            return result

        def fake_add(obj):
            if isinstance(obj, InventoryTransaction):
                added_txs.append(obj)

        session = AsyncMock()
        session.add = fake_add
        session.commit = AsyncMock()
        session.execute = fake_execute

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.receive_transfer(
                transfer_id=str(TRANSFER_ID),
                received_items=[
                    {
                        "ingredient_name": "猪肉",
                        "received_qty": 8.0,  # 少于 dispatched 10.0
                        "variance_reason": "运输损耗",
                    }
                ],
            )

        assert result["has_partial"] is True
        assert transfer.status == TransferStatus.PARTIAL
        # 应有损耗流水（waste 类型）
        waste_txs = [
            tx for tx in added_txs
            if hasattr(tx, "transaction_type")
            and tx.transaction_type == "waste"
        ]
        assert len(waste_txs) >= 1

    @pytest.mark.asyncio
    async def test_receive_fails_wrong_status(self):
        """非 dispatched 状态应拒绝收货"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.APPROVED)

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            session = _make_session(transfer=transfer)
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="只有 dispatched 状态可收货"):
                await svc.receive_transfer(
                    transfer_id=str(TRANSFER_ID),
                    received_items=[{"ingredient_name": "猪肉", "received_qty": 10.0}],
                )


class TestGetPendingTransfers:

    @pytest.mark.asyncio
    async def test_get_pending_inbound(self):
        """inbound = 我是调入方，待收货的单"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.DISPATCHED)

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalars = MagicMock()
            result.scalars.return_value.all = MagicMock(return_value=[transfer])
            return result

        session = AsyncMock()
        session.execute = fake_execute

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.get_pending_transfers(
                store_id=str(STORE_B), direction="inbound"
            )

        assert len(result) == 1
        assert result[0]["transfer_no"] == "IST-20260331-0001"

    @pytest.mark.asyncio
    async def test_get_pending_outbound(self):
        """outbound = 我是调出方，待发货的单"""
        svc = InterStoreTransferService()
        transfer = _make_transfer(status=TransferStatus.APPROVED)

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalars = MagicMock()
            result.scalars.return_value.all = MagicMock(return_value=[transfer])
            return result

        session = AsyncMock()
        session.execute = fake_execute

        with patch("src.services.inter_store_transfer_service.get_db_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.get_pending_transfers(
                store_id=str(STORE_A), direction="outbound"
            )

        assert len(result) == 1


class TestGenerateTransferNo:

    @pytest.mark.asyncio
    async def test_generate_first_of_day(self):
        """今天第一单序号为 0001"""
        svc = InterStoreTransferService()

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            return result

        session = AsyncMock()
        session.execute = fake_execute

        no = await svc._generate_transfer_no(session)
        assert no.startswith("IST-")
        assert no.endswith("-0001")

    @pytest.mark.asyncio
    async def test_generate_increments_sequence(self):
        """有历史记录时序号递增"""
        svc = InterStoreTransferService()
        from datetime import date
        today = date.today().strftime("%Y%m%d")

        async def fake_execute(stmt, *args, **kwargs):
            result = AsyncMock()
            result.scalar_one_or_none = MagicMock(return_value=f"IST-{today}-0005")
            return result

        session = AsyncMock()
        session.execute = fake_execute

        no = await svc._generate_transfer_no(session)
        assert no.endswith("-0006")
