"""Phase 3 Month 5 — 收入分成 (Revenue Sharing)

ISV 月度结算：基于插件安装量 + 定价模型计算应付分成，支持管理员审核付款。
"""

import re
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/revenue")

# ── Constants ──────────────────────────────────────────────────────────────────

# ISV tier → revenue share percentage (ISV receives this % of gross)
SHARE_PCT_MAP: dict[str, float] = {
    "free": 0.0,
    "basic": 70.0,
    "pro": 80.0,
    "enterprise": 85.0,
}

# Estimated monthly calls per install (for per_call pricing)
CALLS_PER_INSTALL_ESTIMATE = 1000

# Valid settlement status transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved"},
    "approved": {"paid"},
    "paid": set(),
}

PERIOD_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")

# ── Pydantic models ────────────────────────────────────────────────────────────


class GenerateSettlementsRequest(BaseModel):
    period: str  # YYYY-MM


class UpdateSettlementStatusRequest(BaseModel):
    status: str  # approved | paid


# ── Helpers ────────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    return dict(row._mapping) if row else {}


def _add_yuan(record: dict) -> dict:
    """Rule 6: add _yuan companion fields for all ¥ amounts."""
    record["gross_revenue_yuan"] = (record.get("gross_revenue_fen") or 0) / 100
    record["net_payout_yuan"] = (record.get("net_payout_fen") or 0) / 100
    return record


def _validate_period(period: str) -> None:
    if not PERIOD_RE.match(period):
        raise HTTPException(status_code=400, detail="period 格式错误，使用 YYYY-MM（如 2026-03）")


# ── Settlement generation ──────────────────────────────────────────────────────


@router.post("/admin/settlements/generate")
async def generate_settlements(
    body: GenerateSettlementsRequest,
    db: AsyncSession = Depends(get_db),
):
    _validate_period(body.period)
    period = body.period

    # Find all active developers with at least one published plugin
    devs_result = await db.execute(
        text("""
            SELECT DISTINCT d.id, d.name, d.tier
            FROM isv_developers d
            JOIN marketplace_plugins p ON p.developer_id = d.id
            WHERE p.status = 'published' AND d.status = 'active'
        """),
    )
    devs = devs_result.fetchall()

    created, updated = 0, 0
    for dev in devs:
        # Get developer's published plugins
        plugins_result = await db.execute(
            text("""
                SELECT install_count, price_type, price_amount
                FROM marketplace_plugins
                WHERE developer_id = :dev_id AND status = 'published'
            """),
            {"dev_id": dev.id},
        )
        plugins = plugins_result.fetchall()

        # Calculate gross revenue (in 分, 0.01 RMB)
        gross_fen = 0
        installed_count = 0
        for p in plugins:
            if p.install_count > 0:
                installed_count += 1
            if p.price_type == "subscription":
                gross_fen += int(p.price_amount * 100) * p.install_count
            elif p.price_type == "per_call":
                gross_fen += int(p.price_amount * 100) * CALLS_PER_INSTALL_ESTIMATE * p.install_count
            # free: gross += 0

        share_pct = SHARE_PCT_MAP.get(dev.tier, 0.0)
        net_fen = int(gross_fen * share_pct / 100)

        # Check if record already exists for this developer + period
        existing = await db.execute(
            text("SELECT id FROM revenue_share_records WHERE developer_id = :dev_id AND period = :period"),
            {"dev_id": dev.id, "period": period},
        )
        if existing.first():
            # Update (preserve 'paid' status)
            await db.execute(
                text("""
                    UPDATE revenue_share_records
                    SET installed_plugins   = :installed,
                        gross_revenue_fen   = :gross,
                        share_pct           = :share_pct,
                        net_payout_fen      = :net,
                        status              = CASE WHEN status = 'paid' THEN 'paid' ELSE 'pending' END
                    WHERE developer_id = :dev_id AND period = :period
                """),
                {
                    "installed": installed_count,
                    "gross": gross_fen,
                    "share_pct": share_pct,
                    "net": net_fen,
                    "dev_id": dev.id,
                    "period": period,
                },
            )
            updated += 1
        else:
            record_id = f"rsr_{uuid.uuid4().hex[:16]}"
            await db.execute(
                text("""
                    INSERT INTO revenue_share_records
                      (id, developer_id, period, installed_plugins, gross_revenue_fen, share_pct, net_payout_fen)
                    VALUES (:id, :dev_id, :period, :installed, :gross, :share_pct, :net)
                """),
                {
                    "id": record_id,
                    "dev_id": dev.id,
                    "period": period,
                    "installed": installed_count,
                    "gross": gross_fen,
                    "share_pct": share_pct,
                    "net": net_fen,
                },
            )
            created += 1

    await db.commit()
    logger.info("settlements_generated", period=period, created=created, updated=updated)
    return {
        "period": period,
        "created": created,
        "updated": updated,
        "total": created + updated,
        "developers_processed": len(devs),
    }


