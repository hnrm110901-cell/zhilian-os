"""Phase 3 Month 4 — 插件市场 (Plugin Marketplace)

ISV 插件提交、管理员审核、门店安装/卸载。
"""

import json
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/marketplace")

# ── Constants ──────────────────────────────────────────────────────────────────

CATEGORIES: dict[str, str] = {
    "pos_integration": "POS集成",
    "erp_integration": "ERP集成",
    "marketing": "营销工具",
    "analytics": "数据分析",
    "operations": "运营管理",
}

PRICE_TYPES = {"free": "免费", "per_call": "按调用计费", "subscription": "按月订阅"}

# ── Pydantic models ────────────────────────────────────────────────────────────


class SubmitPluginRequest(BaseModel):
    developer_id: str
    name: str
    slug: str
    description: str
    category: str = "operations"
    icon_emoji: str = "🔌"
    version: str = "1.0.0"
    tier_required: str = "free"
    price_type: str = "free"
    price_amount: float = 0.0
    webhook_url: Optional[str] = None
    tags: list[str] = []


class ReviewPluginRequest(BaseModel):
    approved: bool
    note: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    return dict(row._mapping) if row else {}


def _parse_tags(plugin: dict) -> dict:
    if isinstance(plugin.get("tags"), str):
        try:
            plugin["tags"] = json.loads(plugin["tags"])
        except Exception:
            plugin["tags"] = []
    return plugin


# ── List / Search ──────────────────────────────────────────────────────────────


