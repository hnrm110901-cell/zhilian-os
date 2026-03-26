"""
等位叫号与排队预估服务 - 测试
"""

import pytest
from datetime import datetime, timedelta

from src.services.queue_management_service import (
    QueueGroup,
    QueueManagementService,
    QueueStatus,
    QueueTicket,
)


@pytest.fixture
def service():
    return QueueManagementService()


class TestTakeNumber:
    def test_take_number_small_table(self, service):
        ticket = service.take_number(2, "张三", "13800000001")
        assert ticket.ticket_no == "S001"
        assert ticket.group == QueueGroup.SMALL_TABLE
        assert ticket.party_size == 2
        assert ticket.customer_name == "张三"
        assert ticket.customer_phone == "13800000001"
        assert ticket.status == QueueStatus.WAITING

    def test_take_number_medium_table(self, service):
        ticket = service.take_number(3, "李四")
        assert ticket.ticket_no == "M001"
        assert ticket.group == QueueGroup.MEDIUM_TABLE

    def test_take_number_large_table(self, service):
        ticket = service.take_number(6, "王五")
        assert ticket.ticket_no == "L001"
        assert ticket.group == QueueGroup.LARGE_TABLE

    def test_take_number_private_room(self, service):
        ticket = service.take_number(10, "赵六")
        assert ticket.ticket_no == "P001"
        assert ticket.group == QueueGroup.PRIVATE_ROOM

    def test_take_number_sequential(self, service):
        t1 = service.take_number(2, "A")
        t2 = service.take_number(2, "B")
        assert t1.ticket_no == "S001"
        assert t2.ticket_no == "S002"

    def test_take_number_invalid_party_size(self, service):
        with pytest.raises(ValueError, match="就餐人数必须大于0"):
            service.take_number(0, "test")

    def test_take_number_empty_name(self, service):
        with pytest.raises(ValueError, match="顾客姓名不能为空"):
            service.take_number(2, "  ")

    def test_auto_group_boundary(self, service):
        """边界值：1人→小桌，4人→中桌，8人→大桌，9人→包厢"""
        t1 = service.take_number(1, "一人")
        assert t1.group == QueueGroup.SMALL_TABLE

        t4 = service.take_number(4, "四人")
        assert t4.group == QueueGroup.MEDIUM_TABLE

        t8 = service.take_number(8, "八人")
        assert t8.group == QueueGroup.LARGE_TABLE

        t9 = service.take_number(9, "九人")
        assert t9.group == QueueGroup.PRIVATE_ROOM


class TestCallNext:
    def test_call_next(self, service):
        service.take_number(2, "张三")
        service.take_number(2, "李四")

        called = service.call_next(QueueGroup.SMALL_TABLE)
        assert called is not None
        assert called.customer_name == "张三"
        assert called.status == QueueStatus.CALLED
        assert called.called_at is not None

    def test_call_next_empty(self, service):
        result = service.call_next(QueueGroup.SMALL_TABLE)
        assert result is None

    def test_call_next_respects_group(self, service):
        service.take_number(2, "小桌客")
        service.take_number(4, "中桌客")

        called = service.call_next(QueueGroup.MEDIUM_TABLE)
        assert called.customer_name == "中桌客"


class TestMarkSeated:
    def test_mark_seated_from_called(self, service):
        ticket = service.take_number(2, "张三")
        service.call_next(QueueGroup.SMALL_TABLE)

        seated = service.mark_seated(ticket.ticket_no)
        assert seated.status == QueueStatus.SEATED
        assert seated.seated_at is not None

    def test_mark_seated_from_waiting(self, service):
        """等待中也可以直接入座（如VIP直接带位）"""
        ticket = service.take_number(2, "张三")
        seated = service.mark_seated(ticket.ticket_no)
        assert seated.status == QueueStatus.SEATED

    def test_mark_seated_invalid_ticket(self, service):
        with pytest.raises(ValueError, match="票号不存在"):
            service.mark_seated("INVALID")

    def test_mark_seated_already_expired(self, service):
        ticket = service.take_number(2, "张三")
        service.mark_expired(ticket.ticket_no)
        with pytest.raises(ValueError, match="只有等待中或已叫号的票据可以入座"):
            service.mark_seated(ticket.ticket_no)


class TestMarkExpired:
    def test_mark_expired(self, service):
        ticket = service.take_number(2, "张三")
        expired = service.mark_expired(ticket.ticket_no)
        assert expired.status == QueueStatus.EXPIRED
        assert expired.expired_at is not None


