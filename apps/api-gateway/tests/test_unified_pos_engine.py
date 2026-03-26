"""
统一 POS 收银引擎测试

覆盖：
  - 多场景开单（堂食/外卖/自提/外摆/宴会/套餐/配送）
  - 海鲜称重下单（按重量/时价/按只）
  - 套餐下单
  - 加菜/退菜
  - 会员折扣
  - 平台券核销 + 叠加规则
  - 混合支付结账
  - 厨打分单（按工位路由）
  - 金额精度（分/元转换）
"""

import os
import sys
import types
import importlib.util
import pytest

# 动态加载（绕过 services/__init__.py 导入问题）
src = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, src)
services_pkg = types.ModuleType("services")
services_pkg.__path__ = [os.path.join(src, "services")]
if "services" not in sys.modules:
    sys.modules["services"] = services_pkg

def _load(name):
    path = os.path.join(src, "services", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"services.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"services.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod

_pos_mod = _load("unified_pos_engine")

UnifiedPOSEngine = _pos_mod.UnifiedPOSEngine
OrderItemSpec = _pos_mod.OrderItemSpec
PricingMode = _pos_mod.PricingMode
ConsumptionScene = _pos_mod.ConsumptionScene
DeviceType = _pos_mod.DeviceType
PaymentMethod = _pos_mod.PaymentMethod
PaymentEntry = _pos_mod.PaymentEntry
CouponApplication = _pos_mod.CouponApplication
KitchenStation = _pos_mod.KitchenStation
OrderPhase = _pos_mod.OrderPhase


# ── 工具 ─────────────────────────────────────────────────────────────────────

def make_engine() -> UnifiedPOSEngine:
    return UnifiedPOSEngine(store_id="S001", brand_id="B001")


def make_fixed_item(name="小炒黄牛肉", price_fen=5800, qty=1) -> OrderItemSpec:
    return OrderItemSpec(
        dish_id=f"D_{name}",
        dish_name=name,
        pricing_mode=PricingMode.FIXED,
        quantity=qty,
        unit_price_fen=price_fen,
    )


def make_seafood_weight_item(
    name="东星斑", price_per_jin_fen=28800, weight_g=850
) -> OrderItemSpec:
    return OrderItemSpec(
        dish_id=f"D_{name}",
        dish_name=name,
        pricing_mode=PricingMode.BY_WEIGHT,
        quantity=1,
        unit_price_fen=price_per_jin_fen,
        weight_g=weight_g,
        weight_unit="g",
        cooking_method="清蒸",
        kitchen_station=KitchenStation.SEAFOOD,
    )


def make_market_price_item(
    name="波士顿龙虾", market_price_fen=38800
) -> OrderItemSpec:
    return OrderItemSpec(
        dish_id=f"D_{name}",
        dish_name=name,
        pricing_mode=PricingMode.MARKET_PRICE,
        quantity=1,
        market_price_fen=market_price_fen,
        cooking_method="蒜蓉",
        kitchen_station=KitchenStation.SEAFOOD,
    )


def make_package_item(name="家庭套餐A", price_fen=28800) -> OrderItemSpec:
    return OrderItemSpec(
        dish_id=f"D_{name}",
        dish_name=name,
        pricing_mode=PricingMode.PACKAGE,
        quantity=1,
        unit_price_fen=price_fen,
        package_items=[
            {"name": "剁椒鱼头", "qty": 1},
            {"name": "小炒黄牛肉", "qty": 1},
            {"name": "凉拌木耳", "qty": 2},
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 多场景开单
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateOrder:
    """多场景开单测试"""

    @pytest.mark.asyncio
    async def test_dine_in_order(self):
        """堂食场景"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01",
            party_size=4,
            items=[make_fixed_item(), make_fixed_item("辣椒炒肉", 3800)],
            scene=ConsumptionScene.DINE_IN,
        )
        assert order["scene"] == "dine_in"
        assert order["table_code"] == "A01"
        assert order["party_size"] == 4
        assert order["item_count"] == 2
        assert order["subtotal_fen"] == 5800 + 3800
        assert order["total_fen"] == 9600
        assert order["order_number"].startswith("DI")

    @pytest.mark.asyncio
    async def test_takeaway_order(self):
        """外卖场景"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="外卖",
            party_size=1,
            items=[make_fixed_item()],
            scene=ConsumptionScene.TAKEAWAY,
        )
        assert order["scene"] == "takeaway"
        assert order["order_number"].startswith("TA")

    @pytest.mark.asyncio
    async def test_self_pickup_order(self):
        """自提场景"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="自提",
            party_size=1,
            items=[make_fixed_item()],
            scene=ConsumptionScene.SELF_PICKUP,
        )
        assert order["scene"] == "self_pickup"
        assert order["order_number"].startswith("SP")

    @pytest.mark.asyncio
    async def test_outdoor_order(self):
        """外摆场景"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="露台01",
            party_size=2,
            items=[make_fixed_item()],
            scene=ConsumptionScene.OUTDOOR,
        )
        assert order["scene"] == "outdoor"
        assert order["order_number"].startswith("OD")

    @pytest.mark.asyncio
    async def test_banquet_order(self):
        """宴会场景"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="VIP1",
            party_size=20,
            items=[make_fixed_item(), make_package_item()],
            scene=ConsumptionScene.BANQUET,
        )
        assert order["scene"] == "banquet"
        assert order["order_number"].startswith("BQ")
        assert order["party_size"] == 20

    @pytest.mark.asyncio
    async def test_delivery_order(self):
        """配送场景"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="配送",
            party_size=1,
            items=[make_fixed_item()],
            scene=ConsumptionScene.DELIVERY,
        )
        assert order["scene"] == "delivery"
        assert order["order_number"].startswith("DL")

    @pytest.mark.asyncio
    async def test_multi_device_order(self):
        """不同设备开单"""
        engine = make_engine()
        for dt in [DeviceType.MINI_PROGRAM, DeviceType.MOBILE, DeviceType.TABLET,
                    DeviceType.TV, DeviceType.TOUCH_SCREEN, DeviceType.POS_TERMINAL]:
            order = await engine.create_order(
                table_code="A01",
                party_size=2,
                items=[make_fixed_item()],
                device_type=dt,
            )
            assert order["device_type"] == dt.value


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 海鲜称重下单
# ═══════════════════════════════════════════════════════════════════════════════


