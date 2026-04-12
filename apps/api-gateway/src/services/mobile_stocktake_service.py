"""
移动盘点服务

Phase 2.2 功能对等模块 — 面向手机/平板的库存盘点服务。
支持全盘、分类盘、抽盘三种模式。

设计原则：
- 所有金额以分(fen)为单位存储和计算
- 纯函数 + dataclass，不依赖ORM
- 盘点状态机: in_progress → pending_review → approved / rejected
- 差异率 > 5% 的品项自动标记为"需调查"
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

class StocktakeStatus(str, Enum):
    """盘点状态"""
    IN_PROGRESS = "in_progress"      # 盘点进行中
    PENDING_REVIEW = "pending_review"  # 待审核
    APPROVED = "approved"            # 已审核通过（库存已调整）
    REJECTED = "rejected"            # 已驳回


class StocktakeScope(str, Enum):
    """盘点范围"""
    FULL = "full"                    # 全盘：所有品项
    PARTIAL = "partial"              # 分类盘：按类别
    SPOT_CHECK = "spot_check"        # 抽盘：随机 20%


# ============================================================
# 数据结构
# ============================================================

# 差异率超过此阈值的品项自动标记为需调查
VARIANCE_THRESHOLD = 0.05  # 5%


@dataclass
class CountRecord:
    """单次盘点记录"""
    record_id: str
    stocktake_id: str
    ingredient_id: str
    ingredient_name: str
    system_qty: float               # 系统库存数量
    counted_qty: float              # 实盘数量
    unit: str                       # 单位
    variance: float                 # 差异 = counted - system
    variance_rate: float            # 差异率 = variance / system（system为0时标记为1.0）
    unit_cost_fen: int              # 单位成本（分）
    variance_fen: int               # 差异金额（分）= variance × unit_cost
    location: str = ""              # 存放位置（如：冷库A、干货区）
    note: str = ""                  # 备注
    needs_investigation: bool = False  # 是否需要调查
    counted_at: str = ""


@dataclass
class Stocktake:
    """盘点会话主体"""
    stocktake_id: str
    store_id: str
    scope: StocktakeScope
    status: StocktakeStatus
    category: str = ""              # scope=partial时的类别名
    records: List[CountRecord] = field(default_factory=list)
    created_by: str = ""            # 创建人
    created_at: str = ""
    submitted_at: str = ""          # 提交审核时间
    approved_by: str = ""           # 审核人
    approved_at: str = ""
    rejected_reason: str = ""


@dataclass
class BatchResult:
    """批量盘点结果"""
    stocktake_id: str
    success_count: int
    failed_count: int
    failures: List[Dict] = field(default_factory=list)


@dataclass
class VarianceItem:
    """差异明细"""
    ingredient_id: str
    ingredient_name: str
    system_qty: float
    counted_qty: float
    unit: str
    variance: float
    variance_rate: float
    variance_fen: int               # 差异金额（分）
    needs_investigation: bool


@dataclass
class VarianceReport:
    """差异报告（详细版）"""
    stocktake_id: str
    store_id: str
    total_items: int                # 总盘点品项数
    matched_items: int              # 一致品项数
    variance_items: int             # 有差异品项数
    investigation_items: int        # 需调查品项数
    items: List[VarianceItem] = field(default_factory=list)
    total_variance_fen: int = 0     # 总差异金额（分）


@dataclass
class VarianceSummary:
    """差异摘要（含¥金额影响）"""
    stocktake_id: str
    store_id: str
    total_items: int
    variance_items: int
    investigation_items: int
    total_variance_fen: int         # 总差异金额（分）
    total_variance_yuan: str        # 总差异金额（元，展示用）
    positive_variance_fen: int      # 盘盈金额（分）
    negative_variance_fen: int      # 盘亏金额（分）
    top_losses: List[Dict] = field(default_factory=list)  # 亏损TOP5


# ============================================================
# 服务层
# ============================================================

class MobileStocktakeService:
    """
    移动盘点服务

    为手机/平板端提供盘点操作支持，包括：
    - 创建盘点会话（全盘/分类盘/抽盘）
    - 逐项或批量录入实盘数量
    - 自动计算差异并标记异常
    - 审批后自动调整系统库存

    POC阶段使用内存存储，后续迁移到数据库。
    """

    def __init__(self):
        # 内存存储：stocktake_id -> Stocktake
        self._stocktakes: Dict[str, Stocktake] = {}

    def create_stocktake(
        self,
        store_id: str,
        scope: StocktakeScope,
        created_by: str = "",
        category: str = "",
    ) -> Stocktake:
        """
        创建盘点会话

        scope 说明：
        - full: 全盘，盘点所有食材
        - partial: 分类盘，只盘点指定类别（需传 category）
        - spot_check: 抽盘，系统随机选取约20%品项
        """
        stocktake_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        if scope == StocktakeScope.PARTIAL and not category:
            raise ValueError("分类盘点必须指定 category（食材类别）")

        stocktake = Stocktake(
            stocktake_id=stocktake_id,
            store_id=store_id,
            scope=scope,
            status=StocktakeStatus.IN_PROGRESS,
            category=category,
            created_by=created_by,
            created_at=now,
        )
        self._stocktakes[stocktake_id] = stocktake

        logger.info(
            "stocktake.session_created",
            stocktake_id=stocktake_id,
            store_id=store_id,
            scope=scope.value,
            category=category,
        )
        return stocktake

    def add_count(
        self,
        stocktake_id: str,
        ingredient_id: str,
        ingredient_name: str,
        system_qty: float,
        counted_qty: float,
        unit: str,
        unit_cost_fen: int,
        location: str = "",
        note: str = "",
    ) -> CountRecord:
        """
        录入单个品项盘点结果

        自动计算差异，差异率超过5%自动标记"需调查"。
        """
        stocktake = self._get_active_stocktake(stocktake_id)

        # 检查是否已录入过该品项（防止重复）
        for r in stocktake.records:
            if r.ingredient_id == ingredient_id:
                raise ValueError(
                    f"品项已录入: ingredient_id={ingredient_id}, "
                    f"如需修改请先删除再重新录入"
                )

        record = self._create_count_record(
            stocktake_id=stocktake_id,
            ingredient_id=ingredient_id,
            ingredient_name=ingredient_name,
            system_qty=system_qty,
            counted_qty=counted_qty,
            unit=unit,
            unit_cost_fen=unit_cost_fen,
            location=location,
            note=note,
        )
        stocktake.records.append(record)

        logger.info(
            "stocktake.count_added",
            stocktake_id=stocktake_id,
            ingredient_id=ingredient_id,
            system_qty=system_qty,
            counted_qty=counted_qty,
            variance=record.variance,
            needs_investigation=record.needs_investigation,
        )
        return record

    def batch_count(
        self,
        stocktake_id: str,
        counts: List[Dict],
    ) -> BatchResult:
        """
        批量录入盘点结果

        counts 格式: [
            {"ingredient_id": "...", "ingredient_name": "...",
             "system_qty": 10.0, "counted_qty": 9.5, "unit": "kg",
             "unit_cost_fen": 1500, "location": "冷库A", "note": ""}
        ]

        部分失败不影响其他品项录入。
        """
        stocktake = self._get_active_stocktake(stocktake_id)

        success_count = 0
        failed_count = 0
        failures = []

        for count_data in counts:
            try:
                # 检查重复
                ingredient_id = count_data["ingredient_id"]
                already_exists = any(
                    r.ingredient_id == ingredient_id for r in stocktake.records
                )
                if already_exists:
                    raise ValueError(f"品项已录入: {ingredient_id}")

                record = self._create_count_record(
                    stocktake_id=stocktake_id,
                    ingredient_id=ingredient_id,
                    ingredient_name=count_data["ingredient_name"],
                    system_qty=count_data["system_qty"],
                    counted_qty=count_data["counted_qty"],
                    unit=count_data.get("unit", "kg"),
                    unit_cost_fen=count_data.get("unit_cost_fen", 0),
                    location=count_data.get("location", ""),
                    note=count_data.get("note", ""),
                )
                stocktake.records.append(record)
                success_count += 1
            except Exception as e:
                failed_count += 1
                failures.append({
                    "ingredient_id": count_data.get("ingredient_id", "unknown"),
                    "error": str(e),
                })

        logger.info(
            "stocktake.batch_count",
            stocktake_id=stocktake_id,
            success_count=success_count,
            failed_count=failed_count,
        )
        return BatchResult(
            stocktake_id=stocktake_id,
            success_count=success_count,
            failed_count=failed_count,
            failures=failures,
        )

    def calculate_variance(self, stocktake_id: str) -> VarianceReport:
        """
        计算差异报告（详细版）

        返回每个品项的差异详情，含金额影响。
        """
        stocktake = self._get_stocktake(stocktake_id)

        items = []
        total_variance_fen = 0

        for record in stocktake.records:
            items.append(VarianceItem(
                ingredient_id=record.ingredient_id,
                ingredient_name=record.ingredient_name,
                system_qty=record.system_qty,
                counted_qty=record.counted_qty,
                unit=record.unit,
                variance=record.variance,
                variance_rate=record.variance_rate,
                variance_fen=record.variance_fen,
                needs_investigation=record.needs_investigation,
            ))
            total_variance_fen += record.variance_fen

        matched = sum(1 for r in stocktake.records if abs(r.variance) < 0.001)
        investigation = sum(1 for r in stocktake.records if r.needs_investigation)

        return VarianceReport(
            stocktake_id=stocktake_id,
            store_id=stocktake.store_id,
            total_items=len(stocktake.records),
            matched_items=matched,
            variance_items=len(stocktake.records) - matched,
            investigation_items=investigation,
            items=items,
            total_variance_fen=total_variance_fen,
        )

    def get_variance_summary(self, stocktake_id: str) -> VarianceSummary:
        """
        差异摘要（含¥金额影响）

        遵循产品宪法：涉及成本必须包含¥金额字段。
        """
        stocktake = self._get_stocktake(stocktake_id)

        total_variance_fen = 0
        positive_fen = 0   # 盘盈
        negative_fen = 0   # 盘亏

        for record in stocktake.records:
            total_variance_fen += record.variance_fen
            if record.variance_fen > 0:
                positive_fen += record.variance_fen
            elif record.variance_fen < 0:
                negative_fen += record.variance_fen

        matched = sum(1 for r in stocktake.records if abs(r.variance) < 0.001)
        investigation = sum(1 for r in stocktake.records if r.needs_investigation)

        # 亏损 TOP5（按金额绝对值排序）
        loss_records = sorted(
            [r for r in stocktake.records if r.variance_fen < 0],
            key=lambda r: r.variance_fen,
        )[:5]
        top_losses = [
            {
                "ingredient_name": r.ingredient_name,
                "variance": r.variance,
                "unit": r.unit,
                "variance_fen": r.variance_fen,
                "variance_yuan": f"¥{abs(r.variance_fen) / 100:.2f}",
            }
            for r in loss_records
        ]

        # 金额转元（展示用，保留2位小数）
        total_variance_yuan = f"¥{total_variance_fen / 100:.2f}"
        if total_variance_fen >= 0:
            total_variance_yuan = f"+¥{total_variance_fen / 100:.2f}"
        else:
            total_variance_yuan = f"-¥{abs(total_variance_fen) / 100:.2f}"

        return VarianceSummary(
            stocktake_id=stocktake_id,
            store_id=stocktake.store_id,
            total_items=len(stocktake.records),
            variance_items=len(stocktake.records) - matched,
            investigation_items=investigation,
            total_variance_fen=total_variance_fen,
            total_variance_yuan=total_variance_yuan,
            positive_variance_fen=positive_fen,
            negative_variance_fen=negative_fen,
            top_losses=top_losses,
        )

    def approve_stocktake(
        self,
        stocktake_id: str,
        approver_id: str,
    ) -> Stocktake:
        """
        审批通过盘点

        审批后系统库存将按实盘数量调整。
        只有 pending_review 状态的盘点才能审批。
        """
        stocktake = self._get_stocktake(stocktake_id)

        # 如果还在盘点中，先自动提交审核
        if stocktake.status == StocktakeStatus.IN_PROGRESS:
            if not stocktake.records:
                raise ValueError("没有盘点记录，不能提交审核")
            stocktake.status = StocktakeStatus.PENDING_REVIEW
            stocktake.submitted_at = datetime.utcnow().isoformat()

        if stocktake.status != StocktakeStatus.PENDING_REVIEW:
            raise ValueError(
                f"当前状态 [{stocktake.status.value}] 不允许审批，"
                f"需要状态: [pending_review]"
            )

        stocktake.status = StocktakeStatus.APPROVED
        stocktake.approved_by = approver_id
        stocktake.approved_at = datetime.utcnow().isoformat()

        # TODO(后续迁移): 审批通过后触发库存调整
        # await inventory_service.adjust_stock_by_stocktake(stocktake)

        logger.info(
            "stocktake.approved",
            stocktake_id=stocktake_id,
            approver_id=approver_id,
            total_items=len(stocktake.records),
            investigation_items=sum(
                1 for r in stocktake.records if r.needs_investigation
            ),
        )
        return stocktake

    def reject_stocktake(
        self,
        stocktake_id: str,
        reason: str,
    ) -> Stocktake:
        """驳回盘点"""
        stocktake = self._get_stocktake(stocktake_id)

        if stocktake.status != StocktakeStatus.PENDING_REVIEW:
            raise ValueError(
                f"当前状态 [{stocktake.status.value}] 不允许驳回"
            )

        stocktake.status = StocktakeStatus.REJECTED
        stocktake.rejected_reason = reason

        logger.info(
            "stocktake.rejected",
            stocktake_id=stocktake_id,
            reason=reason,
        )
        return stocktake

    # ============================================================
    # 内部方法
    # ============================================================

    def _get_stocktake(self, stocktake_id: str) -> Stocktake:
        """获取盘点会话，不存在则抛异常"""
        stocktake = self._stocktakes.get(stocktake_id)
        if not stocktake:
            raise ValueError(f"盘点会话不存在: stocktake_id={stocktake_id}")
        return stocktake

    def _get_active_stocktake(self, stocktake_id: str) -> Stocktake:
        """获取进行中的盘点会话"""
        stocktake = self._get_stocktake(stocktake_id)
        if stocktake.status != StocktakeStatus.IN_PROGRESS:
            raise ValueError(
                f"盘点已结束，不能继续录入: status={stocktake.status.value}"
            )
        return stocktake

    def _create_count_record(
        self,
        stocktake_id: str,
        ingredient_id: str,
        ingredient_name: str,
        system_qty: float,
        counted_qty: float,
        unit: str,
        unit_cost_fen: int,
        location: str = "",
        note: str = "",
    ) -> CountRecord:
        """
        创建盘点记录并计算差异

        差异计算逻辑：
        - variance = counted_qty - system_qty
        - variance_rate = variance / system_qty（system为0且counted>0时为1.0）
        - variance_fen = round(variance * unit_cost_fen)
        - 差异率绝对值 > 5% 自动标记为"需调查"
        """
        record_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # 计算差异
        variance = counted_qty - system_qty

        # 差异率计算：system为0时特殊处理
        if abs(system_qty) < 0.001:
            variance_rate = 1.0 if abs(counted_qty) > 0.001 else 0.0
        else:
            variance_rate = variance / system_qty

        # 差异金额（分）
        variance_fen = round(variance * unit_cost_fen)

        # 超过阈值自动标记需调查
        needs_investigation = abs(variance_rate) > VARIANCE_THRESHOLD

        return CountRecord(
            record_id=record_id,
            stocktake_id=stocktake_id,
            ingredient_id=ingredient_id,
            ingredient_name=ingredient_name,
            system_qty=system_qty,
            counted_qty=counted_qty,
            unit=unit,
            variance=round(variance, 3),
            variance_rate=round(variance_rate, 4),
            unit_cost_fen=unit_cost_fen,
            variance_fen=variance_fen,
            location=location,
            note=note,
            needs_investigation=needs_investigation,
            counted_at=now,
        )


# 模块级单例
mobile_stocktake_service = MobileStocktakeService()
