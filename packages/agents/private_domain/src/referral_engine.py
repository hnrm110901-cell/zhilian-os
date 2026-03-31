"""
裂变场景自动识别引擎 — B3·方向五
基于《小群效应》+ 《黑客增长》病毒系数 + 《流量池》裂变三要素

核心洞见：
- 裂变最高 K 值的场景是「生日宴/家宴/商务宴请」——组织者会主动邀请多人
- 超级粉丝的裂变动机是「传递我的品位」而非「赚钱」
- 裂变内容不应是广告，而是「值得说的故事」

裂变三要素（《流量池》）：裂变诱饵 + 裂变工具 + 裂变钩子
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from src.services.org_hierarchy_service import OrgHierarchyService
    from sqlalchemy.ext.asyncio import AsyncSession
    _ORG_HIERARCHY_AVAILABLE = True
except ImportError:
    _ORG_HIERARCHY_AVAILABLE = False


# ── 裂变场景枚举 ──────────────────────────────────────────────────────────────


class ReferralScenario(str, Enum):
    BIRTHDAY_ORGANIZER = "birthday_organizer"  # 生日宴组织者
    FAMILY_BANQUET     = "family_banquet"      # 家宴组织者
    CORPORATE_HOST     = "corporate_host"      # 商务宴请东道主
    SUPER_FAN          = "super_fan"           # 月消费4次以上的超级用户


# ── 裂变剧本（裂变诱饵 + 裂变工具 + 裂变钩子）──────────────────────────────────
# 每个剧本遵循：不用折扣，用「身份/仪式/社交货币」作为诱饵

REFERRAL_PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    ReferralScenario.BIRTHDAY_ORGANIZER: {
        "trigger_timing": "订单中出现生日关键词后24小时",
        "bait": "生日宴「全桌免费拍照+专属生日菜」礼包（不是折扣）",
        "tool": "含专属码的「生日宴邀请函」H5（可分享到微信）",
        "hook": "每增加1位新朋友扫码加入，组织者额外获得1个神秘惊喜",
        "k_estimate": 3.2,
        "psychology": (
            "《小群效应》：邀请函要有组织者的名字，"
            "「王小明邀请您」比「餐厅邀请您」打开率高4倍"
        ),
    },
    ReferralScenario.FAMILY_BANQUET: {
        "trigger_timing": "6人以上订单完成后",
        "bait": "「本桌合影」服务（员工帮拍+品牌水印+发到组织者微信）",
        "tool": "合影图片内嵌餐厅信息 + 一键分享",
        "hook": "图片分享后，3人以上扫码，下次大桌9折",
        "k_estimate": 2.4,
        "psychology": (
            "《我们为什么买》：顾客在店时拍照分享概率比离店后高6倍，"
            "服务员主动拍照 >> 事后发分享请求"
        ),
    },
    ReferralScenario.CORPORATE_HOST: {
        "trigger_timing": "工作日中午大桌订单完成后",
        "bait": "「商务宴请专属席位」年度预约权（不是折扣，是特权）",
        "tool": "专属推荐链接（绑定推荐人ID，追踪到达顾客）",
        "hook": "推荐的客户成功订座后，推荐人收到「感谢支持」通知+积分",
        "k_estimate": 2.0,
        "psychology": (
            "商务场景：推荐动机是「我带朋友来的好地方」，"
            "强化东道主身份认同"
        ),
    },
    ReferralScenario.SUPER_FAN: {
        "trigger_timing": "累计消费满4次后",
        "bait": "「荣誉食客」身份 + 1张赠予好友的「首单免单」券",
        "tool": "专属推荐链接（绑定推荐人ID）",
        "hook": "好友消费后，推荐人收到「好友选择了您推荐的XX」的通知",
        "k_estimate": 1.8,
        "psychology": (
            "《影响力》社会证明：超级用户的动机是「分享自我认同」，"
            "不是「分享赚钱」——用「荣誉食客」标签激活身份认同"
        ),
    },
}


# ── 裂变信号检测 ──────────────────────────────────────────────────────────────


async def detect_referral_potential(
    customer: Dict[str, Any],
    order_history: List[Dict[str, Any]],
    db: Optional[Any] = None,
    store_id: Optional[str] = None,
) -> Optional[ReferralScenario]:
    """
    识别高裂变潜力场景，返回最优先的 ReferralScenario（或 None）。

    优先级：BIRTHDAY_ORGANIZER > FAMILY_BANQUET > CORPORATE_HOST > SUPER_FAN

    Args:
        customer: 顾客数据，含 total_visits_30d 等字段
        order_history: 订单列表，每项含 days_ago / party_size / tags / weekday / hour
        db: 可选数据库会话，用于读取动态配置
        store_id: 门店ID，与 db 配合使用

    Returns:
        ReferralScenario 或 None（不符合任何高K值场景）
    """
    # 读取动态配置（有 db 时从层级配置读取，否则使用默认值）
    if db is not None and store_id and _ORG_HIERARCHY_AVAILABLE:
        svc = OrgHierarchyService(db)
        family_min_party = await svc.resolve(store_id, "referral_family_min_party", default=6)
        business_lunch_hours = await svc.resolve(store_id, "referral_business_lunch_hours",
            default={"start": 11, "end": 13})
        business_min_party = await svc.resolve(store_id, "referral_business_min_party", default=4)
        super_fan_frequency = await svc.resolve(store_id, "referral_super_fan_frequency", default=4)
    else:
        family_min_party = 6
        business_lunch_hours = {"start": 11, "end": 13}
        business_min_party = 4
        super_fan_frequency = 4

    recent_orders = [o for o in order_history if o.get("days_ago", 999) <= 90]

    # 1. 生日宴组织者（优先级最高）
    has_birthday = any(
        "生日" in str(o.get("tags", "")) for o in recent_orders
    )
    if has_birthday:
        return ReferralScenario.BIRTHDAY_ORGANIZER

    # 2. 家宴组织者（大桌）
    avg_party_size = (
        sum(o.get("party_size", 2) for o in recent_orders)
        / max(len(recent_orders), 1)
    )
    if avg_party_size >= family_min_party:
        return ReferralScenario.FAMILY_BANQUET

    # 3. 商务宴请（工作日中午大桌）
    lunch_start = business_lunch_hours.get("start", 11)
    lunch_end = business_lunch_hours.get("end", 13)
    business_orders = [
        o for o in recent_orders
        if o.get("weekday", True)                                    # 工作日
        and lunch_start <= o.get("hour", 12) <= lunch_end            # 午餐时段
        and o.get("party_size", 2) >= business_min_party             # 最小人数
    ]
    if len(business_orders) >= 2:
        return ReferralScenario.CORPORATE_HOST

    # 4. 超级用户（近30天高频次）
    high_freq = len([o for o in order_history if o.get("days_ago", 999) <= 30]) >= super_fan_frequency
    if high_freq:
        return ReferralScenario.SUPER_FAN

    return None


async def get_playbook(
    scenario: ReferralScenario,
    db: Optional[Any] = None,
    store_id: Optional[str] = None,
) -> Dict[str, Any]:
    """返回指定裂变场景的完整剧本（诱饵/工具/钩子/K值预估）。
    有 db 时从层级配置读取动态 K 值并覆盖静态默认值。
    """
    playbook = dict(REFERRAL_PLAYBOOKS[scenario])

    if db is not None and store_id and _ORG_HIERARCHY_AVAILABLE:
        svc = OrgHierarchyService(db)
        viral_coefficients = await svc.resolve(store_id, "referral_viral_coefficients", default={
            "birthday": 3.2, "family": 2.4, "business": 2.0, "super_fan": 1.8
        })
        _k_map = {
            ReferralScenario.BIRTHDAY_ORGANIZER: "birthday",
            ReferralScenario.FAMILY_BANQUET: "family",
            ReferralScenario.CORPORATE_HOST: "business",
            ReferralScenario.SUPER_FAN: "super_fan",
        }
        key = _k_map.get(scenario)
        if key and key in viral_coefficients:
            playbook["k_estimate"] = viral_coefficients[key]

        # 生日宴：动态触发延迟小时数
        if scenario == ReferralScenario.BIRTHDAY_ORGANIZER:
            birthday_delay_hours = await svc.resolve(store_id, "referral_birthday_delay_hours", default=24)
            playbook["birthday_delay_hours"] = birthday_delay_hours
            playbook["trigger_timing"] = f"订单中出现生日关键词后{birthday_delay_hours}小时"

    return playbook


async def detect_and_get_playbook(
    customer: Dict[str, Any],
    order_history: List[Dict[str, Any]],
    db: Optional[Any] = None,
    store_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    一步返回裂变场景 + 剧本。

    Returns:
        { "scenario": ReferralScenario, "playbook": {...} } 或 None
    """
    scenario = await detect_referral_potential(customer, order_history, db=db, store_id=store_id)
    if scenario is None:
        return None
    return {
        "scenario": scenario,
        "playbook": await get_playbook(scenario, db=db, store_id=store_id),
    }
