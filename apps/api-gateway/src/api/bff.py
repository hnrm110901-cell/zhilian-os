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
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
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
    except Exception:
        return None


async def _cache_set(key: str, value: Dict) -> None:
    try:
        from src.services.redis_cache_service import RedisCacheService
        svc = RedisCacheService()
        await svc.set(key, value, expire=_BFF_CACHE_TTL)
    except Exception:
        pass


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
    store_id:          str,
    monthly_revenue_yuan: float = Query(default=0.0, description="月营收（元），用于财务影响评分"),
    refresh:           bool  = Query(default=False, description="强制刷新缓存"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession   = Depends(get_db),
):
    """
    店长手机主屏一次性聚合：
    - health_score: 门店健康指数（5维度）
    - top3_decisions: Top3 决策（含 ¥ 预期收益）
    - queue_status: 当前排队状态
    - pending_approvals_count: 待审批决策数
    - unread_alerts_count: 未读告警数
    """
    cache_key = f"bff:sm:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    # 并行拉取所有子数据
    health_task    = _fetch_health_score(store_id, db)
    top3_task      = _fetch_top3_decisions(store_id, monthly_revenue_yuan, db)
    queue_task     = _fetch_queue_status(store_id, db)
    pending_task   = _fetch_pending_count(store_id, db)

    health, top3, queue, pending = await asyncio.gather(
        _safe(health_task, default=None),
        _safe(top3_task,   default=[]),
        _safe(queue_task,  default=None),
        _safe(pending_task, default=0),
    )

    payload = {
        "store_id":               store_id,
        "as_of":                  datetime.utcnow().isoformat(),
        "health_score":           health,
        "top3_decisions":         top3,
        "queue_status":           queue,
        "pending_approvals_count": pending,
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/chef/{store_id} ───────────────────────────────────────────

@router.get("/chef/{store_id}", summary="厨师长手机屏聚合数据")
async def chef_home(
    store_id:  str,
    refresh:   bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession   = Depends(get_db),
):
    """
    厨师长手机屏一次性聚合：
    - food_cost_variance: 食材成本差异分析（含 _yuan 字段）
    - waste_top5: 损耗Top5 排名（含 waste_cost_yuan）
    - inventory_alerts: 库存告警列表
    """
    cache_key = f"bff:chef:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    fc_task   = _fetch_food_cost_variance(store_id, db)
    waste_task = _fetch_waste_top5(store_id, db)
    inv_task  = _fetch_inventory_alerts(store_id, db)

    fc, waste, inv = await asyncio.gather(
        _safe(fc_task,    default=None),
        _safe(waste_task, default=[]),
        _safe(inv_task,   default=[]),
    )

    payload = {
        "store_id":           store_id,
        "as_of":              datetime.utcnow().isoformat(),
        "food_cost_variance": fc,
        "waste_top5":         waste,
        "inventory_alerts":   inv,
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/floor/{store_id} ──────────────────────────────────────────

@router.get("/floor/{store_id}", summary="楼面经理平板屏聚合数据")
async def floor_home(
    store_id:  str,
    target_date: Optional[date] = None,
    refresh:   bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession   = Depends(get_db),
):
    """
    楼面经理平板屏一次性聚合：
    - queue_status: 排队状态（等候组数、预计等待分钟）
    - today_reservations: 今日预订列表（前10条）
    - service_alerts: 服务质量告警
    """
    cache_key = f"bff:floor:{store_id}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return {**cached, "_from_cache": True}

    queue_task = _fetch_queue_status(store_id, db)
    resv_task  = _fetch_today_reservations(store_id, target_date, db)
    svc_task   = _fetch_service_alerts(store_id, db)

    queue, reservations, svc = await asyncio.gather(
        _safe(queue_task, default=None),
        _safe(resv_task,  default=[]),
        _safe(svc_task,   default=[]),
    )

    payload = {
        "store_id":          store_id,
        "as_of":             datetime.utcnow().isoformat(),
        "queue_status":      queue,
        "today_reservations": reservations,
        "service_alerts":    svc,
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/hq ────────────────────────────────────────────────────────

@router.get("/hq", summary="总部桌面大屏聚合数据")
async def hq_overview(
    refresh:   bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession   = Depends(get_db),
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

    health_task       = _fetch_all_stores_health(db)
    fc_rank_task      = _fetch_hq_food_cost_ranking(db)
    pending_task      = _fetch_pending_count(store_id=None, db=db)
    trend_task        = _fetch_revenue_trend(db)
    decisions_task    = _fetch_cross_store_decisions(db)

    health_ranking, fc_ranking, pending, revenue_trend, cross_decisions = await asyncio.gather(
        _safe(health_task,       default=[]),
        _safe(fc_rank_task,      default=[]),
        _safe(pending_task,      default=0),
        _safe(trend_task,        default={}),
        _safe(decisions_task,    default=[]),
    )

    # 计算汇总指标
    avg_health = (
        round(sum(s.get("score", 0) for s in health_ranking) / len(health_ranking), 1)
        if health_ranking else 0.0
    )
    total_revenue_yuan = round(sum(s.get("revenue_yuan", 0) or 0 for s in health_ranking), 2)
    critical_count     = sum(1 for s in health_ranking if s.get("level") == "critical")
    warning_count      = sum(1 for s in health_ranking if s.get("level") == "warning")

    payload = {
        "as_of":                    datetime.utcnow().isoformat(),
        "stores_health_ranking":    health_ranking,
        "food_cost_ranking":        fc_ranking,
        "pending_approvals_count":  pending,
        "revenue_trend":            revenue_trend,
        "cross_store_decisions":    cross_decisions,
        "hq_summary": {
            "store_count":          len(health_ranking),
            "avg_health_score":     avg_health,
            "total_revenue_yuan":   total_revenue_yuan,
            "critical_store_count": critical_count,
            "warning_store_count":  warning_count,
        },
    }

    await _cache_set(cache_key, payload)
    return {**payload, "_from_cache": False}


# ── GET /api/v1/bff/sm/{store_id}/notifications ───────────────────────────────

@router.get("/sm/{store_id}/notifications", summary="店长通知列表")
async def sm_notifications(
    store_id:  str,
    limit:     int  = Query(default=20, le=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession   = Depends(get_db),
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
    result  = await db.execute(stmt)
    records = result.scalars().all()

    notifications = []
    for r in records:
        suggestion = r.ai_suggestion or {}
        notifications.append({
            "id":                   r.id,
            "type":                 "pending_decision",
            "title":                suggestion.get("action", "待审批决策"),
            "expected_saving_yuan": suggestion.get("expected_saving_yuan", 0.0),
            "confidence_pct":       round(float(r.ai_confidence or 0) * 100, 1),
            "created_at":           r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "store_id": store_id,
        "total":    len(notifications),
        "items":    notifications,
    }


# ── 内部子调用实现 ─────────────────────────────────────────────────────────────

async def _fetch_health_score(store_id: str, db: AsyncSession) -> Optional[Dict]:
    from src.services.store_health_service import StoreHealthService
    return await StoreHealthService.get_store_score(
        store_id=store_id, target_date=date.today(), db=db
    )


async def _fetch_top3_decisions(
    store_id: str, monthly_revenue_yuan: float, db: AsyncSession
) -> List[Dict]:
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
            "ticket_no":  r[0],
            "party_size": r[1],
            "wait_min":   round(float(r[2]), 0),
            "status":     r[3],
        }
        for r in items_res.fetchall()
    ]

    return {
        "waiting_count":   int(row[0]),
        "avg_wait_min":    round(float(row[1]), 1),
        "served_today":    served_today,
        "queue_items":     queue_items,
    }


async def _fetch_pending_count(store_id: Optional[str], db: AsyncSession) -> int:
    from sqlalchemy import select, func
    from src.models.decision_log import DecisionLog, DecisionStatus

    stmt = select(func.count()).where(DecisionLog.decision_status == DecisionStatus.PENDING)
    if store_id:
        stmt = stmt.where(DecisionLog.store_id == store_id)
    return (await db.scalar(stmt)) or 0


async def _fetch_food_cost_variance(store_id: str, db: AsyncSession) -> Optional[Dict]:
    from src.services.food_cost_service import FoodCostService
    return await FoodCostService.get_store_food_cost_variance(store_id=store_id, db=db)


async def _fetch_waste_top5(store_id: str, db: AsyncSession) -> List[Dict]:
    from src.services.waste_guard_service import WasteGuardService
    from datetime import timedelta
    end   = date.today()
    start = end - timedelta(days=7)
    result = await WasteGuardService.get_top5_waste(
        store_id=store_id, start_date=start, end_date=end, db=db
    )
    return result.get("items", []) if isinstance(result, dict) else []


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
            "ingredient_name":  r[0],
            "current_stock":    float(r[1]),
            "reorder_point":    float(r[2]),
            "unit":             r[3],
            "alert_type":       "low",
            "severity":         r[4],
            "suggested_action": f"补货 {r[0]}，当前库存 {r[1]} {r[3]}",
        }
        for r in rows
    ]


async def _fetch_today_reservations(
    store_id: str, target_date: Optional[date], db: AsyncSession
) -> List[Dict]:
    from sqlalchemy import text
    tdate = target_date or date.today()
    result = await db.execute(
        text("""
            SELECT id, customer_name, party_size, reservation_date,
                   reservation_time, table_number, status, notes
            FROM reservations
            WHERE store_id = :sid
              AND reservation_date = :tdate
              AND status NOT IN ('cancelled', 'no_show')
            ORDER BY reservation_time ASC NULLS LAST
            LIMIT 10
        """),
        {"sid": store_id, "tdate": tdate.isoformat()},
    )
    rows = result.fetchall()
    return [
        {
            "id":            str(r[0]),
            "guest_name":    r[1],
            "party_size":    r[2],
            "reserved_time": (
                f"{r[3]}T{r[4]}" if r[4] else str(r[3])
            ),
            "table_number":  r[5],
            "status":        r[6],
            "notes":         r[7],
        }
        for r in rows
    ]


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
            "alert_type":  r[0],
            "severity":    r[1],
            "description": r[2],
            "created_at":  r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
        }
        for r in rows
    ]


async def _fetch_all_stores_health(db: AsyncSession) -> List[Dict]:
    from src.services.store_health_service import StoreHealthService
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT id FROM stores WHERE is_active = true ORDER BY id LIMIT 50")
    )
    store_ids = [r[0] for r in result.fetchall()]
    if not store_ids:
        return []
    return await StoreHealthService.get_multi_store_scores(
        store_ids=store_ids, target_date=date.today(), db=db
    )


