"""
预定宴会Agent测试 - Reservation & Banquet Agent Tests

测试覆盖 Test Coverage:
1. 预定管理 - Reservation management
2. 宴会管理 - Banquet management
3. 座位分配 - Seating allocation
4. 提醒通知 - Notification services
5. 统计分析 - Analytics and reporting
"""

import pytest
from datetime import datetime, timedelta
from src.agent import (
    ReservationAgent,
    ReservationType,
    ReservationStatus,
    BanquetType,
    TableType,
    NotificationType
)


@pytest.fixture
def agent():
    """创建测试用的Agent实例"""
    return ReservationAgent(
        store_id="STORE001",
        config={
            "advance_booking_days": 30,
            "min_party_size": 1,
            "max_party_size": 50,
            "deposit_rate": 0.3,
            "cancellation_hours": 24,
            "reminder_hours": 2,
        }
    )


@pytest.fixture
def future_date():
    """获取未来日期"""
    return (datetime.now() + timedelta(days=7)).date().isoformat()


class TestReservationCreation:
    """测试预定创建"""

    @pytest.mark.asyncio
    async def test_create_regular_reservation(self, agent, future_date):
        """测试创建普通预定"""
        reservation = await agent.create_reservation(
            customer_id="CUST001",
            customer_name="张三",
            customer_phone="13800138000",
            reservation_date=future_date,
            reservation_time="18:00",
            party_size=4,
            reservation_type=ReservationType.REGULAR
        )

        assert reservation["customer_id"] == "CUST001"
        assert reservation["customer_name"] == "张三"
        assert reservation["party_size"] == 4
        assert reservation["status"] == ReservationStatus.PENDING
        assert reservation["table_type"] == TableType.MEDIUM
        assert "reservation_id" in reservation

    @pytest.mark.asyncio
    async def test_create_vip_reservation(self, agent, future_date):
        """测试创建VIP预定"""
        reservation = await agent.create_reservation(
            customer_id="CUST002",
            customer_name="李四",
            customer_phone="13900139000",
            reservation_date=future_date,
            reservation_time="19:00",
            party_size=6,
            reservation_type=ReservationType.VIP,
            special_requests="需要靠窗位置"
        )

        assert reservation["reservation_type"] == ReservationType.VIP
        assert reservation["special_requests"] == "需要靠窗位置"
        assert reservation["table_type"] == TableType.LARGE

    @pytest.mark.asyncio
    async def test_create_reservation_with_invalid_date(self, agent):
        """测试创建预定时日期无效"""
        past_date = (datetime.now() - timedelta(days=1)).date().isoformat()

        with pytest.raises(ValueError, match="预定日期不能早于当前日期"):
            await agent.create_reservation(
                customer_id="CUST003",
                customer_name="王五",
                customer_phone="13700137000",
                reservation_date=past_date,
                reservation_time="18:00",
                party_size=4
            )

    @pytest.mark.asyncio
    async def test_create_reservation_too_far_in_advance(self, agent):
        """测试创建预定时日期过远"""
        far_future = (datetime.now() + timedelta(days=60)).date().isoformat()

        with pytest.raises(ValueError, match="只能提前30天预定"):
            await agent.create_reservation(
                customer_id="CUST004",
                customer_name="赵六",
                customer_phone="13600136000",
                reservation_date=far_future,
                reservation_time="18:00",
                party_size=4
            )

    @pytest.mark.asyncio
    async def test_create_reservation_invalid_party_size(self, agent, future_date):
        """测试创建预定时人数无效"""
        with pytest.raises(ValueError, match="人数不能少于"):
            await agent.create_reservation(
                customer_id="CUST005",
                customer_name="孙七",
                customer_phone="13500135000",
                reservation_date=future_date,
                reservation_time="18:00",
                party_size=0
            )

        with pytest.raises(ValueError, match="人数不能超过"):
            await agent.create_reservation(
                customer_id="CUST006",
                customer_name="周八",
                customer_phone="13400134000",
                reservation_date=future_date,
                reservation_time="18:00",
                party_size=100
            )


class TestReservationConfirmation:
    """测试预定确认"""

    @pytest.mark.asyncio
    async def test_confirm_reservation(self, agent):
        """测试确认预定"""
        reservation = await agent.confirm_reservation("RES001")

        assert reservation["status"] == ReservationStatus.CONFIRMED
        assert reservation["table_number"] is not None
        assert reservation["confirmed_at"] is not None

    @pytest.mark.asyncio
    async def test_confirm_already_confirmed_reservation(self, agent):
        """测试确认已确认的预定"""
        # 这个测试需要mock _get_reservation返回已确认的预定
        # 实际实现中需要使用mock
        pass


