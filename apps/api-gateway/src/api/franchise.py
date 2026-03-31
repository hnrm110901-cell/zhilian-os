"""
加盟管理 API
品牌方管理加盟商、合同、提成；加盟商查看自己的门户数据
"""

from datetime import date
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.franchise_service import FranchiseService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/franchise", tags=["加盟管理"])

_svc = FranchiseService()


# ================================================================ #
# Pydantic 请求/响应模型
# ================================================================ #


class CreateFranchiseeRequest(BaseModel):
    brand_id: str = Field(..., description="归属品牌ID")
    company_name: str = Field(..., min_length=1, max_length=128, description="公司名")
    contact_name: Optional[str] = Field(None, max_length=64)
    contact_phone: Optional[str] = Field(None, max_length=20)
    contact_email: Optional[str] = Field(None, max_length=128)
    bank_account: Optional[str] = Field(None, max_length=64, description="结算银行账号（加密存储）")
    tax_no: Optional[str] = Field(None, max_length=32)


class CreateContractRequest(BaseModel):
    franchisee_id: str = Field(..., description="加盟商ID（UUID）")
    brand_id: str = Field(..., description="品牌ID")
    store_id: Optional[str] = Field(None, description="关联门店ID")
    contract_type: str = Field(
        ..., description="合同类型: full_franchise / licensed / area_franchise"
    )
    franchise_fee_fen: int = Field(..., ge=0, description="加盟费（分）")
    royalty_rate: float = Field(..., ge=0.0, le=1.0, description="提成率，如 0.05 表示 5%")
    marketing_fund_rate: float = Field(
        0.02, ge=0.0, le=1.0, description="市场基金率，如 0.02 表示 2%"
    )
    start_date: date = Field(..., description="合同开始日期")
    end_date: date = Field(..., description="合同结束日期")


class RenewContractRequest(BaseModel):
    new_end_date: date = Field(..., description="新的合同结束日期")
    updated_terms: Optional[Dict[str, Any]] = Field(
        None, description="可选更新的条款（royalty_rate / marketing_fund_rate / franchise_fee_fen）"
    )


class CalculateRoyaltyRequest(BaseModel):
    contract_id: str = Field(..., description="合同ID（UUID）")
    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)


class MarkRoyaltyPaidRequest(BaseModel):
    payment_reference: str = Field(..., min_length=1, max_length=128, description="付款凭证号")


# ================================================================ #
# 品牌方视角端点
# ================================================================ #


