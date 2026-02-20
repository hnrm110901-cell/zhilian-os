"""
Tests for MemberService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.member_service import MemberService


@pytest.fixture
def member_service():
    """Create a MemberService instance for testing"""
    return MemberService()


@pytest.fixture
def mock_adapter():
    """Create a mock adapter"""
    adapter = AsyncMock()
    return adapter


@pytest.fixture
def sample_member_data():
    """Sample member data for testing"""
    return {
        "cardNo": "M001",
        "mobile": "13800138000",
        "name": "测试会员",
        "sex": 1,
        "birthday": "1990-01-01",
        "balance": 10000,
        "points": 500
    }


class TestGetAdapter:
    """Tests for _get_adapter method"""

    def test_get_adapter_not_available(self, member_service):
        """Test getting adapter when not available"""
        with patch("src.services.member_service.AOQIWEI_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="AoqiweiAdapter is not available"):
                member_service._get_adapter()

    def test_get_adapter_creates_instance(self, member_service):
        """Test adapter instance creation"""
        with patch("src.services.member_service.AOQIWEI_AVAILABLE", True):
            with patch("src.services.member_service.AoqiweiAdapter") as mock_adapter_class:
                mock_adapter_instance = MagicMock()
                mock_adapter_class.return_value = mock_adapter_instance

                adapter = member_service._get_adapter()

                assert adapter == mock_adapter_instance
                mock_adapter_class.assert_called_once()

    def test_get_adapter_reuses_instance(self, member_service):
        """Test adapter instance is reused"""
        with patch("src.services.member_service.AOQIWEI_AVAILABLE", True):
            with patch("src.services.member_service.AoqiweiAdapter") as mock_adapter_class:
                mock_adapter_instance = MagicMock()
                mock_adapter_class.return_value = mock_adapter_instance

                adapter1 = member_service._get_adapter()
                adapter2 = member_service._get_adapter()

                assert adapter1 == adapter2
                mock_adapter_class.assert_called_once()


class TestQueryMember:
    """Tests for query_member method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_query_member_by_card_no(self, member_service, mock_adapter, sample_member_data):
        """Test querying member by card number"""
        mock_adapter.query_member.return_value = sample_member_data
        member_service._adapter = mock_adapter

        result = await member_service.query_member(card_no="M001")

        assert result["cardNo"] == "M001"
        mock_adapter.query_member.assert_called_once_with(
            card_no="M001", mobile=None, openid=None
        )

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_query_member_by_mobile(self, member_service, mock_adapter, sample_member_data):
        """Test querying member by mobile"""
        mock_adapter.query_member.return_value = sample_member_data
        member_service._adapter = mock_adapter

        result = await member_service.query_member(mobile="13800138000")

        assert result["mobile"] == "13800138000"
        mock_adapter.query_member.assert_called_once_with(
            card_no=None, mobile="13800138000", openid=None
        )

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_query_member_by_openid(self, member_service, mock_adapter, sample_member_data):
        """Test querying member by openid"""
        mock_adapter.query_member.return_value = sample_member_data
        member_service._adapter = mock_adapter

        result = await member_service.query_member(openid="wx_openid_123")

        assert result is not None
        mock_adapter.query_member.assert_called_once_with(
            card_no=None, mobile=None, openid="wx_openid_123"
        )


class TestAddMember:
    """Tests for add_member method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_add_member_success(self, member_service, mock_adapter, sample_member_data):
        """Test successfully adding a member"""
        mock_adapter.add_member.return_value = sample_member_data
        member_service._adapter = mock_adapter

        result = await member_service.add_member(
            mobile="13800138000",
            name="测试会员",
            sex=1,
            birthday="1990-01-01"
        )

        assert result["name"] == "测试会员"
        mock_adapter.add_member.assert_called_once_with(
            mobile="13800138000",
            name="测试会员",
            sex=1,
            birthday="1990-01-01",
            card_type=1,
            store_id=None
        )

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_add_member_with_store_id(self, member_service, mock_adapter, sample_member_data):
        """Test adding member with store ID"""
        mock_adapter.add_member.return_value = sample_member_data
        member_service._adapter = mock_adapter

        result = await member_service.add_member(
            mobile="13800138000",
            name="测试会员",
            store_id="STORE001"
        )

        assert result is not None
        mock_adapter.add_member.assert_called_once()
        call_args = mock_adapter.add_member.call_args
        assert call_args.kwargs["store_id"] == "STORE001"


class TestUpdateMember:
    """Tests for update_member method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_update_member_success(self, member_service, mock_adapter):
        """Test successfully updating member"""
        mock_adapter.update_member.return_value = {"success": True}
        member_service._adapter = mock_adapter

        update_data = {"name": "新名字", "mobile": "13900139000"}
        result = await member_service.update_member("M001", update_data)

        assert result["success"] is True
        mock_adapter.update_member.assert_called_once_with("M001", update_data)


