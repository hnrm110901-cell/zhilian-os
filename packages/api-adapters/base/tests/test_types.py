"""行业公共字典类型测试"""
import pytest
import sys
import os

# 确保 packages/api-adapters 在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from base.src.types.enums import (
    ReservationStatus,
    OrderStatus,
    TableType,
    TableStatus,
    MealPeriod,
    PaymentMethod,
    ChannelSource,
    Gender,
    CustomerLevel,
    DishCategory,
    ReservationType,
)
from base.src.types.reservation import UnifiedReservation, ReservationStats
from base.src.types.customer import UnifiedCustomer
from base.src.types.table import UnifiedTable
from base.src.types.order import UnifiedOrder, UnifiedOrderItem
from base.src.types.bill import UnifiedBill
from base.src.types.dish import UnifiedDish, UnifiedSetMeal
from base.src.types.inventory import UnifiedIngredient, UnifiedInventoryRecord
from base.src.types.supplier import UnifiedSupplier, UnifiedPurchaseOrder


class TestEnums:
    """全局枚举测试"""

    def test_reservation_status_covers_all_systems(self):
        assert ReservationStatus.PENDING.value == "pending"
        assert ReservationStatus.CONFIRMED.value == "confirmed"
        assert ReservationStatus.ARRIVED.value == "arrived"
        assert ReservationStatus.SEATED.value == "seated"
        assert ReservationStatus.COMPLETED.value == "completed"
        assert ReservationStatus.CANCELLED.value == "cancelled"
        assert ReservationStatus.NO_SHOW.value == "no_show"
        assert ReservationStatus.TABLE_CHANGE.value == "table_change"

    def test_table_type_covers_kebide_types(self):
        assert TableType.STANDARD_ROOM.value == "standard_room"
        assert TableType.DELUXE_ROOM.value == "deluxe_room"
        assert TableType.CONNECTED_ROOM.value == "connected_room"
        assert TableType.HALL_TABLE.value == "hall_table"
        assert TableType.BOOTH.value == "booth"
        assert TableType.BANQUET_HALL.value == "banquet_hall"
        assert TableType.MULTI_FUNCTION.value == "multi_function"
        assert TableType.SMALL_HALL.value == "small_hall"

    def test_meal_period_values(self):
        assert MealPeriod.BREAKFAST.value == "breakfast"
        assert MealPeriod.LUNCH.value == "lunch"
        assert MealPeriod.DINNER.value == "dinner"
        assert MealPeriod.LATE_NIGHT.value == "late_night"
        assert MealPeriod.TEA.value == "tea"

    def test_channel_source_values(self):
        assert ChannelSource.PHONE.value == "phone"
        assert ChannelSource.WALK_IN.value == "walk_in"
        assert ChannelSource.MEITUAN.value == "meituan"
        assert ChannelSource.DIANPING.value == "dianping"
        assert ChannelSource.DOUYIN.value == "douyin"
        assert ChannelSource.WECHAT.value == "wechat"
        assert ChannelSource.MINI_PROGRAM.value == "mini_program"
        assert ChannelSource.YIDING.value == "yiding"
        assert ChannelSource.KEBIDE.value == "kebide"

    def test_enum_is_str(self):
        assert isinstance(ReservationStatus.PENDING, str)
        assert isinstance(TableType.HALL_TABLE, str)
        assert isinstance(MealPeriod.LUNCH, str)

    def test_reservation_type_covers_banquet_types(self):
        assert ReservationType.REGULAR.value == "regular"
        assert ReservationType.WEDDING.value == "wedding"
        assert ReservationType.BIRTHDAY.value == "birthday"
        assert ReservationType.CORPORATE.value == "corporate"


class TestUnifiedReservation:
    def test_minimal_reservation(self):
        r: UnifiedReservation = {
            "external_id": "ORDER001",
            "source": "yiding",
            "customer_name": "张三",
            "customer_phone": "13800138000",
            "reservation_date": "2026-03-18",
            "party_size": 4,
            "status": ReservationStatus.PENDING,
        }
        assert r["source"] == "yiding"
        assert r["status"] == ReservationStatus.PENDING

    def test_full_reservation(self):
        r: UnifiedReservation = {
            "external_id": "V2_ORDER_001",
            "source": "yiding",
            "store_id": "S001",
            "store_name": "尝在一起",
            "customer_name": "赵六",
            "customer_phone": "13900139000",
            "gender": "male",
            "reservation_date": "2026-03-15",
            "reservation_time": "11:30",
            "party_size": 6,
            "table_area_name": "大厅",
            "table_name": "A03",
            "meal_period": "lunch",
            "status": ReservationStatus.COMPLETED,
            "raw_status": 3,
            "reservation_type": "regular",
            "deposit_amount": 0,
            "pay_amount": 1200.0,
            "source_channel": "dianping",
            "remark": "靠窗位置",
        }
        assert r["pay_amount"] == 1200.0
        assert r["source_channel"] == "dianping"

    def test_kebide_style_reservation(self):
        """客必得风格的一单多桌预订"""
        r: UnifiedReservation = {
            "external_id": "ff2b414b-28c8-41c1-b8bc-0576cfab6158",
            "source": "kebide",
            "customer_name": "韦旭",
            "customer_phone": "18500088475",
            "gender": "male",
            "company": "易达小鸟科技有限公司",
            "reservation_date": "2026-03-20",
            "party_size": 33,
            "reservation_type": "wedding",
            "status": ReservationStatus.CONFIRMED,
            "table_ids": ["desk-a", "desk-b"],
            "has_deposit": True,
            "deposit_amount": 100.0,
            "meal_standard": "300元/人",
            "sales_name": "李俊利",
            "operator_name": "刘强",
            "has_pre_order": True,
            "pre_order_dishes": [
                {"dish_id": "12300088", "name": "香菇老肉", "quantity": 1, "price": 120},
            ],
        }
        assert len(r["table_ids"]) == 2
        assert r["reservation_type"] == "wedding"
        assert r["meal_standard"] == "300元/人"


