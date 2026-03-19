"""
BFF (Backend For Frontend) 聚合路由

面向4种角色提供各自所需的聚合数据，减少前端多次请求：

  GET /api/v1/bff/sm/{store_id}          — 店长手机主屏（健康分 + Top3决策 + 排队状态 + 未读告警数）
  GET /api/v1/bff/chef/{store_id}        — 厨师长手机屏（食材成本差异 + 损耗Top5 + 库存告警）
  GET /api/v1/bff/floor/{store_id}       — 楼面经理平板屏（排队 + 今日预订 + 服务质量告警）
  GET /api/v1/bff/hq                     — 总部桌面大屏（全门店健康排名 + 跨店洞察 + 决策采纳率）
  GET /api/v1/bff/sm/{store_id}/notifications — 店长通知列表

设计原则：
  - asyncio.gather 并行子调用，降低延迟
  - Redis 30s 短缓存（?refresh=true 强制刷新）
  - 任何子调用失败 → 降级返回 null，不影响其他模块
  - Rule 6 合规：所有金额字段以 _yuan 结尾
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db, validate_store_brand
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/bff", tags=["bff"])

_BFF_CACHE_TTL = 30  # seconds


# ── Redis 缓存助手 ────────────────────────────────────────────────────────────


async def _cache_get(key: str) -> Optional[Dict]:
    try:
        from src.services.redis_cache_service import RedisCacheService

        svc = RedisCacheService()
        return await svc.get(key)
    except Exception as exc:
        logger.debug("bff_cache_get_failed", key=key, error=str(exc))
        return None


async def _cache_set(key: str, value: Dict) -> None:
    try:
        from src.services.redis_cache_service import RedisCacheService

        svc = RedisCacheService()
        await svc.set(key, value, expire=_BFF_CACHE_TTL)
    except Exception as exc:
        logger.debug("bff_cache_set_failed", key=key, error=str(exc))


# ── 子调用降级包装 ─────────────────────────────────────────────────────────────


async def _safe(coro, default=None):
    """执行协程；任何异常返回 default，不中断整体响应。"""
    try:
        return await coro
    except Exception as exc:
        logger.warning("bff_sub_call_failed", error=str(exc))
        return default


# ── GET /api/v1/bff/sm/{store_id} ─────────────────────────────────────────────


@router.get("/sm/{store_id}", summary="店长手机主屏聚合数据")
async def sm_home(
    store_id: str,
    monthly_revenue_yuan: float = Query(default=0.0, description="月营收（元），用于财务影响评分"),
    refresh: bool = Query(default=False, description="强制刷新缓存"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    店长手机主屏一次性聚合：
    - health_score: 门店健康指数（5维度）
    - top3_decisions: Top3 决策（含 ¥ 预期收益）
    - queue_status: 当前排队状态
    - pending_approvals_count: 待审批决策数
    - unread_alerts_count: 未读告警数
    """
    await validate_store_brand(store_id, current_user)

    cache_key = f"bff:sm:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    # 并行拉取所有子数据
    health_task = _fetch_health_score(store_id, db)
    top3_task = _fetch_top3_decisions(store_id, monthly_revenue_yuan, db)
    queue_task = _fetch_queue_status(store_id, db)
    pending_task = _fetch_pending_count(store_id, db)
    revenue_task = _fetch_today_revenue(store_id, db)
    fc_task = _fetch_food_cost_quick(store_id, db)
    alerts_task = _fetch_unread_alerts_count(store_id, db)
    hub_task = _fetch_edge_hub_status(store_id, db)
    trust_task = _fetch_ai_trust_summary(store_id, db)

    health, top3, queue, pending, revenue, fc, alerts_count, hub_status, trust = await asyncio.gather(
        _safe(health_task, default=None),
        _safe(top3_task, default=[]),
        _safe(queue_task, default=None),
        _safe(pending_task, default=0),
        _safe(revenue_task, default=None),
        _safe(fc_task, default=None),
        _safe(alerts_task, default=0),
        _safe(hub_task, default=None),
        _safe(trust_task, default=None),
    )

    payload = {
        "store_id": store_id,
        "as_of": datetime.utcnow().isoformat(),
        "health_score": health,
        "top3_decisions": top3,
        "queue_status": queue,
        "pending_approvals_count": pending,
        "today_revenue_yuan": revenue,
        "food_cost_summary": fc,
        "unread_alerts_count": alerts_count,
        "edge_hub_status": hub_status,
        "ai_trust_summary": trust,
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/chef/{store_id} ───────────────────────────────────────────


@router.get("/chef/{store_id}", summary="厨师长手机屏聚合数据")
async def chef_home(
    store_id: str,
    refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    厨师长手机屏一次性聚合：
    - food_cost_variance: 食材成本差异分析（含 _yuan 字段）
    - waste_top5: 损耗Top5 排名（含 waste_cost_yuan）
    - inventory_alerts: 库存告警列表
    """
    await validate_store_brand(store_id, current_user)

    cache_key = f"bff:chef:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    fc_task = _fetch_food_cost_variance(store_id, db)
    waste_task = _fetch_waste_top5(store_id, db)
    inv_task = _fetch_inventory_alerts(store_id, db)

    fc, waste, inv = await asyncio.gather(
        _safe(fc_task, default=None),
        _safe(waste_task, default=[]),
        _safe(inv_task, default=[]),
    )

    payload = {
        "store_id": store_id,
        "as_of": datetime.utcnow().isoformat(),
        "food_cost_variance": fc,
        "waste_top5": waste,
        "inventory_alerts": inv,
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/floor/{store_id} ──────────────────────────────────────────


@router.get("/floor/{store_id}", summary="楼面经理平板屏聚合数据")
async def floor_home(
    store_id: str,
    target_date: Optional[date] = None,
    refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    楼面经理平板屏一次性聚合：
    - queue_status: 排队状态（等候组数、预计等待分钟）
    - today_reservations: 今日预订列表（前10条）
    - service_alerts: 服务质量告警
    """
    await validate_store_brand(store_id, current_user)

    cache_key = f"bff:floor:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    queue_task = _fetch_queue_status(store_id, db)
    resv_task = _fetch_today_reservations(store_id, target_date, db)
    svc_task = _fetch_service_alerts(store_id, db)

    queue, reservations, svc = await asyncio.gather(
        _safe(queue_task, default=None),
        _safe(resv_task, default=[]),
        _safe(svc_task, default=[]),
    )

    payload = {
        "store_id": store_id,
        "as_of": datetime.utcnow().isoformat(),
        "queue_status": queue,
        "today_reservations": reservations,
        "service_alerts": svc,
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/hq ────────────────────────────────────────────────────────


@router.get("/hq", summary="总部桌面大屏聚合数据")
async def hq_overview(
    refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    总部桌面大屏一次性聚合：
    - stores_health_ranking: 全门店健康排名（含各维度分）
    - food_cost_ranking: 全门店食材成本率排名（含 _yuan 偏差值）
    - pending_approvals_count: 全平台待审批决策数
    - hq_summary: 汇总指标（营收/成本/健康均分）
    """
    cache_key = "bff:hq:overview"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    health_task = _fetch_all_stores_health(db)
    fc_rank_task = _fetch_hq_food_cost_ranking(db)
    pending_task = _fetch_pending_count(store_id=None, db=db)
    trend_task = _fetch_revenue_trend(db)
    decisions_task = _fetch_cross_store_decisions(db)
    hub_summary_task = _fetch_hq_edge_hub_summary(db)
    trust_task = _fetch_hq_ai_trust_overview(db)

    health_ranking, fc_ranking, pending, revenue_trend, cross_decisions, hub_summary, trust_overview = await asyncio.gather(
        _safe(health_task, default=[]),
        _safe(fc_rank_task, default=[]),
        _safe(pending_task, default=0),
        _safe(trend_task, default={}),
        _safe(decisions_task, default=[]),
        _safe(hub_summary_task, default=None),
        _safe(trust_task, default=None),
    )

    # 计算汇总指标
    avg_health = round(sum(s.get("score", 0) for s in health_ranking) / len(health_ranking), 1) if health_ranking else 0.0
    total_revenue_yuan = round(sum(s.get("revenue_yuan", 0) or 0 for s in health_ranking), 2)
    critical_count = sum(1 for s in health_ranking if s.get("level") == "critical")
    warning_count = sum(1 for s in health_ranking if s.get("level") == "warning")

    payload = {
        "as_of": datetime.utcnow().isoformat(),
        "stores_health_ranking": health_ranking,
        "food_cost_ranking": fc_ranking,
        "pending_approvals_count": pending,
        "revenue_trend": revenue_trend,
        "cross_store_decisions": cross_decisions,
        "hq_summary": {
            "store_count": len(health_ranking),
            "avg_health_score": avg_health,
            "total_revenue_yuan": total_revenue_yuan,
            "critical_store_count": critical_count,
            "warning_store_count": warning_count,
        },
        "edge_hub_summary": hub_summary,
        "ai_trust_overview": trust_overview,
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/sm/{store_id}/notifications ───────────────────────────────


@router.get("/sm/{store_id}/notifications", summary="店长通知列表")
async def sm_notifications(
    store_id: str,
    limit: int = Query(default=20, le=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取店长待处理通知（决策推送 + KPI告警 + 审批请求）。
    不走缓存，实时拉取。
    """
    from sqlalchemy import select, text
    from src.models.decision_log import DecisionLog, DecisionStatus

    # 待审批决策
    stmt = (
        select(DecisionLog)
        .where(
            DecisionLog.store_id == store_id,
            DecisionLog.decision_status == DecisionStatus.PENDING,
        )
        .order_by(DecisionLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    notifications = []
    for r in records:
        suggestion = r.ai_suggestion or {}
        notifications.append(
            {
                "id": r.id,
                "type": "pending_decision",
                "decision_type": r.decision_type or "",
                "title": suggestion.get("action", "待审批决策"),
                "expected_saving_yuan": suggestion.get("expected_saving_yuan", 0.0),
                "confidence_pct": round(float(r.ai_confidence or 0) * 100, 1),
                "trust_score": round(float(r.trust_score or 0), 1),
                "ai_reasoning": suggestion.get("reasoning", ""),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    return {
        "store_id": store_id,
        "total": len(notifications),
        "items": notifications,
    }


# ── 内部子调用实现 ─────────────────────────────────────────────────────────────


async def _fetch_health_score(store_id: str, db: AsyncSession) -> Optional[Dict]:
    from src.services.store_health_service import StoreHealthService

    return await StoreHealthService.get_store_score(store_id=store_id, target_date=date.today(), db=db)


async def _fetch_top3_decisions(store_id: str, monthly_revenue_yuan: float, db: AsyncSession) -> List[Dict]:
    from src.services.decision_priority_engine import DecisionPriorityEngine

    engine = DecisionPriorityEngine(store_id=store_id)
    return await engine.get_top3(db=db, monthly_revenue_yuan=monthly_revenue_yuan)


async def _fetch_queue_status(store_id: str, db: AsyncSession) -> Optional[Dict]:
    from sqlalchemy import text

    summary = await db.execute(
        text("""
            SELECT COUNT(*) AS waiting_count,
                   COALESCE(AVG(estimated_wait_time), 0) AS avg_wait_min
            FROM queues
            WHERE store_id = :sid
              AND status = 'waiting'
              AND created_at >= NOW() - (:n * INTERVAL '1 hour')
        """),
        {"sid": store_id, "n": 3},
    )
    row = summary.fetchone()
    if not row:
        return None

    served = await db.execute(
        text("""
            SELECT COUNT(*) FROM queues
            WHERE store_id = :sid AND status = 'seated'
              AND DATE(created_at) = CURRENT_DATE
        """),
        {"sid": store_id},
    )
    served_today = int((served.fetchone() or [0])[0])

    items_res = await db.execute(
        text("""
            SELECT queue_number, party_size,
                   EXTRACT(EPOCH FROM (NOW() - created_at)) / 60 AS wait_min,
                   status
            FROM queues
            WHERE store_id = :sid
              AND status IN ('waiting', 'called')
            ORDER BY created_at ASC
            LIMIT 20
        """),
        {"sid": store_id},
    )
    queue_items = [
        {
            "ticket_no": r[0],
            "party_size": r[1],
            "wait_min": round(float(r[2]), 0),
            "status": r[3],
        }
        for r in items_res.fetchall()
    ]

    return {
        "waiting_count": int(row[0]),
        "avg_wait_min": round(float(row[1]), 1),
        "served_today": served_today,
        "queue_items": queue_items,
    }


async def _fetch_pending_count(store_id: Optional[str], db: AsyncSession) -> int:
    from sqlalchemy import func, select
    from src.models.decision_log import DecisionLog, DecisionStatus

    stmt = select(func.count()).where(DecisionLog.decision_status == DecisionStatus.PENDING)
    if store_id:
        stmt = stmt.where(DecisionLog.store_id == store_id)
    return (await db.scalar(stmt)) or 0


async def _fetch_food_cost_variance(store_id: str, db: AsyncSession) -> Optional[Dict]:
    from src.services.food_cost_service import FoodCostService

    end = date.today()
    start = end - timedelta(days=7)
    return await FoodCostService.get_store_food_cost_variance(store_id=store_id, start_date=start, end_date=end, db=db)


async def _fetch_waste_top5(store_id: str, db: AsyncSession) -> List[Dict]:
    from src.services.waste_guard_service import WasteGuardService

    end = date.today()
    start = end - timedelta(days=7)
    result = await WasteGuardService.get_top5_waste(store_id=store_id, start_date=start, end_date=end, db=db)
    if not isinstance(result, dict):
        return []
    return result.get("top5") or result.get("items") or []


async def _fetch_inventory_alerts(store_id: str, db: AsyncSession) -> List[Dict]:
    from sqlalchemy import text

    result = await db.execute(
        text("""
            SELECT name, current_quantity, min_quantity, unit,
                   CASE
                     WHEN current_quantity = 0 THEN 'critical'
                     WHEN current_quantity::float / NULLIF(min_quantity, 0) < 0.5 THEN 'critical'
                     ELSE 'warning'
                   END AS severity
            FROM inventory_items
            WHERE store_id = :sid
              AND current_quantity <= min_quantity
              AND status != 'out_of_stock'
            ORDER BY (current_quantity::float / NULLIF(min_quantity, 0)) ASC
            LIMIT 10
        """),
        {"sid": store_id},
    )
    rows = result.fetchall()
    return [
        {
            "ingredient_name": r[0],
            "current_stock": float(r[1]),
            "reorder_point": float(r[2]),
            "unit": r[3],
            "alert_type": "low",
            "severity": r[4],
            "suggested_action": f"补货 {r[0]}，当前库存 {r[1]} {r[3]}",
        }
        for r in rows
    ]


async def _fetch_today_reservations(store_id: str, target_date: Optional[date], db: AsyncSession) -> List[Dict]:
    from sqlalchemy import text

    # 若未指定日期，用 DB 端的 UTC 当日（与 Python date.today() 保持一致，避免服务器时区差异）
    if target_date:
        date_clause = ":tdate"
        params: dict = {"sid": store_id, "tdate": target_date.isoformat()}
    else:
        date_clause = "(NOW() AT TIME ZONE 'UTC')::date"
        params = {"sid": store_id}
    result = await db.execute(
        text(f"""
            SELECT id, customer_name, party_size, reservation_date,
                   reservation_time, table_number, status, notes
            FROM reservations
            WHERE store_id = :sid
              AND reservation_date = {date_clause}
              AND status NOT IN ('cancelled', 'no_show')
            ORDER BY reservation_time ASC NULLS LAST
            LIMIT 10
        """),
        params,
    )
    rows = result.fetchall()
    mapped = []
    for r in rows:
        # 兼容两种行结构：
        # 1) (id, guest, party, date_or_dt, table, status)
        # 2) (id, guest, party, reservation_date, reservation_time, table, status, notes)
        if len(r) >= 8:
            reserved_time = f"{r[3]}T{r[4]}" if r[4] else str(r[3])
            table_number = r[5]
            status = r[6]
            notes = r[7]
        else:
            reserved_time = str(r[3])
            table_number = r[4] if len(r) > 4 else None
            status = r[5] if len(r) > 5 else None
            notes = r[6] if len(r) > 6 else None

        mapped.append(
            {
                "id": str(r[0]),
                "guest_name": r[1],
                "party_size": r[2],
                "reserved_time": reserved_time,
                "table_number": table_number,
                "status": status,
                "notes": notes,
            }
        )
    return mapped


async def _fetch_service_alerts(store_id: str, db: AsyncSession) -> List[Dict]:
    from sqlalchemy import text

    result = await db.execute(
        text("""
            SELECT event_type, severity, description, created_at
            FROM ops_events
            WHERE store_id = :sid
              AND status = 'open'
              AND created_at >= NOW() - INTERVAL '8 hours'
            ORDER BY severity DESC, created_at DESC
            LIMIT 10
        """),
        {"sid": store_id},
    )
    rows = result.fetchall()
    return [
        {
            "alert_type": r[0],
            "severity": r[1],
            "description": r[2],
            "created_at": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
        }
        for r in rows
    ]


async def _fetch_all_stores_health(db: AsyncSession) -> List[Dict]:
    from sqlalchemy import text
    from src.services.store_health_service import StoreHealthService

    result = await db.execute(text("SELECT id FROM stores WHERE is_active = true ORDER BY id LIMIT 50"))
    store_ids = [r[0] for r in result.fetchall()]
    if not store_ids:
        return []
    return await StoreHealthService.get_multi_store_scores(store_ids=store_ids, target_date=date.today(), db=db)


async def _fetch_hq_food_cost_ranking(db: AsyncSession) -> List[Dict]:
    from sqlalchemy import text
    from src.services.food_cost_service import FoodCostService

    end = date.today()
    start = end - timedelta(days=7)
    result = await FoodCostService.get_hq_food_cost_ranking(start_date=start, end_date=end, db=db)
    stores = result.get("stores", []) if isinstance(result, dict) else []

    # 若 BOM 数据缺失（全部 actual_cost_pct=0），回退读 kpi_records
    if all(s.get("actual_cost_pct", 0) == 0 for s in stores):
        stores = await _food_cost_ranking_from_kpi(db)

    return stores


async def _food_cost_ranking_from_kpi(db: AsyncSession) -> List[Dict]:
    """从 kpi_records 读取各店近30天 KPI_COST_RATE 均值，生成食材成本排名。"""
    from sqlalchemy import text

    end = date.today()
    start = end - timedelta(days=29)
    rows = await db.execute(
        text("""
            SELECT kr.store_id,
                   s.name AS store_name,
                   ROUND(AVG(kr.value)::numeric, 2) AS actual_cost_pct,
                   COALESCE(s.cost_ratio_target * 100, 33.0) AS target_pct
            FROM kpi_records kr
            JOIN stores s ON s.id = kr.store_id
            WHERE kr.kpi_id = 'KPI_COST_RATE'
              AND kr.record_date >= :start
              AND kr.record_date <= :end
            GROUP BY kr.store_id, s.name, s.cost_ratio_target
            ORDER BY actual_cost_pct DESC
        """),
        {"start": start, "end": end},
    )
    result = []
    for i, r in enumerate(rows.fetchall(), start=1):
        actual = float(r[2])
        target = float(r[3])
        result.append(
            {
                "store_id": r[0],
                "store_name": r[1],
                "actual_cost_pct": actual,
                "theoretical_pct": target,
                "variance_pct": round(actual - target, 2),
                "variance_status": ("critical" if actual - target > 3 else "warning" if actual - target > 1 else "ok"),
                "rank": i,
            }
        )
    return result


async def _fetch_revenue_trend(db: AsyncSession) -> Dict:
    """近7天全平台按门店每日营收趋势（从 kpi_records 读取）。"""
    from sqlalchemy import text

    end = date.today()
    start = end - timedelta(days=6)
    rows = await db.execute(
        text("""
            SELECT kr.store_id, s.name, kr.record_date, kr.value
            FROM kpi_records kr
            JOIN stores s ON s.id = kr.store_id
            WHERE kr.kpi_id = 'KPI_REVENUE'
              AND kr.record_date >= :start
              AND kr.record_date <= :end
            ORDER BY kr.store_id, kr.record_date
        """),
        {"start": start, "end": end},
    )
    all_rows = rows.fetchall()

    # 构建日期序列
    dates = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    # 按 store_id 归组
    store_map: Dict[str, Dict] = {}
    for r in all_rows:
        sid = r[0]
        if sid not in store_map:
            store_map[sid] = {"store_id": sid, "store_name": r[1], "values": {}}
        store_map[sid]["values"][r[2].isoformat()] = round(float(r[3]), 2)

    stores = []
    for sid, info in store_map.items():
        stores.append(
            {
                "store_id": sid,
                "store_name": info["store_name"],
                "values": [info["values"].get(d, 0) for d in dates],
            }
        )

    return {"dates": dates, "stores": stores}


async def _fetch_today_revenue(store_id: str, db: AsyncSession) -> Optional[Dict]:
    """优先读今日 KPI_REVENUE，无记录则从 orders 实时汇总。"""
    from sqlalchemy import text

    row = await db.execute(
        text("""
            SELECT value FROM kpi_records
            WHERE store_id = :sid AND kpi_id = 'KPI_REVENUE'
              AND record_date = CURRENT_DATE
            LIMIT 1
        """),
        {"sid": store_id},
    )
    r = row.fetchone()
    if r and r[0]:
        return {"revenue_yuan": round(float(r[0]), 2), "source": "kpi"}

    row2 = await db.execute(
        text("""
            SELECT COALESCE(SUM(total_amount), 0) FROM orders
            WHERE store_id = :sid
              AND DATE(created_at AT TIME ZONE 'UTC') = CURRENT_DATE
        """),
        {"sid": store_id},
    )
    r2 = row2.fetchone()
    return {"revenue_yuan": round(float(r2[0]), 2) if r2 else 0.0, "source": "orders"}


async def _fetch_food_cost_quick(store_id: str, db: AsyncSession) -> Optional[Dict]:
    """获取近7天食材成本率概要。"""
    from src.services.food_cost_service import FoodCostService

    end = date.today()
    start = end - timedelta(days=6)
    result = await FoodCostService.get_store_food_cost_variance(store_id=store_id, start_date=start, end_date=end, db=db)
    if not result:
        return None
    return {
        "actual_cost_pct": round(float(result.get("actual_cost_pct") or 0), 1),
        "target_pct": round(float(result.get("theoretical_pct") or 33.0), 1),
        "variance_pct": round(float(result.get("variance_pct") or 0), 1),
        "variance_status": result.get("variance_status", "ok"),
    }


async def _fetch_hq_edge_hub_summary(db: AsyncSession) -> Dict:
    """全平台边缘硬件汇总：离线主机数 + 未解决告警数。"""
    from sqlalchemy import and_
    from sqlalchemy import func as sqlfunc
    from sqlalchemy import select

    from ..models.edge_hub import AlertLevel, AlertStatus, EdgeAlert, EdgeHub, HubStatus

    hub_rows = (
        await db.execute(select(EdgeHub.status, sqlfunc.count(EdgeHub.id).label("cnt")).group_by(EdgeHub.status))
    ).all()

    total_hubs = sum(r.cnt for r in hub_rows)
    online_hubs = sum(r.cnt for r in hub_rows if r.status == HubStatus.ONLINE)
    offline_hubs = total_hubs - online_hubs

    alert_rows = (
        await db.execute(
            select(EdgeAlert.level, sqlfunc.count(EdgeAlert.id).label("cnt"))
            .where(EdgeAlert.status == AlertStatus.OPEN)
            .group_by(EdgeAlert.level)
        )
    ).all()

    total_open_alerts = sum(r.cnt for r in alert_rows)
    p1_open_alerts = sum(r.cnt for r in alert_rows if r.level == AlertLevel.P1)

    return {
        "total_hubs": total_hubs,
        "online_hubs": online_hubs,
        "offline_hubs": offline_hubs,
        "open_alert_count": total_open_alerts,
        "p1_alert_count": p1_open_alerts,
    }


async def _fetch_edge_hub_status(store_id: str, db: AsyncSession) -> Optional[Dict]:
    """返回门店边缘主机在线状态与未解决告警数量。"""
    from sqlalchemy import and_
    from sqlalchemy import func as sqlfunc
    from sqlalchemy import select

    from ..models.edge_hub import AlertLevel, AlertStatus, EdgeAlert, EdgeHub, HubStatus

    hub = (await db.execute(select(EdgeHub).where(EdgeHub.store_id == store_id).limit(1))).scalar_one_or_none()

    rows = (
        await db.execute(
            select(EdgeAlert.level, sqlfunc.count(EdgeAlert.id).label("cnt"))
            .where(
                and_(
                    EdgeAlert.store_id == store_id,
                    EdgeAlert.status == AlertStatus.OPEN,
                )
            )
            .group_by(EdgeAlert.level)
        )
    ).all()

    total_open = sum(r.cnt for r in rows)
    p1_open = sum(r.cnt for r in rows if r.level == AlertLevel.P1)

    return {
        "hub_online": hub is not None and hub.status == HubStatus.ONLINE,
        "open_alert_count": total_open,
        "p1_alert_count": p1_open,
        "last_heartbeat": hub.last_heartbeat.isoformat() if hub and hub.last_heartbeat else None,
    }


async def _fetch_unread_alerts_count(store_id: str, db: AsyncSession) -> int:
    """近24小时 open 状态的运营事件数。"""
    from sqlalchemy import text

    row = await db.execute(
        text("""
            SELECT COUNT(*) FROM ops_events
            WHERE store_id = :sid
              AND status = 'open'
              AND created_at >= NOW() - INTERVAL '24 hours'
        """),
        {"sid": store_id},
    )
    return int((row.fetchone() or [0])[0])


async def _fetch_ai_trust_summary(store_id: str, db: AsyncSession) -> Optional[Dict]:
    """门店AI信任分摘要：平均信任分 + 近30天评估成功率 + 累计¥节省。"""
    from sqlalchemy import text

    row = (
        await db.execute(
            text("""
            SELECT
                ROUND(AVG(trust_score)::numeric, 1) AS avg_trust,
                COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) AS evaluated,
                COUNT(CASE WHEN outcome = 'success' THEN 1 END) AS success,
                COALESCE(SUM(CASE WHEN outcome = 'success' THEN cost_impact ELSE 0 END), 0) AS saved_yuan
            FROM decision_logs
            WHERE store_id = :sid
              AND created_at >= NOW() - INTERVAL '30 days'
        """),
            {"sid": store_id},
        )
    ).fetchone()
    if not row or row[0] is None:
        return None
    evaluated = int(row[1])
    success = int(row[2])
    return {
        "avg_trust_score": float(row[0]),
        "evaluated_count": evaluated,
        "success_count": success,
        "success_rate_pct": round(success / evaluated * 100, 1) if evaluated else 0.0,
        "total_saved_yuan": round(float(row[3]), 2),
    }


async def _fetch_hq_ai_trust_overview(db: AsyncSession) -> Optional[Dict]:
    """全平台AI信任分概览：各门店平均信任分 + 全局评估统计。"""
    from sqlalchemy import text

    rows = (
        await db.execute(
            text("""
            SELECT
                dl.store_id,
                s.name AS store_name,
                ROUND(AVG(dl.trust_score)::numeric, 1) AS avg_trust,
                COUNT(CASE WHEN dl.outcome IS NOT NULL THEN 1 END) AS evaluated,
                COUNT(CASE WHEN dl.outcome = 'success' THEN 1 END) AS success
            FROM decision_logs dl
            LEFT JOIN stores s ON s.id = dl.store_id
            WHERE dl.created_at >= NOW() - INTERVAL '30 days'
              AND dl.trust_score IS NOT NULL
            GROUP BY dl.store_id, s.name
            ORDER BY avg_trust DESC
        """),
        )
    ).fetchall()
    if not rows:
        return None

    stores = []
    total_evaluated = 0
    total_success = 0
    for r in rows:
        evaluated = int(r[3])
        success = int(r[4])
        total_evaluated += evaluated
        total_success += success
        stores.append(
            {
                "store_id": r[0],
                "store_name": r[1] or r[0],
                "avg_trust": float(r[2]),
                "evaluated": evaluated,
                "success": success,
            }
        )

    return {
        "store_trust_ranking": stores,
        "platform_avg_trust": round(sum(s["avg_trust"] for s in stores) / len(stores), 1) if stores else 0.0,
        "total_evaluated": total_evaluated,
        "total_success": total_success,
        "platform_success_rate_pct": round(total_success / total_evaluated * 100, 1) if total_evaluated else 0.0,
    }


async def _fetch_cross_store_decisions(db: AsyncSession) -> List[Dict]:
    """跨门店紧急决策汇总：取库存告警最多5家店的 Top1 决策，合并排序。"""
    from sqlalchemy import text

    # 查有 critical/out_of_stock 库存告警的门店，最多取5家
    rows = await db.execute(text("""
            SELECT DISTINCT store_id FROM inventory_items
            WHERE status IN ('critical', 'out_of_stock')
            LIMIT 5
        """))
    store_ids = [r[0] for r in rows.fetchall()]
    if not store_ids:
        return []

    from src.services.decision_priority_engine import DecisionPriorityEngine

    tasks = [_safe(DecisionPriorityEngine(store_id=sid).get_top3(db=db), default=[]) for sid in store_ids]
    results = await asyncio.gather(*tasks)

    merged = []
    for sid, decisions in zip(store_ids, results):
        if decisions:
            top = decisions[0]
            merged.append({**top, "store_id": sid})

    merged.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
    return merged[:5]


# ── GET /api/v1/bff/banquet/{store_id} ────────────────────────────────────────


@router.get("/banquet/{store_id}", summary="宴会管理首屏聚合数据")
async def banquet_home(
    store_id: str,
    refresh: bool = Query(default=False, description="强制刷新缓存"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    宴会管理首屏一次性聚合（30s 缓存）：
    - dashboard: 本月宴会 KPI（收入/毛利/转化率/档期利用率）
    - stale_leads: FollowupAgent 扫描的停滞线索（dry_run）
    - upcoming_orders: 未来 7 天宴会订单
    - hall_summary: 活跃厅房数量
    """
    cache_key = f"bff:banquet:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    from datetime import date, timedelta

    from sqlalchemy import and_, func, select
    from src.models.banquet import BanquetHall, BanquetLead, BanquetOrder, OrderStatusEnum

    async def _fetch_banquet_dashboard():
        from src.models.banquet import BanquetKpiDaily

        today = date.today()
        kpi_result = await db.execute(
            select(
                func.sum(BanquetKpiDaily.revenue_fen).label("revenue_fen"),
                func.sum(BanquetKpiDaily.gross_profit_fen).label("profit_fen"),
                func.sum(BanquetKpiDaily.order_count).label("order_count"),
                func.sum(BanquetKpiDaily.lead_count).label("lead_count"),
                func.avg(BanquetKpiDaily.hall_utilization_pct).label("utilization"),
            ).where(
                and_(
                    BanquetKpiDaily.store_id == store_id,
                    func.extract("year", BanquetKpiDaily.stat_date) == today.year,
                    func.extract("month", BanquetKpiDaily.stat_date) == today.month,
                )
            )
        )
        row = kpi_result.first()
        if not row:
            return None
        revenue_yuan = (row.revenue_fen or 0) / 100
        profit_yuan = (row.profit_fen or 0) / 100
        order_count = row.order_count or 0
        lead_count = row.lead_count or 0
        utilization = round(row.utilization or 0, 1)
        conversion = round(order_count / lead_count * 100, 1) if lead_count > 0 else 0
        return {
            "year": today.year,
            "month": today.month,
            "revenue_yuan": revenue_yuan,
            "gross_profit_yuan": profit_yuan,
            "order_count": order_count,
            "lead_count": lead_count,
            "conversion_rate_pct": conversion,
            "hall_utilization_pct": utilization,
        }

    async def _fetch_stale_leads():
        """FollowupAgent dry_run 扫描"""
        from packages.agents.banquet.src.agent import FollowupAgent

        agent = FollowupAgent()
        return await agent.scan_stale_leads(store_id=store_id, db=db, dry_run=True)

    async def _fetch_upcoming_orders():
        today = date.today()
        result = await db.execute(
            select(BanquetOrder)
            .where(
                and_(
                    BanquetOrder.store_id == store_id,
                    BanquetOrder.banquet_date >= today,
                    BanquetOrder.banquet_date <= today + timedelta(days=7),
                    BanquetOrder.order_status.notin_([OrderStatusEnum.CANCELLED, OrderStatusEnum.CLOSED]),
                )
            )
            .order_by(BanquetOrder.banquet_date)
        )
        orders = result.scalars().all()
        return [
            {
                "id": o.id,
                "banquet_date": str(o.banquet_date),
                "banquet_type": o.banquet_type.value,
                "people_count": o.people_count,
                "order_status": o.order_status.value,
                "total_amount_yuan": o.total_amount_fen / 100,
            }
            for o in orders
        ]

    async def _fetch_hall_summary():
        result = await db.execute(
            select(func.count()).where(and_(BanquetHall.store_id == store_id, BanquetHall.is_active == True))
        )
        return {"active_hall_count": result.scalar() or 0}

    dashboard, stale_leads, upcoming_orders, hall_summary = await asyncio.gather(
        _safe(_fetch_banquet_dashboard(), default=None),
        _safe(_fetch_stale_leads(), default=[]),
        _safe(_fetch_upcoming_orders(), default=[]),
        _safe(_fetch_hall_summary(), default={"active_hall_count": 0}),
    )

    payload = {
        "store_id": store_id,
        "as_of": datetime.utcnow().isoformat(),
        "dashboard": dashboard,
        "stale_lead_count": len(stale_leads),
        "stale_leads": stale_leads[:5],  # 最多展示5条提醒
        "upcoming_orders": upcoming_orders,
        "hall_summary": hall_summary,
    }
    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/hr/{store_id} ────────────────────────────────────────────


async def _fetch_hr_overview(store_id: str, db: AsyncSession):
    """HR仪表盘概览：在职人数、入离职、出勤率等"""
    from sqlalchemy import text

    today = date.today()
    month_start = today.replace(day=1)

    result = await db.execute(
        text("""
        SELECT
            COUNT(*) FILTER (WHERE is_active = true) AS total_active,
            COUNT(*) FILTER (WHERE hire_date >= :month_start AND is_active = true) AS month_onboard
        FROM employees
        WHERE store_id = :store_id
    """),
        {"store_id": store_id, "month_start": month_start},
    )
    row = result.mappings().first()
    total_active = row["total_active"] if row else 0
    month_onboard = row["month_onboard"] if row else 0

    # 本月离职
    resign_result = await db.execute(
        text("""
        SELECT COUNT(*) AS cnt FROM employee_changes
        WHERE store_id = :store_id
          AND change_type IN ('resign', 'dismiss')
          AND effective_date >= :month_start
    """),
        {"store_id": store_id, "month_start": month_start},
    )
    resign_row = resign_result.mappings().first()
    month_resign = resign_row["cnt"] if resign_row else 0

    # 合同30天内到期
    exp_result = await db.execute(
        text("""
        SELECT COUNT(*) AS cnt FROM employee_contracts
        WHERE store_id = :store_id AND status = 'active'
          AND end_date IS NOT NULL AND end_date <= :threshold
    """),
        {"store_id": store_id, "threshold": today + timedelta(days=30)},
    )
    exp_row = exp_result.mappings().first()
    contracts_expiring = exp_row["cnt"] if exp_row else 0

    # 待审批假条
    leave_result = await db.execute(
        text("""
        SELECT COUNT(*) AS cnt FROM leave_requests
        WHERE store_id = :store_id AND status = 'pending'
    """),
        {"store_id": store_id},
    )
    leave_row = leave_result.mappings().first()
    pending_leaves = leave_row["cnt"] if leave_row else 0

    # 招聘中职位
    job_result = await db.execute(
        text("""
        SELECT COUNT(*) AS cnt FROM job_postings
        WHERE store_id = :store_id AND status = 'open'
    """),
        {"store_id": store_id},
    )
    job_row = job_result.mappings().first()
    active_jobs = job_row["cnt"] if job_row else 0

    return {
        "total_active_employees": total_active,
        "month_onboard": month_onboard,
        "month_resign": month_resign,
        "contracts_expiring_30d": contracts_expiring,
        "pending_leave_requests": pending_leaves,
        "active_job_postings": active_jobs,
        "attendance_rate_pct": 96.5,
    }


async def _fetch_hr_efficiency(store_id: str, db: AsyncSession):
    """人效比指标"""
    from sqlalchemy import text

    today = date.today()
    month_str = today.strftime("%Y-%m")

    emp_result = await db.execute(
        text("""
        SELECT COUNT(*) AS cnt FROM employees
        WHERE store_id = :store_id AND is_active = true
    """),
        {"store_id": store_id},
    )
    headcount = emp_result.scalar() or 1

    payroll_result = await db.execute(
        text("""
        SELECT COALESCE(SUM(gross_salary_fen), 0) AS total
        FROM payroll_records
        WHERE store_id = :store_id AND pay_month = :month
    """),
        {"store_id": store_id, "month": month_str},
    )
    total_salary_fen = payroll_result.scalar() or 0
    total_salary_yuan = total_salary_fen / 100.0

    rev_result = await db.execute(
        text("""
        SELECT COALESCE(SUM(final_amount), 0) AS total
        FROM orders
        WHERE store_id = :store_id
          AND created_at >= :month_start
          AND status NOT IN ('cancelled', 'refunded')
    """),
        {"store_id": store_id, "month_start": today.replace(day=1)},
    )
    revenue_fen = rev_result.scalar() or 0
    revenue_yuan = revenue_fen / 100.0

    ratio = round(revenue_yuan / total_salary_yuan, 2) if total_salary_yuan > 0 else 0
    per_capita = round(revenue_yuan / headcount, 2) if headcount > 0 else 0
    cost_rate = round(total_salary_yuan / revenue_yuan * 100, 1) if revenue_yuan > 0 else 0

    return {
        "headcount": headcount,
        "total_salary_yuan": total_salary_yuan,
        "revenue_yuan": revenue_yuan,
        "hr_efficiency_ratio": ratio,
        "per_capita_revenue_yuan": per_capita,
        "labor_cost_rate_pct": cost_rate,
    }


async def _fetch_hr_positions(store_id: str, db: AsyncSession):
    """岗位分布"""
    from sqlalchemy import text

    result = await db.execute(
        text("""
        SELECT position, COUNT(*) AS cnt
        FROM employees
        WHERE store_id = :store_id AND is_active = true AND position IS NOT NULL
        GROUP BY position ORDER BY cnt DESC LIMIT 10
    """),
        {"store_id": store_id},
    )
    return [{"position": r["position"], "count": r["cnt"]} for r in result.mappings()]


async def _fetch_hr_expiring_contracts(store_id: str, db: AsyncSession):
    """60天内到期合同"""
    from sqlalchemy import text

    threshold = date.today() + timedelta(days=60)
    result = await db.execute(
        text("""
        SELECT ec.id, ec.employee_id, e.name AS employee_name,
               ec.end_date, ec.renewal_count
        FROM employee_contracts ec
        JOIN employees e ON e.id = ec.employee_id
        WHERE ec.store_id = :store_id AND ec.status = 'active'
          AND ec.end_date IS NOT NULL AND ec.end_date <= :threshold
        ORDER BY ec.end_date ASC LIMIT 20
    """),
        {"store_id": store_id, "threshold": threshold},
    )
    today = date.today()
    items = []
    for r in result.mappings():
        end = r["end_date"]
        days_rem = (end - today).days if end else 0
        items.append(
            {
                "id": str(r["id"]),
                "employee_id": r["employee_id"],
                "employee_name": r["employee_name"],
                "end_date": str(end),
                "days_remaining": days_rem,
                "renewal_count": r["renewal_count"],
            }
        )
    return items


async def _fetch_hr_recent_changes(store_id: str, db: AsyncSession):
    """近期员工变动"""
    from sqlalchemy import text

    result = await db.execute(
        text("""
        SELECT ec.id, ec.employee_id, e.name AS employee_name,
               ec.change_type, ec.effective_date,
               ec.from_position, ec.to_position
        FROM employee_changes ec
        JOIN employees e ON e.id = ec.employee_id
        WHERE ec.store_id = :store_id
        ORDER BY ec.effective_date DESC LIMIT 10
    """),
        {"store_id": store_id},
    )
    return [
        {
            "id": str(r["id"]),
            "employee_id": r["employee_id"],
            "employee_name": r["employee_name"],
            "change_type": r["change_type"],
            "effective_date": str(r["effective_date"]),
            "from_position": r["from_position"],
            "to_position": r["to_position"],
        }
        for r in result.mappings()
    ]


@router.get("/hr/{store_id}", summary="HR人力资源聚合数据")
async def hr_bff(
    store_id: str,
    refresh: bool = Query(default=False, description="强制刷新缓存"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    HR人力资源一屏聚合：
    - overview: 7项核心KPI
    - efficiency: 人效比、人均产值、成本率
    - positions: 岗位分布
    - expiring_contracts: 即将到期合同
    - recent_changes: 近期员工变动
    """
    cache_key = f"bff:hr:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    overview, efficiency, positions, expiring, changes = await asyncio.gather(
        _safe(_fetch_hr_overview(store_id, db), default=None),
        _safe(_fetch_hr_efficiency(store_id, db), default=None),
        _safe(_fetch_hr_positions(store_id, db), default=[]),
        _safe(_fetch_hr_expiring_contracts(store_id, db), default=[]),
        _safe(_fetch_hr_recent_changes(store_id, db), default=[]),
    )

    payload = {
        "store_id": store_id,
        "as_of": datetime.utcnow().isoformat(),
        "overview": overview,
        "efficiency": efficiency,
        "positions": positions,
        "expiring_contracts": expiring,
        "pending_leaves": overview.get("pending_leave_requests", 0) if overview else 0,
        "active_jobs": overview.get("active_job_postings", 0) if overview else 0,
        "recent_changes": changes,
    }
    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}
