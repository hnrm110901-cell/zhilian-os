"""
多阶段工作流引擎 REST API

端点：
  POST /api/v1/workflow/stores/{store_id}/start              — 启动当日规划工作流
  GET  /api/v1/workflow/stores/{store_id}/today              — 获取今日工作流状态
  GET  /api/v1/workflow/stores/{store_id}/phases             — 获取全部阶段 + 倒计时
  POST /api/v1/workflow/phases/{phase_id}/fast-plan          — 触发快速规划（秒级）
  POST /api/v1/workflow/phases/{phase_id}/submit             — 提交/更新决策版本
  POST /api/v1/workflow/phases/{phase_id}/lock               — 手动锁定阶段
  GET  /api/v1/workflow/phases/{phase_id}/versions           — 决策版本历史
  GET  /api/v1/workflow/phases/{phase_id}/diff               — 最新版本 vs 上一版本 diff
  GET  /api/v1/workflow/reports/today-summary                — 全平台今日规划进度

设计：
  - fast-plan 根据 phase_name 分别调用 FastPlanningService 对应方法
  - submit 支持人工录入（mode=manual）覆盖系统建议
  - lock 后阶段不可再提交版本（幂等，重复锁定安全）
  - today-summary 供大屏展示「今日各门店规划完成率」
"""

from __future__ import annotations

import uuid as _uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.models.workflow import (
    ALL_PHASES, PHASE_CONFIG,
    DailyWorkflow, DecisionVersion, WorkflowPhase,
    PhaseStatus, WorkflowStatus,
)
from src.services.fast_planning_service import FastPlanningService
from src.services.timing_service import TimingService
from src.services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class StartWorkflowIn(BaseModel):
    plan_date:    Optional[str] = Field(
        None, description="规划日期（默认=明天），格式 YYYY-MM-DD"
    )
    store_config: Optional[Dict[str, Any]] = Field(
        None, description="门店个性化截止时间，如 {procurement_deadline: '17:45'}"
    )


class SubmitDecisionIn(BaseModel):
    content: Dict[str, Any] = Field(
        ..., description="决策内容（各阶段格式不同，见 API 文档）"
    )
    mode: str = Field(
        "manual", description="提交模式: fast / precise / manual"
    )
    change_reason: Optional[str] = Field(None, description="修改原因说明")
    confidence: Optional[float] = Field(None, ge=0, le=1)


class LockPhaseIn(BaseModel):
    locked_by: str = Field(..., description="锁定人（员工 ID 或 '手动确认'）")


# ── 启动工作流 ────────────────────────────────────────────────────────────────

@router.post(
    "/stores/{store_id}/start",
    summary="启动门店当日规划工作流",
    status_code=status.HTTP_201_CREATED,
)
async def start_workflow(
    store_id: str,
    body:     StartWorkflowIn = StartWorkflowIn(),
    db:       AsyncSession    = Depends(get_db),
    _:        User            = Depends(get_current_user),
):
    """
    启动门店 Day N+1 的多阶段规划工作流（幂等，重复调用安全）。

    默认规划明天，可通过 plan_date 指定其他日期。
    启动后自动进入 initial_plan 阶段（Phase 1），
    可立即调用 `/phases/{id}/fast-plan` 触发快速初版规划。
    """
    if body.plan_date:
        try:
            plan_date = date.fromisoformat(body.plan_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="plan_date 格式错误，应为 YYYY-MM-DD",
            )
    else:
        plan_date = date.today() + timedelta(days=1)

    engine = WorkflowEngine(db)
    wf     = await engine.start_daily_workflow(
        store_id=store_id,
        plan_date=plan_date,
        store_config=body.store_config,
    )
    await db.commit()
    return _wf_to_dict(wf)


# ── 今日工作流状态 ────────────────────────────────────────────────────────────

