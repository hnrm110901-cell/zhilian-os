"""
多端混合点单网关 — 小程序/手机/平板/电视/触摸屏统一接入

核心能力：
  1. 设备注册与会话管理（每个设备一个会话，绑定桌号/角色）
  2. 多端共享购物车（同一桌号的多台设备看到同一个购物车）
  3. 设备能力适配（小程序精简菜单 / 电视大图浏览 / 触摸屏完整操作）
  4. 冲突解决（并发加菜时的乐观锁 + 自动合并）
  5. 离线缓冲（设备断网时本地暂存，恢复后自动同步）
  6. 菜单推送（新菜上架/售罄/时价更新实时推送到所有设备）
  7. 影子模式透传（所有操作同时写入天财商龙）

架构：
  设备 → WebSocket/HTTP → MultiDeviceGateway → UnifiedPOSEngine → DB + 天财商龙
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger()


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class DeviceType(str, Enum):
    """设备类型"""
    MINI_PROGRAM = "mini_program"  # 微信/支付宝小程序
    MOBILE = "mobile"              # 手机（服务员/顾客）
    TABLET = "tablet"              # 平板（iPad 点单）
    TV = "tv"                      # 电视（大屏菜单展示）
    TOUCH_SCREEN = "touch_screen"  # 触摸屏（自助点单机）
    POS_TERMINAL = "pos_terminal"  # POS 收银终端
    KDS_SCREEN = "kds_screen"      # 厨房显示屏


class DeviceRole(str, Enum):
    """设备角色"""
    CUSTOMER_SELF = "customer_self"    # 顾客自助点单
    WAITER = "waiter"                  # 服务员点单
    CASHIER = "cashier"                # 收银员
    KITCHEN = "kitchen"                # 厨房
    MANAGER = "manager"                # 管理员
    DISPLAY = "display"                # 纯展示


class CartEventType(str, Enum):
    """购物车事件类型"""
    ITEM_ADDED = "item_added"
    ITEM_REMOVED = "item_removed"
    ITEM_UPDATED = "item_updated"
    CART_CLEARED = "cart_cleared"
    ORDER_PLACED = "order_placed"
    MENU_UPDATED = "menu_updated"
    PRICE_CHANGED = "price_changed"
    ITEM_SOLD_OUT = "item_sold_out"


class DeviceCapability(str, Enum):
    """设备能力"""
    FULL_MENU = "full_menu"          # 完整菜单（含图片/视频）
    COMPACT_MENU = "compact_menu"    # 精简菜单（文字+小图）
    ORDER_CREATE = "order_create"    # 可以下单
    ORDER_MODIFY = "order_modify"    # 可以改单
    PAYMENT = "payment"              # 可以收款
    KITCHEN_VIEW = "kitchen_view"    # 厨房视图
    WEIGHT_INPUT = "weight_input"    # 可以输入称重
    QR_SCAN = "qr_scan"             # 可以扫码


# ── 设备能力矩阵 ──────────────────────────────────────────────────────────────

DEVICE_CAPABILITIES: Dict[DeviceType, Set[DeviceCapability]] = {
    DeviceType.MINI_PROGRAM: {
        DeviceCapability.COMPACT_MENU,
        DeviceCapability.ORDER_CREATE,
        DeviceCapability.QR_SCAN,
    },
    DeviceType.MOBILE: {
        DeviceCapability.COMPACT_MENU,
        DeviceCapability.ORDER_CREATE,
        DeviceCapability.ORDER_MODIFY,
        DeviceCapability.QR_SCAN,
    },
    DeviceType.TABLET: {
        DeviceCapability.FULL_MENU,
        DeviceCapability.ORDER_CREATE,
        DeviceCapability.ORDER_MODIFY,
        DeviceCapability.WEIGHT_INPUT,
    },
    DeviceType.TV: {
        DeviceCapability.FULL_MENU,
    },
    DeviceType.TOUCH_SCREEN: {
        DeviceCapability.FULL_MENU,
        DeviceCapability.ORDER_CREATE,
        DeviceCapability.PAYMENT,
        DeviceCapability.QR_SCAN,
    },
    DeviceType.POS_TERMINAL: {
        DeviceCapability.FULL_MENU,
        DeviceCapability.ORDER_CREATE,
        DeviceCapability.ORDER_MODIFY,
        DeviceCapability.PAYMENT,
        DeviceCapability.WEIGHT_INPUT,
        DeviceCapability.QR_SCAN,
    },
    DeviceType.KDS_SCREEN: {
        DeviceCapability.KITCHEN_VIEW,
    },
}


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class DeviceSession:
    """设备会话"""
    def __init__(
        self,
        device_id: str,
        device_type: DeviceType,
        device_role: DeviceRole,
        store_id: str,
        table_code: Optional[str] = None,
        employee_id: Optional[str] = None,
    ):
        self.session_id = str(uuid.uuid4())
        self.device_id = device_id
        self.device_type = device_type
        self.device_role = device_role
        self.store_id = store_id
        self.table_code = table_code
        self.employee_id = employee_id
        self.capabilities = DEVICE_CAPABILITIES.get(device_type, set())
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.is_active = True
        self.offline_buffer: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "device_type": self.device_type.value,
            "device_role": self.device_role.value,
            "store_id": self.store_id,
            "table_code": self.table_code,
            "employee_id": self.employee_id,
            "capabilities": [c.value for c in self.capabilities],
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_active": self.is_active,
            "offline_buffer_size": len(self.offline_buffer),
        }


class SharedCart:
    """共享购物车（同桌多设备共享）"""
    def __init__(self, table_code: str, store_id: str):
        self.cart_id = str(uuid.uuid4())
        self.table_code = table_code
        self.store_id = store_id
        self.items: List[Dict[str, Any]] = []
        self.version = 0  # 乐观锁版本
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.contributors: Set[str] = set()  # 参与点单的设备 session_id

    def add_item(self, item: Dict[str, Any], session_id: str) -> int:
        """添加菜品，返回新版本号"""
        item["added_by"] = session_id
        item["added_at"] = datetime.utcnow().isoformat()
        self.items.append(item)
        self.version += 1
        self.updated_at = datetime.utcnow()
        self.contributors.add(session_id)
        return self.version

    def remove_item(self, item_index: int, session_id: str) -> int:
        """删除菜品"""
        if 0 <= item_index < len(self.items):
            self.items.pop(item_index)
            self.version += 1
            self.updated_at = datetime.utcnow()
        return self.version

    def update_item(self, item_index: int, updates: Dict[str, Any], session_id: str) -> int:
        """更新菜品（数量/备注/规格等）"""
        if 0 <= item_index < len(self.items):
            self.items[item_index].update(updates)
            self.items[item_index]["updated_by"] = session_id
            self.items[item_index]["updated_at"] = datetime.utcnow().isoformat()
            self.version += 1
            self.updated_at = datetime.utcnow()
        return self.version

    def clear(self) -> int:
        """清空购物车"""
        self.items = []
        self.version += 1
        self.updated_at = datetime.utcnow()
        return self.version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cart_id": self.cart_id,
            "table_code": self.table_code,
            "store_id": self.store_id,
            "items": self.items,
            "item_count": len(self.items),
            "version": self.version,
            "contributors": list(self.contributors),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ── 多端点单网关 ──────────────────────────────────────────────────────────────

class MultiDeviceOrderingGateway:
    """
    多端混合点单网关。

    统一管理所有点单设备的接入、购物车同步、菜单推送。
    """

    def __init__(self, store_id: str):
        self.store_id = store_id
        self._sessions: Dict[str, DeviceSession] = {}
        self._device_sessions: Dict[str, str] = {}  # device_id → session_id
        self._table_carts: Dict[str, SharedCart] = {}  # table_code → cart
        self._table_devices: Dict[str, Set[str]] = defaultdict(set)  # table → {session_ids}
        self._event_log: List[Dict[str, Any]] = []

    # ── 设备管理 ──────────────────────────────────────────────────────────────

    def register_device(
        self,
        device_id: str,
        device_type: DeviceType,
        device_role: DeviceRole,
        table_code: Optional[str] = None,
        employee_id: Optional[str] = None,
    ) -> DeviceSession:
        """注册设备并创建会话"""
        session = DeviceSession(
            device_id=device_id,
            device_type=device_type,
            device_role=device_role,
            store_id=self.store_id,
            table_code=table_code,
            employee_id=employee_id,
        )
        self._sessions[session.session_id] = session
        self._device_sessions[device_id] = session.session_id

        if table_code:
            self._table_devices[table_code].add(session.session_id)

        logger.info(
            "设备已注册",
            device_id=device_id,
            type=device_type.value,
            role=device_role.value,
            table=table_code,
        )
        return session

    def disconnect_device(self, session_id: str) -> None:
        """断开设备"""
        session = self._sessions.get(session_id)
        if session:
            session.is_active = False
            if session.table_code:
                self._table_devices[session.table_code].discard(session_id)

    def get_table_devices(self, table_code: str) -> List[Dict[str, Any]]:
        """获取桌台上所有在线设备"""
        session_ids = self._table_devices.get(table_code, set())
        return [
            self._sessions[sid].to_dict()
            for sid in session_ids
            if sid in self._sessions and self._sessions[sid].is_active
        ]

    # ── 共享购物车 ────────────────────────────────────────────────────────────

    def get_or_create_cart(self, table_code: str) -> SharedCart:
        """获取或创建桌台购物车"""
        if table_code not in self._table_carts:
            self._table_carts[table_code] = SharedCart(table_code, self.store_id)
        return self._table_carts[table_code]

    def add_to_cart(
        self,
        session_id: str,
        table_code: str,
        item: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        添加菜品到共享购物车。

        乐观锁：如果 expected_version 不匹配，返回冲突信息供前端自动合并。
        """
        cart = self.get_or_create_cart(table_code)

        # 乐观锁检查
        if expected_version is not None and expected_version != cart.version:
            return {
                "success": False,
                "conflict": True,
                "server_version": cart.version,
                "cart": cart.to_dict(),
                "message": "购物车已被其他设备修改，请刷新后重试",
            }

        new_version = cart.add_item(item, session_id)

        # 广播事件到同桌其他设备
        self._broadcast_cart_event(table_code, CartEventType.ITEM_ADDED, {
            "item": item,
            "version": new_version,
            "source_session": session_id,
        })

        return {
            "success": True,
            "version": new_version,
            "cart": cart.to_dict(),
        }

    def remove_from_cart(
        self,
        session_id: str,
        table_code: str,
        item_index: int,
    ) -> Dict[str, Any]:
        """从购物车删除菜品"""
        cart = self.get_or_create_cart(table_code)
        new_version = cart.remove_item(item_index, session_id)

        self._broadcast_cart_event(table_code, CartEventType.ITEM_REMOVED, {
            "item_index": item_index,
            "version": new_version,
            "source_session": session_id,
        })

        return {"success": True, "version": new_version, "cart": cart.to_dict()}

    def get_cart(self, table_code: str) -> Dict[str, Any]:
        """获取购物车状态"""
        cart = self.get_or_create_cart(table_code)
        return cart.to_dict()

    def clear_cart(self, table_code: str) -> None:
        """清空购物车"""
        if table_code in self._table_carts:
            self._table_carts[table_code].clear()
            self._broadcast_cart_event(table_code, CartEventType.CART_CLEARED, {})

    # ── 菜单适配 ──────────────────────────────────────────────────────────────

    def get_adapted_menu(
        self,
        session_id: str,
        full_menu: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        根据设备能力返回适配后的菜单。

        小程序：精简菜单（无图/小图）+ 快速选择
        平板：完整菜单 + 大图 + 详情
        电视：展示菜单（大图/视频）+ 推荐区
        触摸屏：自助点单模式 + 支付入口
        POS：完整菜单 + 称重输入 + 时价输入
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"menu": full_menu, "layout": "default"}

        capabilities = session.capabilities

        if DeviceCapability.FULL_MENU in capabilities:
            menu = full_menu
            layout = "full"
        else:
            # 精简菜单：去掉大图、详细描述
            menu = [
                {
                    "dish_id": d.get("dish_id"),
                    "name": d.get("name"),
                    "price_yuan": d.get("price_yuan"),
                    "unit": d.get("unit"),
                    "category": d.get("category_name"),
                    "is_available": d.get("is_available", True),
                    "pricing_mode": d.get("pricing_mode", "fixed"),
                    "thumbnail": d.get("image_url", "")[:100] if d.get("image_url") else "",
                }
                for d in full_menu
            ]
            layout = "compact"

        # 设备特定功能
        features = {
            "can_order": DeviceCapability.ORDER_CREATE in capabilities,
            "can_modify": DeviceCapability.ORDER_MODIFY in capabilities,
            "can_pay": DeviceCapability.PAYMENT in capabilities,
            "can_weigh": DeviceCapability.WEIGHT_INPUT in capabilities,
            "can_scan": DeviceCapability.QR_SCAN in capabilities,
        }

        return {
            "menu": menu,
            "layout": layout,
            "device_type": session.device_type.value,
            "features": features,
            "item_count": len(menu),
        }

    # ── 离线缓冲 ──────────────────────────────────────────────────────────────

    def buffer_offline_action(
        self,
        session_id: str,
        action: Dict[str, Any],
    ) -> bool:
        """缓存离线操作（设备恢复网络后批量同步）"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        action["buffered_at"] = datetime.utcnow().isoformat()
        session.offline_buffer.append(action)
        return True

    def flush_offline_buffer(self, session_id: str) -> List[Dict[str, Any]]:
        """刷新离线缓冲（设备恢复网络后调用）"""
        session = self._sessions.get(session_id)
        if not session:
            return []

        actions = session.offline_buffer[:]
        session.offline_buffer = []
        session.last_activity = datetime.utcnow()

        logger.info(
            "离线缓冲已刷新",
            session_id=session_id,
            action_count=len(actions),
        )
        return actions

    # ── 实时通知 ──────────────────────────────────────────────────────────────

    def notify_sold_out(self, dish_id: str, dish_name: str) -> None:
        """通知所有设备：菜品售罄"""
        for session in self._sessions.values():
            if session.is_active:
                self._send_to_session(session.session_id, {
                    "event": CartEventType.ITEM_SOLD_OUT.value,
                    "dish_id": dish_id,
                    "dish_name": dish_name,
                    "timestamp": datetime.utcnow().isoformat(),
                })

    def notify_price_change(self, dish_id: str, dish_name: str, new_price_fen: int) -> None:
        """通知所有设备：菜品价格变动（海鲜时价更新）"""
        from decimal import Decimal
        for session in self._sessions.values():
            if session.is_active:
                self._send_to_session(session.session_id, {
                    "event": CartEventType.PRICE_CHANGED.value,
                    "dish_id": dish_id,
                    "dish_name": dish_name,
                    "new_price_fen": new_price_fen,
                    "new_price_yuan": str(Decimal(str(new_price_fen)) / 100),
                    "timestamp": datetime.utcnow().isoformat(),
                })

    # ── 统计 ──────────────────────────────────────────────────────────────────

    def get_gateway_status(self) -> Dict[str, Any]:
        """获取网关状态"""
        active_sessions = [s for s in self._sessions.values() if s.is_active]
        device_type_counts = defaultdict(int)
        for s in active_sessions:
            device_type_counts[s.device_type.value] += 1

        return {
            "store_id": self.store_id,
            "total_sessions": len(self._sessions),
            "active_sessions": len(active_sessions),
            "device_breakdown": dict(device_type_counts),
            "active_tables": len(self._table_carts),
            "total_cart_items": sum(
                len(c.items) for c in self._table_carts.values()
            ),
        }

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _broadcast_cart_event(
        self,
        table_code: str,
        event_type: CartEventType,
        data: Dict[str, Any],
    ) -> None:
        """广播购物车事件到同桌所有设备"""
        session_ids = self._table_devices.get(table_code, set())
        source = data.get("source_session")

        event = {
            "event": event_type.value,
            "table_code": table_code,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        for sid in session_ids:
            if sid != source:  # 不回推给发起方
                self._send_to_session(sid, event)

        self._event_log.append(event)

    def _send_to_session(self, session_id: str, message: Dict[str, Any]) -> None:
        """发送消息到设备（实际场景通过 WebSocket 推送）"""
        # 实际实现中通过 WebSocket 连接池推送
        # 此处记录日志，WebSocket 实现在 API 层
        logger.debug("推送消息到设备", session_id=session_id, event_type=message.get("event"))
