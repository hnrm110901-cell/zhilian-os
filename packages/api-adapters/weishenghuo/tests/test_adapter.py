"""
微生活会员适配器单元测试

重点验证：
  1. Token 获取与缓存机制
  2. 通用请求重试逻辑
  3. 业务错误与网络错误的区分处理
  4. 各会员接口入参校验与降级返回
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.adapter import WeishenghuoAdapter


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def adapter() -> WeishenghuoAdapter:
    return WeishenghuoAdapter(
        {
            "base_url": "https://open.i200.cn",
            "appid": "TEST_APPID",
            "app_secret": "TEST_SECRET",
            "timeout": 5,
            "retry_times": 2,
        }
    )


def _mock_token_response() -> httpx.Response:
    """构造 token 成功响应"""
    return httpx.Response(
        200,
        json={
            "errcode": 0,
            "errmsg": "ok",
            "data": {"access_token": "test_token_abc", "expires_in": 7200},
        },
        request=httpx.Request("POST", "https://open.i200.cn/auth/token"),
    )


def _mock_success_response(data: dict) -> httpx.Response:
    """构造业务成功响应"""
    return httpx.Response(
        200,
        json={"errcode": 0, "errmsg": "ok", "data": data},
        request=httpx.Request("GET", "https://open.i200.cn/test"),
    )


def _mock_business_error_response(errcode: int = 40001, errmsg: str = "参数错误") -> httpx.Response:
    """构造业务错误响应"""
    return httpx.Response(
        200,
        json={"errcode": errcode, "errmsg": errmsg, "data": {}},
        request=httpx.Request("GET", "https://open.i200.cn/test"),
    )


# ── Token 获取 ──────────────────────────────────────────────────────────────────


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_get_access_token_success(self, adapter):
        """首次获取 token 应发起 HTTP 请求"""
        adapter._client.post = AsyncMock(return_value=_mock_token_response())

        token = await adapter._get_access_token()

        assert token == "test_token_abc"
        assert adapter._access_token == "test_token_abc"
        assert adapter._token_expires_at > time.time()
        adapter._client.post.assert_called_once_with(
            "/auth/token",
            json={"appid": "TEST_APPID", "app_secret": "TEST_SECRET"},
        )

    @pytest.mark.asyncio
    async def test_get_access_token_cached(self, adapter):
        """Token 未过期时应直接返回缓存，不发起 HTTP 请求"""
        adapter._access_token = "cached_token"
        adapter._token_expires_at = time.time() + 3600  # 1小时后过期
        adapter._client.post = AsyncMock()

        token = await adapter._get_access_token()

        assert token == "cached_token"
        adapter._client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_access_token_refresh_when_expired(self, adapter):
        """Token 已过期时应重新获取"""
        adapter._access_token = "old_token"
        adapter._token_expires_at = time.time() - 10  # 已过期
        adapter._client.post = AsyncMock(return_value=_mock_token_response())

        token = await adapter._get_access_token()

        assert token == "test_token_abc"
        adapter._client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_access_token_error(self, adapter):
        """Token 获取失败时应抛出异常"""
        error_resp = httpx.Response(
            200,
            json={"errcode": 40001, "errmsg": "invalid appid"},
            request=httpx.Request("POST", "https://open.i200.cn/auth/token"),
        )
        adapter._client.post = AsyncMock(return_value=error_resp)

        with pytest.raises(Exception, match="微生活获取 token 失败"):
            await adapter._get_access_token()


# ── 会员信息查询 ───────────────────────────────────────────────────────────────


class TestGetMemberInfo:
    @pytest.mark.asyncio
    async def test_get_member_info_by_mobile(self, adapter):
        """按手机号查询会员"""
        member_data = {
            "member_id": "M001",
            "mobile": "13800138000",
            "points": 1500,
            "balance": 50000,  # 500元（分）
            "level": "金卡",
            "card_no": "VIP20260001",
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = member_data
            result = await adapter.get_member_info(mobile="13800138000")

        assert result["member_id"] == "M001"
        assert result["points"] == 1500
        mock_req.assert_called_once_with(
            "GET", "/member/info", {"mobile": "13800138000"}
        )

    @pytest.mark.asyncio
    async def test_get_member_info_by_member_id(self, adapter):
        """按会员ID查询"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"member_id": "M001"}
            await adapter.get_member_info(member_id="M001")

        called_params = mock_req.call_args[0][2]
        assert called_params["member_id"] == "M001"
        assert "mobile" not in called_params

    @pytest.mark.asyncio
    async def test_get_member_info_raises_without_params(self, adapter):
        """mobile 和 member_id 都不传时应抛出 ValueError"""
        with pytest.raises(ValueError, match="mobile 和 member_id 至少填写一个"):
            await adapter.get_member_info()

    @pytest.mark.asyncio
    async def test_get_member_info_returns_empty_on_error(self, adapter):
        """查询失败时返回空字典（降级）"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("网络超时")
            result = await adapter.get_member_info(mobile="13800138000")

        assert result == {}


# ── 会员列表 ──────────────────────────────────────────────────────────────────


class TestListMembers:
    @pytest.mark.asyncio
    async def test_list_members_pagination(self, adapter):
        """分页拉取会员列表"""
        page_data = {
            "list": [{"member_id": "M001"}, {"member_id": "M002"}],
            "total": 150,
            "page": 2,
            "page_size": 50,
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = page_data
            result = await adapter.list_members(page=2, page_size=50)

        assert len(result["list"]) == 2
        assert result["total"] == 150
        mock_req.assert_called_once_with(
            "GET", "/member/list", {"page": 2, "page_size": 50}
        )

    @pytest.mark.asyncio
    async def test_list_members_incremental_sync(self, adapter):
        """增量同步：传 updated_after 参数"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"list": [], "total": 0, "page": 1, "page_size": 100}
            await adapter.list_members(updated_after="2026-03-01")

        called_params = mock_req.call_args[0][2]
        assert called_params["updated_after"] == "2026-03-01"

    @pytest.mark.asyncio
    async def test_list_members_caps_page_size(self, adapter):
        """page_size 超过 100 时应限制为 100"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"list": [], "total": 0, "page": 1, "page_size": 100}
            await adapter.list_members(page_size=500)

        called_params = mock_req.call_args[0][2]
        assert called_params["page_size"] == 100

    @pytest.mark.asyncio
    async def test_list_members_returns_empty_on_error(self, adapter):
        """拉取失败时返回空列表（降级）"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("连接超时")
            result = await adapter.list_members()

        assert result["list"] == []
        assert result["total"] == 0