async def _fetch_hq_food_cost_ranking(db: AsyncSession) -> List[Dict]:
    from src.services.food_cost_service import FoodCostService
    from sqlalchemy import text
    from datetime import timedelta
    end   = date.today()
    start = end - timedelta(days=7)
    result = await FoodCostService.get_hq_food_cost_ranking(
        start_date=start, end_date=end, db=db
    )
    stores = result.get("stores", []) if isinstance(result, dict) else []

    # 若 BOM 数据缺失（全部 actual_cost_pct=0），回退读 kpi_records
    if all(s.get("actual_cost_pct", 0) == 0 for s in stores):
        stores = await _food_cost_ranking_from_kpi(db)

    return stores


async def _food_cost_ranking_from_kpi(db: AsyncSession) -> List[Dict]:
    """从 kpi_records 读取各店近30天 KPI_COST_RATE 均值，生成食材成本排名。"""
    from sqlalchemy import text
    from datetime import timedelta
    end   = date.today()
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
        result.append({
            "store_id":       r[0],
            "store_name":     r[1],
            "actual_cost_pct": actual,
            "theoretical_pct": target,
            "variance_pct":   round(actual - target, 2),
            "variance_status": (
                "critical" if actual - target > 3
                else "warning" if actual - target > 1
                else "ok"
            ),
            "rank": i,
        })
    return result


