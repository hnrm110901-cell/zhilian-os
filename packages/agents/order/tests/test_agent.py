"""
订单协同Agent单元测试
"""
import pytest
from datetime import datetime, timedelta
from src.agent import (
    OrderAgent,
    OrderStatus,
    ReservationType,
    PaymentMethod,
)


@pytest.fixture
def agent():
    """创建Agent实例"""
    config = {
        "average_wait_time": 30,
        "average_dining_time": 90,
    }
    return OrderAgent(config)


class TestReservation:
    """预定管理测试"""

    @pytest.mark.asyncio
    async def test_create_reservation_success(self, agent):
        """测试创建预定成功"""
        result = await agent.create_reservation(
            store_id="STORE001",
            customer_name="张三",
            customer_mobile="13800138000",
            party_size=4,
            reservation_time="2024-01-20 18:00",
            special_requests="靠窗座位",
        )

        assert result["success"] is True
        assert "reservation" in result
        assert result["reservation"]["customer_name"] == "张三"
        assert result["reservation"]["party_size"] == 4
        assert result["reservation"]["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_create_reservation_with_special_requests(self, agent):
        """测试带特殊需求的预定"""
        result = await agent.create_reservation(
            store_id="STORE001",
            customer_name="李四",
            customer_mobile="13900139000",
            party_size=2,
            reservation_time="2024-01-20 19:00",
            special_requests="需要儿童座椅",
        )

        assert result["success"] is True
        assert result["reservation"]["special_requests"] == "需要儿童座椅"


class TestQueue:
    """排队管理测试"""

    @pytest.mark.asyncio
    async def test_join_queue(self, agent):
        """测试加入排队"""
        result = await agent.join_queue(
            store_id="STORE001",
            customer_name="王五",
            customer_mobile="13700137000",
            party_size=3,
        )

        assert result["success"] is True
        assert "queue_info" in result
        assert result["queue_info"]["party_size"] == 3
        assert result["queue_info"]["status"] == "waiting"
        assert "queue_number" in result["queue_info"]
        assert "estimated_wait_minutes" in result["queue_info"]

    def test_estimate_wait_time_by_party_size(self, agent):
        """测试根据人数预估等待时间"""
        # 2人
        wait_time_2 = agent._estimate_wait_time("STORE001", 2, [])
        # 4人
        wait_time_4 = agent._estimate_wait_time("STORE001", 4, [])
        # 6人
        wait_time_6 = agent._estimate_wait_time("STORE001", 6, [])

        # 人数越多，等待时间应该越长
        assert wait_time_2 <= wait_time_4 <= wait_time_6

    @pytest.mark.asyncio
    async def test_get_queue_status(self, agent):
        """测试查询排队状态"""
        mock_queue = {"queue_id": "Q123456", "status": "waiting", "queue_number": "A001"}
        result = await agent.get_queue_status("Q123456", queue=mock_queue)

        assert result["success"] is True
        assert "status" in result
        assert "ahead_count" in result
        assert "estimated_wait_minutes" in result


class TestOrdering:
    """点单管理测试"""

    @pytest.mark.asyncio
    async def test_create_order(self, agent):
        """测试创建订单"""
        result = await agent.create_order(
            store_id="STORE001",
            table_id="T001",
            customer_id="C001",
        )

        assert result["success"] is True
        assert "order" in result
        assert result["order"]["store_id"] == "STORE001"
        assert result["order"]["table_id"] == "T001"
        assert result["order"]["status"] == OrderStatus.ORDERING.value

    @pytest.mark.asyncio
    async def test_add_dish(self, agent):
        """测试添加菜品"""
        result = await agent.add_dish(
            order_id="ORD001",
            dish_id="D001",
            dish_name="宫保鸡丁",
            price=48.0,
            quantity=2,
            special_instructions="少辣",
        )

        assert result["success"] is True
        assert result["dish_item"]["dish_name"] == "宫保鸡丁"
        assert result["dish_item"]["quantity"] == 2
        assert result["dish_item"]["subtotal"] == 96.0
        assert result["dish_item"]["special_instructions"] == "少辣"

    @pytest.mark.asyncio
    async def test_recommend_dishes(self, agent):
        """测试推荐菜品"""
        result = await agent.recommend_dishes(
            store_id="STORE001",
            customer_id="C001",
            party_size=4,
        )

        assert result["success"] is True
        assert "recommendations" in result
        assert len(result["recommendations"]) > 0

        # 验证推荐菜品结构
        dish = result["recommendations"][0]
        assert "dish_id" in dish
        assert "dish_name" in dish
        assert "price" in dish
        assert "reason" in dish


class TestPayment:
    """结账管理测试"""

    @pytest.mark.asyncio
    async def test_calculate_bill_without_discount(self, agent):
        """测试计算账单（无折扣）"""
        mock_order = {"order_id": "ORD001", "total_amount": 200.0}
        result = await agent.calculate_bill(order_id="ORD001", order=mock_order)

        assert result["success"] is True
        assert "bill" in result
        assert result["bill"]["total_amount"] > 0
        assert result["bill"]["final_amount"] == result["bill"]["total_amount"]

    @pytest.mark.asyncio
    async def test_calculate_bill_with_member_discount(self, agent):
        """测试计算账单（会员折扣）"""
        mock_order = {"order_id": "ORD001", "total_amount": 200.0}
        result = await agent.calculate_bill(
            order_id="ORD001",
            order=mock_order,
            member_id="M001",
        )

        assert result["success"] is True
        bill = result["bill"]
        assert bill["member_discount"] > 0
        assert bill["final_amount"] < bill["total_amount"]

    @pytest.mark.asyncio
    async def test_calculate_bill_with_coupon(self, agent):
        """测试计算账单（优惠券）"""
        mock_order = {"order_id": "ORD001", "total_amount": 200.0}
        result = await agent.calculate_bill(
            order_id="ORD001",
            order=mock_order,
            coupon_codes=["COUPON001"],
        )

        assert result["success"] is True
        bill = result["bill"]
        assert bill["coupon_discount"] > 0
        assert bill["final_amount"] < bill["total_amount"]

    @pytest.mark.asyncio
    async def test_process_payment_wechat(self, agent):
        """测试微信支付"""
        result = await agent.process_payment(
            order_id="ORD001",
            payment_method=PaymentMethod.WECHAT.value,
            amount=180.0,
        )

        assert result["success"] is True
        assert result["payment"]["payment_method"] == PaymentMethod.WECHAT.value
        assert result["payment"]["amount"] == 180.0
        assert result["payment"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_process_payment_cash(self, agent):
        """测试现金支付"""
        result = await agent.process_payment(
            order_id="ORD001",
            payment_method=PaymentMethod.CASH.value,
            amount=200.0,
        )

        assert result["success"] is True
        assert result["payment"]["payment_method"] == PaymentMethod.CASH.value


class TestOrderManagement:
    """订单管理测试"""

    @pytest.mark.asyncio
    async def test_get_order(self, agent):
        """测试查询订单"""
        mock_order = {"order_id": "ORD001", "status": "ordering", "dishes": [], "total_amount": 0}
        result = await agent.get_order("ORD001", order=mock_order)

        assert result["success"] is True
        assert "order" in result
        assert result["order"]["order_id"] == "ORD001"

    @pytest.mark.asyncio
    async def test_update_order_status(self, agent):
        """测试更新订单状态"""
        mock_order = {"order_id": "ORD001", "status": OrderStatus.ORDERED.value}
        result = await agent.update_order_status(
            order_id="ORD001",
            new_status=OrderStatus.COOKING.value,
            order=mock_order,
        )

        assert result["success"] is True
        assert result["status"] == OrderStatus.COOKING.value

    @pytest.mark.asyncio
    async def test_cancel_order(self, agent):
        """测试取消订单"""
        mock_order = {"order_id": "ORD001", "status": OrderStatus.ORDERING.value}
        result = await agent.cancel_order(
            order_id="ORD001",
            order=mock_order,
            reason="客户要求取消",
        )

        assert result["success"] is True
        assert result["order_id"] == "ORD001"


class TestEnums:
    """枚举类型测试"""

    def test_order_status_enum(self):
        """测试订单状态枚举"""
        assert OrderStatus.RESERVED.value == "reserved"
        assert OrderStatus.WAITING.value == "waiting"
        assert OrderStatus.SEATED.value == "seated"
        assert OrderStatus.ORDERING.value == "ordering"
        assert OrderStatus.ORDERED.value == "ordered"
        assert OrderStatus.COOKING.value == "cooking"
        assert OrderStatus.SERVED.value == "served"
        assert OrderStatus.PAYING.value == "paying"
        assert OrderStatus.PAID.value == "paid"
        assert OrderStatus.COMPLETED.value == "completed"
        assert OrderStatus.CANCELLED.value == "cancelled"

    def test_payment_method_enum(self):
        """测试支付方式枚举"""
        assert PaymentMethod.CASH.value == "cash"
        assert PaymentMethod.WECHAT.value == "wechat"
        assert PaymentMethod.ALIPAY.value == "alipay"
        assert PaymentMethod.CARD.value == "card"
        assert PaymentMethod.MEMBER.value == "member"

    def test_reservation_type_enum(self):
        """测试预定类型枚举"""
        assert ReservationType.ONLINE.value == "online"
        assert ReservationType.PHONE.value == "phone"
        assert ReservationType.WALKIN.value == "walkin"


class TestWorkflow:
    """完整工作流测试"""

    @pytest.mark.asyncio
    async def test_complete_order_workflow(self, agent):
        """测试完整订单流程"""
        # 1. 创建预定
        reservation = await agent.create_reservation(
            store_id="STORE001",
            customer_name="测试用户",
            customer_mobile="13800138000",
            party_size=4,
            reservation_time="2024-01-20 18:00",
        )
        assert reservation["success"] is True

        # 2. 创建订单
        order = await agent.create_order(
            store_id="STORE001",
            table_id="T001",
        )
        assert order["success"] is True
        order_id = order["order"]["order_id"]
        order_data = order["order"]

        # 3. 添加菜品
        dish1 = await agent.add_dish(
            order_id=order_id,
            dish_id="D001",
            dish_name="宫保鸡丁",
            price=48.0,
            quantity=1,
        )
        assert dish1["success"] is True
        # 模拟调用方将菜品追加到订单并更新金额
        order_data["dishes"].append(dish1["dish_item"])
        order_data["total_amount"] = dish1["dish_item"]["subtotal"]

        # 4. 计算账单（传入订单数据）
        bill = await agent.calculate_bill(order_id=order_id, order=order_data)
        assert bill["success"] is True

        # 5. 处理支付
        payment = await agent.process_payment(
            order_id=order_id,
            payment_method=PaymentMethod.WECHAT.value,
            amount=bill["bill"]["final_amount"],
        )
        assert payment["success"] is True

    @pytest.mark.asyncio
    async def test_walkin_customer_workflow(self, agent):
        """测试现场客户流程（无预定）"""
        # 1. 加入排队
        queue = await agent.join_queue(
            store_id="STORE001",
            customer_name="现场客户",
            customer_mobile="13900139000",
            party_size=2,
        )
        assert queue["success"] is True

        # 2. 查询排队状态（需传入 queue 记录）
        queue_record = queue["queue_info"]
        status = await agent.get_queue_status(queue_record["queue_id"], queue=queue_record)
        assert status["success"] is True

        # 3. 入座后创建订单
        order = await agent.create_order(
            store_id="STORE001",
            table_id="T002",
        )
        assert order["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
