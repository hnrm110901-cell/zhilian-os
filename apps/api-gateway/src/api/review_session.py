"""
五步闭环经营复盘 API

端点：
  POST   /sessions                          — 创建复盘会
  GET    /sessions                          — 列表查询
  GET    /sessions/{session_id}             — 复盘会详情（含核查清单 + 措施）
  POST   /sessions/{session_id}/breakdown   — Step 1: 生成拆细账快照
  PATCH  /checklists/{checklist_id}         — Step 2: 勾选核查项
  GET    /sessions/{session_id}/advance     — 检查是否可推进到下一步
  POST   /sessions/{session_id}/advance     — 推进步骤
  POST   /sessions/{session_id}/actions     — Step 3: 创建措施
  PATCH  /actions/{action_id}/progress      — Step 4: 更新执行进度
  POST   /actions/{action_id}/close         — Step 5: 关闭措施
  GET    /sessions/{session_id}/summary     — Step 5: 生成结果摘要
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_active_user, get_db
from src.models.user import User
from src.services.review_session_service import ReviewSessionService

router = APIRouter(prefix="/api/v1/review", tags=["review-session"])


# ── Request / Response Models ─────────────────────────────────────────────


class CreateSessionReq(BaseModel):
    store_id: str
    review_type: str = Field(..., pattern="^(weekly|monthly)$")
    period_label: str = Field(..., description="周: 2026-W12, 月: 2026-03")
    created_by: str = ""


class VerifyChecklistReq(BaseModel):
    verified: bool
    verified_by: str = ""
    verification_note: str = ""


class CreateActionReq(BaseModel):
    owner: str = Field(..., min_length=1, description="责任人")
    deadline: date = Field(..., description="完成时限")
    action_desc: str = Field(..., min_length=1, description="具体动作")
    target_kpi: str = Field(..., min_length=1, description="可量化结果")


class UpdateProgressReq(BaseModel):
    progress_pct: int = Field(..., ge=0, le=100)
    current_kpi_value: str = ""
    note: str = ""
    updated_by: str = ""


class CloseActionReq(BaseModel):
    is_achieved: bool
    actual_impact_fen: int = 0
    closed_note: str = ""


class AdvanceStepReq(BaseModel):
    target_step: int = Field(..., ge=1, le=5)


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/sessions")
async def create_session(req: CreateSessionReq, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """创建复盘会（自动生成核查清单）"""
    svc = ReviewSessionService(db)
    try:
        session = await svc.create_session(
            store_id=req.store_id,
            review_type=req.review_type,
            period_label=req.period_label,
            created_by=req.created_by,
        )
        await db.commit()
        detail = await svc.get_session_detail(str(session.id))
        return detail
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    store_id: str = Query(...),
    review_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    """查询门店复盘会列表"""
    svc = ReviewSessionService(db)
    sessions = await svc.list_sessions(store_id, review_type, limit, offset)
    return [
        {
            "id": str(s.id),
            "store_id": s.store_id,
            "review_type": s.review_type,
            "period_label": s.period_label,
            "current_step": s.current_step,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """获取复盘会完整详情"""
    svc = ReviewSessionService(db)
    try:
        return await svc.get_session_detail(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sessions/{session_id}/breakdown")
async def generate_breakdown(session_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Step 1: 生成拆细账快照"""
    svc = ReviewSessionService(db)
    try:
        breakdown = await svc.generate_breakdown(session_id)
        await db.commit()
        return breakdown
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/checklists/{checklist_id}")
async def verify_checklist(
    checklist_id: str,
    req: VerifyChecklistReq,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    """Step 2: 勾选/取消勾选核查项"""
    svc = ReviewSessionService(db)
    try:
        item = await svc.verify_checklist_item(
            checklist_id=checklist_id,
            verified=req.verified,
            verified_by=req.verified_by,
            verification_note=req.verification_note,
        )
        await db.commit()
        return {
            "id": str(item.id),
            "dimension": item.dimension,
            "verified": item.verified,
            "verified_by": item.verified_by,
            "verification_note": item.verification_note,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions/{session_id}/advance-check")
async def check_advance(session_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """检查是否满足推进到 Step 3 的条件"""
    svc = ReviewSessionService(db)
    return await svc.can_advance_to_step3(session_id)


@router.post("/sessions/{session_id}/advance")
async def advance_step(
    session_id: str,
    req: AdvanceStepReq,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    """推进复盘会到下一步"""
    svc = ReviewSessionService(db)
    try:
        session = await svc.advance_step(session_id, req.target_step)
        await db.commit()
        return {"current_step": session.current_step, "status": session.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/actions")
async def create_action(
    session_id: str,
    req: CreateActionReq,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    """Step 3: 创建措施（四字段缺一不可）"""
    svc = ReviewSessionService(db)
    try:
        action = await svc.create_action(
            session_id=session_id,
            owner=req.owner,
            deadline=req.deadline,
            action_desc=req.action_desc,
            target_kpi=req.target_kpi,
        )
        await db.commit()
        return {
            "id": str(action.id),
            "owner": action.owner,
            "deadline": str(action.deadline),
            "action_desc": action.action_desc,
            "target_kpi": action.target_kpi,
            "progress_status": action.progress_status,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/actions/{action_id}/progress")
async def update_progress(
    action_id: str,
    req: UpdateProgressReq,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    """Step 4: 更新措施执行进度"""
    svc = ReviewSessionService(db)
    try:
        action = await svc.update_action_progress(
            action_id=action_id,
            progress_pct=req.progress_pct,
            current_kpi_value=req.current_kpi_value,
            note=req.note,
            updated_by=req.updated_by,
        )
        await db.commit()
        return {
            "id": str(action.id),
            "progress_pct": action.progress_pct,
            "progress_status": action.progress_status,
            "alert_level": action.alert_level,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/actions/{action_id}/close")
async def close_action(
    action_id: str,
    req: CloseActionReq,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user),
):
    """Step 5: 关闭措施（看结果）"""
    svc = ReviewSessionService(db)
    try:
        action = await svc.close_action(
            action_id=action_id,
            is_achieved=req.is_achieved,
            actual_impact_fen=req.actual_impact_fen,
            closed_note=req.closed_note,
        )
        await db.commit()
        return {
            "id": str(action.id),
            "is_achieved": action.is_achieved,
            "actual_impact_yuan": round((action.actual_impact_fen or 0) / 100, 2),
            "progress_status": action.progress_status,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions/{session_id}/summary")
async def get_result_summary(session_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Step 5: 生成/获取闭环结果摘要"""
    svc = ReviewSessionService(db)
    try:
        summary = await svc.generate_result_summary(session_id)
        await db.commit()
        return summary
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