# ── 交易记录 ──────────────────────────────────────────────────────────────────


class TestGetMemberTransactions:
    @pytest.mark.asyncio
    async def test_get_member_transactions(self, adapter):
        """查询会员交易记录"""
        tx_data = {
            "list": [
                {"tx_id": "T001", "amount": 12800, "type": "consume"},
                {"tx_id": "T002", "amount": 5000, "type": "recharge"},
            ],
            "total": 2,
            "page": 1,
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = tx_data
            result = await adapter.get_member_transactions(
                member_id="M001",
                start_date="2026-03-01",
                end_date="2026-03-17",
            )

        assert len(result["list"]) == 2
        assert result["list"][0]["amount"] == 12800  # 单位：分
        mock_req.assert_called_once_with(
            "GET",
            "/member/transactions",
            {
                "member_id": "M001",
                "start_date": "2026-03-01",
                "end_date": "2026-03-17",
                "page": 1,
            },
        )

    @pytest.mark.asyncio
    async def test_get_member_transactions_returns_empty_on_error(self, adapter):
        """查询失败时返回空列表"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("网络错误")
            result = await adapter.get_member_transactions(
                member_id="M001",
                start_date="2026-03-01",
                end_date="2026-03-17",
            )

        assert result["list"] == []


# ── 请求重试 ──────────────────────────────────────────────────────────────────


class TestRequestRetry:
    @pytest.mark.asyncio
    async def test_request_retry_on_failure(self, adapter):
        """网络错误时应重试指定次数"""
        # 预设 token 避免 token 请求干扰
        adapter._access_token = "valid_token"
        adapter._token_expires_at = time.time() + 3600

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("连接失败")
            return _mock_success_response({"ok": True})

        adapter._client.get = mock_get

        result = await adapter._request("GET", "/test", {})
        assert result == {"ok": True}
        assert call_count == 2  # 第1次失败，第2次成功

    @pytest.mark.asyncio
    async def test_request_exhausts_retries(self, adapter):
        """重试耗尽后应抛出异常"""
        adapter._access_token = "valid_token"
        adapter._token_expires_at = time.time() + 3600

        adapter._client.get = AsyncMock(
            side_effect=httpx.ConnectError("连接失败")
        )

        with pytest.raises(Exception, match="已重试 2 次"):
            await adapter._request("GET", "/test", {})

    @pytest.mark.asyncio
    async def test_request_business_error_no_retry(self, adapter):
        """业务错误（errcode != 0）不重试，直接抛出"""
        adapter._access_token = "valid_token"
        adapter._token_expires_at = time.time() + 3600

        adapter._client.get = AsyncMock(
            return_value=_mock_business_error_response(40001, "参数错误")
        )

        with pytest.raises(Exception, match="微生活业务错误.*参数错误"):
            await adapter._request("GET", "/test", {})

        # 业务错误只调用一次，不重试
        adapter._client.get.assert_called_once()


# ── 初始化 ────────────────────────────────────────────────────────────────────


class TestAdapterInit:
    def test_init_with_config(self):
        adapter = WeishenghuoAdapter(
            {
                "base_url": "https://custom.i200.cn",
                "appid": "MY_APPID",
                "app_secret": "MY_SECRET",
                "timeout": 10,
                "retry_times": 5,
            }
        )
        assert adapter.base_url == "https://custom.i200.cn"
        assert adapter.appid == "MY_APPID"
        assert adapter.app_secret == "MY_SECRET"
        assert adapter.timeout == 10
        assert adapter.retry_times == 5

    def test_missing_credentials_warning(self, monkeypatch):
        """appid/app_secret 未配置时应发出警告但不报错"""
        monkeypatch.delenv("WSH_APPID", raising=False)
        monkeypatch.delenv("WSH_APP_SECRET", raising=False)
        adapter = WeishenghuoAdapter({"base_url": "https://open.i200.cn"})
        assert adapter is not None
        assert adapter.appid == ""
        assert adapter.app_secret == ""

    def test_default_values(self, monkeypatch):
        """未传配置时应使用默认值"""
        monkeypatch.delenv("WSH_BASE_URL", raising=False)
        monkeypatch.delenv("WSH_APPID", raising=False)
        monkeypatch.delenv("WSH_APP_SECRET", raising=False)
        monkeypatch.delenv("WSH_TIMEOUT", raising=False)
        monkeypatch.delenv("WSH_RETRY_TIMES", raising=False)
        adapter = WeishenghuoAdapter({})
        assert adapter.base_url == "https://open.i200.cn"
        assert adapter.timeout == 30
        assert adapter.retry_times == 3


# ── 积分 & 储值 ───────────────────────────────────────────────────────────────


class TestPointsAndStoredValue:
    @pytest.mark.asyncio
    async def test_get_member_points(self, adapter):
        """查询会员积分"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"balance": 2500, "history": []}
            result = await adapter.get_member_points("M001")

        assert result["balance"] == 2500
        mock_req.assert_called_once_with(
            "GET", "/member/points", {"member_id": "M001"}
        )

    @pytest.mark.asyncio
    async def test_get_member_stored_value(self, adapter):
        """查询会员储值余额"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"balance": 100000}  # 1000元
            result = await adapter.get_member_stored_value("M001")

        assert result["balance"] == 100000
        mock_req.assert_called_once_with(
            "GET", "/member/stored-value", {"member_id": "M001"}
        )

    @pytest.mark.asyncio
    async def test_get_member_points_returns_default_on_error(self, adapter):
        """积分查询失败时返回默认值"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("超时")
            result = await adapter.get_member_points("M001")

        assert result == {"balance": 0, "history": []}

    @pytest.mark.asyncio
    async def test_get_member_stored_value_returns_default_on_error(self, adapter):
        """储值查询失败时返回默认值"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("超时")
            result = await adapter.get_member_stored_value("M001")

        assert result == {"balance": 0}


# ── 门店列表 ──────────────────────────────────────────────────────────────────


class TestGetShopList:
    @pytest.mark.asyncio
    async def test_get_shop_list(self, adapter):
        """获取门店列表"""
        shops = [
            {"shop_id": "S001", "shop_name": "朝阳门店"},
            {"shop_id": "S002", "shop_name": "海淀门店"},
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"list": shops}
            result = await adapter.get_shop_list()

        assert len(result) == 2
        assert result[0]["shop_name"] == "朝阳门店"

    @pytest.mark.asyncio
    async def test_get_shop_list_direct_array(self, adapter):
        """API 直接返回列表格式时也能正确处理"""
        shops = [{"shop_id": "S001", "shop_name": "门店A"}]
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = shops
            result = await adapter.get_shop_list()

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_shop_list_returns_empty_on_error(self, adapter):
        """门店列表查询失败时返回空列表"""
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("网络错误")
            result = await adapter.get_shop_list()

        assert result == []
