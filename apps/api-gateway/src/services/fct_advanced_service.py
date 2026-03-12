"""
FCT 高级功能服务

1. 银企直连：银行流水自动匹配
2. 多实体合并：跨实体财务数据汇总 + 内部交易抵消
3. 税务申报自动提取：从凭证/发票数据自动填充申报表

设计原则：
- 核心逻辑为纯函数（可单元测试）
- DB 交互在 async 方法中（可 mock）
"""
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import structlog

logger = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 银企直连 — 纯函数
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BankTransaction:
    """银行流水记录（轻量DTO）"""
    id: str
    tx_date: str
    direction: str  # credit / debit
    amount_yuan: float
    counterparty: str = ""
    memo: str = ""
    bank_ref: str = ""
    match_status: str = "unmatched"
    matched_voucher_id: Optional[str] = None


@dataclass
class MatchRule:
    """匹配规则"""
    rule_name: str
    match_field: str       # counterparty / memo / amount
    match_pattern: str     # SQL LIKE 模式 → Python 正则
    target_account_code: str = ""
    priority: int = 0


def like_to_regex(pattern: str) -> str:
    """将 SQL LIKE 模式转换为 Python 正则。"""
    # 先用占位符保护 LIKE 通配符
    pattern = pattern.replace("%", "\x00").replace("_", "\x01")
    # 转义正则特殊字符
    escaped = re.escape(pattern)
    # 替换占位符为正则通配符
    escaped = escaped.replace("\x00", ".*").replace("\x01", ".")
    return f"^{escaped}$"


def match_transaction(tx: BankTransaction, rules: list[MatchRule]) -> Optional[str]:
    """
    尝试用规则列表匹配一笔银行流水。
    规则按 priority 降序尝试，首个匹配即返回 target_account_code。
    返回 None 表示无匹配。
    """
    sorted_rules = sorted(rules, key=lambda r: r.priority, reverse=True)
    for rule in sorted_rules:
        field_value = ""
        if rule.match_field == "counterparty":
            field_value = tx.counterparty
        elif rule.match_field == "memo":
            field_value = tx.memo
        elif rule.match_field == "amount":
            field_value = str(tx.amount_yuan)

        regex = like_to_regex(rule.match_pattern)
        if re.match(regex, field_value, re.IGNORECASE):
            return rule.target_account_code
    return None


def batch_match_transactions(
    transactions: list[BankTransaction],
    rules: list[MatchRule],
) -> dict[str, int]:
    """
    批量匹配银行流水。
    返回 {"matched": N, "unmatched": M}。
    副作用：修改 tx.match_status 和 tx.matched_voucher_id（此处仅设 account_code 标记）。
    """
    matched = 0
    for tx in transactions:
        if tx.match_status != "unmatched":
            continue
        account_code = match_transaction(tx, rules)
        if account_code:
            tx.match_status = "matched"
            matched += 1
    return {"matched": matched, "unmatched": len(transactions) - matched}


