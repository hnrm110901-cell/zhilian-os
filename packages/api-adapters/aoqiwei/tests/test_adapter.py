"""
奥琦韦适配器单元测试
"""
import pytest
from datetime import datetime
from decimal import Decimal
from src.adapter import AoqiweiAdapter


@pytest.fixture
def adapter():
    """创建适配器实例"""
    config = {
        "base_url": "https://api.aoqiwei.com",
        "api_key": "test_api_key",
        "timeout": 30,
        "retry_times": 3,
    }
    return AoqiweiAdapter(config)


@pytest.fixture
def adapter_no_key():
    """创建没有API密钥的适配器"""
    config = {"base_url": "https://api.aoqiwei.com"}
    return config


class TestAoqiweiAdapter:
    """奥琦韦适配器测试类"""

    def test_init_success(self, adapter):
        """测试适配器初始化成功"""
        assert adapter.base_url == "https://api.aoqiwei.com"
        assert adapter.api_key == "test_api_key"
        assert adapter.timeout == 30
        assert adapter.retry_times == 3

    def test_init_no_api_key(self, adapter_no_key):
        """测试没有API密钥时初始化失败"""
        with pytest.raises(ValueError, match="API密钥不能为空"):
            AoqiweiAdapter(adapter_no_key)

    @pytest.mark.asyncio
    async def test_authenticate(self, adapter):
        """测试认证方法"""
        headers = await adapter.authenticate()
        assert headers["Content-Type"] == "application/json"
        assert headers["X-API-Key"] == "test_api_key"

    @pytest.mark.asyncio
    async def test_query_member_by_card_no(self, adapter):
        """测试通过卡号查询会员"""
        result = await adapter.query_member(card_no="M20240001")
        assert result["cardNo"] == "M20240001"
        assert "mobile" in result
        assert "name" in result

    @pytest.mark.asyncio
    async def test_query_member_by_mobile(self, adapter):
        """测试通过手机号查询会员"""
        result = await adapter.query_member(mobile="13800138000")
        assert result["mobile"] == "13800138000"

    @pytest.mark.asyncio
    async def test_query_member_no_params(self, adapter):
        """测试查询会员时没有提供参数"""
        with pytest.raises(ValueError, match="至少需要提供一个查询条件"):
            await adapter.query_member()

    @pytest.mark.asyncio
    async def test_add_member(self, adapter):
        """测试新增会员"""
        result = await adapter.add_member(
            mobile="13900139000", name="李四", sex=1, birthday="1995-05-05"
        )
        assert result["mobile"] == "13900139000"
        assert result["name"] == "李四"
        assert "cardNo" in result
        assert result["message"] == "会员创建成功"

    @pytest.mark.asyncio
    async def test_update_member(self, adapter):
        """测试修改会员信息"""
        result = await adapter.update_member(
            card_no="M20240001", update_data={"name": "张三三", "sex": 2}
        )
        assert result["message"] == "会员信息更新成功"

    @pytest.mark.asyncio
    async def test_trade_preview(self, adapter):
        """测试交易预览"""
        result = await adapter.trade_preview(
            card_no="M20240001",
            store_id="STORE001",
            cashier="收银员001",
            amount=10000,
        )
        assert result["totalAmount"] == 10000
        assert "discountAmount" in result
        assert "payAmount" in result
        assert result["payAmount"] < result["totalAmount"]

    @pytest.mark.asyncio
    async def test_trade_submit(self, adapter):
        """测试交易提交"""
        result = await adapter.trade_submit(
            card_no="M20240001",
            store_id="STORE001",
            cashier="收银员001",
            amount=9000,
            pay_type=3,
            trade_no="T202401010001",
        )
        assert result["status"] == "success"
        assert "tradeId" in result

    @pytest.mark.asyncio
    async def test_trade_query(self, adapter):
        """测试查询交易"""
        result = await adapter.trade_query(card_no="M20240001")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_trade_cancel(self, adapter):
        """测试交易撤销"""
        result = await adapter.trade_cancel(
            trade_id="T202401010001", reason="客户要求"
        )
        assert result["message"] == "交易撤销成功"

    @pytest.mark.asyncio
    async def test_recharge_submit(self, adapter):
        """测试储值提交"""
        result = await adapter.recharge_submit(
            card_no="M20240001",
            store_id="STORE001",
            cashier="收银员001",
            amount=100000,
            pay_type=3,
            trade_no="R202401010001",
        )
        assert "rechargeId" in result
        assert result["balance"] == 100000
        assert result["message"] == "充值成功"

    @pytest.mark.asyncio
    async def test_recharge_query(self, adapter):
        """测试查询储值"""
        result = await adapter.recharge_query(card_no="M20240001")
        assert "balance" in result
        assert "records" in result

    @pytest.mark.asyncio
    async def test_coupon_list(self, adapter):
        """测试查询优惠券列表"""
        result = await adapter.coupon_list(card_no="M20240001")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_coupon_use(self, adapter):
        """测试券码核销"""
        result = await adapter.coupon_use(
            code="COUPON001", store_id="STORE001", cashier="收银员001", amount=9000
        )
        assert "couponId" in result
        assert "couponName" in result
        assert "faceValue" in result
        assert "useRule" in result


