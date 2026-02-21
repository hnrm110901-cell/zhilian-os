"""
Tests for InventoryService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4

from src.services.inventory_service import InventoryService
from src.models.inventory import InventoryItem, InventoryTransaction, InventoryStatus, TransactionType


@pytest.fixture
def inventory_service():
    """Create an InventoryService instance for testing"""
    return InventoryService(store_id="TEST_STORE")


@pytest.fixture
def mock_inventory_item():
    """Create a mock inventory item"""
    item = MagicMock(spec=InventoryItem)
    item.id = "INV_001"
    item.store_id = "TEST_STORE"
    item.name = "测试物料"
    item.category = "vegetables"
    item.unit = "kg"
    item.current_quantity = 50.0
    item.min_quantity = 20.0
    item.max_quantity = 100.0
    item.unit_cost = 1000  # 10元 in cents
    item.status = InventoryStatus.NORMAL
    item.supplier_name = "测试供应商"
    item.supplier_contact = "13800138000"
    item.transactions = []
    return item


@pytest.fixture
def mock_transaction():
    """Create a mock transaction"""
    trans = MagicMock(spec=InventoryTransaction)
    trans.id = uuid4()
    trans.item_id = "INV_001"
    trans.store_id = "TEST_STORE"
    trans.transaction_type = TransactionType.PURCHASE
    trans.quantity = 10.0
    trans.unit_cost = 1000
    trans.total_cost = 10000
    trans.quantity_before = 40.0
    trans.quantity_after = 50.0
    trans.transaction_time = datetime.now()
    trans.reference_id = "PO_001"
    trans.notes = "测试采购"
    trans.performed_by = "admin"
    return trans


class TestMonitorInventory:
    """Tests for monitor_inventory method"""

    @pytest.mark.asyncio
    async def test_monitor_inventory_success(self, inventory_service, mock_inventory_item):
        """Test successful inventory monitoring"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_inventory_item]
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            items = await inventory_service.monitor_inventory()

            assert len(items) == 1
            assert items[0]["item_id"] == "INV_001"
            assert items[0]["name"] == "测试物料"
            assert items[0]["current_quantity"] == 50.0

    @pytest.mark.asyncio
    async def test_monitor_inventory_with_category_filter(self, inventory_service, mock_inventory_item):
        """Test inventory monitoring with category filter"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_inventory_item]
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            items = await inventory_service.monitor_inventory(category="vegetables")

            assert len(items) == 1
            assert items[0]["category"] == "vegetables"

    @pytest.mark.asyncio
    async def test_monitor_inventory_with_status_filter(self, inventory_service, mock_inventory_item):
        """Test inventory monitoring with status filter"""
        mock_inventory_item.status = InventoryStatus.LOW
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_inventory_item]
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            items = await inventory_service.monitor_inventory(status="low")

            assert len(items) == 1
            assert items[0]["status"] == "low"

    @pytest.mark.asyncio
    async def test_monitor_inventory_empty_result(self, inventory_service):
        """Test inventory monitoring with no results"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            items = await inventory_service.monitor_inventory()

            assert len(items) == 0


