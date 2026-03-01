"""
ARCH-004: 执行审计日志模型

execution_audit 表只允许 INSERT（REVOKE UPDATE/DELETE on app_user）
确保审计日志不可篡改。
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, JSON, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class ExecutionRecord(Base):
    """执行审计日志记录（不可篡改：仅 INSERT）"""

    __tablename__ = "execution_audit"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    command_type = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    actor_id = Column(String(100), nullable=False, index=True)
    actor_role = Column(String(50), nullable=False)
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), index=True)
    status = Column(String(50), nullable=False, index=True)  # completed/pending_approval/rolled_back/failed
    level = Column(String(20), nullable=False)               # notify/approve/auto/rollback
    amount = Column(String(30))                              # 涉及金额（字符串存储，避免精度问题）
    result = Column(JSON, default=dict)
    rollback_id = Column(String(50), index=True)             # 关联的回滚记录ID
    rolled_back_by = Column(String(100))
    rolled_back_at = Column(DateTime)

    # 创建时间（审计记录不可修改，不设 updated_at）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ExecutionRecord(id='{self.id}', command='{self.command_type}', status='{self.status}')>"
