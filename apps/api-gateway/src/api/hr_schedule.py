"""
HR Smart Schedule API — 智能排班接口
提供自动排班生成、手动调整、发布通知、需求配置、AI建议等端点。
"""

import uuid
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.schedule_demand import StoreStaffingDemand
from ..models.user import User
from ..services.smart_schedule_service import smart_schedule_service

logger = structlog.get_logger()
router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────


class AutoGenerateRequest(BaseModel):
    """自动排班请求"""

    store_id: str
    brand_id: str
    week_start: str = Field(..., description="周一日期，格式 YYYY-MM-DD")
    demand_forecast: Optional[Dict[str, Any]] = Field(None, description="外部需求预测覆盖，key=日期字符串，value=岗位需求dict")


class ScheduleAdjustChange(BaseModel):
    """单个调整操作"""

    action: str = Field(..., description="swap / add / remove")
    employee_id: Optional[str] = None
    from_employee_id: Optional[str] = None
    to_employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    position: Optional[str] = None


class ScheduleAdjustRequest(BaseModel):
    """排班调整请求"""

    store_id: str
    schedule_date: str = Field(..., description="YYYY-MM-DD")
    changes: List[ScheduleAdjustChange]


class PublishRequest(BaseModel):
    """发布排班请求"""

    store_id: str
    week_start: str = Field(..., description="周一日期，格式 YYYY-MM-DD")
    published_by: Optional[str] = "system"


class StaffingDemandCreate(BaseModel):
    """岗位编制需求配置"""

    store_id: str
    brand_id: str
    position: str = Field(..., description="waiter/chef/cashier/host/manager/dishwasher")
    day_type: str = Field(..., description="weekday/friday/weekend/holiday")
    shift_type: str = Field(..., description="morning/afternoon/evening")
    min_count: int = Field(1, ge=0)
    max_count: int = Field(3, ge=1)
    is_active: bool = True


# ── 自动排班 ──────────────────────────────────────────────────


@router.post("/hr/schedule/auto-generate")
async def auto_generate_schedule(
    payload: AutoGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    自动生成一周排班计划。
    基于需求预测、员工可用性、劳动法约束，使用贪心算法分配班次。
    """
    try:
        week_start = date.fromisoformat(payload.week_start)

        result = await smart_schedule_service.generate_weekly_schedule(
            db=db,
            store_id=payload.store_id,
            brand_id=payload.brand_id,
            week_start=week_start,
            demand_forecast=payload.demand_forecast,
        )

        logger.info(
            "自动排班完成",
            store_id=payload.store_id,
            week_start=payload.week_start,
            total_shifts=result["stats"]["total_shifts"],
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"排班参数错误: {e}")
    except Exception as e:
        logger.error("自动排班失败", store_id=payload.store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"自动排班失败: {e}")


# ── 查询周排班 ────────────────────────────────────────────────


@router.get("/hr/schedule/weekly/{store_id}")
async def get_weekly_schedule(
    store_id: str,
    week_start: str = Query(..., description="周一日期，YYYY-MM-DD"),
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取指定门店的一周排班（已持久化的排班数据）。
    如果该周排班尚未生成，返回空结构。
    """
    from sqlalchemy.orm import selectinload

    from ..models.schedule import Schedule, Shift

    ws = date.fromisoformat(week_start)
    we = ws + timedelta(days=6)

    stmt = (
        select(Schedule)
        .options(selectinload(Schedule.shifts))
        .where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= ws,
                Schedule.schedule_date <= we,
            )
        )
        .order_by(Schedule.schedule_date)
    )
    result = await db.execute(stmt)
    schedules = result.scalars().all()

    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    daily_schedules = []

    for sched in schedules:
        shifts_data = []
        for shift in sched.shifts:
            shifts_data.append(
                {
                    "employee_id": shift.employee_id,
                    "position": shift.position,
                    "shift_type": shift.shift_type,
                    "start_time": shift.start_time.strftime("%H:%M") if shift.start_time else None,
                    "end_time": shift.end_time.strftime("%H:%M") if shift.end_time else None,
                    "is_confirmed": shift.is_confirmed,
                }
            )

        daily_schedules.append(
            {
                "date": str(sched.schedule_date),
                "day_of_week": day_names[sched.schedule_date.weekday()],
                "is_published": sched.is_published,
                "shifts": shifts_data,
            }
        )

    return {
        "store_id": store_id,
        "week_start": week_start,
        "week_end": str(we),
        "daily_schedules": daily_schedules,
        "total_days": len(daily_schedules),
    }


# ── 手动调整 ──────────────────────────────────────────────────


