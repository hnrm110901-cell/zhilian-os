"""
ISV 生命周期管理 API — Phase 2 Month 3
认证体系 + 套餐升级申请/审核 + Webhook 配置 + 管理员 ISV 列表

路由前缀：/api/v1/open/isv
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/open/isv", tags=["isv_management"])

# 套餐升级路径（只允许逐级申请）
TIER_ORDER = ["free", "basic", "pro", "enterprise"]
TIER_LABELS = {"free": "免费版", "basic": "基础版", "pro": "专业版", "enterprise": "企业版"}


# ── Schemas ────────────────────────────────────────────────────────────────────


class RequestUpgradeBody(BaseModel):
    target_tier: str  # basic / pro / enterprise
    reason: str  # 升级理由，至少 20 字


class SetWebhookBody(BaseModel):
    webhook_url: str  # https:// 开头


class ReviewUpgradeBody(BaseModel):
    approved: bool
    note: Optional[str] = None  # 审核意见（驳回时必填）


class UpdateStatusBody(BaseModel):
    status: str  # active / suspended


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_developer(session: AsyncSession, developer_id: str) -> Dict[str, Any]:
    row = await session.execute(
        text("""
            SELECT id, name, email, company, tier, status, webhook_url,
                   is_verified, verified_at,
                   upgrade_request_tier, upgrade_request_reason, upgrade_requested_at,
                   upgrade_reviewed_at, upgrade_review_note, created_at
            FROM isv_developers WHERE id = :id
        """),
        {"id": developer_id},
    )
    dev = row.mappings().first()
    if not dev:
        raise HTTPException(status_code=404, detail=f"开发者 {developer_id} 不存在")
    return dict(dev)


def _fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


# ── ISV 自助接口 ───────────────────────────────────────────────────────────────


@router.post("/{developer_id}/verify")
async def verify_developer(
    developer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    邮箱验证（MVP 简化版：直接标记已验证，不实际发邮件）。
    生产环境可替换为：发送带 token 的验证链接，点击后回调此接口。
    """
    dev = await _get_developer(db, developer_id)
    if dev["is_verified"]:
        return {"message": "账号已完成验证", "verified_at": _fmt_dt(dev["verified_at"])}

    now = datetime.utcnow()
    await db.execute(
        text("UPDATE isv_developers SET is_verified = true, verified_at = :now WHERE id = :id"),
        {"now": now, "id": developer_id},
    )
    await db.commit()
    logger.info("isv_verified", developer_id=developer_id)
    return {"message": "验证成功", "verified_at": now.isoformat()}


@router.post("/{developer_id}/request-upgrade")
async def request_tier_upgrade(
    developer_id: str,
    body: RequestUpgradeBody,
    db: AsyncSession = Depends(get_db),
):
    """ISV 申请套餐升级，升级申请进入待审核队列"""
    dev = await _get_developer(db, developer_id)

    # 校验：仅已验证开发者可申请升级
    if not dev["is_verified"]:
        raise HTTPException(status_code=403, detail="请先完成邮箱验证再申请升级")

    # 校验：目标套餐必须比当前高一级
    current_idx = TIER_ORDER.index(dev["tier"]) if dev["tier"] in TIER_ORDER else 0
    target_idx = TIER_ORDER.index(body.target_tier) if body.target_tier in TIER_ORDER else -1
    if target_idx <= current_idx:
        raise HTTPException(status_code=400, detail=f"目标套餐 {body.target_tier} 必须高于当前套餐 {dev['tier']}")

    # 校验：不能有未处理的升级申请
    if dev["upgrade_request_tier"] and not dev["upgrade_reviewed_at"]:
        raise HTTPException(status_code=409, detail="已有待审核的升级申请，请等待管理员审核")

    if len(body.reason) < 10:
        raise HTTPException(status_code=400, detail="升级理由至少 10 个字")

    now = datetime.utcnow()
    await db.execute(
        text("""
            UPDATE isv_developers SET
                upgrade_request_tier = :tier,
                upgrade_request_reason = :reason,
                upgrade_requested_at = :now,
                upgrade_reviewed_at = NULL,
                upgrade_review_note = NULL
            WHERE id = :id
        """),
        {"tier": body.target_tier, "reason": body.reason, "now": now, "id": developer_id},
    )
    await db.commit()
    logger.info("isv_upgrade_requested", developer_id=developer_id, target_tier=body.target_tier)
    return {
        "message": f"升级申请已提交，目标套餐：{TIER_LABELS.get(body.target_tier, body.target_tier)}",
        "status": "pending_review",
        "requested_at": now.isoformat(),
    }


