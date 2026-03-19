# HR M3 — z56 FK迁移 + C级预测 + WF-2排班优化 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成三个独立任务：(A) 将4张表的外键从 employee_id 平滑迁移到 assignment_id；(B) 在现有 B级 RetentionRiskService 之上叠加 sklearn ML 预测层，支持冷启动降级；(C) 实现 StaffingService 双数据源排班健康度分析，并将 hr_agent.py 的 staffing placeholder 替换为真实调用。

**Architecture:** 三个 Chunk 顺序开发，互相独立可单独交付。Chunk A 只写迁移文件；Chunk B 新建 `src/services/hr/retention_ml_service.py` + Celery 任务 + hr_agent.py 集成；Chunk C 新建 `src/services/hr/staffing_service.py` + Celery 任务 + hr_agent.py 集成。所有服务层使用 mock AsyncSession 测试，不依赖真实 PostgreSQL。

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 async, Alembic, scikit-learn>=1.4.0, joblib>=1.3.0, Redis, pytest-asyncio, structlog

**Prerequisite:** M1（z50-z55 migrations applied）, M2 已合并 main。

**Spec reference:** `docs/superpowers/specs/2026-03-17-hr-m3-fk-prediction-staffing.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| CREATE | `apps/api-gateway/alembic/versions/z56_fk_migration_to_assignment_id.py` | 4张表 ADD COLUMN + 回填 UPDATE |
| CREATE | `apps/api-gateway/tests/test_z56_fk_migration.py` | 验证迁移结构和幂等性 |
| MODIFY | `apps/api-gateway/requirements.txt` | 添加 scikit-learn + joblib |
| CREATE | `apps/api-gateway/src/services/hr/retention_ml_service.py` | ML训练/预测/Redis存取 + 冷启动降级 |
| MODIFY | `apps/api-gateway/src/core/celery_tasks.py` | 添加 retrain_retention_model_weekly + trigger_staffing_analysis_weekly |
| CREATE | `apps/api-gateway/tests/test_retention_ml_service.py` | 冷启动/ML路径/Redis缺失降级测试 |
| MODIFY | `apps/api-gateway/src/agents/hr_agent.py` | 添加 _predict_retention_risk + _diagnose_staffing 真实实现 |
| CREATE | `apps/api-gateway/src/services/hr/staffing_service.py` | 双数据源排班分析 + Redis缓存 |
| CREATE | `apps/api-gateway/tests/test_staffing_service.py` | 正常路径/降级/空数据测试 |

---

## Chunk A: z56 FK 迁移

**Goal:** 为 `compliance_licenses`, `customer_ownerships`, `shifts`, `employee_metric_records` 四张表新增 `assignment_id UUID NULL` 列，并通过 `employee_id_map` 回填。

### Task A1: 写测试（先行）

**Files:**
- Create: `apps/api-gateway/tests/test_z56_fk_migration.py`

- [ ] **A1.1** 创建测试文件，覆盖四个核心断言（列存在、幂等、SQL语法、downgrade）:

```python
"""Tests for z56 FK migration to assignment_id.

Since CI has no PostgreSQL, we mock schema inspection and verify
the migration SQL logic using string inspection and mock patterns.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")


TARGET_TABLES = [
    "compliance_licenses",
    "customer_ownerships",
    "shifts",
    "employee_metric_records",
]


def test_revision_metadata():
    """Migration file has correct revision and down_revision."""
    from alembic.versions.z56_fk_migration_to_assignment_id import (
        revision,
        down_revision,
    )
    assert revision == "z56_fk_migration_to_assignment_id"
    assert down_revision == "z55_hr_knowledge_tables"


def test_upgrade_adds_column_for_all_tables():
    """upgrade() executes SQL touching each of the 4 target tables."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = False
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    executed_sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    for table in TARGET_TABLES:
        found = any(table in sql for sql in executed_sqls)
        assert found, f"No SQL executed for table {table}"


def test_upgrade_skips_existing_column():
    """upgrade() skips ADD COLUMN when assignment_id already exists (idempotent)."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = True  # column already exists
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    mock_exec.assert_not_called()


def test_upgrade_runs_backfill_update():
    """upgrade() runs UPDATE referencing employee_id_map for each table."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = False
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    all_sqls = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
    assert "employee_id_map" in all_sqls
    assert "assignment_id" in all_sqls


def test_downgrade_drops_column_for_all_tables():
    """downgrade() drops assignment_id from all 4 tables."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = True  # column exists
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import downgrade
        downgrade()

    executed_sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    for table in TARGET_TABLES:
        found = any(table in sql for sql in executed_sqls)
        assert found, f"downgrade() missing for {table}"


def test_no_not_null_constraint():
    """Migration does NOT add NOT NULL (M4 concern only)."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = False
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    all_sqls = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
    assert "NOT NULL" not in all_sqls.upper()
```

- [ ] **A1.2** 运行测试，确认 ImportError:

```bash
cd apps/api-gateway
pytest tests/test_z56_fk_migration.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` (file doesn't exist yet)

### Task A2: 实现迁移文件

**Files:**
- Create: `apps/api-gateway/alembic/versions/z56_fk_migration_to_assignment_id.py`

- [ ] **A2.1** 创建迁移文件:

```python
"""z56 FK迁移 — 4张表新增 assignment_id 列 + 回填

将 compliance_licenses / customer_ownerships / shifts / employee_metric_records
各自新增 assignment_id UUID NULL，通过 employee_id_map 桥接表回填。
M3 不删除旧 employee_id 列，M4 才做最终切割。

Revision ID: z56_fk_migration_to_assignment_id
Revises: z55_hr_knowledge_tables
Create Date: 2026-03-18
"""
import sqlalchemy as sa
from alembic import op

revision = "z56_fk_migration_to_assignment_id"
down_revision = "z55_hr_knowledge_tables"
branch_labels = None
depends_on = None