class TestUnifiedCustomer:
    def test_minimal_customer(self):
        c: UnifiedCustomer = {
            "phone": "13800138000",
            "name": "张三",
            "source": "yiding",
        }
        assert c["phone"] == "13800138000"

    def test_full_customer(self):
        c: UnifiedCustomer = {
            "phone": "13777575146",
            "name": "邱琪潇",
            "source": "yiding",
            "gender": "male",
            "company": "某公司",
            "total_amount": 4732.0,
            "total_visits": 298,
            "per_capita": 3.87,
            "last_visit_date": "2026-01-12",
            "customer_level": "sleeping",
            "sub_level": "vip",
            "preference": "海鲜",
            "allergy": "辣椒",
            "tags": ["常客"],
        }
        assert c["customer_level"] == "sleeping"
        assert c["allergy"] == "辣椒"


class TestUnifiedTable:
    def test_kebide_table(self):
        t: UnifiedTable = {
            "external_id": "75fa889a-0741-45cc-9bb7-99460939ded1",
            "erp_desk_id": "02_227",
            "source": "kebide",
            "name": "227双桃泉",
            "area_name": "七店二楼宴会",
            "table_type": "standard_room",
            "capacity": 20,
            "status": "available",
        }
        assert t["capacity"] == 20
        assert t["table_type"] == "standard_room"


class TestUnifiedOrder:
    def test_pos_order(self):
        o: UnifiedOrder = {
            "external_id": "BILL001",
            "source": "pinzhi",
            "store_id": "S001",
            "order_type": "dine_in",
            "order_status": "completed",
            "total": 580.0,
            "paid": 520.0,
            "discount": 60.0,
            "items": [
                {"dish_id": "D001", "dish_name": "红烧肉", "quantity": 1, "unit_price": 68.0, "subtotal": 68.0},
            ],
        }
        assert o["paid"] == 520.0
        assert len(o["items"]) == 1


class TestUnifiedBill:
    def test_kebide_bill(self):
        b: UnifiedBill = {
            "source": "kebide",
            "total_amount": 3800.0,
            "paid_amount": 3500.0,
            "discount_amount": 300.0,
            "deposit_amount": 100.0,
            "party_size": 10,
            "table_count": 1,
        }
        assert b["total_amount"] == 3800.0


class TestUnifiedDish:
    def test_dish_with_methods(self):
        d: UnifiedDish = {
            "name": "香菇老肉",
            "price": 120.0,
            "category_name": "热菜",
            "methods": [
                {"method_id": "1", "method_name": "微辣", "price": 0, "quantity": 1},
            ],
        }
        assert d["price"] == 120.0
        assert len(d["methods"]) == 1

    def test_set_meal(self):
        s: UnifiedSetMeal = {
            "set_meal_id": "SM001",
            "set_meal_name": "生日宴套餐",
            "price": 888.0,
            "quantity": 1,
            "dishes": [
                {"name": "香菇老肉", "price": 120.0},
                {"name": "西安凉皮", "price": 12.0},
            ],
        }
        assert len(s["dishes"]) == 2


class TestUnifiedSupplier:
    def test_supplier(self):
        s: UnifiedSupplier = {
            "name": "永辉供应链",
            "contact_name": "李经理",
            "contact_phone": "13800138000",
            "categories": ["蔬菜", "水果"],
            "is_active": True,
        }
        assert len(s["categories"]) == 2


class TestCrossModelIntegration:
    def test_reservation_with_dishes(self):
        """预订+预点菜场景"""
        r: UnifiedReservation = {
            "external_id": "R001",
            "source": "kebide",
            "customer_name": "韦旭",
            "customer_phone": "18500088475",
            "reservation_date": "2026-03-20",
            "party_size": 33,
            "status": ReservationStatus.CONFIRMED,
            "reservation_type": ReservationType.WEDDING.value,
            "has_pre_order": True,
            "pre_order_dishes": [
                {"dish_id": "12300088", "name": "香菇老肉", "quantity": 1, "price": 120},
            ],
            "table_ids": ["desk-a", "desk-b"],
        }
        assert r["reservation_type"] == "wedding"
        assert len(r["table_ids"]) == 2
