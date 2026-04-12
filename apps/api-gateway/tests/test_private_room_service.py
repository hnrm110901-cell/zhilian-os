"""
包厢最低消费 + 包间费管理服务 测试

覆盖：
- 最低消费检查（通过/不通过/边界）
- 包间费计算（基础/超时/刚好不超时）
- 订单附加费用（达标/不达标含补足）
- 可用包厢查询（无预订/有预订/已取消）
- 营收统计报表（有数据/空数据/多包厢分组）
"""

import os
for _k, _v in {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from datetime import datetime, timedelta

from src.services.private_room_service import (
    PrivateRoomConfig,
    PrivateRoomService,
    RoomBooking,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def vip_room() -> PrivateRoomConfig:
    """VIP包厢：最低消费 ¥2000，包间费 ¥388，超时 ¥200/h，基本3小时"""
    return PrivateRoomConfig(
        room_id="R001",
        room_name="牡丹厅",
        min_consume_fen=200000,
        room_fee_fen=38800,
        overtime_fee_per_hour_fen=20000,
        max_hours=3.0,
        capacity=12,
    )


@pytest.fixture
def small_room() -> PrivateRoomConfig:
    """小包厢：最低消费 ¥800，包间费 ¥0，超时 ¥100/h，基本2小时"""
    return PrivateRoomConfig(
        room_id="R002",
        room_name="竹苑",
        min_consume_fen=80000,
        room_fee_fen=0,
        overtime_fee_per_hour_fen=10000,
        max_hours=2.0,
        capacity=6,
    )


@pytest.fixture
def rooms(vip_room, small_room) -> list:
    return [vip_room, small_room]


# ── 最低消费检查 ─────────────────────────────────────────────────────────────────


class TestCheckMinConsume:
    """最低消费检查测试"""

    def test_order_exceeds_minimum(self, vip_room):
        """订单超过最低消费 → 通过"""
        result = PrivateRoomService.check_min_consume(vip_room, 250000)
        assert result["pass"] is True
        assert result["shortage_fen"] == 0
        assert result["shortage_yuan"] == "¥0.00"

    def test_order_exactly_meets_minimum(self, vip_room):
        """订单刚好等于最低消费 → 通过"""
        result = PrivateRoomService.check_min_consume(vip_room, 200000)
        assert result["pass"] is True
        assert result["shortage_fen"] == 0

    def test_order_below_minimum(self, vip_room):
        """订单低于最低消费 → 不通过，返回差额"""
        result = PrivateRoomService.check_min_consume(vip_room, 150000)
        assert result["pass"] is False
        assert result["shortage_fen"] == 50000
        assert result["shortage_yuan"] == "¥500.00"
        assert result["min_consume_yuan"] == "¥2000.00"

    def test_zero_order(self, vip_room):
        """零消费 → 差额等于最低消费"""
        result = PrivateRoomService.check_min_consume(vip_room, 0)
        assert result["pass"] is False
        assert result["shortage_fen"] == 200000

    def test_negative_order_raises(self, vip_room):
        """负数消费 → 异常"""
        with pytest.raises(ValueError, match="不能为负数"):
            PrivateRoomService.check_min_consume(vip_room, -100)


# ── 包间费计算 ───────────────────────────────────────────────────────────────────


class TestCalculateRoomCharges:
    """包间费 + 超时费计算测试"""

    def test_within_max_hours_no_overtime(self, vip_room):
        """2小时使用，不超基本时长 → 无超时费"""
        start = datetime(2026, 3, 26, 18, 0)
        end = datetime(2026, 3, 26, 20, 0)
        result = PrivateRoomService.calculate_room_charges(vip_room, start, end)
        assert result["room_fee_fen"] == 38800
        assert result["overtime_fee_fen"] == 0
        assert result["total_fen"] == 38800
        assert result["duration_hours"] == pytest.approx(2.0, abs=0.01)

    def test_overtime_charges(self, vip_room):
        """4.5小时使用，超1.5小时 → 向上取整2小时超时费"""
        start = datetime(2026, 3, 26, 18, 0)
        end = datetime(2026, 3, 26, 22, 30)
        result = PrivateRoomService.calculate_room_charges(vip_room, start, end)
        assert result["overtime_hours"] == pytest.approx(1.5, abs=0.01)
        # 向上取整: 1.5h → 2h × ¥200 = ¥400
        assert result["overtime_fee_fen"] == 40000
        assert result["total_fen"] == 38800 + 40000

    def test_exactly_at_max_hours(self, vip_room):
        """刚好3小时 → 无超时"""
        start = datetime(2026, 3, 26, 18, 0)
        end = datetime(2026, 3, 26, 21, 0)
        result = PrivateRoomService.calculate_room_charges(vip_room, start, end)
        assert result["overtime_fee_fen"] == 0

    def test_end_before_start_raises(self, vip_room):
        """结束早于开始 → 异常"""
        start = datetime(2026, 3, 26, 20, 0)
        end = datetime(2026, 3, 26, 18, 0)
        with pytest.raises(ValueError, match="end_time 必须晚于 start_time"):
            PrivateRoomService.calculate_room_charges(vip_room, start, end)

    def test_no_room_fee_with_overtime(self, small_room):
        """无包间费 + 有超时费"""
        start = datetime(2026, 3, 26, 18, 0)
        end = datetime(2026, 3, 26, 21, 0)  # 3小时，超1小时
        result = PrivateRoomService.calculate_room_charges(small_room, start, end)
        assert result["room_fee_fen"] == 0
        assert result["overtime_fee_fen"] == 10000  # 1h × ¥100
        assert result["total_fen"] == 10000
        assert result["total_yuan"] == "¥100.00"


# ── 订单附加费用 ─────────────────────────────────────────────────────────────────


class TestApplyRoomChargesToOrder:
    """订单附加包间费用测试"""

    def test_order_meets_min_consume(self, vip_room):
        """达标订单 → 无补足，仅加包间费"""
        order = {"order_id": "O001", "total_fen": 250000}
        start = datetime(2026, 3, 26, 18, 0)
        end = datetime(2026, 3, 26, 20, 0)
        result = PrivateRoomService.apply_room_charges_to_order(order, vip_room, start, end)

        assert result["room_charges"]["min_consume_passed"] is True
        assert result["room_charges"]["shortage_supplement_fen"] == 0
        # 250000 + 38800（包间费）= 288800
        assert result["final_total_fen"] == 288800

    def test_order_below_min_consume_with_supplement(self, vip_room):
        """不达标 → 补足差额 + 包间费"""
        order = {"order_id": "O002", "total_fen": 150000}
        start = datetime(2026, 3, 26, 18, 0)
        end = datetime(2026, 3, 26, 20, 0)
        result = PrivateRoomService.apply_room_charges_to_order(order, vip_room, start, end)

        assert result["room_charges"]["min_consume_passed"] is False
        assert result["room_charges"]["shortage_supplement_fen"] == 50000
        # 150000 + 38800 + 50000 = 238800
        assert result["final_total_fen"] == 238800

    def test_missing_total_fen_raises(self, vip_room):
        """订单缺 total_fen → KeyError"""
        order = {"order_id": "O003"}
        start = datetime(2026, 3, 26, 18, 0)
        end = datetime(2026, 3, 26, 20, 0)
        with pytest.raises(KeyError, match="total_fen"):
            PrivateRoomService.apply_room_charges_to_order(order, vip_room, start, end)


# ── 可用包厢查询 ─────────────────────────────────────────────────────────────────


class TestGetAvailableRooms:
    """可用包厢查询测试"""

    def test_all_available_no_bookings(self, rooms):
        """无预订 → 全部可用"""
        result = PrivateRoomService.get_available_rooms(rooms, datetime(2026, 3, 26, 18, 0))
        assert len(result) == 2

    def test_one_occupied(self, rooms):
        """一间被占用 → 返回另一间"""
        bookings = [
            RoomBooking(
                booking_id="BK001",
                room_id="R001",
                room_name="牡丹厅",
                start_time=datetime(2026, 3, 26, 17, 0),
                end_time=datetime(2026, 3, 26, 20, 0),
                status="confirmed",
            ),
        ]
        result = PrivateRoomService.get_available_rooms(
            rooms, datetime(2026, 3, 26, 18, 0), bookings
        )
        assert len(result) == 1
        assert result[0]["room_id"] == "R002"

    def test_cancelled_booking_ignored(self, rooms):
        """已取消预订不占用"""
        bookings = [
            RoomBooking(
                booking_id="BK002",
                room_id="R001",
                room_name="牡丹厅",
                start_time=datetime(2026, 3, 26, 17, 0),
                end_time=datetime(2026, 3, 26, 20, 0),
                status="cancelled",
            ),
        ]
        result = PrivateRoomService.get_available_rooms(
            rooms, datetime(2026, 3, 26, 18, 0), bookings
        )
        assert len(result) == 2

    def test_unavailable_room_excluded(self, vip_room):
        """is_available=False 的包厢不出现"""
        vip_room.is_available = False
        result = PrivateRoomService.get_available_rooms([vip_room], datetime(2026, 3, 26, 18, 0))
        assert len(result) == 0

    def test_available_room_has_yuan_fields(self, rooms):
        """返回结果包含 ¥ 金额字段"""
        result = PrivateRoomService.get_available_rooms(rooms, datetime(2026, 3, 26, 18, 0))
        for r in result:
            assert "min_consume_yuan" in r
            assert "room_fee_yuan" in r
            assert r["min_consume_yuan"].startswith("¥")


# ── 营收统计 ─────────────────────────────────────────────────────────────────────


class TestGetRoomRevenueReport:
    """包厢营收统计报表测试"""

    def test_empty_bookings(self):
        """空预订列表 → 零值报表"""
        result = PrivateRoomService.get_room_revenue_report([])
        assert result["total_bookings"] == 0
        assert result["grand_total_fen"] == 0
        assert result["grand_total_yuan"] == "¥0.00"

    def test_multiple_bookings(self):
        """多笔预订 → 正确汇总"""
        bookings = [
            RoomBooking(
                booking_id="BK001", room_id="R001", room_name="牡丹厅",
                start_time=datetime(2026, 3, 26, 18, 0),
                end_time=datetime(2026, 3, 26, 21, 0),
                order_total_fen=250000, room_fee_fen=38800, overtime_fee_fen=0,
                status="completed",
            ),
            RoomBooking(
                booking_id="BK002", room_id="R001", room_name="牡丹厅",
                start_time=datetime(2026, 3, 25, 18, 0),
                end_time=datetime(2026, 3, 25, 22, 0),
                order_total_fen=300000, room_fee_fen=38800, overtime_fee_fen=20000,
                status="completed",
            ),
            RoomBooking(
                booking_id="BK003", room_id="R002", room_name="竹苑",
                start_time=datetime(2026, 3, 26, 12, 0),
                end_time=datetime(2026, 3, 26, 14, 0),
                order_total_fen=100000, room_fee_fen=0, overtime_fee_fen=0,
                status="completed",
            ),
            RoomBooking(
                booking_id="BK004", room_id="R001", room_name="牡丹厅",
                start_time=datetime(2026, 3, 27, 18, 0),
                end_time=datetime(2026, 3, 27, 21, 0),
                status="cancelled",
            ),
        ]
        result = PrivateRoomService.get_room_revenue_report(bookings)

        assert result["total_bookings"] == 4
        assert result["completed_bookings"] == 3
        assert result["cancelled_bookings"] == 1
        assert result["total_order_revenue_fen"] == 650000
        assert result["total_room_fee_fen"] == 77600
        assert result["total_overtime_fee_fen"] == 20000
        assert result["grand_total_fen"] == 747600
        assert len(result["by_room"]) == 2
        # 按营收降序，R001 排前面
        assert result["by_room"][0]["room_id"] == "R001"
        assert result["avg_duration_hours"] > 0
