"""
FCT 业财税资金一体化数据模型

新增两张表：
  fct_tax_records      — 月度税务测算（增值税 / 企业所得税 / 附加税）
  fct_cash_flow_items  — 资金流预测明细（每日预测进出流）
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Date, DateTime, Boolean,
    Text, JSON, Index, Enum,
)
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class TaxType(str, enum.Enum):
    VAT          = "vat"           # 增值税
    CIT          = "cit"           # 企业所得税
    SURCHARGE    = "surcharge"     # 附加税（城建税 + 教育附加）
    TOTAL        = "total"         # 合计


class TaxpayerType(str, enum.Enum):
    GENERAL      = "general"       # 一般纳税人（VAT 6%）
    SMALL        = "small"         # 小规模纳税人（VAT 3%）
    MICRO        = "micro"         # 微型企业（CIT 20%）


class CashFlowDirection(str, enum.Enum):
    INFLOW       = "inflow"
    OUTFLOW      = "outflow"


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

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id        = Column(String(50), nullable=False, index=True)

    # 计税周期
    year            = Column(Integer, nullable=False)
    month           = Column(Integer, nullable=False)
    period_label    = Column(String(20))              # e.g. "2026-05"

    # 纳税人类型
    taxpayer_type   = Column(Enum(TaxpayerType), default=TaxpayerType.GENERAL)

    # 收入口径（分）
    gross_revenue       = Column(Integer, default=0)   # POS含税总收入
    banquet_revenue     = Column(Integer, default=0)   # 宴会收入
    other_revenue       = Column(Integer, default=0)   # 其他收入
    total_taxable       = Column(Integer, default=0)   # 应税总收入

    # 税额测算（分）
    vat_rate            = Column(Float, default=0.06)  # 增值税率
    vat_amount          = Column(Integer, default=0)   # 增值税额
    vat_surcharge       = Column(Integer, default=0)   # 增值税附加（12% × VAT）
    deductible_input    = Column(Integer, default=0)   # 进项税额（食材采购增值税）
    net_vat             = Column(Integer, default=0)   # 应纳增值税 = 销项 - 进项

    cit_rate            = Column(Float, default=0.20)  # 企业所得税率
    estimated_profit    = Column(Integer, default=0)   # 预估利润（分）
    cit_amount          = Column(Integer, default=0)   # 企业所得税额

    total_tax           = Column(Integer, default=0)   # 合计应纳税额

    # 状态
    is_finalized        = Column(Boolean, default=False)  # 是否已确认入账
    notes               = Column(Text)
    generated_by        = Column(String(100), default="system")

    __table_args__ = (
        Index("ix_fct_tax_store_period", "store_id", "year", "month"),
    )


class FCTCashFlowItem(Base, TimestampMixin):
    """
    资金流预测明细（逐日）。

    每次触发预测时写入 forecast_date 之后 N 天的预测数据，
    方便前端展示 30/60/90 天资金流瀑布图。
    """
    __tablename__ = "fct_cash_flow_items"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id        = Column(String(50), nullable=False, index=True)

    # 预测日期
    forecast_date   = Column(Date, nullable=False, index=True)
    is_actual       = Column(Boolean, default=False)  # True = 已发生的实际值

    # 进流（分）
    pos_inflow          = Column(Integer, default=0)   # POS 营业收入预测
    prepaid_inflow      = Column(Integer, default=0)   # 预收款（宴会定金等）
    other_inflow        = Column(Integer, default=0)
    total_inflow        = Column(Integer, default=0)

    # 出流（分）
    food_cost_outflow   = Column(Integer, default=0)   # 食材采购
    labor_outflow       = Column(Integer, default=0)   # 人工
    rent_outflow        = Column(Integer, default=0)   # 房租（按日分摊）
    utilities_outflow   = Column(Integer, default=0)   # 水电
    tax_outflow         = Column(Integer, default=0)   # 税款
    other_outflow       = Column(Integer, default=0)
    total_outflow       = Column(Integer, default=0)

    # 净流 & 累计
    net_flow            = Column(Integer, default=0)   # 当日净流
    cumulative_balance  = Column(Integer, default=0)   # 累计余额

    # 预警
    is_alert            = Column(Boolean, default=False)   # 是否触发资金预警
    alert_message       = Column(String(200))

    # 预测置信度
    confidence          = Column(Float, default=0.8)  # 0-1

    __table_args__ = (
        Index("ix_fct_cashflow_store_date", "store_id", "forecast_date"),
    )
