"""
决策中枢 API（Decision Hub）

提供：
  GET  /api/v1/decisions/top3          — 查询门店当前 Top3 决策
  POST /api/v1/decisions/trigger-push  — 手动触发决策推送（任意时间点）
  GET  /api/v1/decisions/pending       — 待审批决策列表
  GET  /api/v1/decisions/scenario      — 当前场景识别 + 相似历史案例

对接现有 Agent 建议系统：
  DecisionPriorityEngine 已从 inventory / food_cost / reasoning 三源聚合，
  本文件仅对外暴露 HTTP 接口，供前端展示和手动触发使用。

Rule 7 合规：所有决策输出均含 expected_saving_yuan + confidence_pct + action
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User
from src.services.decision_priority_engine import DecisionPriorityEngine
from src.services.decision_push_service import DecisionPushService
from src.services.scenario_matcher import ScenarioMatcher
from src.services.behavior_score_engine import BehaviorScoreEngine

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/decisions", tags=["decision_hub"])


# ── 响应模型 ──────────────────────────────────────────────────────────────────

class DecisionItem(BaseModel):
    rank:                  int
    title:                 str
    action:                str
    source:                str
    expected_saving_yuan:  float
    expected_cost_yuan:    float
    net_benefit_yuan:      float
    confidence_pct:        float
    urgency_hours:         float
    execution_difficulty:  str
    decision_window_label: str
    priority_score:        float


class Top3Response(BaseModel):
    store_id:       str
    decisions:      List[DecisionItem]
    count:          int
    generated_at:   str


class TriggerPushRequest(BaseModel):
    store_id:            str
    push_type:           str = "morning"   # morning | noon | prebattle | evening
    recipient_user_id:   Optional[str] = None
    monthly_revenue_yuan: float = 0.0


class FlowWindowState(BaseModel):
    window:      str
    slug:        str
    state:       Optional[Dict[str, Any]] = None   # DecisionFlowState.summary() or null


class FlowHistoryResponse(BaseModel):
    store_id:     str
    date:         str
    windows:      List[FlowWindowState]
    pushed_count: int   # 今日实际成功推送次数


class ScenarioResponse(BaseModel):
    store_id:       str
    scenario_type:  str
    scenario_label: str
    metrics:        Dict[str, Any]
    similar_cases:  List[Dict[str, Any]]
    as_of:          str


# ── GET /api/v1/decisions/top3 ────────────────────────────────────────────────

@router.get("/top3", response_model=Top3Response)
async def get_top3_decisions(
    store_id:             str,
    monthly_revenue_yuan: float = Query(default=0.0, description="月营收（元），用于财务影响评分"),
    current_user: User    = Depends(get_current_active_user),
    db: AsyncSession      = Depends(get_db),
):
    """
    查询门店当前 Top3 决策（含 ¥ 预期收益 + 置信度）。

    对接来源：
      - inventory Agent：库存告警 → 补货决策
      - food_cost Agent：成本率偏差 → 压缩成本决策
      - reasoning Agent：综合诊断 → 运营优化决策

    每日4次自动推送（celery_tasks.py），本端点供前端按需查询。
    """
    from datetime import datetime

    try:
        engine    = DecisionPriorityEngine(store_id=store_id)
        decisions = await engine.get_top3(db=db, monthly_revenue_yuan=monthly_revenue_yuan)

        logger.info("top3_decisions_queried", store_id=store_id, count=len(decisions))
        return {
            "store_id":     store_id,
            "decisions":    decisions,
            "count":        len(decisions),
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("top3_decisions_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"决策引擎查询失败: {exc}")


# ── POST /api/v1/decisions/trigger-push ──────────────────────────────────────

@router.post("/trigger-push")
async def trigger_decision_push(
    req: TriggerPushRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession   = Depends(get_db),
):
    """
    手动触发决策推送（无需等待定时任务）。

    push_type:
      - morning    → 晨推 Top3 决策卡片（08:00 自动）
      - noon       → 午推异常告警（12:00 自动，有异常才发）
      - prebattle  → 战前推备战检查（17:30 自动）
      - evening    → 晚推回顾+待审批（20:30 自动）
    """
    import os

    push_type = req.push_type.lower()
    recipient = req.recipient_user_id or os.getenv(
        f"WECHAT_RECIPIENT_{req.store_id.upper()}", f"store_{req.store_id}"
    )

    push_map = {
        "morning":   DecisionPushService.push_morning_decisions,
        "noon":      DecisionPushService.push_noon_anomaly,
        "prebattle": DecisionPushService.push_prebattle_decisions,
        "evening":   DecisionPushService.push_evening_recap,
    }

    if push_type not in push_map:
        raise HTTPException(status_code=400, detail=f"无效的 push_type: {push_type}，可选: {list(push_map)}")

    try:
        result = await push_map[push_type](
            store_id=req.store_id,
            brand_id="",
            recipient_user_id=recipient,
            db=db,
            monthly_revenue_yuan=req.monthly_revenue_yuan,
        )
        logger.info("manual_push_triggered", store_id=req.store_id, push_type=push_type)
        return {"success": True, "push_type": push_type, **result}
    except Exception as exc:
        logger.error("manual_push_failed", store_id=req.store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"推送失败: {exc}")


# ── GET /api/v1/decisions/flow-history ───────────────────────────────────────

_PUSH_WINDOWS = [
    ("08:00晨推", "morning"),
    ("12:00午推", "noon"),
    ("17:30战前", "prebattle"),
    ("20:30晚推", "evening"),
]


@router.get("/flow-history", response_model=FlowHistoryResponse)
async def get_flow_history(
    store_id:    str,
    target_date: Optional[date] = Query(None, alias="date", description="查询日期 YYYY-MM-DD，默认今天"),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询指定门店某日四个时间点的推送流程状态。

    每次推送成功后 DecisionFlowState 会写入 Redis（24h TTL），
    本端点将四个窗口的状态聚合返回，供运营人员核查「今天推了什么」。

    state 字段为 null 表示该时间点尚未推送或 Redis 中已过期。
    """
    from src.services.decision_flow_state import DecisionFlowState

    query_date = target_date or date.today()
    windows: List[FlowWindowState] = []

    for window_name, slug in _PUSH_WINDOWS:
        state = await DecisionFlowState.load_from_redis(
            store_id=store_id,
            push_window=window_name,
            target_date=query_date,
        )
        windows.append(FlowWindowState(
            window=window_name,
            slug=slug,
            state=state.summary() if state else None,
        ))

    pushed_count = sum(
        1 for w in windows
        if w.state and w.state.get("push_sent")
    )

    logger.info(
        "flow_history_queried",
        store_id=store_id,
        date=query_date.isoformat(),
        pushed_count=pushed_count,
    )
    return FlowHistoryResponse(
        store_id=store_id,
        date=query_date.isoformat(),
        windows=windows,
        pushed_count=pushed_count,
    )