# ── Admin settlement management ────────────────────────────────────────────────


@router.get("/admin/settlements")
async def list_settlements(
    period: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {}
    if period:
        conditions.append("r.period = :period")
        params["period"] = period
    if status:
        conditions.append("r.status = :status")
        params["status"] = status

    where = " AND ".join(conditions)
    rows = await db.execute(
        text(f"""
            SELECT r.*, d.name AS developer_name, d.tier AS developer_tier,
                   d.email AS developer_email
            FROM revenue_share_records r
            JOIN isv_developers d ON d.id = r.developer_id
            WHERE {where}
            ORDER BY r.period DESC, r.net_payout_fen DESC
        """),
        params,
    )
    records = [_add_yuan(_row_to_dict(r)) for r in rows.fetchall()]
    return {"settlements": records, "total": len(records)}


@router.post("/admin/settlements/{record_id}/status")
async def update_settlement_status(
    record_id: str,
    body: UpdateSettlementStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(
        text("SELECT id, status FROM revenue_share_records WHERE id = :id"),
        {"id": record_id},
    )
    record = row.first()
    if not record:
        raise HTTPException(status_code=404, detail="结算记录不存在")

    allowed = VALID_TRANSITIONS.get(record.status, set())
    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"状态 '{record.status}' 不可直接变更为 '{body.status}'，可选：{sorted(allowed) or ['无（终态）']}",
        )

    if body.status == "paid":
        await db.execute(
            text("UPDATE revenue_share_records SET status = :status, settled_at = NOW() WHERE id = :id"),
            {"status": body.status, "id": record_id},
        )
    else:
        await db.execute(
            text("UPDATE revenue_share_records SET status = :status WHERE id = :id"),
            {"status": body.status, "id": record_id},
        )

    await db.commit()
    logger.info("settlement_status_updated", record_id=record_id, status=body.status)
    return {"record_id": record_id, "status": body.status}


@router.get("/admin/summary")
async def get_admin_summary(
    period: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    params: dict = {}
    where = "1=1"
    if period:
        where = "period = :period"
        params["period"] = period

    row = await db.execute(
        text(f"""
            SELECT
                COALESCE(SUM(gross_revenue_fen), 0)                              AS total_gross_fen,
                COALESCE(SUM(net_payout_fen), 0)                                 AS total_net_fen,
                COUNT(*) FILTER (WHERE status = 'pending')                       AS pending_count,
                COUNT(*) FILTER (WHERE status = 'approved')                      AS approved_count,
                COUNT(*) FILTER (WHERE status = 'paid')                          AS paid_count,
                COUNT(DISTINCT developer_id)                                     AS developer_count
            FROM revenue_share_records
            WHERE {where}
        """),
        params,
    )
    stats = _row_to_dict(row.first())
    total_gross = stats.get("total_gross_fen") or 0
    total_net = stats.get("total_net_fen") or 0

    return {
        "period": period,
        "total_gross_revenue_fen": total_gross,
        "total_gross_revenue_yuan": total_gross / 100,
        "total_net_payout_fen": total_net,
        "total_net_payout_yuan": total_net / 100,
        "platform_profit_fen": total_gross - total_net,
        "platform_profit_yuan": (total_gross - total_net) / 100,
        "pending_count": stats.get("pending_count") or 0,
        "approved_count": stats.get("approved_count") or 0,
        "paid_count": stats.get("paid_count") or 0,
        "developer_count": stats.get("developer_count") or 0,
    }


# ── Developer self-service ─────────────────────────────────────────────────────


@router.get("/developer/{developer_id}/summary")
async def get_developer_summary(developer_id: str, db: AsyncSession = Depends(get_db)):
    dev_row = await db.execute(
        text("SELECT id, name, tier, status FROM isv_developers WHERE id = :id"),
        {"id": developer_id},
    )
    dev = dev_row.first()
    if not dev:
        raise HTTPException(status_code=404, detail="开发者不存在")

    plugin_row = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'published')                            AS published_count,
                COALESCE(SUM(install_count) FILTER (WHERE status = 'published'), 0)    AS total_installs
            FROM marketplace_plugins WHERE developer_id = :id
        """),
        {"id": developer_id},
    )
    plugin_stats = _row_to_dict(plugin_row.first())

    earn_row = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(net_payout_fen) FILTER (WHERE status = 'paid'), 0)                    AS total_earned_fen,
                COALESCE(SUM(net_payout_fen) FILTER (WHERE status IN ('pending','approved')), 0)   AS pending_earnings_fen
            FROM revenue_share_records WHERE developer_id = :id
        """),
        {"id": developer_id},
    )
    earn_stats = _row_to_dict(earn_row.first())
    total_earned = earn_stats.get("total_earned_fen") or 0
    pending_earn = earn_stats.get("pending_earnings_fen") or 0

    return {
        "developer_id": developer_id,
        "name": dev.name,
        "tier": dev.tier,
        "status": dev.status,
        "published_plugins": plugin_stats.get("published_count") or 0,
        "total_installs": plugin_stats.get("total_installs") or 0,
        "total_earned_fen": total_earned,
        "total_earned_yuan": total_earned / 100,
        "pending_earnings_fen": pending_earn,
        "pending_earnings_yuan": pending_earn / 100,
    }


