"""
易订HTTP客户端 - YiDing HTTP Client

处理与易订API的HTTP通信,包括:
- 请求签名和认证
- 自动重试机制
- 错误处理
- 日志记录
"""

import asyncio
import hashlib
import os
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp
import structlog
from aiohttp import ClientSession, ClientTimeout, ClientError

from .types import YiDingConfig

logger = structlog.get_logger()


class YiDingAPIError(Exception):
    """易订API错误"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        response_data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.response_data = response_data


class YiDingClient:
    """易订HTTP客户端"""

    def __init__(self, config: YiDingConfig):
        """
        初始化易订客户端

        Args:
            config: 易订配置
        """
        self.config = config
        self.base_url = config["base_url"]
        self.app_id = config["app_id"]
        self.app_secret = config["app_secret"]
        self.timeout = config.get("timeout", int(os.getenv("YIDING_TIMEOUT", "10")))
        self.max_retries = config.get("max_retries", int(os.getenv("YIDING_MAX_RETRIES", "3")))

        self.logger = logger.bind(
            adapter="yiding",
            app_id=self.app_id
        )

        self._session: Optional[ClientSession] = None

    async def _get_session(self) -> ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.timeout)
            self._session = ClientSession(
                timeout=timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ZhilianOS/1.0"
                }
            )
        return self._session

    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _generate_signature(self, timestamp: str, nonce: str) -> str:
        """
        生成请求签名

        签名算法: SHA256(app_id + timestamp + nonce + app_secret)

        Args:
            timestamp: 时间戳
            nonce: 随机字符串

        Returns:
            签名字符串
        """
        sign_string = f"{self.app_id}{timestamp}{nonce}{self.app_secret}"
        return hashlib.sha256(sign_string.encode()).hexdigest()

    def _generate_nonce(self) -> str:
        """生成随机字符串"""
        return secrets.token_hex(int(os.getenv("YIDING_NONCE_LENGTH", "16")))

    def _get_auth_headers(self) -> Dict[str, str]:
        """
        获取认证请求头

        Returns:
            包含认证信息的请求头
        """
        timestamp = str(int(time.time() * 1000))
        nonce = self._generate_nonce()
        signature = self._generate_signature(timestamp, nonce)

        return {
            "X-YiDing-AppId": self.app_id,
            "X-YiDing-Timestamp": timestamp,
            "X-YiDing-Nonce": nonce,
            "X-YiDing-Signature": signature
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送HTTP请求(带重试)

        Args:
            method: HTTP方法
            path: API路径
            **kwargs: 其他请求参数

        Returns:
            响应数据

        Raises:
            YiDingAPIError: API调用失败
        """
        url = urljoin(self.base_url, path)
        session = await self._get_session()

        # 添加认证头
        headers = kwargs.pop("headers", {})
        headers.update(self._get_auth_headers())

        last_error = None

        for attempt in range(self.max_retries):
            try:
                self.logger.info(
                    "yiding_api_request",
                    method=method,
                    url=url,
                    attempt=attempt + 1
                )

                async with session.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs
                ) as response:
                    # 记录响应
                    self.logger.info(
                        "yiding_api_response",
                        status=response.status,
                        url=url
                    )

                    # 读取响应体
                    try:
                        data = await response.json()
                    except Exception:
                        data = {"text": await response.text()}

                    # 检查HTTP状态码
                    if response.status >= 400:
                        error_message = data.get("message", "易订API调用失败")
                        error_code = data.get("code")

                        self.logger.error(
                            "yiding_api_error",
                            status=response.status,
                            error_code=error_code,
                            message=error_message
                        )

                        raise YiDingAPIError(
                            message=error_message,
                            status_code=response.status,
                            error_code=error_code,
                            response_data=data
                        )

                    # 检查业务状态码
                    if not data.get("success", True):
                        error_message = data.get("message", "业务处理失败")
                        error_code = data.get("code")

                        self.logger.error(
                            "yiding_business_error",
                            error_code=error_code,
                            message=error_message
                        )

                        raise YiDingAPIError(
                            message=error_message,
                            error_code=error_code,
                            response_data=data
                        )

                    return data

            except (ClientError, asyncio.TimeoutError) as e:
                last_error = e
                self.logger.warning(
                    "yiding_request_failed",
                    attempt=attempt + 1,
                    error=str(e)
                )

                # 如果不是最后一次尝试,等待后重试
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    await asyncio.sleep(wait_time)
                    continue

        # 所有重试都失败
        error_msg = f"易订API调用失败,已重试{self.max_retries}次: {str(last_error)}"
        self.logger.error("yiding_request_exhausted", error=error_msg)
        raise YiDingAPIError(error_msg)

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送GET请求

        Args:
            path: API路径
            params: 查询参数
            **kwargs: 其他请求参数

        Returns:
            响应数据
        """
        return await self._request("GET", path, params=params, **kwargs)

    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送POST请求

        Args:
            path: API路径
            json: JSON请求体
            **kwargs: 其他请求参数

        Returns:
            响应数据
        """
        return await self._request("POST", path, json=json, **kwargs)

    async def put(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送PUT请求

        Args:
            path: API路径
            json: JSON请求体
            **kwargs: 其他请求参数

        Returns:
            响应数据
        """
        return await self._request("PUT", path, json=json, **kwargs)

    async def delete(
        self,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送DELETE请求

        Args:
            path: API路径
            **kwargs: 其他请求参数

        Returns:
            响应数据
        """
        return await self._request("DELETE", path, **kwargs)

    async def ping(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        try:
            await self.get("/api/health")
            return True
        except Exception as e:
            self.logger.error("yiding_health_check_failed", error=str(e))
            return False
