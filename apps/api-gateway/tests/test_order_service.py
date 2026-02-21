"""
Tests for OrderService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4

from src.services.order_service import OrderService
from src.models.order import Order, OrderItem, OrderStatus


@pytest.fixture
def order_service():
    """Create an OrderService instance for testing"""
    return OrderService(store_id="TEST_STORE")


@pytest.fixture
def mock_order():
    """Create a mock order"""
    order = MagicMock(spec=Order)
    order.id = "ORD_20240217_ABC123"
    order.store_id = "TEST_STORE"
    order.table_number = "A01"
    order.customer_name = "测试客户"
    order.customer_phone = "13800138000"
    order.status = OrderStatus.PENDING
    order.total_amount = 10000  # 100元 in cents
    order.discount_amount = 1000  # 10元 discount
    order.final_amount = 9000  # 90元
    order.order_time = datetime.now()
    order.confirmed_at = None
    order.completed_at = None
    order.notes = "测试订单"
    order.order_metadata = {}
    order.items = []
    return order


@pytest.fixture
def mock_order_item():
    """Create a mock order item"""
    item = MagicMock(spec=OrderItem)
    item.id = uuid4()
    item.order_id = "ORD_20240217_ABC123"
    item.item_id = "ITEM_001"
    item.item_name = "测试菜品"
    item.quantity = 2
    item.unit_price = 5000  # 50元 in cents
    item.subtotal = 10000  # 100元
    item.notes = "不要辣"
    item.customizations = {}
    return item


@pytest.fixture
def sample_items():
    """Sample order items for testing"""
    return [
        {
            "item_id": "ITEM_001",
            "item_name": "宫保鸡丁",
            "quantity": 2,
            "unit_price": 3800,
            "notes": "不要辣"
        },
        {
            "item_id": "ITEM_002",
            "item_name": "米饭",
            "quantity": 2,
            "unit_price": 200
        }
    ]


class TestCreateOrder:
    """Tests for create_order method"""

    @pytest.mark.asyncio
    async def test_create_order_success(self, order_service, sample_items):
        """Test successful order creation"""
        mock_session = AsyncMock()

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await order_service.create_order(
                table_number="A01",
                items=sample_items,
                customer_name="测试客户",
                customer_phone="13800138000",
                notes="测试订单"
            )

            assert result["table_number"] == "A01"
            assert result["customer_name"] == "测试客户"
            assert result["status"] == "pending"
            assert result["total_amount"] == 80.0  # (3800*2 + 200*2) / 100
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_order_with_discount(self, order_service, sample_items):
        """Test order creation with discount"""
        mock_session = AsyncMock()

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await order_service.create_order(
                table_number="A01",
                items=sample_items,
                discount_amount=1000
            )

            assert result["discount_amount"] == 10.0
            assert result["final_amount"] == 70.0  # 80 - 10

    @pytest.mark.asyncio
    async def test_create_order_with_error_rollback(self, order_service, sample_items):
        """Test order creation with error rollback"""
        mock_session = AsyncMock()
        mock_session.commit.side_effect = Exception("Database error")

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(Exception):
                await order_service.create_order(
                    table_number="A01",
                    items=sample_items
                )

            mock_session.rollback.assert_called_once()


class TestGetOrder:
    """Tests for get_order method"""

    @pytest.mark.asyncio
    async def test_get_order_success(self, order_service, mock_order, mock_order_item):
        """Test successful order retrieval"""
        mock_order.items = [mock_order_item]
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            order = await order_service.get_order("ORD_20240217_ABC123")

            assert order is not None
            assert order["order_id"] == "ORD_20240217_ABC123"
            assert order["table_number"] == "A01"
            assert len(order["items"]) == 1

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, order_service):
        """Test order not found"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            order = await order_service.get_order("NONEXISTENT")

            assert order is None


class TestListOrders:
    """Tests for list_orders method"""

    @pytest.mark.asyncio
    async def test_list_orders_all(self, order_service, mock_order):
        """Test listing all orders"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            orders = await order_service.list_orders()

            assert len(orders) == 1
            assert orders[0]["order_id"] == "ORD_20240217_ABC123"

    @pytest.mark.asyncio
    async def test_list_orders_with_status_filter(self, order_service, mock_order):
        """Test listing orders with status filter"""
        mock_order.status = OrderStatus.COMPLETED
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            orders = await order_service.list_orders(status="completed")

            assert len(orders) == 1
            assert orders[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_orders_with_table_filter(self, order_service, mock_order):
        """Test listing orders with table number filter"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            orders = await order_service.list_orders(table_number="A01")

            assert len(orders) == 1
            assert orders[0]["table_number"] == "A01"

    @pytest.mark.asyncio
    async def test_list_orders_with_date_range(self, order_service, mock_order):
        """Test listing orders with date range"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            start_date = (datetime.now() - timedelta(days=7)).isoformat()
            end_date = datetime.now().isoformat()

            orders = await order_service.list_orders(
                start_date=start_date,
                end_date=end_date
            )

            assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_list_orders_empty(self, order_service):
        """Test listing orders with no results"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            orders = await order_service.list_orders()

            assert len(orders) == 0


