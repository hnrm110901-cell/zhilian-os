"""
Store Model
"""
from sqlalchemy import Column, String, Boolean, JSON, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum

from .base import Base, TimestampMixin


class StoreStatus(str, enum.Enum):
    """门店状态"""
    ACTIVE = "active"  # 营业中
    INACTIVE = "inactive"  # 暂停营业
    RENOVATING = "renovating"  # 装修中
    PREPARING = "preparing"  # 筹备中
    CLOSED = "closed"  # 已关闭


class Store(Base, TimestampMixin):
    """Store/Restaurant model"""

    __tablename__ = "stores"

    id = Column(String(50), primary_key=True)  # e.g., STORE001
    name = Column(String(100), nullable=False)
    code = Column(String(20), unique=True, nullable=False)  # 门店编码

    # 基本信息
    address = Column(String(255))
    city = Column(String(50))  # 城市
    district = Column(String(50))  # 区域
    phone = Column(String(20))
    email = Column(String(100))

    # 地理位置
    latitude = Column(Float)  # 纬度
    longitude = Column(Float)  # 经度

    # 管理信息
    manager_id = Column(UUID(as_uuid=True))  # 店长ID
    region = Column(String(50))  # 所属区域(华东、华南等)
    status = Column(String(20), default=StoreStatus.ACTIVE.value, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # 门店规模
    area = Column(Float)  # 面积(平方米)
    seats = Column(Integer)  # 座位数
    floors = Column(Integer, default=1)  # 楼层数

    # 营业信息
    opening_date = Column(String(20))  # 开业日期
    business_hours = Column(JSON)  # 营业时间 {"monday": "09:00-22:00", ...}

    # Store configuration
    config = Column(JSON, default=dict)  # 其他配置

    # Business metrics targets
    monthly_revenue_target = Column(Float)  # 月营业额目标
    daily_customer_target = Column(Integer)  # 日客流量目标
    cost_ratio_target = Column(Float)  # 成本率目标
    labor_cost_ratio_target = Column(Float)  # 人力成本率目标

    def __repr__(self):
        return f"<Store(id='{self.id}', name='{self.name}', status='{self.status}')>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "address": self.address,
            "city": self.city,
            "district": self.district,
            "phone": self.phone,
            "email": self.email,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "manager_id": str(self.manager_id) if self.manager_id else None,
            "region": self.region,
            "status": self.status,
            "is_active": self.is_active,
            "area": self.area,
            "seats": self.seats,
            "floors": self.floors,
            "opening_date": self.opening_date,
            "business_hours": self.business_hours,
            "config": self.config,
            "monthly_revenue_target": self.monthly_revenue_target,
            "daily_customer_target": self.daily_customer_target,
            "cost_ratio_target": self.cost_ratio_target,
            "labor_cost_ratio_target": self.labor_cost_ratio_target,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
