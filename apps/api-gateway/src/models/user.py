"""
User Model
"""
from sqlalchemy import Column, String, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from .base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """User roles - 基于实际餐饮岗位"""
    # 系统管理员
    ADMIN = "admin"

    # 管理层
    STORE_MANAGER = "store_manager"  # 店长
    ASSISTANT_MANAGER = "assistant_manager"  # 店长助理
    FLOOR_MANAGER = "floor_manager"  # 楼面经理
    CUSTOMER_MANAGER = "customer_manager"  # 客户经理

    # 前厅运营
    TEAM_LEADER = "team_leader"  # 领班
    WAITER = "waiter"  # 服务员

    # 后厨运营
    HEAD_CHEF = "head_chef"  # 厨师长
    STATION_MANAGER = "station_manager"  # 档口负责人
    CHEF = "chef"  # 厨师

    # 供应链与支持
    WAREHOUSE_MANAGER = "warehouse_manager"  # 库管
    FINANCE = "finance"  # 财务
    PROCUREMENT = "procurement"  # 采购


class User(Base, TimestampMixin):
    """User model for authentication and authorization"""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(Enum(UserRole, values_callable=lambda x: [e.value for e in x]), default=UserRole.WAITER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    store_id = Column(String(50), index=True)  # Associated store
    wechat_user_id = Column(String(100), index=True)  # WeChat Work user ID for push notifications

    def __repr__(self):
        return f"<User(username='{self.username}', role='{self.role}')>"
