"""
执行闭环反馈服务
Execution Feedback Service

记录决策执行结果，形成"建议→执行→结果→健康分更新"的完整闭环。

反馈流程：
  1. 店长/系统提交执行反馈（decision_id + outcome + actual_impact_yuan）
  2. 更新 decision_logs 的 outcome / actual_result / result_deviation
  3. 根据反馈结果调整对应门店的私域信号（positive_outcome → 记录成功信号）
  4. 返回健康分变化摘要（before / after 对比）

无新增数据库表，复用：
  - decision_logs（已有）
  - private_domain_signals（已有，写入 consumption 类型正向信号）
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


# ── 主函数 ────────────────────────────────────────────────────────────────────


async def submit_execution_feedback(
    decision_id: str,
    store_id: str,
    outcome: str,  # "success" | "failure" | "partial"
    actual_impact_yuan: float,
    executor_id: str,
    note: Optional[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    提交决策执行反馈，更新 decision_log，触发健康分重算。

    Args:
        decision_id:        决策日志 ID
        store_id:           门店 ID
        outcome:            执行结果（success/failure/partial）
        actual_impact_yuan: 实际¥影响（元）
        executor_id:        执行人 ID
        note:               备注
        db:                 数据库会话

    Returns:
        {
            "decision_id":      str,
            "outcome":          str,
            "actual_impact_yuan": float,
            "health_before":    float,
            "health_after":     float,
            "health_delta":     float,
            "signal_id":        str | None,
        }
    """
    # ① 查询执行前健康分
    health_before = await _get_current_score(store_id, db)

    # ② 更新 decision_log
    actual_impact_fen = int(actual_impact_yuan * 100)
    await _update_decision_log(decision_id, outcome, actual_impact_fen, executor_id, note, db)

    # ③ 写入正向/负向信号（影响健康分的信号响应维度）
    signal_id = await _write_outcome_signal(store_id, decision_id, outcome, actual_impact_yuan, db)

    # ④ 重算健康分
    health_after = await _get_current_score(store_id, db)
    delta = round(health_after - health_before, 1)

    logger.info(
        "feedback.submitted",
        decision_id=decision_id,
        store_id=store_id,
        outcome=outcome,
        actual_yuan=actual_impact_yuan,
        health_before=health_before,
        health_after=health_after,
        delta=delta,
    )

    return {
        "decision_id": decision_id,
        "outcome": outcome,
        "actual_impact_yuan": actual_impact_yuan,
        "health_before": health_before,
        "health_after": health_after,
        "health_delta": delta,
        "signal_id": signal_id,
    }


# ── 内部 helpers ──────────────────────────────────────────────────────────────


async def _get_current_score(store_id: str, db: AsyncSession) -> float:
    try:
        from .private_domain_health_service import calculate_health_score

        result = await calculate_health_score(store_id, db)
        return float(result.get("total_score", 0))
    except Exception as exc:
        logger.warning("feedback.score_failed", store_id=store_id, error=str(exc))
        return 0.0


