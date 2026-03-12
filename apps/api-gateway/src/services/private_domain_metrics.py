"""
私域增长驾驶舱指标服务
Private Domain Growth Metrics Service

私域三角 KPI：
  ① 自有流量  — 私域规模（会员数、活跃率、企微连接数）
  ② 客户价值  — 盈利能力（复购率、LTV、AOV）
  ③ 旅程健康  — 运营效率（旅程完成率、频控触达数）

以及生命周期漏斗（使用 lifecycle_state 字段聚合）。

所有查询容错（catch Exception → 返回 0 / 空结构），
不影响页面正常渲染。
"""

from __future__ import annotations

import datetime
import inspect
from typing import Any, Dict

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


# ── 内部 helpers ──────────────────────────────────────────────────────────────

async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _scalar(db: AsyncSession, sql: str, params: dict, default=0):
    """执行 SQL 并返回第一行第一列，失败则返回 default。"""
    try:
        result = await db.execute(text(sql), params)
        row = await _maybe_await(result.fetchone())
        return row[0] if row and row[0] is not None else default
    except Exception as exc:
        logger.warning("private_domain_metrics.query_failed", sql=sql[:60], error=str(exc))
        return default


async def _rows(db: AsyncSession, sql: str, params: dict) -> list:
    """执行 SQL 并返回所有行，失败则返回空列表。"""
    try:
        result = await db.execute(text(sql), params)
        rows = await _maybe_await(result.fetchall())
        return list(rows or [])
    except Exception as exc:
        logger.warning("private_domain_metrics.query_failed", sql=sql[:60], error=str(exc))
        return []


# ── 自有流量（Owned Audience）─────────────────────────────────────────────────

async def get_owned_audience(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    自有流量核心指标：
      total_members     — 私域会员总数
      active_members    — 近30天活跃（recency_days ≤ 30）
      active_rate       — 活跃率
      wxwork_connected  — 已连接企微（wechat_openid NOT NULL）
      new_this_month    — 本月新增
    """
    today = datetime.date.today()
    month_start = today.replace(day=1)

    total = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :store_id
    """, {"store_id": store_id})

    active = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :store_id AND recency_days <= 30
    """, {"store_id": store_id})

    connected = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :store_id AND wechat_openid IS NOT NULL
    """, {"store_id": store_id})

    new_this_month = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :store_id AND created_at::date >= :month_start
    """, {"store_id": store_id, "month_start": month_start.isoformat()})

    active_rate = round(active / total, 3) if total > 0 else 0.0
    connect_rate = round(connected / total, 3) if total > 0 else 0.0

    return {
        "total_members":     int(total),
        "active_members":    int(active),
        "active_rate":       active_rate,
        "wxwork_connected":  int(connected),
        "connect_rate":      connect_rate,
        "new_this_month":    int(new_this_month),
    }


# ── 客户价值（Customer Value）─────────────────────────────────────────────────

async def get_customer_value(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    客户价值核心指标：
      repeat_rate_30d       — 近30天下单客户中复购率（frequency>1）
      avg_ltv_yuan          — 会员平均历史消费（元）
      avg_order_value_yuan  — 近30天平均客单价（元）
      avg_orders_per_member — 会员平均累计订单数
    """
    since_30d = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    # 复购率：近30天有订单的客户中 frequency>1 的比例
    total_buyers_30d = await _scalar(db, """
        SELECT COUNT(DISTINCT o.customer_id)
        FROM orders o
        WHERE o.store_id = :store_id
          AND o.created_at::date >= :since
          AND o.customer_id IS NOT NULL
    """, {"store_id": store_id, "since": since_30d})

    repeat_buyers_30d = await _scalar(db, """
        SELECT COUNT(DISTINCT o.customer_id)
        FROM orders o
        JOIN private_domain_members m
          ON m.store_id = o.store_id AND m.customer_id = o.customer_id
        WHERE o.store_id = :store_id
          AND o.created_at::date >= :since
          AND o.customer_id IS NOT NULL
          AND m.frequency > 1
    """, {"store_id": store_id, "since": since_30d})

    # 平均 LTV（分 → 元）
    avg_ltv_fen = await _scalar(db, """
        SELECT AVG(monetary) FROM private_domain_members
        WHERE store_id = :store_id AND monetary > 0
    """, {"store_id": store_id}, default=0)

    # 近30天平均客单价（分 → 元）
    avg_aov_fen = await _scalar(db, """
        SELECT AVG(total_amount)
        FROM orders
        WHERE store_id = :store_id
          AND created_at::date >= :since
          AND total_amount > 0
    """, {"store_id": store_id, "since": since_30d}, default=0)

    # 人均累计订单数
    avg_freq = await _scalar(db, """
        SELECT AVG(frequency::float) FROM private_domain_members
        WHERE store_id = :store_id AND frequency > 0
    """, {"store_id": store_id}, default=0)

    repeat_rate = round(repeat_buyers_30d / total_buyers_30d, 3) if total_buyers_30d > 0 else 0.0

    return {
        "repeat_rate_30d":       repeat_rate,
        "avg_ltv_yuan":          round(float(avg_ltv_fen) / 100, 2),
        "avg_order_value_yuan":  round(float(avg_aov_fen) / 100, 2),
        "avg_orders_per_member": round(float(avg_freq), 1),
    }


