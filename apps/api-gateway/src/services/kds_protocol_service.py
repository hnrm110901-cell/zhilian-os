"""
KDS 厨打协议服务 — 厨房显示系统 + 打印机管理 + 出餐协调

核心能力：
  1. 厨打分单路由（按工位/打印机/KDS屏幕自动分发）
  2. KDS 实时状态管理（接单→制作→装盘→出餐→上菜）
  3. 催菜/加急优先级调整
  4. 出餐计时与超时预警
  5. 工位负载均衡
  6. 打印机/KDS设备注册与心跳
  7. WebSocket 实时推送（给 KDS 大屏和收银台）
  8. 影子模式同步（双写天财商龙厨房状态）

金额规则：本服务不涉及金额
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

class TicketStatus(str, Enum):
    """厨打票状态"""
    QUEUED = "queued"          # 排队中
    RECEIVED = "received"      # 已接单（KDS 已显示）
    COOKING = "cooking"        # 制作中
    PLATING = "plating"        # 装盘中
    READY = "ready"            # 出餐就绪
    SERVED = "served"          # 已上菜
    RETURNED = "returned"      # 退菜
    CANCELLED = "cancelled"    # 已取消


class KDSDeviceType(str, Enum):
    """KDS 设备类型"""
    KDS_SCREEN = "kds_screen"    # 厨房显示屏
    PRINTER = "printer"          # 厨打打印机
    RUNNER_SCREEN = "runner"     # 传菜口屏幕
    EXPEDITOR = "expeditor"      # 催菜员屏（汇总所有工位）


class StationCategory(str, Enum):
    """工位分类"""
    HOT_WOK = "hot_wok"           # 炒锅
    STEAMER = "steamer"           # 蒸柜
    DEEP_FRY = "deep_fry"        # 油炸
    COLD_DISH = "cold_dish"       # 凉菜
    SEAFOOD = "seafood"           # 海鲜档口
    SOUP = "soup"                 # 汤/煲
    PASTRY = "pastry"             # 面点
    GRILL = "grill"               # 烧烤/铁板
    BEVERAGE = "beverage"         # 饮品
    PREP = "prep"                 # 打荷/备料


class PrinterProtocol(str, Enum):
    """打印机协议"""
    ESC_POS = "esc_pos"       # 热敏小票（ESC/POS）
    NETWORK = "network"        # 网络打印机
    BLUETOOTH = "bluetooth"    # 蓝牙打印
    USB = "usb"                # USB 直连


# ── 数据结构 ──────────────────────────────────────────────────────────────────

class KitchenTicket:
    """厨打票"""
    def __init__(
        self,
        order_id: str,
        order_number: str,
        table_code: str,
        station: StationCategory,
        items: List[Dict[str, Any]],
        priority: int = 0,
        scene: str = "dine_in",
    ):
        self.ticket_id = str(uuid.uuid4())
        self.order_id = order_id
        self.order_number = order_number
        self.table_code = table_code
        self.station = station
        self.items = items
        self.priority = priority
        self.scene = scene
        self.status = TicketStatus.QUEUED
        self.created_at = datetime.utcnow()
        self.received_at: Optional[datetime] = None
        self.cooking_at: Optional[datetime] = None
        self.ready_at: Optional[datetime] = None
        self.served_at: Optional[datetime] = None
        self.target_minutes: int = self._estimate_cook_time()
        self.assigned_device_id: Optional[str] = None

    def _estimate_cook_time(self) -> int:
        """估算制作时间（分钟）"""
        base_time = {
            StationCategory.COLD_DISH: 5,
            StationCategory.BEVERAGE: 3,
            StationCategory.PASTRY: 8,
            StationCategory.SOUP: 15,
            StationCategory.HOT_WOK: 10,
            StationCategory.STEAMER: 12,
            StationCategory.DEEP_FRY: 8,
            StationCategory.SEAFOOD: 12,
            StationCategory.GRILL: 10,
            StationCategory.PREP: 5,
        }
        base = base_time.get(self.station, 10)
        # 多菜品增加时间
        extra = max(0, (len(self.items) - 1) * 2)
        return base + extra

    @property
    def elapsed_seconds(self) -> int:
        start = self.cooking_at or self.received_at or self.created_at
        return int((datetime.utcnow() - start).total_seconds())

    @property
    def is_overdue(self) -> bool:
        return self.elapsed_seconds > self.target_minutes * 60

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "order_id": self.order_id,
            "order_number": self.order_number,
            "table_code": self.table_code,
            "station": self.station.value,
            "items": self.items,
            "item_count": len(self.items),
            "priority": self.priority,
            "scene": self.scene,
            "status": self.status.value,
            "target_minutes": self.target_minutes,
            "elapsed_seconds": self.elapsed_seconds,
            "is_overdue": self.is_overdue,
            "created_at": self.created_at.isoformat(),
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "cooking_at": self.cooking_at.isoformat() if self.cooking_at else None,
            "ready_at": self.ready_at.isoformat() if self.ready_at else None,
            "served_at": self.served_at.isoformat() if self.served_at else None,
            "assigned_device_id": self.assigned_device_id,
        }


class KDSDevice:
    """KDS 设备"""
    def __init__(
        self,
        device_id: str,
        device_name: str,
        device_type: KDSDeviceType,
        station: Optional[StationCategory] = None,
        ip_address: str = "",
        printer_protocol: Optional[PrinterProtocol] = None,
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.device_type = device_type
        self.station = station
        self.ip_address = ip_address
        self.printer_protocol = printer_protocol
        self.is_online = True
        self.last_heartbeat = datetime.utcnow()
        self.current_load = 0  # 当前待处理票数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_type": self.device_type.value,
            "station": self.station.value if self.station else None,
            "ip_address": self.ip_address,
            "is_online": self.is_online,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "current_load": self.current_load,
        }


# ── KDS 协议服务 ──────────────────────────────────────────────────────────────

class KDSProtocolService:
    """
    KDS 厨打协议服务。

    管理厨房显示系统、打印机、出餐协调的核心服务。
    """

    def __init__(self, store_id: str):
        self.store_id = store_id
        self._devices: Dict[str, KDSDevice] = {}
        self._tickets: Dict[str, KitchenTicket] = {}
        self._station_queues: Dict[StationCategory, List[str]] = defaultdict(list)
        self._order_tickets: Dict[str, List[str]] = defaultdict(list)
        # WebSocket 订阅者
        self._subscribers: Dict[str, Set] = defaultdict(set)

    # ── 设备管理 ──────────────────────────────────────────────────────────────

    def register_device(
        self,
        device_id: str,
        device_name: str,
        device_type: KDSDeviceType,
        station: Optional[StationCategory] = None,
        ip_address: str = "",
        printer_protocol: Optional[PrinterProtocol] = None,
    ) -> KDSDevice:
        """注册 KDS 设备/打印机"""
        device = KDSDevice(
            device_id=device_id,
            device_name=device_name,
            device_type=device_type,
            station=station,
            ip_address=ip_address,
            printer_protocol=printer_protocol,
        )
        self._devices[device_id] = device
        logger.info("KDS设备注册", device_id=device_id, type=device_type.value, station=station)
        return device

    def heartbeat(self, device_id: str) -> bool:
        """设备心跳"""
        device = self._devices.get(device_id)
        if not device:
            return False
        device.last_heartbeat = datetime.utcnow()
        device.is_online = True
        return True

    def get_devices(self, station: Optional[StationCategory] = None) -> List[Dict[str, Any]]:
        """获取设备列表"""
        devices = self._devices.values()
        if station:
            devices = [d for d in devices if d.station == station]
        return [d.to_dict() for d in devices]

    def check_device_health(self) -> List[Dict[str, Any]]:
        """检查设备健康（超过60s无心跳视为离线）"""
        threshold = datetime.utcnow() - timedelta(seconds=60)
        alerts = []
        for device in self._devices.values():
            if device.last_heartbeat < threshold and device.is_online:
                device.is_online = False
                alerts.append({
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "last_heartbeat": device.last_heartbeat.isoformat(),
                    "alert": "offline",
                })
        return alerts

    # ── 厨打分单 ──────────────────────────────────────────────────────────────

    def dispatch_order(
        self,
        order_id: str,
        order_number: str,
        table_code: str,
        items: List[Dict[str, Any]],
        priority: int = 0,
        scene: str = "dine_in",
    ) -> List[Dict[str, Any]]:
        """
        按工位拆分厨打票并分配到设备。

        自动路由规则：
          1. 按菜品的 kitchen_station 分组
          2. 每个工位找到在线的 KDS/打印机
          3. 优先分配到负载最低的设备
          4. 无对应设备则分配到 expeditor（催菜员汇总屏）
        """
        # 按工位分组
        station_items: Dict[StationCategory, List[Dict[str, Any]]] = defaultdict(list)
        for item in items:
            station_str = item.get("kitchen_station", StationCategory.HOT_WOK.value)
            try:
                station = StationCategory(station_str)
            except ValueError:
                station = StationCategory.HOT_WOK
            station_items[station].append(item)

        tickets = []
        for station, group_items in station_items.items():
            ticket = KitchenTicket(
                order_id=order_id,
                order_number=order_number,
                table_code=table_code,
                station=station,
                items=group_items,
                priority=priority,
                scene=scene,
            )

            # 分配设备
            device = self._find_best_device(station)
            if device:
                ticket.assigned_device_id = device.device_id
                device.current_load += 1

            # 存储
            self._tickets[ticket.ticket_id] = ticket
            self._station_queues[station].append(ticket.ticket_id)
            self._order_tickets[order_id].append(ticket.ticket_id)

            # 标记为已接单
            ticket.status = TicketStatus.RECEIVED
            ticket.received_at = datetime.utcnow()

            tickets.append(ticket.to_dict())

        logger.info(
            "厨打分单完成",
            order_id=order_id,
            stations=[t["station"] for t in tickets],
            ticket_count=len(tickets),
        )
        return tickets

    def _find_best_device(self, station: StationCategory) -> Optional[KDSDevice]:
        """找到该工位负载最低的在线设备"""
        candidates = [
            d for d in self._devices.values()
            if d.station == station and d.is_online
        ]
        if not candidates:
            # 降级到 expeditor 设备
            candidates = [
                d for d in self._devices.values()
                if d.device_type == KDSDeviceType.EXPEDITOR and d.is_online
            ]
        if not candidates:
            return None
        return min(candidates, key=lambda d: d.current_load)

    # ── 状态流转 ──────────────────────────────────────────────────────────────

    def update_ticket_status(
        self,
        ticket_id: str,
        new_status: TicketStatus,
        operator_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新厨打票状态"""
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None

        now = datetime.utcnow()
        old_status = ticket.status
        ticket.status = new_status

        if new_status == TicketStatus.COOKING:
            ticket.cooking_at = now
        elif new_status == TicketStatus.READY:
            ticket.ready_at = now
            # 释放设备负载
            if ticket.assigned_device_id:
                device = self._devices.get(ticket.assigned_device_id)
                if device:
                    device.current_load = max(0, device.current_load - 1)
        elif new_status == TicketStatus.SERVED:
            ticket.served_at = now

        logger.info(
            "厨打票状态变更",
            ticket_id=ticket_id,
            old_status=old_status.value,
            new_status=new_status.value,
            order_id=ticket.order_id,
        )
        return ticket.to_dict()

    def rush_order(self, order_id: str) -> List[Dict[str, Any]]:
        """催菜（提升该订单所有厨打票的优先级）"""
        ticket_ids = self._order_tickets.get(order_id, [])
        updated = []
        for tid in ticket_ids:
            ticket = self._tickets.get(tid)
            if ticket and ticket.status in (
                TicketStatus.QUEUED, TicketStatus.RECEIVED, TicketStatus.COOKING
            ):
                ticket.priority = max(ticket.priority + 1, 2)
                updated.append(ticket.to_dict())

        logger.info("催菜", order_id=order_id, rushed_count=len(updated))
        return updated

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_station_queue(self, station: StationCategory) -> List[Dict[str, Any]]:
        """获取工位队列（按优先级排序）"""
        ticket_ids = self._station_queues.get(station, [])
        tickets = [
            self._tickets[tid] for tid in ticket_ids
            if tid in self._tickets
            and self._tickets[tid].status not in (
                TicketStatus.SERVED, TicketStatus.CANCELLED, TicketStatus.RETURNED
            )
        ]
        # 按优先级降序 + 创建时间升序
        tickets.sort(key=lambda t: (-t.priority, t.created_at))
        return [t.to_dict() for t in tickets]

    def get_order_kitchen_status(self, order_id: str) -> Dict[str, Any]:
        """获取订单的厨房出餐进度"""
        ticket_ids = self._order_tickets.get(order_id, [])
        tickets = [self._tickets[tid] for tid in ticket_ids if tid in self._tickets]

        total = len(tickets)
        ready = sum(1 for t in tickets if t.status in (TicketStatus.READY, TicketStatus.SERVED))
        cooking = sum(1 for t in tickets if t.status == TicketStatus.COOKING)
        overdue = sum(1 for t in tickets if t.is_overdue and t.status not in (
            TicketStatus.READY, TicketStatus.SERVED, TicketStatus.CANCELLED
        ))

        return {
            "order_id": order_id,
            "total_tickets": total,
            "ready_count": ready,
            "cooking_count": cooking,
            "overdue_count": overdue,
            "progress_pct": round(ready / total * 100, 1) if total > 0 else 0,
            "all_ready": ready == total and total > 0,
            "tickets": [t.to_dict() for t in tickets],
        }

    def get_expeditor_view(self) -> Dict[str, Any]:
        """获取催菜员汇总视图（所有工位的当前状态）"""
        station_summary = {}
        for station in StationCategory:
            queue = self.get_station_queue(station)
            if queue:
                station_summary[station.value] = {
                    "queue_length": len(queue),
                    "overdue_count": sum(1 for t in queue if t["is_overdue"]),
                    "avg_wait_seconds": (
                        sum(t["elapsed_seconds"] for t in queue) // len(queue)
                        if queue else 0
                    ),
                    "oldest_ticket": queue[0] if queue else None,
                }

        return {
            "store_id": self.store_id,
            "timestamp": datetime.utcnow().isoformat(),
            "stations": station_summary,
            "total_active_tickets": sum(
                s["queue_length"] for s in station_summary.values()
            ),
            "total_overdue": sum(
                s["overdue_count"] for s in station_summary.values()
            ),
            "devices_online": sum(1 for d in self._devices.values() if d.is_online),
            "devices_total": len(self._devices),
        }

    # ── 打印 ──────────────────────────────────────────────────────────────────

    def generate_print_data(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        生成打印数据（ESC/POS 格式）。

        返回结构化打印指令，由边缘设备（Raspberry Pi）渲染为实际打印命令。
        """
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None

        return {
            "ticket_id": ticket.ticket_id,
            "format": "esc_pos",
            "header": {
                "store_id": self.store_id,
                "order_number": ticket.order_number,
                "table_code": ticket.table_code,
                "station": ticket.station.value,
                "priority": ticket.priority,
                "time": ticket.created_at.strftime("%H:%M"),
            },
            "items": [
                {
                    "name": i.get("dish_name", ""),
                    "qty": i.get("quantity", 1),
                    "spec": i.get("spec_name", ""),
                    "weight": i.get("weight_g"),
                    "method": i.get("cooking_method", ""),
                    "notes": i.get("notes", ""),
                }
                for i in ticket.items
            ],
            "footer": {
                "scene": ticket.scene,
                "total_items": len(ticket.items),
                "rush": "催" if ticket.priority >= 2 else "",
            },
        }
