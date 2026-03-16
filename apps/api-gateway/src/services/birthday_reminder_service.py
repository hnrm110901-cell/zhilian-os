"""
BirthdayReminderService — 生日/入会周年事件触发器（EventScheduler P0）

扫描范围：
  - birthday（生日祝福）    : birth_date 的月/日 落在未来 horizon_days 天内
  - anniversary（周年纪念）: created_at 的月/日 落在未来 horizon_days 天内
                            且注册已满 1 年以上

设计原则：
  - 每个会员每种事件 30 天内不重复触发（通过排除 running 旅程实现）
  - 查询失败时返回空列表，不中断 Celery 任务
  - 每门店每批最多 200 条（保护 DB）
  - SQL 全参数化，无字符串拼接
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

EventType = Literal["birthday", "anniversary"]


@dataclass
class UpcomingEvent:
    """单条生日/周年事件。"""

    customer_id: str
    store_id: str
    wechat_openid: str | None
    event_type: EventType
    days_until: int  # 0 = 今天, 1 = 明天, ...


# ── SQL ──────────────────────────────────────────────────────────────────────

# 生日：birth_date 月/日 落在 [today, today+horizon_days]
# generate_series 确保只在指定天数范围内匹配，不受年份影响
_BIRTHDAY_SQL = text("""
    SELECT
        m.customer_id,
        m.store_id,
        m.wechat_openid,
        'birthday'                     AS event_type,
        (gs.d::date - CURRENT_DATE)    AS days_until
    FROM private_domain_members m
    JOIN generate_series(
        CURRENT_DATE,
        CURRENT_DATE + (:horizon_days * INTERVAL '1 day'),
        '1 day'
    ) AS gs(d) ON (
        EXTRACT(MONTH FROM m.birth_date) = EXTRACT(MONTH FROM gs.d)
        AND EXTRACT(DAY   FROM m.birth_date) = EXTRACT(DAY   FROM gs.d)
    )
    WHERE m.is_active    = true
      AND m.store_id     = :store_id
      AND m.birth_date   IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM private_domain_journeys j
          WHERE j.customer_id  = m.customer_id
            AND j.store_id     = m.store_id
            AND j.journey_type = 'birthday_greeting'
            AND j.status       = 'running'
            AND j.started_at  >= CURRENT_DATE - INTERVAL '30 days'
      )
    ORDER BY days_until ASC
    LIMIT 200
""")

# 周年：created_at 月/日 落在 [today, today+horizon_days]，且注册满1年
_ANNIVERSARY_SQL = text("""
    SELECT
        m.customer_id,
        m.store_id,
        m.wechat_openid,
        'anniversary'                  AS event_type,
        (gs.d::date - CURRENT_DATE)    AS days_until
    FROM private_domain_members m
    JOIN generate_series(
        CURRENT_DATE,
        CURRENT_DATE + (:horizon_days * INTERVAL '1 day'),
        '1 day'
    ) AS gs(d) ON (
        EXTRACT(MONTH FROM m.created_at) = EXTRACT(MONTH FROM gs.d)
        AND EXTRACT(DAY   FROM m.created_at) = EXTRACT(DAY   FROM gs.d)
    )
    WHERE m.is_active   = true
      AND m.store_id    = :store_id
      AND m.created_at <= CURRENT_TIMESTAMP - INTERVAL '1 year'
      AND NOT EXISTS (
          SELECT 1 FROM private_domain_journeys j
          WHERE j.customer_id  = m.customer_id
            AND j.store_id     = m.store_id
            AND j.journey_type = 'anniversary_greeting'
            AND j.status       = 'running'
            AND j.started_at  >= CURRENT_DATE - INTERVAL '30 days'
      )
    ORDER BY days_until ASC
    LIMIT 200
""")


# ── 核心服务 ──────────────────────────────────────────────────────────────────


class BirthdayReminderService:
    """
    扫描即将到来的生日/周年事件并返回待触发列表。

    每种事件 30 天内对同一会员只触发一次（排除已有 running 旅程）。
    查询出错时静默返回空列表，不向调用方抛出异常。
    """

    async def scan_upcoming_events(
        self,
        store_id: str,
        db: AsyncSession,
        *,
        horizon_days: int = 3,
    ) -> List[UpcomingEvent]:
        """
        扫描指定门店即将到来的生日和周年事件。

        Args:
            store_id:     门店 ID
            db:           异步 DB 会话
            horizon_days: 扫描窗口（天），默认 3

        Returns:
            按 days_until 升序排列的事件列表（最近的排前面）。
            查询失败时返回空列表。
        """
        params = {"store_id": store_id, "horizon_days": horizon_days}
        results: List[UpcomingEvent] = []

        for sql, event_type in (
            (_BIRTHDAY_SQL, "birthday"),
            (_ANNIVERSARY_SQL, "anniversary"),
        ):
            try:
                rows = (await db.execute(sql, params)).fetchall()
                results.extend(
                    UpcomingEvent(
                        customer_id=row[0],
                        store_id=row[1],
                        wechat_openid=row[2],
                        event_type=event_type,  # type: ignore[arg-type]
                        days_until=int(row[4]),
                    )
                    for row in rows
                )
            except Exception as exc:
                logger.warning(
                    "birthday_reminder.scan_failed",
                    store_id=store_id,
                    event_type=event_type,
                    error=str(exc),
                )

        logger.info(
            "birthday_reminder.scan_done",
            store_id=store_id,
            horizon_days=horizon_days,
            birthday_count=sum(1 for e in results if e.event_type == "birthday"),
            anniversary_count=sum(1 for e in results if e.event_type == "anniversary"),
        )
        return sorted(results, key=lambda e: e.days_until)
