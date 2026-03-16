"""
私域运营 API
Private Domain Operations API

原有能力：看板、RFM、信号、四象限、旅程、差评处理等。
扩展能力（用户增长）：user_portrait、funnel_optimize、realtime_metrics、personalized_recommend 等 18 个 action，
见 POST /execute 与 GET /actions。
"""

import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

# 向上查找包含 packages/ 的目录作为 repo_root
# Docker: /app/packages/  本地: <repo>/packages/
_repo_root = next(
    (p for p in Path(__file__).resolve().parents if (p / "packages").is_dir()),
    Path(__file__).resolve().parents[2],
)
agent_path = _repo_root / "packages" / "agents" / "private_domain" / "src"
_core_path = Path(__file__).resolve().parents[1] / "core"  # src/core（base_agent 所在目录）
for _p in (agent_path, _core_path):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from agent import PrivateDomainAgent
from growth_handlers import GROWTH_ACTIONS

router = APIRouter(prefix="/api/v1/private-domain", tags=["private_domain"])
logger = structlog.get_logger()


def _get_agent(store_id: str) -> PrivateDomainAgent:
    return PrivateDomainAgent(store_id=store_id)


# ─────────────────────────── Request Models ───────────────────────────


class TriggerJourneyRequest(BaseModel):
    journey_type: str
    customer_id: str


class ProcessReviewRequest(BaseModel):
    review_id: str
    customer_id: Optional[str] = None
    rating: int = 2
    content: str = ""


class QuadrantRequest(BaseModel):
    competition_density: float = 4.0
    member_count: int = 0
    estimated_population: int = 1000


class BatchTriggerRequest(BaseModel):
    customer_ids: List[str]
    journey_type: str


class MarkSignalRequest(BaseModel):
    action: str = "handled"


class TriggerLifecycleRequest(BaseModel):
    trigger: str  # StateTransitionTrigger value
    changed_by: str = "api"
    reason: Optional[str] = None


class TriggerJourneyV2Request(BaseModel):
    customer_id: str
    journey_type: str
    wechat_user_id: Optional[str] = None


class ExecuteRequest(BaseModel):
    """统一执行请求：action + params（兼容 input_data 包裹格式由调用方展平后传入）"""

    action: str
    params: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"action": "user_portrait", "params": {"segment_id": "default", "time_range": "last_30d"}},
                {"action": "nl_query", "params": {"query": "今日数据怎么样"}},
                {"action": "personalized_recommend", "params": {"user_id": "U001", "limit": 5}},
                {"action": "realtime_metrics", "params": {"store_ids": ["S001"], "metrics": ["dau", "traffic"]}},
            ]
        }
    }


# ─────────────────────────── Endpoints ───────────────────────────


@router.post(
    "/execute",
    summary="统一执行 action",
    response_description="success、data、execution_time；失败时 4xx/5xx 与 detail",
)
async def execute_action(
    body: ExecuteRequest,
    store_id: Optional[str] = Query(None, description="门店ID，可选；部分 action 会带入 params"),
    current_user: User = Depends(get_current_active_user),
):
    """
    私域运营 Agent 统一执行入口。

    - **原有 10 个 action**：get_dashboard、analyze_rfm、detect_signals、calculate_store_quadrant、trigger_journey、get_journeys、get_signals、segment_users、get_churn_risks、process_bad_review。
    - **用户增长 18 个 action**：user_portrait、funnel_optimize、ab_test_suggest、realtime_metrics、demand_forecast、anomaly_alert、personalized_recommend、social_content_draft、feedback_analysis、store_location_advice、inventory_plan、staff_schedule_advice、food_safety_alert、privacy_compliance_check、crisis_response_plan、product_idea、integration_advice、nl_query。
    - **nl_query** 必填 params.query；**personalized_recommend** 的 limit 为 1～50。
    - 可选在 params 中传 **context** 预填数据以丰富返回（见 packages/agents/private_domain/README.md）。
    """
    agent = _get_agent(store_id or "default")
    params = body.params or {}
    result = await agent.execute(body.action, params)
    if not result.success:
        raise HTTPException(status_code=400 if "不支持" in (result.error or "") else 500, detail=result.error)
    return {"success": True, "data": result.data, "execution_time": result.execution_time}


