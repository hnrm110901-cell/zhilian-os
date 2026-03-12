"""
DynamicPricingService — Agent-14 私域会员个性化定价策略

核心逻辑：
  1. 读取会员画像（frequency / monetary）→ 推断马斯洛层级
  2. 检测当前时段（午高峰 11-13 / 晚高峰 17-20 / 平峰）
  3. 返回对应层级的定价策略（折扣/套餐/专属礼遇/体验）

设计原则：
  - L1-L2：价格敏感，小额折扣降门槛
  - L3：社交驱动，组合套餐"请客有面子"
  - L4：专属感 > 折扣，优先席位/包厢预约
  - L5：体验 > 价格，主厨新品 / 食材溯源
  - 平峰时段 L2/L3 额外 1 折让利，提升非高峰客流
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any
import inspect

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .journey_narrator import MemberProfile, classify_maslow_level

logger = structlog.get_logger()


# ── 各层级策略配置 ──────────────────────────────────────────────────────────────

_OFFER_CONFIG: Dict[int, Dict[str, Any]] = {
    1: {
        "offer_type":     "quality_story",
        "title":          "品质首选",
        "description":    "精选当季食材，主厨匠心之作，欢迎您放心体验",
        "discount_pct":   0.0,
        "strategy_note":  "L1首次接触：强调品质口碑与安全感，不发折扣",
    },
    2: {
        "offer_type":     "discount_coupon",
        "title":          "回头客专属优惠",
        "description":    "感谢再次光临，享 88折 回头客专属优惠",
        "discount_pct":   8.8,
        "strategy_note":  "L2初步信任：性价比 + 小额折扣，降低再次到店门槛",
    },
    3: {
        "offer_type":     "group_bundle",
        "title":          "聚餐特惠套餐",
        "description":    "带朋友来更划算，3人及以上享 78折 聚餐特惠",
        "discount_pct":   7.8,
        "strategy_note":  "L3社交习惯：组合套餐「请客有面子」，场合适配",
    },
    4: {
        "offer_type":     "exclusive_access",
        "title":          "专属会员礼遇",
        "description":    "您是我们最熟悉的老朋友，优先预约包厢，店长专程接待",
        "discount_pct":   0.0,
        "strategy_note":  "L4尊重需求：专属感 > 折扣，不发通用优惠",
    },
    5: {
        "offer_type":     "experience",
        "title":          "主厨特别体验",
        "description":    "本周主厨新作邀您首品，附食材溯源故事——专为您保留",
        "discount_pct":   0.0,
        "strategy_note":  "L5自我实现：探索体验 + 主厨故事，意义 > 价格",
    },
}

# 午高峰 11-13h，晚高峰 17-20h（左闭右开）
_PEAK_WINDOWS = [(11, 13), (17, 20)]


# ── 数据模型 ───────────────────────────────────────────────────────────────────

@dataclass
class PricingOffer:
    """个性化定价推荐（单条）。"""
    offer_type:     str
    title:          str
    description:    str
    discount_pct:   float    # 0 = 无折扣；8.8 = 88折；7.8 = 78折
    maslow_level:   int
    strategy_note:  str
    is_peak_hour:   bool
    confidence:     float    # [0.3, 1.0]


# ── 核心服务 ───────────────────────────────────────────────────────────────────

class DynamicPricingService:
    """
    基于会员马斯洛层级 + 时段的个性化定价策略推荐。

    会员不存在时默认 L1 策略，DB 异常时同样降级到 L1，不中断调用方。
    """

    @staticmethod
    def _is_peak_hour(dt: datetime) -> bool:
        h = dt.hour
        return any(start <= h < end for start, end in _PEAK_WINDOWS)

    async def recommend(
        self,
        store_id: str,
        customer_id: str,
        db: AsyncSession,
        *,
        at: Optional[datetime] = None,
    ) -> PricingOffer:
        """
        为指定会员生成个性化定价策略。

        Args:
            store_id:    门店 ID
            customer_id: 会员 ID
            db:          异步 DB 会话
            at:          参考时间，None 时取 datetime.now()

        Returns:
            PricingOffer。会员不存在或 DB 失败均返回 L1 策略。
        """
        now = at or datetime.now()
        is_peak = self._is_peak_hour(now)

        profile = await self._load_profile(customer_id, store_id, db)
        level = classify_maslow_level(profile)

        config = dict(_OFFER_CONFIG[level])  # shallow copy，避免污染原始配置

        # 平峰时段 L2/L3 额外让利 1 折（提升非高峰客流）
        if not is_peak and level in (2, 3):
            config["discount_pct"] = round(config["discount_pct"] - 1.0, 1)
            config["description"] += "（平峰专享加码）"

        # 置信度：消费次数越多越可信，[0.3, 1.0]
        confidence = round(min(0.3 + profile.frequency * 0.07, 1.0), 2)

        logger.info(
            "dynamic_pricing.recommended",
            store_id=store_id,
            customer_id=customer_id,
            maslow_level=level,
            offer_type=config["offer_type"],
            is_peak=is_peak,
        )

        return PricingOffer(
            offer_type=config["offer_type"],
            title=config["title"],
            description=config["description"],
            discount_pct=config["discount_pct"],
            maslow_level=level,
            strategy_note=config["strategy_note"],
            is_peak_hour=is_peak,
            confidence=confidence,
        )

    async def _load_profile(
        self,
        customer_id: str,
        store_id: str,
        db: AsyncSession,
    ) -> MemberProfile:
        """从 DB 加载会员画像，失败时返回空画像（→ L1 降级）。"""
        sql = text("""
            SELECT frequency, monetary, recency_days, lifecycle_state
            FROM private_domain_members
            WHERE customer_id = :customer_id AND store_id = :store_id
            LIMIT 1
        """)
        try:
            result = await db.execute(sql, {"customer_id": customer_id, "store_id": store_id})
            row = await _maybe_await(result.fetchone())
            if row is None:
                return MemberProfile()
            return MemberProfile(
                frequency=int(row[0] or 0),
                monetary=int(row[1] or 0),
                recency_days=int(row[2]) if row[2] is not None else None,
                lifecycle_state=row[3],
            )
        except Exception as exc:
            logger.warning(
                "dynamic_pricing.load_profile_failed",
                customer_id=customer_id,
                store_id=store_id,
                error=str(exc),
            )
            return MemberProfile()


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value
