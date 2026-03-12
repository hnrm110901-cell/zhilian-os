"""
Organization hierarchy: Group → Brand → Region
"""
from sqlalchemy import Column, String, Numeric, Boolean, Text
from sqlalchemy.dialects.postgresql import ARRAY

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
