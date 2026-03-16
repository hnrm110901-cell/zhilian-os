"""
JourneyNarrator — 私域旅程个性化消息生成引擎

核心功能：
  1. 基于会员消费行为推断马斯洛需求层级（L1-L5）
  2. 调用 Claude Haiku 实时生成自然语言消息（≤150字，单一CTA）
  3. 降级机制：API Key 未配置 / 调用失败 → 静态模板兜底，业务不中断

与 journey_orchestrator.py 集成：
  execute_step() 中替代 format_journey_message() 调用

马斯洛层级策略：
  L1（freq=0）   — 品质口碑，建立安全感
  L2（freq=1）   — 性价比，降低再次到店门槛
  L3（freq 2-5） — 场合适配，圈子认同，"请客有面子"
  L4（freq≥6）   — 专属感，被认识，不发通用折扣
  L5（freq≥6 且消费≥500元）— 探索体验，主厨故事
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()


# ── 会员画像 ──────────────────────────────────────────────────────────────────


@dataclass
class MemberProfile:
    """旅程个性化所需的会员核心画像（从 private_domain_members 读取）。"""

    frequency: int = 0  # 历史订单总笔数
    monetary: int = 0  # 历史消费总金额（分）
    recency_days: Optional[int] = None  # 距最近消费的天数（None=从未消费）
    lifecycle_state: Optional[str] = None  # 当前生命周期状态


# ── 马斯洛层级分类（纯函数）──────────────────────────────────────────────────

_LEVEL_LABELS = {
    1: "初次接触，尚未消费",
    2: "有过消费，建立初步信任",
    3: "多次消费，形成社交习惯",
    4: "高频忠实，渴望被认识",
    5: "深度忠诚，追求极致体验",
}

_LEVEL_STRATEGY = {
    1: "突出品质口碑和安全感，让顾客放心迈出第一步；不发折扣，发故事和口碑",
    2: "强调性价比和便利，降低再次到店门槛；可附送小额优惠",
    3: "突出场合适配和圈子认同，给顾客'请客有面子'的理由；可提及朋友聚餐场景",
    4: "强调专属感和被记住，让顾客感受到与众不同；不发通用折扣",
    5: "探索新品体验、主厨故事、食材溯源；顾客需要的是意义而非价格",
}


def classify_maslow_level(profile: MemberProfile) -> int:
    """
    基于消费行为推断马斯洛需求层级（L1-L5）。

    >>> classify_maslow_level(MemberProfile(frequency=0))
    1
    >>> classify_maslow_level(MemberProfile(frequency=1))
    2
    >>> classify_maslow_level(MemberProfile(frequency=3))
    3
    >>> classify_maslow_level(MemberProfile(frequency=8, monetary=30000))
    4
    >>> classify_maslow_level(MemberProfile(frequency=10, monetary=60000))
    5
    """
    freq = profile.frequency or 0
    monetary_yuan = (profile.monetary or 0) / 100

    if freq == 0:
        return 1
    if freq == 1:
        return 2
    if freq <= 5:
        return 3
    # freq >= 6
    return 5 if monetary_yuan >= 500 else 4


# ── 旅程步骤目的说明 ──────────────────────────────────────────────────────────

_TEMPLATE_PURPOSE: dict[str, str] = {
    "journey_welcome": "新会员入会后的第一条消息：欢迎加入，建立品牌第一印象",
    "journey_profile_prompt": "入会1天后：引导完善个人信息（生日/口味偏好），提升后续推荐精准度",
    "journey_first_visit_offer": "入会3天仍未到店：提供限时首单优惠，消除犹豫，促成第一次到店",
    "journey_menu_recommend": "注册6小时仍未下单：推荐当季招牌菜，激发食欲和好奇心",
    "journey_first_order_coupon": "注册1天仍未下单：发放首单折扣券，直接降低决策门槛",
    "journey_seasonal_content": "沉睡唤醒第一步：用内容而非折扣重建连接，唤起美好记忆",
    "journey_comeback_coupon": "沉睡唤醒第二步：发放回归优惠券，给顾客到店的具体理由",
    "journey_proactive_remind": "需求预测主动提醒：顾客即将进入消费周期，在他想来之前先打招呼，提升选择我们的概率",
}

# 静态降级模板（API 不可用时兜底）
_FALLBACK_TEMPLATES: dict[str, str] = {
    "journey_welcome": "欢迎加入！您已获得新会员专属优惠券，下次到店出示即可使用",
    "journey_profile_prompt": "您好！完善个人信息（生日/口味偏好）后可享受专属推荐，点击填写",
    "journey_first_visit_offer": "专属首单优惠限时领取，到店下单立减 ¥30，有效期3天，欢迎光临",
    "journey_menu_recommend": "为您精选当季招牌菜，点击查看今日推荐",
    "journey_first_order_coupon": "首单专属折扣券已发放，7天内有效，欢迎携友到店体验",
    "journey_seasonal_content": "时隔许久，我们想念您了！近期新品上线，欢迎回来品鉴",
    "journey_comeback_coupon": "专属回归礼遇券已送达，凭此券到店享受85折优惠，期待再见",
    "birthday_wish": "生日快乐！感谢一路陪伴，您的专属生日礼包已准备好，到店出示即可兑换",
    "anniversary_wish": "感谢一年来的陪伴！您已是我们的老朋友，专属周年礼已送达，欢迎到店领取",
}

_SYSTEM_PROMPT = """你是一位连锁餐饮品牌的私域运营专家，负责撰写发给顾客的企业微信消息。

