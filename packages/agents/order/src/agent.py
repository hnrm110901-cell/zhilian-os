"""
订单协同Agent
处理预定、排位、等位、点单、结账全流程
"""
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime, timedelta
from enum import Enum
import structlog
import uuid
import sys
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent / "apps" / "api-gateway" / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()


class OrderStatus(Enum):
    """订单状态"""

    RESERVED = "reserved"  # 已预定
    WAITING = "waiting"  # 等位中
    SEATED = "seated"  # 已入座
    ORDERING = "ordering"  # 点餐中
    ORDERED = "ordered"  # 已下单
    COOKING = "cooking"  # 制作中
    SERVED = "served"  # 已上菜
    PAYING = "paying"  # 结账中
    PAID = "paid"  # 已支付
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class ReservationType(Enum):
    """预定类型"""

    ONLINE = "online"  # 线上预定
    PHONE = "phone"  # 电话预定
    WALKIN = "walkin"  # 现场预定


class PaymentMethod(Enum):
    """支付方式"""

    CASH = "cash"  # 现金
    WECHAT = "wechat"  # 微信支付
    ALIPAY = "alipay"  # 支付宝
    CARD = "card"  # 银行卡
    MEMBER = "member"  # 会员储值


class OrderState(TypedDict):
    """订单状态"""

    order_id: str
    store_id: str
    customer_info: Dict[str, Any]
    reservation: Optional[Dict[str, Any]]
    queue_info: Optional[Dict[str, Any]]
    table_info: Optional[Dict[str, Any]]
    dishes: List[Dict[str, Any]]
    total_amount: float
    discount_amount: float
    final_amount: float
    payment_info: Optional[Dict[str, Any]]
    status: str
    created_at: str
    updated_at: str


