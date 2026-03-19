"""发券服务 — P2 核心：微生活券透传 + 服务券自建"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.service_voucher import ServiceVoucher, ServiceVoucherTemplate
from ..models.coupon_distribution import CouponDistribution

logger = structlog.get_logger(__name__)


class CouponDistributionService:
    """发券 + 核销服务"""

    async def distribute_weishenghuo_coupon(
        self, db: AsyncSession, *, consumer_id: UUID, store_id: str,
        brand_id: str, coupon_id: str, coupon_name: str,
        coupon_value_fen: int, distributed_by: UUID, phone: str,
    ) -> Dict[str, Any]:
        """透传微生活券（调用 member_service.coupon_use 完成券码核销）"""
        from ..services.member_service import member_service
        # 使用 coupon_id 作为券码，phone 作为收银员标识，0 表示纯券发放
        await member_service.coupon_use(
            code=coupon_id,
            store_id=store_id,
            cashier=phone,
            amount=0,
        )

        dist = CouponDistribution(
            store_id=store_id, brand_id=brand_id, consumer_id=consumer_id,
            coupon_source="weishenghuo", coupon_id=coupon_id,
            coupon_name=coupon_name, coupon_value_fen=coupon_value_fen,
            distributed_by=distributed_by, distributed_at=datetime.now(timezone.utc),
        )
        db.add(dist)
        await db.flush()
        logger.info("微生活券已发放", coupon_id=coupon_id, consumer_id=str(consumer_id))
        return {"success": True, "distribution_id": str(dist.id)}

    async def distribute_service_voucher(
        self, db: AsyncSession, *, template_id: UUID, consumer_id: UUID,
        store_id: str, brand_id: str, distributed_by: UUID,
    ) -> Dict[str, Any]:
        """创建并发放服务券"""
        stmt = select(ServiceVoucherTemplate).where(
            ServiceVoucherTemplate.id == template_id,
            ServiceVoucherTemplate.is_active.is_(True),
        )
        result = await db.execute(stmt)
        template = result.scalar_one_or_none()
        if not template:
            return {"success": False, "error": "券模板不存在或已停用"}

        now = datetime.now(timezone.utc)
        voucher = ServiceVoucher(
            template_id=template.id, consumer_id=consumer_id,
            store_id=store_id, brand_id=brand_id, status="sent",
            issued_by=distributed_by,
            expires_at=now + timedelta(days=template.valid_days),
        )
        db.add(voucher)
        await db.flush()

        dist = CouponDistribution(
            store_id=store_id, brand_id=brand_id, consumer_id=consumer_id,
            coupon_source="service_voucher", coupon_id=str(voucher.id),
            coupon_name=template.name, coupon_value_fen=0,
            distributed_by=distributed_by, distributed_at=now,
        )
        db.add(dist)
        await db.flush()
        logger.info("服务券已发放", voucher_id=str(voucher.id))
        return {"success": True, "distribution_id": str(dist.id), "voucher_id": str(voucher.id)}

    async def confirm_service_voucher(
        self, db: AsyncSession, *, voucher_id: UUID, confirmed_by: UUID,
    ) -> Dict[str, Any]:
        """确认核销服务券（状态机：sent → used）"""
        voucher = await db.get(ServiceVoucher, voucher_id)
        if not voucher:
            return {"success": False, "error": "服务券不存在"}
        if voucher.status != "sent":
            return {"success": False, "error": f"当前状态({voucher.status})不可核销"}

        voucher.status = "used"
        voucher.used_at = datetime.now(timezone.utc)
        voucher.confirmed_by = confirmed_by
        await db.flush()
        logger.info("服务券已核销", voucher_id=str(voucher_id))
        return {"success": True}


coupon_distribution_service = CouponDistributionService()
