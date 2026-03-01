"""
ARCH-004: 执行层 API 端点

POST /api/v1/execution/execute           — 执行指令
POST /api/v1/execution/{id}/rollback     — 回滚执行（30分钟窗口）
GET  /api/v1/execution/audit-logs        — 查询审计日志
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
import structlog

from src.core.trusted_executor import (
    TrustedExecutor, ExecutionError, PermissionDeniedError, ApprovalRequiredError,
    RollbackWindowExpiredError,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])


# ==================== Request / Response 模型 ====================

class ExecuteRequest(BaseModel):
    command_type: str
    payload: Dict[str, Any]


class RollbackRequest(BaseModel):
    reason: Optional[str] = None


class AuditLogFilter(BaseModel):
    store_id: Optional[str] = None
    brand_id: Optional[str] = None
    command_type: Optional[str] = None
    actor_id: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = 50
    offset: int = 0


# ==================== 依赖注入 ====================

async def get_current_user(request=None) -> Dict[str, Any]:
    """获取当前用户（从 request.state.user 注入）"""
    # 实际项目中从认证中间件获取
    return {"user_id": "system", "role": "admin", "store_id": "", "brand_id": ""}


async def get_executor() -> TrustedExecutor:
    """获取 TrustedExecutor 实例（无持久化会话版本）"""
    return TrustedExecutor()


# ==================== 端点 ====================

@router.post("/execute")
async def execute_command(
    request: ExecuteRequest,
    actor: Dict = Depends(get_current_user),
    executor: TrustedExecutor = Depends(get_executor),
):
    """
    执行指令

    - AUTO/NOTIFY 级别：直接执行，返回结果
    - APPROVE 级别：发起审批流，返回 202 Accepted
    """
    try:
        result = await executor.execute(
            command_type=request.command_type,
            payload=request.payload,
            actor=actor,
        )
        return result

    except ApprovalRequiredError as e:
        return {
            "status": "pending_approval",
            "command_type": request.command_type,
            "message": str(e),
            "error_code": e.error_code,
        }

    except PermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": str(e), "error_code": e.error_code},
        )

    except ExecutionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "error_code": e.error_code},
        )

    except Exception as e:
        logger.error("execution_api.unexpected_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "执行失败，请联系管理员", "error_code": "INTERNAL_ERROR"},
        )


@router.post("/{execution_id}/rollback")
async def rollback_execution(
    execution_id: str,
    request: RollbackRequest,
    actor: Dict = Depends(get_current_user),
    executor: TrustedExecutor = Depends(get_executor),
):
    """
    回滚已执行的指令（30分钟窗口内）

    - 需要审批权限
    - 超过 30 分钟窗口返回 409
    """
    try:
        result = await executor.rollback(
            execution_id=execution_id,
            operator=actor,
        )
        return result

    except RollbackWindowExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(e), "error_code": e.error_code},
        )

    except PermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": str(e), "error_code": e.error_code},
        )

    except ExecutionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "error_code": e.error_code},
        )


@router.get("/audit-logs")
async def get_audit_logs(
    store_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    command_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    actor: Dict = Depends(get_current_user),
):
    """
    查询审计日志

    支持按门店、品牌、指令类型、操作人、状态过滤。
    """
    try:
        from src.core.database import AsyncSessionLocal
        from src.models.execution_audit import ExecutionRecord
        from sqlalchemy import select, and_

        conditions = []
        if store_id:
            conditions.append(ExecutionRecord.store_id == store_id)
        if brand_id:
            conditions.append(ExecutionRecord.brand_id == brand_id)
        if command_type:
            conditions.append(ExecutionRecord.command_type == command_type)
        if actor_id:
            conditions.append(ExecutionRecord.actor_id == actor_id)
        if status_filter:
            conditions.append(ExecutionRecord.status == status_filter)

        async with AsyncSessionLocal() as session:
            stmt = select(ExecutionRecord)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            stmt = stmt.order_by(ExecutionRecord.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(stmt)
            records = result.scalars().all()

        return {
            "records": [
                {
                    "execution_id": r.id,
                    "command_type": r.command_type,
                    "actor_id": r.actor_id,
                    "actor_role": r.actor_role,
                    "store_id": r.store_id,
                    "brand_id": r.brand_id,
                    "status": r.status,
                    "level": r.level,
                    "amount": r.amount,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "rollback_id": r.rollback_id,
                }
                for r in records
            ],
            "total": len(records),
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error("audit_logs_query_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "查询审计日志失败", "error_code": "QUERY_ERROR"},
        )
