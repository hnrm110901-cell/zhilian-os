# HR M4 — Contract清理 + 前端全面接入 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 HR Foundation 最终阶段：(A) z57 Alembic Contract迁移（删旧列+加NOT NULL+删桥接表）；(B) 增强SM HR BFF端点并新增HQ HR BFF端点；(C) 将 `/sm/hr` 替换为真实人力首页；(D) 新增 `/hq/hr` 总部人力大盘页。

**Architecture:** 四个顺序Chunk，互相解耦。Chunk A 纯DB迁移，无业务逻辑变更。Chunk B 只改 `apps/api-gateway/src/api/hr.py`，用现有 Service 层组合。Chunk C/D 为前端新页面，调用 Chunk B 的 BFF 端点；后端必须先完成才能前端联调。

**Tech Stack:** Python 3.11, Alembic, FastAPI, SQLAlchemy 2.0 async, pytest-asyncio, React 19, TypeScript, CSS Modules, ZCard/ZKpi/ZBadge/ZSkeleton/ZEmpty 设计系统

**Prerequisite:** M3 已合并 main（z56 已应用，四张表已有 assignment_id UUID NULL 列，StaffingService/RetentionMLService/SkillGapService 均已实现）

**Spec reference:** `docs/superpowers/specs/2026-03-17-hr-foundation-redesign.md` §3.2 M4

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| CREATE | `apps/api-gateway/alembic/versions/z57_contract_drop_old_fk_columns.py` | NOT NULL + 删旧列 + 删 employee_id_map |
| CREATE | `apps/api-gateway/tests/test_z57_contract_migration.py` | 验证z57结构和幂等性 |
| MODIFY | `apps/api-gateway/src/api/hr.py:217-260` | SM BFF 添加 staffing_today + pending_actions_count；新增 HQ BFF端点 |
| CREATE | `apps/api-gateway/tests/test_hr_bff_endpoints.py` | SM/HQ BFF 端点单元测试 |
| MODIFY | `apps/web/src/pages/sm/HRQuick.tsx` | 替换 stub → 真实 SM HR 首页 |
| CREATE | `apps/web/src/pages/sm/HRQuick.module.css` | 店长 HR 首页样式 |
| CREATE | `apps/web/src/pages/hq/HR.tsx` | 总部人力大盘页 |
| CREATE | `apps/web/src/pages/hq/HR.module.css` | 总部人力大盘样式 |
| MODIFY | `apps/web/src/App.tsx:247-264` | 注册 HQ HR 路由 `/hq/hr` |

---

## Chunk A: z57 Contract迁移

**Goal:** 完成 Expand→Migrate→**Contract** 的最后阶段。为4张表的 `assignment_id` 列加 NOT NULL 约束，删除旧 `employee_id`/`holder_employee_id`/`owner_employee_id` 列，最后删除桥接表 `employee_id_map`。

**背景知识：**
- z56（M3）已为4张表添加了 `assignment_id UUID NULL` 并通过 `employee_id_map` 回填
- z57 确认数据完整后收紧约束
- 旧列名参照：`compliance_licenses.holder_employee_id`, `customer_ownerships.owner_employee_id`, `shifts.employee_id`, `employee_metric_records.employee_id`
- 桥接表 `employee_id_map` 只在迁移期使用，M4 可以删除

### Task A1: z57 测试先行

**Files:**
- Create: `apps/api-gateway/tests/test_z57_contract_migration.py`

- [ ] **A1.1** 创建测试文件：

```python
"""Tests for z57 contract migration.

CI has no PostgreSQL — we mock conn and verify SQL logic via string inspection.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

TARGET_TABLES = [
    ("compliance_licenses",      "holder_employee_id"),
    ("customer_ownerships",      "owner_employee_id"),
    ("shifts",                   "employee_id"),
    ("employee_metric_records",  "employee_id"),
]


def test_revision_metadata():
    """Migration has correct revision and down_revision."""
    from alembic.versions.z57_contract_drop_old_fk_columns import (
        revision,
        down_revision,
    )
    assert revision == "z57_contract_drop_old_fk_columns"
    assert down_revision == "z56_fk_migration_to_assignment_id"


def test_upgrade_sets_not_null_for_all_tables():
    """upgrade() emits ALTER TABLE ... ALTER COLUMN assignment_id SET NOT NULL for all 4 tables."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        # No NULL rows exist → safe to proceed
        conn.execute.return_value.scalar.return_value = 0
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        upgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    not_null_tables = [s for s in sqls if "SET NOT NULL" in s]
    assert len(not_null_tables) == len(TARGET_TABLES), (
        f"Expected {len(TARGET_TABLES)} SET NOT NULL statements, got {len(not_null_tables)}"
    )
    for table, _ in TARGET_TABLES:
        found = any(table in s and "SET NOT NULL" in s for s in sqls)
        assert found, f"Missing SET NOT NULL for {table}"


def test_upgrade_drops_old_columns():
    """upgrade() drops the legacy employee_id columns from all 4 tables."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 0
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        upgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    drop_sqls = [s for s in sqls if "DROP COLUMN" in s]
    assert len(drop_sqls) >= len(TARGET_TABLES), (
        f"Expected at least {len(TARGET_TABLES)} DROP COLUMN, got {len(drop_sqls)}"
    )
    for table, old_col in TARGET_TABLES:
        found = any(table in s and old_col in s and "DROP COLUMN" in s for s in sqls)
        assert found, f"Missing DROP COLUMN {old_col} on {table}"


def test_upgrade_drops_employee_id_map():
    """upgrade() drops the employee_id_map bridge table."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 0
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        upgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert any("employee_id_map" in s and "DROP TABLE" in s for s in sqls), (
        "Missing DROP TABLE employee_id_map"
    )


def test_upgrade_aborts_if_null_rows_remain():
    """upgrade() raises RuntimeError when any assignment_id row is still NULL."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        # First table returns 2 NULL rows → abort
        conn.execute.return_value.scalar.return_value = 2
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        with pytest.raises(RuntimeError, match="NULL assignment_id"):
            upgrade()


def test_downgrade_restores_old_columns():
    """downgrade() adds back the legacy columns (nullable) and employee_id_map."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import downgrade
        downgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    # employee_id_map recreated
    assert any("employee_id_map" in s and "CREATE TABLE" in s for s in sqls), (
        "downgrade() did not recreate employee_id_map"
    )
```

