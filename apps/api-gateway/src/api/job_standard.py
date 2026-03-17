"""
岗位标准知识库 API 路由
涵盖：岗位查询/搜索、员工岗位绑定、成长记录管理
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import structlog

from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.job_standard_service import JobStandardService

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["job-standard"])


# ── Pydantic 请求模型 ────────────────────────────────────────


class BindEmployeeJobRequest(BaseModel):
    employee_id: str
    employee_name: str
    store_id: str
    job_code: str
    bound_by: str


class AddGrowthTraceRequest(BaseModel):
    employee_id: str
    employee_name: str
    store_id: Optional[str] = None
    trace_type: str          # hire/transfer/promote/train_complete/assess/reward/penalty/resign/job_change
    event_title: str
    event_detail: Optional[str] = None
    from_job_code: Optional[str] = None
    to_job_code: Optional[str] = None
    kpi_snapshot: Optional[dict] = None
    assessment_score: Optional[int] = None
    is_milestone: bool = False
    created_by: str = "system"


# ── 端点 ────────────────────────────────────────────────────


@router.get("/job-standards")
async def list_job_standards(
    level: Optional[str] = Query(None, description="岗位级别: hq/region/store/support/kitchen"),
    category: Optional[str] = Query(None, description="岗位类别: management/front_of_house/back_of_house/support_dept"),
    db: AsyncSession = Depends(get_db),
):
    """岗位标准列表（支持按 level/category 过滤）"""
    svc = JobStandardService(db)
    standards = await svc.list_standards(job_level=level, job_category=category)
    return {"data": standards, "total": len(standards)}


@router.get("/job-standards/search")
async def search_job_standards(
    keyword: str = Query(..., description="搜索关键词（岗位名称/目标描述）"),
    db: AsyncSession = Depends(get_db),
):
    """搜索岗位标准"""
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="keyword 不能为空")
    svc = JobStandardService(db)
    results = await svc.search_standards(keyword.strip())
    return {"data": results, "total": len(results)}


@router.get("/job-standards/{job_code}")
async def get_job_standard_detail(
    job_code: str,
    db: AsyncSession = Depends(get_db),
):
    """岗位标准详情（含 SOP 列表）"""
    svc = JobStandardService(db)
    detail = await svc.get_standard_detail(job_code)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"岗位标准不存在: {job_code}")
    return {"data": detail}


@router.post("/job-standards/employee-binding")
async def bind_employee_job(
    req: BindEmployeeJobRequest,
    db: AsyncSession = Depends(get_db),
):
    """绑定员工到岗位标准（自动解绑旧绑定）"""
    svc = JobStandardService(db)
    try:
        binding = await svc.bind_employee_job(
            employee_id=req.employee_id,
            employee_name=req.employee_name,
            store_id=req.store_id,
            job_code=req.job_code,
            bound_by=req.bound_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"data": binding, "message": "员工岗位绑定成功"}


@router.get("/job-standards/employee/{employee_id}/current")
async def get_employee_current_job(
    employee_id: str,
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取员工当前绑定的岗位标准"""
    svc = JobStandardService(db)
    current = await svc.get_employee_current_job(employee_id, store_id)
    if current is None:
        return {"data": None, "message": "员工暂未绑定岗位标准"}
    return {"data": current}


@router.get("/job-standards/store/{store_id}/coverage")
async def get_store_job_coverage(
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取门店岗位覆盖情况（哪些关键岗位有人/缺人）"""
    svc = JobStandardService(db)
    coverage = await svc.get_store_job_coverage(store_id)
    return {"data": coverage}


@router.post("/job-standards/growth-trace")
async def add_growth_trace(
    req: AddGrowthTraceRequest,
    db: AsyncSession = Depends(get_db),
):
    """添加员工成长记录"""
    svc = JobStandardService(db)
    trace = await svc.add_growth_trace(
        employee_id=req.employee_id,
        employee_name=req.employee_name,
        store_id=req.store_id,
        trace_type=req.trace_type,
        event_title=req.event_title,
        event_detail=req.event_detail,
        from_job_code=req.from_job_code,
        to_job_code=req.to_job_code,
        kpi_snapshot=req.kpi_snapshot,
        assessment_score=req.assessment_score,
        is_milestone=req.is_milestone,
        created_by=req.created_by,
    )
    return {"data": trace, "message": "成长记录已添加"}


@router.get("/job-standards/employee/{employee_id}/timeline")
async def get_employee_growth_timeline(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取员工完整成长时间轴（倒序）"""
    svc = JobStandardService(db)
    timeline = await svc.get_growth_timeline(employee_id)
    return {"data": timeline, "total": len(timeline)}


@router.get("/job-standards/employee/{employee_id}/kpi-gap")
async def get_employee_kpi_gap(
    employee_id: str,
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """KPI差距分析：员工最新KPI快照 vs 岗位KPI基线"""
    svc = JobStandardService(db)
    gap = await svc.get_employee_kpi_gap(employee_id, store_id)
    return {"data": gap}
