# HR Foundation M1 — New Tables + Knowledge Cold Start

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create all 11 new HR tables via two Alembic migrations (z54/z55), register their SQLAlchemy models, and seed the hr_knowledge_rules + skill_nodes tables with the initial restaurant-industry knowledge pack.

**Architecture:** Two migrations land in sequence: z54 creates the core people tables (persons, employment_assignments, employment_contracts, employee_id_map, attendance_rules, kpi_templates); z55 creates the knowledge OS tables (hr_knowledge_rules, skill_nodes, behavior_patterns, person_achievements, retention_signals, knowledge_captures). Each migration is fully idempotent (checks table existence before creating). Seed data is loaded via a one-off CLI command, not at startup.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (sync Column-style matching existing codebase), Alembic, PostgreSQL, pytest-asyncio, `sqlalchemy.dialects.postgresql.UUID/JSONB/ARRAY`

**Prerequisite (HARD GATE):** Migrations z52 (OrgNode) and z53 (OrgScope) must already be merged and applied before starting Task 1. Verify with:
```bash
cd apps/api-gateway
python -m alembic heads
# z53_org_scope_propagation must appear (possibly alongside other heads if the project uses merge migrations)
python -m alembic upgrade z53_org_scope_propagation
# Should be a no-op ("Already up to date.") if z53 is already applied
```

---

## Chunk 1: Core People Tables (z54) + Models

### Task 1: Alembic migration z54 — core HR tables

**Files:**
- Create: `apps/api-gateway/alembic/versions/z54_hr_core_tables.py`

Background: Look at `z51_job_standard_module.py` to understand the project's migration style — it uses `_table_exists()` guard, `UUID` and `JSONB` from `sqlalchemy.dialects.postgresql`, and idempotent `op.create_table` calls.

- [ ] **Step 1: Write the migration file**

```python
"""HR核心人员表 — 替换 Employee 模型的底层数据结构

创建以下表：
  persons                — 全局人员档案（跨门店唯一身份）
  employment_assignments — 在岗关系（人员 × 门店节点 × 岗位）
  employment_contracts   — 用工合同（薪酬方案 + 考勤规则）
  employee_id_map        — 迁移桥接表（旧String PK → 新UUID，临时，M4删除）
  attendance_rules       — 考勤规则配置（employment_contracts依赖）
  kpi_templates          — KPI模板配置（employment_contracts依赖）

Revision ID: z54_hr_core_tables
Revises: z53_org_scope_propagation
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "z54_hr_core_tables"
down_revision = "z53_org_scope_propagation"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "attendance_rules"):
        op.create_table(
            "attendance_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("rule_config", JSONB, nullable=False, server_default="{}"),
            sa.Column("org_node_id", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "kpi_templates"):
        op.create_table(
            "kpi_templates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("template_config", JSONB, nullable=False, server_default="{}"),
            sa.Column("org_node_id", UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "persons"):
        op.create_table(
            "persons",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("legacy_employee_id", sa.String(50), nullable=True, index=True,
                      comment="迁移桥接：原employees.id（如EMP001），M4后删除"),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("id_number", sa.String(18), nullable=True,
                      comment="身份证号，应用层加密后存储"),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("email", sa.String(200), nullable=True),
            sa.Column("photo_url", sa.String(500), nullable=True),
            sa.Column("preferences", JSONB, nullable=True, server_default="{}"),
            sa.Column("emergency_contact", JSONB, nullable=True, server_default="{}"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "employment_assignments"):
        op.create_table(
            "employment_assignments",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("org_node_id", UUID(as_uuid=True),
                      sa.ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                      nullable=False, index=True),
            sa.Column("job_standard_id", UUID(as_uuid=True), nullable=True,
                      comment="引用job_standards.id，无强FK约束（跨模块）"),
            sa.Column("employment_type", sa.String(30), nullable=False,
                      comment="full_time / hourly / outsourced / dispatched / partner"),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active",
                      comment="active / ended / suspended"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index(
            "idx_employment_assignments_active",
            "employment_assignments",
            ["org_node_id", "status"],
        )

    if not _table_exists(conn, "employment_contracts"):
        op.create_table(
            "employment_contracts",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("assignment_id", UUID(as_uuid=True),
                      sa.ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("contract_type", sa.String(30), nullable=False,
                      comment="labor / hourly / outsource / dispatch / partnership"),
            sa.Column("pay_scheme", JSONB, nullable=False, server_default="{}"),
            sa.Column("attendance_rule_id", UUID(as_uuid=True),
                      sa.ForeignKey("attendance_rules.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("kpi_template_id", UUID(as_uuid=True),
                      sa.ForeignKey("kpi_templates.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("valid_from", sa.Date, nullable=False),
            sa.Column("valid_to", sa.Date, nullable=True),
            sa.Column("signed_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("file_url", sa.String(500), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "employee_id_map"):
        op.create_table(
            "employee_id_map",
            sa.Column("legacy_employee_id", sa.String(50), primary_key=True,
                      comment="原employees.id值，如EMP001"),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("assignment_id", UUID(as_uuid=True),
                      sa.ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                      nullable=False),
        )
        op.create_index("idx_employee_id_map_person", "employee_id_map", ["person_id"])
        op.create_index("idx_employee_id_map_assignment", "employee_id_map", ["assignment_id"])


def downgrade() -> None:
    conn = op.get_bind()
    for table in [
        "employee_id_map", "employment_contracts", "employment_assignments",
        "persons", "kpi_templates", "attendance_rules",
    ]:
        if _table_exists(conn, table):
            op.drop_table(table)
```

- [ ] **Step 2: Verify migration applies cleanly**

```bash
cd apps/api-gateway
python -m alembic upgrade z54_hr_core_tables
```
Expected: no errors, 6 new tables visible in psql (`\dt persons`, `\dt employment_assignments`, etc.)

- [ ] **Step 3: Verify downgrade works**

