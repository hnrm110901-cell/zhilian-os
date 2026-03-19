"""
运维数据库模型
OpsEvent / OpsAsset / OpsMaintenancePlan
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
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
    event_type = Column(String(50), nullable=False)  # health_check / fault / security / maintenance
    severity = Column(String(20), nullable=False, default=OpsEventSeverity.MEDIUM.value)
    component = Column(String(100), nullable=True)  # pos / router / printer …
    description = Column(Text, nullable=False)
    raw_data = Column(JSON, nullable=True)  # 原始上报数据
    diagnosis = Column(Text, nullable=True)  # Agent 诊断结论
    resolution = Column(Text, nullable=True)  # 处置建议 / Runbook
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
    plan_type = Column(String(50), nullable=False)  # preventive / predictive / corrective
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


# ── 运维监控时序表（V2.0 新增）─────────────────────────────────────────────────


class OpsDeviceReading(Base):
    """IoT设备时序读数（温度/功率/在线状态等）"""

    __tablename__ = "ops_device_readings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("ops_assets.id"), nullable=True)
    device_name = Column(String(100), nullable=False)
    metric_type = Column(String(50), nullable=False, comment="temperature/power/online_status/tpm/clean_days")
    value_float = Column(Float, nullable=True)
    value_bool = Column(Boolean, nullable=True)
    unit = Column(String(20), nullable=True)
    is_alert = Column(Boolean, nullable=False, default=False)
    alert_message = Column(Text, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_odr_store_time", "store_id", "recorded_at"),
        Index("ix_odr_metric", "metric_type"),
    )


class OpsNetworkHealth(Base):
    """网络探针结果（ICMP/HTTP/DNS/带宽/WiFi/VPN）"""

    __tablename__ = "ops_network_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    probe_type = Column(String(30), nullable=False, comment="icmp/http/dns/bandwidth/wifi/vpn")
    target = Column(String(200), nullable=False)
    vlan = Column(String(20), nullable=True, comment="vlan10/vlan20/vlan30/vlan40/vlan50/wan")
    latency_ms = Column(Float, nullable=True)
    packet_loss_pct = Column(Float, nullable=True)
    bandwidth_mbps = Column(Float, nullable=True)
    is_available = Column(Boolean, nullable=False, default=True)
    status_code = Column(Integer, nullable=True)
    is_alert = Column(Boolean, nullable=False, default=False)
    alert_message = Column(Text, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_onh_store_time", "store_id", "recorded_at"),
        Index("ix_onh_probe_type", "probe_type"),
    )


class OpsSysHealthCheck(Base):
    """业务系统心跳记录（23套系统健康状态）"""

    __tablename__ = "ops_sys_health_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    system_name = Column(String(100), nullable=False)
    priority = Column(String(5), nullable=False, default="P2", comment="P0/P1/P2/P3")
    check_method = Column(String(30), nullable=False, comment="api_heartbeat/db_probe/port_check/process_check")
    is_available = Column(Boolean, nullable=False, default=True)
    response_ms = Column(Float, nullable=True)
    http_status = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    is_alert = Column(Boolean, nullable=False, default=False)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_oshc_store_time", "store_id", "recorded_at"),
        Index("ix_oshc_system", "system_name"),
        Index("ix_oshc_priority", "priority"),
    )


class OpsFoodSafetyRecord(Base):
    """食安合规记录（冷链/油质/清洁/安全设备）"""

    __tablename__ = "ops_food_safety_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    record_type = Column(
        String(30), nullable=False, comment="cold_chain/fridge_power/ice_machine_clean/oil_quality/safety_device"
    )
    device_name = Column(String(100), nullable=True)
    is_compliant = Column(Boolean, nullable=False, default=True)
    value_float = Column(Float, nullable=True)
    threshold_min = Column(Float, nullable=True)
    threshold_max = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    requires_action = Column(Boolean, nullable=False, default=False)
    action_taken = Column(Text, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_ofsr_store_time", "store_id", "recorded_at"),
        Index("ix_ofsr_type", "record_type"),
    )
