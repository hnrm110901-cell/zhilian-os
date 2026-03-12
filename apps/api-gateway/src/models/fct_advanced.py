"""
FCT 高级功能数据模型

1. 银企直连 (Bank-Treasury Direct Connect)
   - fct_bank_accounts     — 银行账户绑定
   - fct_bank_transactions — 银行流水（自动同步 + 手动导入）
   - fct_bank_match_rules  — 自动匹配规则

2. 多实体合并 (Multi-Entity Consolidation)
   - fct_entities           — 合并实体（门店/子公司/总部）
   - fct_consolidation_runs — 合并执行记录
   - fct_intercompany_items — 内部往来抵消项

3. 税务申报自动提取 (Tax Declaration Auto-Extract)
   - fct_tax_declarations   — 税务申报单
   - fct_tax_extract_rules  — 提取规则配置
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Date, DateTime, Boolean,
    Text, JSON, Index, Enum, Numeric, ForeignKey, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 银企直连
# ═══════════════════════════════════════════════════════════════════════════════

class BankAccountStatus(str, enum.Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    PENDING  = "pending"    # 待验证


class BankTxDirection(str, enum.Enum):
    CREDIT = "credit"   # 收款
    DEBIT  = "debit"    # 付款


class BankTxMatchStatus(str, enum.Enum):
    UNMATCHED = "unmatched"
    MATCHED   = "matched"
    MANUAL    = "manual"
    IGNORED   = "ignored"


class FCTBankAccount(Base, TimestampMixin):
    """
    银行账户绑定。
    每个实体（门店/总部）可绑定多个银行账户，
    通过 API 密钥定期拉取流水或手动导入 CSV/Excel。
    """
    __tablename__ = "fct_bank_accounts"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id      = Column(String(50), nullable=False, index=True)   # 门店/实体 ID
    bank_name      = Column(String(100), nullable=False)              # 开户行
    account_no     = Column(String(40), nullable=False)               # 账号（脱敏存储）
    account_name   = Column(String(100), nullable=False)              # 户名
    currency       = Column(String(3), nullable=False, default="CNY")
    status         = Column(Enum(BankAccountStatus), nullable=False, default=BankAccountStatus.PENDING)
    balance_yuan   = Column(Numeric(15, 2), default=0)               # 最新余额
    last_synced_at = Column(DateTime)
    api_config     = Column(JSON)   # 加密存储的银行API配置
    notes          = Column(Text)

    __table_args__ = (
        UniqueConstraint("entity_id", "account_no", name="uq_bank_entity_account"),
    )


class FCTBankTransaction(Base, TimestampMixin):
    """
    银行流水。
    来源：银企直连API自动拉取 / 手动CSV导入。
    自动匹配：根据 match_rules 尝试关联到 fct_vouchers 或 fct_cash_transactions。
    """
    __tablename__ = "fct_bank_transactions"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_account_id  = Column(UUID(as_uuid=True), ForeignKey("fct_bank_accounts.id"), nullable=False, index=True)
    tx_date          = Column(Date, nullable=False)
    direction        = Column(Enum(BankTxDirection), nullable=False)
    amount_yuan      = Column(Numeric(15, 2), nullable=False)
    counterparty     = Column(String(200))           # 对手方名称
    memo             = Column(String(500))            # 附言/摘要
    bank_ref         = Column(String(100))            # 银行流水号
    match_status     = Column(Enum(BankTxMatchStatus), nullable=False, default=BankTxMatchStatus.UNMATCHED)
    matched_voucher_id = Column(UUID(as_uuid=True))   # 匹配到的凭证
    matched_at       = Column(DateTime)
    raw_data         = Column(JSON)                   # 原始报文

    __table_args__ = (
        Index("ix_bank_tx_date", "bank_account_id", "tx_date"),
    )


class FCTBankMatchRule(Base, TimestampMixin):
    """
    自动匹配规则。
    示例：counterparty LIKE '%美团%' → 标记为外卖平台结算
    """
    __tablename__ = "fct_bank_match_rules"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id     = Column(String(50), nullable=False, index=True)
    rule_name     = Column(String(100), nullable=False)
    match_field   = Column(String(50), nullable=False, default="counterparty")  # counterparty/memo/amount
    match_pattern = Column(String(200), nullable=False)                         # SQL LIKE / regex
    target_account_code = Column(String(20))  # 自动记账的科目代码
    priority      = Column(Integer, default=0)
    is_active     = Column(Boolean, default=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 多实体合并
# ═══════════════════════════════════════════════════════════════════════════════

class EntityType(str, enum.Enum):
    STORE       = "store"       # 门店
    SUBSIDIARY  = "subsidiary"  # 子公司
    HQ          = "hq"          # 总部
    BRANCH      = "branch"      # 分公司


class ConsolidationStatus(str, enum.Enum):
    DRAFT      = "draft"
    RUNNING    = "running"
    COMPLETED  = "completed"
    FAILED     = "failed"


class FCTEntity(Base, TimestampMixin):
    """
    合并实体：总部、分公司、门店。
    树形结构（parent_id），支持多级合并。
    """
    __tablename__ = "fct_entities"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_code = Column(String(50), nullable=False, unique=True)   # S001 / HQ / SUB_SH
    entity_name = Column(String(100), nullable=False)
    entity_type = Column(Enum(EntityType), nullable=False)
    parent_id   = Column(UUID(as_uuid=True), ForeignKey("fct_entities.id"))
    currency    = Column(String(3), default="CNY")
    tax_id      = Column(String(30))    # 纳税人识别号
    is_active   = Column(Boolean, default=True)


class FCTConsolidationRun(Base, TimestampMixin):
    """
    合并执行记录。
    每月末触发，汇总所有子实体财务数据到总部。
    """
    __tablename__ = "fct_consolidation_runs"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period          = Column(String(7), nullable=False)    # YYYY-MM
    status          = Column(Enum(ConsolidationStatus), nullable=False, default=ConsolidationStatus.DRAFT)
    entity_count    = Column(Integer, default=0)
    total_revenue_yuan   = Column(Numeric(15, 2), default=0)
    total_cost_yuan      = Column(Numeric(15, 2), default=0)
    total_profit_yuan    = Column(Numeric(15, 2), default=0)
    elimination_yuan     = Column(Numeric(15, 2), default=0)  # 内部交易抵消金额
    consolidated_at = Column(DateTime)
    run_log         = Column(JSON)   # 执行日志


class FCTIntercompanyItem(Base, TimestampMixin):
    """
    内部往来抵消项。
    当门店A向门店B采购食材时，合并时需抵消这笔内部交易。
    """
    __tablename__ = "fct_intercompany_items"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id         = Column(UUID(as_uuid=True), ForeignKey("fct_consolidation_runs.id"), nullable=False, index=True)
    from_entity_id = Column(UUID(as_uuid=True), ForeignKey("fct_entities.id"), nullable=False)
    to_entity_id   = Column(UUID(as_uuid=True), ForeignKey("fct_entities.id"), nullable=False)
    amount_yuan    = Column(Numeric(15, 2), nullable=False)
    description    = Column(String(200))
    voucher_ref    = Column(String(50))   # 关联凭证号


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 税务申报自动提取
# ═══════════════════════════════════════════════════════════════════════════════

class TaxDeclarationStatus(str, enum.Enum):
    DRAFT      = "draft"
    EXTRACTED  = "extracted"    # 已提取数据
    REVIEWED   = "reviewed"    # 已人工审核
    SUBMITTED  = "submitted"   # 已提交税局
    ACCEPTED   = "accepted"    # 已受理


class TaxDeclarationType(str, enum.Enum):
    VAT_MONTHLY      = "vat_monthly"       # 增值税月报
    CIT_QUARTERLY    = "cit_quarterly"     # 企业所得税季报
    CIT_ANNUAL       = "cit_annual"        # 企业所得税年报
    SURCHARGE        = "surcharge"         # 附加税
    STAMP_TAX        = "stamp_tax"         # 印花税


class FCTTaxDeclaration(Base, TimestampMixin):
    """
    税务申报单。
    自动从凭证+发票数据提取填报字段，人工审核后提交。
    """
    __tablename__ = "fct_tax_declarations"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id       = Column(String(50), nullable=False, index=True)
    period          = Column(String(7), nullable=False)     # YYYY-MM 或 YYYY-Q1
    declaration_type = Column(Enum(TaxDeclarationType), nullable=False)
    status          = Column(Enum(TaxDeclarationStatus), nullable=False, default=TaxDeclarationStatus.DRAFT)
    # 提取的金额字段
    taxable_revenue_yuan  = Column(Numeric(15, 2), default=0)   # 应税收入
    tax_deductible_yuan   = Column(Numeric(15, 2), default=0)   # 可抵扣进项
    tax_payable_yuan      = Column(Numeric(15, 2), default=0)   # 应纳税额
    # 明细
    line_items      = Column(JSON)         # [{field_name, value, source, auto_extracted}]
    extraction_log  = Column(JSON)         # 提取过程日志
    reviewer_notes  = Column(Text)
    submitted_at    = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("entity_id", "period", "declaration_type", name="uq_tax_decl_entity_period_type"),
    )


class FCTTaxExtractRule(Base, TimestampMixin):
    """
    税务数据提取规则。
    定义如何从凭证/发票数据映射到申报表字段。
    示例：VAT月报「销项税额」= SUM(voucher_lines WHERE account_code LIKE '2221%' AND credit > 0)
    """
    __tablename__ = "fct_tax_extract_rules"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    declaration_type  = Column(Enum(TaxDeclarationType), nullable=False)
    field_name        = Column(String(100), nullable=False)   # 申报表字段名
    field_label       = Column(String(200))                   # 中文标签
    extract_sql       = Column(Text)                          # 提取SQL模板
    account_codes     = Column(JSON)                          # 匹配的科目代码列表
    direction         = Column(String(10))                    # debit / credit / net
    is_active         = Column(Boolean, default=True)
    sort_order        = Column(Integer, default=0)
