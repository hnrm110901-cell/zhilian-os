"""
会员进度可见性引擎 — A4·方向八
基于《上瘾》进度条效应 + 《超级用户增长》+ 《关系飞轮》

核心洞见：让顾客永远看到一个"快完成了"的进度，是提升复购的低成本方法。
五个里程碑节点：首次消费满100元 / 距下一级别仅差1次 / 连续3个月 / 积分即将过期 / 年度周年日
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

# ── 会员等级定义 ──────────────────────────────────────────────────────────────


class MemberLevel(str, Enum):
    NEW_FRIEND    = "新朋友"     # 1-3 次
    REGULAR       = "熟客"       # 4-7 次
    OLD_FRIEND    = "老朋友"     # 8-15 次
    HONORED_GUEST = "荣誉食客"  # 16 次+


# 每个等级所需最低消费次数（默认值，可由门店级配置覆盖）
DEFAULT_LEVEL_THRESHOLDS: Dict[str, int] = {
    MemberLevel.NEW_FRIEND:    1,
    MemberLevel.REGULAR:       4,
    MemberLevel.OLD_FRIEND:    8,
    MemberLevel.HONORED_GUEST: 16,
}

# 向后兼容别名
LEVEL_MIN_VISITS = DEFAULT_LEVEL_THRESHOLDS


async def get_level_thresholds(db: Any = None, store_id: Any = None) -> Dict[str, int]:
    """获取门店级会员等级阈值配置，db/store_id 为 None 时降级使用默认值"""
    if db is None or store_id is None:
        return DEFAULT_LEVEL_THRESHOLDS
    try:
        from src.services.org_hierarchy_service import OrgHierarchyService
        svc = OrgHierarchyService(db)
        custom = await svc.resolve(store_id, "member_level_thresholds", default=None)
        return custom if custom else DEFAULT_LEVEL_THRESHOLDS
    except Exception:
        return DEFAULT_LEVEL_THRESHOLDS


# 每个等级的专属权益描述
LEVEL_PRIVILEGE: Dict[str, str] = {
    MemberLevel.NEW_FRIEND:    "消费积分2倍累计",
    MemberLevel.REGULAR:       "每月专属菜品优先品鉴资格",
    MemberLevel.OLD_FRIEND:    "节假日无需预约优先入座",
    MemberLevel.HONORED_GUEST: "厨师长新品试菜邀请",
}

_LEVEL_ORDER = [
    MemberLevel.NEW_FRIEND,
    MemberLevel.REGULAR,
    MemberLevel.OLD_FRIEND,
    MemberLevel.HONORED_GUEST,
]


def _get_level(total_visits: int) -> MemberLevel:
    for level in reversed(_LEVEL_ORDER):
        if total_visits >= LEVEL_MIN_VISITS[level]:
            return level
    return MemberLevel.NEW_FRIEND


def _next_level(current: MemberLevel) -> Optional[MemberLevel]:
    idx = _LEVEL_ORDER.index(current)
    return _LEVEL_ORDER[idx + 1] if idx < len(_LEVEL_ORDER) - 1 else None


def _visits_to_next_level(total_visits: int) -> Optional[int]:
    current = _get_level(total_visits)
    nxt = _next_level(current)
    if nxt is None:
        return None
    return LEVEL_MIN_VISITS[nxt] - total_visits


# ── 里程碑类型 ────────────────────────────────────────────────────────────────


class MilestoneType(str, Enum):
    FIRST_SPEND_100          = "first_spend_100"           # 首次消费满100元
    ONE_AWAY_FROM_NEXT_LEVEL = "one_away_from_next_level"  # 距下一级别仅差1次
    CONSECUTIVE_MONTHS_3     = "consecutive_months_3"      # 连续3个月消费
    POINTS_EXPIRING_7D       = "points_expiring_7d"        # 积分7天后过期
    ANNUAL_ANNIVERSARY       = "annual_anniversary"        # 第一次消费满1年


# ── 里程碑推送规则（文档方向八原文整理）────────────────────────────────────────

MILESTONE_PUSH_RULES: List[Dict[str, Any]] = [
    {
        "milestone": MilestoneType.FIRST_SPEND_100,
        "push_timing": "消费完成后15分钟",
        "psychology": "起点效应——第一次达到里程碑，参与感最强",
    },
    {
        "milestone": MilestoneType.ONE_AWAY_FROM_NEXT_LEVEL,
        "push_timing": "每次消费后实时触发",
        "psychology": "目标趋近效应——越接近目标，动力越强",
        "note": "只在N-1次触发，不要每次都推（会疲劳）",
    },
    {
        "milestone": MilestoneType.CONSECUTIVE_MONTHS_3,
        "push_timing": "连续消费达成时",
        "psychology": "《关系飞轮》：强调共同历史，而非交易记录",
        "forbidden": "不要在这里推优惠，优惠会把「关系」降维成「交易」",
    },
    {
        "milestone": MilestoneType.POINTS_EXPIRING_7D,
        "push_timing": "积分过期前第7天",
        "psychology": "损失厌恶，但要具体化可兑换内容，而不只是说「积分过期」",
    },
    {
        "milestone": MilestoneType.ANNUAL_ANNIVERSARY,
        "push_timing": "周年日当天",
        "psychology": "情感峰值时刻——年度里程碑是最强的关系加固节点",
    },
]


# ── 消息模板渲染 ──────────────────────────────────────────────────────────────


def build_push_message(milestone_type: MilestoneType, member: Dict[str, Any]) -> str:
    """
    根据里程碑类型和会员数据生成推送消息。
    遵循「认知友好」原则：具体 > 抽象，关系 > 交易，禁止折扣词汇。

    member 字段：
        store_name: str            门店名称
        total_visits: int          累计消费次数
        total_spend: float         累计消费金额
        points: int                当前积分
        points_expire_days: int    积分距过期天数
        favorite_dish: str         历史最爱菜品
        consecutive_months: int    连续消费月数
        first_visit_date: str      首次到店日期 YYYY-MM-DD
    """
    store_name        = member.get("store_name", "我们")
    total_visits      = member.get("total_visits", 1)
    points            = member.get("points", 0)
    points_expire_days = member.get("points_expire_days", 7)
    favorite_dish     = member.get("favorite_dish", "招牌菜")
    consecutive_months = member.get("consecutive_months", 3)

    current_level = _get_level(total_visits)
    nxt           = _next_level(current_level)
    to_next       = _visits_to_next_level(total_visits)
    next_privilege = LEVEL_PRIVILEGE.get(nxt, "") if nxt else ""

    if milestone_type == MilestoneType.FIRST_SPEND_100:
        remaining = to_next if to_next is not None else 0
        if remaining <= 0:
            remaining = 1
        return (
            f"恭喜！您刚刚成为{store_name}的「{MemberLevel.NEW_FRIEND.value}」\n"
            f"距离「{MemberLevel.REGULAR.value}」还差 {remaining} 次消费\n"
            f"[查看您的会员旅程]"
        )

    elif milestone_type == MilestoneType.ONE_AWAY_FROM_NEXT_LEVEL:
        if nxt is None:
            return (
                f"您已是{store_name}最高等级「{current_level.value}」，"
                f"感谢一路相伴 ❤️"
            )
        return (
            f"您距离「{nxt.value}」只差 1 次消费！\n"
            f"下次到店即可解锁「{next_privilege}」"
        )

    elif milestone_type == MilestoneType.CONSECUTIVE_MONTHS_3:
        return (
            f"您已经连续 {consecutive_months} 个月光顾我们了\n"
            f"这是我们共同的 {consecutive_months} 个月 📅\n"
            f"您喜欢的「{favorite_dish}」，一直都在"
        )

    elif milestone_type == MilestoneType.POINTS_EXPIRING_7D:
        return (
            f"您有 {points} 积分将在 {points_expire_days} 天后清零\n"
            f"可兑换：免费小食 / 饮品一杯 / 菜品升级（任选其一）\n"
            f"[立即查看兑换清单]"
        )

    elif milestone_type == MilestoneType.ANNUAL_ANNIVERSARY:
        return (
            f"一年前的今天，您第一次来{store_name}\n"
            f"这一年，您和我们一起经历了 {total_visits} 次相聚\n"
            f"今天，专属礼物等您来取 🎁"
        )

    return ""


# ── 核心检测函数 ──────────────────────────────────────────────────────────────


def check_milestones(
    member: Dict[str, Any],
    db: Any = None,
    store_id: Any = None,
    first_spend_threshold: float = 100.0,
    consecutive_months_threshold: int = 3,
    points_expiry_warning_days: int = 7,
) -> List[Dict[str, Any]]:
    """
    检查当前会员数据触发了哪些里程碑，返回触发列表。

    Args:
        member: 会员数据字典
            total_visits: int          累计消费次数（含本次）
            total_spend: float         本次消费后累计金额
            is_first_spend: bool       是否首次消费
            points: int                当前积分
            points_expire_days: int    积分距过期天数（None=无到期积分）
            consecutive_months: int    连续消费月数
            first_visit_date: str      首次到店日期 YYYY-MM-DD（None=未知）
            today: str                 当前日期 YYYY-MM-DD（测试可注入）
        db: 数据库会话（可选），用于读取门店级动态配置
        store_id: 门店ID（可选），与 db 配合读取门店级动态配置
        first_spend_threshold: 首次消费触发金额阈值，默认100元
        consecutive_months_threshold: 连续消费月数阈值，默认3个月
        points_expiry_warning_days: 积分过期预警天数，默认7天

    Returns:
        触发的里程碑列表，每项包含 milestone_type / message / psychology
    """
    triggered: List[Dict[str, Any]] = []

    total_visits       = member.get("total_visits", 0)
    total_spend        = member.get("total_spend", 0.0)
    is_first_spend     = member.get("is_first_spend", False)
    points             = member.get("points", 0)
    points_expire_days = member.get("points_expire_days", None)
    consecutive_months = member.get("consecutive_months", 0)
    first_visit_date_str: Optional[str] = member.get("first_visit_date")
    today_str: str     = member.get("today") or date.today().isoformat()
    today              = date.fromisoformat(today_str)

    # 1. 首次消费满阈值（起点效应），阈值可由门店级配置覆盖（默认100元）
    if is_first_spend and total_spend >= first_spend_threshold:
        triggered.append({
            "milestone_type": MilestoneType.FIRST_SPEND_100,
            "message":    build_push_message(MilestoneType.FIRST_SPEND_100, member),
            "psychology": "起点效应——第一次达到里程碑，参与感最强",
        })

    # 2. 距下一级别仅差1次（目标趋近效应）
    to_next = _visits_to_next_level(total_visits)
    if to_next is not None and to_next == 1:
        triggered.append({
            "milestone_type": MilestoneType.ONE_AWAY_FROM_NEXT_LEVEL,
            "message":    build_push_message(MilestoneType.ONE_AWAY_FROM_NEXT_LEVEL, member),
            "psychology": "目标趋近效应——越接近目标，动力越强",
        })

    # 3. 连续消费月数达阈值（关系飞轮），阈值可由门店级配置覆盖（默认3个月）
    if consecutive_months >= consecutive_months_threshold:
        triggered.append({
            "milestone_type": MilestoneType.CONSECUTIVE_MONTHS_3,
            "message":    build_push_message(MilestoneType.CONSECUTIVE_MONTHS_3, member),
            "psychology": "《关系飞轮》：强调共同历史，而非交易记录",
        })

    # 4. 积分将在预警天数内过期（损失厌恶，具体化兑换内容），天数可由门店级配置覆盖（默认7天）
    if points_expire_days is not None and 0 < points_expire_days <= points_expiry_warning_days and points > 0:
        triggered.append({
            "milestone_type": MilestoneType.POINTS_EXPIRING_7D,
            "message":    build_push_message(MilestoneType.POINTS_EXPIRING_7D, member),
            "psychology": "损失厌恶，但具体化可兑换内容",
        })

    # 5. 第一次消费满1年（情感峰值时刻）
    if first_visit_date_str:
        first_visit = date.fromisoformat(first_visit_date_str)
        try:
            anniversary = first_visit.replace(year=today.year)
        except ValueError:
            # 2月29日跨年处理
            anniversary = first_visit.replace(year=today.year, day=28)
        if anniversary == today:
            triggered.append({
                "milestone_type": MilestoneType.ANNUAL_ANNIVERSARY,
                "message":    build_push_message(MilestoneType.ANNUAL_ANNIVERSARY, member),
                "psychology": "情感峰值时刻——年度里程碑是最强的关系加固节点",
            })

    return triggered
