"""
活海鲜养殖管理模型（Aquarium / Live Seafood Management）

核心表：
- AquariumTank — 鱼缸/水族箱（ID/名称/容量/位置/品类/状态）
- AquariumWaterMetric — 水质指标记录（水温/pH/溶氧/盐度/氨氮/亚硝酸盐）
- LiveSeafoodBatch — 活海鲜批次（鱼缸ID/品种/入缸时间/数量/重量/供应商/成本）
- SeafoodMortalityLog — 死亡记录（批次ID/死亡数量/原因/处理方式/损耗金额）
- AquariumInspection — 每日巡检记录（巡检人/时间/鱼缸状态/异常描述/图片）

金额单位：分（fen），展示时 /100 转元
"""

import enum
import uuid

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


# ── 枚举 ──────────────────────────────────────────────────────────────────────


class TankStatus(str, enum.Enum):
    """鱼缸状态"""
    ACTIVE = "active"            # 正常使用
    MAINTENANCE = "maintenance"  # 维护/清洁中
    EMPTY = "empty"              # 空缸
    DECOMMISSIONED = "decommissioned"  # 已停用


class TankType(str, enum.Enum):
    """鱼缸类型"""
    SALTWATER = "saltwater"    # 海水缸
    FRESHWATER = "freshwater"  # 淡水缸
    MIXED = "mixed"            # 混合


class MetricSource(str, enum.Enum):
    """水质数据来源"""
    IOT = "iot"        # IoT 传感器自动采集
    MANUAL = "manual"  # 手动录入


class MortalityReason(str, enum.Enum):
    """死亡原因"""
    WATER_QUALITY = "water_quality"    # 水质问题
    DISEASE = "disease"                # 疾病
    OVERCROWDING = "overcrowding"      # 密度过高
    TEMPERATURE = "temperature"        # 温度异常
    TRANSPORT = "transport"            # 运输损耗
    NATURAL = "natural"                # 自然死亡
    UNKNOWN = "unknown"                # 原因不明


class MortalityDisposal(str, enum.Enum):
    """死亡处理方式"""
    DISCARD = "discard"      # 丢弃
    COOK_STAFF = "cook_staff"  # 员工餐消化
    RETURN = "return"        # 退回供应商
    INSURANCE = "insurance"  # 保险理赔


class InspectionResult(str, enum.Enum):
    """巡检结果"""
    NORMAL = "normal"      # 正常
    WARNING = "warning"    # 异常待处理
    CRITICAL = "critical"  # 严重异常


# ── 鱼缸/水族箱 ─────────────────────────────────────────────────────────────


