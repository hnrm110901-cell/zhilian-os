"""
User Model
"""
from sqlalchemy import Column, String, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from .base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """User roles"""
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"


class User(Base, TimestampMixin):
    """User model for authentication and authorization"""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(Enum(UserRole), default=UserRole.STAFF, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    store_id = Column(String(50), index=True)  # Associated store

    def __repr__(self):
        return f"<User(username='{self.username}', role='{self.role}')>"
