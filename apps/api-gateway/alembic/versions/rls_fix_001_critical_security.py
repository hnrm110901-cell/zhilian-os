"""修复RLS安全漏洞: session变量不一致 + NULL绕过

CRITICAL-001: bom_templates / bom_items / waste_events 三张表的RLS策略
             使用了错误的 app.current_store_id，而应用层(tenant_filter.py)
             实际设置的是 app.current_tenant，导致RLS策略形同虚设。

CRITICAL-002: rls_001_tenant_isolation 创建的18张表策略中包含
             OR current_setting('app.current_tenant', TRUE) IS NULL
             条件，当未设置tenant上下文时，所有数据对任意连接可见。

修复方案:
  1. 删除bom_templates/bom_items/waste_events上使用错误变量的旧策略，
     用 app.current_tenant 重建。
  2. 删除rls_001中18张表含NULL绕过的旧策略，用不含NULL绕过的安全策略重建。
  3. 所有新策略额外添加 current_setting('app.current_tenant', TRUE) IS NOT NULL
     守卫条件，确保未设置tenant时拒绝一切访问。

Revision ID: rls_fix_001
Revises: z68_mission_journey
Create Date: 2026-03-27
"""
from alembic import op, context
import re
import sqlalchemy as sa

revision = 'rls_fix_001'
down_revision = 'z68_mission_journey'
branch_labels = None
depends_on = None

# DDL 标识符（表名/策略名）不支持 bind 参数，必须拼入 SQL。
# 白名单正则确保标识符只含小写字母、数字、下划线，防止注入。
_SAFE_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _assert_safe_ident(name: str) -> None:
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier in migration: {name!r}")


def _table_exists(table_name: str) -> bool:
    """检查表是否存在（离线模式下始终返回 True）"""
    if context.is_offline_mode():
        return True
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_tables "
            "WHERE schemaname='public' AND tablename=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


# ── CRITICAL-001: 使用了错误变量 app.current_store_id 的三张表 ──
# 来源: r01_bom_tables.py 和 r04_waste_event_table.py
# 旧策略名均为 tenant_isolation（不含 _select/_insert 等后缀，是单条 ALL 策略）
CRITICAL_001_TABLES = ['bom_templates', 'bom_items', 'waste_events']
# 旧策略名: "tenant_isolation"（r01/r04 的 CREATE POLICY tenant_isolation ON ...）
CRITICAL_001_OLD_POLICY = 'tenant_isolation'

# ── CRITICAL-002: 含 NULL 绕过的18张表 ──
# 来源: rls_001_tenant_isolation.py
# 旧策略名格式: {table}_tenant_isolation_policy_{select|insert|update|delete}
RLS_001_TABLES = [
    'orders',
    'order_items',
    'reservations',
    'inventory_items',
    'inventory_transactions',
    'schedules',
    'employees',
    'training_records',
    'training_plans',
    'service_feedbacks',
    'complaints',
    'tasks',
    'notifications',
    'pos_transactions',
    'member_transactions',
    'financial_records',
    'supply_orders',
    'reconciliation_records',
]

# 安全的 USING / WITH CHECK 条件模板（不含 NULL 绕过）
# 1. store_id 必须等于当前会话变量
# 2. 当前会话变量必须非 NULL（防止未设置 tenant 时泄露数据）
_SAFE_USING = (
    "store_id::text = current_setting('app.current_tenant', TRUE) "
    "AND current_setting('app.current_tenant', TRUE) IS NOT NULL "
    "AND current_setting('app.current_tenant', TRUE) <> ''"
)


