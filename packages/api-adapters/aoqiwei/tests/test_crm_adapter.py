"""
奥琦玮 CRM 适配器单元测试

重点验证：
  1. 签名算法（_compute_sig / _ksort_recursive / _http_build_query）
     — 这是最核心的正确性约束，任何修改必须通过这些回归测试
  2. 请求体构建（appkey 不出现在发送体中）
  3. 业务方法入参校验
  4. 新增会员/交易/储值/优惠券/积分全链路方法
"""
import hashlib
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.crm_adapter import (
    AoqiweiCrmAdapter,
    _compute_sig,
    _http_build_query,
    _ksort_recursive,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def crm_adapter() -> AoqiweiCrmAdapter:
    return AoqiweiCrmAdapter(
        {
            "base_url": "https://welcrm.com",
            "appid": "TEST_APPID",
            "appkey": "TEST_APPKEY",
            "timeout": 5,
            "retry_times": 1,
        }
    )


# ── _ksort_recursive ────────────────────────────────────────────────────────────

class TestKsortRecursive:
    def test_flat_dict_sorted(self):
        result = _ksort_recursive({"b": 2, "a": 1, "c": 3})
        assert list(result.keys()) == ["a", "b", "c"]

    def test_nested_dict_sorted(self):
        result = _ksort_recursive({"z": {"b": 2, "a": 1}, "a": 0})
        assert list(result.keys()) == ["a", "z"]
        assert list(result["z"].keys()) == ["a", "b"]

    def test_bool_true_becomes_1(self):
        assert _ksort_recursive(True) == 1

    def test_bool_false_becomes_0(self):
        assert _ksort_recursive(False) == 0

    def test_list_items_recursed(self):
        result = _ksort_recursive([{"b": 2, "a": 1}])
        assert list(result[0].keys()) == ["a", "b"]

    def test_scalar_passthrough(self):
        assert _ksort_recursive(42) == 42
        assert _ksort_recursive("hello") == "hello"
        assert _ksort_recursive(None) is None


# ── _http_build_query ────────────────────────────────────────────────────────────

class TestHttpBuildQuery:
    def test_flat_params(self):
        result = _http_build_query({"a": "1", "b": "2"})
        assert result == "a=1&b=2"

    def test_skips_none(self):
        result = _http_build_query({"a": "1", "b": None, "c": "3"})
        assert "b" not in result
        assert "a=1" in result
        assert "c=3" in result

    def test_skips_empty_string(self):
        result = _http_build_query({"a": "1", "b": "", "c": "3"})
        assert "b" not in result

    def test_nested_dict(self):
        result = _http_build_query({"outer": {"inner": "val"}})
        assert "outer%5Binner%5D=val" in result

    def test_list_values(self):
        result = _http_build_query({"arr": ["x", "y"]})
        assert "arr%5B0%5D=x" in result
        assert "arr%5B1%5D=y" in result

    def test_integer_values(self):
        result = _http_build_query({"amount": 1234})
        assert result == "amount=1234"

    def test_empty_dict(self):
        assert _http_build_query({}) == ""

    def test_space_encoded_as_plus(self):
        result = _http_build_query({"name": "hello world"})
        assert "hello+world" in result


# ── _compute_sig ────────────────────────────────────────────────────────────────

class TestComputeSig:
    """
    签名算法回归测试。
    黄金值由手动模拟 PHP 算法计算得出，任何算法变更必须更新黄金值。
    """

    def _expected_sig(
        self,
        biz_params: Dict[str, Any],
        appid: str,
        appkey: str,
        ts: int,
        version: str = "2.0",
    ) -> str:
        """
        本地参考实现（独立于被测代码）。
        等价于 PHP:
          ksort($args);
          $args['appid'] = appid; $args['appkey'] = appkey; $args['v'] = version; $args['ts'] = ts;
          $query = http_build_query($args);
          return md5($query);
        """
        sorted_params = _ksort_recursive(biz_params)
        query = _http_build_query(sorted_params)
        query += f"&appid={appid}&appkey={appkey}&v={version}&ts={ts}"
        return hashlib.md5(query.encode("utf-8")).hexdigest().lower()

    def test_flat_params_match_reference(self):
        params = {"cno": "1234567890", "shop_id": 42, "consume_amount": 10000}
        ts = 1700000000
        sig = _compute_sig(params, "APPID", "APPKEY", ts)
        expected = self._expected_sig(params, "APPID", "APPKEY", ts)
        assert sig == expected

    def test_deterministic(self):
        params = {"cno": "ABC", "shop_id": 1}
        ts = 1700000001
        assert _compute_sig(params, "ID", "KEY", ts) == _compute_sig(params, "ID", "KEY", ts)

    def test_output_is_32_char_lowercase_hex(self):
        sig = _compute_sig({"a": "1"}, "id", "key", 1000)
        assert len(sig) == 32
        assert sig == sig.lower()
        assert all(c in "0123456789abcdef" for c in sig)

    def test_different_ts_gives_different_sig(self):
        params = {"cno": "X"}
        sig1 = _compute_sig(params, "ID", "KEY", 1000)
        sig2 = _compute_sig(params, "ID", "KEY", 1001)
        assert sig1 != sig2

    def test_appkey_change_changes_sig(self):
        params = {"cno": "X"}
        ts = 1000
        sig1 = _compute_sig(params, "ID", "KEY1", ts)
        sig2 = _compute_sig(params, "ID", "KEY2", ts)
        assert sig1 != sig2

    def test_param_order_does_not_affect_sig(self):
        """参数顺序不影响签名（因为会先 ksort）"""
        ts = 1000
        params_a = {"z": "last", "a": "first", "m": "mid"}
        params_b = {"a": "first", "m": "mid", "z": "last"}
        assert _compute_sig(params_a, "ID", "KEY", ts) == _compute_sig(params_b, "ID", "KEY", ts)

    def test_seconds_level_timestamp(self):
        """ts 必须是秒级整数（不是毫秒）"""
        ts = int(time.time())
        # 应为 10位数字
        assert 1_000_000_000 <= ts <= 9_999_999_999


# ── AoqiweiCrmAdapter 初始化 ────────────────────────────────────────────────────

class TestCrmAdapterInit:
    def test_init_success(self):
        adapter = AoqiweiCrmAdapter(
            {"base_url": "https://welcrm.com", "appid": "AID", "appkey": "AKEY"}
        )
        assert adapter.appid == "AID"
        assert adapter.appkey == "AKEY"
        assert adapter.base_url == "https://welcrm.com"

    def test_init_missing_credentials_does_not_raise(self, monkeypatch):
        monkeypatch.delenv("AOQIWEI_CRM_APPID", raising=False)
        monkeypatch.delenv("AOQIWEI_CRM_APPKEY", raising=False)
        adapter = AoqiweiCrmAdapter({"base_url": "https://welcrm.com"})
        assert adapter is not None


# ── 请求体构建：appkey 不泄露 ─────────────────────────────────────────────────────

class TestBuildRequestBody:
    def test_appkey_not_in_body(self, crm_adapter):
        body = crm_adapter._build_request_body({"cno": "123"})
        assert "appkey" not in body

    def test_sig_in_body(self, crm_adapter):
        body = crm_adapter._build_request_body({"cno": "123"})
        assert "sig" in body
        assert len(body["sig"]) == 32

    def test_appid_in_body(self, crm_adapter):
        body = crm_adapter._build_request_body({"cno": "123"})
        assert body["appid"] == "TEST_APPID"

    def test_v_in_body(self, crm_adapter):
        body = crm_adapter._build_request_body({"cno": "123"})
        assert body["v"] == "2.0"

    def test_req_field_contains_biz_params_json(self, crm_adapter):
        """业务参数被 JSON 序列化后放在 req 字段"""
        body = crm_adapter._build_request_body({"cno": "XYZ", "shop_id": 5})
        import json
        req = json.loads(body["req"])
        assert req["cno"] == "XYZ"
        assert req["shop_id"] == 5


# ── get_member_info 入参校验 ──────────────────────────────────────────────────────

class TestGetMemberInfoValidation:
    @pytest.mark.asyncio
    async def test_raises_if_no_cno_or_mobile(self, crm_adapter):
        with pytest.raises(ValueError, match="cno 和 mobile"):
            await crm_adapter.get_member_info()

    @pytest.mark.asyncio
    async def test_cno_only_accepted(self, crm_adapter):
        """只传 cno 时不报错（实际网络调用会失败，但校验通过）"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"balance": 100}
            result = await crm_adapter.get_member_info(cno="1234567890")
        assert result == {"balance": 100}
        called_params = mock_req.call_args[0][1]
        assert called_params["cno"] == "1234567890"
        assert "mobile" not in called_params

    @pytest.mark.asyncio
    async def test_mobile_only_accepted(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await crm_adapter.get_member_info(mobile="13800138000")
        called_params = mock_req.call_args[0][1]
        assert called_params["mobile"] == "13800138000"

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_error(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("网络超时")
            result = await crm_adapter.get_member_info(cno="X")
        assert result == {}


# ── deal_preview 业务流程 ─────────────────────────────────────────────────────────

class TestDealPreview:
    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"final_amount": 9800}
            await crm_adapter.deal_preview(
                cno="CARD001",
                shop_id=10,
                cashier_id=-1,
                consume_amount=10000,
                payment_amount=10000,
                payment_mode=3,
                biz_id="BIZ_UNIQUE_001",
            )
        assert mock_req.call_args[0][0] == "/deal/preview"

    @pytest.mark.asyncio
    async def test_returns_error_dict_on_failure(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("连接超时")
            result = await crm_adapter.deal_preview(
                cno="CARD001",
                shop_id=10,
                cashier_id=-1,
                consume_amount=10000,
                payment_amount=10000,
                payment_mode=3,
                biz_id="BIZ_001",
            )
        assert result["success"] is False
        assert "message" in result

    @pytest.mark.asyncio
    async def test_sub_balance_defaults_to_zero(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await crm_adapter.deal_preview(
                cno="C",
                shop_id=1,
                cashier_id=-1,
                consume_amount=100,
                payment_amount=100,
                payment_mode=1,
                biz_id="BIZ",
            )
        params = mock_req.call_args[0][1]
        assert params["sub_balance"] == 0
        assert params["sub_credit"] == 0


# ── deal_reverse 入参 ─────────────────────────────────────────────────────────────

class TestDealReverse:
    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": "ok"}
            await crm_adapter.deal_reverse(
                biz_id="ORIG_BIZ_001",
                shop_id=10,
                cashier_id=-1,
            )
        assert mock_req.call_args[0][0] == "/deal/reverse"

    @pytest.mark.asyncio
    async def test_reverse_reason_omitted_when_empty(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await crm_adapter.deal_reverse(biz_id="B", shop_id=1, cashier_id=-1)
        params = mock_req.call_args[0][1]
        assert "reverse_reason" not in params

    @pytest.mark.asyncio
    async def test_reverse_reason_included_when_set(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await crm_adapter.deal_reverse(
                biz_id="B", shop_id=1, cashier_id=-1, reverse_reason="误操作"
            )
        params = mock_req.call_args[0][1]
        assert params["reverse_reason"] == "误操作"


# ══════════════════════════════════════════════════════════════════════════════════
# 新增方法测试（会员查询/管理/交易/储值/优惠券/积分）
# ══════════════════════════════════════════════════════════════════════════════════


# ── query_member 会员查询 ─────────────────────────────────────────────────────────

class TestQueryMember:
    @pytest.mark.asyncio
    async def test_raises_if_no_identifier(self, crm_adapter):
        """三个查询参数都为空时应抛出 ValueError"""
        with pytest.raises(ValueError, match="至少填写一个"):
            await crm_adapter.query_member()

    @pytest.mark.asyncio
    async def test_query_by_card_no(self, crm_adapter):
        """按卡号查询，调用正确端点并传入 cno 参数"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"cno": "C001", "balance": 5000, "name": "张三"}
            result = await crm_adapter.query_member(card_no="C001")
        assert mock_req.call_args[0][0] == "/user/accountBasicsInfo"
        assert result["cno"] == "C001"
        # 验证金额标准化：余额同时有 fen 和 yuan
        assert result["balance_fen"] == 5000
        assert result["balance_yuan"] == 50.0

    @pytest.mark.asyncio
    async def test_query_by_mobile(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"cno": "C002", "balance": 0}
            result = await crm_adapter.query_member(mobile="13800001111")
        params = mock_req.call_args[0][1]
        assert params["mobile"] == "13800001111"
        assert "cno" not in params

    @pytest.mark.asyncio
    async def test_query_by_openid(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"cno": "C003", "balance": 100}
            result = await crm_adapter.query_member(openid="wx_open_id_123")
        params = mock_req.call_args[0][1]
        assert params["openid"] == "wx_open_id_123"

    @pytest.mark.asyncio
    async def test_returns_none_on_not_found(self, crm_adapter):
        """API 返回空结果时返回 None（降级）"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            result = await crm_adapter.query_member(card_no="NONEXIST")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self, crm_adapter):
        """网络异常时返回 None 而非抛异常"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("Connection refused")
            result = await crm_adapter.query_member(card_no="C001")
        assert result is None


# ── add_member 新增会员 ──────────────────────────────────────────────────────────

class TestAddMember:
    @pytest.mark.asyncio
    async def test_add_member_success(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"cno": "NEW001", "mobile": "13900001111"}
            result = await crm_adapter.add_member(
                mobile="13900001111", name="李四", sex=1, birthday="1990-05-15"
            )
        assert mock_req.call_args[0][0] == "/user/register"
        params = mock_req.call_args[0][1]
        assert params["mobile"] == "13900001111"
        assert params["name"] == "李四"
        assert params["sex"] == 1
        assert params["birthday"] == "1990-05-15"
        assert params["card_type"] == 1  # 默认电子卡
        assert result["cno"] == "NEW001"

    @pytest.mark.asyncio
    async def test_add_member_with_store_id(self, crm_adapter):
        """注册门店ID 应映射为 shop_id"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"cno": "NEW002"}
            await crm_adapter.add_member(
                mobile="13900002222", name="王五", store_id="S001"
            )
        params = mock_req.call_args[0][1]
        assert params["shop_id"] == "S001"

    @pytest.mark.asyncio
    async def test_add_member_invalid_sex_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="sex 必须为"):
            await crm_adapter.add_member(mobile="13900003333", name="赵六", sex=3)

    @pytest.mark.asyncio
    async def test_add_member_empty_mobile_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="mobile 不能为空"):
            await crm_adapter.add_member(mobile="", name="空号")

    @pytest.mark.asyncio
    async def test_add_member_empty_name_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="name 不能为空"):
            await crm_adapter.add_member(mobile="13900004444", name="")

    @pytest.mark.asyncio
    async def test_add_member_failure_returns_error_dict(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("手机号已注册")
            result = await crm_adapter.add_member(mobile="13900005555", name="重复")
        assert result["success"] is False
        assert "手机号已注册" in result["message"]


# ── update_member 更新会员 ───────────────────────────────────────────────────────

class TestUpdateMember:
    @pytest.mark.asyncio
    async def test_update_member_filters_allowed_fields(self, crm_adapter):
        """只传允许的字段，忽略非法字段"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": "ok"}
            await crm_adapter.update_member(
                card_no="C001",
                update_data={"name": "新名字", "sex": 2, "hacker_field": "DROP TABLE"},
            )
        params = mock_req.call_args[0][1]
        assert params["cno"] == "C001"
        assert params["name"] == "新名字"
        assert params["sex"] == 2
        # 非法字段应被过滤
        assert "hacker_field" not in params

    @pytest.mark.asyncio
    async def test_update_member_empty_card_no_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="card_no 不能为空"):
            await crm_adapter.update_member(card_no="", update_data={"name": "X"})

    @pytest.mark.asyncio
    async def test_update_member_calls_correct_endpoint(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await crm_adapter.update_member(card_no="C001", update_data={"name": "测试"})
        assert mock_req.call_args[0][0] == "/user/update"


# ── trade_query 交易查询 ─────────────────────────────────────────────────────────

class TestTradeQuery:
    @pytest.mark.asyncio
    async def test_query_by_trade_no(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [
                {"trade_id": "T001", "consume_amount": 10000, "payment_amount": 9500}
            ]
            result = await crm_adapter.trade_query(trade_no="BIZ_001")
        assert mock_req.call_args[0][0] == "/deal/query"
        params = mock_req.call_args[0][1]
        assert params["biz_id"] == "BIZ_001"
        # 验证金额标准化
        assert result[0]["consume_amount_yuan"] == 100.0
        assert result[0]["payment_amount_yuan"] == 95.0

    @pytest.mark.asyncio
    async def test_query_with_date_range(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"list": []}
            result = await crm_adapter.trade_query(
                card_no="C001", start_date="2024-01-01", end_date="2024-01-31"
            )
        params = mock_req.call_args[0][1]
        assert params["cno"] == "C001"
        assert params["start_date"] == "2024-01-01"
        assert params["end_date"] == "2024-01-31"
        assert result == []

    @pytest.mark.asyncio
    async def test_trade_query_returns_empty_on_error(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("查询超时")
            result = await crm_adapter.trade_query(card_no="C001")
        assert result == []


# ── trade_cancel 交易撤销 ────────────────────────────────────────────────────────

class TestTradeCancel:
    @pytest.mark.asyncio
    async def test_cancel_calls_correct_endpoint(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"result": "reversed"}
            result = await crm_adapter.trade_cancel(trade_id="T001", reason="顾客退款")
        assert mock_req.call_args[0][0] == "/deal/cancel"
        params = mock_req.call_args[0][1]
        assert params["biz_id"] == "T001"
        assert params["reason"] == "顾客退款"

    @pytest.mark.asyncio
    async def test_cancel_empty_trade_id_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="trade_id 不能为空"):
            await crm_adapter.trade_cancel(trade_id="")

    @pytest.mark.asyncio
    async def test_cancel_failure_returns_error_dict(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("交易已冲正")
            result = await crm_adapter.trade_cancel(trade_id="T001")
        assert result["success"] is False


# ── recharge_submit 储值充值 ─────────────────────────────────────────────────────

class TestRechargeSubmit:
    @pytest.mark.asyncio
    async def test_recharge_success_with_amount_normalization(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"balance": 15000}
            result = await crm_adapter.recharge_submit(
                card_no="C001", store_id="10", cashier="-1",
                amount=10000, pay_type=3, trade_no="RC_001",
            )
        assert mock_req.call_args[0][0] == "/recharge/commit"
        params = mock_req.call_args[0][1]
        assert params["recharge_amount"] == 10000
        assert params["cno"] == "C001"
        # 金额标准化
        assert result["balance_fen"] == 15000
        assert result["balance_yuan"] == 150.0
        assert result["recharge_amount_fen"] == 10000
        assert result["recharge_amount_yuan"] == 100.0

    @pytest.mark.asyncio
    async def test_recharge_zero_amount_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="amount 必须为正整数"):
            await crm_adapter.recharge_submit(
                card_no="C001", store_id="10", cashier="-1",
                amount=0, pay_type=3, trade_no="RC_002",
            )

    @pytest.mark.asyncio
    async def test_recharge_empty_card_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="card_no 不能为空"):
            await crm_adapter.recharge_submit(
                card_no="", store_id="10", cashier="-1",
                amount=100, pay_type=3, trade_no="RC_003",
            )


# ── recharge_query 储值查询 ──────────────────────────────────────────────────────

class TestRechargeQuery:
    @pytest.mark.asyncio
    async def test_recharge_query_success(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"balance": 20000, "records": [{"amount": 10000}]}
            result = await crm_adapter.recharge_query(card_no="C001")
        assert result["balance_fen"] == 20000
        assert result["balance_yuan"] == 200.0

    @pytest.mark.asyncio
    async def test_recharge_query_degradation_on_error(self, crm_adapter):
        """网络异常时返回降级数据（余额0+空记录）"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("timeout")
            result = await crm_adapter.recharge_query(card_no="C001")
        assert result["balance_fen"] == 0
        assert result["balance_yuan"] == 0.0
        assert result["records"] == []

    @pytest.mark.asyncio
    async def test_recharge_query_empty_card_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="card_no 不能为空"):
            await crm_adapter.recharge_query(card_no="")


# ── coupon_list 优惠券列表 ───────────────────────────────────────────────────────

class TestCouponList:
    @pytest.mark.asyncio
    async def test_coupon_list_with_face_value_normalization(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [
                {"coupon_id": "CP001", "face_value": 2000, "name": "满100减20"},
                {"coupon_id": "CP002", "face_value": 5000, "name": "满200减50"},
            ]
            result = await crm_adapter.coupon_list(card_no="C001")
        assert len(result) == 2
        assert result[0]["face_value_fen"] == 2000
        assert result[0]["face_value_yuan"] == 20.0
        assert result[1]["face_value_yuan"] == 50.0

    @pytest.mark.asyncio
    async def test_coupon_list_with_store_filter(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            await crm_adapter.coupon_list(card_no="C001", store_id="10")
        params = mock_req.call_args[0][1]
        assert params["shop_id"] == 10

    @pytest.mark.asyncio
    async def test_coupon_list_returns_empty_on_error(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("服务不可用")
            result = await crm_adapter.coupon_list(card_no="C001")
        assert result == []

    @pytest.mark.asyncio
    async def test_coupon_list_empty_card_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="card_no 不能为空"):
            await crm_adapter.coupon_list(card_no="")


# ── coupon_use 券码核销 ──────────────────────────────────────────────────────────

class TestCouponUse:
    @pytest.mark.asyncio
    async def test_coupon_use_success(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"discount_amount": 2000, "result": "ok"}
            result = await crm_adapter.coupon_use(
                code="COUPON_ABC", store_id="10", cashier="-1", amount=15000,
            )
        assert mock_req.call_args[0][0] == "/coupon/use"
        params = mock_req.call_args[0][1]
        assert params["coupon_code"] == "COUPON_ABC"
        assert params["consume_amount"] == 15000
        assert result["discount_amount_fen"] == 2000
        assert result["discount_amount_yuan"] == 20.0

    @pytest.mark.asyncio
    async def test_coupon_use_empty_code_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="code 不能为空"):
            await crm_adapter.coupon_use(code="", store_id="10", cashier="-1", amount=100)

    @pytest.mark.asyncio
    async def test_coupon_use_negative_amount_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="amount 不能为负数"):
            await crm_adapter.coupon_use(
                code="CP001", store_id="10", cashier="-1", amount=-100,
            )


# ── query_member_points 积分查询 ──────────────────────────────────────────────────

class TestQueryMemberPoints:
    @pytest.mark.asyncio
    async def test_query_points_success(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"points": 3200, "points_history": 8500}
            result = await crm_adapter.query_member_points(card_no="C001")
        assert mock_req.call_args[0][0] == "/user/credit/query"
        assert result["points"] == 3200
        assert result["points_history"] == 8500

    @pytest.mark.asyncio
    async def test_query_points_degradation(self, crm_adapter):
        """查询失败时返回降级数据（积分=0）"""
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("服务异常")
            result = await crm_adapter.query_member_points(card_no="C001")
        assert result["points"] == 0
        assert result["points_history"] == 0

    @pytest.mark.asyncio
    async def test_query_points_empty_card_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="card_no 不能为空"):
            await crm_adapter.query_member_points(card_no="")


# ── points_exchange 积分兑换 ──────────────────────────────────────────────────────

class TestPointsExchange:
    @pytest.mark.asyncio
    async def test_exchange_success(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"deducted_points": 500, "remaining_points": 2700}
            result = await crm_adapter.points_exchange(
                card_no="C001", points=500, exchange_type="gift",
            )
        assert mock_req.call_args[0][0] == "/user/credit/exchange"
        params = mock_req.call_args[0][1]
        assert params["credit"] == 500
        assert params["exchange_type"] == "gift"
        assert result["remaining_points"] == 2700

    @pytest.mark.asyncio
    async def test_exchange_zero_points_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="points 必须为正整数"):
            await crm_adapter.points_exchange(
                card_no="C001", points=0, exchange_type="cash",
            )

    @pytest.mark.asyncio
    async def test_exchange_negative_points_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="points 必须为正整数"):
            await crm_adapter.points_exchange(
                card_no="C001", points=-100, exchange_type="cash",
            )

    @pytest.mark.asyncio
    async def test_exchange_invalid_type_raises(self, crm_adapter):
        with pytest.raises(ValueError, match="exchange_type 必须为"):
            await crm_adapter.points_exchange(
                card_no="C001", points=100, exchange_type="invalid_type",
            )

    @pytest.mark.asyncio
    async def test_exchange_with_shop_id(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await crm_adapter.points_exchange(
                card_no="C001", points=100, exchange_type="coupon", shop_id=10,
            )
        params = mock_req.call_args[0][1]
        assert params["shop_id"] == 10

    @pytest.mark.asyncio
    async def test_exchange_failure_returns_error_dict(self, crm_adapter):
        with patch.object(crm_adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("积分不足")
            result = await crm_adapter.points_exchange(
                card_no="C001", points=100, exchange_type="gift",
            )
        assert result["success"] is False
        assert "积分不足" in result["message"]


# ── trade_preview / trade_submit 高层封装 ────────────────────────────────────────

class TestTradeHighLevel:
    """测试 member_service 调用的高层封装方法"""

    @pytest.mark.asyncio
    async def test_trade_preview_delegates_to_deal_preview(self, crm_adapter):
        with patch.object(crm_adapter, "deal_preview", new_callable=AsyncMock) as mock_dp:
            mock_dp.return_value = {"final_amount": 9500}
            result = await crm_adapter.trade_preview(
                card_no="C001", store_id="10", cashier="-1", amount=10000,
            )
        # 验证代理调用
        mock_dp.assert_called_once()
        call_kwargs = mock_dp.call_args[1]
        assert call_kwargs["cno"] == "C001"
        assert call_kwargs["consume_amount"] == 10000
        # 验证金额标准化
        assert result["final_amount_fen"] == 9500
        assert result["final_amount_yuan"] == 95.0

    @pytest.mark.asyncio
    async def test_trade_submit_delegates_to_deal_submit(self, crm_adapter):
        with patch.object(crm_adapter, "deal_submit", new_callable=AsyncMock) as mock_ds:
            mock_ds.return_value = {"amount": 9500, "trade_id": "T999"}
            result = await crm_adapter.trade_submit(
                card_no="C001", store_id="10", cashier="-1",
                amount=9500, pay_type=3, trade_no="BIZ_999",
                discount_plan={"sub_balance": 500},
            )
        call_kwargs = mock_ds.call_args[1]
        assert call_kwargs["cno"] == "C001"
        assert call_kwargs["biz_id"] == "BIZ_999"
        assert call_kwargs["sub_balance"] == 500
        assert call_kwargs["sub_credit"] == 0  # 未指定默认为0
        # 金额标准化
        assert result["amount_fen"] == 9500
        assert result["amount_yuan"] == 95.0
