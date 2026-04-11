"""AgentEventProcessor — Agent间事件联动处理器

当一个Agent发现异常时，通知相关Agent做出响应。
支持规则引擎驱动的跨Agent协作：
  - 异常检测 → 多Agent响应生成
  - 目标偏差 → 自动预警事件创建
  - 跨Agent行动建议 → 可执行action列表
"""

from __future__ import annotations

import json
import uuid
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 响应规则引擎：event_type + metric → 各Agent的响应模板 ────────────────────
RESPONSE_RULES: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "material_cost_ratio": [
        {
            "agent": "financial",
            "action": "重新估算本月P&L预测，计算食材超支对利润的影响",
            "response_type": "pnl_reforecast",
        },
        {
            "agent": "supply_chain",
            "action": "检查最近3天的采购单价变化，标记异常供应商",
            "response_type": "procurement_audit",
        },
    ],
    "revenue": [
        {
            "agent": "financial",
            "action": "下调月度营收预测",
            "response_type": "revenue_reforecast",
        },
        {
            "agent": "customer",
            "action": "检查客流和客单价哪个在下降",
            "response_type": "traffic_analysis",
        },
    ],
    "waste": [
        {
            "agent": "supply_chain",
            "action": "标记高损耗食材TOP5",
            "response_type": "waste_top5",
        },
        {
            "agent": "ops",
            "action": "检查是否有过期/临期食材未处理",
            "response_type": "expiry_check",
        },
    ],
}

# ── 跨Agent行动建议模板 ────────────────────────────────────────────────────
CROSS_AGENT_ACTIONS: Dict[str, List[Dict[str, Any]]] = {
    "material_cost_ratio": [
        {
            "agent": "supply_chain",
            "action": "检查近3天采购单价变化",
            "urgency": "high",
            "confidence": 0.85,
        },
        {
            "agent": "ops",
            "action": "排查TOP3损耗品类",
            "urgency": "medium",
            "confidence": 0.75,
        },
        {
            "agent": "financial",
            "action": "更新月度P&L预测",
            "urgency": "high",
            "confidence": 0.90,
        },
    ],
    "revenue": [
        {
            "agent": "customer",
            "action": "分析客流与客单价趋势，定位下降原因",
            "urgency": "high",
            "confidence": 0.80,
        },
        {
            "agent": "marketing",
            "action": "评估近期促销活动ROI，考虑紧急引流方案",
            "urgency": "high",
            "confidence": 0.70,
        },
        {
            "agent": "financial",
            "action": "下调月度营收预测并测算利润影响",
            "urgency": "high",
            "confidence": 0.85,
        },
    ],
    "waste": [
        {
            "agent": "supply_chain",
            "action": "标记高损耗食材TOP5并检查供应商批次质量",
            "urgency": "high",
            "confidence": 0.85,
        },
        {
            "agent": "ops",
            "action": "检查过期/临期食材未处理情况，核查冷链记录",
            "urgency": "high",
            "confidence": 0.80,
        },
        {
            "agent": "kitchen",
            "action": "审查备料计划精准度，减少过量备料",
            "urgency": "medium",
            "confidence": 0.70,
        },
    ],
}

# ── 目标偏差阈值 ────────────────────────────────────────────────────────────
DEVIATION_ON_TRACK = 0.90   # >= 90%视为正轨
DEVIATION_AT_RISK = 0.70    # 70%-90%视为有风险


