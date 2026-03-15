"""
抖音生活服务开放平台 API 适配器
提供团购券管理、订单查询、门店信息、结算单等功能
"""
import hashlib
import hmac
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()


class DouyinAdapter:
    """抖音生活服务开放平台适配器"""

    PRODUCTION_BASE_URL = "https://open.douyin.com"
    SANDBOX_BASE_URL = "https://open-sandbox.douyin.com"

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - app_id: 应用ID
                - app_secret: 应用密钥
                - sandbox: 是否沙箱环境（默认 False）
                - timeout: 超时时间（秒，默认 30）
                - retry_times: 重试次数（默认 3）
        """
        self.config = config
        self.app_id = config.get("app_id")
        self.app_secret = config.get("app_secret")
        self.sandbox = config.get("sandbox", False)
        self.timeout = config.get("timeout", 30)
        self.retry_times = config.get("retry_times", 3)

        if not self.app_id or not self.app_secret:
            raise ValueError("app_id 和 app_secret 不能为空")

        base_url = self.SANDBOX_BASE_URL if self.sandbox else self.PRODUCTION_BASE_URL
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        logger.info(
            "抖音生活服务适配器初始化",
            app_id=self.app_id,
            sandbox=self.sandbox,
        )

    def _generate_sign(self, params: Dict[str, Any], timestamp: str) -> str:
        """
        生成 HMAC-SHA256 签名

        签名规则：sorted(params) 拼接后 + timestamp，以 app_secret 为 key
        """
        sorted_params = sorted(params.items())
        sign_str = ""
        for k, v in sorted_params:
            sign_str += f"{k}={v}&"
        sign_str += f"timestamp={timestamp}"
        signature = hmac.new(
            self.app_secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    async def _ensure_token(self) -> str:
        """确保 access_token 有效，过期时自动刷新"""
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        logger.info("获取抖音 access_token", app_id=self.app_id)
        response = await self.client.post(
            "/oauth/client_token/",
            json={
                "client_key": self.app_id,
                "client_secret": self.app_secret,
                "grant_type": "client_credential",
            },
        )
        response.raise_for_status()
        result = response.json()

        data = result.get("data", {})
        if data.get("error_code", 0) != 0:
            err_msg = data.get("description", "未知错误")
            raise Exception(f"获取 access_token 失败: {err_msg}")

        self._access_token = data["access_token"]
        self._token_expires_at = now + data.get("expires_in", 7200)
        logger.info("access_token 获取成功", expires_in=data.get("expires_in"))
        return self._access_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        need_auth: bool = True,
    ) -> Dict[str, Any]:
        """发送 HTTP 请求（含重试和签名）"""
        for attempt in range(self.retry_times):
            try:
                headers: Dict[str, str] = {"Content-Type": "application/json"}

                if need_auth:
                    token = await self._ensure_token()
                    headers["access-token"] = token

                timestamp = str(int(time.time()))
                sign_data = {**(data or {}), **(params or {})}
                sign = self._generate_sign(sign_data, timestamp)
                headers["X-Signature"] = sign
                headers["X-Timestamp"] = timestamp

                if method.upper() == "GET":
                    response = await self.client.get(
                        endpoint, params=params, headers=headers,
                    )
                elif method.upper() == "POST":
                    response = await self.client.post(
                        endpoint, json=data, params=params, headers=headers,
                    )
                else:
                    raise ValueError(f"不支持的 HTTP 方法: {method}")

                response.raise_for_status()
                result = response.json()
                self._handle_error(result)
                return result

            except httpx.HTTPStatusError as e:
                logger.error(
                    "抖音 HTTP 请求失败",
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise Exception(f"HTTP 请求失败: {e.response.status_code}")

            except Exception as e:
                logger.error(
                    "抖音请求异常",
                    endpoint=endpoint,
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise

        raise Exception("请求失败，已达到最大重试次数")

    def _handle_error(self, response: Dict[str, Any]) -> None:
        """处理业务错误"""
        data = response.get("data", response)
        error_code = data.get("error_code", 0)
        if error_code != 0:
            message = data.get("description", response.get("message", "未知错误"))
            raise Exception(f"抖音 API 错误 [{error_code}]: {message}")

    # ==================== 团购券接口 ====================

    async def query_coupons(
        self, page: int = 1, page_size: int = 20,
    ) -> Dict[str, Any]:
        """查询团购券列表"""
        data = {
            "page": page,
            "page_size": page_size,
        }
        logger.info("查询团购券列表", page=page, page_size=page_size)
        result = await self._request(
            "POST", "/api/apps/trade/v2/coupon/query_list/", data=data,
        )
        return result.get("data", {})

    async def get_coupon_detail(self, coupon_id: str) -> Dict[str, Any]:
        """查询团购券详情"""
        data = {"coupon_id": coupon_id}
        logger.info("查询团购券详情", coupon_id=coupon_id)
        result = await self._request(
            "POST", "/api/apps/trade/v2/coupon/query_detail/", data=data,
        )
        return result.get("data", {})

    async def verify_coupon(self, code: str, shop_id: str) -> Dict[str, Any]:
        """
        核销团购券

        Args:
            code: 券码
            shop_id: 抖音门店 ID
        """
        data = {"code": code, "shop_id": shop_id}
        logger.info("核销团购券", shop_id=shop_id)
        result = await self._request(
            "POST", "/api/apps/trade/v2/coupon/verify/", data=data,
        )
        return result.get("data", {})

    # ==================== 订单接口 ====================

    async def query_orders(
        self,
        start_time: str,
        end_time: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        查询团购订单列表

        Args:
            start_time: 开始时间 (ISO 格式)
            end_time: 结束时间 (ISO 格式)
            page: 页码
            page_size: 每页大小
        """
        data = {
            "start_time": start_time,
            "end_time": end_time,
            "page": page,
            "page_size": page_size,
        }
        logger.info("查询团购订单", start_time=start_time, end_time=end_time, page=page)
        result = await self._request(
            "POST", "/api/apps/trade/v2/order/query_list/", data=data,
        )
        return result.get("data", {})

    async def get_order_detail(self, order_id: str) -> Dict[str, Any]:
        """查询团购订单详情"""
        data = {"order_id": order_id}
        logger.info("查询团购订单详情", order_id=order_id)
        result = await self._request(
            "POST", "/api/apps/trade/v2/order/query_detail/", data=data,
        )
        return result.get("data", {})

    # ==================== 门店接口 ====================

    async def get_shop_info(self, shop_id: str) -> Dict[str, Any]:
        """查询抖音门店信息"""
        data = {"shop_id": shop_id}
        logger.info("查询抖音门店信息", shop_id=shop_id)
        result = await self._request(
            "POST", "/api/apps/trade/v2/shop/query/", data=data,
        )
        return result.get("data", {})

    # ==================== 结算接口 ====================

    async def query_settlements(
        self, start_date: str, end_date: str,
    ) -> Dict[str, Any]:
        """
        查询结算单列表

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        data = {"start_date": start_date, "end_date": end_date}
        logger.info("查询结算单", start_date=start_date, end_date=end_date)
        result = await self._request(
            "POST", "/api/apps/trade/v2/settlement/query_list/", data=data,
        )
        return result.get("data", {})

    # ==================== 资源管理 ====================

    async def close(self) -> None:
        """关闭适配器，释放资源"""
        logger.info("关闭抖音生活服务适配器")
        await self.client.aclose()
