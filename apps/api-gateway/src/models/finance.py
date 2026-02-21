"""
财务相关数据模型
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, JSON, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from .base import Base


class FinancialTransaction(Base):
    """财务交易记录模型"""

    __tablename__ = "financial_transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String, ForeignKey("stores.id"), nullable=False)
    transaction_date = Column(Date, nullable=False)
    transaction_type = Column(String(20), nullable=False)  # income, expense
    category = Column(String(50), nullable=False)  # sales, food_cost, labor_cost, rent, utilities, etc.
    subcategory = Column(String(50))
    amount = Column(Integer, nullable=False)  # 金额（分）
    description = Column(Text)
    reference_id = Column(String)  # 关联订单ID、采购订单ID等
    payment_method = Column(String(20))  # cash, card, wechat, alipay, etc.
    created_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    store = relationship("Store")


class Budget(Base):
    """预算模型"""

    __tablename__ = "budgets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String, ForeignKey("stores.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    category = Column(String(50), nullable=False)  # revenue, food_cost, labor_cost, etc.
    budgeted_amount = Column(Integer, nullable=False)  # 预算金额（分）
    actual_amount = Column(Integer, default=0)  # 实际金额（分）
    variance = Column(Integer, default=0)  # 差异（分）
    variance_percentage = Column(Float, default=0.0)  # 差异百分比
    notes = Column(Text)
    created_by = Column(String)
    approved_by = Column(String)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    store = relationship("Store")


class Invoice(Base):
    """发票模型"""

    __tablename__ = "invoices"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    store_id = Column(String, ForeignKey("stores.id"), nullable=False)
    invoice_type = Column(String(20), nullable=False)  # sales, purchase
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date)
    supplier_id = Column(String, ForeignKey("suppliers.id"))  # 供应商ID（采购发票）
    customer_name = Column(String(100))  # 客户名称（销售发票）
    tax_number = Column(String(50))  # 税号
    total_amount = Column(Integer, nullable=False)  # 总金额（分）
    tax_amount = Column(Integer, default=0)  # 税额（分）
    net_amount = Column(Integer, nullable=False)  # 净额（分）
    status = Column(String(20), default="pending")  # pending, paid, overdue, cancelled
    items = Column(JSON, default=list)  # 发票明细
    notes = Column(Text)
    created_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    store = relationship("Store")
    supplier = relationship("Supplier")


class FinancialReport(Base):
    """财务报表模型"""

    __tablename__ = "financial_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String, ForeignKey("stores.id"), nullable=False)
    report_type = Column(String(50), nullable=False)  # income_statement, cash_flow, balance_sheet
    period_type = Column(String(20), nullable=False)  # daily, weekly, monthly, quarterly, yearly
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    data = Column(JSON, nullable=False)  # 报表数据
    summary = Column(JSON)  # 汇总数据
    generated_by = Column(String)
    generated_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    store = relationship("Store")