class TestReservationCancellation:
    """测试预定取消"""

    @pytest.mark.asyncio
    async def test_cancel_reservation(self, agent):
        """测试取消预定"""
        reservation = await agent.cancel_reservation("RES001")

        assert reservation["status"] == ReservationStatus.CANCELLED
        assert reservation["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_with_reason(self, agent):
        """测试带原因取消预定"""
        reservation = await agent.cancel_reservation(
            "RES002",
            reason="客户临时有事"
        )

        assert reservation["status"] == ReservationStatus.CANCELLED


class TestBanquetManagement:
    """测试宴会管理"""

    @pytest.mark.asyncio
    async def test_create_wedding_banquet(self, agent, future_date):
        """测试创建婚宴"""
        menu_items = [
            {"name": "佛跳墙", "price": 28800},
            {"name": "清蒸石斑鱼", "price": 18800},
            {"name": "红烧鲍鱼", "price": 38800}
        ]

        banquet = await agent.create_banquet(
            customer_id="CUST010",
            customer_name="新郎新娘",
            customer_phone="13800138000",
            banquet_type=BanquetType.WEDDING,
            banquet_date=future_date,
            banquet_time="18:00",
            guest_count=200,
            table_count=20,
            venue="宴会厅A",
            menu_items=menu_items,
            price_per_table=288000,
            special_requirements="需要舞台和音响"
        )

        assert banquet["banquet_type"] == BanquetType.WEDDING
        assert banquet["guest_count"] == 200
        assert banquet["table_count"] == 20
        assert banquet["total_amount"] == 5760000  # 20桌 * 288000
        assert banquet["venue"] == "宴会厅A"
        assert len(banquet["menu_items"]) == 3

    @pytest.mark.asyncio
    async def test_create_birthday_banquet(self, agent, future_date):
        """测试创建生日宴"""
        menu_items = [
            {"name": "长寿面", "price": 8800},
            {"name": "寿桃", "price": 6800}
        ]

        banquet = await agent.create_banquet(
            customer_id="CUST011",
            customer_name="寿星",
            customer_phone="13900139000",
            banquet_type=BanquetType.BIRTHDAY,
            banquet_date=future_date,
            banquet_time="12:00",
            guest_count=50,
            table_count=5,
            venue="包间B",
            menu_items=menu_items,
            price_per_table=188000
        )

        assert banquet["banquet_type"] == BanquetType.BIRTHDAY
        assert banquet["table_count"] == 5
        assert banquet["total_amount"] == 940000  # 5桌 * 188000

    @pytest.mark.asyncio
    async def test_create_corporate_banquet(self, agent, future_date):
        """测试创建公司宴请"""
        menu_items = [
            {"name": "商务套餐A", "price": 158000}
        ]

        banquet = await agent.create_banquet(
            customer_id="CUST012",
            customer_name="某公司",
            customer_phone="13700137000",
            banquet_type=BanquetType.CORPORATE,
            banquet_date=future_date,
            banquet_time="19:00",
            guest_count=40,
            table_count=4,
            venue="会议厅",
            menu_items=menu_items,
            price_per_table=158000,
            special_requirements="需要投影仪"
        )

        assert banquet["banquet_type"] == BanquetType.CORPORATE
        assert banquet["special_requirements"] == "需要投影仪"


class TestSeatingAllocation:
    """测试座位分配"""

    @pytest.mark.asyncio
    async def test_allocate_seating(self, agent, future_date):
        """测试分配座位"""
        plan = await agent.allocate_seating(
            date=future_date,
            time_slot="18:00-20:00"
        )

        assert "plan_id" in plan
        assert plan["store_id"] == "STORE001"
        assert plan["date"] == future_date
        assert plan["time_slot"] == "18:00-20:00"
        assert isinstance(plan["tables"], list)
        assert isinstance(plan["utilization_rate"], float)

    @pytest.mark.asyncio
    async def test_seating_optimization(self, agent):
        """测试座位优化算法"""
        # 模拟预定
        reservations = [
            {
                "reservation_id": "RES001",
                "customer_name": "张三",
                "party_size": 4
            },
            {
                "reservation_id": "RES002",
                "customer_name": "李四",
                "party_size": 2
            },
            {
                "reservation_id": "RES003",
                "customer_name": "王五",
                "party_size": 6
            }
        ]

        # 模拟可用桌位
        available_tables = [
            {"table_number": "S001", "table_type": "small", "capacity": 2},
            {"table_number": "M001", "table_type": "medium", "capacity": 4},
            {"table_number": "L001", "table_type": "large", "capacity": 6},
        ]

        allocation = agent._optimize_seating(reservations, available_tables)

        assert len(allocation) == 3
        # 验证大桌分配给6人
        large_allocation = next(a for a in allocation if a["party_size"] == 6)
        assert large_allocation["capacity"] == 6


class TestNotifications:
    """测试通知服务"""

    @pytest.mark.asyncio
    async def test_send_reminder(self, agent):
        """测试发送提醒"""
        notification = await agent.send_reminder("RES001")

        assert notification["notification_type"] == NotificationType.REMINDER
        assert notification["channel"] == "sms"
        assert notification["status"] == "sent"
        assert "智链餐厅" in notification["content"]

    @pytest.mark.asyncio
    async def test_notification_content_generation(self, agent):
        """测试通知内容生成"""
        reservation = {
            "reservation_id": "RES001",
            "customer_name": "张三",
            "reservation_date": "2026-02-20",
            "reservation_time": "18:00",
            "party_size": 4,
            "table_number": "M001"
        }

        # 测试确认通知
        content = agent._generate_notification_content(
            reservation,
            NotificationType.CONFIRMATION
        )
        assert "张三" in content
        assert "18:00" in content
        assert "4人" in content

        # 测试提醒通知
        content = agent._generate_notification_content(
            reservation,
            NotificationType.REMINDER
        )
        assert "提醒" in content

        # 测试取消通知
        content = agent._generate_notification_content(
            reservation,
            NotificationType.CANCELLATION
        )
        assert "取消" in content


class TestAnalytics:
    """测试统计分析"""

    @pytest.mark.asyncio
    async def test_analyze_reservations(self, agent):
        """测试分析预定数据（无 DB 时返回空结构，有 DB 时返回真实统计）"""
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        end_date = (datetime.now() + timedelta(days=7)).date().isoformat()

        analytics = await agent.analyze_reservations(
            start_date=start_date,
            end_date=end_date
        )

        assert analytics["store_id"] == "STORE001"
        assert "total_reservations" in analytics
        assert 0 <= analytics["confirmation_rate"] <= 1
        assert 0 <= analytics["cancellation_rate"] <= 1
        assert 0 <= analytics["no_show_rate"] <= 1
        assert analytics["average_party_size"] >= 0
        assert isinstance(analytics["peak_hours"], list)
        assert analytics["revenue_from_reservations"] >= 0

    @pytest.mark.asyncio
    async def test_analytics_with_no_data(self, agent):
        """测试无数据时的分析"""
        # 这个测试需要mock _get_reservations_by_period返回空列表
        pass


class TestTableTypeRecommendation:
    """测试桌型推荐"""

    def test_recommend_small_table(self, agent):
        """测试推荐小桌"""
        assert agent._recommend_table_type(2) == TableType.SMALL

    def test_recommend_medium_table(self, agent):
        """测试推荐中桌"""
        assert agent._recommend_table_type(4) == TableType.MEDIUM

    def test_recommend_large_table(self, agent):
        """测试推荐大桌"""
        assert agent._recommend_table_type(6) == TableType.LARGE

    def test_recommend_round_table(self, agent):
        """测试推荐圆桌"""
        assert agent._recommend_table_type(10) == TableType.ROUND

    def test_recommend_banquet_table(self, agent):
        """测试推荐宴会桌"""
        assert agent._recommend_table_type(15) == TableType.BANQUET


class TestAmountEstimation:
    """测试金额预估"""

    def test_estimate_regular_amount(self, agent):
        """测试预估普通预定金额"""
        amount = agent._estimate_amount(4, ReservationType.REGULAR)
        assert amount == 32000  # 4人 * 8000分

    def test_estimate_vip_amount(self, agent):
        """测试预估VIP预定金额"""
        amount = agent._estimate_amount(4, ReservationType.VIP)
        assert amount == 80000  # 4人 * 20000分

    def test_estimate_banquet_amount(self, agent):
        """测试预估宴会金额"""
        amount = agent._estimate_amount(10, ReservationType.BANQUET)
        assert amount == 150000  # 10人 * 15000分

    def test_estimate_private_room_amount(self, agent):
        """测试预估包间金额"""
        amount = agent._estimate_amount(6, ReservationType.PRIVATE_ROOM)
        assert amount == 72000  # 6人 * 12000分


class TestConfiguration:
    """测试配置"""

    def test_default_configuration(self):
        """测试默认配置"""
        agent = ReservationAgent(store_id="STORE001")

        assert agent.config["advance_booking_days"] == 30
        assert agent.config["min_party_size"] == 1
        assert agent.config["max_party_size"] == 50
        assert agent.config["deposit_rate"] == 0.3
        assert agent.config["cancellation_hours"] == 24
        assert agent.config["reminder_hours"] == 2

    def test_custom_configuration(self):
        """测试自定义配置"""
        custom_config = {
            "advance_booking_days": 60,
            "min_party_size": 2,
            "max_party_size": 100,
            "deposit_rate": 0.5,
            "cancellation_hours": 48,
            "reminder_hours": 4,
        }

        agent = ReservationAgent(store_id="STORE002", config=custom_config)

        assert agent.config["advance_booking_days"] == 60
        assert agent.config["deposit_rate"] == 0.5

