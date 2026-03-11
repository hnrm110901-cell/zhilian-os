"""
供应商管理 Agent — 数据模型
Phase 11（Supplier Intelligence System）

5层架构：
  L1 主数据层：SupplierProfile, MaterialCatalog
  L2 交易层：  SupplierQuote, SupplierContract, SupplierDelivery
  L3 分析层：  PriceComparison, SupplierEvaluation, SourcingRecommendation
  L4 预警层：  ContractAlert, SupplyRiskEvent
  L5 事件层：  SupplierAgentLog
"""
import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, Date, DateTime,
    ForeignKey, Enum as SAEnum, JSON, Index, Numeric,
)
from sqlalchemy.orm import relationship

from src.core.database import Base
from src.models.mixins import TimestampMixin


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class SupplierTierEnum(str, enum.Enum):
    STRATEGIC  = "strategic"   # 战略供应商（核心食材，深度合作）
    PREFERRED  = "preferred"   # 优选供应商（稳定合作）
    APPROVED   = "approved"    # 合格供应商（备用）
    PROBATION  = "probation"   # 试用期供应商
    SUSPENDED  = "suspended"   # 暂停合作


class QuoteStatusEnum(str, enum.Enum):
    DRAFT     = "draft"     # 草稿
    SUBMITTED = "submitted" # 已提交
    ACCEPTED  = "accepted"  # 已接受
    REJECTED  = "rejected"  # 已拒绝
    EXPIRED   = "expired"   # 已过期


class ContractStatusEnum(str, enum.Enum):
    DRAFT     = "draft"
    ACTIVE    = "active"
    EXPIRING  = "expiring"   # 30天内到期
    EXPIRED   = "expired"
    TERMINATED = "terminated"


class DeliveryStatusEnum(str, enum.Enum):
    PENDING   = "pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    REJECTED  = "rejected"   # 拒收（质量问题）
    PARTIAL   = "partial"    # 部分收货