- [ ] **A1.2** 运行测试，确认全部 FAIL（模块尚不存在）：

```bash
cd apps/api-gateway
python -m pytest tests/test_z57_contract_migration.py -v 2>&1 | head -30
```

Expected：`ModuleNotFoundError` 或 `ImportError`（z57 migration 文件不存在）

### Task A2: 实现 z57 Migration

**Files:**
- Create: `apps/api-gateway/alembic/versions/z57_contract_drop_old_fk_columns.py`

- [ ] **A2.1** 创建迁移文件：

```python
"""z57 — Contract phase: add NOT NULL, drop old employee_id cols, drop employee_id_map.

Expand → Migrate → Contract — this is the Contract step.

Pre-requisite: z56 has already added assignment_id UUID NULL and backfilled via
employee_id_map. This migration:
  1. Validates zero NULL assignment_id rows remain in all 4 tables.
  2. Adds NOT NULL constraint to assignment_id in all 4 tables.
  3. Drops the legacy employee_id / holder_employee_id / owner_employee_id columns.
  4. Drops the employee_id_map bridge table (no longer needed).
"""
import sqlalchemy as sa
from alembic import op

revision = "z57_contract_drop_old_fk_columns"
down_revision = "z56_fk_migration_to_assignment_id"
branch_labels = None
depends_on = None

# (table_name, legacy_column_name)
# Table names are hardcoded internal constants — not user input.
# f-string interpolation here is safe (DDL table/column names cannot be parameterized).
_TABLES = [
    ("compliance_licenses",     "holder_employee_id"),
    ("customer_ownerships",     "owner_employee_id"),
    ("shifts",                  "employee_id"),
    ("employee_metric_records", "employee_id"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Validate — abort if any NULL assignment_id rows remain
    for table, _ in _TABLES:
        null_count = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE assignment_id IS NULL")
        ).scalar()
        if null_count:
            raise RuntimeError(
                f"NULL assignment_id found in {table} ({null_count} rows). "
                "Run z56 backfill manually before re-running this migration."
            )

    # Step 2: Set NOT NULL constraint on assignment_id
    for table, _ in _TABLES:
        conn.execute(
            sa.text(
                f"ALTER TABLE {table} "
                f"ALTER COLUMN assignment_id SET NOT NULL"
            )
        )

    # Step 3: Drop old legacy employee_id columns
    for table, legacy_col in _TABLES:
        conn.execute(
            sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {legacy_col}")
        )

    # Step 4: Drop employee_id_map bridge table (no longer needed post-Contract)
    conn.execute(
        sa.text("DROP TABLE IF EXISTS employee_id_map CASCADE")
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Recreate employee_id_map bridge table
    conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS employee_id_map ("
            "  legacy_employee_id VARCHAR(50) PRIMARY KEY, "
            "  person_id          UUID NOT NULL, "
            "  assignment_id      UUID NOT NULL"
            ")"
        )
    )

    # Restore old columns (nullable — data is gone, DBA must re-backfill)
    restore_map = [
        ("compliance_licenses",     "holder_employee_id", "VARCHAR(50)"),
        ("customer_ownerships",     "owner_employee_id",  "VARCHAR(50)"),
        ("shifts",                  "employee_id",        "VARCHAR(50)"),
        ("employee_metric_records", "employee_id",        "VARCHAR(50)"),
    ]
    for table, col, col_type in restore_map:
        conn.execute(
            sa.text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type} NULL")
        )

    # Remove NOT NULL from assignment_id
    for table, _ in _TABLES:
        conn.execute(
            sa.text(
                f"ALTER TABLE {table} "
                f"ALTER COLUMN assignment_id DROP NOT NULL"
            )
        )
```

- [ ] **A2.2** 运行测试，确认全部 PASS：

