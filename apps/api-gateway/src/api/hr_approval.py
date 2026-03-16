"""
HR 通用审批流 API — 发起/通过/驳回/转交/催办/委托
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_active_user
from src.models.approval import ApprovalDelegation, ApprovalInstance, ApprovalTemplate
from src.models.user import User
from src.services.approval_engine import approval_engine

logger = structlog.get_logger()
router = APIRouter()


# ── Request / Response Models ────────────────────────────────


class SubmitApprovalRequest(BaseModel):
    template_code: str = Field(..., description="审批模板编码: leave/salary_adjust/resign/reward/contract_renew")
    business_type: str = Field(..., description="业务类型: leave_request/salary_adjust/resign/reward_penalty/contract")
    business_id: str = Field(..., description="关联的业务记录ID")
    applicant_id: str
    applicant_name: str
    store_id: str
    brand_id: str
    amount_fen: Optional[int] = Field(None, description="金额(分)，用于阈梯触发")
    summary: Optional[str] = Field(None, description="业务摘要")


class ApprovalActionRequest(BaseModel):
    approver_id: str
    approver_name: str
    comment: Optional[str] = None


class DelegateRequest(BaseModel):
    approver_id: str
    delegate_to_id: str
    delegate_to_name: str
    comment: Optional[str] = None


class CreateTemplateRequest(BaseModel):
    brand_id: str
    template_code: str
    template_name: str
    approval_chain: list = Field(..., description="审批链路 JSON")
    amount_thresholds: Optional[list] = Field(default_factory=list)
    description: Optional[str] = None


class CreateDelegationRequest(BaseModel):
    brand_id: str
    delegator_id: str
    delegator_name: str
    delegate_id: str
    delegate_name: str
    start_date: date
    end_date: date
    template_codes: Optional[list] = Field(default_factory=list, description="委托的审批类型，空=全部")


# ── 审批流程 API ─────────────────────────────────────────────


@router.post("/hr/approval/submit")
async def submit_approval(
    req: SubmitApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """发起审批"""
    try:
        instance = await approval_engine.submit(
            db=db,
            template_code=req.template_code,
            business_type=req.business_type,
            business_id=req.business_id,
            applicant_id=req.applicant_id,
            applicant_name=req.applicant_name,
            store_id=req.store_id,
            brand_id=req.brand_id,
            amount_fen=req.amount_fen,
            summary=req.summary,
        )
        await db.commit()
        return {
            "success": True,
            "instance_id": str(instance.id),
            "status": instance.status,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("approval.submit.failed", error=str(e))
        raise HTTPException(status_code=500, detail="发起审批失败")


@router.post("/hr/approval/{instance_id}/approve")
async def approve_approval(
    instance_id: UUID,
    req: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """审批通过"""
    try:
        instance = await approval_engine.approve(
            db=db,
            instance_id=instance_id,
            approver_id=req.approver_id,
            approver_name=req.approver_name,
            comment=req.comment,
        )
        await db.commit()
        return {
            "success": True,
            "instance_id": str(instance.id),
            "status": instance.status,
            "final_result": instance.final_result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("approval.approve.failed", error=str(e))
        raise HTTPException(status_code=500, detail="审批操作失败")


@router.post("/hr/approval/{instance_id}/reject")
async def reject_approval(
    instance_id: UUID,
    req: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """审批驳回"""
    try:
        instance = await approval_engine.reject(
            db=db,
            instance_id=instance_id,
            approver_id=req.approver_id,
            approver_name=req.approver_name,
            comment=req.comment,
        )
        await db.commit()
        return {
            "success": True,
            "instance_id": str(instance.id),
            "status": instance.status,
            "final_result": instance.final_result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("approval.reject.failed", error=str(e))
        raise HTTPException(status_code=500, detail="驳回操作失败")


@router.post("/hr/approval/{instance_id}/delegate")
async def delegate_approval(
    instance_id: UUID,
    req: DelegateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """转交审批"""
    try:
        instance = await approval_engine.delegate(
            db=db,
            instance_id=instance_id,
            approver_id=req.approver_id,
            delegate_to_id=req.delegate_to_id,
            delegate_to_name=req.delegate_to_name,
            comment=req.comment,
        )
        await db.commit()
        return {
            "success": True,
            "instance_id": str(instance.id),
            "status": instance.status,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("approval.delegate.failed", error=str(e))
        raise HTTPException(status_code=500, detail="转交操作失败")


@router.get("/hr/approval/pending")
async def get_pending_approvals(
    approver_id: str = Query(..., description="审批人ID"),
    brand_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取我的待审批列表"""
    try:
        instances = await approval_engine.get_pending_approvals(
            db=db,
            approver_id=approver_id,
            brand_id=brand_id,
        )
        return {
            "success": True,
            "total": len(instances),
            "items": [
                {
                    "id": str(inst.id),
                    "template_code": inst.template_code,
                    "business_type": inst.business_type,
                    "business_id": inst.business_id,
                    "applicant_id": inst.applicant_id,
                    "applicant_name": inst.applicant_name,
                    "status": inst.status,
                    "current_level": inst.current_level,
                    "amount_fen": inst.amount_fen,
                    "summary": inst.summary,
                    "deadline": inst.deadline.isoformat() if inst.deadline else None,
                    "created_at": inst.created_at.isoformat() if inst.created_at else None,
                }
                for inst in instances
            ],
        }
    except Exception as e:
        logger.error("approval.pending.failed", error=str(e))
        raise HTTPException(status_code=500, detail="查询待审批列表失败")


