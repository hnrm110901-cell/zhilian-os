"""
异步导出任务 API
提交大数据导出任务、查询进度、下载结果文件
"""
import os
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.core.dependencies import get_current_active_user
from src.core.database import get_db_session
from src.models import User
from src.models.export_job import ExportJob, ExportStatus
from sqlalchemy import select, and_
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/export-jobs", tags=["export_jobs"])

# 支持的导出类型及说明
SUPPORTED_JOB_TYPES = {
    "transactions": "财务交易记录",
    "audit_logs": "审计日志",
    "orders": "订单记录",
}


class ExportJobCreateRequest(BaseModel):
    job_type: str = Field(..., description="导出类型: transactions/audit_logs/orders")
    format: str = Field("csv", description="导出格式: csv/xlsx")
    params: Dict[str, Any] = Field(default_factory=dict, description="过滤参数")


@router.get("/types")
async def get_supported_types(
    current_user: User = Depends(get_current_active_user),
):
    """获取支持的导出类型列表"""
    return {
        "types": [
            {"type": k, "description": v, "supported_params": _get_params_doc(k)}
            for k, v in SUPPORTED_JOB_TYPES.items()
        ]
    }


def _get_params_doc(job_type: str) -> Dict:
    common = {"store_id": "门店ID", "start_date": "开始日期 YYYY-MM-DD", "end_date": "结束日期 YYYY-MM-DD"}
    extra = {
        "transactions": {"transaction_type": "交易类型 income/expense"},
        "audit_logs": {"user_id": "用户ID", "action": "操作类型"},
        "orders": {"status": "订单状态"},
    }
    return {**common, **extra.get(job_type, {})}


@router.post("", status_code=202)
async def create_export_job(
    request: ExportJobCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    提交异步导出任务

    任务会在后台执行，立即返回 job_id，通过 GET /export-jobs/{job_id} 查询进度。

    支持的过滤参数（params 字段）：
    - store_id: 门店ID
    - start_date / end_date: 日期范围（YYYY-MM-DD）
    - transaction_type: income/expense（transactions 类型）
    - action: 操作类型（audit_logs 类型）
    - status: 订单状态（orders 类型）
    """
    if request.job_type not in SUPPORTED_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的导出类型: {request.job_type}，可选: {list(SUPPORTED_JOB_TYPES.keys())}"
        )
    if request.format not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="format 只支持 csv 或 xlsx")

    # 创建 ExportJob 记录
    async with get_db_session() as session:
        job = ExportJob(
            id=uuid.uuid4(),
            user_id=current_user.id,
            job_type=request.job_type,
            format=request.format,
            params=request.params,
            status=ExportStatus.PENDING,
            progress=0,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = str(job.id)

    # 提交 Celery 任务
    try:
        from src.core.celery_tasks import async_export_data
        async_export_data.delay(job_id)
        logger.info("导出任务已提交", job_id=job_id, job_type=request.job_type)
    except Exception as e:
        # Celery 不可用时标记失败
        async with get_db_session() as session:
            job = await session.get(ExportJob, job_id)
            if job:
                job.status = ExportStatus.FAILED
                job.error_message = f"Celery 不可用: {str(e)}"
                await session.commit()
        raise HTTPException(status_code=503, detail=f"任务队列不可用: {str(e)}")

    return {
        "job_id": job_id,
        "status": ExportStatus.PENDING,
        "message": "导出任务已提交，请通过 job_id 查询进度",
    }


@router.get("")
async def list_export_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
):
    """获取当前用户的导出任务列表"""
    async with get_db_session() as session:
        stmt = (
            select(ExportJob)
            .where(ExportJob.user_id == current_user.id)
            .order_by(ExportJob.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        jobs = result.scalars().all()
    return {"jobs": [j.to_dict() for j in jobs], "total": len(jobs)}


@router.get("/{job_id}")
async def get_export_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    查询导出任务状态和进度

    - status: pending（等待）/ running（执行中）/ completed（完成）/ failed（失败）
    - progress: 0-100
    - 完成后可通过 GET /export-jobs/{job_id}/download 下载文件
    """
    async with get_db_session() as session:
        job = await session.get(ExportJob, job_id)
        if not job or str(job.user_id) != str(current_user.id):
            raise HTTPException(status_code=404, detail="任务不存在或无权限访问")
    return job.to_dict()


@router.get("/{job_id}/download")
async def download_export_file(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    下载已完成的导出文件

    只有 status=completed 的任务才能下载。
    """
    async with get_db_session() as session:
        job = await session.get(ExportJob, job_id)
        if not job or str(job.user_id) != str(current_user.id):
            raise HTTPException(status_code=404, detail="任务不存在或无权限访问")
        if job.status != ExportStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"任务尚未完成，当前状态: {job.status}"
            )
        if not job.file_path or not os.path.exists(job.file_path):
            raise HTTPException(status_code=410, detail="文件已过期或不存在")

        filename = os.path.basename(job.file_path)
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if job.format == "xlsx" else "text/csv"
        )
        return FileResponse(
            path=job.file_path,
            filename=filename,
            media_type=media_type,
        )


@router.delete("/{job_id}")
async def delete_export_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """删除导出任务记录（同时删除临时文件）"""
    async with get_db_session() as session:
        job = await session.get(ExportJob, job_id)
        if not job or str(job.user_id) != str(current_user.id):
            raise HTTPException(status_code=404, detail="任务不存在或无权限访问")
        # 删除临时文件
        if job.file_path and os.path.exists(job.file_path):
            try:
                os.remove(job.file_path)
            except OSError as e:
                logger.warning("export_jobs.file_cleanup_failed", file_path=job.file_path, error=str(e))
        await session.delete(job)
        await session.commit()
    return {"success": True, "message": "任务已删除"}
