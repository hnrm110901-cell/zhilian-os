"""
审计日志模型
记录系统中的所有重要操作
"""
from sqlalchemy import Column, String, DateTime, JSON, Integer, Text, Index
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from src.core.database import Base


class AuditLog(Base):
    """审计日志模型"""

    __tablename__ = "audit_logs"

    # 主键
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # 操作信息
    action = Column(String(100), nullable=False, comment="操作类型")
    resource_type = Column(String(100), nullable=False, comment="资源类型")
    resource_id = Column(String(100), comment="资源ID")

    # 用户信息
    user_id = Column(String(36), nullable=False, comment="操作用户ID")
    username = Column(String(100), comment="用户名")
    user_role = Column(String(50), comment="用户角色")

    # 操作详情
    description = Column(Text, comment="操作描述")
    changes = Column(JSON, comment="变更内容")
    old_value = Column(JSON, comment="旧值")
    new_value = Column(JSON, comment="新值")

    # 请求信息
    ip_address = Column(String(45), comment="IP地址")
    user_agent = Column(String(500), comment="User Agent")
    request_method = Column(String(10), comment="请求方法")
    request_path = Column(String(500), comment="请求路径")

    # 结果信息
    status = Column(String(20), nullable=False, default="success", comment="操作状态: success, failed")
    error_message = Column(Text, comment="错误信息")

    # 门店信息
    store_id = Column(String(36), comment="门店ID")

    # 时间戳
    created_at = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")

    # 索引
    __table_args__ = (
        Index('idx_user_id', 'user_id'),
        Index('idx_action', 'action'),
        Index('idx_resource_type', 'resource_type'),
        Index('idx_created_at', 'created_at'),
        Index('idx_store_id', 'store_id'),
        Index('idx_status', 'status'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "username": self.username,
            "user_role": self.user_role,
            "description": self.description,
            "changes": self.changes,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_method": self.request_method,
            "request_path": self.request_path,
            "status": self.status,
            "error_message": self.error_message,
            "store_id": self.store_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# 审计日志操作类型常量
class AuditAction:
    """审计日志操作类型"""

    # 认证相关
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"

    # 用户管理
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_ROLE_CHANGE = "user_role_change"

    # 数据操作
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    VIEW = "view"
    EXPORT = "export"
    IMPORT = "import"

    # 财务操作
    TRANSACTION_CREATE = "transaction_create"
    TRANSACTION_UPDATE = "transaction_update"
    TRANSACTION_DELETE = "transaction_delete"
    BUDGET_CREATE = "budget_create"
    BUDGET_UPDATE = "budget_update"

    # 库存操作
    INVENTORY_UPDATE = "inventory_update"
    INVENTORY_ADJUST = "inventory_adjust"

    # 订单操作
    ORDER_CREATE = "order_create"
    ORDER_UPDATE = "order_update"
    ORDER_CANCEL = "order_cancel"
    ORDER_COMPLETE = "order_complete"

    # 系统操作
    BACKUP_CREATE = "backup_create"
    BACKUP_RESTORE = "backup_restore"
    BACKUP_DELETE = "backup_delete"
    CONFIG_UPDATE = "config_update"
    SYSTEM_SETTING_UPDATE = "system_setting_update"

    # 通知操作
    NOTIFICATION_SEND = "notification_send"

    # 报表操作
    REPORT_GENERATE = "report_generate"
    REPORT_EXPORT = "report_export"


# 资源类型常量
class ResourceType:
    """资源类型"""

    USER = "user"
    STORE = "store"
    ORDER = "order"
    INVENTORY = "inventory"
    TRANSACTION = "transaction"
    BUDGET = "budget"
    BACKUP = "backup"
    NOTIFICATION = "notification"
    REPORT = "report"
    SUPPLIER = "supplier"
    PURCHASE_ORDER = "purchase_order"
    MEMBER = "member"
    SYSTEM = "system"
