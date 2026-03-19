"""
P2 绩效计算 API

端点：
  POST /api/v1/performance/compute
      → 触发指定门店指定月份的指标计算，写入 employee_metric_records

  GET /api/v1/performance/{store_id}/metrics
      → 查询已计算的员工指标列表（按月份/员工/指标过滤）

  GET /api/v1/performance/{store_id}/summary
      → 查询门店月度绩效汇总（各指标的达成率分布）
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_active_user, require_role
from src.models.hr.person import Person
from src.models.employee_metric import EmployeeMetricRecord
from src.models.user import User, UserRole
from src.services.performance_compute_service import PerformanceComputeService

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ComputeRequest(BaseModel):
    store_id: str
    year: int
    month: int  # 1–12


class ComputeResponse(BaseModel):
    store_id: str
    year: int
    month: int
    rows_written: int
    message: str


class MetricRecord(BaseModel):
    id: str
    employee_id: str
    employee_name: Optional[str] = None
    store_id: str
    metric_id: str
    period_start: date
    period_end: date
    value: Optional[float] = None
    target: Optional[float] = None
    achievement_rate: Optional[float] = None
    data_source: Optional[str] = None


class MetricSummaryItem(BaseModel):
    metric_id: str
    avg_value: Optional[float]
    avg_achievement_rate: Optional[float]
    employee_count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/compute", response_model=ComputeResponse)
async def trigger_compute(
    req: ComputeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """
    触发指定门店、指定月份的绩效指标计算。

    计算结果 upsert 到 employee_metric_records 表，可重复调用（幂等）。
    """
    if not (1 <= req.month <= 12):
        raise HTTPException(status_code=422, detail="month 必须在 1–12 之间")

    rows_written = await PerformanceComputeService.compute_and_write(
        session=db,
        store_id=req.store_id,
        year=req.year,
        month=req.month,
    )
    await db.commit()

    return ComputeResponse(
        store_id=req.store_id,
        year=req.year,
        month=req.month,
        rows_written=rows_written,
        message=f"计算完成，共写入 {rows_written} 条指标记录",
    )


@router.get("/{store_id}/metrics", response_model=List[MetricRecord])
async def get_metrics(
    store_id: str,
    year: int = Query(..., description="年份"),
    month: int = Query(..., description="月份 1–12"),
    employee_id: Optional[str] = Query(None, description="按员工ID过滤"),
    metric_id: Optional[str] = Query(None, description="按指标ID过滤，如 revenue / waste_rate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[MetricRecord]:
    """查询已计算的员工指标列表。"""
    period_start = date(year, month, 1)

    conditions = [
        EmployeeMetricRecord.store_id == store_id,
        EmployeeMetricRecord.period_start == period_start,
    ]
    if employee_id:
        conditions.append(EmployeeMetricRecord.employee_id == employee_id)
    if metric_id:
        conditions.append(EmployeeMetricRecord.metric_id == metric_id)

    result = await db.execute(
        select(EmployeeMetricRecord, Person.name)
        .join(Person, Person.legacy_employee_id == EmployeeMetricRecord.employee_id, isouter=True)
        .where(and_(*conditions))
        .order_by(EmployeeMetricRecord.employee_id, EmployeeMetricRecord.metric_id)
    )
    rows = result.all()

    return [
        MetricRecord(
            id=str(rec.id),
            employee_id=rec.employee_id,
            employee_name=name,
            store_id=rec.store_id,
            metric_id=rec.metric_id,
            period_start=rec.period_start,
            period_end=rec.period_end,
            value=float(rec.value) if rec.value is not None else None,
            target=float(rec.target) if rec.target is not None else None,
            achievement_rate=float(rec.achievement_rate) if rec.achievement_rate is not None else None,
            data_source=rec.data_source,
        )
        for rec, name in rows
    ]


@router.get("/{store_id}/summary", response_model=List[MetricSummaryItem])
async def get_summary(
    store_id: str,
    year: int = Query(..., description="年份"),
    month: int = Query(..., description="月份 1–12"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[MetricSummaryItem]:
    """门店月度绩效汇总：各指标的平均值与平均达成率。"""
    from sqlalchemy import func

    period_start = date(year, month, 1)

    result = await db.execute(
        select(
            EmployeeMetricRecord.metric_id,
            func.avg(EmployeeMetricRecord.value).label("avg_value"),
            func.avg(EmployeeMetricRecord.achievement_rate).label("avg_achievement_rate"),
            func.count(EmployeeMetricRecord.employee_id.distinct()).label("employee_count"),
        )
        .where(
            and_(
                EmployeeMetricRecord.store_id == store_id,
                EmployeeMetricRecord.period_start == period_start,
            )
        )
        .group_by(EmployeeMetricRecord.metric_id)
        .order_by(EmployeeMetricRecord.metric_id)
    )

    return [
        MetricSummaryItem(
            metric_id=row.metric_id,
            avg_value=float(row.avg_value) if row.avg_value is not None else None,
            avg_achievement_rate=float(row.avg_achievement_rate) if row.avg_achievement_rate is not None else None,
            employee_count=row.employee_count,
        )
        for row in result
    ]
