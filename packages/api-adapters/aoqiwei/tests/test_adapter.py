"""
奥琦韦适配器单元测试
"""
import pytest
from datetime import datetime
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
