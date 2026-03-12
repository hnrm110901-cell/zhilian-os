"""
Edge Hub Models — Phase 9
屯象OS 门店边缘硬件层：边缘主机 / 设备 / 耳机绑定 / 告警
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer,
    String, Text, ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


# ── Enums ────────────────────────────────────────────────────────────────────

class HubStatus(str, enum.Enum):
    ONLINE   = "online"
    OFFLINE  = "offline"
    DEGRADED = "degraded"
    UPGRADING = "upgrading"


class DeviceType(str, enum.Enum):
    HEADSET = "headset"
    PRINTER = "printer"
    KDS     = "kds"
    SENSOR  = "sensor"
    CAMERA  = "camera"
    OTHER   = "other"


class DeviceStatus(str, enum.Enum):
    ONLINE  = "online"
    OFFLINE = "offline"
    ERROR   = "error"


class AlertLevel(str, enum.Enum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class AlertStatus(str, enum.Enum):
    OPEN     = "open"
    RESOLVED = "resolved"
    IGNORED  = "ignored"


class BindingStatus(str, enum.Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"


# ── Models ───────────────────────────────────────────────────────────────────

class EdgeHub(Base, TimestampMixin):
    """门店边缘主机"""
    __tablename__ = "edge_hubs"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id         = Column(String(36), nullable=False, index=True)
    hub_code         = Column(String(64), nullable=False, unique=True)
    name             = Column(String(128), nullable=True)
    status           = Column(String(32), nullable=False, default=HubStatus.OFFLINE)
    runtime_version  = Column(String(32), nullable=True)
    ip_address       = Column(String(64), nullable=True)
    mac_address      = Column(String(64), nullable=True)
    network_mode     = Column(String(32), nullable=False, default="cloud")
    last_heartbeat   = Column(DateTime, nullable=True)
    cpu_pct          = Column(Float, nullable=True)
    mem_pct          = Column(Float, nullable=True)
    disk_pct         = Column(Float, nullable=True)
    temperature_c    = Column(Float, nullable=True)
    uptime_seconds   = Column(Integer, nullable=True)
    pending_status_queue = Column(Integer, nullable=True)
    last_queue_error = Column(Text, nullable=True)
    device_secret_hash = Column(String(128), nullable=True)
    provisioned_at   = Column(DateTime, nullable=True)
    is_active        = Column(Boolean, nullable=False, default=True)

    devices  = relationship("EdgeDevice", back_populates="hub", lazy="select")
    alerts   = relationship("EdgeAlert",  back_populates="hub", lazy="select")


class EdgeDevice(Base, TimestampMixin):
    """门店边缘设备（耳机/打印机/KDS/传感器等）"""
    __tablename__ = "edge_devices"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hub_id       = Column(String(36), ForeignKey("edge_hubs.id"), nullable=False, index=True)
    store_id     = Column(String(36), nullable=False, index=True)
    device_code  = Column(String(64), nullable=False)
    device_type  = Column(String(32), nullable=False)
    name         = Column(String(128), nullable=True)
    status       = Column(String(32), nullable=False, default=DeviceStatus.OFFLINE)
    last_seen    = Column(DateTime, nullable=True)
    firmware_ver = Column(String(32), nullable=True)
    extra        = Column(JSON, nullable=True)

    hub      = relationship("EdgeHub",       back_populates="devices")
    bindings = relationship("HeadsetBinding", back_populates="device", lazy="select")


class HeadsetBinding(Base, TimestampMixin):
    """岗位与耳机绑定关系"""
    __tablename__ = "headset_bindings"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id    = Column(String(36), nullable=False, index=True)
    device_id   = Column(String(36), ForeignKey("edge_devices.id"), nullable=False)
    position    = Column(String(64), nullable=False)   # e.g. store_manager, front_manager
    employee_id = Column(String(36), nullable=True)
    channel     = Column(Integer, nullable=True)        # 通话频道号
    status      = Column(String(32), nullable=False, default=BindingStatus.ACTIVE)
    bound_at    = Column(DateTime, nullable=True, default=datetime.utcnow)
    unbound_at  = Column(DateTime, nullable=True)

    device = relationship("EdgeDevice", back_populates="bindings")


class EdgeAlert(Base, TimestampMixin):
    """边缘层告警"""
    __tablename__ = "edge_alerts"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id     = Column(String(36), nullable=False, index=True)
    hub_id       = Column(String(36), ForeignKey("edge_hubs.id"), nullable=True, index=True)
    device_id    = Column(String(36), nullable=True)
    level        = Column(String(8),  nullable=False, default=AlertLevel.P3)
    alert_type   = Column(String(64), nullable=False)   # headset_offline / hub_disconnect / etc.
    message      = Column(Text, nullable=True)
    status       = Column(String(32), nullable=False, default=AlertStatus.OPEN)
    resolved_at  = Column(DateTime, nullable=True)
    resolved_by  = Column(String(64), nullable=True)

    hub = relationship("EdgeHub", back_populates="alerts")
