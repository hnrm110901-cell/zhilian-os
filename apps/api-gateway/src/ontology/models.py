"""
智链OS 本体数据模型（Python dataclass）

与 Neo4j 节点对应，用于：
  - 推理引擎类型提示
  - 数据融合层 Schema 验证
  - API 序列化

共 11 个本体对象（对标 Palantir Gotham 的 Person/Org/PhoneNumber 等）
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date


# ── L1 核心实体（门店运营主体） ─────────────────────────────────────────────────

@dataclass
class CompanyNode:
    """连锁总部节点"""
    company_id: str
    name: str
    founded_date: Optional[date] = None


@dataclass
class StoreNode:
    """门店节点（单店或连锁分店）"""
    store_id: str           # 格式：BRAND-CITY-SEQ，如 XJ-CHANGSHA-001
    name: str
    tier: str               # premium / standard / fast-food
    address: str
    capacity: int           # 座位数
    company_id: Optional[str] = None


@dataclass
class StaffNode:
    """员工节点"""
    staff_id: str
    name: str
    role: str               # 后厨主厨 / 服务员 / 店长 / 区域经理
    store_id: str
    wechat_id: Optional[str] = None
    error_rate: float = 0.0  # 历史操作失误率 0-1（推理引擎更新）
    joined_date: Optional[int] = None  # Unix timestamp


# ── L2 菜品与配方（BOM 本体层核心） ───────────────────────────────────────────

@dataclass
class DishNode:
    """菜品节点"""
    dish_id: str            # 格式：DISH-<name>-<seq>
    name: str
    category: str           # 海鲜 / 蔬菜 / 主食 / 饮品
    price: float
    store_id: str


@dataclass
class BOMNode:
    """配方（BOM）节点 — 支持时间版本管理"""
    dish_id: str
    version: str            # 格式：YYYY-MM
    effective_date: date
    expiry_date: Optional[date] = None
    yield_rate: float = 1.0  # 出成率，如 0.85 表示 85% 可食用
    notes: Optional[str] = None


@dataclass
class BOMItemRelation:
    """BOM → 食材关系（关系属性）"""
    bom_dish_id: str
    bom_version: str
    ingredient_id: str
    quantity: float
    unit: str               # g / ml / piece / kg


# ── L3 供应链与库存 ──────────────────────────────────────────────────────────

@dataclass
class IngredientNode:
    """食材节点"""
    ing_id: str             # 格式：ING-<name>-<seq>
    name: str
    category: str           # 海鲜 / 蔬菜 / 调料 / 主食
    unit_type: str          # 标准计量单位
    supplier_ids: List[str] = field(default_factory=list)


@dataclass
class SupplierNode:
    """供应商节点"""
    supplier_id: str
    name: str
    contact_phone: str
    lead_time: int          # 交货周期（天）
    reliability: float = 1.0   # 供货可靠性 0-1
    quality_score: float = 5.0  # 质量评分 0-5


@dataclass
class InventorySnapshotNode:
    """库存快照节点（时间序列，追加写入，不修改）"""
    snapshot_id: str
    ingredient_id: str
    quantity: float
    unit: str
    timestamp: int          # Unix timestamp（毫秒）
    source: str             # manual_input / pos_sync / iot_sensor / excel_import


# ── L4 运营事件 ──────────────────────────────────────────────────────────────

@dataclass
class OrderNode:
    """订单节点"""
    order_id: str
    store_id: str
    placed_at: int          # Unix timestamp
    total_amount: float
    status: str             # pending / completed / cancelled


@dataclass
class WasteEventNode:
    """损耗事件节点（推理层的核心分析对象）"""
    event_id: str
    ingredient_id: str
    amount: float
    unit: str
    occurred_at: int        # Unix timestamp
    # 推理层写入字段（初始为空，推理完成后更新）
    root_cause_type: Optional[str] = None   # staff_error / food_quality / equipment_fault / process_deviation
    root_cause_confidence: float = 0.0
    root_cause_evidence: List[str] = field(default_factory=list)
    analysis_timestamp: Optional[int] = None


@dataclass
class EquipmentNode:
    """设备节点（冰箱 / 冷库 / 炉灶等）"""
    equipment_id: str
    name: str
    store_id: str
    status: str             # normal / fault / maintenance
    last_maintenance: Optional[int] = None   # Unix timestamp
    malfunction_rate: float = 0.0


# ── 本体版本元数据 ────────────────────────────────────────────────────────────

ONTOLOGY_VERSION = "1.0"
ONTOLOGY_OBJECTS = [
    "Company", "Store", "Staff",
    "Dish", "BOM", "Ingredient",
    "Supplier", "InventorySnapshot",
    "Order", "WasteEvent", "Equipment",
]
ONTOLOGY_RELATION_COUNT = 15
