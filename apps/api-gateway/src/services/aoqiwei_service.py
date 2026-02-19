"""
奥琦韦会员系统适配器
Aoqiwei Member System Adapter
"""
from typing import Dict, Any, Optional
import httpx
import structlog
from datetime import datetime

from ..core.config import settings

logger = structlog.get_logger()


class AoqiweiService:
    """奥琦韦会员系统服务"""

    def __init__(self):
        self.api_key = settings.AOQIWEI_API_KEY
        self.base_url = settings.AOQIWEI_BASE_URL
        self.timeout = settings.AOQIWEI_TIMEOUT
        self.retry_times = settings.AOQIWEI_RETRY_TIMES

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_key and self.base_url)

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态信息
        """
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "奥琦韦未配置，请设置AOQIWEI_API_KEY和AOQIWEI_BASE_URL",
                "configured": False,
                "reachable": False,
            }

        try:
            async with httpx.AsyncClient() as client:
                # 尝试调用一个简单的API端点来验证连接
                response = await client.get(
                    f"{self.base_url}/api/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "message": "奥琦韦连接正常",
                        "configured": True,
                        "reachable": True,
                        "response_time_ms": response.elapsed.total_seconds() * 1000,
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "message": f"奥琦韦API返回错误: {response.status_code}",
                        "configured": True,
                        "reachable": False,
                        "status_code": response.status_code,
                    }

        except httpx.TimeoutException:
            logger.error("奥琦韦API超时")
            return {
                "status": "timeout",
                "message": "奥琦韦API连接超时",
                "configured": True,
                "reachable": False,
            }
        except Exception as e:
            logger.error("奥琦韦健康检查失败", error=str(e))
            return {
                "status": "error",
                "message": f"奥琦韦连接失败: {str(e)}",
                "configured": True,
                "reachable": False,
            }

    async def query_member(self, mobile: str) -> Dict[str, Any]:
        """
        查询会员信息

        Args:
            mobile: 会员手机号

        Returns:
            会员信息
        """
        if not self.is_configured():
            raise Exception("奥琦韦未配置")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/member/query",
                    params={"mobile": mobile},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
                result = response.json()

                if response.status_code == 200:
                    logger.info("查询会员信息成功", mobile=mobile)
                    return result
                else:
                    logger.error("查询会员信息失败", error=result)
                    raise Exception(f"查询会员失败: {result.get('message')}")

        except Exception as e:
            logger.error("查询会员信息异常", error=str(e))
            raise

    async def register_member(self, member_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        注册会员

        Args:
            member_data: 会员信息

        Returns:
            注册结果
        """
        if not self.is_configured():
            raise Exception("奥琦韦未配置")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/member/register",
                    json=member_data,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
                result = response.json()

                if response.status_code == 200:
                    logger.info("注册会员成功")
                    return result
                else:
                    logger.error("注册会员失败", error=result)
                    raise Exception(f"注册会员失败: {result.get('message')}")

        except Exception as e:
            logger.error("注册会员异常", error=str(e))
            raise

    async def submit_transaction(
        self, transaction_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        提交交易

        Args:
            transaction_data: 交易数据

        Returns:
            交易结果
        """
        if not self.is_configured():
            raise Exception("奥琦韦未配置")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/transaction/submit",
                    json=transaction_data,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
                result = response.json()

                if response.status_code == 200:
                    logger.info("提交交易成功")
                    return result
                else:
                    logger.error("提交交易失败", error=result)
                    raise Exception(f"提交交易失败: {result.get('message')}")

        except Exception as e:
            logger.error("提交交易异常", error=str(e))
            raise


# 创建全局实例
aoqiwei_service = AoqiweiService()
