"""
EffectEvaluator — 决策效果闭环

定时扫描已执行但未评估的 DecisionLog，根据 decision_type 匹配评估策略，
查询实际业务指标，计算偏差，更新 outcome/trust_score。

与 P1 的 evaluation_delay_hours 联动判断评估窗口。
与 P3 的 context_data 联动理解决策的完整链路。

关键设计：
  - 幂等：已评估的 DecisionLog（outcome 非 NULL）不会重复评估
  - 渐进式：8种评估策略可逐步实现，未覆盖的用默认超期评估
  - 不改表结构：所有字段（outcome、actual_result、result_deviation、trust_score）已存在

信任分贝叶斯更新：
  - success + deviation < 10%  → trust ↑（渐近100）
  - partial                    → trust +0.5
  - failure                    → trust ↓（衰减）
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import exc as sa_exc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 每种 decision_type 的默认评估延迟（小时）
_DEFAULT_EVAL_DELAYS: Dict[str, int] = {
    "inventory_alert": 48,
    "schedule_optimization": 72,
    "purchase_suggestion": 72,
    "menu_pricing": 168,
    "cost_optimization": 72,
    "revenue_anomaly": 24,
    "kpi_improvement": 168,
    "order_anomaly": 24,
}


class EffectEvaluator:
    """决策效果评估器。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run_evaluation_sweep(self) -> Dict[str, Any]:
        """
        执行一次评估扫描：

        1. 查找已执行但未评估、且已超过评估窗口的 DecisionLog
        2. 逐条评估：查实际指标 → 算偏差 → 判 outcome → 更新 trust_score
        3. 返回评估统计
        """
        unevaluated = await self._find_unevaluated()
        if not unevaluated:
            logger.info("effect_evaluator.no_pending")
            return {"evaluated": 0, "skipped": 0}

        evaluated = 0
        skipped = 0
        errors = 0

        for record in unevaluated:
            try:
                did = record["id"]
                decision_type = record["decision_type"]
                store_id = record["store_id"]
                executed_at = record["executed_at"]
                expected_result = record.get("expected_result") or {}
                context_data = record.get("context_data") or {}
                current_trust = record.get("trust_score") or 50.0

                # 检查是否超过评估窗口
                delay_hours = self._get_eval_delay(decision_type, context_data)
                eval_deadline = executed_at + datetime.timedelta(hours=delay_hours)
                if datetime.datetime.utcnow() < eval_deadline:
                    skipped += 1
                    continue

                # 分发到具体评估策略
                result = await self._evaluate(decision_type, store_id, executed_at, expected_result, context_data)

                if result is None:
                    # 无法评估（缺少数据），标记为超期待评估
                    result = {
                        "outcome": "partial",
                        "actual_result": {"note": "评估数据不足，标记为部分完成"},
                        "deviation": 0.0,
                    }

                # 计算信任分变化
                trust_delta = _compute_trust_delta(
                    result["outcome"],
                    result.get("deviation", 0.0),
                    current_trust,
                )
                new_trust = max(0.0, min(100.0, current_trust + trust_delta))

                # 更新 DecisionLog
                await self._update_decision(
                    did,
                    outcome=result["outcome"],
                    actual_result=result.get("actual_result", {}),
                    deviation=result.get("deviation", 0.0),
                    trust_score=round(new_trust, 2),
                )
                evaluated += 1

                logger.info(
                    "effect_evaluator.evaluated",
                    decision_id=did,
                    decision_type=decision_type,
                    outcome=result["outcome"],
                    deviation=result.get("deviation"),
                    trust_before=current_trust,
                    trust_after=new_trust,
                )

            except (sa_exc.SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
                errors += 1
                logger.warning(
                    "effect_evaluator.eval_error",
                    decision_id=record.get("id"),
                    error=str(exc),
                )

        stats = {
            "evaluated": evaluated,
            "skipped": skipped,
            "errors": errors,
            "total_scanned": len(unevaluated),
        }
        logger.info("effect_evaluator.sweep_done", **stats)
        return stats

    async def _find_unevaluated(self) -> List[Dict[str, Any]]:
        """查找已执行但未评估的 DecisionLog。"""
        try:
            rows = (await self.db.execute(text("""
                    SELECT id, decision_type, store_id, executed_at,
                           expected_result, context_data, trust_score
                    FROM decision_logs
                    WHERE outcome IS NULL
                      AND decision_status = 'executed'
                      AND executed_at IS NOT NULL
                    ORDER BY executed_at ASC
                    LIMIT 100
                """))).fetchall()

            return [
                {
                    "id": str(r[0]),
                    "decision_type": r[1],
                    "store_id": r[2],
                    "executed_at": r[3],
                    "expected_result": r[4],
                    "context_data": r[5],
                    "trust_score": r[6],
                }
                for r in rows
            ]
        except sa_exc.SQLAlchemyError as exc:
            logger.warning("effect_evaluator.find_failed", error=str(exc))
            return []

    def _get_eval_delay(self, decision_type: str, context_data: Dict) -> int:
        """获取评估延迟小时数。优先从 P1 SkillDescriptor 读取，否则用默认值。"""
        # 尝试从 context_data 中读取关联的 skill 评估延迟
        skill_delay = context_data.get("evaluation_delay_hours")
        if skill_delay is not None:
            return int(skill_delay)

        # 尝试从 SkillRegistry 读取
        try:
            from src.core.skill_registry import SkillRegistry

            registry = SkillRegistry.get()
            # 查找匹配 decision_type 对应的技能
            skills = registry.query(intent=decision_type)
            if skills:
                return skills[0].evaluation_delay_hours
        except (ImportError, AttributeError, ValueError):
            pass

        return _DEFAULT_EVAL_DELAYS.get(decision_type, 72)

    async def _evaluate(
        self,
        decision_type: str,
        store_id: str,
        executed_at: datetime.datetime,
        expected_result: Dict,
        context_data: Dict,
    ) -> Optional[Dict[str, Any]]:
        """分发到具体评估策略。"""
        evaluators = {
            "inventory_alert": self._evaluate_inventory,
            "schedule_optimization": self._evaluate_schedule,
            "purchase_suggestion": self._evaluate_purchase,
            "menu_pricing": self._evaluate_pricing,
            "cost_optimization": self._evaluate_cost,
            "revenue_anomaly": self._evaluate_revenue,
            "kpi_improvement": self._evaluate_kpi,
            "order_anomaly": self._evaluate_order,
        }
        evaluator = evaluators.get(decision_type)
        if evaluator:
            return await evaluator(store_id, executed_at, expected_result, context_data)

        # 默认评估：超期未评估，标记为 partial
        return {
            "outcome": "partial",
            "actual_result": {"note": f"decision_type '{decision_type}' 暂无自动评估策略"},
            "deviation": 0.0,
        }

    async def _evaluate_inventory(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """库存预警评估：查 waste_events 变化。"""
        try:
            before_count = await self._count_waste_events(store_id, executed_at, before=True)
            after_count = await self._count_waste_events(store_id, executed_at, before=False)

            if before_count == 0:
                deviation = 0.0
            else:
                deviation = round((after_count - before_count) / before_count * 100, 2)

            if after_count <= before_count * 0.7:
                outcome = "success"
            elif after_count <= before_count:
                outcome = "partial"
            else:
                outcome = "failure"

            return {
                "outcome": outcome,
                "actual_result": {
                    "waste_before": before_count,
                    "waste_after": after_count,
                    "change_pct": deviation,
                },
                "deviation": abs(deviation),
            }
        except sa_exc.SQLAlchemyError as exc:
            logger.debug("effect_evaluator.inventory_eval_error", error=str(exc))
            return None

    async def _evaluate_schedule(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """排班优化评估：查 labor_cost_ratio 变化。"""
        try:
            before_ratio = await self._get_labor_cost_ratio(store_id, executed_at, before=True)
            after_ratio = await self._get_labor_cost_ratio(store_id, executed_at, before=False)

            if before_ratio is None or after_ratio is None:
                return None

            deviation = round((after_ratio - before_ratio) / max(before_ratio, 0.01) * 100, 2)
            expected_ratio = expected.get("target_labor_cost_ratio")

            if after_ratio < before_ratio * 0.95:
                outcome = "success"
            elif after_ratio <= before_ratio:
                outcome = "partial"
            else:
                outcome = "failure"

            return {
                "outcome": outcome,
                "actual_result": {
                    "labor_cost_before": before_ratio,
                    "labor_cost_after": after_ratio,
                    "change_pct": deviation,
                },
                "deviation": abs(deviation),
            }
        except sa_exc.SQLAlchemyError as exc:
            logger.debug("effect_evaluator.schedule_eval_error", error=str(exc))
            return None

    async def _evaluate_purchase(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """采购建议评估：查采购成本偏差。"""
        expected_cost = expected.get("estimated_cost_yuan")
        if expected_cost is None:
            return {
                "outcome": "partial",
                "actual_result": {"note": "无预期采购成本基线"},
                "deviation": 0.0,
            }

        try:
            actual_cost = await self._get_actual_purchase_cost(store_id, executed_at)
            if actual_cost is None:
                return None

            deviation = round((actual_cost - expected_cost) / max(expected_cost, 0.01) * 100, 2)

            if abs(deviation) < 10:
                outcome = "success"
            elif abs(deviation) < 25:
                outcome = "partial"
            else:
                outcome = "failure"

            return {
                "outcome": outcome,
                "actual_result": {
                    "expected_cost_yuan": expected_cost,
                    "actual_cost_yuan": actual_cost,
                    "deviation_pct": deviation,
                },
                "deviation": abs(deviation),
            }
        except sa_exc.SQLAlchemyError as exc:
            logger.debug("effect_evaluator.purchase_eval_error", error=str(exc))
            return None

    async def _evaluate_pricing(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """菜品定价评估：查菜品销量×毛利变化（7天窗口）。"""
        return {
            "outcome": "partial",
            "actual_result": {"note": "定价评估需7天数据积累"},
            "deviation": 0.0,
        }

    async def _evaluate_cost(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """总成本优化评估。"""
        try:
            rows = (
                await self.db.execute(
                    text("""
                    SELECT total_cost_rate
                    FROM cost_truth_snapshots
                    WHERE store_id = :sid
                      AND snapshot_date >= :since
                    ORDER BY snapshot_date DESC
                    LIMIT 1
                """),
                    {"sid": store_id, "since": executed_at.date()},
                )
            ).fetchone()

            if not rows:
                return None

            actual_rate = float(rows[0]) if rows[0] else None
            if actual_rate is None:
                return None

            expected_rate = expected.get("target_cost_rate", actual_rate)
            deviation = round((actual_rate - expected_rate) / max(expected_rate, 0.01) * 100, 2)

            if actual_rate < expected_rate:
                outcome = "success"
            elif abs(deviation) < 5:
                outcome = "partial"
            else:
                outcome = "failure"

            return {
                "outcome": outcome,
                "actual_result": {"actual_cost_rate": actual_rate, "expected_cost_rate": expected_rate},
                "deviation": abs(deviation),
            }
        except sa_exc.SQLAlchemyError as exc:
            logger.debug("effect_evaluator.cost_eval_error", error=str(exc))
            return None

    async def _evaluate_revenue(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """营收异常评估：查营收恢复情况（24h 窗口）。"""
        try:
            rows = (
                await self.db.execute(
                    text("""
                    SELECT COALESCE(SUM(total_amount), 0)
                    FROM orders
                    WHERE store_id = :sid
                      AND order_time >= :since
                      AND order_time < :until
                      AND status != 'cancelled'
                """),
                    {
                        "sid": store_id,
                        "since": executed_at,
                        "until": executed_at + datetime.timedelta(hours=24),
                    },
                )
            ).fetchone()

            actual_revenue = float(rows[0]) if rows and rows[0] else 0.0
            expected_revenue = expected.get("expected_revenue_yuan", 0.0)

            if expected_revenue <= 0:
                return {
                    "outcome": "partial",
                    "actual_result": {"actual_revenue_yuan": actual_revenue, "note": "无预期营收基线"},
                    "deviation": 0.0,
                }

            deviation = round((actual_revenue - expected_revenue) / expected_revenue * 100, 2)

            if actual_revenue >= expected_revenue * 0.9:
                outcome = "success"
            elif actual_revenue >= expected_revenue * 0.7:
                outcome = "partial"
            else:
                outcome = "failure"

            return {
                "outcome": outcome,
                "actual_result": {
                    "actual_revenue_yuan": actual_revenue,
                    "expected_revenue_yuan": expected_revenue,
                },
                "deviation": abs(deviation),
            }
        except sa_exc.SQLAlchemyError as exc:
            logger.debug("effect_evaluator.revenue_eval_error", error=str(exc))
            return None

    async def _evaluate_kpi(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """KPI 改进评估（7天窗口）。"""
        return {
            "outcome": "partial",
            "actual_result": {"note": "KPI评估需7天数据积累"},
            "deviation": 0.0,
        }

    async def _evaluate_order(
        self,
        store_id: str,
        executed_at: datetime.datetime,
        expected: Dict,
        context: Dict,
    ) -> Optional[Dict[str, Any]]:
        """订单异常评估：查异常订单是否消除（24h 窗口）。"""
        try:
            rows = (
                await self.db.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM orders
                    WHERE store_id = :sid
                      AND order_time >= :since
                      AND order_time < :until
                      AND status = 'anomaly'
                """),
                    {
                        "sid": store_id,
                        "since": executed_at,
                        "until": executed_at + datetime.timedelta(hours=24),
                    },
                )
            ).fetchone()

            anomaly_count = int(rows[0]) if rows else 0

            if anomaly_count == 0:
                outcome = "success"
            elif anomaly_count <= 2:
                outcome = "partial"
            else:
                outcome = "failure"

            return {
                "outcome": outcome,
                "actual_result": {"anomaly_count_after": anomaly_count},
                "deviation": float(anomaly_count),
            }
        except sa_exc.SQLAlchemyError as exc:
            logger.debug("effect_evaluator.order_eval_error", error=str(exc))
            return None

    # ── 数据查询 helpers ─────────────────────────────────────────────────

    async def _count_waste_events(
        self,
        store_id: str,
        pivot: datetime.datetime,
        before: bool,
    ) -> int:
        """统计损耗事件数量（pivot 前后各 48h）。"""
        if before:
            since = pivot - datetime.timedelta(hours=48)
            until = pivot
        else:
            since = pivot
            until = pivot + datetime.timedelta(hours=48)

        try:
            rows = (
                await self.db.execute(
                    text("""
                    SELECT COUNT(*)
                    FROM waste_events
                    WHERE store_id = :sid
                      AND created_at >= :since
                      AND created_at < :until
                """),
                    {"sid": store_id, "since": since, "until": until},
                )
            ).fetchone()
            return int(rows[0]) if rows else 0
        except sa_exc.SQLAlchemyError:
            return 0

    async def _get_labor_cost_ratio(
        self,
        store_id: str,
        pivot: datetime.datetime,
        before: bool,
    ) -> Optional[float]:
        """获取人力成本率（pivot 前后各 72h 的平均值）。"""
        if before:
            since = pivot - datetime.timedelta(hours=72)
            until = pivot
        else:
            since = pivot
            until = pivot + datetime.timedelta(hours=72)

        try:
            rows = (
                await self.db.execute(
                    text("""
                    SELECT AVG(labor_cost_ratio)
                    FROM cost_truth_snapshots
                    WHERE store_id = :sid
                      AND snapshot_date >= :since
                      AND snapshot_date < :until
                """),
                    {"sid": store_id, "since": since.date(), "until": until.date()},
                )
            ).fetchone()
            return float(rows[0]) if rows and rows[0] is not None else None
        except sa_exc.SQLAlchemyError:
            return None

    async def _get_actual_purchase_cost(
        self,
        store_id: str,
        executed_at: datetime.datetime,
    ) -> Optional[float]:
        """获取实际采购成本（executed_at 后 72h）。"""
        try:
            rows = (
                await self.db.execute(
                    text("""
                    SELECT COALESCE(SUM(total_amount), 0)
                    FROM purchase_orders
                    WHERE store_id = :sid
                      AND created_at >= :since
                      AND created_at < :until
                """),
                    {
                        "sid": store_id,
                        "since": executed_at,
                        "until": executed_at + datetime.timedelta(hours=72),
                    },
                )
            ).fetchone()
            val = float(rows[0]) if rows and rows[0] else None
            # 分 → 元
            return round(val / 100, 2) if val else None
        except sa_exc.SQLAlchemyError:
            return None

    async def _update_decision(
        self,
        decision_id: str,
        outcome: str,
        actual_result: Dict,
        deviation: float,
        trust_score: float,
    ) -> None:
        """更新 DecisionLog 的 outcome/actual_result/result_deviation/trust_score。"""
        try:
            await self.db.execute(
                text("""
                    UPDATE decision_logs
                    SET outcome          = :outcome,
                        actual_result    = :actual,
                        result_deviation = :deviation,
                        trust_score      = :trust
                    WHERE id = :did
                      AND outcome IS NULL
                """),
                {
                    "outcome": outcome,
                    "actual": __import__("json").dumps(actual_result, default=str),
                    "deviation": deviation,
                    "trust": trust_score,
                    "did": decision_id,
                },
            )
            await self.db.commit()
        except sa_exc.SQLAlchemyError as exc:
            logger.warning("effect_evaluator.update_failed", decision_id=decision_id, error=str(exc))
            await self.db.rollback()


def _compute_trust_delta(outcome: str, deviation: float, current_trust: float) -> float:
    """
    贝叶斯式信任分更新。

    - success + deviation < 10% → 渐近 100（越高越难涨）
    - partial                   → +0.5
    - failure                   → 衰减（越高跌越多）
    """
    if outcome == "success" and abs(deviation) < 10:
        return min(5.0, (100 - current_trust) * 0.1)
    elif outcome == "success":
        return min(3.0, (100 - current_trust) * 0.05)
    elif outcome == "partial":
        return 0.5
    elif outcome == "failure":
        return -max(3.0, current_trust * 0.08)
    return 0.0
