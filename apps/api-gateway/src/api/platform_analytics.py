"""Phase 3 Month 6 — 平台分析 (Platform Analytics)

商业化收尾：API 用量追踪、插件评分、平台生态总览与月度趋势。
"""

import uuid
from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/platform")

# ── Helpers ────────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    return dict(row._mapping) if row else {}


def _last_n_months(n: int) -> list[str]:
    """Return list of 'YYYY-MM' strings for the last n months, oldest first."""
    today = date.today()
    result = []
    year, month = today.year, today.month
    for _ in range(n):
        result.append(f"{year}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(result))


# ── Pydantic models ────────────────────────────────────────────────────────────


class LogUsageRequest(BaseModel):
    developer_id: str
    api_key: Optional[str] = None
    endpoint: str
    capability_level: int = 1
    is_billable: bool = False
    response_ms: Optional[int] = None


class RatePluginRequest(BaseModel):
    store_id: str
    rating: int  # 1-5
    comment: Optional[str] = None


# ── Commercial overview ────────────────────────────────────────────────────────


@router.get("/overview")
async def get_platform_overview(db: AsyncSession = Depends(get_db)):
    """Aggregate ecosystem KPIs across all tables."""
    dev_row = await db.execute(
        text("""
            SELECT
                COUNT(*)                                    AS total_developers,
                COUNT(*) FILTER (WHERE status = 'active')  AS active_developers,
                COUNT(*) FILTER (WHERE tier = 'free')      AS free_count,
                COUNT(*) FILTER (WHERE tier = 'basic')     AS basic_count,
                COUNT(*) FILTER (WHERE tier = 'pro')       AS pro_count,
                COUNT(*) FILTER (WHERE tier = 'enterprise') AS enterprise_count
            FROM isv_developers
        """),
    )
    devs = _row_to_dict(dev_row.first())

    plugin_row = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'published')        AS published_plugins,
                COUNT(*) FILTER (WHERE status = 'pending_review')   AS pending_plugins,
                COALESCE(SUM(install_count) FILTER (WHERE status = 'published'), 0) AS total_installs,
                COALESCE(AVG(rating_avg) FILTER (WHERE status = 'published' AND rating_count > 0), 0) AS avg_rating
            FROM marketplace_plugins
        """),
    )
    plugins = _row_to_dict(plugin_row.first())

    rev_row = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(gross_revenue_fen), 0)                             AS total_gross_fen,
                COALESCE(SUM(net_payout_fen), 0)                                AS total_net_fen,
                COUNT(*) FILTER (WHERE status = 'paid')                         AS paid_records,
                COUNT(*) FILTER (WHERE status = 'pending')                      AS pending_records
            FROM revenue_share_records
        """),
    )
    rev = _row_to_dict(rev_row.first())

    current_period = date.today().strftime("%Y-%m")
    curr_row = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(gross_revenue_fen), 0) AS gross_fen,
                COALESCE(SUM(net_payout_fen), 0)    AS net_fen
            FROM revenue_share_records WHERE period = :period
        """),
        {"period": current_period},
    )
    curr = _row_to_dict(curr_row.first())

    total_gross = rev.get("total_gross_fen") or 0
    total_net = rev.get("total_net_fen") or 0
    curr_gross = curr.get("gross_fen") or 0
    curr_net = curr.get("net_fen") or 0

    return {
        "total_developers": devs.get("total_developers") or 0,
        "active_developers": devs.get("active_developers") or 0,
        "by_tier": {
            "free": devs.get("free_count") or 0,
            "basic": devs.get("basic_count") or 0,
            "pro": devs.get("pro_count") or 0,
            "enterprise": devs.get("enterprise_count") or 0,
        },
        "published_plugins": plugins.get("published_plugins") or 0,
        "pending_plugins": plugins.get("pending_plugins") or 0,
        "total_installs": plugins.get("total_installs") or 0,
        "avg_plugin_rating": round(float(plugins.get("avg_rating") or 0), 2),
        "total_gross_revenue_fen": total_gross,
        "total_gross_revenue_yuan": total_gross / 100,
        "total_net_payout_fen": total_net,
        "total_net_payout_yuan": total_net / 100,
        "platform_profit_yuan": (total_gross - total_net) / 100,
        "current_month": current_period,
        "current_month_gross_yuan": curr_gross / 100,
        "current_month_net_yuan": curr_net / 100,
    }


@router.get("/trends")
async def get_revenue_trends(
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """Monthly revenue + developer-count trend for the last N months."""
    periods = _last_n_months(months)
    if not periods:
        return {"periods": [], "trends": []}

    rows = await db.execute(
        text("""
            SELECT period,
                   COALESCE(SUM(gross_revenue_fen), 0)    AS gross_fen,
                   COALESCE(SUM(net_payout_fen), 0)       AS net_fen,
                   COUNT(DISTINCT developer_id)           AS developer_count
            FROM revenue_share_records
            WHERE period >= :start AND period <= :end
            GROUP BY period
            ORDER BY period ASC
        """),
        {"start": periods[0], "end": periods[-1]},
    )
    by_period = {r.period: _row_to_dict(r) for r in rows.fetchall()}

    trends = []
    for period in periods:
        data = by_period.get(period, {})
        gross = data.get("gross_fen") or 0
        net = data.get("net_fen") or 0
        trends.append(
            {
                "period": period,
                "gross_yuan": gross / 100,
                "net_yuan": net / 100,
                "platform_profit_yuan": (gross - net) / 100,
                "developer_count": data.get("developer_count") or 0,
            }
        )

    return {"periods": periods, "trends": trends}


@router.get("/top-plugins")
async def get_top_plugins(
    limit: int = Query(default=10, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Top plugins by install count (published only)."""
    rows = await db.execute(
        text("""
            SELECT p.id, p.name, p.icon_emoji, p.category, p.version,
                   p.install_count, p.rating_avg, p.rating_count,
                   p.tier_required, p.price_type,
                   d.name AS developer_name
            FROM marketplace_plugins p
            JOIN isv_developers d ON d.id = p.developer_id
            WHERE p.status = 'published'
            ORDER BY p.install_count DESC, p.rating_avg DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    return {"plugins": [_row_to_dict(r) for r in rows.fetchall()]}


# ── API usage tracking ─────────────────────────────────────────────────────────


@router.post("/usage/log", status_code=201)
async def log_api_usage(body: LogUsageRequest, db: AsyncSession = Depends(get_db)):
    """Record a single API call. Called by middleware or ISV systems."""
    log_id = f"log_{uuid.uuid4().hex[:16]}"
    await db.execute(
        text("""
            INSERT INTO api_usage_logs
              (id, developer_id, api_key, endpoint, capability_level, is_billable, response_ms)
            VALUES
              (:id, :developer_id, :api_key, :endpoint, :capability_level, :is_billable, :response_ms)
        """),
        {
            "id": log_id,
            "developer_id": body.developer_id,
            "api_key": body.api_key,
            "endpoint": body.endpoint,
            "capability_level": body.capability_level,
            "is_billable": body.is_billable,
            "response_ms": body.response_ms,
        },
    )
    await db.commit()
    return {"log_id": log_id}


@router.get("/usage/stats")
async def get_usage_stats(
    developer_id: Optional[str] = None,
    period: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Platform or per-developer API usage statistics."""
    conditions = ["1=1"]
    params: dict = {}
    if developer_id:
        conditions.append("developer_id = :developer_id")
        params["developer_id"] = developer_id
    if period:
        conditions.append("TO_CHAR(called_at, 'YYYY-MM') = :period")
        params["period"] = period

    where = " AND ".join(conditions)

    stats_row = await db.execute(
        text(f"""
            SELECT
                COUNT(*)                                AS total_calls,
                COUNT(*) FILTER (WHERE is_billable)     AS billable_calls,
                COALESCE(AVG(response_ms), 0)          AS avg_response_ms,
                COUNT(DISTINCT developer_id)            AS unique_developers
            FROM api_usage_logs
            WHERE {where}
        """),
        params,
    )
    stats = _row_to_dict(stats_row.first())

    top_rows = await db.execute(
        text(f"""
            SELECT endpoint, COUNT(*) AS call_count
            FROM api_usage_logs
            WHERE {where}
            GROUP BY endpoint
            ORDER BY call_count DESC
            LIMIT 10
        """),
        params,
    )
    top_endpoints = [_row_to_dict(r) for r in top_rows.fetchall()]

    return {
        "total_calls": stats.get("total_calls") or 0,
        "billable_calls": stats.get("billable_calls") or 0,
        "avg_response_ms": round(float(stats.get("avg_response_ms") or 0), 1),
        "unique_developers": stats.get("unique_developers") or 0,
        "top_endpoints": top_endpoints,
    }


# ── Plugin ratings ─────────────────────────────────────────────────────────────


@router.post("/plugins/{plugin_id}/rate")
async def rate_plugin(
    plugin_id: str,
    body: RatePluginRequest,
    db: AsyncSession = Depends(get_db),
):
    if not (1 <= body.rating <= 5):
        raise HTTPException(status_code=400, detail="评分必须在 1-5 之间")

    plugin_check = await db.execute(
        text("SELECT id FROM marketplace_plugins WHERE id = :id AND status = 'published'"),
        {"id": plugin_id},
    )
    if not plugin_check.first():
        raise HTTPException(status_code=404, detail="插件不存在或未发布")

    install_check = await db.execute(
        text("SELECT 1 FROM plugin_installations WHERE plugin_id = :pid AND store_id = :sid"),
        {"pid": plugin_id, "sid": body.store_id},
    )
    if not install_check.first():
        raise HTTPException(status_code=403, detail="仅已安装的门店可以评分")

    rating_id = f"rat_{uuid.uuid4().hex[:12]}"
    await db.execute(
        text("""
            INSERT INTO plugin_ratings (id, plugin_id, store_id, rating, comment)
            VALUES (:id, :pid, :sid, :rating, :comment)
            ON CONFLICT (plugin_id, store_id) DO UPDATE
            SET rating = EXCLUDED.rating, comment = EXCLUDED.comment
        """),
        {"id": rating_id, "pid": plugin_id, "sid": body.store_id, "rating": body.rating, "comment": body.comment},
    )

    # Sync avg rating back to the plugin card
    await db.execute(
        text("""
            UPDATE marketplace_plugins SET
                rating_avg   = (SELECT AVG(rating::float) FROM plugin_ratings WHERE plugin_id = :id),
                rating_count = (SELECT COUNT(*)           FROM plugin_ratings WHERE plugin_id = :id)
            WHERE id = :id
        """),
        {"id": plugin_id},
    )
    await db.commit()
    logger.info("plugin_rated", plugin_id=plugin_id, store_id=body.store_id, rating=body.rating)
    return {"plugin_id": plugin_id, "store_id": body.store_id, "rating": body.rating}


@router.get("/plugins/{plugin_id}/ratings")
async def get_plugin_ratings(plugin_id: str, db: AsyncSession = Depends(get_db)):
    summary_row = await db.execute(
        text("""
            SELECT
                COALESCE(AVG(rating::float), 0)                AS avg_rating,
                COUNT(*)                                       AS total_ratings,
                COUNT(*) FILTER (WHERE rating = 5)             AS five_star_count,
                COUNT(*) FILTER (WHERE rating >= 4)            AS four_plus_count
            FROM plugin_ratings WHERE plugin_id = :id
        """),
        {"id": plugin_id},
    )
    summary = _row_to_dict(summary_row.first())

    rows = await db.execute(
        text("""
            SELECT id, store_id, rating, comment, created_at
            FROM plugin_ratings
            WHERE plugin_id = :id
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"id": plugin_id},
    )
    return {
        "plugin_id": plugin_id,
        "avg_rating": round(float(summary.get("avg_rating") or 0), 2),
        "total_ratings": summary.get("total_ratings") or 0,
        "five_star_count": summary.get("five_star_count") or 0,
        "four_plus_count": summary.get("four_plus_count") or 0,
        "ratings": [_row_to_dict(r) for r in rows.fetchall()],
    }
