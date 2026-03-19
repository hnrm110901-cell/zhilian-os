"""
HR Attendance Report API — 考勤报表 + 排班关联考勤 + 班次模板 + 考勤规则 + 打卡
"""

import uuid
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.attendance import AttendanceLog, AttendanceRule, ShiftTemplate
from ..models.user import User
from ..services.attendance_engine import AttendanceEngine

logger = structlog.get_logger()
router = APIRouter()


@router.get("/hr/attendance/report")
async def get_attendance_report(
    store_id: str = Query(...),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    考勤月报：按员工汇总出勤天数、迟到次数、早退次数、缺勤天数、
    加班时数、平均工时、出勤率。
    """
    try:
        today = date.today()
        if not start_date:
            start = today.replace(day=1)
        else:
            start = date.fromisoformat(start_date)
        if not end_date:
            end = today
        else:
            end = date.fromisoformat(end_date)

        result = await db.execute(
            text("""
            SELECT
                a.employee_id,
                e.name AS employee_name,
                e.position,
                COUNT(*) AS total_records,
                COUNT(*) FILTER (WHERE a.status = 'normal') AS normal_days,
                COUNT(*) FILTER (WHERE a.status = 'late') AS late_days,
                COUNT(*) FILTER (WHERE a.status = 'early_leave') AS early_leave_days,
                COUNT(*) FILTER (WHERE a.status = 'absent') AS absent_days,
                COUNT(*) FILTER (WHERE a.status = 'leave') AS leave_days,
                COALESCE(SUM(a.late_minutes), 0) AS total_late_minutes,
                COALESCE(SUM(a.actual_hours), 0) AS total_actual_hours,
                COALESCE(SUM(a.overtime_hours), 0) AS total_overtime_hours
            FROM attendance_logs a
            JOIN employees e ON e.id = a.employee_id
            WHERE a.store_id = :store_id
              AND a.work_date >= :start_date
              AND a.work_date <= :end_date
            GROUP BY a.employee_id, e.name, e.position
            ORDER BY e.name
        """),
            {"store_id": store_id, "start_date": start, "end_date": end},
        )

        items = []
        for r in result.mappings():
            total = r["total_records"] or 1
            normal = r["normal_days"] + r["late_days"]  # 迟到也算出勤
            attendance_rate = round(normal / max(total, 1) * 100, 1)
            avg_hours = round(float(r["total_actual_hours"]) / max(total, 1), 1)

            items.append(
                {
                    "employee_id": r["employee_id"],
                    "employee_name": r["employee_name"],
                    "position": r["position"],
                    "total_records": r["total_records"],
                    "normal_days": r["normal_days"],
                    "late_days": r["late_days"],
                    "early_leave_days": r["early_leave_days"],
                    "absent_days": r["absent_days"],
                    "leave_days": r["leave_days"],
                    "total_late_minutes": r["total_late_minutes"],
                    "total_actual_hours": float(r["total_actual_hours"]),
                    "total_overtime_hours": float(r["total_overtime_hours"]),
                    "avg_daily_hours": avg_hours,
                    "attendance_rate_pct": attendance_rate,
                }
            )

        # 汇总统计
        total_employees = len(items)
        avg_rate = round(sum(i["attendance_rate_pct"] for i in items) / max(total_employees, 1), 1)
        total_overtime = sum(i["total_overtime_hours"] for i in items)
        total_late = sum(i["late_days"] for i in items)
        total_absent = sum(i["absent_days"] for i in items)

        return {
            "period": {"start": str(start), "end": str(end)},
            "summary": {
                "total_employees": total_employees,
                "avg_attendance_rate_pct": avg_rate,
                "total_overtime_hours": round(total_overtime, 1),
                "total_late_count": total_late,
                "total_absent_count": total_absent,
            },
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("考勤报表查询失败", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"考勤报表查询失败: {e}")


@router.get("/hr/attendance/daily")
async def get_daily_attendance(
    store_id: str = Query(...),
    work_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    日考勤明细：指定日期所有员工的打卡记录。
    关联排班数据（如果存在）。
    """
    target = date.fromisoformat(work_date) if work_date else date.today()

    # 考勤记录
    result = await db.execute(
        text("""
        SELECT
            a.employee_id,
            e.name AS employee_name,
            e.position,
            a.clock_in,
            a.clock_out,
            a.actual_hours,
            a.overtime_hours,
            a.status,
            a.late_minutes,
            a.leave_type,
            a.source
        FROM attendance_logs a
        JOIN employees e ON e.id = a.employee_id
        WHERE a.store_id = :store_id AND a.work_date = :work_date
        ORDER BY a.clock_in ASC
    """),
        {"store_id": store_id, "work_date": target},
    )

    items = []
    for r in result.mappings():
        items.append(
            {
                "employee_id": r["employee_id"],
                "employee_name": r["employee_name"],
                "position": r["position"],
                "clock_in": str(r["clock_in"]) if r["clock_in"] else None,
                "clock_out": str(r["clock_out"]) if r["clock_out"] else None,
                "actual_hours": float(r["actual_hours"]) if r["actual_hours"] else None,
                "overtime_hours": float(r["overtime_hours"]) if r["overtime_hours"] else None,
                "status": r["status"],
                "late_minutes": r["late_minutes"],
                "leave_type": r["leave_type"],
                "source": r["source"],
            }
        )

    # 排班数据（如果存在 schedules 表）
    schedule_items = []
    try:
        sched_result = await db.execute(
            text("""
            SELECT s.employee_id, e.name AS employee_name,
                   s.shift_start, s.shift_end, s.shift_type
            FROM schedules s
            JOIN employees e ON e.id = s.employee_id
            WHERE s.store_id = :store_id AND s.schedule_date = :work_date
            ORDER BY s.shift_start ASC
        """),
            {"store_id": store_id, "work_date": target},
        )
        for r in sched_result.mappings():
            schedule_items.append(
                {
                    "employee_id": r["employee_id"],
                    "employee_name": r["employee_name"],
                    "shift_start": str(r["shift_start"]) if r["shift_start"] else None,
                    "shift_end": str(r["shift_end"]) if r["shift_end"] else None,
                    "shift_type": r["shift_type"],
                }
            )
    except Exception:
        pass  # schedules表可能不存在

    return {
        "work_date": str(target),
        "attendance": items,
        "schedule": schedule_items,
    }


# ══════════════════════════════════════════════════════════════
# W1-1 新增端点：班次模板 / 考勤规则 / 打卡 / 批量导入 / 月度汇总
# ══════════════════════════════════════════════════════════════


# ── Pydantic Schemas ──────────────────────────────────────────


class ShiftTemplateCreate(BaseModel):
    brand_id: str
    store_id: Optional[str] = None
    name: str = Field(..., max_length=50)
    code: str = Field(..., max_length=20)
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    is_cross_day: bool = False
    break_minutes: int = 60
    min_work_hours: Optional[float] = None
    late_threshold_minutes: int = 5
    early_leave_threshold_minutes: int = 5
    applicable_positions: List[str] = []
    is_active: bool = True
    sort_order: int = 0


class AttendanceRuleCreate(BaseModel):
    brand_id: str
    store_id: Optional[str] = None
    employment_type: Optional[str] = None
    clock_methods: List[str] = ["wechat"]
    gps_fence_enabled: bool = False
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_radius_meters: int = 200
    late_deduction_fen: int = 0
    absent_deduction_fen: int = 0
    early_leave_deduction_fen: int = 0
    weekday_overtime_rate: float = 1.5
    weekend_overtime_rate: float = 2.0
    holiday_overtime_rate: float = 3.0
    work_hour_type: str = "standard"
    monthly_standard_hours: float = 174
    is_active: bool = True


class ClockEventRequest(BaseModel):
    store_id: str
    brand_id: str
    employee_id: str
    clock_time: str = Field(..., description="ISO datetime")
    clock_type: str = Field("clock_in", description="clock_in | clock_out")
    source: str = "wechat"
    gps_data: Optional[Dict[str, Any]] = None


class BatchImportRequest(BaseModel):
    store_id: str
    brand_id: str
    records: List[Dict[str, Any]]


# ── 班次模板 ──────────────────────────────────────────────────


@router.get("/hr/attendance/shift-templates")
async def list_shift_templates(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """班次模板列表（品牌级 + 门店级）"""
    conditions = [ShiftTemplate.brand_id == brand_id]
    if store_id:
        conditions.append((ShiftTemplate.store_id == store_id) | ShiftTemplate.store_id.is_(None))
    else:
        conditions.append(ShiftTemplate.store_id.is_(None))

    result = await db.execute(
        select(ShiftTemplate).where(and_(*conditions)).order_by(ShiftTemplate.sort_order, ShiftTemplate.start_time)
    )
    templates = result.scalars().all()

    items = []
    for t in templates:
        items.append(
            {
                "id": str(t.id),
                "brand_id": t.brand_id,
                "store_id": t.store_id,
                "name": t.name,
                "code": t.code,
                "start_time": t.start_time.strftime("%H:%M") if t.start_time else None,
                "end_time": t.end_time.strftime("%H:%M") if t.end_time else None,
                "is_cross_day": t.is_cross_day,
                "break_minutes": t.break_minutes,
                "min_work_hours": float(t.min_work_hours) if t.min_work_hours else None,
                "late_threshold_minutes": t.late_threshold_minutes,
                "early_leave_threshold_minutes": t.early_leave_threshold_minutes,
                "applicable_positions": t.applicable_positions or [],
                "is_active": t.is_active,
                "sort_order": t.sort_order,
            }
        )

    return {"items": items, "total": len(items)}


@router.post("/hr/attendance/shift-templates")
async def create_shift_template(
    payload: ShiftTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建班次模板"""
    start_parts = payload.start_time.split(":")
    end_parts = payload.end_time.split(":")
    start_t = time(int(start_parts[0]), int(start_parts[1]))
    end_t = time(int(end_parts[0]), int(end_parts[1]))

    template = ShiftTemplate(
        id=uuid.uuid4(),
        brand_id=payload.brand_id,
        store_id=payload.store_id,
        name=payload.name,
        code=payload.code,
        start_time=start_t,
        end_time=end_t,
        is_cross_day=payload.is_cross_day,
        break_minutes=payload.break_minutes,
        min_work_hours=payload.min_work_hours,
        late_threshold_minutes=payload.late_threshold_minutes,
        early_leave_threshold_minutes=payload.early_leave_threshold_minutes,
        applicable_positions=payload.applicable_positions,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(template)
    await db.flush()

    logger.info("班次模板已创建", template_id=str(template.id), name=payload.name)
    return {
        "id": str(template.id),
        "name": payload.name,
        "code": payload.code,
        "message": "班次模板创建成功",
    }


# ── 考勤规则 ──────────────────────────────────────────────────


@router.get("/hr/attendance/rules")
async def list_attendance_rules(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """考勤规则列表"""
    conditions = [AttendanceRule.brand_id == brand_id, AttendanceRule.is_active.is_(True)]
    if store_id:
        conditions.append((AttendanceRule.store_id == store_id) | AttendanceRule.store_id.is_(None))

    result = await db.execute(select(AttendanceRule).where(and_(*conditions)))
    rules = result.scalars().all()

    items = []
    for r in rules:
        items.append(
            {
                "id": str(r.id),
                "brand_id": r.brand_id,
                "store_id": r.store_id,
                "employment_type": r.employment_type,
                "clock_methods": r.clock_methods or ["wechat"],
                "gps_fence_enabled": r.gps_fence_enabled,
                "gps_latitude": float(r.gps_latitude) if r.gps_latitude else None,
                "gps_longitude": float(r.gps_longitude) if r.gps_longitude else None,
                "gps_radius_meters": r.gps_radius_meters,
                "late_deduction_fen": r.late_deduction_fen,
                "late_deduction_yuan": round((r.late_deduction_fen or 0) / 100, 2),
                "absent_deduction_fen": r.absent_deduction_fen,
                "absent_deduction_yuan": round((r.absent_deduction_fen or 0) / 100, 2),
                "early_leave_deduction_fen": r.early_leave_deduction_fen,
                "early_leave_deduction_yuan": round((r.early_leave_deduction_fen or 0) / 100, 2),
                "weekday_overtime_rate": float(r.weekday_overtime_rate) if r.weekday_overtime_rate else 1.5,
                "weekend_overtime_rate": float(r.weekend_overtime_rate) if r.weekend_overtime_rate else 2.0,
                "holiday_overtime_rate": float(r.holiday_overtime_rate) if r.holiday_overtime_rate else 3.0,
                "work_hour_type": r.work_hour_type,
                "monthly_standard_hours": float(r.monthly_standard_hours) if r.monthly_standard_hours else 174,
                "is_active": r.is_active,
            }
        )

    return {"items": items, "total": len(items)}


@router.post("/hr/attendance/rules")
async def create_or_update_attendance_rule(
    payload: AttendanceRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建或更新考勤规则（按 brand_id + store_id + employment_type 唯一匹配）"""
    # 检查是否已存在
    conditions = [
        AttendanceRule.brand_id == payload.brand_id,
    ]
    if payload.store_id:
        conditions.append(AttendanceRule.store_id == payload.store_id)
    else:
        conditions.append(AttendanceRule.store_id.is_(None))
    if payload.employment_type:
        conditions.append(AttendanceRule.employment_type == payload.employment_type)
    else:
        conditions.append(AttendanceRule.employment_type.is_(None))

    result = await db.execute(select(AttendanceRule).where(and_(*conditions)).limit(1))
    existing = result.scalar_one_or_none()

    if existing:
        # 更新现有规则
        existing.clock_methods = payload.clock_methods
        existing.gps_fence_enabled = payload.gps_fence_enabled
        existing.gps_latitude = payload.gps_latitude
        existing.gps_longitude = payload.gps_longitude
        existing.gps_radius_meters = payload.gps_radius_meters
        existing.late_deduction_fen = payload.late_deduction_fen
        existing.absent_deduction_fen = payload.absent_deduction_fen
        existing.early_leave_deduction_fen = payload.early_leave_deduction_fen
        existing.weekday_overtime_rate = payload.weekday_overtime_rate
        existing.weekend_overtime_rate = payload.weekend_overtime_rate
        existing.holiday_overtime_rate = payload.holiday_overtime_rate
        existing.work_hour_type = payload.work_hour_type
        existing.monthly_standard_hours = payload.monthly_standard_hours
        existing.is_active = payload.is_active
        await db.flush()
        logger.info("考勤规则已更新", rule_id=str(existing.id))
        return {"id": str(existing.id), "action": "updated", "message": "考勤规则更新成功"}
    else:
        # 新建
        rule = AttendanceRule(
            id=uuid.uuid4(),
            brand_id=payload.brand_id,
            store_id=payload.store_id,
            employment_type=payload.employment_type,
            clock_methods=payload.clock_methods,
            gps_fence_enabled=payload.gps_fence_enabled,
            gps_latitude=payload.gps_latitude,
            gps_longitude=payload.gps_longitude,
            gps_radius_meters=payload.gps_radius_meters,
            late_deduction_fen=payload.late_deduction_fen,
            absent_deduction_fen=payload.absent_deduction_fen,
            early_leave_deduction_fen=payload.early_leave_deduction_fen,
            weekday_overtime_rate=payload.weekday_overtime_rate,
            weekend_overtime_rate=payload.weekend_overtime_rate,
            holiday_overtime_rate=payload.holiday_overtime_rate,
            work_hour_type=payload.work_hour_type,
            monthly_standard_hours=payload.monthly_standard_hours,
            is_active=payload.is_active,
        )
        db.add(rule)
        await db.flush()
        logger.info("考勤规则已创建", rule_id=str(rule.id))
        return {"id": str(rule.id), "action": "created", "message": "考勤规则创建成功"}


# ── 打卡 ──────────────────────────────────────────────────────


@router.post("/hr/attendance/clock")
async def clock_event(
    payload: ClockEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    打卡（含GPS）。
    自动判定迟到/早退/正常，计算扣款。
    """
    from datetime import datetime as dt

    try:
        clock_time = dt.fromisoformat(payload.clock_time)
        engine = AttendanceEngine(store_id=payload.store_id, brand_id=payload.brand_id)

        result = await engine.process_clock_event(
            db=db,
            employee_id=payload.employee_id,
            clock_time=clock_time,
            clock_type=payload.clock_type,
            gps_data=payload.gps_data,
            source=payload.source,
        )

        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"打卡参数错误: {e}")
    except Exception as e:
        logger.error("打卡处理失败", employee_id=payload.employee_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"打卡处理失败: {e}")


# ── 批量导入 ──────────────────────────────────────────────────


@router.post("/hr/attendance/batch-import")
async def batch_import_clock_data(
    payload: BatchImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    批量导入打卡数据（从考勤机/企微/钉钉同步）。
    每条记录需包含: employee_id, clock_time, clock_type, source (optional), gps_data (optional)
    """
    try:
        engine = AttendanceEngine(store_id=payload.store_id, brand_id=payload.brand_id)
        result = await engine.batch_import_clock_data(db=db, records=payload.records)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("批量导入打卡数据失败", store_id=payload.store_id, count=len(payload.records), error=str(e))
        raise HTTPException(status_code=500, detail=f"批量导入失败: {e}")


# ── 月度汇总 ─────────────────────────────────────────────────


@router.get("/hr/attendance/monthly-summary/{employee_id}/{pay_month}")
async def get_monthly_summary(
    employee_id: str,
    pay_month: str,
    store_id: str = Query(...),
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    月度考勤汇总 — 供薪酬计算使用。
    pay_month 格式: "2026-03"
    返回: 出勤天数、迟到次数/分钟、早退次数、旷工天数、
          加班时数（工作日/周末/节假日）、总扣款等。
    """
    try:
        engine = AttendanceEngine(store_id=store_id, brand_id=brand_id)
        summary = await engine.calculate_monthly_summary(
            db=db,
            employee_id=employee_id,
            pay_month=pay_month,
        )
        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error("月度考勤汇总失败", employee_id=employee_id, pay_month=pay_month, error=str(e))
        raise HTTPException(status_code=500, detail=f"月度考勤汇总失败: {e}")
