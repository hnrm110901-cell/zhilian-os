import uuid
import pytest
from src.models.service_voucher import ServiceVoucherTemplate, ServiceVoucher
from src.models.coupon_distribution import CouponDistribution, CouponRedemption, CouponRoiDaily


class TestServiceVoucherModels:
    def test_template_create(self):
        t = ServiceVoucherTemplate(
            brand_id="BRAND001", name="赠送小菜", voucher_type="complimentary_dish",
        )
        assert t.name == "赠送小菜"

    def test_voucher_create(self):
        v = ServiceVoucher(
            template_id=uuid.uuid4(), consumer_id=uuid.uuid4(),
            store_id="STORE001", brand_id="BRAND001",
            issued_by=uuid.uuid4(), expires_at="2026-04-01T00:00:00Z",
        )
        assert v.store_id == "STORE001"


class TestCouponDistributionModels:
    def test_distribution_create(self):
        d = CouponDistribution(
            store_id="STORE001", brand_id="BRAND001", consumer_id=uuid.uuid4(),
            coupon_source="weishenghuo", coupon_id="C001",
            coupon_name="满100减20", distributed_by=uuid.uuid4(),
        )
        assert d.coupon_source == "weishenghuo"

    def test_roi_daily_create(self):
        r = CouponRoiDaily(
            date="2026-03-18", store_id="STORE001", brand_id="BRAND001",
        )
        assert r.distributed_count in (0, None)