@router.get(
    "/stores/{store_id}/today",
    summary="获取门店今日工作流状态",
)
async def get_today_workflow(
    store_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    获取门店当日（由今天触发的）工作流状态。

    若今日尚未启动工作流，返回 404。
    """
    engine = WorkflowEngine(db)
    wf     = await engine.get_current_workflow(store_id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="今日工作流尚未启动，请先调用 POST /stores/{store_id}/start",
        )
    return _wf_to_dict(wf)


# ── 全部阶段状态 + 倒计时 ─────────────────────────────────────────────────────

@router.get(
    "/stores/{store_id}/phases",
    summary="获取工作流全部阶段状态（含倒计时）",
)
async def get_store_phases(
    store_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    获取门店今日工作流的 6 个阶段状态，包含：
    - 各阶段的 status（pending/running/reviewing/locked）
    - 硬 deadline 时间
    - 距 deadline 倒计时
    - 最新版本号和置信度
    """
    engine = WorkflowEngine(db)
    timing = TimingService(db)

    wf = await engine.get_current_workflow(store_id)
    if not wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="今日工作流尚未启动")

    phases    = await engine.get_all_phases(wf.id)
    countdown = await timing.get_workflow_countdown(wf.id)

    # 合并最新版本信息
    result = []
    for phase, cd in zip(phases, countdown):
        latest = await engine.get_latest_version(phase.id)
        result.append({
            **cd,
            "phase_id":        str(phase.id),
            "latest_version":  latest.version_number if latest else 0,
            "latest_mode":     latest.generation_mode if latest else None,
            "latest_confidence": latest.confidence if latest else None,
        })
    return {"workflow": _wf_to_dict(wf), "phases": result}


# ── 触发快速规划 ──────────────────────────────────────────────────────────────

