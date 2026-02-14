"""
品智适配器单元测试
"""
import pytest
from src.adapter import PinzhiAdapter
from src.signature import generate_sign, verify_sign


@pytest.fixture
def adapter():
    """创建适配器实例"""
    config = {
        "base_url": "http://192.168.1.100:8080/pzcatering-gateway",
        "token": "test_token_12345",
        "timeout": 30,
        "retry_times": 3,
    }
    return PinzhiAdapter(config)


@pytest.fixture
def adapter_no_token():
    """创建没有token的适配器配置"""
    config = {"base_url": "http://192.168.1.100:8080/pzcatering-gateway"}
    return config


@pytest.fixture
def adapter_no_url():
    """创建没有base_url的适配器配置"""
    config = {"token": "test_token"}
    return config


class TestSignature:
    """签名算法测试"""

    def test_generate_sign_basic(self):
        """测试基本签名生成"""
        token = "test_token"
        params = {"ognid": "12345", "beginDate": "2024-01-01"}
        sign = generate_sign(token, params)

        assert isinstance(sign, str)
        assert len(sign) == 32  # MD5签名长度为32

    def test_generate_sign_with_sorting(self):
        """测试参数排序"""
        token = "test_token"
        # 参数顺序不同，但签名应该相同
        params1 = {"z_param": "value1", "a_param": "value2"}
        params2 = {"a_param": "value2", "z_param": "value1"}

        sign1 = generate_sign(token, params1)
        sign2 = generate_sign(token, params2)

        assert sign1 == sign2

    def test_generate_sign_exclude_params(self):
        """测试排除特定参数"""
        token = "test_token"
        params_with_excluded = {
            "ognid": "12345",
            "sign": "old_sign",
            "pageIndex": 1,
            "pageSize": 20,
        }
        params_without_excluded = {"ognid": "12345"}

        sign1 = generate_sign(token, params_with_excluded)
        sign2 = generate_sign(token, params_without_excluded)

        # sign, pageIndex, pageSize应该被排除，所以签名相同
        assert sign1 == sign2

    def test_generate_sign_with_none_values(self):
        """测试None值参数"""
        token = "test_token"
        params = {"ognid": "12345", "beginDate": None}
        sign = generate_sign(token, params)

        # None值应该被过滤掉
        assert isinstance(sign, str)

    def test_verify_sign_success(self):
        """测试签名验证成功"""
        token = "test_token"
        params = {"ognid": "12345"}
        sign = generate_sign(token, params)

        assert verify_sign(token, params, sign) is True

    def test_verify_sign_failure(self):
        """测试签名验证失败"""
        token = "test_token"
        params = {"ognid": "12345"}
        wrong_sign = "wrong_sign_value"

        assert verify_sign(token, params, wrong_sign) is False