@router.get("/plugins")
async def list_plugins(
    category: Optional[str] = None,
    tier_required: Optional[str] = None,
    price_type: Optional[str] = None,
    search: Optional[str] = None,
    status: str = "published",
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    conditions = ["p.status = :status"]
    params: dict = {"status": status, "limit": limit, "offset": offset}

    if category:
        conditions.append("p.category = :category")
        params["category"] = category
    if tier_required:
        conditions.append("p.tier_required = :tier_required")
        params["tier_required"] = tier_required
    if price_type:
        conditions.append("p.price_type = :price_type")
        params["price_type"] = price_type
    if search:
        conditions.append("(p.name ILIKE :search OR p.description ILIKE :search)")
        params["search"] = f"%{search}%"

    where = " AND ".join(conditions)

    rows = await db.execute(
        text(f"""
            SELECT p.*, d.name AS developer_name, d.company AS developer_company
            FROM marketplace_plugins p
            JOIN isv_developers d ON d.id = p.developer_id
            WHERE {where}
            ORDER BY p.install_count DESC, p.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total_row = await db.execute(
        text(f"SELECT COUNT(*) FROM marketplace_plugins p WHERE {where}"),
        count_params,
    )
    total = total_row.scalar() or 0
    plugins = [_parse_tags(_row_to_dict(r)) for r in rows.fetchall()]
    return {"plugins": plugins, "total": total, "categories": CATEGORIES}


@router.get("/plugins/{slug}")
async def get_plugin(slug: str, db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        text("""
            SELECT p.*, d.name AS developer_name, d.company AS developer_company
            FROM marketplace_plugins p
            JOIN isv_developers d ON d.id = p.developer_id
            WHERE p.slug = :slug
        """),
        {"slug": slug},
    )
    plugin = row.first()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    return _parse_tags(_row_to_dict(plugin))


# ── Submit ─────────────────────────────────────────────────────────────────────


@router.post("/plugins", status_code=201)
async def submit_plugin(body: SubmitPluginRequest, db: AsyncSession = Depends(get_db)):
    if body.category not in CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"无效分类，可选：{list(CATEGORIES.keys())}",
        )
    if body.price_type not in PRICE_TYPES:
        raise HTTPException(status_code=400, detail=f"无效价格类型，可选：{list(PRICE_TYPES.keys())}")

    dev_row = await db.execute(
        text("SELECT id, status FROM isv_developers WHERE id = :id"),
        {"id": body.developer_id},
    )
    dev = dev_row.first()
    if not dev:
        raise HTTPException(status_code=404, detail="开发者账号不存在")
    if dev.status == "suspended":
        raise HTTPException(status_code=403, detail="账号已暂停，无法提交插件")

    slug_check = await db.execute(
        text("SELECT 1 FROM marketplace_plugins WHERE slug = :slug LIMIT 1"),
        {"slug": body.slug},
    )
    if slug_check.first():
        raise HTTPException(status_code=409, detail="插件标识符已被使用，请更换")

    plugin_id = f"plg_{uuid.uuid4().hex[:16]}"
    await db.execute(
        text("""
            INSERT INTO marketplace_plugins
              (id, developer_id, name, slug, description, category, icon_emoji,
               version, status, tier_required, price_type, price_amount, webhook_url, tags)
            VALUES
              (:id, :developer_id, :name, :slug, :description, :category, :icon_emoji,
               :version, 'pending_review', :tier_required, :price_type, :price_amount,
               :webhook_url, :tags)
        """),
        {
            "id": plugin_id,
            "developer_id": body.developer_id,
            "name": body.name,
            "slug": body.slug,
            "description": body.description,
            "category": body.category,
            "icon_emoji": body.icon_emoji,
            "version": body.version,
            "tier_required": body.tier_required,
            "price_type": body.price_type,
            "price_amount": body.price_amount,
            "webhook_url": body.webhook_url,
            "tags": json.dumps(body.tags, ensure_ascii=False),
        },
    )
    await db.commit()
    logger.info("plugin_submitted", plugin_id=plugin_id, developer_id=body.developer_id)
    return {"plugin_id": plugin_id, "status": "pending_review", "message": "插件已提交审核，等待管理员审核"}


# ── Admin review ───────────────────────────────────────────────────────────────


@router.get("/admin/plugins")
async def admin_list_plugins(
    status: str = "pending_review",
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        text("""
            SELECT p.*, d.name AS developer_name, d.email AS developer_email
            FROM marketplace_plugins p
            JOIN isv_developers d ON d.id = p.developer_id
            WHERE p.status = :status
            ORDER BY p.created_at ASC
        """),
        {"status": status},
    )
    plugins = [_parse_tags(_row_to_dict(r)) for r in rows.fetchall()]
    return {"plugins": plugins, "total": len(plugins)}


@router.post("/admin/plugins/{plugin_id}/review")
async def review_plugin(
    plugin_id: str,
    body: ReviewPluginRequest,
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(
        text("SELECT id, status FROM marketplace_plugins WHERE id = :id"),
        {"id": plugin_id},
    )
    plugin = row.first()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    if plugin.status != "pending_review":
        raise HTTPException(status_code=409, detail=f"当前状态 '{plugin.status}' 不可审核")
    if not body.approved and not body.note:
        raise HTTPException(status_code=400, detail="驳回时必须填写审核意见")

    if body.approved:
        await db.execute(
            text("""
                UPDATE marketplace_plugins
                SET status = 'published', review_note = :note,
                    published_at = NOW(), updated_at = NOW()
                WHERE id = :id
            """),
            {"note": body.note, "id": plugin_id},
        )
    else:
        await db.execute(
            text("""
                UPDATE marketplace_plugins
                SET status = 'rejected', review_note = :note, updated_at = NOW()
                WHERE id = :id
            """),
            {"note": body.note, "id": plugin_id},
        )
    await db.commit()
    new_status = "published" if body.approved else "rejected"
    logger.info("plugin_reviewed", plugin_id=plugin_id, approved=body.approved)
    return {"plugin_id": plugin_id, "status": new_status}


# ── Store installs ─────────────────────────────────────────────────────────────


@router.post("/stores/{store_id}/install/{plugin_id}", status_code=201)
async def install_plugin(
    store_id: str,
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
):
    plugin_row = await db.execute(
        text("SELECT id, name, status FROM marketplace_plugins WHERE id = :id"),
        {"id": plugin_id},
    )
    plugin = plugin_row.first()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    if plugin.status != "published":
        raise HTTPException(status_code=400, detail="插件未发布，无法安装")

    existing = await db.execute(
        text("SELECT id FROM plugin_installations WHERE plugin_id = :pid AND store_id = :sid"),
        {"pid": plugin_id, "sid": store_id},
    )
    if existing.first():
        raise HTTPException(status_code=409, detail="插件已安装")

    install_id = f"inst_{uuid.uuid4().hex[:16]}"
    await db.execute(
        text("""
            INSERT INTO plugin_installations (id, plugin_id, store_id, status, config)
            VALUES (:id, :pid, :sid, 'active', '{}')
        """),
        {"id": install_id, "pid": plugin_id, "sid": store_id},
    )
    await db.execute(
        text("UPDATE marketplace_plugins SET install_count = install_count + 1 WHERE id = :id"),
        {"id": plugin_id},
    )
    await db.commit()
    logger.info("plugin_installed", plugin_id=plugin_id, store_id=store_id)
    return {"installation_id": install_id, "plugin_name": plugin.name, "status": "active"}


@router.delete("/stores/{store_id}/install/{plugin_id}")
async def uninstall_plugin(
    store_id: str,
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
):
    row = await db.execute(
        text("SELECT id FROM plugin_installations WHERE plugin_id = :pid AND store_id = :sid"),
        {"pid": plugin_id, "sid": store_id},
    )
    if not row.first():
        raise HTTPException(status_code=404, detail="未安装此插件")

    await db.execute(
        text("DELETE FROM plugin_installations WHERE plugin_id = :pid AND store_id = :sid"),
        {"pid": plugin_id, "sid": store_id},
    )
    await db.execute(
        text("UPDATE marketplace_plugins SET install_count = GREATEST(install_count - 1, 0) WHERE id = :id"),
        {"id": plugin_id},
    )
    await db.commit()
    return {"message": "插件已卸载"}


@router.get("/stores/{store_id}/plugins")
async def get_store_plugins(store_id: str, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text("""
            SELECT p.id, p.name, p.slug, p.category, p.icon_emoji, p.version,
                   p.tier_required, p.price_type,
                   i.id AS installation_id, i.status AS installation_status,
                   i.installed_at, i.last_used_at
            FROM plugin_installations i
            JOIN marketplace_plugins p ON p.id = i.plugin_id
            WHERE i.store_id = :store_id AND i.status = 'active'
            ORDER BY i.installed_at DESC
        """),
        {"store_id": store_id},
    )
    return {"store_id": store_id, "plugins": [_row_to_dict(r) for r in rows.fetchall()]}


# ── Platform stats ─────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_marketplace_stats(db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'published')      AS published_count,
                COUNT(*) FILTER (WHERE status = 'pending_review') AS pending_review_count,
                COUNT(DISTINCT developer_id) FILTER (WHERE status = 'published') AS active_developers,
                COALESCE(SUM(install_count) FILTER (WHERE status = 'published'), 0) AS total_installs
            FROM marketplace_plugins
        """),
    )
    stats = _row_to_dict(row.first())

    cat_rows = await db.execute(
        text("""
            SELECT category, COUNT(*) AS count
            FROM marketplace_plugins WHERE status = 'published'
            GROUP BY category ORDER BY count DESC
        """),
    )
    by_category = {r.category: r.count for r in cat_rows.fetchall()}

    return {
        "published_plugins": stats.get("published_count") or 0,
        "pending_review": stats.get("pending_review_count") or 0,
        "active_developers": stats.get("active_developers") or 0,
        "total_installs": stats.get("total_installs") or 0,
        "by_category": by_category,
        "categories": CATEGORIES,
    }