输出规则：
1. 字数150字以内
2. 只有一个明确的行动号召
3. 语气自然亲切，像熟悉的朋友，不像营销机器人
4. 根据顾客需求层级选择价值主张：
   L1（初次接触）: 品质口碑、安全感，让顾客放心
   L2（初步信任）: 性价比、便利，降低再次到店门槛
   L3（社交习惯）: 场合适配、圈子认同，"请客有面子"
   L4（尊重需求）: 专属感、被认识，而非折扣
   L5（自我实现）: 探索体验、主厨故事、食材溯源
5. L1-L3 禁止使用"尊享""尊贵""专属VIP"等过度营销词
6. 只输出消息正文，不加引号或任何前缀"""


# ── 核心引擎 ──────────────────────────────────────────────────────────────────


class JourneyNarrator:
    """
    私域旅程个性化消息生成引擎。

    ANTHROPIC_API_KEY 未配置或 Claude 调用失败时，
    自动降级为静态模板，旅程发送不中断。
    """

    def __init__(self, llm=None):
        """
        Args:
            llm: 可注入的 LLM 客户端（测试用）。
                 不传时从环境变量懒初始化 AnthropicClient。
        """
        self._llm = llm

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            from src.core.llm import AnthropicClient, LLMModel

            self._llm = AnthropicClient(
                api_key=api_key,
                model=LLMModel.CLAUDE_HAIKU,  # 消息生成用 Haiku，快且省成本
            )
            return self._llm
        except Exception as exc:
            logger.warning("journey_narrator.llm_init_failed", error=str(exc))
            return None

    def _build_prompt(
        self,
        template_id: str,
        store_id: str,
        maslow_level: int,
        profile: MemberProfile,
    ) -> str:
        purpose = _TEMPLATE_PURPOSE.get(template_id, f"旅程步骤消息（{template_id}）")
        recency_desc = f"{profile.recency_days}天未到店" if profile.recency_days is not None else "首次加入"
        monetary_yuan = round((profile.monetary or 0) / 100)

        return (
            f"请为以下会员生成一条企微消息：\n\n"
            f"会员信息：\n"
            f"- 历史消费次数：{profile.frequency} 次\n"
            f"- 历史消费金额：约 ¥{monetary_yuan}\n"
            f"- 到店状态：{recency_desc}\n"
            f"- 需求层级：L{maslow_level}（{_LEVEL_LABELS[maslow_level]}）\n"
            f"- 运营策略：{_LEVEL_STRATEGY[maslow_level]}\n"
            f"- 门店编号：{store_id}\n\n"
            f"消息目的：{purpose}\n\n"
            f"直接输出消息正文："
        )

    async def generate(
        self,
        template_id: str,
        store_id: str,
        customer_id: str,
        profile: Optional[MemberProfile] = None,
    ) -> str:
        """
        生成个性化旅程消息。

        Args:
            template_id:  旅程步骤模板 ID
            store_id:     门店 ID
            customer_id:  会员 ID（用于日志追踪）
            profile:      会员画像（None 时按 L1 策略生成）

        Returns:
            个性化消息文本（≤150字）。失败时返回静态模板文本。
        """
        if profile is None:
            profile = MemberProfile()

        maslow_level = classify_maslow_level(profile)
        llm = self._get_llm()

        if llm is None:
            logger.debug(
                "journey_narrator.fallback_no_llm",
                template_id=template_id,
                customer_id=customer_id,
            )
            return _FALLBACK_TEMPLATES.get(template_id, "您有一条来自门店的消息")

        prompt = self._build_prompt(template_id, store_id, maslow_level, profile)

        try:
            text = await llm.generate(
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=200,
            )
            text = text.strip().strip('"').strip("'").strip()
            logger.info(
                "journey_narrator.generated",
                template_id=template_id,
                customer_id=customer_id,
                maslow_level=maslow_level,
                length=len(text),
            )
            return text or _FALLBACK_TEMPLATES.get(template_id, "您有一条来自门店的消息")
        except Exception as exc:
            logger.warning(
                "journey_narrator.llm_failed_fallback",
                template_id=template_id,
                customer_id=customer_id,
                error=str(exc),
            )
            return _FALLBACK_TEMPLATES.get(template_id, "您有一条来自门店的消息")
