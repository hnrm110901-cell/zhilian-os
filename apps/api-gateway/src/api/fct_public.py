"""
业财税资金一体化（FCT）公开 API — 独立部署形态

与 fct.py 契约一致，但使用 API Key 认证（X-API-Key），不依赖智链OS 用户与权限。
用于独立服务部署时对外暴露；租户可通过请求体或 X-Tenant-Id 传递。
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.database import get_db
from src.services.fct_service import fct_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_db_fct():
    """独立部署时使用，不启用租户过滤，避免依赖 TenantContext。"""
    return get_db(enable_tenant_isolation=False)


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


async def verify_fct_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    """独立部署时 API Key 校验；FCT_API_KEY 为空则不校验（仅建议内网使用）。"""
    api_key = getattr(settings, "FCT_API_KEY", None) or ""
    if not api_key:
        return
    if not x_api_key or x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


# ---------- Request 模型（与 fct 一致） ----------


class FctEventRequest(BaseModel):
    event_type: str = Field(..., description="事件类型")
    event_id: Optional[str] = Field(None, description="幂等 id")
    occurred_at: Optional[str] = None
    source_system: str = Field("external", description="来源系统")
    source_id: Optional[str] = None
    tenant_id: str = Field(..., description="租户 id")
    entity_id: str = Field(..., description="主体/门店 id")
    payload: Dict[str, Any] = Field(..., description="事件载荷")


# ---------- 端点（与 fct 契约一致） ----------


@router.post("/events", summary="业财事件接入（独立形态）")
async def post_events(
    body: FctEventRequest,
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """接收业财事件，驱动凭证规则引擎。契约与合并形态一致，支持幂等。"""
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
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
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
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    try:
        voucher = await fct_service.get_voucher_by_id(session, voucher_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid voucher_id: {e}")
    if not voucher:
        raise HTTPException(status_code=404, detail="voucher not found")
    return _voucher_to_response(voucher, list(voucher.lines))


@router.post("/vouchers", summary="手工/调整凭证创建", status_code=201)
async def create_manual_voucher(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """创建手工凭证：借贷必平。body: tenant_id, entity_id, biz_date, lines[], description?, attachments?, budget_check?, budget_occupy?"""
    try:
        biz_date = body.get("biz_date")
        if isinstance(biz_date, str):
            biz_date = date.fromisoformat(biz_date)
        return await fct_service.create_manual_voucher(
            session, tenant_id=body["tenant_id"], entity_id=body["entity_id"], biz_date=biz_date, lines=body["lines"], description=body.get("description"), attachments=body.get("attachments"), budget_check=body.get("budget_check"), budget_occupy=body.get("budget_occupy")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/vouchers/{voucher_id}/status", summary="凭证过账/状态变更")
async def update_voucher_status(
    voucher_id: str,
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """凭证状态变更。body: { status, budget_check?, budget_occupy? }"""
    try:
        return await fct_service.update_voucher_status(session, voucher_id=voucher_id, target_status=body["status"], budget_check=body.get("budget_check"), budget_occupy=body.get("budget_occupy"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/vouchers/{voucher_id}/void", summary="凭证作废")
async def void_voucher(
    voucher_id: str,
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """作废凭证（仅草稿或已过账）。"""
    try:
        return await fct_service.void_voucher(session, voucher_id=voucher_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/vouchers/{voucher_id}/red-flush", summary="凭证红冲", status_code=201)
async def red_flush_voucher(
    voucher_id: str,
    biz_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """根据已过账凭证生成红字凭证。"""
    try:
        return await fct_service.red_flush_voucher(session, voucher_id=voucher_id, biz_date=biz_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ledger/balances", summary="总账余额")
async def get_ledger_balances(
    tenant_id: str = Query(..., description="租户 id"),
    entity_id: Optional[str] = Query(None),
    as_of_date: Optional[date] = Query(None),
    period: Optional[str] = Query(None, description="所属期 YYYYMM，与 as_of_date 二选一"),
    posted_only: bool = Query(True, description="仅已过账凭证参与汇总"),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
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
    period: Optional[str] = Query(None, description="所属期 YYYYMM，传则覆盖 start_date/end_date"),
    account_code: Optional[str] = Query(None),
    posted_only: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    try:
        return await fct_service.get_ledger_entries(
            session, tenant_id=tenant_id, entity_id=entity_id, start_date=start_date, end_date=end_date, period=period, account_code=account_code, posted_only=posted_only, skip=skip, limit=limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/periods", summary="会计期间列表")
async def list_periods(
    tenant_id: str = Query(...),
    start_key: Optional[str] = Query(None),
    end_key: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_periods(session, tenant_id=tenant_id, start_key=start_key, end_key=end_key)


@router.post("/periods/{period_key}/close", summary="期间结账")
async def close_period(
    period_key: str,
    tenant_id: str = Query(...),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    try:
        return await fct_service.close_period(session, tenant_id=tenant_id, period_key=period_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/periods/{period_key}/reopen", summary="期间反结账")
async def reopen_period(
    period_key: str,
    tenant_id: str = Query(...),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    try:
        return await fct_service.reopen_period(session, tenant_id=tenant_id, period_key=period_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.upsert_master(
        session, tenant_id=body.tenant_id, master_type=master_type, code=body.code, name=body.name, extra=body.extra
    )


@router.get("/master", summary="主数据列表")
async def list_master(
    tenant_id: str = Query(...),
    master_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_master(session, tenant_id=tenant_id, master_type=master_type, skip=skip, limit=limit)


# ---------- 资金与税务 ----------


@router.get("/cash/transactions", summary="资金流水")
async def get_cash_transactions(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_cash_transactions(
        session, tenant_id=tenant_id, entity_id=entity_id, start_date=start_date, end_date=end_date, status=status, skip=skip, limit=limit
    )


@router.post("/cash/transactions", summary="资金收付款/内部划拨录入", status_code=201)
async def create_cash_transaction(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """录入一笔收款或付款。body: tenant_id, entity_id, tx_date, amount, direction, description?, ref_id?, generate_voucher?, budget_check?, budget_occupy?"""
    try:
        tx_date = body.get("tx_date")
        if isinstance(tx_date, str):
            tx_date = date.fromisoformat(tx_date)
        return await fct_service.create_cash_transaction(
            session, tenant_id=body["tenant_id"], entity_id=body["entity_id"], tx_date=tx_date, amount=float(body["amount"]), direction=body["direction"], description=body.get("description"), ref_id=body.get("ref_id"), generate_voucher=body.get("generate_voucher", False), budget_check=body.get("budget_check"), budget_occupy=body.get("budget_occupy")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/cash/transactions/{transaction_id}/match", summary="资金流水勾对/取消勾对")
async def match_cash_transaction(
    transaction_id: str,
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """body: match_id?（不传或空则取消匹配）, match_type?, remark?"""
    try:
        return await fct_service.match_cash_transaction(
            session, transaction_id=transaction_id, match_id=body.get("match_id"), match_type=body.get("match_type"), remark=body.get("remark")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cash/transactions/import", summary="批量导入资金流水", status_code=201)
async def import_cash_transactions(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """批量导入银行/业务流水。body: tenant_id, entity_id, items=[{tx_date, amount, direction, ref_id?, description?}], ref_type?=bank, skip_duplicate_ref_id?=true"""
    try:
        items = body.get("items") or []
        if not items:
            raise ValueError("items 不能为空")
        return await fct_service.import_cash_transactions(
            session,
            tenant_id=body["tenant_id"],
            entity_id=body["entity_id"],
            items=items,
            ref_type=body.get("ref_type") or "bank",
            skip_duplicate_ref_id=body.get("skip_duplicate_ref_id", True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cash/reconciliation", summary="资金对账状态")
async def get_cash_reconciliation(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.get_cash_reconciliation_status(session, tenant_id=tenant_id, entity_id=entity_id)


@router.get("/tax/invoices", summary="税务发票列表")
async def get_tax_invoices(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    invoice_type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_tax_invoices(
        session, tenant_id=tenant_id, entity_id=entity_id, invoice_type=invoice_type, start_date=start_date, end_date=end_date, skip=skip, limit=limit
    )


@router.post("/tax/invoices", summary="发票登记", status_code=201)
async def create_tax_invoice(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """body: tenant_id, entity_id, invoice_type(output|input), invoice_no?, amount?, tax_amount?, invoice_date?, status?, extra?"""
    try:
        inv_date = body.get("invoice_date")
        if isinstance(inv_date, str):
            inv_date = date.fromisoformat(inv_date)
        return await fct_service.create_tax_invoice(
            session, tenant_id=body["tenant_id"], entity_id=body["entity_id"], invoice_type=body["invoice_type"], invoice_no=body.get("invoice_no"), amount=body.get("amount"), tax_amount=body.get("tax_amount"), invoice_date=inv_date, status=body.get("status") or "draft", extra=body.get("extra")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/tax/invoices/{invoice_id}", summary="更新发票")
async def update_tax_invoice(
    invoice_id: str,
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """body: invoice_no?, amount?, tax_amount?, invoice_date?, status?, extra?"""
    try:
        inv_date = body.get("invoice_date")
        if isinstance(inv_date, str):
            inv_date = date.fromisoformat(inv_date)
        return await fct_service.update_tax_invoice(
            session, invoice_id=invoice_id, invoice_no=body.get("invoice_no"), amount=body.get("amount"), tax_amount=body.get("tax_amount"), invoice_date=inv_date, status=body.get("status"), extra=body.get("extra")
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
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
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
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """从总账已过账凭证取数生成申报草稿（如增值税销项/进项/应纳税额）。"""
    try:
        return await fct_service.get_tax_declaration_draft(
            session, tenant_id=tenant_id, tax_type=tax_type, period=period, entity_id=entity_id
        )
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
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """period_summary / aggregate / trend / by_entity / by_region / comparison / plan_vs_actual / consolidated。"""
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
    _start, _end = start_date, end_date
    if period and len(period) == 6:
        try:
            from calendar import monthrange
            _start = date(int(period[:4]), int(period[4:6]), 1)
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


@router.put("/plans", summary="年度计划 upsert")
async def upsert_plan(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """body: tenant_id, plan_year, targets (revenue/cost/...), entity_id 可选。"""
    return await fct_service.upsert_plan(
        session,
        tenant_id=body["tenant_id"],
        plan_year=body["plan_year"],
        targets=body.get("targets") or {},
        entity_id=body.get("entity_id"),
        extra=body.get("extra"),
    )


@router.get("/plans", summary="查询年度计划")
async def get_plan(
    tenant_id: str = Query(...),
    plan_year: int = Query(...),
    entity_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    out = await fct_service.get_plan(session, tenant_id=tenant_id, plan_year=plan_year, entity_id=entity_id)
    if out is None:
        return {"plan": None, "message": "未配置该年度计划"}
    return {"plan": out}


# ---------- Phase 4：费控/备用金 ----------
@router.put("/petty-cash", summary="备用金主档 upsert")
async def upsert_petty_cash(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.upsert_petty_cash(
        session, tenant_id=body["tenant_id"], entity_id=body["entity_id"], cash_type=body["cash_type"], amount_limit=float(body["amount_limit"]), status=body.get("status") or "active", extra=body.get("extra")
    )


@router.get("/petty-cash", summary="备用金主档列表")
async def list_petty_cash(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    cash_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_petty_cash(session, tenant_id=tenant_id, entity_id=entity_id, cash_type=cash_type, skip=skip, limit=limit)


@router.post("/petty-cash/records", summary="备用金流水：申请/冲销/还款")
async def add_petty_cash_record(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    biz_date = body.get("biz_date")
    if isinstance(biz_date, str):
        biz_date = date.fromisoformat(biz_date)
    return await fct_service.add_petty_cash_record(
        session, petty_cash_id=body["petty_cash_id"], record_type=body["record_type"], amount=float(body["amount"]), biz_date=biz_date, ref_type=body.get("ref_type"), ref_id=body.get("ref_id"), description=body.get("description")
    )


@router.get("/petty-cash/{petty_cash_id}/records", summary="备用金流水列表")
async def list_petty_cash_records(
    petty_cash_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_petty_cash_records(session, petty_cash_id=petty_cash_id, start_date=start_date, end_date=end_date, skip=skip, limit=limit)


# ---------- Phase 4：预算占位 ----------
@router.put("/budgets", summary="预算 upsert")
async def upsert_budget(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.upsert_budget(
        session, tenant_id=body["tenant_id"], budget_type=body["budget_type"], period=body["period"], category=body["category"], amount=float(body["amount"]), entity_id=body.get("entity_id") or "", status=body.get("status") or "active", extra=body.get("extra")
    )


@router.get("/budgets/check", summary="预算占用校验")
async def check_budget(
    tenant_id: str = Query(...),
    budget_type: str = Query(...),
    period: str = Query(...),
    category: str = Query(...),
    amount_to_use: float = Query(...),
    entity_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.check_budget(session, tenant_id=tenant_id, budget_type=budget_type, period=period, category=category, amount_to_use=amount_to_use, entity_id=entity_id or "")


@router.post("/budgets/occupy", summary="预算占用")
async def occupy_budget(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.occupy_budget(
        session, tenant_id=body["tenant_id"], budget_type=body["budget_type"], period=body["period"], category=body["category"], amount=float(body["amount"]), entity_id=body.get("entity_id") or ""
    )


@router.put("/budgets/control", summary="预算控制配置 upsert")
async def upsert_budget_control(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    """body: tenant_id, entity_id?, budget_type?=period, category?, enforce_check?, auto_occupy?。"""
    return await fct_service.upsert_budget_control(
        session,
        tenant_id=body["tenant_id"],
        entity_id=body.get("entity_id") or "",
        budget_type=body.get("budget_type") or "period",
        category=body.get("category") or "",
        enforce_check=body.get("enforce_check", False),
        auto_occupy=body.get("auto_occupy", False),
    )


@router.get("/budgets/control", summary="预算控制配置列表")
async def list_budget_controls(
    tenant_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    budget_type: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_budget_controls(session, tenant_id=tenant_id, entity_id=entity_id, budget_type=budget_type)


# ---------- Phase 4：发票闭环 ----------
@router.post("/invoices/link", summary="发票与凭证关联")
async def link_invoice_to_voucher(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.link_invoice_to_voucher(session, invoice_id=body["invoice_id"], voucher_id=body["voucher_id"])


@router.get("/invoices/by-voucher/{voucher_id}", summary="按凭证查关联发票")
async def list_invoices_by_voucher(
    voucher_id: str,
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.list_invoices_by_voucher(session, voucher_id=voucher_id)


@router.post("/invoices/{invoice_id}/verify", summary="发票验真占位")
async def verify_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.verify_invoice_stub(session, invoice_id=invoice_id)


# ---------- Phase 4：审批流占位 ----------
@router.post("/approvals", summary="审批记录占位")
async def create_approval(
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.create_approval_record(
        session, tenant_id=body["tenant_id"], ref_type=body["ref_type"], ref_id=body["ref_id"], step=body.get("step", 1), status=body.get("status") or "pending", extra=body.get("extra")
    )


@router.get("/approvals/by-ref", summary="按业务单查审批记录")
async def get_approval_by_ref(
    tenant_id: str = Query(...),
    ref_type: str = Query(...),
    ref_id: str = Query(...),
    session: AsyncSession = Depends(get_db_fct),
    _: None = Depends(verify_fct_api_key),
) -> Dict[str, Any]:
    return await fct_service.get_approval_by_ref(session, tenant_id=tenant_id, ref_type=ref_type, ref_id=ref_id)


@router.get("/status", summary="服务状态")
async def get_status(_: None = Depends(verify_fct_api_key)) -> Dict[str, Any]:
    return {"service": "fct", "mode": "standalone"}