async def _update_decision_log(
    decision_id: str,
    outcome: str,
    actual_impact_fen: int,
    executor_id: str,
    note: Optional[str],
    db: AsyncSession,
) -> None:
    now = datetime.datetime.utcnow()
    try:
        # 读取当前 trust_score 用于贝叶斯更新
        current_row = (
            await db.execute(
                text("SELECT trust_score, expected_result FROM decision_logs WHERE id = :did"),
                {"did": decision_id},
            )
        ).fetchone()

        current_trust = float(current_row[0]) if current_row and current_row[0] else 50.0
        expected_result = current_row[1] if current_row else None

        # 计算偏差（如果有预期值）
        deviation = 0.0
        if expected_result and isinstance(expected_result, dict):
            expected_fen = expected_result.get("impact_fen", 0)
            if expected_fen:
                deviation = abs(actual_impact_fen - expected_fen) / max(abs(expected_fen), 1) * 100

        # 贝叶斯信任分更新
        from src.services.effect_evaluator import _compute_trust_delta

        trust_delta = _compute_trust_delta(outcome, deviation, current_trust)
        new_trust = max(0.0, min(100.0, current_trust + trust_delta))

        await db.execute(
            text("""
                UPDATE decision_logs
                SET outcome       = :outcome,
                    actual_result = :actual,
                    result_deviation = :deviation,
                    trust_score   = :trust,
                    executed_at   = :now,
                    manager_id    = COALESCE(manager_id, :executor),
                    manager_feedback = COALESCE(manager_feedback || ' | ', '') || :note
                WHERE id = :did
            """),
            {
                "outcome": outcome,
                "actual": {"impact_fen": actual_impact_fen},
                "deviation": round(deviation, 2),
                "trust": round(new_trust, 2),
                "now": now,
                "executor": executor_id,
                "note": note or "",
                "did": decision_id,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("feedback.update_log_failed", decision_id=decision_id, error=str(exc))
        await db.rollback()


async def _write_outcome_signal(
    store_id: str,
    decision_id: str,
    outcome: str,
    actual_impact_yuan: float,
    db: AsyncSession,
) -> Optional[str]:
    """
    正向结果 → 写入 consumption 类型信号（提升信号响应维度分）
    负向结果 → 写入 churn_risk 类型信号（供后续改善参考）
    """
    signal_type = "consumption" if outcome == "success" else "churn_risk"
    severity = "low" if outcome == "success" else "medium"
    description = (
        f"决策执行{'成功' if outcome == 'success' else '失败'}：{decision_id}"
        f" | 实际影响 ¥{actual_impact_yuan:,.2f}"
        f" | outcome={outcome}"
    )
    sid = f"SIG_FB_{uuid.uuid4().hex[:8]}"
    try:
        await db.execute(
            text("""
                INSERT INTO private_domain_signals
                    (id, signal_id, store_id, customer_id,
                     signal_type, description, severity,
                     triggered_at, resolved_at, action_taken)
                VALUES
                    (gen_random_uuid(), :sid, :store_id, NULL,
                     :signal_type, :description, :severity,
                     :now, :resolved_at, :action)
                ON CONFLICT (signal_id) DO NOTHING
            """),
            {
                "sid": sid,
                "store_id": store_id,
                "signal_type": signal_type,
                "description": description,
                "severity": severity,
                "now": datetime.datetime.utcnow(),
                # 成功结果信号立即标为已解决（不拉低信号响应分）
                "resolved_at": datetime.datetime.utcnow() if outcome == "success" else None,
                "action": f"execution_feedback:{outcome}",
            },
        )
        await db.commit()
        return sid
    except Exception as exc:
        logger.warning("feedback.write_signal_failed", error=str(exc))
        await db.rollback()
        return None


# ── 历史反馈查询 ──────────────────────────────────────────────────────────────


async def get_feedback_history(
    store_id: str,
    db: AsyncSession,
    days: int = 30,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    查询门店近 N 天的决策执行反馈历史，含¥实际影响统计。
    """
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    try:
        rows = (
            await db.execute(
                text("""
                SELECT
                    id,
                    decision_type,
                    outcome,
                    actual_result,
                    executed_at,
                    manager_feedback
                FROM decision_logs
                WHERE store_id    = :s
                  AND outcome     IS NOT NULL
                  AND executed_at >= :since
                ORDER BY executed_at DESC
                LIMIT :limit
            """),
                {"s": store_id, "since": since, "limit": limit},
            )
        ).fetchall()
    except Exception as exc:
        logger.warning("feedback.history_failed", store_id=store_id, error=str(exc))
        rows = []

    items = []
    total_success_yuan = 0.0
    for r in rows:
        actual = r[3] or {}
        impact_yuan = round((actual.get("impact_fen", 0)) / 100, 2)
        if r[2] == "success":
            total_success_yuan += impact_yuan
        items.append(
            {
                "decision_id": str(r[0]),
                "decision_type": r[1],
                "outcome": r[2],
                "actual_impact_yuan": impact_yuan,
                "executed_at": str(r[4]) if r[4] else None,
                "note": r[5],
            }
        )

    success_count = sum(1 for i in items if i["outcome"] == "success")
    adoption_rate = round(success_count / len(items), 3) if items else 0.0

    return {
        "store_id": store_id,
        "days": days,
        "total_decisions": len(items),
        "success_count": success_count,
        "adoption_rate": adoption_rate,
        "total_success_yuan": round(total_success_yuan, 2),
        "items": items,
    }
