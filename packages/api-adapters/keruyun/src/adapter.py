"""
客如云餐饮管理系统API适配器
提供订单管理、菜品管理、会员管理、报表等功能
"""
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional, List
import structlog
import httpx
import hashlib

logger = structlog.get_logger()


class KeruyunAdapter:
    """客如云餐饮管理系统适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - base_url: API基础URL
                - client_id: 客户端ID
                - client_secret: 客户端密钥
                - store_id: 门店ID
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.config = config
        self.base_url = config.get("base_url", "https://api.keruyun.com")
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        self.store_id = config.get("store_id")
        self.timeout = config.get("timeout", 30)
        self.retry_times = config.get("retry_times", 3)

        if not self.client_id or not self.client_secret:
            raise ValueError("client_id和client_secret不能为空")

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        logger.info("客如云适配器初始化", base_url=self.base_url, store_id=self.store_id)

    def _generate_sign(self, params: Dict[str, Any], timestamp: str) -> str:
        """
        生成API签名（客如云签名算法）

        按 client_id + sorted_params + timestamp + client_secret 拼接后 MD5
        """
        sorted_params = sorted(params.items())
        sign_str = self.client_id
        for k, v in sorted_params:
            sign_str += f"{k}={v}"
        sign_str += timestamp + self.client_secret
        return hashlib.md5(sign_str.encode()).hexdigest().upper()

    def authenticate(self) -> Dict[str, str]:
        """返回包含认证信息的请求头"""
        timestamp = str(int(datetime.now().timestamp()))
        return {
            "Content-Type": "application/json",
            "X-Client-Id": self.client_id,
            "X-Timestamp": timestamp,
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发送HTTP请求（含重试）"""
        for attempt in range(self.retry_times):
            try:
                timestamp = str(int(datetime.now().timestamp()))
                request_data = data or {}
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
                logger.error("HTTP请求失败", endpoint=endpoint,
                             status_code=e.response.status_code, attempt=attempt + 1)
                if attempt == self.retry_times - 1:
                    raise Exception(f"HTTP请求失败: {e.response.status_code}")

            except Exception as e:
                logger.error("请求异常", endpoint=endpoint, error=str(e), attempt=attempt + 1)
                if attempt == self.retry_times - 1:
                    raise

        raise Exception("请求失败，已达到最大重试次数")

    def handle_error(self, response: Dict[str, Any]) -> None:
        """处理业务错误"""
        code = response.get("code", 0)
        if code != 0 and code != 200 and code != "success":
            message = response.get("message", "未知错误")
            raise Exception(f"客如云API错误 [{code}]: {message}")

    # ==================== 订单管理接口 ====================

    async def query_order(
        self,
        order_id: Optional[str] = None,
        order_sn: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询订单"""
        data: Dict[str, Any] = {"store_id": self.store_id}
        if order_id:
            data["order_id"] = order_id
        if order_sn:
            data["order_sn"] = order_sn
        if start_time:
            data["start_time"] = start_time
        if end_time:
            data["end_time"] = end_time

        logger.info("查询订单", data=data)
        response = await self._request("POST", "/api/v2/order/query", data=data)
        return response.get("data", {})

    async def update_order_status(
        self,
        order_id: str,
        status: int,
    ) -> Dict[str, Any]:
        """更新订单状态"""
        data = {"store_id": self.store_id, "order_id": order_id, "status": status}
        logger.info("更新订单状态", order_id=order_id, status=status)
        response = await self._request("POST", "/api/v2/order/update_status", data=data)
        return response.get("data", {})

    # ==================== 菜品管理接口 ====================

    async def query_dish(
        self,
        sku_id: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询菜品"""
        data: Dict[str, Any] = {"store_id": self.store_id}
        if sku_id:
            data["sku_id"] = sku_id
        if category_id:
            data["category_id"] = category_id

        logger.info("查询菜品", data=data)
        response = await self._request("POST", "/api/v2/dish/query", data=data)
        return response.get("data", [])

    async def update_dish_status(self, sku_id: str, is_sold_out: int) -> Dict[str, Any]:
        """更新菜品售罄状态（1=售罄, 0=正常）"""
        data = {"store_id": self.store_id, "sku_id": sku_id, "is_sold_out": is_sold_out}
        logger.info("更新菜品状态", sku_id=sku_id, is_sold_out=is_sold_out)
        response = await self._request("POST", "/api/v2/dish/update_status", data=data)
        return response.get("data", {})

    # ==================== 会员管理接口 ====================

    async def query_member(
        self,
        member_id: Optional[str] = None,
        mobile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询会员"""
        if not any([member_id, mobile]):
            raise ValueError("至少需要提供 member_id 或 mobile")

        data: Dict[str, Any] = {"store_id": self.store_id}
        if member_id:
            data["member_id"] = member_id
        if mobile:
            data["mobile"] = mobile

        logger.info("查询会员", data=data)
        response = await self._request("POST", "/api/v2/member/query", data=data)
        return response.get("data", {})

    # ==================== 报表接口 ====================

    async def query_revenue_report(
        self,
        date: str,
    ) -> Dict[str, Any]:
        """查询日营收报表"""
        data = {"store_id": self.store_id, "date": date}
        logger.info("查询营收报表", date=date)
        response = await self._request("POST", "/api/v2/report/revenue", data=data)
        return response.get("data", {})

    async def close(self):
        """关闭适配器，释放资源"""
        logger.info("关闭客如云适配器")
        await self.client.aclose()

    # ==================== 标准化数据总线接口 ====================

    def to_order(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将客如云原始订单字段映射到标准 OrderSchema

        客如云订单字段参考：
          order_id, order_sn, store_id, table_id, table_name,
          status (1=待确认, 2=服务中, 3=已结账, 4=已取消),
          total_amount, discount_amount (单位：分),
          create_time (ISO datetime), member_id, waiter_id, note,
          items (list): item_id, sku_id, sku_name, qty, unit_price
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

        # 状态映射（客如云：1=待确认, 2=服务中, 3=已结账, 4=已取消）
        _STATUS_MAP = {
            1: OrderStatus.PENDING,
            2: OrderStatus.CONFIRMED,
            3: OrderStatus.COMPLETED,
            4: OrderStatus.CANCELLED,
        }
        order_status = _STATUS_MAP.get(int(raw.get("status", 1)), OrderStatus.PENDING)

        # 订单项映射
        items = []
        for idx, item in enumerate(raw.get("items", []), start=1):
            unit_price = Decimal(str(item.get("unit_price", 0))) / 100  # 分 → 元
            qty = int(item.get("qty", item.get("quantity", 1)))
            items.append(OrderItemSchema(
                item_id=str(item.get("item_id", f"{raw.get('order_id', '')}_{idx}")),
                dish_id=str(item.get("sku_id", "")),
                dish_name=str(item.get("sku_name", "")),
                dish_category=DishCategory.MAIN_COURSE,
                quantity=qty,
                unit_price=unit_price,
                subtotal=unit_price * qty,
                special_requirements=item.get("note"),
            ))

        total = Decimal(str(raw.get("total_amount", 0))) / 100
        discount = Decimal(str(raw.get("discount_amount", 0))) / 100
        subtotal = total + discount

        create_time_raw = raw.get("create_time", "")
        try:
            if isinstance(create_time_raw, (int, float)) and create_time_raw > 1e9:
                created_at = datetime.fromtimestamp(create_time_raw)
            else:
                created_at = datetime.fromisoformat(str(create_time_raw).replace("T", " "))
        except (ValueError, TypeError, OSError):
            created_at = datetime.utcnow()

        return OrderSchema(
            order_id=str(raw.get("order_id", "")),
            order_number=str(raw.get("order_sn", raw.get("order_id", ""))),
            order_type=OrderType.DINE_IN,
            order_status=order_status,
            store_id=store_id,
            brand_id=brand_id,
            table_number=raw.get("table_name", raw.get("table_id")),
            customer_id=raw.get("member_id"),
            items=items,
            subtotal=subtotal,
            discount=discount,
            service_charge=Decimal("0"),
            total=total,
            created_at=created_at,
            waiter_id=raw.get("waiter_id"),
            notes=raw.get("note"),
        )

    def to_staff_action(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将客如云原始操作数据映射为标准 StaffAction

        原始字段参考（POS 操作日志）：
          action_type, staff_id, amount, reason, approved_by, operate_time
        """
        import sys
        import os as _os
        _src_dir = _os.path.dirname(__file__)
        _repo_root = _os.path.abspath(_os.path.join(_src_dir, "../../../.."))
        _gateway_src = _os.path.join(_repo_root, "apps", "api-gateway", "src")
        if _gateway_src not in sys.path:
            sys.path.insert(0, _gateway_src)

        from schemas.restaurant_standard_schema import StaffAction

        action_time_raw = raw.get("operate_time", raw.get("create_time", ""))
        try:
            if isinstance(action_time_raw, (int, float)) and action_time_raw > 1e9:
                created_at = datetime.fromtimestamp(action_time_raw)
            else:
                created_at = datetime.fromisoformat(str(action_time_raw).replace("T", " "))
        except (ValueError, TypeError, OSError):
            created_at = datetime.utcnow()

        amount_raw = raw.get("amount")
        amount = Decimal(str(amount_raw)) / 100 if amount_raw is not None else None

        return StaffAction(
            action_type=str(raw.get("action_type", raw.get("type", "unknown"))),
            brand_id=brand_id,
            store_id=store_id,
            operator_id=str(raw.get("staff_id", raw.get("operator_id", ""))),
            amount=amount,
            reason=raw.get("reason"),
            approved_by=raw.get("approved_by"),
            created_at=created_at,
        )