# (table_name, legacy_col_name)
_TABLES = [
    ("compliance_licenses", "holder_employee_id"),
    ("customer_ownerships", "owner_employee_id"),
    ("shifts", "employee_id"),
    ("employee_metric_records", "employee_id"),
]


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns"
            "  WHERE table_schema='public'"
            "    AND table_name=:t AND column_name=:c"
            ")"
        ),
        {"t": table, "c": column},
    )
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    for table, legacy_col in _TABLES:
        if _column_exists(conn, table, "assignment_id"):
            continue

        conn.execute(sa.text(
            f"ALTER TABLE {table} ADD COLUMN assignment_id UUID NULL"
        ))

        conn.execute(sa.text(f"""
            UPDATE {table} t
            SET assignment_id = (
                SELECT ea.id
                FROM employee_id_map m
                JOIN employment_assignments ea ON ea.person_id = m.person_id
                WHERE m.legacy_employee_id = t.{legacy_col}
                  AND ea.status = 'active'
                ORDER BY ea.created_at DESC
                LIMIT 1
            )
            WHERE t.assignment_id IS NULL
        """))

        conn.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_assignment_id"
            f" ON {table}(assignment_id)"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    for table, _ in _TABLES:
        if not _column_exists(conn, table, "assignment_id"):
            continue
        conn.execute(sa.text(
            f"DROP INDEX IF EXISTS ix_{table}_assignment_id"
        ))
        conn.execute(sa.text(
            f"ALTER TABLE {table} DROP COLUMN assignment_id"
        ))
```

- [ ] **A2.2** 运行测试，全部通过:

```bash
cd apps/api-gateway
pytest tests/test_z56_fk_migration.py -v
```

Expected: 6 passed

- [ ] **A2.3** 提交:

```bash
git add apps/api-gateway/alembic/versions/z56_fk_migration_to_assignment_id.py \
        apps/api-gateway/tests/test_z56_fk_migration.py
git commit -m "feat(hr): M3 Chunk A — z56 FK migration adds assignment_id to 4 tables"
```

---

## Chunk B: HRAgent v2 C级 ML 预测

**Goal:** 新建 `RetentionMLService`（sklearn LR + joblib/Redis 存取 + 冷启动降级），添加 Celery 周训练任务，在 hr_agent.py 中添加 ML 预测路径（有 person_id 时）。

> **Security note:** joblib is used for sklearn model serialization per spec §2.5. Models are trained from our own DB data and stored in our own Redis — no untrusted external model loading.

### Task B1: 添加依赖

**Files:**
- Modify: `apps/api-gateway/requirements.txt`

- [ ] **B1.1** 在 requirements.txt 的 `# ML` 或末尾添加:

```
# ML (HR retention prediction — spec §2.2)
scikit-learn>=1.4.0
joblib>=1.3.0
```

- [ ] **B1.2** 验证安装（如本机未安装则 `pip install scikit-learn joblib`）:

```bash
python3 -c "import sklearn, joblib; print('sklearn', sklearn.__version__, 'joblib', joblib.__version__)"
```

### Task B2: 写测试（先行）

**Files:**
- Create: `apps/api-gateway/tests/test_retention_ml_service.py`

- [ ] **B2.1** 创建测试文件（7个测试）:

