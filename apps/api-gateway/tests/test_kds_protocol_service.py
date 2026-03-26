"""
KDS 厨打协议服务测试

覆盖：
  - 设备注册/心跳/健康检查
  - 厨打分单路由（按工位）
  - 状态流转（接单→制作→装盘→出餐→上菜）
  - 催菜优先级提升
  - 工位队列查询
  - 催菜员汇总视图
  - 打印数据生成
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.kds_protocol_service import (
    KDSProtocolService,
    KDSDeviceType,
    StationCategory,
    PrinterProtocol,
    TicketStatus,
)


def make_service() -> KDSProtocolService:
    return KDSProtocolService(store_id="S001")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 设备管理
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeviceManagement:
    """设备管理测试"""

    def test_register_kds_device(self):
        """注册 KDS 屏"""
        svc = make_service()
        device = svc.register_device(
            device_id="KDS-001",
            device_name="炒锅KDS",
            device_type=KDSDeviceType.KDS_SCREEN,
            station=StationCategory.HOT_WOK,
            ip_address="192.168.1.100",
        )
        assert device.device_id == "KDS-001"
        assert device.station == StationCategory.HOT_WOK
        assert device.is_online is True

    def test_register_printer(self):
        """注册打印机"""
        svc = make_service()
        device = svc.register_device(
            device_id="PRT-001",
            device_name="海鲜档打印机",
            device_type=KDSDeviceType.PRINTER,
            station=StationCategory.SEAFOOD,
            printer_protocol=PrinterProtocol.ESC_POS,
        )
        assert device.device_type == KDSDeviceType.PRINTER

    def test_heartbeat(self):
        """心跳更新"""
        svc = make_service()
        svc.register_device("KDS-001", "test", KDSDeviceType.KDS_SCREEN)
        assert svc.heartbeat("KDS-001") is True
        assert svc.heartbeat("nonexistent") is False

    def test_get_devices_by_station(self):
        """按工位获取设备"""
        svc = make_service()
        svc.register_device("KDS-001", "炒锅", KDSDeviceType.KDS_SCREEN, StationCategory.HOT_WOK)
        svc.register_device("KDS-002", "蒸柜", KDSDeviceType.KDS_SCREEN, StationCategory.STEAMER)
        svc.register_device("KDS-003", "炒锅2", KDSDeviceType.KDS_SCREEN, StationCategory.HOT_WOK)

        hot_wok_devices = svc.get_devices(StationCategory.HOT_WOK)
        assert len(hot_wok_devices) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 厨打分单
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatch:
    """厨打分单测试"""

    def test_dispatch_by_station(self):
        """按工位分票"""
        svc = make_service()
        svc.register_device("KDS-HOT", "炒锅", KDSDeviceType.KDS_SCREEN, StationCategory.HOT_WOK)
        svc.register_device("KDS-COLD", "凉菜", KDSDeviceType.KDS_SCREEN, StationCategory.COLD_DISH)

        tickets = svc.dispatch_order(
            order_id="O001",
            order_number="DI20260326001",
            table_code="A01",
            items=[
                {"dish_name": "小炒黄牛肉", "quantity": 1, "kitchen_station": "hot_wok"},
                {"dish_name": "辣椒炒肉", "quantity": 1, "kitchen_station": "hot_wok"},
                {"dish_name": "凉拌木耳", "quantity": 2, "kitchen_station": "cold_dish"},
            ],
        )
        assert len(tickets) == 2
        hot_wok = [t for t in tickets if t["station"] == "hot_wok"][0]
        assert hot_wok["item_count"] == 2
        assert hot_wok["status"] == "received"

    def test_dispatch_assigns_device(self):
        """分票时分配设备"""
        svc = make_service()
        svc.register_device("KDS-HOT", "炒锅", KDSDeviceType.KDS_SCREEN, StationCategory.HOT_WOK)

        tickets = svc.dispatch_order(
            order_id="O001",
            order_number="DI001",
            table_code="A01",
            items=[{"dish_name": "test", "quantity": 1, "kitchen_station": "hot_wok"}],
        )
        assert tickets[0]["assigned_device_id"] == "KDS-HOT"

    def test_dispatch_load_balance(self):
        """负载均衡"""
        svc = make_service()
        svc.register_device("KDS-HOT-1", "炒锅1", KDSDeviceType.KDS_SCREEN, StationCategory.HOT_WOK)
        svc.register_device("KDS-HOT-2", "炒锅2", KDSDeviceType.KDS_SCREEN, StationCategory.HOT_WOK)

        # 第一单分配到 KDS-HOT-1（负载为0）
        t1 = svc.dispatch_order("O1", "DI001", "A01", [{"dish_name": "d1", "quantity": 1, "kitchen_station": "hot_wok"}])
        # 第二单分配到 KDS-HOT-2（KDS-HOT-1 负载为1）
        t2 = svc.dispatch_order("O2", "DI002", "A02", [{"dish_name": "d2", "quantity": 1, "kitchen_station": "hot_wok"}])

        assert t1[0]["assigned_device_id"] != t2[0]["assigned_device_id"]

    def test_dispatch_no_device_fallback(self):
        """无对应设备时仍可分票"""
        svc = make_service()
        tickets = svc.dispatch_order(
            order_id="O001",
            order_number="DI001",
            table_code="A01",
            items=[{"dish_name": "test", "quantity": 1, "kitchen_station": "hot_wok"}],
        )
        assert len(tickets) == 1
        assert tickets[0]["assigned_device_id"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 状态流转
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatusTransition:
    """状态流转测试"""

    def test_full_lifecycle(self):
        """完整生命周期：接单→制作→装盘→出餐→上菜"""
        svc = make_service()
        tickets = svc.dispatch_order(
            "O001", "DI001", "A01",
            [{"dish_name": "test", "quantity": 1, "kitchen_station": "hot_wok"}],
        )
        tid = tickets[0]["ticket_id"]

        # 接单 → 制作
        r = svc.update_ticket_status(tid, TicketStatus.COOKING)
        assert r["status"] == "cooking"

        # 制作 → 装盘
        r = svc.update_ticket_status(tid, TicketStatus.PLATING)
        assert r["status"] == "plating"

        # 装盘 → 出餐
        r = svc.update_ticket_status(tid, TicketStatus.READY)
        assert r["status"] == "ready"

        # 出餐 → 上菜
        r = svc.update_ticket_status(tid, TicketStatus.SERVED)
        assert r["status"] == "served"

    def test_update_nonexistent_ticket(self):
        """更新不存在的票"""
        svc = make_service()
        result = svc.update_ticket_status("fake_id", TicketStatus.COOKING)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 催菜
# ═══════════════════════════════════════════════════════════════════════════════


class TestRush:
    """催菜测试"""

    def test_rush_increases_priority(self):
        """催菜提升优先级"""
        svc = make_service()
        svc.dispatch_order(
            "O001", "DI001", "A01",
            [{"dish_name": "test", "quantity": 1, "kitchen_station": "hot_wok"}],
        )
        rushed = svc.rush_order("O001")
        assert len(rushed) == 1
        assert rushed[0]["priority"] >= 1

    def test_rush_only_active_tickets(self):
        """催菜只影响活跃票"""
        svc = make_service()
        tickets = svc.dispatch_order(
            "O001", "DI001", "A01",
            [
                {"dish_name": "d1", "quantity": 1, "kitchen_station": "hot_wok"},
                {"dish_name": "d2", "quantity": 1, "kitchen_station": "cold_dish"},
            ],
        )
        # 标记凉菜为已上菜
        svc.update_ticket_status(tickets[1]["ticket_id"], TicketStatus.SERVED)

        rushed = svc.rush_order("O001")
        assert len(rushed) == 1  # 只有炒锅的票被催


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 查询
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuery:
    """查询测试"""

    def test_station_queue(self):
        """工位队列查询"""
        svc = make_service()
        svc.dispatch_order("O1", "DI001", "A01", [{"dish_name": "d1", "quantity": 1, "kitchen_station": "hot_wok"}])
        svc.dispatch_order("O2", "DI002", "A02", [{"dish_name": "d2", "quantity": 1, "kitchen_station": "hot_wok"}])

        queue = svc.get_station_queue(StationCategory.HOT_WOK)
        assert len(queue) == 2

    def test_order_kitchen_status(self):
        """订单厨房进度"""
        svc = make_service()
        svc.dispatch_order(
            "O001", "DI001", "A01",
            [
                {"dish_name": "d1", "quantity": 1, "kitchen_station": "hot_wok"},
                {"dish_name": "d2", "quantity": 1, "kitchen_station": "cold_dish"},
            ],
        )
        status = svc.get_order_kitchen_status("O001")
        assert status["total_tickets"] == 2
        assert status["progress_pct"] == 0.0

    def test_expeditor_view(self):
        """催菜员汇总视图"""
        svc = make_service()
        svc.dispatch_order("O1", "DI001", "A01", [{"dish_name": "d1", "quantity": 1, "kitchen_station": "hot_wok"}])
        svc.dispatch_order("O2", "DI002", "B01", [{"dish_name": "d2", "quantity": 1, "kitchen_station": "seafood"}])

        view = svc.get_expeditor_view()
        assert view["total_active_tickets"] == 2
        assert "hot_wok" in view["stations"]
        assert "seafood" in view["stations"]

    def test_print_data(self):
        """打印数据生成"""
        svc = make_service()
        tickets = svc.dispatch_order(
            "O001", "DI001", "A01",
            [{"dish_name": "小炒黄牛肉", "quantity": 1, "kitchen_station": "hot_wok", "notes": "少盐"}],
        )
        print_data = svc.generate_print_data(tickets[0]["ticket_id"])
        assert print_data is not None
        assert print_data["format"] == "esc_pos"
        assert len(print_data["items"]) == 1
        assert print_data["items"][0]["name"] == "小炒黄牛肉"
