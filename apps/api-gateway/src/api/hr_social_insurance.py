"""
HR Social Insurance API -- 社保公积金配置管理
"""

import uuid as uuid_mod
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.employee import Employee
from ..models.social_insurance import EmployeeSocialInsurance, SocialInsuranceConfig
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()


# ── 请求模型 ──────────────────────────────────────────


class SocialInsuranceConfigRequest(BaseModel):
    region_code: str
    region_name: str
    effective_year: int
    base_floor_fen: int
    base_ceiling_fen: int
    pension_employer_pct: float = 16.0
    pension_employee_pct: float = 8.0
    medical_employer_pct: float = 8.0
    medical_employee_pct: float = 2.0
    unemployment_employer_pct: float = 0.7
    unemployment_employee_pct: float = 0.3
    injury_employer_pct: float = 0.4
    maternity_employer_pct: float = 0.0
    housing_fund_employer_pct: float = 8.0
    housing_fund_employee_pct: float = 8.0
    remark: Optional[str] = None


class EmployeeSocialInsuranceRequest(BaseModel):
    store_id: str
    employee_id: str
    config_id: str
    effective_year: int
    personal_base_fen: int
    has_pension: bool = True
    has_medical: bool = True
    has_unemployment: bool = True
    has_injury: bool = True
    has_maternity: bool = True
    has_housing_fund: bool = True
    housing_fund_pct_override: Optional[float] = None
    remark: Optional[str] = None


# ── 区域配置 ──────────────────────────────────────────


