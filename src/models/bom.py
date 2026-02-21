"""
BOM (Bill of Materials) 配方卡模型
用于管理菜品的原材料配方、净菜率、烹饪损耗等
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class BOM(Base):
    """配方卡表 (Bill of Materials)"""
    __tablename__ = "boms"

    id = Column(String(36), primary_key=True)

    # 菜品信息
    dish_id = Column(String(36), nullable=False, index=True, comment="菜品ID")
    dish_name = Column(String(100), nullable=False, comment="菜品名称")
    dish_category = Column(String(50), comment="菜品分类")

    # 门店信息
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True, comment="门店ID")
    store = relationship("Store", backref="boms")

    # 产出信息
    yield_portions = Column(Float, default=1.0, comment="产出份数")
    yield_unit = Column(String(20), default="份", comment="产出单位")

    # 成本信息
    total_cost = Column(Float, comment="总成本 (元)")
    cost_per_portion = Column(Float, comment="单份成本 (元)")

    # 配方详情 (JSON格式存储原材料列表)
    ingredients = Column(JSON, nullable=False, comment="原材料配方")
    # 格式: [
    #   {
    #     "material_id": "MAT001",
    #     "material_name": "鸡胸肉",
    #     "quantity": 150,
    #     "unit": "g",
    #     "purchase_unit": "kg",
    #     "purchase_quantity": 0.15,
    #     "net_rate": 0.85,
    #     "cooking_loss": 0.10,
    #     "actual_consumption": 176.47,
    #     "unit_cost": 25.0,
    #     "total_cost": 4.41
    #   }
    # ]

    # 制作说明
    preparation_notes = Column(Text, comment="制作说明")
    cooking_time = Column(Integer, comment="烹饪时间 (分钟)")
    difficulty_level = Column(String(20), comment="难度等级: easy, medium, hard")

    # 版本控制
    version = Column(Integer, default=1, comment="版本号")
    is_active = Column(Integer, default=1, comment="是否启用 (0=否, 1=是)")

    # 审计信息
    created_by = Column(String(36), comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_by = Column(String(36), comment="更新人ID")
    updated_at = Column(DateTime, onupdate=datetime.utcnow, comment="更新时间")

    # 统计信息
    usage_count = Column(Integer, default=0, comment="使用次数")
    last_used_at = Column(DateTime, comment="最后使用时间")

    def __repr__(self):
        return f"<BOM(id={self.id}, dish_name={self.dish_name}, store_id={self.store_id})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "dish_id": self.dish_id,
            "dish_name": self.dish_name,
            "dish_category": self.dish_category,
            "store_id": self.store_id,
            "yield_portions": self.yield_portions,
            "yield_unit": self.yield_unit,
            "total_cost": self.total_cost,
            "cost_per_portion": self.cost_per_portion,
            "ingredients": self.ingredients,
            "preparation_notes": self.preparation_notes,
            "cooking_time": self.cooking_time,
            "difficulty_level": self.difficulty_level,
            "version": self.version,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None
        }

    def calculate_total_cost(self):
        """计算总成本"""
        if not self.ingredients:
            return 0.0

        total = 0.0
        for ingredient in self.ingredients:
            # 实际消耗 = 配方用量 / 净菜率 / (1 - 烹饪损耗率)
            quantity = ingredient.get("quantity", 0)
            net_rate = ingredient.get("net_rate", 1.0)
            cooking_loss = ingredient.get("cooking_loss", 0.0)

            actual_consumption = quantity / net_rate / (1 - cooking_loss)
            ingredient["actual_consumption"] = round(actual_consumption, 2)

            # 成本 = 实际消耗 * 单价
            unit_cost = ingredient.get("unit_cost", 0)
            ingredient_cost = (actual_consumption / 1000) * unit_cost  # 转换为kg
            ingredient["total_cost"] = round(ingredient_cost, 2)

            total += ingredient_cost

        self.total_cost = round(total, 2)
        self.cost_per_portion = round(total / self.yield_portions, 2) if self.yield_portions > 0 else 0

        return self.total_cost


class Material(Base):
    """原材料表"""
    __tablename__ = "materials"

    id = Column(String(36), primary_key=True)

    # 基本信息
    material_code = Column(String(50), unique=True, nullable=False, comment="物料编码")
    material_name = Column(String(100), nullable=False, comment="物料名称")
    material_category = Column(String(50), comment="物料分类")
    material_type = Column(String(50), comment="物料类型: raw, semi_finished, finished")

    # 单位信息
    base_unit = Column(String(20), nullable=False, comment="基本单位: g, ml, 个")
    purchase_unit = Column(String(20), nullable=False, comment="采购单位: kg, L, 箱")
    conversion_rate = Column(Float, nullable=False, comment="换算率 (采购单位→基本单位)")

    # 质量参数
    net_rate = Column(Float, default=1.0, comment="净菜率 (0-1)")
    shelf_life_days = Column(Integer, comment="保质期 (天)")
    storage_condition = Column(String(100), comment="储存条件")

    # 成本信息
    standard_cost = Column(Float, comment="标准成本 (元/采购单位)")
    latest_cost = Column(Float, comment="最新成本 (元/采购单位)")

    # 供应商信息
    primary_supplier_id = Column(String(36), comment="主供应商ID")
    supplier_info = Column(JSON, comment="供应商信息列表")

    # 审计信息
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, onupdate=datetime.utcnow, comment="更新时间")
    is_active = Column(Integer, default=1, comment="是否启用")

    def __repr__(self):
        return f"<Material(id={self.id}, name={self.material_name}, code={self.material_code})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "material_code": self.material_code,
            "material_name": self.material_name,
            "material_category": self.material_category,
            "material_type": self.material_type,
            "base_unit": self.base_unit,
            "purchase_unit": self.purchase_unit,
            "conversion_rate": self.conversion_rate,
            "net_rate": self.net_rate,
            "shelf_life_days": self.shelf_life_days,
            "storage_condition": self.storage_condition,
            "standard_cost": self.standard_cost,
            "latest_cost": self.latest_cost,
            "primary_supplier_id": self.primary_supplier_id,
            "supplier_info": self.supplier_info,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active
        }


class WasteRecord(Base):
    """损耗记录表"""
    __tablename__ = "waste_records"

    id = Column(String(36), primary_key=True)

    # 门店信息
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True, comment="门店ID")
    store = relationship("Store", backref="waste_records")

    # 物料信息
    material_id = Column(String(36), ForeignKey("materials.id"), nullable=False, index=True, comment="物料ID")
    material = relationship("Material", backref="waste_records")

    # 损耗信息
    waste_quantity = Column(Float, nullable=False, comment="损耗数量")
    waste_unit = Column(String(20), nullable=False, comment="损耗单位")
    waste_cost = Column(Float, comment="损耗成本 (元)")

    # 损耗原因
    waste_type = Column(String(50), nullable=False, comment="损耗类型: expired, spoiled, damaged, operational, theft")
    waste_reason = Column(Text, comment="损耗原因详细说明")

    # 时间信息
    waste_date = Column(DateTime, nullable=False, index=True, comment="损耗日期")
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="记录时间")

    # 责任人
    responsible_person_id = Column(String(36), comment="责任人ID")
    approved_by = Column(String(36), comment="审批人ID")

    # 审计信息
    created_by = Column(String(36), comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    def __repr__(self):
        return f"<WasteRecord(id={self.id}, material_id={self.material_id}, quantity={self.waste_quantity})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "store_id": self.store_id,
            "material_id": self.material_id,
            "waste_quantity": self.waste_quantity,
            "waste_unit": self.waste_unit,
            "waste_cost": self.waste_cost,
            "waste_type": self.waste_type,
            "waste_reason": self.waste_reason,
            "waste_date": self.waste_date.isoformat() if self.waste_date else None,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "responsible_person_id": self.responsible_person_id,
            "approved_by": self.approved_by,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