class TestTradePreview:
    """Tests for trade_preview method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_preview_success(self, member_service, mock_adapter):
        """Test trade preview"""
        preview_data = {
            "available_balance": 10000,
            "available_points": 500,
            "discount_amount": 1000
        }
        mock_adapter.trade_preview.return_value = preview_data
        member_service._adapter = mock_adapter

        result = await member_service.trade_preview(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=5000
        )

        assert result["available_balance"] == 10000
        mock_adapter.trade_preview.assert_called_once_with(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=5000,
            dish_list=None
        )

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_preview_with_dish_list(self, member_service, mock_adapter):
        """Test trade preview with dish list"""
        preview_data = {"available_balance": 10000}
        mock_adapter.trade_preview.return_value = preview_data
        member_service._adapter = mock_adapter

        dish_list = [
            {"dish_id": "D001", "name": "宫保鸡丁", "price": 3800, "quantity": 1}
        ]

        result = await member_service.trade_preview(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=3800,
            dish_list=dish_list
        )

        assert result is not None
        call_args = mock_adapter.trade_preview.call_args
        assert call_args.kwargs["dish_list"] == dish_list


class TestTradeSubmit:
    """Tests for trade_submit method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_submit_success(self, member_service, mock_adapter):
        """Test successful trade submission"""
        trade_data = {
            "trade_id": "T001",
            "success": True,
            "balance_after": 5000
        }
        mock_adapter.trade_submit.return_value = trade_data
        member_service._adapter = mock_adapter

        result = await member_service.trade_submit(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=5000,
            pay_type=1,
            trade_no="TN001"
        )

        assert result["success"] is True
        mock_adapter.trade_submit.assert_called_once_with(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=5000,
            pay_type=1,
            trade_no="TN001",
            discount_plan=None
        )

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_submit_with_discount_plan(self, member_service, mock_adapter):
        """Test trade submission with discount plan"""
        trade_data = {"trade_id": "T001", "success": True}
        mock_adapter.trade_submit.return_value = trade_data
        member_service._adapter = mock_adapter

        discount_plan = {"balance": 3000, "points": 200}

        result = await member_service.trade_submit(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=5000,
            pay_type=1,
            trade_no="TN001",
            discount_plan=discount_plan
        )

        assert result is not None
        call_args = mock_adapter.trade_submit.call_args
        assert call_args.kwargs["discount_plan"] == discount_plan


class TestTradeQuery:
    """Tests for trade_query method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_query_by_trade_id(self, member_service, mock_adapter):
        """Test querying trade by trade ID"""
        trades = [{"trade_id": "T001", "amount": 5000}]
        mock_adapter.trade_query.return_value = trades
        member_service._adapter = mock_adapter

        result = await member_service.trade_query(trade_id="T001")

        assert len(result) == 1
        assert result[0]["trade_id"] == "T001"
        mock_adapter.trade_query.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_query_by_card_no(self, member_service, mock_adapter):
        """Test querying trades by card number"""
        trades = [
            {"trade_id": "T001", "amount": 5000},
            {"trade_id": "T002", "amount": 3000}
        ]
        mock_adapter.trade_query.return_value = trades
        member_service._adapter = mock_adapter

        result = await member_service.trade_query(card_no="M001")

        assert len(result) == 2
        mock_adapter.trade_query.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_query_with_date_range(self, member_service, mock_adapter):
        """Test querying trades with date range"""
        trades = [{"trade_id": "T001", "amount": 5000}]
        mock_adapter.trade_query.return_value = trades
        member_service._adapter = mock_adapter

        result = await member_service.trade_query(
            card_no="M001",
            start_date="2024-01-01",
            end_date="2024-01-31"
        )

        assert len(result) == 1
        call_args = mock_adapter.trade_query.call_args
        assert call_args.kwargs["start_date"] == "2024-01-01"
        assert call_args.kwargs["end_date"] == "2024-01-31"


class TestTradeCancel:
    """Tests for trade_cancel method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_cancel_success(self, member_service, mock_adapter):
        """Test successful trade cancellation"""
        cancel_result = {"success": True, "message": "撤销成功"}
        mock_adapter.trade_cancel.return_value = cancel_result
        member_service._adapter = mock_adapter

        result = await member_service.trade_cancel("T001", "客户要求")

        assert result["success"] is True
        mock_adapter.trade_cancel.assert_called_once_with("T001", "客户要求")

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_trade_cancel_without_reason(self, member_service, mock_adapter):
        """Test trade cancellation without reason"""
        cancel_result = {"success": True}
        mock_adapter.trade_cancel.return_value = cancel_result
        member_service._adapter = mock_adapter

        result = await member_service.trade_cancel("T001")

        assert result["success"] is True
        mock_adapter.trade_cancel.assert_called_once_with("T001", "")


