"""
HR批量操作API — 批量入职/调动/调薪/工资条推送/算薪/续签合同
面向60+门店、4000+员工的连锁餐饮企业，支持大规模人事操作。

每个操作逐条执行、逐条提交，单条失败不影响其余（部分成功模式）。
"""
import uuid
from datetime import date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.employee import Employee
from ..models.employee_lifecycle import EmployeeChange, ChangeType
from ..models.employee_contract import EmployeeContract, ContractType, ContractStatus
from ..models.payroll import SalaryStructure, PayrollRecord, PayrollStatus
from ..services.payroll_service import PayrollService
from ..services.payslip_service import PayslipService

logger = structlog.get_logger()
router = APIRouter()

# 单批次上限
MAX_BATCH_SIZE = 200


# ── 请求模型 ──────────────────────────────────────────────

class BatchHireItem(BaseModel):
    """单个入职员工信息"""
    employee_id: str = Field(..., description="员工编号（如 EMP2026001）")
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    position: str
    store_id: str
    hire_date: str = Field(..., description="入职日期 YYYY-MM-DD")
    employment_type: str = Field(default="regular", description="用工类型: regular/part_time/intern")
    base_salary_fen: int = Field(default=0, description="基本工资（分）")
    wechat_userid: Optional[str] = None
    remark: Optional[str] = None


class BatchHireRequest(BaseModel):
    brand_id: str
    employees: List[BatchHireItem]


class BatchTransferItem(BaseModel):
    """单条调动记录"""
    employee_id: str
    from_store_id: str
    to_store_id: str
    new_position: Optional[str] = None
    effective_date: str = Field(..., description="生效日期 YYYY-MM-DD")
    remark: Optional[str] = None


class BatchTransferRequest(BaseModel):
    brand_id: str
    transfers: List[BatchTransferItem]


class BatchSalaryAdjustItem(BaseModel):
    """单条调薪记录"""
    employee_id: str
    store_id: str
    new_base_salary_fen: int = Field(..., description="新基本工资（分）")
    effective_month: str = Field(..., description="生效月份 YYYY-MM")
    reason: Optional[str] = None


class BatchSalaryAdjustRequest(BaseModel):
    brand_id: str
    adjustments: List[BatchSalaryAdjustItem]


class BatchPayslipPushRequest(BaseModel):
    store_ids: List[str] = Field(..., description="门店ID列表（支持跨店批量推送）")
    brand_id: Optional[str] = None
    pay_month: str = Field(..., description="薪资月份 YYYY-MM")
    channel: str = Field(default="im", description="推送渠道: im|sms|pdf")


class BatchPayrollCalculateRequest(BaseModel):
    store_ids: List[str] = Field(..., description="门店ID列表")
    pay_month: str = Field(..., description="薪资月份 YYYY-MM")


class BatchContractRenewItem(BaseModel):
    employee_id: str
    store_id: str
    new_end_date: str = Field(..., description="新合同到期日 YYYY-MM-DD")
    contract_type: str = Field(default="fixed_term", description="合同类型")
    remark: Optional[str] = None


class BatchContractRenewRequest(BaseModel):
    brand_id: str
    renewals: List[BatchContractRenewItem]


class FailedItem(BaseModel):
    index: int
    name: Optional[str] = None
    employee_id: Optional[str] = None
    error: str


class BatchResult(BaseModel):
    success_count: int = 0
    failed_count: int = 0
    failed: List[FailedItem] = []
    total: int = 0


# ── 批量入职 ──────────────────────────────────────────────

