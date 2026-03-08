import io
import json
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

for _k, _v in {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

from src.api.mobile import (  # noqa: E402
    TaskSubmitPayload,
    mobile_task_submit,
    mobile_task_upload_evidence,
)
from src.models.task import TaskStatus  # noqa: E402


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.store_id = "store-123"
    user.username = "tester"
    user.full_name = "Tester"
    return user


def _mock_db_with_task(task: MagicMock):
    result = SimpleNamespace(scalar_one_or_none=lambda: task)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock(return_value=None)
    return db


@pytest.mark.asyncio
async def test_mobile_task_submit_requires_evidence_for_inspection():
    task = MagicMock()
    task.id = uuid.uuid4()
    task.store_id = "store-123"
    task.title = "开档巡检"
    task.category = "inspection"
    task.status = TaskStatus.PENDING
    task.result = None
    task.attachments = None
    task.is_deleted = "false"

    db = _mock_db_with_task(task)
    user = _mock_user()

    result = await mobile_task_submit(str(task.id), TaskSubmitPayload(), user, db)

    assert result.ok is False
    assert "要求证据" in result.message
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mobile_task_submit_sets_completed_and_merges_attachments():
    task = MagicMock()
    task.id = uuid.uuid4()
    task.store_id = "store-123"
    task.title = "库存盘点"
    task.category = "ops"
    task.status = TaskStatus.IN_PROGRESS
    task.result = None
    task.attachments = json.dumps(["old.jpg"], ensure_ascii=False)
    task.is_deleted = "false"

    db = _mock_db_with_task(task)
    user = _mock_user()

    payload = TaskSubmitPayload(
        evidence_note="已完成盘点",
        evidence_files=["new-1.jpg", "new-2.jpg"],
    )
    result = await mobile_task_submit(str(task.id), payload, user, db)

    assert result.ok is True
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "已完成盘点"
    assert task.completed_at is not None
    assert json.loads(task.attachments) == ["old.jpg", "new-1.jpg", "new-2.jpg"]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mobile_task_upload_evidence_returns_file_url_and_persists_name(monkeypatch):
    monkeypatch.setenv("MOBILE_EVIDENCE_BASE_URL", "https://cdn.zhilian.test/evidence")

    task = MagicMock()
    task.id = uuid.uuid4()
    task.store_id = "store-123"
    task.title = "服务抽检"
    task.category = "service"
    task.status = TaskStatus.IN_PROGRESS
    task.attachments = json.dumps(["base.jpg"], ensure_ascii=False)
    task.is_deleted = "false"

    db = _mock_db_with_task(task)
    user = _mock_user()
    file = UploadFile(filename="proof.jpg", file=io.BytesIO(b"fake-image"))

    resp = await mobile_task_upload_evidence(str(task.id), file, user, db)

    assert resp["ok"] is True
    assert resp["file_name"] == "proof.jpg"
    assert resp["file_url"] == "https://cdn.zhilian.test/evidence/proof.jpg"
    assert json.loads(task.attachments) == ["base.jpg", "proof.jpg"]
    db.commit.assert_awaited_once()