@router.get("/developer/{developer_id}/settlements")
async def get_developer_settlements(developer_id: str, db: AsyncSession = Depends(get_db)):
    dev_check = await db.execute(
        text("SELECT 1 FROM isv_developers WHERE id = :id"),
        {"id": developer_id},
    )
    if not dev_check.first():
        raise HTTPException(status_code=404, detail="开发者不存在")

    rows = await db.execute(
        text("""
            SELECT id, period, installed_plugins, gross_revenue_fen, share_pct,
                   net_payout_fen, status, created_at, settled_at
            FROM revenue_share_records
            WHERE developer_id = :id
            ORDER BY period DESC
        """),
        {"id": developer_id},
    )
    records = [_add_yuan(_row_to_dict(r)) for r in rows.fetchall()]
    return {"developer_id": developer_id, "settlements": records}


@router.get("/developer/{developer_id}/plugins")
async def get_developer_plugins(developer_id: str, db: AsyncSession = Depends(get_db)):
    dev_check = await db.execute(
        text("SELECT 1 FROM isv_developers WHERE id = :id"),
        {"id": developer_id},
    )
    if not dev_check.first():
        raise HTTPException(status_code=404, detail="开发者不存在")

    rows = await db.execute(
        text("""
            SELECT id, name, slug, category, icon_emoji, status,
                   tier_required, price_type, price_amount, install_count,
                   created_at, published_at
            FROM marketplace_plugins
            WHERE developer_id = :id
            ORDER BY install_count DESC, created_at DESC
        """),
        {"id": developer_id},
    )
    plugins = [_row_to_dict(r) for r in rows.fetchall()]
    return {"developer_id": developer_id, "plugins": plugins, "total": len(plugins)}
