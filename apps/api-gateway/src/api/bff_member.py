"""
BFF 会员数据聚合路由

三源融合：member_syncs（POS同步） + consumer_identities（CDP统一身份） + private_domain_members（私域运营）

  GET /api/v1/bff/member/{store_id}/overview    — 会员概览仪表盘
  GET /api/v1/bff/member/{store_id}/members     — 分页会员列表（搜索/筛选）
  GET /api/v1/bff/member/{store_id}/member/{consumer_id} — 单会员跨系统聚合详情

设计原则：
  - asyncio.gather 并行子调用，降低延迟
  - Redis 30s 短缓存（?refresh=true 强制刷新）
  - 任何子调用失败 → 降级返回 null，不影响其他模块
  - Rule 6 合规：金额字段以 _yuan 结尾
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_db

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/bff/member", tags=["BFF-会员"])

_BFF_CACHE_TTL = 30  # seconds


# ── Redis 缓存助手 ────────────────────────────────────────────────────────────


async def _cache_get(key: str) -> Optional[Dict]:
    try:
        from src.services.redis_cache_service import RedisCacheService

        svc = RedisCacheService()
        return await svc.get(key)
    except Exception as exc:
        logger.debug("bff_member_cache_get_failed", key=key, error=str(exc))
        return None


async def _cache_set(key: str, value: Dict) -> None:
    try:
        from src.services.redis_cache_service import RedisCacheService

        svc = RedisCacheService()
        await svc.set(key, value, expire=_BFF_CACHE_TTL)
    except Exception as exc:
        logger.debug("bff_member_cache_set_failed", key=key, error=str(exc))


# ── 子调用降级包装 ─────────────────────────────────────────────────────────────


async def _safe(coro, default=None):
    """执行协程；任何异常返回 default，不中断整体响应。"""
    try:
        return await coro
    except Exception as exc:
        logger.warning("bff_member_sub_call_failed", error=str(exc))
        return default


# ── 辅助：分转元 ──────────────────────────────────────────────────────────────


def _fen_to_yuan(fen_val) -> Optional[float]:
    """分 → 元，保留2位小数。None/非数值 → None。"""
    if fen_val is None:
        return None
    try:
        return round(float(fen_val) / 100, 2)
    except (TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 1: GET /{store_id}/overview — 会员概览仪表盘
# ═══════════════════════════════════════════════════════════════════════════════


async def _fetch_member_total_stats(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """从 member_syncs 聚合总量统计（通过 external_systems.store_id 关联）"""
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) AS total_members,
                COUNT(*) FILTER (
                    WHERE ms.last_activity >= NOW() - INTERVAL '30 days'
                ) AS active_members_30d,
                COUNT(*) FILTER (
                    WHERE ms.created_at >= NOW() - INTERVAL '7 days'
                ) AS new_members_7d,
                COALESCE(AVG(ms.balance), 0) AS avg_balance,
                COALESCE(SUM(ms.points), 0) AS total_points_issued
            FROM member_syncs ms
            JOIN external_systems es ON ms.system_id = es.id
            WHERE es.store_id = :store_id
        """),
        {"store_id": store_id},
    )
    row = result.mappings().first()
    if not row:
        return {
            "total_members": 0,
            "active_members_30d": 0,
            "new_members_7d": 0,
            "avg_stored_value_yuan": 0.0,
            "total_points_issued": 0,
        }
    return {
        "total_members": row["total_members"] or 0,
        "active_members_30d": row["active_members_30d"] or 0,
        "new_members_7d": row["new_members_7d"] or 0,
        # balance 字段为 Numeric(12,2)，已经是元单位
        "avg_stored_value_yuan": round(float(row["avg_balance"] or 0), 2),
        "total_points_issued": int(row["total_points_issued"] or 0),
    }


