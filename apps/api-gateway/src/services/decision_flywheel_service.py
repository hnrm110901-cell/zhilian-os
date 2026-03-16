"""
决策飞轮服务 — Palantir闭环引擎

数据感知 → 模式识别 → 决策建议 → 一键执行 → 效果追踪 → 模型校准
    ↑                                                        ↓
    └────────── 校准数据注入未来AI prompt ──────────────────────┘

设计原则：
1. 每个方法必须有 rule-based fallback（LLM不可用时降级）
2. 金额单位：数据库存分(fen)，展示转元(/100)
3. SQL 用 text() + :param 绑定，绝不拼接字符串
4. 所有操作通过 structlog 记录（可审计）
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.llm import get_llm_client

logger = structlog.get_logger()

CALIBRATION_SYSTEM_PROMPT = """你是一位资深的餐饮连锁经营分析师，负责校准AI决策系统的预测准确性。
基于历史决策数据（预测值 vs 实际值），分析预测偏差模式并给出校准建议。

请严格按以下JSON格式回复，不要包含其他文字：
{
    "calibration_insights": "3-5句中文校准洞察，指出哪些类型预测偏高/偏低、可能原因",
    "adjustment_suggestions": [
        {"decision_type": "决策类型", "direction": "偏高|偏低|准确",
         "adjustment_pct": 10, "reason": "原因说明"}
    ],
    "overall_assessment": "整体校准评估（1-2句话）"
}

