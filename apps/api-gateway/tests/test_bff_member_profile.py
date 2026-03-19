import uuid
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, patch


class TestBffMemberProfile:
    @pytest.mark.asyncio
    @patch("src.api.bff_member_profile.validate_store_brand", new_callable=AsyncMock)
    @patch("src.api.bff_member_profile._cache_get", new_callable=AsyncMock, return_value=None)
    @patch("src.api.bff_member_profile._cache_set", new_callable=AsyncMock)
    @patch("src.api.bff_member_profile.member_profile_aggregator")
    @patch("src.api.bff_member_profile.get_db")
    async def test_endpoint_returns_profile(
        self, mock_get_db, mock_aggregator, mock_cache_set, mock_cache_get, mock_validate
    ):
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
        mock_user = SimpleNamespace(
            brand_id="BRAND001", store_id="STORE001", role="store_manager"
        )

        result = await get_member_profile(
            store_id="STORE001",
            phone="13800001234",
            current_user=mock_user,
            db=mock_db,
        )
        assert result["consumer_id"] == str(consumer_id)
        assert result["identity"]["name"] == "刘女士"
        mock_validate.assert_called_once_with("STORE001", mock_user)
