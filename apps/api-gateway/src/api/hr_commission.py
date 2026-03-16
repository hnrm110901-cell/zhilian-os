"""
HR Commission API -- 提成规则管理 + 提成记录
"""

import uuid as uuid_mod
from datetime import date
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.commission import CommissionCalcMethod, CommissionRecord, CommissionRule, CommissionType
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()


# ── 请求模型 ──────────────────────────────────────────


class CommissionRuleRequest(BaseModel):
    store_id: str
    name: str
    commission_type: str  # sales_amount|dish_count|service_fee|membership|custom
    calc_method: str  # fixed_per_unit|percentage|tiered
    applicable_positions: Optional[List[str]] = None
    applicable_employee_ids: Optional[List[str]] = None
    fixed_amount_fen: int = 0
    rate_pct: float = 0
    tiered_rules: Optional[list] = None
    target_dish_ids: Optional[List[str]] = None
    target_categories: Optional[List[str]] = None
    effective_date: str
    expire_date: Optional[str] = None
    remark: Optional[str] = None


class CommissionRecordRequest(BaseModel):
    store_id: str
    employee_id: str
    pay_month: str
    rule_id: str
    base_amount_fen: int = 0
    base_quantity: int = 0
    commission_fen: int
    calculation_detail: Optional[dict] = None
    remark: Optional[str] = None


# ── 提成规则 ──────────────────────────────────────────


@router.get("/hr/commission/rules")
async def list_commission_rules(
    store_id: str = Query(...),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店提成规则列表"""
    query = select(CommissionRule).where(CommissionRule.store_id == store_id)
    if active_only:
        query = query.where(CommissionRule.is_active.is_(True))
    result = await db.execute(query.order_by(CommissionRule.created_at.desc()))
    rules = result.scalars().all()

    return {
        "items": [
            {
                "id": str(r.id),
                "name": r.name,
                "commission_type": r.commission_type.value,
                "calc_method": r.calc_method.value,
                "applicable_positions": r.applicable_positions,
                "fixed_amount_yuan": (r.fixed_amount_fen or 0) / 100,
                "rate_pct": float(r.rate_pct or 0),
                "tiered_rules": r.tiered_rules,
                "is_active": r.is_active,
                "effective_date": str(r.effective_date),
                "expire_date": str(r.expire_date) if r.expire_date else None,
                "remark": r.remark,
            }
            for r in rules
        ],
    }


@router.post("/hr/commission/rules")
async def create_commission_rule(
    body: CommissionRuleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建提成规则"""
    rule = CommissionRule(
        id=uuid_mod.uuid4(),
        store_id=body.store_id,
        name=body.name,
        commission_type=body.commission_type,
        calc_method=body.calc_method,
        applicable_positions=body.applicable_positions,
        applicable_employee_ids=body.applicable_employee_ids,
        fixed_amount_fen=body.fixed_amount_fen,
        rate_pct=body.rate_pct,
        tiered_rules=body.tiered_rules,
        target_dish_ids=body.target_dish_ids,
        target_categories=body.target_categories,
        effective_date=date.fromisoformat(body.effective_date),
        expire_date=date.fromisoformat(body.expire_date) if body.expire_date else None,
        remark=body.remark,
    )
    db.add(rule)
    await db.commit()
    return {"id": str(rule.id), "message": "提成规则创建成功"}


@router.put("/hr/commission/rules/{rule_id}/toggle")
async def toggle_commission_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """启用/停用提成规则"""
    result = await db.execute(select(CommissionRule).where(CommissionRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.is_active = not rule.is_active
    await db.commit()
    return {"id": str(rule.id), "is_active": rule.is_active}


# ── 提成记录 ──────────────────────────────────────────


@router.get("/hr/commission/records")
async def list_commission_records(
    store_id: str = Query(...),
    pay_month: str = Query(...),
    employee_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店月度提成记录"""
    from ..models.employee import Employee

    query = (
        select(CommissionRecord, Employee.name.label("employee_name"))
        .join(Employee, CommissionRecord.employee_id == Employee.id)
        .where(
            and_(
                CommissionRecord.store_id == store_id,
                CommissionRecord.pay_month == pay_month,
            )
        )
    )
    if employee_id:
        query = query.where(CommissionRecord.employee_id == employee_id)

    result = await db.execute(query.order_by(CommissionRecord.commission_fen.desc()))
    rows = result.all()

    return {
        "items": [
            {
                "id": str(r.CommissionRecord.id),
                "employee_id": r.CommissionRecord.employee_id,
                "employee_name": r.employee_name,
                "pay_month": r.CommissionRecord.pay_month,
                "rule_id": str(r.CommissionRecord.rule_id),
                "base_amount_yuan": r.CommissionRecord.base_amount_fen / 100,
                "base_quantity": r.CommissionRecord.base_quantity,
                "commission_yuan": r.CommissionRecord.commission_fen / 100,
                "calculation_detail": r.CommissionRecord.calculation_detail,
            }
            for r in rows
        ],
    }


@router.post("/hr/commission/records")
async def create_commission_record(
    body: CommissionRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建提成记录"""
    record = CommissionRecord(
        id=uuid_mod.uuid4(),
        store_id=body.store_id,
        employee_id=body.employee_id,
        pay_month=body.pay_month,
        rule_id=body.rule_id,
        base_amount_fen=body.base_amount_fen,
        base_quantity=body.base_quantity,
        commission_fen=body.commission_fen,
        calculation_detail=body.calculation_detail,
        remark=body.remark,
    )
    db.add(record)
    await db.commit()
    return {"id": str(record.id), "commission_yuan": body.commission_fen / 100}
