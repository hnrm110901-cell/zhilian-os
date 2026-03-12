"""
FCT 高级功能单元测试

覆盖：
  1. 银企直连：like_to_regex / match_transaction / batch_match / compute_balance
  2. 多实体合并：consolidate_entities / validate_intercompany_balance
  3. 税务申报自动提取：extract_tax_fields / compute_vat / compute_surcharge / compute_cit
"""
import os
for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from src.services.fct_advanced_service import (
    # 银企直连
    BankTransaction, MatchRule,
    like_to_regex, match_transaction, batch_match_transactions, compute_bank_balance,
    # 多实体合并
    EntityFinancials, IntercompanyItem, ConsolidationResult,
    consolidate_entities, validate_intercompany_balance,
    # 税务申报
    VoucherSummary, ExtractRule, ExtractedField,
    extract_tax_fields, _matches_account_codes,
    compute_vat_payable, compute_surcharge, compute_cit_quarterly,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 银企直连
# ═══════════════════════════════════════════════════════════════════════════════

class TestLikeToRegex:

    def test_percent_wildcard(self):
        """% 应转为 .*"""
        assert like_to_regex("%美团%") == "^.*美团.*$"

    def test_underscore_wildcard(self):
        """_ 应转为 ."""
        assert like_to_regex("S_01") == "^S.01$"

    def test_exact_match(self):
        """无通配符应精确匹配。"""
        regex = like_to_regex("饿了么")
        import re
        assert re.match(regex, "饿了么")
        assert not re.match(regex, "饿了么外卖")


class TestMatchTransaction:

    def _make_tx(self, counterparty="", memo="", amount=100.0):
        return BankTransaction(
            id="tx1", tx_date="2026-03-01", direction="credit",
            amount_yuan=amount, counterparty=counterparty, memo=memo,
        )

    def test_match_counterparty(self):
        """按 counterparty 匹配。"""
        tx = self._make_tx(counterparty="美团外卖结算")
        rules = [MatchRule("美团", "counterparty", "%美团%", "6001")]
        assert match_transaction(tx, rules) == "6001"

    def test_match_memo(self):
        """按 memo 匹配。"""
        tx = self._make_tx(memo="工资发放202603")
        rules = [MatchRule("工资", "memo", "%工资%", "5001")]
        assert match_transaction(tx, rules) == "5001"

    def test_no_match_returns_none(self):
        """无匹配规则时返回 None。"""
        tx = self._make_tx(counterparty="个人转账")
        rules = [MatchRule("美团", "counterparty", "%美团%", "6001")]
        assert match_transaction(tx, rules) is None

    def test_priority_order(self):
        """高优先级规则优先匹配。"""
        tx = self._make_tx(counterparty="美团外卖结算")
        rules = [
            MatchRule("通用外卖", "counterparty", "%外卖%", "6001", priority=1),
            MatchRule("美团专用", "counterparty", "%美团%", "6002", priority=10),
        ]
        assert match_transaction(tx, rules) == "6002"

    def test_match_amount_field(self):
        """按 amount 匹配（精确值）。"""
        tx = self._make_tx(amount=88.88)
        rules = [MatchRule("固定金额", "amount", "88.88", "7001")]
        assert match_transaction(tx, rules) == "7001"


class TestBatchMatch:

    def test_batch_match_counts(self):
        """批量匹配应返回正确的计数。"""
        txs = [
            BankTransaction("t1", "2026-03-01", "credit", 100, counterparty="美团结算"),
            BankTransaction("t2", "2026-03-01", "credit", 200, counterparty="个人转账"),
            BankTransaction("t3", "2026-03-01", "debit", 50, counterparty="饿了么结算"),
        ]
        rules = [
            MatchRule("外卖平台", "counterparty", "%美团%", "6001"),
            MatchRule("外卖平台2", "counterparty", "%饿了么%", "6001"),
        ]
        result = batch_match_transactions(txs, rules)
        assert result["matched"] == 2
        assert result["unmatched"] == 1

    def test_already_matched_skipped(self):
        """已匹配的流水不再重新匹配。"""
        tx = BankTransaction("t1", "2026-03-01", "credit", 100,
                             counterparty="美团", match_status="matched")
        result = batch_match_transactions([tx], [MatchRule("美团", "counterparty", "%美团%", "6001")])
        assert result["matched"] == 0


class TestComputeBankBalance:

    def test_credit_increases_balance(self):
        """收款增加余额。"""
        txs = [BankTransaction("t1", "2026-03-01", "credit", 1000)]
        assert compute_bank_balance(5000, txs) == 6000

    def test_debit_decreases_balance(self):
        """付款减少余额。"""
        txs = [BankTransaction("t1", "2026-03-01", "debit", 300)]
        assert compute_bank_balance(5000, txs) == 4700

    def test_mixed_transactions(self):
        """混合收付款计算。"""
        txs = [
            BankTransaction("t1", "2026-03-01", "credit", 2000),
            BankTransaction("t2", "2026-03-02", "debit", 500),
            BankTransaction("t3", "2026-03-03", "credit", 300),
        ]
        assert compute_bank_balance(1000, txs) == 2800

    def test_empty_transactions(self):
        """无流水时余额不变。"""
        assert compute_bank_balance(10000, []) == 10000


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 多实体合并
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsolidateEntities:

    def test_simple_consolidation(self):
        """简单合并：两个门店无内部交易。"""
        entities = [
            EntityFinancials("S001", "门店1", revenue_yuan=100000, cost_yuan=70000, profit_yuan=30000),
            EntityFinancials("S002", "门店2", revenue_yuan=80000, cost_yuan=55000, profit_yuan=25000),
        ]
        result = consolidate_entities(entities, [], "2026-03")
        assert result.entity_count == 2
        assert result.total_revenue_yuan == 180000
        assert result.total_cost_yuan == 125000
        assert result.elimination_yuan == 0
        assert result.net_profit_yuan == 55000

    def test_consolidation_with_intercompany(self):
        """有内部交易时应抵消。"""
        entities = [
            EntityFinancials("S001", "中央厨房", revenue_yuan=200000, cost_yuan=150000, profit_yuan=50000),
            EntityFinancials("S002", "门店A", revenue_yuan=300000, cost_yuan=220000, profit_yuan=80000),
        ]
        # 中央厨房向门店A供应10万食材（内部交易）
        items = [IntercompanyItem("S001", "S002", 100000, "食材供应")]
        result = consolidate_entities(entities, items, "2026-03")

        assert result.elimination_yuan == 100000
        # 合并后：收入 500000-100000=400000, 成本 370000-100000=270000
        assert result.net_profit_yuan == 130000

    def test_empty_entities(self):
        """空实体列表。"""
        result = consolidate_entities([], [], "2026-03")
        assert result.entity_count == 0
        assert result.net_profit_yuan == 0

    def test_single_entity_no_elimination(self):
        """单实体无抵消。"""
        entities = [EntityFinancials("HQ", "总部", 500000, 350000, 150000)]
        result = consolidate_entities(entities, [], "2026-03")
        assert result.net_profit_yuan == 150000


class TestValidateIntercompanyBalance:

    def test_balanced_pairs(self):
        """配对的内部往来应通过。"""
        items = [
            IntercompanyItem("S001", "S002", 10000, "食材"),
            IntercompanyItem("S002", "S001", 10000, "食材"),
        ]
        assert validate_intercompany_balance(items) is True

    def test_unbalanced_pairs(self):
        """不配对的内部往来应失败。"""
        items = [
            IntercompanyItem("S001", "S002", 10000, "食材"),
            IntercompanyItem("S002", "S001", 8000, "食材"),  # 差2000
        ]
        assert validate_intercompany_balance(items) is False

    def test_empty_is_balanced(self):
        """无内部往来视为平衡。"""
        assert validate_intercompany_balance([]) is True

    def test_one_way_is_unbalanced(self):
        """单向往来（无反向）应失败。"""
        items = [IntercompanyItem("S001", "S002", 5000)]
        assert validate_intercompany_balance(items) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 税务申报自动提取
# ═══════════════════════════════════════════════════════════════════════════════

class TestMatchesAccountCodes:

    def test_exact_match(self):
        assert _matches_account_codes("6001", ["6001"]) is True

    def test_prefix_match(self):
        assert _matches_account_codes("222101", ["2221%"]) is True

    def test_no_match(self):
        assert _matches_account_codes("5001", ["6001", "2221%"]) is False

    def test_multiple_patterns(self):
        assert _matches_account_codes("6002", ["6001", "6002"]) is True


class TestExtractTaxFields:

    def test_extract_output_tax(self):
        """提取销项税额（贷方汇总）。"""
        summaries = [
            VoucherSummary("222101", "应交税费-销项", debit_total=0, credit_total=60000),
            VoucherSummary("222102", "应交税费-进项", debit_total=30000, credit_total=0),
            VoucherSummary("6001", "主营业务收入", debit_total=0, credit_total=1000000),
        ]
        rules = [
            ExtractRule("output_tax", "销项税额", ["2221%"], "credit", 1),
            ExtractRule("input_tax", "进项税额", ["2221%"], "debit", 2),
        ]
        result = extract_tax_fields(summaries, rules)
        assert len(result) == 2
        # 销项：222101 credit 60000 + 222102 credit 0 = 60000
        assert result[0].field_name == "output_tax"
        assert result[0].value_yuan == 60000
        # 进项：222101 debit 0 + 222102 debit 30000 = 30000
        assert result[1].field_name == "input_tax"
        assert result[1].value_yuan == 30000

    def test_extract_net_direction(self):
        """net 方向 = debit - credit。"""
        summaries = [
            VoucherSummary("5001", "主营业务成本", debit_total=800000, credit_total=50000),
        ]
        rules = [
            ExtractRule("cost", "成本合计", ["5001"], "net"),
        ]
        result = extract_tax_fields(summaries, rules)
        assert result[0].value_yuan == 750000

    def test_no_matching_accounts(self):
        """无匹配科目时金额为 0。"""
        summaries = [VoucherSummary("1001", "现金", 10000, 5000)]
        rules = [ExtractRule("output_tax", "销项税额", ["2221%"], "credit")]
        result = extract_tax_fields(summaries, rules)
        assert result[0].value_yuan == 0


class TestComputeVatPayable:

    def test_positive_vat(self):
        """销项 > 进项 → 有应纳税额。"""
        result = compute_vat_payable(60000, 30000)
        assert result["tax_payable_yuan"] == 30000
        assert result["carried_forward_yuan"] == 0

    def test_negative_vat_carried_forward(self):
        """销项 < 进项 → 留抵。"""
        result = compute_vat_payable(20000, 30000)
        assert result["tax_payable_yuan"] == 0
        assert result["carried_forward_yuan"] == 10000

    def test_with_carried_forward(self):
        """有上期留抵时应扣除。"""
        result = compute_vat_payable(60000, 30000, carried_forward=5000)
        assert result["tax_payable_yuan"] == 25000

    def test_zero_tax(self):
        """销项=进项时应纳税额为0。"""
        result = compute_vat_payable(30000, 30000)
        assert result["tax_payable_yuan"] == 0
        assert result["carried_forward_yuan"] == 0


class TestComputeSurcharge:

    def test_standard_surcharge(self):
        """标准附加税 = VAT × 12%。"""
        result = compute_surcharge(10000)
        assert result["urban_construction_tax"] == 700
        assert result["education_surcharge"] == 300
        assert result["local_education_surcharge"] == 200
        assert result["total_surcharge"] == 1200

    def test_zero_vat(self):
        """VAT=0 时附加税为0。"""
        result = compute_surcharge(0)
        assert result["total_surcharge"] == 0

    def test_decimal_precision(self):
        """小数精度验证。"""
        result = compute_surcharge(333.33)
        assert result["urban_construction_tax"] == 23.33
        assert result["education_surcharge"] == 10.0
        assert result["local_education_surcharge"] == 6.67


class TestComputeCitQuarterly:

    def test_profitable_standard(self):
        """标准税率25%。"""
        result = compute_cit_quarterly(1000000, 700000, profit_rate_assumption=1.0, cit_rate=0.25)
        assert result["taxable_income_yuan"] == 300000
        assert result["cit_payable_yuan"] == 75000

    def test_loss_no_tax(self):
        """亏损不缴税。"""
        result = compute_cit_quarterly(500000, 600000)
        assert result["cit_payable_yuan"] == 0

    def test_micro_enterprise_discount(self):
        """微型企业优惠税率5%。"""
        result = compute_cit_quarterly(
            2000000, 1500000,
            profit_rate_assumption=1.0, is_micro=True,
        )
        # 利润50万 < 300万，适用5%
        assert result["cit_payable_yuan"] == 25000

    def test_profit_rate_assumption(self):
        """利润率假设 10% 下的测算。"""
        result = compute_cit_quarterly(
            1000000, 700000,
            profit_rate_assumption=0.10, cit_rate=0.25,
        )
        # 利润=300000, 应税=300000*0.1=30000, CIT=30000*0.25=7500
        assert result["taxable_income_yuan"] == 30000
        assert result["cit_payable_yuan"] == 7500
