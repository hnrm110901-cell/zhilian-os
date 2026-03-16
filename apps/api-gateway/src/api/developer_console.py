"""
ISV 开发者控制台 API — Phase 4 Month 12

开发者视角的统一控制台：API 用量、插件健康、收入汇总、Webhook 状态。

Router prefix: /api/v1/console
Endpoints:
  GET  /developers/{dev_id}/overview   — 控制台首屏聚合（1 请求加载所有模块）
  POST /developers/{dev_id}/snapshot   — 触发快照计算（幂等，当天覆盖）
  GET  /developers/{dev_id}/trend      — 近 N 天 API 调用趋势
  GET  /developers/{dev_id}/plugins    — 插件健康列表（安装量 + 评分 + 告警）
  GET  /developers/{dev_id}/revenue    — 收入历史（结算记录汇总）
  GET  /developers/{dev_id}/webhooks   — Webhook 健康（成功率 / 失败）
  GET  /admin/leaderboard              — 管理端：开发者贡献排行榜
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/console", tags=["developer_console"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row(row) -> Dict[str, Any]:
    return dict(row._mapping)


def _float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


async def _require_developer(dev_id: str, db: AsyncSession) -> Dict[str, Any]:
    row = await db.execute(
        text("SELECT * FROM isv_developers WHERE id = :id"),
        {"id": dev_id},
    )
    dev = row.fetchone()
    if not dev:
        raise HTTPException(status_code=404, detail="开发者不存在")
    return _row(dev)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/developers/{dev_id}/overview")
async def get_console_overview(
    dev_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    控制台首屏聚合接口（BFF 模式）。
    一次请求返回：开发者基本信息、API 用量（本月）、插件汇总、
    待结算金额、Webhook 健康、最新快照。
    子查询失败降级返回 null，不阻断整体。
    """
    dev = await _require_developer(dev_id, db)
    today = date.today()
    month = f"{today.year}-{today.month:02d}"

    # ── API usage this month ──────────────────────────────────────────────────
    api_usage: Optional[Dict] = None
    try:
        row = await db.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN is_billable THEN 1 ELSE 0 END) AS billable "
                "FROM api_usage_logs "
                "WHERE developer_id = :did "
                "AND TO_CHAR(called_at, 'YYYY-MM') = :m"
            ),
            {"did": dev_id, "m": month},
        )
        r = row.fetchone()
        api_usage = {
            "month": month,
            "total_calls": r.total or 0,
            "billable_calls": r.billable or 0,
        }
    except Exception as exc:
        logger.warning("console_api_usage_failed", dev_id=dev_id, error=str(exc))

    # ── Plugin summary ────────────────────────────────────────────────────────
    plugin_summary: Optional[Dict] = None
    try:
        row = await db.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) AS published, "
                "SUM(install_count) AS installs, "
                "AVG(CASE WHEN rating_count > 0 THEN rating_avg END) AS avg_rating "
                "FROM marketplace_plugins WHERE developer_id = :did"
            ),
            {"did": dev_id},
        )
        r = row.fetchone()
        plugin_summary = {
            "total": r.total or 0,
            "published": r.published or 0,
            "total_installs": r.installs or 0,
            "avg_rating": round(_float(r.avg_rating), 2) if r.avg_rating else None,
        }
    except Exception as exc:
        logger.warning("console_plugin_summary_failed", dev_id=dev_id, error=str(exc))

    # ── Revenue (pending settlement) ──────────────────────────────────────────
    revenue_summary: Optional[Dict] = None
    try:
        row = await db.execute(
            text(
                "SELECT "
                "SUM(CASE WHEN status='pending' THEN net_payout_fen ELSE 0 END) AS pending_fen, "
                "SUM(CASE WHEN status='paid'    THEN net_payout_fen ELSE 0 END) AS paid_fen "
                "FROM revenue_share_records WHERE developer_id = :did"
            ),
            {"did": dev_id},
        )
        r = row.fetchone()
        pending_fen = r.pending_fen or 0
        paid_fen = r.paid_fen or 0
        revenue_summary = {
            "pending_yuan": round(pending_fen / 100, 2),
            "paid_yuan": round(paid_fen / 100, 2),
        }
    except Exception as exc:
        logger.warning("console_revenue_summary_failed", dev_id=dev_id, error=str(exc))

    # ── Webhook health ────────────────────────────────────────────────────────
    webhook_health: Optional[Dict] = None
    try:
        row = await db.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN failure_count > 0 THEN 1 ELSE 0 END) AS failing "
                "FROM webhook_subscriptions WHERE developer_id = :did AND status = 'active'"
            ),
            {"did": dev_id},
        )
        r = row.fetchone()
        webhook_health = {
            "active_count": r.total or 0,
            "failing_count": r.failing or 0,
        }
    except Exception as exc:
        logger.warning("console_webhook_health_failed", dev_id=dev_id, error=str(exc))

    # ── Latest snapshot ───────────────────────────────────────────────────────
    snapshot: Optional[Dict] = None
    try:
        row = await db.execute(
            text(
                "SELECT * FROM developer_console_snapshots " "WHERE developer_id = :did " "ORDER BY snapshot_date DESC LIMIT 1"
            ),
            {"did": dev_id},
        )
        s = row.fetchone()
        if s:
            snapshot = _row(s)
            for k in ("pending_settlement_yuan", "last_paid_yuan", "avg_rating", "api_quota_used_pct"):
                if snapshot.get(k) is not None:
                    snapshot[k] = _float(snapshot[k])
    except Exception as exc:
        logger.warning("console_latest_snapshot_failed", dev_id=dev_id, error=str(exc))

    return {
        "developer": {
            "id": dev["id"],
            "name": dev.get("company_name") or dev.get("name"),
            "tier": dev.get("tier", "free"),
            "status": dev.get("status"),
        },
        "api_usage": api_usage,
        "plugin_summary": plugin_summary,
        "revenue_summary": revenue_summary,
        "webhook_health": webhook_health,
        "latest_snapshot": snapshot,
        "as_of": today.isoformat(),
    }


