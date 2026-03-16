"""电子发票模型 — 支持诺诺/百旺平台的数电票开具/红冲/查验"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class InvoicePlatform(str, enum.Enum):
    NUONUO = "nuonuo"
    BAIWANG = "baiwang"


class InvoiceType(str, enum.Enum):
    NORMAL_ELECTRONIC = "normal_electronic"  # 普通电子发票
    SPECIAL_ELECTRONIC = "special_electronic"  # 增值税专用电子发票
    NORMAL_PAPER = "normal_paper"  # 普通纸质发票


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUING = "issuing"  # 提交开票中（异步）
    ISSUED = "issued"
    VOID_PENDING = "void_pending"
    VOIDED = "voided"
    RED_PENDING = "red_pending"  # 红冲申请中
    RED_ISSUED = "red_issued"  # 红冲已开


class EInvoice(Base, TimestampMixin):
    __tablename__ = "e_invoices"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True, index=True)
    order_id = Column(String(50), nullable=True, index=True)  # 关联订单

    # 发票基本信息
    invoice_type = Column(String(30), nullable=False, default=InvoiceType.NORMAL_ELECTRONIC.value)
    invoice_code = Column(String(20), nullable=True)  # 发票代码（平台返回）
    invoice_number = Column(String(20), nullable=True)  # 发票号码

    # 购方信息
    buyer_name = Column(String(200), nullable=False)
    buyer_tax_number = Column(String(20), nullable=True)
    buyer_address = Column(String(300), nullable=True)
    buyer_phone = Column(String(30), nullable=True)
    buyer_bank_account = Column(String(100), nullable=True)

    # 销方信息（从品牌配置读取）
    seller_name = Column(String(200), nullable=False)
    seller_tax_number = Column(String(20), nullable=False)

    # 金额（分）
    total_amount_fen = Column(Integer, nullable=False)  # 合计金额（含税）
    tax_amount_fen = Column(Integer, nullable=False, default=0)  # 税额
    amount_without_tax_fen = Column(Integer, nullable=False, default=0)  # 不含税金额

    # 开票平台
    platform = Column(String(20), nullable=False, default=InvoicePlatform.NUONUO.value)
    platform_invoice_id = Column(String(100), nullable=True, unique=True)  # 平台流水号
    platform_serial_no = Column(String(100), nullable=True)  # 提交请求流水号

    # 状态
    status = Column(String(20), nullable=False, default=InvoiceStatus.DRAFT.value, index=True)

    # 发票文件
    pdf_url = Column(Text, nullable=True)
    ofd_url = Column(Text, nullable=True)
    xml_url = Column(Text, nullable=True)

    # 红冲关联
    original_invoice_id = Column(UUID(as_uuid=True), nullable=True)  # 被红冲的原票ID
    red_reason = Column(String(200), nullable=True)

    # 备注
    remark = Column(Text, nullable=True)
    issued_at = Column(DateTime, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    operator = Column(String(100), nullable=True)  # 开票人


class EInvoiceItem(Base, TimestampMixin):
    __tablename__ = "e_invoice_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("e_invoices.id"), nullable=False, index=True)

    item_name = Column(String(200), nullable=False)  # 商品名称
    item_code = Column(String(50), nullable=True)  # 税收分类编码
    specification = Column(String(100), nullable=True)  # 规格型号
    unit = Column(String(20), nullable=True)  # 计量单位
    quantity = Column(Integer, nullable=True)
    unit_price_fen = Column(Integer, nullable=True)  # 单价（分）
    amount_fen = Column(Integer, nullable=False)  # 金额（分）
    tax_rate = Column(Integer, nullable=False, default=600)  # 税率（万分比，600=6%）
    tax_amount_fen = Column(Integer, nullable=False, default=0)