@router.post("/franchisees", summary="注册新加盟商")
async def create_franchisee(
    req: CreateFranchiseeRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """注册新加盟商，银行账号字段自动加密存储。"""
    try:
        result = await _svc.create_franchisee(
            db=db,
            brand_id=req.brand_id,
            company_name=req.company_name,
            contact_name=req.contact_name,
            contact_phone=req.contact_phone,
            contact_email=req.contact_email,
            bank_account=req.bank_account,
            tax_no=req.tax_no,
        )
        await db.commit()
        return {"success": True, "data": result}
    except Exception as exc:
        await db.rollback()
        logger.error("注册加盟商失败", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/franchisees", summary="加盟商列表")
async def list_franchisees(
    brand_id: str = Query(..., description="品牌ID"),
    status: Optional[str] = Query(None, description="状态筛选: active/suspended/terminated"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """获取品牌方名下加盟商列表（分页）。"""
    result = await _svc.list_franchisees(
        db=db, brand_id=brand_id, status=status, limit=limit, offset=offset
    )
    return {"success": True, "data": result}


@router.get("/franchisees/{franchisee_id}", summary="加盟商详情")
async def get_franchisee(
    franchisee_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """获取单个加盟商详情。"""
    result = await _svc.get_franchisee(db=db, franchisee_id=franchisee_id)
    if not result:
        raise HTTPException(status_code=404, detail="加盟商不存在")
    return {"success": True, "data": result}


@router.post("/contracts", summary="签订加盟合同")
async def create_contract(
    req: CreateContractRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """签订加盟合同，自动生成合同编号。"""
    try:
        result = await _svc.create_contract(
            db=db,
            franchisee_id=req.franchisee_id,
            brand_id=req.brand_id,
            store_id=req.store_id,
            contract_type=req.contract_type,
            franchise_fee_fen=req.franchise_fee_fen,
            royalty_rate=req.royalty_rate,
            marketing_fund_rate=req.marketing_fund_rate,
            start_date=req.start_date,
            end_date=req.end_date,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        logger.error("创建合同失败", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/contracts/{contract_id}", summary="合同详情")
async def get_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """获取合同详情。"""
    result = await _svc.get_contract(db=db, contract_id=contract_id)
    if not result:
        raise HTTPException(status_code=404, detail="合同不存在")
    return {"success": True, "data": result}


@router.post("/contracts/{contract_id}/renew", summary="续签合同")
async def renew_contract(
    contract_id: str,
    req: RenewContractRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """合同续签：延长到期日，可选更新费率条款。"""
    try:
        result = await _svc.renew_contract(
            db=db,
            contract_id=contract_id,
            new_end_date=req.new_end_date,
            updated_terms=req.updated_terms,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        logger.error("合同续签失败", contract_id=contract_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/royalties/calculate-monthly", summary="计算月度提成")
async def calculate_monthly_royalty(
    req: CalculateRoyaltyRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """从订单表聚合月度营收，计算并创建提成记录（幂等，重算不覆盖已付记录）。"""
    try:
        result = await _svc.calculate_monthly_royalty(
            db=db,
            contract_id=req.contract_id,
            year=req.year,
            month=req.month,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        logger.error("月度提成计算失败", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/royalties/{royalty_id}/mark-paid", summary="标记提成已收款")
async def mark_royalty_paid(
    royalty_id: str,
    req: MarkRoyaltyPaidRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """标记提成记录为已付，记录付款凭证号。"""
    try:
        result = await _svc.mark_royalty_paid(
            db=db,
            royalty_id=royalty_id,
            payment_reference=req.payment_reference,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        logger.error("标记提成已付失败", royalty_id=royalty_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/overview/{brand_id}", summary="品牌加盟总览（BFF）")
async def get_brand_franchise_overview(
    brand_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    品牌方视角：加盟商数量、本月应收提成、逾期情况、合同到期预警。
    """
    result = await _svc.get_brand_franchise_overview(db=db, brand_id=brand_id)
    return {"success": True, "data": result}


# ================================================================ #
# 加盟商门户视角端点
# ================================================================ #


@router.get("/portal/dashboard", summary="加盟商仪表盘（门户BFF）")
async def franchisee_dashboard(
    franchisee_id: str = Query(..., description="加盟商ID（UUID）"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    加盟商门户首屏聚合：门店营收、待付提成、合同到期预警、最近结算记录。
    """
    result = await _svc.get_franchisee_dashboard(db=db, franchisee_id=franchisee_id)
    return {"success": True, "data": result}


@router.get("/portal/royalties", summary="我的提成记录")
async def portal_royalties(
    contract_id: str = Query(..., description="合同ID（UUID）"),
    months: int = Query(12, ge=1, le=36, description="查询最近 N 个月"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """加盟商查看自己指定合同的提成历史记录。"""
    result = await _svc.get_royalty_history(db=db, contract_id=contract_id, months=months)
    return {"success": True, "data": result}


@router.get("/portal/stores", summary="我的门店列表")
async def portal_stores(
    franchisee_id: str = Query(..., description="加盟商ID（UUID）"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    加盟商查看名下所有合同关联的门店及近 30 日营收汇总。
    （通过 dashboard 接口的 store_revenues_30d 字段获取详情）
    """
    dashboard = await _svc.get_franchisee_dashboard(db=db, franchisee_id=franchisee_id)
    return {
        "success": True,
        "data": {
            "store_ids": dashboard["store_ids"],
            "store_revenues_30d": dashboard["store_revenues_30d"],
        },
    }
