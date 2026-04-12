"""
Database Models
"""
from logging.config import fileConfig
import sys
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import models and config
from src.models import Base  # noqa: E402
from src.core.config import settings  # noqa: E402

# 显式 import 后期新增的 model（未在 src/models/__init__.py 中注册的）
# 确保 autogenerate 能检测到全部表
import src.models.action_plan  # noqa: F401
import src.models.knowledge_rule  # noqa: F401
import src.models.private_domain  # noqa: F401
import src.models.ontology_action  # noqa: F401
import src.models.ops  # noqa: F401
import src.models.reasoning  # noqa: F401
import src.models.bom  # noqa: F401
import src.models.cross_store  # noqa: F401
import src.models.ingredient_mapping  # noqa: F401
import src.models.execution_audit  # noqa: F401
import src.models.customer_key  # noqa: F401
import src.models.workflow  # noqa: F401
import src.models.forecast  # noqa: F401
import src.models.agent_config  # noqa: F401
import src.models.consumer_identity  # noqa: F401 — Sprint 1 CDP
import src.models.consumer_id_mapping  # noqa: F401 — Sprint 1 CDP
import src.models.member_check_in       # noqa: F401 — P1 识客
import src.models.member_dish_preference # noqa: F401 — P1 菜品偏好
import src.models.service_voucher        # noqa: F401 — P2 服务券
import src.models.coupon_distribution    # noqa: F401 — P2 发券+ROI
import src.models.marketing_task          # noqa: F401 — P3 营销任务

# HR 模块 — 业人一体化
import src.models.payroll  # noqa: F401
import src.models.approval_flow  # noqa: F401
import src.models.leave  # noqa: F401
import src.models.employee_lifecycle  # noqa: F401
import src.models.recruitment  # noqa: F401
import src.models.performance_review  # noqa: F401
import src.models.employee_contract  # noqa: F401
import src.models.commission  # noqa: F401
import src.models.reward_penalty  # noqa: F401
import src.models.social_insurance  # noqa: F401
import src.models.employee_growth  # noqa: F401
import src.models.brand_im_config  # noqa: F401

# HR架构重构 — 三层模型（hr/ 目录为主模型，旧 models/person.py 为兼容）
import src.models.hr.person  # noqa: F401
import src.models.hr.employment_assignment  # noqa: F401
import src.models.hr.employment_contract  # noqa: F401
import src.models.skill_node  # noqa: F401
import src.models.achievement  # noqa: F401
import src.models.behavior_pattern  # noqa: F401
import src.models.retention_signal  # noqa: F401
import src.models.knowledge_capture  # noqa: F401

# HR 模块 — 业人一体化
import src.models.payroll  # noqa: F401
import src.models.approval_flow  # noqa: F401
import src.models.leave  # noqa: F401
import src.models.employee_lifecycle  # noqa: F401
import src.models.recruitment  # noqa: F401
import src.models.performance_review  # noqa: F401
import src.models.employee_contract  # noqa: F401
import src.models.commission  # noqa: F401
import src.models.reward_penalty  # noqa: F401
import src.models.social_insurance  # noqa: F401
import src.models.employee_growth  # noqa: F401
import src.models.brand_im_config  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url with the one from settings
# Use psycopg2 instead of asyncpg for migrations (Alembic requires sync driver)
database_url = settings.DATABASE_URL.replace("+asyncpg", "").replace(
    "postgresql://", "postgresql+psycopg2://"
)
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _get_tenant_schemas(connection) -> list[str]:
    """从 tenant_schema_map 表获取所有活跃租户 Schema"""
    try:
        result = connection.execute(
            __import__("sqlalchemy").text(
                "SELECT schema_name FROM public.tenant_schema_map WHERE is_active = TRUE"
            )
        )
        return [row[0] for row in result.fetchall()]
    except Exception:
        return []


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    先迁移 public schema，再循环迁移所有租户 schema。
    """
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # 1. 迁移 public schema（系统表 + 共享表）
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

        # 2. 迁移所有租户 schema（DDL 结构保持一致）
        tenant_schemas = _get_tenant_schemas(connection)
        for schema in tenant_schemas:
            try:
                connection.execute(
                    __import__("sqlalchemy").text(f"SET search_path TO {schema}, public")
                )
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    compare_type=True,
                    compare_server_default=True,
                    version_table_schema=schema,
                    include_schemas=[schema],
                )
                with context.begin_transaction():
                    context.run_migrations()
                print(f"  ✅ Schema '{schema}' migrated")
            except Exception as e:
                print(f"  ⚠️ Schema '{schema}' migration skipped: {e}")
            finally:
                connection.execute(
                    __import__("sqlalchemy").text("SET search_path TO public")
                )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