async def _fetch_revenue_trend(db: AsyncSession) -> Dict:
    """近7天全平台按门店每日营收趋势（从 kpi_records 读取）。"""
    from sqlalchemy import text
    from datetime import timedelta
    end   = date.today()
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
        stores.append({
            "store_id":   sid,
            "store_name": info["store_name"],
            "values":     [info["values"].get(d, 0) for d in dates],
        })

    return {"dates": dates, "stores": stores}


async def _fetch_cross_store_decisions(db: AsyncSession) -> List[Dict]:
    """跨门店紧急决策汇总：取库存告警最多5家店的 Top1 决策，合并排序。"""
    from sqlalchemy import text
    # 查有 critical/out_of_stock 库存告警的门店，最多取5家
    rows = await db.execute(
        text("""
            SELECT DISTINCT store_id FROM inventory_items
            WHERE status IN ('critical', 'out_of_stock')
            LIMIT 5
        """)
    )
    store_ids = [r[0] for r in rows.fetchall()]
    if not store_ids:
        return []

    from src.services.decision_priority_engine import DecisionPriorityEngine
    tasks = [
        _safe(DecisionPriorityEngine(store_id=sid).get_top3(db=db), default=[])
        for sid in store_ids
    ]
    results = await asyncio.gather(*tasks)

    merged = []
    for sid, decisions in zip(store_ids, results):
        if decisions:
            top = decisions[0]
            merged.append({**top, "store_id": sid})

    merged.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
    return merged[:5]
