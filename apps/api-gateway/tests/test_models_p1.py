import uuid
import pytest
from src.models.member_check_in import MemberCheckIn
from src.models.member_dish_preference import MemberDishPreference


class TestMemberCheckInModel:
    def test_create_instance(self):
        ci = MemberCheckIn(
            store_id="STORE001",
            brand_id="BRAND001",
            consumer_id=uuid.uuid4(),
            trigger_type="manual_search",
        )
        assert ci.trigger_type == "manual_search"
        assert ci.store_id == "STORE001"

    def test_trigger_type_values(self):
        for tt in ("manual_search", "reservation", "pos_webhook"):
            ci = MemberCheckIn(
                store_id="S1", brand_id="B1",
                consumer_id=uuid.uuid4(), trigger_type=tt,
            )
            assert ci.trigger_type == tt


class TestMemberDishPreferenceModel:
    def test_create_instance(self):
        dp = MemberDishPreference(
            consumer_id=uuid.uuid4(),
            store_id="STORE001",
            brand_id="BRAND001",
            dish_name="特色江蟹生",
            order_count=5,
        )
        assert dp.dish_name == "特色江蟹生"
        assert dp.order_count == 5
        assert dp.is_favorite in (False, None)  # SQLAlchemy applies column default at INSERT, not at __init__
