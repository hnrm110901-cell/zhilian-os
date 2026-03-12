"""
DemandPredictor — 私域会员到店需求预测（Agent-13）

核心算法：
  avg_interval_days = (最后一单 - 第一单) / (消费次数 - 1)
  days_until_visit  = avg_interval_days - recency_days
  若 0 ≤ days_until_visit ≤ horizon_days → 预测即将到店

用法：
  predictor = DemandPredictor()
  candidates = await predictor.scan_upcoming_visitors("S001", db, horizon_days=3)
  for c in candidates:
      await orch.trigger(c.customer_id, c.store_id, "proactive_remind", db,
                         wechat_user_id=c.wechat_openid)

设计原则（来自设计方案 Agent-13）：
  - 只处理 frequency ≥ 2 的会员（有历史规律可分析）
  - 排除 lost / lead 状态（无意义触达）
  - 排除已有进行中 proactive_remind 旅程的会员（防重复）
  - 每门店每批最多 100 人（保护 DB）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
import inspect

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


@dataclass
class DemandPrediction:
    """单条到店预测结果。"""
    customer_id: str
    store_id: str
    wechat_openid: str | None
    avg_interval_days: float     # 平均消费间隔（天）
    recency_days: int            # 距上次消费天数
    days_until_visit: float      # 预计距下次到店天数（可为负：已超期）
    order_count: int             # 历史消费次数（置信度参考）

    @property
    def confidence(self) -> float:
        """
        简单置信度：消费次数越多、模式越规律，置信度越高。
        范围 [0.3, 1.0]。
        """
        base = min(self.order_count / 10, 1.0)   # 10次消费 → 满分
        return round(max(base, 0.3), 2)


# ── SQL ───────────────────────────────────────────────────────────────────────

_SCAN_SQL = text("""
    WITH order_stats AS (
        SELECT
            customer_id,
            store_id,
            MIN(created_at)   AS first_order,
            MAX(created_at)   AS last_order,
            COUNT(*)          AS order_count
        FROM orders
        WHERE customer_id IS NOT NULL
          AND store_id = :store_id
        GROUP BY customer_id, store_id
    ),
    intervals AS (
        SELECT
            os.customer_id,
            os.store_id,
            os.order_count,
            EXTRACT(DAY FROM (os.last_order - os.first_order))
                / NULLIF(os.order_count - 1, 0)      AS avg_interval_days,
            m.recency_days,
            m.wechat_openid,
            m.lifecycle_state
        FROM order_stats os
        JOIN private_domain_members m
            ON  m.customer_id = os.customer_id
            AND m.store_id    = os.store_id
        WHERE os.order_count >= 2
          AND COALESCE(m.lifecycle_state, 'repeat')
              NOT IN ('lost', 'lead', 'registered')
    )
    SELECT
        customer_id,
        store_id,
        wechat_openid,
        order_count,
        avg_interval_days,
        recency_days,
        (avg_interval_days - recency_days) AS days_until_visit
    FROM intervals
    WHERE avg_interval_days IS NOT NULL
      AND avg_interval_days > 0
      AND (avg_interval_days - recency_days) BETWEEN 0 AND :horizon_days
      AND NOT EXISTS (
          SELECT 1 FROM private_domain_journeys j
          WHERE j.customer_id  = intervals.customer_id
            AND j.store_id     = intervals.store_id
            AND j.status       = 'running'
            AND j.journey_type = 'proactive_remind'
      )
    ORDER BY days_until_visit ASC
    LIMIT 100
""")


# ── 核心服务 ──────────────────────────────────────────────────────────────────

class DemandPredictor:
    """
    会员到店需求预测服务。

    基于历史消费间隔推算下次到店窗口，筛选出即将到店（≤horizon_days天）的会员。
    查询失败时返回空列表，不中断调用方流程。
    """

    async def scan_upcoming_visitors(
        self,
        store_id: str,
        db: AsyncSession,
        *,
        horizon_days: int = 3,
    ) -> List[DemandPrediction]:
        """
        扫描指定门店内预计将在 horizon_days 天内到店的会员。

        Args:
            store_id:     门店 ID
            db:           异步 DB 会话
            horizon_days: 预测窗口（天），默认 3（72h）

        Returns:
            按 days_until_visit 升序排列的预测列表（最近要到的排前面）。
            查询失败时返回空列表。
        """
        try:
            result = await db.execute(
                _SCAN_SQL,
                {"store_id": store_id, "horizon_days": horizon_days},
            )
            rows = await _maybe_await(result.fetchall())

            predictions = [
                DemandPrediction(
                    customer_id=row[0],
                    store_id=row[1],
                    wechat_openid=row[2],
                    order_count=int(row[3]),
                    avg_interval_days=float(row[4]),
                    recency_days=int(row[5]),
                    days_until_visit=float(row[6]),
                )
                for row in rows
            ]
            logger.info(
                "demand_predictor.scan_done",
                store_id=store_id,
                horizon_days=horizon_days,
                found=len(predictions),
            )
            return predictions

        except Exception as exc:
            logger.warning(
                "demand_predictor.scan_failed",
                store_id=store_id,
                error=str(exc),
            )
            return []


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value
