"""
L5 行动层 REST API

端点：
  POST /api/v1/l5/stores/{store_id}/execute             — 从指定推理报告触发行动
  POST /api/v1/l5/stores/{store_id}/dispatch-pending    — 派发门店所有未处理 P1/P2
  GET  /api/v1/l5/stores/{store_id}/action-plans        — 门店行动计划列表
  GET  /api/v1/l5/action-plans/{plan_id}                — 行动计划详情
  PATCH /api/v1/l5/action-plans/{plan_id}/outcome       — 记录行动结果（反馈闭环）
  GET  /api/v1/l5/reports/platform-stats                — 全平台派发统计
  POST /api/v1/l5/scan/dispatch                         — 触发 Celery 全平台批量派发

设计：
  - execute 支持按 report_id 或 (store_id + dimension) 查找最新报告
  - outcome 写入 kpi_delta 实现 L4→L5→L4 改善效果量化
  - platform-stats 用于大屏展示「行动处理率」「P1 平均解决时长」
"""

from __future__ import annotations

import uuid as _uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.action_plan import ActionPlan
from src.models.reasoning import ReasoningReport
from src.models.user import User
from src.services.action_dispatch_service import ActionDispatchService

router = APIRouter(prefix="/api/v1/l5", tags=["l5_action"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class ExecuteIn(BaseModel):
    report_id: Optional[str] = Field(
        None,
        description="指定推理报告 ID（优先）；为空时取门店该维度最新 P1/P2 报告",
    )
    dimension: Optional[str] = Field(
        None,
        description="维度（report_id 为空时使用）",
    )


class DispatchPendingIn(BaseModel):
    days_back: int = Field(1, ge=1, le=7, description="回溯天数（默认 1 = 近两天）")


class OutcomeIn(BaseModel):
    outcome: str = Field(
        ...,
        description="结果: resolved / escalated / expired / no_effect / cancelled",
    )
    resolved_by: str = Field(..., description="操作人（员工 ID 或姓名）")
    outcome_note: Optional[str] = Field(None, description="补充说明")
    kpi_delta: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "KPI 改善量，格式: "
            "{waste_rate: {before: 0.15, after: 0.11, delta: -0.04}}"
        ),
    )
    followup_report_id: Optional[str] = Field(
        None, description="行动后跟进诊断报告 ID"
    )


class BatchDispatchIn(BaseModel):
    store_ids: Optional[List[str]] = Field(None, description="指定门店（None=全平台）")
    days_back: int = Field(1, ge=1, le=7)


# ── 从推理报告触发行动 ────────────────────────────────────────────────────────

