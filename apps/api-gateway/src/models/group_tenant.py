"""
GroupTenant — 集团SaaS计费锚点表
每个集团对应一条计费记录，用于订阅管理、功能开关、状态追踪。
"""

from datetime import date, datetime
from sqlalchemy import Boolean, Column, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class GroupTenant(Base):
    """集团SaaS计费锚点

    一个 Group（集团）对应一条 GroupTenant 记录。
    该表是订阅计费、功能灰度、账号生命周期管理的权威来源。
    """

    __tablename__ = "group_tenants"

    # 主键：与 group_id 保持同值，便于 JOIN 无需额外关联
    id = Column(String(50), primary_key=True)

    # 关联集团
    group_id = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="FK -> groups.group_id，每集团唯一",
    )

    # 计费联系人
    billing_email = Column(String(200), nullable=False, comment="财务/管理员邮箱")

    # 订阅层级：standard / enterprise / flagship
    subscription_tier = Column(
        String(20),
        nullable=False,
        default="standard",
        comment="standard=标准版 | enterprise=企业版 | flagship=旗舰版",
    )

    # 功能开关（JSONB）：key=功能码, value=bool
    # 示例：{"one_id": true, "cross_brand_analytics": false}
    feature_flags = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="功能开关字典，key=功能码, value=bool",
    )

    # 账号状态：trial / active / suspended / churned
    status = Column(
        String(20),
        nullable=False,
        default="trial",
        index=True,
        comment="trial=试用 | active=正常 | suspended=暂停 | churned=流失",
    )

    # 合同起始日期（计费周期参考点）
    contract_start_date = Column(Date, nullable=True, comment="合同生效日期")

    # 备注（销售/客成备忘）
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="最后更新时间",
    )

    def __repr__(self) -> str:
        return (
            f"<GroupTenant(group_id='{self.group_id}', "
            f"tier='{self.subscription_tier}', status='{self.status}')>"
        )
