"""
生日自动触发服务
检测当日/近期生日会员，自动生成通知和折扣
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class BirthdayBenefit:
    """生日权益"""
    benefit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    discount_rate: float = 1.0  # 折扣率（0.88=88折）
    free_dish: str = ""         # 赠送菜品名
    coupon_fen: int = 0         # 优惠券金额（分）
    valid_days: int = 7         # 有效期（天）

    @property
    def coupon_yuan(self) -> float:
        return round(self.coupon_fen / 100, 2)


@dataclass
class MemberInfo:
    """会员简要信息（纯内存模拟）"""
    member_id: str = ""
    name: str = ""
    phone: str = ""
    birthday: Optional[date] = None
    store_id: str = ""


@dataclass
class BirthdayNotification:
    """生日通知"""
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    member_id: str = ""
    member_name: str = ""
    benefit: Optional[BirthdayBenefit] = None
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent: bool = False


class BirthdayTriggerService:
    """生日自动触发服务"""

    def __init__(self):
        self._members: Dict[str, MemberInfo] = {}
        self._benefits: Dict[str, BirthdayBenefit] = {}
        self._notifications: List[BirthdayNotification] = []
        # 默认生日权益
        self._default_benefit = BirthdayBenefit(
            name="生日专享",
            discount_rate=0.88,
            free_dish="长寿面",
            coupon_fen=2000,  # 20元券
            valid_days=7,
        )
        self._benefits[self._default_benefit.benefit_id] = self._default_benefit

    def register_member(self, member: MemberInfo) -> None:
        """注册会员（模拟）"""
        self._members[member.member_id] = member

    def add_benefit(self, benefit: BirthdayBenefit) -> BirthdayBenefit:
        """添加生日权益方案"""
        self._benefits[benefit.benefit_id] = benefit
        return benefit

    def check_birthday_today(
        self,
        store_id: str,
        check_date: Optional[date] = None,
        advance_days: int = 0,
    ) -> List[MemberInfo]:
        """
        检查当日（或指定日期）生日的会员
        advance_days: 提前N天也算（用于提前通知）
        """
        target = check_date or date.today()
        matches = []
        for member in self._members.values():
            if member.store_id != store_id:
                continue
            if member.birthday is None:
                continue
            # 检查月日是否匹配（含提前天数）
            for offset in range(advance_days + 1):
                check = target + timedelta(days=offset)
                if member.birthday.month == check.month and member.birthday.day == check.day:
                    matches.append(member)
                    break
        logger.info("生日会员检测", store_id=store_id, date=str(target), count=len(matches))
        return matches

    def get_benefits(self, benefit_id: Optional[str] = None) -> BirthdayBenefit:
        """获取生日权益方案"""
        if benefit_id and benefit_id in self._benefits:
            return self._benefits[benefit_id]
        return self._default_benefit

    def generate_notification(
        self,
        member: MemberInfo,
        benefit: Optional[BirthdayBenefit] = None,
    ) -> BirthdayNotification:
        """为生日会员生成通知"""
        b = benefit or self._default_benefit
        message = (
            f"亲爱的{member.name}，祝您生日快乐！🎂\n"
            f"我们为您准备了生日专属权益：\n"
            f"• {b.discount_rate * 100:.0f}折生日优惠\n"
        )
        if b.free_dish:
            message += f"• 赠送{b.free_dish}一份\n"
        if b.coupon_fen > 0:
            message += f"• ¥{b.coupon_yuan}生日红包\n"
        message += f"有效期{b.valid_days}天，期待您的光临！"

        notif = BirthdayNotification(
            member_id=member.member_id,
            member_name=member.name,
            benefit=b,
            message=message,
        )
        self._notifications.append(notif)
        logger.info("生成生日通知", member=member.name, benefit=b.name)
        return notif

    def apply_discount(
        self,
        member_id: str,
        order_amount_fen: int,
        benefit_id: Optional[str] = None,
    ) -> Dict:
        """
        应用生日折扣
        返回折后金额和优惠详情
        """
        benefit = self.get_benefits(benefit_id)
        discounted_fen = int(order_amount_fen * benefit.discount_rate)
        savings_fen = order_amount_fen - discounted_fen

        result = {
            "member_id": member_id,
            "original_fen": order_amount_fen,
            "original_yuan": round(order_amount_fen / 100, 2),
            "discounted_fen": discounted_fen,
            "discounted_yuan": round(discounted_fen / 100, 2),
            "savings_fen": savings_fen,
            "savings_yuan": round(savings_fen / 100, 2),
            "discount_rate": benefit.discount_rate,
            "benefit_name": benefit.name,
            "free_dish": benefit.free_dish,
            "coupon_fen": benefit.coupon_fen,
            "coupon_yuan": benefit.coupon_yuan,
        }
        logger.info("应用生日折扣", member_id=member_id,
                     savings_yuan=result["savings_yuan"])
        return result

    def run_daily_check(self, store_id: str, advance_days: int = 3) -> List[BirthdayNotification]:
        """每日定时任务：检测生日会员并生成通知"""
        members = self.check_birthday_today(store_id, advance_days=advance_days)
        notifications = []
        for m in members:
            notif = self.generate_notification(m)
            notifications.append(notif)
        return notifications