```bash
cd apps/api-gateway
python -m pytest tests/test_z57_contract_migration.py -v
```

Expected：`6 passed`

- [ ] **A2.3** Commit：

```bash
git add apps/api-gateway/alembic/versions/z57_contract_drop_old_fk_columns.py \
        apps/api-gateway/tests/test_z57_contract_migration.py
git commit -m "feat(hr): M4 Chunk A — z57 Contract migration drops old FK columns + employee_id_map"
```

---

## Chunk B: BFF 端点增强

**Goal:** (1) 增强现有 `GET /api/v1/hr/bff/sm/{store_id}` 端点，添加 `staffing_today` 和 `pending_actions_count`；(2) 新增 `GET /api/v1/hr/bff/hq/{org_node_id}` 端点，返回总部 HR 大盘数据。

**背景：**
- 现有 `bff_sm_hr()` 在 `apps/api-gateway/src/api/hr.py:217-260`，返回 `{store_id, retention, skill_gaps}`
- `StaffingService` 已实现（M3），入口：`StaffingService(session).diagnose_staffing(store_id, date.today())`
- `SkillGapService` 已实现（M2），入口：`SkillGapService(session).analyze_store(store_id)` （注意：需确认实际方法名）
- `RetentionRiskService` 已实现（M2）

### Task B1: BFF 测试先行

**Files:**
- Create: `apps/api-gateway/tests/test_hr_bff_endpoints.py`

先确认 SkillGapService 方法名：

```bash
cd apps/api-gateway
grep -n "async def " src/services/hr/skill_gap_service.py
grep -n "async def " src/services/hr/staffing_service.py | head -5
```

- [ ] **B1.1** 创建 BFF 测试文件：

```python
"""Tests for HR BFF endpoints (SM + HQ).

All DB/service calls are mocked — no real PostgreSQL needed.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.main import app
from src.core.database import get_db
from src.core.dependencies import get_current_active_user


def make_mock_user():
    user = MagicMock()
    user.id = "user-1"
    user.store_id = "S001"
    return user


def make_mock_session():
    return AsyncMock()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: make_mock_session()
    app.dependency_overrides[get_current_active_user] = lambda: make_mock_user()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSmHRBff:
    """SM HR BFF endpoint tests."""

    def test_sm_bff_returns_required_fields(self, client):
        """GET /api/v1/hr/bff/sm/{store_id} returns all required top-level fields."""
        # Patch at source module (lazy import inside function body looks up name there)
        with patch("src.agents.hr_agent.HRAgentV1") as MockAgent, \
             patch("src.services.hr.staffing_service.StaffingService") as MockStaffing:
            # Mock HRAgent diagnose
            mock_diag = MagicMock()
            mock_diag.high_risk_persons = [{"person_id": "p1", "risk_score": 0.9}]
            mock_diag.recommendations = [{"action": "1-on-1面谈"}]
            MockAgent.return_value.diagnose = AsyncMock(return_value=mock_diag)

            # Mock StaffingService
            mock_staffing = AsyncMock()
            mock_staffing.diagnose_staffing.return_value = {
                "peak_hours": [12, 13],
                "understaffed_hours": [12],
                "overstaffed_hours": [],
                "estimated_savings_yuan": 0.0,
                "confidence": 0.75,
                "analysis_date": "2026-03-18",
                "fused_demand": {},
                "total_active_staff": 8,
                "recommended_staff": 9,
                "recommendation_text": "12点需补1人",
            }
            MockStaffing.return_value = mock_staffing

            resp = client.get("/api/v1/hr/bff/sm/S001")

        assert resp.status_code == 200
        body = resp.json()
        assert "store_id" in body
        assert "retention" in body
        assert "staffing_today" in body
        assert "skill_gaps" in body
        assert "pending_actions_count" in body

    def test_sm_bff_partial_failure_returns_null_section(self, client):
        """If staffing service raises, staffing_today is null and other sections still return."""
        with patch("src.agents.hr_agent.HRAgentV1") as MockAgent, \
             patch("src.services.hr.staffing_service.StaffingService") as MockStaffing:
            mock_diag = MagicMock()
            mock_diag.high_risk_persons = []
            mock_diag.recommendations = []
            MockAgent.return_value.diagnose = AsyncMock(return_value=mock_diag)

            # StaffingService raises
            mock_staffing = AsyncMock()
            mock_staffing.diagnose_staffing.side_effect = Exception("DB unavailable")
            MockStaffing.return_value = mock_staffing

            resp = client.get("/api/v1/hr/bff/sm/S001")

        assert resp.status_code == 200
        body = resp.json()
        assert body["staffing_today"] is None
        assert "retention" in body  # Other sections still present


class TestHqHRBff:
    """HQ HR BFF endpoint tests."""

    def test_hq_bff_returns_required_fields(self, client):
        """GET /api/v1/hr/bff/hq/{org_node_id} returns all required top-level fields."""
        mock_session = make_mock_session()
        # Mock DB queries for headcount, heatmap, knowledge health
        mock_session.execute.return_value.scalar.return_value = 42
        mock_session.execute.return_value.fetchall.return_value = []

        app.dependency_overrides[get_db] = lambda: mock_session

        resp = client.get("/api/v1/hr/bff/hq/org-node-1")

        assert resp.status_code == 200
        body = resp.json()
        assert "org_node_id" in body
        assert "as_of" in body
        assert "headcount" in body
        assert "turnover_heatmap" in body
        assert "knowledge_health" in body

    def test_hq_bff_partial_failure_returns_null_section(self, client):
        """HQ BFF handles DB error gracefully — null per section."""
        mock_session = make_mock_session()
        mock_session.execute.side_effect = Exception("DB error")
        app.dependency_overrides[get_db] = lambda: mock_session

        resp = client.get("/api/v1/hr/bff/hq/org-node-1")

        assert resp.status_code == 200
        body = resp.json()
        assert "org_node_id" in body  # response shape always present
        assert body.get("headcount") is None  # DB error → null section
```