@router.post("/{developer_id}/webhook")
async def set_webhook(
    developer_id: str,
    body: SetWebhookBody,
    db: AsyncSession = Depends(get_db),
):
    """配置 Webhook 回调 URL（ISV 接收事件通知用）"""
    await _get_developer(db, developer_id)  # 确认存在

    if not body.webhook_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook URL 必须使用 HTTPS")

    await db.execute(
        text("UPDATE isv_developers SET webhook_url = :url WHERE id = :id"),
        {"url": body.webhook_url, "id": developer_id},
    )
    await db.commit()
    logger.info("isv_webhook_set", developer_id=developer_id)
    return {"message": "Webhook URL 已配置", "webhook_url": body.webhook_url}


@router.get("/{developer_id}/status")
async def get_developer_status(
    developer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查询开发者认证状态和升级申请进度"""
    dev = await _get_developer(db, developer_id)
    upgrade_status = None
    if dev["upgrade_request_tier"]:
        if dev["upgrade_reviewed_at"]:
            upgrade_status = "approved" if dev["tier"] == dev["upgrade_request_tier"] else "rejected"
        else:
            upgrade_status = "pending_review"

    return {
        "developer_id": developer_id,
        "tier": dev["tier"],
        "tier_label": TIER_LABELS.get(dev["tier"], dev["tier"]),
        "status": dev["status"],
        "is_verified": dev["is_verified"],
        "verified_at": _fmt_dt(dev["verified_at"]),
        "webhook_url": dev["webhook_url"],
        "upgrade_request": (
            {
                "target_tier": dev["upgrade_request_tier"],
                "reason": dev["upgrade_request_reason"],
                "requested_at": _fmt_dt(dev["upgrade_requested_at"]),
                "status": upgrade_status,
                "reviewed_at": _fmt_dt(dev["upgrade_reviewed_at"]),
                "review_note": dev["upgrade_review_note"],
            }
            if dev["upgrade_request_tier"]
            else None
        ),
    }


# ── 管理员接口 ─────────────────────────────────────────────────────────────────


@router.get("/admin/list")
async def admin_list_developers(
    status: Optional[str] = Query(None, description="过滤状态：active/suspended/all"),
    pending_upgrade: bool = Query(False, description="仅显示有待审核升级申请的开发者"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """[管理员] 查询所有 ISV 开发者列表"""
    conditions = ["1=1"]
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if status and status != "all":
        conditions.append("d.status = :status")
        params["status"] = status
    if pending_upgrade:
        conditions.append("d.upgrade_request_tier IS NOT NULL AND d.upgrade_reviewed_at IS NULL")

    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT d.id, d.name, d.email, d.company, d.tier, d.status,
                   d.is_verified, d.webhook_url,
                   d.upgrade_request_tier, d.upgrade_requested_at,
                   d.upgrade_reviewed_at,
                   (SELECT COUNT(*) FROM isv_api_keys k WHERE k.developer_id = d.id AND k.is_active = true) AS active_keys,
                   d.created_at
            FROM isv_developers d
            WHERE {where}
            ORDER BY d.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = [dict(r) for r in result.mappings().all()]

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM isv_developers d WHERE {where}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_result.scalar() or 0

    # 处理日期序列化
    for row in rows:
        for col in ("upgrade_requested_at", "upgrade_reviewed_at", "created_at"):
            if row.get(col) and hasattr(row[col], "isoformat"):
                row[col] = row[col].isoformat()

    return {"total": total, "developers": rows}


@router.post("/admin/{developer_id}/review-upgrade")
async def admin_review_upgrade(
    developer_id: str,
    body: ReviewUpgradeBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """[管理员] 审核套餐升级申请：批准或拒绝"""
    dev = await _get_developer(db, developer_id)

    if not dev["upgrade_request_tier"]:
        raise HTTPException(status_code=404, detail="该开发者没有待处理的升级申请")
    if dev["upgrade_reviewed_at"]:
        raise HTTPException(status_code=409, detail="该升级申请已处理过")
    if not body.approved and not body.note:
        raise HTTPException(status_code=400, detail="驳回时必须填写审核意见")

    now = datetime.utcnow()
    new_tier = dev["upgrade_request_tier"] if body.approved else dev["tier"]

    await db.execute(
        text("""
            UPDATE isv_developers SET
                tier = :new_tier,
                upgrade_reviewed_at = :now,
                upgrade_review_note = :note
            WHERE id = :id
        """),
        {"new_tier": new_tier, "now": now, "note": body.note or "已批准", "id": developer_id},
    )
    # 若批准，同步更新 API Key 的速率限制
    if body.approved:
        rpm_map = {"free": 60, "basic": 300, "pro": 1000, "enterprise": 5000}
        new_rpm = rpm_map.get(new_tier, 60)
        await db.execute(
            text("UPDATE isv_api_keys SET rate_limit_rpm = :rpm WHERE developer_id = :id AND is_active = true"),
            {"rpm": new_rpm, "id": developer_id},
        )

    await db.commit()
    logger.info(
        "isv_upgrade_reviewed",
        developer_id=developer_id,
        approved=body.approved,
        new_tier=new_tier,
        reviewer=current_user.username if current_user else "system",
    )
    return {
        "message": "升级申请已批准" if body.approved else "升级申请已驳回",
        "developer_id": developer_id,
        "new_tier": new_tier,
        "tier_label": TIER_LABELS.get(new_tier, new_tier),
        "reviewed_at": now.isoformat(),
    }


@router.put("/admin/{developer_id}/status")
async def admin_update_status(
    developer_id: str,
    body: UpdateStatusBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """[管理员] 暂停或恢复 ISV 账号"""
    if body.status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="status 只能是 active 或 suspended")

    dev = await _get_developer(db, developer_id)
    if dev["status"] == body.status:
        return {"message": f"账号已是 {body.status} 状态，无需变更"}

    await db.execute(
        text("UPDATE isv_developers SET status = :status WHERE id = :id"),
        {"status": body.status, "id": developer_id},
    )
    # 暂停时停用所有 API Key
    if body.status == "suspended":
        await db.execute(
            text("UPDATE isv_api_keys SET is_active = false WHERE developer_id = :id"),
            {"id": developer_id},
        )
    await db.commit()

    logger.info(
        "isv_status_changed",
        developer_id=developer_id,
        new_status=body.status,
        operator=current_user.username if current_user else "system",
    )
    return {"message": f"账号已{'暂停' if body.status == 'suspended' else '恢复'}", "status": body.status}


@router.get("/admin/stats")
async def admin_isv_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """[管理员] ISV 生态总览统计"""
    result = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'active') AS active_count,
            COUNT(*) FILTER (WHERE status = 'suspended') AS suspended_count,
            COUNT(*) FILTER (WHERE is_verified = true) AS verified_count,
            COUNT(*) FILTER (WHERE upgrade_request_tier IS NOT NULL AND upgrade_reviewed_at IS NULL) AS pending_upgrade_count,
            COUNT(*) FILTER (WHERE tier = 'free') AS free_count,
            COUNT(*) FILTER (WHERE tier = 'basic') AS basic_count,
            COUNT(*) FILTER (WHERE tier = 'pro') AS pro_count,
            COUNT(*) FILTER (WHERE tier = 'enterprise') AS enterprise_count
        FROM isv_developers
    """))
    row = dict(result.mappings().first() or {})
    return {
        "active_developers": row.get("active_count", 0),
        "suspended_developers": row.get("suspended_count", 0),
        "verified_developers": row.get("verified_count", 0),
        "pending_upgrade_reviews": row.get("pending_upgrade_count", 0),
        "by_tier": {
            "free": row.get("free_count", 0),
            "basic": row.get("basic_count", 0),
            "pro": row.get("pro_count", 0),
            "enterprise": row.get("enterprise_count", 0),
        },
    }
