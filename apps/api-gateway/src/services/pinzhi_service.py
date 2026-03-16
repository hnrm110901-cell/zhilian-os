"""
品智POS系统适配器
Pinzhi POS System Adapter
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog

from ..core.config import settings

logger = structlog.get_logger()


def _generate_sign(token: str, params: Dict[str, Any]) -> str:
    """
    生成品智 API 签名（与适配器算法保持一致）。
    """
    filtered = {k: v for k, v in params.items() if k not in ["sign", "pageIndex", "pageSize"] and v is not None}
    sorted_items = sorted(filtered.items(), key=lambda item: item[0])
    param_str = "&".join([f"{k}={v}" for k, v in sorted_items]) + f"&token={token}"
    return hashlib.md5(param_str.encode("utf-8")).hexdigest()


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

    def _probe_params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = dict(extra or {})
        params["sign"] = _generate_sign(self.token, params)
        return params

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
                # 优先探测品智 .do 接口（更贴近真实业务通路）
                probe_candidates = [
                    ("/pinzhi/reportcategory.do", self._probe_params()),
                    ("/pinzhi/storeInfo.do", self._probe_params()),
                ]

                for endpoint, params in probe_candidates:
                    response = await client.get(
                        f"{self.base_url}{endpoint}",
                        params=params,
                        timeout=self.timeout,
                    )
                    if response.status_code != 200:
                        continue

                    payload: Dict[str, Any] = {}
                    try:
                        payload = response.json() if response.content else {}
                    except Exception:
                        payload = {}

                    success = payload.get("success")
                    errcode = payload.get("errcode")
                    if success in (0, "0") or (success is None and errcode in (0, "0")):
                        return {
                            "status": "healthy",
                            "message": "品智 .do 接口连接正常",
                            "configured": True,
                            "reachable": True,
                            "probe_endpoint": endpoint,
                            "response_time_ms": response.elapsed.total_seconds() * 1000,
                        }

                    return {
                        "status": "auth_failed",
                        "message": f"品智鉴权失败: {payload.get('msg') or payload.get('errmsg') or payload}",
                        "configured": True,
                        "reachable": False,
                        "probe_endpoint": endpoint,
                    }

                # 回退到历史健康接口（兼容部分代理环境）
                response = await client.get(
                    f"{self.base_url}/api/health",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "message": "品智连接正常（health fallback）",
                        "configured": True,
                        "reachable": True,
                        "probe_endpoint": "/api/health",
                        "response_time_ms": response.elapsed.total_seconds() * 1000,
                    }
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

    async def get_orders(self, store_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
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

    async def get_sales_data(self, store_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
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
