"""
天财商龙餐饮管理系统API适配器
提供订单管理、菜品管理、会员管理、库存管理等功能
"""
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional, List
import structlog
import httpx
import hashlib
import json

logger = structlog.get_logger()


class TiancaiShanglongAdapter:
    """天财商龙餐饮管理系统适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - base_url: API基础URL
                - app_id: 应用ID
                - app_secret: 应用密钥
                - store_id: 门店ID
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.config = config
        self.base_url = config.get("base_url", "https://api.tiancai.com")
        self.app_id = config.get("app_id")
        self.app_secret = config.get("app_secret")
        self.store_id = config.get("store_id")
        self.timeout = config.get("timeout", 30)
        self.retry_times = config.get("retry_times", 3)

        if not self.app_id or not self.app_secret:
            raise ValueError("app_id和app_secret不能为空")

        # 初始化HTTP客户端
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        logger.info("天财商龙适配器初始化", base_url=self.base_url, store_id=self.store_id)

    def _generate_sign(self, params: Dict[str, Any], timestamp: str) -> str:
        """
        生成API签名

        Args:
            params: 请求参数
            timestamp: 时间戳

        Returns:
            签名字符串
        """
        # 按key排序
        sorted_params = sorted(params.items())
        # 拼接字符串
        sign_str = f"app_id={self.app_id}&"
        sign_str += "&".join([f"{k}={v}" for k, v in sorted_params])
        sign_str += f"&timestamp={timestamp}&app_secret={self.app_secret}"
        # MD5加密
        return hashlib.md5(sign_str.encode()).hexdigest().upper()

    def authenticate(self) -> Dict[str, str]:
        """
        认证方法，返回认证头部

        Returns:
            认证头部字典
        """
        timestamp = str(int(datetime.now().timestamp()))
        return {
            "Content-Type": "application/json",
            "X-App-Id": self.app_id,
            "X-Timestamp": timestamp,
        }

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
                timestamp = str(int(datetime.now().timestamp()))
                request_data = data or {}

                # 生成签名
                sign = self._generate_sign(request_data, timestamp)

                headers = self.authenticate()
                headers["X-Sign"] = sign

                if method.upper() == "GET":
                    response = await self.client.get(endpoint, params=request_data, headers=headers)
                elif method.upper() == "POST":
                    response = await self.client.post(endpoint, json=request_data, headers=headers)
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
        code = response.get("code", 0)
        if code != 0 and code != 200:
            message = response.get("message", "未知错误")
            raise Exception(f"天财商龙API错误 [{code}]: {message}")

    # ==================== 订单管理接口 ====================

    async def query_order(
        self,
        order_id: Optional[str] = None,
        order_no: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询订单

        Args:
            order_id: 订单ID
            order_no: 订单号
            start_time: 开始时间 (YYYY-MM-DD HH:mm:ss)
            end_time: 结束时间 (YYYY-MM-DD HH:mm:ss)

        Returns:
            订单信息
        """
        data = {"store_id": self.store_id}
        if order_id:
            data["order_id"] = order_id
        if order_no:
            data["order_no"] = order_no
        if start_time:
            data["start_time"] = start_time
        if end_time:
            data["end_time"] = end_time

        logger.info("查询订单", data=data)

        response = await self._request("POST", "/api/order/query", data=data)
        return response.get("data", {})

    async def create_order(
        self,
        table_no: str,
        dishes: List[Dict[str, Any]],
        member_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建订单

        Args:
            table_no: 桌号
            dishes: 菜品列表 [{"dish_id": "D001", "quantity": 2, "price": 4800}]
            member_id: 会员ID

        Returns:
            订单信息
        """
        data = {
            "store_id": self.store_id,
            "table_no": table_no,
            "dishes": dishes,
        }
        if member_id:
            data["member_id"] = member_id

        logger.info("创建订单", table_no=table_no, dishes_count=len(dishes))

        response = await self._request("POST", "/api/order/create", data=data)
        return response.get("data", {})

    async def update_order_status(
        self,
        order_id: str,
        status: int,
        pay_type: Optional[int] = None,
        pay_amount: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        更新订单状态

        Args:
            order_id: 订单ID
            status: 订单状态 (1-待支付 2-已支付 3-已取消)
            pay_type: 支付方式 (1-现金 2-微信 3-支付宝 4-会员卡)
            pay_amount: 支付金额（分）

        Returns:
            更新结果
        """
        data = {
            "store_id": self.store_id,
            "order_id": order_id,
            "status": status,
        }
        if pay_type:
            data["pay_type"] = pay_type
        if pay_amount:
            data["pay_amount"] = pay_amount

        logger.info("更新订单状态", order_id=order_id, status=status)

        response = await self._request("POST", "/api/order/update_status", data=data)
        return response.get("data", {})

    # ==================== 菜品管理接口 ====================

    async def query_dish(
        self,
        dish_id: Optional[str] = None,
        category_id: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询菜品

        Args:
            dish_id: 菜品ID
            category_id: 分类ID
            keyword: 关键词

        Returns:
            菜品列表
        """
        data = {"store_id": self.store_id}
        if dish_id:
            data["dish_id"] = dish_id
        if category_id:
            data["category_id"] = category_id
        if keyword:
            data["keyword"] = keyword

        logger.info("查询菜品", data=data)

        response = await self._request("POST", "/api/dish/query", data=data)
        return response.get("data", [])

    async def update_dish_status(
        self,
        dish_id: str,
        status: int,
    ) -> Dict[str, Any]:
        """
        更新菜品状态

        Args:
            dish_id: 菜品ID
            status: 状态 (1-在售 0-停售)

        Returns:
            更新结果
        """
        data = {
            "store_id": self.store_id,
            "dish_id": dish_id,
            "status": status,
        }

        logger.info("更新菜品状态", dish_id=dish_id, status=status)

        response = await self._request("POST", "/api/dish/update_status", data=data)
        return response.get("data", {})

    # ==================== 会员管理接口 ====================

    async def query_member(
        self,
        member_id: Optional[str] = None,
        mobile: Optional[str] = None,
        card_no: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询会员

        Args:
            member_id: 会员ID
            mobile: 手机号
            card_no: 会员卡号

        Returns:
            会员信息
        """
        if not any([member_id, mobile, card_no]):
            raise ValueError("至少需要提供一个查询条件")

        data = {"store_id": self.store_id}
        if member_id:
            data["member_id"] = member_id
        if mobile:
            data["mobile"] = mobile
        if card_no:
            data["card_no"] = card_no

        logger.info("查询会员", data=data)

        response = await self._request("POST", "/api/member/query", data=data)
        return response.get("data", {})

    async def add_member(
        self,
        mobile: str,
        name: str,
        card_no: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        新增会员

        Args:
            mobile: 手机号
            name: 姓名
            card_no: 会员卡号

        Returns:
            会员信息
        """
        data = {
            "store_id": self.store_id,
            "mobile": mobile,
            "name": name,
        }
        if card_no:
            data["card_no"] = card_no

        logger.info("新增会员", mobile=mobile, name=name)

        response = await self._request("POST", "/api/member/add", data=data)
        return response.get("data", {})

    async def member_recharge(
        self,
        member_id: str,
        amount: int,
        pay_type: int,
    ) -> Dict[str, Any]:
        """
        会员充值

        Args:
            member_id: 会员ID
            amount: 充值金额（分）
            pay_type: 支付方式

        Returns:
            充值结果
        """
        data = {
            "store_id": self.store_id,
            "member_id": member_id,
            "amount": amount,
            "pay_type": pay_type,
        }

        logger.info("会员充值", member_id=member_id, amount=amount)

        response = await self._request("POST", "/api/member/recharge", data=data)
        return response.get("data", {})

    # ==================== 库存管理接口 ====================

    async def query_inventory(
        self,
        material_id: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询库存

        Args:
            material_id: 原料ID
            keyword: 关键词

        Returns:
            库存列表
        """
        data = {"store_id": self.store_id}
        if material_id:
            data["material_id"] = material_id
        if keyword:
            data["keyword"] = keyword

        logger.info("查询库存", data=data)

        response = await self._request("POST", "/api/inventory/query", data=data)
        return response.get("data", [])

    async def update_inventory(
        self,
        material_id: str,
        quantity: float,
        operation_type: int,
    ) -> Dict[str, Any]:
        """
        更新库存

        Args:
            material_id: 原料ID
            quantity: 数量
            operation_type: 操作类型 (1-入库 2-出库 3-盘点)

        Returns:
            更新结果
        """
        data = {
            "store_id": self.store_id,
            "material_id": material_id,
            "quantity": quantity,
            "operation_type": operation_type,
        }

        logger.info("更新库存", material_id=material_id, quantity=quantity)

        response = await self._request("POST", "/api/inventory/update", data=data)
        return response.get("data", {})

    async def close(self):
        """关闭适配器，释放资源"""
        logger.info("关闭天财商龙适配器")
        await self.client.aclose()

    # ==================== 标准化数据总线接口 ====================

    def to_order(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将天财商龙原始订单字段映射到标准 OrderSchema

        天财商龙订单字段参考：
          order_id, order_no, store_id, table_no, status, pay_amount,
          dishes (dish_id, dish_name, quantity, price),
          member_id, create_time, remark
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

        # 状态映射（天财商龙：1=待支付, 2=已支付, 3=已取消）
        _STATUS_MAP = {
            1: OrderStatus.PENDING,
            2: OrderStatus.COMPLETED,
            3: OrderStatus.CANCELLED,
        }
        order_status = _STATUS_MAP.get(int(raw.get("status", 1)), OrderStatus.PENDING)

        # 订单项映射
        items = []
        for idx, item in enumerate(raw.get("dishes", raw.get("items", [])), start=1):
            unit_price = Decimal(str(item.get("price", 0))) / 100  # 分 → 元
            qty = int(item.get("quantity", item.get("qty", 1)))
            items.append(OrderItemSchema(
                item_id=str(item.get("item_id", f"{raw.get('order_id', '')}_{idx}")),
                dish_id=str(item.get("dish_id", item.get("good_id", ""))),
                dish_name=str(item.get("dish_name", item.get("good_name", ""))),
                dish_category=DishCategory.MAIN_COURSE,
                quantity=qty,
                unit_price=unit_price,
                subtotal=unit_price * qty,
                special_requirements=item.get("remark"),
            ))

        total = Decimal(str(raw.get("pay_amount", raw.get("total_amount", 0)))) / 100
        discount = Decimal(str(raw.get("discount_amount", 0))) / 100
        subtotal = total + discount

        create_time_raw = raw.get("create_time", raw.get("order_time", ""))
        try:
            if isinstance(create_time_raw, (int, float)) and create_time_raw > 1e9:
                created_at = datetime.fromtimestamp(create_time_raw)
            else:
                created_at = datetime.fromisoformat(str(create_time_raw).replace("T", " "))
        except (ValueError, TypeError, OSError):
            created_at = datetime.utcnow()

        return OrderSchema(
            order_id=str(raw.get("order_id", "")),
            order_number=str(raw.get("order_no", raw.get("order_id", ""))),
            order_type=OrderType.DINE_IN,
            order_status=order_status,
            store_id=store_id,
            brand_id=brand_id,
            table_number=raw.get("table_no"),
            customer_id=raw.get("member_id"),
            items=items,
            subtotal=subtotal,
            discount=discount,
            service_charge=Decimal("0"),
            total=total,
            created_at=created_at,
            waiter_id=raw.get("waiter_id", raw.get("operator_id")),
            notes=raw.get("remark"),
        )

    def to_staff_action(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将天财商龙原始操作数据映射为标准 StaffAction

        原始字段参考（POS 操作日志）：
          action_type, operator_id, amount, reason, approved_by, create_time
        """
        import sys
        import os as _os
        _src_dir = _os.path.dirname(__file__)
        _repo_root = _os.path.abspath(_os.path.join(_src_dir, "../../../.."))
        _gateway_src = _os.path.join(_repo_root, "apps", "api-gateway", "src")
        if _gateway_src not in sys.path:
            sys.path.insert(0, _gateway_src)

        from schemas.restaurant_standard_schema import StaffAction

        action_time_raw = raw.get("action_time", raw.get("create_time", ""))
        try:
            if isinstance(action_time_raw, (int, float)) and action_time_raw > 1e9:
                created_at = datetime.fromtimestamp(action_time_raw)
            else:
                created_at = datetime.fromisoformat(str(action_time_raw).replace("T", " "))
        except (ValueError, TypeError, OSError):
            created_at = datetime.utcnow()

        amount_raw = raw.get("amount", raw.get("pay_amount"))
        amount = Decimal(str(amount_raw)) / 100 if amount_raw is not None else None

        return StaffAction(
            action_type=str(raw.get("action_type", raw.get("type", "unknown"))),
            brand_id=brand_id,
            store_id=store_id,
            operator_id=str(raw.get("operator_id", raw.get("staff_id", ""))),
            amount=amount,
            reason=raw.get("reason"),
            approved_by=raw.get("approved_by"),
            created_at=created_at,
        )