async def _fetch_level_distribution(store_id: str, db: AsyncSession) -> Dict[str, int]:
    """会员等级分布（从 member_syncs）"""
    result = await db.execute(
        text("""
            SELECT
                COALESCE(ms.level, '普通') AS level,
                COUNT(*) AS cnt
            FROM member_syncs ms
            JOIN external_systems es ON ms.system_id = es.id
            WHERE es.store_id = :store_id
            GROUP BY COALESCE(ms.level, '普通')
        """),
        {"store_id": store_id},
    )
    dist = {"普通": 0, "银卡": 0, "金卡": 0, "钻石": 0}
    for row in result.mappings():
        level_name = row["level"]
        if level_name in dist:
            dist[level_name] = row["cnt"]
        else:
            # 未知等级归入普通
            dist["普通"] += row["cnt"]
    return dist


async def _fetch_lifecycle_distribution(store_id: str, db: AsyncSession) -> Dict[str, int]:
    """生命周期分布（从 private_domain_members 的 recency_days 推断）"""
    result = await db.execute(
        text("""
            SELECT
                CASE
                    WHEN created_at >= NOW() - INTERVAL '30 days' THEN '新客'
                    WHEN recency_days <= 30 THEN '活跃'
                    WHEN recency_days <= 90 THEN '沉睡'
                    ELSE '流失'
                END AS lifecycle,
                COUNT(*) AS cnt
            FROM private_domain_members
            WHERE store_id = :store_id AND is_active = true
            GROUP BY lifecycle
        """),
        {"store_id": store_id},
    )
    dist = {"新客": 0, "活跃": 0, "沉睡": 0, "流失": 0}
    for row in result.mappings():
        lc = row["lifecycle"]
        if lc in dist:
            dist[lc] = row["cnt"]
    return dist


async def _fetch_top_value_members(store_id: str, db: AsyncSession) -> List[Dict[str, Any]]:
    """Top 5 高价值会员（从 consumer_identities + private_domain_members 联合查询）"""
    result = await db.execute(
        text("""
            SELECT
                ci.display_name AS name,
                COALESCE(ms.level, '普通') AS level,
                ci.total_order_amount_fen,
                ci.total_order_count AS visit_count,
                ci.last_order_at
            FROM consumer_identities ci
            JOIN private_domain_members pdm
                ON pdm.consumer_id = ci.id AND pdm.store_id = :store_id
            LEFT JOIN consumer_id_mappings cim
                ON cim.consumer_id = ci.id AND cim.id_type = 'pos_member_id' AND cim.is_active = true
            LEFT JOIN member_syncs ms
                ON ms.member_id = cim.external_id
            WHERE ci.is_merged = false
            ORDER BY ci.total_order_amount_fen DESC NULLS LAST
            LIMIT 5
        """),
        {"store_id": store_id},
    )
    members = []
    for row in result.mappings():
        members.append({
            "name": row["name"] or "未知",
            "level": row["level"] or "普通",
            "total_spend_yuan": _fen_to_yuan(row["total_order_amount_fen"]) or 0.0,
            "visit_count": row["visit_count"] or 0,
            "last_visit": row["last_order_at"].isoformat() if row["last_order_at"] else None,
        })
    return members


async def _fetch_source_breakdown(store_id: str, db: AsyncSession) -> Dict[str, int]:
    """数据来源分布（从 consumer_id_mappings + external_systems）"""
    result = await db.execute(
        text("""
            SELECT
                COALESCE(cim.source_system, 'unknown') AS source,
                COUNT(DISTINCT cim.consumer_id) AS cnt
            FROM consumer_id_mappings cim
            WHERE cim.store_id = :store_id AND cim.is_active = true
            GROUP BY COALESCE(cim.source_system, 'unknown')
        """),
        {"store_id": store_id},
    )
    breakdown = {"aoqiwei_crm": 0, "pinzhi": 0}
    for row in result.mappings():
        src = row["source"]
        if src in breakdown:
            breakdown[src] = row["cnt"]
        else:
            # 映射常见名称变体（微生活即奥琦玮CRM，统一归入 aoqiwei_crm）
            if "aoqiwei" in src.lower() or "aqw" in src.lower() or "weishenghuo" in src.lower() or "wsh" in src.lower():
                breakdown["aoqiwei_crm"] += row["cnt"]
            elif "pinzhi" in src.lower() or "pz" in src.lower():
                breakdown["pinzhi"] += row["cnt"]
    return breakdown


