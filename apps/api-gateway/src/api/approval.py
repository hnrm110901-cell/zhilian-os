"""
审批流API
Approval Workflow API

提供Human-in-the-loop决策审批接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

from ..core.dependencies import get_current_active_user, get_db
from ..core.permissions import Permission, require_permission
from ..models import User
from ..models.decision_log import DecisionLog, DecisionType, DecisionStatus, DecisionOutcome
from ..services.approval_service import approval_service
from sqlalchemy.orm import Session

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class CreateApprovalRequest(BaseModel):
    """创建审批请求"""
    decision_type: str = Field(..., description="决策类型")
    agent_type: str = Field(..., description="Agent类型")
    agent_method: str = Field(..., description="Agent方法名")
    store_id: str = Field(..., description="门店ID")
    ai_suggestion: Dict[str, Any] = Field(..., description="AI建议内容")
    ai_confidence: float = Field(..., description="AI置信度 (0-1)", ge=0, le=1)
    ai_reasoning: str = Field(..., description="AI推理过程")
    ai_alternatives: Optional[List[Dict[str, Any]]] = Field(None, description="AI备选方案")
    context_data: Optional[Dict[str, Any]] = Field(None, description="决策上下文数据")
    rag_context: Optional[Dict[str, Any]] = Field(None, description="RAG检索上下文")


class ApproveDecisionRequest(BaseModel):
    """批准决策请求"""
    manager_feedback: Optional[str] = Field(None, description="店长反馈意见")


class RejectDecisionRequest(BaseModel):
    """拒绝决策请求"""
    manager_feedback: str = Field(..., description="拒绝原因")


class ModifyDecisionRequest(BaseModel):
    """修改决策请求"""
    modified_decision: Dict[str, Any] = Field(..., description="修改后的决策")
    manager_feedback: Optional[str] = Field(None, description="修改说明")


class RecordOutcomeRequest(BaseModel):
    """记录决策结果请求"""
    outcome: str = Field(..., description="决策结果: success, failure, partial, pending")
    actual_result: Dict[str, Any] = Field(..., description="实际结果数据")
    expected_result: Dict[str, Any] = Field(..., description="预期结果数据")
    business_impact: Optional[Dict[str, Any]] = Field(None, description="业务影响指标")


class DecisionLogResponse(BaseModel):
    """决策日志响应"""
    id: str
    decision_type: str
    agent_type: str
    agent_method: str
    store_id: str
    ai_suggestion: Dict[str, Any]
    ai_confidence: float
    ai_reasoning: str
    ai_alternatives: List[Dict[str, Any]]
    manager_id: Optional[str]
    manager_decision: Optional[Dict[str, Any]]
    manager_feedback: Optional[str]
    decision_status: str
    created_at: str
    approved_at: Optional[str]
    executed_at: Optional[str]
    outcome: Optional[str]
    trust_score: Optional[float]

    class Config:
        from_attributes = True


class DecisionStatisticsResponse(BaseModel):
    """决策统计响应"""
    total: int
    approved: int
    rejected: int
    modified: int
    pending: int
    approval_rate: float
    modification_rate: float
    rejection_rate: float
    avg_trust_score: float
    by_type: Dict[str, int]


# ==================== 审批管理 ====================


@router.post("/approvals", summary="创建审批请求", response_model=DecisionLogResponse)
async def create_approval(
    request: CreateApprovalRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    创建审批请求

    当Agent生成决策建议时，调用此接口创建审批请求。
    系统会自动发送企微通知给相关店长。
    """
    try:
        # 验证决策类型
        try:
            decision_type = DecisionType(request.decision_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid decision type: {request.decision_type}")

        # 创建审批请求
        decision_log = await approval_service.create_approval_request(
            decision_type=decision_type,
            agent_type=request.agent_type,
            agent_method=request.agent_method,
            store_id=request.store_id,
            ai_suggestion=request.ai_suggestion,
            ai_confidence=request.ai_confidence,
            ai_reasoning=request.ai_reasoning,
            ai_alternatives=request.ai_alternatives,
            context_data=request.context_data,
            rag_context=request.rag_context,
            db=db
        )

        logger.info(
            "approval_created",
            decision_id=decision_log.id,
            decision_type=request.decision_type,
            store_id=request.store_id,
            user_id=current_user.id
        )

        return decision_log.to_dict()

    except Exception as e:
        logger.error("create_approval_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approvals", summary="获取待审批列表", response_model=List[DecisionLogResponse])
async def get_pending_approvals(
    store_id: Optional[str] = Query(None, description="门店ID"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取待审批决策列表

    店长可以查看自己管理门店的待审批决策。
    管理员可以查看所有门店的待审批决策。
    """
    try:
        # 如果是店长，只能查看自己管理的门店
        if current_user.role in ["store_manager", "assistant_manager"]:
            manager_id = current_user.id
        else:
            manager_id = None

        decisions = await approval_service.get_pending_approvals(
            store_id=store_id,
            manager_id=manager_id,
            db=db
        )

        return [decision.to_dict() for decision in decisions]

    except Exception as e:
        logger.error("get_pending_approvals_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approvals/{decision_id}", summary="获取审批详情", response_model=DecisionLogResponse)
async def get_approval_detail(
    decision_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取审批详情

    查看特定决策的完整信息，包括AI建议、审批历史等。
    """
    try:
        decision_log = db.query(DecisionLog).filter(DecisionLog.id == decision_id).first()
        if not decision_log:
            raise HTTPException(status_code=404, detail="Decision not found")

        return decision_log.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_approval_detail_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/{decision_id}/approve", summary="批准决策", response_model=DecisionLogResponse)
async def approve_decision(
    decision_id: str,
    request: ApproveDecisionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    批准决策

    店长批准AI的决策建议，系统将执行该决策。
    """
    try:
        decision_log = await approval_service.approve_decision(
            decision_id=decision_id,
            manager_id=current_user.id,
            manager_feedback=request.manager_feedback,
            db=db
        )

        logger.info(
            "decision_approved",
            decision_id=decision_id,
            manager_id=current_user.id
        )

        return decision_log.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("approve_decision_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/{decision_id}/reject", summary="拒绝决策", response_model=DecisionLogResponse)
async def reject_decision(
    decision_id: str,
    request: RejectDecisionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    拒绝决策

    店长拒绝AI的决策建议，需要说明拒绝原因。
    拒绝的决策将被标记为训练数据，用于优化AI。
    """
    try:
        decision_log = await approval_service.reject_decision(
            decision_id=decision_id,
            manager_id=current_user.id,
            manager_feedback=request.manager_feedback,
            db=db
        )

        logger.info(
            "decision_rejected",
            decision_id=decision_id,
            manager_id=current_user.id,
            reason=request.manager_feedback
        )

        return decision_log.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("reject_decision_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/{decision_id}/modify", summary="修改决策", response_model=DecisionLogResponse)
async def modify_decision(
    decision_id: str,
    request: ModifyDecisionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    修改决策

    店长修改AI的决策建议，系统将执行修改后的决策。
    修改的决策将被标记为训练数据，用于优化AI。
    """
    try:
        decision_log = await approval_service.modify_decision(
            decision_id=decision_id,
            manager_id=current_user.id,
            modified_decision=request.modified_decision,
            manager_feedback=request.manager_feedback,
            db=db
        )

        logger.info(
            "decision_modified",
            decision_id=decision_id,
            manager_id=current_user.id
        )

        return decision_log.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("modify_decision_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approvals/{decision_id}/outcome", summary="记录决策结果", response_model=DecisionLogResponse)
async def record_decision_outcome(
    decision_id: str,
    request: RecordOutcomeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    记录决策结果

    决策执行后，记录实际结果和业务影响。
    系统会自动计算信任度评分。
    """
    try:
        # 验证结果类型
        try:
            outcome = DecisionOutcome(request.outcome)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid outcome: {request.outcome}")

        decision_log = await approval_service.record_decision_outcome(
            decision_id=decision_id,
            outcome=outcome,
            actual_result=request.actual_result,
            expected_result=request.expected_result,
            business_impact=request.business_impact,
            db=db
        )

        logger.info(
            "decision_outcome_recorded",
            decision_id=decision_id,
            outcome=request.outcome,
            trust_score=decision_log.trust_score
        )

        return decision_log.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("record_decision_outcome_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approvals/statistics", summary="获取决策统计", response_model=DecisionStatisticsResponse)
async def get_decision_statistics(
    store_id: Optional[str] = Query(None, description="门店ID"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取决策统计数据

    查看决策的批准率、拒绝率、修改率等统计指标。
    """
    try:
        statistics = await approval_service.get_decision_statistics(
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            db=db
        )

        return statistics

    except Exception as e:
        logger.error("get_decision_statistics_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 企微回调 ====================


@router.post("/approvals/wechat/callback", summary="企微审批回调")
async def wechat_approval_callback(
    decision_id: str = Query(..., description="决策ID"),
    action: str = Query(..., description="操作: approve, reject, modify"),
    user_id: str = Query(..., description="用户ID"),
    feedback: Optional[str] = Query(None, description="反馈意见"),
    modified_data: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db)
):
    """
    企微审批回调

    处理来自企微的审批操作回调。
    """
    try:
        if action == "approve":
            decision_log = await approval_service.approve_decision(
                decision_id=decision_id,
                manager_id=user_id,
                manager_feedback=feedback,
                db=db
            )
        elif action == "reject":
            if not feedback:
                raise HTTPException(status_code=400, detail="Feedback is required for rejection")
            decision_log = await approval_service.reject_decision(
                decision_id=decision_id,
                manager_id=user_id,
                manager_feedback=feedback,
                db=db
            )
        elif action == "modify":
            if not modified_data:
                raise HTTPException(status_code=400, detail="Modified data is required")
            decision_log = await approval_service.modify_decision(
                decision_id=decision_id,
                manager_id=user_id,
                modified_decision=modified_data,
                manager_feedback=feedback,
                db=db
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

        logger.info(
            "wechat_callback_processed",
            decision_id=decision_id,
            action=action,
            user_id=user_id
        )

        return {
            "success": True,
            "message": "Callback processed successfully",
            "decision_id": decision_log.id,
            "status": decision_log.decision_status.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("wechat_callback_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