# ── GET /api/v1/decisions/pending ────────────────────────────────────────────

@router.get("/pending")
async def list_pending_decisions(
    store_id:      Optional[str] = None,
    limit:         int           = Query(default=20, le=100),
    current_user:  User          = Depends(get_current_active_user),
    db: AsyncSession             = Depends(get_db),
):
    """
    获取待审批决策列表（给前端审批页面使用）。
    """
    from sqlalchemy import select
    from src.models.decision_log import DecisionLog, DecisionStatus

    stmt = (
        select(DecisionLog)
        .where(DecisionLog.decision_status == DecisionStatus.PENDING)
        .order_by(DecisionLog.created_at.desc())
        .limit(limit)
    )
    if store_id:
        stmt = stmt.where(DecisionLog.store_id == store_id)

    result  = await db.execute(stmt)
    records = result.scalars().all()

    items = []
    for r in records:
        suggestion = r.ai_suggestion or {}
        items.append({
            "id":                    r.id,
            "store_id":              r.store_id,
            "decision_type":         r.decision_type,
            "action":                suggestion.get("action", ""),
            "expected_saving_yuan":  suggestion.get("expected_saving_yuan", 0.0),
            "confidence_pct":        round(float(r.ai_confidence or 0) * 100, 1),
            "created_at":            r.created_at.isoformat() if r.created_at else None,
        })

    return {"total": len(items), "items": items}


# ── GET /api/v1/decisions/scenario ───────────────────────────────────────────

