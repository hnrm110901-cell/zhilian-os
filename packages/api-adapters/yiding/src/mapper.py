"""
易订数据映射器 - YiDing Data Mapper

负责在易订原始格式和智链OS统一格式之间转换数据
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from .types import (
    UnifiedReservation,
    UnifiedCustomer,
    UnifiedTable,
    ReservationStats,
    YiDingReservation,
    YiDingCustomer,
    YiDingTable,
    CreateReservationDTO,
    UpdateReservationDTO,
    ReservationStatus,
    TableType,
    TableStatus
)


class YiDingMapper:
    """易订数据映射器"""

    # ============================================
    # 预订映射 Reservation Mapping
    # ============================================

    def to_unified_reservation(
        self,
        yiding_data: YiDingReservation
    ) -> UnifiedReservation:
        """
        易订预订 → 统一格式

        Args:
            yiding_data: 易订预订数据

        Returns:
            统一格式预订
        """
        return UnifiedReservation(
            id=f"yiding_{yiding_data['id']}",
            external_id=yiding_data["id"],
            source="yiding",
            store_id=yiding_data["store_id"],

            # 客户信息
            customer_id=yiding_data["customer_id"],
            customer_name=yiding_data["customer_name"],
            customer_phone=yiding_data["customer_phone"],

            # 预订信息
            reservation_date=yiding_data["reservation_date"],
            reservation_time=yiding_data["reservation_time"],
            party_size=yiding_data["party_size"],
            table_type=self._map_table_type(yiding_data["table_type"]),
            table_number=yiding_data.get("table_number"),

            # 状态
            status=self._map_status(yiding_data["status"]),

            # 金额
            deposit_amount=yiding_data.get("deposit_amount", 0),
            estimated_amount=yiding_data.get("estimated_amount", 0),

            # 备注
            special_requests=yiding_data.get("special_requests"),
            note=yiding_data.get("note"),

            # 时间戳
            created_at=yiding_data["created_at"],
            updated_at=yiding_data["updated_at"],
            confirmed_at=yiding_data.get("confirmed_at"),
            seated_at=yiding_data.get("seated_at"),
            completed_at=yiding_data.get("completed_at")
        )

    def to_yiding_reservation(
        self,
        data: CreateReservationDTO
    ) -> Dict[str, Any]:
        """
        统一格式 → 易订预订

        Args:
            data: 创建预订DTO

        Returns:
            易订格式预订数据
        """
        return {
            "store_id": data["store_id"],
            "customer_name": data["customer_name"],
            "customer_phone": data["customer_phone"],
            "reservation_date": data["reservation_date"],
            "reservation_time": data["reservation_time"],
            "party_size": data["party_size"],
            "table_type": self._reverse_map_table_type(
                data.get("table_type", TableType.MEDIUM)
            ),
            "special_requests": data.get("special_requests"),
            "source": "zhilianos"  # 标记来源
        }

    def to_yiding_reservation_update(
        self,
        data: UpdateReservationDTO
    ) -> Dict[str, Any]:
        """
        更新DTO → 易订更新格式

        Args:
            data: 更新预订DTO

        Returns:
            易订格式更新数据
        """
        result = {}

        if "reservation_date" in data:
            result["reservation_date"] = data["reservation_date"]
        if "reservation_time" in data:
            result["reservation_time"] = data["reservation_time"]
        if "party_size" in data:
            result["party_size"] = data["party_size"]
        if "table_type" in data:
            result["table_type"] = self._reverse_map_table_type(data["table_type"])
        if "table_number" in data:
            result["table_number"] = data["table_number"]
        if "special_requests" in data:
            result["special_requests"] = data["special_requests"]
        if "status" in data:
            result["status"] = self._reverse_map_status(data["status"])

        return result

    # ============================================
    # 客户映射 Customer Mapping
    # ============================================

    def to_unified_customer(
        self,
        yiding_data: YiDingCustomer
    ) -> UnifiedCustomer:
        """
        易订客户 → 统一格式

        Args:
            yiding_data: 易订客户数据

        Returns:
            统一格式客户
        """
        return UnifiedCustomer(
            id=f"yiding_{yiding_data['id']}",
            external_id=yiding_data["id"],
            source="yiding",

            phone=yiding_data["phone"],
            name=yiding_data["name"],
            gender=yiding_data.get("gender"),
            birthday=yiding_data.get("birthday"),

            # 会员信息
            member_level=yiding_data.get("member_level"),
            member_points=yiding_data.get("points"),
            balance=yiding_data.get("balance"),

            # 统计
            total_visits=yiding_data.get("visit_count", 0),
            total_spent=yiding_data.get("total_spent", 0),
            last_visit=yiding_data.get("last_visit_date"),

            # 偏好
            preferences={
                "favorite_dishes": yiding_data.get("favorite_dishes", []),
                "table_preference": yiding_data.get("preferred_table"),
                "time_preference": yiding_data.get("preferred_time"),
                "dietary_restrictions": yiding_data.get("dietary_restrictions", [])
            },

            tags=yiding_data.get("tags", []),
            created_at=yiding_data["created_at"],
            updated_at=yiding_data["updated_at"]
        )

    # ============================================
    # 桌台映射 Table Mapping
    # ============================================

    def to_unified_table(
        self,
        yiding_data: YiDingTable
    ) -> UnifiedTable:
        """
        易订桌台 → 统一格式

        Args:
            yiding_data: 易订桌台数据

        Returns:
            统一格式桌台
        """
        return UnifiedTable(
            id=f"yiding_{yiding_data['id']}",
            table_number=yiding_data["table_number"],
            table_type=self._map_table_type(yiding_data["table_type"]),
            capacity=yiding_data["capacity"],
            min_capacity=yiding_data["min_capacity"],
            status=self._map_table_status(yiding_data["status"]),
            location=yiding_data.get("location"),
            features=yiding_data.get("features", [])
        )

    # ============================================
    # 统计映射 Stats Mapping
    # ============================================

    def to_reservation_stats(
        self,
        yiding_data: Dict[str, Any]
    ) -> ReservationStats:
        """
        易订统计 → 统一格式

        Args:
            yiding_data: 易订统计数据

        Returns:
            统一格式统计
        """
        total = yiding_data.get("total_reservations", 0)

        return ReservationStats(
            store_id=yiding_data["store_id"],
            period_start=yiding_data["period_start"],
            period_end=yiding_data["period_end"],
            total_reservations=total,
            confirmed_count=yiding_data.get("confirmed_count", 0),
            cancelled_count=yiding_data.get("cancelled_count", 0),
            no_show_count=yiding_data.get("no_show_count", 0),
            confirmation_rate=yiding_data.get("confirmation_rate", 0.0),
            cancellation_rate=yiding_data.get("cancellation_rate", 0.0),
            no_show_rate=yiding_data.get("no_show_rate", 0.0),
            average_party_size=yiding_data.get("average_party_size", 0.0),
            peak_hours=yiding_data.get("peak_hours", []),
            revenue_from_reservations=yiding_data.get("revenue", 0)
        )

    # ============================================
    # 辅助映射方法 Helper Mapping Methods
    # ============================================

    def _map_status(self, yiding_status: str) -> ReservationStatus:
        """映射预订状态: 易订 → 统一"""
        status_map = {
            "pending": ReservationStatus.PENDING,
            "confirmed": ReservationStatus.CONFIRMED,
            "arrived": ReservationStatus.SEATED,
            "finished": ReservationStatus.COMPLETED,
            "cancelled": ReservationStatus.CANCELLED,
            "noshow": ReservationStatus.NO_SHOW
        }
        return status_map.get(yiding_status, ReservationStatus.PENDING)

    def _reverse_map_status(self, status: ReservationStatus) -> str:
        """映射预订状态: 统一 → 易订"""
        status_map = {
            ReservationStatus.PENDING: "pending",
            ReservationStatus.CONFIRMED: "confirmed",
            ReservationStatus.SEATED: "arrived",
            ReservationStatus.COMPLETED: "finished",
            ReservationStatus.CANCELLED: "cancelled",
            ReservationStatus.NO_SHOW: "noshow"
        }
        return status_map.get(status, "pending")

    def _map_table_type(self, yiding_type: str) -> TableType:
        """映射桌型: 易订 → 统一"""
        type_map = {
            "small": TableType.SMALL,
            "medium": TableType.MEDIUM,
            "large": TableType.LARGE,
            "round": TableType.ROUND,
            "private": TableType.PRIVATE_ROOM
        }
        return type_map.get(yiding_type, TableType.MEDIUM)

    def _reverse_map_table_type(self, table_type: TableType) -> str:
        """映射桌型: 统一 → 易订"""
        type_map = {
            TableType.SMALL: "small",
            TableType.MEDIUM: "medium",
            TableType.LARGE: "large",
            TableType.ROUND: "round",
            TableType.PRIVATE_ROOM: "private"
        }
        return type_map.get(table_type, "medium")

    def _map_table_status(self, yiding_status: str) -> TableStatus:
        """映射桌台状态: 易订 → 统一"""
        status_map = {
            "available": TableStatus.AVAILABLE,
            "occupied": TableStatus.OCCUPIED,
            "reserved": TableStatus.RESERVED,
            "maintenance": TableStatus.MAINTENANCE
        }
        return status_map.get(yiding_status, TableStatus.AVAILABLE)
