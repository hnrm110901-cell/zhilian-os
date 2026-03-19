"""
Payroll API — 薪酬管理接口
"""

from datetime import date
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.payroll_service import PayrollService

logger = structlog.get_logger()
router = APIRouter()


# ── Request / Response ─────────────────────────────────────


class SalaryStructureRequest(BaseModel):
    employee_id: str
    store_id: str
    salary_type: str = "monthly"
    base_salary_fen: int = 0
    position_allowance_fen: int = 0
    meal_allowance_fen: int = 0
    transport_allowance_fen: int = 0
    hourly_rate_fen: Optional[int] = None
    performance_coefficient: float = 1.0
    social_insurance_fen: int = 0
    housing_fund_fen: int = 0
    special_deduction_fen: int = 0
    effective_date: Optional[date] = None
    approved_by: Optional[str] = None
    remark: Optional[str] = None


class CalculateRequest(BaseModel):
    store_id: str
    pay_month: str  # YYYY-MM


class ConfirmRequest(BaseModel):
    payroll_id: str
    confirmed_by: str


class MarkPaidRequest(BaseModel):
    store_id: str
    pay_month: str


# ── 薪资方案 ───────────────────────────────────────────────


@router.get("/payroll/salary-structure/{employee_id}")
async def get_salary_structure(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取员工当前薪资方案"""
    svc = PayrollService(store_id=current_user.store_id)
    structure = await svc.get_salary_structure(db, employee_id)
    if not structure:
        raise HTTPException(status_code=404, detail="无生效薪资方案")
    return {
        "id": str(structure.id),
        "employee_id": structure.employee_id,
        "salary_type": structure.salary_type.value if structure.salary_type else "monthly",
        "base_salary_yuan": structure.base_salary_fen / 100,
        "position_allowance_yuan": structure.position_allowance_fen / 100,
        "meal_allowance_yuan": structure.meal_allowance_fen / 100,
        "transport_allowance_yuan": structure.transport_allowance_fen / 100,
        "hourly_rate_yuan": (structure.hourly_rate_fen or 0) / 100,
        "performance_coefficient": float(structure.performance_coefficient or 1.0),
        "social_insurance_yuan": structure.social_insurance_fen / 100,
        "housing_fund_yuan": structure.housing_fund_fen / 100,
        "special_deduction_yuan": structure.special_deduction_fen / 100,
        "effective_date": str(structure.effective_date),
        "is_active": structure.is_active,
    }


@router.post("/payroll/salary-structure")
async def upsert_salary_structure(
    req: SalaryStructureRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建/更新薪资方案"""
    svc = PayrollService(store_id=req.store_id)
    data = req.model_dump()
    if data.get("effective_date") is None:
        data["effective_date"] = date.today()
    structure = await svc.upsert_salary_structure(db, data)
    await db.commit()
    return {"id": str(structure.id), "message": "薪资方案已保存"}


# ── 算薪 ───────────────────────────────────────────────────


@router.post("/payroll/calculate/{employee_id}")
async def calculate_single(
    employee_id: str,
    pay_month: str = Query(..., description="薪资月份 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """为单个员工算薪"""
    svc = PayrollService(store_id=current_user.store_id)
    try:
        record = await svc.calculate_payroll(db, employee_id, pay_month)
        await db.commit()
        return {
            "id": str(record.id),
            "employee_id": record.employee_id,
            "net_salary_yuan": record.net_salary_fen / 100,
            "status": record.status.value,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/payroll/batch-calculate")
async def batch_calculate(
    req: CalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量算薪（全店）"""
    svc = PayrollService(store_id=req.store_id)
    result = await svc.batch_calculate(db, req.store_id, req.pay_month)
    await db.commit()
    return result


# ── 工资表查询 ─────────────────────────────────────────────


@router.get("/payroll/list")
async def get_payroll_list(
    store_id: str = Query(...),
    pay_month: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取月度工资表"""
    svc = PayrollService(store_id=store_id)
    items = await svc.get_payroll_list(db, store_id, pay_month)
    return {"items": items, "total": len(items)}


@router.get("/payroll/summary")
async def get_payroll_summary(
    store_id: str = Query(...),
    pay_month: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取月度薪酬汇总"""
    svc = PayrollService(store_id=store_id)
    return await svc.get_payroll_summary(db, store_id, pay_month)


# ── 确认 & 发放 ───────────────────────────────────────────


@router.post("/payroll/confirm")
async def confirm_payroll(
    req: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """确认工资单"""
    svc = PayrollService(store_id=current_user.store_id)
    try:
        record = await svc.confirm_payroll(db, req.payroll_id, req.confirmed_by)
        await db.commit()
        return {"id": str(record.id), "status": record.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/payroll/mark-paid")
async def mark_paid(
    req: MarkPaidRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """标记整月已发放"""
    svc = PayrollService(store_id=req.store_id)
    count = await svc.mark_paid(db, req.store_id, req.pay_month)
    await db.commit()
    return {"paid_count": count, "message": f"已标记 {count} 条工资单为已发放"}


# ── 新引擎薪酬计算 ─────────────────────────────────────────


@router.get("/payroll/detail/{employee_id}/{pay_month}")
async def get_payroll_detail(
    employee_id: str,
    pay_month: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取员工薪酬明细（106项）"""
    from ..models.salary_item import SalaryItemRecord

    result = await db.execute(
        select(SalaryItemRecord)
        .where(
            and_(
                SalaryItemRecord.employee_id == employee_id,
                SalaryItemRecord.pay_month == pay_month,
            )
        )
        .order_by(SalaryItemRecord.item_category)
    )
    records = result.scalars().all()
    items = []
    for r in records:
        items.append(
            {
                "item_name": r.item_name,
                "item_category": r.item_category,
                "amount_yuan": r.amount_fen / 100,
                "amount_fen": r.amount_fen,
                "formula": r.formula_snapshot,
            }
        )

    income = sum(r.amount_fen for r in records if r.item_category in ("income", "subsidy"))
    deduction = sum(r.amount_fen for r in records if r.item_category in ("deduction", "tax"))
    return {
        "employee_id": employee_id,
        "pay_month": pay_month,
        "items": items,
        "total_income_yuan": income / 100,
        "total_deduction_yuan": deduction / 100,
        "net_salary_yuan": (income - deduction) / 100,
    }


@router.post("/payroll/formula-calculate/{employee_id}")
async def formula_calculate(
    employee_id: str,
    pay_month: str = Query(..., description="YYYY-MM"),
    store_id: str = Query(...),
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """使用公式引擎计算员工薪酬"""
    from ..services.salary_formula_engine import SalaryFormulaEngine

    engine = SalaryFormulaEngine(brand_id=brand_id)
    try:
        result = await engine.calculate_employee_salary(db, employee_id, pay_month, store_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/payroll/simulate")
async def simulate_payroll(
    employee_id: str = Query(...),
    pay_month: str = Query(..., description="YYYY-MM"),
    store_id: str = Query(...),
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """模拟薪酬计算（不写DB，调试用）"""
    from ..services.salary_formula_engine import SalaryFormulaEngine

    engine = SalaryFormulaEngine(brand_id=brand_id)
    try:
        return await engine.simulate_calculation(db, employee_id, pay_month, store_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 工资套导入 ──


@router.post("/payroll/salary-items/import")
async def import_salary_items(
    file: UploadFile = File(...),
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """导入工资套（薪酬项定义）"""
    from ..services.salary_formula_engine import SalaryFormulaEngine

    content = await file.read()
    engine = SalaryFormulaEngine(brand_id=brand_id)
    result = await engine.import_salary_items(db, content, brand_id, store_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    await db.commit()
    return result


# ── 公式校验 & 测试 ──


class FormulaValidateRequest(BaseModel):
    formula: str
    available_variables: Optional[List[str]] = None


class FormulaTestRequest(BaseModel):
    formula: str
    test_variables: Dict[str, float]  # {"基本工资": 500000, "司龄月数": 36}


@router.post("/payroll/formula/validate")
async def validate_formula(
    req: FormulaValidateRequest,
    brand_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
):
    """校验公式语法和变量引用"""
    from ..services.salary_formula_engine import SalaryFormulaEngine

    engine = SalaryFormulaEngine(brand_id=brand_id)
    return engine.validate_formula(req.formula, req.available_variables)


@router.post("/payroll/formula/test")
async def test_formula(
    req: FormulaTestRequest,
    brand_id: str = Query(...),
    current_user: User = Depends(get_current_active_user),
):
    """用模拟数据测试公式（不写DB）"""
    from ..services.salary_formula_engine import SalaryFormulaEngine

    engine = SalaryFormulaEngine(brand_id=brand_id)
    return engine.test_formula(req.formula, req.test_variables)


# ── 城市最低工资 ──


@router.get("/payroll/city-wage-configs")
async def list_city_wage_configs(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询城市最低工资配置"""
    from ..models.city_wage_config import CityWageConfig

    query = select(CityWageConfig)
    if year:
        query = query.where(CityWageConfig.year == year)
    result = await db.execute(query.order_by(CityWageConfig.city))
    configs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(c.id),
                "city": c.city,
                "province": c.province,
                "year": c.year,
                "min_monthly_wage_yuan": c.min_monthly_wage_fen / 100,
                "min_hourly_wage_yuan": c.min_hourly_wage_fen / 100,
            }
            for c in configs
        ]
    }


@router.post("/payroll/city-wage-configs")
async def create_city_wage_config(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建/更新城市最低工资"""
    from ..models.city_wage_config import CityWageConfig

    config = CityWageConfig(
        city=data["city"],
        province=data.get("province"),
        year=data["year"],
        min_monthly_wage_fen=data.get("min_monthly_wage_fen", 0),
        min_hourly_wage_fen=data.get("min_hourly_wage_fen", 0),
        social_insurance_base_floor_fen=data.get("social_insurance_base_floor_fen", 0),
        social_insurance_base_ceil_fen=data.get("social_insurance_base_ceil_fen", 0),
        housing_fund_base_floor_fen=data.get("housing_fund_base_floor_fen", 0),
        housing_fund_base_ceil_fen=data.get("housing_fund_base_ceil_fen", 0),
    )
    db.add(config)
    await db.commit()
    return {"id": str(config.id), "message": "城市工资配置已创建"}