@router.get("/scenario", response_model=ScenarioResponse)
async def get_store_scenario(
    store_id:      str,
    as_of:         Optional[date] = None,
    current_user:  User           = Depends(get_current_active_user),
    db: AsyncSession              = Depends(get_db),
):
    """
    识别门店当前经营场景，并返回最相似的历史案例（含执行结果）。

    场景类型：成本超标期 / 损耗高发期 / 节假日高峰期 /
              营收下行期 / 周末经营期 / 新品上市期 / 工作日正常期
    """
    try:
        scenario_info = await ScenarioMatcher.identify_current_scenario(
            store_id=store_id, db=db, as_of=as_of
        )
        similar_cases = await ScenarioMatcher.find_similar_cases(
            store_id=store_id,
            scenario_type=scenario_info["scenario_type"],
            cost_rate_pct=scenario_info["metrics"]["cost_rate_pct"],
            revenue_fen=int(scenario_info["metrics"]["revenue_yuan"] * 100),
            db=db,
        )
        return {
            **scenario_info,
            "similar_cases": similar_cases,
        }
    except Exception as exc:
        logger.error("scenario_query_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"场景识别失败: {exc}")


# ── GET /api/v1/decisions/behavior-report ────────────────────────────────────

@router.get("/behavior-report")
async def get_behavior_report(
    store_id:   str,
    start_date: Optional[date] = None,
    end_date:   Optional[date] = None,
    current_user: User         = Depends(get_current_active_user),
    db: AsyncSession           = Depends(get_db),
):
    """
    门店 AI 建议采纳率报告（BehaviorScoreEngine）。

    指标：
      - AI建议发出数 / 采纳数 / 采纳率%
      - 已采纳建议中：有效果反馈数 / 执行准确率%
      - 累计节省¥（系统价值证明，不归因到个人）

    默认区间：最近30天。
    """
    if start_date is None:
        start_date = date.today() - timedelta(days=30)
    if end_date is None:
        end_date = date.today()

    try:
        report = await BehaviorScoreEngine.get_store_report(
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            db=db,
        )
        return report
    except Exception as exc:
        logger.error("behavior_report_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"采纳率报告查询失败: {exc}")


# ── P3-1 A/B 测试：推送时间点效果分析 ─────────────────────────────────────────

@router.get("/stores/{store_id}/push-ab-test", summary="决策推送时间点 A/B 测试分析")
async def get_push_ab_test(
    store_id:      str,
    start_date:    Optional[date] = None,
    end_date:      Optional[date] = None,
    lookback_days: int            = Query(30, ge=7, le=180, description="回望天数"),
    current_user:  User           = Depends(get_current_active_user),
    db: AsyncSession              = Depends(get_db),
):
    """
    分析门店 4 个决策推送时间点（晨推/午推/战前/晚推）的采纳效果。

    通过 Wilson Score 置信区间评估哪个时间点推送效果最优，
    并给出推荐的最优推送时间点。

    Response:
      - variants: 每个时间点的采纳率、响应时长、统计置信度
      - winner_id / winner_label: 当前最优时间点
      - recommendation: 文字建议
    """
    from src.services.decision_ab_test_service import DecisionPushABTestService
    try:
        return await DecisionPushABTestService.analyze(
            session=db,
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            lookback_days=lookback_days,
        )
    except Exception as exc:
        logger.error("push_ab_test_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"A/B 测试分析失败: {exc}")


@router.get("/push-ab-test/multi-store", summary="多门店推送时间点横向对比")
async def get_push_ab_test_multi_store(
    store_ids:     str            = Query(..., description="逗号分隔的门店 ID 列表"),
    lookback_days: int            = Query(30, ge=7, le=180, description="回望天数"),
    current_user:  User           = Depends(get_current_active_user),
    db: AsyncSession              = Depends(get_db),
):
    """
    多门店横向对比各推送时间点效果，找出全局最优推送时间点。
    """
    from src.services.decision_ab_test_service import DecisionPushABTestService
    ids = [s.strip() for s in store_ids.split(",") if s.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="store_ids 不能为空")
    if len(ids) > 20:
        raise HTTPException(status_code=400, detail="一次最多对比 20 个门店")
    try:
        return await DecisionPushABTestService.compare_stores(
            session=db,
            store_ids=ids,
            lookback_days=lookback_days,
        )
    except Exception as exc:
        logger.error("push_ab_test_multi_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"多店 A/B 对比失败: {exc}")