class TestPinzhiAdapter:
    """品智适配器测试类"""

    def test_init_success(self, adapter):
        """测试适配器初始化成功"""
        assert adapter.base_url == "http://192.168.1.100:8080/pzcatering-gateway"
        assert adapter.token == "test_token_12345"
        assert adapter.timeout == 30
        assert adapter.retry_times == 3

    def test_init_no_token(self, adapter_no_token):
        """测试没有token时初始化失败"""
        with pytest.raises(ValueError, match="token不能为空"):
            PinzhiAdapter(adapter_no_token)

    def test_init_no_url(self, adapter_no_url):
        """测试没有base_url时初始化失败"""
        with pytest.raises(ValueError, match="base_url不能为空"):
            PinzhiAdapter(adapter_no_url)

    def test_add_sign(self, adapter):
        """测试添加签名"""
        params = {"ognid": "12345"}
        signed_params = adapter._add_sign(params)

        assert "sign" in signed_params
        assert len(signed_params["sign"]) == 32

    @pytest.mark.asyncio
    async def test_get_store_info_all(self, adapter):
        """测试查询所有门店"""
        result = await adapter.get_store_info()

        assert isinstance(result, list)
        assert len(result) > 0
        assert "ognid" in result[0]
        assert "ognname" in result[0]

    @pytest.mark.asyncio
    async def test_get_store_info_by_id(self, adapter):
        """测试查询指定门店"""
        result = await adapter.get_store_info(ognid="12345")

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_dish_categories(self, adapter):
        """测试查询菜品类别"""
        result = await adapter.get_dish_categories()

        assert isinstance(result, list)
        if len(result) > 0:
            assert "rcId" in result[0]
            assert "rcNAME" in result[0]
            assert "fatherId" in result[0]

    @pytest.mark.asyncio
    async def test_get_dishes(self, adapter):
        """测试查询菜品信息"""
        result = await adapter.get_dishes(updatetime=0)

        assert isinstance(result, list)
        if len(result) > 0:
            assert "dishesId" in result[0]
            assert "dishesName" in result[0]
            assert "dishPrice" in result[0]

    @pytest.mark.asyncio
    async def test_get_tables(self, adapter):
        """测试查询桌台信息"""
        result = await adapter.get_tables()

        assert isinstance(result, list)
        if len(result) > 0:
            assert "tableId" in result[0]
            assert "tableName" in result[0]
            assert "blName" in result[0]

    @pytest.mark.asyncio
    async def test_get_employees(self, adapter):
        """测试查询员工信息"""
        result = await adapter.get_employees()

        assert isinstance(result, list)
        if len(result) > 0:
            assert "epId" in result[0]
            assert "epName" in result[0]
            assert "pgName" in result[0]

    @pytest.mark.asyncio
    async def test_query_orders(self, adapter):
        """测试查询订单"""
        result = await adapter.query_orders(
            ognid="12345", begin_date="2024-01-01", end_date="2024-01-31"
        )

        assert isinstance(result, list)
        if len(result) > 0:
            assert "billId" in result[0]
            assert "billNo" in result[0]
            assert "billStatus" in result[0]

    @pytest.mark.asyncio
    async def test_query_orders_with_pagination(self, adapter):
        """测试分页查询订单"""
        result = await adapter.query_orders(page_index=1, page_size=10)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_query_order_summary(self, adapter):
        """测试查询收入数据"""
        result = await adapter.query_order_summary(
            ognid="12345", business_date="2024-01-01"
        )

        assert isinstance(result, dict)
        assert "ognId" in result
        assert "businesDate" in result

    @pytest.mark.asyncio
    async def test_get_pay_types(self, adapter):
        """测试查询支付方式"""
        result = await adapter.get_pay_types()

        assert isinstance(result, list)
        if len(result) > 0:
            assert "id" in result[0]
            assert "name" in result[0]
            assert "category" in result[0]


class TestDataStructure:
    """数据结构测试"""

    @pytest.mark.asyncio
    async def test_store_data_structure(self, adapter):
        """测试门店数据结构"""
        result = await adapter.get_store_info()

        if len(result) > 0:
            store = result[0]
            required_fields = [
                "ognid",
                "ognno",
                "ognname",
                "ognaddress",
                "brandid",
                "brandname",
            ]
            for field in required_fields:
                assert field in store, f"缺少必需字段: {field}"

    @pytest.mark.asyncio
    async def test_order_data_structure(self, adapter):
        """测试订单数据结构"""
        result = await adapter.query_orders()

        if len(result) > 0:
            order = result[0]
            required_fields = [
                "billId",
                "billNo",
                "billStatus",
                "billPriceTotal",
                "realPrice",
                "payDate",
            ]
            for field in required_fields:
                assert field in order, f"缺少必需字段: {field}"

    @pytest.mark.asyncio
    async def test_amount_in_fen(self, adapter):
        """测试金额单位为分"""
        result = await adapter.query_orders()

        if len(result) > 0:
            order = result[0]
            # 验证金额字段都是整数（分）
            assert isinstance(order["dishPriceTotal"], int)
            assert isinstance(order["billPriceTotal"], int)
            assert isinstance(order["realPrice"], int)

    @pytest.mark.asyncio
    async def test_datetime_format(self, adapter):
        """测试日期时间格式"""
        result = await adapter.query_orders()

        if len(result) > 0:
            order = result[0]
            # 验证日期格式 YYYY-MM-DD
            assert len(order["payDate"]) == 10
            assert order["payDate"].count("-") == 2

            # 验证日期时间格式 YYYY-MM-DD HH:mm:ss
            if order.get("openTime"):
                assert len(order["openTime"]) == 19
                assert order["openTime"].count(":") == 2


class TestErrorHandling:
    """错误处理测试"""

    def test_handle_error_with_success_field(self, adapter):
        """测试处理success字段错误"""
        response = {"success": 1, "msg": "参数错误"}

        with pytest.raises(Exception, match="品智API错误"):
            adapter.handle_error(response)

    def test_handle_error_with_errcode_field(self, adapter):
        """测试处理errcode字段错误"""
        response = {"errcode": 1, "errmsg": "签名验证失败"}

        with pytest.raises(Exception, match="品智API错误"):
            adapter.handle_error(response)

    def test_handle_error_success(self, adapter):
        """测试处理成功响应"""
        response = {"success": 0, "msg": "成功"}

        # 不应该抛出异常
        adapter.handle_error(response)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
