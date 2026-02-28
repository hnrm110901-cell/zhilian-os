"""
天财商龙餐饮管理系统API适配器
提供订单管理、菜品管理、会员管理、库存管理等功能
"""
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime
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