@router.post(
    "/stores/{store_id}/execute",
    summary="从推理报告触发 L5 行动派发",
    status_code=status.HTTP_200_OK,
)
async def execute_from_report(
    store_id: str,
    body:     ExecuteIn,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    针对指定推理报告（或门店最新 P1/P2 报告）立即派发行动：

    - P1 → WeChat P1 + URGENT 任务 + 审批申请（waste/cost 维度）
    - P2 → WeChat P2 + HIGH 任务
    - P3 → WeChat 通知（轻量）
    - OK → 跳过，返回 dispatch_status=skipped

    若行动计划已存在（幂等），直接返回已有记录。
    """
    report = await _resolve_report(store_id, body.report_id, body.dimension, db)

    svc  = ActionDispatchService(db)
    plan = await svc.dispatch_from_report(report)
    await db.commit()
    return _plan_to_dict(plan)


# ── 门店批量派发未处理 P1/P2 ─────────────────────────────────────────────────

@router.post(
    "/stores/{store_id}/dispatch-pending",
    summary="派发门店所有未处理 P1/P2 推理报告",
    status_code=status.HTTP_200_OK,
)
async def dispatch_store_pending(
    store_id: str,
    body:     DispatchPendingIn = DispatchPendingIn(),
    db:       AsyncSession      = Depends(get_db),
    _:        User              = Depends(get_current_user),
):
    """扫描并派发门店近 N 天内所有尚未生成行动计划的 P1/P2 报告。"""
    svc   = ActionDispatchService(db)
    stats = await svc.dispatch_pending_alerts(
        store_id=store_id, days_back=body.days_back
    )
    await db.commit()
    return {"store_id": store_id, **stats}


# ── 行动计划列表 ──────────────────────────────────────────────────────────────

@router.get(
    "/stores/{store_id}/action-plans",
    summary="门店行动计划历史列表",
    response_model=List[dict],
)
async def list_store_action_plans(
    store_id:  str,
    days:      int          = Query(30, ge=1, le=365),
    severity:  Optional[str] = Query(None, pattern="^(P1|P2|P3)$"),
    outcome:   Optional[str] = Query(None),
    limit:     int          = Query(50, ge=1, le=200),
    db:        AsyncSession = Depends(get_db),
    _:         User         = Depends(get_current_user),
):
    """查询门店行动计划历史，支持严重程度和结果过滤。"""
    svc   = ActionDispatchService(db)
    plans = await svc.list_plans(
        store_id=store_id, days=days, severity=severity, outcome=outcome, limit=limit
    )
    return [_plan_to_dict(p) for p in plans]


# ── 行动计划详情 ──────────────────────────────────────────────────────────────

@router.get(
    "/action-plans/{plan_id}",
    summary="行动计划详情",
)
async def get_action_plan(
    plan_id: str,
    db:      AsyncSession = Depends(get_db),
    _:       User         = Depends(get_current_user),
):
    """获取单条行动计划完整详情（含 WeChat action_id、task_id、kpi_delta）。"""
    try:
        pid = _uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="plan_id 格式错误",
        )

    stmt = select(ActionPlan).where(ActionPlan.id == pid)
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行动计划不存在")
    return _plan_to_dict(plan, full=True)


# ── 记录行动结果（反馈闭环） ──────────────────────────────────────────────────

@router.patch(
    "/action-plans/{plan_id}/outcome",
    summary="记录行动结果（L4→L5→L4 反馈闭环）",
)
async def record_outcome(
    plan_id: str,
    body:    OutcomeIn,
    db:      AsyncSession = Depends(get_db),
    _:       User         = Depends(get_current_user),
):
    """
    记录行动执行结果，完成 Human-in-the-Loop 闭环并量化改善效果。

    `kpi_delta` 示例::

        {"waste_rate": {"before": 0.15, "after": 0.11, "delta": -0.04}}

    结果将作为训练信号回馈给 L4 置信度校准模型。
    """
    valid_outcomes = {"resolved", "escalated", "expired", "no_effect", "cancelled"}
    if body.outcome not in valid_outcomes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"无效结果值，可选: {valid_outcomes}",
        )
    try:
        pid = _uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="plan_id 格式错误",
        )

    followup_id = None
    if body.followup_report_id:
        try:
            followup_id = _uuid.UUID(body.followup_report_id)
        except ValueError:
            pass

    svc  = ActionDispatchService(db)
    plan = await svc.record_outcome(
        plan_id=pid,
        outcome=body.outcome,
        resolved_by=body.resolved_by,
        outcome_note=body.outcome_note or "",
        kpi_delta=body.kpi_delta,
        followup_report_id=followup_id,
    )
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行动计划不存在")

    await db.commit()
    return {
        "plan_id":     plan_id,
        "outcome":     plan.outcome,
        "resolved_by": plan.resolved_by,
        "resolved_at": plan.resolved_at.isoformat() if plan.resolved_at else None,
        "kpi_delta":   plan.kpi_delta,
    }


# ── 全平台派发统计 ────────────────────────────────────────────────────────────

@router.get(
    "/reports/platform-stats",
    summary="全平台行动派发统计（大屏）",
)
async def get_platform_stats(
    days: int          = Query(7, ge=1, le=30),
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(get_current_user),
):
    """
    返回全平台近 N 天行动派发统计：

    - dispatch_dist: {dispatched, partial, failed, skipped} 计数
    - outcome_dist:  {resolved, escalated, expired, no_effect, pending} 计数
    - severity_dist: {P1, P2, P3} 计数
    - resolution_rate: 已解决 / 总计（%）
    """
    svc   = ActionDispatchService(db)
    stats = await svc.get_platform_stats(days=days)

    total    = stats.get("total_plans", 0)
    resolved = stats.get("outcome_dist", {}).get("resolved", 0)
    stats["resolution_rate"] = round(resolved / total * 100, 1) if total else 0.0
    return stats


# ── 触发 Celery 批量派发 ──────────────────────────────────────────────────────

@router.post(
    "/scan/dispatch",
    summary="触发 Celery 全平台批量行动派发",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_batch_dispatch(
    body: BatchDispatchIn = BatchDispatchIn(),
    _:    User            = Depends(get_current_user),
):
    """
    触发 Celery `nightly_action_dispatch` 任务（全平台 P1/P2 行动批量派发）。

    适用场景：
    - 手动补跑（夜间任务失败后）
    - 指定门店子集重新派发
    - 应急告警时段强制刷新
    """
    try:
        from src.core.celery_tasks import nightly_action_dispatch
        task = nightly_action_dispatch.delay(
            store_ids=body.store_ids,
            days_back=body.days_back,
        )
        return {
            "status":    "accepted",
            "task_id":   task.id,
            "store_ids": body.store_ids,
            "days_back": body.days_back,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Celery 任务提交失败: {str(e)}",
        )


# ── 内部工具函数 ──────────────────────────────────────────────────────────────

async def _resolve_report(
    store_id:   str,
    report_id:  Optional[str],
    dimension:  Optional[str],
    db:         AsyncSession,
) -> ReasoningReport:
    """解析目标推理报告（按 ID 或维度最新）"""
    if report_id:
        try:
            rid = _uuid.UUID(report_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="report_id 格式错误",
            )
        stmt   = select(ReasoningReport).where(
            and_(
                ReasoningReport.id       == rid,
                ReasoningReport.store_id == store_id,
            )
        )
        report = (await db.execute(stmt)).scalar_one_or_none()
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="推理报告不存在",
            )
        return report

    if dimension:
        stmt = (
            select(ReasoningReport)
            .where(
                and_(
                    ReasoningReport.store_id  == store_id,
                    ReasoningReport.dimension == dimension,
                    ReasoningReport.severity.in_(["P1", "P2", "P3"]),
                )
            )
            .order_by(ReasoningReport.report_date.desc())
            .limit(1)
        )
        report = (await db.execute(stmt)).scalar_one_or_none()
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"门店 {store_id} 在 {dimension} 维度暂无 P1/P2/P3 推理报告",
            )
        return report

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="report_id 和 dimension 至少提供一个",
    )


def _plan_to_dict(plan: ActionPlan, full: bool = False) -> dict:
    base = {
        "plan_id":           str(plan.id),
        "reasoning_report_id": str(plan.reasoning_report_id),
        "store_id":          plan.store_id,
        "report_date":       plan.report_date.isoformat() if plan.report_date else None,
        "dimension":         plan.dimension,
        "severity":          plan.severity,
        "root_cause":        plan.root_cause,
        "confidence":        plan.confidence,
        "dispatch_status":   plan.dispatch_status,
        "dispatched_at":     plan.dispatched_at.isoformat() if plan.dispatched_at else None,
        "dispatched_actions": plan.dispatched_actions,
        "outcome":           plan.outcome,
        "resolved_at":       plan.resolved_at.isoformat() if plan.resolved_at else None,
        "resolved_by":       plan.resolved_by,
        "created_at":        plan.created_at.isoformat() if plan.created_at else None,
    }
    if full:
        base.update({
            "wechat_action_id":   plan.wechat_action_id,
            "task_id":            str(plan.task_id) if plan.task_id else None,
            "decision_log_id":    str(plan.decision_log_id) if plan.decision_log_id else None,
            "notification_ids":   plan.notification_ids,
            "outcome_note":       plan.outcome_note,
            "followup_report_id": str(plan.followup_report_id) if plan.followup_report_id else None,
            "kpi_delta":          plan.kpi_delta,
        })
    return base
