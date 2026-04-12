"""
多端混合点单网关测试

覆盖：
  - 设备注册（7种设备类型）
  - 共享购物车（同桌多设备共享）
  - 乐观锁冲突检测
  - 设备能力适配
  - 离线缓冲
  - 网关状态统计
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.multi_device_ordering_gateway import (
    MultiDeviceOrderingGateway,
    DeviceType,
    DeviceRole,
    DeviceCapability,
    DEVICE_CAPABILITIES,
)


def make_gateway() -> MultiDeviceOrderingGateway:
    return MultiDeviceOrderingGateway(store_id="S001")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 设备注册
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeviceRegistration:
    """设备注册测试"""

    def test_register_all_device_types(self):
        """注册所有7种设备类型"""
        gw = make_gateway()
        for dt in DeviceType:
            session = gw.register_device(
                device_id=f"DEV-{dt.value}",
                device_type=dt,
                device_role=DeviceRole.CUSTOMER_SELF,
                table_code="A01",
            )
            assert session.device_type == dt
            assert session.is_active is True

    def test_pos_terminal_full_capabilities(self):
        """POS 终端拥有全部能力"""
        gw = make_gateway()
        session = gw.register_device("POS-001", DeviceType.POS_TERMINAL, DeviceRole.CASHIER)
        assert DeviceCapability.FULL_MENU in session.capabilities
        assert DeviceCapability.ORDER_CREATE in session.capabilities
        assert DeviceCapability.PAYMENT in session.capabilities
        assert DeviceCapability.WEIGHT_INPUT in session.capabilities

    def test_mini_program_limited_capabilities(self):
        """小程序能力受限"""
        gw = make_gateway()
        session = gw.register_device("MP-001", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF)
        assert DeviceCapability.COMPACT_MENU in session.capabilities
        assert DeviceCapability.FULL_MENU not in session.capabilities
        assert DeviceCapability.PAYMENT not in session.capabilities

    def test_tv_display_only(self):
        """电视只有展示能力"""
        gw = make_gateway()
        session = gw.register_device("TV-001", DeviceType.TV, DeviceRole.DISPLAY)
        assert DeviceCapability.FULL_MENU in session.capabilities
        assert DeviceCapability.ORDER_CREATE not in session.capabilities

    def test_table_device_tracking(self):
        """桌台设备追踪"""
        gw = make_gateway()
        gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")
        gw.register_device("MP1", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF, table_code="A01")
        gw.register_device("T2", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A02")

        devices_a01 = gw.get_table_devices("A01")
        assert len(devices_a01) == 2

    def test_disconnect_device(self):
        """断开设备"""
        gw = make_gateway()
        session = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")
        gw.disconnect_device(session.session_id)

        devices = gw.get_table_devices("A01")
        assert len(devices) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 共享购物车
# ═══════════════════════════════════════════════════════════════════════════════


class TestSharedCart:
    """共享购物车测试"""

    def test_add_to_cart(self):
        """添加菜品到购物车"""
        gw = make_gateway()
        s1 = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")

        result = gw.add_to_cart(
            s1.session_id,
            "A01",
            {"dish_id": "D001", "dish_name": "小炒黄牛肉", "quantity": 1, "unit_price_fen": 5800},
        )
        assert result["success"] is True
        assert result["version"] == 1

    def test_multi_device_shared_cart(self):
        """多设备共享同一购物车"""
        gw = make_gateway()
        s1 = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")
        s2 = gw.register_device("MP1", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF, table_code="A01")

        gw.add_to_cart(s1.session_id, "A01", {"dish_name": "菜1", "quantity": 1, "unit_price_fen": 1000})
        gw.add_to_cart(s2.session_id, "A01", {"dish_name": "菜2", "quantity": 1, "unit_price_fen": 2000})

        cart = gw.get_cart("A01")
        assert cart["item_count"] == 2
        assert len(cart["contributors"]) == 2

    def test_optimistic_lock_conflict(self):
        """乐观锁冲突检测"""
        gw = make_gateway()
        s1 = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")
        s2 = gw.register_device("MP1", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF, table_code="A01")

        # s1 添加，版本变为 1
        gw.add_to_cart(s1.session_id, "A01", {"dish_name": "菜1", "quantity": 1})

        # s2 基于旧版本(0)添加 → 冲突
        result = gw.add_to_cart(
            s2.session_id, "A01",
            {"dish_name": "菜2", "quantity": 1},
            expected_version=0,
        )
        assert result["success"] is False
        assert result["conflict"] is True
        assert result["server_version"] == 1

    def test_no_conflict_when_version_matches(self):
        """版本匹配时无冲突"""
        gw = make_gateway()
        s1 = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")

        r1 = gw.add_to_cart(s1.session_id, "A01", {"dish_name": "菜1", "quantity": 1})
        r2 = gw.add_to_cart(
            s1.session_id, "A01",
            {"dish_name": "菜2", "quantity": 1},
            expected_version=r1["version"],
        )
        assert r2["success"] is True

    def test_remove_from_cart(self):
        """从购物车删除"""
        gw = make_gateway()
        s1 = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")

        gw.add_to_cart(s1.session_id, "A01", {"dish_name": "菜1"})
        gw.add_to_cart(s1.session_id, "A01", {"dish_name": "菜2"})

        result = gw.remove_from_cart(s1.session_id, "A01", 0)
        assert result["cart"]["item_count"] == 1

    def test_clear_cart(self):
        """清空购物车"""
        gw = make_gateway()
        s1 = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")

        gw.add_to_cart(s1.session_id, "A01", {"dish_name": "菜1"})
        gw.add_to_cart(s1.session_id, "A01", {"dish_name": "菜2"})
        gw.clear_cart("A01")

        cart = gw.get_cart("A01")
        assert cart["item_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 菜单适配
# ═══════════════════════════════════════════════════════════════════════════════


class TestMenuAdaptation:
    """菜单适配测试"""

    def test_full_menu_for_tablet(self):
        """平板显示完整菜单"""
        gw = make_gateway()
        session = gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF)

        menu = [
            {"dish_id": "D1", "name": "菜1", "price_yuan": "58.00", "image_url": "http://img/d1.jpg", "description": "long desc"},
        ]
        result = gw.get_adapted_menu(session.session_id, menu)
        assert result["layout"] == "full"
        assert result["features"]["can_order"] is True
        assert result["features"]["can_weigh"] is True

    def test_compact_menu_for_mini_program(self):
        """小程序显示精简菜单"""
        gw = make_gateway()
        session = gw.register_device("MP1", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF)

        menu = [
            {"dish_id": "D1", "name": "菜1", "price_yuan": "58.00", "image_url": "http://img/d1.jpg", "description": "long desc"},
        ]
        result = gw.get_adapted_menu(session.session_id, menu)
        assert result["layout"] == "compact"
        assert result["features"]["can_pay"] is False

    def test_kds_kitchen_view(self):
        """KDS 只有厨房视图"""
        gw = make_gateway()
        session = gw.register_device("KDS-1", DeviceType.KDS_SCREEN, DeviceRole.KITCHEN)
        result = gw.get_adapted_menu(session.session_id, [])
        assert result["features"]["can_order"] is False
        assert "kitchen_view" in [c.value for c in session.capabilities]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 离线缓冲
# ═══════════════════════════════════════════════════════════════════════════════


class TestOfflineBuffer:
    """离线缓冲测试"""

    def test_buffer_offline_action(self):
        """缓存离线操作"""
        gw = make_gateway()
        session = gw.register_device("MP1", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF)

        result = gw.buffer_offline_action(session.session_id, {"action": "add_item", "dish_id": "D1"})
        assert result is True
        assert session.offline_buffer_size == 1

    def test_flush_offline_buffer(self):
        """刷新离线缓冲"""
        gw = make_gateway()
        session = gw.register_device("MP1", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF)

        gw.buffer_offline_action(session.session_id, {"action": "add_item", "dish_id": "D1"})
        gw.buffer_offline_action(session.session_id, {"action": "add_item", "dish_id": "D2"})

        actions = gw.flush_offline_buffer(session.session_id)
        assert len(actions) == 2
        assert len(session.offline_buffer) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 网关状态
# ═══════════════════════════════════════════════════════════════════════════════


class TestGatewayStatus:
    """网关状态测试"""

    def test_gateway_status(self):
        """网关状态统计"""
        gw = make_gateway()
        gw.register_device("T1", DeviceType.TABLET, DeviceRole.CUSTOMER_SELF, table_code="A01")
        gw.register_device("MP1", DeviceType.MINI_PROGRAM, DeviceRole.CUSTOMER_SELF, table_code="A01")
        gw.register_device("POS1", DeviceType.POS_TERMINAL, DeviceRole.CASHIER)

        status = gw.get_gateway_status()
        assert status["total_sessions"] == 3
        assert status["active_sessions"] == 3
        assert status["device_breakdown"]["tablet"] == 1
        assert status["device_breakdown"]["mini_program"] == 1
        assert status["device_breakdown"]["pos_terminal"] == 1

    def test_device_capability_matrix(self):
        """设备能力矩阵完整性"""
        for dt in DeviceType:
            assert dt in DEVICE_CAPABILITIES, f"缺少 {dt.value} 的能力定义"
            caps = DEVICE_CAPABILITIES[dt]
            assert len(caps) > 0, f"{dt.value} 至少应有1个能力"
