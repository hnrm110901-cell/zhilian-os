"""
员工自助查询API — 员工H5端使用
员工可查看自己的工资条、考勤、请假、培训、合同等信息
"""

from datetime import date, datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db

logger = structlog.get_logger()
router = APIRouter(prefix="/hr/self-service", tags=["hr_employee_self_service"])


# ── 请求模型 ──────────────────────────────────────────


class LeaveRequestBody(BaseModel):
    employee_id: str
    store_id: str
    leave_category: str  # annual/sick/personal/compensatory/other
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    reason: str
    brand_id: Optional[str] = None


class PayslipConfirmBody(BaseModel):
    store_id: str


# ── 工具函数 ──────────────────────────────────────────


def _mask_phone(phone: Optional[str]) -> str:
    """手机号脱敏：138****1234"""
    if not phone or len(phone) < 7:
        return phone or ""
    return phone[:3] + "****" + phone[-4:]


def _mask_id_card(id_card: Optional[str]) -> str:
    """身份证脱敏：****1234"""
    if not id_card or len(id_card) < 4:
        return id_card or ""
    return "****" + id_card[-4:]


# ── API 端点 ──────────────────────────────────────────


@router.get("/my-profile")
async def get_my_profile(
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的基本信息（脱敏）"""
    result = await db.execute(
        text("""
            SELECT id, name, gender, phone, email, id_card_number,
                   position, employment_type, hire_date, store_id,
                   department, status
            FROM employees WHERE id = :eid AND status != 'deleted'
        """),
        {"eid": employee_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="员工不存在")

    profile = dict(row)
    profile["phone"] = _mask_phone(profile.get("phone"))
    profile["id_card_number"] = _mask_id_card(profile.get("id_card_number"))
    return {"code": 0, "data": profile}


@router.get("/my-payslips")
async def get_my_payslips(
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """工资条历史列表"""
    result = await db.execute(
        text("""
            SELECT pay_month, net_salary_fen, push_status, confirmed, confirmed_at
            FROM hr_payslips
            WHERE employee_id = :eid
            ORDER BY pay_month DESC
            LIMIT 12
        """),
        {"eid": employee_id},
    )
    items = []
    for row in result.mappings().all():
        r = dict(row)
        r["net_salary_yuan"] = round((r.get("net_salary_fen") or 0) / 100, 2)
        items.append(r)
    return {"code": 0, "data": items}


@router.get("/my-payslip/{pay_month}")
async def get_my_payslip(
    pay_month: str,
    employee_id: str = Query(..., description="员工ID"),
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的工资条（某月明细）"""
    result = await db.execute(
        text("""
            SELECT item_name, item_category, amount_fen, formula
            FROM hr_salary_items
            WHERE employee_id = :eid AND pay_month = :pm AND store_id = :sid
            ORDER BY item_category, item_name
        """),
        {"eid": employee_id, "pm": pay_month, "sid": store_id},
    )
    items = []
    total_income = 0
    total_deduction = 0
    for row in result.mappings().all():
        r = dict(row)
        amount_fen = r.get("amount_fen") or 0
        r["amount_yuan"] = round(amount_fen / 100, 2)
        if r.get("item_category") in ("income", "base", "allowance", "bonus", "commission"):
            total_income += amount_fen
        else:
            total_deduction += amount_fen
        items.append(r)

    # 查询确认状态
    confirm_result = await db.execute(
        text("SELECT confirmed, confirmed_at FROM hr_payslips WHERE employee_id = :eid AND pay_month = :pm"),
        {"eid": employee_id, "pm": pay_month},
    )
    confirm_row = confirm_result.mappings().first()

    return {
        "code": 0,
        "data": {
            "pay_month": pay_month,
            "items": items,
            "total_income_yuan": round(total_income / 100, 2),
            "total_deduction_yuan": round(total_deduction / 100, 2),
            "net_salary_yuan": round((total_income - total_deduction) / 100, 2),
            "confirmed": confirm_row["confirmed"] if confirm_row else False,
            "confirmed_at": str(confirm_row["confirmed_at"]) if confirm_row and confirm_row["confirmed_at"] else None,
        },
    }


@router.post("/my-payslip/{pay_month}/confirm")
async def confirm_my_payslip(
    pay_month: str,
    body: PayslipConfirmBody,
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """确认工资条"""
    await db.execute(
        text("""
            UPDATE hr_payslips
            SET confirmed = true, confirmed_at = NOW()
            WHERE employee_id = :eid AND pay_month = :pm
        """),
        {"eid": employee_id, "pm": pay_month},
    )
    await db.commit()
    return {"code": 0, "data": {"success": True}}


@router.get("/my-attendance/{month}")
async def get_my_attendance(
    month: str,
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的月考勤记录"""
    result = await db.execute(
        text("""
            SELECT work_date, status, clock_in, clock_out,
                   late_minutes, early_leave_minutes, overtime_minutes
            FROM hr_attendance_records
            WHERE employee_id = :eid
              AND to_char(work_date, 'YYYY-MM') = :month
            ORDER BY work_date
        """),
        {"eid": employee_id, "month": month},
    )
    records = [dict(r) for r in result.mappings().all()]

    # 统计
    normal = sum(1 for r in records if r.get("status") == "normal")
    late = sum(1 for r in records if r.get("status") == "late")
    absent = sum(1 for r in records if r.get("status") == "absent")
    leave = sum(1 for r in records if r.get("status") == "leave")

    # 序列化日期时间
    for r in records:
        for k in ("work_date", "clock_in", "clock_out"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()

    return {
        "code": 0,
        "data": {
            "month": month,
            "records": records,
            "stats": {
                "total_days": len(records),
                "normal": normal,
                "late": late,
                "absent": absent,
                "leave": leave,
            },
        },
    }


@router.get("/my-leaves")
async def get_my_leaves(
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的请假记录"""
    result = await db.execute(
        text("""
            SELECT id, leave_category, start_date, end_date, leave_days,
                   reason, status, created_at
            FROM hr_leave_requests
            WHERE employee_id = :eid
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"eid": employee_id},
    )
    items = []
    for row in result.mappings().all():
        r = dict(row)
        for k in ("start_date", "end_date", "created_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
        items.append(r)
    return {"code": 0, "data": items}


@router.post("/leave-request")
async def submit_leave_request(
    body: LeaveRequestBody,
    db: AsyncSession = Depends(get_db),
):
    """提交请假申请"""
    # 计算天数
    try:
        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
        leave_days = (end - start).days + 1
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，应为YYYY-MM-DD")

    if leave_days <= 0:
        raise HTTPException(status_code=400, detail="结束日期必须大于等于开始日期")

    result = await db.execute(
        text("""
            INSERT INTO hr_leave_requests
                (employee_id, store_id, leave_category, start_date, end_date,
                 leave_days, reason, status, created_at)
            VALUES
                (:eid, :sid, :cat, :sd, :ed, :days, :reason, 'pending', NOW())
            RETURNING id
        """),
        {
            "eid": body.employee_id,
            "sid": body.store_id,
            "cat": body.leave_category,
            "sd": body.start_date,
            "ed": body.end_date,
            "days": leave_days,
            "reason": body.reason,
        },
    )
    row = result.fetchone()
    await db.commit()
    return {"code": 0, "data": {"success": True, "request_id": str(row[0]) if row else ""}}


@router.get("/my-leave-balance")
async def get_my_leave_balance(
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的假期余额"""
    result = await db.execute(
        text("""
            SELECT leave_category, total_days, used_days, remaining_days
            FROM hr_leave_balances
            WHERE employee_id = :eid AND year = EXTRACT(YEAR FROM CURRENT_DATE)::int
        """),
        {"eid": employee_id},
    )
    items = [dict(r) for r in result.mappings().all()]
    return {"code": 0, "data": items}


@router.get("/my-courses")
async def get_my_courses(
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的培训课程"""
    result = await db.execute(
        text("""
            SELECT e.id AS enrollment_id, e.course_id, c.title AS course_title,
                   c.category, c.course_type, e.status, e.progress_pct,
                   e.score, e.certificate_no, e.enrolled_at, e.completed_at,
                   c.credits, c.is_mandatory, c.duration_minutes
            FROM hr_training_enrollments e
            JOIN hr_training_courses c ON c.id = e.course_id
            WHERE e.employee_id = :eid
            ORDER BY e.enrolled_at DESC
        """),
        {"eid": employee_id},
    )
    items = []
    for row in result.mappings().all():
        r = dict(row)
        for k in ("enrolled_at", "completed_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
        items.append(r)
    return {"code": 0, "data": items}


@router.get("/my-contract")
async def get_my_contract(
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的合同信息"""
    result = await db.execute(
        text("""
            SELECT id, contract_no, contract_type, start_date, end_date,
                   renewal_count, status
            FROM hr_contracts
            WHERE employee_id = :eid
            ORDER BY start_date DESC
            LIMIT 1
        """),
        {"eid": employee_id},
    )
    row = result.mappings().first()
    if not row:
        return {"code": 0, "data": None}
    r = dict(row)
    for k in ("start_date", "end_date"):
        if r.get(k) and hasattr(r[k], "isoformat"):
            r[k] = r[k].isoformat()
    return {"code": 0, "data": r}


@router.get("/my-approvals")
async def get_my_approvals(
    employee_id: str = Query(..., description="员工ID"),
    db: AsyncSession = Depends(get_db),
):
    """我的审批（我发起的）"""
    result = await db.execute(
        text("""
            SELECT id, template_code, business_type, status,
                   summary, created_at
            FROM hr_approval_instances
            WHERE applicant_id = :eid
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"eid": employee_id},
    )
    items = []
    for row in result.mappings().all():
        r = dict(row)
        if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
        items.append(r)
    return {"code": 0, "data": items}