class TestDataMapping:
    """数据映射测试"""

    @pytest.mark.asyncio
    async def test_member_data_structure(self, adapter):
        """测试会员数据结构"""
        result = await adapter.query_member(card_no="M20240001")

        # 验证必需字段
        required_fields = [
            "cardNo",
            "mobile",
            "name",
            "sex",
            "level",
            "points",
            "balance",
        ]
        for field in required_fields:
            assert field in result, f"缺少必需字段: {field}"

        # 验证数据类型
        assert isinstance(result["cardNo"], str)
        assert isinstance(result["mobile"], str)
        assert isinstance(result["name"], str)
        assert isinstance(result["sex"], int)
        assert isinstance(result["level"], int)
        assert isinstance(result["points"], int)
        assert isinstance(result["balance"], int)

    @pytest.mark.asyncio
    async def test_amount_in_fen(self, adapter):
        """测试金额单位为分"""
        # 测试交易预览
        result = await adapter.trade_preview(
            card_no="M20240001",
            store_id="STORE001",
            cashier="收银员001",
            amount=10000,  # 100元 = 10000分
        )
        assert result["totalAmount"] == 10000
        assert isinstance(result["payAmount"], int)

        # 测试储值
        result = await adapter.recharge_submit(
            card_no="M20240001",
            store_id="STORE001",
            cashier="收银员001",
            amount=50000,  # 500元 = 50000分
            pay_type=3,
            trade_no="R202401010001",
        )
        assert result["balance"] == 50000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# ARCH-001: to_order() / to_staff_action() 标准数据总线接口测试
# ---------------------------------------------------------------------------

@pytest.fixture
def supply_chain_adapter():
    """奥琦玮供应链适配器（真实实现）"""
    config = {
        "base_url": "https://openapi.acescm.cn",
        "app_key": "test_key",
        "app_secret": "test_secret",
    }
    return AoqiweiAdapter(config)


@pytest.fixture
def raw_pos_order():
    return {
        "orderId": "AQ20240101001",
        "orderNo": "AQ-2024-001",
        "orderDate": "2024-01-01 12:00:00",
        "orderStatus": "2",
        "shopCode": "SH001",
        "tableNo": "5",
        "memberId": "M001",
        "totalAmount": 18400,
        "discountAmount": 2000,
        "remark": "少辣",
        "waiterId": "W001",
        "items": [
            {"orderItemNo": "AQ20240101001_1", "goodCode": "G001", "goodName": "宫保鸡丁", "qty": 2, "price": 5800},
            {"orderItemNo": "AQ20240101001_2", "goodCode": "G002", "goodName": "麻婆豆腐", "qty": 1, "price": 4200},
        ],
    }


@pytest.fixture
def raw_pos_staff_action():
    return {
        "actionType": "discount_apply",
        "operatorId": "STAFF_001",
        "amount": 2000,
        "reason": "会员折扣",
        "approvedBy": "MGR_001",
        "actionTime": "2024-01-01 12:05:00",
    }


class TestToOrderMapsCorrectly:
    def test_order_id_mapped(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.order_id == "AQ20240101001"

    def test_order_number_mapped(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.order_number == "AQ-2024-001"

    def test_store_id_injected(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.store_id == "STORE_A1"

    def test_brand_id_injected(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.brand_id == "BRAND_A"

    def test_total_converted_from_fen(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.total == Decimal("184.00")

    def test_discount_converted_from_fen(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.discount == Decimal("20.00")

    def test_items_count(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert len(order.items) == 2

    def test_item_name(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.items[0].dish_name == "宫保鸡丁"

    def test_item_price_converted(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.items[0].unit_price == Decimal("58.00")

    def test_invalid_date_falls_back(self, supply_chain_adapter, raw_pos_order):
        raw_pos_order["orderDate"] = "bad-date"
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert isinstance(order.created_at, datetime)


class TestToStaffActionMapsCorrectly:
    def test_action_type(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.action_type == "discount_apply"

    def test_store_brand_injected(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.store_id == "STORE_A1"
        assert action.brand_id == "BRAND_A"

    def test_amount_converted(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.amount == Decimal("20.00")

    def test_approved_by(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.approved_by == "MGR_001"


class TestSignRegression:
    """MD5 签名回归测试（原有功能不受影响）"""

    def test_sign_deterministic(self, supply_chain_adapter):
        params = {"appKey": "test_key", "timestamp": "1700000000000", "shopCode": "SH001"}
        assert supply_chain_adapter._sign(params) == supply_chain_adapter._sign(params)

    def test_sign_length(self, supply_chain_adapter):
        params = {"appKey": "k", "timestamp": "1"}
        assert len(supply_chain_adapter._sign(params)) == 32

    def test_sign_excludes_empty(self, supply_chain_adapter):
        p1 = {"a": "1", "b": None, "d": "2"}
        p2 = {"a": "1", "d": "2"}
        assert supply_chain_adapter._sign(p1) == supply_chain_adapter._sign(p2)