```python
"""Tests for RetentionMLService — C级 ML retention risk prediction.

All tests mock sklearn / Redis / AsyncSession.
No real PostgreSQL or model training required.
"""
import io
import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get = MagicMock(return_value=None)
    r.setex = MagicMock()
    return r


def _make_feature_rows(n: int):
    rows = []
    for i in range(n):
        row = MagicMock()
        row.tenure_days = 180 + i * 10
        row.achievement_count = i % 5
        row.recent_signal_avg = 0.6 + (i % 3) * 0.1
        row.is_churned = i % 7 == 0
        rows.append(row)
    return rows


@pytest.mark.asyncio
async def test_cold_start_returns_heuristic(mock_session, mock_redis):
    """< 50 samples => prediction_source == 'heuristic'."""
    from src.services.hr.retention_ml_service import RetentionMLService

    result_mock = MagicMock()
    result_mock.fetchall.return_value = _make_feature_rows(10)
    mock_session.execute.return_value = result_mock
    mock_session.execute.side_effect = None
    mock_session.execute.return_value = result_mock

    svc = RetentionMLService(session=mock_session, redis_client=mock_redis)
    prediction = await svc.predict(person_id=uuid.uuid4(), store_id="STORE001")

    assert prediction["prediction_source"] == "heuristic"
    assert 0.0 <= prediction["risk_score"] <= 1.0
    assert prediction["risk_level"] in ("low", "medium", "high")


@pytest.mark.asyncio
async def test_cold_start_no_error_when_redis_empty(mock_session, mock_redis):
    """No exception when Redis has no stored model."""
    from src.services.hr.retention_ml_service import RetentionMLService

    mock_redis.get.return_value = None
    result_mock = MagicMock()
    result_mock.fetchone.return_value = None
    mock_session.execute.return_value = result_mock

    svc = RetentionMLService(session=mock_session, redis_client=mock_redis)
    prediction = await svc.predict(person_id=uuid.uuid4(), store_id="STORE001")

    assert "risk_score" in prediction
    assert prediction["prediction_source"] == "heuristic"


@pytest.mark.asyncio
async def test_ml_path_uses_model_from_redis(mock_session, mock_redis):
    """Redis model present => prediction_source == 'ml', risk_score from model."""
    import joblib
    from src.services.hr.retention_ml_service import RetentionMLService

    mock_model = MagicMock()
    mock_model.predict_proba.return_value = [[0.28, 0.72]]
    model_payload = {
        "model": mock_model,
        "trained_at": datetime.utcnow().isoformat(),
        "sample_count": 80,
    }
    buf = io.BytesIO()
    joblib.dump(model_payload, buf)
    mock_redis.get.return_value = buf.getvalue()

    result_mock = MagicMock()
    result_mock.fetchone.return_value = None
    mock_session.execute.return_value = result_mock

    svc = RetentionMLService(session=mock_session, redis_client=mock_redis)
    prediction = await svc.predict(person_id=uuid.uuid4(), store_id="STORE001")

    assert prediction["prediction_source"] == "ml"
    assert prediction["risk_score"] == pytest.approx(0.72, abs=0.01)
    assert prediction["risk_level"] == "high"


@pytest.mark.asyncio
async def test_ml_path_low_risk_level(mock_session, mock_redis):
    """risk_level == 'low' when predict_proba < 0.4."""
    import joblib
    from src.services.hr.retention_ml_service import RetentionMLService

    mock_model = MagicMock()
    mock_model.predict_proba.return_value = [[0.75, 0.25]]
    payload = {"model": mock_model, "trained_at": datetime.utcnow().isoformat(), "sample_count": 60}
    buf = io.BytesIO()
    joblib.dump(payload, buf)
    mock_redis.get.return_value = buf.getvalue()

    result_mock = MagicMock()
    result_mock.fetchone.return_value = None
    mock_session.execute.return_value = result_mock

    svc = RetentionMLService(session=mock_session, redis_client=mock_redis)
    prediction = await svc.predict(person_id=uuid.uuid4(), store_id="STORE001")

    assert prediction["risk_level"] == "low"
    assert prediction["risk_score"] < 0.4


@pytest.mark.asyncio
async def test_train_stores_model_in_redis(mock_session, mock_redis):
    """train_for_store() calls redis.setex with 7-day TTL."""
    from unittest.mock import patch
    from src.services.hr.retention_ml_service import RetentionMLService

    rows = _make_feature_rows(60)
    result_mock = MagicMock()
    result_mock.fetchall.return_value = rows
    mock_session.execute.return_value = result_mock

    with patch("sklearn.linear_model.LogisticRegression") as MockLR:
        instance = MagicMock()
        instance.predict_proba.return_value = [[0.4, 0.6]] * 60
        instance.fit = MagicMock()
        MockLR.return_value = instance

        svc = RetentionMLService(session=mock_session, redis_client=mock_redis)
        result = await svc.train_for_store("STORE001")

    assert result["sample_count"] == 60
    assert "trained_at" in result
    mock_redis.setex.assert_called_once()
    key, ttl, _ = mock_redis.setex.call_args[0]
    assert "hr:retention_model:STORE001" in key
    assert ttl == 7 * 24 * 3600


@pytest.mark.asyncio
async def test_train_skips_when_insufficient_samples(mock_session, mock_redis):
    """train_for_store() returns cold_start=True when < 50 samples."""
    from src.services.hr.retention_ml_service import RetentionMLService

    result_mock = MagicMock()
    result_mock.fetchall.return_value = _make_feature_rows(20)
    mock_session.execute.return_value = result_mock

    svc = RetentionMLService(session=mock_session, redis_client=mock_redis)
    result = await svc.train_for_store("STORE001")

    assert result["cold_start"] is True
    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_prediction_contains_required_fields(mock_session, mock_redis):
    """Output has all spec fields: person_id, risk_score, risk_level, prediction_source, intervention."""
    from src.services.hr.retention_ml_service import RetentionMLService

    result_mock = MagicMock()
    result_mock.fetchone.return_value = None
    mock_session.execute.return_value = result_mock

    svc = RetentionMLService(session=mock_session, redis_client=mock_redis)
    person_id = uuid.uuid4()
    prediction = await svc.predict(person_id=person_id, store_id="STORE001")

    for key in ("person_id", "risk_score", "risk_level", "prediction_source", "intervention"):
        assert key in prediction, f"Missing: {key}"
    intervention = prediction["intervention"]
    for k in ("action", "confidence", "estimated_impact"):
        assert k in intervention, f"intervention missing: {k}"
    assert str(prediction["person_id"]) == str(person_id)
```

- [ ] **B2.2** 运行测试，确认 ImportError:

```bash
cd apps/api-gateway
pytest tests/test_retention_ml_service.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'src.services.hr.retention_ml_service'`

### Task B3: 实现 RetentionMLService

**Files:**
- Create: `apps/api-gateway/src/services/hr/retention_ml_service.py`

- [ ] **B3.1** 创建服务文件:

