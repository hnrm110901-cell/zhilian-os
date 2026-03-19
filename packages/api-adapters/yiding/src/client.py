"""
易订HTTP客户端 - YiDing HTTP Client

基于真实易订开放API（https://open.zhidianfan.com/yidingopen/）
认证方式：appid + secret → access_token
"""

import asyncio
import os
import ssl
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp
import structlog
from aiohttp import ClientSession, ClientTimeout, ClientError, TCPConnector

from .types import YiDingConfig

logger = structlog.get_logger()

# 默认基础URL
DEFAULT_BASE_URL = "https://open.zhidianfan.com/yidingopen/"


class YiDingAPIError(Exception):
    """易订API错误"""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.response_data = response_data


class YiDingClient:
    """
    易订HTTP客户端

    认证流程：
    1. GET /auth/token?appid=xxx&secret=xxx → access_token
    2. 后续请求通过 access_token 参数传递
    """

    def __init__(self, config: YiDingConfig):
        self.config = config
        self.base_url = config.get("base_url", DEFAULT_BASE_URL)
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        self.appid = config["appid"]
        self.secret = config["secret"]
        self.hotel_id = config.get("hotel_id")
        self.timeout = config.get("timeout", int(os.getenv("YIDING_TIMEOUT", "10")))
        self.max_retries = config.get("max_retries", int(os.getenv("YIDING_MAX_RETRIES", "3")))

        self.logger = logger.bind(adapter="yiding", appid=self.appid)

        self._session: Optional[ClientSession] = None
        self._access_token: Optional[str] = None
        self._token_time: float = 0
        self._business_name: Optional[str] = None

    async def _get_session(self) -> ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.timeout)
            # 尝试使用certifi证书，如不可用则跳过SSL验证
            ssl_context: Any = None
            try:
                import certifi
                ssl_context = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            connector = TCPConnector(ssl=ssl_context)
            self._session = ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "TunxiangOS/1.0"
                }
            )
        return self._session

    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_token(self) -> str:
        """
        获取access_token

        GET /auth/token?appid=xxx&secret=xxx

        Returns:
            access_token字符串

        Raises:
            YiDingAPIError: 认证失败
        """
        # Token有效期内复用（假设1小时有效，提前5分钟刷新）
        if self._access_token and (time.time() - self._token_time) < 3300:
            return self._access_token

        session = await self._get_session()
        url = urljoin(self.base_url, "auth/token")

        self.logger.info("yiding_get_token", url=url)

        try:
            async with session.get(
                url,
                params={"appid": self.appid, "secret": self.secret}
            ) as response:
                data = await response.json()

                if data.get("error_code") != 0:
                    error_msg = data.get("error_msg", "认证失败")
                    self.logger.error(
                        "yiding_token_failed",
                        error_code=data.get("error_code"),
                        error_msg=error_msg
                    )
                    raise YiDingAPIError(
                        message=f"易订认证失败: {error_msg}",
                        error_code=data.get("error_code"),
                        response_data=data
                    )

                token_data = data.get("data", {})
                self._access_token = token_data.get("access_token")
                self._business_name = token_data.get("business_name")
                self._token_time = time.time()

                self.logger.info(
                    "yiding_token_ok",
                    business_name=self._business_name
                )

                return self._access_token

        except (ClientError, asyncio.TimeoutError) as e:
            raise YiDingAPIError(f"易订认证请求失败: {str(e)}")

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        need_token: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送HTTP请求（带token和重试）

        易订API约定：
        - GET请求：access_token放query params
        - POST/PUT请求：access_token放JSON body
        - 响应：error_code=0表示成功
        """
        session = await self._get_session()
        url = urljoin(self.base_url, path)

        # 获取token并注入
        if need_token:
            token = await self.get_token()
            if method.upper() == "GET":
                params = params or {}
                params["access_token"] = token
            else:
                json = json or {}
                json["access_token"] = token

        last_error = None

        for attempt in range(self.max_retries):
            try:
                self.logger.info(
                    "yiding_api_request",
                    method=method,
                    url=url,
                    attempt=attempt + 1
                )

                request_kwargs = {**kwargs}
                if params:
                    request_kwargs["params"] = params
                if json:
                    request_kwargs["json"] = json

                async with session.request(
                    method,
                    url,
                    **request_kwargs
                ) as response:
                    try:
                        data = await response.json()
                    except Exception:
                        text = await response.text()
                        raise YiDingAPIError(
                            f"易订API返回非JSON: {text[:200]}"
                        )

                    self.logger.info(
                        "yiding_api_response",
                        status=response.status,
                        error_code=data.get("error_code")
                    )

                    # 检查业务错误码
                    error_code = data.get("error_code")
                    if error_code is not None and int(error_code) != 0:
                        error_msg = data.get("error_msg", "未知错误")

                        # token过期，清除后重试
                        if int(error_code) in (-2, -3):
                            self._access_token = None
                            self._token_time = 0
                            if attempt < self.max_retries - 1:
                                self.logger.warning(
                                    "yiding_token_expired_retry",
                                    attempt=attempt + 1
                                )
                                continue

                        raise YiDingAPIError(
                            message=f"易订API错误: {error_msg}",
                            error_code=int(error_code),
                            response_data=data
                        )

                    return data

            except YiDingAPIError:
                raise
            except (ClientError, asyncio.TimeoutError) as e:
                last_error = e
                self.logger.warning(
                    "yiding_request_failed",
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue

        error_msg = f"易订API调用失败,已重试{self.max_retries}次: {str(last_error)}"
        self.logger.error("yiding_request_exhausted", error=error_msg)
        raise YiDingAPIError(error_msg)

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """GET请求"""
        return await self._request("GET", path, params=params, **kwargs)

    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """POST请求"""
        return await self._request("POST", path, json=json, **kwargs)

    async def put(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """PUT请求"""
        return await self._request("PUT", path, json=json, **kwargs)

    async def ping(self) -> bool:
        """
        健康检查（通过获取token验证连通性）

        Returns:
            是否健康
        """
        try:
            await self.get_token()
            return True
        except Exception as e:
            self.logger.error("yiding_health_check_failed", error=str(e))
            return False
