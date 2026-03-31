"""
Organization hierarchy: Group → Brand → Region
+ 6级组织架构树（集团 → 事业部 → 品牌 → 区域 → 门店 → 部门组）

Phase 1 升级（z69）：
- Group：增加 org_node_id / is_active / subscription_tier / max_brands / max_stores
- Brand：增加 org_node_id / is_active / cross_brand_one_id（group_id 原已存在）
- Region：增加 org_node_id / group_id（冗余） / is_active
  注：store_ids（ARRAY）已废弃，改为通过 stores.region_id 反向关联
"""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

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

    # --- Phase 1 新增字段 ---
    # 关联 org_nodes 树节点（集团根节点）
    org_node_id = Column(
        String(64),
        nullable=True,
        index=True,
        comment="FK -> org_nodes.id，集团对应的树根节点",
    )
    # 账号状态（区别于业务层面的 is_active）
    is_active = Column(Boolean, nullable=False, default=True, comment="集团账号是否有效")
    # 订阅层级（镜像 group_tenants.subscription_tier，冗余便于查询）
    subscription_tier = Column(
        String(20),
        nullable=False,
        default="standard",
        comment="standard/enterprise/flagship",
    )
    # 规模上限（合同约定）
    max_brands = Column(Integer, nullable=True, comment="合同允许的最大品牌数")
    max_stores = Column(Integer, nullable=True, comment="合同允许的最大门店数")


class Brand(Base, TimestampMixin):
    """品牌"""

    __tablename__ = "brands"

    brand_id = Column(String(50), primary_key=True)
    group_id = Column(String(50), nullable=False, index=True)  # 原有字段，保持不变
    brand_name = Column(String(100), nullable=False)
    cuisine_type = Column(String(30), nullable=False)  # sichuan/hunan/cantonese/...
    avg_ticket_yuan = Column(Numeric(10, 2))
    target_food_cost_pct = Column(Numeric(5, 2), nullable=False)
    target_labor_cost_pct = Column(Numeric(5, 2), nullable=False)
    target_rent_cost_pct = Column(Numeric(5, 2))
    target_waste_pct = Column(Numeric(5, 2), nullable=False)
    logo_url = Column(Text)
    status = Column(String(20), nullable=False, default="active")  # active/inactive

    # --- Phase 1 新增字段 ---
    org_node_id = Column(
        String(64),
        nullable=True,
        index=True,
        comment="FK -> org_nodes.id，品牌对应的树节点",
    )
    is_active = Column(Boolean, nullable=False, default=True, comment="品牌是否有效")
    # One ID 开关：是否允许跨品牌消费者打通
    cross_brand_one_id = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否参与集团 One ID 跨品牌身份整合",
    )


class Region(Base, TimestampMixin):
    """区域"""

    __tablename__ = "regions"

    region_id = Column(String(50), primary_key=True)
    brand_id = Column(String(50), nullable=False, index=True)
    region_name = Column(String(100), nullable=False)
    supervisor_id = Column(String(50))
    # store_ids 已废弃：改为通过 stores.region_id 做反向关联
    # 保留字段避免破坏现有查询，新代码应使用关联查询
    store_ids = Column(ARRAY(String(50)), comment="[废弃] 请使用 stores.region_id 关联")

    # --- Phase 1 新增字段 ---
    org_node_id = Column(
        String(64),
        nullable=True,
        index=True,
        comment="FK -> org_nodes.id，区域对应的树节点",
    )
    # 冗余 group_id：从 brand.group_id 派生，避免2层JOIN
    group_id = Column(
        String(50),
        nullable=True,
        index=True,
        comment="冗余字段：来自 brands.group_id，加速集团级区域查询",
    )
    is_active = Column(Boolean, nullable=False, default=True, comment="区域是否有效")


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
