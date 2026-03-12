"""
AgentOKRService — P1 统一量化日志服务
记录每次 Agent 决策推送、用户响应、实际效果
计算采纳率/准确率/响应时效，与 PPT 定义的 OKR 对比

用法（在各 Agent API 中调用）：
    log_id = await okr_service.log_recommendation(db, brand_id, store_id,
        agent_name="ops_flow", action_type="order_anomaly",
        recommendation_summary="退单率偏高，建议检查出品质量",
        recommendation_yuan=800.0, confidence=0.85, priority="P1")

    await okr_service.record_adoption(db, log_id, adopted=True)
    await okr_service.verify_outcome(db, log_id, actual_outcome_yuan=750.0)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from src.models.agent_okr import AgentResponseLog, AgentOKRSnapshot

logger = structlog.get_logger()

# ── OKR 目标定义（来自PPT Slide 8）──────────────────────────────────────────────

OKR_TARGETS: Dict[str, Dict[str, Any]] = {
    "business_intel": {
        "adoption_rate":      0.70,  # 决策建议采纳率 >70%
        "accuracy_error_pct": 5.0,   # 预测准确度 ±5%以内
        "latency_seconds":    None,  # 无时效要求
    },
    "ops_flow": {
        "adoption_rate":      0.90,  # 库存预警命中率 >90%
        "accuracy_error_pct": 10.0,
        "latency_seconds":    300,   # 订单异常响应 <5分钟
    },
    "people": {
        "adoption_rate":      0.60,
        "accuracy_error_pct": 8.0,
        "latency_seconds":    None,
    },
    "marketing": {
        "adoption_rate":      0.50,
        "accuracy_error_pct": 15.0,
        "latency_seconds":    None,
    },
    "banquet": {
        "adoption_rate":      0.40,  # 报价转签约率 >40%
        "accuracy_error_pct": 10.0,
        "latency_seconds":    7200,  # 线索跟进 <2小时
    },
    "dish_rd": {
        "adoption_rate":      0.70,
        "accuracy_error_pct": 5.0,
        "latency_seconds":    None,
    },
    "supplier": {
        "adoption_rate":      0.65,
        "accuracy_error_pct": 10.0,
        "latency_seconds":    None,
    },
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def compute_adoption_rate(adopted: int, rejected: int) -> Optional[float]:
    """采纳率 = adopted / (adopted + rejected)"""
    total = adopted + rejected
    if total == 0:
        return None
    return round(adopted / total, 4)


def compute_prediction_error(predicted: float, actual: float) -> Optional[float]:
    """预测误差百分比 = |predicted - actual| / |actual| * 100"""
    if actual == 0:
        return None
    return round(abs(predicted - actual) / abs(actual) * 100, 2)


def check_okr_adoption(agent_name: str, adoption_rate: Optional[float]) -> Optional[bool]:
    """判断采纳率是否达到 OKR 目标"""
    if adoption_rate is None:
        return None
    target = OKR_TARGETS.get(agent_name, {}).get("adoption_rate")
    if target is None:
        return None
    return adoption_rate >= target


def check_okr_accuracy(agent_name: str, avg_error_pct: Optional[float]) -> Optional[bool]:
    """判断预测准确度是否达到 OKR 目标（误差越小越好）"""
    if avg_error_pct is None:
        return None
    target = OKR_TARGETS.get(agent_name, {}).get("accuracy_error_pct")
    if target is None:
        return None
    return avg_error_pct <= target


def check_okr_latency(agent_name: str, avg_latency_s: Optional[float]) -> Optional[bool]:
    """判断响应时效是否达到 OKR 目标"""
    if avg_latency_s is None:
        return None
    target = OKR_TARGETS.get(agent_name, {}).get("latency_seconds")
    if target is None:
        return None
    return avg_latency_s <= target


def build_okr_status_label(met: Optional[bool]) -> str:
    if met is True:
        return "✅ 达标"
    if met is False:
        return "❌ 未达标"
    return "⏳ 数据不足"


# ── Service ───────────────────────────────────────────────────────────────────

class AgentOKRService:

    async def log_recommendation(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        agent_name: str,
        action_type: str,
        recommendation_summary: str,
        recommendation_yuan: float = 0.0,
        confidence: float = 0.8,
        priority: str = "P2",
        source_record_id: Optional[str] = None,
        extra_data: Optional[Dict] = None,
    ) -> str:
        """记录 Agent 推送的建议，返回 log_id"""
        log = AgentResponseLog(
            id=str(uuid.uuid4()),
            brand_id=brand_id,
            store_id=store_id,
            agent_name=agent_name,
            action_type=action_type,
            recommendation_summary=recommendation_summary,
            recommendation_yuan=Decimal(str(recommendation_yuan)) if recommendation_yuan else None,
            confidence=confidence,
            priority=priority,
            source_record_id=source_record_id,
            extra_data=extra_data or {},
        )
        db.add(log)
        logger.info("okr.logged", agent=agent_name, action=action_type, yuan=recommendation_yuan)
        return log.id

    async def record_adoption(
        self,
        db: AsyncSession,
        log_id: str,
        adopted: bool,
    ) -> Dict[str, Any]:
        """记录用户是否接受了 Agent 建议"""
        result = await db.execute(
            select(AgentResponseLog).where(AgentResponseLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        if not log:
            return {"success": False, "message": f"日志 {log_id} 不存在"}

        now = datetime.now()
        log.status = "adopted" if adopted else "rejected"
        log.responded_at = now
        if log.created_at:
            log.response_latency_seconds = int((now - log.created_at).total_seconds())

        logger.info("okr.response_recorded", log_id=log_id, adopted=adopted)
        return {
            "success": True,
            "log_id": log_id,
            "status": log.status,
            "latency_seconds": log.response_latency_seconds,
        }

    async def verify_outcome(
        self,
        db: AsyncSession,
        log_id: str,
        actual_outcome_yuan: float,
    ) -> Dict[str, Any]:
        """验证建议实际效果（采纳后回填）"""
        result = await db.execute(
            select(AgentResponseLog).where(AgentResponseLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        if not log:
            return {"success": False, "message": f"日志 {log_id} 不存在"}

        predicted = float(log.recommendation_yuan or 0)
        error_pct = compute_prediction_error(predicted, actual_outcome_yuan)

        log.actual_outcome_yuan = Decimal(str(actual_outcome_yuan))
        log.prediction_error_pct = error_pct
        log.outcome_verified = True
        log.outcome_verified_at = datetime.now()

        return {
            "success": True,
            "log_id": log_id,
            "predicted_yuan": predicted,
            "actual_yuan": actual_outcome_yuan,
            "prediction_error_pct": error_pct,
        }

    async def get_okr_summary(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
        days: int = 7,
    ) -> Dict[str, Any]:
        """获取所有 Agent 的 OKR 达成概览"""
        since = datetime.now() - timedelta(days=days)

        base_cond = [
            AgentResponseLog.brand_id == brand_id,
            AgentResponseLog.created_at >= since,
        ]
        if store_id:
            base_cond.append(AgentResponseLog.store_id == store_id)

        # 按 agent_name 聚合
        stats_result = await db.execute(
            select(
                AgentResponseLog.agent_name,
                func.count().label("total"),
                func.sum(
                    (AgentResponseLog.status == "adopted").cast(
                        type_=__import__("sqlalchemy").Integer
                    )
                ).label("adopted"),
                func.sum(
                    (AgentResponseLog.status == "rejected").cast(
                        type_=__import__("sqlalchemy").Integer
                    )
                ).label("rejected"),
                func.avg(AgentResponseLog.response_latency_seconds).label("avg_latency"),
                func.avg(AgentResponseLog.prediction_error_pct).label("avg_error"),
                func.sum(AgentResponseLog.recommendation_yuan).label("total_yuan"),
            )
            .where(and_(*base_cond))
            .group_by(AgentResponseLog.agent_name)
        )
        rows = stats_result.all()

        agents_summary = []
        overall_adopted = 0
        overall_rejected = 0
        overall_yuan = 0.0

        for row in rows:
            agent = row.agent_name
            adopted = int(row.adopted or 0)
            rejected = int(row.rejected or 0)
            adoption_rate = compute_adoption_rate(adopted, rejected)
            avg_error = float(row.avg_error) if row.avg_error is not None else None
            avg_latency = float(row.avg_latency) if row.avg_latency is not None else None
            total_yuan = float(row.total_yuan or 0)

            okr_adoption = check_okr_adoption(agent, adoption_rate)
            okr_accuracy = check_okr_accuracy(agent, avg_error)
            okr_latency = check_okr_latency(agent, avg_latency)

            targets = OKR_TARGETS.get(agent, {})
            agents_summary.append({
                "agent_name": agent,
                "total_recommendations": int(row.total),
                "adopted_count": adopted,
                "rejected_count": rejected,
                "adoption_rate": adoption_rate,
                "adoption_rate_pct": round(adoption_rate * 100, 1) if adoption_rate is not None else None,
                "adoption_target_pct": round(targets.get("adoption_rate", 0) * 100, 0),
                "okr_adoption": build_okr_status_label(okr_adoption),
                "avg_prediction_error_pct": avg_error,
                "accuracy_target_pct": targets.get("accuracy_error_pct"),
                "okr_accuracy": build_okr_status_label(okr_accuracy),
                "avg_response_latency_seconds": avg_latency,
                "latency_target_seconds": targets.get("latency_seconds"),
                "okr_latency": build_okr_status_label(okr_latency),
                "total_recommendation_yuan": total_yuan,
            })

            overall_adopted += adopted
            overall_rejected += rejected
            overall_yuan += total_yuan

        overall_rate = compute_adoption_rate(overall_adopted, overall_rejected)
        return {
            "brand_id": brand_id,
            "store_id": store_id,
            "period_days": days,
            "as_of": str(datetime.now()),
            "overall": {
                "total_recommendations": overall_adopted + overall_rejected,
                "overall_adoption_rate": overall_rate,
                "overall_adoption_rate_pct": round(overall_rate * 100, 1) if overall_rate is not None else None,
                "total_recommendation_yuan": round(overall_yuan, 2),
            },
            "agents": agents_summary,
        }

    async def get_recent_logs(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """获取近期 Agent 响应日志"""
        conds = [AgentResponseLog.brand_id == brand_id]
        if store_id:
            conds.append(AgentResponseLog.store_id == store_id)
        if agent_name:
            conds.append(AgentResponseLog.agent_name == agent_name)
        if status:
            conds.append(AgentResponseLog.status == status)

        result = await db.execute(
            select(AgentResponseLog)
            .where(and_(*conds))
            .order_by(desc(AgentResponseLog.created_at))
            .limit(limit)
        )
        logs = result.scalars().all()
        return [_log_to_dict(l) for l in logs]

    async def compute_daily_snapshot(
        self,
        db: AsyncSession,
        brand_id: str,
        target_date: date,
    ) -> Dict[str, Any]:
        """计算指定日期的 OKR 快照并持久化（供 Celery 每日任务调用）"""
        period_str = str(target_date)
        since = datetime(target_date.year, target_date.month, target_date.day)
        until = since + timedelta(days=1)

        # 查询当天数据
        stats_result = await db.execute(
            select(
                AgentResponseLog.agent_name,
                AgentResponseLog.store_id,
                func.count().label("total"),
                func.sum(
                    (AgentResponseLog.status == "adopted").cast(
                        type_=__import__("sqlalchemy").Integer
                    )
                ).label("adopted"),
                func.sum(
                    (AgentResponseLog.status == "rejected").cast(
                        type_=__import__("sqlalchemy").Integer
                    )
                ).label("rejected"),
                func.avg(AgentResponseLog.response_latency_seconds).label("avg_latency"),
                func.avg(AgentResponseLog.prediction_error_pct).label("avg_error"),
                func.avg(AgentResponseLog.confidence).label("avg_conf"),
                func.sum(AgentResponseLog.recommendation_yuan).label("total_yuan"),
                func.sum(AgentResponseLog.actual_outcome_yuan).label("actual_yuan"),
            )
            .where(and_(
                AgentResponseLog.brand_id == brand_id,
                AgentResponseLog.created_at >= since,
                AgentResponseLog.created_at < until,
            ))
            .group_by(AgentResponseLog.agent_name, AgentResponseLog.store_id)
        )

        snapshots_created = 0
        for row in stats_result.all():
            adopted = int(row.adopted or 0)
            rejected = int(row.rejected or 0)
            adoption_rate = compute_adoption_rate(adopted, rejected)
            avg_error = float(row.avg_error) if row.avg_error is not None else None
            avg_latency = float(row.avg_latency) if row.avg_latency is not None else None

            snap = AgentOKRSnapshot(
                id=str(uuid.uuid4()),
                brand_id=brand_id,
                store_id=row.store_id,
                agent_name=row.agent_name,
                period=period_str,
                period_type="day",
                total_recommendations=int(row.total),
                adopted_count=adopted,
                rejected_count=rejected,
                adoption_rate=adoption_rate,
                avg_confidence=float(row.avg_conf) if row.avg_conf else None,
                total_impact_yuan=Decimal(str(row.total_yuan or 0)),
                actual_impact_yuan=Decimal(str(row.actual_yuan or 0)) if row.actual_yuan else None,
                avg_prediction_error_pct=avg_error,
                avg_response_latency_seconds=int(avg_latency) if avg_latency else None,
                okr_adoption_met=check_okr_adoption(row.agent_name, adoption_rate),
                okr_accuracy_met=check_okr_accuracy(row.agent_name, avg_error),
                okr_latency_met=check_okr_latency(row.agent_name, avg_latency),
            )
            db.add(snap)
            snapshots_created += 1

        logger.info("okr.snapshot_computed", brand_id=brand_id, period=period_str,
                    snapshots=snapshots_created)
        return {"period": period_str, "snapshots_created": snapshots_created}


def _log_to_dict(l: AgentResponseLog) -> Dict:
    return {
        "id": l.id, "brand_id": l.brand_id, "store_id": l.store_id,
        "agent_name": l.agent_name, "action_type": l.action_type,
        "recommendation_summary": l.recommendation_summary,
        "recommendation_yuan": float(l.recommendation_yuan or 0),
        "confidence": l.confidence, "priority": l.priority,
        "status": l.status,
        "responded_at": str(l.responded_at) if l.responded_at else None,
        "response_latency_seconds": l.response_latency_seconds,
        "actual_outcome_yuan": float(l.actual_outcome_yuan or 0) if l.actual_outcome_yuan else None,
        "prediction_error_pct": l.prediction_error_pct,
        "outcome_verified": l.outcome_verified,
        "created_at": str(l.created_at),
    }


# 全局单例
agent_okr_service = AgentOKRService()
