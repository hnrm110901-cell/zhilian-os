"""
损耗事件服务（业务核心）

职责：
  1. CRUD — 损耗事件的记录和查询
  2. 理论消耗计算 — 从 BOM 查标准用量，与实际对比
  3. 触发五步推理 — 异步调用 WasteReasoningEngine
  4. Neo4j 双写 — 将事件同步到本体层（Palantir Sense Layer）
  5. 自动创建企微 Action — 达到阈值时推送告警
"""

import hashlib
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.waste_event import WasteEvent, WasteEventStatus, WasteEventType

logger = structlog.get_logger()

# 触发企微告警的损耗量阈值（variance_pct，即偏差百分比）
WECHAT_ALERT_THRESHOLD = 0.20  # 超出理论消耗 20%


class WasteEventService:
    """损耗事件业务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create_event(
        self,
        store_id: str,
        ingredient_id: str,
        quantity: float,
        unit: str,
        event_type: WasteEventType = WasteEventType.UNKNOWN,
        dish_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        reported_by: Optional[str] = None,
        assigned_staff_id: Optional[str] = None,
        notes: Optional[str] = None,
        photo_urls: Optional[List[str]] = None,
        auto_analyze: bool = True,
    ) -> WasteEvent:
        """
        记录损耗事件。

        若 dish_id 已知，则自动从 BOM 计算理论消耗并得出偏差。
        当 auto_analyze=True 时，提交后异步触发五步推理。
        """
        ts = int(time.time() * 1000)
        raw = f"{store_id}:{ingredient_id}:{ts}"
        event_id = "WE-" + hashlib.sha1(raw.encode()).hexdigest()[:10].upper()

        theoretical_qty = None
        variance_qty = None
        variance_pct = None

        if dish_id:
            theoretical_qty = await self._fetch_theoretical_qty(dish_id, ingredient_id)
            if theoretical_qty and theoretical_qty > 0:
                variance_qty = float(quantity) - float(theoretical_qty)
                variance_pct = round(variance_qty / float(theoretical_qty), 4)

        event = WasteEvent(
            id=uuid.uuid4(),
            event_id=event_id,
            store_id=store_id,
            event_type=event_type,
            status=WasteEventStatus.PENDING,
            dish_id=uuid.UUID(dish_id) if dish_id else None,
            ingredient_id=ingredient_id,
            quantity=quantity,
            unit=unit,
            theoretical_qty=theoretical_qty,
            variance_qty=variance_qty,
            variance_pct=variance_pct,
            occurred_at=occurred_at or datetime.utcnow(),
            reported_by=reported_by,
            assigned_staff_id=assigned_staff_id,
            notes=notes,
            photo_urls=photo_urls,
        )
        self.db.add(event)
        await self.db.flush()

        # Neo4j 本体同步（非阻塞）
        await self._sync_to_neo4j(event)

        # 触发企微告警（偏差超阈值）
        if variance_pct and abs(variance_pct) >= WECHAT_ALERT_THRESHOLD:
            await self._trigger_wechat_alert(event)

        logger.info(
            "损耗事件已记录",
            event_id=event_id,
            store_id=store_id,
            ingredient_id=ingredient_id,
            qty=quantity,
            variance_pct=variance_pct,
        )

        # 异步触发推理（由 Celery 任务处理，此处放入队列）
        if auto_analyze:
            self._enqueue_analysis(event_id)

        return event

    async def get_event(self, event_id: str) -> Optional[WasteEvent]:
        """按 event_id（字符串）查询"""
        stmt = select(WasteEvent).where(WasteEvent.event_id == event_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_uuid(self, uuid_id: str) -> Optional[WasteEvent]:
        """按 UUID 主键查询"""
        stmt = select(WasteEvent).where(WasteEvent.id == uuid.UUID(uuid_id))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_events(
        self,
        store_id: str,
        status: Optional[WasteEventStatus] = None,
        event_type: Optional[WasteEventType] = None,
        dish_id: Optional[str] = None,
        ingredient_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WasteEvent]:
        """查询门店损耗事件列表"""
        since = datetime.utcnow() - timedelta(days=days)
        conditions = [
            WasteEvent.store_id == store_id,
            WasteEvent.occurred_at >= since,
        ]
        if status:
            conditions.append(WasteEvent.status == status)
        if event_type:
            conditions.append(WasteEvent.event_type == event_type)
        if dish_id:
            conditions.append(WasteEvent.dish_id == uuid.UUID(dish_id))
        if ingredient_id:
            conditions.append(WasteEvent.ingredient_id == ingredient_id)

        stmt = (
            select(WasteEvent)
            .where(and_(*conditions))
            .order_by(WasteEvent.occurred_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def write_back_analysis(
        self,
        event_id: str,
        root_cause: str,
        confidence: float,
        evidence: dict,
        scores: dict,
    ) -> Optional[WasteEvent]:
        """将推理结论回写（由 WasteReasoningEngine / Celery 调用）"""
        await self.db.execute(
            update(WasteEvent)
            .where(WasteEvent.event_id == event_id)
            .values(
                root_cause=root_cause,
                confidence=confidence,
                evidence=evidence,
                scores=scores,
                status=WasteEventStatus.ANALYZED,
            )
        )
        return await self.get_event(event_id)

    async def verify_event(
        self,
        event_id: str,
        verified_root_cause: str,
        verifier: str,
        action_taken: Optional[str] = None,
    ) -> Optional[WasteEvent]:
        """人工验证推理结论"""
        stmt = select(WasteEvent).where(WasteEvent.event_id == event_id)
        result = await self.db.execute(stmt)
        ev = result.scalar_one_or_none()
        if not ev:
            return None
        ev.root_cause = verified_root_cause
        ev.status = WasteEventStatus.VERIFIED
        ev.action_taken = action_taken
        await self.db.flush()
        # 同步验证结果到 Neo4j
        await self._sync_analysis_to_neo4j(ev)
        return ev

    async def close_event(self, event_id: str) -> bool:
        """关闭损耗事件"""
        await self.db.execute(
            update(WasteEvent)
            .where(WasteEvent.event_id == event_id)
            .values(status=WasteEventStatus.CLOSED)
        )
        return True

    # ── 聚合统计 ──────────────────────────────────────────────────────────────

    async def get_store_waste_summary(
        self,
        store_id: str,
        days: int = 30,
    ) -> dict:
        """门店损耗汇总（按食材分组）"""
        from sqlalchemy import func
        since = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(
                WasteEvent.ingredient_id,
                func.sum(WasteEvent.quantity).label("total_qty"),
                func.count(WasteEvent.id).label("event_count"),
                func.avg(WasteEvent.variance_pct).label("avg_variance_pct"),
            )
            .where(
                and_(
                    WasteEvent.store_id == store_id,
                    WasteEvent.occurred_at >= since,
                )
            )
            .group_by(WasteEvent.ingredient_id)
            .order_by(func.sum(WasteEvent.quantity).desc())
            .limit(20)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        total_events = await self.db.execute(
            select(func.count(WasteEvent.id)).where(
                and_(WasteEvent.store_id == store_id, WasteEvent.occurred_at >= since)
            )
        )

        return {
            "store_id": store_id,
            "days": days,
            "total_events": total_events.scalar() or 0,
            "by_ingredient": [
                {
                    "ingredient_id": row.ingredient_id,
                    "total_qty": float(row.total_qty or 0),
                    "event_count": row.event_count,
                    "avg_variance_pct": round(float(row.avg_variance_pct or 0), 4),
                }
                for row in rows
            ],
        }

    async def get_root_cause_distribution(
        self,
        store_id: str,
        days: int = 30,
    ) -> List[dict]:
        """损耗根因分布统计"""
        from sqlalchemy import func
        since = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(
                WasteEvent.root_cause,
                func.count(WasteEvent.id).label("count"),
                func.avg(WasteEvent.confidence).label("avg_confidence"),
            )
            .where(
                and_(
                    WasteEvent.store_id == store_id,
                    WasteEvent.occurred_at >= since,
                    WasteEvent.root_cause.isnot(None),
                )
            )
            .group_by(WasteEvent.root_cause)
            .order_by(func.count(WasteEvent.id).desc())
        )
        result = await self.db.execute(stmt)
        return [
            {
                "root_cause": row.root_cause,
                "count": row.count,
                "avg_confidence": round(float(row.avg_confidence or 0), 3),
            }
            for row in result.all()
        ]

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _fetch_theoretical_qty(
        self,
        dish_id: str,
        ingredient_id: str,
    ) -> Optional[float]:
        """从 BOM 读取食材的标准用量（理论消耗）"""
        from src.models.bom import BOMTemplate, BOMItem
        from sqlalchemy import and_

        stmt = (
            select(BOMItem.standard_qty)
            .join(BOMTemplate, BOMItem.bom_id == BOMTemplate.id)
            .where(
                and_(
                    BOMTemplate.dish_id == uuid.UUID(dish_id),
                    BOMTemplate.is_active.is_(True),
                    BOMItem.ingredient_id == ingredient_id,
                )
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        qty = result.scalar()
        return float(qty) if qty else None

    async def _sync_to_neo4j(self, event: WasteEvent) -> None:
        """将损耗事件写入 Neo4j WasteEvent 节点"""
        try:
            from src.ontology.data_sync import OntologyDataSync

            with OntologyDataSync() as sync:
                cypher = """
                MERGE (w:WasteEvent {event_id: $event_id})
                ON CREATE SET
                    w.quantity     = $qty,
                    w.unit         = $unit,
                    w.event_type   = $event_type,
                    w.occurred_at  = $occurred_at,
                    w.store_id     = $store_id,
                    w.created_at   = timestamp()
                ON MATCH SET
                    w.quantity     = $qty,
                    w.unit         = $unit
                WITH w
                MATCH (i:Ingredient {ing_id: $ingredient_id})
                MERGE (w)-[:WASTE_OF]->(i)
                """
                with sync.driver.session() as session:
                    session.run(
                        cypher,
                        event_id=event.event_id,
                        qty=float(event.quantity),
                        unit=event.unit,
                        event_type=event.event_type.value,
                        occurred_at=int(event.occurred_at.timestamp() * 1000),
                        store_id=event.store_id,
                        ingredient_id=event.ingredient_id,
                    )
                    # 关联菜品（如有）
                    if event.dish_id:
                        session.run(
                            """
                            MATCH (w:WasteEvent {event_id: $event_id})
                            MATCH (d:Dish {dish_id: $dish_id})
                            MERGE (w)-[:WASTE_OF]->(d)
                            """,
                            event_id=event.event_id,
                            dish_id=f"DISH-{event.dish_id}",
                        )
        except Exception as e:
            logger.warning("WasteEvent Neo4j 同步失败", error=str(e), event_id=event.event_id)

    async def _sync_analysis_to_neo4j(self, event: WasteEvent) -> None:
        """将推理结论回写 Neo4j WasteEvent 节点"""
        if not event.root_cause:
            return
        try:
            import json
            from src.ontology.data_sync import OntologyDataSync

            with OntologyDataSync() as sync:
                with sync.driver.session() as session:
                    session.run(
                        """
                        MATCH (w:WasteEvent {event_id: $event_id})
                        SET w.root_cause     = $root_cause,
                            w.confidence     = $confidence,
                            w.evidence_chain = $evidence,
                            w.scores         = $scores
                        """,
                        event_id=event.event_id,
                        root_cause=event.root_cause,
                        confidence=event.confidence or 0.0,
                        evidence=json.dumps(event.evidence or {}),
                        scores=json.dumps(event.scores or {}),
                    )
        except Exception as e:
            logger.warning("WasteEvent 推理结论 Neo4j 同步失败", error=str(e))

    async def _trigger_wechat_alert(self, event: WasteEvent) -> None:
        """损耗偏差超阈值时，创建企微 Action 告警"""
        try:
            from src.services.wechat_action_fsm import (
                ActionCategory,
                ActionPriority,
                get_wechat_fsm,
            )
            fsm = get_wechat_fsm()
            pct = round((event.variance_pct or 0) * 100, 1)
            priority = ActionPriority.P0 if abs(pct) >= 50 else ActionPriority.P1

            action = await fsm.create_action(
                store_id=event.store_id,
                category=ActionCategory.WASTE_ALERT,
                priority=priority,
                title=f"损耗偏差告警：{event.ingredient_id}（+{pct}%）",
                content=(
                    f"食材 `{event.ingredient_id}` 实际损耗 {event.quantity}{event.unit}，"
                    f"超出BOM理论值 {pct}%\n"
                    f"事件ID：`{event.event_id}`\n"
                    f"发生时间：{event.occurred_at.strftime('%Y-%m-%d %H:%M')}"
                ),
                receiver_user_id=event.reported_by or "store_manager",
                source_event_id=event.event_id,
                evidence={"variance_pct": event.variance_pct, "quantity": float(event.quantity)},
            )
            await fsm.push_to_wechat(action.action_id)

            # 记录 Action ID 到事件
            await self.db.execute(
                update(WasteEvent)
                .where(WasteEvent.id == event.id)
                .values(wechat_action_id=action.action_id)
            )
        except Exception as e:
            logger.warning("企微损耗告警失败", error=str(e), event_id=event.event_id)

    def _enqueue_analysis(self, event_id: str) -> None:
        """投递损耗推理到 Celery 队列"""
        try:
            from src.core.celery_tasks import process_waste_event
            process_waste_event.delay(event_id)
        except Exception as e:
            logger.warning("Celery 推理任务投递失败", error=str(e), event_id=event_id)
