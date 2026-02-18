"""
财务管理API
"""
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.auth import get_current_user, require_permission
from src.services.finance_service import get_finance_service
from src.models import User

router = APIRouter()


# Pydantic模型
class TransactionCreate(BaseModel):
    store_id: str = Field(..., description="门店ID")
    transaction_date: date = Field(..., description="交易日期")
    transaction_type: str = Field(..., description="交易类型: income, expense")
    category: str = Field(..., description="类别")
    subcategory: Optional[str] = Field(None, description="子类别")
    amount: int = Field(..., description="金额（分）")
    description: Optional[str] = Field(None, description="描述")
    reference_id: Optional[str] = Field(None, description="关联ID")
    payment_method: Optional[str] = Field(None, description="支付方式")


class BudgetCreate(BaseModel):
    store_id: str = Field(..., description="门店ID")
    year: int = Field(..., description="年份")
    month: int = Field(..., ge=1, le=12, description="月份")
    category: str = Field(..., description="类别")
    budgeted_amount: int = Field(..., description="预算金额（分）")
    notes: Optional[str] = Field(None, description="备注")


@router.post("/transactions")
async def create_transaction(
    data: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("finance:write")),
):
    """创建财务交易记录"""
    service = get_finance_service(db)
    transaction_data = data.dict()
    transaction_data["created_by"] = current_user.id
    return await service.create_transaction(transaction_data)


@router.get("/transactions")
async def get_transactions(
    store_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    transaction_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取财务交易记录列表"""
    service = get_finance_service(db)
    return await service.get_transactions(
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        skip=skip,
        limit=limit,
    )


@router.get("/reports/income-statement")
async def get_income_statement(
    store_id: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取损益表"""
    service = get_finance_service(db)
    return await service.generate_income_statement(store_id, start_date, end_date)


@router.get("/reports/cash-flow")
async def get_cash_flow(
    store_id: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取现金流量表"""
    service = get_finance_service(db)
    return await service.generate_cash_flow(store_id, start_date, end_date)


@router.post("/budgets")
async def create_budget(
    data: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("finance:write")),
):
    """创建预算"""
    service = get_finance_service(db)
    budget_data = data.dict()
    budget_data["created_by"] = current_user.id
    return await service.create_budget(budget_data)


@router.get("/budgets/analysis")
async def get_budget_analysis(
    store_id: str = Query(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取预算分析"""
    service = get_finance_service(db)
    return await service.get_budget_analysis(store_id, year, month)


@router.get("/metrics")
async def get_financial_metrics(
    store_id: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取财务指标"""
    service = get_finance_service(db)
    return await service.get_financial_metrics(store_id, start_date, end_date)