class OrderAgent(BaseAgent):
    """订单协同Agent"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化订单Agent

        Args:
            config: 配置字典
        """
        super().__init__()
        self.config = config
        self.average_wait_time = config.get("average_wait_time", 30)  # 平均等位时间（分钟）
        self.average_dining_time = config.get("average_dining_time", 90)  # 平均用餐时间（分钟）

        logger.info("订单协同Agent初始化", config=config)

    def get_supported_actions(self) -> List[str]:
        """获取支持的操作列表"""
        return [
            "create_reservation", "join_queue", "get_queue_status",
            "create_order", "add_dish", "recommend_dishes",
            "calculate_bill", "process_payment", "get_order",
            "update_order_status", "cancel_order"
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """
        执行Agent操作

        Args:
            action: 操作名称
            params: 操作参数

        Returns:
            AgentResponse: 统一的响应格式
        """
        try:
            if action == "create_reservation":
                result = await self.create_reservation(**params)
            elif action == "join_queue":
                result = await self.join_queue(**params)
            elif action == "get_queue_status":
                result = await self.get_queue_status(**params)
            elif action == "create_order":
                result = await self.create_order(**params)
            elif action == "add_dish":
                result = await self.add_dish(**params)
            elif action == "recommend_dishes":
                result = await self.recommend_dishes(**params)
            elif action == "calculate_bill":
                result = await self.calculate_bill(**params)
            elif action == "process_payment":
                result = await self.process_payment(**params)
            elif action == "get_order":
                result = await self.get_order(**params)
            elif action == "update_order_status":
                result = await self.update_order_status(**params)
            elif action == "cancel_order":
                result = await self.cancel_order(**params)
            else:
                return AgentResponse(
                    success=False,
                    data=None,
                    error=f"Unsupported action: {action}"
                )

            return AgentResponse(
                success=result.get("success", True),
                data=result,
                error=result.get("error") if not result.get("success", True) else None
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                error=str(e)
            )

    # ==================== 预定管理 ====================

    async def create_reservation(
        self,
        store_id: str,
        customer_name: str,
        customer_mobile: str,
        party_size: int,
        reservation_time: str,
        special_requests: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建预定

        Args:
            store_id: 门店ID
            customer_name: 客户姓名
            customer_mobile: 客户手机号
            party_size: 用餐人数
            reservation_time: 预定时间 (YYYY-MM-DD HH:mm)
            special_requests: 特殊需求

        Returns:
            预定结果
        """
        logger.info(
            "创建预定",
            store_id=store_id,
            customer=customer_name,
            party_size=party_size,
            time=reservation_time,
        )

        # 生成预定ID
        reservation_id = f"RSV{uuid.uuid4().hex[:12].upper()}"

        # 检查时间可用性
        is_available = await self._check_time_availability(
            store_id, reservation_time, party_size
        )

        if not is_available:
            return {
                "success": False,
                "message": "该时间段已满，请选择其他时间",
                "alternative_times": await self._suggest_alternative_times(
                    store_id, reservation_time, party_size
                ),
            }

        # 创建预定记录
        reservation = {
            "reservation_id": reservation_id,
            "store_id": store_id,
            "customer_name": customer_name,
            "customer_mobile": customer_mobile,
            "party_size": party_size,
            "reservation_time": reservation_time,
            "special_requests": special_requests,
            "status": "confirmed",
            "created_at": datetime.now().isoformat(),
        }

        logger.info("预定创建成功", reservation_id=reservation_id)

        return {
            "success": True,
            "reservation": reservation,
            "message": "预定成功",
        }

    async def _check_time_availability(
        self, store_id: str, time: str, party_size: int
    ) -> bool:
        """检查时间可用性"""
        # TODO: 查询数据库检查该时间段的预定情况
        # TODO: 考虑桌台容量和已有预定
        return True  # 临时返回可用

    async def _suggest_alternative_times(
        self, store_id: str, requested_time: str, party_size: int
    ) -> List[str]:
        """建议替代时间"""
        # TODO: 基于当前预定情况推荐可用时间
        base_time = datetime.fromisoformat(requested_time)
        alternatives = [
            (base_time + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M")
            for i in [1, 2, -1]
        ]
        return alternatives

    # ==================== 排位/等位管理 ====================

    async def join_queue(
        self,
        store_id: str,
        customer_name: str,
        customer_mobile: str,
        party_size: int,
    ) -> Dict[str, Any]:
        """
        加入排队

        Args:
            store_id: 门店ID
            customer_name: 客户姓名
            customer_mobile: 客户手机号
            party_size: 用餐人数

        Returns:
            排队结果
        """
        logger.info(
            "加入排队",
            store_id=store_id,
            customer=customer_name,
            party_size=party_size,
        )

        # 生成排队号
        queue_number = await self._generate_queue_number(store_id)

        # 预估等待时间
        estimated_wait = await self._estimate_wait_time(store_id, party_size)

        queue_info = {
            "queue_id": f"Q{uuid.uuid4().hex[:12].upper()}",
            "queue_number": queue_number,
            "store_id": store_id,
            "customer_name": customer_name,
            "customer_mobile": customer_mobile,
            "party_size": party_size,
            "estimated_wait_minutes": estimated_wait,
            "status": "waiting",
            "joined_at": datetime.now().isoformat(),
        }

        logger.info(
            "排队成功",
            queue_number=queue_number,
            estimated_wait=estimated_wait,
        )

        return {
            "success": True,
            "queue_info": queue_info,
            "message": f"您的排队号是{queue_number}，预计等待{estimated_wait}分钟",
        }

    async def _generate_queue_number(self, store_id: str) -> str:
        """生成排队号"""
        # TODO: 从数据库获取当前最大排队号并递增
        # 临时生成格式：A001, A002, ...
        return f"A{datetime.now().strftime('%H%M%S')[-3:]}"

    async def _estimate_wait_time(self, store_id: str, party_size: int) -> int:
        """预估等待时间"""
        # TODO: 基于当前排队人数、桌台周转率等计算
        # 简化算法：基础等待时间 + 人数因子
        base_wait = self.average_wait_time
        party_factor = (party_size - 2) * 5 if party_size > 2 else 0
        return base_wait + party_factor

    async def get_queue_status(self, queue_id: str) -> Dict[str, Any]:
        """
        查询排队状态

        Args:
            queue_id: 排队ID

        Returns:
            排队状态
        """
        logger.info("查询排队状态", queue_id=queue_id)

        # TODO: 从数据库查询排队信息
        return {
            "success": True,
            "queue_id": queue_id,
            "status": "waiting",
            "ahead_count": 5,  # 前面还有5桌
            "estimated_wait_minutes": 25,
        }

    # ==================== 点单管理 ====================

    async def create_order(
        self,
        store_id: str,
        table_id: str,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建订单

        Args:
            store_id: 门店ID
            table_id: 桌台ID
            customer_id: 客户ID（可选）

        Returns:
            订单信息
        """
        logger.info("创建订单", store_id=store_id, table_id=table_id)

        order_id = f"ORD{uuid.uuid4().hex[:12].upper()}"

        order = {
            "order_id": order_id,
            "store_id": store_id,
            "table_id": table_id,
            "customer_id": customer_id,
            "dishes": [],
            "total_amount": 0,
            "status": OrderStatus.ORDERING.value,
            "created_at": datetime.now().isoformat(),
        }

        logger.info("订单创建成功", order_id=order_id)

        return {"success": True, "order": order}

    async def add_dish(
        self,
        order_id: str,
        dish_id: str,
        dish_name: str,
        price: float,
        quantity: int = 1,
        special_instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        添加菜品

        Args:
            order_id: 订单ID
            dish_id: 菜品ID
            dish_name: 菜品名称
            price: 价格
            quantity: 数量
            special_instructions: 特殊要求

        Returns:
            添加结果
        """
        logger.info(
            "添加菜品",
            order_id=order_id,
            dish_name=dish_name,
            quantity=quantity,
        )

        dish_item = {
            "dish_id": dish_id,
            "dish_name": dish_name,
            "price": price,
            "quantity": quantity,
            "special_instructions": special_instructions,
            "subtotal": price * quantity,
        }

        # TODO: 更新订单数据库

        return {
            "success": True,
            "message": f"已添加{quantity}份{dish_name}",
            "dish_item": dish_item,
        }

    async def recommend_dishes(
        self,
        store_id: str,
        customer_id: Optional[str] = None,
        party_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        推荐菜品

        Args:
            store_id: 门店ID
            customer_id: 客户ID
            party_size: 用餐人数

        Returns:
            推荐菜品列表
        """
        logger.info(
            "推荐菜品",
            store_id=store_id,
            customer_id=customer_id,
            party_size=party_size,
        )

        # TODO: 基于历史订单、热门菜品、个人偏好推荐
        # TODO: 考虑用餐人数、时段、季节等因素

        recommendations = [
            {
                "dish_id": "D001",
                "dish_name": "宫保鸡丁",
                "price": 48.0,
                "reason": "本店招牌菜，好评率95%",
                "popularity_rank": 1,
            },
            {
                "dish_id": "D002",
                "dish_name": "麻婆豆腐",
                "price": 32.0,
                "reason": "您上次点过并给了好评",
                "popularity_rank": 3,
            },
        ]

        return {
            "success": True,
            "recommendations": recommendations,
            "message": f"为您推荐{len(recommendations)}道菜品",
        }

    # ==================== 结账管理 ====================

    async def calculate_bill(
        self,
        order_id: str,
        member_id: Optional[str] = None,
        coupon_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        计算账单

        Args:
            order_id: 订单ID
            member_id: 会员ID
            coupon_codes: 优惠券码列表

        Returns:
            账单详情
        """
        logger.info(
            "计算账单",
            order_id=order_id,
            member_id=member_id,
            coupons=coupon_codes,
        )

        # TODO: 从数据库获取订单详情
        # TODO: 计算会员折扣
        # TODO: 应用优惠券
        # TODO: 计算积分抵扣

        # 临时模拟数据
        total_amount = 200.0
        member_discount = 20.0 if member_id else 0
        coupon_discount = 10.0 if coupon_codes else 0
        final_amount = total_amount - member_discount - coupon_discount

        bill = {
            "order_id": order_id,
            "total_amount": total_amount,
            "member_discount": member_discount,
            "coupon_discount": coupon_discount,
            "final_amount": final_amount,
            "breakdown": {
                "dishes_total": total_amount,
                "service_fee": 0,
                "tax": 0,
            },
        }

        logger.info("账单计算完成", final_amount=final_amount)

        return {"success": True, "bill": bill}

    async def process_payment(
        self,
        order_id: str,
        payment_method: str,
        amount: float,
        payment_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        处理支付

        Args:
            order_id: 订单ID
            payment_method: 支付方式
            amount: 支付金额
            payment_details: 支付详情

        Returns:
            支付结果
        """
        logger.info(
            "处理支付",
            order_id=order_id,
            method=payment_method,
            amount=amount,
        )

        # TODO: 调用支付接口
        # TODO: 更新订单状态
        # TODO: 生成支付凭证

        payment_id = f"PAY{uuid.uuid4().hex[:12].upper()}"

        payment_result = {
            "payment_id": payment_id,
            "order_id": order_id,
            "payment_method": payment_method,
            "amount": amount,
            "status": "success",
            "paid_at": datetime.now().isoformat(),
        }

        logger.info("支付成功", payment_id=payment_id)

        return {
            "success": True,
            "payment": payment_result,
            "message": "支付成功",
        }

    # ==================== 订单查询 ====================

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        查询订单

        Args:
            order_id: 订单ID

        Returns:
            订单详情
        """
        logger.info("查询订单", order_id=order_id)

        # TODO: 从数据库查询订单
        return {
            "success": True,
            "order": {
                "order_id": order_id,
                "status": OrderStatus.PAID.value,
                "dishes": [],
                "total_amount": 200.0,
            },
        }

    async def update_order_status(
        self, order_id: str, new_status: str
    ) -> Dict[str, Any]:
        """
        更新订单状态

        Args:
            order_id: 订单ID
            new_status: 新状态

        Returns:
            更新结果
        """
        logger.info("更新订单状态", order_id=order_id, new_status=new_status)

        # TODO: 验证状态转换合法性
        # TODO: 更新数据库
        # TODO: 触发相关通知

        return {
            "success": True,
            "order_id": order_id,
            "status": new_status,
            "message": "订单状态已更新",
        }

    async def cancel_order(
        self, order_id: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        取消订单

        Args:
            order_id: 订单ID
            reason: 取消原因

        Returns:
            取消结果
        """
        logger.info("取消订单", order_id=order_id, reason=reason)

        # TODO: 检查订单状态是否可取消
        # TODO: 处理退款（如已支付）
        # TODO: 更新订单状态

        return {
            "success": True,
            "order_id": order_id,
            "message": "订单已取消",
        }