```python
"""RetentionMLService — C级 ML 离职风险预测.

冷启动策略: 标记样本 < 50 时回退到启发式规则（同 B级 RetentionRiskService）。
模型存储: joblib 序列化 → Redis key hr:retention_model:{store_id}，TTL 7天。

特征工程:
  tenure_days       — employment_assignments.start_date 在职天数
  achievement_count — person_achievements 近90天成就数
  recent_signal_avg — retention_signals 近30天均值 (0-1)
"""
import io
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import sqlalchemy as sa
import structlog

logger = structlog.get_logger()

_MIN_TRAIN_SAMPLES = 50
_REDIS_TTL_SECONDS = 7 * 24 * 3600
_REDIS_KEY_TEMPLATE = "hr:retention_model:{store_id}"
_HIGH_RISK_THRESHOLD = 0.70
_MEDIUM_RISK_THRESHOLD = 0.40

_INTERVENTIONS = {
    "high": {
        "action": "安排一对一面谈",
        "estimated_impact": "降低离职概率 23%",
        "confidence": 0.68,
    },
    "medium": {
        "action": "了解近期诉求，酌情调整排班",
        "estimated_impact": "降低离职概率 12%",
        "confidence": 0.55,
    },
    "low": {
        "action": "保持正常关注",
        "estimated_impact": "维持现状",
        "confidence": 0.80,
    },
}


def _classify_risk(score: float) -> str:
    if score >= _HIGH_RISK_THRESHOLD:
        return "high"
    if score >= _MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def _heuristic_score(
    tenure_days: int, achievement_count: int, recent_signal_avg: float
) -> float:
    """B级启发式评分 (与 RetentionRiskService 相同逻辑)."""
    baseline = 0.3
    new_hire = 0.2 if tenure_days < 90 else 0.0
    no_achieve = 0.2 if achievement_count == 0 else 0.0
    signal = (1.0 - recent_signal_avg) * 0.5 if recent_signal_avg > 0 else 0.15
    return min(1.0, baseline + new_hire + no_achieve + signal)


class RetentionMLService:
    """C级 ML 预测服务 — Redis模型优先，冷启动降级到启发式."""

    def __init__(self, session, redis_client=None) -> None:
        self._session = session
        self._redis = redis_client

    async def predict(
        self, person_id: uuid.UUID, store_id: str
    ) -> Dict[str, Any]:
        """返回结构化预测结果 (spec §2.7)."""
        features = await self._fetch_person_features(person_id)
        model_payload = self._load_model_from_redis(store_id)

        if model_payload is not None:
            score, source = self._ml_predict(features, model_payload)
            model_trained_at = model_payload.get("trained_at")
            sample_count = model_payload.get("sample_count", 0)
        else:
            score = _heuristic_score(
                features.get("tenure_days", 180),
                features.get("achievement_count", 0),
                features.get("recent_signal_avg", 0.5),
            )
            source = "heuristic"
            model_trained_at = None
            sample_count = 0

        level = _classify_risk(score)
        intervention = dict(_INTERVENTIONS[level])
        intervention["deadline"] = (
            datetime.utcnow() + timedelta(days=14)
        ).strftime("%Y-%m-%d")

        result: Dict[str, Any] = {
            "person_id": str(person_id),
            "risk_score": round(score, 4),
            "risk_level": level,
            "prediction_source": source,
            "intervention": intervention,
        }
        if model_trained_at:
            result["model_trained_at"] = model_trained_at
            result["sample_count"] = sample_count

        logger.info(
            "retention_ml.predict",
            person_id=str(person_id),
            store_id=store_id,
            risk_level=level,
            source=source,
        )
        return result

    async def train_for_store(self, store_id: str) -> Dict[str, Any]:
        """训练模型并存入 Redis。样本不足时返回 cold_start=True."""
        rows = await self._fetch_training_data(store_id)
        if len(rows) < _MIN_TRAIN_SAMPLES:
            logger.info("retention_ml.cold_start", store_id=store_id, n=len(rows))
            return {"cold_start": True, "sample_count": len(rows), "store_id": store_id}

        X = [
            [
                float(r.tenure_days or 0),
                float(r.achievement_count or 0),
                float(r.recent_signal_avg or 0.5),
            ]
            for r in rows
        ]
        y = [int(bool(r.is_churned)) for r in rows]

        from sklearn.linear_model import LogisticRegression
        import joblib

        model = LogisticRegression(max_iter=500, class_weight="balanced")
        model.fit(X, y)

        trained_at = datetime.utcnow().isoformat()
        payload = {"model": model, "trained_at": trained_at, "sample_count": len(rows)}

        buf = io.BytesIO()
        joblib.dump(payload, buf)
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id)
        if self._redis:
            self._redis.setex(key, _REDIS_TTL_SECONDS, buf.getvalue())

        logger.info("retention_ml.trained", store_id=store_id, samples=len(rows))
        return {"cold_start": False, "sample_count": len(rows), "trained_at": trained_at}

    # ─── Private ──────────────────────────────────────────────────────────────

    def _load_model_from_redis(self, store_id: str) -> Optional[Dict]:
        if not self._redis:
            return None
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id)
        raw = self._redis.get(key)
        if not raw:
            return None
        try:
            import joblib
            return joblib.load(io.BytesIO(raw))
        except Exception as exc:
            logger.warning("retention_ml.model_load_failed", error=str(exc))
            return None

    def _ml_predict(self, features: dict, payload: dict) -> tuple:
        model = payload["model"]
        X = [[
            float(features.get("tenure_days", 0)),
            float(features.get("achievement_count", 0)),
            float(features.get("recent_signal_avg", 0.5)),
        ]]
        proba = model.predict_proba(X)[0]
        return float(proba[1]), "ml"

    async def _fetch_person_features(self, person_id: uuid.UUID) -> Dict[str, Any]:
        result = await self._session.execute(
            sa.text("""
                SELECT
                    COALESCE(EXTRACT(DAY FROM NOW() - ea.start_date)::int, 180) AS tenure_days,
                    COALESCE((
                        SELECT COUNT(*) FROM person_achievements pa
                        WHERE pa.person_id = :pid
                          AND pa.achieved_at >= NOW() - INTERVAL '90 days'
                    ), 0) AS achievement_count,
                    COALESCE((
                        SELECT AVG(rs.signal_value) FROM retention_signals rs
                        WHERE rs.person_id = :pid
                          AND rs.recorded_at >= NOW() - INTERVAL '30 days'
                    ), 0.5) AS recent_signal_avg
                FROM employment_assignments ea
                WHERE ea.person_id = :pid AND ea.status = 'active'
                ORDER BY ea.created_at DESC LIMIT 1
            """),
            {"pid": str(person_id)},
        )
        row = result.fetchone()
        if row:
            return {
                "tenure_days": int(row.tenure_days or 180),
                "achievement_count": int(row.achievement_count or 0),
                "recent_signal_avg": float(row.recent_signal_avg or 0.5),
            }
        return {"tenure_days": 180, "achievement_count": 0, "recent_signal_avg": 0.5}

    async def _fetch_training_data(self, store_id: str):
        result = await self._session.execute(
            sa.text("""
                SELECT
                    EXTRACT(DAY FROM COALESCE(ea.end_date, NOW()) - ea.start_date)::int AS tenure_days,
                    COALESCE((
                        SELECT COUNT(*) FROM person_achievements pa
                        WHERE pa.person_id = p.id
                          AND pa.achieved_at >= NOW() - INTERVAL '90 days'
                    ), 0) AS achievement_count,
                    COALESCE((
                        SELECT AVG(rs.signal_value) FROM retention_signals rs
                        WHERE rs.person_id = p.id
                          AND rs.recorded_at >= NOW() - INTERVAL '30 days'
                    ), 0.5) AS recent_signal_avg,
                    CASE WHEN ea.status = 'terminated'
                         AND ea.end_date >= NOW() - INTERVAL '30 days'
                    THEN TRUE ELSE FALSE END AS is_churned
                FROM persons p
                JOIN employment_assignments ea ON ea.person_id = p.id
                JOIN org_nodes on_ ON on_.id = ea.org_node_id
                WHERE on_.store_id = :store_id AND ea.start_date IS NOT NULL
                LIMIT 500
            """),
            {"store_id": store_id},
        )
        return result.fetchall()
```

