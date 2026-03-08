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

    @pytest.mark.asyncio
    async def test_create_reservation_conflict_returns_ranked_alternatives(self, agent, monkeypatch):
        """测试预定冲突时返回智能排序的备选时段"""
        monkeypatch.setenv("ORDER_MAX_CONCURRENT_RESERVATIONS", "2")
        existing_reservations = [
            # 请求时段已满
            {"store_id": "STORE001", "reservation_time": "2024-01-20 18:00", "status": "confirmed"},
            {"store_id": "STORE001", "reservation_time": "2024-01-20 18:00", "status": "confirmed"},
            # 18:30 负载较高(1)
            {"store_id": "STORE001", "reservation_time": "2024-01-20 18:30", "status": "confirmed"},
            # 17:30 负载较低(0) -> 应优先于18:30
        ]

        result = await agent.create_reservation(
            store_id="STORE001",
            customer_name="冲突用户",
            customer_mobile="13800138001",
            party_size=4,
            reservation_time="2024-01-20 18:00",
            existing_reservations=existing_reservations,
        )
        assert result["success"] is False
        assert "alternative_times" in result
        assert len(result["alternative_times"]) > 0
        # 智能排序：更低负载 + 时间更近
        assert result["alternative_times"][0] == "2024-01-20 17:30"


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
    async def test_create_order_reject_when_table_unavailable(self):
        """测试桌台不可用时拒绝下单"""
        async def checker(**kwargs):
            return {"available": False, "reason": "已被占用", "source": "mock_table_manager"}

        agent = OrderAgent({"average_wait_time": 30, "average_dining_time": 90, "table_availability_checker": checker})
        result = await agent.create_order(store_id="STORE001", table_id="T009", customer_id="C001")
        assert result["success"] is False
        assert "桌台 T009 当前不可下单" in result["message"]

    @pytest.mark.asyncio
    async def test_create_order_calls_table_occupy_callback(self):
        """测试下单成功后调用桌台占用回调"""
        called = {"count": 0, "order_id": None}

        def checker(**kwargs):
            return True

        async def occupy_callback(**kwargs):
            called["count"] += 1
            called["order_id"] = kwargs.get("order_id")

        agent = OrderAgent(
            {
                "average_wait_time": 30,
                "average_dining_time": 90,
                "table_availability_checker": checker,
                "table_occupy_callback": occupy_callback,
            }
        )
        result = await agent.create_order(store_id="STORE001", table_id="T010", customer_id="C002")
        assert result["success"] is True
        assert called["count"] == 1
        assert called["order_id"] == result["order"]["order_id"]

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

    @pytest.mark.asyncio
    async def test_recommend_dishes_multilingual_en_us(self, agent):
        """测试多语言菜单支持（英文）"""
        recent_orders = [
            {
                "store_id": "STORE001",
                "dishes": [
                    {"dish_id": "D001", "dish_name": "宫保鸡丁", "price": 48.0, "quantity": 3},
                    {"dish_id": "D002", "dish_name": "米饭", "price": 3.0, "quantity": 2},
                ],
            }
        ]
        result = await agent.recommend_dishes(
            store_id="STORE001",
            recent_orders=recent_orders,
            locale="en-US",
        )
        assert result["success"] is True
        assert result["locale"] == "en-US"
        assert result["recommendations"][0]["dish_name"] in {"Kung Pao Chicken", "Steamed Rice"}
        assert "dish_name_zh" in result["recommendations"][0]
        assert "Recommended" in result["message"]

    @pytest.mark.asyncio
    async def test_modify_order_update_quantity_and_total(self, agent):
        """测试订单改数量后金额重算"""
        order = {
            "order_id": "ORD001",
            "dishes": [
                {"dish_id": "D001", "dish_name": "宫保鸡丁", "price": 48.0, "quantity": 1, "subtotal": 48.0},
                {"dish_id": "D002", "dish_name": "米饭", "price": 3.0, "quantity": 2, "subtotal": 6.0},
            ],
            "total_amount": 54.0,
            "status": OrderStatus.ORDERING.value,
        }
        result = await agent.modify_order(
            order_id="ORD001",
            order=order,
            modifications=[{"action": "update_quantity", "dish_id": "D001", "quantity": 2}],
        )
        assert result["success"] is True
        updated = result["updated_order"]
        assert updated["total_amount"] == 102.0
        dish = next(d for d in updated["dishes"] if d["dish_id"] == "D001")
        assert dish["quantity"] == 2

    @pytest.mark.asyncio
    async def test_modify_order_remove_dish(self, agent):
        """测试订单删菜"""
        order = {
            "order_id": "ORD002",
            "dishes": [
                {"dish_id": "D001", "dish_name": "宫保鸡丁", "price": 48.0, "quantity": 1, "subtotal": 48.0},
                {"dish_id": "D002", "dish_name": "米饭", "price": 3.0, "quantity": 2, "subtotal": 6.0},
            ],
            "total_amount": 54.0,
            "status": OrderStatus.ORDERING.value,
        }
        result = await agent.modify_order(
            order_id="ORD002",
            order=order,
            modifications=[{"action": "remove_dish", "dish_id": "D002"}],
        )
        assert result["success"] is True
        updated = result["updated_order"]
        assert len(updated["dishes"]) == 1
        assert updated["total_amount"] == 48.0

    @pytest.mark.asyncio
    async def test_modify_order_update_instructions_and_invalid_quantity(self, agent):
        """测试改备注和非法数量输入"""
        order = {
            "order_id": "ORD003",
            "dishes": [
                {
                    "dish_id": "D003",
                    "dish_name": "鱼香肉丝",
                    "price": 38.0,
                    "quantity": 1,
                    "subtotal": 38.0,
                    "special_instructions": None,
                }
            ],
            "total_amount": 38.0,
            "status": OrderStatus.ORDERING.value,
        }
        result = await agent.modify_order(
            order_id="ORD003",
            order=order,
            modifications=[
                {"action": "update_instructions", "dish_id": "D003", "special_instructions": "少盐"},
                {"action": "update_quantity", "dish_id": "D003", "quantity": 0},
            ],
        )
        assert result["success"] is True
        updated = result["updated_order"]
        assert updated["dishes"][0]["special_instructions"] == "少盐"
        assert any("数量非法" in msg for msg in result["applied_modifications"])

    @pytest.mark.asyncio
    async def test_merge_table_orders_success(self, agent):
        """测试拼桌合单成功"""
        primary_order = {
            "order_id": "ORD100",
            "store_id": "STORE001",
            "table_id": "T001",
            "dishes": [
                {"dish_id": "D001", "dish_name": "宫保鸡丁", "price": 48.0, "quantity": 1, "subtotal": 48.0}
            ],
            "total_amount": 48.0,
            "status": OrderStatus.ORDERING.value,
        }
        secondary_order = {
            "order_id": "ORD101",
            "store_id": "STORE001",
            "table_id": "T002",
            "dishes": [
                {"dish_id": "D002", "dish_name": "米饭", "price": 3.0, "quantity": 2, "subtotal": 6.0}
            ],
            "total_amount": 6.0,
            "status": OrderStatus.ORDERING.value,
        }
        result = await agent.merge_table_orders(primary_order=primary_order, secondary_order=secondary_order)
        assert result["success"] is True
        merged = result["merged_order"]
        assert merged["is_merged_table"] is True
        assert merged["total_amount"] == 54.0
        assert merged["table_ids"] == ["T001", "T002"]
        assert result["closed_order_id"] == "ORD101"

    @pytest.mark.asyncio
    async def test_merge_table_orders_reject_cross_store(self, agent):
        """测试跨门店拼桌被拒绝"""
        primary_order = {"order_id": "ORD200", "store_id": "STORE001", "table_id": "T001", "dishes": []}
        secondary_order = {"order_id": "ORD201", "store_id": "STORE002", "table_id": "T002", "dishes": []}
        result = await agent.merge_table_orders(primary_order=primary_order, secondary_order=secondary_order)
        assert result["success"] is False
        assert "跨门店订单不能拼桌" in result["message"]


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
    async def test_update_order_status_invalid_transition(self, agent):
        """测试非法状态转换被拒绝"""
        mock_order = {"order_id": "ORD001", "status": OrderStatus.ORDERING.value}
        result = await agent.update_order_status(
            order_id="ORD001",
            new_status=OrderStatus.PAID.value,
            order=mock_order,
        )
        assert result["success"] is False
        assert "不允许从 ordering 转换到 paid" in result["message"]

    @pytest.mark.asyncio
    async def test_update_order_status_unknown_status(self, agent):
        """测试未知状态输入被校验拒绝"""
        mock_order = {"order_id": "ORD001", "status": "unknown_status"}
        result = await agent.update_order_status(
            order_id="ORD001",
            new_status=OrderStatus.ORDERED.value,
            order=mock_order,
        )
        assert result["success"] is False
        assert "未知订单状态" in result["message"]

    def test_get_valid_next_statuses(self, agent):
        """测试获取状态机下一跳"""
        assert agent.get_valid_next_statuses(OrderStatus.RESERVED.value) == [
            OrderStatus.WAITING.value,
            OrderStatus.SEATED.value,
            OrderStatus.CANCELLED.value,
        ]
        assert agent.get_valid_next_statuses(OrderStatus.PAID.value) == [
            OrderStatus.COMPLETED.value
        ]

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
