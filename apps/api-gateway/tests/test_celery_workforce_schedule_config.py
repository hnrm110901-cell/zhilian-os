import importlib
import os
import sys
from unittest.mock import patch


def _reload_celery_app():
    module_name = "src.core.celery_app"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


class TestCeleryWorkforceScheduleConfig:
    def test_default_workforce_schedule_is_0700(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
                "L8_WORKFORCE_HOUR": "7",
                "L8_WORKFORCE_MINUTE": "0",
                "L8_AUTO_SCHEDULE_HOUR": "7",
                "L8_AUTO_SCHEDULE_MINUTE": "0",
            },
            clear=False,
        ):
            m = _reload_celery_app()
            schedule = m.celery_app.conf.beat_schedule

            advice = schedule["daily-workforce-advice"]["schedule"]
            auto = schedule["daily-auto-workforce-schedule"]["schedule"]
            assert advice.hour == {7}
            assert advice.minute == {0}
            assert auto.hour == {7}
            assert auto.minute == {0}

    def test_supports_celery_alias_env_keys(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
                "L8_WORKFORCE_HOUR": "7",
                "L8_WORKFORCE_MINUTE": "0",
                "L8_AUTO_SCHEDULE_HOUR": "7",
                "L8_AUTO_SCHEDULE_MINUTE": "0",
                "CELERY_WORKFORCE_HOUR": "8",
                "CELERY_WORKFORCE_MINUTE": "15",
                "CELERY_AUTO_SCHEDULE_HOUR": "8",
                "CELERY_AUTO_SCHEDULE_MINUTE": "20",
            },
            clear=False,
        ):
            m = _reload_celery_app()
            schedule = m.celery_app.conf.beat_schedule

            advice = schedule["daily-workforce-advice"]["schedule"]
            auto = schedule["daily-auto-workforce-schedule"]["schedule"]
            # 历史 key 优先，因此此处仍应是 L8_* 的值
            assert advice.hour == {7}
            assert advice.minute == {0}
            assert auto.hour == {7}
            assert auto.minute == {0}

    def test_invalid_workforce_env_falls_back_to_0700(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
                "L8_WORKFORCE_HOUR": "invalid",
                "L8_WORKFORCE_MINUTE": "-1",
                "L8_AUTO_SCHEDULE_HOUR": "100",
                "L8_AUTO_SCHEDULE_MINUTE": "bad",
            },
            clear=False,
        ):
            m = _reload_celery_app()
            schedule = m.celery_app.conf.beat_schedule

            advice = schedule["daily-workforce-advice"]["schedule"]
            auto = schedule["daily-auto-workforce-schedule"]["schedule"]
            assert advice.hour == {7}
            assert advice.minute == {0}
            assert auto.hour == {7}
            assert auto.minute == {0}

    def test_timezone_and_enable_utc_can_be_configured(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
                "CELERY_TIMEZONE": "Asia/Shanghai",
                "CELERY_ENABLE_UTC": "false",
            },
            clear=False,
        ):
            m = _reload_celery_app()
            assert m.celery_app.conf.timezone == "Asia/Shanghai"
            assert m.celery_app.conf.enable_utc is False