- [ ] **B3.2** 运行测试:

```bash
cd apps/api-gateway
pytest tests/test_retention_ml_service.py -v
```

Expected: 7 passed

### Task B4: 添加 Celery 任务 + hr_agent.py 集成

**Files:**
- Modify: `apps/api-gateway/src/core/celery_tasks.py`
- Modify: `apps/api-gateway/src/core/celery_app.py`
- Modify: `apps/api-gateway/src/agents/hr_agent.py`

- [ ] **B4.1** 查看 celery_tasks.py 末尾，找合适插入位置:

```bash
tail -30 apps/api-gateway/src/core/celery_tasks.py
```

- [ ] **B4.2** 在 `celery_tasks.py` 末尾追加 HR ML 训练任务:

```python
@celery_app.task(name="hr.retrain_retention_model_weekly")
def retrain_retention_model_weekly():
    """每周日 02:00 UTC — 遍历所有 active store，重训留任预测模型存入 Redis。"""
    import asyncio

    async def _run():
        import redis as redis_lib
        from src.core.config import settings
        from src.core.database import AsyncSessionLocal
        from src.services.hr.retention_ml_service import RetentionMLService

        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=False)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                sa.text("SELECT id FROM stores WHERE is_active = TRUE")
            )
            store_ids = [str(row[0]) for row in result.fetchall()]

        for store_id in store_ids:
            async with AsyncSessionLocal() as session:
                svc = RetentionMLService(session=session, redis_client=r)
                outcome = await svc.train_for_store(store_id)
                logger.info("celery.hr_ml_retrain", store_id=store_id, outcome=outcome)

    asyncio.run(_run())
```

> **Note:** Verify `sa` and `logger` are already imported at top of `celery_tasks.py`. Add if missing.

- [ ] **B4.3** 在 `celery_app.py` 的 `beat_schedule` dict 中添加:

```python
"hr-retrain-retention-model-weekly": {
    "task": "hr.retrain_retention_model_weekly",
    "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 02:00 UTC
    "options": {"priority": 3},
},
```

- [ ] **B4.4** 在 `hr_agent.py` 顶部导入区添加 lazy import helper:

```python
_retention_ml_cls = None

def _get_retention_ml_cls():
    global _retention_ml_cls
    if _retention_ml_cls is None:
        try:
            from src.services.hr.retention_ml_service import RetentionMLService
            _retention_ml_cls = RetentionMLService
        except ImportError:
            logger.warning("hr_agent.retention_ml_import_failed")
    return _retention_ml_cls
```

- [ ] **B4.5** 在 `hr_agent.py` 中添加 `_predict_retention_risk` 方法（在 `_diagnose_retention` 之后）:

```python
async def _predict_retention_risk(
    self, store_id: str, session, person_id: str
) -> HRDiagnosis:
    """C级 ML预测 — 有 person_id 时走 ML路径，失败回退 B级扫描。"""
    import os
    redis_client = None
    try:
        import redis as redis_lib
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        redis_client = redis_lib.from_url(redis_url, decode_responses=False)
    except Exception:
        pass

    MLSvc = _get_retention_ml_cls()
    if MLSvc is None:
        return await self._diagnose_retention(store_id, session)

    svc = MLSvc(session=session, redis_client=redis_client)
    prediction = await svc.predict(
        person_id=uuid_mod.UUID(person_id), store_id=store_id
    )

    level = prediction["risk_level"]
    score = prediction["risk_score"]
    source = prediction["prediction_source"]
    summary = f"ML预测 [{source}]: 离职风险 {level} (score={score:.2f})"

    return HRDiagnosis(
        intent="retention_risk",
        store_id=store_id,
        summary=summary,
        recommendations=[prediction.get("intervention", {})],
        high_risk_persons=[prediction] if level == "high" else [],
    )
```

- [ ] **B4.6** 更新 `diagnose()` 中 `retention_risk` 分支:

```python
if intent == "retention_risk":
    if person_id:
        return await self._predict_retention_risk(store_id, session, person_id)
    return await self._diagnose_retention(store_id, session)
```

- [ ] **B4.7** 语法验证:

```bash
cd apps/api-gateway
python3 -c "from src.agents.hr_agent import HRAgentV1; print('OK')"
```

- [ ] **B4.8** 提交 Chunk B:

```bash
git add apps/api-gateway/requirements.txt \
        apps/api-gateway/src/services/hr/retention_ml_service.py \
        apps/api-gateway/src/core/celery_tasks.py \
        apps/api-gateway/src/core/celery_app.py \
        apps/api-gateway/src/agents/hr_agent.py \
        apps/api-gateway/tests/test_retention_ml_service.py
git commit -m "feat(hr): M3 Chunk B — RetentionMLService C级ML预测 + Celery周训练 + HRAgent集成"
```

---

## Chunk C: WF-2 StaffingService 排班优化

**Goal:** 实现 `StaffingService.diagnose_staffing()` — 双数据源融合（orders 40% + daily_metrics 60%），计算峰值/缺编/超编时段和节省金额；替换 hr_agent.py 中的 staffing placeholder。

### Task C1: 写测试（先行）

**Files:**
- Create: `apps/api-gateway/tests/test_staffing_service.py`

- [ ] **C1.1** 创建测试文件（7个测试）:

