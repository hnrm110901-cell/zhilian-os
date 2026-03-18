import uuid
import pytest
from unittest.mock import AsyncMock, patch


class TestBffMemberProfile:
    @pytest.mark.asyncio
    @patch("src.api.bff_member_profile.member_profile_aggregator")
    @patch("src.api.bff_member_profile.get_db")
    async def test_endpoint_returns_profile(self, mock_get_db, mock_aggregator):
        """GET /api/v1/bff/member-profile/{store_id}/{phone} 返回画像"""
        from src.api.bff_member_profile import get_member_profile

        consumer_id = uuid.uuid4()
        mock_aggregator.aggregate = AsyncMock(return_value={
            "consumer_id": str(consumer_id),
            "identity": {"name": "刘女士", "phone": "138****1234", "tags": [], "lifecycle_stage": "活跃期"},
            "preferences": None,
            "assets": None,
            "milestones": None,
            "ai_script": None,
        })

        mock_db = AsyncMock()

        result = await get_member_profile(
            store_id="STORE001",
            phone="13800001234",
            db=mock_db,
        )
        assert result["consumer_id"] == str(consumer_id)
        assert result["identity"]["name"] == "刘女士"
