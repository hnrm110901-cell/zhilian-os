"""
数据融合引擎模型 — Phase P1
面向品质中大型餐饮集团的历史数据智能融合 + SaaS渐进替换

核心表：
  FusionProject    — 融合项目（一个客户一个项目，跨品牌）
  FusionTask       — 融合任务（一个系统一个任务，可断点续传）
  FusionEntityMap  — 实体映射（跨系统同一实体的 canonical_id 关联）
  FusionProvenance — 数据血缘（每条融合数据的来源追踪）
  FusionConflict   — 冲突记录（多源数据不一致时的仲裁日志）

设计原则：
  - 多租户隔离：brand_id + store_id
  - 金额单位：fen（分），展示时 /100 转元
  - 主键：String(36) UUID
  - 断点续传：FusionTask 记录 last_cursor + processed_count
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

FusionProjectStatusEnum = ENUM(
    "created",        # 项目创建，尚未启动
    "scanning",       # 扫描外部系统，评估数据量
    "importing",      # 正在导入历史数据
    "resolving",      # 实体解析与去重合并
    "generating",     # 知识库生成中
    "completed",      # 全部完成
    "failed",         # 失败（可重试）
    "paused",         # 手动暂停
    name="fusion_project_status_enum",
    create_type=True,
)

FusionTaskStatusEnum = ENUM(
    "pending",        # 等待执行
    "running",        # 正在执行
    "completed",      # 完成
    "failed",         # 失败
    "paused",         # 暂停（可续传）
    "cancelled",      # 已取消
    name="fusion_task_status_enum",
    create_type=True,
)

FusionTaskChannelEnum = ENUM(
    "api",            # 通过POS/SaaS API拉取
    "file",           # CSV/Excel文件导入
    "db_mirror",      # 数据库只读镜像
    "webhook",        # Webhook实时推送
    name="fusion_task_channel_enum",
    create_type=True,
)

FusionEntityTypeEnum = ENUM(
    "dish",           # 菜品
    "ingredient",     # 食材
    "customer",       # 客户/会员
    "supplier",       # 供应商
    "employee",       # 员工
    "order",          # 订单
    "store",          # 门店
    name="fusion_entity_type_enum",
    create_type=True,
)

FusionConflictResolutionEnum = ENUM(
    "auto_latest",    # 自动采用最新数据
    "auto_primary",   # 自动采用主源系统
    "auto_highest",   # 自动采用最高置信度
    "manual",         # 人工仲裁
    "pending",        # 待处理
    name="fusion_conflict_resolution_enum",
    create_type=True,
)


# ── 融合项目 ──────────────────────────────────────────────────────────────────

class FusionProject(Base):
    """
    融合项目：一个客户的完整数据融合过程
    一个集团可能有多个品牌，每个品牌可以独立或合并融合
    """

    __tablename__ = "fusion_projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False, comment="品牌ID（集团级可为集团ID）")
    store_id = Column(String(36), nullable=True, comment="门店ID（null表示集团级项目）")

    # 基本信息
    name = Column(String(200), nullable=False, comment="项目名称，如：尝在一起-历史数据融合")
    description = Column(Text, nullable=True, comment="项目描述")
    status = Column(FusionProjectStatusEnum, nullable=False, server_default="created")

    # 来源系统配置（JSON数组，记录要融合的所有外部系统）
    # 格式: [{"system_type": "pinzhi", "category": "pos", "config": {...}}, ...]
    source_systems = Column(JSON, nullable=False, server_default="[]",
                            comment="来源系统列表")

    # 融合范围
    data_start_date = Column(DateTime, nullable=True, comment="历史数据回溯起点")
    data_end_date = Column(DateTime, nullable=True, comment="历史数据截止日期")
    entity_types = Column(JSON, nullable=False, server_default='["order","dish","customer","ingredient"]',
                          comment="要融合的实体类型")

    # 进度统计
    total_tasks = Column(Integer, nullable=False, server_default="0")
    completed_tasks = Column(Integer, nullable=False, server_default="0")
    total_records_imported = Column(Integer, nullable=False, server_default="0")
    total_entities_resolved = Column(Integer, nullable=False, server_default="0")
    total_conflicts = Column(Integer, nullable=False, server_default="0")

    # 知识库生成状态
    knowledge_generated = Column(Boolean, nullable=False, server_default="false",
                                 comment="知识库是否已生成")
    health_report_generated = Column(Boolean, nullable=False, server_default="false",
                                     comment="经营体检报告是否已生成")

    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_fusion_project_brand", "brand_id"),
        Index("idx_fusion_project_status", "status"),
    )


# ── 融合任务 ──────────────────────────────────────────────────────────────────

class FusionTask(Base):
    """
    融合任务：一个来源系统 + 一个数据类型 = 一个任务
    支持断点续传：记录 last_cursor 和 processed_count
    """

    __tablename__ = "fusion_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), nullable=False, comment="所属融合项目ID")
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=True)

    # 来源系统
    source_system = Column(String(50), nullable=False, comment="来源系统标识，如 pinzhi/tiancai")
    source_category = Column(String(50), nullable=False, comment="系统类别，如 pos/reservation/member")
    channel = Column(FusionTaskChannelEnum, nullable=False, server_default="api",
                     comment="数据采集通道")

    # 任务范围
    entity_type = Column(FusionEntityTypeEnum, nullable=False, comment="实体类型")
    status = Column(FusionTaskStatusEnum, nullable=False, server_default="pending")
    priority = Column(Integer, nullable=False, server_default="0", comment="优先级，0=普通，越大越高")

    # 时间范围
    date_range_start = Column(DateTime, nullable=True, comment="数据拉取起始日期")
    date_range_end = Column(DateTime, nullable=True, comment="数据拉取截止日期")

    # 断点续传
    last_cursor = Column(String(500), nullable=True, comment="上次处理到的位置标记（页码/offset/日期）")
    batch_size = Column(Integer, nullable=False, server_default="100")

    # 进度
    total_estimated = Column(Integer, nullable=True, comment="预估总记录数")
    processed_count = Column(Integer, nullable=False, server_default="0")
    success_count = Column(Integer, nullable=False, server_default="0")
    error_count = Column(Integer, nullable=False, server_default="0")
    duplicate_count = Column(Integer, nullable=False, server_default="0")

    # 错误信息
    last_error = Column(Text, nullable=True, comment="最近一次错误信息")
    error_details = Column(JSON, nullable=True, comment="错误明细列表")

    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_fusion_task_project", "project_id"),
        Index("idx_fusion_task_status", "status"),
        Index("idx_fusion_task_store_system", "store_id", "source_system"),
    )


# ── 实体映射 ──────────────────────────────────────────────────────────────────

class FusionEntityMap(Base):
    """
    实体映射：跨系统的同一实体关联
    例如：品智POS的"剁椒鱼头"和美团外卖的"招牌剁椒鱼头(大份)" → 同一个 canonical_id

    核心作用：
    - 建立跨系统实体的统一标识（canonical_id）
    - 记录每个外部系统中该实体的原始ID
    - 置信度评分支持自动/手动确认
    """

    __tablename__ = "fusion_entity_maps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=True)

    # 规范实体
    entity_type = Column(FusionEntityTypeEnum, nullable=False)
    canonical_id = Column(String(36), nullable=False, comment="屯象OS内部统一ID")
    canonical_name = Column(String(200), nullable=True, comment="规范名称")

    # 外部实体
    source_system = Column(String(50), nullable=False, comment="来源系统")
    external_id = Column(String(200), nullable=False, comment="外部系统中的原始ID")
    external_name = Column(String(200), nullable=True, comment="外部系统中的原始名称")

    # 匹配质量
    confidence = Column(Float, nullable=False, server_default="0.0",
                        comment="匹配置信度 0.0~1.0")
    match_method = Column(String(50), nullable=True,
                          comment="匹配方法: exact_id/exact_name/fuzzy_name/manual")
    is_confirmed = Column(Boolean, nullable=False, server_default="false",
                          comment="是否已人工确认")

    # 元数据（存储外部系统的额外属性，用于后续分析）
    external_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_fusion_entity_canonical", "entity_type", "canonical_id"),
        Index("idx_fusion_entity_external", "source_system", "external_id"),
        Index("idx_fusion_entity_brand_type", "brand_id", "entity_type"),
        Index("idx_fusion_entity_confidence", "confidence"),
    )


# ── 数据血缘 ──────────────────────────────────────────────────────────────────

class FusionProvenance(Base):
    """
    数据血缘追踪：每条融合进屯象OS的数据，可追溯到原SaaS的原始记录
    对标 Palantir Foundry 的 Data Lineage

    用途：
    - 审计合规：任何数据都能追溯到来源
    - 冲突仲裁：多源数据不一致时，看各自来源可信度
    - 数据质量：统计各来源系统的数据质量分布
    """

    __tablename__ = "fusion_provenances"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)

    # 屯象OS内部数据指向
    target_table = Column(String(100), nullable=False, comment="目标表名，如 orders/dishes")
    target_id = Column(String(36), nullable=False, comment="目标记录ID")
    target_field = Column(String(100), nullable=True, comment="目标字段名（null表示整条记录）")

    # 来源信息
    source_system = Column(String(50), nullable=False)
    source_table = Column(String(200), nullable=True, comment="来源系统中的表/接口名")
    source_id = Column(String(200), nullable=False, comment="来源系统中的原始ID")
    source_field = Column(String(100), nullable=True, comment="来源字段名")

    # 融合信息
    fusion_task_id = Column(String(36), nullable=True, comment="产生该记录的融合任务ID")
    imported_at = Column(DateTime, server_default=func.now(), comment="导入时间")

    # 数据快照（记录导入时的原始值，用于冲突仲裁和审计）
    original_value = Column(Text, nullable=True, comment="导入时的原始值（JSON序列化）")

    __table_args__ = (
        Index("idx_fusion_prov_target", "target_table", "target_id"),
        Index("idx_fusion_prov_source", "source_system", "source_id"),
        Index("idx_fusion_prov_task", "fusion_task_id"),
    )


# ── 冲突记录 ──────────────────────────────────────────────────────────────────

class FusionConflict(Base):
    """
    冲突记录：多源数据不一致时的仲裁日志
    例如：品智POS和美团的同一订单金额不一致

    仲裁策略：
    - auto_latest: 自动采用时间最新的数据
    - auto_primary: 自动采用主源系统（POS为主）
    - auto_highest: 自动采用置信度最高的来源
    - manual: 需要人工介入仲裁
    """

    __tablename__ = "fusion_conflicts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=True)

    # 冲突实体
    entity_type = Column(FusionEntityTypeEnum, nullable=False)
    canonical_id = Column(String(36), nullable=False, comment="冲突实体的规范ID")
    field_name = Column(String(100), nullable=False, comment="冲突字段名")

    # 冲突双方
    source_a_system = Column(String(50), nullable=False)
    source_a_value = Column(Text, nullable=True, comment="来源A的值（JSON序列化）")
    source_a_timestamp = Column(DateTime, nullable=True)

    source_b_system = Column(String(50), nullable=False)
    source_b_value = Column(Text, nullable=True, comment="来源B的值（JSON序列化）")
    source_b_timestamp = Column(DateTime, nullable=True)

    # 仲裁结果
    resolution = Column(FusionConflictResolutionEnum, nullable=False, server_default="pending")
    resolved_value = Column(Text, nullable=True, comment="最终采用的值")
    resolved_by = Column(String(100), nullable=True, comment="仲裁人（auto/user_id）")
    resolved_at = Column(DateTime, nullable=True)

    # 影响评估
    impact_amount_fen = Column(Integer, nullable=True,
                               comment="冲突影响金额（分），如订单金额差异")

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_fusion_conflict_entity", "entity_type", "canonical_id"),
        Index("idx_fusion_conflict_resolution", "resolution"),
        Index("idx_fusion_conflict_brand", "brand_id"),
    )
