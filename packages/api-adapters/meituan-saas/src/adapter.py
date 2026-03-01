"""
美团餐饮SAAS平台API适配器
提供订单管理、门店管理、商品管理、配送管理等功能
"""
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime
import httpx
import hashlib
import json

logger = structlog.get_logger()


class MeituanSaasAdapter:
    """美团餐饮SAAS平台适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - base_url: API基础URL
                - app_key: 应用Key
                - app_secret: 应用密钥
                - poi_id: 门店ID (Point of Interest)
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.config = config
        self.base_url = config.get("base_url", "https://waimaiopen.meituan.com")
        self.app_key = config.get("app_key")
        self.app_secret = config.get("app_secret")
        self.poi_id = config.get("poi_id")
        self.timeout = config.get("timeout", 30)
        self.retry_times = config.get("retry_times", 3)

        if not self.app_key or not self.app_secret:
            raise ValueError("app_key和app_secret不能为空")

        # 初始化HTTP客户端
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        logger.info("美团SAAS适配器初始化", base_url=self.base_url, poi_id=self.poi_id)

    def _generate_sign(self, params: Dict[str, Any]) -> str:
        """
        生成API签名（美团签名算法）

        Args:
            params: 请求参数

        Returns:
            签名字符串
        """
        # 按key排序
        sorted_params = sorted(params.items())
        # 拼接字符串
        sign_str = self.app_secret
        for k, v in sorted_params:
            sign_str += f"{k}{v}"
        sign_str += self.app_secret
        # MD5加密
        return hashlib.md5(sign_str.encode()).hexdigest().lower()

    def authenticate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        认证方法，添加认证参数

        Args:
            params: 原始请求参数

        Returns:
            包含认证信息的参数字典
        """
        timestamp = str(int(datetime.now().timestamp()))
        auth_params = {
            "app_key": self.app_key,
            "timestamp": timestamp,
            **params,
        }
        # 生成签名
        auth_params["sign"] = self._generate_sign(auth_params)
        return auth_params

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送HTTP请求

        Args:
            method: HTTP方法 (GET/POST)
            endpoint: API端点
            data: 请求数据

        Returns:
            API响应数据

        Raises:
            Exception: 请求失败
        """
        for attempt in range(self.retry_times):
            try:
                request_data = data or {}
                # 添加认证参数
                auth_data = self.authenticate(request_data)

                headers = {"Content-Type": "application/x-www-form-urlencoded"}

                if method.upper() == "GET":
                    response = await self.client.get(endpoint, params=auth_data, headers=headers)
                elif method.upper() == "POST":
                    response = await self.client.post(endpoint, data=auth_data, headers=headers)
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")

                response.raise_for_status()
                result = response.json()
                self.handle_error(result)
                return result

            except httpx.HTTPStatusError as e:
                logger.error(
                    "HTTP请求失败",
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise Exception(f"HTTP请求失败: {e.response.status_code}")

            except Exception as e:
                logger.error(
                    "请求异常",
                    endpoint=endpoint,
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise

        raise Exception("请求失败，已达到最大重试次数")

    def handle_error(self, response: Dict[str, Any]) -> None:
        """
        处理业务错误

        Args:
            response: API响应数据

        Raises:
            Exception: 业务错误
        """
        code = response.get("code")
        if code != "ok" and code != 0:
            message = response.get("message", "未知错误")
            raise Exception(f"美团API错误 [{code}]: {message}")

    # ==================== 订单管理接口 ====================

    async def query_order(
        self,
        order_id: Optional[str] = None,
        day_seq: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询订单详情

        Args:
            order_id: 订单ID
            day_seq: 日流水号

        Returns:
            订单详情
        """
        if not order_id and not day_seq:
            raise ValueError("order_id和day_seq至少提供一个")

        data = {}
        if order_id:
            data["order_id"] = order_id
        if day_seq:
            data["day_seq"] = day_seq

        logger.info("查询订单", data=data)

        response = await self._request("GET", "/api/order/queryById", data=data)
        return response.get("data", {})

    async def confirm_order(
        self,
        order_id: str,
    ) -> Dict[str, Any]:
        """
        确认订单

        Args:
            order_id: 订单ID

        Returns:
            确认结果
        """
        data = {"order_id": order_id}

        logger.info("确认订单", order_id=order_id)

        response = await self._request("POST", "/api/order/confirm", data=data)
        return response.get("data", {})

    async def cancel_order(
        self,
        order_id: str,
        reason_code: int,
        reason: str,
    ) -> Dict[str, Any]:
        """
        取消订单

        Args:
            order_id: 订单ID
            reason_code: 取消原因代码
            reason: 取消原因描述

        Returns:
            取消结果
        """
        data = {
            "order_id": order_id,
            "reason_code": reason_code,
            "reason": reason,
        }

        logger.info("取消订单", order_id=order_id, reason=reason)

        response = await self._request("POST", "/api/order/cancel", data=data)
        return response.get("data", {})

    async def refund_order(
        self,
        order_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        订单退款

        Args:
            order_id: 订单ID
            reason: 退款原因

        Returns:
            退款结果
        """
        data = {
            "order_id": order_id,
            "reason": reason,
        }

        logger.info("订单退款", order_id=order_id, reason=reason)

        response = await self._request("POST", "/api/order/refund", data=data)
        return response.get("data", {})

    # ==================== 商品管理接口 ====================

    async def query_food(
        self,
        food_id: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询商品

        Args:
            food_id: 商品ID
            category_id: 分类ID

        Returns:
            商品列表
        """
        data = {"app_poi_code": self.poi_id}
        if food_id:
            data["food_id"] = food_id
        if category_id:
            data["category_id"] = category_id

        logger.info("查询商品", data=data)

        response = await self._request("GET", "/api/food/query", data=data)
        return response.get("data", [])

    async def update_food_stock(
        self,
        food_id: str,
        stock: int,
    ) -> Dict[str, Any]:
        """
        更新商品库存

        Args:
            food_id: 商品ID
            stock: 库存数量

        Returns:
            更新结果
        """
        data = {
            "app_poi_code": self.poi_id,
            "food_id": food_id,
            "stock": stock,
        }

        logger.info("更新商品库存", food_id=food_id, stock=stock)

        response = await self._request("POST", "/api/food/updateStock", data=data)
        return response.get("data", {})

    async def update_food_price(
        self,
        food_id: str,
        price: int,
    ) -> Dict[str, Any]:
        """
        更新商品价格

        Args:
            food_id: 商品ID
            price: 价格（分）

        Returns:
            更新结果
        """
        data = {
            "app_poi_code": self.poi_id,
            "food_id": food_id,
            "price": price,
        }

        logger.info("更新商品价格", food_id=food_id, price=price)

        response = await self._request("POST", "/api/food/updatePrice", data=data)
        return response.get("data", {})

    async def sold_out_food(
        self,
        food_id: str,
    ) -> Dict[str, Any]:
        """
        商品售罄

        Args:
            food_id: 商品ID

        Returns:
            操作结果
        """
        data = {
            "app_poi_code": self.poi_id,
            "food_id": food_id,
        }

        logger.info("商品售罄", food_id=food_id)

        response = await self._request("POST", "/api/food/soldout", data=data)
        return response.get("data", {})

    async def on_sale_food(
        self,
        food_id: str,
    ) -> Dict[str, Any]:
        """
        商品上架

        Args:
            food_id: 商品ID

        Returns:
            操作结果
        """
        data = {
            "app_poi_code": self.poi_id,
            "food_id": food_id,
        }

        logger.info("商品上架", food_id=food_id)

        response = await self._request("POST", "/api/food/onsale", data=data)
        return response.get("data", {})

    # ==================== 门店管理接口 ====================

    async def query_poi_info(self) -> Dict[str, Any]:
        """
        查询门店信息

        Returns:
            门店信息
        """
        data = {"app_poi_code": self.poi_id}

        logger.info("查询门店信息", poi_id=self.poi_id)

        response = await self._request("GET", "/api/poi/query", data=data)
        return response.get("data", {})

    async def update_poi_status(
        self,
        is_online: int,
    ) -> Dict[str, Any]:
        """
        更新门店营业状态

        Args:
            is_online: 营业状态 (1-营业中 0-休息中)

        Returns:
            更新结果
        """
        data = {
            "app_poi_code": self.poi_id,
            "is_online": is_online,
        }

        logger.info("更新门店状态", poi_id=self.poi_id, is_online=is_online)

        response = await self._request("POST", "/api/poi/updateStatus", data=data)
        return response.get("data", {})

    # ==================== 配送管理接口 ====================

    async def query_logistics(
        self,
        order_id: str,
    ) -> Dict[str, Any]:
        """
        查询配送信息

        Args:
            order_id: 订单ID

        Returns:
            配送信息
        """
        data = {"order_id": order_id}

        logger.info("查询配送信息", order_id=order_id)

        response = await self._request("GET", "/api/logistics/query", data=data)
        return response.get("data", {})

    async def close(self):
        """关闭适配器，释放资源"""
        logger.info("关闭美团SAAS适配器")
        await self.client.aclose()
