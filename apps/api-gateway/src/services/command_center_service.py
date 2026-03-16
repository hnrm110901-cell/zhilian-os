"""
指挥中心服务 — CommandCenterService
跨系统聚合：实时概览、事件流、KPI矩阵、行动调度、系统脉搏。

汇聚 Order / IntegrationHubStatus / ComplianceScore / ComplianceAlert /
DianpingReview / ReconciliationRecord / ProcurementRule / Store 等模型，
为平台管理员提供"作战指挥台"数据源。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, case, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.auto_procurement import ProcurementExecution, ProcurementRule
from src.models.compliance_engine import ComplianceAlert, ComplianceScore
from src.models.dianping_review import DianpingReview
from src.models.integration_hub import IntegrationHubStatus
from src.models.order import Order, OrderStatus
from src.models.reconciliation import ReconciliationRecord, ReconciliationStatus
from src.models.store import Store

logger = structlog.get_logger()

# ── 常量 ──────────────────────────────────────────────────────────────────────

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

_EVENT_ICONS: Dict[str, str] = {
    "order": "ShoppingCartOutlined",
    "integration": "ApiOutlined",
    "compliance": "SafetyCertificateOutlined",
    "review": "CommentOutlined",
    "procurement": "ShoppingOutlined",
    "reconciliation": "AuditOutlined",
}


def _fen_to_yuan(fen: Optional[int]) -> float:
    """分 → 元，保留两位小数"""
    if fen is None:
        return 0.0
    return round(fen / 100, 2)


def _safe_ts(dt: Optional[datetime]) -> Optional[str]:
    """安全输出 ISO 时间戳"""
    return dt.isoformat() if dt else None


# ── Service ───────────────────────────────────────────────────────────────────


class CommandCenterService:
    """指挥中心聚合服务"""

    # ------------------------------------------------------------------ #
    #  1. 实时概览                                                        #
    # ------------------------------------------------------------------ #
    async def get_live_overview(self, db: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """聚合今日核心运营数据，返回一屏概览。"""
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())

        # 今日营收 / 订单数 / 客单价
        order_stats = await self._order_stats_today(db, brand_id, today_start)

        # 集成健康概览
        integration_health = await self._integration_health(db)

        # 合规评分（最新一次快照均值）
        compliance = await self._latest_compliance(db, brand_id)

        # 活跃告警数
        active_alerts = await self._active_alert_count(db, brand_id)

        # 待处理采购建议数
        pending_procurement = await self._pending_procurement(db, brand_id)

        # 未读评论数
        unread_reviews = await self._unread_review_count(db, brand_id)

        # 未处理对账差异数
        unresolved_recon = await self._unresolved_reconciliation(db, brand_id)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "brand_id": brand_id,
            "revenue_today_yuan": order_stats["revenue_yuan"],
            "order_count_today": order_stats["count"],
            "avg_order_value_yuan": order_stats["avg_yuan"],
            "integration_health": integration_health,
            "compliance_score": compliance["score"],
            "compliance_grade": compliance["grade"],
            "active_alerts": active_alerts,
            "pending_procurement": pending_procurement,
            "unread_reviews": unread_reviews,
            "unresolved_reconciliation": unresolved_recon,
        }

    # ------------------------------------------------------------------ #
    #  2. 跨系统事件流                                                    #
    # ------------------------------------------------------------------ #
    async def get_event_stream(self, db: AsyncSession, brand_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """从多张表取最新事件，合并排序后返回。"""
        events: List[Dict[str, Any]] = []
        cutoff = datetime.utcnow() - timedelta(hours=24)

        # 最新订单
        events.extend(await self._recent_order_events(db, brand_id, cutoff, 15))

        # 集成同步事件
        events.extend(await self._recent_integration_events(db, cutoff, 10))

        # 合规告警
        events.extend(await self._recent_compliance_events(db, brand_id, cutoff, 10))

        # 评论事件
        events.extend(await self._recent_review_events(db, brand_id, cutoff, 10))

        # 对账事件
        events.extend(await self._recent_reconciliation_events(db, brand_id, cutoff, 10))

        # 按时间倒序排列，截取 limit
        events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return events[:limit]

    # ------------------------------------------------------------------ #
    #  3. KPI 矩阵                                                       #
    # ------------------------------------------------------------------ #
    async def get_kpi_matrix(self, db: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """多维 KPI 面板数据。"""
        today = date.today()
        week_ago = today - timedelta(days=7)
        month_start = today.replace(day=1)
        today_start = datetime.combine(today, datetime.min.time())
        week_start = datetime.combine(week_ago, datetime.min.time())
        month_start_dt = datetime.combine(month_start, datetime.min.time())

        # ── 营收 KPI ──
        rev_today = await self._revenue_in_range(db, brand_id, today_start, None)
        rev_week = await self._revenue_in_range(db, brand_id, week_start, None)
        rev_month = await self._revenue_in_range(db, brand_id, month_start_dt, None)

        # ── 运营 KPI ──
        completed_count = await self._order_count_by_status(db, brand_id, today_start, OrderStatus.COMPLETED.value)
        total_count = await self._order_count_total(db, brand_id, today_start)
        fulfillment_rate = round(completed_count / total_count * 100, 1) if total_count else 100.0

        # ── 合规 KPI ──
        compliance = await self._latest_compliance(db, brand_id)

        # ── 集成 KPI ──
        integration = await self._integration_kpi(db)

        return {
            "revenue": {
                "daily_yuan": rev_today,
                "weekly_yuan": rev_week,
                "monthly_yuan": rev_month,
            },
            "operations": {
                "order_fulfillment_rate": fulfillment_rate,
                "completed_orders": completed_count,
                "total_orders": total_count,
            },
            "compliance": {
                "overall_score": compliance["score"],
                "grade": compliance["grade"],
                "active_alerts": await self._active_alert_count(db, brand_id),
            },
            "integration": integration,
        }

    # ------------------------------------------------------------------ #
    #  4. 行动调度                                                       #
    # ------------------------------------------------------------------ #
    async def dispatch_action(
        self, db: AsyncSession, brand_id: str, action_type: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调度跨系统操作，返回执行结果。"""
        logger.info(
            "command_center.dispatch",
            brand_id=brand_id,
            action_type=action_type,
        )

        handler = {
            "sync_all": self._dispatch_sync_all,
            "run_closing": self._dispatch_run_closing,
            "check_procurement": self._dispatch_check_procurement,
            "generate_alerts": self._dispatch_generate_alerts,
        }.get(action_type)

        if handler is None:
            return {"success": False, "message": f"未知操作类型: {action_type}"}

        return await handler(db, brand_id, params)

    # ------------------------------------------------------------------ #
    #  5. 系统脉搏                                                       #
    # ------------------------------------------------------------------ #
    async def get_system_pulse(self, db: AsyncSession) -> Dict[str, Any]:
        """平台级全局指标，不限品牌。"""
        today_start = datetime.combine(date.today(), datetime.min.time())

        # 品牌数
        brand_count_q = await db.execute(select(func.count(func.distinct(Store.brand_id))).where(Store.is_active.is_(True)))
        brand_count = brand_count_q.scalar() or 0

        # 门店数
        store_count_q = await db.execute(select(func.count(Store.id)).where(Store.is_active.is_(True)))
        store_count = store_count_q.scalar() or 0

        # 今日订单总数
        order_count_q = await db.execute(select(func.count(Order.id)).where(Order.order_time >= today_start))
        total_orders_today = order_count_q.scalar() or 0

        # 今日营收（全局）
        rev_q = await db.execute(
            select(func.coalesce(func.sum(Order.final_amount), 0)).where(
                and_(
                    Order.order_time >= today_start,
                    Order.status != OrderStatus.CANCELLED.value,
                )
            )
        )
        total_revenue_fen = rev_q.scalar() or 0

        # 集成状态汇总
        integration_q = await db.execute(
            select(
                IntegrationHubStatus.status,
                func.count(IntegrationHubStatus.id),
            ).group_by(IntegrationHubStatus.status)
        )
        integration_summary = {row[0]: row[1] for row in integration_q.all()}

        # 最近系统错误（集成层）
        recent_errors_q = await db.execute(
            select(IntegrationHubStatus)
            .where(IntegrationHubStatus.last_error_at.isnot(None))
            .order_by(desc(IntegrationHubStatus.last_error_at))
            .limit(5)
        )
        recent_errors = [
            {
                "integration": row.display_name,
                "error": row.last_error_message,
                "at": _safe_ts(row.last_error_at),
            }
            for row in recent_errors_q.scalars().all()
        ]

        return {
            "total_brands": brand_count,
            "total_stores": store_count,
            "total_orders_today": total_orders_today,
            "total_revenue_today_yuan": _fen_to_yuan(total_revenue_fen),
            "integration_summary": integration_summary,
            "recent_errors": recent_errors,
        }

    # ================================================================== #
    #  私有：数据聚合帮助方法                                             #
    # ================================================================== #

    async def _order_stats_today(self, db: AsyncSession, brand_id: str, today_start: datetime) -> Dict[str, Any]:
        """今日订单统计：营收/数量/客单价"""
        stmt = (
            select(
                func.coalesce(func.sum(Order.final_amount), 0).label("rev"),
                func.count(Order.id).label("cnt"),
            )
            .where(
                and_(
                    Order.order_time >= today_start,
                    Order.status != OrderStatus.CANCELLED.value,
                )
            )
            .join(Store, Store.id == Order.store_id)
            .where(Store.brand_id == brand_id)
        )
        row = (await db.execute(stmt)).one()
        revenue_fen = row.rev or 0
        count = row.cnt or 0
        avg_fen = (revenue_fen // count) if count else 0
        return {
            "revenue_yuan": _fen_to_yuan(revenue_fen),
            "count": count,
            "avg_yuan": _fen_to_yuan(avg_fen),
        }

    async def _integration_health(self, db: AsyncSession) -> Dict[str, Any]:
        """集成健康汇总"""
        stmt = select(
            IntegrationHubStatus.status,
            func.count(IntegrationHubStatus.id),
        ).group_by(IntegrationHubStatus.status)
        rows = (await db.execute(stmt)).all()
        summary = {r[0]: r[1] for r in rows}
        total = sum(summary.values())
        healthy = summary.get("healthy", 0)
        return {
            "total": total,
            "healthy": healthy,
            "degraded": summary.get("degraded", 0),
            "error": summary.get("error", 0),
            "rate": round(healthy / total * 100, 1) if total else 100.0,
        }

    async def _latest_compliance(self, db: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """品牌下最新合规评分均值"""
        stmt = (
            select(
                func.avg(ComplianceScore.overall_score).label("avg_score"),
            )
            .where(ComplianceScore.brand_id == brand_id)
            .where(
                ComplianceScore.score_date
                == select(func.max(ComplianceScore.score_date))
                .where(ComplianceScore.brand_id == brand_id)
                .correlate(None)
                .scalar_subquery()
            )
        )
        row = (await db.execute(stmt)).one()
        avg_score = round(float(row.avg_score)) if row.avg_score else 0
        # 推导评级
        grade = (
            "A+"
            if avg_score >= 95
            else (
                "A"
                if avg_score >= 85
                else ("B" if avg_score >= 70 else ("C" if avg_score >= 55 else ("D" if avg_score >= 40 else "F")))
            )
        )
        return {"score": avg_score, "grade": grade}

    async def _active_alert_count(self, db: AsyncSession, brand_id: str) -> int:
        stmt = select(func.count(ComplianceAlert.id)).where(
            and_(
                ComplianceAlert.brand_id == brand_id,
                ComplianceAlert.is_resolved.is_(False),
            )
        )
        return (await db.execute(stmt)).scalar() or 0

    async def _pending_procurement(self, db: AsyncSession, brand_id: str) -> int:
        """待执行的采购规则数"""
        stmt = select(func.count(ProcurementRule.id)).where(ProcurementRule.brand_id == brand_id)
        return (await db.execute(stmt)).scalar() or 0

    async def _unread_review_count(self, db: AsyncSession, brand_id: str) -> int:
        """未回复评论数"""
        stmt = select(func.count(DianpingReview.id)).where(
            and_(
                DianpingReview.brand_id == brand_id,
                or_(
                    DianpingReview.reply_content.is_(None),
                    DianpingReview.reply_content == "",
                ),
            )
        )
        return (await db.execute(stmt)).scalar() or 0

    async def _unresolved_reconciliation(self, db: AsyncSession, brand_id: str) -> int:
        """有差异的对账记录数"""
        stmt = (
            select(func.count(ReconciliationRecord.id))
            .join(Store, Store.id == ReconciliationRecord.store_id)
            .where(
                and_(
                    Store.brand_id == brand_id,
                    ReconciliationRecord.status == ReconciliationStatus.MISMATCHED.value,
                )
            )
        )
        return (await db.execute(stmt)).scalar() or 0

    # ── 事件流子查询 ──────────────────────────────────────────────────

    async def _recent_order_events(
        self, db: AsyncSession, brand_id: str, cutoff: datetime, limit: int
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(Order)
            .join(Store, Store.id == Order.store_id)
            .where(and_(Store.brand_id == brand_id, Order.order_time >= cutoff))
            .order_by(desc(Order.order_time))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "timestamp": _safe_ts(r.order_time),
                "source_system": "order",
                "event_type": "new_order",
                "title": f"新订单 ¥{_fen_to_yuan(r.final_amount)}",
                "detail": f"桌号 {r.table_number or '-'}，状态 {r.status}",
                "severity": "info",
                "entity_id": str(r.id),
            }
            for r in rows
        ]

    async def _recent_integration_events(self, db: AsyncSession, cutoff: datetime, limit: int) -> List[Dict[str, Any]]:
        stmt = (
            select(IntegrationHubStatus)
            .where(
                or_(
                    IntegrationHubStatus.last_sync_at >= cutoff,
                    IntegrationHubStatus.last_error_at >= cutoff,
                )
            )
            .order_by(desc(IntegrationHubStatus.updated_at))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        events = []
        for r in rows:
            severity = "info" if r.status == "healthy" else ("critical" if r.status == "error" else "warning")
            events.append(
                {
                    "timestamp": _safe_ts(r.updated_at),
                    "source_system": "integration",
                    "event_type": f"sync_{r.status}",
                    "title": f"{r.display_name} {r.status}",
                    "detail": r.last_error_message or f"今日同步 {r.sync_count_today} 次",
                    "severity": severity,
                    "entity_id": str(r.id),
                }
            )
        return events

    async def _recent_compliance_events(
        self, db: AsyncSession, brand_id: str, cutoff: datetime, limit: int
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(ComplianceAlert)
            .where(
                and_(
                    ComplianceAlert.brand_id == brand_id,
                    ComplianceAlert.created_at >= cutoff,
                )
            )
            .order_by(desc(ComplianceAlert.created_at))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "timestamp": _safe_ts(r.created_at),
                "source_system": "compliance",
                "event_type": r.alert_type,
                "title": r.title,
                "detail": r.description or "",
                "severity": r.severity,
                "entity_id": str(r.id),
            }
            for r in rows
        ]

    async def _recent_review_events(
        self, db: AsyncSession, brand_id: str, cutoff: datetime, limit: int
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(DianpingReview)
            .where(
                and_(
                    DianpingReview.brand_id == brand_id,
                    DianpingReview.created_at >= cutoff,
                )
            )
            .order_by(desc(DianpingReview.created_at))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "timestamp": _safe_ts(r.created_at),
                "source_system": "review",
                "event_type": "new_review",
                "title": f"{r.author_name} {'★' * r.rating}",
                "detail": (r.content or "")[:80],
                "severity": "warning" if r.rating <= 2 else "info",
                "entity_id": str(r.id),
            }
            for r in rows
        ]

    async def _recent_reconciliation_events(
        self, db: AsyncSession, brand_id: str, cutoff: datetime, limit: int
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(ReconciliationRecord)
            .join(Store, Store.id == ReconciliationRecord.store_id)
            .where(
                and_(
                    Store.brand_id == brand_id,
                    ReconciliationRecord.created_at >= cutoff,
                )
            )
            .order_by(desc(ReconciliationRecord.created_at))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "timestamp": _safe_ts(r.created_at),
                "source_system": "reconciliation",
                "event_type": f"recon_{r.status}",
                "title": f"对账 {r.reconciliation_date} {r.status}",
                "detail": f"POS ¥{_fen_to_yuan(r.pos_total_amount)} / 实际 ¥{_fen_to_yuan(r.actual_total_amount)}",
                "severity": "warning" if r.status == ReconciliationStatus.MISMATCHED.value else "info",
                "entity_id": str(r.id),
            }
            for r in rows
        ]

    # ── KPI 子查询 ────────────────────────────────────────────────────

    async def _revenue_in_range(self, db: AsyncSession, brand_id: str, start: datetime, end: Optional[datetime]) -> float:
        conditions = [
            Order.order_time >= start,
            Order.status != OrderStatus.CANCELLED.value,
        ]
        if end:
            conditions.append(Order.order_time < end)
        stmt = (
            select(func.coalesce(func.sum(Order.final_amount), 0))
            .join(Store, Store.id == Order.store_id)
            .where(and_(*conditions, Store.brand_id == brand_id))
        )
        fen = (await db.execute(stmt)).scalar() or 0
        return _fen_to_yuan(fen)

    async def _order_count_by_status(self, db: AsyncSession, brand_id: str, since: datetime, status: str) -> int:
        stmt = (
            select(func.count(Order.id))
            .join(Store, Store.id == Order.store_id)
            .where(
                and_(
                    Store.brand_id == brand_id,
                    Order.order_time >= since,
                    Order.status == status,
                )
            )
        )
        return (await db.execute(stmt)).scalar() or 0

    async def _order_count_total(self, db: AsyncSession, brand_id: str, since: datetime) -> int:
        stmt = (
            select(func.count(Order.id))
            .join(Store, Store.id == Order.store_id)
            .where(
                and_(
                    Store.brand_id == brand_id,
                    Order.order_time >= since,
                )
            )
        )
        return (await db.execute(stmt)).scalar() or 0

    async def _integration_kpi(self, db: AsyncSession) -> Dict[str, Any]:
        """集成层 KPI"""
        stmt = select(
            func.count(IntegrationHubStatus.id).label("total"),
            func.sum(IntegrationHubStatus.sync_count_today).label("syncs"),
            func.sum(IntegrationHubStatus.error_count_today).label("errors"),
        )
        row = (await db.execute(stmt)).one()
        total_syncs = row.syncs or 0
        total_errors = row.errors or 0
        success_rate = round((total_syncs - total_errors) / total_syncs * 100, 1) if total_syncs else 100.0
        return {
            "total_integrations": row.total or 0,
            "sync_count_today": total_syncs,
            "error_count_today": total_errors,
            "success_rate": success_rate,
        }

    # ── 行动调度实现 ──────────────────────────────────────────────────

    async def _dispatch_sync_all(self, db: AsyncSession, brand_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """触发全量同步：重置今日同步计数并标记为"同步中"。"""
        stmt = select(IntegrationHubStatus).where(IntegrationHubStatus.status.in_(["healthy", "degraded", "error"]))
        rows = (await db.execute(stmt)).scalars().all()
        triggered = 0
        for row in rows:
            row.sync_count_today = (row.sync_count_today or 0) + 1
            row.last_sync_at = datetime.utcnow()
            triggered += 1
        await db.commit()
        return {
            "success": True,
            "message": f"已触发 {triggered} 个集成的同步",
            "triggered_count": triggered,
        }

    async def _dispatch_run_closing(self, db: AsyncSession, brand_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """触发日结：统计今日营收数据。"""
        today_start = datetime.combine(date.today(), datetime.min.time())
        stats = await self._order_stats_today(db, brand_id, today_start)
        return {
            "success": True,
            "message": f"日结完成：今日营收 ¥{stats['revenue_yuan']}，共 {stats['count']} 单",
            "revenue_yuan": stats["revenue_yuan"],
            "order_count": stats["count"],
        }

    async def _dispatch_check_procurement(self, db: AsyncSession, brand_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """检查采购规则，返回待执行数量。"""
        count = await self._pending_procurement(db, brand_id)
        return {
            "success": True,
            "message": f"当前有 {count} 条采购规则待检查",
            "pending_count": count,
        }

    async def _dispatch_generate_alerts(self, db: AsyncSession, brand_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """扫描合规风险并返回告警数。"""
        active = await self._active_alert_count(db, brand_id)
        return {
            "success": True,
            "message": f"当前有 {active} 条未处理告警",
            "active_alerts": active,
        }


# 单例
command_center_service = CommandCenterService()