class TestUpdateOrderStatus:
    """Tests for update_order_status method"""

    @pytest.mark.asyncio
    async def test_update_order_status_to_confirmed(self, order_service, mock_order):
        """Test updating order status to confirmed"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await order_service.update_order_status(
                order_id="ORD_20240217_ABC123",
                status="confirmed"
            )

            assert result["order_id"] == "ORD_20240217_ABC123"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_order_status_to_completed(self, order_service, mock_order):
        """Test updating order status to completed"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await order_service.update_order_status(
                order_id="ORD_20240217_ABC123",
                status="completed",
                notes="订单完成"
            )

            assert result["order_id"] == "ORD_20240217_ABC123"

    @pytest.mark.asyncio
    async def test_update_order_status_not_found(self, order_service):
        """Test updating status for non-existent order"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(ValueError, match="订单不存在"):
                await order_service.update_order_status(
                    order_id="NONEXISTENT",
                    status="confirmed"
                )

    @pytest.mark.asyncio
    async def test_update_order_status_with_error_rollback(self, order_service, mock_order):
        """Test status update with error rollback"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("Database error")

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(Exception):
                await order_service.update_order_status(
                    order_id="ORD_20240217_ABC123",
                    status="confirmed"
                )

            mock_session.rollback.assert_called_once()


class TestAddItems:
    """Tests for add_items method"""

    @pytest.mark.asyncio
    async def test_add_items_success(self, order_service, mock_order):
        """Test successfully adding items to order"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        new_items = [
            {
                "item_id": "ITEM_003",
                "item_name": "可乐",
                "quantity": 1,
                "unit_price": 500
            }
        ]

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await order_service.add_items(
                order_id="ORD_20240217_ABC123",
                items=new_items
            )

            assert result["order_id"] == "ORD_20240217_ABC123"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_items_order_not_found(self, order_service):
        """Test adding items to non-existent order"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        new_items = [{"item_id": "ITEM_003", "item_name": "可乐", "quantity": 1, "unit_price": 500}]

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(ValueError, match="订单不存在"):
                await order_service.add_items(
                    order_id="NONEXISTENT",
                    items=new_items
                )

    @pytest.mark.asyncio
    async def test_add_items_with_error_rollback(self, order_service, mock_order):
        """Test adding items with error rollback"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("Database error")

        new_items = [{"item_id": "ITEM_003", "item_name": "可乐", "quantity": 1, "unit_price": 500}]

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(Exception):
                await order_service.add_items(
                    order_id="ORD_20240217_ABC123",
                    items=new_items
                )

            mock_session.rollback.assert_called_once()


class TestCancelOrder:
    """Tests for cancel_order method"""

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, order_service, mock_order):
        """Test successfully canceling an order"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await order_service.cancel_order(
                order_id="ORD_20240217_ABC123",
                reason="客户要求取消"
            )

            assert result["order_id"] == "ORD_20240217_ABC123"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_without_reason(self, order_service, mock_order):
        """Test canceling order without reason"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await order_service.cancel_order(order_id="ORD_20240217_ABC123")

            assert result["order_id"] == "ORD_20240217_ABC123"

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, order_service):
        """Test canceling non-existent order"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(ValueError, match="订单不存在"):
                await order_service.cancel_order(order_id="NONEXISTENT")

    @pytest.mark.asyncio
    async def test_cancel_order_with_error_rollback(self, order_service, mock_order):
        """Test canceling order with error rollback"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("Database error")

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(Exception):
                await order_service.cancel_order(order_id="ORD_20240217_ABC123")

            mock_session.rollback.assert_called_once()


class TestGetOrderStatistics:
    """Tests for get_order_statistics method"""

    @pytest.mark.asyncio
    async def test_get_order_statistics_success(self, order_service):
        """Test getting order statistics"""
        # Create mock orders with different statuses
        mock_order1 = MagicMock(spec=Order)
        mock_order1.status = OrderStatus.COMPLETED
        mock_order1.final_amount = 10000

        mock_order2 = MagicMock(spec=Order)
        mock_order2.status = OrderStatus.CANCELLED
        mock_order2.final_amount = 5000

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order1, mock_order2]
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            stats = await order_service.get_order_statistics()

            assert stats["total_orders"] == 2
            assert stats["completed_orders"] == 1
            assert stats["cancelled_orders"] == 1
            assert stats["total_revenue"] == 100.0  # 10000 / 100

    @pytest.mark.asyncio
    async def test_get_order_statistics_with_date_range(self, order_service, mock_order):
        """Test getting statistics with date range"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            start_date = (datetime.now() - timedelta(days=7)).isoformat()
            end_date = datetime.now().isoformat()

            stats = await order_service.get_order_statistics(
                start_date=start_date,
                end_date=end_date
            )

            assert "total_orders" in stats
            assert "status_breakdown" in stats

    @pytest.mark.asyncio
    async def test_get_order_statistics_empty(self, order_service):
        """Test getting statistics with no orders"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch("src.services.order_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            stats = await order_service.get_order_statistics()

            assert stats["total_orders"] == 0
            assert stats["completed_orders"] == 0
            assert stats["total_revenue"] == 0.0


class TestHelperMethods:
    """Tests for helper methods"""

    def test_order_to_dict_with_items(self, order_service, mock_order, mock_order_item):
        """Test converting order to dict with items"""
        mock_order.items = [mock_order_item]

        result = order_service._order_to_dict(mock_order)

        assert result["order_id"] == "ORD_20240217_ABC123"
        assert result["table_number"] == "A01"
        assert result["status"] == "pending"
        assert len(result["items"]) == 1
        assert result["items"][0]["item_name"] == "测试菜品"

    def test_order_to_dict_without_items(self, order_service, mock_order):
        """Test converting order to dict without items"""
        mock_order.items = []

        result = order_service._order_to_dict(mock_order)

        assert result["order_id"] == "ORD_20240217_ABC123"
        assert result["items"] == []

    def test_order_to_dict_with_provided_items(self, order_service, mock_order):
        """Test converting order to dict with provided items list"""
        items = [
            {"item_id": "ITEM_001", "item_name": "测试", "quantity": 1, "unit_price": 1000}
        ]

        result = order_service._order_to_dict(mock_order, items=items)

        assert result["items"] == items
