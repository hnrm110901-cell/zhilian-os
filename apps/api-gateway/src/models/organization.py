"""
Organization hierarchy: Group → Brand → Region
+ 6级组织架构树（集团 → 事业部 → 品牌 → 区域 → 门店 → 部门组）
"""
import uuid
from sqlalchemy import Column, String, Numeric, Boolean, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from .base import Base, TimestampMixin


class Group(Base, TimestampMixin):
    """集团"""
    __tablename__ = "groups"

    group_id = Column(String(50), primary_key=True)
    group_name = Column(String(200), nullable=False)
    legal_entity = Column(String(200), nullable=False)
    unified_social_credit_code = Column(String(18), nullable=False)
    industry_type = Column(String(30), nullable=False)  # chinese_formal/hotpot/...
    contact_person = Column(String(50), nullable=False)
    contact_phone = Column(String(20), nullable=False)
    address = Column(Text)


class Brand(Base, TimestampMixin):
    """品牌"""
    __tablename__ = "brands"

    brand_id = Column(String(50), primary_key=True)
    group_id = Column(String(50), nullable=False, index=True)
    brand_name = Column(String(100), nullable=False)
    cuisine_type = Column(String(30), nullable=False)  # sichuan/hunan/cantonese/...
    avg_ticket_yuan = Column(Numeric(10, 2))
    target_food_cost_pct = Column(Numeric(5, 2), nullable=False)
    target_labor_cost_pct = Column(Numeric(5, 2), nullable=False)
    target_rent_cost_pct = Column(Numeric(5, 2))
    target_waste_pct = Column(Numeric(5, 2), nullable=False)
    logo_url = Column(Text)
    status = Column(String(20), nullable=False, default="active")  # active/inactive


class Region(Base, TimestampMixin):
    """区域"""
    __tablename__ = "regions"

    region_id = Column(String(50), primary_key=True)
    brand_id = Column(String(50), nullable=False, index=True)
    region_name = Column(String(100), nullable=False)
    supervisor_id = Column(String(50))
    store_ids = Column(ARRAY(String(50)))


class Organization(Base, TimestampMixin):
    """组织架构节点（自引用树）"""

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, unique=True)  # 组织编码
    parent_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)
    level = Column(Integer, nullable=False)  # 1=集团 2=事业部 3=品牌 4=区域 5=门店 6=部门组
    org_type = Column(String(30), nullable=False)  # group/business_unit/brand/region/store/department
    store_id = Column(String(50), nullable=True, index=True)  # level≥5时关联Store
    manager_id = Column(String(50), nullable=True)  # 负责人employee_id
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)

    def __repr__(self):
        return f"<Organization(code='{self.code}', name='{self.name}', level={self.level})>"
