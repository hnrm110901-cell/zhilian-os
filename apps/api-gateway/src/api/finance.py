"""
财务管理API
"""
from typing import Optional
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from src.core.database import get_db
from src.core.dependencies import get_current_active_user, require_permission
from src.services.finance_service import get_finance_service
from src.services.report_export_service import report_export_service
from src.core.neural_symbolic_guardrails import guardrails, AIProposal, GuardrailResult
try:
    from src.services.pdf_report_service import pdf_report_service
    PDF_AVAILABLE = True
except ImportError:
    pdf_report_service = None
    PDF_AVAILABLE = False
from src.models import User, FinancialTransaction

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
    transaction_data = data.model_dump()
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
    current_user: User = Depends(get_current_active_user),
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
    current_user: User = Depends(get_current_active_user),
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
    current_user: User = Depends(get_current_active_user),
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
    budget_data = data.model_dump()
    budget_data["created_by"] = current_user.id
    return await service.create_budget(budget_data)


@router.get("/budgets/analysis")
async def get_budget_analysis(
    store_id: str = Query(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
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
    current_user: User = Depends(get_current_active_user),
):
    """获取财务指标"""
    service = get_finance_service(db)
    return await service.get_financial_metrics(store_id, start_date, end_date)


@router.get("/reports/export")
async def export_report(
    report_type: str = Query(..., description="报表类型: income_statement, cash_flow, transactions"),
    format: str = Query("csv", description="导出格式: csv, pdf, xlsx"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    store_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    导出财务报表

    支持的报表类型:
    - income_statement: 损益表
    - cash_flow: 现金流量表
    - transactions: 交易明细

    支持的格式:
    - csv: CSV格式
    - pdf: PDF格式
    - xlsx: Excel格式
    """
    try:
        from datetime import datetime
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        if format == "csv":
            content = await report_export_service.export_to_csv(
                report_type=report_type,
                start_date=start_datetime,
                end_date=end_datetime,
                store_id=store_id,
                db=db
            )

            # 生成文件名
            filename = f"{report_type}_{start_date}_{end_date}.csv"

            return Response(
                content=content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
        elif format == "pdf":
            # Check if PDF is available
            if not PDF_AVAILABLE:
                raise HTTPException(
                    status_code=501,
                    detail="PDF导出功能不可用，请安装reportlab库"
                )

            # 获取报表数据
            service = get_finance_service(db)

            if report_type == "income_statement":
                data = await service.generate_income_statement(
                    store_id=str(store_id) if store_id else "STORE001",
                    start_date=start_date,
                    end_date=end_date
                )
                content = pdf_report_service.generate_income_statement_pdf(
                    data, start_datetime, end_datetime
                )
            elif report_type == "cash_flow":
                data = await service.generate_cash_flow(
                    store_id=str(store_id) if store_id else "STORE001",
                    start_date=start_date,
                    end_date=end_date
                )
                content = pdf_report_service.generate_cash_flow_pdf(
                    data, start_datetime, end_datetime
                )
            else:
                raise HTTPException(status_code=400, detail=f"PDF格式不支持报表类型: {report_type}")

            # 生成文件名
            filename = f"{report_type}_{start_date}_{end_date}.pdf"

            return Response(
                content=content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
        elif format == "xlsx":
            content = await report_export_service.export_to_xlsx(
                report_type=report_type,
                start_date=start_datetime,
                end_date=end_datetime,
                store_id=store_id,
                db=db
            )
            filename = f"{report_type}_{start_date}_{end_date}.xlsx"
            return Response(
                content=content,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        else:
            raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


# ==================== 退款校验 ====================

class RefundRequest(BaseModel):
    order_id: str = Field(..., description="订单ID")
    store_id: str = Field(..., description="门店ID")
    refund_amount: int = Field(..., description="退款金额（分）", gt=0)
    original_order_amount: int = Field(..., description="原订单金额（分）", gt=0)
    days_since_order: int = Field(..., description="下单至今天数", ge=0)
    customer_id: str = Field(..., description="顾客ID")
    reason: Optional[str] = Field(None, description="退款原因")


class RefundResponse(BaseModel):
    approved: bool
    requires_human_approval: bool
    violations: list
    escalation_reason: Optional[str]
    message: str


@router.post("/refunds/validate", response_model=RefundResponse)
async def validate_refund(
    req: RefundRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    退款前置校验（Guardrails）

    在实际退款前调用此接口，系统会通过符号规则引擎校验：
    - REF_001: 退款金额不可超过原订单金额
    - REF_002: 退款申请必须在有效期内（默认7天）
    - REF_003: 单日退款总额不可超过当日营收20%
    - REF_004: 单笔超阈值需人工审批（默认500元）
    - REF_005: 同一顾客24小时内退款次数上限（默认3次）
    """
    import uuid

    # 构建 AI 提案（此处退款申请视为"提案"送入符号校验层）
    proposal = AIProposal(
        proposal_id=str(uuid.uuid4()),
        proposal_type="refund",
        content={
            "refund_amount": req.refund_amount,
            "days_since_order": req.days_since_order,
        },
        confidence=1.0,
        reasoning="用户发起退款申请",
        created_at=datetime.utcnow(),
    )

    # 从 DB 查询真实业务上下文，确保 REF_003/REF_005 规则有效触发
    today = datetime.utcnow().date()
    yesterday_dt = datetime.utcnow() - timedelta(hours=24)

    daily_revenue = (await db.execute(
        select(func.sum(FinancialTransaction.amount)).where(
            and_(
                FinancialTransaction.store_id == req.store_id,
                FinancialTransaction.transaction_date == today,
                FinancialTransaction.transaction_type == "income",
            )
        )
    )).scalar() or 0

    daily_refund_total = (await db.execute(
        select(func.sum(FinancialTransaction.amount)).where(
            and_(
                FinancialTransaction.store_id == req.store_id,
                FinancialTransaction.transaction_date == today,
                FinancialTransaction.category == "refund",
            )
        )
    )).scalar() or 0

    # 顾客24h退款次数：统计当日该门店退款流水中 reference_id 匹配顾客的记录
    customer_refund_count_24h = (await db.execute(
        select(func.count()).select_from(FinancialTransaction).where(
            and_(
                FinancialTransaction.store_id == req.store_id,
                FinancialTransaction.category == "refund",
                FinancialTransaction.reference_id == req.customer_id,
                FinancialTransaction.transaction_date >= yesterday_dt.date(),
            )
        )
    )).scalar() or 0

    context = {
        "original_order_amount": req.original_order_amount,
        "daily_revenue": daily_revenue,
        "daily_refund_total": daily_refund_total,
        "customer_refund_count_24h": customer_refund_count_24h,
    }

    result: GuardrailResult = guardrails.validate_proposal(proposal, context)

    violations_out = [
        {"rule_id": v.rule_id, "rule_name": v.rule_name,
         "severity": v.severity, "recommendation": v.recommendation}
        for v in result.violations
    ]

    if result.violations and any(v.severity == "critical" for v in result.violations):
        message = "退款被拦截，存在严重违规"
    elif result.requires_human_approval:
        message = "退款需人工审批后方可执行"
    else:
        message = "退款校验通过，可执行退款"

    return RefundResponse(
        approved=result.approved,
        requires_human_approval=result.requires_human_approval,
        violations=violations_out,
        escalation_reason=result.escalation_reason,
        message=message,
    )