```python
"""Tests for StaffingService — WF-2 staffing health analysis.

All tests mock AsyncSession + Redis. No real PostgreSQL required.
"""
import json
import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get = MagicMock(return_value=None)
    r.setex = MagicMock()
    return r


def _make_execute(orders_data, metrics_data, shifts_data):
    """Build a side_effect that dispatches by SQL content."""
    def _row(hour, count):
        r = MagicMock(); r.hour = hour; r.order_count = count; r.avg_count = count; r.headcount = count; return r

    async def fake_execute(stmt, params=None):
        sql = str(stmt).lower()
        result = MagicMock()
        if "from orders" in sql and "7" in sql:
            result.fetchall.return_value = [_row(h, c) for h, c in orders_data]
        elif "from orders" in sql and "30" in sql:
            result.fetchall.return_value = [_row(h, c) for h, c in metrics_data]
        elif "shifts" in sql:
            result.fetchall.return_value = [_row(h, c) for h, c in shifts_data]
        else:
            result.fetchall.return_value = []
        return result
    return fake_execute


@pytest.mark.asyncio
async def test_output_has_all_required_fields(mock_session, mock_redis):
    """Output contains all spec §3.3 required keys."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute([], [], [])
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    for key in ("store_id", "analysis_date", "peak_hours", "understaffed_hours",
                "overstaffed_hours", "recommended_headcount", "estimated_savings_yuan",
                "confidence", "data_freshness"):
        assert key in result, f"Missing: {key}"


@pytest.mark.asyncio
async def test_peak_hours_detected(mock_session, mock_redis):
    """peak_hours contains lunch/dinner spike hours."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[(9, 3), (10, 4), (11, 5), (12, 20), (13, 18), (17, 4), (18, 22), (19, 19)],
        metrics_data=[(9, 3.0), (10, 4.0), (11, 5.0), (12, 18.0), (13, 16.0), (17, 4.0), (18, 20.0), (19, 17.0)],
        shifts_data=[(9, 2), (10, 2), (12, 3), (18, 3)],
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert len(result["peak_hours"]) > 0
    assert 12 in result["peak_hours"] or 18 in result["peak_hours"]


@pytest.mark.asyncio
async def test_savings_yuan_positive_when_overstaffed(mock_session, mock_redis):
    """estimated_savings_yuan > 0 when actual headcount >> recommended."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[(h, 2) for h in range(9, 21)],
        metrics_data=[(h, 2.0) for h in range(9, 21)],
        shifts_data=[(h, 10) for h in range(9, 21)],   # massively overstaffed
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["estimated_savings_yuan"] > 0


@pytest.mark.asyncio
async def test_both_empty_returns_zero_confidence(mock_session, mock_redis):
    """Both data sources empty => confidence == 0.0, no crash."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute([], [], [])
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["confidence"] == 0.0
    assert result["peak_hours"] == []
    assert result["estimated_savings_yuan"] == 0.0


@pytest.mark.asyncio
async def test_orders_empty_falls_back_to_metrics(mock_session, mock_redis):
    """No orders data => falls back to metrics only, confidence > 0, no crash."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[],
        metrics_data=[(12, 15.0), (18, 12.0)],
        shifts_data=[(12, 4), (18, 3)],
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["confidence"] > 0.0
    assert isinstance(result["peak_hours"], list)


@pytest.mark.asyncio
async def test_redis_cache_hit_skips_db(mock_session, mock_redis):
    """Cached result returned without hitting DB."""
    from src.services.hr.staffing_service import StaffingService

    cached = {
        "store_id": "STORE001", "analysis_date": "2026-03-18",
        "peak_hours": [12, 18], "understaffed_hours": [], "overstaffed_hours": [],
        "recommended_headcount": {"12": 5}, "estimated_savings_yuan": 0.0,
        "confidence": 0.75, "data_freshness": {},
    }
    mock_redis.get.return_value = json.dumps(cached).encode()

    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert result["peak_hours"] == [12, 18]
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_understaffed_hours_detected(mock_session, mock_redis):
    """Hours where actual headcount < recommended are in understaffed_hours."""
    from src.services.hr.staffing_service import StaffingService

    mock_session.execute.side_effect = _make_execute(
        orders_data=[(12, 30)],   # very high demand at noon
        metrics_data=[(12, 25.0)],
        shifts_data=[(12, 1)],    # only 1 person on shift
    )
    svc = StaffingService(session=mock_session, redis_client=mock_redis)
    result = await svc.diagnose_staffing("STORE001", date(2026, 3, 18))

    assert 12 in result["understaffed_hours"]
```

- [ ] **C1.2** 运行测试，确认 ImportError:

```bash
cd apps/api-gateway
pytest tests/test_staffing_service.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError`

### Task C2: 实现 StaffingService

**Files:**
- Create: `apps/api-gateway/src/services/hr/staffing_service.py`

- [ ] **C2.1** 创建服务文件:

