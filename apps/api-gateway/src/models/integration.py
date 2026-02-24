"""
External System Integration Models
外部系统集成模型
"""
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Enum, Text, Boolean, Integer, Float, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base


class IntegrationType(str, enum.Enum):
    """集成类型"""
    POS = "pos"  # POS系统
    SUPPLIER = "supplier"  # 供应商系统
    MEMBER = "member"  # 会员系统
    PAYMENT = "payment"  # 支付系统
    DELIVERY = "delivery"  # 配送系统
    ERP = "erp"  # ERP系统
    RESERVATION = "reservation"  # 预订系统


class IntegrationStatus(str, enum.Enum):
    """集成状态"""
    ACTIVE = "active"  # 激活
    INACTIVE = "inactive"  # 未激活
    ERROR = "error"  # 错误
    TESTING = "testing"  # 测试中


class SyncStatus(str, enum.Enum):
    """同步状态"""
    PENDING = "pending"  # 待同步
    SYNCING = "syncing"  # 同步中
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    PARTIAL = "partial"  # 部分成功


class ExternalSystem(Base):
    """外部系统配置"""
    __tablename__ = "external_systems"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, comment="系统名称")
    type = Column(
        Enum(IntegrationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        comment="集成类型"
    )
    provider = Column(String(100), comment="提供商名称")
    version = Column(String(50), comment="版本")
    status = Column(
        Enum(IntegrationStatus, values_callable=lambda x: [e.value for e in x]),
        default=IntegrationStatus.INACTIVE,
        comment="状态"
    )
    store_id = Column(String(50), comment="关联门店ID")

    # 连接配置
    api_endpoint = Column(String(500), comment="API端点")
    api_key = Column(String(500), comment="API密钥")
    api_secret = Column(String(500), comment="API密钥")
    webhook_url = Column(String(500), comment="Webhook URL")
    webhook_secret = Column(String(500), comment="Webhook签名密钥(HMAC-SHA256)")
    config = Column(JSON, comment="其他配置(JSON)")

    # 同步配置
    sync_enabled = Column(Boolean, default=True, comment="是否启用同步")
    sync_interval = Column(Integer, default=300, comment="同步间隔(秒)")
    last_sync_at = Column(DateTime, comment="最后同步时间")
    last_sync_status = Column(
        Enum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        comment="最后同步状态"
    )
    last_error = Column(Text, comment="最后错误信息")

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    created_by = Column(String(50), comment="创建人")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "name": self.name,
            "type": self.type.value if self.type else None,
            "provider": self.provider,
            "version": self.version,
            "status": self.status.value if self.status else None,
            "store_id": self.store_id,
            "api_endpoint": self.api_endpoint,
            "webhook_url": self.webhook_url,
            "sync_enabled": self.sync_enabled,
            "sync_interval": self.sync_interval,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status.value if self.last_sync_status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SyncLog(Base):
    """同步日志"""
    __tablename__ = "sync_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id = Column(UUID(as_uuid=True), nullable=False, comment="外部系统ID")
    sync_type = Column(String(50), nullable=False, comment="同步类型")
    status = Column(
        Enum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        comment="同步状态"
    )

    # 同步详情
    records_total = Column(Integer, default=0, comment="总记录数")
    records_success = Column(Integer, default=0, comment="成功记录数")
    records_failed = Column(Integer, default=0, comment="失败记录数")

    # 时间信息
    started_at = Column(DateTime, nullable=False, comment="开始时间")
    completed_at = Column(DateTime, comment="完成时间")
    duration_seconds = Column(Float, comment="耗时(秒)")

    # 错误信息
    error_message = Column(Text, comment="错误信息")
    error_details = Column(JSON, comment="错误详情")

    # 同步数据
    request_data = Column(JSON, comment="请求数据")
    response_data = Column(JSON, comment="响应数据")

    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "system_id": str(self.system_id),
            "sync_type": self.sync_type,
            "status": self.status.value if self.status else None,
            "records_total": self.records_total,
            "records_success": self.records_success,
            "records_failed": self.records_failed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class POSTransaction(Base):
    """POS交易记录"""
    __tablename__ = "pos_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id = Column(UUID(as_uuid=True), nullable=False, comment="外部系统ID")
    store_id = Column(String(50), nullable=False, comment="门店ID")

    # POS交易信息
    pos_transaction_id = Column(String(100), nullable=False, unique=True, comment="POS交易ID")
    pos_order_number = Column(String(100), comment="POS订单号")
    transaction_type = Column(String(50), comment="交易类型: sale/refund/void")

    # 金额信息
    subtotal = Column(Numeric(12, 2), default=0, comment="小计")
    tax = Column(Numeric(12, 2), default=0, comment="税费")
    discount = Column(Numeric(12, 2), default=0, comment="折扣")
    total = Column(Numeric(12, 2), default=0, comment="总金额")
    payment_method = Column(String(50), comment="支付方式")

    # 订单详情
    items = Column(JSON, comment="订单项目")
    customer_info = Column(JSON, comment="客户信息")

    # 同步状态
    sync_status = Column(
        Enum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        default=SyncStatus.PENDING,
        comment="同步状态"
    )
    synced_at = Column(DateTime, comment="同步时间")

    # 时间信息
    transaction_time = Column(DateTime, nullable=False, comment="交易时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 原始数据
    raw_data = Column(JSON, comment="原始POS数据")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "system_id": str(self.system_id),
            "store_id": self.store_id,
            "pos_transaction_id": self.pos_transaction_id,
            "pos_order_number": self.pos_order_number,
            "transaction_type": self.transaction_type,
            "subtotal": self.subtotal,
            "tax": self.tax,
            "discount": self.discount,
            "total": self.total,
            "payment_method": self.payment_method,
            "sync_status": self.sync_status.value if self.sync_status else None,
            "transaction_time": self.transaction_time.isoformat() if self.transaction_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SupplierOrder(Base):
    """供应商订单"""
    __tablename__ = "supplier_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id = Column(UUID(as_uuid=True), nullable=False, comment="外部系统ID")
    store_id = Column(String(50), nullable=False, comment="门店ID")

    # 订单信息
    order_number = Column(String(100), nullable=False, unique=True, comment="订单号")
    supplier_id = Column(String(100), comment="供应商ID")
    supplier_name = Column(String(200), comment="供应商名称")
    order_type = Column(String(50), comment="订单类型: purchase/return")
    status = Column(String(50), comment="订单状态: pending/confirmed/shipped/delivered/cancelled")

    # 金额信息
    subtotal = Column(Numeric(12, 2), default=0, comment="小计")
    tax = Column(Numeric(12, 2), default=0, comment="税费")
    shipping = Column(Numeric(12, 2), default=0, comment="运费")
    total = Column(Numeric(12, 2), default=0, comment="总金额")

    # 订单详情
    items = Column(JSON, comment="订单项目")
    delivery_info = Column(JSON, comment="配送信息")

    # 时间信息
    order_date = Column(DateTime, nullable=False, comment="订单日期")
    expected_delivery = Column(DateTime, comment="预计送达时间")
    actual_delivery = Column(DateTime, comment="实际送达时间")

    # 同步状态
    sync_status = Column(
        Enum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        default=SyncStatus.PENDING,
        comment="同步状态"
    )
    synced_at = Column(DateTime, comment="同步时间")

    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 原始数据
    raw_data = Column(JSON, comment="原始供应商数据")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "system_id": str(self.system_id),
            "store_id": self.store_id,
            "order_number": self.order_number,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "order_type": self.order_type,
            "status": self.status,
            "subtotal": self.subtotal,
            "tax": self.tax,
            "shipping": self.shipping,
            "total": self.total,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "expected_delivery": self.expected_delivery.isoformat() if self.expected_delivery else None,
            "actual_delivery": self.actual_delivery.isoformat() if self.actual_delivery else None,
            "sync_status": self.sync_status.value if self.sync_status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MemberSync(Base):
    """会员同步记录"""
    __tablename__ = "member_syncs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id = Column(UUID(as_uuid=True), nullable=False, comment="外部系统ID")

    # 会员信息
    member_id = Column(String(100), nullable=False, comment="会员ID")
    external_member_id = Column(String(100), comment="外部系统会员ID")
    phone = Column(String(20), comment="手机号")
    name = Column(String(100), comment="姓名")
    email = Column(String(200), comment="邮箱")

    # 会员等级和积分
    level = Column(String(50), comment="会员等级")
    points = Column(Integer, default=0, comment="积分")
    balance = Column(Numeric(12, 2), default=0, comment="余额")

    # 同步状态
    sync_status = Column(
        Enum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        default=SyncStatus.PENDING,
        comment="同步状态"
    )
    synced_at = Column(DateTime, comment="同步时间")
    last_activity = Column(DateTime, comment="最后活动时间")

    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 原始数据
    raw_data = Column(JSON, comment="原始会员数据")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "system_id": str(self.system_id),
            "member_id": self.member_id,
            "external_member_id": self.external_member_id,
            "phone": self.phone,
            "name": self.name,
            "email": self.email,
            "level": self.level,
            "points": self.points,
            "balance": self.balance,
            "sync_status": self.sync_status.value if self.sync_status else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ReservationSync(Base):
    """预订同步记录"""
    __tablename__ = "reservation_syncs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id = Column(UUID(as_uuid=True), nullable=False, comment="外部系统ID")
    store_id = Column(String(50), nullable=False, comment="门店ID")

    # 预订信息
    reservation_id = Column(String(100), nullable=False, comment="预订ID")
    external_reservation_id = Column(String(100), comment="外部系统预订ID")
    reservation_number = Column(String(100), comment="预订号")

    # 客户信息
    customer_name = Column(String(100), nullable=False, comment="客户姓名")
    customer_phone = Column(String(20), nullable=False, comment="客户电话")
    customer_count = Column(Integer, nullable=False, comment="就餐人数")

    # 预订时间
    reservation_date = Column(DateTime, nullable=False, comment="预订日期")
    reservation_time = Column(String(20), nullable=False, comment="预订时间段")
    arrival_time = Column(DateTime, comment="实际到店时间")

    # 桌台信息
    table_type = Column(String(50), comment="桌台类型")
    table_number = Column(String(20), comment="桌号")
    area = Column(String(50), comment="区域")

    # 预订状态
    status = Column(String(50), nullable=False, comment="预订状态: pending/confirmed/arrived/seated/completed/cancelled/no_show")

    # 特殊要求
    special_requirements = Column(Text, comment="特殊要求")
    notes = Column(Text, comment="备注")

    # 预付信息
    deposit_required = Column(Boolean, default=False, comment="是否需要预付")
    deposit_amount = Column(Numeric(12, 2), default=0, comment="预付金额")
    deposit_paid = Column(Boolean, default=False, comment="是否已预付")

    # 来源信息
    source = Column(String(50), comment="预订来源: yiding/phone/wechat/app")
    channel = Column(String(50), comment="渠道")

    # 同步状态
    sync_status = Column(
        Enum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        default=SyncStatus.PENDING,
        comment="同步状态"
    )
    synced_at = Column(DateTime, comment="同步时间")

    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    cancelled_at = Column(DateTime, comment="取消时间")

    # 原始数据
    raw_data = Column(JSON, comment="原始预订数据")

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "system_id": str(self.system_id),
            "store_id": self.store_id,
            "reservation_id": self.reservation_id,
            "external_reservation_id": self.external_reservation_id,
            "reservation_number": self.reservation_number,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_count": self.customer_count,
            "reservation_date": self.reservation_date.isoformat() if self.reservation_date else None,
            "reservation_time": self.reservation_time,
            "arrival_time": self.arrival_time.isoformat() if self.arrival_time else None,
            "table_type": self.table_type,
            "table_number": self.table_number,
            "area": self.area,
            "status": self.status,
            "special_requirements": self.special_requirements,
            "notes": self.notes,
            "deposit_required": self.deposit_required,
            "deposit_amount": self.deposit_amount,
            "deposit_paid": self.deposit_paid,
            "source": self.source,
            "sync_status": self.sync_status.value if self.sync_status else None,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
