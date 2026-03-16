"""
FCT 业财税资金一体化数据模型

新增两张表：
  fct_tax_records      — 月度税务测算（增值税 / 企业所得税 / 附加税）
  fct_cash_flow_items  — 资金流预测明细（每日预测进出流）
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class TaxType(str, enum.Enum):
    VAT = "vat"  # 增值税
    CIT = "cit"  # 企业所得税
    SURCHARGE = "surcharge"  # 附加税（城建税 + 教育附加）
    TOTAL = "total"  # 合计


class TaxpayerType(str, enum.Enum):
    GENERAL = "general"  # 一般纳税人（VAT 6%）
    SMALL = "small"  # 小规模纳税人（VAT 3%）
    MICRO = "micro"  # 微型企业（CIT 20%）


class CashFlowDirection(str, enum.Enum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class FCTTaxRecord(Base, TimestampMixin):
    """
    月度税务测算记录。

    每个自然月末（或手动触发）生成一条测算记录：
      - 收入口径：POS 实收 + 宴会预收
      - 增值税（VAT）= 含税收入 / (1 + 税率) × 税率
      - 企业所得税（CIT）= 应纳税所得额 × 税率（利润率假设 10-15%）
      - 附加税 = VAT × 12%（城建 7% + 教育附加 3% + 地方教育 2%）
    """

    __tablename__ = "fct_tax_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)

    # 计税周期
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    period_label = Column(String(20))  # e.g. "2026-05"

    # 纳税人类型
    taxpayer_type = Column(Enum(TaxpayerType), default=TaxpayerType.GENERAL)

    # 收入口径（分）
    gross_revenue = Column(Integer, default=0)  # POS含税总收入
    banquet_revenue = Column(Integer, default=0)  # 宴会收入
    other_revenue = Column(Integer, default=0)  # 其他收入
    total_taxable = Column(Integer, default=0)  # 应税总收入

    # 税额测算（分）
    vat_rate = Column(Float, default=0.06)  # 增值税率
    vat_amount = Column(Integer, default=0)  # 增值税额
    vat_surcharge = Column(Integer, default=0)  # 增值税附加（12% × VAT）
    deductible_input = Column(Integer, default=0)  # 进项税额（食材采购增值税）
    net_vat = Column(Integer, default=0)  # 应纳增值税 = 销项 - 进项

    cit_rate = Column(Float, default=0.20)  # 企业所得税率
    estimated_profit = Column(Integer, default=0)  # 预估利润（分）
    cit_amount = Column(Integer, default=0)  # 企业所得税额

    total_tax = Column(Integer, default=0)  # 合计应纳税额

    # 状态
    is_finalized = Column(Boolean, default=False)  # 是否已确认入账
    notes = Column(Text)
    generated_by = Column(String(100), default="system")

    __table_args__ = (Index("ix_fct_tax_store_period", "store_id", "year", "month"),)


class FCTCashFlowItem(Base, TimestampMixin):
    """
    资金流预测明细（逐日）。

    每次触发预测时写入 forecast_date 之后 N 天的预测数据，
    方便前端展示 30/60/90 天资金流瀑布图。
    """

    __tablename__ = "fct_cash_flow_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)

    # 预测日期
    forecast_date = Column(Date, nullable=False, index=True)
    is_actual = Column(Boolean, default=False)  # True = 已发生的实际值

    # 进流（分）
    pos_inflow = Column(Integer, default=0)  # POS 营业收入预测
    prepaid_inflow = Column(Integer, default=0)  # 预收款（宴会定金等）
    other_inflow = Column(Integer, default=0)
    total_inflow = Column(Integer, default=0)

    # 出流（分）
    food_cost_outflow = Column(Integer, default=0)  # 食材采购
    labor_outflow = Column(Integer, default=0)  # 人工
    rent_outflow = Column(Integer, default=0)  # 房租（按日分摊）
    utilities_outflow = Column(Integer, default=0)  # 水电
    tax_outflow = Column(Integer, default=0)  # 税款
    other_outflow = Column(Integer, default=0)
    total_outflow = Column(Integer, default=0)

    # 净流 & 累计
    net_flow = Column(Integer, default=0)  # 当日净流
    cumulative_balance = Column(Integer, default=0)  # 累计余额

    # 预警
    is_alert = Column(Boolean, default=False)  # 是否触发资金预警
    alert_message = Column(String(200))

    # 预测置信度
    confidence = Column(Float, default=0.8)  # 0-1

    __table_args__ = (Index("ix_fct_cashflow_store_date", "store_id", "forecast_date"),)


class FCTBudgetControl(Base, TimestampMixin):
    """预算控制配置（enforce_check / auto_occupy）。"""

    __tablename__ = "fct_budget_control"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, default="", index=True)
    budget_type = Column(String(16), nullable=False, index=True)
    category = Column(String(64), nullable=False, default="", index=True)
    enforce_check = Column(String(8), nullable=False, default="false")
    auto_occupy = Column(String(8), nullable=False, default="false")
    extra = Column(JSON)

    __table_args__ = (
        Index(
            "ix_fct_budget_control_tenant_entity_type_cat",
            "tenant_id",
            "entity_id",
            "budget_type",
            "category",
            unique=True,
        ),
    )


class FCTPettyCash(Base, TimestampMixin):
    """备用金主档。"""

    __tablename__ = "fct_petty_cash"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    cash_type = Column(String(16), nullable=False, index=True)
    amount_limit = Column(Numeric(18, 2), nullable=False, default=0)
    current_balance = Column(Numeric(18, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="active")
    extra = Column(JSON)

    records = relationship(
        "FCTPettyCashRecord",
        back_populates="petty_cash",
        cascade="all, delete-orphan",
        lazy="select",
    )


class FCTPettyCashRecord(Base, TimestampMixin):
    """备用金收支明细。"""

    __tablename__ = "fct_petty_cash_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    petty_cash_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fct_petty_cash.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_type = Column(String(16), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    biz_date = Column(Date, nullable=False, index=True)
    ref_type = Column(String(32))
    ref_id = Column(String(64))
    description = Column(Text)
    extra = Column(JSON)

    petty_cash = relationship("FCTPettyCash", back_populates="records")


class FCTApprovalRecord(Base, TimestampMixin):
    """审批流记录。"""

    __tablename__ = "fct_approval_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    ref_type = Column(String(32), nullable=False, index=True)
    ref_id = Column(String(64), nullable=False, index=True)
    step = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="pending")
    approved_at = Column(String(32))
    approved_by = Column(String(64))
    comment = Column(Text)
    extra = Column(JSON)


class FCTPeriod(Base, TimestampMixin):
    """会计期间状态（open/closed）。"""

    __tablename__ = "fct_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    period_key = Column(String(16), nullable=False, index=True)  # YYYY-MM
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    closed_at = Column(String(32))
    extra = Column(JSON)

    __table_args__ = (Index("ix_fct_periods_tenant_period", "tenant_id", "period_key", unique=True),)


# ── 会计凭证（双分录）───────────────────────────────────────────────────────


class Voucher(Base, TimestampMixin):
    """
    会计凭证主表。

    每次业务事件（门店日结、采购入库、工资发放等）触发一张凭证，
    凭证借贷必须平衡（允许 0.01 元尾差）。
    """

    __tablename__ = "fct_vouchers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voucher_no = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(80), nullable=False)  # store_daily_settlement / purchase_receipt / …
    event_id = Column(String(100), index=True)  # 来源业务事件 ID（幂等键）
    biz_date = Column(Date, nullable=False)
    status = Column(String(20), default="posted")  # draft / posted / reversed
    description = Column(Text)

    lines = relationship("VoucherLine", back_populates="voucher", cascade="all, delete-orphan", lazy="select")

    __table_args__ = (
        Index("ix_fct_voucher_store_date", "store_id", "biz_date"),
        Index("ix_fct_voucher_event", "event_type", "event_id"),
    )


class VoucherLine(Base):
    """
    凭证分录行。

    遵循中国企业会计准则：
      - 借方（debit）和贷方（credit）互斥，同一行不同时有值
      - Decimal(15, 2) 存储元，精度满足日常餐饮场景
    """

    __tablename__ = "fct_voucher_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voucher_id = Column(UUID(as_uuid=True), ForeignKey("fct_vouchers.id", ondelete="CASCADE"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False, default=1)  # 行序号
    account_code = Column(String(20), nullable=False)
    account_name = Column(String(100))
    debit = Column(Numeric(15, 2))  # 借方金额（元）
    credit = Column(Numeric(15, 2))  # 贷方金额（元）
    auxiliary = Column(JSON)  # 辅助核算（供应商ID、部门等）
    summary = Column(String(200))  # 摘要

    voucher = relationship("Voucher", back_populates="lines")