async def _fetch_last_sync_time(store_id: str, db: AsyncSession) -> Optional[str]:
    """最后同步时间"""
    result = await db.execute(
        text("""
            SELECT MAX(ms.synced_at) AS last_synced
            FROM member_syncs ms
            JOIN external_systems es ON ms.system_id = es.id
            WHERE es.store_id = :store_id
        """),
        {"store_id": store_id},
    )
    row = result.mappings().first()
    if row and row["last_synced"]:
        return row["last_synced"].isoformat()
    return None


@router.get("/{store_id}/overview", summary="会员概览仪表盘")
async def get_member_overview(
    store_id: str,
    refresh: bool = Query(default=False, description="强制刷新缓存"),
    db: AsyncSession = Depends(get_db),
):
    """
    会员概览聚合数据：总量统计、等级分布、生命周期分布、Top5高价值会员、来源分布。

    三源融合：member_syncs + consumer_identities + private_domain_members
    """
    cache_key = f"bff:member:overview:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    # 并行拉取所有子数据
    (
        total_stats,
        level_dist,
        lifecycle_dist,
        top_members,
        source_dist,
        synced_at,
    ) = await asyncio.gather(
        _safe(_fetch_member_total_stats(store_id, db), default=None),
        _safe(_fetch_level_distribution(store_id, db), default=None),
        _safe(_fetch_lifecycle_distribution(store_id, db), default=None),
        _safe(_fetch_top_value_members(store_id, db), default=None),
        _safe(_fetch_source_breakdown(store_id, db), default=None),
        _safe(_fetch_last_sync_time(store_id, db), default=None),
    )

    payload = {
        "store_id": store_id,
        "total_members": total_stats["total_members"] if total_stats else None,
        "active_members_30d": total_stats["active_members_30d"] if total_stats else None,
        "new_members_7d": total_stats["new_members_7d"] if total_stats else None,
        "avg_stored_value_yuan": total_stats["avg_stored_value_yuan"] if total_stats else None,
        "total_points_issued": total_stats["total_points_issued"] if total_stats else None,
        "member_level_distribution": level_dist,
        "lifecycle_distribution": lifecycle_dist,
        "top_value_members": top_members,
        "source_breakdown": source_dist,
        "synced_at": synced_at,
    }

    await _cache_set(cache_key, payload)
    return payload


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 2: GET /{store_id}/members — 分页会员列表
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{store_id}/members", summary="分页会员列表（搜索/筛选）")
async def list_store_members(
    store_id: str,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    search: Optional[str] = Query(default=None, description="按手机号/姓名搜索"),
    level: Optional[str] = Query(default=None, description="按等级筛选"),
    lifecycle: Optional[str] = Query(default=None, description="按生命周期筛选: 新客/活跃/沉睡/流失"),
    source: Optional[str] = Query(default=None, description="按来源筛选: aoqiwei_crm/pinzhi"),
    db: AsyncSession = Depends(get_db),
):
    """
    分页查询门店会员列表，支持多维度筛选。

    融合 member_syncs（基础信息）+ private_domain_members（RFM + 生命周期）。
    """
    # 动态构建 WHERE 子句
    conditions = ["es.store_id = :store_id"]
    params: Dict[str, Any] = {"store_id": store_id}

    if search:
        conditions.append("(ms.phone ILIKE :search OR ms.name ILIKE :search)")
        params["search"] = f"%{search}%"

    if level:
        conditions.append("ms.level = :level")
        params["level"] = level

    if source:
        conditions.append("cim.source_system = :source")
        params["source"] = source

    # 生命周期筛选需要 join private_domain_members
    lifecycle_join = ""
    if lifecycle:
        lifecycle_map = {
            "新客": "pdm.created_at >= NOW() - INTERVAL '30 days'",
            "活跃": "pdm.recency_days <= 30 AND pdm.created_at < NOW() - INTERVAL '30 days'",
            "沉睡": "pdm.recency_days > 30 AND pdm.recency_days <= 90",
            "流失": "pdm.recency_days > 90",
        }
        lc_condition = lifecycle_map.get(lifecycle)
        if lc_condition:
            lifecycle_join = """
                JOIN private_domain_members pdm
                    ON pdm.customer_id = ms.member_id AND pdm.store_id = :store_id AND pdm.is_active = true
            """
            conditions.append(lc_condition)

    where_clause = " AND ".join(conditions)
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    # 查询总数
    count_sql = f"""
        SELECT COUNT(DISTINCT ms.id) AS total
        FROM member_syncs ms
        JOIN external_systems es ON ms.system_id = es.id
        LEFT JOIN consumer_id_mappings cim
            ON cim.external_id = ms.member_id AND cim.is_active = true
        {lifecycle_join}
        WHERE {where_clause}
    """
    count_result = await db.execute(text(count_sql), params)
    total = count_result.scalar() or 0

    # 查询分页数据
    data_sql = f"""
        SELECT DISTINCT ON (ms.id)
            ms.id,
            ms.member_id,
            ms.name,
            ms.phone,
            ms.level,
            ms.points,
            ms.balance,
            ms.last_activity,
            ms.synced_at,
            cim.source_system,
            cim.consumer_id
        FROM member_syncs ms
        JOIN external_systems es ON ms.system_id = es.id
        LEFT JOIN consumer_id_mappings cim
            ON cim.external_id = ms.member_id AND cim.is_active = true
        {lifecycle_join}
        WHERE {where_clause}
        ORDER BY ms.id, ms.last_activity DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    data_result = await db.execute(text(data_sql), params)

    members = []
    for row in data_result.mappings():
        members.append({
            "id": str(row["id"]),
            "member_id": row["member_id"],
            "name": row["name"],
            "phone": row["phone"],
            "level": row["level"] or "普通",
            "points": row["points"] or 0,
            # balance 为 Numeric(12,2)，已是元单位
            "balance_yuan": round(float(row["balance"] or 0), 2),
            "last_activity": row["last_activity"].isoformat() if row["last_activity"] else None,
            "synced_at": row["synced_at"].isoformat() if row["synced_at"] else None,
            "source": row["source_system"],
            "consumer_id": str(row["consumer_id"]) if row["consumer_id"] else None,
        })

    return {
        "store_id": store_id,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        "members": members,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 3: GET /{store_id}/member/{consumer_id} — 单会员跨系统聚合详情
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{store_id}/member/{consumer_id}", summary="单会员跨系统聚合详情")
async def get_member_detail(
    store_id: str,
    consumer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    通过 consumer_id 聚合三源数据：

    1. consumer_identities — CDP 统一身份（基础 profile + RFM 快照 + 聚合统计）
    2. consumer_id_mappings — 所有外部ID映射
    3. member_syncs — POS 同步的会员等级/积分/余额
    4. private_domain_members — 私域 RFM 评分 + 生命周期标签
    """

    # 子查询 1: CDP 统一身份
    async def _fetch_identity():
        result = await db.execute(
            text("""
                SELECT
                    id, primary_phone, display_name, gender, birth_date,
                    wechat_nickname, wechat_avatar_url,
                    total_order_count, total_order_amount_fen,
                    total_reservation_count,
                    first_order_at, last_order_at, first_store_id,
                    rfm_recency_days, rfm_frequency, rfm_monetary_fen,
                    tags, source, confidence_score, created_at
                FROM consumer_identities
                WHERE id = :consumer_id AND is_merged = false
            """),
            {"consumer_id": consumer_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return {
            "consumer_id": str(row["id"]),
            "phone": row["primary_phone"],
            "name": row["display_name"],
            "gender": row["gender"],
            "birth_date": row["birth_date"].isoformat() if row["birth_date"] else None,
            "wechat_nickname": row["wechat_nickname"],
            "wechat_avatar_url": row["wechat_avatar_url"],
            "total_order_count": row["total_order_count"] or 0,
            "total_order_amount_yuan": _fen_to_yuan(row["total_order_amount_fen"]) or 0.0,
            "total_reservation_count": row["total_reservation_count"] or 0,
            "first_order_at": row["first_order_at"].isoformat() if row["first_order_at"] else None,
            "last_order_at": row["last_order_at"].isoformat() if row["last_order_at"] else None,
            "first_store_id": row["first_store_id"],
            "rfm": {
                "recency_days": row["rfm_recency_days"],
                "frequency": row["rfm_frequency"],
                "monetary_yuan": _fen_to_yuan(row["rfm_monetary_fen"]),
            },
            "tags": row["tags"] or [],
            "source": row["source"],
            "confidence_score": row["confidence_score"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    # 子查询 2: 外部ID映射列表
    async def _fetch_id_mappings():
        result = await db.execute(
            text("""
                SELECT
                    id_type, external_id, source_system, confidence,
                    is_verified, is_active, created_at
                FROM consumer_id_mappings
                WHERE consumer_id = :consumer_id
                ORDER BY is_active DESC, created_at DESC
            """),
            {"consumer_id": consumer_id},
        )
        return [
            {
                "id_type": row["id_type"],
                "external_id": row["external_id"],
                "source_system": row["source_system"],
                "confidence": row["confidence"],
                "is_verified": row["is_verified"],
                "is_active": row["is_active"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in result.mappings()
        ]

    # 子查询 3: POS 同步会员数据（可能多个来源）
    async def _fetch_synced_members():
        result = await db.execute(
            text("""
                SELECT
                    ms.member_id, ms.external_member_id, ms.name, ms.phone,
                    ms.level, ms.points, ms.balance,
                    ms.last_activity, ms.synced_at,
                    es.name AS system_name, es.provider
                FROM consumer_id_mappings cim
                JOIN member_syncs ms ON ms.member_id = cim.external_id
                JOIN external_systems es ON ms.system_id = es.id
                WHERE cim.consumer_id = :consumer_id
                    AND cim.is_active = true
                    AND cim.id_type = 'pos_member_id'
            """),
            {"consumer_id": consumer_id},
        )
        return [
            {
                "member_id": row["member_id"],
                "external_member_id": row["external_member_id"],
                "name": row["name"],
                "phone": row["phone"],
                "level": row["level"],
                "points": row["points"] or 0,
                "balance_yuan": round(float(row["balance"] or 0), 2),
                "last_activity": row["last_activity"].isoformat() if row["last_activity"] else None,
                "synced_at": row["synced_at"].isoformat() if row["synced_at"] else None,
                "system_name": row["system_name"],
                "provider": row["provider"],
            }
            for row in result.mappings()
        ]

    # 子查询 4: 私域会员数据（门店维度）
    async def _fetch_private_domain():
        result = await db.execute(
            text("""
                SELECT
                    rfm_level, store_quadrant, dynamic_tags,
                    recency_days, frequency, monetary,
                    last_visit, risk_score, channel_source,
                    r_score, f_score, m_score,
                    birth_date, rfm_updated_at, created_at
                FROM private_domain_members
                WHERE consumer_id = :consumer_id
                    AND store_id = :store_id
                    AND is_active = true
            """),
            {"consumer_id": consumer_id, "store_id": store_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return {
            "rfm_level": row["rfm_level"],
            "store_quadrant": row["store_quadrant"],
            "dynamic_tags": row["dynamic_tags"] or [],
            "recency_days": row["recency_days"],
            "frequency": row["frequency"],
            "monetary_yuan": _fen_to_yuan(row["monetary"]) or 0.0,
            "last_visit": row["last_visit"].isoformat() if row["last_visit"] else None,
            "risk_score": row["risk_score"],
            "channel_source": row["channel_source"],
            "rfm_scores": {
                "r": row["r_score"],
                "f": row["f_score"],
                "m": row["m_score"],
            },
            "birth_date": row["birth_date"].isoformat() if row["birth_date"] else None,
            "rfm_updated_at": row["rfm_updated_at"].isoformat() if row["rfm_updated_at"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    # 并行拉取
    identity, id_mappings, synced_members, private_domain = await asyncio.gather(
        _safe(_fetch_identity(), default=None),
        _safe(_fetch_id_mappings(), default=None),
        _safe(_fetch_synced_members(), default=None),
        _safe(_fetch_private_domain(), default=None),
    )

    if identity is None and id_mappings is None:
        return {
            "store_id": store_id,
            "consumer_id": consumer_id,
            "found": False,
            "message": "未找到该会员信息",
        }

    return {
        "store_id": store_id,
        "consumer_id": consumer_id,
        "found": True,
        "identity": identity,
        "id_mappings": id_mappings,
        "synced_members": synced_members,
        "private_domain": private_domain,
    }
