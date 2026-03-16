"""银行流水对账 API — 导入/对账/查询/分类/匹配/统计"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.bank_reconcile_service import BankReconcileService

router = APIRouter(prefix="/bank-recon", tags=["bank-reconciliation"])

svc = BankReconcileService()


# ── 请求模型 ──────────────────────────────────────────────────────────────


class RunReconciliationRequest(BaseModel):
    bank_name: str
    period_start: date
    period_end: date
    brand_id: str = "default"


class CategorizeRequest(BaseModel):
    category: str  # sales/purchase/salary/rent/tax/other


class MatchRequest(BaseModel):
    order_id: str


# ── 导入银行流水 ──────────────────────────────────────────────────────────


@router.post("/import")
async def import_statements(
    file: UploadFile = File(...),
    bank_name: str = Form(...),
    brand_id: str = Form("default"),
    file_format: str = Form("csv"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """上传银行流水文件（CSV），解析并导入"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    content_bytes = await file.read()
    # 尝试UTF-8，失败则GBK
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = content_bytes.decode("gbk", errors="replace")

    result = await svc.import_statements(db, brand_id, bank_name, content, file_format)
    return {
        "success": True,
        "message": f"成功导入 {result['imported']} 条流水",
        "data": result,
    }


# ── 执行对账 ──────────────────────────────────────────────────────────────


@router.post("/run")
async def run_reconciliation(
    req: RunReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """执行银行对账：匹配银行流水与系统记录"""
    result = await svc.run_reconciliation(db, req.brand_id, req.bank_name, req.period_start, req.period_end)
    return {
        "success": True,
        "message": "对账完成",
        "data": result,
    }


# ── 批次列表 ──────────────────────────────────────────────────────────────


@router.get("/batches")
async def list_batches(
    brand_id: str = Query("default"),
    bank_name: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询对账批次列表"""
    data = await svc.list_batches(db, brand_id, page, page_size, bank_name)
    return {"success": True, "data": data}


# ── 批次详情 ──────────────────────────────────────────────────────────────


@router.get("/batches/{batch_id}")
async def get_batch_detail(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询对账批次详情（含流水明细）"""
    data = await svc.get_batch_detail(db, batch_id)
    if not data:
        raise HTTPException(status_code=404, detail="批次不存在")
    return {"success": True, "data": data}


# ── 流水列表 ──────────────────────────────────────────────────────────────


@router.get("/statements")
async def list_statements(
    brand_id: str = Query("default"),
    bank_name: Optional[str] = Query(None),
    is_matched: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询银行流水列表（支持多种筛选）"""
    data = await svc.list_statements(
        db,
        brand_id,
        bank_name,
        is_matched,
        category,
        start_date,
        end_date,
        page,
        page_size,
    )
    return {"success": True, "data": data}


# ── 手动分类 ──────────────────────────────────────────────────────────────


@router.post("/statements/{statement_id}/categorize")
async def categorize_statement(
    statement_id: str,
    req: CategorizeRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """手动设置流水分类"""
    valid_categories = {"sales", "purchase", "salary", "rent", "tax", "other"}
    if req.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"无效分类，可选: {', '.join(valid_categories)}")

    result = await svc.categorize_statement(db, statement_id, req.category)
    if not result:
        raise HTTPException(status_code=404, detail="流水记录不存在")
    return {"success": True, "data": result}


# ── 手动匹配 ──────────────────────────────────────────────────────────────


@router.post("/statements/{statement_id}/match")
async def match_statement(
    statement_id: str,
    req: MatchRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """手动将流水与内部单据匹配"""
    result = await svc.match_statement(db, statement_id, req.order_id)
    if not result:
        raise HTTPException(status_code=404, detail="流水记录不存在")
    return {"success": True, "data": result}


# ── 统计概览 ──────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_stats(
    brand_id: str = Query("default"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """银行流水统计概览：总余额、未匹配金额等"""
    data = await svc.get_stats(db, brand_id)
    return {"success": True, "data": data}
