"""
增量备份 API
提供全量/增量备份任务的触发、查询、下载和删除接口
"""
import os
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.core.database import get_db

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])


class BackupCreateRequest(BaseModel):
    backup_type: str = "full"          # full / incremental
    since_timestamp: Optional[str] = None  # ISO 8601，增量备份起始时间
    tables: List[str] = []             # 空列表 = 全部表


@router.get("/types")
async def get_backup_types():
    """支持的备份类型"""
    return {
        "types": [
            {"type": "full", "description": "全量备份，导出所有指定表的完整数据"},
            {"type": "incremental", "description": "增量备份，仅导出 since_timestamp 之后变更的行"},
        ]
    }


@router.post("/", status_code=202)
async def create_backup(req: BackupCreateRequest, db: AsyncSession = Depends(get_db)):
    """触发备份任务，立即返回 job_id，后台异步执行"""
    if req.backup_type not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="backup_type 必须为 full 或 incremental")
    if req.backup_type == "incremental" and not req.since_timestamp:
        raise HTTPException(status_code=400, detail="增量备份必须提供 since_timestamp")

    import uuid
    job_id = str(uuid.uuid4())
    tables_json = req.tables or []

    await db.execute(
        text(
            "INSERT INTO backup_jobs (id, backup_type, since_timestamp, tables, status, progress, created_at, updated_at) "
            "VALUES (:id, :bt, :st, :tb::jsonb, 'pending', 0, NOW(), NOW())"
        ),
        {
            "id": job_id,
            "bt": req.backup_type,
            "st": req.since_timestamp,
            "tb": __import__("json").dumps(tables_json),
        },
    )
    await db.commit()

    try:
        from src.core.celery_tasks import run_backup
        task = run_backup.delay(job_id)
        await db.execute(
            text("UPDATE backup_jobs SET celery_task_id=:tid WHERE id=:id"),
            {"tid": task.id, "id": job_id},
        )
        await db.commit()
    except Exception as e:
        await db.execute(
            text("UPDATE backup_jobs SET status='failed', error_message=:err WHERE id=:id"),
            {"err": f"Celery 不可用: {str(e)[:200]}", "id": job_id},
        )
        await db.commit()
        raise HTTPException(status_code=503, detail="Celery 服务不可用，备份任务提交失败")

    return {"job_id": job_id, "status": "pending", "message": "备份任务已提交"}


@router.get("/")
async def list_backups(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """查询备份任务列表"""
    where = "WHERE 1=1"
    params: dict = {"limit": limit, "offset": offset}
    if status:
        where += " AND status = :status"
        params["status"] = status

    result = await db.execute(
        text(f"SELECT * FROM backup_jobs {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
        params,
    )
    rows = [dict(r) for r in result.mappings().fetchall()]
    for r in rows:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
    return {"items": rows, "total": len(rows)}


@router.get("/{job_id}")
async def get_backup(job_id: str, db: AsyncSession = Depends(get_db)):
    """查询单个备份任务状态"""
    result = await db.execute(
        text("SELECT * FROM backup_jobs WHERE id = :id"),
        {"id": job_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="备份任务不存在")
    data = dict(row)
    for k, v in data.items():
        if hasattr(v, "isoformat"):
            data[k] = v.isoformat()
    return data


@router.get("/{job_id}/download")
async def download_backup(job_id: str, db: AsyncSession = Depends(get_db)):
    """下载备份压缩包（仅 completed 状态可下载）"""
    result = await db.execute(
        text("SELECT status, file_path, backup_type, created_at FROM backup_jobs WHERE id = :id"),
        {"id": job_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="备份任务不存在")
    if row["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"任务状态为 {row['status']}，尚不可下载")
    file_path = row["file_path"]
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="备份文件不存在或已被清理")
    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        media_type="application/gzip",
        filename=filename,
    )


@router.delete("/{job_id}", status_code=204)
async def delete_backup(job_id: str, db: AsyncSession = Depends(get_db)):
    """删除备份任务记录及临时文件"""
    result = await db.execute(
        text("SELECT file_path FROM backup_jobs WHERE id = :id"),
        {"id": job_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="备份任务不存在")
    if row["file_path"] and os.path.exists(row["file_path"]):
        os.remove(row["file_path"])
    await db.execute(text("DELETE FROM backup_jobs WHERE id = :id"), {"id": job_id})
    await db.commit()

