"""
等位叫号与排队预估服务

纯Python实现，不依赖数据库。
管理取号、叫号、入座、过号以及等位时间预估。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class QueueGroup(str, Enum):
    """桌型分组"""
    SMALL_TABLE = "small_table"       # 2人桌
    MEDIUM_TABLE = "medium_table"     # 4人桌
    LARGE_TABLE = "large_table"       # 6-8人桌
    PRIVATE_ROOM = "private_room"     # 包厢


class QueueStatus(str, Enum):
    """排队状态"""
    WAITING = "waiting"
    CALLED = "called"
    SEATED = "seated"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# 人数 → 桌型映射规则
PARTY_SIZE_TO_GROUP = [
    (2, QueueGroup.SMALL_TABLE),
    (4, QueueGroup.MEDIUM_TABLE),
    (8, QueueGroup.LARGE_TABLE),
]
# 超过8人或包厢需求 → PRIVATE_ROOM（默认兜底）


@dataclass
class QueueTicket:
    """排队票据"""
    ticket_no: str
    group: QueueGroup
    party_size: int
    customer_name: str
    customer_phone: Optional[str]
    status: QueueStatus = QueueStatus.WAITING
    is_vip: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    called_at: Optional[datetime] = None
    seated_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


class QueueManagementService:
    """等位叫号与排队预估"""

    def __init__(self):
        self._ticket_counter: Dict[QueueGroup, int] = {
            g: 0 for g in QueueGroup
        }
        self._queue: List[QueueTicket] = []

    @property
    def queue(self) -> List[QueueTicket]:
        """当前队列（只读副本）"""
        return list(self._queue)

    def _assign_group(self, party_size: int) -> QueueGroup:
        """根据人数分配桌型"""
        for max_size, group in PARTY_SIZE_TO_GROUP:
            if party_size <= max_size:
                return group
        return QueueGroup.PRIVATE_ROOM

    def _generate_ticket_no(self, group: QueueGroup) -> str:
        """生成票号：桌型前缀 + 序号"""
        prefix_map = {
            QueueGroup.SMALL_TABLE: "S",
            QueueGroup.MEDIUM_TABLE: "M",
            QueueGroup.LARGE_TABLE: "L",
            QueueGroup.PRIVATE_ROOM: "P",
        }
        self._ticket_counter[group] += 1
        return f"{prefix_map[group]}{self._ticket_counter[group]:03d}"

    def _find_ticket(self, ticket_no: str) -> Optional[QueueTicket]:
        """按票号查找"""
        for ticket in self._queue:
            if ticket.ticket_no == ticket_no:
                return ticket
        return None

    def _waiting_tickets(self, group: QueueGroup) -> List[QueueTicket]:
        """指定分组的等待中票据（按排队顺序）"""
        return [
            t for t in self._queue
            if t.group == group and t.status == QueueStatus.WAITING
        ]

    def take_number(
        self,
        party_size: int,
        customer_name: str,
        phone: Optional[str] = None,
    ) -> QueueTicket:
        """
        取号

        Args:
            party_size: 就餐人数
            customer_name: 顾客姓名
            phone: 手机号（用于叫号通知）

        Returns:
            QueueTicket 排队票据
        """
        if party_size <= 0:
            raise ValueError("就餐人数必须大于0")
        if not customer_name or not customer_name.strip():
            raise ValueError("顾客姓名不能为空")

        group = self._assign_group(party_size)
        ticket_no = self._generate_ticket_no(group)

        ticket = QueueTicket(
            ticket_no=ticket_no,
            group=group,
            party_size=party_size,
            customer_name=customer_name.strip(),
            customer_phone=phone,
        )

        self._queue.append(ticket)

        logger.info(
            "queue_ticket_taken",
            ticket_no=ticket_no,
            group=group.value,
            party_size=party_size,
            waiting_ahead=len(self._waiting_tickets(group)) - 1,
        )

        return ticket

    def call_next(self, group: QueueGroup) -> Optional[QueueTicket]:
        """
        叫号：叫指定分组的下一位

        Args:
            group: 桌型分组

        Returns:
            被叫的票据，队列空时返回 None
        """
        waiting = self._waiting_tickets(group)
        if not waiting:
            logger.info("queue_empty", group=group.value)
            return None

        ticket = waiting[0]
        ticket.status = QueueStatus.CALLED
        ticket.called_at = datetime.utcnow()

        logger.info(
            "queue_ticket_called",
            ticket_no=ticket.ticket_no,
            group=group.value,
            customer_name=ticket.customer_name,
        )

        return ticket

    def mark_seated(self, ticket_no: str) -> QueueTicket:
        """
        标记入座

        Args:
            ticket_no: 票号

        Returns:
            更新后的票据
        """
        ticket = self._find_ticket(ticket_no)
        if ticket is None:
            raise ValueError(f"票号不存在: {ticket_no}")
        if ticket.status not in (QueueStatus.WAITING, QueueStatus.CALLED):
            raise ValueError(
                f"只有等待中或已叫号的票据可以入座，当前状态: {ticket.status.value}"
            )

        ticket.status = QueueStatus.SEATED
        ticket.seated_at = datetime.utcnow()

        logger.info(
            "queue_ticket_seated",
            ticket_no=ticket_no,
            customer_name=ticket.customer_name,
        )

        return ticket

    def mark_expired(self, ticket_no: str) -> QueueTicket:
        """
        标记过号

        Args:
            ticket_no: 票号

        Returns:
            更新后的票据
        """
        ticket = self._find_ticket(ticket_no)
        if ticket is None:
            raise ValueError(f"票号不存在: {ticket_no}")
        if ticket.status not in (QueueStatus.WAITING, QueueStatus.CALLED):
            raise ValueError(
                f"只有等待中或已叫号的票据可以过号，当前状态: {ticket.status.value}"
            )

        ticket.status = QueueStatus.EXPIRED
        ticket.expired_at = datetime.utcnow()

        logger.info(
            "queue_ticket_expired",
            ticket_no=ticket_no,
            customer_name=ticket.customer_name,
        )

        return ticket

    def cancel_ticket(self, ticket_no: str) -> QueueTicket:
        """
        取消排队

        Args:
            ticket_no: 票号

        Returns:
            更新后的票据
        """
        ticket = self._find_ticket(ticket_no)
        if ticket is None:
            raise ValueError(f"票号不存在: {ticket_no}")
        if ticket.status != QueueStatus.WAITING:
            raise ValueError(
                f"只有等待中的票据可以取消，当前状态: {ticket.status.value}"
            )

        ticket.status = QueueStatus.CANCELLED
        ticket.cancelled_at = datetime.utcnow()

        logger.info(
            "queue_ticket_cancelled",
            ticket_no=ticket_no,
            customer_name=ticket.customer_name,
        )

        return ticket

    def estimate_wait_time(
        self,
        group: QueueGroup,
        current_turnover_minutes: float,
        queue: Optional[List[QueueTicket]] = None,
    ) -> Dict:
        """
        预估等位时间

        基于当前翻台速度（分钟/桌）和前面排队人数计算。

        Args:
            group: 桌型分组
            current_turnover_minutes: 当前翻台时间（分钟/桌）
            queue: 可选的外部队列，默认用内部队列

        Returns:
            预估信息：前面人数、预估等待分钟
        """
        if current_turnover_minutes <= 0:
            raise ValueError("翻台时间必须大于0")

        tickets = queue if queue is not None else self._queue
        waiting_count = sum(
            1 for t in tickets
            if t.group == group and t.status == QueueStatus.WAITING
        )

        estimated_minutes = round(waiting_count * current_turnover_minutes)

        return {
            "group": group.value,
            "waiting_count": waiting_count,
            "estimated_minutes": estimated_minutes,
            "estimated_display": self._format_wait_time(estimated_minutes),
        }

    def _format_wait_time(self, minutes: int) -> str:
        """格式化等待时间"""
        if minutes <= 0:
            return "无需等位"
        if minutes < 60:
            return f"约{minutes}分钟"
        hours = minutes // 60
        remaining = minutes % 60
        if remaining == 0:
            return f"约{hours}小时"
        return f"约{hours}小时{remaining}分钟"

    def get_queue_status(self) -> Dict:
        """
        获取各分组排队状态

        Returns:
            各分组的排队人数和状态汇总
        """
        result = {}
        for group in QueueGroup:
            waiting = self._waiting_tickets(group)
            called = [
                t for t in self._queue
                if t.group == group and t.status == QueueStatus.CALLED
            ]
            result[group.value] = {
                "waiting_count": len(waiting),
                "called_count": len(called),
                "total_party_size": sum(t.party_size for t in waiting),
            }

        total_waiting = sum(v["waiting_count"] for v in result.values())
        return {
            "groups": result,
            "total_waiting": total_waiting,
        }

    def skip_to_vip(self, ticket_no: str) -> QueueTicket:
        """
        VIP插队：将指定票据移到其分组等待队列的最前面

        Args:
            ticket_no: 票号

        Returns:
            更新后的票据
        """
        ticket = self._find_ticket(ticket_no)
        if ticket is None:
            raise ValueError(f"票号不存在: {ticket_no}")
        if ticket.status != QueueStatus.WAITING:
            raise ValueError(
                f"只有等待中的票据可以VIP插队，当前状态: {ticket.status.value}"
            )

        ticket.is_vip = True

        # 从队列中移除再插入到该分组等待票据的最前面
        self._queue.remove(ticket)

        # 找到该分组第一个等待票据的位置
        insert_idx = 0
        for i, t in enumerate(self._queue):
            if t.group == ticket.group and t.status == QueueStatus.WAITING:
                insert_idx = i
                break
        else:
            # 没有同分组等待的，放到队列末尾
            insert_idx = len(self._queue)

        self._queue.insert(insert_idx, ticket)

        logger.info(
            "queue_vip_skip",
            ticket_no=ticket_no,
            group=ticket.group.value,
            customer_name=ticket.customer_name,
        )

        return ticket

    def send_call_notification(self, ticket: QueueTicket) -> Dict:
        """
        生成叫号通知内容（用于短信/微信推送）

        Args:
            ticket: 被叫的票据

        Returns:
            通知内容字典
        """
        group_names = {
            QueueGroup.SMALL_TABLE: "小桌(2人)",
            QueueGroup.MEDIUM_TABLE: "中桌(4人)",
            QueueGroup.LARGE_TABLE: "大桌(6-8人)",
            QueueGroup.PRIVATE_ROOM: "包厢",
        }

        message = (
            f"【叫号通知】{ticket.customer_name}您好，"
            f"您的{group_names.get(ticket.group, '')}排号{ticket.ticket_no}已到号，"
            f"请尽快到前台确认入座。超过5分钟未到将自动过号。"
        )

        notification = {
            "ticket_no": ticket.ticket_no,
            "customer_name": ticket.customer_name,
            "customer_phone": ticket.customer_phone,
            "message": message,
            "group": ticket.group.value,
            "party_size": ticket.party_size,
        }

        logger.info(
            "queue_call_notification_generated",
            ticket_no=ticket.ticket_no,
            has_phone=ticket.customer_phone is not None,
        )

        return notification

    def auto_expire_check(
        self,
        queue: Optional[List[QueueTicket]] = None,
        max_wait_minutes: int = 120,
    ) -> List[QueueTicket]:
        """
        自动过号检查：超过最大等待时间的票据自动过号

        Args:
            queue: 可选的外部队列，默认用内部队列
            max_wait_minutes: 最大等待时间（分钟），默认120分钟

        Returns:
            被过号的票据列表
        """
        if max_wait_minutes <= 0:
            raise ValueError("最大等待时间必须大于0")

        tickets = queue if queue is not None else self._queue
        now = datetime.utcnow()
        expired_tickets = []

        for ticket in tickets:
            if ticket.status not in (QueueStatus.WAITING, QueueStatus.CALLED):
                continue

            elapsed = (now - ticket.created_at).total_seconds() / 60
            if elapsed > max_wait_minutes:
                ticket.status = QueueStatus.EXPIRED
                ticket.expired_at = now
                expired_tickets.append(ticket)

                logger.info(
                    "queue_auto_expired",
                    ticket_no=ticket.ticket_no,
                    waited_minutes=round(elapsed),
                    max_wait_minutes=max_wait_minutes,
                )

        return expired_tickets