- [ ] **B1.2** 运行测试，确认 FAIL（`staffing_today` 和 HQ 端点不存在）：

```bash
cd apps/api-gateway
python -m pytest tests/test_hr_bff_endpoints.py -v 2>&1 | tail -20
```

Expected：FAIL 或 AssertionError（响应缺少 `staffing_today`/HQ endpoint 404）

### Task B2: 实现 BFF 增强

**Files:**
- Modify: `apps/api-gateway/src/api/hr.py:217-260` (bff_sm_hr) 和文件末尾（新增 HQ BFF）

- [ ] **B2.1** 替换 `bff_sm_hr` 函数（hr.py 第217-260行）并新增 HQ BFF。在 hr.py 顶部 import 区增加：

```python
from datetime import date
```

（如果已有 `from datetime import date` 则跳过）

- [ ] **B2.2** 替换 hr.py 中 `bff_sm_hr` 函数（完整替换 lines 217-260）：

```python
@router.get("/bff/sm/{store_id}")
async def bff_sm_hr(
    store_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """BFF首屏: 店长HR视角聚合数据.

    Returns retention risks + staffing_today + skill_gaps + pending_actions_count.
    Partial failure → null per section, never blocks entire response.
    """
    from src.agents.hr_agent import HRAgentV1
    from src.services.hr.staffing_service import StaffingService

    agent = HRAgentV1()

    # Retention risk section
    retention = None
    try:
        diag = await agent.diagnose("retention_risk", store_id=store_id, session=session)
        retention = {
            "high_risk_count": len(diag.high_risk_persons),
            "persons": diag.high_risk_persons[:5],
            "recommendations": diag.recommendations[:3],
        }
    except Exception as exc:
        logger.warning("bff_sm_hr.retention_failed", store_id=store_id, error=str(exc))

    # Staffing today section (WF-2)
    staffing_today = None
    try:
        svc = StaffingService(session)
        staffing_today = await svc.diagnose_staffing(store_id, date.today())
    except Exception as exc:
        logger.warning("bff_sm_hr.staffing_failed", store_id=store_id, error=str(exc))

    # Skill gap section
    skill_gaps = None
    try:
        diag = await agent.diagnose("skill_gaps", store_id=store_id, session=session)
        skill_gaps = {
            "total_potential_yuan": sum(
                r.get("expected_yuan", 0) for r in diag.recommendations
            ),
            "top_recommendations": diag.recommendations[:5],
        }
    except Exception as exc:
        logger.warning("bff_sm_hr.skill_gaps_failed", store_id=store_id, error=str(exc))

    # Pending actions count (retention signals awaiting intervention)
    pending_actions_count = 0
    try:
        result = await session.execute(
            sa.text(
                "SELECT COUNT(*) FROM retention_signals rs "
                "JOIN employment_assignments ea ON ea.id = rs.assignment_id "
                "JOIN stores s ON s.org_node_id = ea.org_node_id "
                "WHERE s.id = :store_id "
                "AND rs.intervention_status = 'pending' "
                "AND rs.risk_score >= 0.70"
            ),
            {"store_id": store_id},
        )
        pending_actions_count = result.scalar() or 0
    except Exception as exc:
        logger.warning("bff_sm_hr.pending_count_failed", store_id=store_id, error=str(exc))

    return {
        "store_id": store_id,
        "as_of": date.today().isoformat(),
        "retention": retention,
        "staffing_today": staffing_today,
        "skill_gaps": skill_gaps,
        "pending_actions_count": pending_actions_count,
    }
```

- [ ] **B2.3** 在 hr.py 文件末尾（`bff_sm_hr` 之后）新增 HQ BFF 端点：