# ── 旅程健康（Journey Health / Referral Power）────────────────────────────────

async def get_journey_health(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    旅程健康指标：
      running_journeys    — 进行中旅程数
      completed_journeys  — 已完成旅程数
      total_journeys      — 总旅程数（近90天）
      completion_rate     — 完成率
      bad_review_signals  — 近30天差评信号数（负向代理指标）
      churn_risk_count    — 高流失风险会员数（risk_score ≥ 0.6）
    """
    since_90d = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    since_30d = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    running = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_journeys
        WHERE store_id = :store_id AND status = 'running'
    """, {"store_id": store_id})

    completed = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_journeys
        WHERE store_id = :store_id AND status = 'completed'
          AND started_at::date >= :since
    """, {"store_id": store_id, "since": since_90d})

    total_90d = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_journeys
        WHERE store_id = :store_id AND started_at::date >= :since
    """, {"store_id": store_id, "since": since_90d})

    bad_review = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_signals
        WHERE store_id = :store_id
          AND signal_type = 'bad_review'
          AND triggered_at::date >= :since
    """, {"store_id": store_id, "since": since_30d})

    churn_risk = await _scalar(db, """
        SELECT COUNT(*) FROM private_domain_members
        WHERE store_id = :store_id AND risk_score >= 0.6
    """, {"store_id": store_id})

    completion_rate = round(completed / total_90d, 3) if total_90d > 0 else 0.0

    return {
        "running_journeys":   int(running),
        "completed_journeys": int(completed),
        "total_journeys_90d": int(total_90d),
        "completion_rate":    completion_rate,
        "bad_review_signals": int(bad_review),
        "churn_risk_count":   int(churn_risk),
    }


# ── 生命周期漏斗（Lifecycle Funnel）──────────────────────────────────────────

_LIFECYCLE_STATES = [
    "lead", "registered", "first_order_pending",
    "repeat", "high_frequency", "vip",
    "at_risk", "dormant", "lost",
]


async def get_lifecycle_funnel(store_id: str, db: AsyncSession) -> Dict[str, int]:
    """
    按 lifecycle_state 字段聚合会员分布。
    未设置 lifecycle_state 的会员通过 recency_days 粗分：
      recency_days=0 AND frequency=0 → first_order_pending
      否则 → repeat
    """
    # 已有 lifecycle_state 的分布
    rows = await _rows(db, """
        SELECT COALESCE(lifecycle_state, '_unknown') AS state,
               COUNT(*)::int AS cnt
        FROM private_domain_members
        WHERE store_id = :store_id
        GROUP BY lifecycle_state
    """, {"store_id": store_id})

    funnel: Dict[str, int] = {s: 0 for s in _LIFECYCLE_STATES}
    unknown_count = 0
    for row in rows:
        state, cnt = row[0], int(row[1])
        if state == "_unknown":
            unknown_count += cnt
        elif state in funnel:
            funnel[state] += cnt

    # 将 unknown 按 frequency=0 分配到 first_order_pending，其余到 repeat
    if unknown_count > 0:
        fop = await _scalar(db, """
            SELECT COUNT(*) FROM private_domain_members
            WHERE store_id = :store_id
              AND lifecycle_state IS NULL
              AND frequency = 0
        """, {"store_id": store_id})
        funnel["first_order_pending"] += int(fop)
        funnel["repeat"] += max(0, unknown_count - int(fop))

    return funnel


# ── 对外聚合接口 ──────────────────────────────────────────────────────────────

async def get_full_metrics(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    汇总全部私域指标。每个子查询独立容错，互不影响。

    Returns:
        {
            "store_id":         str,
            "as_of":            ISO datetime,
            "owned_audience":   {...},
            "customer_value":   {...},
            "journey_health":   {...},
            "lifecycle_funnel": {"repeat": 650, ...},
        }
    """
    # 并发查询（SQLAlchemy async session 不支持真正的并发，
    # 但顺序执行在同一连接上已足够快）
    audience  = await get_owned_audience(store_id, db)
    cvalue    = await get_customer_value(store_id, db)
    journeys  = await get_journey_health(store_id, db)
    funnel    = await get_lifecycle_funnel(store_id, db)

    return {
        "store_id":         store_id,
        "as_of":            datetime.datetime.utcnow().isoformat(),
        "owned_audience":   audience,
        "customer_value":   cvalue,
        "journey_health":   journeys,
        "lifecycle_funnel": funnel,
    }