```python
"""StaffingService — WF-2 排班健康度诊断.

双数据源融合:
  orders 近7天小时聚合  权重 40%
  orders 近30天均值     权重 60% (历史基准)

orders 为空时权重升为 100% 历史均值。
两者皆空时返回 confidence=0.0 空结果，不抛错。
"""
import json
import math
import statistics
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
import structlog

logger = structlog.get_logger()

_ORDERS_WEIGHT = 0.4
_METRICS_WEIGHT = 0.6
_HOURLY_WAGE_DEFAULT = 25.0   # 元/小时 (spec §3.4)
_REDIS_TTL_SECONDS = 24 * 3600
_REDIS_KEY_TEMPLATE = "hr:staffing_diagnosis:{store_id}:{date}"
_AVG_ORDERS_PER_STAFF = 8.0


def _compute_fused_demand(
    recent: Dict[int, float], historical: Dict[int, float]
) -> Dict[int, float]:
    if not recent and not historical:
        return {}
    if not recent:
        return dict(historical)
    if not historical:
        return dict(recent)
    all_hours = set(recent) | set(historical)
    return {
        h: _ORDERS_WEIGHT * recent.get(h, 0.0) + _METRICS_WEIGHT * historical.get(h, 0.0)
        for h in all_hours
    }


def _compute_peak_hours(fused: Dict[int, float]) -> List[int]:
    if len(fused) < 2:
        return []
    values = list(fused.values())
    mean = statistics.mean(values)
    try:
        std = statistics.stdev(values)
    except statistics.StatisticsError:
        std = 0.0
    threshold = mean + std
    return sorted(h for h, v in fused.items() if v > threshold)


def _compute_recommended_headcount(fused: Dict[int, float]) -> Dict[int, int]:
    return {
        h: max(1, math.ceil(v / _AVG_ORDERS_PER_STAFF) + 1)
        for h, v in fused.items()
    }


def _compute_savings(actual: Dict[int, int], recommended: Dict[int, int]) -> float:
    total = 0.0
    for h, cnt in actual.items():
        surplus = max(0, cnt - recommended.get(h, 0))
        total += surplus * _HOURLY_WAGE_DEFAULT
    return round(total, 2)


class StaffingService:
    """WF-2 排班健康度诊断服务."""

    def __init__(self, session, redis_client=None) -> None:
        self._session = session
        self._redis = redis_client

    async def diagnose_staffing(
        self, store_id: str, analysis_date: date
    ) -> Dict[str, Any]:
        cached = self._get_cached(store_id, analysis_date)
        if cached is not None:
            return cached

        recent_orders = await self._fetch_recent_orders(store_id, analysis_date)
        historical_avg = await self._fetch_historical_avg(store_id, analysis_date)
        actual_shifts = await self._fetch_actual_shifts(store_id, analysis_date)

        fused = _compute_fused_demand(recent_orders, historical_avg)

        if not fused:
            result = self._empty_result(store_id, analysis_date)
            self._cache(store_id, analysis_date, result)
            return result

        peak_hours = _compute_peak_hours(fused)
        recommended = _compute_recommended_headcount(fused)

        understaffed = sorted(
            h for h in fused if actual_shifts.get(h, 0) < recommended.get(h, 0)
        )
        overstaffed = sorted(
            h for h in fused if actual_shifts.get(h, 0) > recommended.get(h, 0) + 1
        )
        savings = _compute_savings(actual_shifts, recommended)

        if recent_orders and historical_avg:
            confidence = 0.75
        elif historical_avg:
            confidence = 0.55
        else:
            confidence = 0.60

        result = {
            "store_id": store_id,
            "analysis_date": str(analysis_date),
            "peak_hours": peak_hours,
            "understaffed_hours": understaffed,
            "overstaffed_hours": overstaffed,
            "recommended_headcount": {str(h): v for h, v in recommended.items()},
            "estimated_savings_yuan": savings,
            "confidence": confidence,
            "data_freshness": {
                "orders_days": 7 if recent_orders else 0,
                "daily_metrics_days": 30 if historical_avg else 0,
            },
        }
        self._cache(store_id, analysis_date, result)
        logger.info("staffing.diagnosed", store_id=store_id, date=str(analysis_date),
                    peak_hours=peak_hours, savings_yuan=savings)
        return result

    # ─── Private ──────────────────────────────────────────────────────────────

    def _get_cached(self, store_id: str, analysis_date: date) -> Optional[Dict]:
        if not self._redis:
            return None
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id, date=str(analysis_date))
        raw = self._redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _cache(self, store_id: str, analysis_date: date, result: dict) -> None:
        if not self._redis:
            return
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id, date=str(analysis_date))
        try:
            self._redis.setex(key, _REDIS_TTL_SECONDS, json.dumps(result).encode())
        except Exception as exc:
            logger.warning("staffing.cache_failed", error=str(exc))

    @staticmethod
    def _empty_result(store_id: str, analysis_date: date) -> Dict:
        return {
            "store_id": store_id, "analysis_date": str(analysis_date),
            "peak_hours": [], "understaffed_hours": [], "overstaffed_hours": [],
            "recommended_headcount": {}, "estimated_savings_yuan": 0.0,
            "confidence": 0.0, "data_freshness": {"orders_days": 0, "daily_metrics_days": 0},
        }

    async def _fetch_recent_orders(self, store_id: str, analysis_date: date) -> Dict[int, float]:
        since = analysis_date - timedelta(days=7)
        result = await self._session.execute(
            sa.text("""
                SELECT EXTRACT(HOUR FROM created_at)::int AS hour,
                       COUNT(*)::float / 7 AS order_count
                FROM orders
                WHERE store_id = :store_id AND created_at >= :since
                GROUP BY hour ORDER BY hour
            """),
            {"store_id": store_id, "since": str(since)},
        )
        return {r.hour: float(r.order_count) for r in result.fetchall()}

    async def _fetch_historical_avg(self, store_id: str, analysis_date: date) -> Dict[int, float]:
        since = analysis_date - timedelta(days=30)
        weekday = analysis_date.weekday()
        result = await self._session.execute(
            sa.text("""
                SELECT EXTRACT(HOUR FROM created_at)::int AS hour,
                       AVG(daily_count)::float AS avg_count
                FROM (
                    SELECT DATE_TRUNC('hour', created_at) AS created_at,
                           COUNT(*) AS daily_count
                    FROM orders
                    WHERE store_id = :store_id AND created_at >= :since
                      AND EXTRACT(DOW FROM created_at) = :weekday
                    GROUP BY DATE_TRUNC('hour', created_at)
                ) sub
                GROUP BY hour ORDER BY hour
            """),
            {"store_id": store_id, "since": str(since), "weekday": weekday},
        )
        return {r.hour: float(r.avg_count) for r in result.fetchall()}

    async def _fetch_actual_shifts(self, store_id: str, analysis_date: date) -> Dict[int, int]:
        result = await self._session.execute(
            sa.text("""
                SELECT EXTRACT(HOUR FROM s.start_time)::int AS hour,
                       COUNT(*)::int AS headcount
                FROM shifts s
                JOIN schedules sc ON sc.id = s.schedule_id
                WHERE sc.store_id = :store_id AND DATE(s.start_time) = :d
                GROUP BY hour ORDER BY hour
            """),
            {"store_id": store_id, "d": str(analysis_date)},
        )
        return {r.hour: int(r.headcount) for r in result.fetchall()}
```

