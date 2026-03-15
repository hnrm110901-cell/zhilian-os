"""
HR Lifecycle API -- 员工生命周期（试岗→入职→转正）+ 企微集成
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import date
from pydantic import BaseModel
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.employee_lifecycle_service import EmployeeLifecycleService
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()

lifecycle_svc = EmployeeLifecycleService()


# ── 请求模型 ──────────────────────────────────────────

class TrialRequest(BaseModel):
    store_id: str
    employee_id: str
    name: str
    position: str
    hire_date: str                          # YYYY-MM-DD
    phone: Optional[str] = None
    email: Optional[str] = None
    wechat_userid: Optional[str] = None     # 企业微信用户ID
    trial_days: int = 7
    remark: Optional[str] = None


class OnboardConfirmRequest(BaseModel):
    employee_id: str
    effective_date: Optional[str] = None    # 默认今天
    position: Optional[str] = None
    probation_months: int = 3
    probation_salary_pct: int = 80          # 试用期薪资比例
    base_salary_fen: int = 0
    position_allowance_fen: int = 0
    meal_allowance_fen: int = 0
    transport_allowance_fen: int = 0
    social_insurance_fen: int = 0
    housing_fund_fen: int = 0
    special_deduction_fen: int = 0
    contract_no: Optional[str] = None
    contract_end_date: Optional[str] = None
    remark: Optional[str] = None


class ProbationPassRequest(BaseModel):
    employee_id: str
    effective_date: Optional[str] = None
    base_salary_fen: Optional[int] = None   # 转正后薪资（不传则用合同约定）
    performance_coefficient: float = 1.0
    remark: Optional[str] = None


# ── 接口 ──────────────────────────────────────────────

@router.post("/hr/lifecycle/trial")
async def start_trial(
    body: TrialRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """试岗登记：创建试岗员工 + 企微通知"""
    try:
        result = await lifecycle_svc.start_trial(db, body.model_dump())
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hr/lifecycle/onboard")
async def confirm_onboard(
    body: OnboardConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """正式入职：试岗通过 → 签合同 → 建薪资方案"""
    try:
        result = await lifecycle_svc.confirm_onboard(db, body.model_dump())
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hr/lifecycle/probation-pass")
async def probation_pass(
    body: ProbationPassRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """转正：试用期结束 → 正式员工 → 薪资调整到100%"""
    try:
        result = await lifecycle_svc.confirm_probation_pass(db, body.model_dump())
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
