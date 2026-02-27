"""
业财税资金一体化（FCT）REST API

- POST /events 业财事件接入
- GET  /vouchers 凭证列表
- GET  /vouchers/{id} 凭证详情
- GET  /ledger/balances 总账余额（占位）
- GET  /reports/* 业财报表（占位）
"""
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.database import get_db
from src.core.dependencies import get_current_active_user, require_permission
from src.core.permissions import Permission
from src.models.user import User
from src.services.fct_service import fct_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ---------- Request/Response 模型 ----------


class PaymentItem(BaseModel):
    method: str
    amount: int


class FctEventPayloadStoreDaily(BaseModel):
    store_id: str
    biz_date: str
    total_sales: int = 0
    total_sales_tax: int = 0
    payment_breakdown: List[Dict[str, Any]] = []
    discounts: int = 0
    refunds: int = 0


class FctEventRequest(BaseModel):
    """业财事件入参（与技术方案契约一致）"""
    event_type: str = Field(..., description="事件类型")
    event_id: Optional[str] = Field(None, description="幂等 id，不传则服务端生成")
    occurred_at: Optional[str] = Field(None, description="发生时间 ISO8601")
    source_system: str = Field("zhilian_os", description="来源系统")
    source_id: Optional[str] = None
    tenant_id: str = Field(..., description="租户 id")
    entity_id: str = Field(..., description="主体/门店 id")
    payload: Dict[str, Any] = Field(..., description="事件载荷")


class VoucherLineResponse(BaseModel):
    id: str
    line_no: int
    account_code: str
    account_name: Optional[str]
    debit: float
    credit: float
    description: Optional[str]

    class Config:
        from_attributes = True


class VoucherResponse(BaseModel):
    id: str
    voucher_no: str
    tenant_id: str
    entity_id: str
    biz_date: date
    event_type: Optional[str]
    event_id: Optional[str]
    status: str
    description: Optional[str]
    lines: List[VoucherLineResponse] = []

    class Config:
        from_attributes = True


class ManualVoucherLineBody(BaseModel):
    account_code: str
    account_name: Optional[str] = None
    debit: float = 0
    credit: float = 0
    auxiliary: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


class BudgetCheckOccupyBody(BaseModel):
    budget_type: Optional[str] = "period"
    period: Optional[str] = None
    category: Optional[str] = None
    amount_to_use: Optional[float] = None
    amount: Optional[float] = None
    entity_id: Optional[str] = None


class ManualVoucherBody(BaseModel):
    tenant_id: str
    entity_id: str
    biz_date: date
    description: Optional[str] = None
    lines: List[ManualVoucherLineBody]
    attachments: Optional[Dict[str, Any]] = None
    budget_check: Optional[BudgetCheckOccupyBody] = None
    budget_occupy: Optional[BudgetCheckOccupyBody] = None


class VoucherStatusBody(BaseModel):
    status: str = Field(..., description="posted | rejected | approved")
    budget_check: Optional[BudgetCheckOccupyBody] = None
    budget_occupy: Optional[BudgetCheckOccupyBody] = None


class CashTransactionBody(BaseModel):
    tenant_id: str
    entity_id: str
    tx_date: date
    amount: float = Field(..., gt=0)
    direction: str = Field(..., description="in | out")
    description: Optional[str] = None
    ref_id: Optional[str] = None
    generate_voucher: bool = False
    budget_check: Optional[BudgetCheckOccupyBody] = None
    budget_occupy: Optional[BudgetCheckOccupyBody] = None