@router.put("/hr/schedule/adjust")
async def adjust_schedule(
    payload: ScheduleAdjustRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    手动调整排班：换班、加人、减人。
    已发布的排班不允许调整（需先撤回）。
    """
    try:
        schedule_date = date.fromisoformat(payload.schedule_date)
        changes = [c.model_dump() for c in payload.changes]

        result = await smart_schedule_service.adjust_schedule(
            db=db,
            store_id=payload.store_id,
            schedule_date=schedule_date,
            changes=changes,
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("排班调整失败", store_id=payload.store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"排班调整失败: {e}")


# ── 发布排班 ──────────────────────────────────────────────────


@router.post("/hr/schedule/publish")
async def publish_schedule(
    payload: PublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    发布一周排班，标记为已发布状态。
    发布后排班不可直接修改（需先撤回）。
    """
    try:
        week_start = date.fromisoformat(payload.week_start)

        result = await smart_schedule_service.publish_schedule(
            db=db,
            store_id=payload.store_id,
            week_start=week_start,
            published_by=payload.published_by or current_user.username,
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("排班发布失败", store_id=payload.store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"排班发布失败: {e}")


# ── 需求配置 ──────────────────────────────────────────────────


@router.get("/hr/schedule/demand/{store_id}")
async def get_staffing_demand(
    store_id: str,
    brand_id: str = Query(...),
    day_type: Optional[str] = Query(None, description="weekday/friday/weekend/holiday"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店岗位编制需求配置。
    可按 day_type 筛选。
    """
    conditions = [
        StoreStaffingDemand.store_id == store_id,
        StoreStaffingDemand.brand_id == brand_id,
        StoreStaffingDemand.is_active.is_(True),
    ]
    if day_type:
        conditions.append(StoreStaffingDemand.day_type == day_type)

    result = await db.execute(
        select(StoreStaffingDemand)
        .where(and_(*conditions))
        .order_by(
            StoreStaffingDemand.day_type,
            StoreStaffingDemand.shift_type,
            StoreStaffingDemand.position,
        )
    )
    demands = result.scalars().all()

    items = []
    for d in demands:
        items.append(
            {
                "id": str(d.id),
                "store_id": d.store_id,
                "brand_id": d.brand_id,
                "position": d.position,
                "day_type": d.day_type,
                "shift_type": d.shift_type,
                "min_count": d.min_count,
                "max_count": d.max_count,
                "is_active": d.is_active,
            }
        )

    return {"items": items, "total": len(items)}


@router.post("/hr/schedule/demand")
async def set_staffing_demand(
    payload: StaffingDemandCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    设置/更新门店岗位编制需求。
    按 (store_id, position, day_type, shift_type) 唯一匹配，存在则更新，不存在则新建。
    """
    # 查找已有配置
    stmt = (
        select(StoreStaffingDemand)
        .where(
            and_(
                StoreStaffingDemand.store_id == payload.store_id,
                StoreStaffingDemand.position == payload.position,
                StoreStaffingDemand.day_type == payload.day_type,
                StoreStaffingDemand.shift_type == payload.shift_type,
            )
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.min_count = payload.min_count
        existing.max_count = payload.max_count
        existing.is_active = payload.is_active
        existing.brand_id = payload.brand_id
        await db.flush()
        logger.info("编制需求已更新", demand_id=str(existing.id))
        return {
            "id": str(existing.id),
            "action": "updated",
            "message": "编制需求更新成功",
        }
    else:
        demand = StoreStaffingDemand(
            id=uuid.uuid4(),
            store_id=payload.store_id,
            brand_id=payload.brand_id,
            position=payload.position,
            day_type=payload.day_type,
            shift_type=payload.shift_type,
            min_count=payload.min_count,
            max_count=payload.max_count,
            is_active=payload.is_active,
        )
        db.add(demand)
        await db.flush()
        logger.info("编制需求已创建", demand_id=str(demand.id))
        return {
            "id": str(demand.id),
            "action": "created",
            "message": "编制需求创建成功",
        }


# ── AI 优化建议 ──────────────────────────────────────────────


@router.get("/hr/schedule/suggestions/{store_id}")
async def get_schedule_suggestions(
    store_id: str,
    week_start: str = Query(..., description="周一日期，YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取排班优化建议。
    分析维度：人力成本、覆盖缺口、公平性、合规风险。
    每条建议包含：建议动作 + 预期¥影响 + 置信度。
    """
    try:
        ws = date.fromisoformat(week_start)

        suggestions = await smart_schedule_service.get_schedule_suggestions(
            db=db,
            store_id=store_id,
            week_start=ws,
        )

        return {"store_id": store_id, "week_start": week_start, "suggestions": suggestions}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("排班建议获取失败", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"排班建议获取失败: {e}")


# ── AI 排班深度分析 ──────────────────────────────────────────


@router.get("/hr/schedule/ai-analysis/{store_id}")
async def get_ai_schedule_analysis(
    store_id: str,
    week_start: str = Query(..., description="周一日期，YYYY-MM-DD"),
    month: Optional[str] = Query(None, description="月份，YYYY-MM-DD（用于人力成本分析），默认取 week_start 所在月"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    AI排班综合分析 — 包含排班优化建议 + 人力成本效率分析。

    返回：
    - schedule_suggestions: 排班优化建议（合规 + AI/规则分析）
    - labor_cost_analysis: 人力成本效率分析（月度维度）
    - 每条建议包含：建议动作 + 预期¥影响 + 置信度 + 优先级
    """
    try:
        ws = date.fromisoformat(week_start)
        month_date = date.fromisoformat(month) if month else ws

        # 并行获取排班建议和人力成本分析
        suggestions = await smart_schedule_service.get_schedule_suggestions(
            db=db,
            store_id=store_id,
            week_start=ws,
        )

        labor_analysis = await smart_schedule_service.analyze_labor_cost_efficiency(
            db=db,
            store_id=store_id,
            month=month_date,
        )

        # 汇总预期节省金额
        total_expected_saving = sum(
            s.get("expected_saving_yuan", 0) for s in suggestions if isinstance(s.get("expected_saving_yuan"), (int, float))
        )
        total_expected_saving += sum(
            s.get("expected_saving_yuan", 0)
            for s in labor_analysis.get("suggestions", [])
            if isinstance(s.get("expected_saving_yuan"), (int, float))
        )

        return {
            "store_id": store_id,
            "week_start": week_start,
            "month": str(month_date.replace(day=1)),
            "schedule_suggestions": suggestions,
            "labor_cost_analysis": labor_analysis,
            "total_expected_saving_yuan": round(total_expected_saving, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AI排班分析失败", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"AI排班分析失败: {e}")