```python
@router.get("/bff/hq/{org_node_id}")
async def bff_hq_hr(
    org_node_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """BFF首屏: 总部HR大盘聚合数据.

    Returns org_headcount + turnover_heatmap + knowledge_health.
    NOTE: talent_pipeline intentionally deferred to M5 (requires TalentPipelineService
    which depends on job_standard assignment coverage data not yet tracked).
    Partial failure → null per section.
    """
    # Headcount: active assignments under this org node and its children
    headcount = None
    try:
        result = await session.execute(
            sa.text(
                "SELECT COUNT(*) FROM employment_assignments ea "
                "JOIN org_nodes n ON n.id = ea.org_node_id "
                "WHERE ea.status = 'active' "
                "AND (n.id = :org_node_id OR n.path LIKE :path_prefix)"
            ),
            {
                "org_node_id": org_node_id,
                "path_prefix": f"{org_node_id}.%",
            },
        )
        headcount = {"total_active": result.scalar() or 0}
    except Exception as exc:
        logger.warning("bff_hq_hr.headcount_failed", org_node_id=org_node_id, error=str(exc))

    # Turnover heatmap: top 5 stores by average risk_score
    turnover_heatmap = None
    try:
        result = await session.execute(
            sa.text(
                "SELECT s.id AS store_id, s.name AS store_name, "
                "       AVG(rs.risk_score) AS avg_risk, COUNT(rs.id) AS signal_count "
                "FROM retention_signals rs "
                "JOIN employment_assignments ea ON ea.id = rs.assignment_id "
                "JOIN org_nodes n ON n.id = ea.org_node_id "
                "JOIN stores s ON s.org_node_id = n.id "
                "WHERE rs.computed_at >= NOW() - INTERVAL '30 days' "
                "AND (n.id = :org_node_id OR n.path LIKE :path_prefix) "
                "GROUP BY s.id, s.name "
                "ORDER BY avg_risk DESC "
                "LIMIT 5"
            ),
            {
                "org_node_id": org_node_id,
                "path_prefix": f"{org_node_id}.%",
            },
        )
        rows = result.fetchall()
        turnover_heatmap = [
            {
                "store_id": str(r.store_id),
                "store_name": r.store_name,
                "avg_risk": round(float(r.avg_risk), 3),
                "signal_count": r.signal_count,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("bff_hq_hr.heatmap_failed", org_node_id=org_node_id, error=str(exc))

    # Knowledge health: active rules + skill nodes count
    knowledge_health = None
    try:
        rules_result = await session.execute(
            sa.text("SELECT COUNT(*) FROM hr_knowledge_rules WHERE is_active = TRUE")
        )
        skills_result = await session.execute(
            sa.text("SELECT COUNT(*) FROM skill_nodes")
        )
        knowledge_health = {
            "active_rules": rules_result.scalar() or 0,
            "skill_nodes": skills_result.scalar() or 0,
        }
    except Exception as exc:
        logger.warning("bff_hq_hr.knowledge_failed", org_node_id=org_node_id, error=str(exc))

    return {
        "org_node_id": org_node_id,
        "as_of": date.today().isoformat(),
        "headcount": headcount,
        "turnover_heatmap": turnover_heatmap,
        "knowledge_health": knowledge_health,
    }
```

- [ ] **B2.4** 运行测试，确认 PASS：

```bash
cd apps/api-gateway
python -m pytest tests/test_hr_bff_endpoints.py -v
```

Expected：`4 passed`（2 SM + 2 HQ tests）

- [ ] **B2.5** Commit：

```bash
git add apps/api-gateway/src/api/hr.py \
        apps/api-gateway/tests/test_hr_bff_endpoints.py
git commit -m "feat(hr): M4 Chunk B — SM BFF adds staffing_today + HQ HR BFF endpoint"
```

---

## Chunk C: SM HR 前端首页

**Goal:** 将 `apps/web/src/pages/sm/HRQuick.tsx`（目前是 ZEmpty stub）替换为真实的店长HR首页，调用 `GET /api/v1/hr/bff/sm/{store_id}` 展示：留人风险预警卡、今日排班健康度、技能成长建议。

**设计参考：**
- 参考 `apps/web/src/pages/sm/Workforce.tsx`（组件用法和样式模式）
- 设计系统：ZCard, ZKpi, ZBadge, ZSkeleton, ZEmpty, ZButton
- CSS Modules（camelCase类名）
- `const STORE_ID = localStorage.getItem('store_id') || 'S001'`
- `apiClient.get(...)` 而非 axios/fetch
- 品牌色 `var(--accent)` = `#FF6B2C`

### Task C1: SM HR 首页

**Files:**
- Modify: `apps/web/src/pages/sm/HRQuick.tsx`
- Create: `apps/web/src/pages/sm/HRQuick.module.css`

- [ ] **C1.1** 创建 CSS module 文件：

```css
/* apps/web/src/pages/sm/HRQuick.module.css */
.page {
  padding: 16px;
  background: var(--bg-primary);
  min-height: 100vh;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.headerTitle {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.pendingBadge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.section {
  margin-bottom: 16px;
}

.sectionTitle {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 10px;
  padding-left: 4px;
}

.kpiRow {
  display: flex;
  gap: 12px;
}

.riskList {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.riskItem {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-light);
}

.riskName {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.riskScore {
  font-size: 13px;
  color: var(--text-secondary);
}

.staffingRow {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.peakHour {
  padding: 4px 10px;
  background: var(--bg-secondary);
  border-radius: 12px;
  font-size: 13px;
  color: var(--text-primary);
}

.skillList {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skillItem {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-light);
}

.skillName {
  font-size: 14px;
  color: var(--text-primary);
}

.skillYuan {
  font-size: 13px;
  color: var(--accent);
  font-weight: 600;
}

.emptyHint {
  padding: 16px 0;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.peakSection {
  margin-top: 12px;
}

.staffingNote {
  margin-top: 10px;
  font-size: 13px;
  color: var(--text-secondary);
}
```