class AquariumTank(Base, TimestampMixin):
    """鱼缸/水族箱主数据"""

    __tablename__ = "aquarium_tanks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 基本信息
    name = Column(String(100), nullable=False)            # 鱼缸名称，如"1号海水缸"
    tank_type = Column(String(20), default=TankType.SALTWATER.value, nullable=False)
    capacity_liters = Column(Float, nullable=False)       # 容量（升）
    location = Column(String(200))                        # 位置描述，如"大厅入口左侧"

    # 状态
    status = Column(String(20), default=TankStatus.ACTIVE.value, nullable=False, index=True)

    # 当前养殖品类（冗余字段，方便查询）
    current_species = Column(String(200))                 # 当前品种，逗号分隔

    # 设备信息
    equipment_info = Column(Text)                         # 过滤/增氧/温控设备描述
    notes = Column(Text)

    # 关联
    water_metrics = relationship("AquariumWaterMetric", back_populates="tank", cascade="all, delete-orphan")
    batches = relationship("LiveSeafoodBatch", back_populates="tank", cascade="all, delete-orphan")
    inspections = relationship("AquariumInspection", back_populates="tank", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AquariumTank(id={self.id}, name='{self.name}', status='{self.status}')>"


# ── 水质指标记录 ─────────────────────────────────────────────────────────────


class AquariumWaterMetric(Base, TimestampMixin):
    """
    水质指标记录

    海水标准参考：
    - 水温: 16-22°C
    - pH: 7.8-8.4
    - 溶解氧: >5 mg/L
    - 盐度: 30-35‰
    - 氨氮: <0.5 mg/L
    - 亚硝酸盐: <0.1 mg/L
    """

    __tablename__ = "aquarium_water_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tank_id = Column(UUID(as_uuid=True), ForeignKey("aquarium_tanks.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 水质指标
    temperature = Column(Float)       # 水温 °C
    ph = Column(Float)                # pH 值
    dissolved_oxygen = Column(Float)  # 溶解氧 mg/L
    salinity = Column(Float)          # 盐度 ‰
    ammonia = Column(Float)           # 氨氮 mg/L
    nitrite = Column(Float)           # 亚硝酸盐 mg/L

    # 数据来源
    source = Column(String(20), default=MetricSource.MANUAL.value, nullable=False)
    recorded_by = Column(String(100))  # 记录人（手动时填写）
    recorded_at = Column(DateTime, nullable=False, index=True)  # 记录时间

    notes = Column(Text)

    # 关联
    tank = relationship("AquariumTank", back_populates="water_metrics")

    def __repr__(self):
        return f"<AquariumWaterMetric(tank={self.tank_id}, temp={self.temperature}, pH={self.ph})>"


# ── 活海鲜批次 ───────────────────────────────────────────────────────────────


class LiveSeafoodBatch(Base, TimestampMixin):
    """活海鲜入缸批次"""

    __tablename__ = "live_seafood_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tank_id = Column(UUID(as_uuid=True), ForeignKey("aquarium_tanks.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 品种信息
    species = Column(String(100), nullable=False)   # 品种名，如"波士顿龙虾"
    category = Column(String(50))                    # 分类，如"虾蟹类"/"贝类"/"鱼类"

    # 入缸信息
    entry_date = Column(DateTime, nullable=False, index=True)
    initial_quantity = Column(Integer, nullable=False)   # 入缸数量（只/条/个）
    initial_weight_g = Column(Integer)                   # 入缸总重量（克）
    unit = Column(String(20), default="只")              # 计量单位

    # 当前存活
    current_quantity = Column(Integer, nullable=False)   # 当前存活数量
    current_weight_g = Column(Integer)                   # 当前估计总重量（克）

    # 成本（单位：分）
    unit_cost_fen = Column(Integer, nullable=False)      # 单位成本（分/只 或 分/斤）
    total_cost_fen = Column(Integer, nullable=False)     # 批次总成本（分）
    cost_unit = Column(String(20), default="只")         # 成本计算单位

    # 供应商
    supplier_name = Column(String(100))
    supplier_contact = Column(String(100))
    purchase_order_id = Column(String(100))              # 关联采购单号

    # 状态
    is_active = Column(String(10), default="true", nullable=False)  # "true"/"false"
    notes = Column(Text)

    # 关联
    tank = relationship("AquariumTank", back_populates="batches")
    mortality_logs = relationship("SeafoodMortalityLog", back_populates="batch", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<LiveSeafoodBatch(species='{self.species}', qty={self.current_quantity}/{self.initial_quantity})>"


# ── 死亡记录 ─────────────────────────────────────────────────────────────────


class SeafoodMortalityLog(Base, TimestampMixin):
    """
    海鲜死亡/损耗记录

    损耗金额 = 批次单位成本 × 死亡数量（单位：分）
    """

    __tablename__ = "seafood_mortality_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("live_seafood_batches.id"), nullable=False, index=True)
    tank_id = Column(UUID(as_uuid=True), ForeignKey("aquarium_tanks.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 死亡详情
    dead_quantity = Column(Integer, nullable=False)      # 死亡数量
    dead_weight_g = Column(Integer)                      # 死亡重量（克）
    reason = Column(String(30), default=MortalityReason.UNKNOWN.value, nullable=False)
    disposal = Column(String(20), default=MortalityDisposal.DISCARD.value, nullable=False)

    # 损耗金额（单位：分） = 批次单位成本 × 死亡数量
    loss_amount_fen = Column(Integer, nullable=False, default=0)

    # 记录信息
    recorded_by = Column(String(100))
    recorded_at = Column(DateTime, nullable=False, index=True)
    notes = Column(Text)

    # 关联
    batch = relationship("LiveSeafoodBatch", back_populates="mortality_logs")

    def __repr__(self):
        return f"<SeafoodMortalityLog(batch={self.batch_id}, dead={self.dead_quantity}, loss=¥{self.loss_amount_fen / 100:.2f})>"


# ── 每日巡检记录 ─────────────────────────────────────────────────────────────


class AquariumInspection(Base, TimestampMixin):
    """每日巡检记录"""

    __tablename__ = "aquarium_inspections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tank_id = Column(UUID(as_uuid=True), ForeignKey("aquarium_tanks.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 巡检信息
    inspector = Column(String(100), nullable=False)      # 巡检人
    inspection_date = Column(Date, nullable=False, index=True)
    inspection_time = Column(DateTime, nullable=False)

    # 巡检结果
    result = Column(String(20), default=InspectionResult.NORMAL.value, nullable=False)
    tank_cleanliness = Column(Integer)  # 清洁度评分 1-10
    fish_activity = Column(Integer)     # 鱼类活跃度 1-10
    equipment_status = Column(Integer)  # 设备状态评分 1-10

    # 异常描述
    abnormal_description = Column(Text)
    action_taken = Column(Text)         # 已采取措施
    image_urls = Column(Text)           # 图片URL，逗号分隔

    notes = Column(Text)

    # 关联
    tank = relationship("AquariumTank", back_populates="inspections")

    def __repr__(self):
        return f"<AquariumInspection(tank={self.tank_id}, result='{self.result}', date={self.inspection_date})>"
