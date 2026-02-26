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

from ..core.dependencies import get_current_active_user
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
):
    """标记信号已处理"""
    # 实际应更新DB；此处返回确认
    return {"signal_id": signal_id, "action": body.action, "handled_at": __import__("datetime").datetime.utcnow().isoformat()}


@router.get("/stats/trend/{store_id}")
async def get_trend_stats(
    store_id: str,
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_active_user),
):
    """获取趋势统计（会员增长、复购率、旅程完成率）"""
    import random, datetime
    random.seed(store_id)
    today = datetime.date.today()
    trend = []
    for i in range(days, 0, -1):
        d = today - datetime.timedelta(days=i)
        trend.append({
            "date": d.isoformat(),
            "new_members": random.randint(2, 15),
            "repurchase_rate": round(random.uniform(0.25, 0.55), 3),
            "journey_completion": round(random.uniform(0.6, 0.9), 3),
            "revenue": random.randint(3000, 12000),
        })
    return {"trend": trend, "days": days}