@router.get("/actions")
async def list_actions(current_user: User = Depends(get_current_active_user)):
    """列出私域运营 Agent 支持的所有 action（含原有能力与用户增长 18 项）。"""
    agent = _get_agent("default")
    return {"actions": agent.get_supported_actions(), "growth_actions": GROWTH_ACTIONS}


# ─────────────────────────── 原有 Endpoints ───────────────────────────


@router.get("/dashboard/{store_id}")
async def get_dashboard(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取私域运营看板"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_dashboard", {})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/rfm/{store_id}")
async def get_rfm_segments(
    store_id: str,
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_active_user),
):
    """获取RFM用户分层"""
    agent = _get_agent(store_id)
    result = await agent.execute("analyze_rfm", {"days": days})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"segments": result.data, "total": len(result.data)}


@router.get("/signals/{store_id}")
async def get_signals(
    store_id: str,
    signal_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
):
    """获取信号列表"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_signals", {"signal_type": signal_type, "limit": limit})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"signals": result.data, "total": len(result.data)}


@router.get("/churn-risks/{store_id}")
async def get_churn_risks(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取流失风险用户"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_churn_risks", {})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"users": result.data, "total": len(result.data)}


@router.get("/journeys/{store_id}")
async def get_journeys(
    store_id: str,
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
):
    """获取旅程列表"""
    agent = _get_agent(store_id)
    result = await agent.execute("get_journeys", {"status": status})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return {"journeys": result.data, "total": len(result.data)}


@router.post("/journeys/{store_id}/trigger")
async def trigger_journey(
    store_id: str,
    body: TriggerJourneyRequest,
    current_user: User = Depends(get_current_active_user),
):
    """触发用户旅程"""
    agent = _get_agent(store_id)
    result = await agent.execute(
        "trigger_journey",
        {
            "journey_type": body.journey_type,
            "customer_id": body.customer_id,
        },
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/quadrant/{store_id}")
async def calculate_quadrant(
    store_id: str,
    body: QuadrantRequest,
    current_user: User = Depends(get_current_active_user),
):
    """计算门店四象限"""
    agent = _get_agent(store_id)
    result = await agent.execute(
        "calculate_store_quadrant",
        {
            "competition_density": body.competition_density,
            "member_count": body.member_count,
            "estimated_population": body.estimated_population,
        },
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/reviews/{store_id}/process")
async def process_bad_review(
    store_id: str,
    body: ProcessReviewRequest,
    current_user: User = Depends(get_current_active_user),
):
    """处理差评，触发差评修复旅程"""
    agent = _get_agent(store_id)
    result = await agent.execute(
        "process_bad_review",
        {
            "review_id": body.review_id,
            "customer_id": body.customer_id,
            "rating": body.rating,
            "content": body.content,
        },
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/journeys/{store_id}/batch-trigger")
async def batch_trigger_journeys(
    store_id: str,
    body: BatchTriggerRequest,
    current_user: User = Depends(get_current_active_user),
):
    """批量触发旅程"""
    agent = _get_agent(store_id)
    results = []
    for cid in body.customer_ids:
        r = await agent.execute(
            "trigger_journey",
            {
                "journey_type": body.journey_type,
                "customer_id": cid,
            },
        )
        results.append({"customer_id": cid, "success": r.success, "journey": r.data})
    return {"triggered": len(results), "results": results}


@router.patch("/signals/{store_id}/{signal_id}/mark-handled")
async def mark_signal_handled(
    store_id: str,
    signal_id: str,
    body: MarkSignalRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """标记信号已处理"""
    import datetime

    from sqlalchemy import update as _update

    from ..models.private_domain import PrivateDomainSignal

    handled_at = datetime.datetime.utcnow()
    result = await db.execute(
        _update(PrivateDomainSignal)
        .where(
            PrivateDomainSignal.signal_id == signal_id,
            PrivateDomainSignal.store_id == store_id,
        )
        .values(action_taken=body.action, resolved_at=handled_at)
        .returning(PrivateDomainSignal.signal_id)
    )
    updated = result.fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail=f"信号 {signal_id} 不存在")
    await db.commit()
    return {"signal_id": signal_id, "action": body.action, "handled_at": handled_at.isoformat()}


@router.get("/lifecycle/{store_id}/{customer_id}", summary="检测会员生命周期状态")
async def get_lifecycle_state(
    store_id: str,
    customer_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """返回该会员当前生命周期状态（优先读已保存值，无则按 RFM 实时判断）。"""
    from ..services.lifecycle_state_machine import LifecycleStateMachine

    sm = LifecycleStateMachine()
    state = await sm.detect_state(customer_id, store_id, db)
    return {"customer_id": customer_id, "store_id": store_id, "state": state.value}


@router.post("/lifecycle/{store_id}/{customer_id}/trigger", summary="触发生命周期转移")
async def apply_lifecycle_trigger(
    store_id: str,
    customer_id: str,
    body: TriggerLifecycleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    对指定会员应用生命周期触发器。合法的 trigger 值：
    register / first_order / repeat_order / high_frequency_milestone /
    vip_upgrade / churn_warning / inactivity_long
    """
    from ..models.member_lifecycle import StateTransitionTrigger
    from ..services.lifecycle_state_machine import LifecycleStateMachine

    try:
        trigger = StateTransitionTrigger(body.trigger)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效 trigger: {body.trigger}，合法值: {[t.value for t in StateTransitionTrigger]}",
        )
    sm = LifecycleStateMachine()
    result = await sm.apply_trigger(
        customer_id,
        store_id,
        trigger,
        db,
        changed_by=body.changed_by,
        reason=body.reason,
    )
    return result


