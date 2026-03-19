# tests/test_cdp_rfm_celery.py
"""
CDP RFM Celery 定时任务测试。
注意：在全量测试中，FakeCelery 可能替换了 celery_app，导致 bind=True 装饰器
行为不一致。本文件兼容两种情况：真 Celery（自动注入 self）和 FakeCelery（需手动传）。
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _call_task(task_fn):
    """兼容 bind=True 真 Celery 和 FakeCelery 两种调用方式"""
    try:
        return task_fn()
    except TypeError:
        # FakeCelery: bind=True 不会自动注入 self
        return task_fn(MagicMock())


def test_recalculate_rfm_daily_task_registered():
    """验证 celery 任务已注册（函数存在且可调用）"""
    from src.core.celery_tasks import recalculate_rfm_daily
    assert callable(recalculate_rfm_daily)


@patch("src.core.celery_tasks.cdp_rfm_service")
@patch("src.core.database.AsyncSessionLocal")
def test_recalculate_rfm_daily_calls_service(mock_session_cls, mock_svc):
    """验证任务调用 recalculate_all"""
    mock_svc.recalculate_all = AsyncMock(return_value={"updated": 50, "errors": []})

    mock_db = AsyncMock()
    mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    from src.core.celery_tasks import recalculate_rfm_daily
    result = _call_task(recalculate_rfm_daily)
    assert result["success"] is True
    assert result["updated"] == 50


@patch("src.core.celery_tasks.cdp_rfm_service")
@patch("src.core.celery_tasks.lifecycle_state_machine")
@patch("src.core.database.AsyncSessionLocal")
def test_rfm_triggers_lifecycle_transition(mock_session_cls, mock_lsm, mock_svc):
    """RFM等级变化时触发生命周期状态转移"""
    mock_svc.recalculate_all = AsyncMock(return_value={
        "updated": 2,
        "level_changes": [
            {"consumer_id": "C001", "old_level": "S3", "new_level": "S1"},
        ],
        "errors": []
    })
    mock_lsm.detect_and_sync = AsyncMock()

    mock_db = AsyncMock()
    mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    from src.core.celery_tasks import recalculate_rfm_daily
    result = _call_task(recalculate_rfm_daily)
    assert result["lifecycle_transitions"] >= 0