@router.post("/hr/batch/hire")
async def batch_hire(
    req: BatchHireRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    批量入职 — 一次创建多个员工记录。
    适用场景：Excel导入后的批量创建、新店开业批量招聘。
    单批次上限200人。

    每个员工独立事务：创建Employee + EmployeeChange(ONBOARD)记录。
    """
    employees_data = req.employees
    if len(employees_data) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=400, detail=f"单批次最多{MAX_BATCH_SIZE}人")

    results: Dict[str, Any] = {
        "success_count": 0,
        "failed_count": 0,
        "failed": [],
        "employee_ids": [],
        "total": len(employees_data),
    }

    for idx, emp_data in enumerate(employees_data):
        savepoint = await db.begin_nested()
        try:
            # 检查员工ID是否已存在
            exists = await db.execute(
                select(Employee.id).where(Employee.id == emp_data.employee_id)
            )
            if exists.scalars().first():
                raise ValueError(f"员工ID {emp_data.employee_id} 已存在")

            hire_date_parsed = date.fromisoformat(emp_data.hire_date)

            # 创建员工记录
            employee = Employee(
                id=emp_data.employee_id,
                store_id=emp_data.store_id,
                name=emp_data.name,
                phone=emp_data.phone,
                email=emp_data.email,
                position=emp_data.position,
                hire_date=hire_date_parsed,
                is_active=True,
                employment_status="regular",
                employment_type=emp_data.employment_type,
                wechat_userid=emp_data.wechat_userid,
            )
            db.add(employee)

            # 创建入职变动记录
            change = EmployeeChange(
                id=uuid.uuid4(),
                store_id=emp_data.store_id,
                employee_id=emp_data.employee_id,
                change_type=ChangeType.ONBOARD,
                effective_date=hire_date_parsed,
                to_position=emp_data.position,
                to_store_id=emp_data.store_id,
                to_salary_fen=emp_data.base_salary_fen,
                remark=emp_data.remark or f"批量入职 - {emp_data.position}",
            )
            db.add(change)

            # 如有基本工资则创建薪资方案
            if emp_data.base_salary_fen > 0:
                salary_structure = SalaryStructure(
                    store_id=emp_data.store_id,
                    employee_id=emp_data.employee_id,
                    salary_type="monthly",
                    base_salary_fen=emp_data.base_salary_fen,
                    effective_date=hire_date_parsed,
                )
                db.add(salary_structure)

            await savepoint.commit()
            results["success_count"] += 1
            results["employee_ids"].append(emp_data.employee_id)

        except Exception as e:
            await savepoint.rollback()
            results["failed_count"] += 1
            results["failed"].append({
                "index": idx,
                "name": emp_data.name,
                "employee_id": emp_data.employee_id,
                "error": str(e),
            })
            logger.warning(
                "batch_hire_item_failed",
                index=idx,
                employee_id=emp_data.employee_id,
                error=str(e),
            )

    await db.commit()

    logger.info(
        "batch_hire_completed",
        total=results["total"],
        success=results["success_count"],
        failed=results["failed_count"],
        operator=current_user.username,
    )
    return results


# ── 批量调动 ──────────────────────────────────────────────

@router.post("/hr/batch/transfer")
async def batch_transfer(
    req: BatchTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    批量调动 — 门店间员工批量调配。
    适用场景：新店开业从老店调人、淡旺季跨店借调。

    每条调动：更新Employee的store_id/position + 创建EmployeeChange(TRANSFER)。
    """
    transfers = req.transfers
    if len(transfers) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=400, detail=f"单批次最多{MAX_BATCH_SIZE}条")

    results: Dict[str, Any] = {
        "success_count": 0,
        "failed_count": 0,
        "failed": [],
        "total": len(transfers),
    }

    for idx, t in enumerate(transfers):
        savepoint = await db.begin_nested()
        try:
            # 查找员工
            emp_result = await db.execute(
                select(Employee).where(
                    and_(
                        Employee.id == t.employee_id,
                        Employee.is_active.is_(True),
                    )
                )
            )
            employee = emp_result.scalar_one_or_none()
            if not employee:
                raise ValueError(f"员工 {t.employee_id} 不存在或已离职")

            effective = date.fromisoformat(t.effective_date)
            old_position = employee.position
            old_store = employee.store_id

            # 更新员工信息
            employee.store_id = t.to_store_id
            if t.new_position:
                employee.position = t.new_position

            # 创建调动记录
            change = EmployeeChange(
                id=uuid.uuid4(),
                store_id=t.to_store_id,
                employee_id=t.employee_id,
                change_type=ChangeType.TRANSFER,
                effective_date=effective,
                from_position=old_position,
                to_position=t.new_position or old_position,
                from_store_id=old_store,
                to_store_id=t.to_store_id,
                remark=t.remark or f"批量调动: {old_store} → {t.to_store_id}",
            )
            db.add(change)

            await savepoint.commit()
            results["success_count"] += 1

        except Exception as e:
            await savepoint.rollback()
            results["failed_count"] += 1
            results["failed"].append({
                "index": idx,
                "employee_id": t.employee_id,
                "error": str(e),
            })
            logger.warning(
                "batch_transfer_item_failed",
                index=idx,
                employee_id=t.employee_id,
                error=str(e),
            )

    await db.commit()

    logger.info(
        "batch_transfer_completed",
        total=results["total"],
        success=results["success_count"],
        failed=results["failed_count"],
        operator=current_user.username,
    )
    return results