class TestSeafoodOrder:
    """海鲜复杂下单测试"""

    def test_weight_based_pricing(self):
        """按重量计价（分/斤 × 实际重量克 / 500克）"""
        item = make_seafood_weight_item(
            name="东星斑",
            price_per_jin_fen=28800,  # ¥288/斤
            weight_g=850,              # 850克 = 1.7斤
        )
        subtotal = item.calculate_subtotal_fen()
        # 28800 × (850/500) = 28800 × 1.7 = 48960
        assert subtotal == 48960

    def test_market_price_item(self):
        """时价菜品"""
        item = make_market_price_item(
            name="波士顿龙虾",
            market_price_fen=38800,
        )
        subtotal = item.calculate_subtotal_fen()
        assert subtotal == 38800

    def test_by_count_pricing(self):
        """按只计价"""
        item = OrderItemSpec(
            dish_id="D_帝王蟹",
            dish_name="帝王蟹",
            pricing_mode=PricingMode.BY_COUNT,
            quantity=2,
            unit_price_fen=58800,  # ¥588/只
        )
        assert item.calculate_subtotal_fen() == 117600

    def test_gift_item_zero_price(self):
        """赠品不计价"""
        item = OrderItemSpec(
            dish_id="D_gift",
            dish_name="赠品水果拼盘",
            pricing_mode=PricingMode.FIXED,
            quantity=1,
            unit_price_fen=3800,
            is_gift=True,
        )
        assert item.calculate_subtotal_fen() == 0

    def test_seafood_cooking_method(self):
        """海鲜做法记录"""
        item = make_seafood_weight_item()
        item.cooking_method = "白灼"
        d = item.to_dict()
        assert d["cooking_method"] == "白灼"
        assert d["weight_g"] == 850
        assert d["pricing_mode"] == "by_weight"

    @pytest.mark.asyncio
    async def test_mixed_seafood_order(self):
        """混合海鲜订单"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="B03",
            party_size=6,
            items=[
                make_seafood_weight_item("东星斑", 28800, 850),
                make_market_price_item("波士顿龙虾", 38800),
                make_fixed_item("蒜蓉粉丝蒸扇贝", 4800, qty=3),
                make_fixed_item("凉拌海蜇", 2800),
            ],
        )
        # 48960 + 38800 + 14400 + 2800 = 104960
        assert order["subtotal_fen"] == 104960
        assert order["item_count"] == 4


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 套餐下单
# ═══════════════════════════════════════════════════════════════════════════════


class TestPackageOrder:
    """套餐下单测试"""

    def test_package_pricing(self):
        """套餐按整体价格计算"""
        item = make_package_item("家庭套餐A", 28800)
        assert item.calculate_subtotal_fen() == 28800

    def test_package_items_preserved(self):
        """套餐子菜品信息保留"""
        item = make_package_item()
        d = item.to_dict()
        assert len(d["package_items"]) == 3
        assert d["pricing_mode"] == "package"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 加菜/退菜
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrderModification:
    """加菜/退菜测试"""

    @pytest.mark.asyncio
    async def test_add_items(self):
        """加菜后金额正确更新"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 3000)],
        )
        oid = order["order_id"]
        assert order["subtotal_fen"] == 3000

        updated = await engine.add_items(oid, [make_fixed_item("菜2", 5000)])
        assert updated["subtotal_fen"] == 8000
        assert updated["item_count"] == 2

    @pytest.mark.asyncio
    async def test_void_item(self):
        """退菜后金额正确更新"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 3000), make_fixed_item("菜2", 5000)],
        )
        oid = order["order_id"]
        item_id = order["items"][0]["item_id"]

        updated = await engine.void_item(oid, item_id, "不想吃了", "W001")
        assert updated["subtotal_fen"] == 5000
        assert updated["item_count"] == 1

    @pytest.mark.asyncio
    async def test_void_nonexistent_item(self):
        """退不存在的菜品应报错"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item()],
        )
        with pytest.raises(ValueError, match="菜品不存在"):
            await engine.void_item(order["order_id"], "fake_id", "test", "W001")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 优惠券
