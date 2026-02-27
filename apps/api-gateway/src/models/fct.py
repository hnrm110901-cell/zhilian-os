"""
业财税资金一体化（FCT）数据模型

- FctEvent: 业财事件原始记录
- FctVoucher: 凭证
- FctVoucherLine: 凭证分录
"""
from sqlalchemy import Column, String, Integer, Text, Enum, JSON, ForeignKey, Date, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from datetime import date

from .base import Base, TimestampMixin


class FctVoucherStatus(str, enum.Enum):
    """凭证状态"""
    DRAFT = "draft"          # 草稿
    PENDING = "pending"       # 待审核
    APPROVED = "approved"     # 已审核
    POSTED = "posted"         # 已过账
    REJECTED = "rejected"     # 已驳回
    VOIDED = "voided"         # 已作废（不参与总账）


class FctEvent(Base, TimestampMixin):
    """业财事件原始记录（用于追溯与重跑）"""

    __tablename__ = "fct_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(64), unique=True, nullable=False, index=True)  # 业务侧幂等 id
    event_type = Column(String(64), nullable=False, index=True)
    occurred_at = Column(String(32), nullable=False)  # ISO8601
    source_system = Column(String(64), nullable=False)
    source_id = Column(String(128))
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)  # 门店/主体
    payload = Column(JSON, nullable=False)
    # 处理结果
    processed_at = Column(String(32))
    voucher_id = Column(UUID(as_uuid=True), ForeignKey("fct_vouchers.id"))
    error_message = Column(Text)

    voucher = relationship("FctVoucher", back_populates="source_events", foreign_keys=[voucher_id])


class FctVoucher(Base, TimestampMixin):
    """凭证"""

    __tablename__ = "fct_vouchers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voucher_no = Column(String(32), nullable=False, index=True)  # 凭证号，按主体+期间生成
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(Date, nullable=False, index=True)
    event_type = Column(String(64))  # 来源事件类型
    event_id = Column(String(64))    # 来源 event_id
    status = Column(
        Enum(FctVoucherStatus, values_callable=lambda x: [e.value for e in x]),
        default=FctVoucherStatus.DRAFT,
        nullable=False,
        index=True,
    )
    description = Column(Text)
    attachments = Column(JSON)  # 可选附件/扩展

    source_events = relationship("FctEvent", back_populates="voucher", foreign_keys="FctEvent.voucher_id")
    lines = relationship("FctVoucherLine", back_populates="voucher", cascade="all, delete-orphan")


class FctVoucherLine(Base, TimestampMixin):
    """凭证分录"""

    __tablename__ = "fct_voucher_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voucher_id = Column(UUID(as_uuid=True), ForeignKey("fct_vouchers.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False)  # 行号
    account_code = Column(String(32), nullable=False)  # 科目编码
    account_name = Column(String(128))
    debit = Column(Numeric(18, 2), default=0)   # 借方金额
    credit = Column(Numeric(18, 2), default=0)   # 贷方金额
    auxiliary = Column(JSON)  # 辅助核算：部门、客商等
    description = Column(Text)

    voucher = relationship("FctVoucher", back_populates="lines")


class FctMasterType(str, enum.Enum):
    """主数据类型"""
    STORE = "store"
    SUPPLIER = "supplier"
    ACCOUNT = "account"
    BANK_ACCOUNT = "bank_account"


class FctMaster(Base, TimestampMixin):
    """业财主数据（门店、客商、科目、银行账户等）"""
    __tablename__ = "fct_master"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    type = Column(
        Enum(FctMasterType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    code = Column(String(64), nullable=False, index=True)  # 编码，同 tenant+type 下唯一
    name = Column(String(128), nullable=False)
    extra = Column(JSON)  # 扩展字段


class FctCashTransaction(Base, TimestampMixin):
    """资金流水（用于对账）"""
    __tablename__ = "fct_cash_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    tx_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)  # 正为收入，负为支出
    direction = Column(String(8), nullable=False)  # in / out
    ref_type = Column(String(32))  # voucher / settlement / manual
    ref_id = Column(String(64))
    status = Column(String(20), default="pending")  # pending / matched
    match_id = Column(UUID(as_uuid=True))  # 对账匹配 id
    description = Column(Text)


class FctTaxInvoice(Base, TimestampMixin):
    """税务发票（销项/进项）；Phase 4 发票闭环：与凭证关联、验真占位"""
    __tablename__ = "fct_tax_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    invoice_type = Column(String(16), nullable=False)  # output / input
    invoice_no = Column(String(64), index=True)
    amount = Column(Numeric(18, 2))
    tax_amount = Column(Numeric(18, 2))
    invoice_date = Column(Date)
    status = Column(String(20), default="draft")
    voucher_id = Column(UUID(as_uuid=True), ForeignKey("fct_vouchers.id"))
    verify_status = Column(String(20), default="pending")  # pending / verified / failed（Phase 4 验真占位）
    verified_at = Column(String(32))  # ISO8601（验真时间）
    extra = Column(JSON)


class FctTaxDeclaration(Base, TimestampMixin):
    """税务申报记录占位"""
    __tablename__ = "fct_tax_declarations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    tax_type = Column(String(32), nullable=False)  # vat / income_tax
    period = Column(String(16), nullable=False)  # 202502
    declared_at = Column(String(32))
    status = Column(String(20), default="draft")  # draft / submitted
    extra = Column(JSON)


class FctPlan(Base, TimestampMixin):
    """年度计划（业财税资金目标，用于与日/周/月/季实际对比达成与差距）"""
    __tablename__ = "fct_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=True, index=True)  # 空表示租户级
    plan_year = Column(Integer, nullable=False, index=True)  # 2026
    # 年度目标：revenue, cost, gross_margin, output_tax, input_tax, net_tax, cash_in, cash_out, voucher_count（可选）
    targets = Column(JSON, nullable=False)  # {"revenue": 1000000, "cost": 600000, ...}
    extra = Column(JSON)  # 备注、编制人等


class FctPeriod(Base, TimestampMixin):
    """会计期间（按租户，自然月 period_key=YYYYMM）"""
    __tablename__ = "fct_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    period_key = Column(String(16), nullable=False, index=True)  # 202502
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), default="open", nullable=False)  # open / closed
    closed_at = Column(String(32))  # ISO8601
    extra = Column(JSON)


