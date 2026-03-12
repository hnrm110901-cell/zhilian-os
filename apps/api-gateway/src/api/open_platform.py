"""
开放平台 API — Phase 2 aPaaS
ISV 开发者自助注册 + API Key 管理 + 能力目录

路由前缀：/api/v1/open
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/open", tags=["open_platform"])

# ── 能力目录（静态配置） ───────────────────────────────────────────────────────

CAPABILITIES: List[Dict[str, Any]] = [
    # Level 1 — 数据同步
    {"level": 1, "key": "sync_orders", "name": "订单同步", "description": "批量同步 POS/外卖平台订单到屯象", "tier_required": "free"},
    {"level": 1, "key": "sync_dishes", "name": "菜品同步", "description": "同步菜品信息、价格、库存到屯象", "tier_required": "free"},
    {"level": 1, "key": "sync_inventory", "name": "库存同步", "description": "实时同步食材库存数据", "tier_required": "free"},
    {"level": 1, "key": "sync_members", "name": "会员同步", "description": "同步会员信息、积分、消费记录", "tier_required": "free"},
    # Level 2 — 智能决策
    {"level": 2, "key": "predict_sales", "name": "销量预测", "description": "基于历史数据预测菜品日销量", "tier_required": "basic"},
    {"level": 2, "key": "suggest_schedule", "name": "智能排班", "description": "根据客流预测生成最优排班方案", "tier_required": "basic"},
    {"level": 2, "key": "suggest_purchase", "name": "采购建议", "description": "基于销量预测生成食材采购清单", "tier_required": "basic"},
    {"level": 2, "key": "suggest_pricing", "name": "定价建议", "description": "竞品+成本+弹性分析给出定价区间", "tier_required": "basic"},
    # Level 3 — 营销能力
    {"level": 3, "key": "customer_profile", "name": "客户画像", "description": "RFM 模型 + 流失风险评分", "tier_required": "pro"},
    {"level": 3, "key": "recommend_dishes", "name": "个性化推荐", "description": "协同过滤 + 内容匹配推荐菜品", "tier_required": "pro"},
    {"level": 3, "key": "coupon_strategy", "name": "发券策略", "description": "AI 生成差异化优惠券方案", "tier_required": "pro"},
    {"level": 3, "key": "marketing_campaign", "name": "营销活动", "description": "触发企微批量挽回/促活活动", "tier_required": "pro"},
    # Level 4 — 高级能力
    {"level": 4, "key": "query_sop", "name": "SOP 知识库", "description": "自然语言查询餐饮运营 SOP 最佳实践", "tier_required": "enterprise"},
    {"level": 4, "key": "federated_model", "name": "联邦学习模型", "description": "获取跨店联邦训练的共享模型参数", "tier_required": "enterprise"},
]

TIER_CONFIG = {
    "free":       {"rate_limit_rpm": 60,   "label": "免费版",  "price_yuan": 0},
    "basic":      {"rate_limit_rpm": 300,  "label": "基础版",  "price_yuan": 999},
    "pro":        {"rate_limit_rpm": 1000, "label": "专业版",  "price_yuan": 2999},
    "enterprise": {"rate_limit_rpm": 5000, "label": "企业版",  "price_yuan": 9999},
}


# ── Request / Response schemas ─────────────────────────────────────────────────

class RegisterDeveloperRequest(BaseModel):
    name: str
    email: str
    company: Optional[str] = None
    tier: str = "free"   # free / basic / pro / enterprise


class RegisterDeveloperResponse(BaseModel):
    developer_id: str
    api_key: str
    api_secret: str          # 只在注册时返回一次，之后不可再查
    rate_limit_rpm: int
    tier: str
    message: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


async def _email_exists(session: AsyncSession, email: str) -> bool:
    row = await session.execute(
        text("SELECT 1 FROM isv_developers WHERE email = :email LIMIT 1"),
        {"email": email},
    )
    return row.first() is not None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/capabilities")
async def list_capabilities(
    level: Optional[int] = None,
    tier: Optional[str] = None,
):
    """列出所有开放能力（按 Level 分组）"""
    caps = CAPABILITIES
    if level is not None:
        caps = [c for c in caps if c["level"] == level]
    if tier is not None:
        tier_order = ["free", "basic", "pro", "enterprise"]
        if tier in tier_order:
            idx = tier_order.index(tier)
            accessible = set(tier_order[: idx + 1])
            caps = [c for c in caps if c["tier_required"] in accessible]
    return {
        "total": len(caps),
        "capabilities": caps,
    }


@router.get("/pricing")
async def get_pricing():
    """查询各套餐价格及限制"""
    return {
        "tiers": [
            {
                "tier": k,
                **v,
                "max_level": {"free": 1, "basic": 2, "pro": 3, "enterprise": 4}[k],
            }
            for k, v in TIER_CONFIG.items()
        ]
    }


@router.post("/developers", response_model=RegisterDeveloperResponse)
async def register_developer(
    body: RegisterDeveloperRequest,
    db: AsyncSession = Depends(get_db),
):
    """ISV 开发者自助注册 — 生成 API Key & Secret"""
    tier = body.tier if body.tier in TIER_CONFIG else "free"

    # 邮箱唯一性校验
    if await _email_exists(db, body.email):
        raise HTTPException(status_code=409, detail="该邮箱已注册开发者账号")

    developer_id = f"dev_{uuid.uuid4().hex[:16]}"
    api_key = f"zlos_{secrets.token_urlsafe(32)}"
    api_secret = secrets.token_urlsafe(48)
    secret_hash = _hash_secret(api_secret)
    key_id = f"key_{uuid.uuid4().hex[:16]}"
    rate_limit_rpm = TIER_CONFIG[tier]["rate_limit_rpm"]
    now = datetime.utcnow()

    await db.execute(
        text("""
            INSERT INTO isv_developers (id, name, email, company, tier, is_verified, created_at)
            VALUES (:id, :name, :email, :company, :tier, false, :now)
        """),
        {
            "id": developer_id,
            "name": body.name,
            "email": body.email,
            "company": body.company,
            "tier": tier,
            "now": now,
        },
    )
    await db.execute(
        text("""
            INSERT INTO isv_api_keys (id, developer_id, key_name, api_key, api_secret_hash,
                                      rate_limit_rpm, is_active, created_at)
            VALUES (:id, :developer_id, 'default', :api_key, :secret_hash,
                    :rate_limit_rpm, true, :now)
        """),
        {
            "id": key_id,
            "developer_id": developer_id,
            "api_key": api_key,
            "secret_hash": secret_hash,
            "rate_limit_rpm": rate_limit_rpm,
            "now": now,
        },
    )
    await db.commit()

    logger.info("isv_developer_registered", developer_id=developer_id, tier=tier, email=body.email)

    return RegisterDeveloperResponse(
        developer_id=developer_id,
        api_key=api_key,
        api_secret=api_secret,
        rate_limit_rpm=rate_limit_rpm,
        tier=tier,
        message=f"注册成功！请妥善保存 api_secret，页面关闭后将无法再次查看。",
    )


@router.get("/developers/{developer_id}")
async def get_developer_info(
    developer_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询开发者信息（含 API Key 列表，secret 不返回）"""
    result = await db.execute(
        text("SELECT id, name, email, company, tier, is_verified, created_at FROM isv_developers WHERE id = :id"),
        {"id": developer_id},
    )
    dev = result.mappings().first()
    if not dev:
        raise HTTPException(status_code=404, detail="开发者不存在")

    keys_result = await db.execute(
        text("""
            SELECT id, key_name, api_key, rate_limit_rpm, is_active, last_used_at, created_at
            FROM isv_api_keys WHERE developer_id = :dev_id ORDER BY created_at DESC
        """),
        {"dev_id": developer_id},
    )
    keys = [dict(r) for r in keys_result.mappings().all()]
    # 对 api_key 做掩码处理（只显示前8位 + ***）
    for k in keys:
        raw: str = k["api_key"]
        k["api_key_masked"] = raw[:12] + "***"
        del k["api_key"]

    tier = dev["tier"]
    return {
        "developer_id": dev["id"],
        "name": dev["name"],
        "email": dev["email"],
        "company": dev["company"],
        "tier": tier,
        "tier_label": TIER_CONFIG.get(tier, {}).get("label", tier),
        "is_verified": dev["is_verified"],
        "created_at": dev["created_at"].isoformat() if dev["created_at"] else None,
        "api_keys": keys,
        "capabilities_accessible": [
            c for c in CAPABILITIES
            if c["tier_required"] in (["free", "basic", "pro", "enterprise"][: ["free", "basic", "pro", "enterprise"].index(tier) + 1])
        ],
    }


@router.get("/stats")
async def get_platform_stats(
    db: AsyncSession = Depends(get_db),
):
    """平台统计概览（注册开发者数 / API Key 数 / 能力数）"""
    dev_count = (await db.execute(text("SELECT COUNT(*) FROM isv_developers"))).scalar() or 0
    key_count = (await db.execute(text("SELECT COUNT(*) FROM isv_api_keys WHERE is_active = true"))).scalar() or 0
    return {
        "registered_developers": dev_count,
        "active_api_keys": key_count,
        "total_capabilities": len(CAPABILITIES),
        "capability_levels": 4,
    }