```bash
python -m alembic downgrade z53_org_scope_propagation
python -m alembic upgrade z54_hr_core_tables
```
Expected: both commands succeed with no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/api-gateway/alembic/versions/z54_hr_core_tables.py
git commit -m "feat(hr): z54 migration — persons/assignments/contracts/attendance_rules/kpi_templates"
```

---

### Task 2: SQLAlchemy models for z54 tables

**Files:**
- Create: `apps/api-gateway/src/models/hr/__init__.py`
- Create: `apps/api-gateway/src/models/hr/person.py`
- Create: `apps/api-gateway/src/models/hr/employment_assignment.py`
- Create: `apps/api-gateway/src/models/hr/employment_contract.py`
- Create: `apps/api-gateway/src/models/hr/employee_id_map.py`
- Create: `apps/api-gateway/src/models/hr/attendance_rule.py`
- Create: `apps/api-gateway/src/models/hr/kpi_template.py`
- Modify: `apps/api-gateway/src/models/__init__.py`

Background: Look at `src/models/employee.py` and `src/models/base.py` to understand the existing model pattern. Models use `Column` (not `mapped_column`), `Base` from `src.models.base`, and `TimestampMixin` where appropriate. UUIDs use `UUID(as_uuid=True)` with `default=uuid.uuid4`.

- [ ] **Step 1: Write the test first**

Create `apps/api-gateway/tests/test_hr_models_z54.py`:

```python
"""Unit tests for z54 HR core models — no DB required."""
import uuid
import pytest
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.hr.employment_contract import EmploymentContract
from src.models.hr.employee_id_map import EmployeeIdMap
from src.models.hr.attendance_rule import AttendanceRule
from src.models.hr.kpi_template import KpiTemplate


def test_person_tablename():
    assert Person.__tablename__ == "persons"


def test_person_has_required_columns():
    cols = {c.name for c in Person.__table__.columns}
    assert {"id", "legacy_employee_id", "name", "phone", "email",
            "preferences", "created_at", "updated_at"}.issubset(cols)


def test_person_id_is_uuid():
    from sqlalchemy.dialects.postgresql import UUID
    col = Person.__table__.columns["id"]
    assert isinstance(col.type, UUID)


def test_employment_assignment_tablename():
    assert EmploymentAssignment.__tablename__ == "employment_assignments"


def test_employment_assignment_has_required_columns():
    cols = {c.name for c in EmploymentAssignment.__table__.columns}
    assert {"id", "person_id", "org_node_id", "employment_type",
            "start_date", "status"}.issubset(cols)


def test_employment_contract_has_pay_scheme_jsonb():
    from sqlalchemy.dialects.postgresql import JSONB
    col = EmploymentContract.__table__.columns["pay_scheme"]
    assert isinstance(col.type, JSONB)


def test_employee_id_map_pk_is_string():
    col = EmployeeIdMap.__table__.columns["legacy_employee_id"]
    from sqlalchemy import String
    assert isinstance(col.type, String)
    assert col.primary_key is True


def test_all_models_importable():
    # Smoke test: all 6 models import without error
    from src.models.hr import (
        Person, EmploymentAssignment, EmploymentContract,
        EmployeeIdMap, AttendanceRule, KpiTemplate,
    )
    assert all([Person, EmploymentAssignment, EmploymentContract,
                EmployeeIdMap, AttendanceRule, KpiTemplate])
```

- [ ] **Step 2: Run the test — expect ImportError (models don't exist yet)**

```bash
cd apps/api-gateway
python -m pytest tests/test_hr_models_z54.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'src.models.hr'`

- [ ] **Step 3: Create `src/models/hr/__init__.py`**

```python
"""HR domain models — persons, assignments, contracts."""
from .person import Person
from .employment_assignment import EmploymentAssignment
from .employment_contract import EmploymentContract
from .employee_id_map import EmployeeIdMap
from .attendance_rule import AttendanceRule
from .kpi_template import KpiTemplate

__all__ = [
    "Person",
    "EmploymentAssignment",
    "EmploymentContract",
    "EmployeeIdMap",
    "AttendanceRule",
    "KpiTemplate",
]
```

- [ ] **Step 4: Create `src/models/hr/person.py`**

Note: Do NOT use `TimestampMixin` here — that mixin uses plain `DateTime` (no timezone), but our migration creates `TIMESTAMP(timezone=True)` columns. Define them explicitly to stay consistent with the migration and avoid asyncpg timezone-handling bugs.

```python
"""Person — 全局人员档案（跨门店唯一自然人身份）"""
import uuid
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legacy_employee_id = Column(String(50), nullable=True, index=True,
                                comment="迁移桥接：原employees.id，M4后删除")
    name = Column(String(100), nullable=False)
    id_number = Column(String(18), nullable=True,
                       comment="身份证号，应用层加密后存储")
    phone = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    photo_url = Column(String(500), nullable=True)
    preferences = Column(JSONB, nullable=True, default=dict)
    emergency_contact = Column(JSONB, nullable=True, default=dict)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, name={self.name!r})>"
```

- [ ] **Step 5: Create `src/models/hr/employment_assignment.py`**

```python
"""EmploymentAssignment — 在岗关系（Person × OrgNode × 岗位）"""
import uuid
from sqlalchemy import Column, String, Date, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class EmploymentAssignment(Base):
    __tablename__ = "employment_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    org_node_id = Column(UUID(as_uuid=True),
                         ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    # 引用job_standards.id，无强FK（跨模块，避免循环依赖）
    job_standard_id = Column(UUID(as_uuid=True), nullable=True)
    employment_type = Column(String(30), nullable=False,
                             comment="full_time/hourly/outsourced/dispatched/partner")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="active",
                    comment="active/ended/suspended")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<EmploymentAssignment(id={self.id}, "
                f"person_id={self.person_id}, status={self.status!r})>")
