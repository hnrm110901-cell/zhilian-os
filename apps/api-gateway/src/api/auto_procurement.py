"""
智能采购 API
前缀: /api/v1/auto-procurement
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.auto_procurement_service import auto_procurement_service

router = APIRouter(prefix="/auto-procurement", tags=["智能采购"])


@router.post("/check")
async def trigger_check(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """触发库存检查，生成采购建议"""
    brand_id = data.get("brand_id")
    if not brand_id:
        raise HTTPException(status_code=400, detail="缺少必填字段: brand_id")

    store_id = data.get("store_id")
    try:
        suggestions = await auto_procurement_service.check_and_generate(db, brand_id, store_id)
        await db.commit()
        return {"success": True, "data": suggestions}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"检查库存失败: {str(e)}")


@router.get("/suggestions")
async def list_suggestions(
    brand_id: str = Query(..., description="品牌ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取待处理的采购建议"""
    try:
        result = await auto_procurement_service.get_suggestions(db, brand_id, page, page_size)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询采购建议失败: {str(e)}")


@router.post("/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """审批采购建议 -> 生成采购单"""
    try:
        result = await auto_procurement_service.approve_suggestion(db, suggestion_id)
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"审批失败: {str(e)}")


@router.post("/suggestions/{suggestion_id}/skip")
async def skip_suggestion(
    suggestion_id: str,
    data: Dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """跳过采购建议"""
    reason = data.get("reason")
    try:
        result = await auto_procurement_service.skip_suggestion(db, suggestion_id, reason)
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"跳过失败: {str(e)}")


@router.post("/rules")
async def create_rule(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """创建采购规则"""
    required = ["brand_id", "ingredient_id", "ingredient_name", "supplier_id", "supplier_name", "min_stock_qty", "reorder_qty"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")

    try:
        rule = await auto_procurement_service.create_rule(db, data)
        await db.commit()
        return {"success": True, "data": rule}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建规则失败: {str(e)}")


@router.get("/rules")
async def list_rules(
    brand_id: str = Query(..., description="品牌ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询采购规则列表"""
    try:
        result = await auto_procurement_service.list_rules(db, brand_id, page, page_size)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询规则失败: {str(e)}")


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """更新采购规则"""
    try:
        result = await auto_procurement_service.update_rule(db, rule_id, data)
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"更新规则失败: {str(e)}")


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """删除采购规则"""
    try:
        await auto_procurement_service.delete_rule(db, rule_id)
        await db.commit()
        return {"success": True, "data": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除规则失败: {str(e)}")


@router.get("/executions")
async def list_executions(
    brand_id: str = Query(..., description="品牌ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="状态筛选"),
    trigger_type: Optional[str] = Query(None, description="触发类型"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询执行记录"""
    try:
        result = await auto_procurement_service.get_executions(db, brand_id, page, page_size, status, trigger_type)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询执行记录失败: {str(e)}")


@router.get("/stats")
async def get_stats(
    brand_id: str = Query(..., description="品牌ID"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """智能采购统计概览"""
    try:
        result = await auto_procurement_service.get_stats(db, brand_id)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}")
