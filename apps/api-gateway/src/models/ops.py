"""
运维数据库模型
OpsEvent / OpsAsset / OpsMaintenancePlan
"""
import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, JSON, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class OpsEventSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OpsEventStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class OpsAssetType(str, enum.Enum):
    # 软件域
    POS = "pos"
    ERP = "erp"
    MEMBER = "member"
    # 硬件域
    PRINTER = "printer"
    KDS = "kds"
    DOOR_ACCESS = "door_access"
    CAMERA = "camera"
    SERVER = "server"
    # 网络域
    ROUTER = "router"
    SWITCH = "switch"
    AP = "ap"
    VPN = "vpn"


class OpsMaintenancePriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class OpsEvent(Base):
    """运维事件记录"""
    __tablename__ = "ops_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    event_type = Column(String(50), nullable=False)   # health_check / fault / security / maintenance
    severity = Column(String(20), nullable=False, default=OpsEventSeverity.MEDIUM.value)
    component = Column(String(100), nullable=True)    # pos / router / printer …
    description = Column(Text, nullable=False)
    raw_data = Column(JSON, nullable=True)            # 原始上报数据
    diagnosis = Column(Text, nullable=True)           # Agent 诊断结论
    resolution = Column(Text, nullable=True)          # 处置建议 / Runbook
    status = Column(String(20), nullable=False, default=OpsEventStatus.OPEN.value)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_ops_events_store_id", "store_id"),
        Index("ix_ops_events_severity", "severity"),
        Index("ix_ops_events_status", "status"),
        Index("ix_ops_events_created", "created_at"),
    )


class OpsAsset(Base):
    """IT 资产台账"""
    __tablename__ = "ops_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    asset_type = Column(String(30), nullable=False)
    name = Column(String(100), nullable=False)
    ip_address = Column(String(45), nullable=True)
    mac_address = Column(String(17), nullable=True)
    firmware_version = Column(String(50), nullable=True)
    serial_number = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="online")  # online/offline/degraded
    last_seen = Column(DateTime, nullable=True)
    asset_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_ops_assets_store_id", "store_id"),
        Index("ix_ops_assets_type", "asset_type"),
        Index("ix_ops_assets_status", "status"),
    )


class OpsMaintenancePlan(Base):
    """预测性维护计划"""
    __tablename__ = "ops_maintenance_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("ops_assets.id"), nullable=True)
    plan_type = Column(String(50), nullable=False)    # preventive / predictive / corrective
    description = Column(Text, nullable=False)
    priority = Column(String(20), nullable=False, default=OpsMaintenancePriority.MEDIUM.value)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending/in_progress/done/skipped
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_ops_mp_store_id", "store_id"),
        Index("ix_ops_mp_status", "status"),
        Index("ix_ops_mp_scheduled", "scheduled_at"),
    )