```

- [ ] **Step 6: Create `src/models/hr/employment_contract.py`**

```python
"""EmploymentContract — 用工合同（薪酬方案 + 考勤规则）"""
import uuid
from sqlalchemy import Column, String, Date, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class EmploymentContract(Base):
    __tablename__ = "employment_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    contract_type = Column(String(30), nullable=False,
                           comment="labor/hourly/outsource/dispatch/partnership")
    pay_scheme = Column(JSONB, nullable=False, default=dict,
                        comment="薪酬方案：月薪/时薪/提成比例等")
    attendance_rule_id = Column(UUID(as_uuid=True),
                                ForeignKey("attendance_rules.id", ondelete="SET NULL"),
                                nullable=True)
    kpi_template_id = Column(UUID(as_uuid=True),
                             ForeignKey("kpi_templates.id", ondelete="SET NULL"),
                             nullable=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    signed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    file_url = Column(String(500), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<EmploymentContract(id={self.id}, "
                f"type={self.contract_type!r})>")
```

- [ ] **Step 7: Create `src/models/hr/employee_id_map.py`**

```python
"""EmployeeIdMap — 迁移桥接表（旧String PK → 新UUID）。临时表，M4阶段删除。"""
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class EmployeeIdMap(Base):
    __tablename__ = "employee_id_map"

    legacy_employee_id = Column(String(50), primary_key=True,
                                comment="原employees.id，如EMP001")
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                           nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<EmployeeIdMap({self.legacy_employee_id!r} → {self.person_id})>"
```

- [ ] **Step 8: Create `src/models/hr/attendance_rule.py`**

```python
"""AttendanceRule — 考勤规则配置（被EmploymentContract引用）"""
import uuid
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class AttendanceRule(Base):
    __tablename__ = "attendance_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    rule_config = Column(JSONB, nullable=False, default=dict)
    # NULL = 全集团通用规则
    org_node_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<AttendanceRule(id={self.id}, name={self.name!r})>"
```

- [ ] **Step 9: Create `src/models/hr/kpi_template.py`**

```python
"""KpiTemplate — KPI模板配置（被EmploymentContract引用）"""
import uuid
from sqlalchemy import Column, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class KpiTemplate(Base):
    __tablename__ = "kpi_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    template_config = Column(JSONB, nullable=False, default=dict)
    # NULL = 全集团通用模板
    org_node_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<KpiTemplate(id={self.id}, name={self.name!r})>"
```

- [ ] **Step 10: Register new models in `src/models/__init__.py`**

Find the models `__init__.py`. It will have a list of imports. Add:
```python
# HR domain models (z54)
from .hr import (
    Person,
    EmploymentAssignment,
    EmploymentContract,
    EmployeeIdMap,
    AttendanceRule,
    KpiTemplate,
)
```

- [ ] **Step 11: Run the model tests — expect PASS**

```bash
cd apps/api-gateway
python -m pytest tests/test_hr_models_z54.py -v
```
Expected: all 8 tests PASS

- [ ] **Step 12: Commit**

```bash
git add apps/api-gateway/src/models/hr/ \
        apps/api-gateway/src/models/__init__.py \
        apps/api-gateway/tests/test_hr_models_z54.py
git commit -m "feat(hr): SQLAlchemy models for z54 core HR tables (Person/Assignment/Contract)"
```

---

## Chunk 2: Knowledge OS Tables (z55) + Models

### Task 3: Alembic migration z55 — knowledge OS tables

**Files:**
- Create: `apps/api-gateway/alembic/versions/z55_hr_knowledge_tables.py`

- [ ] **Step 1: Write the migration file**

```python
"""HR知识OS层 — 三位一体知识操作系统

创建以下表：
  hr_knowledge_rules — HR专属行业经验库（与现有knowledge_rules共存，不修改）
  skill_nodes        — 技能知识图谱骨架
  behavior_patterns  — 行为模式学习（元数据，向量存Qdrant）
  person_achievements — 技能认证记录
  retention_signals  — 离职风险预测信号
  knowledge_captures  — 对话式知识采集记录

Revision ID: z55_hr_knowledge_tables
Revises: z54_hr_core_tables
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "z55_hr_knowledge_tables"
down_revision = "z54_hr_core_tables"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "hr_knowledge_rules"):
        op.create_table(
            "hr_knowledge_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("rule_type", sa.String(30), nullable=False,
                      comment="sop / kpi_baseline / alert / best_practice"),
            sa.Column("category", sa.String(50), nullable=True,
                      comment="turnover / scheduling / standards / training"),
            sa.Column("condition", JSONB, nullable=False, server_default="{}"),
            sa.Column("action", JSONB, nullable=False, server_default="{}"),
            sa.Column("expected_impact", JSONB, nullable=True),
            sa.Column("confidence", sa.Float, nullable=False, server_default="0.8"),
            sa.Column("industry_source", sa.String(100), nullable=True),
            sa.Column("org_node_id", UUID(as_uuid=True), nullable=True,
                      comment="NULL = 全行业通用"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_hr_knowledge_rules_category",
                        "hr_knowledge_rules", ["category", "rule_type"])
        op.create_index("idx_hr_knowledge_rules_org",
                        "hr_knowledge_rules", ["org_node_id"])

    if not _table_exists(conn, "skill_nodes"):
        op.create_table(
            "skill_nodes",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("skill_name", sa.String(100), nullable=False),
            sa.Column("category", sa.String(50), nullable=True,
                      comment="service / kitchen / management / compliance"),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("prerequisite_skill_ids", ARRAY(UUID(as_uuid=True)),
                      nullable=True, server_default="{}",
                      comment="前置技能UUID数组（无FK约束，PostgreSQL数组）"),
            sa.Column("related_training_ids", ARRAY(UUID(as_uuid=True)),
                      nullable=True, server_default="{}"),
            sa.Column("kpi_impact", JSONB, nullable=True),
            sa.Column("estimated_revenue_lift", sa.Numeric(10, 2), nullable=True,
                      comment="预计¥收入提升（元/月）"),
            sa.Column("org_node_id", UUID(as_uuid=True), nullable=True,
                      comment="NULL = 行业通用技能"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_skill_nodes_category",
                        "skill_nodes", ["category"])

    if not _table_exists(conn, "behavior_patterns"):
        op.create_table(
            "behavior_patterns",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("pattern_type", sa.String(50), nullable=True,
                      comment="turnover_risk / high_performance / schedule_optimal"),
            sa.Column("feature_vector", JSONB, nullable=False, server_default="{}",
                      comment="特征元数据（字段名+权重），实际向量存Qdrant"),
            sa.Column("qdrant_vector_id", sa.String(100), nullable=True,
                      comment="Qdrant collection hr_behavior_patterns 的向量ID"),
            sa.Column("outcome", sa.String(100), nullable=True),
            sa.Column("confidence", sa.Float, nullable=True),
            sa.Column("sample_size", sa.Integer, nullable=True),
            sa.Column("org_scope", sa.String(30), nullable=True,
                      comment="brand / region / network"),
            sa.Column("org_node_id", UUID(as_uuid=True), nullable=True),
            sa.Column("last_trained", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "person_achievements"):
        op.create_table(
            "person_achievements",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("skill_node_id", UUID(as_uuid=True),
                      sa.ForeignKey("skill_nodes.id", ondelete="RESTRICT"),
                      nullable=False, index=True),
            sa.Column("achieved_at", sa.Date, nullable=False),
            sa.Column("evidence", sa.Text, nullable=True),
            sa.Column("verified_by", UUID(as_uuid=True), nullable=True,
                      comment="认证人的person_id"),
            sa.Column("trigger_type", sa.String(30), nullable=True,
                      server_default="'manual'",
                      comment="manual / legacy_import / ai_assessment"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_person_achievements_person_skill",
                        "person_achievements", ["person_id", "skill_node_id"],
                        unique=True)

    if not _table_exists(conn, "retention_signals"):
        op.create_table(
            "retention_signals",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("assignment_id", UUID(as_uuid=True),
                      sa.ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("risk_score", sa.Float, nullable=False,
                      comment="0.0-1.0"),
            sa.Column("risk_factors", JSONB, nullable=False, server_default="{}"),
            sa.Column("intervention_status", sa.String(30), nullable=False,
                      server_default="'pending'",
                      comment="pending / in_progress / resolved"),
            sa.Column("intervention_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("computed_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index("idx_retention_signals_scan",
                        "retention_signals", ["risk_score", "computed_at"])
        op.create_index("idx_retention_signals_assignment",
                        "retention_signals", ["assignment_id", "computed_at"])

    if not _table_exists(conn, "knowledge_captures"):
        op.create_table(
            "knowledge_captures",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("trigger_type", sa.String(30), nullable=True,
                      comment=("exit / monthly_review / incident / onboarding / "
                               "growth_review / talent_assessment / legacy_import")),
            sa.Column("raw_dialogue", sa.Text, nullable=True),
            sa.Column("context", sa.Text, nullable=True),
            sa.Column("action", sa.Text, nullable=True),
            sa.Column("result", sa.Text, nullable=True),
            sa.Column("structured_output", JSONB, nullable=True),
            sa.Column("knowledge_node_id", UUID(as_uuid=True), nullable=True,
                      comment="关联的skill_nodes.id（无强FK，可为空）"),
            sa.Column("quality_score", sa.Float, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table in [
        "knowledge_captures", "retention_signals", "person_achievements",
        "behavior_patterns", "skill_nodes", "hr_knowledge_rules",
    ]:
        if _table_exists(conn, table):
            op.drop_table(table)
```

- [ ] **Step 2: Apply z55 migration**

```bash
cd apps/api-gateway
python -m alembic upgrade z55_hr_knowledge_tables
```
Expected: 6 new tables created, no errors.

- [ ] **Step 3: Verify indexes exist**

```bash
python -c "
import subprocess, sys
r = subprocess.run(['psql', '-c',
    \"SELECT indexname FROM pg_indexes WHERE tablename IN \
    ('retention_signals','skill_nodes','hr_knowledge_rules') \
    ORDER BY indexname;\"],
    capture_output=True, text=True)
print(r.stdout)
"
```
Expected: `idx_hr_knowledge_rules_category`, `idx_retention_signals_scan`, `idx_skill_nodes_category` visible.

- [ ] **Step 4: Commit**

```bash
git add apps/api-gateway/alembic/versions/z55_hr_knowledge_tables.py
git commit -m "feat(hr): z55 migration — hr_knowledge_rules/skill_nodes/behavior_patterns/achievements/retention/captures"
```

---

### Task 4: SQLAlchemy models for z55 tables

**Files:**
- Create: `apps/api-gateway/src/models/hr_knowledge/__init__.py`
- Create: `apps/api-gateway/src/models/hr_knowledge/hr_knowledge_rule.py`
- Create: `apps/api-gateway/src/models/hr_knowledge/skill_node.py`
- Create: `apps/api-gateway/src/models/hr_knowledge/behavior_pattern.py`
- Create: `apps/api-gateway/src/models/hr_knowledge/person_achievement.py`
- Create: `apps/api-gateway/src/models/hr_knowledge/retention_signal.py`
- Create: `apps/api-gateway/src/models/hr_knowledge/knowledge_capture.py`
- Modify: `apps/api-gateway/src/models/__init__.py`

- [ ] **Step 1: Write the test first**

Create `apps/api-gateway/tests/test_hr_models_z55.py`:

```python
"""Unit tests for z55 HR knowledge OS models — no DB required."""
import pytest
from src.models.hr_knowledge.hr_knowledge_rule import HrKnowledgeRule
from src.models.hr_knowledge.skill_node import SkillNode
from src.models.hr_knowledge.behavior_pattern import BehaviorPattern
from src.models.hr_knowledge.person_achievement import PersonAchievement
from src.models.hr_knowledge.retention_signal import RetentionSignal
from src.models.hr_knowledge.knowledge_capture import KnowledgeCapture


def test_hr_knowledge_rule_tablename():
    assert HrKnowledgeRule.__tablename__ == "hr_knowledge_rules"


def test_skill_node_has_array_columns():
    from sqlalchemy.dialects.postgresql import ARRAY
    col = SkillNode.__table__.columns["prerequisite_skill_ids"]
    assert isinstance(col.type, ARRAY)


def test_retention_signal_has_risk_score():
    cols = {c.name for c in RetentionSignal.__table__.columns}
    assert "risk_score" in cols
    assert "intervention_status" in cols


def test_person_achievement_unique_constraint():
    # Should have a unique constraint on (person_id, skill_node_id)
    uqs = [c for c in PersonAchievement.__table__.constraints
           if hasattr(c, 'columns')]
    col_sets = [frozenset(c.name for c in uq.columns) for uq in uqs
                if len(list(uq.columns)) == 2]
    assert frozenset(["person_id", "skill_node_id"]) in col_sets


def test_knowledge_capture_trigger_types():
    col = KnowledgeCapture.__table__.columns["trigger_type"]
    # Should be a VARCHAR/String, not an Enum (flexible for new types)
    from sqlalchemy import String
    assert isinstance(col.type, String)


def test_behavior_pattern_has_qdrant_vector_id():
    cols = {c.name for c in BehaviorPattern.__table__.columns}
    assert "qdrant_vector_id" in cols


def test_all_knowledge_models_importable():
    from src.models.hr_knowledge import (
        HrKnowledgeRule, SkillNode, BehaviorPattern,
        PersonAchievement, RetentionSignal, KnowledgeCapture,
    )
    assert all([HrKnowledgeRule, SkillNode, BehaviorPattern,
                PersonAchievement, RetentionSignal, KnowledgeCapture])
```

- [ ] **Step 2: Run test — expect ImportError**

```bash
python -m pytest tests/test_hr_models_z55.py -v 2>&1 | head -5
```
Expected: `ModuleNotFoundError: No module named 'src.models.hr_knowledge'`

- [ ] **Step 3: Create `src/models/hr_knowledge/hr_knowledge_rule.py`**

```python
"""HrKnowledgeRule — HR专属行业经验库

与现有 knowledge_rules 表共存，互不干扰。
现有表用于通用规则引擎；本表专用于HR领域AGI推理。
"""
import uuid
from sqlalchemy import Column, String, Float, Boolean, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class HrKnowledgeRule(Base):
    __tablename__ = "hr_knowledge_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_type = Column(String(30), nullable=False,
                       comment="sop / kpi_baseline / alert / best_practice")
    category = Column(String(50), nullable=True,
                      comment="turnover / scheduling / standards / training")
    condition = Column(JSONB, nullable=False, default=dict)
    action = Column(JSONB, nullable=False, default=dict)
    expected_impact = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=False, default=0.8)
    industry_source = Column(String(100), nullable=True)
    org_node_id = Column(UUID(as_uuid=True), nullable=True,
                         comment="NULL = 全行业通用")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<HrKnowledgeRule(id={self.id}, type={self.rule_type!r})>"
```

- [ ] **Step 4: Create `src/models/hr_knowledge/skill_node.py`**

```python
"""SkillNode — 知识图谱骨架（技能节点）

prerequisite_skill_ids 使用PostgreSQL ARRAY存储前置技能UUID列表。
无FK约束（图结构不适合FK）。未来可迁移至Neo4j，skill_node.id作为桥接键。
"""
import uuid
from sqlalchemy import Column, String, Text, Numeric, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from ..base import Base


class SkillNode(Base):
    __tablename__ = "skill_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True,
                      comment="service / kitchen / management / compliance")
    description = Column(Text, nullable=True)
    prerequisite_skill_ids = Column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list,
        comment="前置技能UUID列表（无FK约束）",
    )
    related_training_ids = Column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list,
    )
    kpi_impact = Column(JSONB, nullable=True)
    estimated_revenue_lift = Column(Numeric(10, 2), nullable=True,
                                    comment="预计¥收入提升（元/月）")
    org_node_id = Column(UUID(as_uuid=True), nullable=True,
                         comment="NULL = 行业通用技能")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<SkillNode(id={self.id}, name={self.skill_name!r})>"
```

- [ ] **Step 5: Create remaining 4 models**

`src/models/hr_knowledge/behavior_pattern.py`:
```python
"""BehaviorPattern — 行为模式学习（元数据层，向量存Qdrant hr_behavior_patterns）"""
import uuid
from sqlalchemy import Column, String, Float, Integer, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class BehaviorPattern(Base):
    __tablename__ = "behavior_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern_type = Column(String(50), nullable=True)
    feature_vector = Column(JSONB, nullable=False, default=dict,
                            comment="特征元数据（字段名+权重），非向量值")
    qdrant_vector_id = Column(String(100), nullable=True,
                              comment="Qdrant hr_behavior_patterns collection的向量ID")
    outcome = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    sample_size = Column(Integer, nullable=True)
    org_scope = Column(String(30), nullable=True)
    org_node_id = Column(UUID(as_uuid=True), nullable=True)
    last_trained = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
```

`src/models/hr_knowledge/person_achievement.py`:
```python
"""PersonAchievement — 技能认证记录（技能图谱的可见外衣）"""
import uuid
from sqlalchemy import Column, String, Date, Text, Float, ForeignKey, UniqueConstraint, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class PersonAchievement(Base):
    __tablename__ = "person_achievements"
    __table_args__ = (
        UniqueConstraint("person_id", "skill_node_id",
                         name="uq_person_skill"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    skill_node_id = Column(UUID(as_uuid=True),
                           ForeignKey("skill_nodes.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    achieved_at = Column(Date, nullable=False)
    evidence = Column(Text, nullable=True)
    verified_by = Column(UUID(as_uuid=True), nullable=True)
    trigger_type = Column(String(30), nullable=True, default="manual")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
```

`src/models/hr_knowledge/retention_signal.py`:
```python
"""RetentionSignal — 离职风险预测信号（WF-1每日扫描）"""
import uuid
from sqlalchemy import Column, String, Float, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class RetentionSignal(Base):
    __tablename__ = "retention_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                           nullable=False)
    risk_score = Column(Float, nullable=False, comment="0.0-1.0")
    risk_factors = Column(JSONB, nullable=False, default=dict)
    intervention_status = Column(String(30), nullable=False, default="pending")
    intervention_at = Column(TIMESTAMP(timezone=True), nullable=True)
    computed_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                         nullable=False)
```

`src/models/hr_knowledge/knowledge_capture.py`:
```python
"""KnowledgeCapture — 对话式知识采集记录（WF-4）"""
import uuid
from sqlalchemy import Column, String, Text, Float, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class KnowledgeCapture(Base):
    __tablename__ = "knowledge_captures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    trigger_type = Column(String(30), nullable=True,
                          comment=("exit/monthly_review/incident/onboarding/"
                                   "growth_review/talent_assessment/legacy_import"))
    raw_dialogue = Column(Text, nullable=True)
    context = Column(Text, nullable=True)
    action = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    structured_output = Column(JSONB, nullable=True)
    knowledge_node_id = Column(UUID(as_uuid=True), nullable=True)
    quality_score = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
```

- [ ] **Step 6: Create `src/models/hr_knowledge/__init__.py`**

```python
"""HR Knowledge OS models — 三位一体知识操作系统。"""
from .hr_knowledge_rule import HrKnowledgeRule
from .skill_node import SkillNode
from .behavior_pattern import BehaviorPattern
from .person_achievement import PersonAchievement
from .retention_signal import RetentionSignal
from .knowledge_capture import KnowledgeCapture

__all__ = [
    "HrKnowledgeRule",
    "SkillNode",
    "BehaviorPattern",
    "PersonAchievement",
    "RetentionSignal",
    "KnowledgeCapture",
]
```

- [ ] **Step 7: Register in `src/models/__init__.py`**

Add alongside the z54 imports:
```python
# HR Knowledge OS models (z55)
from .hr_knowledge import (
    HrKnowledgeRule,
    SkillNode,
    BehaviorPattern,
    PersonAchievement,
    RetentionSignal,
    KnowledgeCapture,
)
```

- [ ] **Step 8: Run both model test files**

```bash
python -m pytest tests/test_hr_models_z54.py tests/test_hr_models_z55.py -v
```
Expected: all 15 tests PASS (8 from z54 + 7 from z55)

- [ ] **Step 9: Commit**

```bash
git add apps/api-gateway/src/models/hr_knowledge/ \
        apps/api-gateway/src/models/__init__.py \
        apps/api-gateway/tests/test_hr_models_z55.py
git commit -m "feat(hr): SQLAlchemy models for z55 knowledge OS tables (HrKnowledgeRule/SkillNode/etc)"
```

---

## Chunk 3: Seed Data Service

### Task 5: HR knowledge seed data files

**Files:**
- Create: `apps/api-gateway/src/data/` (new directory)
- Create: `apps/api-gateway/src/data/hr_seed_rules.json`
- Create: `apps/api-gateway/src/data/hr_seed_skills.json`

Background: The seed data provides the "cold start" for the three-layer knowledge OS. Rules should cover turnover/scheduling/standards/training categories. Skills should model a standard chain restaurant career ladder (service staff → team leader → floor manager → store manager).

- [ ] **Step 0: Create the data directory**

```bash
mkdir -p apps/api-gateway/src/data
```

- [ ] **Step 1: Create `src/data/hr_seed_rules.json`**

This file contains the initial 5 representative rules (the full 500+ set will be provided by the business team in a follow-up; this scaffold validates the loader):

```json
[
  {
    "rule_type": "alert",
    "category": "turnover",
    "condition": {"consecutive_late_days": {"gte": 3}, "last_month_performance_pct": {"lte": 60}},
    "action": {"type": "notify_manager", "message": "员工连续迟到3天且上月绩效低于60分，建议安排1对1谈话"},
    "expected_impact": {"retention_lift_pct": 30, "action_cost_yuan": 0},
    "confidence": 0.85,
    "industry_source": "屯象16年餐饮管理经验"
  },
  {
    "rule_type": "alert",
    "category": "turnover",
    "condition": {"days_since_last_training": {"gte": 90}, "tenure_months": {"lte": 6}},
    "action": {"type": "assign_training", "message": "新员工入职6个月内90天未培训，离职风险上升"},
    "expected_impact": {"retention_lift_pct": 20},
    "confidence": 0.75,
    "industry_source": "屯象16年餐饮管理经验"
  },
  {
    "rule_type": "sop",
    "category": "scheduling",
    "condition": {"weekday": "friday", "meal_period": "dinner", "expected_covers": {"gte": 80}},
    "action": {"type": "staffing_recommendation", "min_servers": 4, "min_kitchen": 3},
    "expected_impact": {"service_quality_score_lift": 15},
    "confidence": 0.80,
    "industry_source": "连锁餐饮行业标准"
  },
  {
    "rule_type": "kpi_baseline",
    "category": "standards",
    "condition": {"position": "waiter", "tenure_months": {"gte": 3}},
    "action": {"kpi_targets": {"table_turn_rate": 2.5, "customer_satisfaction": 4.2, "upsell_rate_pct": 15}},
    "confidence": 0.90,
    "industry_source": "连锁餐饮行业标准"
  },
  {
    "rule_type": "best_practice",
    "category": "training",
    "condition": {"new_employee": true, "days_since_hire": {"lte": 7}},
    "action": {"type": "onboarding_checklist", "required_skills": ["food_safety_basics", "pos_system", "service_etiquette"]},
    "expected_impact": {"90_day_retention_lift_pct": 25},
    "confidence": 0.88,
    "industry_source": "屯象种子客户最佳实践"
  }
]
```

- [ ] **Step 2: Create `src/data/hr_seed_skills.json`**

```json
[
  {
    "skill_name": "餐饮服务礼仪",
    "category": "service",
    "description": "标准问候、引座、点餐、上菜、结账全流程礼仪规范",
    "estimated_revenue_lift": 0.0
  },
  {
    "skill_name": "POS系统操作",
    "category": "service",
    "description": "收银系统点餐、改单、退单、打印操作",
    "estimated_revenue_lift": 0.0
  },
  {
    "skill_name": "食品安全基础",
    "category": "compliance",
    "description": "食品卫生法规、个人卫生要求、储存温控规范",
    "estimated_revenue_lift": 0.0
  },
  {
    "skill_name": "酒水知识与推荐",
    "category": "service",
    "description": "酒单讲解、配餐推荐、开瓶服务、醒酒时机",
    "kpi_impact": {"avg_check_per_table_yuan": 35},
    "estimated_revenue_lift": 35.0
  },
  {
    "skill_name": "客诉处理",
    "category": "service",
    "description": "投诉接收、道歉话术、补偿方案、升级判断、事后复盘",
    "kpi_impact": {"customer_satisfaction_score_lift": 0.3},
    "estimated_revenue_lift": 0.0
  },
  {
    "skill_name": "排班基础",
    "category": "management",
    "description": "排班需求预测、轮休安排、假期协调、兼职调配",
    "estimated_revenue_lift": 800.0
  },
  {
    "skill_name": "新员工带教",
    "category": "management",
    "description": "一对一辅导、岗位示范、跟台评估、出师标准",
    "estimated_revenue_lift": 0.0
  },
  {
    "skill_name": "成本意识与控制",
    "category": "management",
    "description": "人力成本率计算、损耗识别、班次成本核算",
    "kpi_impact": {"labor_cost_rate_reduction_pct": 1.5},
    "estimated_revenue_lift": 1500.0
  },
  {
    "skill_name": "数据分析基础",
    "category": "management",
    "description": "营业额趋势、客流分析、毛利率解读、异常识别",
    "estimated_revenue_lift": 0.0
  },
  {
    "skill_name": "供应商沟通",
    "category": "management",
    "description": "订货流程、验收标准、异常退货、价格谈判基础",
    "estimated_revenue_lift": 500.0
  }
]
```

- [ ] **Step 3: Commit seed data**

```bash
git add apps/api-gateway/src/data/hr_seed_rules.json \
        apps/api-gateway/src/data/hr_seed_skills.json
git commit -m "feat(hr): add HR knowledge cold-start seed data (rules + skill nodes)"
```

---

### Task 6: Seed loader service + CLI command

**Files:**
- Create: `apps/api-gateway/src/services/hr/` (new directory)
- Create: `apps/api-gateway/src/services/hr/__init__.py`
- Create: `apps/api-gateway/src/services/hr/seed_service.py`
- Create: `apps/api-gateway/src/cli/` (new directory)
- Create: `apps/api-gateway/src/cli/__init__.py`
- Create: `apps/api-gateway/src/cli/seed_hr_knowledge.py`
- Create: `apps/api-gateway/tests/test_hr_seed_service.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api-gateway/tests/test_hr_seed_service.py`:

```python
"""Tests for HR knowledge seed loader — uses SQLite in-memory for speed."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_load_rules_inserts_correct_count():
    """Loader should insert exactly as many rules as are in the JSON file."""
    from src.services.hr.seed_service import HrSeedService

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    sample_rules = [
        {"rule_type": "alert", "category": "turnover",
         "condition": {}, "action": {}, "confidence": 0.8}
    ] * 3

    with patch.object(HrSeedService, "_load_json",
                      return_value=sample_rules):
        service = HrSeedService(mock_session)
        count = await service.load_rules(skip_if_exists=False)

    assert count == 3
    assert mock_session.execute.call_count == 3


@pytest.mark.asyncio
async def test_load_skills_inserts_correct_count():
    from src.services.hr.seed_service import HrSeedService

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    sample_skills = [
        {"skill_name": f"Skill {i}", "category": "service"}
        for i in range(5)
    ]

    with patch.object(HrSeedService, "_load_json",
                      return_value=sample_skills):
        service = HrSeedService(mock_session)
        count = await service.load_skills(skip_if_exists=False)

    assert count == 5


@pytest.mark.asyncio
async def test_load_rules_skips_when_exists():
    """skip_if_exists=True should not insert if rules already exist."""
    from src.services.hr.seed_service import HrSeedService

    mock_session = AsyncMock()
    # Simulate: COUNT(*) returns 10 (already seeded)
    mock_result = MagicMock()
    mock_result.scalar.return_value = 10
    mock_session.execute = AsyncMock(return_value=mock_result)

    service = HrSeedService(mock_session)
    count = await service.load_rules(skip_if_exists=True)

    assert count == 0  # No inserts performed
```

- [ ] **Step 2: Run test — expect ImportError**

```bash
python -m pytest tests/test_hr_seed_service.py -v 2>&1 | head -5
```
Expected: `ModuleNotFoundError: No module named 'src.services.hr'`

- [ ] **Step 3: Create directories and `src/services/hr/__init__.py`**

```bash
mkdir -p apps/api-gateway/src/services/hr
mkdir -p apps/api-gateway/src/cli
touch apps/api-gateway/src/cli/__init__.py
```

```python
"""HR domain services."""
from .seed_service import HrSeedService

__all__ = ["HrSeedService"]
```

- [ ] **Step 4: Create `src/services/hr/seed_service.py`**

```python
"""HrSeedService — HR知识库冷启动数据加载器

用法（CLI）：
    python -m src.cli.seed_hr_knowledge
"""
import json
import uuid
import logging
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


class HrSeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── public ────────────────────────────────────────────────────────────

    async def load_rules(self, skip_if_exists: bool = True) -> int:
        """Load hr_seed_rules.json into hr_knowledge_rules.

        Returns number of rows inserted (0 if skipped).
        Note: --force (skip_if_exists=False) truncates the table first to avoid
        duplicates, since each insert generates a fresh UUID and ON CONFLICT
        only catches PK collisions.
        """
        if skip_if_exists and await self._rule_count() > 0:
            logger.info("hr_knowledge_rules already seeded, skipping.")
            return 0

        if not skip_if_exists:
            await self._session.execute(
                sa.text("TRUNCATE TABLE hr_knowledge_rules")
            )

        rules = self._load_json("hr_seed_rules.json")
        inserted = 0
        for rule in rules:
            await self._session.execute(
                sa.text(
                    "INSERT INTO hr_knowledge_rules "
                    "(id, rule_type, category, condition, action, "
                    " expected_impact, confidence, industry_source, is_active) "
                    "VALUES (:id, :rule_type, :category, :condition::jsonb, "
                    "        :action::jsonb, :expected_impact::jsonb, "
                    "        :confidence, :industry_source, true) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "rule_type": rule.get("rule_type", "sop"),
                    "category": rule.get("category"),
                    "condition": json.dumps(rule.get("condition", {})),
                    "action": json.dumps(rule.get("action", {})),
                    "expected_impact": json.dumps(rule.get("expected_impact") or {}),
                    "confidence": rule.get("confidence", 0.8),
                    "industry_source": rule.get("industry_source"),
                },
            )
            inserted += 1

        await self._session.commit()
        logger.info("Inserted %d HR knowledge rules.", inserted)
        return inserted

    async def load_skills(self, skip_if_exists: bool = True) -> int:
        """Load hr_seed_skills.json into skill_nodes.

        Returns number of rows inserted (0 if skipped).
        Note: --force truncates first to avoid UUID-collision-safe duplicates.
        """
        if skip_if_exists and await self._skill_count() > 0:
            logger.info("skill_nodes already seeded, skipping.")
            return 0

        if not skip_if_exists:
            await self._session.execute(
                sa.text("TRUNCATE TABLE skill_nodes CASCADE")
            )

        skills = self._load_json("hr_seed_skills.json")
        inserted = 0
        for skill in skills:
            await self._session.execute(
                sa.text(
                    "INSERT INTO skill_nodes "
                    "(id, skill_name, category, description, "
                    " kpi_impact, estimated_revenue_lift) "
                    "VALUES (:id, :skill_name, :category, :description, "
                    "        :kpi_impact::jsonb, :estimated_revenue_lift) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "skill_name": skill["skill_name"],
                    "category": skill.get("category"),
                    "description": skill.get("description"),
                    "kpi_impact": json.dumps(skill.get("kpi_impact") or {}),
                    "estimated_revenue_lift": skill.get("estimated_revenue_lift"),
                },
            )
            inserted += 1

        await self._session.commit()
        logger.info("Inserted %d skill nodes.", inserted)
        return inserted

    # ── private ───────────────────────────────────────────────────────────

    def _load_json(self, filename: str) -> list[dict[str, Any]]:
        path = _DATA_DIR / filename
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    async def _rule_count(self) -> int:
        result = await self._session.execute(
            sa.text("SELECT COUNT(*) FROM hr_knowledge_rules")
        )
        return result.scalar() or 0

    async def _skill_count(self) -> int:
        result = await self._session.execute(
            sa.text("SELECT COUNT(*) FROM skill_nodes")
        )
        return result.scalar() or 0
```

- [ ] **Step 5: Create the CLI entry point**

Create `apps/api-gateway/src/cli/seed_hr_knowledge.py`:

```python
"""CLI: 加载HR知识库种子数据

运行方式：
    cd apps/api-gateway
    python -m src.cli.seed_hr_knowledge
    python -m src.cli.seed_hr_knowledge --force   # 强制重新导入（清空后重载）
"""
import asyncio
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _run(force: bool) -> None:
    from src.core.database import AsyncSessionLocal
    from src.services.hr.seed_service import HrSeedService

    async with AsyncSessionLocal() as session:
        service = HrSeedService(session)
        skip = not force

        rules_count = await service.load_rules(skip_if_exists=skip)
        skills_count = await service.load_skills(skip_if_exists=skip)

        logger.info(
            "Seed complete. Rules inserted: %d, Skills inserted: %d",
            rules_count,
            skills_count,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Load HR knowledge seed data")
    parser.add_argument("--force", action="store_true",
                        help="Re-insert even if data already exists")
    args = parser.parse_args()
    asyncio.run(_run(force=args.force))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run seed service tests — expect PASS**

```bash
python -m pytest tests/test_hr_seed_service.py -v
```
Expected: all 3 tests PASS

- [ ] **Step 7: Run seed CLI against local DB to verify end-to-end**

```bash
python -m src.cli.seed_hr_knowledge
```
Expected output:
```
INFO Inserted 5 HR knowledge rules.
INFO Inserted 10 skill nodes.
INFO Seed complete. Rules inserted: 5, Skills inserted: 10
```

Running it a second time (skip_if_exists=True):
```bash
python -m src.cli.seed_hr_knowledge
```
Expected:
```
INFO hr_knowledge_rules already seeded, skipping.
INFO skill_nodes already seeded, skipping.
INFO Seed complete. Rules inserted: 0, Skills inserted: 0
```

- [ ] **Step 8: Commit**

```bash
git add apps/api-gateway/src/services/hr/ \
        apps/api-gateway/src/cli/seed_hr_knowledge.py \
        apps/api-gateway/tests/test_hr_seed_service.py
git commit -m "feat(hr): HrSeedService + seed_hr_knowledge CLI for knowledge cold start"
```

---

## Chunk 4: Migration Integration Test + TS Build Check

### Task 7: Migration integration test (z54 + z55)

**Files:**
- Create: `apps/api-gateway/tests/test_z54_z55_migrations.py`

Background: Look at `tests/test_alembic_migrations.py` to understand the existing migration test pattern. Tests run `alembic upgrade` and `alembic downgrade` as subprocesses and check return codes.

- [ ] **Step 1: Write the migration integration test**

```python
"""Integration tests for z54 + z55 HR migrations.

Requires a real PostgreSQL database (zhilian_test).
Run with: pytest tests/test_z54_z55_migrations.py -v -m integration
"""
import pytest
from pathlib import Path
import subprocess
import sys
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_ENV = {
    **os.environ,
    "APP_ENV": "test",
    "DATABASE_URL": os.environ.get(
        "DATABASE_URL",
        "postgresql://test:test@localhost:5432/zhilian_test",
    ),
    "REDIS_URL": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret",
    "JWT_SECRET": "test-jwt",
}


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=_ENV,
        capture_output=True,
        text=True,
        check=False,
    )


def _psql(sql: str) -> subprocess.CompletedProcess:
    """Run a SQL statement against the test DB via psql."""
    db_url = _ENV.get("DATABASE_URL",
                      "postgresql://test:test@localhost:5432/zhilian_test")
    return subprocess.run(
        ["psql", db_url, "-c", sql],
        capture_output=True, text=True, env=_ENV,
    )


@pytest.mark.integration
def test_z54_upgrade_creates_persons_table():
    result = _alembic("upgrade", "z54_hr_core_tables")
    assert result.returncode == 0, result.stderr
    check = _psql("SELECT 1 FROM persons LIMIT 0;")
    assert check.returncode == 0, "persons table not found after z54 upgrade"


@pytest.mark.integration
def test_z55_upgrade_creates_knowledge_tables():
    result = _alembic("upgrade", "z55_hr_knowledge_tables")
    assert result.returncode == 0, result.stderr
    check = _psql("SELECT 1 FROM hr_knowledge_rules LIMIT 0;")
    assert check.returncode == 0, "hr_knowledge_rules table not found after z55 upgrade"


@pytest.mark.integration
def test_z55_downgrade_removes_knowledge_tables():
    result = _alembic("downgrade", "z54_hr_core_tables")
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_z54_downgrade_removes_persons_table():
    result = _alembic("downgrade", "z53_org_scope_propagation")
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_full_round_trip():
    """Upgrade z54→z55 then downgrade z55→z54→z53 — all must succeed."""
    for direction, target in [
        ("upgrade", "z54_hr_core_tables"),
        ("upgrade", "z55_hr_knowledge_tables"),
        ("downgrade", "z54_hr_core_tables"),
        ("downgrade", "z53_org_scope_propagation"),
        # Restore
        ("upgrade", "z54_hr_core_tables"),
        ("upgrade", "z55_hr_knowledge_tables"),
    ]:
        r = _alembic(direction, target)
        assert r.returncode == 0, f"alembic {direction} {target} failed:\n{r.stderr}"
```

- [ ] **Step 2: Run unit tests (non-integration) to confirm nothing is broken**

```bash
cd apps/api-gateway
python -m pytest tests/test_hr_models_z54.py tests/test_hr_models_z55.py \
                 tests/test_hr_seed_service.py -v
```
Expected: all tests PASS

- [ ] **Step 3: Run TypeScript build check on frontend (no changes expected)**

```bash
cd apps/web
npx tsc --noEmit --skipLibCheck 2>&1 | tail -5
```
Expected: zero TypeScript errors (M1 touches only backend)

- [ ] **Step 4: Commit test file**

```bash
git add apps/api-gateway/tests/test_z54_z55_migrations.py
git commit -m "test(hr): add migration integration tests for z54 + z55"
```

---

## Final Validation

- [ ] **Run full unit test suite to check no regressions**

```bash
cd apps/api-gateway
python -m pytest tests/ -v --ignore=tests/integration \
    -k "not integration" --tb=short 2>&1 | tail -20
```
Expected: all pre-existing tests still PASS, new HR tests PASS.

- [ ] **Verify both migrations in migration chain**

```bash
python -m alembic history | grep -E "z54|z55"
```
Expected:
```
z55_hr_knowledge_tables -> (head), ...
z54_hr_core_tables -> z55_hr_knowledge_tables, ...
```

- [ ] **Final commit with summary**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(hr): M1 complete — z54/z55 migrations, 12 new models, seed service

新增11张HR表（6个核心人员表 + 6个知识OS表）
- z54: persons / employment_assignments / employment_contracts
       attendance_rules / kpi_templates / employee_id_map
- z55: hr_knowledge_rules / skill_nodes / behavior_patterns
       person_achievements / retention_signals / knowledge_captures
+ HrSeedService + CLI cold-start loader
+ 5条行业规则 + 10个技能节点种子数据
+ 18个模型单元测试 + 5个迁移集成测试

下一步：M2 — 数据迁移脚本 + 双写模式 + HRAgent v1（B级）

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```
