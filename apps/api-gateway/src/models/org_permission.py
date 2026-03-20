"""
OrgPermission — 用户对组织节点的权限映射

支持多节点权限（一个用户可以管理多个不相邻节点）：
  区域经理A → [reg-south: read_write, reg-east: read_only]
  集团CFO    → [grp-demo: read_only]（只读集团财务）
  门店店长   → [sto-gz-001: admin]
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class OrgPermissionLevel(str, enum.Enum):
    READ_ONLY  = "read_only"   # 只读（督导查看）
    READ_WRITE = "read_write"  # 读写（区域经理）
    ADMIN      = "admin"       # 完全控制（门店店长在本店）


class OrgPermission(Base, TimestampMixin):
    """
    用户 → 组织节点 权限行
    一个用户可以有多条记录（管理多个节点）
    权限作用范围 = org_node_id 的整棵子树
    """
    __tablename__ = "org_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "org_node_id", name="uq_org_perm_user_node"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    org_node_id = Column(String(64), ForeignKey("org_nodes.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    permission_level = Column(
        String(32),
        nullable=False,
        default=OrgPermissionLevel.READ_ONLY.value,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    granted_by = Column(UUID(as_uuid=True), nullable=True)  # 授权人 user_id

    def __repr__(self):
        return (f"<OrgPermission(user='{self.user_id}', "
                f"node='{self.org_node_id}', level='{self.permission_level}')>")