规则：
1. 基于实际数据分析，不要空泛
2. adjustment_pct: 建议调整百分比（正=上调，负=下调）
3. 关注餐饮行业特点：季节性、节假日效应、人员流动规律
4. 优先关注偏差最大的决策类型"""

_TYPE_LABELS = {
    "turnover_risk": "离职风险预测",
    "salary_adjust": "调薪建议",
    "schedule_optimize": "排班优化",
    "inventory_reorder": "补货建议",
    "waste_reduction": "损耗控制",
    "menu_optimize": "菜单优化",
}


class DecisionFlywheelService:
    """决策飞轮服务 — Palantir闭环引擎"""

    # ─── 1. 记录决策 ───────────────────────────────────────

    async def record_decision(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        decision_type: str,
        module: str,
        source: str,
        target_type: str,
        target_id: str,
        target_name: str,
        recommendation: str,
        predicted_impact_fen: int = None,
        confidence: float = None,
        risk_score: int = None,
        ai_analysis: str = None,
        context_snapshot: dict = None,
        model_version: str = None,
    ) -> str:
        """记录一条AI决策建议，返回decision_id"""
        decision_id = str(uuid.uuid4())
        now = datetime.utcnow()
        await db.execute(
            text("""
            INSERT INTO decision_records (
                id, brand_id, store_id, decision_type, module, source,
                target_type, target_id, target_name, recommendation,
                predicted_impact_fen, confidence, risk_score, ai_analysis,
                context_snapshot, model_version, status, created_at, updated_at
            ) VALUES (
                :id, :brand_id, :store_id, :decision_type, :module, :source,
                :target_type, :target_id, :target_name, :recommendation,
                :predicted_impact_fen, :confidence, :risk_score, :ai_analysis,
                :context_snapshot, :model_version, 'pending', :now, :now
            )
        """),
            {
                "id": decision_id,
                "brand_id": brand_id,
                "store_id": store_id,
                "decision_type": decision_type,
                "module": module,
                "source": source,
                "target_type": target_type,
                "target_id": target_id,
                "target_name": target_name,
                "recommendation": recommendation,
                "predicted_impact_fen": predicted_impact_fen,
                "confidence": confidence,
                "risk_score": risk_score,
                "ai_analysis": ai_analysis,
                "context_snapshot": (
                    json.dumps(context_snapshot, ensure_ascii=False, default=str) if context_snapshot else None
                ),
                "model_version": model_version,
                "now": now,
            },
        )
        await db.commit()
        logger.info(
            "decision_recorded", decision_id=decision_id, decision_type=decision_type, module=module, target_id=target_id
        )
        return decision_id

    # ─── 2. 记录用户响应 ──────────────────────────────────

    async def record_user_action(
        self,
        db: AsyncSession,
        decision_id: str,
        user_id: str,
        action: str,
        note: str = None,
        modified_action: str = None,
    ) -> dict:
        """记录用户对AI建议的响应 (accept/reject/modify/ignore/defer)"""
        now = datetime.utcnow()
        result = await db.execute(
            text("""
            UPDATE decision_records
            SET user_action = :action, user_id = :user_id,
                user_action_at = :now, user_note = :note,
                modified_action = :modified_action,
                status = CASE WHEN :action IN ('accept','modify') THEN 'actioned'
                              WHEN :action = 'defer' THEN 'pending'
                              ELSE 'closed' END,
                updated_at = :now
            WHERE id = :decision_id
            RETURNING id, decision_type, user_action, status
        """),
            {
                "decision_id": decision_id,
                "user_id": user_id,
                "action": action,
                "note": note,
                "modified_action": modified_action,
                "now": now,
            },
        )
        row = result.mappings().first()
        await db.commit()
        if not row:
            return {"error": "decision_not_found", "decision_id": decision_id}
        logger.info("decision_user_action", decision_id=decision_id, action=action)
        return {
            "decision_id": str(row["id"]),
            "decision_type": row["decision_type"],
            "user_action": row["user_action"],
            "status": row["status"],
            "actioned_at": now.isoformat(),
        }

    # ─── 3. 标记执行 ──────────────────────────────────────

    async def mark_executed(
        self,
        db: AsyncSession,
        decision_id: str,
        execution_detail: dict = None,
    ) -> dict:
        """标记决策已执行，进入效果追踪阶段"""
        now = datetime.utcnow()
        result = await db.execute(
            text("""
            UPDATE decision_records
            SET executed = true, executed_at = :now,
                execution_detail = :detail, status = 'tracking', updated_at = :now
            WHERE id = :decision_id AND user_action IN ('accept','modify')
            RETURNING id, decision_type, target_name, predicted_impact_fen
        """),
            {
                "decision_id": decision_id,
                "now": now,
                "detail": json.dumps(execution_detail, ensure_ascii=False, default=str) if execution_detail else None,
            },
        )
        row = result.mappings().first()
        await db.commit()
        if not row:
            return {"error": "decision_not_found_or_not_actioned"}
        logger.info("decision_executed", decision_id=decision_id)
        pred = row["predicted_impact_fen"]
        return {
            "decision_id": str(row["id"]),
            "decision_type": row["decision_type"],
            "target_name": row["target_name"],
            "executed_at": now.isoformat(),
            "status": "tracking",
            "predicted_impact_yuan": round(pred / 100, 2) if pred else None,
        }

    # ─── 4. 效果回顾（定时任务调用） ─────────────────────

    async def run_effect_reviews(self, db: AsyncSession) -> dict:
        """扫描 status='tracking' 的已执行决策，在30/60/90天回顾点测量效果"""
        now = datetime.utcnow()
        counts = {"30d": 0, "60d": 0, "90d": 0}
        errors: List[dict] = []
        windows = [
            ("30d", 30, "review_30d_at", "review_30d_result"),
            ("60d", 60, "review_60d_at", "review_60d_result"),
            ("90d", 90, "review_90d_at", "review_90d_result"),
        ]
        for label, days, at_col, res_col in windows:
            rows = await db.execute(
                text(f"""
                SELECT id, brand_id, store_id, decision_type, module,
                       target_type, target_id, target_name, recommendation,
                       predicted_impact_fen, confidence, executed_at,
                       context_snapshot, user_action, modified_action
                FROM decision_records
                WHERE status = 'tracking' AND executed = true
                  AND executed_at <= :cutoff AND {at_col} IS NULL
                ORDER BY executed_at ASC LIMIT 50
            """),
                {"cutoff": now - timedelta(days=days)},
            )
            for rec in [dict(r) for r in rows.mappings()]:
                try:
                    effect = await self._measure_effect(db, rec)
                    await db.execute(
                        text(f"""
                        UPDATE decision_records
                        SET {at_col} = :now, {res_col} = :result,
                            actual_impact_fen = COALESCE(:actual_fen, actual_impact_fen),
                            status = CASE WHEN :label = '90d' THEN 'reviewed' ELSE status END,
                            updated_at = :now
                        WHERE id = :id
                    """),
                        {
                            "now": now,
                            "id": rec["id"],
                            "label": label,
                            "result": json.dumps(effect, ensure_ascii=False, default=str),
                            "actual_fen": effect.get("actual_impact_fen"),
                        },
                    )
                    counts[label] += 1
                except Exception as e:
                    errors.append({"decision_id": str(rec["id"]), "window": label, "error": str(e)})
                    logger.warning("effect_review_failed", decision_id=rec["id"], error=str(e))
        await db.commit()
        logger.info("effect_reviews_done", counts=counts, errors=len(errors))
        return {"total_reviewed": sum(counts.values()), "reviewed_by_window": counts, "errors": errors}

    async def _measure_effect(self, db: AsyncSession, record: dict) -> dict:
        """根据决策类型测量实际效果"""
        dt = record.get("decision_type", "")
        tid, sid = record.get("target_id", ""), record.get("store_id", "")
        ex_at = record.get("executed_at")
        if dt == "turnover_risk":
            return await self._measure_turnover(db, tid, sid, ex_at, record)
        elif dt == "salary_adjust":
            return await self._measure_salary(db, tid, sid, ex_at, record)
        elif dt == "schedule_optimize":
            return await self._measure_schedule(db, sid, ex_at, record)
        return await self._measure_generic(db, tid, sid, record)

    async def _measure_turnover(self, db, emp_id, store_id, executed_at, record):
        """离职风险决策效果：留存、出勤变化、绩效变化"""
        emp = (
            (
                await db.execute(
                    text("SELECT is_active FROM employees WHERE id = :id AND store_id = :sid"), {"id": emp_id, "sid": store_id}
                )
            )
            .mappings()
            .first()
        )
        if not emp:
            return {"target_status": "not_found", "retained": None, "actual_impact_fen": None, "metric_changes": {}}
        retained = bool(emp["is_active"])
        # 出勤率：执行前30天 vs 后30天
        att = (
            (
                await db.execute(
                    text("""
            SELECT COUNT(*) FILTER (WHERE work_date < :ex AND status IN ('normal','late')) AS bef_ok,
                   COUNT(*) FILTER (WHERE work_date < :ex) AS bef_all,
                   COUNT(*) FILTER (WHERE work_date >= :ex AND status IN ('normal','late')) AS aft_ok,
                   COUNT(*) FILTER (WHERE work_date >= :ex) AS aft_all
            FROM attendance_logs
            WHERE employee_id = :eid AND store_id = :sid
              AND work_date BETWEEN :s AND :e
        """),
                    {
                        "eid": emp_id,
                        "sid": store_id,
                        "ex": executed_at,
                        "s": executed_at - timedelta(days=30),
                        "e": executed_at + timedelta(days=30),
                    },
                )
            )
            .mappings()
            .first()
        )
        bef_rate = round(int(att["bef_ok"]) / max(int(att["bef_all"]), 1) * 100, 1) if att else 0
        aft_rate = round(int(att["aft_ok"]) / max(int(att["aft_all"]), 1) * 100, 1) if att else 0
        # 绩效
        perfs = [
            dict(r)
            for r in (
                await db.execute(
                    text("""
            SELECT total_score FROM performance_reviews
            WHERE employee_id = :eid AND store_id = :sid AND status = 'completed'
            ORDER BY review_period DESC LIMIT 2
        """),
                    {"eid": emp_id, "sid": store_id},
                )
            ).mappings()
        ]
        perf_chg = round(float(perfs[0]["total_score"]) - float(perfs[1]["total_score"]), 1) if len(perfs) >= 2 else None
        # 实际影响
        pred = record.get("predicted_impact_fen") or 0
        actual = abs(pred) if (retained and pred > 0) else (-abs(pred) if pred else -1500000)
        return {
            "target_status": "active" if retained else "resigned",
            "retained": retained,
            "actual_impact_fen": actual,
            "metric_changes": {
                "attendance_before": bef_rate,
                "attendance_after": aft_rate,
                "attendance_change": round(aft_rate - bef_rate, 1),
                "performance_change": perf_chg,
            },
        }

    async def _measure_salary(self, db, emp_id, store_id, executed_at, record):
        """调薪决策效果：留存、薪资变化、绩效改善"""
        emp = (
            (
                await db.execute(
                    text("SELECT is_active FROM employees WHERE id = :id AND store_id = :sid"), {"id": emp_id, "sid": store_id}
                )
            )
            .mappings()
            .first()
        )
        retained = bool(emp["is_active"]) if emp else None
        pays = [
            dict(r)
            for r in (
                await db.execute(
                    text("""
            SELECT net_pay_fen FROM payroll_records
            WHERE employee_id = :eid ORDER BY pay_month DESC LIMIT 6
        """),
                    {"eid": emp_id},
                )
            ).mappings()
        ]
        sal_chg = int(pays[0]["net_pay_fen"]) - int(pays[-1]["net_pay_fen"]) if len(pays) >= 2 else None
        actual = None
        if sal_chg is not None:
            actual = (1500000 - abs(sal_chg * 12)) if retained else -abs(sal_chg * 12)
        return {
            "target_status": "active" if retained else "resigned",
            "retained": retained,
            "actual_impact_fen": actual,
            "metric_changes": {
                "salary_change_fen": sal_chg,
                "salary_change_yuan": round(sal_chg / 100, 2) if sal_chg else None,
            },
        }

    async def _measure_schedule(self, db, store_id, executed_at, record):
        """排班优化效果：加班变化、人力成本"""
        ot = (
            (
                await db.execute(
                    text("""
            SELECT COALESCE(SUM(overtime_hours) FILTER (WHERE work_date < :ex), 0) AS bef,
                   COALESCE(SUM(overtime_hours) FILTER (WHERE work_date >= :ex), 0) AS aft
            FROM attendance_logs WHERE store_id = :sid
              AND work_date BETWEEN :s AND :e
        """),
                    {
                        "sid": store_id,
                        "ex": executed_at,
                        "s": executed_at - timedelta(days=30),
                        "e": executed_at + timedelta(days=30),
                    },
                )
            )
            .mappings()
            .first()
        )
        ot_bef, ot_aft = (float(ot["bef"]), float(ot["aft"])) if ot else (0, 0)
        m1 = (executed_at.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        m2 = executed_at.strftime("%Y-%m")
        costs = {
            r["pay_month"]: int(r["t"])
            for r in (
                await db.execute(
                    text("""
            SELECT pay_month, COALESCE(SUM(net_pay_fen),0) AS t
            FROM payroll_records WHERE store_id = :sid AND pay_month IN (:m1,:m2)
            GROUP BY pay_month
        """),
                    {"sid": store_id, "m1": m1, "m2": m2},
                )
            ).mappings()
        }
        chg = costs.get(m2, 0) - costs.get(m1, 0)
        return {
            "target_status": "measured",
            "actual_impact_fen": -chg,
            "metric_changes": {
                "ot_before": ot_bef,
                "ot_after": ot_aft,
                "ot_reduction": round(ot_bef - ot_aft, 1),
                "cost_change_yuan": round(chg / 100, 2),
            },
        }

    async def _measure_generic(self, db, target_id, store_id, record):
        """通用效果度量"""
        active = None
        if record.get("target_type") == "employee":
            r = (
                (
                    await db.execute(
                        text("SELECT is_active FROM employees WHERE id = :id AND store_id = :sid"),
                        {"id": target_id, "sid": store_id},
                    )
                )
                .mappings()
                .first()
            )
            active = bool(r["is_active"]) if r else None
        status = "active" if active else ("inactive" if active is False else "unknown")
        return {"target_status": status, "actual_impact_fen": None, "metric_changes": {"note": "通用度量，具体效果需人工确认"}}

    # ─── 5. 校准分析 ──────────────────────────────────────

    async def calibrate(self, db: AsyncSession, store_id: str) -> dict:
        """对已完成效果回顾的决策进行校准：偏差计算 + 分类准确率 + AI洞察"""
        rows = [
            dict(r)
            for r in (
                await db.execute(
                    text("""
            SELECT id, decision_type, predicted_impact_fen, actual_impact_fen,
                   confidence, recommendation, user_action, executed_at
            FROM decision_records
            WHERE store_id = :sid AND status IN ('reviewed','calibrated')
              AND predicted_impact_fen IS NOT NULL AND actual_impact_fen IS NOT NULL
            ORDER BY executed_at DESC LIMIT 200
        """),
                    {"sid": store_id},
                )
            ).mappings()
        ]
        if not rows:
            return {
                "store_id": store_id,
                "total_decisions": 0,
                "accuracy_by_type": {},
                "calibration_insights": "数据不足，暂无法校准。",
                "total_predicted_yuan": 0,
                "total_actual_yuan": 0,
            }
        # 按类型分组
        groups: Dict[str, list] = {}
        for r in rows:
            p, a = int(r["predicted_impact_fen"]), int(r["actual_impact_fen"])
            dev = round((a - p) / abs(p) * 100, 1) if p else 0
            groups.setdefault(r["decision_type"], []).append({"predicted_fen": p, "actual_fen": a, "deviation_pct": dev})
        accuracy_by_type = {}
        tot_pred = tot_act = 0
        for dt, items in groups.items():
            devs = [abs(i["deviation_pct"]) for i in items]
            avg_dev = round(sum(devs) / len(devs), 1)
            acc = round(sum(1 for d in devs if d <= 20) / len(items) * 100, 1)
            avg_p = sum(i["predicted_fen"] for i in items) / len(items)
            avg_a = sum(i["actual_fen"] for i in items) / len(items)
            accuracy_by_type[dt] = {
                "count": len(items),
                "avg_deviation_pct": avg_dev,
                "accuracy_pct": acc,
                "direction": "偏高" if avg_p > avg_a else ("偏低" if avg_p < avg_a else "准确"),
                "avg_predicted_yuan": round(avg_p / 100, 2),
                "avg_actual_yuan": round(avg_a / 100, 2),
            }
            tot_pred += sum(i["predicted_fen"] for i in items)
            tot_act += sum(i["actual_fen"] for i in items)
        # AI 校准洞察
        insights = await self._generate_calibration_insights(accuracy_by_type, rows)
        # 标记已校准
        for r in rows:
            await db.execute(
                text("""
                UPDATE decision_records SET status = 'calibrated', updated_at = :now
                WHERE id = :id AND status = 'reviewed'
            """),
                {"id": r["id"], "now": datetime.utcnow()},
            )
        await db.commit()
        logger.info("calibration_done", store_id=store_id, total=len(rows))
        return {
            "store_id": store_id,
            "total_decisions": len(rows),
            "accuracy_by_type": accuracy_by_type,
            "calibration_insights": insights,
            "total_predicted_yuan": round(tot_pred / 100, 2),
            "total_actual_yuan": round(tot_act / 100, 2),
        }

    async def _generate_calibration_insights(self, accuracy_by_type, records) -> str:
        """调用Claude生成校准洞察，LLM不可用时降级到规则引擎"""
        if not getattr(settings, "LLM_ENABLED", False):
            return self._rule_calibration(accuracy_by_type)
        try:
            ctx = {
                "accuracy_by_type": accuracy_by_type,
                "sample_size": len(records),
                "examples": [
                    {
                        "type": r["decision_type"],
                        "predicted_yuan": round(int(r["predicted_impact_fen"]) / 100, 2),
                        "actual_yuan": round(int(r["actual_impact_fen"]) / 100, 2),
                        "action": r.get("user_action"),
                    }
                    for r in records[:10]
                ],
            }
            resp = await get_llm_client().generate(
                prompt=f"请分析以下AI决策系统的校准数据：\n{json.dumps(ctx, ensure_ascii=False, default=str)}",
                system_prompt=CALIBRATION_SYSTEM_PROMPT,
                max_tokens=800,
                temperature=0.3,
            )
            parsed = self._parse_llm_json(resp)
            parts = [parsed.get("calibration_insights", ""), parsed.get("overall_assessment", "")]
            for s in parsed.get("adjustment_suggestions", []):
                parts.append(
                    f"[{s.get('decision_type')}] {s.get('direction')}，"
                    f"建议调整{s.get('adjustment_pct', 0)}%：{s.get('reason', '')}"
                )
            return "\n".join(p for p in parts if p)
        except Exception as e:
            logger.warning("calibration_llm_failed", error=str(e))
            return self._rule_calibration(accuracy_by_type)

    def _rule_calibration(self, accuracy_by_type: dict) -> str:
        """规则引擎校准洞察（LLM降级方案）"""
        if not accuracy_by_type:
            return "数据不足，暂无法生成校准洞察。"
        parts = []
        for dt, s in accuracy_by_type.items():
            lbl = _TYPE_LABELS.get(dt, dt)
            acc = s["accuracy_pct"]
            assess = (
                "预测准确，可继续信赖"
                if acc >= 80
                else (
                    f"预测{s['direction']}，平均偏差{s['avg_deviation_pct']}%，建议适度校准"
                    if acc >= 60
                    else f"预测{s['direction']}偏差较大（{s['avg_deviation_pct']}%），建议人工复核"
                )
            )
            parts.append(f"【{lbl}】{s['count']}次决策，准确率{acc}%，{assess}。")
        weighted = sum(s["accuracy_pct"] * s["count"] for s in accuracy_by_type.values()) / max(
            sum(s["count"] for s in accuracy_by_type.values()), 1
        )
        parts.append(f"整体加权准确率：{round(weighted, 1)}%（规则引擎分析）")
        return "\n".join(parts)

    # ─── 6. 上下文注入 ────────────────────────────────────

    async def get_calibration_context(self, db: AsyncSession, store_id: str, decision_type: str) -> str:
        """生成校准上下文字符串，注入到未来的AI prompt中"""
        stats = (
            (
                await db.execute(
                    text("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE actual_impact_fen IS NOT NULL) AS reviewed,
                   COUNT(*) FILTER (WHERE user_action = 'accept') AS accepted,
                   AVG(predicted_impact_fen) FILTER (WHERE predicted_impact_fen IS NOT NULL) AS avg_pred,
                   AVG(actual_impact_fen) FILTER (WHERE actual_impact_fen IS NOT NULL) AS avg_act
            FROM decision_records
            WHERE store_id = :sid AND decision_type = :dt
        """),
                    {"sid": store_id, "dt": decision_type},
                )
            )
            .mappings()
            .first()
        )
        total = int(stats["total"]) if stats and stats["total"] else 0
        if total == 0:
            return ""
        reviewed = int(stats["reviewed"] or 0)
        accepted = int(stats["accepted"] or 0)
        acc_rate = round(accepted / max(total, 1) * 100, 1)
        avg_p = float(stats["avg_pred"]) if stats["avg_pred"] else 0
        avg_a = float(stats["avg_act"]) if stats["avg_act"] else 0
        dev_pct = round((avg_a - avg_p) / abs(avg_p) * 100, 1) if avg_p and reviewed else 0
        direction = "偏高" if dev_pct < 0 else ("偏低" if dev_pct > 0 else "准确")
        acc_pct = max(0, round(100 - abs(dev_pct), 1))
        lbl = _TYPE_LABELS.get(decision_type, decision_type)
        parts = [f"[历史校准] 该门店{lbl}共{total}次，用户采纳率{acc_rate}%。"]
        if reviewed:
            parts.append(f"已回顾{reviewed}次，准确率约{acc_pct}%，偏差{abs(dev_pct)}%（{direction}）。")
            if abs(dev_pct) > 15:
                adj = "下调" if dev_pct < 0 else "上调"
                parts.append(f"建议{adj}预测值{min(abs(dev_pct), 30):.0f}%。")
        # 近期方案效果
        recents = [
            dict(r)
            for r in (
                await db.execute(
                    text("""
            SELECT recommendation, review_30d_result FROM decision_records
            WHERE store_id = :sid AND decision_type = :dt
              AND user_action IN ('accept','modify') AND review_30d_result IS NOT NULL
            ORDER BY executed_at DESC LIMIT 5
        """),
                    {"sid": store_id, "dt": decision_type},
                )
            ).mappings()
        ]
        effects: Dict[str, Dict] = {}
        for row in recents:
            r30 = row.get("review_30d_result")
            if isinstance(r30, str):
                try:
                    r30 = json.loads(r30)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(r30, dict) or "retained" not in r30:
                continue
            key = (row["recommendation"] or "")[:20]
            eff = effects.setdefault(key, {"total": 0, "ok": 0})
            eff["total"] += 1
            if r30["retained"]:
                eff["ok"] += 1
        if effects:
            ef_parts = [f"「{k}」成功率{round(v['ok']/max(v['total'],1)*100)}%" for k, v in effects.items()]
            parts.append("近期方案效果：" + "，".join(ef_parts) + "。")
        return " ".join(parts)

    # ─── 7. 飞轮看板数据 ──────────────────────────────────

    async def get_flywheel_dashboard(self, db: AsyncSession, store_id: str, brand_id: str = None) -> dict:
        """飞轮运转看板数据"""
        wh = "WHERE store_id = :store_id"
        p: Dict[str, Any] = {"store_id": store_id}
        if brand_id:
            wh += " AND brand_id = :brand_id"
            p["brand_id"] = brand_id
        # 概览
        ov = (
            (
                await db.execute(
                    text(f"""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE user_action='accept') AS accepted,
                   COUNT(*) FILTER (WHERE user_action='modify') AS modified,
                   COUNT(*) FILTER (WHERE user_action IS NOT NULL) AS responded
            FROM decision_records {wh}
        """),
                    p,
                )
            )
            .mappings()
            .first()
        )
        total = int(ov["total"]) if ov else 0
        responded = int(ov["responded"]) if ov else 0
        acc_rate = (
            round((int(ov["accepted"] or 0) + int(ov["modified"] or 0)) / max(responded, 1) * 100, 1) if responded else 0
        )
        # 按类型
        by_type = [
            {
                "type": r["decision_type"],
                "count": int(r["cnt"]),
                "acceptance_rate": round(int(r["adopted"]) / max(int(r["resp"]), 1) * 100, 1) if int(r["resp"]) else 0,
            }
            for r in (
                await db.execute(
                    text(f"""
            SELECT decision_type, COUNT(*) AS cnt,
                   COUNT(*) FILTER (WHERE user_action IN ('accept','modify')) AS adopted,
                   COUNT(*) FILTER (WHERE user_action IS NOT NULL) AS resp
            FROM decision_records {wh} GROUP BY decision_type ORDER BY cnt DESC
        """),
                    p,
                )
            ).mappings()
        ]
        # 按状态
        by_status = {"pending": 0, "actioned": 0, "tracking": 0, "reviewed": 0, "calibrated": 0, "closed": 0}
        for r in (
            await db.execute(
                text(f"""
            SELECT status, COUNT(*) AS c FROM decision_records {wh} GROUP BY status
        """),
                p,
            )
        ).mappings():
            by_status[r["status"]] = int(r["c"])
        # 最近10条
        recent = [
            {
                "id": str(r["id"]),
                "decision_type": r["decision_type"],
                "target_name": r["target_name"],
                "recommendation": (r["recommendation"] or "")[:80],
                "predicted_impact_yuan": round(int(r["predicted_impact_fen"]) / 100, 2) if r["predicted_impact_fen"] else None,
                "user_action": r["user_action"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in (
                await db.execute(
                    text(f"""
            SELECT id, decision_type, target_name, recommendation,
                   predicted_impact_fen, user_action, status, created_at
            FROM decision_records {wh} ORDER BY created_at DESC LIMIT 10
        """),
                    p,
                )
            ).mappings()
        ]
        # 校准汇总
        cal = (
            (
                await db.execute(
                    text(f"""
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(predicted_impact_fen),0) AS tp,
                   COALESCE(SUM(actual_impact_fen),0) AS ta,
                   AVG(CASE WHEN predicted_impact_fen!=0
                       THEN ABS((actual_impact_fen-predicted_impact_fen)::float
                            / ABS(predicted_impact_fen)*100) END) AS avg_dev
            FROM decision_records {wh}
              AND actual_impact_fen IS NOT NULL AND predicted_impact_fen IS NOT NULL
        """),
                    p,
                )
            )
            .mappings()
            .first()
        )
        avg_d = round(float(cal["avg_dev"]), 1) if cal and cal["avg_dev"] else 0
        cal_summary = {
            "calibrated_count": int(cal["cnt"]) if cal else 0,
            "accuracy_pct": max(0, round(100 - avg_d, 1)),
            "total_saved_yuan": round(max(int(cal["ta"]) if cal else 0, 0) / 100, 2),
            "avg_deviation_pct": avg_d,
        }
        health = self._flywheel_health(total, acc_rate, cal_summary["calibrated_count"], cal_summary["accuracy_pct"])
        return {
            "store_id": store_id,
            "total_decisions": total,
            "acceptance_rate": acc_rate,
            "decisions_by_type": by_type,
            "decisions_by_status": by_status,
            "recent_decisions": recent,
            "calibration_summary": cal_summary,
            "flywheel_health": health,
        }

    @staticmethod
    def _flywheel_health(total, acc_rate, cal_count, acc_pct) -> str:
        """飞轮健康度: strong / growing / cold"""
        if total < 10:
            return "cold"
        if total < 30 or acc_rate < 30:
            return "growing" if acc_rate >= 20 else "cold"
        if cal_count >= 5 and acc_pct >= 70 and acc_rate >= 50:
            return "strong"
        return "growing" if (acc_rate >= 40 or cal_count >= 3) else "cold"

    @staticmethod
    def _parse_llm_json(response: str) -> Dict[str, Any]:
        """解析LLM返回的JSON，处理```json包裹"""
        t = response.strip()
        if t.startswith("```"):
            lines = t.split("\n")
            s = 1 if lines[0].startswith("```") else 0
            e = -1 if lines[-1].strip() == "```" else len(lines)
            t = "\n".join(lines[s:e]).strip()
        return json.loads(t)