def _voucher_to_response(v, lines: Optional[List] = None) -> Dict[str, Any]:
    return {
        "id": str(v.id),
        "voucher_no": v.voucher_no,
        "tenant_id": v.tenant_id,
        "entity_id": v.entity_id,
        "biz_date": v.biz_date.isoformat() if v.biz_date else None,
        "event_type": v.event_type,
        "event_id": v.event_id,
        "status": v.status.value if hasattr(v.status, "value") else v.status,
        "description": v.description,
        "lines": [
            {
                "id": str(l.id),
                "line_no": l.line_no,
                "account_code": l.account_code,
                "account_name": l.account_name,
                "debit": float(l.debit or 0),
                "credit": float(l.credit or 0),
                "description": l.description,
            }
            for l in (lines or getattr(v, "lines", []))
        ],
    }


# ---------- 端点 ----------


@router.post("/events", summary="业财事件接入")
async def post_events(
    body: FctEventRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """
    接收业财事件，驱动凭证规则引擎生成凭证。
    与《业财税资金一体化技术方案》契约一致，支持幂等。
    """
    raw = body.model_dump()
    return await fct_service.ingest_event(session, raw)


@router.get("/vouchers", summary="凭证列表")
async def get_vouchers(
    tenant_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """分页查询凭证列表。"""
    result = await fct_service.get_vouchers(
        session,
        tenant_id=tenant_id,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        skip=skip,
        limit=limit,
    )
    items = [_voucher_to_response(v) for v in result["items"]]
    return {"total": result["total"], "skip": result["skip"], "limit": result["limit"], "items": items}


@router.get("/vouchers/{voucher_id}", summary="凭证详情")
async def get_voucher(
    voucher_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """凭证详情（含分录）。"""
    try:
        voucher = await fct_service.get_voucher_by_id(session, voucher_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid voucher_id: {e}")
    if not voucher:
        raise HTTPException(status_code=404, detail="voucher not found")
    return _voucher_to_response(voucher, list(voucher.lines))


@router.post("/vouchers", summary="手工/调整凭证创建", status_code=201)
async def create_manual_voucher(
    body: ManualVoucherBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """创建手工凭证：借贷必平，来源为 manual。可选 budget_check/budget_occupy 与预算联动。"""
    try:
        lines_dict = [{"account_code": l.account_code, "account_name": l.account_name, "debit": l.debit, "credit": l.credit, "auxiliary": l.auxiliary, "description": l.description} for l in body.lines]
        budget_check = body.budget_check.model_dump() if body.budget_check else None
        budget_occupy = body.budget_occupy.model_dump() if body.budget_occupy else None
        if budget_occupy and (budget_occupy.get("amount_to_use") is None and budget_occupy.get("amount") is None):
            budget_occupy["amount_to_use"] = sum(max(l.debit, l.credit) for l in body.lines)
        return await fct_service.create_manual_voucher(
            session, tenant_id=body.tenant_id, entity_id=body.entity_id, biz_date=body.biz_date, lines=lines_dict, description=body.description, attachments=body.attachments, budget_check=budget_check, budget_occupy=budget_occupy
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/vouchers/{voucher_id}/status", summary="凭证过账/状态变更")
async def update_voucher_status(
    voucher_id: str,
    body: VoucherStatusBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """凭证状态变更：draft→posted/rejected，pending→approved/rejected，approved→posted。过账时可选 budget_check/budget_occupy。"""
    try:
        budget_check = body.budget_check.model_dump() if body.budget_check else None
        budget_occupy = body.budget_occupy.model_dump() if body.budget_occupy else None
        return await fct_service.update_voucher_status(session, voucher_id=voucher_id, target_status=body.status, budget_check=budget_check, budget_occupy=budget_occupy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/vouchers/{voucher_id}/void", summary="凭证作废")
async def void_voucher(
    voucher_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """作废凭证（仅草稿或已过账），作废后不参与总账。"""
    try:
        return await fct_service.void_voucher(session, voucher_id=voucher_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/vouchers/{voucher_id}/red-flush", summary="凭证红冲", status_code=201)
async def red_flush_voucher(
    voucher_id: str,
    biz_date: Optional[date] = Query(None, description="红字凭证业务日期，默认同原凭证"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """根据已过账凭证生成红字凭证（借贷相反），新凭证为草稿。"""
    try:
        return await fct_service.red_flush_voucher(session, voucher_id=voucher_id, biz_date=biz_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ledger/balances", summary="总账余额")
async def get_ledger_balances(
    tenant_id: str = Query(..., description="租户 id"),
    entity_id: Optional[str] = Query(None),
    as_of_date: Optional[date] = Query(None),
    period: Optional[str] = Query(None, description="所属期 YYYYMM，与 as_of_date 二选一，传则取该月月末余额"),
    posted_only: bool = Query(True, description="仅已过账凭证参与汇总"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """总账余额：按科目汇总（默认仅已过账凭证）；支持 period=YYYYMM 按期间取数。"""
    try:
        return await fct_service.get_ledger_balances(
            session, tenant_id=tenant_id, entity_id=entity_id, as_of_date=as_of_date, period=period, posted_only=posted_only
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ledger/entries", summary="总账明细")
async def get_ledger_entries(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: Optional[str] = Query(None, description="所属期 YYYYMM，传则覆盖 start_date/end_date 为该月"),
    account_code: Optional[str] = Query(None),
    posted_only: bool = Query(True, description="仅已过账凭证"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """总账明细：按科目+主体+日期范围返回每条分录；支持 period=YYYYMM。"""
    try:
        return await fct_service.get_ledger_entries(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=start_date, end_date=end_date, period=period, account_code=account_code, posted_only=posted_only, skip=skip, limit=limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/periods", summary="会计期间列表")
async def list_periods(
    tenant_id: str = Query(...),
    start_key: Optional[str] = Query(None, description="起始期间 202502"),
    end_key: Optional[str] = Query(None, description="结束期间"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """会计期间列表，按 period_key 排序；可选 start_key/end_key 范围。"""
    return await fct_service.list_periods(session, tenant_id=tenant_id, start_key=start_key, end_key=end_key)


@router.post("/periods/{period_key}/close", summary="期间结账")
async def close_period(
    period_key: str,
    tenant_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """结账：该期间内不得有草稿凭证；结账后该期间禁止新增/过账/作废/红冲。"""
    try:
        return await fct_service.close_period(session, tenant_id=tenant_id, period_key=period_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/periods/{period_key}/reopen", summary="期间反结账")
async def reopen_period(
    period_key: str,
    tenant_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """反结账：将期间状态改回 open。"""
    try:
        return await fct_service.reopen_period(session, tenant_id=tenant_id, period_key=period_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reports/{report_type}", summary="业财报表")
async def get_reports(
    report_type: str,
    tenant_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: Optional[str] = Query(None, description="所属期 YYYYMM，仅 consolidated 时必填"),
    group_by: Optional[str] = Query("day", description="趋势分组：day|week|month|quarter；consolidated 时为 entity|all"),
    compare_type: Optional[str] = Query("yoy", description="同比环比：yoy|mom|qoq，仅 comparison 时有效"),
    granularity: Optional[str] = Query("month", description="计划对比粒度：day|week|month|quarter，仅 plan_vs_actual 时有效"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """业财报表：period_summary/aggregate/trend/by_entity/by_region/comparison/plan_vs_actual/consolidated。"""
    if report_type == "consolidated":
        if not tenant_id or not period:
            raise HTTPException(status_code=400, detail="consolidated 报表需传 tenant_id 与 period(YYYYMM)")
        try:
            return await fct_service.get_report_consolidated(
                session, tenant_id=tenant_id, period=period, group_by=group_by
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if not tenant_id:
        params = {"tenant_id": tenant_id, "entity_id": entity_id, "start_date": start_date, "end_date": end_date}
        return await fct_service.get_reports_stub(report_type, params)
    # 支持 period=YYYYMM：推导 start_date/end_date 为该月首末
    _start, _end = start_date, end_date
    if period and len(period) == 6:
        try:
            _start = date(int(period[:4]), int(period[4:6]), 1)
            from calendar import monthrange
            _end = date(int(period[:4]), int(period[4:6]), monthrange(int(period[:4]), int(period[4:6]))[1])
        except (ValueError, TypeError):
            pass
    if report_type == "period_summary":
        return await fct_service.get_report_period_summary(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=_start, end_date=_end
        )
    if report_type == "aggregate":
        return await fct_service.get_report_aggregate(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=_start, end_date=_end
        )
    if report_type == "trend":
        return await fct_service.get_report_trend(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=_start, end_date=_end, group_by=group_by or "day"
        )
    if report_type == "by_entity":
        return await fct_service.get_report_by_entity(
            session, tenant_id=tenant_id, start_date=_start, end_date=_end
        )
    if report_type == "by_region":
        return await fct_service.get_report_by_region(
            session, tenant_id=tenant_id, start_date=_start, end_date=_end
        )
    if report_type == "comparison":
        return await fct_service.get_report_comparison(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=_start, end_date=_end, compare_type=compare_type or "yoy"
        )
    if report_type == "plan_vs_actual":
        return await fct_service.get_plan_vs_actual(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=_start, end_date=_end, granularity=granularity or "month"
        )
    params = {"tenant_id": tenant_id, "entity_id": entity_id, "start_date": start_date, "end_date": end_date}
    return await fct_service.get_reports_stub(report_type, params)


# ---------- 年度计划 ----------


class PlanUpsertBody(BaseModel):
    tenant_id: str
    plan_year: int
    targets: Dict[str, float]  # revenue, cost, gross_margin, output_tax, input_tax, net_tax, cash_in, cash_out, voucher_count
    entity_id: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


@router.put("/plans", summary="年度计划 upsert")
async def upsert_plan(
    body: PlanUpsertBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """按租户+主体+年度唯一；targets 为业财税资金年度目标。"""
    return await fct_service.upsert_plan(
        session, tenant_id=body.tenant_id, plan_year=body.plan_year, targets=body.targets, entity_id=body.entity_id, extra=body.extra
    )


@router.get("/plans", summary="查询年度计划")
async def get_plan(
    tenant_id: str = Query(...),
    plan_year: int = Query(...),
    entity_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """entity_id 为空则查租户级计划。"""
    out = await fct_service.get_plan(session, tenant_id=tenant_id, plan_year=plan_year, entity_id=entity_id)
    if out is None:
        return {"plan": None, "message": "未配置该年度计划"}
    return {"plan": out}


# ---------- 主数据 ----------


class MasterUpsertBody(BaseModel):
    tenant_id: str
    code: str
    name: str
    extra: Optional[Dict[str, Any]] = None


@router.put("/master/{master_type}", summary="主数据 upsert")
async def upsert_master(
    master_type: str,
    body: MasterUpsertBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """主数据类型：store / supplier / account / bank_account"""
    return await fct_service.upsert_master(
        session, tenant_id=body.tenant_id, master_type=master_type, code=body.code, name=body.name, extra=body.extra
    )


@router.get("/master", summary="主数据列表")
async def list_master(
    tenant_id: str = Query(...),
    master_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_master(session, tenant_id=tenant_id, master_type=master_type, skip=skip, limit=limit)


# ---------- 资金流水与对账 ----------


@router.get("/cash/transactions", summary="资金流水")
async def get_cash_transactions(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_cash_transactions(
        session, tenant_id=tenant_id, entity_id=entity_id, start_date=start_date, end_date=end_date, status=status, skip=skip, limit=limit
    )


@router.post("/cash/transactions", summary="资金收付款/内部划拨录入", status_code=201)
async def create_cash_transaction(
    body: CashTransactionBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """录入一笔收款或付款；可选同时生成手工凭证；可选 budget_check/budget_occupy。"""
    try:
        budget_check = body.budget_check.model_dump() if body.budget_check else None
        budget_occupy = body.budget_occupy.model_dump() if body.budget_occupy else None
        return await fct_service.create_cash_transaction(
            session, tenant_id=body.tenant_id, entity_id=body.entity_id, tx_date=body.tx_date, amount=body.amount, direction=body.direction, description=body.description, ref_id=body.ref_id, generate_voucher=body.generate_voucher, budget_check=budget_check, budget_occupy=budget_occupy
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CashMatchBody(BaseModel):
    match_id: Optional[str] = Field(None, description="匹配标识（银行流水 id 等）；不传或空则取消匹配")
    match_type: Optional[str] = Field(None, description="匹配类型：bank_receipt / business / manual")
    remark: Optional[str] = None


@router.patch("/cash/transactions/{transaction_id}/match", summary="资金流水勾对/取消勾对")
async def match_cash_transaction(
    transaction_id: str,
    body: CashMatchBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """勾对：body.match_id 有值则标记为已匹配；无则取消匹配。仅 pending 可勾对，仅 matched 可取消。"""
    try:
        return await fct_service.match_cash_transaction(
            session, transaction_id=transaction_id, match_id=body.match_id, match_type=body.match_type, remark=body.remark
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CashTransactionsImportBody(BaseModel):
    tenant_id: str
    entity_id: str
    items: List[Dict[str, Any]] = Field(..., description="[{tx_date, amount, direction, ref_id?, description?}]")
    ref_type: Optional[str] = Field("bank", description="bank / business")
    skip_duplicate_ref_id: Optional[bool] = True


@router.post("/cash/transactions/import", summary="批量导入资金流水", status_code=201)
async def import_cash_transactions(
    body: CashTransactionsImportBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """批量导入银行/业务流水；按 ref_id 去重（可选）。"""
    try:
        if not body.items:
            raise ValueError("items 不能为空")
        return await fct_service.import_cash_transactions(
            session,
            tenant_id=body.tenant_id,
            entity_id=body.entity_id,
            items=body.items,
            ref_type=body.ref_type or "bank",
            skip_duplicate_ref_id=body.skip_duplicate_ref_id is not False,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cash/reconciliation", summary="资金对账状态")
async def get_cash_reconciliation(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.get_cash_reconciliation_status(session, tenant_id=tenant_id, entity_id=entity_id)


# ---------- 税务（占位） ----------


@router.get("/tax/invoices", summary="税务发票列表")
async def get_tax_invoices(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    invoice_type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_tax_invoices(
        session, tenant_id=tenant_id, entity_id=entity_id, invoice_type=invoice_type, start_date=start_date, end_date=end_date, skip=skip, limit=limit
    )


class TaxInvoiceCreateBody(BaseModel):
    tenant_id: str
    entity_id: str
    invoice_type: str = Field(..., description="output | input")
    invoice_no: Optional[str] = None
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    invoice_date: Optional[date] = None
    status: Optional[str] = "draft"
    extra: Optional[Dict[str, Any]] = None


class TaxInvoiceUpdateBody(BaseModel):
    invoice_no: Optional[str] = None
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    invoice_date: Optional[date] = None
    status: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


@router.post("/tax/invoices", summary="发票登记", status_code=201)
async def create_tax_invoice(
    body: TaxInvoiceCreateBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """登记进项/销项发票，同租户下 invoice_type+invoice_no 唯一。"""
    try:
        return await fct_service.create_tax_invoice(
            session, tenant_id=body.tenant_id, entity_id=body.entity_id, invoice_type=body.invoice_type, invoice_no=body.invoice_no, amount=body.amount, tax_amount=body.tax_amount, invoice_date=body.invoice_date, status=body.status or "draft", extra=body.extra
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/tax/invoices/{invoice_id}", summary="更新发票")
async def update_tax_invoice(
    invoice_id: str,
    body: TaxInvoiceUpdateBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """更新发票信息（关联凭证用 POST /invoices/link）。"""
    try:
        return await fct_service.update_tax_invoice(
            session, invoice_id=invoice_id, invoice_no=body.invoice_no, amount=body.amount, tax_amount=body.tax_amount, invoice_date=body.invoice_date, status=body.status, extra=body.extra
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tax/declarations", summary="税务申报列表")
async def get_tax_declarations(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    tax_type: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_tax_declarations(
        session, tenant_id=tenant_id, entity_id=entity_id, tax_type=tax_type, period=period, skip=skip, limit=limit
    )


@router.get("/tax/declarations/draft", summary="税务申报表草稿（按总账取数）")
async def get_tax_declaration_draft(
    tenant_id: str = Query(...),
    tax_type: str = Query("vat", description="税种：vat"),
    period: str = Query(..., description="所属期 YYYYMM"),
    entity_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """从总账已过账凭证取数生成申报草稿（增值税销项/进项/应纳税额）。"""
    try:
        return await fct_service.get_tax_declaration_draft(
            session, tenant_id=tenant_id, tax_type=tax_type, period=period, entity_id=entity_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- Phase 4：费控/备用金 ----------
class PettyCashUpsertBody(BaseModel):
    tenant_id: str
    entity_id: str
    cash_type: str  # fixed / temporary
    amount_limit: float
    status: Optional[str] = "active"
    extra: Optional[Dict[str, Any]] = None


@router.put("/petty-cash", summary="备用金主档 upsert")
async def upsert_petty_cash(
    body: PettyCashUpsertBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    return await fct_service.upsert_petty_cash(
        session, tenant_id=body.tenant_id, entity_id=body.entity_id, cash_type=body.cash_type, amount_limit=body.amount_limit, status=body.status or "active", extra=body.extra
    )


@router.get("/petty-cash", summary="备用金主档列表")
async def list_petty_cash(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    cash_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_petty_cash(session, tenant_id=tenant_id, entity_id=entity_id, cash_type=cash_type, skip=skip, limit=limit)


class PettyCashRecordBody(BaseModel):
    petty_cash_id: str
    record_type: str  # apply / offset / repay
    amount: float
    biz_date: date
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    description: Optional[str] = None


@router.post("/petty-cash/records", summary="备用金流水：申请/冲销/还款")
async def add_petty_cash_record(
    body: PettyCashRecordBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    return await fct_service.add_petty_cash_record(
        session, petty_cash_id=body.petty_cash_id, record_type=body.record_type, amount=body.amount, biz_date=body.biz_date, ref_type=body.ref_type, ref_id=body.ref_id, description=body.description
    )


@router.get("/petty-cash/{petty_cash_id}/records", summary="备用金流水列表")
async def list_petty_cash_records(
    petty_cash_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_petty_cash_records(session, petty_cash_id=petty_cash_id, start_date=start_date, end_date=end_date, skip=skip, limit=limit)


# ---------- Phase 4：预算占位 ----------
class BudgetUpsertBody(BaseModel):
    tenant_id: str
    budget_type: str  # project / period
    period: str
    category: str
    amount: float
    entity_id: Optional[str] = ""
    status: Optional[str] = "active"
    extra: Optional[Dict[str, Any]] = None


@router.put("/budgets", summary="预算 upsert")
async def upsert_budget(
    body: BudgetUpsertBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    return await fct_service.upsert_budget(
        session, tenant_id=body.tenant_id, budget_type=body.budget_type, period=body.period, category=body.category, amount=body.amount, entity_id=body.entity_id or "", status=body.status or "active", extra=body.extra
    )


@router.get("/budgets/check", summary="预算占用校验")
async def check_budget(
    tenant_id: str = Query(...),
    budget_type: str = Query(...),
    period: str = Query(...),
    category: str = Query(...),
    amount_to_use: float = Query(...),
    entity_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.check_budget(session, tenant_id=tenant_id, budget_type=budget_type, period=period, category=category, amount_to_use=amount_to_use, entity_id=entity_id or "")


class BudgetOccupyBody(BaseModel):
    tenant_id: str
    budget_type: str
    period: str
    category: str
    amount: float
    entity_id: Optional[str] = ""


@router.post("/budgets/occupy", summary="预算占用")
async def occupy_budget(
    body: BudgetOccupyBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    return await fct_service.occupy_budget(
        session, tenant_id=body.tenant_id, budget_type=body.budget_type, period=body.period, category=body.category, amount=body.amount, entity_id=body.entity_id or ""
    )


class BudgetControlBody(BaseModel):
    tenant_id: str
    entity_id: Optional[str] = ""
    budget_type: Optional[str] = "period"
    category: Optional[str] = ""
    enforce_check: bool = False
    auto_occupy: bool = False


@router.put("/budgets/control", summary="预算控制配置 upsert")
async def upsert_budget_control(
    body: BudgetControlBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    """按 (tenant_id, entity_id, budget_type, category) 唯一；enforce_check=true 时制单/过账/付款前强制校验预算，auto_occupy=true 时成功后自动占用。"""
    return await fct_service.upsert_budget_control(
        session,
        tenant_id=body.tenant_id,
        entity_id=body.entity_id or "",
        budget_type=body.budget_type or "period",
        category=body.category or "",
        enforce_check=body.enforce_check,
        auto_occupy=body.auto_occupy,
    )


@router.get("/budgets/control", summary="预算控制配置列表")
async def list_budget_controls(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    budget_type: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_budget_controls(session, tenant_id=tenant_id, entity_id=entity_id, budget_type=budget_type)


# ---------- Phase 4：发票闭环 ----------
class InvoiceLinkBody(BaseModel):
    invoice_id: str
    voucher_id: str


@router.post("/invoices/link", summary="发票与凭证关联")
async def link_invoice_to_voucher(
    body: InvoiceLinkBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    return await fct_service.link_invoice_to_voucher(session, invoice_id=body.invoice_id, voucher_id=body.voucher_id)


@router.get("/invoices/by-voucher/{voucher_id}", summary="按凭证查关联发票")
async def list_invoices_by_voucher(
    voucher_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.list_invoices_by_voucher(session, voucher_id=voucher_id)


@router.post("/invoices/{invoice_id}/verify", summary="发票验真占位")
async def verify_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    return await fct_service.verify_invoice_stub(session, invoice_id=invoice_id)


# ---------- Phase 4：审批流占位 ----------
class ApprovalCreateBody(BaseModel):
    tenant_id: str
    ref_type: str  # voucher / payment / expense
    ref_id: str
    step: Optional[int] = 1
    status: Optional[str] = "pending"
    extra: Optional[Dict[str, Any]] = None


@router.post("/approvals", summary="审批记录占位")
async def create_approval(
    body: ApprovalCreateBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_WRITE)),
) -> Dict[str, Any]:
    return await fct_service.create_approval_record(
        session, tenant_id=body.tenant_id, ref_type=body.ref_type, ref_id=body.ref_id, step=body.step or 1, status=body.status or "pending", extra=body.extra
    )


@router.get("/approvals/by-ref", summary="按业务单查审批记录")
async def get_approval_by_ref(
    tenant_id: str = Query(...),
    ref_type: str = Query(...),
    ref_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    return await fct_service.get_approval_by_ref(session, tenant_id=tenant_id, ref_type=ref_type, ref_id=ref_id)


@router.get("/status", summary="FCT 模块状态")
async def get_fct_status(
    current_user: User = Depends(require_permission(Permission.FCT_READ)),
) -> Dict[str, Any]:
    """返回业财税资金扩展模块状态（合并部署时可用）。"""
    from src.core.config import settings
    return {
        "enabled": getattr(settings, "FCT_ENABLED", False),
        "mode": getattr(settings, "FCT_MODE", "embedded"),
    }
