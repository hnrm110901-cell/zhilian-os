"""
测试 RLS 安全漏洞修复迁移脚本（rls_fix_001_critical_security.py）

修复背景:
  - bom_templates / bom_items / waste_events 三张表的 RLS 策略
    使用了错误的 session 变量 app.current_store_id
  - 应用层 tenant_filter.py 实际设置的是 app.current_tenant
  - 导致三张表 RLS 策略永远不生效（完全无租户隔离）

本测试文件验证:
  1. 修复迁移使用了正确的 session 变量名
  2. 三张受影响的表均被覆盖
  3. downgrade() 函数存在且可逆
  4. 旧变量名已不再出现在新策略中
  5. NULL 绕过守卫条件存在

测试日期: 2026-03-30
"""

import ast
import pathlib

# 修复迁移文件路径
_VERSIONS_DIR = pathlib.Path(__file__).parent.parent.parent / "alembic" / "versions"
_MIGRATION_FILE = _VERSIONS_DIR / "rls_fix_001_critical_security.py"

# 三张受影响的表
_REQUIRED_TABLES = {"bom_templates", "bom_items", "waste_events"}

# 正确的 session 变量
_CORRECT_VAR = "app.current_tenant"

# 错误的（旧）session 变量
_WRONG_VAR = "app.current_store_id"


