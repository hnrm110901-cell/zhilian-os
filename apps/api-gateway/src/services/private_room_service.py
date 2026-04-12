"""
包厢最低消费 + 包间费管理服务（Private Room Service）

核心功能：
- 包厢配置管理（最低消费、包间费、超时费）
- 最低消费检查
- 包间费 + 超时费计算
- 订单附加包间费用
- 可用包厢查询
- 包厢营收统计报表

金额单位：分（fen），API 返回时 /100 转元
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


# ── 数据模型 ────────────────────────────────────────────────────────────────────


@dataclass
class PrivateRoomConfig:
    """包厢配置"""
    room_id: str
    room_name: str
    min_consume_fen: int  # 最低消费（分）
    room_fee_fen: int  # 包间费（分）
    overtime_fee_per_hour_fen: int  # 超时每小时费用（分）
    max_hours: float  # 基本时长（小时），超出后收超时费
    capacity: int = 10  # 包厢容纳人数
    is_available: bool = True  # 是否可用


@dataclass
class RoomBooking:
    """包厢预订记录"""
    booking_id: str
    room_id: str
    room_name: str
    start_time: datetime
    end_time: datetime
    order_total_fen: int = 0  # 消费金额（分）
    room_fee_fen: int = 0  # 包间费（分）
    overtime_fee_fen: int = 0  # 超时费（分）
    status: str = "confirmed"  # confirmed / completed / cancelled


# ── 服务类 ──────────────────────────────────────────────────────────────────────


class PrivateRoomService:
    """包厢最低消费 + 包间费管理服务"""

    @staticmethod
    def check_min_consume(
        room_config: PrivateRoomConfig,
        order_total_fen: int,
    ) -> Dict[str, Any]:
        """
        检查订单是否满足包厢最低消费

        Args:
            room_config: 包厢配置
            order_total_fen: 订单消费总额（分）

        Returns:
            {
                "pass": bool,          # 是否达到最低消费
                "shortage_fen": int,   # 差额（分），通过时为 0
                "min_consume_fen": int,
                "order_total_fen": int,
                "min_consume_yuan": str,  # ¥金额展示
                "shortage_yuan": str,     # ¥差额展示
            }
        """
        if order_total_fen < 0:
            raise ValueError("order_total_fen 不能为负数")

        shortage = max(0, room_config.min_consume_fen - order_total_fen)
        passed = shortage == 0

        return {
            "pass": passed,
            "shortage_fen": shortage,
            "min_consume_fen": room_config.min_consume_fen,
            "order_total_fen": order_total_fen,
            "min_consume_yuan": f"¥{room_config.min_consume_fen / 100:.2f}",
            "shortage_yuan": f"¥{shortage / 100:.2f}",
        }

    @staticmethod
    def calculate_room_charges(
        room_config: PrivateRoomConfig,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """
        计算包间费 + 超时费

        Args:
            room_config: 包厢配置
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            {
                "room_fee_fen": int,       # 基础包间费（分）
                "overtime_fee_fen": int,   # 超时费（分）
                "total_fen": int,          # 总费用（分）
                "duration_hours": float,   # 实际使用时长
                "overtime_hours": float,   # 超时时长
                "total_yuan": str,         # ¥总费用展示
            }
        """
        if end_time <= start_time:
            raise ValueError("end_time 必须晚于 start_time")

        duration_seconds = (end_time - start_time).total_seconds()
        duration_hours = duration_seconds / 3600

        # 超时部分：向上取整到小时
        overtime_hours = max(0, duration_hours - room_config.max_hours)
        overtime_ceil = math.ceil(overtime_hours) if overtime_hours > 0 else 0
        overtime_fee = overtime_ceil * room_config.overtime_fee_per_hour_fen

        total = room_config.room_fee_fen + overtime_fee

        return {
            "room_fee_fen": room_config.room_fee_fen,
            "overtime_fee_fen": overtime_fee,
            "total_fen": total,
            "duration_hours": round(duration_hours, 2),
            "overtime_hours": round(overtime_hours, 2),
            "total_yuan": f"¥{total / 100:.2f}",
        }

    @staticmethod
    def apply_room_charges_to_order(
        order: Dict[str, Any],
        room_config: PrivateRoomConfig,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """
        将包间费用附加到订单上，并检查最低消费

        Args:
            order: 订单字典，必须包含 "total_fen" 字段
            room_config: 包厢配置
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            更新后的订单字典，新增 room_charges 和 final_total_fen 字段
        """
        if "total_fen" not in order:
            raise KeyError("订单必须包含 total_fen 字段")

        order_total = order["total_fen"]

        # 计算包间费
        charges = PrivateRoomService.calculate_room_charges(
            room_config, start_time, end_time
        )

        # 检查最低消费
        min_check = PrivateRoomService.check_min_consume(
            room_config, order_total
        )

        # 如果未达最低消费，补足差额
        shortage_supplement = min_check["shortage_fen"]

        final_total = order_total + charges["total_fen"] + shortage_supplement

        updated_order = dict(order)
        updated_order["room_charges"] = {
            "room_id": room_config.room_id,
            "room_name": room_config.room_name,
            "room_fee_fen": charges["room_fee_fen"],
            "overtime_fee_fen": charges["overtime_fee_fen"],
            "room_total_fen": charges["total_fen"],
            "min_consume_passed": min_check["pass"],
            "shortage_supplement_fen": shortage_supplement,
        }
        updated_order["final_total_fen"] = final_total
        updated_order["final_total_yuan"] = f"¥{final_total / 100:.2f}"

        return updated_order

    @staticmethod
    def get_available_rooms(
        rooms: List[PrivateRoomConfig],
        query_time: datetime,
        bookings: Optional[List[RoomBooking]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取可用包厢列表

        Args:
            rooms: 所有包厢配置
            query_time: 查询时间
            bookings: 已有预订列表（用于排除已占用包厢）

        Returns:
            可用包厢列表
        """
        bookings = bookings or []

        # 已占用包厢ID集合
        occupied_ids = set()
        for booking in bookings:
            if booking.status == "cancelled":
                continue
            # 检查查询时间是否在预订时段内
            if booking.start_time <= query_time < booking.end_time:
                occupied_ids.add(booking.room_id)

        available = []
        for room in rooms:
            if not room.is_available:
                continue
            if room.room_id in occupied_ids:
                continue
            available.append({
                "room_id": room.room_id,
                "room_name": room.room_name,
                "capacity": room.capacity,
                "min_consume_yuan": f"¥{room.min_consume_fen / 100:.2f}",
                "room_fee_yuan": f"¥{room.room_fee_fen / 100:.2f}",
                "max_hours": room.max_hours,
                "overtime_fee_per_hour_yuan": f"¥{room.overtime_fee_per_hour_fen / 100:.2f}",
            })

        return available

    @staticmethod
    def get_room_revenue_report(
        bookings: List[RoomBooking],
    ) -> Dict[str, Any]:
        """
        包厢营收统计报表

        Args:
            bookings: 预订记录列表

        Returns:
            {
                "total_bookings": int,
                "completed_bookings": int,
                "cancelled_bookings": int,
                "total_order_revenue_fen": int,
                "total_room_fee_fen": int,
                "total_overtime_fee_fen": int,
                "grand_total_fen": int,
                "grand_total_yuan": str,
                "by_room": [...],
                "avg_duration_hours": float,
            }
        """
        if not bookings:
            return {
                "total_bookings": 0,
                "completed_bookings": 0,
                "cancelled_bookings": 0,
                "total_order_revenue_fen": 0,
                "total_room_fee_fen": 0,
                "total_overtime_fee_fen": 0,
                "grand_total_fen": 0,
                "grand_total_yuan": "¥0.00",
                "by_room": [],
                "avg_duration_hours": 0.0,
            }

        completed = [b for b in bookings if b.status == "completed"]
        cancelled = [b for b in bookings if b.status == "cancelled"]

        total_order = sum(b.order_total_fen for b in completed)
        total_room = sum(b.room_fee_fen for b in completed)
        total_overtime = sum(b.overtime_fee_fen for b in completed)
        grand = total_order + total_room + total_overtime

        # 按包厢分组统计
        room_stats: Dict[str, Dict[str, Any]] = {}
        total_duration = 0.0
        for b in completed:
            duration = (b.end_time - b.start_time).total_seconds() / 3600
            total_duration += duration

            if b.room_id not in room_stats:
                room_stats[b.room_id] = {
                    "room_id": b.room_id,
                    "room_name": b.room_name,
                    "booking_count": 0,
                    "order_revenue_fen": 0,
                    "room_fee_fen": 0,
                    "overtime_fee_fen": 0,
                    "total_fen": 0,
                }
            rs = room_stats[b.room_id]
            rs["booking_count"] += 1
            rs["order_revenue_fen"] += b.order_total_fen
            rs["room_fee_fen"] += b.room_fee_fen
            rs["overtime_fee_fen"] += b.overtime_fee_fen
            rs["total_fen"] = rs["order_revenue_fen"] + rs["room_fee_fen"] + rs["overtime_fee_fen"]

        by_room = []
        for rs in room_stats.values():
            rs["total_yuan"] = f"¥{rs['total_fen'] / 100:.2f}"
            by_room.append(rs)

        # 按营收降序排列
        by_room.sort(key=lambda x: x["total_fen"], reverse=True)

        avg_duration = total_duration / len(completed) if completed else 0.0

        return {
            "total_bookings": len(bookings),
            "completed_bookings": len(completed),
            "cancelled_bookings": len(cancelled),
            "total_order_revenue_fen": total_order,
            "total_room_fee_fen": total_room,
            "total_overtime_fee_fen": total_overtime,
            "grand_total_fen": grand,
            "grand_total_yuan": f"¥{grand / 100:.2f}",
            "by_room": by_room,
            "avg_duration_hours": round(avg_duration, 2),
        }