@router.get("/lifecycle/{store_id}/{customer_id}/history", summary="查看生命周期转移历史")
async def get_lifecycle_history(
    store_id: str,
    customer_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """返回会员状态转移历史（倒序，最近优先）。"""
    from ..services.lifecycle_state_machine import LifecycleStateMachine

    sm = LifecycleStateMachine()
    history = await sm.get_history(customer_id, store_id, db, limit=limit)
    return {"history": history, "total": len(history)}


@router.post("/journeys/{store_id}/trigger-v2", summary="触发多步骤旅程（新编排引擎）")
async def trigger_journey_v2(
    store_id: str,
    body: TriggerJourneyV2Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    使用新 JourneyOrchestrator 触发多步骤旅程，自动调度 Celery 延迟任务。
    journey_type: member_activation / first_order_conversion / dormant_wakeup
    """
    from ..services.journey_orchestrator import JourneyOrchestrator

    orch = JourneyOrchestrator()
    result = await orch.trigger(
        body.customer_id,
        store_id,
        body.journey_type,
        db,
        wechat_user_id=body.wechat_user_id,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/metrics/{store_id}", summary="私域三角 KPI 驾驶舱")
async def get_private_domain_metrics(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    私域增长三角 KPI：
      - **owned_audience**  — 自有流量（会员规模、活跃率、企微连接率）
      - **customer_value**  — 客户价值（复购率、LTV、AOV）
      - **journey_health**  — 旅程健康（完成率、风险信号数）
      - **lifecycle_funnel** — 生命周期漏斗分布（9段）
    """
    from ..services.private_domain_metrics import get_full_metrics

    return await get_full_metrics(store_id, db)


@router.get("/health/{store_id}", summary="私域健康分（5维度综合评分）")
async def get_health_score(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    私域健康综合评分（0-100）：

    | 维度       | 权重 | 说明                        |
    |------------|------|-----------------------------|
    | 会员质量   | 30分 | S4/S5 高价值会员占比        |
    | 留存控制   | 25分 | 低风险会员比例              |
    | 信号响应   | 20分 | 近30天信号已处理率          |
    | 旅程完成   | 15分 | 近30天旅程完成率            |
    | 增长势能   | 10分 | 近7天新客激活率             |

    等级：优秀(85+) / 良好(70-84) / 待改善(50-69) / 预警(<50)
    """
    from ..services.private_domain_health_service import calculate_health_score

    try:
        return await calculate_health_score(store_id, db)
    except Exception as exc:
        logger.error("private_domain.health_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/lifecycle/{store_id}/maslow-distribution", summary="马斯洛需求层级分布")
async def get_maslow_distribution(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    统计门店会员的马斯洛需求层级分布（L1-L5）。

    层级规则（与 journey_narrator.classify_maslow_level 完全一致）：
      L1: frequency = 0
      L2: frequency = 1
      L3: frequency 2-5
      L4: frequency ≥ 6 且 monetary < 50000 分（< ¥500）
      L5: frequency ≥ 6 且 monetary ≥ 50000 分（≥ ¥500）
    """
    sql = text("""
        SELECT
            COUNT(CASE WHEN frequency = 0 THEN 1 END)::int                          AS l1,
            COUNT(CASE WHEN frequency = 1 THEN 1 END)::int                          AS l2,
            COUNT(CASE WHEN frequency BETWEEN 2 AND 5 THEN 1 END)::int              AS l3,
            COUNT(CASE WHEN frequency >= 6 AND monetary < 50000 THEN 1 END)::int    AS l4,
            COUNT(CASE WHEN frequency >= 6 AND monetary >= 50000 THEN 1 END)::int   AS l5,
            COUNT(*)::int                                                            AS total
        FROM private_domain_members
        WHERE store_id = :store_id
    """)
    try:
        row = (await db.execute(sql, {"store_id": store_id})).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if row is None:
        return {"store_id": store_id, "total": 0, "distribution": []}

    total = row[5] or 1  # 避免除零
    distribution = [
        {"level": 1, "label": "初次接触（未消费）", "count": row[0], "pct": round(row[0] / total, 3)},
        {"level": 2, "label": "初步信任（消费1次）", "count": row[1], "pct": round(row[1] / total, 3)},
        {"level": 3, "label": "社交习惯（消费2-5次）", "count": row[2], "pct": round(row[2] / total, 3)},
        {"level": 4, "label": "高频忠实（≥6次<¥500）", "count": row[3], "pct": round(row[3] / total, 3)},
        {"level": 5, "label": "深度忠诚（≥6次≥¥500）", "count": row[4], "pct": round(row[4] / total, 3)},
    ]
    return {"store_id": store_id, "total": row[5], "distribution": distribution}


@router.get("/dynamic-pricing/{store_id}", summary="Agent-14 会员个性化定价策略")
async def get_dynamic_pricing(
    store_id: str,
    customer_id: str = Query(..., description="会员 ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    基于会员马斯洛层级 + 当前时段，返回个性化定价策略推荐。

    - L1: 品质故事，无折扣
    - L2: 88折回头客券
    - L3: 78折聚餐套餐
    - L4: 专属礼遇，无折扣
    - L5: 主厨体验，无折扣
    - 平峰（非 11-13h / 17-20h）L2/L3 额外让利 1 折
    """
    from dataclasses import asdict

    from ..services.dynamic_pricing_service import DynamicPricingService

    svc = DynamicPricingService()
    offer = await svc.recommend(store_id, customer_id, db)
    return asdict(offer)


@router.get("/stats/trend/{store_id}")
async def get_trend_stats(
    store_id: str,
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取趋势统计（会员增长、复购率、旅程完成率）"""
    import datetime

    today = datetime.date.today()
    since = today - datetime.timedelta(days=days)

    # 按日汇总营收和订单
    orders_sql = text("""
        SELECT DATE(created_at) AS day,
               COALESCE(SUM(total_amount), 0)::bigint AS revenue
        FROM orders
        WHERE store_id = :store_id AND created_at::date >= :since
        GROUP BY DATE(created_at)
    """)
    # 新会员数（按加入日期）
    members_sql = text("""
        SELECT DATE(created_at) AS day, COUNT(*)::int AS new_members
        FROM private_domain_members
        WHERE store_id = :store_id AND created_at::date >= :since
        GROUP BY DATE(created_at)
    """)
    # 旅程完成率（已完成/总启动，按 started_at 日期）
    journey_sql = text("""
        SELECT DATE(started_at) AS day,
               COUNT(CASE WHEN status = 'completed' THEN 1 END)::float
                 / NULLIF(COUNT(*), 0) AS completion_rate
        FROM private_domain_journeys
        WHERE store_id = :store_id AND started_at::date >= :since
        GROUP BY DATE(started_at)
    """)
    # 复购率（当日下单客户中历史频次>1的比例）
    repurchase_sql = text("""
        SELECT o.created_at::date AS day,
               COUNT(DISTINCT CASE WHEN m.frequency > 1 THEN o.customer_id END)::float
                 / NULLIF(COUNT(DISTINCT o.customer_id), 0) AS repurchase_rate
        FROM orders o
        LEFT JOIN private_domain_members m
          ON m.customer_id = o.customer_id AND m.store_id = o.store_id
        WHERE o.store_id = :store_id AND o.created_at::date >= :since
          AND o.customer_id IS NOT NULL
        GROUP BY o.created_at::date
    """)

    params = {"store_id": store_id, "since": since.isoformat()}
    try:
        revenue_by_day = {str(r[0]): int(r[1]) for r in (await db.execute(orders_sql, params)).fetchall()}
        members_by_day = {str(r[0]): int(r[1]) for r in (await db.execute(members_sql, params)).fetchall()}
        journey_by_day = {
            str(r[0]): round(float(r[1]), 3) if r[1] is not None else 0.0
            for r in (await db.execute(journey_sql, params)).fetchall()
        }
        repurchase_by_day = {
            str(r[0]): round(float(r[1]), 3) if r[1] is not None else 0.0
            for r in (await db.execute(repurchase_sql, params)).fetchall()
        }
    except Exception:
        revenue_by_day = {}
        members_by_day = {}
        journey_by_day = {}
        repurchase_by_day = {}

    trend = []
    for i in range(days, 0, -1):
        d = today - datetime.timedelta(days=i)
        d_str = d.isoformat()
        trend.append(
            {
                "date": d_str,
                "new_members": members_by_day.get(d_str, 0),
                "repurchase_rate": repurchase_by_day.get(d_str, 0.0),
                "journey_completion": journey_by_day.get(d_str, 0.0),
                "revenue": revenue_by_day.get(d_str, 0),
            }
        )
    return {"trend": trend, "days": days}


# ── 会员档案管理 ────────────────────────────────────────────────────────────────


class MemberProfilePatch(BaseModel):
    birth_date: Optional[date] = None
    wechat_openid: Optional[str] = None
    channel_source: Optional[str] = None


@router.get("/members/{store_id}/list", summary="会员档案列表（分页+搜索）")
async def list_members(
    store_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="customer_id 模糊搜索"),
    lifecycle_state: Optional[str] = Query(None, description="生命周期状态过滤"),
    rfm_level: Optional[str] = Query(None, description="RFM等级过滤"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回门店私域会员档案列表，支持按 customer_id 搜索、生命周期状态和 RFM 等级过滤。
    """
    conditions = ["m.store_id = :store_id"]
    params: Dict = {"store_id": store_id}

    if search:
        conditions.append("m.customer_id ILIKE :search")
        params["search"] = f"%{search}%"
    if lifecycle_state:
        conditions.append("m.lifecycle_state = :lifecycle_state")
        params["lifecycle_state"] = lifecycle_state
    if rfm_level:
        conditions.append("m.rfm_level = :rfm_level")
        params["rfm_level"] = rfm_level

    where = " AND ".join(conditions)

    count_sql = text(f"SELECT COUNT(*) FROM private_domain_members m WHERE {where}")
    list_sql = text(f"""
        SELECT
            m.customer_id,
            m.rfm_level,
            m.lifecycle_state,
            m.birth_date,
            m.wechat_openid,
            m.channel_source,
            m.recency_days,
            m.frequency,
            m.monetary,
            m.last_visit,
            m.is_active,
            m.created_at
        FROM private_domain_members m
        WHERE {where}
        ORDER BY m.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    try:
        total = (await db.execute(count_sql, params)).scalar() or 0
        rows = (await db.execute(list_sql, params)).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    members = [
        {
            "customer_id": row[0],
            "rfm_level": row[1],
            "lifecycle_state": row[2],
            "birth_date": str(row[3]) if row[3] else None,
            "wechat_openid": row[4],
            "channel_source": row[5],
            "recency_days": row[6],
            "frequency": row[7],
            "monetary": row[8],
            "monetary_yuan": round(row[8] / 100, 2) if row[8] else 0.0,
            "last_visit": str(row[9]) if row[9] else None,
            "is_active": row[10],
            "joined_at": str(row[11]) if row[11] else None,
        }
        for row in rows
    ]
    return {
        "store_id": store_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "members": members,
    }


@router.patch("/members/{store_id}/{customer_id}", summary="更新会员档案（生日/企微/渠道）")
async def patch_member_profile(
    store_id: str,
    customer_id: str,
    body: MemberProfilePatch,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新会员档案字段（仅允许修改 birth_date / wechat_openid / channel_source）。
    只更新请求体中非 None 的字段，其余字段保持不变。
    """
    updates: Dict[str, Any] = {}
    if body.birth_date is not None:
        updates["birth_date"] = body.birth_date
    if body.wechat_openid is not None:
        updates["wechat_openid"] = body.wechat_openid
    if body.channel_source is not None:
        updates["channel_source"] = body.channel_source

    if not updates:
        raise HTTPException(status_code=422, detail="没有可更新的字段")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    sql = text(f"""
        UPDATE private_domain_members
        SET {set_clause}
        WHERE store_id = :store_id AND customer_id = :customer_id
        RETURNING customer_id
    """)
    params = {**updates, "store_id": store_id, "customer_id": customer_id}

    try:
        result = (await db.execute(sql, params)).fetchone()
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="会员不存在")

    return {"updated": True, "customer_id": customer_id, "fields": list(updates.keys())}


# ── 客户360画像（私域视角） ──────────────────────────────────────────────────────


@router.get("/customer360/{store_id}/{customer_id}", summary="客户360画像（私域视角）")
async def get_customer360(
    store_id: str,
    customer_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    聚合单个会员的私域视角360画像：
      - 会员基础档案（RFM等级、生命周期、消费摘要、马斯洛层级）
      - 近期旅程历史（最近10条，含状态+完成时间）
      - 近期订单记录（最近5笔，含¥金额）
      - 个性化定价策略推荐（DynamicPricingService）

    会员不存在返回 404；订单/旅程查询失败静默降级为空列表。
    """
    # 1. 会员档案
    member_sql = text("""
        SELECT
            customer_id, rfm_level, lifecycle_state, birth_date,
            wechat_openid, channel_source, recency_days, frequency,
            monetary, last_visit, is_active, created_at
        FROM private_domain_members
        WHERE store_id = :store_id AND customer_id = :customer_id
        LIMIT 1
    """)
    try:
        member_row = (await db.execute(member_sql, {"store_id": store_id, "customer_id": customer_id})).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if member_row is None:
        raise HTTPException(status_code=404, detail="会员不存在")

    member = {
        "customer_id": member_row[0],
        "rfm_level": member_row[1],
        "lifecycle_state": member_row[2],
        "birth_date": str(member_row[3]) if member_row[3] else None,
        "wechat_openid": member_row[4],
        "channel_source": member_row[5],
        "recency_days": member_row[6],
        "frequency": member_row[7],
        "monetary": member_row[8],
        "monetary_yuan": round(member_row[8] / 100, 2) if member_row[8] else 0.0,
        "last_visit": str(member_row[9]) if member_row[9] else None,
        "is_active": member_row[10],
        "joined_at": str(member_row[11]) if member_row[11] else None,
    }

    # 2. 旅程历史（最近10条）
    journeys_sql = text("""
        SELECT journey_type, status, started_at, completed_at
        FROM private_domain_journeys
        WHERE store_id = :store_id AND customer_id = :customer_id
        ORDER BY started_at DESC
        LIMIT 10
    """)
    try:
        journey_rows = (await db.execute(journeys_sql, {"store_id": store_id, "customer_id": customer_id})).fetchall()
    except Exception:
        journey_rows = []

    recent_journeys = [
        {
            "journey_type": r[0],
            "status": r[1],
            "started_at": str(r[2]) if r[2] else None,
            "completed_at": str(r[3]) if r[3] else None,
        }
        for r in journey_rows
    ]

    # 3. 近期订单（最近5笔）
    orders_sql = text("""
        SELECT order_id, total_amount, created_at, status
        FROM orders
        WHERE store_id = :store_id AND customer_id = :customer_id
        ORDER BY created_at DESC
        LIMIT 5
    """)
    try:
        order_rows = (await db.execute(orders_sql, {"store_id": store_id, "customer_id": customer_id})).fetchall()
    except Exception:
        order_rows = []

    recent_orders = [
        {
            "order_id": str(r[0]),
            "total_amount": int(r[1]) if r[1] is not None else 0,
            "total_amount_yuan": round(int(r[1]) / 100, 2) if r[1] is not None else 0.0,
            "created_at": str(r[2]) if r[2] else None,
            "status": r[3],
        }
        for r in order_rows
    ]

    # 4. 个性化定价策略（DynamicPricingService，失败时静默返回 None）
    from dataclasses import asdict as _asdict

    from ..services.dynamic_pricing_service import DynamicPricingService

    pricing_offer = None
    try:
        pricing_offer = _asdict(await DynamicPricingService().recommend(store_id, customer_id, db))
    except Exception as exc:
        logger.warning("private_domain.dynamic_pricing_failed", store_id=store_id, customer_id=customer_id, error=str(exc))

    return {
        "store_id": store_id,
        "customer_id": customer_id,
        "member": member,
        "recent_journeys": recent_journeys,
        "recent_orders": recent_orders,
        "pricing_offer": pricing_offer,
    }