@router.get("/hr/approval/history/{instance_id}")
async def get_approval_history(
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取审批轨迹"""
    try:
        history = await approval_engine.get_approval_history(db, instance_id)
        return {"success": True, **history}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("approval.history.failed", error=str(e))
        raise HTTPException(status_code=500, detail="查询审批轨迹失败")


# ── 审批模板管理 ─────────────────────────────────────────────


@router.get("/hr/approval/templates")
async def list_templates(
    brand_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """审批模板列表"""
    conditions = [ApprovalTemplate.is_active.is_(True)]
    if brand_id:
        conditions.append(ApprovalTemplate.brand_id == brand_id)

    result = await db.execute(select(ApprovalTemplate).where(and_(*conditions)))
    templates = result.scalars().all()

    return {
        "success": True,
        "total": len(templates),
        "items": [
            {
                "id": str(t.id),
                "brand_id": t.brand_id,
                "template_code": t.template_code,
                "template_name": t.template_name,
                "approval_chain": t.approval_chain,
                "amount_thresholds": t.amount_thresholds,
                "description": t.description,
            }
            for t in templates
        ],
    }


@router.post("/hr/approval/templates")
async def create_template(
    req: CreateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建审批模板"""
    # 检查 template_code 唯一性
    existing = await db.execute(select(ApprovalTemplate).where(ApprovalTemplate.template_code == req.template_code))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail=f"模板编码 {req.template_code} 已存在")

    template = ApprovalTemplate(
        brand_id=req.brand_id,
        template_code=req.template_code,
        template_name=req.template_name,
        approval_chain=req.approval_chain,
        amount_thresholds=req.amount_thresholds or [],
        description=req.description,
        is_active=True,
    )
    db.add(template)
    await db.commit()

    return {
        "success": True,
        "template_id": str(template.id),
        "template_code": template.template_code,
    }


# ── 审批委托管理 ─────────────────────────────────────────────


@router.post("/hr/approval/delegations")
async def create_delegation(
    req: CreateDelegationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """设置审批委托"""
    delegation = ApprovalDelegation(
        brand_id=req.brand_id,
        delegator_id=req.delegator_id,
        delegator_name=req.delegator_name,
        delegate_id=req.delegate_id,
        delegate_name=req.delegate_name,
        start_date=req.start_date,
        end_date=req.end_date,
        template_codes=req.template_codes or [],
        is_active=True,
    )
    db.add(delegation)
    await db.commit()

    return {
        "success": True,
        "delegation_id": str(delegation.id),
    }


@router.get("/hr/approval/delegations")
async def list_delegations(
    delegator_id: Optional[str] = Query(None, description="委托人ID"),
    delegate_id: Optional[str] = Query(None, description="代理人ID"),
    brand_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查看审批委托"""
    conditions = [ApprovalDelegation.is_active.is_(True)]
    if delegator_id:
        conditions.append(ApprovalDelegation.delegator_id == delegator_id)
    if delegate_id:
        conditions.append(ApprovalDelegation.delegate_id == delegate_id)
    if brand_id:
        conditions.append(ApprovalDelegation.brand_id == brand_id)

    result = await db.execute(select(ApprovalDelegation).where(and_(*conditions)))
    delegations = result.scalars().all()

    return {
        "success": True,
        "total": len(delegations),
        "items": [
            {
                "id": str(d.id),
                "brand_id": d.brand_id,
                "delegator_id": d.delegator_id,
                "delegator_name": d.delegator_name,
                "delegate_id": d.delegate_id,
                "delegate_name": d.delegate_name,
                "start_date": d.start_date.isoformat(),
                "end_date": d.end_date.isoformat(),
                "template_codes": d.template_codes,
            }
            for d in delegations
        ],
    }
