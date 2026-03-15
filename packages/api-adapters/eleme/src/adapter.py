"""
饿了么开放平台API适配器
提供订单管理、商品管理、门店管理、配送管理等功能

饿了么开放平台文档: https://open.shop.ele.me
"""
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional, List
import structlog
import httpx
import hashlib
import json
import time

logger = structlog.get_logger()

# 饿了么API基础URL
ELEME_PRODUCTION_URL = "https://open-api.shop.ele.me"
ELEME_SANDBOX_URL = "https://open-api-sandbox.shop.ele.me"


class ElemeAdapter:
    """饿了么开放平台适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - app_key: 应用Key
                - app_secret: 应用密钥
                - sandbox: 是否沙箱环境 (默认False)
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.config = config
        self.app_key = config.get("app_key")
        self.app_secret = config.get("app_secret")
        self.sandbox = config.get("sandbox", False)
        self.timeout = config.get("timeout", 30)
        self.retry_times = config.get("retry_times", 3)

        self.base_url = ELEME_SANDBOX_URL if self.sandbox else ELEME_PRODUCTION_URL

        if not self.app_key or not self.app_secret:
            raise ValueError("app_key和app_secret不能为空")

        # OAuth2 token 缓存
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # 初始化HTTP客户端
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        logger.info(
            "饿了么适配器初始化",
            base_url=self.base_url,
            sandbox=self.sandbox,
        )

    # ==================== 认证管理 ====================

    async def _get_access_token(self) -> str:
        """
        获取或刷新 OAuth2 access_token

        Returns:
            有效的 access_token
        """
        now = time.time()
        # token 有效期内直接返回（提前60秒刷新）
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        # 刷新 token
        await self._refresh_token()
        return self._access_token

    async def _refresh_token(self) -> None:
        """
        通过 client_credentials 模式获取 access_token

        饿了么开放平台 OAuth2 token 端点:
          POST /token
          grant_type=client_credentials
        """
        timestamp = str(int(time.time()))
        sign_str = f"{self.app_key}{self.app_secret}{timestamp}"
        sign = hashlib.sha256(sign_str.encode("utf-8")).hexdigest().upper()

        payload = {
            "grant_type": "client_credentials",
            "app_key": self.app_key,
            "timestamp": timestamp,
            "sign": sign,
        }

        try:
            response = await self.client.post("/token", json=payload)
            response.raise_for_status()
            data = response.json()

            if "access_token" not in data:
                error_msg = data.get("error", data.get("message", "未知错误"))
                raise Exception(f"饿了么获取token失败: {error_msg}")

            self._access_token = data["access_token"]
            # expires_in 单位为秒
            expires_in = int(data.get("expires_in", 86400))
            self._token_expires_at = time.time() + expires_in

            logger.info("饿了么token刷新成功", expires_in=expires_in)

        except httpx.HTTPStatusError as e:
            logger.error("饿了么token请求失败", status_code=e.response.status_code)
            raise Exception(f"饿了么token请求失败: {e.response.status_code}")

    def _generate_sign(self, params: Dict[str, Any]) -> str:
        """
        生成API签名（SHA256）

        饿了么签名算法：
          1. 按key字典序排列参数
          2. 拼接 app_secret + 排序参数键值对 + app_secret
          3. SHA256 取大写hex

        Args:
            params: 请求参数

        Returns:
            签名字符串
        """
        sorted_params = sorted(params.items())
        sign_str = self.app_secret
        for k, v in sorted_params:
            sign_str += f"{k}{v}"
        sign_str += self.app_secret
        return hashlib.sha256(sign_str.encode("utf-8")).hexdigest().upper()

    # ==================== 通用请求 ====================

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送HTTP请求（带重试和token自动刷新）

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
                access_token = await self._get_access_token()
                request_data = data or {}

                timestamp = str(int(time.time()))
                auth_params = {
                    "app_key": self.app_key,
                    "access_token": access_token,
                    "timestamp": timestamp,
                    **request_data,
                }
                auth_params["sign"] = self._generate_sign(auth_params)

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                }

                if method.upper() == "GET":
                    response = await self.client.get(
                        endpoint, params=auth_params, headers=headers,
                    )
                elif method.upper() == "POST":
                    response = await self.client.post(
                        endpoint, json=auth_params, headers=headers,
                    )
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")

                response.raise_for_status()
                result = response.json()
                self._handle_error(result)
                return result

            except httpx.HTTPStatusError as e:
                logger.error(
                    "饿了么HTTP请求失败",
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                )
                # token 过期时清除缓存，下次循环会重新获取
                if e.response.status_code == 401:
                    self._access_token = None
                    self._token_expires_at = 0
                if attempt == self.retry_times - 1:
                    raise Exception(f"饿了么HTTP请求失败: {e.response.status_code}")

            except Exception as e:
                logger.error(
                    "饿了么请求异常",
                    endpoint=endpoint,
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise

        raise Exception("请求失败，已达到最大重试次数")

    def _handle_error(self, response: Dict[str, Any]) -> None:
        """
        处理业务错误

        Args:
            response: API响应数据

        Raises:
            Exception: 业务错误
        """
        code = response.get("code")
        if code is not None and code != "200" and code != 200 and code != "ok":
            message = response.get("message", response.get("msg", "未知错误"))
            raise Exception(f"饿了么API错误 [{code}]: {message}")

    # ==================== 订单管理接口 ====================

    async def query_orders(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        status: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        查询订单列表

        Args:
            start_time: 开始时间 (ISO8601)
            end_time: 结束时间 (ISO8601)
            status: 订单状态筛选
            page: 页码
            page_size: 每页数量

        Returns:
            订单列表及分页信息
        """
        data: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }
        if start_time:
            data["start_time"] = start_time
        if end_time:
            data["end_time"] = end_time
        if status is not None:
            data["status"] = status

        logger.info("饿了么查询订单列表", page=page, page_size=page_size)
        response = await self._request("GET", "/api/v1/orders", data=data)
        return response.get("data", {})

    async def get_order_detail(self, order_id: str) -> Dict[str, Any]:
        """
        获取订单详情

        Args:
            order_id: 饿了么订单ID

        Returns:
            订单详情
        """
        data = {"order_id": order_id}
        logger.info("饿了么查询订单详情", order_id=order_id)
        response = await self._request("GET", "/api/v1/order/detail", data=data)
        return response.get("data", {})

    async def confirm_order(self, order_id: str) -> Dict[str, Any]:
        """
        确认接单

        Args:
            order_id: 饿了么订单ID

        Returns:
            确认结果
        """
        data = {"order_id": order_id}
        logger.info("饿了么确认订单", order_id=order_id)
        response = await self._request("POST", "/api/v1/order/confirm", data=data)
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
            order_id: 饿了么订单ID
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
        logger.info("饿了么取消订单", order_id=order_id, reason=reason)
        response = await self._request("POST", "/api/v1/order/cancel", data=data)
        return response.get("data", {})

    async def query_refund(self, order_id: str) -> Dict[str, Any]:
        """
        查询退款信息

        Args:
            order_id: 饿了么订单ID

        Returns:
            退款详情
        """
        data = {"order_id": order_id}
        logger.info("饿了么查询退款", order_id=order_id)
        response = await self._request("GET", "/api/v1/order/refund", data=data)
        return response.get("data", {})

    # ==================== 商品管理接口 ====================

    async def query_foods(
        self,
        category_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        查询商品列表

        Args:
            category_id: 分类ID（可选筛选）
            page: 页码
            page_size: 每页数量

        Returns:
            商品列表
        """
        data: Dict[str, Any] = {"page": page, "page_size": page_size}
        if category_id:
            data["category_id"] = category_id

        logger.info("饿了么查询商品", page=page)
        response = await self._request("GET", "/api/v1/foods", data=data)
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
        data = {"food_id": food_id, "stock": stock}
        logger.info("饿了么更新库存", food_id=food_id, stock=stock)
        response = await self._request("POST", "/api/v1/food/stock", data=data)
        return response.get("data", {})

    async def sold_out_food(self, food_id: str) -> Dict[str, Any]:
        """
        商品售罄（下架）

        Args:
            food_id: 商品ID

        Returns:
            操作结果
        """
        data = {"food_id": food_id}
        logger.info("饿了么商品售罄", food_id=food_id)
        response = await self._request("POST", "/api/v1/food/soldout", data=data)
        return response.get("data", {})

    async def on_sale_food(self, food_id: str) -> Dict[str, Any]:
        """
        商品上架

        Args:
            food_id: 商品ID

        Returns:
            操作结果
        """
        data = {"food_id": food_id}
        logger.info("饿了么商品上架", food_id=food_id)
        response = await self._request("POST", "/api/v1/food/onsale", data=data)
        return response.get("data", {})

    # ==================== 门店管理接口 ====================

    async def get_shop_info(self, shop_id: Optional[str] = None) -> Dict[str, Any]:
        """
        查询门店信息

        Args:
            shop_id: 门店ID（可选，默认当前绑定门店）

        Returns:
            门店信息
        """
        data: Dict[str, Any] = {}
        if shop_id:
            data["shop_id"] = shop_id

        logger.info("饿了么查询门店信息", shop_id=shop_id)
        response = await self._request("GET", "/api/v1/shop/info", data=data)
        return response.get("data", {})

    async def update_shop_status(
        self,
        status: int,
        shop_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        更新门店营业状态

        Args:
            status: 营业状态 (1=营业中, 0=休息中)
            shop_id: 门店ID（可选）

        Returns:
            更新结果
        """
        data: Dict[str, Any] = {"status": status}
        if shop_id:
            data["shop_id"] = shop_id

        logger.info("饿了么更新门店状态", status=status, shop_id=shop_id)
        response = await self._request("POST", "/api/v1/shop/status", data=data)
        return response.get("data", {})

    # ==================== 配送管理接口 ====================

    async def query_delivery_status(self, order_id: str) -> Dict[str, Any]:
        """
        查询配送状态

        Args:
            order_id: 订单ID

        Returns:
            配送信息（骑手位置、状态、预计到达时间等）
        """
        data = {"order_id": order_id}
        logger.info("饿了么查询配送状态", order_id=order_id)
        response = await self._request("GET", "/api/v1/delivery/status", data=data)
        return response.get("data", {})

    # ==================== 标准化数据总线接口 ====================

    def to_order(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将饿了么原始订单字段映射到标准 OrderSchema

        饿了么订单字段参考：
          order_id, eleme_order_id, create_time, status, total_price,
          food_list (food_id, food_name, quantity, price),
          shop_id, user_id
        """
        import sys
        import os as _os
        _src_dir = _os.path.dirname(__file__)
        _repo_root = _os.path.abspath(_os.path.join(_src_dir, "../../../.."))
        _gateway_src = _os.path.join(_repo_root, "apps", "api-gateway", "src")
        if _gateway_src not in sys.path:
            sys.path.insert(0, _gateway_src)

        from schemas.restaurant_standard_schema import (
            OrderSchema, OrderStatus, OrderType, OrderItemSchema, DishCategory
        )

        # 饿了么订单状态映射
        # 0=待付款, 1=待接单, 2=已接单, 3=配送中, 4=已完成, 5=已取消, 9=退款中
        _STATUS_MAP = {
            0: OrderStatus.PENDING,
            1: OrderStatus.PENDING,
            2: OrderStatus.CONFIRMED,
            3: OrderStatus.CONFIRMED,
            4: OrderStatus.COMPLETED,
            5: OrderStatus.CANCELLED,
            9: OrderStatus.CANCELLED,
        }
        order_status = _STATUS_MAP.get(
            int(raw.get("status", 1)), OrderStatus.PENDING
        )

        # 订单项映射
        items = []
        food_list = raw.get("food_list", raw.get("items", []))
        for idx, item in enumerate(food_list, start=1):
            unit_price = Decimal(str(item.get("price", 0))) / 100  # 分 -> 元
            qty = int(item.get("quantity", item.get("count", 1)))
            items.append(OrderItemSchema(
                item_id=str(item.get("item_id", f"{raw.get('order_id', '')}_{idx}")),
                dish_id=str(item.get("food_id", item.get("sku_id", ""))),
                dish_name=str(item.get("food_name", item.get("name", ""))),
                dish_category=DishCategory.MAIN_COURSE,
                quantity=qty,
                unit_price=unit_price,
                subtotal=unit_price * qty,
                special_requirements=item.get("remark"),
            ))

        total = Decimal(str(raw.get("total_price", raw.get("order_amount", 0)))) / 100
        discount = Decimal(str(raw.get("discount_price", raw.get("shop_discount", 0)))) / 100
        subtotal = total + discount

        create_time_raw = raw.get("create_time", raw.get("created_at", ""))
        try:
            if isinstance(create_time_raw, (int, float)) and create_time_raw > 1e9:
                created_at = datetime.fromtimestamp(create_time_raw)
            else:
                created_at = datetime.fromisoformat(
                    str(create_time_raw).replace("T", " ")
                )
        except (ValueError, TypeError, OSError):
            created_at = datetime.utcnow()

        return OrderSchema(
            order_id=str(raw.get("order_id", raw.get("eleme_order_id", ""))),
            order_number=str(raw.get("day_seq", raw.get("order_id", ""))),
            order_type=OrderType.TAKEOUT,
            order_status=order_status,
            store_id=store_id,
            brand_id=brand_id,
            table_number=None,
            customer_id=str(raw.get("user_id", "")) or None,
            items=items,
            subtotal=subtotal,
            discount=discount,
            service_charge=Decimal("0"),
            total=total,
            created_at=created_at,
            waiter_id=None,
            notes=raw.get("remark", raw.get("caution")),
        )

    async def close(self):
        """关闭适配器，释放资源"""
        logger.info("关闭饿了么适配器")
        await self.client.aclose()
