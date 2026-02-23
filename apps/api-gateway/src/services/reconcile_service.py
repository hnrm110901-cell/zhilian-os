"""
Reconciliation Service
对账服务
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta
from sqlalchemy import select, and_, func
import structlog
import uuid
import os

from src.core.database import get_db_session
from src.models.reconciliation import ReconciliationRecord, ReconciliationStatus
from src.models.order import Order
from src.models.store import Store
from src.services.neural_system import neural_system

logger = structlog.get_logger()


class ReconcileService:
    """对账服务"""

    # 默认差异阈值（百分比）
    DEFAULT_THRESHOLD = float(os.getenv("RECONCILE_DEFAULT_THRESHOLD", "2.0"))

    async def perform_reconciliation(
        self,
        store_id: str,
        reconciliation_date: Optional[date] = None,
        threshold: Optional[float] = None
    ) -> ReconciliationRecord:
        """
        执行对账

        Args:
            store_id: 门店ID
            reconciliation_date: 对账日期（默认为昨天）
            threshold: 差异阈值百分比（默认2%）

        Returns:
            对账记录
        """
        try:
            if reconciliation_date is None:
                # 默认对账昨天的数据
                reconciliation_date = date.today() - timedelta(days=1)

            if threshold is None:
                threshold = await self._get_store_threshold(store_id)

            logger.info(
                "开始执行对账",
                store_id=store_id,
                reconciliation_date=str(reconciliation_date),
                threshold=threshold
            )

            async with get_db_session() as session:
                # 检查是否已存在对账记录
                existing_record = await self._get_existing_record(
                    session, store_id, reconciliation_date
                )

                if existing_record:
                    logger.info(
                        "对账记录已存在，更新数据",
                        store_id=store_id,
                        reconciliation_date=str(reconciliation_date)
                    )
                    record = existing_record
                else:
                    record = ReconciliationRecord(
                        store_id=store_id,
                        reconciliation_date=reconciliation_date
                    )
                    session.add(record)

                # 1. 获取POS数据
                pos_data = await self._fetch_pos_data(
                    session, store_id, reconciliation_date
                )
                record.pos_total_amount = pos_data["total_amount"]
                record.pos_order_count = pos_data["order_count"]
                record.pos_transaction_count = pos_data["transaction_count"]

                # 2. 获取实际数据（从Order表）
                actual_data = await self._fetch_actual_data(
                    session, store_id, reconciliation_date
                )
                record.actual_total_amount = actual_data["total_amount"]
                record.actual_order_count = actual_data["order_count"]
                record.actual_transaction_count = actual_data["transaction_count"]

                # 3. 计算差异
                record.diff_amount = record.actual_total_amount - record.pos_total_amount
                record.diff_order_count = record.actual_order_count - record.pos_order_count
                record.diff_transaction_count = record.actual_transaction_count - record.pos_transaction_count

                # 计算差异比例
                if record.pos_total_amount > 0:
                    record.diff_ratio = (
                        abs(record.diff_amount) / record.pos_total_amount * 100
                    )
                else:
                    record.diff_ratio = 0.0

                # 4. 确定状态
                _match_threshold = float(os.getenv("RECONCILE_MATCH_THRESHOLD", "0.1"))
                if abs(record.diff_ratio) <= _match_threshold:  # 差异小于阈值视为匹配
                    record.status = ReconciliationStatus.MATCHED
                elif abs(record.diff_ratio) > threshold:
                    record.status = ReconciliationStatus.MISMATCHED
                else:
                    record.status = ReconciliationStatus.PENDING

                # 5. 生成差异明细
                record.discrepancies = self._generate_discrepancies(record)

                await session.commit()
                await session.refresh(record)

                # 6. 如果差异超过阈值，触发预警
                if record.status == ReconciliationStatus.MISMATCHED and record.alert_sent == "false":
                    await self._trigger_alert(record, threshold)
                    record.alert_sent = "true"
                    record.alert_sent_at = datetime.now().isoformat()
                    await session.commit()

                logger.info(
                    "对账完成",
                    store_id=store_id,
                    reconciliation_date=str(reconciliation_date),
                    status=record.status.value,
                    diff_ratio=record.diff_ratio
                )

                return record

        except Exception as e:
            logger.error(
                "对账失败",
                store_id=store_id,
                reconciliation_date=str(reconciliation_date) if reconciliation_date else None,
                error=str(e),
                exc_info=e
            )
            raise

    async def _get_store_threshold(self, store_id: str) -> float:
        """获取门店的差异阈值配置"""
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Store).where(Store.id == store_id)
                )
                store = result.scalar_one_or_none()

                if store and hasattr(store, 'reconcile_threshold'):
                    return float(store.reconcile_threshold)

                return self.DEFAULT_THRESHOLD

        except Exception as e:
            logger.warning("获取门店阈值失败，使用默认值", error=str(e))
            return self.DEFAULT_THRESHOLD

    async def _get_existing_record(
        self,
        session,
        store_id: str,
        reconciliation_date: date
    ) -> Optional[ReconciliationRecord]:
        """获取已存在的对账记录"""
        result = await session.execute(
            select(ReconciliationRecord).where(
                and_(
                    ReconciliationRecord.store_id == store_id,
                    ReconciliationRecord.reconciliation_date == reconciliation_date
                )
            )
        )
        return result.scalar_one_or_none()

    async def _fetch_pos_data(
        self,
        session,
        store_id: str,
        reconciliation_date: date
    ) -> Dict[str, int]:
        """
        获取POS数据

        优先从POS适配器获取真实数据，失败时回退到Order表
        """
        business_date = reconciliation_date.strftime("%Y-%m-%d")

        # 尝试从真实POS系统获取数据
        try:
            from src.services.pos_service import pos_service
            summary = await pos_service.query_order_summary(
                ognid=store_id,
                business_date=business_date
            )
            if summary:
                total_amount = int(float(summary.get("totalAmount", 0)) * 100)
                order_count = int(summary.get("orderCount", 0))
                transaction_count = int(summary.get("transactionCount", order_count))
                logger.info(
                    "从POS系统获取对账数据",
                    store_id=store_id,
                    business_date=business_date,
                    total_amount=total_amount,
                    order_count=order_count
                )
                return {
                    "total_amount": total_amount,
                    "order_count": order_count,
                    "transaction_count": transaction_count,
                }
        except Exception as e:
            logger.warning(
                "POS系统获取数据失败，回退到Order表",
                store_id=store_id,
                error=str(e)
            )

        # 回退：从Order表获取数据
        try:
            start_datetime = datetime.combine(reconciliation_date, datetime.min.time())
            end_datetime = datetime.combine(reconciliation_date, datetime.max.time())

            result = await session.execute(
                select(
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_amount")
                ).where(
                    and_(
                        Order.store_id == store_id,
                        Order.created_at >= start_datetime,
                        Order.created_at <= end_datetime,
                        Order.status != "cancelled"
                    )
                )
            )

            row = result.first()
            order_count = row.order_count or 0
            total_amount = int(row.total_amount or 0)

            return {
                "total_amount": total_amount,
                "order_count": order_count,
                "transaction_count": order_count
            }

        except Exception as e:
            logger.error("获取POS数据失败", error=str(e))
            return {
                "total_amount": 0,
                "order_count": 0,
                "transaction_count": 0
            }

    async def _fetch_actual_data(
        self,
        session,
        store_id: str,
        reconciliation_date: date
    ) -> Dict[str, int]:
        """获取实际数据（从系统订单表）"""
        try:
            start_datetime = datetime.combine(reconciliation_date, datetime.min.time())
            end_datetime = datetime.combine(reconciliation_date, datetime.max.time())

            # 查询当天的订单数据
            result = await session.execute(
                select(
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.total_amount).label("total_amount")
                ).where(
                    and_(
                        Order.store_id == store_id,
                        Order.created_at >= start_datetime,
                        Order.created_at <= end_datetime,
                        Order.status == "completed"  # 只统计已完成的订单
                    )
                )
            )

            row = result.first()

            order_count = row.order_count or 0
            total_amount = int(row.total_amount or 0)

            return {
                "total_amount": total_amount,
                "order_count": order_count,
                "transaction_count": order_count
            }

        except Exception as e:
            logger.error("获取实际数据失败", error=str(e))
            return {
                "total_amount": 0,
                "order_count": 0,
                "transaction_count": 0
            }

    def _generate_discrepancies(self, record: ReconciliationRecord) -> List[Dict[str, Any]]:
        """生成差异明细"""
        discrepancies = []

        if record.diff_amount != 0:
            discrepancies.append({
                "type": "amount",
                "description": "金额差异",
                "pos_value": record.pos_total_amount,
                "actual_value": record.actual_total_amount,
                "difference": record.diff_amount,
                "difference_yuan": record.diff_amount / 100
            })

        if record.diff_order_count != 0:
            discrepancies.append({
                "type": "order_count",
                "description": "订单数差异",
                "pos_value": record.pos_order_count,
                "actual_value": record.actual_order_count,
                "difference": record.diff_order_count
            })

        if record.diff_transaction_count != 0:
            discrepancies.append({
                "type": "transaction_count",
                "description": "交易笔数差异",
                "pos_value": record.pos_transaction_count,
                "actual_value": record.actual_transaction_count,
                "difference": record.diff_transaction_count
            })

        return discrepancies

    async def _trigger_alert(self, record: ReconciliationRecord, threshold: float):
        """触发对账异常预警"""
        try:
            diff_yuan = record.diff_amount / 100
            pos_yuan = record.pos_total_amount / 100
            actual_yuan = record.actual_total_amount / 100

            # 触发Neural System事件
            await neural_system.emit_event(
                event_type="reconcile.anomaly",
                data={
                    "reconciliation_id": str(record.id),
                    "store_id": record.store_id,
                    "reconciliation_date": str(record.reconciliation_date),
                    "pos_amount": pos_yuan,
                    "actual_amount": actual_yuan,
                    "diff_amount": diff_yuan,
                    "diff_ratio": record.diff_ratio,
                    "threshold": threshold,
                    "discrepancies": record.discrepancies
                },
                store_id=record.store_id
            )

            logger.info(
                "对账异常预警已触发",
                reconciliation_id=str(record.id),
                diff_ratio=record.diff_ratio
            )

        except Exception as e:
            logger.error("触发对账预警失败", error=str(e), exc_info=e)

    async def get_reconciliation_record(
        self,
        store_id: str,
        reconciliation_date: date
    ) -> Optional[ReconciliationRecord]:
        """获取对账记录"""
        try:
            async with get_db_session() as session:
                return await self._get_existing_record(session, store_id, reconciliation_date)
        except Exception as e:
            logger.error("获取对账记录失败", error=str(e), exc_info=e)
            return None

    async def confirm_reconciliation(
        self,
        record_id: uuid.UUID,
        user_id: uuid.UUID,
        resolution: Optional[str] = None
    ) -> bool:
        """确认对账记录"""
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(ReconciliationRecord).where(
                        ReconciliationRecord.id == record_id
                    )
                )
                record = result.scalar_one_or_none()

                if record:
                    record.status = ReconciliationStatus.CONFIRMED
                    record.confirmed_by = user_id
                    record.confirmed_at = datetime.now().isoformat()
                    if resolution:
                        record.resolution = resolution
                    record.updated_at = datetime.now()

                    await session.commit()

                    logger.info(
                        "对账记录已确认",
                        record_id=str(record_id),
                        user_id=str(user_id)
                    )
                    return True

                return False

        except Exception as e:
            logger.error("确认对账记录失败", error=str(e), exc_info=e)
            return False

    async def query_reconciliation_records(
        self,
        store_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[ReconciliationStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """查询对账记录列表"""
        try:
            async with get_db_session() as session:
                # 构建查询条件
                conditions = [ReconciliationRecord.store_id == store_id]

                if start_date:
                    conditions.append(ReconciliationRecord.reconciliation_date >= start_date)
                if end_date:
                    conditions.append(ReconciliationRecord.reconciliation_date <= end_date)
                if status:
                    conditions.append(ReconciliationRecord.status == status)

                # 查询总数
                count_query = select(ReconciliationRecord).where(and_(*conditions))
                count_result = await session.execute(count_query)
                total = len(count_result.scalars().all())

                # 分页查询
                offset = (page - 1) * page_size
                query = (
                    select(ReconciliationRecord)
                    .where(and_(*conditions))
                    .order_by(ReconciliationRecord.reconciliation_date.desc())
                    .offset(offset)
                    .limit(page_size)
                )

                result = await session.execute(query)
                records = result.scalars().all()

                return {
                    "records": records,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size
                }

        except Exception as e:
            logger.error("查询对账记录失败", error=str(e), exc_info=e)
            raise


# 创建全局服务实例
reconcile_service = ReconcileService()