class TestGetItem:
    """Tests for get_item method"""

    @pytest.mark.asyncio
    async def test_get_item_success(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test successful item retrieval"""
        mock_inventory_item.transactions = [mock_transaction]
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_inventory_item
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            item = await inventory_service.get_item("INV_001")

            assert item is not None
            assert item["item_id"] == "INV_001"
            assert "recent_transactions" in item
            assert len(item["recent_transactions"]) == 1

    @pytest.mark.asyncio
    async def test_get_item_not_found(self, inventory_service):
        """Test item not found"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            item = await inventory_service.get_item("NONEXISTENT")

            assert item is None


class TestGenerateRestockAlerts:
    """Tests for generate_restock_alerts method"""

    @pytest.mark.asyncio
    async def test_generate_restock_alerts_with_low_stock(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test generating restock alerts for low stock items"""
        mock_inventory_item.status = InventoryStatus.LOW
        mock_inventory_item.current_quantity = 15.0

        mock_session = AsyncMock()

        # Mock items query result
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_inventory_item]

        # Mock transactions query result
        mock_trans_result = MagicMock()
        mock_trans_result.scalars.return_value.all.return_value = [mock_transaction]

        # Return different results for the two queries
        mock_session.execute.side_effect = [mock_items_result, mock_trans_result]

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            alerts = await inventory_service.generate_restock_alerts()

            assert len(alerts) == 1
            assert alerts[0]["item_id"] == "INV_001"
            assert alerts[0]["alert_level"] == "warning"
            assert alerts[0]["current_stock"] == 15.0
            assert alerts[0]["recommended_quantity"] > 0

    @pytest.mark.asyncio
    async def test_generate_restock_alerts_with_critical_stock(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test generating restock alerts for critical stock items"""
        mock_inventory_item.status = InventoryStatus.CRITICAL
        mock_inventory_item.current_quantity = 2.0

        mock_session = AsyncMock()

        # Mock items query result
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_inventory_item]

        # Mock transactions query result
        mock_trans_result = MagicMock()
        mock_trans_result.scalars.return_value.all.return_value = [mock_transaction]

        mock_session.execute.side_effect = [mock_items_result, mock_trans_result]

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            alerts = await inventory_service.generate_restock_alerts()

            assert len(alerts) == 1
            assert alerts[0]["alert_level"] == "urgent"

    @pytest.mark.asyncio
    async def test_generate_restock_alerts_with_out_of_stock(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test generating restock alerts for out of stock items"""
        mock_inventory_item.status = InventoryStatus.OUT_OF_STOCK
        mock_inventory_item.current_quantity = 0.0

        mock_session = AsyncMock()

        # Mock items query result
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_inventory_item]

        # Mock transactions query result
        mock_trans_result = MagicMock()
        mock_trans_result.scalars.return_value.all.return_value = [mock_transaction]

        mock_session.execute.side_effect = [mock_items_result, mock_trans_result]

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            alerts = await inventory_service.generate_restock_alerts()

            assert len(alerts) == 1
            assert alerts[0]["alert_level"] == "critical"

    @pytest.mark.asyncio
    async def test_generate_restock_alerts_no_alerts(self, inventory_service):
        """Test generating restock alerts with no items needing restock"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            alerts = await inventory_service.generate_restock_alerts()

            assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_generate_restock_alerts_with_category_filter(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test generating restock alerts with category filter"""
        mock_inventory_item.status = InventoryStatus.LOW
        mock_inventory_item.category = "vegetables"

        mock_session = AsyncMock()

        # Mock items query result
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_inventory_item]

        # Mock transactions query result
        mock_trans_result = MagicMock()
        mock_trans_result.scalars.return_value.all.return_value = [mock_transaction]

        mock_session.execute.side_effect = [mock_items_result, mock_trans_result]

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            alerts = await inventory_service.generate_restock_alerts(category="vegetables")

            assert len(alerts) == 1
            assert alerts[0]["category"] == "vegetables"


class TestRecordTransaction:
    """Tests for record_transaction method"""

    @pytest.mark.asyncio
    async def test_record_transaction_purchase(self, inventory_service, mock_inventory_item):
        """Test recording a purchase transaction"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_inventory_item
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await inventory_service.record_transaction(
                item_id="INV_001",
                transaction_type="purchase",
                quantity=10.0,
                unit_cost=1000,
                notes="测试采购"
            )

            assert result["item_id"] == "INV_001"
            assert result["quantity"] == 10.0
            assert result["quantity_before"] == 50.0
            assert result["quantity_after"] == 60.0
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_transaction_usage(self, inventory_service, mock_inventory_item):
        """Test recording a usage transaction"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_inventory_item
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            result = await inventory_service.record_transaction(
                item_id="INV_001",
                transaction_type="usage",
                quantity=-5.0,
                notes="测试使用"
            )

            assert result["quantity"] == -5.0
            assert result["quantity_after"] == 45.0

    @pytest.mark.asyncio
    async def test_record_transaction_item_not_found(self, inventory_service):
        """Test recording transaction for non-existent item"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(ValueError, match="库存项目不存在"):
                await inventory_service.record_transaction(
                    item_id="NONEXISTENT",
                    transaction_type="purchase",
                    quantity=10.0
                )

    @pytest.mark.asyncio
    async def test_record_transaction_with_error_rollback(self, inventory_service, mock_inventory_item):
        """Test transaction rollback on error"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_inventory_item
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("Database error")

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            with pytest.raises(Exception):
                await inventory_service.record_transaction(
                    item_id="INV_001",
                    transaction_type="purchase",
                    quantity=10.0
                )

            mock_session.rollback.assert_called_once()


class TestGetInventoryStatistics:
    """Tests for get_inventory_statistics method"""

    @pytest.mark.asyncio
    async def test_get_inventory_statistics_success(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test getting inventory statistics"""
        mock_session = AsyncMock()

        # Mock items query
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_inventory_item]

        # Mock transactions query
        mock_trans_result = MagicMock()
        mock_trans_result.scalars.return_value.all.return_value = [mock_transaction]

        mock_session.execute.side_effect = [mock_items_result, mock_trans_result]

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            stats = await inventory_service.get_inventory_statistics()

            assert stats["total_items"] == 1
            assert stats["total_value"] > 0
            assert "status_breakdown" in stats
            assert "transaction_counts" in stats

    @pytest.mark.asyncio
    async def test_get_inventory_statistics_with_date_range(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test getting inventory statistics with date range"""
        mock_session = AsyncMock()

        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_inventory_item]

        mock_trans_result = MagicMock()
        mock_trans_result.scalars.return_value.all.return_value = [mock_transaction]

        mock_session.execute.side_effect = [mock_items_result, mock_trans_result]

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            start_date = (datetime.now() - timedelta(days=7)).isoformat()
            end_date = datetime.now().isoformat()

            stats = await inventory_service.get_inventory_statistics(
                start_date=start_date,
                end_date=end_date
            )

            assert "total_items" in stats
            assert "transaction_counts" in stats

    @pytest.mark.asyncio
    async def test_get_inventory_statistics_empty(self, inventory_service):
        """Test getting inventory statistics with no data"""
        mock_session = AsyncMock()

        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = []

        mock_trans_result = MagicMock()
        mock_trans_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_items_result, mock_trans_result]

        with patch("src.services.inventory_service.get_db_session") as mock_get_db:
            mock_get_db.return_value.__aenter__.return_value = mock_session

            stats = await inventory_service.get_inventory_statistics()

            assert stats["total_items"] == 0
            assert stats["total_value"] == 0


class TestGetInventoryReport:
    """Tests for get_inventory_report method"""

    @pytest.mark.asyncio
    async def test_get_inventory_report_success(self, inventory_service):
        """Test generating inventory report"""
        with patch.object(inventory_service, "monitor_inventory", return_value=[
            {"item_id": "INV_001", "status": "low", "name": "测试物料"}
        ]):
            with patch.object(inventory_service, "generate_restock_alerts", return_value=[
                {"item_id": "INV_001", "alert_level": "warning"}
            ]):
                with patch.object(inventory_service, "get_inventory_statistics", return_value={
                    "total_items": 1,
                    "total_value": 500.0,
                    "status_breakdown": {"low": 1, "normal": 0, "critical": 0, "out_of_stock": 0}
                }):
                    report = await inventory_service.get_inventory_report()

                    assert "report_generated_at" in report
                    assert report["store_id"] == "TEST_STORE"
                    assert "inventory_summary" in report
                    assert "restock_alerts" in report
                    assert len(report["low_stock_items"]) == 1


class TestHelperMethods:
    """Tests for helper methods"""

    def test_calculate_status_normal(self, inventory_service, mock_inventory_item):
        """Test status calculation for normal stock"""
        mock_inventory_item.current_quantity = 50.0
        mock_inventory_item.min_quantity = 20.0

        status = inventory_service._calculate_status(mock_inventory_item)

        assert status == InventoryStatus.NORMAL

    def test_calculate_status_low(self, inventory_service, mock_inventory_item):
        """Test status calculation for low stock"""
        mock_inventory_item.current_quantity = 15.0
        mock_inventory_item.min_quantity = 20.0

        status = inventory_service._calculate_status(mock_inventory_item)

        assert status == InventoryStatus.LOW

    def test_calculate_status_critical(self, inventory_service, mock_inventory_item):
        """Test status calculation for critical stock"""
        mock_inventory_item.current_quantity = 1.0
        mock_inventory_item.min_quantity = 20.0

        status = inventory_service._calculate_status(mock_inventory_item)

        assert status == InventoryStatus.CRITICAL

    def test_calculate_status_out_of_stock(self, inventory_service, mock_inventory_item):
        """Test status calculation for out of stock"""
        mock_inventory_item.current_quantity = 0.0
        mock_inventory_item.min_quantity = 20.0

        status = inventory_service._calculate_status(mock_inventory_item)

        assert status == InventoryStatus.OUT_OF_STOCK

    def test_calculate_restock_quantity_with_max(self, inventory_service, mock_inventory_item):
        """Test restock quantity calculation with max quantity"""
        mock_inventory_item.current_quantity = 30.0
        mock_inventory_item.max_quantity = 100.0

        quantity = inventory_service._calculate_restock_quantity(mock_inventory_item)

        assert quantity == 70.0

    def test_calculate_restock_quantity_without_max(self, inventory_service, mock_inventory_item):
        """Test restock quantity calculation without max quantity"""
        mock_inventory_item.current_quantity = 10.0
        mock_inventory_item.min_quantity = 20.0
        mock_inventory_item.max_quantity = None

        quantity = inventory_service._calculate_restock_quantity(mock_inventory_item)

        assert quantity == 30.0  # min * 2 - current

    def test_get_alert_level_critical(self, inventory_service, mock_inventory_item):
        """Test alert level for out of stock"""
        mock_inventory_item.status = InventoryStatus.OUT_OF_STOCK

        level = inventory_service._get_alert_level(mock_inventory_item)

        assert level == "critical"

    def test_get_alert_level_urgent(self, inventory_service, mock_inventory_item):
        """Test alert level for critical stock"""
        mock_inventory_item.status = InventoryStatus.CRITICAL

        level = inventory_service._get_alert_level(mock_inventory_item)

        assert level == "urgent"

    def test_get_alert_level_warning(self, inventory_service, mock_inventory_item):
        """Test alert level for low stock"""
        mock_inventory_item.status = InventoryStatus.LOW

        level = inventory_service._get_alert_level(mock_inventory_item)

        assert level == "warning"

    def test_estimate_stockout_date_from_transactions(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test stockout date estimation"""
        mock_inventory_item.current_quantity = 50.0
        mock_transaction.transaction_type = TransactionType.USAGE
        mock_transaction.quantity = -5.0
        mock_transaction.transaction_time = datetime.now() - timedelta(days=10)

        transactions = [mock_transaction] * 10  # 10 transactions of -5 each

        stockout_date = inventory_service._estimate_stockout_date_from_transactions(
            mock_inventory_item, transactions
        )

        assert stockout_date is not None

    def test_estimate_stockout_date_no_transactions(self, inventory_service, mock_inventory_item):
        """Test stockout date estimation with no transactions"""
        stockout_date = inventory_service._estimate_stockout_date_from_transactions(
            mock_inventory_item, []
        )

        assert stockout_date is None

    def test_generate_recommendations_with_alerts(self, inventory_service):
        """Test generating recommendations with alerts"""
        inventory_items = [
            {"status": "critical"},
            {"status": "out_of_stock"},
            {"status": "low"}
        ]
        restock_alerts = [{"item_id": "INV_001"}]

        recommendations = inventory_service._generate_recommendations(inventory_items, restock_alerts)

        assert len(recommendations) > 0
        assert any("补货" in rec for rec in recommendations)

    def test_generate_recommendations_no_alerts(self, inventory_service):
        """Test generating recommendations with no alerts"""
        inventory_items = [{"status": "normal"}]
        restock_alerts = []

        recommendations = inventory_service._generate_recommendations(inventory_items, restock_alerts)

        assert len(recommendations) == 0

    def test_item_to_dict_without_transactions(self, inventory_service, mock_inventory_item):
        """Test converting item to dict without transactions"""
        result = inventory_service._item_to_dict(mock_inventory_item, include_transactions=False)

        assert result["item_id"] == "INV_001"
        assert result["name"] == "测试物料"
        assert "recent_transactions" not in result

    def test_item_to_dict_with_transactions(self, inventory_service, mock_inventory_item, mock_transaction):
        """Test converting item to dict with transactions"""
        mock_inventory_item.transactions = [mock_transaction]

        result = inventory_service._item_to_dict(mock_inventory_item, include_transactions=True)

        assert "recent_transactions" in result
        assert len(result["recent_transactions"]) == 1

