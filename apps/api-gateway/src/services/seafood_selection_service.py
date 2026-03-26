"""
顾客海鲜自选流程服务（Seafood Selection Flow）

核心功能：
- 完整的 看鱼→选鱼→称重→选做法→下单 闭环
- 基于 session 的状态管理（内存存储）
- 支持多条海鲜选择、称重、做法组合

金额单位：分（fen），API 返回时 /100 转元
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class SelectionStatus(str, Enum):
    """选鱼流程状态"""
    BROWSING = "browsing"        # 浏览中
    SELECTING = "selecting"      # 选择中
    WEIGHING = "weighing"        # 称重中
    COOKING_CHOICE = "cooking_choice"  # 选做法中
    CONFIRMED = "confirmed"      # 已确认下单
    CANCELLED = "cancelled"      # 已取消


class CookingMethod(str, Enum):
    """烹饪做法"""
    STEAM = "清蒸"
    BOIL = "白灼"
    STIR_FRY = "爆炒"
    DEEP_FRY = "油炸"
    BRAISED = "红烧"
    GRILLED = "烧烤"
    SASHIMI = "刺身"
    SPICY = "香辣"
    GARLIC = "蒜蓉"
    SALT_PEPPER = "椒盐"
    CONGEE = "粥底"
    SOUP = "煲汤"


# ── 品种推荐做法映射 ──────────────────────────────────────────────────────
SPECIES_COOKING_MAP: Dict[str, List[str]] = {
    "波士顿龙虾": ["清蒸", "蒜蓉", "芝士焗"],
    "澳洲龙虾": ["刺身", "清蒸", "蒜蓉"],
    "帝王蟹": ["清蒸", "白灼", "煲粥"],
    "石斑鱼": ["清蒸", "红烧", "煲汤"],
    "东星斑": ["清蒸", "刺身"],
    "多宝鱼": ["清蒸", "红烧"],
    "鲈鱼": ["清蒸", "红烧", "煲汤"],
    "基围虾": ["白灼", "椒盐", "蒜蓉"],
    "皮皮虾": ["清蒸", "椒盐", "香辣"],
    "鲍鱼": ["清蒸", "蒜蓉", "红烧"],
    "生蚝": ["蒜蓉", "烧烤", "刺身"],
    "花甲": ["爆炒", "煲汤", "蒜蓉"],
    "扇贝": ["蒜蓉", "清蒸"],
}


@dataclass
class TankInfo:
    """鱼缸信息"""
    tank_id: str
    species: str
    available_qty: int
    unit_price_fen: int  # 单价（分/斤）
    unit_price_yuan: float
    cooking_methods: List[str]
    status: str  # 正常/补货中/暂停


@dataclass
class SelectionItem:
    """单个选择项"""
    item_id: str
    tank_id: str
    species: str
    quantity: int  # 条/只
    weight_g: Optional[int] = None  # 称重（克）
    scale_id: Optional[str] = None
    cooking_method: Optional[str] = None
    unit_price_fen: int = 0
    total_price_fen: int = 0
    total_price_yuan: float = 0.0
    status: str = "selected"  # selected/weighed/method_chosen


@dataclass
class SelectionSession:
    """选鱼会话"""
    session_id: str
    table_code: str
    customer_id: Optional[str]
    status: SelectionStatus
    items: List[SelectionItem] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    total_price_fen: int = 0
    total_price_yuan: float = 0.0


@dataclass
class OrderItemOutput:
    """确认后的订单项"""
    item_id: str
    species: str
    quantity: int
    weight_g: int
    cooking_method: str
    price_fen: int
    price_yuan: float


class SeafoodSelectionFlow:
    """
    顾客海鲜自选流程

    管理从看鱼到下单的完整闭环，内存存储会话状态。
    """

    def __init__(self) -> None:
        self._logger = logger.bind(service="seafood_selection_flow")
        # 内存存储：session_id → SelectionSession
        self._sessions: Dict[str, SelectionSession] = {}
        # 模拟鱼缸数据
        self._tanks: Dict[str, TankInfo] = {}

    def register_tank(self, tank: TankInfo) -> None:
        """注册/更新鱼缸信息（供外部初始化数据用）"""
        self._tanks[tank.tank_id] = tank

    # ── 流程方法 ──────────────────────────────────────────────────────────

    def start_selection(
        self,
        table_code: str,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        开始选鱼流程，返回 session_id

        Args:
            table_code: 桌号
            customer_id: 顾客ID（可选，会员可关联）
        """
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        session = SelectionSession(
            session_id=session_id,
            table_code=table_code,
            customer_id=customer_id,
            status=SelectionStatus.BROWSING,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session_id] = session

        self._logger.info("选鱼流程开始", session_id=session_id, table=table_code)

        return {
            "session_id": session_id,
            "table_code": table_code,
            "status": SelectionStatus.BROWSING.value,
            "message": f"桌号 {table_code} 选鱼流程已开始",
        }

    def browse_tanks(self, session_id: str) -> Dict[str, Any]:
        """
        展示可选鱼缸和品种列表

        Args:
            session_id: 会话ID
        """
        session = self._get_session(session_id)
        if session is None:
            return {"error": "会话不存在或已过期", "session_id": session_id}

        if session.status == SelectionStatus.CANCELLED:
            return {"error": "该选鱼流程已取消", "session_id": session_id}

        if session.status == SelectionStatus.CONFIRMED:
            return {"error": "该选鱼流程已确认下单", "session_id": session_id}

        available_tanks = [
            {
                "tank_id": t.tank_id,
                "species": t.species,
                "available_qty": t.available_qty,
                "unit_price_fen": t.unit_price_fen,
                "unit_price_yuan": t.unit_price_yuan,
                "cooking_methods": t.cooking_methods,
                "status": t.status,
            }
            for t in self._tanks.values()
            if t.status == "正常" and t.available_qty > 0
        ]

        return {
            "session_id": session_id,
            "tanks": available_tanks,
            "total_available": len(available_tanks),
        }

    def select_item(
        self,
        session_id: str,
        tank_id: str,
        species: str,
        quantity: int,
    ) -> Dict[str, Any]:
        """
        选择海鲜

        Args:
            session_id: 会话ID
            tank_id: 鱼缸ID
            species: 品种
            quantity: 数量（条/只）
        """
        session = self._get_session(session_id)
        if session is None:
            return {"error": "会话不存在", "session_id": session_id}

        if session.status in (SelectionStatus.CONFIRMED, SelectionStatus.CANCELLED):
            return {"error": f"流程已{session.status.value}，无法继续选择"}

        # 检查鱼缸
        tank = self._tanks.get(tank_id)
        if tank is None:
            return {"error": f"鱼缸 {tank_id} 不存在"}

        if tank.available_qty < quantity:
            return {
                "error": f"{species} 库存不足，当前可选 {tank.available_qty} 条/只",
            }

        if quantity <= 0:
            return {"error": "数量必须大于0"}

        item_id = str(uuid.uuid4())[:8]
        item = SelectionItem(
            item_id=item_id,
            tank_id=tank_id,
            species=species,
            quantity=quantity,
            unit_price_fen=tank.unit_price_fen,
        )
        session.items.append(item)
        session.status = SelectionStatus.SELECTING
        session.updated_at = datetime.now().isoformat()

        # 预扣库存
        tank.available_qty -= quantity

        self._logger.info(
            "海鲜已选择",
            session_id=session_id,
            species=species,
            quantity=quantity,
            item_id=item_id,
        )

        return {
            "session_id": session_id,
            "item_id": item_id,
            "species": species,
            "quantity": quantity,
            "message": f"已选择 {species} {quantity} 条/只，请前往称重",
            "next_step": "weigh_item",
        }

    def weigh_item(
        self,
        session_id: str,
        item_id: str,
        weight_g: int,
        scale_id: str,
    ) -> Dict[str, Any]:
        """
        称重确认

        Args:
            session_id: 会话ID
            item_id: 选择项ID
            weight_g: 重量（克）
            scale_id: 电子秤ID
        """
        session = self._get_session(session_id)
        if session is None:
            return {"error": "会话不存在"}

        item = self._find_item(session, item_id)
        if item is None:
            return {"error": f"选择项 {item_id} 不存在"}

        if weight_g <= 0:
            return {"error": "重量必须大于0"}

        item.weight_g = weight_g
        item.scale_id = scale_id

        # 计算价格（按斤计价：1斤=500g）
        weight_jin = weight_g / 500.0
        item.total_price_fen = round(item.unit_price_fen * weight_jin)
        item.total_price_yuan = round(item.total_price_fen / 100, 2)
        item.status = "weighed"

        session.status = SelectionStatus.WEIGHING
        session.updated_at = datetime.now().isoformat()
        self._recalculate_total(session)

        self._logger.info(
            "称重完成",
            item_id=item_id,
            weight_g=weight_g,
            price_yuan=item.total_price_yuan,
        )

        # 推荐做法
        recommended = SPECIES_COOKING_MAP.get(item.species, ["清蒸", "红烧"])

        return {
            "session_id": session_id,
            "item_id": item_id,
            "species": item.species,
            "weight_g": weight_g,
            "weight_display": f"{weight_g}克（约{weight_jin:.1f}斤）",
            "total_price_fen": item.total_price_fen,
            "total_price_yuan": item.total_price_yuan,
            "recommended_cooking": recommended,
            "next_step": "choose_cooking_method",
        }

    def choose_cooking_method(
        self,
        session_id: str,
        item_id: str,
        method: str,
    ) -> Dict[str, Any]:
        """
        选择烹饪做法

        Args:
            session_id: 会话ID
            item_id: 选择项ID
            method: 做法名称
        """
        session = self._get_session(session_id)
        if session is None:
            return {"error": "会话不存在"}

        item = self._find_item(session, item_id)
        if item is None:
            return {"error": f"选择项 {item_id} 不存在"}

        if item.weight_g is None:
            return {"error": "请先完成称重再选做法"}

        item.cooking_method = method
        item.status = "method_chosen"
        session.status = SelectionStatus.COOKING_CHOICE
        session.updated_at = datetime.now().isoformat()

        self._logger.info(
            "做法已选择", item_id=item_id, method=method,
        )

        return {
            "session_id": session_id,
            "item_id": item_id,
            "species": item.species,
            "cooking_method": method,
            "message": f"{item.species} 选择做法【{method}】",
            "next_step": "confirm_selection 或继续 select_item",
        }

    def confirm_selection(self, session_id: str) -> Dict[str, Any]:
        """
        确认下单，生成订单项列表

        Args:
            session_id: 会话ID
        """
        session = self._get_session(session_id)
        if session is None:
            return {"error": "会话不存在"}

        if not session.items:
            return {"error": "未选择任何海鲜"}

        # 检查所有项是否完成称重和做法选择
        incomplete = []
        for item in session.items:
            if item.weight_g is None:
                incomplete.append(f"{item.species}（未称重）")
            elif item.cooking_method is None:
                incomplete.append(f"{item.species}（未选做法）")

        if incomplete:
            return {
                "error": "以下选项未完成",
                "incomplete_items": incomplete,
                "message": "请完成所有称重和做法选择后再确认",
            }

        # 生成订单项
        order_items: List[Dict[str, Any]] = []
        for item in session.items:
            order_items.append({
                "item_id": item.item_id,
                "species": item.species,
                "quantity": item.quantity,
                "weight_g": item.weight_g,
                "cooking_method": item.cooking_method,
                "price_fen": item.total_price_fen,
                "price_yuan": item.total_price_yuan,
            })

        session.status = SelectionStatus.CONFIRMED
        session.updated_at = datetime.now().isoformat()
        self._recalculate_total(session)

        self._logger.info(
            "选鱼确认下单",
            session_id=session_id,
            items_count=len(order_items),
            total_yuan=session.total_price_yuan,
        )

        return {
            "session_id": session_id,
            "status": "confirmed",
            "table_code": session.table_code,
            "order_items": order_items,
            "total_price_fen": session.total_price_fen,
            "total_price_yuan": session.total_price_yuan,
            "items_count": len(order_items),
            "message": f"已确认下单，共 {len(order_items)} 项，合计 ¥{session.total_price_yuan}",
        }

    def cancel_selection(self, session_id: str) -> Dict[str, Any]:
        """
        取消选鱼流程

        Args:
            session_id: 会话ID
        """
        session = self._get_session(session_id)
        if session is None:
            return {"error": "会话不存在"}

        if session.status == SelectionStatus.CONFIRMED:
            return {"error": "已确认下单，无法取消，请走退单流程"}

        # 恢复库存
        for item in session.items:
            tank = self._tanks.get(item.tank_id)
            if tank:
                tank.available_qty += item.quantity

        session.status = SelectionStatus.CANCELLED
        session.updated_at = datetime.now().isoformat()

        self._logger.info("选鱼流程已取消", session_id=session_id)

        return {
            "session_id": session_id,
            "status": "cancelled",
            "message": "选鱼流程已取消，库存已恢复",
        }

    def get_selection_status(self, session_id: str) -> Dict[str, Any]:
        """
        获取当前选择状态

        Args:
            session_id: 会话ID
        """
        session = self._get_session(session_id)
        if session is None:
            return {"error": "会话不存在", "session_id": session_id}

        items_detail = []
        for item in session.items:
            items_detail.append({
                "item_id": item.item_id,
                "species": item.species,
                "quantity": item.quantity,
                "weight_g": item.weight_g,
                "cooking_method": item.cooking_method,
                "price_fen": item.total_price_fen,
                "price_yuan": item.total_price_yuan,
                "item_status": item.status,
            })

        return {
            "session_id": session_id,
            "table_code": session.table_code,
            "customer_id": session.customer_id,
            "status": session.status.value,
            "items": items_detail,
            "items_count": len(session.items),
            "total_price_fen": session.total_price_fen,
            "total_price_yuan": session.total_price_yuan,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _get_session(self, session_id: str) -> Optional[SelectionSession]:
        return self._sessions.get(session_id)

    def _find_item(
        self, session: SelectionSession, item_id: str
    ) -> Optional[SelectionItem]:
        for item in session.items:
            if item.item_id == item_id:
                return item
        return None

    def _recalculate_total(self, session: SelectionSession) -> None:
        """重新计算会话总价"""
        session.total_price_fen = sum(i.total_price_fen for i in session.items)
        session.total_price_yuan = round(session.total_price_fen / 100, 2)
