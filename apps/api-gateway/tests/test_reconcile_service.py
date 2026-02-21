"""
对账服务单元测试
"""
import pytest
import uuid
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal

from src.services.reconcile_service import ReconcileService
from src.models.reconciliation import ReconciliationRecord, ReconciliationStatus
from src.models.store import Store
from src.models.order import Order, OrderStatus


@pytest.fixture
async def reconcile_service(test_db):
    """创建对账服务实例"""
    return ReconcileService(test_db)


@pytest.fixture
async def test_store(test_db):
    """创建测试门店"""
    store = Store(
        id=uuid.uuid4(),
        name="测试门店",
        address="测试地址",
        phone="13800138000",
        is_active=True,
    )
    test_db.add(store)
    await test_db.commit()
    await test_db.refresh(store)
    return store


@pytest.fixture
async def test_orders(test_db, test_store):
    """创建测试订单"""
    orders = []
    today = date.today()

    for i in range(3):
        order = Order(
            id=uuid.uuid4(),
            store_id=test_store.id,
            order_number=f"ORD{i:04d}",
            total_amount=Decimal("100.00"),
            status=OrderStatus.COMPLETED,
            created_at=datetime.combine(today, datetime.min.time()),
        )
        orders.append(order)
        test_db.add(order)

    await test_db.commit()
    return orders


class TestReconcileService:
    """对账服务测试类"""

    @pytest.mark.asyncio
    async def test_perform_reconciliation_match(self, reconcile_service, test_store, test_orders):
        """测试对账匹配"""
        reconcile_date = date.today()
        pos_amount = Decimal("300.00")  # 与订单总额一致

        with patch('src.services.reconcile_service.neural_system') as mock_neural:
            mock_neural.emit = AsyncMock()

            record = await reconcile_service.perform_reconciliation(
                store_id=test_store.id,
                reconcile_date=reconcile_date,
                pos_amount=pos_amount
            )

            assert record is not None
            assert record.status == ReconciliationStatus.MATCHED
            assert record.pos_amount == pos_amount
            assert record.system_amount == Decimal("300.00")
            assert record.difference == Decimal("0.00")

            # 验证不应发送异常事件
            mock_neural.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_perform_reconciliation_mismatch(self, reconcile_service, test_store, test_orders):
        """测试对账不匹配"""
        reconcile_date = date.today()
        pos_amount = Decimal("350.00")  # 与订单总额不一致

        with patch('src.services.reconcile_service.neural_system') as mock_neural:
            mock_neural.emit = AsyncMock()

            record = await reconcile_service.perform_reconciliation(
                store_id=test_store.id,
                reconcile_date=reconcile_date,
                pos_amount=pos_amount
            )

            assert record.status == ReconciliationStatus.MISMATCHED
            assert record.difference == Decimal("50.00")
            assert abs(record.difference_percentage) > 0

            # 验证应发送异常事件
            mock_neural.emit.assert_called_once()
            call_args = mock_neural.emit.call_args
            assert call_args[0][0] == "reconcile.anomaly"

    @pytest.mark.asyncio
    async def test_reconciliation_threshold(self, reconcile_service, test_store, test_orders):
        """测试对账阈值"""
        reconcile_date = date.today()
        # 差异在阈值内 (2%)
        pos_amount = Decimal("305.00")  # 差异 5/300 = 1.67%

        with patch('src.services.reconcile_service.neural_system') as mock_neural:
            mock_neural.emit = AsyncMock()

            record = await reconcile_service.perform_reconciliation(
                store_id=test_store.id,
                reconcile_date=reconcile_date,
                pos_amount=pos_amount,
                threshold_percentage=2.0
            )

            # 差异在阈值内，应该匹配
            assert record.status == ReconciliationStatus.MATCHED
            mock_neural.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconciliation_exceed_threshold(self, reconcile_service, test_store, test_orders):
        """测试超过对账阈值"""
        reconcile_date = date.today()
        # 差异超过阈值 (2%)
        pos_amount = Decimal("320.00")  # 差异 20/300 = 6.67%

        with patch('src.services.reconcile_service.neural_system') as mock_neural:
            mock_neural.emit = AsyncMock()

            record = await reconcile_service.perform_reconciliation(
                store_id=test_store.id,
                reconcile_date=reconcile_date,
                pos_amount=pos_amount,
                threshold_percentage=2.0
            )

            # 差异超过阈值，应该不匹配
            assert record.status == ReconciliationStatus.MISMATCHED
            mock_neural.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_reconciliation_record(self, reconcile_service, test_store):
        """测试获取对账记录"""
        reconcile_date = date.today()
        pos_amount = Decimal("100.00")

        # 创建记录
        created_record = await reconcile_service.perform_reconciliation(
            store_id=test_store.id,
            reconcile_date=reconcile_date,
            pos_amount=pos_amount
        )

        # 获取记录
        fetched_record = await reconcile_service.get_reconciliation_record(
            created_record.id
        )

        assert fetched_record is not None
        assert fetched_record.id == created_record.id

    @pytest.mark.asyncio
    async def test_list_reconciliation_records(self, reconcile_service, test_store):
        """测试列出对账记录"""
        # 创建多条记录
        for i in range(3):
            reconcile_date = date.today() - timedelta(days=i)
            await reconcile_service.perform_reconciliation(
                store_id=test_store.id,
                reconcile_date=reconcile_date,
                pos_amount=Decimal("100.00")
            )

        # 获取记录列表
        records = await reconcile_service.list_reconciliation_records(
            store_id=test_store.id,
            limit=10
        )

        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_list_records_by_status(self, reconcile_service, test_store):
        """测试按状态列出对账记录"""
        # 创建匹配记录
        await reconcile_service.perform_reconciliation(
            store_id=test_store.id,
            reconcile_date=date.today(),
            pos_amount=Decimal("0.00")
        )

        # 创建不匹配记录
        await reconcile_service.perform_reconciliation(
            store_id=test_store.id,
            reconcile_date=date.today() - timedelta(days=1),
            pos_amount=Decimal("1000.00")
        )

        # 获取不匹配记录
        mismatched_records = await reconcile_service.list_reconciliation_records(
            store_id=test_store.id,
            status=ReconciliationStatus.MISMATCHED
        )

        assert len(mismatched_records) > 0
        assert all(r.status == ReconciliationStatus.MISMATCHED for r in mismatched_records)

    @pytest.mark.asyncio
    async def test_calculate_system_amount(self, reconcile_service, test_store, test_orders):
        """测试计算系统金额"""
        reconcile_date = date.today()

        system_amount = await reconcile_service._calculate_system_amount(
            store_id=test_store.id,
            reconcile_date=reconcile_date
        )

        assert system_amount == Decimal("300.00")  # 3个订单，每个100

    @pytest.mark.asyncio
    async def test_reconciliation_with_no_orders(self, reconcile_service, test_store):
        """测试无订单时对账"""
        reconcile_date = date.today() + timedelta(days=1)
        pos_amount = Decimal("100.00")

        record = await reconcile_service.perform_reconciliation(
            store_id=test_store.id,
            reconcile_date=reconcile_date,
            pos_amount=pos_amount
        )

        assert record.system_amount == Decimal("0.00")
        assert record.status == ReconciliationStatus.MISMATCHED