# ── 批量调薪 ──────────────────────────────────────────────

@router.post("/hr/batch/salary-adjust")
async def batch_salary_adjust(
    req: BatchSalaryAdjustRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    批量调薪 — 全店涨薪、岗位调薪、最低工资标准调整。
    适用场景：年度调薪、最低工资上调后批量调整。

    每条调薪：停用旧SalaryStructure → 创建新方案 → 记录EmployeeChange(SALARY_ADJUST)。
    """
    adjustments = req.adjustments
    if len(adjustments) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=400, detail=f"单批次最多{MAX_BATCH_SIZE}条")

    results: Dict[str, Any] = {
        "success_count": 0,
        "failed_count": 0,
        "failed": [],
        "total": len(adjustments),
        "total_increase_yuan": 0,
    }

    for idx, adj in enumerate(adjustments):
        savepoint = await db.begin_nested()
        try:
            # 查找员工
            emp_result = await db.execute(
                select(Employee).where(
                    and_(
                        Employee.id == adj.employee_id,
                        Employee.is_active.is_(True),
                    )
                )
            )
            employee = emp_result.scalar_one_or_none()
            if not employee:
                raise ValueError(f"员工 {adj.employee_id} 不存在或已离职")

            # 获取当前薪资方案
            old_structure_result = await db.execute(
                select(SalaryStructure).where(
                    and_(
                        SalaryStructure.employee_id == adj.employee_id,
                        SalaryStructure.is_active.is_(True),
                    )
                )
            )
            old_structure = old_structure_result.scalar_one_or_none()
            old_salary_fen = old_structure.base_salary_fen if old_structure else 0

            # 解析生效月份为日期（取月份第一天）
            effective_parts = adj.effective_month.split("-")
            effective_date = date(int(effective_parts[0]), int(effective_parts[1]), 1)

            # 停用旧薪资方案
            if old_structure:
                old_structure.is_active = False
                old_structure.expire_date = effective_date

            # 创建新薪资方案（继承旧方案的津贴等字段）
            new_structure = SalaryStructure(
                store_id=adj.store_id,
                employee_id=adj.employee_id,
                salary_type=old_structure.salary_type if old_structure else "monthly",
                base_salary_fen=adj.new_base_salary_fen,
                position_allowance_fen=old_structure.position_allowance_fen if old_structure else 0,
                meal_allowance_fen=old_structure.meal_allowance_fen if old_structure else 0,
                transport_allowance_fen=old_structure.transport_allowance_fen if old_structure else 0,
                hourly_rate_fen=old_structure.hourly_rate_fen if old_structure else None,
                performance_coefficient=old_structure.performance_coefficient if old_structure else 1.0,
                social_insurance_fen=old_structure.social_insurance_fen if old_structure else 0,
                housing_fund_fen=old_structure.housing_fund_fen if old_structure else 0,
                special_deduction_fen=old_structure.special_deduction_fen if old_structure else 0,
                effective_date=effective_date,
                remark=adj.reason or "批量调薪",
            )
            db.add(new_structure)

            # 创建薪资调整变动记录
            change = EmployeeChange(
                id=uuid.uuid4(),
                store_id=adj.store_id,
                employee_id=adj.employee_id,
                change_type=ChangeType.SALARY_ADJUST,
                effective_date=effective_date,
                from_salary_fen=old_salary_fen,
                to_salary_fen=adj.new_base_salary_fen,
                remark=adj.reason or f"批量调薪: {old_salary_fen / 100:.2f}元 → {adj.new_base_salary_fen / 100:.2f}元",
            )
            db.add(change)

            await savepoint.commit()
            results["success_count"] += 1
            results["total_increase_yuan"] += (adj.new_base_salary_fen - old_salary_fen) / 100

        except Exception as e:
            await savepoint.rollback()
            results["failed_count"] += 1
            results["failed"].append({
                "index": idx,
                "employee_id": adj.employee_id,
                "error": str(e),
            })
            logger.warning(
                "batch_salary_adjust_item_failed",
                index=idx,
                employee_id=adj.employee_id,
                error=str(e),
            )

    await db.commit()

    # 四舍五入总增量
    results["total_increase_yuan"] = round(results["total_increase_yuan"], 2)

    logger.info(
        "batch_salary_adjust_completed",
        total=results["total"],
        success=results["success_count"],
        failed=results["failed_count"],
        total_increase_yuan=results["total_increase_yuan"],
        operator=current_user.username,
    )
    return results


# ── 批量推送工资条 ────────────────────────────────────────

@router.post("/hr/batch/payslip-push")
async def batch_payslip_push(
    req: BatchPayslipPushRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    批量推送工资条 — 支持多门店一键推送。
    适用场景：总部统一推送全部门店的工资条。

    逐店调用PayslipService.batch_push_payslips。
    """
    if len(req.store_ids) > 100:
        raise HTTPException(status_code=400, detail="单批次最多100家门店")

    results: Dict[str, Any] = {
        "total_stores": len(req.store_ids),
        "success_stores": 0,
        "failed_stores": 0,
        "total_pushed": 0,
        "total_failed_push": 0,
        "store_details": [],
    }

    for store_id in req.store_ids:
        try:
            svc = PayslipService(store_id=store_id, brand_id=req.brand_id or "")
            push_result = await svc.batch_push_payslips(db, req.pay_month)

            pushed = push_result.get("success_count", push_result.get("pushed_count", 0))
            failed = push_result.get("failed_count", 0)

            results["success_stores"] += 1
            results["total_pushed"] += pushed
            results["total_failed_push"] += failed
            results["store_details"].append({
                "store_id": store_id,
                "status": "ok",
                "pushed": pushed,
                "failed": failed,
            })
        except Exception as e:
            results["failed_stores"] += 1
            results["store_details"].append({
                "store_id": store_id,
                "status": "error",
                "error": str(e),
            })
            logger.warning(
                "batch_payslip_push_store_failed",
                store_id=store_id,
                error=str(e),
            )

    logger.info(
        "batch_payslip_push_completed",
        total_stores=results["total_stores"],
        success_stores=results["success_stores"],
        total_pushed=results["total_pushed"],
        channel=req.channel,
        operator=current_user.username,
    )
    return results


# ── 跨门店批量算薪 ────────────────────────────────────────

@router.post("/hr/batch/payroll-calculate")
async def batch_payroll_calculate(
    req: BatchPayrollCalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    跨门店批量算薪 — 总部一键为多家门店计算全月工资。
    适用场景：每月薪酬计算日，总部HR一次性触发所有门店算薪。

    逐店调用PayrollService.batch_calculate。
    """
    if len(req.store_ids) > 100:
        raise HTTPException(status_code=400, detail="单批次最多100家门店")

    results: Dict[str, Any] = {
        "pay_month": req.pay_month,
        "total_stores": len(req.store_ids),
        "success_stores": 0,
        "failed_stores": 0,
        "total_employees": 0,
        "total_success": 0,
        "total_failed": 0,
        "total_net_salary_yuan": 0,
        "store_details": [],
    }

    for store_id in req.store_ids:
        try:
            svc = PayrollService(store_id=store_id)
            calc_result = await svc.batch_calculate(db, store_id, req.pay_month)

            results["success_stores"] += 1
            results["total_employees"] += calc_result.get("total_employees", 0)
            results["total_success"] += calc_result.get("success", 0)
            results["total_failed"] += len(calc_result.get("failed", []))
            results["total_net_salary_yuan"] += calc_result.get("total_net_salary_yuan", 0)
            results["store_details"].append({
                "store_id": store_id,
                "status": "ok",
                "employees": calc_result.get("total_employees", 0),
                "success": calc_result.get("success", 0),
                "failed": calc_result.get("failed", []),
                "net_salary_yuan": calc_result.get("total_net_salary_yuan", 0),
            })
        except Exception as e:
            results["failed_stores"] += 1
            results["store_details"].append({
                "store_id": store_id,
                "status": "error",
                "error": str(e),
            })
            logger.warning(
                "batch_payroll_calc_store_failed",
                store_id=store_id,
                error=str(e),
            )

    await db.commit()
    results["total_net_salary_yuan"] = round(results["total_net_salary_yuan"], 2)

    logger.info(
        "batch_payroll_calculate_completed",
        pay_month=req.pay_month,
        total_stores=results["total_stores"],
        success_stores=results["success_stores"],
        total_success=results["total_success"],
        total_net_salary_yuan=results["total_net_salary_yuan"],
        operator=current_user.username,
    )
    return results


# ── 批量续签合同 ──────────────────────────────────────────

@router.post("/hr/batch/contract-renew")
async def batch_contract_renew(
    req: BatchContractRenewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    批量续签合同 — 批量延长员工合同期限。
    适用场景：年底合同集中到期时批量续签。

    查找员工当前有效合同，标记为RENEWED，创建新合同。
    """
    renewals = req.renewals
    if len(renewals) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=400, detail=f"单批次最多{MAX_BATCH_SIZE}条")

    results: Dict[str, Any] = {
        "success_count": 0,
        "failed_count": 0,
        "failed": [],
        "total": len(renewals),
        "new_contract_ids": [],
    }

    for idx, r in enumerate(renewals):
        savepoint = await db.begin_nested()
        try:
            # 查找员工当前生效的合同
            contract_result = await db.execute(
                select(EmployeeContract).where(
                    and_(
                        EmployeeContract.employee_id == r.employee_id,
                        EmployeeContract.status.in_([
                            ContractStatus.ACTIVE,
                            ContractStatus.EXPIRING,
                        ]),
                    )
                ).order_by(EmployeeContract.created_at.desc()).limit(1)
            )
            old_contract = contract_result.scalar_one_or_none()

            new_end = date.fromisoformat(r.new_end_date)

            # 将旧合同标记为已续签
            if old_contract:
                old_contract.status = ContractStatus.RENEWED

            # 解析合同类型
            try:
                ct = ContractType(r.contract_type)
            except ValueError:
                ct = ContractType.FIXED_TERM

            # 创建新合同
            new_contract = EmployeeContract(
                id=uuid.uuid4(),
                store_id=r.store_id,
                employee_id=r.employee_id,
                contract_type=ct,
                status=ContractStatus.ACTIVE,
                start_date=date.today(),
                end_date=new_end,
                remark=r.remark or "批量续签",
            )
            db.add(new_contract)

            await savepoint.commit()
            results["success_count"] += 1
            results["new_contract_ids"].append(str(new_contract.id))

        except Exception as e:
            await savepoint.rollback()
            results["failed_count"] += 1
            results["failed"].append({
                "index": idx,
                "employee_id": r.employee_id,
                "error": str(e),
            })
            logger.warning(
                "batch_contract_renew_item_failed",
                index=idx,
                employee_id=r.employee_id,
                error=str(e),
            )

    await db.commit()

    logger.info(
        "batch_contract_renew_completed",
        total=results["total"],
        success=results["success_count"],
        failed=results["failed_count"],
        operator=current_user.username,
    )
    return results


# ── 批量任务进度查询 ──────────────────────────────────────

# 内存存储（生产环境应使用Redis）
_batch_job_progress: Dict[str, Dict[str, Any]] = {}


@router.get("/hr/batch/progress/{job_id}")
async def get_batch_progress(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    查询批量操作进度 — 用于大批量异步任务的进度追踪。
    当前实现为同步执行，此端点预留给未来Celery异步任务集成。
    """
    progress = _batch_job_progress.get(job_id)
    if not progress:
        raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")
    return progress
