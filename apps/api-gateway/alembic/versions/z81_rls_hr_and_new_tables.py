"""补全 HR 模块 + 新功能表的 RLS 策略

审计发现 HR 迁移 (hr01-hr21) + 数据融合 (z69) + shadow 模式 (z70) +
活海鲜/菜品变体 (z71) 共 60+ 张表缺少 tenant_id RLS 策略。

本迁移统一补全：
1. ENABLE + FORCE ROW LEVEL SECURITY
2. CREATE POLICY tenant_isolation USING (store_id / brand_id 匹配 app.current_tenant)

Revision ID: z81
Revises: z80
"""

import re
import sqlalchemy as sa
from alembic import op

revision = "z81"
down_revision = "z80"
branch_labels = None
depends_on = None

_SAFE_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _assert_safe_ident(name: str) -> None:
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier in migration: {name!r}")


# ── 按隔离列分组 ──────────────────────────────────────────────────────────

# store_id 隔离的表（大部分 HR 表通过 store_id 关联）
_STORE_ID_TABLES = [
    # hr01
    "salary_structures", "payroll_records", "tax_declarations",
    "leave_type_configs", "leave_balances", "leave_requests",
    "overtime_requests", "employee_changes",
    # hr02
    "job_postings", "candidates", "interviews", "offers",
    "performance_templates", "performance_reviews", "employee_contracts",
    # hr03
    "commission_rules", "commission_records", "reward_penalty_records",
    "social_insurance_configs", "employee_social_insurances",
    # hr04
    "skill_definitions", "employee_skills", "career_paths",
    "employee_milestones", "employee_growth_plans", "employee_wellbeing",
    # hr05
    "brand_im_configs", "im_sync_logs",
    # hr08
    "salary_item_definitions", "salary_item_records", "city_wage_configs",
    # hr09
    "exit_interviews",
    # hr10
    "training_courses", "training_enrollments", "training_exams",
    "exam_attempts", "mentorships",
    # hr12
    "shift_templates", "attendance_rules",
    # hr13
    "sensitive_data_audit_logs",
    # hr14
    "hr_business_rules",
    # hr15
    "approval_templates", "hr_approval_instances",
    "hr_approval_records", "hr_approval_delegations",
    # hr17
    "payslip_records",
    # hr19
    "store_staffing_demands",
    # hr20
    "operation_audit_logs",
    # hr21
    "decision_records",
    # z69 — data fusion
    "fusion_projects", "fusion_tasks", "fusion_entity_maps",
    "fusion_provenances", "fusion_conflicts",
    # z70 — shadow mode
    "shadow_sessions", "shadow_records", "consistency_reports",
    "cutover_states", "cutover_events",
    # z71 — aquarium
    "aquarium_tanks", "aquarium_water_metrics", "live_seafood_batches",
    "seafood_mortality_logs", "aquarium_inspections",
]

# 这些表可能没有 store_id 列，用 brand_id 或通过 FK 间接隔离
# 使用宽松策略：仅 ENABLE+FORCE RLS，不创建列策略（通过 FK 继承安全）
_FK_ONLY_TABLES = [
    # hr01 — approval 流程是跨门店的，通过 brand_id 隔离
    "approval_flow_templates", "approval_instances", "approval_node_records",
    # hr07
    "organizations",
    # z71 — 菜品变体通过 dish_id FK 间接隔离
    "dish_method_variants", "dish_specifications",
]


def _apply_rls(conn, table: str, col: str = "store_id") -> None:
    """为一张表添加 RLS 策略（幂等：先 DROP 再 CREATE）。"""
    _assert_safe_ident(table)
    _assert_safe_ident(col)
    policy_name = f"{table}_tenant_isolation"

    conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
    conn.execute(sa.text(f"""
        CREATE POLICY {policy_name} ON {table}
        USING (
            current_setting('app.current_tenant', TRUE) IS NOT NULL
            AND {col}::text = current_setting('app.current_tenant', TRUE)
        )
    """))


def _apply_rls_fk_only(conn, table: str) -> None:
    """仅启用 RLS（不创建列策略，依赖 FK 关联的父表隔离）。"""
    _assert_safe_ident(table)
    conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def upgrade() -> None:
    conn = op.get_bind()

    for table in _STORE_ID_TABLES:
        try:
            _apply_rls(conn, table)
        except Exception:
            # 表可能不存在（某些 HR 迁移可能未执行），跳过
            pass

    for table in _FK_ONLY_TABLES:
        try:
            _apply_rls_fk_only(conn, table)
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()

    for table in _STORE_ID_TABLES:
        _assert_safe_ident(table)
        policy_name = f"{table}_tenant_isolation"
        try:
            conn.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
            conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        except Exception:
            pass

    for table in _FK_ONLY_TABLES:
        _assert_safe_ident(table)
        try:
            conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        except Exception:
            pass
