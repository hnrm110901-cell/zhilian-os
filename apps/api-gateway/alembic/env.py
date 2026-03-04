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


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to DB)."""
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

