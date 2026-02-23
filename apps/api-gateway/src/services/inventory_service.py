"""
Inventory Service - 库存管理数据库服务
处理库存的数据库操作
"""
import structlog
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload
import uuid

from src.core.database import get_db_session
from src.models.inventory import InventoryItem, InventoryTransaction, InventoryStatus, TransactionType

logger = structlog.get_logger()


class InventoryService:
    """库存服务类"""

    def __init__(self, store_id: str = "STORE001"):
        """
        初始化库存服务

        Args:
            store_id: 门店ID
        """
        self.store_id = store_id
        self.alert_thresholds = {
            "low_stock_ratio": float(os.getenv("INVENTORY_LOW_STOCK_RATIO", "0.3")),
            "critical_stock_ratio": float(os.getenv("INVENTORY_CRITICAL_STOCK_RATIO", "0.1")),
        }
        logger.info("InventoryService初始化", store_id=store_id)

    async def monitor_inventory(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        监控库存状态

        Args:
            category: 物料分类
            status: 库存状态

        Returns:
            库存项目列表
        """
        async with get_db_session() as session:
            stmt = (
                select(InventoryItem)
                .where(InventoryItem.store_id == self.store_id)
            )

            if category:
                stmt = stmt.where(InventoryItem.category == category)

            if status:
                stmt = stmt.where(InventoryItem.status == status)

            stmt = stmt.order_by(InventoryItem.name)

            result = await session.execute(stmt)
            items = result.scalars().all()

            return [self._item_to_dict(item) for item in items]

    async def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        获取库存项目详情

        Args:
            item_id: 物料ID

        Returns:
            库存项目信息
        """
        async with get_db_session() as session:
            stmt = (
                select(InventoryItem)
                .options(selectinload(InventoryItem.transactions))
                .where(InventoryItem.id == item_id)
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()

            if not item:
                return None

            return self._item_to_dict(item, include_transactions=True)

    async def generate_restock_alerts(
        self,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        生成补货提醒

        Args:
            category: 物料分类

        Returns:
            补货提醒列表
        """
        async with get_db_session() as session:
            stmt = (
                select(InventoryItem)
                .where(
                    and_(
                        InventoryItem.store_id == self.store_id,
                        or_(
                            InventoryItem.status == InventoryStatus.LOW,
                            InventoryItem.status == InventoryStatus.CRITICAL,
                            InventoryItem.status == InventoryStatus.OUT_OF_STOCK
                        )
                    )
                )
            )

            if category:
                stmt = stmt.where(InventoryItem.category == category)

            stmt = stmt.order_by(InventoryItem.status.desc(), InventoryItem.name)

            result = await session.execute(stmt)
            items = result.scalars().all()

            # Optimize: Fetch all transaction data in a single query to avoid N+1
            if items:
                item_ids = [item.id for item in items]
                thirty_days_ago = datetime.now() - timedelta(days=int(os.getenv("INVENTORY_HISTORY_DAYS", "30")))

                trans_stmt = (
                    select(InventoryTransaction)
                    .where(
                        and_(
                            InventoryTransaction.item_id.in_(item_ids),
                            InventoryTransaction.transaction_type == TransactionType.USAGE,
                            InventoryTransaction.transaction_time >= thirty_days_ago
                        )
                    )
                )
                trans_result = await session.execute(trans_stmt)
                all_transactions = trans_result.scalars().all()

                # Group transactions by item_id for quick lookup
                transactions_by_item = {}
                for trans in all_transactions:
                    if trans.item_id not in transactions_by_item:
                        transactions_by_item[trans.item_id] = []
                    transactions_by_item[trans.item_id].append(trans)

            alerts = []
            for item in items:
                # 计算建议补货数量
                recommended_quantity = self._calculate_restock_quantity(item)

                # 预测缺货日期 - 使用预加载的交易数据
                item_transactions = transactions_by_item.get(item.id, [])
                estimated_stockout_date = self._estimate_stockout_date_from_transactions(
                    item, item_transactions
                )

                alert = {
                    "alert_id": f"ALERT_{item.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "item_id": item.id,
                    "item_name": item.name,
                    "category": item.category,
                    "current_stock": item.current_quantity,
                    "min_stock": item.min_quantity,
                    "recommended_quantity": recommended_quantity,
                    "alert_level": self._get_alert_level(item),
                    "status": item.status.value,
                    "estimated_stockout_date": estimated_stockout_date,
                    "supplier_name": item.supplier_name,
                    "supplier_contact": item.supplier_contact,
                    "created_at": datetime.now().isoformat()
                }
                alerts.append(alert)

            return alerts

    async def record_transaction(
        self,
        item_id: str,
        transaction_type: str,
        quantity: float,
        unit_cost: Optional[int] = None,
        reference_id: Optional[str] = None,
        notes: Optional[str] = None,
        performed_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        记录库存交易

        Args:
            item_id: 物料ID
            transaction_type: 交易类型
            quantity: 数量（正数为入库，负数为出库）
            unit_cost: 单位成本（分）
            reference_id: 关联ID
            notes: 备注
            performed_by: 操作人

        Returns:
            交易记录
        """
        async with get_db_session() as session:
            try:
                # 获取库存项目
                stmt = select(InventoryItem).where(InventoryItem.id == item_id)
                result = await session.execute(stmt)
                item = result.scalar_one_or_none()

                if not item:
                    raise ValueError(f"库存项目不存在: {item_id}")

                # 记录交易前数量
                quantity_before = item.current_quantity

                # 更新库存数量
                item.current_quantity += quantity
                quantity_after = item.current_quantity

                # 更新库存状态
                item.status = self._calculate_status(item)

                # 创建交易记录
                transaction = InventoryTransaction(
                    item_id=item_id,
                    store_id=self.store_id,
                    transaction_type=TransactionType(transaction_type),
                    quantity=quantity,
                    unit_cost=unit_cost or item.unit_cost,
                    total_cost=(unit_cost or item.unit_cost) * abs(quantity) if unit_cost or item.unit_cost else 0,
                    quantity_before=quantity_before,
                    quantity_after=quantity_after,
                    reference_id=reference_id,
                    notes=notes,
                    performed_by=performed_by,
                    transaction_time=datetime.utcnow()
                )

                session.add(transaction)
                await session.commit()

                logger.info(
                    "库存交易记录成功",
                    item_id=item_id,
                    type=transaction_type,
                    quantity=quantity
                )

                return {
                    "transaction_id": str(transaction.id),
                    "item_id": item_id,
                    "item_name": item.name,
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "quantity_before": quantity_before,
                    "quantity_after": quantity_after,
                    "status": item.status.value,
                    "transaction_time": transaction.transaction_time.isoformat()
                }

            except Exception as e:
                await session.rollback()
                logger.error("记录库存交易失败", error=str(e))
                raise

    async def get_inventory_statistics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取库存统计

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计信息
        """
        async with get_db_session() as session:
            # 查询所有库存项目
            items_stmt = select(InventoryItem).where(InventoryItem.store_id == self.store_id)
            items_result = await session.execute(items_stmt)
            items = items_result.scalars().all()

            # 统计库存状态
            status_counts = {
                "normal": 0,
                "low": 0,
                "critical": 0,
                "out_of_stock": 0
            }
            for item in items:
                status_counts[item.status.value] = status_counts.get(item.status.value, 0) + 1

            # 计算库存总值
            total_value = sum(
                (item.current_quantity * (item.unit_cost or 0))
                for item in items
            ) / 100  # Convert cents to yuan

            # 查询交易记录
            transactions_stmt = select(InventoryTransaction).where(
                InventoryTransaction.store_id == self.store_id
            )

            if start_date:
                start_dt = datetime.fromisoformat(start_date)
                transactions_stmt = transactions_stmt.where(
                    InventoryTransaction.transaction_time >= start_dt
                )

            if end_date:
                end_dt = datetime.fromisoformat(end_date)
                transactions_stmt = transactions_stmt.where(
                    InventoryTransaction.transaction_time <= end_dt
                )

            transactions_result = await session.execute(transactions_stmt)
            transactions = transactions_result.scalars().all()

            # 统计交易类型
            transaction_counts = {}
            for trans in transactions:
                trans_type = trans.transaction_type.value
                transaction_counts[trans_type] = transaction_counts.get(trans_type, 0) + 1

            return {
                "total_items": len(items),
                "total_value": round(total_value, 2),
                "status_breakdown": status_counts,
                "transaction_counts": transaction_counts,
                "alerts_count": status_counts["low"] + status_counts["critical"] + status_counts["out_of_stock"]
            }

    async def get_inventory_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取库存报告

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            库存报告
        """
        # 获取库存监控数据
        inventory_items = await self.monitor_inventory()

        # 获取补货提醒
        restock_alerts = await self.generate_restock_alerts()

        # 获取统计数据
        statistics = await self.get_inventory_statistics(start_date, end_date)

        return {
            "report_generated_at": datetime.now().isoformat(),
            "store_id": self.store_id,
            "inventory_summary": {
                "total_items": statistics["total_items"],
                "total_value": statistics["total_value"],
                "status_breakdown": statistics["status_breakdown"]
            },
            "restock_alerts": restock_alerts,
            "critical_items": [
                item for item in inventory_items
                if item["status"] in ["critical", "out_of_stock"]
            ],
            "low_stock_items": [
                item for item in inventory_items
                if item["status"] == "low"
            ],
            "recommendations": self._generate_recommendations(inventory_items, restock_alerts)
        }

    def _item_to_dict(
        self,
        item: InventoryItem,
        include_transactions: bool = False
    ) -> Dict[str, Any]:
        """
        将库存项目对象转换为字典

        Args:
            item: 库存项目对象
            include_transactions: 是否包含交易记录

        Returns:
            库存项目字典
        """
        item_dict = {
            "item_id": item.id,
            "name": item.name,
            "category": item.category,
            "unit": item.unit,
            "current_quantity": item.current_quantity,
            "min_quantity": item.min_quantity,
            "max_quantity": item.max_quantity,
            "unit_cost": item.unit_cost / 100 if item.unit_cost else 0,
            "status": item.status.value,
            "supplier_name": item.supplier_name,
            "supplier_contact": item.supplier_contact,
            "stock_value": (item.current_quantity * (item.unit_cost or 0)) / 100
        }

        if include_transactions and hasattr(item, "transactions") and item.transactions:
            item_dict["recent_transactions"] = [
                {
                    "transaction_id": str(trans.id),
                    "type": trans.transaction_type.value,
                    "quantity": trans.quantity,
                    "quantity_before": trans.quantity_before,
                    "quantity_after": trans.quantity_after,
                    "transaction_time": trans.transaction_time.isoformat() if trans.transaction_time else None
                }
                for trans in sorted(item.transactions, key=lambda t: t.transaction_time, reverse=True)[:10]
            ]

        return item_dict

    def _calculate_status(self, item: InventoryItem) -> InventoryStatus:
        """计算库存状态"""
        if item.current_quantity <= 0:
            return InventoryStatus.OUT_OF_STOCK
        elif item.current_quantity <= item.min_quantity * self.alert_thresholds["critical_stock_ratio"]:
            return InventoryStatus.CRITICAL
        elif item.current_quantity <= item.min_quantity:
            return InventoryStatus.LOW
        else:
            return InventoryStatus.NORMAL

    def _calculate_restock_quantity(self, item: InventoryItem) -> float:
        """计算建议补货数量"""
        if item.max_quantity:
            return item.max_quantity - item.current_quantity
        else:
            # 如果没有设置最大库存，建议补到安全库存的N倍（支持环境变量覆盖）
            restock_multiplier = float(os.getenv("INVENTORY_RESTOCK_MULTIPLIER", "2"))
            return item.min_quantity * restock_multiplier - item.current_quantity

    async def _estimate_stockout_date(
        self,
        session,
        item: InventoryItem
    ) -> Optional[str]:
        """预测缺货日期 - 已弃用，使用 _estimate_stockout_date_from_transactions"""
        # 查询最近30天的消耗记录
        thirty_days_ago = datetime.now() - timedelta(days=int(os.getenv("INVENTORY_HISTORY_DAYS", "30")))
        stmt = (
            select(InventoryTransaction)
            .where(
                and_(
                    InventoryTransaction.item_id == item.id,
                    InventoryTransaction.transaction_type == TransactionType.USAGE,
                    InventoryTransaction.transaction_time >= thirty_days_ago
                )
            )
        )
        result = await session.execute(stmt)
        transactions = result.scalars().all()

        return self._estimate_stockout_date_from_transactions(item, transactions)

    def _estimate_stockout_date_from_transactions(
        self,
        item: InventoryItem,
        transactions: List[InventoryTransaction]
    ) -> Optional[str]:
        """从交易记录预测缺货日期 - 优化版本，避免N+1查询"""
        if not transactions:
            return None

        # 计算平均每日消耗
        thirty_days_ago = datetime.now() - timedelta(days=int(os.getenv("INVENTORY_HISTORY_DAYS", "30")))
        total_usage = sum(abs(trans.quantity) for trans in transactions)
        days = (datetime.now() - thirty_days_ago).days
        avg_daily_usage = total_usage / days if days > 0 else 0

        if avg_daily_usage <= 0:
            return None

        # 预测缺货天数
        days_until_stockout = item.current_quantity / avg_daily_usage
        stockout_date = datetime.now() + timedelta(days=days_until_stockout)

        return stockout_date.isoformat()

    def _get_alert_level(self, item: InventoryItem) -> str:
        """获取预警级别"""
        if item.status == InventoryStatus.OUT_OF_STOCK:
            return "critical"
        elif item.status == InventoryStatus.CRITICAL:
            return "urgent"
        elif item.status == InventoryStatus.LOW:
            return "warning"
        else:
            return "info"

    def _generate_recommendations(
        self,
        inventory_items: List[Dict[str, Any]],
        restock_alerts: List[Dict[str, Any]]
    ) -> List[str]:
        """生成建议"""
        recommendations = []

        if len(restock_alerts) > 0:
            recommendations.append(f"有{len(restock_alerts)}个物料需要补货")

        critical_count = sum(1 for item in inventory_items if item["status"] == "critical")
        if critical_count > 0:
            recommendations.append(f"有{critical_count}个物料库存严重不足，需要紧急处理")

        out_of_stock_count = sum(1 for item in inventory_items if item["status"] == "out_of_stock")
        if out_of_stock_count > 0:
            recommendations.append(f"有{out_of_stock_count}个物料已缺货，影响正常运营")

        return recommendations


# 创建全局服务实例
inventory_service = InventoryService()
