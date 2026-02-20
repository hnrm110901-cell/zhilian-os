"""
供应链服务测试
Tests for Supply Chain Service
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.services.supply_chain_service import SupplyChainService, get_supply_chain_service
from src.models.supply_chain import Supplier, PurchaseOrder
from src.core.exceptions import NotFoundError


class TestSupplyChainService:
    """SupplyChainService测试类"""

    def test_init(self):
        """测试服务初始化"""
        mock_db = AsyncMock(spec=AsyncSession)
        service = SupplyChainService(mock_db)
        assert service.db == mock_db

    @pytest.mark.asyncio
    async def test_get_suppliers_no_filters(self):
        """测试获取供应商列表（无过滤）"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock suppliers
        mock_supplier = MagicMock(spec=Supplier)
        mock_supplier.id = uuid.uuid4()
        mock_supplier.name = "测试供应商"
        mock_supplier.code = "SUP001"
        mock_supplier.category = "food"
        mock_supplier.contact_person = "张三"
        mock_supplier.phone = "13800138000"
        mock_supplier.email = "test@example.com"
        mock_supplier.address = "测试地址"
        mock_supplier.status = "active"
        mock_supplier.rating = 5.0
        mock_supplier.payment_terms = "net30"
        mock_supplier.delivery_time = 3
        mock_supplier.created_at = datetime.now()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_supplier]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_db.execute.side_effect = [mock_result, mock_count_result]

        service = SupplyChainService(mock_db)
        result = await service.get_suppliers()

        assert len(result["suppliers"]) == 1
        assert result["suppliers"][0]["name"] == "测试供应商"
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_get_suppliers_with_filters(self):
        """测试获取供应商列表（带过滤）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_db.execute.side_effect = [mock_result, mock_count_result]

        service = SupplyChainService(mock_db)
        result = await service.get_suppliers(status="active", category="food")

        assert result["suppliers"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_create_supplier(self):
        """测试创建供应商"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_supplier = MagicMock(spec=Supplier)
        mock_supplier.id = uuid.uuid4()
        mock_supplier.name = "新供应商"
        mock_supplier.code = "SUP002"
        mock_supplier.status = "active"

        async def mock_refresh(obj):
            obj.id = mock_supplier.id
            obj.name = mock_supplier.name
            obj.code = mock_supplier.code
            obj.status = mock_supplier.status

        mock_db.refresh = mock_refresh

        service = SupplyChainService(mock_db)
        data = {
            "name": "新供应商",
            "code": "SUP002",
            "category": "food",
            "contact_person": "李四",
            "phone": "13900139000"
        }

        result = await service.create_supplier(data)

        assert result["name"] == "新供应商"
        assert result["code"] == "SUP002"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_purchase_orders_no_filters(self):
        """测试获取采购订单列表（无过滤）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_order = MagicMock(spec=PurchaseOrder)
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "PO-001"
        mock_order.supplier_id = str(uuid.uuid4())
        mock_order.store_id = "STORE001"
        mock_order.status = "pending"
        mock_order.total_amount = 5000.0
        mock_order.items = []
        mock_order.expected_delivery = datetime.now() + timedelta(days=3)
        mock_order.created_at = datetime.now()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db.execute.return_value = mock_result

        service = SupplyChainService(mock_db)
        result = await service.get_purchase_orders()

        assert len(result["orders"]) == 1
        assert result["orders"][0]["order_number"] == "PO-001"
        assert result["orders"][0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_purchase_orders_with_filters(self):
        """测试获取采购订单列表（带过滤）"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = SupplyChainService(mock_db)
        result = await service.get_purchase_orders(
            status="completed",
            supplier_id="SUP001"
        )

        assert result["orders"] == []

    @pytest.mark.asyncio
    async def test_create_purchase_order(self):
        """测试创建采购订单"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_order = MagicMock(spec=PurchaseOrder)
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "PO-20260301120000"
        mock_order.status = "pending"

        async def mock_refresh(obj):
            obj.id = mock_order.id
            obj.order_number = mock_order.order_number
            obj.status = mock_order.status

        mock_db.refresh = mock_refresh

        service = SupplyChainService(mock_db)
        data = {
            "supplier_id": str(uuid.uuid4()),
            "store_id": "STORE001",
            "total_amount": 5000.0,
            "expected_delivery": datetime.now() + timedelta(days=3)
        }

        result = await service.create_purchase_order(data)

        assert "id" in result
        assert result["status"] == "pending"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_order_status_success(self):
        """测试更新订单状态成功"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_order = MagicMock(spec=PurchaseOrder)
        order_id = uuid.uuid4()
        mock_order.id = order_id
        mock_order.order_number = "PO-001"
        mock_order.status = "pending"
        mock_order.notes = None
        mock_order.updated_at = datetime.now()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        service = SupplyChainService(mock_db)
        result = await service.update_order_status(
            str(order_id),
            "approved",
            "订单已审批"
        )

        assert result["status"] == "approved"
        assert mock_order.status == "approved"
        assert mock_order.notes == "订单已审批"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_order_status_not_found(self):
        """测试更新不存在的订单"""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = SupplyChainService(mock_db)

        with pytest.raises(NotFoundError):
            await service.update_order_status(str(uuid.uuid4()), "approved")

    @pytest.mark.asyncio
    async def test_get_supplier_performance_no_orders(self):
        """测试获取供应商绩效（无订单）"""
        mock_db = AsyncMock(spec=AsyncSession)

        supplier_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = SupplyChainService(mock_db)
        result = await service.get_supplier_performance(supplier_id, days=30)

        assert result["total_orders"] == 0
        assert result["on_time_delivery_rate"] == 0
        assert result["total_amount"] == 0


class TestGlobalFunction:
    """测试全局函数"""

    def test_get_supply_chain_service(self):
        """测试get_supply_chain_service函数"""
        mock_db = AsyncMock(spec=AsyncSession)
        service = get_supply_chain_service(mock_db)
        assert isinstance(service, SupplyChainService)
        assert service.db == mock_db
