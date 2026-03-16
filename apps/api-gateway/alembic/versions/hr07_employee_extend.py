"""hr07 — 员工模型扩展 + 组织架构表

Revision ID: hr07
Revises: hr06
Create Date: 2026-03-15

Adds:
  - employees 表新增 30+ 列（用工类型/合规/个人/银行/工作/工会等）
  - organizations 表（6级组织架构树）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'hr07'
down_revision = 'hr06'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 员工表扩展字段 ──
    with op.batch_alter_table('employees') as batch_op:
        # 用工类型扩展
        batch_op.add_column(sa.Column('employment_type', sa.String(30), server_default='regular'))
        batch_op.add_column(sa.Column('grade_level', sa.String(50), nullable=True))
        # 合规字段
        batch_op.add_column(sa.Column('health_cert_expiry', sa.Date, nullable=True))
        batch_op.add_column(sa.Column('health_cert_attachment', sa.String(500), nullable=True))
        batch_op.add_column(sa.Column('id_card_no', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('id_card_expiry', sa.Date, nullable=True))
        batch_op.add_column(sa.Column('background_check', sa.String(50), nullable=True))
        # 个人扩展
        batch_op.add_column(sa.Column('gender', sa.String(10), nullable=True))
        batch_op.add_column(sa.Column('birth_date', sa.Date, nullable=True))
        batch_op.add_column(sa.Column('education', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('marital_status', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('ethnicity', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('hukou_type', sa.String(30), nullable=True))
        batch_op.add_column(sa.Column('hukou_location', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('height_cm', sa.Integer, nullable=True))
        batch_op.add_column(sa.Column('weight_kg', sa.Integer, nullable=True))
        batch_op.add_column(sa.Column('political_status', sa.String(30), nullable=True))
        # 紧急联系人
        batch_op.add_column(sa.Column('emergency_contact', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('emergency_phone', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('emergency_relation', sa.String(20), nullable=True))
        # 银行信息
        batch_op.add_column(sa.Column('bank_name', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('bank_account', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('bank_branch', sa.String(200), nullable=True))
        # 工作相关
        batch_op.add_column(sa.Column('daily_wage_standard_fen', sa.Integer, nullable=True))
        batch_op.add_column(sa.Column('work_hour_type', sa.String(30), nullable=True))
        batch_op.add_column(sa.Column('first_work_date', sa.Date, nullable=True))
        batch_op.add_column(sa.Column('regular_date', sa.Date, nullable=True))
        batch_op.add_column(sa.Column('seniority_months', sa.Integer, nullable=True))
        # 住宿
        batch_op.add_column(sa.Column('accommodation', sa.String(100), nullable=True))
        # 工会
        batch_op.add_column(sa.Column('union_member', sa.Boolean, server_default='false'))
        batch_op.add_column(sa.Column('union_cadre', sa.Boolean, server_default='false'))
        # 学历/专业
        batch_op.add_column(sa.Column('major', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('graduation_school', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('professional_cert', sa.String(200), nullable=True))
        # 组织架构
        batch_op.add_column(sa.Column('org_id', UUID(as_uuid=True), nullable=True))
        batch_op.create_index('ix_employees_org_id', ['org_id'])
        batch_op.create_index('ix_employees_health_cert_expiry', ['health_cert_expiry'])

    # ── 组织架构表 ──
    op.create_table(
        'organizations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=True, index=True),
        sa.Column('level', sa.Integer, nullable=False),
        sa.Column('org_type', sa.String(30), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=True, index=True),
        sa.Column('manager_id', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('organizations')

    with op.batch_alter_table('employees') as batch_op:
        for col in [
            'employment_type', 'grade_level', 'health_cert_expiry', 'health_cert_attachment',
            'id_card_no', 'id_card_expiry', 'background_check', 'gender', 'birth_date',
            'education', 'marital_status', 'ethnicity', 'hukou_type', 'hukou_location',
            'height_cm', 'weight_kg', 'political_status', 'emergency_contact', 'emergency_phone',
            'emergency_relation', 'bank_name', 'bank_account', 'bank_branch',
            'daily_wage_standard_fen', 'work_hour_type', 'first_work_date', 'regular_date',
            'seniority_months', 'accommodation', 'union_member', 'union_cadre',
            'major', 'graduation_school', 'professional_cert', 'org_id',
        ]:
            batch_op.drop_column(col)