class AgentEventProcessor:
    """Agent间事件联动处理器 — 规则驱动的跨Agent协作引擎"""

    # ─────────────────────────────────────────────────────────────────────
    # 方法1: 批量处理待处理事件
    # ─────────────────────────────────────────────────────────────────────
    async def process_pending_events(
        self,
        session: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """查询并处理所有待处理的agent事件

        Returns:
            {"processed_count": N, "responses": [...]}
        """
        logger.info("agent_event_processor.process_pending.start", brand_id=brand_id)

        # 查询待处理事件
        result = await session.execute(
            text("""
                SELECT id, brand_id, store_id, source_agent, event_type,
                       severity, payload, target_agents
                FROM agent_events
                WHERE processed = FALSE AND brand_id = :brand_id
                ORDER BY created_at ASC
            """),
            {"brand_id": brand_id},
        )
        rows = result.fetchall()

        if not rows:
            logger.info("agent_event_processor.no_pending_events", brand_id=brand_id)
            return {"processed_count": 0, "responses": []}

        all_responses: List[Dict[str, Any]] = []

        for row in rows:
            event_id = row[0]
            store_id = row[2]
            event_type = row[4]
            severity = row[5]
            payload = row[6] if isinstance(row[6], dict) else json.loads(row[6] or "{}")
            target_agents = row[7] or []

            # 根据event_type和metric生成响应
            metric = payload.get("metric", "")
            responses = self._generate_responses(
                event_type=event_type,
                metric=metric,
                severity=severity,
                payload=payload,
                target_agents=target_agents,
            )

            # 写回responses并标记已处理
            await session.execute(
                text("""
                    UPDATE agent_events
                    SET responses = :responses::jsonb,
                        processed = TRUE,
                        processed_at = NOW()
                    WHERE id = :event_id
                """),
                {
                    "event_id": event_id,
                    "responses": json.dumps(responses, ensure_ascii=False),
                },
            )

            all_responses.append({
                "event_id": str(event_id),
                "store_id": store_id,
                "event_type": event_type,
                "metric": metric,
                "severity": severity,
                "response_count": len(responses),
                "responses": responses,
            })

            logger.info(
                "agent_event_processor.event_processed",
                event_id=str(event_id),
                metric=metric,
                response_count=len(responses),
            )

        logger.info(
            "agent_event_processor.process_pending.done",
            brand_id=brand_id,
            processed_count=len(all_responses),
        )

        return {
            "processed_count": len(all_responses),
            "responses": all_responses,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 方法2: 基于单个事件生成跨Agent行动建议
    # ─────────────────────────────────────────────────────────────────────
    async def generate_cross_agent_actions(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        event: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """基于单个事件生成跨Agent行动建议

        Args:
            event: {"event_type": "anomaly_detected", "metric": "material_cost_ratio",
                    "severity": "warning", "payload": {...}}

        Returns:
            [{"agent": "supply_chain", "action": "...", "expected_impact_yuan": 1200.00,
              "urgency": "high", "confidence": 0.85}, ...]
        """
        metric = event.get("metric", "")
        severity = event.get("severity", "warning")
        payload = event.get("payload", {})

        # 获取行动模板
        action_templates = CROSS_AGENT_ACTIONS.get(metric, [])

        if not action_templates:
            logger.warning(
                "agent_event_processor.no_action_template",
                metric=metric,
                store_id=store_id,
            )
            return []

        # 查询门店近期经营数据以估算影响金额
        impact_data = await self._fetch_impact_data(session, store_id, brand_id)

        actions: List[Dict[str, Any]] = []
        for template in action_templates:
            expected_impact_fen = self._estimate_impact_fen(
                metric=metric,
                agent=template["agent"],
                impact_data=impact_data,
                severity=severity,
            )
            # 金额从分转元（DB存分，展示用元）
            expected_impact_yuan = round(expected_impact_fen / 100, 2)

            actions.append({
                "agent": template["agent"],
                "action": template["action"],
                "expected_impact_yuan": expected_impact_yuan,
                "urgency": self._adjust_urgency(template["urgency"], severity),
                "confidence": template["confidence"],
            })

        logger.info(
            "agent_event_processor.cross_agent_actions_generated",
            store_id=store_id,
            metric=metric,
            action_count=len(actions),
        )

        return actions

    # ─────────────────────────────────────────────────────────────────────
    # 方法3: 目标偏差预警
    # ─────────────────────────────────────────────────────────────────────
    async def check_objective_deviations(
        self,
        session: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """检查所有active目标是否跟上时间进度，对落后目标自动创建预警事件

        Returns:
            {"on_track": N, "at_risk": N, "behind": N, "alerts": [...]}
        """
        today = date.today()
        current_year = today.year

        logger.info(
            "agent_event_processor.check_deviations.start",
            brand_id=brand_id,
            check_date=str(today),
        )

        # 查询所有active的月度/季度目标
        result = await session.execute(
            text("""
                SELECT id, store_id, fiscal_year, period_type, period_value,
                       metric_code, target_value, actual_value, bsc_dimension,
                       objective_name
                FROM business_objectives
                WHERE brand_id = :brand_id
                  AND status = 'active'
                  AND fiscal_year = :fiscal_year
                  AND period_type IN ('month', 'quarter')
            """),
            {"brand_id": brand_id, "fiscal_year": current_year},
        )
        rows = result.fetchall()

        on_track_count = 0
        at_risk_count = 0
        behind_count = 0
        alerts: List[Dict[str, Any]] = []

        for row in rows:
            obj_id = row[0]
            store_id = row[1]
            period_type = row[3]
            period_value = row[4]
            metric_code = row[5]
            target_value = row[6] or 0
            actual_value = row[7] or 0
            bsc_dimension = row[8]
            objective_name = row[9]

            if target_value == 0:
                continue

            # 计算时间进度百分比
            time_pct = self._calc_time_progress(today, period_type, period_value)
            if time_pct is None or time_pct <= 0:
                continue

            # 计算实际进度百分比
            actual_pct = actual_value / target_value

            # 偏差比 = actual_pct / time_pct
            deviation_ratio = actual_pct / time_pct if time_pct > 0 else 1.0

            # 分类
            if deviation_ratio >= DEVIATION_ON_TRACK:
                category = "on_track"
                on_track_count += 1
            elif deviation_ratio >= DEVIATION_AT_RISK:
                category = "at_risk"
                at_risk_count += 1
            else:
                category = "behind"
                behind_count += 1

                # 对behind的目标自动创建agent_event通知Chief Agent
                alert_payload = {
                    "objective_id": str(obj_id),
                    "objective_name": objective_name,
                    "metric": metric_code,
                    "bsc_dimension": str(bsc_dimension),
                    "target_value_fen": target_value,
                    "actual_value_fen": actual_value,
                    "time_progress_pct": round(time_pct * 100, 1),
                    "actual_progress_pct": round(actual_pct * 100, 1),
                    "deviation_ratio": round(deviation_ratio, 3),
                    "gap_yuan": round((target_value * time_pct - actual_value) / 100, 2),
                }

                await session.execute(
                    text("""
                        INSERT INTO agent_events
                            (brand_id, store_id, source_agent, event_type,
                             severity, payload, target_agents)
                        VALUES
                            (:brand_id, :store_id, 'objective_monitor',
                             'objective_behind', 'warning',
                             :payload::jsonb, :target_agents)
                    """),
                    {
                        "brand_id": brand_id,
                        "store_id": store_id,
                        "payload": json.dumps(alert_payload, ensure_ascii=False),
                        "target_agents": ["chief"],
                    },
                )

                alerts.append({
                    "objective_id": str(obj_id),
                    "objective_name": objective_name,
                    "store_id": store_id,
                    "metric_code": metric_code,
                    "category": category,
                    "time_progress_pct": round(time_pct * 100, 1),
                    "actual_progress_pct": round(actual_pct * 100, 1),
                    "gap_yuan": alert_payload["gap_yuan"],
                })

        logger.info(
            "agent_event_processor.check_deviations.done",
            brand_id=brand_id,
            on_track=on_track_count,
            at_risk=at_risk_count,
            behind=behind_count,
            alert_count=len(alerts),
        )

        return {
            "on_track": on_track_count,
            "at_risk": at_risk_count,
            "behind": behind_count,
            "alerts": alerts,
        }

    # ═════════════════════════════════════════════════════════════════════
    # 私有方法
    # ═════════════════════════════════════════════════════════════════════

    def _generate_responses(
        self,
        event_type: str,
        metric: str,
        severity: str,
        payload: Dict[str, Any],
        target_agents: List[str],
    ) -> List[Dict[str, Any]]:
        """基于规则引擎为事件生成Agent响应"""
        if event_type != "anomaly_detected":
            return [{
                "agent": "chief",
                "response_type": "acknowledged",
                "message": f"事件类型 {event_type} 已接收，待人工处理",
                "generated_at": datetime.utcnow().isoformat(),
            }]

        rules = RESPONSE_RULES.get(metric, [])
        responses: List[Dict[str, Any]] = []

        for rule in rules:
            # 只生成target_agents中包含的Agent响应
            if target_agents and rule["agent"] not in target_agents:
                continue

            responses.append({
                "agent": rule["agent"],
                "response_type": rule["response_type"],
                "action": rule["action"],
                "severity": severity,
                "context": {
                    "metric": metric,
                    "current_value": payload.get("current_value"),
                    "baseline_value": payload.get("baseline_value"),
                },
                "generated_at": datetime.utcnow().isoformat(),
            })

        # 如果规则引擎无匹配，生成通用响应
        if not responses:
            for agent_name in target_agents:
                responses.append({
                    "agent": agent_name,
                    "response_type": "generic_alert",
                    "action": f"关注指标 {metric} 异常，请人工排查",
                    "severity": severity,
                    "generated_at": datetime.utcnow().isoformat(),
                })

        return responses

    async def _fetch_impact_data(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
    ) -> Dict[str, Any]:
        """查询门店近期经营数据以估算影响"""
        result = await session.execute(
            text("""
                SELECT
                    COALESCE(AVG(revenue), 0) AS avg_daily_revenue_fen,
                    COALESCE(AVG(material_cost), 0) AS avg_daily_material_fen,
                    COALESCE(AVG(waste_amount), 0) AS avg_daily_waste_fen
                FROM store_pnl
                WHERE store_id = :store_id
                  AND brand_id = :brand_id
                  AND report_date >= CURRENT_DATE - INTERVAL '7 days'
            """),
            {"store_id": store_id, "brand_id": brand_id},
        )
        row = result.fetchone()

        if row is None:
            return {
                "avg_daily_revenue_fen": 0,
                "avg_daily_material_fen": 0,
                "avg_daily_waste_fen": 0,
            }

        return {
            "avg_daily_revenue_fen": int(row[0] or 0),
            "avg_daily_material_fen": int(row[1] or 0),
            "avg_daily_waste_fen": int(row[2] or 0),
        }

    def _estimate_impact_fen(
        self,
        metric: str,
        agent: str,
        impact_data: Dict[str, Any],
        severity: str,
    ) -> int:
        """估算单个行动的潜在影响金额（分）

        基于近7天日均数据，按severity调整系数。
        """
        severity_multiplier = {"critical": 0.05, "warning": 0.03, "info": 0.01}
        multiplier = severity_multiplier.get(severity, 0.02)

        if metric == "material_cost_ratio":
            base = impact_data.get("avg_daily_material_fen", 0)
            # 月度影响 = 日均食材成本 × 30 × 改善比例
            return int(base * 30 * multiplier)
        elif metric == "revenue":
            base = impact_data.get("avg_daily_revenue_fen", 0)
            return int(base * 30 * multiplier)
        elif metric == "waste":
            base = impact_data.get("avg_daily_waste_fen", 0)
            return int(base * 30 * multiplier)

        return 0

    def _adjust_urgency(self, base_urgency: str, severity: str) -> str:
        """根据事件严重度调整行动紧急度"""
        if severity == "critical":
            return "critical"
        if severity == "warning" and base_urgency == "medium":
            return "high"
        return base_urgency

    def _calc_time_progress(
        self,
        today: date,
        period_type: str,
        period_value: int,
    ) -> Optional[float]:
        """计算当前日期在目标周期内的时间进度百分比

        例：4月10日，月目标(period_value=4) → 10/30 = 33.3%
        """
        year = today.year

        if period_type == "month":
            if today.month != period_value:
                # 已过去的月份返回100%，未来月份返回None
                if today.month > period_value:
                    return 1.0
                return None
            _, days_in_month = monthrange(year, period_value)
            return today.day / days_in_month

        elif period_type == "quarter":
            quarter_start_month = (period_value - 1) * 3 + 1
            quarter_end_month = quarter_start_month + 2

            if today.month > quarter_end_month:
                return 1.0
            if today.month < quarter_start_month:
                return None

            # 计算季度内总天数和已过天数
            total_days = 0
            elapsed_days = 0
            for m in range(quarter_start_month, quarter_end_month + 1):
                _, dim = monthrange(year, m)
                total_days += dim
                if today.month > m:
                    elapsed_days += dim
                elif today.month == m:
                    elapsed_days += today.day

            return elapsed_days / total_days if total_days > 0 else None

        return None
