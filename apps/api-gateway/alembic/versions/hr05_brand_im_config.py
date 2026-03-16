"""
HR05: 品牌 IM 平台配置 + 通讯录同步

新建表:
  - brand_im_configs     品牌 IM 平台配置（企微/钉钉）
  - im_sync_logs         通讯录同步日志

扩展字段:
  - employees.dingtalk_userid    钉钉用户ID
  - users.dingtalk_user_id       钉钉用户ID

Revision ID: hr05
Revises: hr04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON, ENUM as PG_ENUM

revision = 'hr05'
down_revision = 'hr04'
branch_labels = None
depends_on = None


def _create_enum_safe(name, values):
    """安全创建 PostgreSQL ENUM（已存在则跳过，兼容 offline SQL 生成模式）"""
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(
        f"DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({vals}); "
        f"EXCEPTION WHEN duplicate_object THEN NULL; "
        f"END $$"
    ))


def upgrade():
    # ── ENUM ──
    _create_enum_safe("im_platform_enum", ["wechat_work", "dingtalk"])

    # ── 1. brand_im_configs ──
    op.create_table(
        "brand_im_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("im_platform", PG_ENUM(
            "wechat_work", "dingtalk",
            name="im_platform_enum", create_type=False,
        ), nullable=False),
        # 企微
        sa.Column("wechat_corp_id", sa.String(100), nullable=True),
        sa.Column("wechat_corp_secret", sa.String(200), nullable=True),
        sa.Column("wechat_agent_id", sa.String(50), nullable=True),
        sa.Column("wechat_token", sa.String(200), nullable=True),
        sa.Column("wechat_encoding_aes_key", sa.String(200), nullable=True),
        # 钉钉
        sa.Column("dingtalk_app_key", sa.String(100), nullable=True),
        sa.Column("dingtalk_app_secret", sa.String(200), nullable=True),
        sa.Column("dingtalk_agent_id", sa.String(50), nullable=True),
        sa.Column("dingtalk_aes_key", sa.String(200), nullable=True),
        sa.Column("dingtalk_token", sa.String(200), nullable=True),
        # 同步配置
        sa.Column("sync_enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("sync_interval_minutes", sa.Integer, default=1440),
        sa.Column("auto_create_user", sa.Boolean, default=True),
        sa.Column("auto_disable_user", sa.Boolean, default=True),
        sa.Column("default_store_id", sa.String(50), nullable=True),
        # 同步状态
        sa.Column("last_sync_at", sa.DateTime, nullable=True),
        sa.Column("last_sync_status", sa.String(20), nullable=True),
        sa.Column("last_sync_message", sa.Text, nullable=True),
        sa.Column("last_sync_stats", JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 2. im_sync_logs ──
    op.create_table(
        "im_sync_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.String(50), nullable=False, index=True),
        sa.Column("im_platform", sa.String(20), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("total_platform_members", sa.Integer, default=0),
        sa.Column("added_count", sa.Integer, default=0),
        sa.Column("updated_count", sa.Integer, default=0),
        sa.Column("disabled_count", sa.Integer, default=0),
        sa.Column("user_created_count", sa.Integer, default=0),
        sa.Column("user_disabled_count", sa.Integer, default=0),
        sa.Column("error_count", sa.Integer, default=0),
        sa.Column("errors", JSON, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 3. 扩展字段 ──
    op.add_column("employees", sa.Column("dingtalk_userid", sa.String(100), nullable=True, index=True))
    op.add_column("users", sa.Column("dingtalk_user_id", sa.String(100), nullable=True, index=True))


def downgrade():
    op.drop_column("users", "dingtalk_user_id")
    op.drop_column("employees", "dingtalk_userid")
    op.drop_table("im_sync_logs")
    op.drop_table("brand_im_configs")