# ---------- Phase 4：费控/备用金 ----------
class FctPettyCashType(str, enum.Enum):
    """备用金类型"""
    FIXED = "fixed"      # 固定备用金
    TEMPORARY = "temporary"  # 临时备用金


class FctPettyCash(Base, TimestampMixin):
    """备用金主档（门店/主体维度，按类型）"""
    __tablename__ = "fct_petty_cash"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    cash_type = Column(String(16), nullable=False, index=True)  # fixed / temporary
    amount_limit = Column(Numeric(18, 2), nullable=False, default=0)  # 限额（元）
    current_balance = Column(Numeric(18, 2), nullable=False, default=0)  # 当前余额
    status = Column(String(20), default="active", nullable=False)  # active / closed
    extra = Column(JSON)


class FctPettyCashRecord(Base, TimestampMixin):
    """备用金流水：申请/冲销/还款"""
    __tablename__ = "fct_petty_cash_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    petty_cash_id = Column(UUID(as_uuid=True), ForeignKey("fct_petty_cash.id", ondelete="CASCADE"), nullable=False, index=True)
    record_type = Column(String(16), nullable=False, index=True)  # apply / offset / repay
    amount = Column(Numeric(18, 2), nullable=False)  # 申请/冲销/还款金额（元）
    biz_date = Column(Date, nullable=False, index=True)
    ref_type = Column(String(32))  # voucher / expense / manual
    ref_id = Column(String(64))
    description = Column(Text)
    extra = Column(JSON)


# ---------- Phase 4：预算占位 ----------
class FctBudget(Base, TimestampMixin):
    """项目/期间预算（编制与占用占位）"""
    __tablename__ = "fct_budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, server_default="", index=True)
    budget_type = Column(String(16), nullable=False, index=True)  # project / period
    period = Column(String(32), nullable=False, index=True)  # 202602 或 project_id
    category = Column(String(64), nullable=False, index=True)  # 费用类别
    amount = Column(Numeric(18, 2), nullable=False, default=0)  # 预算金额
    used = Column(Numeric(18, 2), nullable=False, default=0)  # 已占用
    status = Column(String(20), default="active", nullable=False)  # active / frozen / closed
    extra = Column(JSON)


class FctBudgetControl(Base, TimestampMixin):
    """预算控制配置：制单/过账/付款时是否强制校验预算、是否自动占用。entity_id/category 空表示「全部」。"""
    __tablename__ = "fct_budget_control"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, server_default="", index=True)
    budget_type = Column(String(16), nullable=False, index=True)  # period / project
    category = Column(String(64), nullable=False, server_default="", index=True)
    enforce_check = Column(String(8), nullable=False, server_default="false")  # true: 制单/过账/付款前必须校验，超预算拒绝
    auto_occupy = Column(String(8), nullable=False, server_default="false")   # true: 成功后自动占用预算
    extra = Column(JSON)


# ---------- Phase 4：审批流占位 ----------
class FctApprovalRecord(Base, TimestampMixin):
    """审批记录占位（凭证/付款/费用等，与 OA 或工作流对接）"""
    __tablename__ = "fct_approval_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    ref_type = Column(String(32), nullable=False, index=True)  # voucher / payment / expense
    ref_id = Column(String(64), nullable=False, index=True)  # 业务单 id
    step = Column(Integer, nullable=False, default=1)  # 审批步骤
    status = Column(String(20), default="pending", nullable=False)  # pending / approved / rejected
    approved_at = Column(String(32))  # ISO8601
    approved_by = Column(String(64))
    comment = Column(Text)
    extra = Column(JSON)  # 工作流 id、回调 URL 等