class TestRechargeSubmit:
    """Tests for recharge_submit method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_recharge_submit_success(self, member_service, mock_adapter):
        """Test successful recharge submission"""
        recharge_data = {
            "recharge_id": "R001",
            "success": True,
            "balance_after": 15000
        }
        mock_adapter.recharge_submit.return_value = recharge_data
        member_service._adapter = mock_adapter

        result = await member_service.recharge_submit(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=5000,
            pay_type=1,
            trade_no="TN002"
        )

        assert result["success"] is True
        assert result["balance_after"] == 15000
        mock_adapter.recharge_submit.assert_called_once_with(
            card_no="M001",
            store_id="STORE001",
            cashier="cashier01",
            amount=5000,
            pay_type=1,
            trade_no="TN002"
        )


class TestRechargeQuery:
    """Tests for recharge_query method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_recharge_query_success(self, member_service, mock_adapter):
        """Test querying recharge records"""
        recharge_data = {
            "balance": 15000,
            "records": [
                {"recharge_id": "R001", "amount": 5000, "date": "2024-01-15"}
            ]
        }
        mock_adapter.recharge_query.return_value = recharge_data
        member_service._adapter = mock_adapter

        result = await member_service.recharge_query("M001")

        assert result["balance"] == 15000
        assert len(result["records"]) == 1
        mock_adapter.recharge_query.assert_called_once_with("M001", None, None)

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_recharge_query_with_date_range(self, member_service, mock_adapter):
        """Test querying recharge records with date range"""
        recharge_data = {"balance": 15000, "records": []}
        mock_adapter.recharge_query.return_value = recharge_data
        member_service._adapter = mock_adapter

        result = await member_service.recharge_query(
            "M001",
            start_date="2024-01-01",
            end_date="2024-01-31"
        )

        assert result is not None
        mock_adapter.recharge_query.assert_called_once_with(
            "M001", "2024-01-01", "2024-01-31"
        )


class TestCouponList:
    """Tests for coupon_list method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_coupon_list_success(self, member_service, mock_adapter):
        """Test listing coupons"""
        coupons = [
            {"coupon_id": "C001", "name": "满100减20", "value": 2000},
            {"coupon_id": "C002", "name": "8折券", "discount": 0.8}
        ]
        mock_adapter.coupon_list.return_value = coupons
        member_service._adapter = mock_adapter

        result = await member_service.coupon_list("M001")

        assert len(result) == 2
        assert result[0]["coupon_id"] == "C001"
        mock_adapter.coupon_list.assert_called_once_with("M001", None)

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_coupon_list_with_store_id(self, member_service, mock_adapter):
        """Test listing coupons for specific store"""
        coupons = [{"coupon_id": "C001", "name": "满100减20"}]
        mock_adapter.coupon_list.return_value = coupons
        member_service._adapter = mock_adapter

        result = await member_service.coupon_list("M001", store_id="STORE001")

        assert len(result) == 1
        mock_adapter.coupon_list.assert_called_once_with("M001", "STORE001")

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_coupon_list_empty(self, member_service, mock_adapter):
        """Test listing coupons with no results"""
        mock_adapter.coupon_list.return_value = []
        member_service._adapter = mock_adapter

        result = await member_service.coupon_list("M001")

        assert len(result) == 0


class TestCouponUse:
    """Tests for coupon_use method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_coupon_use_success(self, member_service, mock_adapter):
        """Test successful coupon usage"""
        use_result = {
            "success": True,
            "coupon_id": "C001",
            "discount_amount": 2000
        }
        mock_adapter.coupon_use.return_value = use_result
        member_service._adapter = mock_adapter

        result = await member_service.coupon_use(
            code="CODE123",
            store_id="STORE001",
            cashier="cashier01",
            amount=10000
        )

        assert result["success"] is True
        assert result["discount_amount"] == 2000
        mock_adapter.coupon_use.assert_called_once_with(
            "CODE123", "STORE001", "cashier01", 10000
        )


class TestTestConnection:
    """Tests for test_connection method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_connection_success(self, member_service, mock_adapter):
        """Test successful connection"""
        mock_adapter.query_member.return_value = {"cardNo": "TEST001"}
        member_service._adapter = mock_adapter

        result = await member_service.test_connection()

        assert result["success"] is True
        assert result["message"] == "连接成功"
        assert result["member_card"] == "TEST001"

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_connection_failure(self, member_service, mock_adapter):
        """Test connection failure"""
        mock_adapter.query_member.side_effect = Exception("Connection error")
        member_service._adapter = mock_adapter

        result = await member_service.test_connection()

        assert result["success"] is False
        assert "error" in result


class TestClose:
    """Tests for close method"""

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_close_with_adapter(self, member_service, mock_adapter):
        """Test closing service with adapter"""
        member_service._adapter = mock_adapter

        await member_service.close()

        mock_adapter.close.assert_called_once()
        assert member_service._adapter is None

    @pytest.mark.asyncio
    @patch("src.services.member_service.AOQIWEI_AVAILABLE", True)
    async def test_close_without_adapter(self, member_service):
        """Test closing service without adapter"""
        member_service._adapter = None

        await member_service.close()

        # Should not raise any exception
        assert member_service._adapter is None
