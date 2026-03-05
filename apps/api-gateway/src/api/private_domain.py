"""
私域运营 API
Private Domain Operations API

原有能力：看板、RFM、信号、四象限、旅程、差评处理等。
扩展能力（用户增长）：user_portrait、funnel_optimize、realtime_metrics、personalized_recommend 等 18 个 action，
见 POST /execute 与 GET /actions。
"""
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core.dependencies import get_current_active_user
from ..core.database import get_db
from ..models.user import User

import sys
from pathlib import Path
# packages/ 目录位于仓库根（相对于此文件向上 5 级）
_repo_root = Path(__file__).resolve().parents[4]
agent_path = _repo_root / "packages" / "agents" / "private_domain" / "src"
_core_path = Path(__file__).resolve().parents[1] / "core"  # src/core（base_agent 所在目录）
for _p in (agent_path, _core_path):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from agent import PrivateDomainAgent
from growth_handlers import GROWTH_ACTIONS

router = APIRouter(prefix="/api/v1/private-domain", tags=["private_domain"])


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
    result = await agent.execute("trigger_journey", {
        "journey_type": body.journey_type,
        "customer_id": body.customer_id,
    })
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
    result = await agent.execute("calculate_store_quadrant", {
        "competition_density": body.competition_density,
        "member_count": body.member_count,
        "estimated_population": body.estimated_population,
    })
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
    result = await agent.execute("process_bad_review", {
        "review_id": body.review_id,
        "customer_id": body.customer_id,
        "rating": body.rating,
        "content": body.content,
    })
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
        r = await agent.execute("trigger_journey", {
            "journey_type": body.journey_type,
            "customer_id": cid,
        })
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
        revenue_by_day = {
            str(r[0]): int(r[1])
            for r in (await db.execute(orders_sql, params)).fetchall()
        }
        members_by_day = {
            str(r[0]): int(r[1])
            for r in (await db.execute(members_sql, params)).fetchall()
        }
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
        trend.append({
            "date": d_str,
            "new_members": members_by_day.get(d_str, 0),
            "repurchase_rate": repurchase_by_day.get(d_str, 0.0),
            "journey_completion": journey_by_day.get(d_str, 0.0),
            "revenue": revenue_by_day.get(d_str, 0),
        })
    return {"trend": trend, "days": days}
