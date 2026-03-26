"""
赠菜/试吃/招待审批管理服务 - 测试
"""

import pytest
from datetime import date, datetime, timedelta

from src.services.complimentary_service import (
    ApprovalStatus,
    ComplimentaryReason,
    ComplimentaryRequest,
    ComplimentaryService,
)


@pytest.fixture
def service():
    return ComplimentaryService()


@pytest.fixture
def sample_request(service):
    """创建一个标准赠菜申请"""
    return service.create_request(
        order_id="order-001",
        dish_id="dish-001",
        dish_name="宫保鸡丁",
        quantity=1,
        cost_fen=1500,
        reason=ComplimentaryReason.COMPLAINT,
        requester_id="user-001",
    )


class TestCreateRequest:
    def test_create_basic(self, service):
        req = service.create_request(
            order_id="order-001",
            dish_id="dish-001",
            dish_name="宫保鸡丁",
            quantity=1,
            cost_fen=1500,
            reason=ComplimentaryReason.COMPLAINT,
            requester_id="user-001",
        )
        assert req.request_id is not None
        assert req.order_id == "order-001"
        assert req.dish_name == "宫保鸡丁"
        assert req.quantity == 1
        assert req.cost_fen == 1500
        assert req.reason == ComplimentaryReason.COMPLAINT
        assert req.status == ApprovalStatus.PENDING
        assert req.total_cost_fen == 1500
        assert req.total_cost_yuan == 15.0

    def test_create_with_quantity(self, service):
        req = service.create_request(
            order_id="order-002",
            dish_id="dish-002",
            dish_name="小龙虾",
            quantity=3,
            cost_fen=5000,
            reason=ComplimentaryReason.MARKETING,
            requester_id="user-002",
        )
        assert req.total_cost_fen == 15000
        assert req.total_cost_yuan == 150.0

    def test_create_invalid_quantity(self, service):
        with pytest.raises(ValueError, match="数量必须大于0"):
            service.create_request(
                order_id="o1", dish_id="d1", dish_name="test",
                quantity=0, cost_fen=100,
                reason=ComplimentaryReason.STAFF_MEAL, requester_id="u1",
            )

    def test_create_negative_cost(self, service):
        with pytest.raises(ValueError, match="成本不能为负数"):
            service.create_request(
                order_id="o1", dish_id="d1", dish_name="test",
                quantity=1, cost_fen=-100,
                reason=ComplimentaryReason.STAFF_MEAL, requester_id="u1",
            )


class TestAutoApproveCheck:
    def test_staff_meal_auto_approved(self, service):
        req = service.create_request(
            order_id="o1", dish_id="d1", dish_name="员工套餐",
            quantity=1, cost_fen=800,
            reason=ComplimentaryReason.STAFF_MEAL, requester_id="u1",
        )
        result = service.auto_approve_check(req, daily_budget_fen=50000, daily_used_fen=0)
        assert result is True
        assert req.status == ApprovalStatus.AUTO_APPROVED

    def test_small_amount_auto_approved(self, service):
        req = service.create_request(
            order_id="o1", dish_id="d1", dish_name="凉菜",
            quantity=1, cost_fen=1000,
            reason=ComplimentaryReason.COMPLAINT, requester_id="u1",
        )
        result = service.auto_approve_check(req, daily_budget_fen=50000, daily_used_fen=0)
        assert result is True
        assert req.status == ApprovalStatus.AUTO_APPROVED

    def test_large_amount_not_auto_approved(self, service):
        req = service.create_request(
            order_id="o1", dish_id="d1", dish_name="龙虾",
            quantity=1, cost_fen=20000,
            reason=ComplimentaryReason.VIP_MAINTAIN, requester_id="u1",
        )
        result = service.auto_approve_check(req, daily_budget_fen=50000, daily_used_fen=0)
        assert result is False
        assert req.status == ApprovalStatus.PENDING

    def test_over_budget_not_auto_approved(self, service):
        """即使是员工餐，超预算也不自动通过"""
        req = service.create_request(
            order_id="o1", dish_id="d1", dish_name="员工套餐",
            quantity=1, cost_fen=800,
            reason=ComplimentaryReason.STAFF_MEAL, requester_id="u1",
        )
        result = service.auto_approve_check(req, daily_budget_fen=5000, daily_used_fen=4500)
        assert result is False

    def test_exact_threshold_not_auto_approved(self, service):
        """刚好等于2000分不自动通过（条件是严格小于）"""
        req = service.create_request(
            order_id="o1", dish_id="d1", dish_name="中等菜",
            quantity=1, cost_fen=2000,
            reason=ComplimentaryReason.COMPLAINT, requester_id="u1",
        )
        result = service.auto_approve_check(req, daily_budget_fen=50000, daily_used_fen=0)
        assert result is False


