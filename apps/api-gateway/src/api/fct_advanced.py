"""
FCT 高级功能 API

1. 银企直连：/api/v1/fct-advanced/bank/*
2. 多实体合并：/api/v1/fct-advanced/consolidation/*
3. 税务申报自动提取：/api/v1/fct-advanced/tax-declaration/*
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime

from src.services.fct_advanced_service import (
    BankTransaction, MatchRule,
    match_transaction, batch_match_transactions, compute_bank_balance,
    EntityFinancials, IntercompanyItem,
    consolidate_entities, validate_intercompany_balance,
    VoucherSummary, ExtractRule,
    extract_tax_fields, compute_vat_payable, compute_surcharge, compute_cit_quarterly,
)

router = APIRouter(prefix="/api/v1/fct-advanced", tags=["fct_advanced"])


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 银企直连
# ═══════════════════════════════════════════════════════════════════════════════

class BankTransactionIn(BaseModel):
    id: str
    tx_date: str
    direction: str
    amount_yuan: float
    counterparty: str = ""
    memo: str = ""
    bank_ref: str = ""

class MatchRuleIn(BaseModel):
    rule_name: str
    match_field: str = "counterparty"
    match_pattern: str
    target_account_code: str = ""
    priority: int = 0

class BatchMatchRequest(BaseModel):
    transactions: List[BankTransactionIn]
    rules: List[MatchRuleIn]

class BalanceRequest(BaseModel):
    opening_balance: float
    transactions: List[BankTransactionIn]


@router.post("/bank/batch-match")
async def api_batch_match(req: BatchMatchRequest):
    """批量匹配银行流水。"""
    txs = [BankTransaction(**t.model_dump()) for t in req.transactions]
    rules = [MatchRule(**r.model_dump()) for r in req.rules]
    result = batch_match_transactions(txs, rules)
    return {
        **result,
        "transactions": [
            {"id": t.id, "match_status": t.match_status}
            for t in txs
        ],
    }


@router.post("/bank/compute-balance")
async def api_compute_balance(req: BalanceRequest):
    """计算银行账户余额。"""
    txs = [BankTransaction(**t.model_dump()) for t in req.transactions]
    balance = compute_bank_balance(req.opening_balance, txs)
    return {"opening_balance": req.opening_balance, "closing_balance": balance}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 多实体合并
# ═══════════════════════════════════════════════════════════════════════════════

class EntityFinancialsIn(BaseModel):
    entity_id: str
    entity_name: str
    revenue_yuan: float = 0
    cost_yuan: float = 0
    profit_yuan: float = 0

class IntercompanyItemIn(BaseModel):
    from_entity_id: str
    to_entity_id: str
    amount_yuan: float
    description: str = ""

class ConsolidationRequest(BaseModel):
    period: str
    entities: List[EntityFinancialsIn]
    intercompany_items: List[IntercompanyItemIn] = []


@router.post("/consolidation/run")
async def api_run_consolidation(req: ConsolidationRequest):
    """执行多实体财务合并。"""
    entities = [EntityFinancials(**e.model_dump()) for e in req.entities]
    items = [IntercompanyItem(**i.model_dump()) for i in req.intercompany_items]
    result = consolidate_entities(entities, items, req.period)
    return {
        "period": result.period,
        "entity_count": result.entity_count,
        "total_revenue_yuan": result.total_revenue_yuan,
        "total_cost_yuan": result.total_cost_yuan,
        "total_profit_yuan": result.total_profit_yuan,
        "elimination_yuan": result.elimination_yuan,
        "net_profit_yuan": result.net_profit_yuan,
    }


@router.post("/consolidation/validate-intercompany")
async def api_validate_intercompany(items: List[IntercompanyItemIn]):
    """验证内部往来平衡性。"""
    ic_items = [IntercompanyItem(**i.model_dump()) for i in items]
    balanced = validate_intercompany_balance(ic_items)
    return {"balanced": balanced}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 税务申报自动提取
# ═══════════════════════════════════════════════════════════════════════════════

class VoucherSummaryIn(BaseModel):
    account_code: str
    account_name: str
    debit_total: float = 0
    credit_total: float = 0

class ExtractRuleIn(BaseModel):
    field_name: str
    field_label: str
    account_codes: List[str]
    direction: str
    sort_order: int = 0

class ExtractRequest(BaseModel):
    voucher_summaries: List[VoucherSummaryIn]
    rules: List[ExtractRuleIn]

class VatRequest(BaseModel):
    output_tax: float
    input_tax: float
    carried_forward: float = 0

class CitRequest(BaseModel):
    revenue_yuan: float
    cost_yuan: float
    profit_rate_assumption: float = 0.10
    cit_rate: float = 0.25
    is_micro: bool = False


@router.post("/tax-declaration/extract")
async def api_extract_tax_fields(req: ExtractRequest):
    """从凭证数据自动提取税务申报字段。"""
    summaries = [VoucherSummary(**v.model_dump()) for v in req.voucher_summaries]
    rules = [ExtractRule(**r.model_dump()) for r in req.rules]
    fields = extract_tax_fields(summaries, rules)
    return {
        "fields": [
            {
                "field_name": f.field_name,
                "field_label": f.field_label,
                "value_yuan": f.value_yuan,
                "source_accounts": f.source_accounts,
                "auto_extracted": f.auto_extracted,
            }
            for f in fields
        ]
    }


@router.post("/tax-declaration/compute-vat")
async def api_compute_vat(req: VatRequest):
    """计算增值税应纳税额。"""
    return compute_vat_payable(req.output_tax, req.input_tax, req.carried_forward)


@router.post("/tax-declaration/compute-surcharge")
async def api_compute_surcharge(vat_payable: float):
    """计算附加税。"""
    return compute_surcharge(vat_payable)


@router.post("/tax-declaration/compute-cit")
async def api_compute_cit(req: CitRequest):
    """计算企业所得税（季度预缴）。"""
    return compute_cit_quarterly(
        req.revenue_yuan, req.cost_yuan,
        req.profit_rate_assumption, req.cit_rate, req.is_micro,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 驾驶舱 BFF
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def api_fct_advanced_dashboard():
    """FCT 高级功能驾驶舱。"""
    return {
        "bank_treasury": {
            "total_accounts": 0,
            "unmatched_transactions": 0,
            "last_sync": None,
        },
        "consolidation": {
            "total_entities": 0,
            "last_run_period": None,
            "last_run_status": None,
        },
        "tax_declaration": {
            "pending_declarations": 0,
            "next_deadline": None,
        },
    }