# ═══════════════════════════════════════════════════════════════════════════════


class TestCoupon:
    """优惠券测试"""

    @pytest.mark.asyncio
    async def test_apply_coupon(self):
        """应用优惠券后金额正确"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 10000)],
        )
        coupon = CouponApplication(
            coupon_code="MT001",
            platform="meituan",
            coupon_value_fen=2000,
            min_order_fen=5000,
        )
        updated = await engine.apply_coupon(order["order_id"], coupon)
        assert updated["coupon_discount_fen"] == 2000
        assert updated["total_fen"] == 8000

    @pytest.mark.asyncio
    async def test_coupon_min_order_check(self):
        """优惠券最低消费检查"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 3000)],
        )
        coupon = CouponApplication(
            coupon_code="MT001",
            platform="meituan",
            coupon_value_fen=2000,
            min_order_fen=5000,
        )
        with pytest.raises(ValueError, match="未达到最低消费"):
            await engine.apply_coupon(order["order_id"], coupon)

    @pytest.mark.asyncio
    async def test_same_platform_no_stack(self):
        """同平台券不可叠加"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 20000)],
        )
        oid = order["order_id"]

        await engine.apply_coupon(oid, CouponApplication("MT001", "meituan", 2000))
        with pytest.raises(ValueError, match="同平台券不可叠加"):
            await engine.apply_coupon(oid, CouponApplication("MT002", "meituan", 3000))

    @pytest.mark.asyncio
    async def test_cross_platform_stack(self):
        """不同平台券可叠加"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 20000)],
        )
        oid = order["order_id"]

        await engine.apply_coupon(oid, CouponApplication("MT001", "meituan", 2000))
        updated = await engine.apply_coupon(oid, CouponApplication("DY001", "douyin", 1500))
        assert updated["coupon_discount_fen"] == 3500
        assert updated["total_fen"] == 16500


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 结账
# ═══════════════════════════════════════════════════════════════════════════════


