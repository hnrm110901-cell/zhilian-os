"""
敏感数据管理API — 加密读写 + 脱敏 + 审计日志

端点（按注册顺序，静态路径在前）:
  GET  /hr/sensitive/audit-logs                   — 审计日志查询
  POST /hr/sensitive/batch-encrypt                — 批量加密迁移
  GET  /hr/sensitive/{employee_id}/masked         — 脱敏批量读取
  GET  /hr/sensitive/{employee_id}/{field_name}   — 解密读取（需审计）
  PUT  /hr/sensitive/{employee_id}/{field_name}   — 加密写入
"""
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.sensitive_audit_log import SensitiveDataAuditLog
from ..models.user import User
from ..services.sensitive_data_service import sensitive_data_service

logger = structlog.get_logger()
router = APIRouter()


# ── 请求/响应模型 ─────────────────────────────────────

class SensitiveFieldWriteRequest(BaseModel):
    """写入敏感字段请求体"""
    value: str = Field(..., min_length=1, max_length=200, description="明文值")


class BatchEncryptRequest(BaseModel):
    """批量加密请求体"""
    store_id: Optional[str] = Field(None, description="门店ID（空=全部）")


# ── 审计日志查询（静态路径，必须在 {employee_id} 之前注册） ──

@router.get("/hr/sensitive/audit-logs")
async def get_audit_logs(
    employee_id: Optional[str] = Query(None, description="按员工过滤"),
    operator_id: Optional[str] = Query(None, description="按操作人过滤"),
    action: Optional[str] = Query(None, description="按操作类型过滤: read/write/export/batch_encrypt"),
    store_id: Optional[str] = Query(None, description="按门店过滤"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询敏感数据访问审计日志"""
    stmt = select(SensitiveDataAuditLog).order_by(
        desc(SensitiveDataAuditLog.created_at)
    )

    if employee_id:
        stmt = stmt.where(SensitiveDataAuditLog.employee_id == employee_id)
    if operator_id:
        stmt = stmt.where(SensitiveDataAuditLog.operator_id == operator_id)
    if action:
        stmt = stmt.where(SensitiveDataAuditLog.action == action)
    if store_id:
        stmt = stmt.where(SensitiveDataAuditLog.store_id == store_id)
    if start_date:
        stmt = stmt.where(
            SensitiveDataAuditLog.created_at >= datetime.fromisoformat(start_date)
        )
    if end_date:
        stmt = stmt.where(
            SensitiveDataAuditLog.created_at <= datetime.fromisoformat(end_date + "T23:59:59")
        )

    # 分页
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    logs = result.scalars().all()

    return {
        "page": page,
        "page_size": page_size,
        "items": [log.to_dict() for log in logs],
    }


# ── 批量加密迁移（静态路径） ──────────────────────────

@router.post("/hr/sensitive/batch-encrypt")
async def batch_encrypt(
    body: BatchEncryptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量加密已有明文数据（一次性迁移用）

    将 employees 表中未加密的 id_card_no / bank_account / phone 字段
    用 AES-256-GCM 加密。已加密的记录会被跳过（幂等）。
    """
    result = await sensitive_data_service.batch_encrypt_existing(
        db=db,
        operator_id=str(current_user.id),
        store_id=body.store_id,
    )
    await db.commit()
    return result


# ── 脱敏批量读取（/masked 在 /{field_name} 之前注册） ──

@router.get("/hr/sensitive/{employee_id}/masked")
async def get_masked_fields(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量获取脱敏后的所有敏感字段（列表展示用，不记录审计日志）"""
    try:
        masked = await sensitive_data_service.get_all_masked(db, employee_id)
        return {"employee_id": employee_id, "masked": masked}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 解密读取 ──────────────────────────────────────────

@router.get("/hr/sensitive/{employee_id}/{field_name}")
async def get_sensitive_field(
    employee_id: str,
    field_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """解密读取敏感字段（自动记录审计日志）

    field_name: id_card_no / bank_account / phone
    """
    try:
        plaintext = await sensitive_data_service.get_sensitive_field(
            db=db,
            employee_id=employee_id,
            field_name=field_name,
            operator_id=str(current_user.id),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:500],
        )
        await db.commit()
        return {"employee_id": employee_id, "field_name": field_name, "value": plaintext}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 加密写入 ──────────────────────────────────────────

@router.put("/hr/sensitive/{employee_id}/{field_name}")
async def set_sensitive_field(
    employee_id: str,
    field_name: str,
    body: SensitiveFieldWriteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """加密写入敏感字段（自动记录审计日志）

    field_name: id_card_no / bank_account / phone
    """
    try:
        result = await sensitive_data_service.set_sensitive_field(
            db=db,
            employee_id=employee_id,
            field_name=field_name,
            plaintext=body.value,
            operator_id=str(current_user.id),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:500],
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