class TestEstimateWaitTime:
    def test_estimate_basic(self, service):
        service.take_number(2, "A")
        service.take_number(2, "B")
        service.take_number(2, "C")

        result = service.estimate_wait_time(QueueGroup.SMALL_TABLE, 30.0)
        assert result["waiting_count"] == 3
        assert result["estimated_minutes"] == 90
        assert "1小时30分钟" in result["estimated_display"]

    def test_estimate_no_wait(self, service):
        result = service.estimate_wait_time(QueueGroup.SMALL_TABLE, 30.0)
        assert result["waiting_count"] == 0
        assert result["estimated_minutes"] == 0
        assert "无需等位" in result["estimated_display"]

    def test_estimate_invalid_turnover(self, service):
        with pytest.raises(ValueError, match="翻台时间必须大于0"):
            service.estimate_wait_time(QueueGroup.SMALL_TABLE, 0)

    def test_estimate_with_external_queue(self, service):
        """使用外部队列估算"""
        external = [
            QueueTicket(
                ticket_no="S001", group=QueueGroup.SMALL_TABLE,
                party_size=2, customer_name="A", customer_phone=None,
                status=QueueStatus.WAITING,
            ),
            QueueTicket(
                ticket_no="S002", group=QueueGroup.SMALL_TABLE,
                party_size=2, customer_name="B", customer_phone=None,
                status=QueueStatus.WAITING,
            ),
        ]
        result = service.estimate_wait_time(
            QueueGroup.SMALL_TABLE, 20.0, queue=external,
        )
        assert result["waiting_count"] == 2
        assert result["estimated_minutes"] == 40


class TestGetQueueStatus:
    def test_queue_status(self, service):
        service.take_number(2, "小A")
        service.take_number(2, "小B")
        service.take_number(4, "中A")

        status = service.get_queue_status()
        assert status["total_waiting"] == 3
        assert status["groups"]["small_table"]["waiting_count"] == 2
        assert status["groups"]["medium_table"]["waiting_count"] == 1
        assert status["groups"]["large_table"]["waiting_count"] == 0


class TestVipSkip:
    def test_vip_skip(self, service):
        service.take_number(2, "普通客A")
        service.take_number(2, "普通客B")
        vip_ticket = service.take_number(2, "VIP客户")

        service.skip_to_vip(vip_ticket.ticket_no)

        # VIP应该排在最前面
        called = service.call_next(QueueGroup.SMALL_TABLE)
        assert called.customer_name == "VIP客户"
        assert called.is_vip is True

    def test_vip_skip_invalid_status(self, service):
        ticket = service.take_number(2, "张三")
        service.mark_expired(ticket.ticket_no)
        with pytest.raises(ValueError, match="只有等待中的票据可以VIP插队"):
            service.skip_to_vip(ticket.ticket_no)


class TestSendCallNotification:
    def test_notification_content(self, service):
        ticket = service.take_number(2, "张三", "13800000001")
        service.call_next(QueueGroup.SMALL_TABLE)

        notification = service.send_call_notification(ticket)
        assert notification["ticket_no"] == "S001"
        assert notification["customer_name"] == "张三"
        assert notification["customer_phone"] == "13800000001"
        assert "叫号通知" in notification["message"]
        assert "张三" in notification["message"]
        assert "S001" in notification["message"]
        assert "小桌(2人)" in notification["message"]


class TestAutoExpireCheck:
    def test_auto_expire(self, service):
        ticket = service.take_number(2, "张三")
        # 将创建时间改为3小时前
        ticket.created_at = datetime.utcnow() - timedelta(hours=3)

        expired = service.auto_expire_check(max_wait_minutes=120)
        assert len(expired) == 1
        assert expired[0].ticket_no == ticket.ticket_no
        assert expired[0].status == QueueStatus.EXPIRED

    def test_auto_expire_not_expired(self, service):
        service.take_number(2, "张三")
        expired = service.auto_expire_check(max_wait_minutes=120)
        assert len(expired) == 0

    def test_auto_expire_invalid_max_wait(self, service):
        with pytest.raises(ValueError, match="最大等待时间必须大于0"):
            service.auto_expire_check(max_wait_minutes=0)


class TestCancelTicket:
    def test_cancel(self, service):
        ticket = service.take_number(2, "张三")
        cancelled = service.cancel_ticket(ticket.ticket_no)
        assert cancelled.status == QueueStatus.CANCELLED
        assert cancelled.cancelled_at is not None

    def test_cancel_non_waiting(self, service):
        ticket = service.take_number(2, "张三")
        service.call_next(QueueGroup.SMALL_TABLE)
        with pytest.raises(ValueError, match="只有等待中的票据可以取消"):
            service.cancel_ticket(ticket.ticket_no)
