"""
本体层 Schema：11 个节点标签与核心关系类型（Palantir 目标架构）
"""
from enum import Enum
from typing import Set

# 11 个核心对象类型（节点标签）
class NodeLabel(str, Enum):
    Store = "Store"
    Dish = "Dish"
    Ingredient = "Ingredient"
    Order = "Order"
    Staff = "Staff"
    InventorySnapshot = "InventorySnapshot"
    BOM = "BOM"
    WasteEvent = "WasteEvent"
    Action = "Action"
    Supplier = "Supplier"
    Equipment = "Equipment"
    TrainingModule = "TrainingModule"  # Phase 1.3: 培训模块节点


# 核心语义关系类型
class RelType(str, Enum):
    # (Order)-[:CONTAINS]->(Dish)
    CONTAINS = "CONTAINS"
    # (Dish)-[:HAS_BOM]->(BOM)
    HAS_BOM = "HAS_BOM"
    # (BOM)-[:REQUIRES {qty, unit, waste_factor}]->(Ingredient)
    REQUIRES = "REQUIRES"
    # (WasteEvent)-[:TRIGGERED_BY]->(Staff)
    TRIGGERED_BY = "TRIGGERED_BY"
    # (Action)-[:ASSIGNED_TO]->(Staff)
    ASSIGNED_TO = "ASSIGNED_TO"
    # 扩展关系
    BELONGS_TO = "BELONGS_TO"       # Staff/Equipment -> Store
    SERVES = "SERVES"               # Order -[:SERVES]-> Staff
    SUPPLIES = "SUPPLIES"           # Supplier -[:SUPPLIES]-> Ingredient
    LOCATED_AT = "LOCATED_AT"       # InventorySnapshot -> Ingredient / Store
    TRACED_TO = "TRACED_TO"         # Action 溯源到推理/事件
    # Phase 1.3: 培训关系
    COMPLETED_TRAINING = "COMPLETED_TRAINING"  # (Staff)-[:COMPLETED_TRAINING {score, completed_at}]->(TrainingModule)
    NEEDS_TRAINING = "NEEDS_TRAINING"          # (Staff)-[:NEEDS_TRAINING {waste_event_id, urgency, deadline}]->(TrainingModule)
    # Phase 3: 门店相似度关系（跨门店知识传播路由）
    SIMILAR_TO = "SIMILAR_TO"                  # (Store)-[:SIMILAR_TO {score, reason}]->(Store)


NODE_LABELS: Set[str] = {e.value for e in NodeLabel}
REL_TYPES: Set[str] = {e.value for e in RelType}

# 各节点建议唯一约束属性（用于 MERGE）
NODE_ID_PROP: dict = {
    NodeLabel.Store.value: "store_id",
    NodeLabel.Dish.value: "dish_id",
    NodeLabel.Ingredient.value: "ing_id",
    NodeLabel.Order.value: "order_id",
    NodeLabel.Staff.value: "staff_id",
    NodeLabel.InventorySnapshot.value: "snapshot_id",
    NodeLabel.BOM.value: "bom_id",
    NodeLabel.WasteEvent.value: "event_id",
    NodeLabel.Action.value: "action_id",
    NodeLabel.Supplier.value: "sup_id",
    NodeLabel.Equipment.value: "equip_id",
    NodeLabel.TrainingModule.value: "module_id",  # Phase 1.3
}

# 徐记 POC 扩展节点（海鲜池与损耗溯源）
class ExtensionNodeLabel(str, Enum):
    LiveSeafood = "LiveSeafood"       # 活海鲜：品种/重量/价格/入池时间/死亡率
    SeafoodPool = "SeafoodPool"       # 海鲜池：容量/温度/盐度/设备状态
    PortionWeight = "PortionWeight"   # 份量记录：菜品/实际克重/标准克重/厨师ID
    PurchaseInvoice = "PurchaseInvoice"  # 采购凭证：供应商/批次/价格/验收人

EXTENSION_ID_PROP: dict = {
    ExtensionNodeLabel.LiveSeafood.value: "live_seafood_id",
    ExtensionNodeLabel.SeafoodPool.value: "pool_id",
    ExtensionNodeLabel.PortionWeight.value: "portion_id",
    ExtensionNodeLabel.PurchaseInvoice.value: "invoice_id",
}