class RiskLevelEnum(str, enum.Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class AlertTypeEnum(str, enum.Enum):
    CONTRACT_EXPIRING  = "contract_expiring"   # 合同即将到期
    PRICE_SPIKE        = "price_spike"         # 价格异常上涨
    DELIVERY_DELAY     = "delivery_delay"      # 交期延误
    QUALITY_ISSUE      = "quality_issue"       # 质量问题
    SUPPLY_SHORTAGE    = "supply_shortage"     # 供应紧张
    SINGLE_SOURCE_RISK = "single_source_risk"  # 单一来源风险


class SupplierAgentTypeEnum(str, enum.Enum):
    PRICE_COMPARISON   = "price_comparison"    # 比价分析
    SUPPLIER_RATING    = "supplier_rating"     # 供应商评级
    AUTO_SOURCING      = "auto_sourcing"       # 自动寻源
    CONTRACT_RISK      = "contract_risk"       # 合同风险
    SUPPLY_CHAIN_RISK  = "supply_chain_risk"   # 供应链风险


# ─────────────────────────────────────────────
# L1 主数据层
# ─────────────────────────────────────────────

class SupplierProfile(Base, TimestampMixin):
    """供应商档案（L1）— 在基础 Supplier 基础上扩展智能分析字段"""

    __tablename__ = "supplier_profiles"

    id              = Column(String(36), primary_key=True)
    supplier_id     = Column(String(36), nullable=False, unique=True, index=True)  # FK→suppliers.id
    brand_id        = Column(String(36), nullable=False, index=True)

    # 分级与认证
    tier            = Column(SAEnum(SupplierTierEnum), nullable=False, default=SupplierTierEnum.APPROVED)
    certified       = Column(Boolean, default=False)             # 是否通过资质审核
    cert_expiry     = Column(Date)                               # 资质到期日

    # 能力标签
    category_tags   = Column(JSON, default=list)    # ["蔬菜","肉类","干货"]
    region_coverage = Column(JSON, default=list)    # ["华中","华南"]
    min_order_yuan  = Column(Numeric(10, 2), default=0)  # 最低起订金额¥

    # 综合评分（由 SupplierRatingAgent 计算）
    composite_score = Column(Float, default=0.0)   # 0-100，综合得分
    price_score     = Column(Float, default=0.0)   # 价格竞争力
    quality_score   = Column(Float, default=0.0)   # 质量稳定性
    delivery_score  = Column(Float, default=0.0)   # 交期准时率
    service_score   = Column(Float, default=0.0)   # 服务响应度
    last_rated_at   = Column(DateTime)

    # 备注与风险标记
    risk_flags      = Column(JSON, default=list)   # ["单一来源","价格波动大"]
    internal_notes  = Column(Text)

    __table_args__ = (
        Index("ix_supplier_profiles_brand_tier", "brand_id", "tier"),
    )


class MaterialCatalog(Base, TimestampMixin):
    """物料目录（L1）— 标准化物料与多供应商价格汇总"""

    __tablename__ = "material_catalogs"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    material_code   = Column(String(50), nullable=False)
    material_name   = Column(String(200), nullable=False)
    spec            = Column(String(100))               # 规格，如"500g/袋"
    base_unit       = Column(String(20), default="kg")  # 基本单位
    category        = Column(String(50))                # 蔬菜/肉类/干货等

    # 价格参考
    benchmark_price_yuan  = Column(Numeric(10, 4), default=0)  # 基准单价¥
    latest_price_yuan     = Column(Numeric(10, 4), default=0)  # 最新市场均价¥
    price_updated_at      = Column(DateTime)

    # 采购策略
    preferred_supplier_id = Column(String(36), index=True)   # FK→supplier_profiles.id
    backup_supplier_ids   = Column(JSON, default=list)
    safety_stock_days     = Column(Integer, default=3)        # 安全库存天数
    reorder_point_kg      = Column(Float, default=0)          # 再订货点（kg）

    is_active       = Column(Boolean, default=True)

    __table_args__ = (
        Index("ix_material_catalogs_brand_code", "brand_id", "material_code"),
    )


# ─────────────────────────────────────────────
# L2 交易层
# ─────────────────────────────────────────────

class SupplierQuote(Base, TimestampMixin):
    """供应商报价单（L2）— 记录每次询价/报价结果"""

    __tablename__ = "supplier_quotes"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    store_id        = Column(String(36), index=True)        # 门店级采购可为空
    supplier_id     = Column(String(36), nullable=False, index=True)
    material_id     = Column(String(36), index=True)        # FK→material_catalogs.id

    material_name   = Column(String(200), nullable=False)
    spec            = Column(String(100))
    unit            = Column(String(20), default="kg")
    quantity        = Column(Float, nullable=False)         # 询价数量
    unit_price_yuan = Column(Numeric(10, 4), nullable=False) # 报价单价¥
    total_yuan      = Column(Numeric(10, 2))                 # 总价¥
    valid_until     = Column(Date)                           # 报价有效期

    status          = Column(SAEnum(QuoteStatusEnum), default=QuoteStatusEnum.SUBMITTED)
    delivery_days   = Column(Integer, default=3)             # 承诺交期（天）
    min_order_qty   = Column(Float, default=0)               # 最低起订量
    notes           = Column(Text)

    # 比价时自动填入
    rank_in_comparison = Column(Integer)    # 在本次比价中的排名（1=最优）
    price_delta_pct    = Column(Float)      # 与基准价偏差%（正=贵，负=便宜）

    __table_args__ = (
        Index("ix_supplier_quotes_brand_supplier", "brand_id", "supplier_id"),
        Index("ix_supplier_quotes_material", "material_id"),
    )


class SupplierContract(Base, TimestampMixin):
    """供应商合同（L2）"""

    __tablename__ = "supplier_contracts"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    supplier_id     = Column(String(36), nullable=False, index=True)
    contract_no     = Column(String(100), unique=True, nullable=False)
    contract_name   = Column(String(200))

    start_date      = Column(Date, nullable=False)
    end_date        = Column(Date, nullable=False)
    auto_renew      = Column(Boolean, default=False)
    renewal_notice_days = Column(Integer, default=30)  # 提前N天预警

    status          = Column(SAEnum(ContractStatusEnum), default=ContractStatusEnum.DRAFT)

    # 合同条款关键字段
    annual_value_yuan    = Column(Numeric(12, 2), default=0)   # 年度合同金额¥
    payment_terms        = Column(String(50), default="net30") # 账期
    delivery_guarantee   = Column(Boolean, default=False)       # 是否有货源保障条款
    price_lock_months    = Column(Integer, default=0)           # 锁价月数（0=不锁价）
    penalty_clause       = Column(Boolean, default=False)       # 是否有违约金条款
    exclusive_clause     = Column(Boolean, default=False)       # 是否有排他条款

    # 覆盖品类
    covered_categories   = Column(JSON, default=list)   # ["蔬菜","肉类"]
    covered_material_ids = Column(JSON, default=list)

    file_url        = Column(String(500))  # 合同文件URL
    signed_by       = Column(String(100))
    signed_at       = Column(DateTime)
    notes           = Column(Text)

    __table_args__ = (
        Index("ix_supplier_contracts_brand_status", "brand_id", "status"),
        Index("ix_supplier_contracts_end_date", "end_date"),
    )


class SupplierDelivery(Base, TimestampMixin):
    """收货记录（L2）— 每次到货质量与准时率评估"""

    __tablename__ = "supplier_deliveries"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    store_id        = Column(String(36), nullable=False, index=True)
    supplier_id     = Column(String(36), nullable=False, index=True)
    purchase_order_id = Column(String(36), index=True)  # FK→purchase_orders.id

    promised_date   = Column(Date, nullable=False)     # 承诺到货日
    actual_date     = Column(Date)                     # 实际到货日
    delay_days      = Column(Integer, default=0)       # 延误天数（负=提前）

    status          = Column(SAEnum(DeliveryStatusEnum), default=DeliveryStatusEnum.PENDING)

    # 收货评估
    ordered_qty     = Column(Float, nullable=False)
    received_qty    = Column(Float, default=0)
    rejected_qty    = Column(Float, default=0)         # 拒收数量
    reject_reason   = Column(String(200))              # 拒收原因

    # 质量评分（1-5）
    quality_score   = Column(Float)
    freshness_ok    = Column(Boolean)                  # 新鲜度是否达标
    packaging_ok    = Column(Boolean)                  # 包装是否完好
    temp_ok         = Column(Boolean)                  # 温控是否达标（冷链）

    inspector_id    = Column(String(36))               # 验收人ID
    notes           = Column(Text)

    __table_args__ = (
        Index("ix_supplier_deliveries_supplier_date", "supplier_id", "promised_date"),
    )


# ─────────────────────────────────────────────
# L3 分析层
# ─────────────────────────────────────────────

class PriceComparison(Base, TimestampMixin):
    """比价记录（L3）— PriceComparisonAgent 输出"""

    __tablename__ = "price_comparisons"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    store_id        = Column(String(36), index=True)
    material_id     = Column(String(36), index=True)
    material_name   = Column(String(200), nullable=False)

    # 本次比价汇总
    comparison_date = Column(Date, nullable=False)
    quote_count     = Column(Integer, default=0)        # 参与比价的供应商数
    best_price_yuan = Column(Numeric(10, 4))            # 最优报价单价¥
    best_supplier_id = Column(String(36))               # 最优供应商ID
    avg_price_yuan  = Column(Numeric(10, 4))            # 均价¥
    price_spread_pct = Column(Float)                    # 最高/最低价差比%

    # AI 推荐
    recommended_supplier_id = Column(String(36))        # 综合推荐（不一定是最低价）
    recommendation_reason   = Column(Text)              # 推荐理由（含¥节省估算）
    estimated_saving_yuan   = Column(Numeric(10, 2))    # 与当前采购商相比¥节省
    confidence              = Column(Float, default=0.8) # 推荐置信度

    # 原始报价快照
    quote_snapshot  = Column(JSON, default=list)        # [{supplier_id, price, rank, ...}]

    __table_args__ = (
        Index("ix_price_comparisons_brand_material", "brand_id", "material_id"),
    )


class SupplierEvaluation(Base, TimestampMixin):
    """供应商评估记录（L3）— SupplierRatingAgent 输出，每月或按需生成"""

    __tablename__ = "supplier_evaluations"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    supplier_id     = Column(String(36), nullable=False, index=True)
    eval_period     = Column(String(10), nullable=False)  # "2026-03"（月度）

    # 四维度得分（0-100）
    price_score     = Column(Float, default=0.0)   # 价格竞争力：基准价偏差
    quality_score   = Column(Float, default=0.0)   # 质量：拒收率、新鲜度
    delivery_score  = Column(Float, default=0.0)   # 交期：准时率
    service_score   = Column(Float, default=0.0)   # 服务：响应速度、投诉处理

    composite_score = Column(Float, default=0.0)   # 综合得分（加权）
    tier_suggestion = Column(SAEnum(SupplierTierEnum))  # AI建议调整到的级别

    # 原始数据摘要
    delivery_count  = Column(Integer, default=0)   # 本期收货次数
    on_time_count   = Column(Integer, default=0)   # 准时次数
    reject_rate     = Column(Float, default=0.0)   # 拒收率%
    avg_price_delta_pct = Column(Float, default=0.0)  # 价格偏差%

    # AI 建议动作
    action_required = Column(Boolean, default=False)  # 是否需要采取行动
    action_text     = Column(Text)                    # 具体建议

    __table_args__ = (
        Index("ix_supplier_evaluations_supplier_period", "supplier_id", "eval_period"),
    )


class SourcingRecommendation(Base, TimestampMixin):
    """自动寻源推荐（L3）— AutoSourcingAgent 输出"""

    __tablename__ = "sourcing_recommendations"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    store_id        = Column(String(36), index=True)
    trigger         = Column(String(50), default="bom_gap")  # bom_gap/manual/scheduled

    # 需求描述
    material_id     = Column(String(36), index=True)
    material_name   = Column(String(200))
    required_qty    = Column(Float, default=0)
    required_unit   = Column(String(20), default="kg")
    needed_by_date  = Column(Date)

    # 推荐结果
    recommended_supplier_id = Column(String(36))
    recommended_price_yuan  = Column(Numeric(10, 4))
    alternative_supplier_ids = Column(JSON, default=list)  # 备选供应商
    sourcing_strategy        = Column(String(50))    # single/split/spot
    split_plan               = Column(JSON)          # 分拆采购方案
    estimated_total_yuan     = Column(Numeric(10, 2))
    estimated_saving_yuan    = Column(Numeric(10, 2))  # vs历史采购价节省¥

    reasoning       = Column(Text)        # AI 推理链
    confidence      = Column(Float, default=0.8)
    status          = Column(String(20), default="pending")  # pending/accepted/rejected
    accepted_by     = Column(String(36))
    accepted_at     = Column(DateTime)

    __table_args__ = (
        Index("ix_sourcing_recommendations_brand", "brand_id", "trigger"),
    )


# ─────────────────────────────────────────────
# L4 预警层
# ─────────────────────────────────────────────

class ContractAlert(Base, TimestampMixin):
    """合同预警（L4）— ContractRiskAgent 生成"""

    __tablename__ = "contract_alerts"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    contract_id     = Column(String(36), nullable=False, index=True)
    supplier_id     = Column(String(36), nullable=False, index=True)

    alert_type      = Column(SAEnum(AlertTypeEnum), nullable=False)
    risk_level      = Column(SAEnum(RiskLevelEnum), nullable=False, default=RiskLevelEnum.MEDIUM)

    title           = Column(String(200), nullable=False)
    description     = Column(Text)
    recommended_action = Column(Text)                 # 建议行动（含¥影响）
    financial_impact_yuan = Column(Numeric(10, 2))    # 若不处理的潜在¥损失

    days_to_expiry  = Column(Integer)                 # 距到期天数（合同到期类）
    is_resolved     = Column(Boolean, default=False)
    resolved_at     = Column(DateTime)
    resolved_by     = Column(String(36))

    # 企微推送状态
    wechat_sent     = Column(Boolean, default=False)
    wechat_sent_at  = Column(DateTime)

    __table_args__ = (
        Index("ix_contract_alerts_brand_resolved", "brand_id", "is_resolved"),
    )


class SupplyRiskEvent(Base, TimestampMixin):
    """供应链风险事件（L4）— SupplyChainRiskAgent 生成"""

    __tablename__ = "supply_risk_events"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    store_id        = Column(String(36), index=True)
    supplier_id     = Column(String(36), index=True)
    material_id     = Column(String(36), index=True)

    alert_type      = Column(SAEnum(AlertTypeEnum), nullable=False)
    risk_level      = Column(SAEnum(RiskLevelEnum), nullable=False)

    title           = Column(String(200), nullable=False)
    description     = Column(Text)
    probability     = Column(Float, default=0.5)    # 风险发生概率（0-1）
    impact_days     = Column(Integer, default=0)    # 预计影响天数
    financial_impact_yuan = Column(Numeric(10, 2))  # 潜在¥损失

    # 缓解方案
    mitigation_plan  = Column(Text)
    backup_supplier_ids = Column(JSON, default=list)  # 可替代供应商

    is_resolved     = Column(Boolean, default=False)
    resolved_at     = Column(DateTime)
    wechat_sent     = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_supply_risk_events_brand_level", "brand_id", "risk_level"),
    )


# ─────────────────────────────────────────────
# L5 事件层
# ─────────────────────────────────────────────

class SupplierAgentLog(Base, TimestampMixin):
    """Supplier Agent 执行日志（L5）"""

    __tablename__ = "supplier_agent_logs"

    id              = Column(String(36), primary_key=True)
    brand_id        = Column(String(36), nullable=False, index=True)
    agent_type      = Column(SAEnum(SupplierAgentTypeEnum), nullable=False)
    triggered_by    = Column(String(50), default="scheduled")  # scheduled/manual/webhook

    input_params    = Column(JSON, default=dict)
    output_summary  = Column(JSON, default=dict)
    recommendation_count = Column(Integer, default=0)
    alert_count     = Column(Integer, default=0)
    saving_yuan     = Column(Numeric(10, 2), default=0)   # 本次运行估算¥节省

    duration_ms     = Column(Integer, default=0)
    success         = Column(Boolean, default=True)
    error_message   = Column(Text)

    __table_args__ = (
        Index("ix_supplier_agent_logs_brand_type", "brand_id", "agent_type"),
    )
