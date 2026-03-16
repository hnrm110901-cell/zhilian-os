"""
旅程 catch-up dispatcher + orchestrator next_action_at 测试
"""
import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.journey_orchestrator import (
    BUILTIN_JOURNEYS,
    JourneyOrchestrator,
    evaluate_condition,
)


# ── Fake DB helpers ──


class FakeRow:
    """模拟 SQLAlchemy Row"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getitem__(self, idx):
        return list(self.__dict__.values())[idx]


class FakeResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or ([] if row is None else [row])

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._row


class FakeSession:
    """模拟 AsyncSession，记录所有 SQL 调用"""

    def __init__(self, results=None):
        self._results = results or []
        self._call_idx = 0
        self.executed = []
        self.committed = False

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        if self._call_idx < len(self._results):
            r = self._results[self._call_idx]
            self._call_idx += 1
            return r
        return FakeResult()

    async def commit(self):
        self.committed = True


# ── orchestrator.trigger() 设置 next_action_at 测试 ──


@pytest.mark.asyncio
async def test_trigger_sets_next_action_at():
    """trigger() 应在 INSERT 中设置 next_action_at 为 now + step[0].delay_minutes"""
    db = FakeSession(results=[FakeResult()])  # INSERT 返回

    # mock celery task
    with patch("src.services.journey_orchestrator.JourneyOrchestrator.trigger") as _:
        pass

    orchestrator = JourneyOrchestrator()

    # Patch celery import inside trigger to avoid actual scheduling
    mock_task = MagicMock()
    mock_task.apply_async = MagicMock()
    with patch.dict("sys.modules", {"src.core.celery_tasks": MagicMock(execute_journey_step=mock_task)}):
        with patch("src.services.journey_orchestrator.JourneyOrchestrator.trigger.__module__", create=True):
            result = await orchestrator.trigger(
                customer_id="C001",
                store_id="S001",
                journey_id="member_activation",
                db=db,
            )

    assert "journey_db_id" in result
    assert result["total_steps"] == 3

    # 检查 INSERT SQL 包含 next_action_at
    insert_sql, insert_params = db.executed[0]
    assert "next_action_at" in insert_sql
    assert "next_action_at" in insert_params


@pytest.mark.asyncio
async def test_trigger_first_step_immediate():
    """member_activation 第一步 delay=0，next_action_at 应接近 now"""
    db = FakeSession(results=[FakeResult()])

    orchestrator = JourneyOrchestrator()
    mock_task = MagicMock()
    mock_task.apply_async = MagicMock()

    with patch.dict("sys.modules", {"src.core.celery_tasks": MagicMock(execute_journey_step=mock_task)}):
        result = await orchestrator.trigger(
            customer_id="C001",
            store_id="S001",
            journey_id="member_activation",
            db=db,
        )

    _, insert_params = db.executed[0]
    next_at = insert_params["next_action_at"]
    # delay_minutes=0，所以 next_action_at 应该在几秒内
    assert (next_at - datetime.utcnow()).total_seconds() < 5


# ── orchestrator.execute_step() 设置 next_action_at 测试 ──


@pytest.mark.asyncio
async def test_execute_step_sets_next_action_at_for_next_step():
    """执行 step 0 后，应为 step 1 设置 next_action_at"""
    journey_db_id = str(uuid.uuid4())

    journey_row = FakeRow(
        id=journey_db_id,
        journey_type="member_activation",
        customer_id="C001",
        store_id="S001",
        status="running",
        started_at=datetime.utcnow() - timedelta(minutes=5),
        step_history=[],
    )
    orders_row = FakeRow(cnt=0)

    # execute_step 执行顺序：
    # 1. SELECT journey
    # 2. SELECT COUNT orders
    # 3. SELECT member profile (Redis miss 后 DB fallback)
    # 4. UPDATE journey
    db = FakeSession(results=[
        FakeResult(row=journey_row),
        FakeResult(row=orders_row),
        FakeResult(),  # member profile (无记录)
        FakeResult(),  # UPDATE
    ])

    orchestrator = JourneyOrchestrator()
    result = await orchestrator.execute_step(
        journey_db_id, 0, db,
    )

    assert result["step_id"] == "welcome"
    assert result["executed"] is True

    # 找到 UPDATE 语句（包含 next_action_at）
    update_calls = [
        (sql, params) for sql, params in db.executed
        if "UPDATE" in str(sql) and "next_action_at" in str(sql)
    ]
    assert len(update_calls) == 1
    _, update_params = update_calls[0]
    assert update_params["next_action_at"] is not None
    # member_activation step 1 delay = 1440 min (1 day)
    expected_delay = timedelta(minutes=1440)
    actual_delay = update_params["next_action_at"] - datetime.utcnow()
    assert abs(actual_delay.total_seconds() - expected_delay.total_seconds()) < 10


@pytest.mark.asyncio
async def test_execute_last_step_clears_next_action_at():
    """执行最后一步后，next_action_at 应为 None，status 应为 completed"""
    journey_db_id = str(uuid.uuid4())

    journey_row = FakeRow(
        id=journey_db_id,
        journey_type="member_activation",
        customer_id="C001",
        store_id="S001",
        status="running",
        started_at=datetime.utcnow() - timedelta(days=4),
        step_history=[
            {"step_index": 0, "executed": True},
            {"step_index": 1, "executed": False, "skipped_reason": "条件不满足"},
        ],
    )
    orders_row = FakeRow(cnt=0)

    db = FakeSession(results=[
        FakeResult(row=journey_row),
        FakeResult(row=orders_row),
        FakeResult(),  # member profile
        FakeResult(),  # UPDATE
    ])

    orchestrator = JourneyOrchestrator()
    result = await orchestrator.execute_step(
        journey_db_id, 2, db,
    )

    assert result["step_id"] == "first_visit_offer"

    update_calls = [
        (sql, params) for sql, params in db.executed
        if "UPDATE" in str(sql) and "next_action_at" in str(sql)
    ]
    assert len(update_calls) == 1
    _, update_params = update_calls[0]
    assert update_params["next_action_at"] is None
    assert update_params["status"] == "completed"
    assert update_params["completed_at"] is not None


# ── evaluate_condition 测试 ──


def test_evaluate_condition_none():
    assert evaluate_condition(None, 0) is True
    assert evaluate_condition(None, 5) is True


def test_evaluate_condition_event_not_exist():
    assert evaluate_condition({"event_not_exist": "order_pay"}, 0) is True
    assert evaluate_condition({"event_not_exist": "order_pay"}, 1) is False


def test_evaluate_condition_unknown():
    assert evaluate_condition({"unknown_type": "foo"}, 0) is True
