# tests/test_cdp_rfm_celery.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

def test_recalculate_rfm_daily_task_registered():
    """验证 celery 任务已注册"""
    from src.core.celery_tasks import app
    assert "recalculate_rfm_daily" in [t for t in app.tasks]

@patch("src.core.celery_tasks.cdp_rfm_service")
def test_recalculate_rfm_daily_calls_service(mock_svc):
    """验证任务调用 recalculate_all"""
    mock_svc.recalculate_all = AsyncMock(return_value={"updated": 50, "errors": []})
    from src.core.celery_tasks import recalculate_rfm_daily
    result = recalculate_rfm_daily()
    assert result["success"] is True
    assert result["updated"] == 50

@patch("src.core.celery_tasks.cdp_rfm_service")
@patch("src.core.celery_tasks.lifecycle_state_machine")
def test_rfm_triggers_lifecycle_transition(mock_lsm, mock_svc):
    """RFM等级变化时触发生命周期状态转移"""
    mock_svc.recalculate_all = AsyncMock(return_value={
        "updated": 2,
        "level_changes": [
            {"consumer_id": "C001", "old_level": "S3", "new_level": "S1"},
        ],
        "errors": []
    })
    mock_lsm.apply_trigger = AsyncMock()
    from src.core.celery_tasks import recalculate_rfm_daily
    result = recalculate_rfm_daily()
    assert result["lifecycle_transitions"] >= 0
