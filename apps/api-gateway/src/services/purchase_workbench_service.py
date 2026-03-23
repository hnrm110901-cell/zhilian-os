"""
采购工作台服务

Phase 2.2 功能对等模块 — 管理完整采购周期：
创建采购单 → 提交供应商 → 供应商确认 → 收货 → 对账

设计原则：
- 所有金额以分(fen)为单位存储和计算
- 纯函数 + dataclass，不依赖ORM
- 采购单状态机: draft → submitted → confirmed → partially_received
                → received → reconciled → closed
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ============================================================
# 枚举定义
# ============================================================

class POStatus(str, Enum):
    """采购单状态"""
    DRAFT = "draft"                          # 草稿
    SUBMITTED = "submitted"                  # 已提交供应商
    CONFIRMED = "confirmed"                  # 供应商已确认
    PARTIALLY_RECEIVED = "partially_received"  # 部分收货
    RECEIVED = "received"                    # 全部收货
    RECONCILED = "reconciled"                # 已对账
    CLOSED = "closed"                        # 已关闭


class ReconcileIssueType(str, Enum):
    """对账差异类型"""
    QTY_MISMATCH = "qty_mismatch"       # 数量不符
    PRICE_MISMATCH = "price_mismatch"   # 价格不符
    QUALITY_ISSUE = "quality_issue"     # 质量问题


# ============================================================
# 数据结构
# ============================================================

@dataclass
class POItem:
    """采购单明细"""
    item_id: str
    ingredient_id: str
    ingredient_name: str
    unit: str                       # 单位（kg/斤/箱/瓶等）
    ordered_qty: float              # 下单数量
    unit_price_fen: int             # 单价（分）
    ordered_amount_fen: int         # 下单金额（分）= qty × unit_price
    confirmed_qty: float = 0.0     # 供应商确认数量
    received_qty: float = 0.0      # 实收数量
    received_amount_fen: int = 0   # 实收金额（分）


@dataclass
class PurchaseOrder:
    """采购单主体"""
    order_id: str
    store_id: str
    supplier_id: str
    supplier_name: str
    status: POStatus
    items: List[POItem] = field(default_factory=list)
    total_ordered_fen: int = 0     # 下单总金额（分）
    total_confirmed_fen: int = 0   # 确认总金额（分）
    total_received_fen: int = 0    # 实收总金额（分）
    created_at: str = ""
    submitted_at: str = ""
    confirmed_at: str = ""
    received_at: str = ""
    reconciled_at: str = ""
    note: str = ""


@dataclass
class ReceiveItem:
    """收货明细（输入参数）"""
    item_id: str
    received_qty: float
    unit_price_fen: Optional[int] = None  # 实际单价（分），为空则用下单价
    quality_ok: bool = True
    quality_note: str = ""


@dataclass
class ReceiveResult:
    """收货结果"""
    order_id: str
    fully_received: bool            # 是否全部收货完成
    received_items_count: int
    total_received_fen: int
    variance_items: List[Dict] = field(default_factory=list)  # 数量差异明细
    message: str = ""


@dataclass
class ReconcileIssue:
    """对账差异项"""
    item_id: str
    ingredient_name: str
    issue_type: ReconcileIssueType
    expected_value: str
    actual_value: str
    variance_fen: int = 0          # 金额差异（分）


@dataclass
class ReconcileResult:
    """对账结果"""
    order_id: str
    is_clean: bool                  # 无差异
    total_ordered_fen: int
    total_received_fen: int
    variance_fen: int               # 总金额差异（分）
    issues: List[ReconcileIssue] = field(default_factory=list)


@dataclass
class SuggestedOrderItem:
    """AI建议采购项"""
    ingredient_id: str
    ingredient_name: str
    current_stock: float
    suggested_qty: float
    unit: str
    estimated_unit_price_fen: int
    estimated_amount_fen: int
    reason: str                     # 建议原因（如：库存低于安全线、预测需求增长）


@dataclass
class SuggestedOrder:
    """AI建议采购单"""
    supplier_id: str
    supplier_name: str
    items: List[SuggestedOrderItem] = field(default_factory=list)
    total_estimated_fen: int = 0
    confidence: float = 0.0         # 置信度 0~1
    reasoning: str = ""             # AI 推理说明


@dataclass
class SupplierPerformance:
    """供应商绩效"""
    supplier_id: str
    supplier_name: str
    total_orders: int = 0
    on_time_rate: float = 0.0       # 准时交货率 0~1
    quality_pass_rate: float = 0.0  # 质量合格率 0~1
    avg_price_variance_rate: float = 0.0  # 平均价格偏差率
    total_amount_fen: int = 0       # 累计采购金额（分）


# ============================================================
# 服务层
# ============================================================

class PurchaseWorkbenchService:
    """
    采购工作台服务

    管理完整采购生命周期：创建 → 提交 → 确认 → 收货 → 对账。
    POC阶段使用内存存储，后续迁移到数据库。
    """

    def __init__(self):
        # 内存存储：order_id -> PurchaseOrder
        self._orders: Dict[str, PurchaseOrder] = {}

    def create_purchase_order(
        self,
        store_id: str,
        supplier_id: str,
        supplier_name: str,
        items: List[Dict],
        note: str = "",
    ) -> PurchaseOrder:
        """
        创建采购单

        items 格式: [
            {"ingredient_id": "...", "ingredient_name": "...",
             "ordered_qty": 10.0, "unit": "kg", "unit_price_fen": 1500}
        ]
        """
        order_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        po_items = []
        total_fen = 0
        for item_data in items:
            item_id = str(uuid.uuid4())
            qty = item_data["ordered_qty"]
            price = item_data["unit_price_fen"]
            # 金额 = 数量 × 单价（四舍五入到分）
            amount_fen = round(qty * price)
            total_fen += amount_fen

            po_items.append(POItem(
                item_id=item_id,
                ingredient_id=item_data["ingredient_id"],
                ingredient_name=item_data["ingredient_name"],
                unit=item_data.get("unit", "kg"),
                ordered_qty=qty,
                unit_price_fen=price,
                ordered_amount_fen=amount_fen,
            ))

        order = PurchaseOrder(
            order_id=order_id,
            store_id=store_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            status=POStatus.DRAFT,
            items=po_items,
            total_ordered_fen=total_fen,
            created_at=now,
            note=note,
        )
        self._orders[order_id] = order

        logger.info(
            "purchase.order_created",
            order_id=order_id,
            store_id=store_id,
            supplier_id=supplier_id,
            item_count=len(po_items),
            total_ordered_fen=total_fen,
        )
        return order

    def submit_order(self, order_id: str) -> PurchaseOrder:
        """
        提交采购单给供应商

        只有草稿状态的采购单可以提交。
        """
        order = self._get_order(order_id)
        self._assert_status(order, [POStatus.DRAFT], "提交")

        if not order.items:
            raise ValueError("空采购单不能提交")

        order.status = POStatus.SUBMITTED
        order.submitted_at = datetime.utcnow().isoformat()

        logger.info("purchase.order_submitted", order_id=order_id)
        return order

    def supplier_confirm(
        self,
        order_id: str,
        confirmed_items: List[Dict],
    ) -> PurchaseOrder:
        """
        供应商确认采购单

        confirmed_items 格式: [{"item_id": "...", "confirmed_qty": 8.0}]
        供应商可能确认的数量少于下单数量（缺货等）。
        """
        order = self._get_order(order_id)
        self._assert_status(order, [POStatus.SUBMITTED], "供应商确认")

        # 建立 item_id -> confirmed_qty 映射
        confirm_map = {c["item_id"]: c["confirmed_qty"] for c in confirmed_items}

        total_confirmed_fen = 0
        for item in order.items:
            if item.item_id in confirm_map:
                item.confirmed_qty = confirm_map[item.item_id]
            else:
                # 未在确认列表中的项，默认确认全部
                item.confirmed_qty = item.ordered_qty
            total_confirmed_fen += round(item.confirmed_qty * item.unit_price_fen)

        order.total_confirmed_fen = total_confirmed_fen
        order.status = POStatus.CONFIRMED
        order.confirmed_at = datetime.utcnow().isoformat()

        logger.info(
            "purchase.order_confirmed",
            order_id=order_id,
            total_confirmed_fen=total_confirmed_fen,
        )
        return order

    def receive_goods(
        self,
        order_id: str,
        received_items: List[ReceiveItem],
    ) -> ReceiveResult:
        """
        收货

        支持分批收货：
        - 所有确认项都已收货 → 状态变为 received
        - 部分收货 → 状态变为 partially_received

        收货时可以修改实际单价（如供应商临时调价）。
        """
        order = self._get_order(order_id)
        self._assert_status(
            order,
            [POStatus.CONFIRMED, POStatus.PARTIALLY_RECEIVED],
            "收货",
        )

        # 建立收货映射
        receive_map = {r.item_id: r for r in received_items}
        variance_items = []

        for item in order.items:
            if item.item_id not in receive_map:
                continue

            recv = receive_map[item.item_id]
            item.received_qty += recv.received_qty

            # 如果供应商给了新单价，更新
            actual_price = recv.unit_price_fen if recv.unit_price_fen else item.unit_price_fen
            item.received_amount_fen += round(recv.received_qty * actual_price)

            # 检查数量差异
            if item.received_qty != item.confirmed_qty:
                variance_items.append({
                    "item_id": item.item_id,
                    "ingredient_name": item.ingredient_name,
                    "confirmed_qty": item.confirmed_qty,
                    "received_qty": item.received_qty,
                    "variance": item.received_qty - item.confirmed_qty,
                })

        # 计算实收总金额
        order.total_received_fen = sum(i.received_amount_fen for i in order.items)

        # 判断是否全部收货完成
        fully_received = all(
            i.received_qty >= i.confirmed_qty
            for i in order.items
            if i.confirmed_qty > 0
        )

        if fully_received:
            order.status = POStatus.RECEIVED
            order.received_at = datetime.utcnow().isoformat()
        else:
            order.status = POStatus.PARTIALLY_RECEIVED

        result = ReceiveResult(
            order_id=order_id,
            fully_received=fully_received,
            received_items_count=len(received_items),
            total_received_fen=order.total_received_fen,
            variance_items=variance_items,
            message="全部收货完成" if fully_received else "部分收货",
        )

        logger.info(
            "purchase.goods_received",
            order_id=order_id,
            fully_received=fully_received,
            received_items_count=len(received_items),
            total_received_fen=order.total_received_fen,
        )
        return result

    def reconcile_order(self, order_id: str) -> ReconcileResult:
        """
        对账

        比较下单数量/价格 vs 实收数量/价格，列出所有差异项。
        """
        order = self._get_order(order_id)
        self._assert_status(order, [POStatus.RECEIVED], "对账")

        issues: List[ReconcileIssue] = []

        for item in order.items:
            # 检查数量差异
            if abs(item.received_qty - item.ordered_qty) > 0.001:
                issues.append(ReconcileIssue(
                    item_id=item.item_id,
                    ingredient_name=item.ingredient_name,
                    issue_type=ReconcileIssueType.QTY_MISMATCH,
                    expected_value=f"{item.ordered_qty} {item.unit}",
                    actual_value=f"{item.received_qty} {item.unit}",
                    variance_fen=item.received_amount_fen - item.ordered_amount_fen,
                ))

            # 检查金额差异（即使数量一致，单价可能变了）
            elif abs(item.received_amount_fen - item.ordered_amount_fen) > 0:
                issues.append(ReconcileIssue(
                    item_id=item.item_id,
                    ingredient_name=item.ingredient_name,
                    issue_type=ReconcileIssueType.PRICE_MISMATCH,
                    expected_value=f"{item.ordered_amount_fen}分",
                    actual_value=f"{item.received_amount_fen}分",
                    variance_fen=item.received_amount_fen - item.ordered_amount_fen,
                ))

        variance_fen = order.total_received_fen - order.total_ordered_fen
        is_clean = len(issues) == 0

        order.status = POStatus.RECONCILED
        order.reconciled_at = datetime.utcnow().isoformat()

        result = ReconcileResult(
            order_id=order_id,
            is_clean=is_clean,
            total_ordered_fen=order.total_ordered_fen,
            total_received_fen=order.total_received_fen,
            variance_fen=variance_fen,
            issues=issues,
        )

        logger.info(
            "purchase.order_reconciled",
            order_id=order_id,
            is_clean=is_clean,
            variance_fen=variance_fen,
            issue_count=len(issues),
        )
        return result

    def get_suggested_orders(self, store_id: str) -> List[SuggestedOrder]:
        """
        AI 智能采购建议

        基于库存水平和消耗预测，生成建议采购单。
        POC阶段返回模拟数据，后续接入 InventoryAgent 预测结果。
        """
        # POC阶段：返回空列表，后续接入AI预测
        logger.info("purchase.suggestions_requested", store_id=store_id)
        return []

    def get_supplier_performance(self, supplier_id: str) -> SupplierPerformance:
        """
        供应商绩效统计

        统计该供应商的历史采购数据：准时率、质量合格率、价格偏差等。
        POC阶段从内存订单中统计。
        """
        supplier_orders = [
            o for o in self._orders.values()
            if o.supplier_id == supplier_id
        ]

        total_orders = len(supplier_orders)
        total_amount_fen = sum(o.total_received_fen for o in supplier_orders)
        supplier_name = supplier_orders[0].supplier_name if supplier_orders else ""

        # POC阶段简化：有收货完成的订单视为准时
        completed = [o for o in supplier_orders if o.status in (
            POStatus.RECEIVED, POStatus.RECONCILED, POStatus.CLOSED
        )]
        on_time_rate = len(completed) / total_orders if total_orders > 0 else 0.0

        return SupplierPerformance(
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            total_orders=total_orders,
            on_time_rate=round(on_time_rate, 2),
            quality_pass_rate=1.0,  # POC阶段默认100%
            avg_price_variance_rate=0.0,
            total_amount_fen=total_amount_fen,
        )

    def get_orders(self, store_id: str) -> List[PurchaseOrder]:
        """获取门店所有采购单，按创建时间倒序"""
        orders = [
            o for o in self._orders.values()
            if o.store_id == store_id
        ]
        orders.sort(key=lambda o: o.created_at, reverse=True)
        return orders

    # ============================================================
    # 内部方法
    # ============================================================

    def _get_order(self, order_id: str) -> PurchaseOrder:
        """获取采购单，不存在则抛异常"""
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"采购单不存在: order_id={order_id}")
        return order

    def _assert_status(
        self,
        order: PurchaseOrder,
        allowed: List[POStatus],
        action: str,
    ) -> None:
        """校验采购单状态是否允许执行指定操作"""
        if order.status not in allowed:
            allowed_str = ", ".join(s.value for s in allowed)
            raise ValueError(
                f"当前状态 [{order.status.value}] 不允许执行 [{action}]，"
                f"需要状态: [{allowed_str}]"
            )


# 模块级单例
purchase_workbench_service = PurchaseWorkbenchService()