- [ ] **C2.2** 运行测试，全部通过:

```bash
cd apps/api-gateway
pytest tests/test_staffing_service.py -v
```

Expected: 7 passed

### Task C3: Celery 任务 + hr_agent.py 集成

**Files:**
- Modify: `apps/api-gateway/src/core/celery_tasks.py`
- Modify: `apps/api-gateway/src/core/celery_app.py`
- Modify: `apps/api-gateway/src/agents/hr_agent.py`

- [ ] **C3.1** 在 `celery_tasks.py` 末尾追加排班分析任务:

```python
@celery_app.task(name="hr.trigger_staffing_analysis_weekly")
def trigger_staffing_analysis_weekly():
    """每周一 06:00 UTC — 遍历所有 active store，生成排班诊断存入 Redis。"""
    import asyncio
    from datetime import date

    async def _run():
        import redis as redis_lib
        from src.core.config import settings
        from src.core.database import AsyncSessionLocal
        from src.services.hr.staffing_service import StaffingService

        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=False)
        today = date.today()

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                sa.text("SELECT id FROM stores WHERE is_active = TRUE")
            )
            store_ids = [str(row[0]) for row in res.fetchall()]

        for store_id in store_ids:
            async with AsyncSessionLocal() as session:
                svc = StaffingService(session=session, redis_client=r)
                d = await svc.diagnose_staffing(store_id, today)
                logger.info("celery.hr_staffing_weekly", store_id=store_id,
                            peak_hours=d.get("peak_hours"), savings=d.get("estimated_savings_yuan"))

    asyncio.run(_run())
```

- [ ] **C3.2** 在 `celery_app.py` beat_schedule 添加:

```python
"hr-staffing-analysis-weekly": {
    "task": "hr.trigger_staffing_analysis_weekly",
    "schedule": crontab(hour=6, minute=0, day_of_week=1),  # Monday 06:00 UTC
    "options": {"priority": 3},
},
```

- [ ] **C3.3** 在 `hr_agent.py` 中，**删除** `_diagnose_staffing_placeholder` 方法，**添加** `_diagnose_staffing`:

```python
async def _diagnose_staffing(self, store_id: str, session) -> HRDiagnosis:
    """WF-2: 排班健康度诊断 — 调用 StaffingService."""
    import os
    from datetime import date

    redis_client = None
    try:
        import redis as redis_lib
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        redis_client = redis_lib.from_url(redis_url, decode_responses=False)
    except Exception:
        pass

    from src.services.hr.staffing_service import StaffingService
    svc = StaffingService(session=session, redis_client=redis_client)
    d = await svc.diagnose_staffing(store_id, date.today())

    peak = d.get("peak_hours", [])
    savings = d.get("estimated_savings_yuan", 0.0)
    understaffed = d.get("understaffed_hours", [])
    overstaffed = d.get("overstaffed_hours", [])
    confidence = d.get("confidence", 0.0)

    summary = (
        f"排班诊断 (置信度{confidence:.0%})："
        f"峰值 {peak}，缺编 {understaffed}，超编 {overstaffed}，可节省 ¥{savings:.2f}"
    )
    recommendations = []
    if understaffed:
        recommendations.append({
            "action": f"在 {understaffed} 时段增加排班",
            "expected_yuan": 0.0,
            "confidence": confidence,
            "source": "staffing_service",
        })
    if savings > 0:
        recommendations.append({
            "action": f"减少 {overstaffed} 超编，可节省 ¥{savings:.2f}",
            "expected_yuan": savings,
            "confidence": confidence,
            "source": "staffing_service",
        })

    return HRDiagnosis(
        intent="staffing", store_id=store_id,
        summary=summary, recommendations=recommendations,
    )
```

- [ ] **C3.4** 更新 `diagnose()` 中 staffing 分支:

```python
elif intent == "staffing":
    return await self._diagnose_staffing(store_id, session)
```

- [ ] **C3.5** 语法验证:

```bash
cd apps/api-gateway
python3 -c "from src.agents.hr_agent import HRAgentV1; print('OK')"
```

Expected: `OK`

### Task C4: 全量测试 + 提交

- [ ] **C4.1** 运行所有 M3 新增测试:

```bash
cd apps/api-gateway
pytest tests/test_z56_fk_migration.py tests/test_retention_ml_service.py tests/test_staffing_service.py -v
```

Expected: 20 passed, 0 failed

- [ ] **C4.2** 确认 HR 相关测试无回归:

```bash
cd apps/api-gateway
pytest tests/ -k "hr" -v 2>&1 | tail -15
```

Expected: 全部通过

- [ ] **C4.3** 提交 Chunk C:

```bash
git add apps/api-gateway/src/services/hr/staffing_service.py \
        apps/api-gateway/src/core/celery_tasks.py \
        apps/api-gateway/src/core/celery_app.py \
        apps/api-gateway/src/agents/hr_agent.py \
        apps/api-gateway/tests/test_staffing_service.py
git commit -m "feat(hr): M3 Chunk C — StaffingService WF-2排班优化 + HRAgent集成"
```

---

## 最终验收

- [ ] 全量运行 M3 测试:

```bash
cd apps/api-gateway
pytest tests/test_z56_fk_migration.py tests/test_retention_ml_service.py tests/test_staffing_service.py -v --tb=short
```

Expected: 20 passed

- [ ] 前端构建确认无新增 TS 错误 (M3 不涉及前端变更):

```bash
cd apps/web && pnpm run build 2>&1 | tail -5
```