class TestSettle:
    """结账测试"""

    @pytest.mark.asyncio
    async def test_single_payment(self):
        """单一支付方式"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 10000)],
        )
        result = await engine.settle(
            order["order_id"],
            [PaymentEntry(PaymentMethod.WECHAT, 10000)],
        )
        assert result["total_fen"] == 10000
        assert result["paid_fen"] == 10000
        assert result["change_fen"] == 0

    @pytest.mark.asyncio
    async def test_mixed_payment(self):
        """混合支付（微信+会员余额+积分）"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 10000)],
        )
        result = await engine.settle(
            order["order_id"],
            [
                PaymentEntry(PaymentMethod.WECHAT, 5000),
                PaymentEntry(PaymentMethod.MEMBER_BALANCE, 3000),
                PaymentEntry(PaymentMethod.MEMBER_POINTS, 2000),
            ],
        )
        assert result["paid_fen"] == 10000
        assert result["change_fen"] == 0

    @pytest.mark.asyncio
    async def test_cash_with_change(self):
        """现金找零"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 8800)],
        )
        result = await engine.settle(
            order["order_id"],
            [PaymentEntry(PaymentMethod.CASH, 10000)],
        )
        assert result["change_fen"] == 1200

    @pytest.mark.asyncio
    async def test_insufficient_payment(self):
        """支付不足应报错"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("菜1", 10000)],
        )
        with pytest.raises(ValueError, match="支付不足"):
            await engine.settle(
                order["order_id"],
                [PaymentEntry(PaymentMethod.WECHAT, 5000)],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 厨打分单
# ═══════════════════════════════════════════════════════════════════════════════


class TestKitchenDispatch:
    """厨打分单测试"""

    @pytest.mark.asyncio
    async def test_dispatch_by_station(self):
        """按工位自动拆分厨打票"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01",
            party_size=4,
            items=[
                OrderItemSpec("D1", "小炒黄牛肉", PricingMode.FIXED, 1, 5800,
                              kitchen_station=KitchenStation.HOT_WOK),
                OrderItemSpec("D2", "剁椒鱼头", PricingMode.FIXED, 1, 8800,
                              kitchen_station=KitchenStation.STEAMER),
                OrderItemSpec("D3", "凉拌木耳", PricingMode.FIXED, 1, 1800,
                              kitchen_station=KitchenStation.COLD_DISH),
                OrderItemSpec("D4", "辣椒炒肉", PricingMode.FIXED, 1, 3800,
                              kitchen_station=KitchenStation.HOT_WOK),
            ],
        )
        tickets = await engine.dispatch_to_kitchen(order["order_id"])
        assert len(tickets) == 3  # hot_wok, steamer, cold_dish
        stations = {t["station"] for t in tickets}
        assert stations == {"hot_wok", "steamer", "cold_dish"}

        # 炒锅工位应该有2道菜
        hot_wok_ticket = [t for t in tickets if t["station"] == "hot_wok"][0]
        assert hot_wok_ticket["item_count"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 金额精度
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmountPrecision:
    """金额精度测试"""

    def test_fen_to_yuan_conversion(self):
        """分转元精度"""
        item = make_fixed_item("test", 9999)
        d = item.to_dict()
        assert d["unit_price_yuan"] == "99.99"
        assert d["subtotal_yuan"] == "99.99"

    def test_weight_calculation_precision(self):
        """称重计算精度"""
        # 388元/斤 × 1.23斤 = 477.24元 = 47724分
        item = OrderItemSpec(
            dish_id="test",
            dish_name="test",
            pricing_mode=PricingMode.BY_WEIGHT,
            quantity=1,
            unit_price_fen=38800,
            weight_g=615,  # 615g = 1.23斤
        )
        subtotal = item.calculate_subtotal_fen()
        assert subtotal == 47724  # 38800 × (615/500) = 38800 × 1.23 = 47724

    @pytest.mark.asyncio
    async def test_order_yuan_fields(self):
        """订单返回 yuan 字段"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item("test", 12345)],
        )
        assert order["subtotal_yuan"] == "123.45"
        assert order["total_yuan"] == "123.45"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. 查询
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuery:
    """查询测试"""

    @pytest.mark.asyncio
    async def test_get_order(self):
        """获取订单"""
        engine = make_engine()
        order = await engine.create_order(
            table_code="A01", party_size=2,
            items=[make_fixed_item()],
        )
        fetched = engine.get_order(order["order_id"])
        assert fetched is not None
        assert fetched["order_id"] == order["order_id"]

    @pytest.mark.asyncio
    async def test_get_active_orders(self):
        """获取活跃订单"""
        engine = make_engine()
        await engine.create_order("A01", 2, [make_fixed_item()])
        await engine.create_order("A02", 4, [make_fixed_item()])
        actives = engine.get_active_orders()
        assert len(actives) == 2

    @pytest.mark.asyncio
    async def test_completed_order_not_active(self):
        """已完成订单不在活跃列表"""
        engine = make_engine()
        order = await engine.create_order("A01", 2, [make_fixed_item("菜", 5000)])
        await engine.settle(
            order["order_id"],
            [PaymentEntry(PaymentMethod.CASH, 5000)],
        )
        actives = engine.get_active_orders()
        assert len(actives) == 0
