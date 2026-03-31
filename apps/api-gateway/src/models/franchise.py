"""
加盟商管理模型
核心关系：Franchisor（总部/品牌方）→ FranchiseContract（加盟合同）→ FranchiseeStore（加盟门店）
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from .base import Base


class Franchisee(Base):
    """加盟商（法人/个人）"""

    __tablename__ = "franchisees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)  # 归属品牌
    company_name = Column(String(128), nullable=False)          # 公司名
    contact_name = Column(String(64))
    contact_phone = Column(String(20))
    contact_email = Column(String(128))
    status = Column(String(20), nullable=False, default="active")
    # 财务信息（bank_account 加密存储，使用 src.core.crypto.field_crypto）
    bank_account = Column(String(256))    # 结算银行账号（ENC:前缀表示已加密）
    tax_no = Column(String(32))           # 税号
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": str(self.id),
            "brand_id": self.brand_id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "contact_email": self.contact_email,
            "status": self.status,
            "tax_no": self.tax_no,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FranchiseContract(Base):
    """加盟合同"""

    __tablename__ = "franchise_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    franchisee_id = Column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True, index=True)    # 对应的门店（stores.id 是 String）
    contract_no = Column(String(32), nullable=False, unique=True)
    contract_type = Column(String(30), nullable=False)          # full_franchise / licensed / area_franchise
    # 费用条款
    franchise_fee_fen = Column(Integer, nullable=False, default=0)    # 加盟费（分）
    royalty_rate = Column(Float, nullable=False, default=0.05)         # 提成率（0.05 = 5%）
    marketing_fund_rate = Column(Float, nullable=False, default=0.02)  # 市场基金率（0.02 = 2%）
    # 周期
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    renewal_count = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="draft")       # draft/signed/active/expired/terminated
    signed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": str(self.id),
            "franchisee_id": str(self.franchisee_id),
            "brand_id": self.brand_id,
            "store_id": self.store_id,
            "contract_no": self.contract_no,
            "contract_type": self.contract_type,
            "franchise_fee_fen": self.franchise_fee_fen,
            "franchise_fee_yuan": round(self.franchise_fee_fen / 100, 2) if self.franchise_fee_fen else 0,
            "royalty_rate": self.royalty_rate,
            "marketing_fund_rate": self.marketing_fund_rate,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "renewal_count": self.renewal_count,
            "status": self.status,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FranchiseRoyalty(Base):
    """加盟费/提成结算记录（月度）"""

    __tablename__ = "franchise_royalties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    franchisee_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)
    period_year = Column(Integer, nullable=False)    # 年
    period_month = Column(Integer, nullable=False)   # 月（1-12）
    gross_revenue_fen = Column(Integer, nullable=False, default=0)   # 月营收（分）
    royalty_amount_fen = Column(Integer, nullable=False, default=0)  # 提成金额（分）
    marketing_fund_fen = Column(Integer, nullable=False, default=0)  # 市场基金（分）
    total_due_fen = Column(Integer, nullable=False, default=0)       # 合计应付（分）
    status = Column(String(20), nullable=False, default="pending")   # pending/invoiced/paid/overdue
    due_date = Column(Date, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    payment_reference = Column(String(128), nullable=True)           # 付款凭证号
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("contract_id", "period_year", "period_month", name="uq_royalty_contract_period"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "contract_id": str(self.contract_id),
            "franchisee_id": str(self.franchisee_id),
            "store_id": self.store_id,
            "period_year": self.period_year,
            "period_month": self.period_month,
            "gross_revenue_fen": self.gross_revenue_fen,
            "gross_revenue_yuan": round(self.gross_revenue_fen / 100, 2),
            "royalty_amount_fen": self.royalty_amount_fen,
            "royalty_amount_yuan": round(self.royalty_amount_fen / 100, 2),
            "marketing_fund_fen": self.marketing_fund_fen,
            "marketing_fund_yuan": round(self.marketing_fund_fen / 100, 2),
            "total_due_fen": self.total_due_fen,
            "total_due_yuan": round(self.total_due_fen / 100, 2),
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "payment_reference": self.payment_reference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FranchiseePortalAccess(Base):
    """加盟商门户访问权限"""

    __tablename__ = "franchisee_portal_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    franchisee_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # 关联用户账号
    role = Column(String(20), nullable=False, default="viewer")         # owner/manager/viewer
    # store_ids 为 NULL 表示可访问该加盟合同内全部门店
    store_ids = Column(ARRAY(String), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": str(self.id),
            "franchisee_id": str(self.franchisee_id),
            "user_id": str(self.user_id),
            "role": self.role,
            "store_ids": self.store_ids,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
