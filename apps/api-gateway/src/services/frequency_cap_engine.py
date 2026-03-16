"""
频控引擎
Frequency Cap Engine

防止对会员过度骚扰，遵守企业微信官方限制。

纯函数（无副作用）：
  make_daily_key(person_id, store_id, channel)  → str
  make_weekly_key(person_id, store_id, channel) → str
  is_quiet_hours(hour)                           → bool
  get_channel_daily_limit(channel)               → int
  get_channel_weekly_limit(channel)              → int

服务类（依赖 Redis）：
  FrequencyCapEngine.can_send(person_id, store_id, channel) → bool
  FrequencyCapEngine.record_send(person_id, store_id, channel) → None
  FrequencyCapEngine.get_counts(person_id, store_id, channel) → dict
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Optional

import structlog

logger = structlog.get_logger()

# ── 频控限制（环境变量可覆盖）──────────────────────────────────────────────────
# 企业微信每人每天最多1条，每周最多3条（官方建议）
_WXWORK_DAILY_LIMIT = int(os.getenv("FC_WXWORK_DAILY_LIMIT", "1"))
_WXWORK_WEEKLY_LIMIT = int(os.getenv("FC_WXWORK_WEEKLY_LIMIT", "3"))

# 小程序订阅消息
_MINIAPP_DAILY_LIMIT = int(os.getenv("FC_MINIAPP_DAILY_LIMIT", "2"))
_MINIAPP_WEEKLY_LIMIT = int(os.getenv("FC_MINIAPP_WEEKLY_LIMIT", "5"))

# 短信（成本高，限制更严）
_SMS_DAILY_LIMIT = int(os.getenv("FC_SMS_DAILY_LIMIT", "1"))
_SMS_WEEKLY_LIMIT = int(os.getenv("FC_SMS_WEEKLY_LIMIT", "2"))

# 勿扰时间：22:00-09:00
_QUIET_START = int(os.getenv("FC_QUIET_START", "22"))
_QUIET_END = int(os.getenv("FC_QUIET_END", "9"))

# Redis key TTL
_DAY_TTL = 86400  # 24h
_WEEK_TTL = 604800  # 7d

SUPPORTED_CHANNELS = ("wxwork", "miniapp", "sms")


# ── 纯函数 ────────────────────────────────────────────────────────────────────


def make_daily_key(person_id: str, store_id: str, channel: str) -> str:
    """
    生成每日频控 Redis key（按自然日重置）。

    格式：fc:daily:{channel}:{store_id}:{person_id}:{YYYYMMDD}
    """
    today = datetime.utcnow().strftime("%Y%m%d")
    return f"fc:daily:{channel}:{store_id}:{person_id}:{today}"


def make_weekly_key(person_id: str, store_id: str, channel: str) -> str:
    """
    生成每周频控 Redis key（按 ISO 周重置）。

    格式：fc:weekly:{channel}:{store_id}:{person_id}:{YYYY-W{week}}
    """
    now = datetime.utcnow()
    week = now.strftime("%Y-W%W")
    return f"fc:weekly:{channel}:{store_id}:{person_id}:{week}"


def is_quiet_hours(hour: Optional[int] = None) -> bool:
    """
    检查当前是否处于勿扰时段（默认 22:00-09:00）。

    Args:
        hour: 当前小时（0-23），None 时取 datetime.utcnow()
    """
    if hour is None:
        hour = datetime.utcnow().hour
    if _QUIET_START < _QUIET_END:
        # 正常时段（如 01:00-06:00）
        return _QUIET_START <= hour < _QUIET_END
    else:
        # 跨午夜时段（如 22:00-09:00）
        return hour >= _QUIET_START or hour < _QUIET_END


def get_channel_daily_limit(channel: str) -> int:
    """返回指定渠道的每日发送上限。"""
    return {
        "wxwork": _WXWORK_DAILY_LIMIT,
        "miniapp": _MINIAPP_DAILY_LIMIT,
        "sms": _SMS_DAILY_LIMIT,
    }.get(channel, 1)


def get_channel_weekly_limit(channel: str) -> int:
    """返回指定渠道的每周发送上限。"""
    return {
        "wxwork": _WXWORK_WEEKLY_LIMIT,
        "miniapp": _MINIAPP_WEEKLY_LIMIT,
        "sms": _SMS_WEEKLY_LIMIT,
    }.get(channel, 3)


# ── 服务类 ────────────────────────────────────────────────────────────────────


class FrequencyCapEngine:
    """
    频控引擎（依赖 Redis）。

    用法：
        engine = FrequencyCapEngine(redis_client)
        if await engine.can_send(person_id, store_id, "wxwork"):
            await send_message(...)
            await engine.record_send(person_id, store_id, "wxwork")
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def can_send(
        self,
        person_id: str,
        store_id: str,
        channel: str,
        *,
        respect_quiet_hours: bool = True,
    ) -> bool:
        """
        检查是否允许向该用户在该渠道发送消息。

        返回 False 的情况：
          1. 当前处于勿扰时段（且 respect_quiet_hours=True）
          2. 今日该渠道发送次数已达上限
          3. 本周该渠道发送次数已达上限
          4. Redis 不可用（降级为允许发送，避免阻断业务）

        Args:
            person_id:           会员/客户ID
            store_id:            门店ID
            channel:             渠道（wxwork / miniapp / sms）
            respect_quiet_hours: 是否遵守勿扰时段（默认 True）
        """
        if respect_quiet_hours and is_quiet_hours():
            logger.debug(
                "freq_cap.quiet_hours",
                person_id=person_id,
                channel=channel,
                hour=datetime.utcnow().hour,
            )
            return False

        if not self._redis:
            return True  # Redis 不可用时降级允许

        try:
            daily_key = make_daily_key(person_id, store_id, channel)
            weekly_key = make_weekly_key(person_id, store_id, channel)

            daily_count = int(await self._redis.get(daily_key) or 0)
            weekly_count = int(await self._redis.get(weekly_key) or 0)

            if daily_count >= get_channel_daily_limit(channel):
                logger.debug(
                    "freq_cap.daily_limit_reached",
                    person_id=person_id,
                    channel=channel,
                    daily_count=daily_count,
                    limit=get_channel_daily_limit(channel),
                )
                return False

            if weekly_count >= get_channel_weekly_limit(channel):
                logger.debug(
                    "freq_cap.weekly_limit_reached",
                    person_id=person_id,
                    channel=channel,
                    weekly_count=weekly_count,
                    limit=get_channel_weekly_limit(channel),
                )
                return False

            return True

        except Exception as e:
            logger.warning("freq_cap.redis_error", error=str(e))
            return True  # Redis 故障时降级允许，不阻断发送

    async def record_send(
        self,
        person_id: str,
        store_id: str,
        channel: str,
    ) -> None:
        """
        记录一次发送，递增日/周计数器。

        消息实际发送成功后调用。
        """
        if not self._redis:
            return

        try:
            daily_key = make_daily_key(person_id, store_id, channel)
            weekly_key = make_weekly_key(person_id, store_id, channel)

            await self._redis.incr(daily_key)
            await self._redis.expire(daily_key, _DAY_TTL)

            await self._redis.incr(weekly_key)
            await self._redis.expire(weekly_key, _WEEK_TTL)

            logger.debug(
                "freq_cap.recorded",
                person_id=person_id,
                store_id=store_id,
                channel=channel,
            )

        except Exception as e:
            logger.warning("freq_cap.record_error", error=str(e))

    async def get_counts(
        self,
        person_id: str,
        store_id: str,
        channel: str,
    ) -> Dict[str, int]:
        """
        查询当前发送计数（用于调试/看板）。

        Returns:
            {"daily": int, "daily_limit": int, "weekly": int, "weekly_limit": int}
        """
        if not self._redis:
            return {
                "daily": 0,
                "daily_limit": get_channel_daily_limit(channel),
                "weekly": 0,
                "weekly_limit": get_channel_weekly_limit(channel),
            }

        try:
            daily_key = make_daily_key(person_id, store_id, channel)
            weekly_key = make_weekly_key(person_id, store_id, channel)

            daily = int(await self._redis.get(daily_key) or 0)
            weekly = int(await self._redis.get(weekly_key) or 0)

            return {
                "daily": daily,
                "daily_limit": get_channel_daily_limit(channel),
                "weekly": weekly,
                "weekly_limit": get_channel_weekly_limit(channel),
            }

        except Exception as e:
            logger.warning("freq_cap.get_counts_error", error=str(e))
            return {
                "daily": 0,
                "daily_limit": get_channel_daily_limit(channel),
                "weekly": 0,
                "weekly_limit": get_channel_weekly_limit(channel),
            }
