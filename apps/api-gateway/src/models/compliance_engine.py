"""
合规引擎模型 — ComplianceScore + ComplianceAlert
统一合规评分系统，连接健康证、食品安全检查、证照管理。
"""

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class ComplianceScore(Base, TimestampMixin):
    """
    门店合规评分快照。
    每日计算一次，记录各维度得分和综合评级。
    """

    __tablename__ = "compliance_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # 评分日期（每日快照）
    score_date = Column(Date, nullable=False, index=True)

    # 四维评分（0-100）
    health_cert_score = Column(Integer, nullable=False, default=0, comment="健康证合规：有效证件占比")
    food_safety_score = Column(Integer, nullable=False, default=0, comment="食品安全：检查通过率+溯源覆盖率")
    license_score = Column(Integer, nullable=False, default=0, comment="证照合规：必要证照有效率")
    hygiene_score = Column(Integer, nullable=False, default=0, comment="卫生检查：日检/周检得分")

    # 综合评分与评级
    overall_score = Column(Integer, nullable=False, default=0, comment="加权综合分")
    grade = Column(String(5), nullable=False, default="F", comment="评级：A+/A/B/C/D/F")

    # 风险项 [{type, description, severity, deadline}]
    risk_items = Column(JSON, nullable=False, default=list)

    # 自动执行的操作记录 [{action, timestamp, result}]
    auto_actions_taken = Column(JSON, nullable=True)


class ComplianceAlert(Base, TimestampMixin):
    """
    合规告警记录。
    由合规引擎自动生成，支持自动执行和人工处置。
    """

    __tablename__ = "compliance_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # 告警类型
    alert_type = Column(
        String(30),
        nullable=False,
        index=True,
        comment="cert_expired/cert_expiring/inspection_failed/license_expiring/trace_gap/score_drop",
    )

    # 严重程度
    severity = Column(
        String(10),
        nullable=False,
        index=True,
        comment="critical/high/medium/low",
    )

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # 关联实体（健康证/检查/证照 ID）
    related_entity_id = Column(String(100), nullable=True)

    # 处置状态
    is_resolved = Column(Boolean, nullable=False, default=False, index=True)
    resolved_by = Column(String(50), nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # 自动操作类型
    auto_action = Column(
        String(50),
        nullable=True,
        comment="block_scheduling/notify_manager/flag_inspection",
    )
