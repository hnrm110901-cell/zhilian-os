import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestPosWebhookCheckIn:
    @pytest.mark.asyncio
    @patch("src.api.pos_webhook.get_db_session")
    @patch("src.api.pos_webhook.identity_resolution_service")
    async def test_check_in_created_on_order_with_phone(self, mock_irs, mock_get_session):
        """POS订单含 customer_phone 时创建识客事件"""
        from src.api.pos_webhook import _handle_member_check_in

        consumer_id = uuid.uuid4()
        mock_irs.resolve = AsyncMock(return_value=consumer_id)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_store = MagicMock()
        mock_store.brand_id = "BRAND001"
        mock_session.get = AsyncMock(return_value=mock_store)
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _handle_member_check_in(
            store_id="STORE001",
            customer_phone="13800001234",
        )
        assert result == consumer_id
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_in_skipped_when_no_phone(self):
        """无 customer_phone 时跳过"""
        from src.api.pos_webhook import _handle_member_check_in

        result = await _handle_member_check_in(
            store_id="STORE001", customer_phone=None,
        )
        assert result is None
