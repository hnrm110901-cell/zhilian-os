"""
Assignment — 任职关系（Person 在某个 OrgNode 的岗位分配）

核心语义：一个人在哪个节点、什么岗位、什么用工类型。
一人可有多个 Assignment（跨店兼职/调动历史）。
Assignment 是"在职关系"，语义上最接近旧 Employee。

迁移路径：employees 的门店/岗位/入职信息 → assignments
99个引用 employee_id 的模型将在 M3 阶段迁移到 assignment_id
"""
import uuid
import enum
from sqlalchemy import Column, String, Date, DateTime, Boolean, Integer, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from src.models.base import Base, TimestampMixin


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"          # 全职
    PART_TIME = "part_time"          # 兼职
    HOURLY = "hourly"                # 小时工
    OUTSOURCE = "outsource"          # 外包
    DISPATCH = "dispatch"            # 派遣
    PARTNER = "partner"              # 合伙人
    INTERN = "intern"                # 实习
    TEMP = "temp"                    # 临时


class AssignmentStatus(str, enum.Enum):
    ACTIVE = "active"                # 在职
    ENDED = "ended"                  # 已结束
    SUSPENDED = "suspended"          # 停职
    PENDING = "pending"              # 待入职


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联人员
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False, index=True,
                       comment="关联 Person")

    # 组织节点（集团→品牌→区域→门店）
    org_node_id = Column(UUID(as_uuid=True), nullable=True, index=True,
                         comment="组织节点ID（关联 OrgNode，暂不建FK）")
    store_id = Column(String(50), nullable=True, index=True,
                      comment="门店ID（兼容旧系统，冗余字段）")
    brand_id = Column(String(50), nullable=True, index=True,
                      comment="品牌ID（便于跨品牌查询）")

    # 岗位
    job_standard_id = Column(UUID(as_uuid=True), nullable=True,
                             comment="岗位标准ID（关联 JobStandard）")
    position = Column(String(50), comment="岗位名称: waiter/chef/cashier/manager/...")
    department = Column(String(50), comment="部门")
    grade_level = Column(String(20), comment="职级")

    # 用工类型
    employment_type = Column(SAEnum(EmploymentType, name="employment_type_enum", create_type=False),
                             default=EmploymentType.FULL_TIME, comment="用工类型")

    # 时间
    start_date = Column(Date, nullable=False, comment="任职开始日期")
    end_date = Column(Date, nullable=True, comment="任职结束日期（null=在职）")
    probation_end_date = Column(Date, comment="试用期结束日期")

    # 状态
    status = Column(SAEnum(AssignmentStatus, name="assignment_status_enum", create_type=False),
                    default=AssignmentStatus.ACTIVE, index=True, comment="任职状态")

    # 工时
    work_hour_type = Column(String(20), default="standard",
                            comment="工时制: standard/comprehensive/flexible")

    # 旧系统兼容（M3迁移期使用）
    legacy_employee_id = Column(String(50), nullable=True, index=True,
                                comment="旧 employees.id，迁移用")

    def __repr__(self):
        return f"<Assignment {self.person_id} @ {self.store_id} ({self.status})>"
