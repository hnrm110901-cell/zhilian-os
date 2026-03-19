import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession


class TestMemberProfileAggregator:
    """MemberProfileAggregator 聚合服务测试"""

    @pytest.mark.asyncio
    @patch("src.services.member_profile_aggregator.identity_resolution_service")
    async def test_aggregate_returns_consumer_id(self, mock_irs):
        """resolve phone → consumer_id 正确传递"""
        from src.services.member_profile_aggregator import member_profile_aggregator

        consumer_id = uuid.uuid4()
        mock_irs.resolve = AsyncMock(return_value=consumer_id)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        profile = await member_profile_aggregator.aggregate(
            db=mock_db, phone="13800001234", store_id="STORE001",
        )
        assert profile["consumer_id"] == str(consumer_id)
        mock_irs.resolve.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.member_profile_aggregator.identity_resolution_service")
    async def test_crm_failure_degrades_gracefully(self, mock_irs):
        """微生活CRM不可用时 assets=None"""
        from src.services.member_profile_aggregator import member_profile_aggregator

        mock_irs.resolve = AsyncMock(return_value=uuid.uuid4())

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            member_profile_aggregator, "_fetch_crm_assets",
            AsyncMock(side_effect=Exception("CRM down")),
        ):
            profile = await member_profile_aggregator.aggregate(
                db=mock_db, phone="13800001234", store_id="STORE001",
            )
        assert profile["assets"] is None
        assert "identity" in profile

    @pytest.mark.asyncio
    @patch("src.services.member_profile_aggregator.identity_resolution_service")
    async def test_identity_section_from_consumer(self, mock_irs):
        """identity 从 consumer_identities 表读取"""
        from src.services.member_profile_aggregator import member_profile_aggregator

        cid = uuid.uuid4()
        mock_irs.resolve = AsyncMock(return_value=cid)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_consumer = MagicMock()
        mock_consumer.display_name = "刘女士"
        mock_consumer.primary_phone = "13800001234"
        mock_consumer.tags = ["VIP"]
        mock_consumer.birth_date = None
        mock_consumer.dietary_restrictions = None
        mock_consumer.anniversary = None
        mock_consumer.last_order_at = None
        mock_consumer.total_order_count = 0

        mock_result_consumer = MagicMock()
        mock_result_consumer.scalar_one_or_none.return_value = mock_consumer

        mock_result_empty = MagicMock()
        mock_result_empty.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_result_consumer, mock_result_empty])
        mock_db.get = AsyncMock(return_value=mock_consumer)

        profile = await member_profile_aggregator.aggregate(
            db=mock_db, phone="13800001234", store_id="STORE001",
        )
        assert profile["identity"]["name"] == "刘女士"
        assert "VIP" in profile["identity"]["tags"]