@router.get("/hr/social-insurance/configs")
async def list_configs(
    effective_year: Optional[int] = Query(None),
    region_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取社保公积金区域配置列表"""
    query = select(SocialInsuranceConfig).where(SocialInsuranceConfig.is_active.is_(True))
    if effective_year:
        query = query.where(SocialInsuranceConfig.effective_year == effective_year)
    if region_code:
        query = query.where(SocialInsuranceConfig.region_code == region_code)

    result = await db.execute(query.order_by(SocialInsuranceConfig.region_code))
    configs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(c.id),
                "region_code": c.region_code,
                "region_name": c.region_name,
                "effective_year": c.effective_year,
                "base_floor_yuan": c.base_floor_fen / 100,
                "base_ceiling_yuan": c.base_ceiling_fen / 100,
                "pension_employer_pct": float(c.pension_employer_pct),
                "pension_employee_pct": float(c.pension_employee_pct),
                "medical_employer_pct": float(c.medical_employer_pct),
                "medical_employee_pct": float(c.medical_employee_pct),
                "unemployment_employer_pct": float(c.unemployment_employer_pct),
                "unemployment_employee_pct": float(c.unemployment_employee_pct),
                "injury_employer_pct": float(c.injury_employer_pct),
                "maternity_employer_pct": float(c.maternity_employer_pct),
                "housing_fund_employer_pct": float(c.housing_fund_employer_pct),
                "housing_fund_employee_pct": float(c.housing_fund_employee_pct),
                "total_employer_pct": float(
                    c.pension_employer_pct
                    + c.medical_employer_pct
                    + c.unemployment_employer_pct
                    + c.injury_employer_pct
                    + c.maternity_employer_pct
                    + c.housing_fund_employer_pct
                ),
                "total_employee_pct": float(
                    c.pension_employee_pct + c.medical_employee_pct + c.unemployment_employee_pct + c.housing_fund_employee_pct
                ),
            }
            for c in configs
        ],
    }


@router.post("/hr/social-insurance/configs")
async def create_config(
    body: SocialInsuranceConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建区域社保公积金配置"""
    config = SocialInsuranceConfig(
        id=uuid_mod.uuid4(),
        region_code=body.region_code,
        region_name=body.region_name,
        effective_year=body.effective_year,
        base_floor_fen=body.base_floor_fen,
        base_ceiling_fen=body.base_ceiling_fen,
        pension_employer_pct=body.pension_employer_pct,
        pension_employee_pct=body.pension_employee_pct,
        medical_employer_pct=body.medical_employer_pct,
        medical_employee_pct=body.medical_employee_pct,
        unemployment_employer_pct=body.unemployment_employer_pct,
        unemployment_employee_pct=body.unemployment_employee_pct,
        injury_employer_pct=body.injury_employer_pct,
        maternity_employer_pct=body.maternity_employer_pct,
        housing_fund_employer_pct=body.housing_fund_employer_pct,
        housing_fund_employee_pct=body.housing_fund_employee_pct,
        remark=body.remark,
    )
    db.add(config)
    await db.commit()
    return {"id": str(config.id), "message": f"{body.region_name} {body.effective_year}年社保配置创建成功"}


# ── 员工参保 ──────────────────────────────────────────


@router.get("/hr/social-insurance/employees")
async def list_employee_insurances(
    store_id: str = Query(...),
    effective_year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店员工参保列表"""
    query = (
        select(
            EmployeeSocialInsurance,
            Employee.name.label("employee_name"),
            Employee.position.label("employee_position"),
            SocialInsuranceConfig.region_name,
        )
        .join(Employee, EmployeeSocialInsurance.employee_id == Employee.id)
        .join(SocialInsuranceConfig, EmployeeSocialInsurance.config_id == SocialInsuranceConfig.id)
        .where(
            and_(
                EmployeeSocialInsurance.store_id == store_id,
                EmployeeSocialInsurance.is_active.is_(True),
            )
        )
    )
    if effective_year:
        query = query.where(EmployeeSocialInsurance.effective_year == effective_year)

    result = await db.execute(query)
    rows = result.all()

    return {
        "items": [
            {
                "id": str(r.EmployeeSocialInsurance.id),
                "employee_id": r.EmployeeSocialInsurance.employee_id,
                "employee_name": r.employee_name,
                "position": r.employee_position,
                "region_name": r.region_name,
                "effective_year": r.EmployeeSocialInsurance.effective_year,
                "personal_base_yuan": r.EmployeeSocialInsurance.personal_base_fen / 100,
                "has_pension": r.EmployeeSocialInsurance.has_pension,
                "has_medical": r.EmployeeSocialInsurance.has_medical,
                "has_unemployment": r.EmployeeSocialInsurance.has_unemployment,
                "has_housing_fund": r.EmployeeSocialInsurance.has_housing_fund,
                "housing_fund_pct_override": (
                    float(r.EmployeeSocialInsurance.housing_fund_pct_override)
                    if r.EmployeeSocialInsurance.housing_fund_pct_override
                    else None
                ),
            }
            for r in rows
        ],
    }


@router.post("/hr/social-insurance/employees")
async def set_employee_insurance(
    body: EmployeeSocialInsuranceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """设置员工参保方案"""
    # 验证员工存在
    emp = await db.execute(select(Employee.id).where(Employee.id == body.employee_id))
    if not emp.scalars().first():
        raise HTTPException(status_code=404, detail="员工不存在")

    # 停用旧方案
    old_result = await db.execute(
        select(EmployeeSocialInsurance).where(
            and_(
                EmployeeSocialInsurance.employee_id == body.employee_id,
                EmployeeSocialInsurance.effective_year == body.effective_year,
                EmployeeSocialInsurance.is_active.is_(True),
            )
        )
    )
    old = old_result.scalar_one_or_none()
    if old:
        old.is_active = False

    record = EmployeeSocialInsurance(
        id=uuid_mod.uuid4(),
        store_id=body.store_id,
        employee_id=body.employee_id,
        config_id=body.config_id,
        effective_year=body.effective_year,
        personal_base_fen=body.personal_base_fen,
        has_pension=body.has_pension,
        has_medical=body.has_medical,
        has_unemployment=body.has_unemployment,
        has_injury=body.has_injury,
        has_maternity=body.has_maternity,
        has_housing_fund=body.has_housing_fund,
        housing_fund_pct_override=body.housing_fund_pct_override,
        remark=body.remark,
    )
    db.add(record)
    await db.commit()
    return {"id": str(record.id), "message": "员工参保方案设置成功"}
