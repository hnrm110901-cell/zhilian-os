"""
定时报表执行器 + 邮件附件投递测试
"""
from email.mime.multipart import MIMEMultipart
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 邮件附件支持测试 ──


class TestEmailAttachmentSupport:
    """测试 EmailNotificationHandler 附件功能"""

    @pytest.mark.asyncio
    async def test_send_with_attachment(self):
        """带附件的邮件应包含 MIMEBase 附件部分"""
        from src.services.multi_channel_notification import EmailNotificationHandler

        handler = EmailNotificationHandler()

        # Mock SMTP 配置和发送
        with patch("src.services.multi_channel_notification.email_config") as mock_cfg:
            mock_cfg.SMTP_PASSWORD = "test_pass"
            mock_cfg.SMTP_FROM_NAME = "屯象OS"
            mock_cfg.SMTP_USER = "test@example.com"
            mock_cfg.SMTP_HOST = "smtp.example.com"
            mock_cfg.SMTP_PORT = 587
            mock_cfg.SMTP_USE_TLS = True
            mock_cfg.SMTP_TIMEOUT = 30

            # Capture the message object
            captured_msg = {}

            def fake_send_sync(msg, recipient):
                captured_msg["msg"] = msg
                captured_msg["recipient"] = recipient

            handler._send_email_sync = fake_send_sync

            result = await handler.send(
                recipient="boss@restaurant.com",
                title="周报附件",
                content="请查看附件中的周报。",
                extra_data={
                    "attachments": [
                        {"filename": "weekly_report.xlsx", "data": b"\x00\x01\x02"},
                    ],
                },
            )

        assert result is True
        msg = captured_msg["msg"]
        assert msg.get_content_type() == "multipart/mixed"

        # 检查附件
        payloads = msg.get_payload()
        attachment_parts = [
            p for p in payloads
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachment_parts) == 1
        assert "weekly_report.xlsx" in attachment_parts[0]["Content-Disposition"]

    @pytest.mark.asyncio
    async def test_send_without_attachment_uses_alternative(self):
        """无附件的邮件应使用 multipart/alternative"""
        from src.services.multi_channel_notification import EmailNotificationHandler

        handler = EmailNotificationHandler()

        with patch("src.services.multi_channel_notification.email_config") as mock_cfg:
            mock_cfg.SMTP_PASSWORD = "test_pass"
            mock_cfg.SMTP_FROM_NAME = "屯象OS"
            mock_cfg.SMTP_USER = "test@example.com"
            mock_cfg.SMTP_HOST = "smtp.example.com"
            mock_cfg.SMTP_PORT = 587
            mock_cfg.SMTP_USE_TLS = True
            mock_cfg.SMTP_TIMEOUT = 30

            captured = {}
            handler._send_email_sync = lambda msg, r: captured.update(msg=msg)

            await handler.send(
                recipient="boss@restaurant.com",
                title="纯文本通知",
                content="无附件",
            )

        assert captured["msg"].get_content_type() == "multipart/alternative"

    @pytest.mark.asyncio
    async def test_send_with_multiple_attachments(self):
        """支持多个附件"""
        from src.services.multi_channel_notification import EmailNotificationHandler

        handler = EmailNotificationHandler()

        with patch("src.services.multi_channel_notification.email_config") as mock_cfg:
            mock_cfg.SMTP_PASSWORD = "test_pass"
            mock_cfg.SMTP_FROM_NAME = "屯象OS"
            mock_cfg.SMTP_USER = "test@example.com"
            mock_cfg.SMTP_HOST = "smtp.example.com"
            mock_cfg.SMTP_PORT = 587
            mock_cfg.SMTP_USE_TLS = True
            mock_cfg.SMTP_TIMEOUT = 30

            captured = {}
            handler._send_email_sync = lambda msg, r: captured.update(msg=msg)

            await handler.send(
                recipient="boss@restaurant.com",
                title="多附件报表",
                content="两个附件",
                extra_data={
                    "attachments": [
                        {"filename": "report.xlsx", "data": b"\x00"},
                        {"filename": "report.pdf", "data": b"\x01"},
                    ],
                },
            )

        payloads = captured["msg"].get_payload()
        attachment_parts = [
            p for p in payloads
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachment_parts) == 2

    @pytest.mark.asyncio
    async def test_send_skips_without_smtp_config(self):
        """SMTP 未配置时跳过发送"""
        from src.services.multi_channel_notification import EmailNotificationHandler

        handler = EmailNotificationHandler()

        with patch("src.services.multi_channel_notification.email_config") as mock_cfg:
            mock_cfg.SMTP_PASSWORD = ""  # 未配置

            result = await handler.send(
                recipient="boss@restaurant.com",
                title="test",
                content="test",
            )

        assert result is False


# ── _calc_next_run 测试（确保执行器正确计算下次运行时间）──


class TestCalcNextRun:

    def test_daily_schedule(self):
        from src.services.custom_report_service import custom_report_service

        result = custom_report_service._calc_next_run("daily", "06:00", None, None)
        assert "T06:00:00" in result

    def test_weekly_schedule(self):
        from src.services.custom_report_service import custom_report_service

        result = custom_report_service._calc_next_run("weekly", "10:00", 4, None)  # Friday
        assert "T10:00:00" in result

    def test_monthly_schedule(self):
        from src.services.custom_report_service import custom_report_service

        result = custom_report_service._calc_next_run("monthly", "08:00", None, 1)
        assert "T08:00:00" in result
