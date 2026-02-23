"""
API适配器基础类
提供统一的接口规范和通用功能
"""
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class APIError(Exception):
    """API错误基类"""

    def __init__(self, code: int, message: str, system: Optional[str] = None):
        self.code = code
        self.message = message
        self.system = system
        super().__init__(f"[{system}] {code}: {message}")


class BaseAdapter(ABC):
    """API适配器基类"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含base_url, api_key等
        """
        self.config = config
        self.base_url = config.get("base_url")
        self.timeout = config.get("timeout", int(os.getenv("ADAPTER_DEFAULT_TIMEOUT", "30")))
        self.retry_times = config.get("retry_times", int(os.getenv("ADAPTER_DEFAULT_RETRY_TIMES", "3")))
        self.client = httpx.AsyncClient(timeout=self.timeout)

    @abstractmethod
    async def authenticate(self) -> Dict[str, str]:
        """
        认证方法，返回认证头部

        Returns:
            认证头部字典
        """
        pass

    @retry(
        stop=stop_after_attempt(int(os.getenv("ADAPTER_RETRY_ATTEMPTS", "3"))),
        wait=wait_exponential(multiplier=int(os.getenv("ADAPTER_RETRY_MULTIPLIER", "1")), min=int(os.getenv("ADAPTER_RETRY_MIN", "2")), max=int(os.getenv("ADAPTER_RETRY_MAX", "10"))),
    )
    async def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        统一请求方法

        Args:
            method: HTTP方法 (GET, POST, PUT, DELETE)
            endpoint: API端点
            params: URL参数
            data: 请求体数据
            headers: 请求头

        Returns:
            响应数据字典

        Raises:
            APIError: API调用失败
        """
        url = f"{self.base_url}{endpoint}"

        # 获取认证头部
        auth_headers = await self.authenticate()
        if headers:
            auth_headers.update(headers)

        logger.info(
            "API请求",
            method=method,
            url=url,
            params=params,
            system=self.__class__.__name__,
        )

        try:
            response = await self.client.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=auth_headers,
            )

            # 记录响应
            logger.info(
                "API响应",
                status_code=response.status_code,
                response_time=response.elapsed.total_seconds(),
                system=self.__class__.__name__,
            )

            # 检查HTTP状态码
            if response.status_code >= 400:
                raise APIError(
                    code=response.status_code,
                    message=response.text,
                    system=self.__class__.__name__,
                )

            # 解析响应
            response_data = response.json()

            # 处理业务错误
            self.handle_error(response_data)

            return response_data

        except httpx.HTTPError as e:
            logger.error("HTTP请求失败", exc_info=e, system=self.__class__.__name__)
            raise APIError(
                code=500, message=str(e), system=self.__class__.__name__
            )

    @abstractmethod
    def handle_error(self, response: Dict[str, Any]) -> None:
        """
        处理业务错误

        Args:
            response: API响应数据

        Raises:
            APIError: 业务错误
        """
        pass

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
