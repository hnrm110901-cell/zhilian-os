"""
易订数据映射器 - YiDing Data Mapper

将易订真实API返回的中文缩写字段映射为智链OS统一格式
"""

from typing import Any, Dict, List, Optional

from .types import (
    UnifiedReservation,
    UnifiedCustomer,
    UnifiedTable,
    UnifiedBill,
    UnifiedDish,
    ReservationStats,
    ReservationStatus,
)


class YiDingMapper:
    """易订数据映射器"""

    # ============================================
    # 预订映射 Reservation Mapping
    # ============================================

    @staticmethod
    def _map_status(raw_status) -> ReservationStatus:
        """
        映射易订预订状态码

        易订状态: 1预订 2入座 3结账 4退订 6换桌
        """
        status_map = {
            1: ReservationStatus.PENDING,
            "1": ReservationStatus.PENDING,
            2: ReservationStatus.SEATED,
            "2": ReservationStatus.SEATED,
            3: ReservationStatus.COMPLETED,
            "3": ReservationStatus.COMPLETED,
            4: ReservationStatus.CANCELLED,
            "4": ReservationStatus.CANCELLED,
            6: ReservationStatus.TABLE_CHANGE,
            "6": ReservationStatus.TABLE_CHANGE,
        }
        return status_map.get(raw_status, ReservationStatus.PENDING)

    def to_unified_reservation(
        self,
        data: Dict[str, Any],
        store_id: Optional[str] = None,
    ) -> UnifiedReservation:
        """
        易订预订订单 → 统一格式

        对应接口: 2.1 获取线上预订订单 / 5.2 订单列表 / 5.3 订单列表V2
        """
        resv_order = str(data.get("resv_order", ""))
        raw_status = data.get("status", 1)

        result: UnifiedReservation = {
            "id": f"yiding_{resv_order}",
            "external_id": resv_order,
            "source": "yiding",
            "store_id": str(data.get("hotel_id", store_id or "")),
            "store_name": data.get("hotel_name", ""),
            "customer_name": data.get("vip_name", ""),
            "customer_phone": data.get("vip_phone", ""),
            "customer_sex": data.get("vip_sex", ""),
            "reservation_date": data.get("resv_date", ""),
            "dest_time": data.get("dest_time", ""),
            "party_size": int(data.get("resv_num", 0)),
            "area_code": data.get("area_code", ""),
            "table_code": data.get("table_code", ""),
            "meal_type_code": data.get("meal_type_code", ""),
            "meal_type_name": data.get("meal_type_name", ""),
            "status": self._map_status(raw_status),
            "raw_status": int(raw_status) if raw_status else 0,
            "sales_code": data.get("app_user_code", ""),
            "sales_name": data.get("app_user_name", ""),
            "deposit": int(data.get("deposit", 0)),
            "deposit_amount": str(data.get("deposit_amount", "0")),
            "pay_type": int(data.get("pay_type", 0)) if data.get("pay_type") else 0,
            "dish_standard": float(data.get("dish_standard", 0) or 0),
            "pay_amount": float(data.get("paymount", 0) or 0),
            "is_dish": int(data.get("is_dish", 0)),
            "order_type": int(data.get("order_type", 1) or 1),
            "remark": data.get("remark", ""),
            "created_at": data.get("created_at", ""),
        }

        # V2 特有字段
        if "table_area_name" in data:
            result["table_area_name"] = data["table_area_name"]
        if "table_name" in data:
            result["table_name"] = data["table_name"]
        if "sourceName" in data or "source_name" in data:
            result["source_name"] = data.get("sourceName", data.get("source_name", ""))
        if "inTableTime" in data:
            result["in_table_time"] = data["inTableTime"]

        return result

    def to_unified_reservations(
        self,
        data_list: List[Dict[str, Any]],
        store_id: Optional[str] = None,
    ) -> List[UnifiedReservation]:
        """批量转换预订订单"""
        return [
            self.to_unified_reservation(item, store_id)
            for item in (data_list or [])
        ]

    # ============================================
    # 客户映射 Customer Mapping
    # ============================================

    def to_unified_customer(
        self,
        data: Dict[str, Any],
    ) -> UnifiedCustomer:
        """
        易订会员信息 → 统一格式

        对应接口: 4.1 获取会员信息 / 5.1 获取会员列表
        """
        phone = data.get("vip_phone", "")

        return UnifiedCustomer(
            id=f"yiding_{phone}",
            source="yiding",
            phone=phone,
            name=data.get("vip_name", ""),
            sex=data.get("vip_sex", ""),
            company=data.get("vip_company", ""),
            address=data.get("vip_address", ""),
            birthday=data.get("vip_birthday", ""),
            total_amount=float(data.get("sum_amount", 0) or 0),
            total_visits=int(data.get("sum_ordered", 0) or 0),
            per_person=float(data.get("per_person", 0) or 0),
            last_visit=data.get("last_ordered", ""),
            first_class_value=data.get("first_class_value", ""),
            sub_value=data.get("sub_value", ""),
            hobby=data.get("hobby", ""),
            detest=data.get("detest", ""),
            tag=data.get("tag", ""),
            remark=data.get("remark", ""),
            short_phone_num=data.get("short_phone_num", ""),
            manager_name=data.get("app_user_name", ""),
            manager_phone=data.get("app_user_phone", ""),
            created_at=data.get("created_at", ""),
        )

    def to_unified_customers(
        self,
        data_list: List[Dict[str, Any]],
    ) -> List[UnifiedCustomer]:
        """批量转换会员"""
        return [self.to_unified_customer(item) for item in (data_list or [])]

    # ============================================
    # 统计计算 Stats
    # ============================================

    def compute_reservation_stats(
        self,
        reservations: List[UnifiedReservation],
        store_id: str,
        start_date: str,
        end_date: str,
    ) -> ReservationStats:
        """从预订列表计算统计数据"""
        status_breakdown: Dict[str, int] = {}
        total_party = 0
        total_deposit = 0.0
        total_pay = 0.0

        for r in reservations:
            status_key = r.get("status", ReservationStatus.PENDING).value
            status_breakdown[status_key] = status_breakdown.get(status_key, 0) + 1
            total_party += r.get("party_size", 0)
            try:
                total_deposit += float(r.get("deposit_amount", "0") or "0")
            except (ValueError, TypeError):
                pass
            total_pay += r.get("pay_amount", 0)

        total = len(reservations)
        avg_party = total_party / total if total > 0 else 0

        return ReservationStats(
            store_id=store_id,
            period_start=start_date,
            period_end=end_date,
            total_reservations=total,
            status_breakdown=status_breakdown,
            average_party_size=round(avg_party, 1),
            total_deposit=round(total_deposit, 2),
            total_pay_amount=round(total_pay, 2),
        )
