"""z69: P0安全修复 — 修复bom_templates/bom_items/waste_events的RLS session变量

原问题：r01_bom_tables.py 和 r04_waste_event_table.py 中的RLS策略使用
        current_setting('app.current_store_id', TRUE)，
        但应用代码（tenant_filter.py:94）实际设置的是 app.current_tenant。
        导致RLS永远不生效，所有租户可互相访问彼此数据。

修复：将三张表的策略改为使用 app.current_tenant，并启用 FORCE ROW LEVEL SECURITY
      确保表所有者也受到约束（防止super user绕过）。

Revision ID: z69
Revises: z68_mission_journey
Create Date: 2026-03-31
"""
from alembic import op
import re
import sqlalchemy as sa

revision = "z69"
down_revision = "z68_mission_journey"
branch_labels = None
depends_on = None

# DDL 标识符不支持 bind 参数，白名单校验防止注入
_SAFE_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _assert_safe_ident(name: str) -> None:
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier in migration: {name!r}")


def upgrade() -> None:
    conn = op.get_bind()

    for tbl in ("bom_templates", "bom_items", "waste_events"):
        _assert_safe_ident(tbl)

        # 先禁用旧策略
        conn.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}"))

        # 创建修复后的策略（使用正确的 app.current_tenant 变量）
        # IS NOT NULL 显式拒绝：当session变量未设置时返回false，拒绝访问，不暴露全表
        conn.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {tbl} "
            f"USING ("
            f"  current_setting('app.current_tenant', TRUE) IS NOT NULL"
            f"  AND store_id::text = current_setting('app.current_tenant', TRUE)"
            f")"
        ))

        # 确保没有数据时拒绝访问（而不是全表可见），表所有者也受约束
        conn.execute(sa.text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    """回滚：恢复原来的错误策略（使用 app.current_store_id）"""
    conn = op.get_bind()

    for tbl in ("bom_templates", "bom_items", "waste_events"):
        _assert_safe_ident(tbl)

        conn.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}"))
        conn.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {tbl} "
            f"USING (store_id = current_setting('app.current_store_id', TRUE))"
        ))
        # 注意：downgrade 不恢复 FORCE RLS，与原始迁移行为一致