def _read_migration_source() -> str:
    """读取修复迁移文件的源代码"""
    assert _MIGRATION_FILE.exists(), (
        f"修复迁移文件不存在: {_MIGRATION_FILE}\n"
        "请先创建 rls_fix_001_critical_security.py"
    )
    return _MIGRATION_FILE.read_text(encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# 测试1: 验证迁移脚本中使用了正确的 session 变量名
# ────────────────────────────────────────────────────────────────────────────

def test_rls_fix_uses_correct_session_var():
    """修复迁移必须包含正确的 session 变量 app.current_tenant"""
    source = _read_migration_source()
    assert _CORRECT_VAR in source, (
        f"迁移文件中未找到正确的 session 变量 '{_CORRECT_VAR}'。\n"
        f"应用层 tenant_filter.py 设置的是 '{_CORRECT_VAR}'，RLS 策略必须与之一致。"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试2: 验证三张表都被覆盖
# ────────────────────────────────────────────────────────────────────────────

def test_all_three_tables_fixed():
    """迁移文件必须覆盖 bom_templates / bom_items / waste_events 三张表"""
    source = _read_migration_source()
    missing = [t for t in _REQUIRED_TABLES if t not in source]
    assert not missing, (
        f"以下表在修复迁移中未被覆盖: {missing}\n"
        "三张表均使用了错误的 app.current_store_id，必须全部修复。"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试3: 验证 downgrade 可逆（函数存在且有实际内容）
# ────────────────────────────────────────────────────────────────────────────

def test_migration_is_reversible():
    """迁移必须包含非空的 downgrade() 函数，确保可以回滚"""
    source = _read_migration_source()

    # 解析 AST，找到 downgrade 函数
    tree = ast.parse(source)
    downgrade_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            downgrade_fn = node
            break

    assert downgrade_fn is not None, "迁移文件中缺少 downgrade() 函数"

    # 函数体不能只有 pass 或 docstring
    body = downgrade_fn.body
    non_trivial = [
        stmt for stmt in body
        if not isinstance(stmt, (ast.Pass, ast.Expr))
        or (isinstance(stmt, ast.Expr) and not isinstance(stmt.value, ast.Constant))
    ]
    # 至少有一条实质性语句（赋值、循环、调用等）
    has_real_logic = any(
        isinstance(stmt, (ast.Assign, ast.For, ast.Expr, ast.If, ast.With, ast.AugAssign))
        and not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        for stmt in body
    )
    assert has_real_logic, (
        "downgrade() 函数体为空或仅含 pass/docstring，无法真正回滚迁移。\n"
        "必须恢复旧策略（即使旧策略有漏洞）以保证迁移链完整性。"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试4: 验证新策略中不再出现错误的旧变量名（在 upgrade 部分）
# ────────────────────────────────────────────────────────────────────────────

def test_wrong_var_not_in_upgrade_policies():
    """upgrade() 创建的新 RLS 策略的 SQL 中不应含错误变量 app.current_store_id

    注意：upgrade() 注释中允许提及旧变量名（用于解释修复原因），
    但 CREATE POLICY 的 USING / WITH CHECK 子句中绝不能出现错误变量。
    """
    source = _read_migration_source()

    tree = ast.parse(source)
    upgrade_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            upgrade_fn = node
            break

    assert upgrade_fn is not None, "迁移文件中缺少 upgrade() 函数"

    # 从 upgrade 函数中提取所有字符串常量（即实际执行的 SQL）
    # 注释不会出现在 AST 字符串节点中，因此这里只检查真实 SQL 内容
    sql_strings = []
    for node in ast.walk(upgrade_fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql_strings.append(node.value)

    # 在所有 SQL 字符串中，不应出现错误变量
    offending = [s for s in sql_strings if _WRONG_VAR in s]
    assert not offending, (
        f"upgrade() 的 SQL 语句中仍然包含错误的变量名 '{_WRONG_VAR}':\n"
        + "\n".join(f"  - {s[:200]}" for s in offending)
        + f"\n新策略必须只使用 '{_CORRECT_VAR}'。"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试5: 验证 NULL 守卫条件存在（防止未设置 tenant 时泄露数据）
# ────────────────────────────────────────────────────────────────────────────

def test_null_guard_condition_present():
    """新 RLS 策略必须包含 IS NOT NULL 守卫，防止未设置 tenant 时数据泄露"""
    source = _read_migration_source()
    assert "IS NOT NULL" in source, (
        "修复迁移中缺少 IS NOT NULL 守卫条件。\n"
        "当 app.current_tenant 未设置时，current_setting() 返回空字符串，"
        "必须显式拒绝此类连接以防数据泄露。"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试6: 验证迁移元数据（revision / down_revision）
# ────────────────────────────────────────────────────────────────────────────

def test_migration_metadata():
    """迁移文件必须有正确的 revision 和 down_revision 声明"""
    source = _read_migration_source()
    assert "revision" in source, "迁移文件缺少 revision 标识"
    assert "down_revision" in source, "迁移文件缺少 down_revision（迁移链断裂风险）"

    # revision 不能是 None
    assert "revision = None" not in source, "revision 不能为 None"

    # down_revision 不能是 None（这是中间节点，不是初始迁移）
    assert "down_revision = None" not in source, (
        "down_revision 不能为 None，修复迁移必须接在已有迁移链末端"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试7: 验证 DROP IF EXISTS（幂等性）
# ────────────────────────────────────────────────────────────────────────────

def test_migration_is_idempotent():
    """迁移必须使用 DROP IF EXISTS（或等效的幂等操作），支持重复执行"""
    source = _read_migration_source()
    assert "DROP POLICY IF EXISTS" in source or "DROP IF EXISTS" in source, (
        "修复迁移缺少 DROP IF EXISTS 幂等保护。\n"
        "迁移脚本必须支持在相同数据库上重复执行而不报错。"
    )


# ────────────────────────────────────────────────────────────────────────────
# 测试8: 验证 tenant_filter.py 中实际设置的变量与迁移一致
# ────────────────────────────────────────────────────────────────────────────

def test_tenant_filter_consistency():
    """应用层 tenant_filter.py 设置的 session 变量必须与迁移文件中使用的一致"""
    tenant_filter_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "src" / "core" / "tenant_filter.py"
    )
    assert tenant_filter_path.exists(), f"tenant_filter.py 不存在: {tenant_filter_path}"

    tf_source = tenant_filter_path.read_text(encoding="utf-8")
    assert _CORRECT_VAR in tf_source, (
        f"tenant_filter.py 中未找到 '{_CORRECT_VAR}'，\n"
        f"请确认应用层实际使用的 session 变量名。"
    )

    # 同时确认应用层没有使用错误变量（若有也是漏洞）
    assert _WRONG_VAR not in tf_source, (
        f"tenant_filter.py 中发现错误变量 '{_WRONG_VAR}'，\n"
        "应用层应统一使用 app.current_tenant。"
    )
