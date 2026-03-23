"""
影子模式 + 灰度切换模型 — Phase P2.1
SaaS渐进替换的安全网：影子记账 → 一致性验证 → 灰度切换 → 一键回退

核心表：
  ShadowSession     — 影子运行会话（一个门店一个会话）
  ShadowRecord      — 影子记账记录（双写对比数据）
  ConsistencyReport — 一致性比对报告（每日/每周自动生成）
  CutoverState      — 灰度切换状态（按模块×门店控制）
  CutoverEvent      — 切换事件日志（审计追踪）

设计原则：
  - 状态机：shadow → canary → primary → sole
  - 任何阶段 < 30秒回退到上一状态
  - 金额单位：fen（分）
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Index, Integer,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSON

from .base import Base

# ── PG Enums ──────────────────────────────────────────────────────────────────

ShadowSessionStatusEnum = ENUM(
    "active",         # 影子运行中
    "paused",         # 暂停
    "validating",     # 一致性验证中
    "ready",          # 验证通过，可以切换
    "completed",      # 已完成切换
    "terminated",     # 终止（放弃切换）
    name="shadow_session_status_enum",
    create_type=True,
)

ShadowRecordTypeEnum = ENUM(
    "order",          # 订单
    "inventory",      # 库存变动
    "payment",        # 支付
    "member_points",  # 会员积分
    "schedule",       # 排班
    "purchase",       # 采购
    name="shadow_record_type_enum",
    create_type=True,
)

ConsistencyLevelEnum = ENUM(
    "perfect",        # 完全一致 (差异率 = 0%)
    "acceptable",     # 可接受 (差异率 < 0.1%)
    "warning",        # 预警 (差异率 0.1% ~ 1%)
    "critical",       # 严重 (差异率 > 1%)
    name="consistency_level_enum",
    create_type=True,
)

CutoverPhaseEnum = ENUM(
    "shadow",         # 影子模式：原SaaS为主，屯象OS影子记账
    "canary",         # 灰度模式：部分操作走屯象OS
    "primary",        # 主切模式：屯象OS为主，原SaaS为备
    "sole",           # 完全切换：原SaaS下线
    name="cutover_phase_enum",
    create_type=True,
)

CutoverModuleEnum = ENUM(
    "analytics",      # 分析决策类（报表/预警）
    "management",     # 后台管理类（排班/采购审批）
    "operations",     # 前台操作类（收银/点单）
    "finance",        # 财务对账类（日结/月结）
    name="cutover_module_enum",
    create_type=True,
)


# ── 影子会话 ──────────────────────────────────────────────────────────────────

class ShadowSession(Base):
    """
    影子运行会话：一个门店对一个SaaS的影子运行过程
    控制影子模式的生命周期
    """

    __tablename__ = "shadow_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)

    # 对标的原SaaS系统
    source_system = Column(String(50), nullable=False, comment="原SaaS系统标识")
    status = Column(ShadowSessionStatusEnum, nullable=False, server_default="active")

    # 配置
    modules = Column(JSON, nullable=False, server_default='["order","inventory"]',
                     comment="影子覆盖的模块列表")
    auto_validate = Column(Boolean, nullable=False, server_default="true",
                           comment="是否自动每日验证一致性")

    # 统计
    total_records = Column(Integer, nullable=False, server_default="0")
    consistent_records = Column(Integer, nullable=False, server_default="0")
    inconsistent_records = Column(Integer, nullable=False, server_default="0")
    consistency_rate = Column(Float, nullable=False, server_default="0.0",
                              comment="一致性比率 0.0~1.0")

    # 达标天数（连续30天差异率<0.1%即可切换）
    consecutive_pass_days = Column(Integer, nullable=False, server_default="0")
    target_pass_days = Column(Integer, nullable=False, server_default="30")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_shadow_session_store", "store_id", "source_system"),
        Index("idx_shadow_session_status", "status"),
    )


# ── 影子记录 ──────────────────────────────────────────────────────────────────

class ShadowRecord(Base):
    """
    影子记账记录：原SaaS产生的每条业务数据，在屯象OS中的影子副本
    用于双写对比
    """

    __tablename__ = "shadow_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)

    # 记录类型
    record_type = Column(ShadowRecordTypeEnum, nullable=False)

    # 原系统数据
    source_system = Column(String(50), nullable=False)
    source_id = Column(String(200), nullable=False, comment="原系统中的记录ID")
    source_data = Column(JSON, nullable=True, comment="原系统数据快照")
    source_amount_fen = Column(Integer, nullable=True, comment="原系统金额（分）")

    # 屯象OS影子数据
    shadow_data = Column(JSON, nullable=True, comment="屯象OS计算的影子数据")
    shadow_amount_fen = Column(Integer, nullable=True, comment="屯象OS计算的金额（分）")

    # 对比结果
    is_consistent = Column(Boolean, nullable=True, comment="是否一致（null=未对比）")
    diff_fields = Column(JSON, nullable=True, comment="不一致的字段列表")
    diff_amount_fen = Column(Integer, nullable=True, comment="金额差异（分）")

    created_at = Column(DateTime, server_default=func.now())
    compared_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_shadow_record_session", "session_id"),
        Index("idx_shadow_record_source", "source_system", "source_id"),
        Index("idx_shadow_record_consistent", "is_consistent"),
        Index("idx_shadow_record_created", "created_at"),
    )


# ── 一致性报告 ────────────────────────────────────────────────────────────────

class ConsistencyReport(Base):
    """
    一致性比对报告：每日/每周自动生成
    记录原SaaS与屯象OS之间的数据差异
    """

    __tablename__ = "consistency_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)

    # 报告周期
    report_date = Column(DateTime, nullable=False, comment="报告日期")
    period_type = Column(String(20), nullable=False, server_default="daily",
                         comment="daily / weekly / monthly")

    # 汇总指标
    level = Column(ConsistencyLevelEnum, nullable=False, server_default="warning")
    total_compared = Column(Integer, nullable=False, server_default="0")
    consistent_count = Column(Integer, nullable=False, server_default="0")
    inconsistent_count = Column(Integer, nullable=False, server_default="0")
    consistency_rate = Column(Float, nullable=False, server_default="0.0")

    # 分类统计
    order_consistency_rate = Column(Float, nullable=True)
    inventory_consistency_rate = Column(Float, nullable=True)
    payment_consistency_rate = Column(Float, nullable=True)

    # 金额差异汇总
    total_diff_amount_fen = Column(Integer, nullable=False, server_default="0",
                                   comment="总金额差异（绝对值，分）")

    # 详情
    top_diffs = Column(JSON, nullable=True, comment="TOP10差异记录")
    recommendations = Column(JSON, nullable=True, comment="修复建议")

    # 是否达标（差异率 < 0.1%）
    is_pass = Column(Boolean, nullable=False, server_default="false")

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_consistency_session_date", "session_id", "report_date"),
        Index("idx_consistency_level", "level"),
    )


# ── 灰度切换状态 ──────────────────────────────────────────────────────────────

class CutoverState(Base):
    """
    灰度切换状态：按模块×门店独立控制
    状态机：shadow → canary → primary → sole
    任何阶段都可以 rollback 到上一状态
    """

    __tablename__ = "cutover_states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)

    # 切换维度
    module = Column(CutoverModuleEnum, nullable=False, comment="功能模块")
    phase = Column(CutoverPhaseEnum, nullable=False, server_default="shadow")
    previous_phase = Column(CutoverPhaseEnum, nullable=True, comment="上一个阶段（用于回退）")

    # 切换条件
    shadow_pass_days = Column(Integer, nullable=False, server_default="0",
                              comment="影子模式达标天数")
    required_pass_days = Column(Integer, nullable=False, server_default="30")
    health_gate_passed = Column(Boolean, nullable=False, server_default="false",
                                comment="健康门禁是否通过")

    # 灰度比例（canary阶段使用）
    canary_percentage = Column(Integer, nullable=False, server_default="0",
                               comment="灰度流量比例 0~100")

    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_transition_at = Column(DateTime, nullable=True, comment="最后一次阶段切换时间")

    __table_args__ = (
        Index("idx_cutover_store_module", "store_id", "module", unique=True),
        Index("idx_cutover_phase", "phase"),
        Index("idx_cutover_brand", "brand_id"),
    )


# ── 切换事件日志 ──────────────────────────────────────────────────────────────

class CutoverEvent(Base):
    """
    切换事件日志：记录每一次阶段变更，用于审计
    """

    __tablename__ = "cutover_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cutover_state_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    module = Column(CutoverModuleEnum, nullable=False)

    # 变更信息
    from_phase = Column(CutoverPhaseEnum, nullable=False)
    to_phase = Column(CutoverPhaseEnum, nullable=False)
    trigger = Column(String(50), nullable=False, comment="触发方式: auto/manual/rollback")
    operator = Column(String(100), nullable=True, comment="操作人")
    reason = Column(Text, nullable=True, comment="变更原因")

    # 变更时的健康指标快照
    health_snapshot = Column(JSON, nullable=True, comment="切换时的健康指标")

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_cutover_event_state", "cutover_state_id"),
        Index("idx_cutover_event_store", "store_id"),
        Index("idx_cutover_event_created", "created_at"),
    )
