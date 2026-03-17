"""
OrgNode — 通用组织层级节点
支持：集团 → 品牌 → 区域 → 城市 → 门店 → 部门（任意深度）
使用 path 字符串（ltree 风格）支持高效子树查询
"""
import enum
from sqlalchemy import Column, String, Boolean, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class OrgNodeType(str, enum.Enum):
    GROUP      = "group"       # 集团
    BRAND      = "brand"       # 品牌
    REGION     = "region"      # 大区（如华南区）
    CITY       = "city"        # 城市
    STORE      = "store"       # 门店
    DEPARTMENT = "department"  # 部门（门店内部，如前厅/后厨）


class StoreType(str, enum.Enum):
    FLAGSHIP     = "flagship"      # 旗舰店
    STANDARD     = "standard"      # 标准店
    MALL         = "mall"          # 购物中心店
    DARK_KITCHEN = "dark_kitchen"  # 暗厨/纯外卖
    FRANCHISE    = "franchise"     # 加盟店（门店层面标记）
    KIOSK        = "kiosk"         # 快取店/档口


class OperationMode(str, enum.Enum):
    DIRECT    = "direct"     # 直营
    FRANCHISE = "franchise"  # 加盟
    JOINT     = "joint"      # 联营
    MANAGED   = "managed"    # 托管


class OrgNode(Base, TimestampMixin):
    """
    通用组织节点树
    path 格式：parent_id.child_id.grandchild_id（点分隔，便于 LIKE 查询子树）
    示例：
      集团根节点  path="grp001"          depth=0
      品牌节点    path="grp001.brd001"   depth=1
      区域节点    path="grp001.brd001.reg001"  depth=2
      门店节点    path="grp001.brd001.reg001.sto001"  depth=3
    """
    __tablename__ = "org_nodes"

    id = Column(String(64), primary_key=True)          # 业务 ID，如 "grp-xj-001"
    name = Column(String(128), nullable=False)          # 显示名称
    code = Column(String(32), unique=True, nullable=True)  # 编码（可选，用于对接外部系统）
    node_type = Column(String(32), nullable=False, index=True)

    # 树形结构
    parent_id = Column(String(64), ForeignKey("org_nodes.id"), nullable=True, index=True)
    path = Column(String(512), nullable=False, index=True)  # 用点分隔的完整路径
    depth = Column(Integer, nullable=False, default=0)      # 层级深度，0=根

    # 门店级专属字段（node_type=store 时有意义）
    store_type     = Column(String(32), nullable=True)   # StoreType 枚举值
    operation_mode = Column(String(32), nullable=True)   # OperationMode 枚举值
    store_ref_id   = Column(String(50), ForeignKey("stores.id"), nullable=True)  # 关联 stores 表

    # 元数据
    description  = Column(Text, nullable=True)
    extra        = Column(JSON, default=dict, server_default="{}")   # 扩展字段（如企微部门ID、POS编码）
    is_active    = Column(Boolean, default=True, nullable=False)
    sort_order   = Column(Integer, default=0)

    # 关系
    parent   = relationship("OrgNode", remote_side=[id], foreign_keys=[parent_id])
    configs  = relationship("OrgConfig", back_populates="org_node", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<OrgNode(id='{self.id}', name='{self.name}', type='{self.node_type}', path='{self.path}')>"

    def get_ancestor_ids(self) -> list[str]:
        """从 path 解析出所有祖先节点 ID（从根到父）"""
        parts = self.path.split(".")
        return parts[:-1]  # 排除自身

    def is_ancestor_of(self, other_path: str) -> bool:
        """判断本节点是否是另一个节点的祖先"""
        return other_path.startswith(self.path + ".")