@router.post(
    "/phases/{phase_id}/fast-plan",
    summary="触发快速规划（秒级生成初版决策）",
)
async def trigger_fast_plan(
    phase_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    对指定阶段触发快速规划（使用 FastPlanningService，<30 秒响应）。

    支持阶段：initial_plan / procurement / scheduling / menu / marketing

    快速模式使用历史规律 + L3/L4 数据，准确度约 80%。
    生成后自动保存为最新版本（mode=fast），店长可进一步人工修改。
    """
    import time

    pid   = _parse_uuid(phase_id)
    phase, wf = await _get_phase_and_wf(pid, db)

    if phase.status == PhaseStatus.LOCKED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"阶段 {phase.phase_name} 已锁定，无法重新生成",
        )

    fast_svc = FastPlanningService(db)
    engine   = WorkflowEngine(db)

    t0 = time.time()
    try:
        if phase.phase_name == "initial_plan":
            content = await fast_svc.generate_initial_plan(wf.store_id, wf.plan_date)
        elif phase.phase_name == "procurement":
            # 从 initial_plan 取预测客流
            init_phase   = await engine.get_phase(wf.id, "initial_plan")
            init_ver     = await engine.get_latest_version(init_phase.id) if init_phase else None
            footfall     = (init_ver.content or {}).get("forecast_footfall", 80) if init_ver else 80
            content      = await fast_svc.generate_procurement(wf.store_id, wf.plan_date, footfall)
        elif phase.phase_name == "scheduling":
            init_phase   = await engine.get_phase(wf.id, "initial_plan")
            init_ver     = await engine.get_latest_version(init_phase.id) if init_phase else None
            footfall     = (init_ver.content or {}).get("forecast_footfall", 80) if init_ver else 80
            content      = await fast_svc.generate_scheduling(wf.store_id, wf.plan_date, footfall)
        elif phase.phase_name == "menu":
            content = await fast_svc.generate_menu_plan(wf.store_id, wf.plan_date)
        elif phase.phase_name == "marketing":
            menu_phase   = await engine.get_phase(wf.id, "menu")
            menu_ver     = await engine.get_latest_version(menu_phase.id) if menu_phase else None
            menu_plan    = menu_ver.content if menu_ver else {}
            content      = await fast_svc.generate_marketing_plan(wf.store_id, wf.plan_date, menu_plan)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"阶段 {phase.phase_name} 不支持快速规划",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"快速规划生成失败: {str(e)}",
        )

    elapsed = round(time.time() - t0, 2)
    version = await engine.submit_decision(
        phase_id=pid,
        content=content,
        submitted_by="system",
        mode="fast",
        generation_seconds=elapsed,
        data_completeness=content.get("data_completeness", 0.7),
        confidence=content.get("confidence", 0.75),
        change_reason="系统快速规划自动生成",
    )
    await db.commit()
    return {
        "phase_name":        phase.phase_name,
        "version_number":    version.version_number,
        "generation_seconds": elapsed,
        "data_completeness": version.data_completeness,
        "confidence":        version.confidence,
        "content":           version.content,
    }


# ── 提交/更新决策 ─────────────────────────────────────────────────────────────

@router.post(
    "/phases/{phase_id}/submit",
    summary="提交/更新决策版本（人工修改）",
)
async def submit_decision(
    phase_id: str,
    body:     SubmitDecisionIn,
    db:       AsyncSession = Depends(get_db),
    user:     User         = Depends(get_current_user),
):
    """
    向指定阶段提交新的决策版本（人工修改系统建议）。

    每次提交自动递增版本号，并记录与上一版本的 diff。
    阶段 LOCKED 后不可再提交。
    """
    pid    = _parse_uuid(phase_id)
    phase, _ = await _get_phase_and_wf(pid, db)

    engine  = WorkflowEngine(db)
    version = await engine.submit_decision(
        phase_id=pid,
        content=body.content,
        submitted_by=str(user.id) if hasattr(user, "id") else "user",
        mode=body.mode,
        confidence=body.confidence or 0.9,
        change_reason=body.change_reason or "",
    )
    await db.commit()
    return _version_to_dict(version)


# ── 手动锁定阶段 ──────────────────────────────────────────────────────────────

@router.post(
    "/phases/{phase_id}/lock",
    summary="手动锁定阶段（店长确认）",
)
async def lock_phase(
    phase_id: str,
    body:     LockPhaseIn,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    店长确认后手动锁定阶段，将当前最新版本标记为最终版本。

    锁定后：
    - 该阶段不可再提交新版本
    - 自动推进到下一阶段（如 procurement → scheduling）
    - 发送企微通知给相关人员
    """
    pid    = _parse_uuid(phase_id)
    engine = WorkflowEngine(db)
    phase  = await engine.lock_phase(pid, locked_by=body.locked_by)
    await db.commit()
    return {
        "phase_name": phase.phase_name,
        "status":     phase.status,
        "locked_at":  phase.locked_at.isoformat() if phase.locked_at else None,
        "locked_by":  phase.locked_by,
    }


# ── 版本历史 ──────────────────────────────────────────────────────────────────

@router.get(
    "/phases/{phase_id}/versions",
    summary="获取阶段决策版本历史",
)
async def get_versions(
    phase_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    获取阶段全部决策版本历史（版本链），
    每个版本包含生成时间、模式、置信度和与前一版本的 diff。
    """
    pid      = _parse_uuid(phase_id)
    engine   = WorkflowEngine(db)
    versions = await engine.get_phase_versions(pid)
    return [_version_to_dict(v) for v in versions]


# ── 版本 diff ────────────────────────────────────────────────────────────────

@router.get(
    "/phases/{phase_id}/diff",
    summary="获取最新版本 vs 上一版本的变化 diff",
)
async def get_diff(
    phase_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    返回最新决策版本与上一版本的差异（方便店长快速核查修改了什么）。
    """
    pid      = _parse_uuid(phase_id)
    engine   = WorkflowEngine(db)
    versions = await engine.get_phase_versions(pid)

    if not versions:
        return {"diff": None, "message": "暂无版本"}
    if len(versions) == 1:
        return {"diff": None, "message": "仅有初版，无 diff", "version": 1}

    latest = versions[-1]
    return {
        "version_from": versions[-2].version_number,
        "version_to":   latest.version_number,
        "diff":         latest.changes_from_prev,
        "change_reason": latest.change_reason,
        "submitted_by":  latest.submitted_by,
        "submitted_at":  latest.created_at.isoformat() if latest.created_at else None,
    }


# ── 全平台今日规划进度大屏 ────────────────────────────────────────────────────

@router.get(
    "/reports/today-summary",
    summary="全平台今日规划进度（大屏）",
)
async def get_today_summary(
    db: AsyncSession = Depends(get_db),
    _:  User         = Depends(get_current_user),
):
    """
    全平台今日规划进度统计：

    - 已启动工作流数量
    - 各阶段 locked/running/pending 分布
    - 今日已完全锁定的门店数（all phases locked）
    - 有逾期阶段的门店数（高风险）
    """
    from datetime import datetime
    today = date.today()

    # 今日所有工作流
    wf_stmt = (
        select(DailyWorkflow)
        .where(DailyWorkflow.trigger_date == today)
    )
    workflows = (await db.execute(wf_stmt)).scalars().all()

    total_stores  = len(workflows)
    fully_locked  = 0
    overdue_stores = 0
    phase_dist    = {p: {"locked": 0, "running": 0, "pending": 0} for p in ALL_PHASES}

    timing = TimingService(db)
    for wf in workflows:
        phases = (await db.execute(
            select(WorkflowPhase).where(WorkflowPhase.workflow_id == wf.id)
        )).scalars().all()

        all_locked  = all(p.status == PhaseStatus.LOCKED.value for p in phases)
        any_overdue = any(timing.is_overdue(p) for p in phases
                         if p.status in (PhaseStatus.RUNNING.value, PhaseStatus.REVIEWING.value))

        if all_locked:
            fully_locked += 1
        if any_overdue:
            overdue_stores += 1

        for p in phases:
            if p.phase_name in phase_dist:
                bucket = "locked" if p.status == PhaseStatus.LOCKED.value else \
                         "running" if p.status in (PhaseStatus.RUNNING.value, PhaseStatus.REVIEWING.value) else \
                         "pending"
                phase_dist[p.phase_name][bucket] += 1

    return {
        "date":              today.isoformat(),
        "total_stores":      total_stores,
        "fully_locked":      fully_locked,
        "overdue_stores":    overdue_stores,
        "completion_rate":   round(fully_locked / total_stores * 100, 1) if total_stores else 0,
        "phase_distribution": phase_dist,
    }


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _parse_uuid(raw: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"UUID 格式错误: {raw}",
        )


async def _get_phase_and_wf(
    phase_id: _uuid.UUID, db: AsyncSession
) -> tuple:
    """获取 WorkflowPhase 及其所属的 DailyWorkflow"""
    phase_stmt = select(WorkflowPhase).where(WorkflowPhase.id == phase_id)
    phase = (await db.execute(phase_stmt)).scalar_one_or_none()
    if not phase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流阶段不存在")

    wf_stmt = select(DailyWorkflow).where(DailyWorkflow.id == phase.workflow_id)
    wf = (await db.execute(wf_stmt)).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    return phase, wf


def _wf_to_dict(wf: DailyWorkflow) -> dict:
    return {
        "workflow_id":   str(wf.id),
        "store_id":      wf.store_id,
        "plan_date":     wf.plan_date.isoformat() if wf.plan_date else None,
        "trigger_date":  wf.trigger_date.isoformat() if wf.trigger_date else None,
        "status":        wf.status,
        "current_phase": wf.current_phase,
        "started_at":    wf.started_at.isoformat() if wf.started_at else None,
        "completed_at":  wf.completed_at.isoformat() if wf.completed_at else None,
    }


def _version_to_dict(v: DecisionVersion) -> dict:
    return {
        "version_id":         str(v.id),
        "phase_id":           str(v.phase_id),
        "version_number":     v.version_number,
        "phase_name":         v.phase_name,
        "plan_date":          v.plan_date.isoformat() if v.plan_date else None,
        "generation_mode":    v.generation_mode,
        "generation_seconds": v.generation_seconds,
        "data_completeness":  v.data_completeness,
        "confidence":         v.confidence,
        "content":            v.content,
        "changes_from_prev":  v.changes_from_prev,
        "change_reason":      v.change_reason,
        "submitted_by":       v.submitted_by,
        "is_final":           v.is_final,
        "created_at":         v.created_at.isoformat() if v.created_at else None,
    }
