"""
预定宴会Agent - Reservation & Banquet Agent

核心功能 Core Features:
1. 预定管理 - Reservation management
2. 宴会管理 - Banquet management
3. 座位分配 - Seating allocation
4. 提醒通知 - Notification services
5. 统计分析 - Analytics and reporting
6. 冲突检测 - Conflict detection
"""

import os
import asyncio
import structlog
from datetime import datetime, timedelta
from enum import Enum
from typing import TypedDict, List, Optional, Dict, Any
from collections import defaultdict
import sys
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()


class ReservationType(str, Enum):
    """预定类型 Reservation Type"""
    REGULAR = "regular"  # 普通预定
    BANQUET = "banquet"  # 宴会
    PRIVATE_ROOM = "private_room"  # 包间
    VIP = "vip"  # VIP预定


class ReservationStatus(str, Enum):
    """预定状态 Reservation Status"""
    PENDING = "pending"  # 待确认
    CONFIRMED = "confirmed"  # 已确认
    SEATED = "seated"  # 已入座
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消
    NO_SHOW = "no_show"  # 未到店


class BanquetType(str, Enum):
    """宴会类型 Banquet Type"""
    WEDDING = "wedding"  # 婚宴
    BIRTHDAY = "birthday"  # 生日宴
    CORPORATE = "corporate"  # 公司宴请
    FAMILY = "family"  # 家庭聚会
    CONFERENCE = "conference"  # 会议餐
    OTHER = "other"  # 其他


class TableType(str, Enum):
    """桌型 Table Type"""
    SMALL = "small"  # 小桌(2-4人)
    MEDIUM = "medium"  # 中桌(4-6人)
    LARGE = "large"  # 大桌(6-10人)
    ROUND = "round"  # 圆桌(10-12人)
    BANQUET = "banquet"  # 宴会桌(12+人)


class NotificationType(str, Enum):
    """通知类型 Notification Type"""
    CONFIRMATION = "confirmation"  # 确认通知
    REMINDER = "reminder"  # 提醒通知
    CANCELLATION = "cancellation"  # 取消通知
    MODIFICATION = "modification"  # 修改通知


class Reservation(TypedDict):
    """预定 Reservation"""
    reservation_id: str  # 预定ID
    customer_id: str  # 客户ID
    customer_name: str  # 客户姓名
    customer_phone: str  # 客户电话
    store_id: str  # 门店ID
    reservation_type: ReservationType  # 预定类型
    reservation_date: str  # 预定日期
    reservation_time: str  # 预定时间
    party_size: int  # 人数
    table_type: Optional[TableType]  # 桌型
    table_number: Optional[str]  # 桌号
    special_requests: Optional[str]  # 特殊要求
    status: ReservationStatus  # 状态
    deposit_amount: int  # 定金(分)
    estimated_amount: int  # 预估消费(分)
    created_at: str  # 创建时间
    updated_at: str  # 更新时间
    confirmed_at: Optional[str]  # 确认时间
    seated_at: Optional[str]  # 入座时间
    completed_at: Optional[str]  # 完成时间


class Banquet(TypedDict):
    """宴会 Banquet"""
    banquet_id: str  # 宴会ID
    reservation_id: str  # 关联预定ID
    customer_id: str  # 客户ID
    customer_name: str  # 客户姓名
    customer_phone: str  # 客户电话
    store_id: str  # 门店ID
    banquet_type: BanquetType  # 宴会类型
    banquet_date: str  # 宴会日期
    banquet_time: str  # 宴会时间
    guest_count: int  # 宾客人数
    table_count: int  # 桌数
    venue: str  # 场地
    menu_id: Optional[str]  # 菜单ID
    menu_items: List[Dict[str, Any]]  # 菜单项
    price_per_table: int  # 每桌价格(分)
    total_amount: int  # 总金额(分)
    deposit_amount: int  # 定金(分)
    special_requirements: Optional[str]  # 特殊要求
    status: ReservationStatus  # 状态
    created_at: str  # 创建时间
    updated_at: str  # 更新时间


class SeatingPlan(TypedDict):
    """座位安排 Seating Plan"""
    plan_id: str  # 方案ID
    reservation_id: str  # 预定ID
    store_id: str  # 门店ID
    date: str  # 日期
    time_slot: str  # 时段
    tables: List[Dict[str, Any]]  # 桌位列表
    utilization_rate: float  # 利用率
    created_at: str  # 创建时间


