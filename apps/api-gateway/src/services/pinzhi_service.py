"""
品智POS系统适配器
Pinzhi POS System Adapter
"""
from typing import Dict, Any, Optional, List
import httpx
import structlog
from datetime import datetime

from ..core.config import settings

logger = structlog.get_logger()


class PinzhiService:
    """品智POS系统服务"""

    def __init__(self):
        self.token = settings.PINZHI_TOKEN
        self.base_url = settings.PINZHI_BASE_URL
        self.timeout = settings.PINZHI_TIMEOUT
        self.retry_times = settings.PINZHI_RETRY_TIMES

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.token and self.base_url)

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态信息
        """
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "品智未配置，请设置PINZHI_TOKEN和PINZHI_BASE_URL",
                "configured": False,
                "reachable": False,
            }

        try:
            async with httpx.AsyncClient() as client:
                # 尝试调用一个简单的API端点来验证连接
                response = await client.get(
                    f"{self.base_url}/api/health",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "message": "品智连接正常",
                        "configured": True,
                        "reachable": True,
                        "response_time_ms": response.elapsed.total_seconds() * 1000,
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "message": f"品智API返回错误: {response.status_code}",
                        "configured": True,
                        "reachable": False,
                        "status_code": response.status_code,
                    }

        except httpx.TimeoutException:
            logger.error("品智API超时")
            return {
                "status": "timeout",
                "message": "品智API连接超时",
                "configured": True,
                "reachable": False,
            }
        except Exception as e:
            logger.error("品智健康检查失败", error=str(e))
            return {
                "status": "error",
                "message": f"品智连接失败: {str(e)}",
                "configured": True,
                "reachable": False,
            }

    async def get_stores(self) -> List[Dict[str, Any]]:
        """
        获取门店列表

        Returns:
            门店列表
        """
        if not self.is_configured():
            raise Exception("品智未配置")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/stores",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.timeout,
                )
                result = response.json()

                if response.status_code == 200:
                    logger.info("获取门店列表成功")
                    return result.get("data", [])
                else:
                    logger.error("获取门店列表失败", error=result)
                    raise Exception(f"获取门店列表失败: {result.get('message')}")

        except Exception as e:
            logger.error("获取门店列表异常", error=str(e))
            raise

    async def get_dishes(self, store_id: str) -> List[Dict[str, Any]]:
        """
        获取菜品列表

        Args:
            store_id: 门店ID

        Returns:
            菜品列表
        """
        if not self.is_configured():
            raise Exception("品智未配置")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/dishes",
                    params={"store_id": store_id},
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.timeout,
                )
                result = response.json()

                if response.status_code == 200:
                    logger.info("获取菜品列表成功", store_id=store_id)
                    return result.get("data", [])
                else:
                    logger.error("获取菜品列表失败", error=result)
                    raise Exception(f"获取菜品列表失败: {result.get('message')}")

        except Exception as e:
            logger.error("获取菜品列表异常", error=str(e))
            raise

    async def get_orders(
        self, store_id: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        获取订单列表

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            订单列表
        """
        if not self.is_configured():
            raise Exception("品智未配置")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/orders",
                    params={
                        "store_id": store_id,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.timeout,
                )
                result = response.json()

                if response.status_code == 200:
                    logger.info("获取订单列表成功", store_id=store_id)
                    return result.get("data", [])
                else:
                    logger.error("获取订单列表失败", error=result)
                    raise Exception(f"获取订单列表失败: {result.get('message')}")

        except Exception as e:
            logger.error("获取订单列表异常", error=str(e))
            raise

    async def get_sales_data(
        self, store_id: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        获取营业数据

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            营业数据
        """
        if not self.is_configured():
            raise Exception("品智未配置")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/sales",
                    params={
                        "store_id": store_id,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.timeout,
                )
                result = response.json()

                if response.status_code == 200:
                    logger.info("获取营业数据成功", store_id=store_id)
                    return result.get("data", {})
                else:
                    logger.error("获取营业数据失败", error=result)
                    raise Exception(f"获取营业数据失败: {result.get('message')}")

        except Exception as e:
            logger.error("获取营业数据异常", error=str(e))
            raise


# 创建全局实例
pinzhi_service = PinzhiService()
