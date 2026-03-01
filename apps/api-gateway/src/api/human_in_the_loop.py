"""
Human-in-the-Loop API - 人机协同审批API
"机器不可信"安全防线 - 高危操作分级审批
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict

from src.core.dependencies import get_db, get_current_user
from src.services.human_in_the_loop_service import (
    get_human_in_the_loop_service,
    HumanInTheLoopService,
    OperationType,
    RiskLevel,
    TrustPhase,
    ApprovalStatus
)
from src.models.user import User
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/human-in-the-loop")


class AIDecisionRequest(BaseModel):
    """AI决策请求"""
    store_id: str
    operation_type: OperationType
    description: str
    reasoning: str
    expected_impact: Dict
    confidence_score: float
    operation_params: Dict


class ApprovalDecision(BaseModel):
    """审批决定"""
    request_id: str
    approved: bool
    comment: Optional[str] = None


@router.post("/submit-decision")
async def submit_ai_decision(
    request: AIDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    提交AI决策

    AI做出决策后，根据风险等级决定是自动执行还是提交人工审批

    风险等级:
    - **Level 1 (Low)**: 自动执行（查询、分析、报表、通知）
    - **Level 2 (Medium)**: 自动执行+事后审计（自动排班、小额采购、优惠券发放）
    - **Level 3 (High)**: 人工审批（大额采购、人员调动、价格调整、供应商变更）
    - **Level 4 (Critical)**: 禁止AI操作（资金打款、数据删除、权限变更、合同签署）
    """
    service = get_human_in_the_loop_service(db)

    result = await service.submit_ai_decision(
        store_id=request.store_id,
        operation_type=request.operation_type,
        description=request.description,
        reasoning=request.reasoning,
        expected_impact=request.expected_impact,
        confidence_score=request.confidence_score,
        operation_params=request.operation_params
    )

    return result


@router.post("/approve")
async def approve_request(
    decision: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    审批请求

    店长或管理员审批AI提交的高风险操作
    """
    service = get_human_in_the_loop_service(db)

    approval = await service.approve_request(
        request_id=decision.request_id,
        approver_id=current_user.id,
        approved=decision.approved,
        comment=decision.comment
    )

    return {
        "success": True,
        "approval": approval.model_dump(),
        "message": "审批成功" if decision.approved else "已拒绝"
    }


@router.get("/pending-approvals/{store_id}")
async def get_pending_approvals(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取待审批的请求

    店长可以查看所有待审批的AI决策
    """
    service = get_human_in_the_loop_service(db)
    approvals = await service.get_pending_approvals(store_id)

    return {
        "store_id": store_id,
        "total": len(approvals),
        "approvals": [a.model_dump() for a in approvals]
    }


@router.get("/trust-phase/{store_id}")
async def get_trust_phase(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取门店的信任阶段

    信任阶段决定了AI的自主权限:
    - **观察期（1-3个月）**: AI只提建议，不执行
    - **辅助期（3-6个月）**: AI执行低风险操作，高风险需审批
    - **自主期（6个月+）**: AI自主执行大部分操作，仅极高风险需审批
    """
    service = get_human_in_the_loop_service(db)
    trust_phase = await service.get_store_trust_phase(store_id)

    phase_descriptions = {
        TrustPhase.OBSERVATION: {
            "name": "观察期",
            "duration": "1-3个月",
            "description": "AI只提建议，不执行。人工对比AI建议和实际决策，建立信任基础。",
            "ai_autonomy": "0%"
        },
        TrustPhase.ASSISTANCE: {
            "name": "辅助期",
            "duration": "3-6个月",
            "description": "AI执行低风险操作，高风险操作需审批。逐步放权。",
            "ai_autonomy": "60%"
        },
        TrustPhase.AUTONOMOUS: {
            "name": "自主期",
            "duration": "6个月+",
            "description": "AI自主执行大部分操作，仅极高风险需审批。完全信任。",
            "ai_autonomy": "90%"
        }
    }

    return {
        "store_id": store_id,
        "trust_phase": trust_phase,
        "details": phase_descriptions.get(trust_phase, {})
    }


@router.get("/trust-metrics/{store_id}")
async def get_trust_metrics(
    store_id: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取门店动态信任指标

    返回驱动信任阶段计算的原始指标:
    - adoption_rate: AI建议采纳率
    - success_rate: 已完成决策的成功率
    - avg_confidence: 平均AI置信度
    - escalation_rate: 升级人工审批比例
    - phase: 当前动态信任阶段及原因
    """
    from src.services.dynamic_trust_service import compute_dynamic_phase, compute_trust_metrics

    phase_result = await compute_dynamic_phase(store_id)
    metrics = await compute_trust_metrics(store_id, days=days)

    return {
        "store_id": store_id,
        "phase": phase_result["phase"],
        "phase_reason": phase_result["reason"],
        "days_since_onboarding": phase_result["days_since_onboarding"],
        "metrics": metrics,
    }


@router.get("/statistics/{store_id}")
async def get_approval_statistics(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取审批统计

    用于评估AI的可信度和门店的信任阶段
    """
    service = get_human_in_the_loop_service(db)
    stats = await service.get_approval_statistics(store_id)

    return {
        "store_id": store_id,
        "statistics": stats,
        "trust_building": {
            "formula": "信任 = 效果 × 时间 × 透明度",
            "factors": {
                "effect": "一周内必须看到数据改善",
                "time": "3个月免费试用建立信任",
                "transparency": "所有AI决策可追溯可解释"
            }
        }
    }


@router.get("/risk-classification")
async def get_risk_classification(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取风险分类规则

    展示不同操作类型的风险等级和处理方式
    """
    risk_classification = {
        "Level 1 - 自动执行（低风险）": {
            "operations": ["查询操作", "数据分析", "报表生成", "提醒通知"],
            "handling": "自动执行，无需审批"
        },
        "Level 2 - 自动执行+事后审计（中风险）": {
            "operations": [
                "自动排班（在预算范围内）",
                "自动采购（小额订单）",
                "优惠券发放（在额度内）"
            ],
            "handling": "自动执行，记录审计日志"
        },
        "Level 3 - 人工审批（高风险）": {
            "operations": [
                "大额采购（>5000元）",
                "人员调动",
                "价格调整",
                "供应商变更"
            ],
            "handling": "推送企业微信，店长审批后执行"
        },
        "Level 4 - 禁止AI操作（极高风险）": {
            "operations": [
                "资金打款",
                "数据删除",
                "权限变更",
                "合同签署"
            ],
            "handling": "禁止AI自动执行，必须人工操作"
        }
    }

    return {
        "principle": "建立信任需要三年，摧毁信任只需大模型发疯一次",
        "risk_classification": risk_classification
    }