class Notification(TypedDict):
    """通知 Notification"""
    notification_id: str  # 通知ID
    reservation_id: str  # 预定ID
    customer_id: str  # 客户ID
    notification_type: NotificationType  # 通知类型
    channel: str  # 渠道(sms/wechat/phone)
    content: str  # 内容
    sent_at: Optional[str]  # 发送时间
    status: str  # 状态(pending/sent/failed)


class ReservationAnalytics(TypedDict):
    """预定分析 Reservation Analytics"""
    store_id: str  # 门店ID
    period_start: str  # 统计开始时间
    period_end: str  # 统计结束时间
    total_reservations: int  # 总预定数
    confirmed_count: int  # 确认数
    cancelled_count: int  # 取消数
    no_show_count: int  # 未到店数
    confirmation_rate: float  # 确认率
    cancellation_rate: float  # 取消率
    no_show_rate: float  # 未到店率
    average_party_size: float  # 平均人数
    peak_hours: List[str]  # 高峰时段
    revenue_from_reservations: int  # 预定收入(分)


class ReservationAgent(BaseAgent):
    """
    预定宴会Agent

    工作流程 Workflow:
    1. create_reservation() - 创建预定
    2. confirm_reservation() - 确认预定
    3. allocate_seating() - 分配座位
    4. manage_banquet() - 管理宴会
    5. send_notifications() - 发送通知
    6. analyze_reservations() - 分析预定数据
    """

    def __init__(
        self,
        store_id: str,
        order_agent: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化预定宴会Agent

        Args:
            store_id: 门店ID
            order_agent: 订单Agent
            config: 配置参数
        """
        super().__init__()
        self.store_id = store_id
        self.order_agent = order_agent
        self.config = config or {
            "advance_booking_days": int(os.getenv("RESERVATION_ADVANCE_BOOKING_DAYS", "30")),  # 提前预定天数
            "min_party_size": 1,  # 最小人数
            "max_party_size": int(os.getenv("RESERVATION_MAX_PARTY_SIZE", "50")),  # 最大人数
            "deposit_rate": float(os.getenv("RESERVATION_DEPOSIT_RATE", "0.3")),  # 定金比例
            "cancellation_hours": int(os.getenv("RESERVATION_CANCELLATION_HOURS", "24")),  # 取消提前时间(小时)
            "reminder_hours": int(os.getenv("RESERVATION_REMINDER_HOURS", "2")),  # 提醒提前时间(小时)
        }
        self.logger = logger.bind(agent="reservation", store_id=store_id)

    def get_supported_actions(self) -> List[str]:
        """获取支持的操作列表"""
        return [
            "create_reservation", "confirm_reservation", "cancel_reservation",
            "create_banquet", "allocate_seating", "send_reminder",
            "analyze_reservations"
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
                result = await self.create_reservation(
                    customer_id=params["customer_id"],
                    customer_name=params["customer_name"],
                    customer_phone=params["customer_phone"],
                    reservation_date=params["reservation_date"],
                    reservation_time=params["reservation_time"],
                    party_size=params["party_size"],
                    reservation_type=params.get("reservation_type", ReservationType.REGULAR),
                    special_requests=params.get("special_requests")
                )
                return AgentResponse(success=True, data=result)
            elif action == "confirm_reservation":
                result = await self.confirm_reservation(
                    reservation_id=params["reservation_id"]
                )
                return AgentResponse(success=True, data=result)
            elif action == "cancel_reservation":
                result = await self.cancel_reservation(
                    reservation_id=params["reservation_id"],
                    reason=params.get("reason")
                )
                return AgentResponse(success=True, data=result)
            elif action == "create_banquet":
                result = await self.create_banquet(
                    customer_id=params["customer_id"],
                    customer_name=params["customer_name"],
                    customer_phone=params["customer_phone"],
                    banquet_type=params["banquet_type"],
                    banquet_date=params["banquet_date"],
                    banquet_time=params["banquet_time"],
                    guest_count=params["guest_count"],
                    table_count=params["table_count"],
                    venue=params["venue"],
                    menu_items=params["menu_items"],
                    price_per_table=params["price_per_table"],
                    special_requirements=params.get("special_requirements")
                )
                return AgentResponse(success=True, data=result)
            elif action == "allocate_seating":
                result = await self.allocate_seating(
                    date=params["date"],
                    time_slot=params["time_slot"]
                )
                return AgentResponse(success=True, data=result)
            elif action == "send_reminder":
                result = await self.send_reminder(
                    reservation_id=params["reservation_id"]
                )
                return AgentResponse(success=True, data=result)
            elif action == "analyze_reservations":
                result = await self.analyze_reservations(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            else:
                return AgentResponse(
                    success=False,
                    data=None,
                    error=f"Unsupported action: {action}"
                )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                error=str(e)
            )

    async def create_reservation(
        self,
        customer_id: str,
        customer_name: str,
        customer_phone: str,
        reservation_date: str,
        reservation_time: str,
        party_size: int,
        reservation_type: ReservationType = ReservationType.REGULAR,
        special_requests: Optional[str] = None
    ) -> Reservation:
        """
        创建预定

        Args:
            customer_id: 客户ID
            customer_name: 客户姓名
            customer_phone: 客户电话
            reservation_date: 预定日期
            reservation_time: 预定时间
            party_size: 人数
            reservation_type: 预定类型
            special_requests: 特殊要求

        Returns:
            预定信息
        """
        self.logger.info(
            "creating_reservation",
            customer_id=customer_id,
            party_size=party_size,
            date=reservation_date
        )

        try:
            # 验证预定参数
            self._validate_reservation_params(
                reservation_date,
                reservation_time,
                party_size
            )

            # 检查可用性
            available = await self._check_availability(
                reservation_date,
                reservation_time,
                party_size
            )

            if not available:
                raise ValueError("该时段暂无可用座位")

            # 推荐桌型
            table_type = self._recommend_table_type(party_size)

            # 计算预估消费和定金
            estimated_amount = self._estimate_amount(party_size, reservation_type)
            deposit_amount = int(estimated_amount * self.config["deposit_rate"])

            # 创建预定记录
            reservation: Reservation = {
                "reservation_id": f"RES_{datetime.now().strftime('%Y%m%d%H%M%S')}_{customer_id[-4:]}",
                "customer_id": customer_id,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "store_id": self.store_id,
                "reservation_type": reservation_type,
                "reservation_date": reservation_date,
                "reservation_time": reservation_time,
                "party_size": party_size,
                "table_type": table_type,
                "table_number": None,  # 稍后分配
                "special_requests": special_requests,
                "status": ReservationStatus.PENDING,
                "deposit_amount": deposit_amount,
                "estimated_amount": estimated_amount,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "confirmed_at": None,
                "seated_at": None,
                "completed_at": None
            }

            # 发送确认通知
            await self._send_notification(
                reservation,
                NotificationType.CONFIRMATION
            )

            self.logger.info(
                "reservation_created",
                reservation_id=reservation["reservation_id"],
                status=reservation["status"]
            )

            return reservation

        except Exception as e:
            self.logger.error("create_reservation_failed", error=str(e))
            raise

    def _validate_reservation_params(
        self,
        reservation_date: str,
        reservation_time: str,
        party_size: int
    ):
        """验证预定参数"""
        # 验证日期
        res_date = datetime.fromisoformat(reservation_date)
        if res_date < datetime.now():
            raise ValueError("预定日期不能早于当前日期")

        max_advance = datetime.now() + timedelta(days=self.config["advance_booking_days"])
        if res_date > max_advance:
            raise ValueError(f"只能提前{self.config['advance_booking_days']}天预定")

        # 验证人数
        if party_size < self.config["min_party_size"]:
            raise ValueError(f"人数不能少于{self.config['min_party_size']}人")

        if party_size > self.config["max_party_size"]:
            raise ValueError(f"人数不能超过{self.config['max_party_size']}人,请联系宴会部")

    async def _check_availability(
        self,
        date: str,
        time: str,
        party_size: int
    ) -> bool:
        """检查可用性"""
        existing = await self._get_reservations_by_time(date, time)
        available_tables = await self._get_available_tables(date, time)
        occupied = {r.get("table_number") for r in existing if r.get("table_number")}
        for table in available_tables:
            if table["table_number"] not in occupied and table["capacity"] >= party_size:
                return True
        return False

    def _recommend_table_type(self, party_size: int) -> TableType:
        """推荐桌型"""
        if party_size <= 2:
            return TableType.SMALL
        elif party_size <= int(os.getenv("TABLE_SIZE_MEDIUM_MAX", "4")):
            return TableType.MEDIUM
        elif party_size <= int(os.getenv("TABLE_SIZE_LARGE_MAX", "6")):
            return TableType.LARGE
        elif party_size <= int(os.getenv("TABLE_SIZE_ROUND_MAX", "10")):
            return TableType.ROUND
        else:
            return TableType.BANQUET

    def _estimate_amount(
        self,
        party_size: int,
        reservation_type: ReservationType
    ) -> int:
        """预估消费金额"""
        # 基础人均消费(分)
        base_per_person = {
            ReservationType.REGULAR: int(os.getenv("RESERVATION_AMOUNT_REGULAR", "8000")),  # 80元/人
            ReservationType.BANQUET: int(os.getenv("RESERVATION_AMOUNT_BANQUET", "15000")),  # 150元/人
            ReservationType.PRIVATE_ROOM: int(os.getenv("RESERVATION_AMOUNT_PRIVATE_ROOM", "12000")),  # 120元/人
            ReservationType.VIP: int(os.getenv("RESERVATION_AMOUNT_VIP", "20000")),  # 200元/人
        }

        per_person = base_per_person.get(reservation_type, 8000)
        return party_size * per_person

    async def confirm_reservation(
        self,
        reservation_id: str
    ) -> Reservation:
        """
        确认预定

        Args:
            reservation_id: 预定ID

        Returns:
            更新后的预定信息
        """
        self.logger.info("confirming_reservation", reservation_id=reservation_id)

        try:
            # 获取预定信息
            reservation = await self._get_reservation(reservation_id)

            if reservation["status"] != ReservationStatus.PENDING:
                raise ValueError(f"预定状态为{reservation['status']},无法确认")

            # 分配座位
            table_number = await self._allocate_table(reservation)

            # 更新状态
            reservation["status"] = ReservationStatus.CONFIRMED
            reservation["table_number"] = table_number
            reservation["confirmed_at"] = datetime.now().isoformat()
            reservation["updated_at"] = datetime.now().isoformat()

            # 发送确认通知
            await self._send_notification(
                reservation,
                NotificationType.CONFIRMATION
            )

            self.logger.info(
                "reservation_confirmed",
                reservation_id=reservation_id,
                table_number=table_number
            )

            return reservation

        except Exception as e:
            self.logger.error("confirm_reservation_failed", error=str(e))
            raise

    async def _allocate_table(self, reservation: Reservation) -> str:
        """分配桌位"""
        date = reservation.get("reservation_date", "")
        time = reservation.get("reservation_time", "")
        party_size = reservation.get("party_size", 1)
        table_type = str(reservation.get("table_type", "")).lower()

        available_tables = await self._get_available_tables(date, time)
        existing = await self._get_reservations_by_time(date, time)
        occupied = {r.get("table_number") for r in existing if r.get("table_number")}

        # 优先匹配桌型
        for table in available_tables:
            if table["table_number"] not in occupied and table["capacity"] >= party_size:
                if str(table.get("table_type", "")).lower() == table_type:
                    return table["table_number"]

        # 退而求其次，任意合适空桌
        for table in available_tables:
            if table["table_number"] not in occupied and table["capacity"] >= party_size:
                return table["table_number"]

        # 无可用桌位时生成临时编号
        return f"{table_type.upper()[:1]}{datetime.now().strftime('%H%M%S')[-3:]}"

    async def cancel_reservation(
        self,
        reservation_id: str,
        reason: Optional[str] = None
    ) -> Reservation:
        """
        取消预定

        Args:
            reservation_id: 预定ID
            reason: 取消原因

        Returns:
            更新后的预定信息
        """
        self.logger.info("cancelling_reservation", reservation_id=reservation_id)

        try:
            reservation = await self._get_reservation(reservation_id)

            # 检查是否可以取消
            if reservation["status"] in [ReservationStatus.COMPLETED, ReservationStatus.CANCELLED]:
                raise ValueError(f"预定状态为{reservation['status']},无法取消")

            # 检查取消时间
            res_datetime = datetime.fromisoformat(f"{reservation['reservation_date']}T{reservation['reservation_time']}")
            hours_until = (res_datetime - datetime.now()).total_seconds() / 3600

            if hours_until < self.config["cancellation_hours"]:
                self.logger.warning(
                    "late_cancellation",
                    reservation_id=reservation_id,
                    hours_until=hours_until
                )

            # 更新状态
            reservation["status"] = ReservationStatus.CANCELLED
            reservation["updated_at"] = datetime.now().isoformat()

            # 发送取消通知
            await self._send_notification(
                reservation,
                NotificationType.CANCELLATION
            )

            self.logger.info("reservation_cancelled", reservation_id=reservation_id)

            return reservation

        except Exception as e:
            self.logger.error("cancel_reservation_failed", error=str(e))
            raise

    async def create_banquet(
        self,
        customer_id: str,
        customer_name: str,
        customer_phone: str,
        banquet_type: BanquetType,
        banquet_date: str,
        banquet_time: str,
        guest_count: int,
        table_count: int,
        venue: str,
        menu_items: List[Dict[str, Any]],
        price_per_table: int,
        special_requirements: Optional[str] = None
    ) -> Banquet:
        """
        创建宴会

        Args:
            customer_id: 客户ID
            customer_name: 客户姓名
            customer_phone: 客户电话
            banquet_type: 宴会类型
            banquet_date: 宴会日期
            banquet_time: 宴会时间
            guest_count: 宾客人数
            table_count: 桌数
            venue: 场地
            menu_items: 菜单项
            price_per_table: 每桌价格
            special_requirements: 特殊要求

        Returns:
            宴会信息
        """
        self.logger.info(
            "creating_banquet",
            customer_id=customer_id,
            guest_count=guest_count,
            table_count=table_count
        )

        try:
            # 先创建预定
            reservation = await self.create_reservation(
                customer_id=customer_id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                reservation_date=banquet_date,
                reservation_time=banquet_time,
                party_size=guest_count,
                reservation_type=ReservationType.BANQUET,
                special_requests=special_requirements
            )

            # 计算总金额
            total_amount = price_per_table * table_count
            deposit_amount = int(total_amount * self.config["deposit_rate"])

            # 创建宴会记录
            banquet: Banquet = {
                "banquet_id": f"BAN_{datetime.now().strftime('%Y%m%d%H%M%S')}_{customer_id[-4:]}",
                "reservation_id": reservation["reservation_id"],
                "customer_id": customer_id,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "store_id": self.store_id,
                "banquet_type": banquet_type,
                "banquet_date": banquet_date,
                "banquet_time": banquet_time,
                "guest_count": guest_count,
                "table_count": table_count,
                "venue": venue,
                "menu_id": None,
                "menu_items": menu_items,
                "price_per_table": price_per_table,
                "total_amount": total_amount,
                "deposit_amount": deposit_amount,
                "special_requirements": special_requirements,
                "status": ReservationStatus.PENDING,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            self.logger.info(
                "banquet_created",
                banquet_id=banquet["banquet_id"],
                total_amount=total_amount
            )

            return banquet

        except Exception as e:
            self.logger.error("create_banquet_failed", error=str(e))
            raise

    async def allocate_seating(
        self,
        date: str,
        time_slot: str
    ) -> SeatingPlan:
        """
        分配座位方案

        Args:
            date: 日期
            time_slot: 时段

        Returns:
            座位安排方案
        """
        self.logger.info("allocating_seating", date=date, time_slot=time_slot)

        try:
            # 获取该时段的所有预定
            reservations = await self._get_reservations_by_time(date, time_slot)

            # 获取可用桌位
            available_tables = await self._get_available_tables(date, time_slot)

            # 智能分配算法
            allocation = self._optimize_seating(reservations, available_tables)

            # 计算利用率
            total_capacity = sum(t["capacity"] for t in available_tables)
            total_guests = sum(r["party_size"] for r in reservations)
            utilization_rate = total_guests / total_capacity if total_capacity > 0 else 0

            plan: SeatingPlan = {
                "plan_id": f"PLAN_{date}_{time_slot}_{datetime.now().strftime('%H%M%S')}",
                "reservation_id": None,
                "store_id": self.store_id,
                "date": date,
                "time_slot": time_slot,
                "tables": allocation,
                "utilization_rate": round(utilization_rate, 2),
                "created_at": datetime.now().isoformat()
            }

            self.logger.info(
                "seating_allocated",
                plan_id=plan["plan_id"],
                utilization_rate=plan["utilization_rate"]
            )

            return plan

        except Exception as e:
            self.logger.error("allocate_seating_failed", error=str(e))
            raise

    def _optimize_seating(
        self,
        reservations: List[Reservation],
        available_tables: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """优化座位分配"""
        allocation = []

        # 按人数排序预定
        sorted_reservations = sorted(reservations, key=lambda x: x["party_size"], reverse=True)

        # 简单的贪心算法分配
        for reservation in sorted_reservations:
            # 找到最合适的桌位
            best_table = None
            min_waste = float('inf')

            for table in available_tables:
                if table.get("assigned"):
                    continue

                capacity = table["capacity"]
                party_size = reservation["party_size"]

                if capacity >= party_size:
                    waste = capacity - party_size
                    if waste < min_waste:
                        min_waste = waste
                        best_table = table

            if best_table:
                best_table["assigned"] = True
                allocation.append({
                    "table_number": best_table["table_number"],
                    "table_type": best_table["table_type"],
                    "capacity": best_table["capacity"],
                    "reservation_id": reservation["reservation_id"],
                    "customer_name": reservation["customer_name"],
                    "party_size": reservation["party_size"]
                })

        return allocation

    async def send_reminder(
        self,
        reservation_id: str
    ) -> Notification:
        """
        发送提醒

        Args:
            reservation_id: 预定ID

        Returns:
            通知记录
        """
        self.logger.info("sending_reminder", reservation_id=reservation_id)

        try:
            reservation = await self._get_reservation(reservation_id)

            notification = await self._send_notification(
                reservation,
                NotificationType.REMINDER
            )

            return notification

        except Exception as e:
            self.logger.error("send_reminder_failed", error=str(e))
            raise

    async def _send_notification(
        self,
        reservation: Reservation,
        notification_type: NotificationType
    ) -> Notification:
        """发送通知"""
        # 生成通知内容
        content = self._generate_notification_content(reservation, notification_type)

        notification: Notification = {
            "notification_id": f"NOTIF_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "reservation_id": reservation["reservation_id"],
            "customer_id": reservation["customer_id"],
            "notification_type": notification_type,
            "channel": "sms",  # 默认短信
            "content": content,
            "sent_at": datetime.now().isoformat(),
            "status": "sent"
        }

        self.logger.info(
            "notification_sent",
            notification_id=notification["notification_id"],
            type=notification_type
        )

        return notification

    def _generate_notification_content(
        self,
        reservation: Reservation,
        notification_type: NotificationType
    ) -> str:
        """生成通知内容"""
        if notification_type == NotificationType.CONFIRMATION:
            return f"【智链餐厅】尊敬的{reservation['customer_name']},您的预定已确认。日期:{reservation['reservation_date']} 时间:{reservation['reservation_time']} 人数:{reservation['party_size']}人 桌号:{reservation.get('table_number', '待分配')}"

        elif notification_type == NotificationType.REMINDER:
            return f"【智链餐厅】尊敬的{reservation['customer_name']},提醒您今天{reservation['reservation_time']}有预定,人数{reservation['party_size']}人,期待您的光临!"

        elif notification_type == NotificationType.CANCELLATION:
            return f"【智链餐厅】尊敬的{reservation['customer_name']},您的预定已取消。如有疑问请联系我们。"

        else:
            return f"【智链餐厅】预定通知"

    async def analyze_reservations(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> ReservationAnalytics:
        """
        分析预定数据

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            预定分析结果
        """
        self.logger.info("analyzing_reservations", start_date=start_date, end_date=end_date)

        try:
            # 获取预定数据
            reservations = await self._get_reservations_by_period(start_date, end_date)

            if not reservations:
                raise ValueError("该时段没有预定数据")

            # 统计各状态数量
            total = len(reservations)
            confirmed = sum(1 for r in reservations if r["status"] == ReservationStatus.CONFIRMED)
            cancelled = sum(1 for r in reservations if r["status"] == ReservationStatus.CANCELLED)
            no_show = sum(1 for r in reservations if r["status"] == ReservationStatus.NO_SHOW)

            # 计算率
            confirmation_rate = confirmed / total if total > 0 else 0
            cancellation_rate = cancelled / total if total > 0 else 0
            no_show_rate = no_show / total if total > 0 else 0

            # 计算平均人数
            party_sizes = [r["party_size"] for r in reservations]
            average_party_size = sum(party_sizes) / len(party_sizes) if party_sizes else 0

            # 分析高峰时段
            time_counts = defaultdict(int)
            for r in reservations:
                hour = r["reservation_time"].split(":")[0]
                time_counts[hour] += 1

            peak_hours = sorted(time_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            peak_hours_list = [f"{h}:00" for h, _ in peak_hours]

            # 计算收入
            revenue = sum(r.get("estimated_amount", 0) for r in reservations if r["status"] in [ReservationStatus.CONFIRMED, ReservationStatus.COMPLETED])

            analytics: ReservationAnalytics = {
                "store_id": self.store_id,
                "period_start": start_date or (datetime.now() - timedelta(days=int(os.getenv("AGENT_STATS_DAYS", "30")))).isoformat(),
                "period_end": end_date or datetime.now().isoformat(),
                "total_reservations": total,
                "confirmed_count": confirmed,
                "cancelled_count": cancelled,
                "no_show_count": no_show,
                "confirmation_rate": round(confirmation_rate, 2),
                "cancellation_rate": round(cancellation_rate, 2),
                "no_show_rate": round(no_show_rate, 2),
                "average_party_size": round(average_party_size, 1),
                "peak_hours": peak_hours_list,
                "revenue_from_reservations": revenue
            }

            self.logger.info(
                "reservations_analyzed",
                total=total,
                confirmation_rate=analytics["confirmation_rate"]
            )

            return analytics

        except Exception as e:
            self.logger.error("analyze_reservations_failed", error=str(e))
            raise

    # Helper methods

    async def _get_reservation(self, reservation_id: str) -> Reservation:
        """获取预定信息"""
        # 模拟数据
        return {
            "reservation_id": reservation_id,
            "customer_id": "CUST001",
            "customer_name": "张三",
            "customer_phone": "13800138000",
            "store_id": self.store_id,
            "reservation_type": ReservationType.REGULAR,
            "reservation_date": datetime.now().date().isoformat(),
            "reservation_time": "18:00",
            "party_size": 4,
            "table_type": TableType.MEDIUM,
            "table_number": "M001",
            "special_requests": None,
            "status": ReservationStatus.PENDING,
            "deposit_amount": 10000,
            "estimated_amount": 32000,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "confirmed_at": None,
            "seated_at": None,
            "completed_at": None
        }

    async def _get_reservations_by_time(
        self,
        date: str,
        time_slot: str
    ) -> List[Reservation]:
        """获取指定时段的预定"""
        # 模拟数据
        return []

    async def _get_available_tables(
        self,
        date: str,
        time_slot: str
    ) -> List[Dict[str, Any]]:
        """获取可用桌位"""
        # 模拟数据
        return [
            {"table_number": "S001", "table_type": "small", "capacity": 2},
            {"table_number": "M001", "table_type": "medium", "capacity": 4},
            {"table_number": "L001", "table_type": "large", "capacity": 6},
            {"table_number": "R001", "table_type": "round", "capacity": 10},
        ]

    async def _get_reservations_by_period(
        self,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> List[Reservation]:
        """获取时段内的预定"""
        import random
        # 生成模拟数据
        reservations = []
        for i in range(50):
            status_choices = [
                ReservationStatus.CONFIRMED,
                ReservationStatus.COMPLETED,
                ReservationStatus.CANCELLED,
                ReservationStatus.NO_SHOW
            ]

            reservation: Reservation = {
                "reservation_id": f"RES{i:04d}",
                "customer_id": f"CUST{random.randint(1, 100):03d}",
                "customer_name": f"客户{i}",
                "customer_phone": f"138{random.randint(10000000, 99999999)}",
                "store_id": self.store_id,
                "reservation_type": random.choice(list(ReservationType)),
                "reservation_date": (datetime.now() - timedelta(days=random.randint(0, 30))).date().isoformat(),
                "reservation_time": f"{random.randint(11, 20)}:00",
                "party_size": random.randint(2, 10),
                "table_type": random.choice(list(TableType)),
                "table_number": f"T{random.randint(1, 20):03d}",
                "special_requests": None,
                "status": random.choice(status_choices),
                "deposit_amount": random.randint(5000, 20000),
                "estimated_amount": random.randint(20000, 80000),
                "created_at": (datetime.now() - timedelta(days=random.randint(0, 30))).isoformat(),
                "updated_at": datetime.now().isoformat(),
                "confirmed_at": datetime.now().isoformat() if random.random() > 0.3 else None,
                "seated_at": None,
                "completed_at": None
            }
            reservations.append(reservation)

        return reservations