"""
数据备份管理API
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional

from src.core.dependencies import get_current_active_user, require_permission
from src.services.backup_service import get_backup_service
from src.models import User

router = APIRouter()


class BackupCreate(BaseModel):
    backup_type: str = Field("manual", description="备份类型: manual, scheduled")


@router.post("/create")
async def create_backup(
    data: BackupCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("backup:write")),
):
    """创建数据库备份"""
    service = get_backup_service()

    # 在后台执行备份，避免阻塞
    try:
        result = await service.create_backup(backup_type=data.backup_type)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.get("/list")
async def list_backups(
    current_user: User = Depends(require_permission("backup:read")),
):
    """列出所有备份"""
    service = get_backup_service()
    backups = await service.list_backups()
    return {"backups": backups, "total": len(backups)}


@router.post("/restore/{backup_name}")
async def restore_backup(
    backup_name: str,
    current_user: User = Depends(require_permission("backup:write")),
):
    """恢复数据库备份"""
    service = get_backup_service()

    try:
        result = await service.restore_backup(backup_name)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.delete("/{backup_name}")
async def delete_backup(
    backup_name: str,
    current_user: User = Depends(require_permission("backup:write")),
):
    """删除备份文件"""
    service = get_backup_service()

    try:
        result = await service.delete_backup(backup_name)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/verify/{backup_name}")
async def verify_backup(
    backup_name: str,
    current_user: User = Depends(require_permission("backup:read")),
):
    """验证备份文件完整性"""
    service = get_backup_service()

    try:
        result = await service.verify_backup(backup_name)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")
