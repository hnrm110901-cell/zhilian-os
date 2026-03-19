"""z54 — HR架构重构M1：新建 persons / assignments / person_contracts / skill_nodes / achievements

扩展式迁移（Expand → Migrate → Contract）第一步：
- 新建全部新表，旧 employees 表完全不受影响
- Person: 全局人员档案（跨门店唯一）
- Assignment: 任职关系（Person 在某个 OrgNode 的岗位分配）
- PersonContract: 合同（绑定 Assignment，含薪酬方案+考勤规则）
- SkillNode: 技能图谱节点（知识OS骨架）
- Achievement: 技能认证记录（Person × SkillNode）

Revision ID: z54
Revises: hr21
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "z54"
down_revision = "hr21"
branch_labels = None
depends_on = None


def _create_enum_safe(name: str, values: list) -> None:
    """安全创建 ENUM 类型（已存在则跳过）"""
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(
        f"DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({vals}); "
        f"EXCEPTION WHEN duplicate_object THEN NULL; "
        f"END $$;"
    ))


def upgrade() -> None:
    # ── ENUM 类型 ────────────────────────────────────────────────
    _create_enum_safe("employment_type_enum", [
        "full_time", "part_time", "hourly", "outsource",
        "dispatch", "partner", "intern", "temp",
    ])
    _create_enum_safe("assignment_status_enum", [
        "active", "ended", "suspended", "pending",
    ])
    _create_enum_safe("person_contract_type_enum", [
        "full_time", "part_time", "hourly", "outsource",
        "dispatch", "partner", "internship",
    ])
    _create_enum_safe("person_contract_status_enum", [
        "draft", "active", "expiring", "expired", "terminated", "renewed",
    ])

    # ── persons 表 ───────────────────────────────────────────────
    op.create_table(
        "persons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, index=True, comment="姓名"),
        sa.Column("id_number", sa.String(18), unique=True, nullable=True, comment="身份证号(加密)"),
        sa.Column("phone", sa.String(20), index=True, comment="手机号"),
        sa.Column("photo_url", sa.String(500), comment="头像URL"),
        # 个人信息
        sa.Column("gender", sa.String(10), comment="性别"),
        sa.Column("birth_date", sa.Date, comment="出生日期"),
        sa.Column("education", sa.String(20), comment="学历"),
        sa.Column("ethnicity", sa.String(20), comment="民族"),
        sa.Column("marital_status", sa.String(20), comment="婚姻状况"),
        sa.Column("hukou_type", sa.String(20), comment="户口类型"),
        sa.Column("hukou_location", sa.String(200), comment="户籍地"),
        # 紧急联系人
        sa.Column("emergency_contact", sa.String(50)),
        sa.Column("emergency_phone", sa.String(20)),
        sa.Column("emergency_relation", sa.String(20)),
        # 银行信息
        sa.Column("bank_name", sa.String(100)),
        sa.Column("bank_account", sa.String(50), comment="加密"),
        sa.Column("bank_branch", sa.String(200)),
        # IM
        sa.Column("wechat_userid", sa.String(100), index=True),
        sa.Column("dingtalk_userid", sa.String(100), index=True),
        # 合规
        sa.Column("health_cert_expiry", sa.Date),
        sa.Column("health_cert_attachment", sa.String(500)),
        sa.Column("id_card_expiry", sa.Date),
        sa.Column("background_check", sa.String(20), server_default="pending"),
        # 技能快照
        sa.Column("skills_snapshot", JSON, server_default="[]"),
        # 元数据
        sa.Column("source", sa.String(50), comment="来源"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # ── assignments 表 ───────────────────────────────────────────
    op.create_table(
        "assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("persons.id"), nullable=False, index=True),
        # 组织
        sa.Column("org_node_id", UUID(as_uuid=True), nullable=True, index=True, comment="组织节点"),
        sa.Column("store_id", sa.String(50), nullable=True, index=True, comment="门店ID(兼容)"),
        sa.Column("brand_id", sa.String(50), nullable=True, index=True, comment="品牌ID"),
        # 岗位
        sa.Column("job_standard_id", UUID(as_uuid=True), nullable=True),
        sa.Column("position", sa.String(50), comment="岗位"),
        sa.Column("department", sa.String(50)),
        sa.Column("grade_level", sa.String(20), comment="职级"),
        # 用工类型
        sa.Column("employment_type", sa.Enum(
            "full_time", "part_time", "hourly", "outsource",
            "dispatch", "partner", "intern", "temp",
            name="employment_type_enum", create_type=False,
        ), server_default="full_time"),
        # 时间
        sa.Column("start_date", sa.Date, nullable=False, comment="任职开始"),
        sa.Column("end_date", sa.Date, nullable=True, comment="任职结束"),
        sa.Column("probation_end_date", sa.Date),
        # 状态
        sa.Column("status", sa.Enum(
            "active", "ended", "suspended", "pending",
            name="assignment_status_enum", create_type=False,
        ), server_default="active", index=True),
        # 工时
        sa.Column("work_hour_type", sa.String(20), server_default="standard"),
        # 旧系统兼容
        sa.Column("legacy_employee_id", sa.String(50), nullable=True, index=True, comment="旧employee.id"),
        # 时间戳
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    # 复合索引：按品牌+状态查询
    op.create_index("ix_assignments_brand_status", "assignments", ["brand_id", "status"])

    # ── person_contracts 表 ──────────────────────────────────────
    op.create_table(
        "person_contracts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", UUID(as_uuid=True), sa.ForeignKey("assignments.id"), nullable=False, index=True),
        # 合同类型
        sa.Column("contract_type", sa.Enum(
            "full_time", "part_time", "hourly", "outsource",
            "dispatch", "partner", "internship",
            name="person_contract_type_enum", create_type=False,
        ), nullable=False),
        sa.Column("status", sa.Enum(
            "draft", "active", "expiring", "expired", "terminated", "renewed",
            name="person_contract_status_enum", create_type=False,
        ), server_default="draft", index=True),
        # 合同期限
        sa.Column("contract_no", sa.String(50), unique=True),
        sa.Column("sign_date", sa.Date),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, comment="null=无固定期限"),
        # 薪酬方案
        sa.Column("pay_scheme", JSON, server_default="{}", comment="结构化薪酬方案"),
        # 考勤规则
        sa.Column("attendance_rule_id", UUID(as_uuid=True), nullable=True),
        # 试用期
        sa.Column("probation_salary_pct", sa.Integer, server_default="80"),
        # 续签
        sa.Column("renewal_count", sa.Integer, server_default="0"),
        sa.Column("previous_contract_id", UUID(as_uuid=True), nullable=True),
        # 终止
        sa.Column("termination_date", sa.Date),
        sa.Column("termination_reason", sa.Text),
        # 电子签
        sa.Column("esign_status", sa.String(20), server_default="pending"),
        sa.Column("esign_url", sa.String(500)),
        sa.Column("signed_pdf_url", sa.String(500)),
        # 备注
        sa.Column("remark", sa.Text),
        # 时间戳
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # ── skill_nodes 表 ───────────────────────────────────────────
    op.create_table(
        "skill_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("skill_id", sa.String(50), unique=True, nullable=False, comment="技能编码"),
        sa.Column("name", sa.String(100), nullable=False, index=True),
        sa.Column("category", sa.String(50), index=True, comment="cooking/service/management/safety"),
        # 图谱关系
        sa.Column("prerequisites", JSON, server_default="[]"),
        sa.Column("related_trainings", JSON, server_default="[]"),
        sa.Column("parent_skill_id", UUID(as_uuid=True), nullable=True),
        # KPI影响
        sa.Column("kpi_impact", JSON, server_default="{}"),
        sa.Column("estimated_revenue_lift", sa.Float, server_default="0"),
        # 等级
        sa.Column("max_level", sa.Integer, server_default="5"),
        sa.Column("level_criteria", JSON, server_default="{}"),
        # 范围
        sa.Column("applicable_positions", JSON, server_default="[]"),
        sa.Column("industry_scope", sa.String(50), server_default="general"),
        # 状态
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("description", sa.Text),
        # 时间戳
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # ── achievements 表 ──────────────────────────────────────────
    op.create_table(
        "achievements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("persons.id"), nullable=False, index=True),
        sa.Column("skill_node_id", UUID(as_uuid=True), sa.ForeignKey("skill_nodes.id"), nullable=False, index=True),
        # 认证
        sa.Column("level", sa.Integer, server_default="1"),
        sa.Column("achieved_at", sa.DateTime, nullable=False),
        sa.Column("evidence", JSON, server_default="{}"),
        # 验证
        sa.Column("verified_by", UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime),
        sa.Column("verification_method", sa.String(50)),
        # 有效期
        sa.Column("expires_at", sa.DateTime),
        sa.Column("is_valid", sa.String(20), server_default="valid"),
        # 备注
        sa.Column("remark", sa.Text),
        # 时间戳
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    # 复合唯一约束：一个人在某技能只有一条有效认证
    op.create_index("ix_achievements_person_skill", "achievements", ["person_id", "skill_node_id"])


def downgrade() -> None:
    op.drop_table("achievements")
    op.drop_table("skill_nodes")
    op.drop_table("person_contracts")
    op.drop_table("assignments")
    op.drop_table("persons")
    op.execute(sa.text("DROP TYPE IF EXISTS person_contract_status_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS person_contract_type_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS assignment_status_enum"))
    op.execute(sa.text("DROP TYPE IF EXISTS employment_type_enum"))