def _drop_and_recreate_policies(table: str, old_policy_names: list[str]) -> None:
    """删除旧策略并创建安全的新策略（SELECT/INSERT/UPDATE/DELETE 四条）

    Args:
        table: 表名（已通过白名单校验）
        old_policy_names: 需要删除的旧策略名列表
    """
    conn = op.get_bind()

    # 1. 删除所有旧策略（幂等: DROP IF EXISTS）
    for policy in old_policy_names:
        _assert_safe_ident(policy)
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {table}"))

    # 2. 创建使用正确变量、不含 NULL 绕过的新策略
    # SELECT 策略
    conn.execute(sa.text(
        f"CREATE POLICY {table}_rls_select ON {table} "
        f"FOR SELECT USING ({_SAFE_USING})"
    ))

    # INSERT 策略
    conn.execute(sa.text(
        f"CREATE POLICY {table}_rls_insert ON {table} "
        f"FOR INSERT WITH CHECK ({_SAFE_USING})"
    ))

    # UPDATE 策略
    conn.execute(sa.text(
        f"CREATE POLICY {table}_rls_update ON {table} "
        f"FOR UPDATE USING ({_SAFE_USING}) WITH CHECK ({_SAFE_USING})"
    ))

    # DELETE 策略
    conn.execute(sa.text(
        f"CREATE POLICY {table}_rls_delete ON {table} "
        f"FOR DELETE USING ({_SAFE_USING})"
    ))

    # 3. 确保 RLS 已启用且强制生效（含表所有者）
    conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def upgrade() -> None:
    """修复两个 CRITICAL 级别的 RLS 安全漏洞"""

    # ====================================================================
    # CRITICAL-001: 修复 bom_templates / bom_items / waste_events
    # 问题: 策略使用 app.current_store_id，但应用层设置的是 app.current_tenant
    # ====================================================================
    for table in CRITICAL_001_TABLES:
        _assert_safe_ident(table)
        if not _table_exists(table):
            continue

        # r01/r04 创建的策略名为 "tenant_isolation"（单条 ALL 策略）
        _drop_and_recreate_policies(table, [CRITICAL_001_OLD_POLICY])

    # ====================================================================
    # CRITICAL-002: 修复 rls_001 中18张表的 NULL 绕过漏洞
    # 问题: OR current_setting('app.current_tenant', TRUE) IS NULL
    #       导致未设置 tenant 上下文时所有数据可见
    # ====================================================================
    for table in RLS_001_TABLES:
        _assert_safe_ident(table)
        if not _table_exists(table):
            continue

        # rls_001 创建的策略名格式: {table}_tenant_isolation_policy_{op}
        old_policies = [
            f"{table}_tenant_isolation_policy_select",
            f"{table}_tenant_isolation_policy_insert",
            f"{table}_tenant_isolation_policy_update",
            f"{table}_tenant_isolation_policy_delete",
        ]
        _drop_and_recreate_policies(table, old_policies)


def downgrade() -> None:
    """回退: 恢复为修复前的策略

    警告: 回退会重新引入安全漏洞（NULL绕过 + 错误变量名）。
    仅在紧急回滚时使用，回退后应尽快重新修复。
    """
    conn = op.get_bind()

    # ── 回退 CRITICAL-001: 恢复 r01/r04 的旧策略（使用 app.current_store_id）──
    for table in CRITICAL_001_TABLES:
        _assert_safe_ident(table)
        if not _table_exists(table):
            continue

        # 删除新策略
        for op_type in ('select', 'insert', 'update', 'delete'):
            conn.execute(sa.text(
                f"DROP POLICY IF EXISTS {table}_rls_{op_type} ON {table}"
            ))

        # 恢复旧的单条策略（使用错误的 app.current_store_id）
        conn.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (store_id = current_setting('app.current_store_id', TRUE))"
        ))

    # ── 回退 CRITICAL-002: 恢复 rls_001 含 NULL 绕过的旧策略 ──
    _NULL_BYPASS_USING = (
        "store_id = current_setting('app.current_tenant', TRUE)::text "
        "OR current_setting('app.current_tenant', TRUE) IS NULL"
    )

    for table in RLS_001_TABLES:
        _assert_safe_ident(table)
        if not _table_exists(table):
            continue

        # 删除新策略
        for op_type in ('select', 'insert', 'update', 'delete'):
            conn.execute(sa.text(
                f"DROP POLICY IF EXISTS {table}_rls_{op_type} ON {table}"
            ))

        policy_base = f"{table}_tenant_isolation_policy"

        # 恢复旧策略（含 NULL 绕过）
        conn.execute(sa.text(
            f"CREATE POLICY {policy_base}_select ON {table} "
            f"FOR SELECT USING ({_NULL_BYPASS_USING})"
        ))
        conn.execute(sa.text(
            f"CREATE POLICY {policy_base}_insert ON {table} "
            f"FOR INSERT WITH CHECK ({_NULL_BYPASS_USING})"
        ))
        conn.execute(sa.text(
            f"CREATE POLICY {policy_base}_update ON {table} "
            f"FOR UPDATE USING ({_NULL_BYPASS_USING}) "
            f"WITH CHECK ({_NULL_BYPASS_USING})"
        ))
        conn.execute(sa.text(
            f"CREATE POLICY {policy_base}_delete ON {table} "
            f"FOR DELETE USING ({_NULL_BYPASS_USING})"
        ))