- [ ] **C1.2** 替换 `HRQuick.tsx`（完整文件）：

```tsx
/**
 * 店长 HR 首页
 * 路由：/sm/hr
 * 数据：GET /api/v1/hr/bff/sm/{store_id}
 *
 * 展示：留人风险预警 | 今日排班健康 | 技能成长建议
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './HRQuick.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';

interface RiskPerson {
  person_id: string;
  name?: string;
  risk_score: number;
  risk_level?: string;
}

interface SkillRec {
  skill_name?: string;
  expected_yuan?: number;
  action?: string;
}

interface StaffingToday {
  peak_hours: number[];
  understaffed_hours: number[];
  overstaffed_hours: number[];
  estimated_savings_yuan: number;
  confidence: number;
  total_active_staff?: number;
  recommended_staff?: number;
  recommendation_text?: string;
}

interface BffData {
  store_id: string;
  as_of: string;
  pending_actions_count: number;
  retention: {
    high_risk_count: number;
    persons: RiskPerson[];
    recommendations: { action?: string }[];
  } | null;
  staffing_today: StaffingToday | null;
  skill_gaps: {
    total_potential_yuan: number;
    top_recommendations: SkillRec[];
  } | null;
}

function riskBadgeType(score: number): 'critical' | 'warning' | 'info' {
  if (score >= 0.7) return 'critical';
  if (score >= 0.5) return 'warning';
  return 'info';
}

export default function HRQuick() {
  const [data, setData] = useState<BffData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/bff/sm/${STORE_ID}`);
      setData(resp);
    } catch (e) {
      handleApiError(e, '人力数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className={styles.page}>
        <ZSkeleton rows={6} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className={styles.page}>
        <ZEmpty title="暂无数据" description="人力数据加载失败，请稍后重试" />
      </div>
    );
  }

  const { retention, staffing_today, skill_gaps, pending_actions_count } = data;

  return (
    <div className={styles.page}>
      {/* 标题栏 */}
      <div className={styles.header}>
        <span className={styles.headerTitle}>人力健康看板</span>
        {pending_actions_count > 0 && (
          <div className={styles.pendingBadge}>
            <ZBadge type="critical" text={`${pending_actions_count} 待处理`} />
          </div>
        )}
      </div>

      {/* 留人风险预警 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>🚨 留人风险预警</div>
        <ZCard>
          {retention ? (
            <>
              <div className={styles.kpiRow}>
                <ZKpi
                  label="高风险人员"
                  value={retention.high_risk_count}
                  unit="人"
                  status={retention.high_risk_count > 0 ? 'warning' : 'good'}
                />
              </div>
              {retention.persons.length > 0 ? (
                <div className={styles.riskList}>
                  {retention.persons.map((p) => (
                    <div key={p.person_id} className={styles.riskItem}>
                      <span className={styles.riskName}>
                        {p.name || `员工 ${p.person_id.slice(0, 8)}`}
                      </span>
                      <ZBadge
                        type={riskBadgeType(p.risk_score)}
                        text={`风险 ${Math.round(p.risk_score * 100)}%`}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className={styles.emptyHint}>当前无高风险员工 ✓</div>
              )}
            </>
          ) : (
            <ZEmpty title="风险数据暂不可用" />
          )}
        </ZCard>
      </div>

      {/* 今日排班健康 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>📅 今日排班健康</div>
        <ZCard>
          {staffing_today ? (
            <>
              <div className={styles.kpiRow}>
                <ZKpi
                  label="在班人数"
                  value={staffing_today.total_active_staff ?? '—'}
                  unit="人"
                />
                <ZKpi
                  label="建议人数"
                  value={staffing_today.recommended_staff ?? '—'}
                  unit="人"
                  status={
                    staffing_today.understaffed_hours.length > 0 ? 'warning' : 'good'
                  }
                />
                {staffing_today.estimated_savings_yuan > 0 && (
                  <ZKpi
                    label="可节省"
                    value={`¥${staffing_today.estimated_savings_yuan.toFixed(0)}`}
                    status="good"
                  />
                )}
              </div>
              {staffing_today.peak_hours.length > 0 && (
                <div className={styles.peakSection}>
                  <div className={styles.sectionTitle}>高峰时段</div>
                  <div className={styles.staffingRow}>
                    {staffing_today.peak_hours.map((h) => (
                      <span key={h} className={styles.peakHour}>{h}:00</span>
                    ))}
                  </div>
                </div>
              )}
              {staffing_today.recommendation_text && (
                <div className={styles.staffingNote}>
                  {staffing_today.recommendation_text}
                </div>
              )}
            </>
          ) : (
            <ZEmpty title="排班数据暂不可用" />
          )}
        </ZCard>
      </div>

      {/* 技能成长建议 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>🎓 技能成长建议</div>
        <ZCard>
          {skill_gaps ? (
            <>
              <div className={styles.kpiRow}>
                <ZKpi
                  label="潜在收入提升"
                  value={`¥${skill_gaps.total_potential_yuan.toFixed(0)}`}
                  unit="/月"
                  status="good"
                />
              </div>
              {skill_gaps.top_recommendations.length > 0 ? (
                <div className={styles.skillList}>
                  {skill_gaps.top_recommendations.slice(0, 3).map((rec, i) => (
                    <div key={i} className={styles.skillItem}>
                      <span className={styles.skillName}>
                        {rec.skill_name || rec.action || '技能提升'}
                      </span>
                      {rec.expected_yuan != null && (
                        <span className={styles.skillYuan}>
                          +¥{rec.expected_yuan.toFixed(0)}/月
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className={styles.emptyHint}>暂无技能建议</div>
              )}
            </>
          ) : (
            <ZEmpty title="技能数据暂不可用" />
          )}
        </ZCard>
      </div>
    </div>
  );
}
```

- [ ] **C1.3** TypeScript 编译检查（无 ts 错误）：

```bash
cd apps/web
npx tsc --noEmit 2>&1 | grep -i "HRQuick\|hrquick" | head -20
```

Expected：无 HRQuick 相关错误

- [ ] **C1.4** Commit：

```bash
git add apps/web/src/pages/sm/HRQuick.tsx \
        apps/web/src/pages/sm/HRQuick.module.css
git commit -m "feat(hr): M4 Chunk C — SM HR首页替换为真实留人/排班/技能看板"
```

---

## Chunk D: HQ HR 前端大盘

**Goal:** 新增总部人力大盘页 `/hq/hr`，调用 `GET /api/v1/hr/bff/hq/{org_node_id}`，展示：全集团在职人数、高风险门店热力排名、知识库健康度。在 App.tsx 注册路由。

**设计参考：** 参考 `apps/web/src/pages/hq/Workforce.tsx`（桌面端样式）

### Task D1: HQ HR 页面

**Files:**
- Create: `apps/web/src/pages/hq/HR.tsx`
- Create: `apps/web/src/pages/hq/HR.module.css`
- Modify: `apps/web/src/App.tsx` (注册路由 + lazy import)

- [ ] **D1.1** 创建 CSS module：

```css
/* apps/web/src/pages/hq/HR.module.css */
.page {
  padding: 24px;
  background: var(--bg-primary);
  min-height: 100vh;
}

.header {
  margin-bottom: 24px;
}

.headerTitle {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.headerSub {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.kpiRow {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.kpiCard {
  flex: 1;
}

.section {
  margin-bottom: 24px;
}

.sectionTitle {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.heatmapTable {
  width: 100%;
  border-collapse: collapse;
}

.heatmapTable th {
  text-align: left;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
}

.heatmapTable td {
  padding: 10px 12px;
  font-size: 14px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-light);
}

.knowledgeRow {
  display: flex;
  gap: 16px;
}

.flexCard {
  flex: 1;
}
```

- [ ] **D1.2** 创建 `HR.tsx`：

```tsx
/**
 * 总部人力大盘
 * 路由：/hq/hr
 * 数据：GET /api/v1/hr/bff/hq/{org_node_id}
 *
 * 展示：全集团在职人数 | 高风险门店排名 | 知识库健康度
 * 注：talent_pipeline 延至 M5 实现（依赖 TalentPipelineService）
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZSkeleton, ZEmpty,
} from '../../design-system/components';
import apiClient from '../../services/api';
import { handleApiError } from '../../utils/message';
import styles from './HR.module.css';

// 总部使用全集团根节点；实际应从 auth context 获取
const ORG_NODE_ID = localStorage.getItem('org_node_id') || 'root';

interface HeatmapItem {
  store_id: string;
  store_name: string;
  avg_risk: number;
  signal_count: number;
}

interface HqHrData {
  org_node_id: string;
  as_of: string;
  headcount: { total_active: number } | null;
  turnover_heatmap: HeatmapItem[] | null;
  knowledge_health: {
    active_rules: number;
    skill_nodes: number;
  } | null;
}

function riskBadge(avgRisk: number) {
  if (avgRisk >= 0.7) return <ZBadge type="critical" text="高危" />;
  if (avgRisk >= 0.5) return <ZBadge type="warning" text="警戒" />;
  return <ZBadge type="info" text="正常" />;
}

export default function HQHr() {
  const [data, setData] = useState<HqHrData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/hr/bff/hq/${ORG_NODE_ID}`);
      setData(resp);
    } catch (e) {
      handleApiError(e, '总部人力数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className={styles.page}>
        <ZSkeleton rows={8} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className={styles.page}>
        <ZEmpty title="暂无数据" description="总部人力数据加载失败，请稍后重试" />
      </div>
    );
  }

  const { headcount, turnover_heatmap, knowledge_health, as_of } = data;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>人力大盘</div>
        <div className={styles.headerSub}>更新时间：{as_of}</div>
      </div>

      {/* 核心 KPI */}
      <div className={styles.kpiRow}>
        <div className={styles.kpiCard}>
          <ZCard>
            <ZKpi
              label="全集团在职人数"
              value={headcount?.total_active ?? '—'}
              unit="人"
            />
          </ZCard>
        </div>
        <div className={styles.kpiCard}>
          <ZCard>
            <ZKpi
              label="高风险门店"
              value={
                turnover_heatmap
                  ? turnover_heatmap.filter((s) => s.avg_risk >= 0.7).length
                  : '—'
              }
              unit="家"
              status={
                turnover_heatmap && turnover_heatmap.some((s) => s.avg_risk >= 0.7)
                  ? 'critical'
                  : 'good'
              }
            />
          </ZCard>
        </div>
        <div className={styles.kpiCard}>
          <ZCard>
            <ZKpi
              label="知识规则总数"
              value={knowledge_health?.active_rules ?? '—'}
              unit="条"
            />
          </ZCard>
        </div>
      </div>

      {/* 留人风险热力排名 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>⚠️ 留人风险门店排名（近30天）</div>
        <ZCard>
          {turnover_heatmap && turnover_heatmap.length > 0 ? (
            <table className={styles.heatmapTable}>
              <thead>
                <tr>
                  <th>门店</th>
                  <th>平均风险分</th>
                  <th>预警信号数</th>
                  <th>风险等级</th>
                </tr>
              </thead>
              <tbody>
                {turnover_heatmap.map((item) => (
                  <tr key={item.store_id}>
                    <td>{item.store_name}</td>
                    <td>{(item.avg_risk * 100).toFixed(1)}%</td>
                    <td>{item.signal_count}</td>
                    <td>{riskBadge(item.avg_risk)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <ZEmpty title="暂无高风险门店" description="所有门店留人风险正常" />
          )}
        </ZCard>
      </div>

      {/* 知识库健康度 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>📚 知识库健康度</div>
        <div className={styles.knowledgeRow}>
          <ZCard className={styles.flexCard}>
            <ZKpi
              label="行业经验规则"
              value={knowledge_health?.active_rules ?? '—'}
              unit="条已激活"
            />
          </ZCard>
          <ZCard className={styles.flexCard}>
            <ZKpi
              label="技能图谱节点"
              value={knowledge_health?.skill_nodes ?? '—'}
              unit="个技能"
            />
          </ZCard>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **D1.3** 在 `apps/web/src/App.tsx` 注册 HQ HR 路由。

在 App.tsx 的 `// HR 模块页面` 注释块（约第247行）附近，找到最后一个 lazy import，在其后添加：

```typescript
const HQHrPage = lazy(() => import('./pages/hq/HR'));
```

然后找到 `/hq` 路由块，在 `<Route path="workforce" ... />` 旁添加：

```tsx
<Route path="hr" element={<HQHrPage />} />
```

（注意：需要找到 hq 路由组的正确位置，参考 `/hq/workforce` 路由的注册方式）

- [ ] **D1.4** TypeScript 编译检查：

```bash
cd apps/web
npx tsc --noEmit 2>&1 | grep -i "hq/HR\|HQHr\|HRPage" | head -20
```

Expected：无相关错误

- [ ] **D1.5** 全量后端测试确认无回归：

```bash
cd apps/api-gateway
python -m pytest tests/test_z56_fk_migration.py tests/test_z57_contract_migration.py \
    tests/test_hr_bff_endpoints.py tests/test_retention_ml_service.py \
    tests/test_staffing_service.py -v
```

Expected：`~25 passed, 0 failed`

- [ ] **D1.6** Commit：

```bash
git add apps/web/src/pages/hq/HR.tsx \
        apps/web/src/pages/hq/HR.module.css \
        apps/web/src/App.tsx
git commit -m "feat(hr): M4 Chunk D — HQ HR大盘页 + /hq/hr路由注册"
```

---

## 最终验收

完成后执行以下检查：

```bash
# 后端：全量 HR 相关测试
cd apps/api-gateway
python -m pytest tests/test_z57_contract_migration.py \
    tests/test_hr_bff_endpoints.py \
    tests/test_retention_ml_service.py \
    tests/test_staffing_service.py \
    tests/test_z56_fk_migration.py -v

# 前端：TypeScript 编译
cd apps/web
npx tsc --noEmit 2>&1 | head -20
```

**M4 交付检查清单：**
- [ ] z57 migration: `assignment_id` NOT NULL 约束已加，旧列已删，`employee_id_map` 已删
- [ ] SM BFF: 返回 `staffing_today` 和 `pending_actions_count`
- [ ] HQ BFF: 新端点返回 `headcount`、`turnover_heatmap`、`knowledge_health`
- [ ] `/sm/hr`：真实页面（留人风险 + 排班 + 技能），非 ZEmpty stub
- [ ] `/hq/hr`：总部大盘页已注册并可访问
- [ ] 所有后端测试通过，无新 TypeScript 错误