@router.post("/developers/{dev_id}/snapshot", status_code=200)
async def compute_snapshot(
    dev_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    计算并存储今日快照（幂等，同日重复调用会覆盖数据）。
    """
    await _require_developer(dev_id, db)
    today = date.today()
    month = f"{today.year}-{today.month:02d}"

    # Gather data
    api_today = 0
    api_month = 0
    try:
        r = await db.execute(
            text(
                "SELECT "
                "SUM(CASE WHEN DATE(called_at) = :td THEN 1 ELSE 0 END) AS today_cnt, "
                "SUM(CASE WHEN TO_CHAR(called_at,'YYYY-MM') = :m THEN 1 ELSE 0 END) AS month_cnt "
                "FROM api_usage_logs WHERE developer_id = :did"
            ),
            {"did": dev_id, "td": today.isoformat(), "m": month},
        )
        res = r.fetchone()
        api_today = res.today_cnt or 0
        api_month = res.month_cnt or 0
    except Exception as exc:
        logger.warning("snapshot_api_usage_failed", dev_id=dev_id, error=str(exc))

    published = 0
    installs = 0
    avg_rating = None
    try:
        r = await db.execute(
            text(
                "SELECT "
                "SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) AS pub, "
                "SUM(install_count) AS inst, "
                "AVG(CASE WHEN rating_count > 0 THEN rating_avg END) AS avgr "
                "FROM marketplace_plugins WHERE developer_id = :did"
            ),
            {"did": dev_id},
        )
        res = r.fetchone()
        published = res.pub or 0
        installs = res.inst or 0
        avg_rating = round(_float(res.avgr), 2) if res.avgr else None
    except Exception as exc:
        logger.warning("snapshot_plugin_failed", dev_id=dev_id, error=str(exc))

    pending_yuan = 0.0
    last_paid_yuan = 0.0
    try:
        r = await db.execute(
            text(
                "SELECT "
                "SUM(CASE WHEN status='pending' THEN net_payout_fen ELSE 0 END) AS pend, "
                "MAX(CASE WHEN status='paid'    THEN net_payout_fen ELSE NULL END) AS paid "
                "FROM revenue_share_records WHERE developer_id = :did"
            ),
            {"did": dev_id},
        )
        res = r.fetchone()
        pending_yuan = round((res.pend or 0) / 100, 2)
        last_paid_yuan = round((res.paid or 0) / 100, 2)
    except Exception as exc:
        logger.warning("snapshot_revenue_failed", dev_id=dev_id, error=str(exc))

    webhook_count = 0
    webhook_failing = 0
    try:
        r = await db.execute(
            text(
                "SELECT COUNT(*) AS cnt, "
                "SUM(CASE WHEN failure_count > 0 THEN 1 ELSE 0 END) AS fail "
                "FROM webhook_subscriptions WHERE developer_id = :did AND status='active'"
            ),
            {"did": dev_id},
        )
        res = r.fetchone()
        webhook_count = res.cnt or 0
        webhook_failing = res.fail or 0
    except Exception as exc:
        logger.warning("snapshot_webhook_failed", dev_id=dev_id, error=str(exc))

    # Quota %: look up billing cycle
    quota_pct = 0.0
    try:
        r = await db.execute(
            text("SELECT free_quota, billable_calls " "FROM api_billing_cycles WHERE developer_id = :did AND period = :m"),
            {"did": dev_id, "m": month},
        )
        res = r.fetchone()
        if res and res.free_quota and res.free_quota > 0:
            quota_pct = round(min(res.billable_calls / res.free_quota * 100, 999.99), 2)
    except Exception as exc:
        logger.warning("snapshot_quota_failed", dev_id=dev_id, error=str(exc))

    snap_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO developer_console_snapshots "
            "(id, developer_id, snapshot_date, api_calls_today, api_calls_month, "
            "api_quota_used_pct, published_plugins, total_installs, avg_rating, "
            "pending_settlement_yuan, last_paid_yuan, "
            "webhook_count, webhook_failure_count) "
            "VALUES (:id, :did, :sd, :at, :am, :qp, :pub, :inst, :avgr, :py, :lpy, :wc, :wf) "
            "ON CONFLICT (developer_id, snapshot_date) DO UPDATE SET "
            "api_calls_today = EXCLUDED.api_calls_today, "
            "api_calls_month = EXCLUDED.api_calls_month, "
            "api_quota_used_pct = EXCLUDED.api_quota_used_pct, "
            "published_plugins = EXCLUDED.published_plugins, "
            "total_installs = EXCLUDED.total_installs, "
            "avg_rating = EXCLUDED.avg_rating, "
            "pending_settlement_yuan = EXCLUDED.pending_settlement_yuan, "
            "last_paid_yuan = EXCLUDED.last_paid_yuan, "
            "webhook_count = EXCLUDED.webhook_count, "
            "webhook_failure_count = EXCLUDED.webhook_failure_count"
        ),
        {
            "id": snap_id,
            "did": dev_id,
            "sd": today.isoformat(),
            "at": api_today,
            "am": api_month,
            "qp": quota_pct,
            "pub": published,
            "inst": installs,
            "avgr": avg_rating,
            "py": pending_yuan,
            "lpy": last_paid_yuan,
            "wc": webhook_count,
            "wf": webhook_failing,
        },
    )
    await db.commit()

    return {
        "snapshot_date": today.isoformat(),
        "api_calls_today": api_today,
        "api_calls_month": api_month,
        "api_quota_used_pct": quota_pct,
        "published_plugins": published,
        "total_installs": installs,
        "avg_rating": avg_rating,
        "pending_settlement_yuan": pending_yuan,
        "last_paid_yuan": last_paid_yuan,
        "webhook_count": webhook_count,
        "webhook_failure_count": webhook_failing,
    }


@router.get("/developers/{dev_id}/trend")
async def get_api_trend(
    dev_id: str,
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """近 N 天 API 调用趋势。"""
    await _require_developer(dev_id, db)
    since = date.today() - timedelta(days=days - 1)

    rows = await db.execute(
        text(
            "SELECT DATE(called_at) AS day, COUNT(*) AS cnt "
            "FROM api_usage_logs "
            "WHERE developer_id = :did AND DATE(called_at) >= :since "
            "GROUP BY DATE(called_at) ORDER BY day ASC"
        ),
        {"did": dev_id, "since": since.isoformat()},
    )
    db_data = {str(r.day): r.cnt for r in rows.fetchall()}

    # Fill in zero for missing days
    trend = []
    for i in range(days):
        d = str(since + timedelta(days=i))
        trend.append({"date": d, "calls": db_data.get(d, 0)})

    return {"developer_id": dev_id, "days": days, "trend": trend}


@router.get("/developers/{dev_id}/plugins")
async def get_developer_plugins_health(
    dev_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """开发者插件健康列表（安装量 + 评分 + 状态）。"""
    await _require_developer(dev_id, db)
    rows = await db.execute(
        text(
            "SELECT id, name, icon_emoji, category, status, "
            "install_count, rating_avg, rating_count, price_type, tier_required "
            "FROM marketplace_plugins WHERE developer_id = :did "
            "ORDER BY install_count DESC"
        ),
        {"did": dev_id},
    )
    plugins = []
    for r in rows.fetchall():
        p = _row(r)
        p["rating_avg"] = _float(p.get("rating_avg"))
        plugins.append(p)
    return {"developer_id": dev_id, "plugins": plugins, "total": len(plugins)}


@router.get("/developers/{dev_id}/revenue")
async def get_developer_revenue(
    dev_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """收入历史（近12期结算记录）。"""
    await _require_developer(dev_id, db)
    rows = await db.execute(
        text(
            "SELECT period, gross_revenue_fen, share_pct, net_payout_fen, status "
            "FROM revenue_share_records "
            "WHERE developer_id = :did "
            "ORDER BY period DESC LIMIT 12"
        ),
        {"did": dev_id},
    )
    records = []
    for r in rows.fetchall():
        d = _row(r)
        d["gross_revenue_yuan"] = round((d.get("gross_revenue_fen") or 0) / 100, 2)
        d["net_payout_yuan"] = round((d.get("net_payout_fen") or 0) / 100, 2)
        records.append(d)
    return {"developer_id": dev_id, "records": records, "total": len(records)}


@router.get("/developers/{dev_id}/webhooks")
async def get_developer_webhook_health(
    dev_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Webhook 健康状态（各订阅成功率）。"""
    await _require_developer(dev_id, db)
    rows = await db.execute(
        text(
            "SELECT s.id, s.endpoint_url, s.status, s.failure_count, s.last_triggered_at, "
            "COUNT(d.id) AS total_deliveries, "
            "SUM(CASE WHEN d.status = 'delivered' THEN 1 ELSE 0 END) AS success_cnt "
            "FROM webhook_subscriptions s "
            "LEFT JOIN webhook_delivery_logs d ON d.subscription_id = s.id "
            "WHERE s.developer_id = :did "
            "GROUP BY s.id, s.endpoint_url, s.status, s.failure_count, s.last_triggered_at "
            "ORDER BY s.created_at DESC"
        ),
        {"did": dev_id},
    )
    subs = []
    for r in rows.fetchall():
        d = _row(r)
        total = d.get("total_deliveries") or 0
        success = d.get("success_cnt") or 0
        d["success_rate_pct"] = round(success / total * 100, 1) if total > 0 else None
        subs.append(d)
    return {"developer_id": dev_id, "subscriptions": subs}


@router.get("/admin/leaderboard")
async def get_developer_leaderboard(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    管理端：开发者贡献排行榜（按累计净分成金额降序）。
    """
    rows = await db.execute(
        text(
            "SELECT d.id, d.company_name, d.tier, d.status, "
            "COUNT(DISTINCT p.id) AS plugin_count, "
            "SUM(p.install_count) AS total_installs, "
            "SUM(r.net_payout_fen) AS net_fen "
            "FROM isv_developers d "
            "LEFT JOIN marketplace_plugins p ON p.developer_id = d.id AND p.status = 'published' "
            "LEFT JOIN revenue_share_records r ON r.developer_id = d.id AND r.status = 'paid' "
            "GROUP BY d.id, d.company_name, d.tier, d.status "
            "ORDER BY net_fen DESC NULLS LAST "
            "LIMIT :lim"
        ),
        {"lim": limit},
    )
    board = []
    for i, r in enumerate(rows.fetchall()):
        d = _row(r)
        d["rank"] = i + 1
        d["net_yuan"] = round((d.get("net_fen") or 0) / 100, 2)
        d["total_installs"] = d.get("total_installs") or 0
        board.append(d)
    return {"leaderboard": board, "total": len(board)}
