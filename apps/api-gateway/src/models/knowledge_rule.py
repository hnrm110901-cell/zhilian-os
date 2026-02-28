"""
推理规则库模型（知识资产护城河核心）

设计：
  - KnowledgeRule：单条推理规则（条件 + 结论 + 置信度权重）
  - RuleCategory：规则分类（损耗 / 效率 / 质量 / 成本 / 客流）
  - RuleExecution：规则执行日志（可追溯）

规则来源：
  1. 专家预置（seed_rules.py）— 餐饮行业通用规则
  2. 推理引擎归纳（Phase 2 WasteReasoningEngine 输出）
  3. 人工审核后入库

目标：500+ 条规则（Phase 3 验收标准）
"""

import uuid
import enum
from sqlalchemy import (
    Column, String, Text, Float, Boolean, Integer,
    DateTime, Enum, JSON, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

from src.models.base import Base, TimestampMixin


class RuleCategory(str, enum.Enum):
    WASTE       = "waste"        # 损耗规则
    EFFICIENCY  = "efficiency"   # 人效规则
    QUALITY     = "quality"      # 品质规则
    COST        = "cost"         # 成本规则
    TRAFFIC     = "traffic"      # 客流规则
    INVENTORY   = "inventory"    # 库存规则
    COMPLIANCE  = "compliance"   # 合规规则
    BENCHMARK   = "benchmark"    # 行业基准
    CROSS_STORE = "cross_store"  # 跨店知识聚合规则（L3）


class RuleType(str, enum.Enum):
    THRESHOLD   = "threshold"    # 阈值规则（if metric > X then alert）
    PATTERN     = "pattern"      # 模式规则（if A and B and C then D）
    ANOMALY     = "anomaly"      # 异常规则（标准差 / 趋势偏离）
    CAUSAL      = "causal"       # 因果规则（root cause 映射）
    BENCHMARK   = "benchmark"    # 基准对比规则


class RuleStatus(str, enum.Enum):
    DRAFT     = "draft"       # 草稿（未生效）
    ACTIVE    = "active"      # 生效中
    INACTIVE  = "inactive"    # 暂停
    ARCHIVED  = "archived"    # 已归档（替代版本已上线）


class KnowledgeRule(Base, TimestampMixin):
    """
    推理规则

    每条规则描述一个可量化的业务逻辑：
      "当菜品损耗率连续3天超过基准值15%时，根因为人员操作失误的概率为72%"
    """
    __tablename__ = "knowledge_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 规则标识
    rule_code = Column(String(50), unique=True, nullable=False)  # WASTE-001
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # 分类
    category = Column(Enum(RuleCategory), nullable=False, index=True)
    rule_type = Column(Enum(RuleType), nullable=False, default=RuleType.THRESHOLD)

    # 规则体（结构化条件-结论对）
    condition = Column(JSON, nullable=False)
    # 格式示例：
    # {"metric": "waste_rate", "operator": ">", "threshold": 0.15,
    #  "window_days": 3, "consecutive": True}
    conclusion = Column(JSON, nullable=False)
    # 格式示例：
    # {"root_cause": "staff_error", "confidence": 0.72,
    #  "recommended_action": "联系门店长复核操作流程"}

    # 置信度和权重
    base_confidence = Column(Float, nullable=False, default=0.7)
    weight = Column(Float, nullable=False, default=1.0)

    # 适用范围
    applicable_store_ids = Column(JSON)  # null 表示全平台适用
    applicable_dish_categories = Column(JSON)  # null 表示所有菜品类别
    industry_type = Column(String(50))  # seafood / hotpot / fastfood / general

    # 状态
    status = Column(Enum(RuleStatus), nullable=False, default=RuleStatus.DRAFT, index=True)

    # 质量指标（持续更新）
    hit_count = Column(Integer, default=0)          # 命中次数
    correct_count = Column(Integer, default=0)       # 正确命中次数（人工验证）
    accuracy_rate = Column(Float)                    # 准确率
    last_hit_at = Column(DateTime)

    # 版本管理
    version = Column(Integer, nullable=False, default=1)
    superseded_by = Column(UUID(as_uuid=True))  # 被哪条规则替代

    # 来源
    source = Column(String(50), default="expert")  # expert / inference_engine / crowdsource
    contributed_by = Column(String(100))  # 贡献者（门店ID或专家ID）
    is_public = Column(Boolean, default=False)  # 是否可对外共享（模型市场）

    # 关联
    tags = Column(JSON)  # ["海鲜", "损耗", "人员操作"]

    __table_args__ = (
        Index("idx_rule_category_status", "category", "status"),
        Index("idx_rule_industry_type", "industry_type"),
        Index("idx_rule_source", "source"),
    )

    def __repr__(self):
        return f"<KnowledgeRule({self.rule_code}: {self.name[:30]})>"


class RuleExecution(Base, TimestampMixin):
    """
    规则执行日志（可追溯性）

    每次推理引擎匹配到规则并输出结论时记录。
    """
    __tablename__ = "rule_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    rule_code = Column(String(50), nullable=False)

    # 触发上下文
    store_id = Column(String(50), nullable=False, index=True)
    event_id = Column(String(100))  # 关联的损耗/库存事件 ID
    dish_id = Column(String(100))

    # 匹配结果
    condition_values = Column(JSON)  # 触发时的实际度量值
    conclusion_output = Column(JSON)  # 实际输出结论
    confidence_score = Column(Float)

    # 人工验证
    is_verified = Column(Boolean)
    verified_by = Column(String(100))
    verified_at = Column(DateTime)
    verification_notes = Column(Text)

    executed_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_rule_exec_store_date", "store_id", "executed_at"),
        Index("idx_rule_exec_rule_id", "rule_id"),
    )


class IndustryBenchmark(Base, TimestampMixin):
    """
    行业基准数据库

    存储餐饮行业各品类的标准指标基准值（来自头部门店数据归纳 + 行业报告）。
    """
    __tablename__ = "industry_benchmarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 维度
    industry_type = Column(String(50), nullable=False, index=True)  # seafood/hotpot/fastfood
    metric_name = Column(String(100), nullable=False)  # waste_rate / labor_cost_ratio / etc.
    metric_category = Column(Enum(RuleCategory), nullable=False)

    # 基准值
    p25_value = Column(Float)   # 行业 25 分位（落后）
    p50_value = Column(Float)   # 行业中位数
    p75_value = Column(Float)   # 行业 75 分位（优秀）
    p90_value = Column(Float)   # 行业 90 分位（标杆）

    unit = Column(String(20))          # %、元/人天、件/天
    direction = Column(String(10))     # lower_better / higher_better

    # 元数据
    data_source = Column(String(200))  # 来源描述（如 "2025中国餐饮白皮书"）
    sample_size = Column(Integer)      # 样本量
    valid_until = Column(DateTime)     # 有效期

    description = Column(Text)

    __table_args__ = (
        UniqueConstraint("industry_type", "metric_name", name="uq_benchmark_type_metric"),
        Index("idx_benchmark_type", "industry_type"),
    )

    def __repr__(self):
        return f"<IndustryBenchmark({self.industry_type}/{self.metric_name}: p50={self.p50_value})>"
