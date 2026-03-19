import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestCouponDistributionService:
    @pytest.mark.asyncio
    async def test_distribute_service_voucher(self):
        """发放服务券：创建 voucher + distribution 记录"""
        from src.services.coupon_distribution_service import coupon_distribution_service

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_template = MagicMock()
        mock_template.id = uuid.uuid4()
        mock_template.name = "赠送小菜券"
        mock_template.valid_days = 7
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await coupon_distribution_service.distribute_service_voucher(
            db=mock_db,
            template_id=mock_template.id,
            consumer_id=uuid.uuid4(),
            store_id="STORE001",
            brand_id="BRAND001",
            distributed_by=uuid.uuid4(),
        )
        assert result["success"] is True
        assert mock_db.add.call_count == 2  # voucher + distribution

    @pytest.mark.asyncio
    async def test_confirm_service_voucher(self):
        """确认核销服务券"""
        from src.services.coupon_distribution_service import coupon_distribution_service

        voucher_id = uuid.uuid4()
        mock_voucher = MagicMock()
        mock_voucher.id = voucher_id
        mock_voucher.status = "sent"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_voucher)
        mock_db.commit = AsyncMock()

        result = await coupon_distribution_service.confirm_service_voucher(
            db=mock_db,
            voucher_id=voucher_id,
            confirmed_by=uuid.uuid4(),
        )
        assert result["success"] is True
        assert mock_voucher.status == "used"