def compute_bank_balance(
    opening_balance: float,
    transactions: list[BankTransaction],
) -> float:
    """从期初余额 + 流水计算期末余额。"""
    balance = opening_balance
    for tx in transactions:
        if tx.direction == "credit":
            balance += tx.amount_yuan
        elif tx.direction == "debit":
            balance -= tx.amount_yuan
    return round(balance, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 多实体合并 — 纯函数
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EntityFinancials:
    """单实体财务摘要"""
    entity_id: str
    entity_name: str
    revenue_yuan: float = 0.0
    cost_yuan: float = 0.0
    profit_yuan: float = 0.0


@dataclass
class IntercompanyItem:
    """内部往来项"""
    from_entity_id: str
    to_entity_id: str
    amount_yuan: float
    description: str = ""


@dataclass
class ConsolidationResult:
    """合并结果"""
    period: str
    entity_count: int
    total_revenue_yuan: float
    total_cost_yuan: float
    total_profit_yuan: float
    elimination_yuan: float
    net_profit_yuan: float


def consolidate_entities(
    entities: list[EntityFinancials],
    intercompany_items: list[IntercompanyItem],
    period: str,
) -> ConsolidationResult:
    """
    合并多实体财务数据。
    1. 汇总所有实体的收入/成本/利润
    2. 抵消内部往来（内部交易在收入端和成本端各扣一次）
    """
    total_revenue = sum(e.revenue_yuan for e in entities)
    total_cost = sum(e.cost_yuan for e in entities)
    total_profit = sum(e.profit_yuan for e in entities)

    elimination = sum(item.amount_yuan for item in intercompany_items)

    # 内部交易抵消：收入和成本各减去抵消金额
    net_revenue = total_revenue - elimination
    net_cost = total_cost - elimination
    net_profit = net_revenue - net_cost

    return ConsolidationResult(
        period=period,
        entity_count=len(entities),
        total_revenue_yuan=round(total_revenue, 2),
        total_cost_yuan=round(total_cost, 2),
        total_profit_yuan=round(total_profit, 2),
        elimination_yuan=round(elimination, 2),
        net_profit_yuan=round(net_profit, 2),
    )


def validate_intercompany_balance(
    items: list[IntercompanyItem],
) -> bool:
    """
    验证内部往来平衡性：A→B 和 B→A 的金额应配对。
    实际使用中允许差异（因为 A 和 B 可能在不同月确认），
    这里仅做基础校验。
    """
    # 构建 (from, to) → total_amount 映射
    pair_sums: dict[tuple[str, str], float] = {}
    for item in items:
        key = (item.from_entity_id, item.to_entity_id)
        pair_sums[key] = pair_sums.get(key, 0) + item.amount_yuan

    # 检查每对是否有反向配对
    for (a, b), amount in pair_sums.items():
        reverse = pair_sums.get((b, a), 0)
        if abs(amount - reverse) > 0.01:
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 税务申报自动提取 — 纯函数
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class VoucherSummary:
    """凭证摘要（用于税务提取）"""
    account_code: str
    account_name: str
    debit_total: float = 0.0
    credit_total: float = 0.0


@dataclass
class ExtractRule:
    """税务提取规则"""
    field_name: str
    field_label: str
    account_codes: list[str]
    direction: str  # debit / credit / net
    sort_order: int = 0


@dataclass
class ExtractedField:
    """提取的申报字段"""
    field_name: str
    field_label: str
    value_yuan: float
    source_accounts: list[str]
    auto_extracted: bool = True


def extract_tax_fields(
    voucher_summaries: list[VoucherSummary],
    rules: list[ExtractRule],
) -> list[ExtractedField]:
    """
    根据提取规则从凭证汇总数据中提取税务申报字段。

    规则示例：
    - 销项税额：account_codes=['2221%'], direction='credit'
    - 进项税额：account_codes=['2221%'], direction='debit'
    """
    results = []
    sorted_rules = sorted(rules, key=lambda r: r.sort_order)

    for rule in sorted_rules:
        total = 0.0
        matched_accounts = []

        for vs in voucher_summaries:
            if _matches_account_codes(vs.account_code, rule.account_codes):
                matched_accounts.append(vs.account_code)
                if rule.direction == "debit":
                    total += vs.debit_total
                elif rule.direction == "credit":
                    total += vs.credit_total
                elif rule.direction == "net":
                    total += vs.debit_total - vs.credit_total

        results.append(ExtractedField(
            field_name=rule.field_name,
            field_label=rule.field_label,
            value_yuan=round(total, 2),
            source_accounts=matched_accounts,
        ))

    return results


def _matches_account_codes(account_code: str, patterns: list[str]) -> bool:
    """检查科目代码是否匹配任一模式（支持 % 通配符）。"""
    for pattern in patterns:
        if pattern.endswith("%"):
            if account_code.startswith(pattern[:-1]):
                return True
        elif account_code == pattern:
            return True
    return False


def compute_vat_payable(
    output_tax: float,
    input_tax: float,
    carried_forward: float = 0.0,
) -> dict[str, float]:
    """
    计算增值税应纳税额。
    应纳税额 = 销项税额 - 进项税额 - 上期留抵
    若为负（即留抵），应纳税额=0，结转下期。
    """
    raw = output_tax - input_tax - carried_forward
    if raw >= 0:
        return {
            "tax_payable_yuan": round(raw, 2),
            "carried_forward_yuan": 0.0,
        }
    else:
        return {
            "tax_payable_yuan": 0.0,
            "carried_forward_yuan": round(abs(raw), 2),
        }


def compute_surcharge(vat_payable: float) -> dict[str, float]:
    """
    计算附加税（基于增值税应纳税额）。
    城建税 7% + 教育附加 3% + 地方教育 2% = 12%
    """
    urban_construction = round(vat_payable * 0.07, 2)
    education = round(vat_payable * 0.03, 2)
    local_education = round(vat_payable * 0.02, 2)
    total = round(urban_construction + education + local_education, 2)
    return {
        "urban_construction_tax": urban_construction,
        "education_surcharge": education,
        "local_education_surcharge": local_education,
        "total_surcharge": total,
    }


def compute_cit_quarterly(
    revenue_yuan: float,
    cost_yuan: float,
    profit_rate_assumption: float = 0.10,
    cit_rate: float = 0.25,
    is_micro: bool = False,
) -> dict[str, float]:
    """
    计算企业所得税（季度预缴）。
    微型企业优惠：应纳税所得额≤300万，CIT 20%×25%=5%。
    """
    profit = revenue_yuan - cost_yuan
    if profit <= 0:
        return {"taxable_income_yuan": 0.0, "cit_payable_yuan": 0.0}

    taxable_income = profit * profit_rate_assumption if profit_rate_assumption < 1.0 else profit
    effective_rate = 0.05 if is_micro and taxable_income <= 3_000_000 else cit_rate
    cit = round(taxable_income * effective_rate, 2)

    return {
        "taxable_income_yuan": round(taxable_income, 2),
        "cit_payable_yuan": cit,
    }