class TestApproveReject:
    def test_approve(self, service, sample_request):
        result = service.approve(sample_request, approver_id="mgr-001")
        assert result.status == ApprovalStatus.APPROVED
        assert result.approver_id == "mgr-001"
        assert result.updated_at is not None

    def test_approve_already_approved(self, service, sample_request):
        service.approve(sample_request, "mgr-001")
        with pytest.raises(ValueError, match="只能审批待处理的申请"):
            service.approve(sample_request, "mgr-002")

    def test_reject(self, service, sample_request):
        result = service.reject(sample_request, "mgr-001", "成本过高")
        assert result.status == ApprovalStatus.REJECTED
        assert result.reject_reason == "成本过高"

    def test_reject_empty_reason(self, service, sample_request):
        with pytest.raises(ValueError, match="拒绝原因不能为空"):
            service.reject(sample_request, "mgr-001", "  ")


class TestDailyComplimentary:
    def test_daily_stats(self, service):
        today = date.today()
        requests = []

        # 创建2个已通过的申请
        r1 = service.create_request(
            "o1", "d1", "宫保鸡丁", 1, 1500,
            ComplimentaryReason.COMPLAINT, "u1",
        )
        r1.status = ApprovalStatus.APPROVED
        requests.append(r1)

        r2 = service.create_request(
            "o2", "d2", "员工餐", 2, 800,
            ComplimentaryReason.STAFF_MEAL, "u2",
        )
        r2.status = ApprovalStatus.AUTO_APPROVED
        requests.append(r2)

        # 创建1个未通过的（不应计入）
        r3 = service.create_request(
            "o3", "d3", "龙虾", 1, 30000,
            ComplimentaryReason.VIP_MAINTAIN, "u3",
        )
        requests.append(r3)

        result = service.calculate_daily_complimentary(requests, today)
        assert result["approved_count"] == 2
        assert result["total_cost_fen"] == 1500 + 1600  # 1500 + 800*2
        assert result["total_cost_yuan"] == 31.0
        assert "complaint" in result["by_reason"]
        assert "staff_meal" in result["by_reason"]


class TestReport:
    def test_report_by_date_range(self, service):
        today = date.today()
        requests = []

        r1 = service.create_request(
            "o1", "d1", "菜A", 1, 1000,
            ComplimentaryReason.COMPLAINT, "u1",
        )
        r1.status = ApprovalStatus.APPROVED
        requests.append(r1)

        r2 = service.create_request(
            "o2", "d2", "菜B", 1, 2000,
            ComplimentaryReason.MARKETING, "u2",
        )
        r2.status = ApprovalStatus.APPROVED
        requests.append(r2)

        report = service.get_complimentary_report(
            requests, today, today,
        )
        assert report["total_requests"] == 2
        assert report["total_cost_fen"] == 3000
        assert report["total_cost_yuan"] == 30.0
        assert len(report["by_reason"]) == 2
        assert len(report["daily_trend"]) == 1

    def test_report_invalid_date_range(self, service):
        with pytest.raises(ValueError, match="开始日期不能晚于结束日期"):
            service.get_complimentary_report(
                [], date(2025, 12, 31), date(2025, 12, 1),
            )


class TestBudgetAlert:
    def test_no_alert_under_80(self, service):
        result = service.check_budget_alert(3000, 10000)
        assert result is None

    def test_warning_at_80_percent(self, service):
        result = service.check_budget_alert(8000, 10000)
        assert result is not None
        assert result["level"] == "warning"
        assert "即将用完" in result["message"]

    def test_critical_at_100_percent(self, service):
        result = service.check_budget_alert(12000, 10000)
        assert result is not None
        assert result["level"] == "critical"
        assert "超支" in result["message"]
        assert result["daily_used_yuan"] == 120.0
        assert result["daily_budget_yuan"] == 100.0

    def test_invalid_budget(self, service):
        with pytest.raises(ValueError, match="每日预算必须大于0"):
            service.check_budget_alert(1000, 0)
