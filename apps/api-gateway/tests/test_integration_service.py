"""
集成服务测试
Tests for Integration Service
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.services.integration_service import IntegrationService
from src.models.integration import (
    ExternalSystem,
    POSTransaction,
    IntegrationType,
    IntegrationStatus,
    SyncStatus,
)


class TestIntegrationService:
    """IntegrationService测试类"""

    @pytest.mark.asyncio
    async def test_create_system(self):
        """测试创建外部系统"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        config = {
            "api_endpoint": "https://api.example.com",
            "api_key": "test_key",
            "api_secret": "test_secret",
        }

        result = await service.create_system(
            session=mock_session,
            name="Test POS",
            type=IntegrationType.POS,
            provider="test_provider",
            config=config,
            created_by="USER001",
            store_id="STORE001",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_system(self):
        """测试获取外部系统"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_system = MagicMock(spec=ExternalSystem)
        mock_system.id = uuid.uuid4()
        mock_system.name = "Test POS"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_system
        mock_session.execute.return_value = mock_result

        result = await service.get_system(mock_session, str(mock_system.id))

        assert result == mock_system
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_systems_no_filters(self):
        """测试获取外部系统列表（无过滤）"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_system1 = MagicMock(spec=ExternalSystem)
        mock_system1.id = uuid.uuid4()
        mock_system2 = MagicMock(spec=ExternalSystem)
        mock_system2.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_system1, mock_system2]
        mock_session.execute.return_value = mock_result

        result = await service.get_systems(mock_session)

        assert len(result) == 2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_systems_with_filters(self):
        """测试获取外部系统列表（带过滤）"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.get_systems(
            mock_session,
            type=IntegrationType.POS,
            store_id="STORE001",
            status=IntegrationStatus.ACTIVE,
        )

        assert len(result) == 0
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_system(self):
        """测试更新外部系统"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_system = MagicMock(spec=ExternalSystem)
        mock_system.id = uuid.uuid4()
        mock_system.name = "Old Name"

        with patch.object(service, 'get_system', return_value=mock_system):
            result = await service.update_system(
                mock_session,
                str(mock_system.id),
                name="New Name",
                status=IntegrationStatus.ACTIVE,
            )

        assert result == mock_system
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_system_not_found(self):
        """测试更新不存在的系统"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        with patch.object(service, 'get_system', return_value=None):
            result = await service.update_system(
                mock_session,
                "nonexistent_id",
                name="New Name",
            )

        assert result is None
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_system(self):
        """测试删除外部系统"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_system = MagicMock(spec=ExternalSystem)
        mock_system.id = uuid.uuid4()

        with patch.object(service, 'get_system', return_value=mock_system):
            result = await service.delete_system(mock_session, str(mock_system.id))

        assert result is True
        mock_session.delete.assert_called_once_with(mock_system)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_system_not_found(self):
        """测试删除不存在的系统"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        with patch.object(service, 'get_system', return_value=None):
            result = await service.delete_system(mock_session, "nonexistent_id")

        assert result is False
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    @patch('src.services.integration_service.httpx.AsyncClient')
    async def test_test_connection_pos_success(self, mock_client_cls):
        """测试POS系统连接成功"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_system = MagicMock(spec=ExternalSystem)
        mock_system.id = uuid.uuid4()
        mock_system.type = IntegrationType.POS
        mock_system.api_endpoint = "https://api.example.com"
        mock_system.api_key = "test_key"

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with patch.object(service, 'get_system', return_value=mock_system):
            result = await service.test_connection(mock_session, str(mock_system.id))

        assert result["success"] is True
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_test_connection_system_not_found(self):
        """测试连接不存在的系统"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        with patch.object(service, 'get_system', return_value=None):
            result = await service.test_connection(mock_session, "nonexistent_id")

        assert result["success"] is False
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_create_pos_transaction(self):
        """测试创建POS交易记录"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        transaction_data = {
            "transaction_id": "TXN001",
            "order_number": "ORD001",
            "type": "sale",
            "subtotal": 100.0,
            "tax": 10.0,
            "total": 110.0,
            "payment_method": "cash",
            "items": [{"name": "Item1", "price": 100.0}],
        }

        result = await service.create_pos_transaction(
            mock_session,
            "SYSTEM001",
            "STORE001",
            transaction_data,
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pos_transactions_no_filters(self):
        """测试获取POS交易记录（无过滤）"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_txn1 = MagicMock(spec=POSTransaction)
        mock_txn2 = MagicMock(spec=POSTransaction)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_txn1, mock_txn2]
        mock_session.execute.return_value = mock_result

        result = await service.get_pos_transactions(mock_session)

        assert len(result) == 2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pos_transactions_with_filters(self):
        """测试获取POS交易记录（带过滤）"""
        mock_session = AsyncMock(spec=AsyncSession)
        service = IntegrationService()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.get_pos_transactions(
            mock_session,
            store_id="STORE001",
            sync_status=SyncStatus.PENDING,
            limit=50,
        )

        assert len(result) == 0
        mock_session.execute.assert_called_once()

