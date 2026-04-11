"""Chief Agent — 经营大脑编排引擎

管理思想内核：
  - 德鲁克MBO: 目标→衡量→反馈
  - BSC: 四维平衡不偏科
  - PDCA: 计划→执行→检查→改善
  - 道家无为: 无异常则不打扰
"""

import json
import uuid
from datetime import date, timedelta
from typing import Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 异常阈值常量 ─────────────────────────────────────────────────
REVENUE_DROP_WARNING_PCT = 0.20       # 营收下降 >20% 触发 warning
MATERIAL_COST_WARNING = 0.38          # 食材成本率 >38% warning
MATERIAL_COST_CRITICAL = 0.42         # 食材成本率 >42% critical
WASTE_SPIKE_RATIO = 1.50              # 损耗金额 >均值150% warning

# ── 异常类型 → 目标 Agent 映射 ────────────────────────────────────
ANOMALY_TARGET_MAP: Dict[str, List[str]] = {
    "revenue_drop": ["financial", "customer"],
    "material_cost_high": ["financial", "supply_chain"],
    "waste_spike": ["supply_chain", "ops"],
}


class ChiefAgentService:
    """经营大脑 — 编排 Agent 间协作、异常检测、复盘生成"""

    # ─────────────────────────────────────────────────────────────
    # 方法1: 日复盘
    # ─────────────────────────────────────────────────────────────
    async def daily_review(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        target_date: Optional[date] = None,
    ) -> Dict:
        """每日经营复盘：异常检测 → 事件广播 → 复盘报告生成

        Returns:
            {"review_session_id": ..., "highlights": [...], "anomalies": [...],
             "recommendations": [...], "agent_session_id": ...}
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        logger.info(
            "chief_agent.daily_review.start",
            store_id=store_id,
            brand_id=brand_id,
            target_date=str(target_date),
        )

        agent_session_id = str(uuid.uuid4())

        # ── 1. 记录编排会话（状态: running） ──────────────────────
        await session.execute(
            text("""
                INSERT INTO chief_agent_sessions
                    (id, brand_id, store_id, trigger_type, trigger_source,
                     orchestration_plan, status)
                VALUES
                    (:id, :brand_id, :store_id, 'scheduled', 'daily_review',
                     :plan::jsonb, 'running')
            """),
            {
                "id": agent_session_id,
                "brand_id": brand_id,
                "store_id": store_id,
                "plan": json.dumps(
                    {"steps": ["fetch_pnl", "baseline", "anomaly_detect",
                               "event_broadcast", "generate_review"]},
                    ensure_ascii=False,
                ),
            },
        )

        # ── 2. 读取当日 store_pnl + operation_snapshot ───────────
        today_row = await self._fetch_today_metrics(
            session, store_id, target_date
        )

        # ── 3. 读取7日均值作为基线 ───────────────────────────────
        baseline = await self._fetch_baseline(
            session, store_id, target_date, days=7
        )

        # ── 4. 异常检测 ──────────────────────────────────────────
        anomalies = self._detect_anomalies(today_row, baseline)

        # ── 5. 异常事件写入 agent_events ─────────────────────────
        for anomaly in anomalies:
            target_agents = ANOMALY_TARGET_MAP.get(
                anomaly["type"], ["ops"]
            )
            await session.execute(
                text("""
                    INSERT INTO agent_events
                        (brand_id, store_id, source_agent, event_type,
                         severity, payload, target_agents)
                    VALUES
                        (:brand_id, :store_id, 'chief', 'anomaly_detected',
                         :severity, :payload::jsonb, :target_agents)
                """),
                {
                    "brand_id": brand_id,
                    "store_id": store_id,
                    "severity": anomaly["severity"],
                    "payload": json.dumps(anomaly, ensure_ascii=False),
                    "target_agents": target_agents,
                },
            )

        # ── 6. 生成 highlights ───────────────────────────────────
        highlights = self._build_highlights(today_row, baseline)

        # ── 7. 生成 recommendations ──────────────────────────────
        recommendations = self._build_recommendations(anomalies)

        # ── 8. UPSERT review_sessions ────────────────────────────
        ai_summary = {
            "date": str(target_date),
            "highlights": highlights,
            "anomalies": anomalies,
            "recommendations": recommendations,
        }

        review_result = await session.execute(
            text("""
                INSERT INTO review_sessions
                    (brand_id, store_id, review_type, period_start, period_end,
                     ai_summary, status)
                VALUES
                    (:brand_id, :store_id, 'daily', :target_date, :target_date,
                     :ai_summary::jsonb, 'draft')
                ON CONFLICT ON CONSTRAINT review_sessions_pkey DO NOTHING
                RETURNING id
            """),
            {
                "brand_id": brand_id,
                "store_id": store_id,
                "target_date": target_date,
                "ai_summary": json.dumps(ai_summary, ensure_ascii=False),
            },
        )
        review_row = review_result.fetchone()
        review_session_id = str(review_row[0]) if review_row else None

        # 如果 INSERT 被跳过（已存在），则 UPDATE
        if review_session_id is None:
            await session.execute(
                text("""
                    UPDATE review_sessions
                       SET ai_summary = :ai_summary::jsonb,
                           status = 'draft'
                     WHERE brand_id = :brand_id
                       AND store_id = :store_id
                       AND review_type = 'daily'
                       AND period_start = :target_date
                    RETURNING id
                """),
                {
                    "brand_id": brand_id,
                    "store_id": store_id,
                    "target_date": target_date,
                    "ai_summary": json.dumps(ai_summary, ensure_ascii=False),
                },
            )

        # ── 9. 完成编排会话 ──────────────────────────────────────
        confidence = 0.85 if not anomalies else max(0.50, 0.85 - 0.05 * len(anomalies))
        await session.execute(
            text("""
                UPDATE chief_agent_sessions
                   SET status = 'completed',
                       completed_at = NOW(),
                       final_output = :output::jsonb,
                       confidence = :confidence
                 WHERE id = :id
            """),
            {
                "id": agent_session_id,
                "output": json.dumps(ai_summary, ensure_ascii=False),
                "confidence": round(confidence, 2),
            },
        )

        await session.commit()

        logger.info(
            "chief_agent.daily_review.done",
            store_id=store_id,
            anomaly_count=len(anomalies),
        )

        return {
            "agent_session_id": agent_session_id,
            "review_session_id": review_session_id,
            "highlights": highlights,
            "anomalies": anomalies,
            "recommendations": recommendations,
        }

    # ─────────────────────────────────────────────────────────────
    # 方法2: 周复盘
    # ─────────────────────────────────────────────────────────────
    async def weekly_review(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        week_end: Optional[date] = None,
    ) -> Dict:
        """周度经营复盘：本周vs上周环比 + 同品牌门店排名

        Returns:
            {"review_session_id": ..., "summary": {...}}
        """
        if week_end is None:
            today = date.today()
            # 默认取上周日
            week_end = today - timedelta(days=today.isoweekday())
        week_start = week_end - timedelta(days=6)
        prev_week_end = week_start - timedelta(days=1)
        prev_week_start = prev_week_end - timedelta(days=6)

        logger.info(
            "chief_agent.weekly_review.start",
            store_id=store_id,
            brand_id=brand_id,
            week_start=str(week_start),
            week_end=str(week_end),
        )

        # ── 本周汇总 ─────────────────────────────────────────────
        this_week = await self._fetch_period_summary(
            session, store_id, week_start, week_end
        )

        # ── 上周汇总 ─────────────────────────────────────────────
        prev_week = await self._fetch_period_summary(
            session, store_id, prev_week_start, prev_week_end
        )

        # ── 环比计算 ─────────────────────────────────────────────
        wow = self._compute_wow(this_week, prev_week)

        # ── 同品牌门店排名 ───────────────────────────────────────
        rank_result = await session.execute(
            text("""
                SELECT store_id,
                       COALESCE(SUM(total_revenue), 0) AS week_revenue
                  FROM store_pnl
                 WHERE brand_id = :brand_id
                   AND biz_date >= :week_start
                   AND biz_date <= :week_end
                 GROUP BY store_id
                 ORDER BY week_revenue DESC
            """),
            {
                "brand_id": brand_id,
                "week_start": week_start,
                "week_end": week_end,
            },
        )
        rank_rows = rank_result.fetchall()
        store_rank = None
        total_stores = len(rank_rows)
        for idx, r in enumerate(rank_rows, 1):
            if r.store_id == store_id:
                store_rank = idx
                break

        summary = {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "this_week": this_week,
            "prev_week": prev_week,
            "wow": wow,
            "brand_rank": store_rank,
            "brand_total_stores": total_stores,
        }

        # ── 写入 review_sessions ─────────────────────────────────
        result = await session.execute(
            text("""
                INSERT INTO review_sessions
                    (brand_id, store_id, review_type, period_start, period_end,
                     ai_summary, status)
                VALUES
                    (:brand_id, :store_id, 'weekly', :week_start, :week_end,
                     :ai_summary::jsonb, 'draft')
                RETURNING id
            """),
            {
                "brand_id": brand_id,
                "store_id": store_id,
                "week_start": week_start,
                "week_end": week_end,
                "ai_summary": json.dumps(summary, ensure_ascii=False),
            },
        )
        row = result.fetchone()
        review_session_id = str(row[0]) if row else None

        await session.commit()

        logger.info(
            "chief_agent.weekly_review.done",
            store_id=store_id,
            review_session_id=review_session_id,
        )

        return {
            "review_session_id": review_session_id,
            "summary": summary,
        }

    # ─────────────────────────────────────────────────────────────
    # 方法3: 处理未决 Agent 事件
    # ─────────────────────────────────────────────────────────────
    async def process_agent_events(
        self,
        session: AsyncSession,
        brand_id: str,
    ) -> Dict:
        """扫描并处理未处理的 agent_events

        Returns:
            {"processed_count": int, "dispatched": [...]}
        """
        logger.info(
            "chief_agent.process_events.start",
            brand_id=brand_id,
        )

        result = await session.execute(
            text("""
                SELECT id, store_id, source_agent, event_type, severity,
                       payload, target_agents
                  FROM agent_events
                 WHERE brand_id = :brand_id
                   AND processed = FALSE
                 ORDER BY created_at ASC
                 LIMIT 100
            """),
            {"brand_id": brand_id},
        )
        rows = result.fetchall()

        dispatched: List[Dict] = []

        for row in rows:
            event_id = str(row.id)
            target_agents = row.target_agents or []

            # 根据 event_type 和 target_agents 决定响应策略
            response_actions = self._plan_response(
                row.event_type, row.severity, target_agents
            )

            # 标记已处理，记录响应
            await session.execute(
                text("""
                    UPDATE agent_events
                       SET processed = TRUE,
                           processed_at = NOW(),
                           responses = :responses::jsonb
                     WHERE id = :id
                """),
                {
                    "id": event_id,
                    "responses": json.dumps(
                        response_actions, ensure_ascii=False
                    ),
                },
            )

            dispatched.append({
                "event_id": event_id,
                "event_type": row.event_type,
                "severity": row.severity,
                "target_agents": target_agents,
                "response_actions": response_actions,
            })

        await session.commit()

        logger.info(
            "chief_agent.process_events.done",
            brand_id=brand_id,
            processed_count=len(dispatched),
        )

        return {
            "processed_count": len(dispatched),
            "dispatched": dispatched,
        }

    # ═════════════════════════════════════════════════════════════
    # 私有方法
    # ═════════════════════════════════════════════════════════════

    async def _fetch_today_metrics(
        self, session: AsyncSession, store_id: str, target_date: date
    ) -> Dict:
        """读取当日 store_pnl 核心指标"""
        result = await session.execute(
            text("""
                SELECT total_revenue,
                       material_cost,
                       waste_amount,
                       order_count,
                       CASE WHEN total_revenue > 0
                            THEN material_cost::numeric / total_revenue
                            ELSE 0 END AS material_cost_rate
                  FROM store_pnl
                 WHERE store_id = :store_id
                   AND biz_date = :biz_date
                 LIMIT 1
            """),
            {"store_id": store_id, "biz_date": target_date},
        )
        row = result.fetchone()
        if row is None:
            logger.warning(
                "chief_agent.no_pnl_data",
                store_id=store_id,
                biz_date=str(target_date),
            )
            return {
                "total_revenue": 0,
                "material_cost": 0,
                "waste_amount": 0,
                "order_count": 0,
                "material_cost_rate": 0,
            }
        return {
            "total_revenue": float(row.total_revenue or 0),
            "material_cost": float(row.material_cost or 0),
            "waste_amount": float(row.waste_amount or 0),
            "order_count": int(row.order_count or 0),
            "material_cost_rate": float(row.material_cost_rate or 0),
        }

    async def _fetch_baseline(
        self, session: AsyncSession, store_id: str, target_date: date, days: int = 7
    ) -> Dict:
        """读取过去 N 日均值作为异常检测基线"""
        start_date = target_date - timedelta(days=days)
        result = await session.execute(
            text("""
                SELECT COALESCE(AVG(total_revenue), 0) AS avg_revenue,
                       COALESCE(AVG(material_cost), 0) AS avg_material_cost,
                       COALESCE(AVG(waste_amount), 0)  AS avg_waste,
                       COALESCE(AVG(order_count), 0)   AS avg_orders,
                       CASE WHEN COALESCE(SUM(total_revenue), 0) > 0
                            THEN SUM(material_cost)::numeric / SUM(total_revenue)
                            ELSE 0 END AS avg_material_cost_rate
                  FROM store_pnl
                 WHERE store_id = :store_id
                   AND biz_date >= :start_date
                   AND biz_date < :target_date
            """),
            {
                "store_id": store_id,
                "start_date": start_date,
                "target_date": target_date,
            },
        )
        row = result.fetchone()
        return {
            "avg_revenue": float(row.avg_revenue) if row else 0,
            "avg_material_cost": float(row.avg_material_cost) if row else 0,
            "avg_waste": float(row.avg_waste) if row else 0,
            "avg_orders": float(row.avg_orders) if row else 0,
            "avg_material_cost_rate": float(row.avg_material_cost_rate) if row else 0,
        }

    def _detect_anomalies(self, today: Dict, baseline: Dict) -> List[Dict]:
        """基于阈值的异常检测"""
        anomalies: List[Dict] = []

        # 营收下降 >20%
        avg_rev = baseline.get("avg_revenue", 0)
        today_rev = today.get("total_revenue", 0)
        if avg_rev > 0:
            drop_pct = (avg_rev - today_rev) / avg_rev
            if drop_pct > REVENUE_DROP_WARNING_PCT:
                anomalies.append({
                    "type": "revenue_drop",
                    "severity": "warning",
                    "metric": "total_revenue",
                    "today_value": today_rev,
                    "baseline_value": round(avg_rev, 2),
                    "deviation_pct": round(drop_pct * 100, 1),
                    "message": f"营收¥{today_rev:,.0f}，较7日均值下降{drop_pct*100:.0f}%",
                })

        # 食材成本率
        cost_rate = today.get("material_cost_rate", 0)
        if cost_rate > MATERIAL_COST_CRITICAL:
            anomalies.append({
                "type": "material_cost_high",
                "severity": "critical",
                "metric": "material_cost_rate",
                "today_value": round(cost_rate * 100, 1),
                "threshold": MATERIAL_COST_CRITICAL * 100,
                "message": f"食材成本率{cost_rate*100:.1f}%，超过临界值{MATERIAL_COST_CRITICAL*100:.0f}%",
            })
        elif cost_rate > MATERIAL_COST_WARNING:
            anomalies.append({
                "type": "material_cost_high",
                "severity": "warning",
                "metric": "material_cost_rate",
                "today_value": round(cost_rate * 100, 1),
                "threshold": MATERIAL_COST_WARNING * 100,
                "message": f"食材成本率{cost_rate*100:.1f}%，超过警戒值{MATERIAL_COST_WARNING*100:.0f}%",
            })

        # 损耗金额 >均值150%
        avg_waste = baseline.get("avg_waste", 0)
        today_waste = today.get("waste_amount", 0)
        if avg_waste > 0 and today_waste > avg_waste * WASTE_SPIKE_RATIO:
            ratio = today_waste / avg_waste
            anomalies.append({
                "type": "waste_spike",
                "severity": "warning",
                "metric": "waste_amount",
                "today_value": today_waste,
                "baseline_value": round(avg_waste, 2),
                "ratio": round(ratio, 2),
                "message": f"损耗¥{today_waste:,.0f}，为7日均值的{ratio:.0f}倍",
            })

        return anomalies

    def _build_highlights(self, today: Dict, baseline: Dict) -> List[Dict]:
        """生成今日亮点摘要"""
        highlights = []

        # 今日营收
        rev = today.get("total_revenue", 0)
        avg_rev = baseline.get("avg_revenue", 0)
        rev_vs = ""
        if avg_rev > 0:
            pct = ((rev - avg_rev) / avg_rev) * 100
            direction = "上升" if pct >= 0 else "下降"
            rev_vs = f"，较7日均值{direction}{abs(pct):.0f}%"
        highlights.append({
            "label": "今日营收",
            "value": f"¥{rev:,.0f}",
            "note": rev_vs,
        })

        # 食材成本率
        cost_rate = today.get("material_cost_rate", 0)
        highlights.append({
            "label": "食材成本率",
            "value": f"{cost_rate*100:.1f}%",
            "note": "达标" if cost_rate <= MATERIAL_COST_WARNING else "偏高",
        })

        # 订单量
        orders = today.get("order_count", 0)
        highlights.append({
            "label": "订单量",
            "value": str(orders),
            "note": "",
        })

        return highlights

    def _build_recommendations(self, anomalies: List[Dict]) -> List[Dict]:
        """基于异常生成可执行建议"""
        recommendations: List[Dict] = []

        for a in anomalies:
            if a["type"] == "revenue_drop":
                recommendations.append({
                    "action": "排查客流下降原因，检查周边竞品活动",
                    "expected_impact": "预期可恢复营收5-10%",
                    "confidence": 0.6,
                    "priority": "high",
                })
            elif a["type"] == "material_cost_high":
                recommendations.append({
                    "action": "检查当日高成本菜品出品量，核实采购价格",
                    "expected_impact": "预期降低成本率1-2个百分点",
                    "confidence": 0.7,
                    "priority": "critical" if a["severity"] == "critical" else "high",
                })
            elif a["type"] == "waste_spike":
                recommendations.append({
                    "action": "复查备货计划与实际销量偏差，优化明日预估",
                    "expected_impact": f"预期减少损耗¥{a.get('today_value', 0) * 0.3:,.0f}",
                    "confidence": 0.65,
                    "priority": "high",
                })

        if not anomalies:
            recommendations.append({
                "action": "各项指标正常，保持当前运营节奏",
                "expected_impact": "无需额外动作",
                "confidence": 0.9,
                "priority": "low",
            })

        return recommendations

    async def _fetch_period_summary(
        self, session: AsyncSession, store_id: str,
        start_date: date, end_date: date,
    ) -> Dict:
        """读取指定时段的汇总指标"""
        result = await session.execute(
            text("""
                SELECT COALESCE(SUM(total_revenue), 0)  AS sum_revenue,
                       COALESCE(SUM(material_cost), 0)  AS sum_material_cost,
                       COALESCE(SUM(waste_amount), 0)   AS sum_waste,
                       COALESCE(SUM(order_count), 0)    AS sum_orders,
                       COUNT(*)                         AS day_count
                  FROM store_pnl
                 WHERE store_id = :store_id
                   AND biz_date >= :start_date
                   AND biz_date <= :end_date
            """),
            {
                "store_id": store_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        row = result.fetchone()
        if row is None or row.day_count == 0:
            return {
                "sum_revenue": 0,
                "sum_material_cost": 0,
                "sum_waste": 0,
                "sum_orders": 0,
                "day_count": 0,
                "material_cost_rate": 0,
            }
        sum_rev = float(row.sum_revenue)
        sum_mat = float(row.sum_material_cost)
        return {
            "sum_revenue": sum_rev,
            "sum_material_cost": sum_mat,
            "sum_waste": float(row.sum_waste),
            "sum_orders": int(row.sum_orders),
            "day_count": int(row.day_count),
            "material_cost_rate": round(sum_mat / sum_rev, 4) if sum_rev > 0 else 0,
        }

    def _compute_wow(self, this_week: Dict, prev_week: Dict) -> Dict:
        """计算周环比"""
        wow: Dict = {}
        for key in ("sum_revenue", "sum_material_cost", "sum_waste", "sum_orders"):
            curr = this_week.get(key, 0)
            prev = prev_week.get(key, 0)
            if prev > 0:
                wow[f"{key}_change_pct"] = round(((curr - prev) / prev) * 100, 1)
            else:
                wow[f"{key}_change_pct"] = None
        return wow

    def _plan_response(
        self, event_type: str, severity: str, target_agents: List[str]
    ) -> List[Dict]:
        """根据事件类型规划响应动作"""
        actions: List[Dict] = []

        if event_type == "anomaly_detected":
            for agent in target_agents:
                if agent == "financial":
                    actions.append({
                        "agent": "financial",
                        "action": "review_cost_structure",
                        "priority": severity,
                    })
                elif agent == "customer":
                    actions.append({
                        "agent": "customer",
                        "action": "analyze_traffic_pattern",
                        "priority": severity,
                    })
                elif agent == "supply_chain":
                    actions.append({
                        "agent": "supply_chain",
                        "action": "check_procurement_prices",
                        "priority": severity,
                    })
                elif agent == "ops":
                    actions.append({
                        "agent": "ops",
                        "action": "review_waste_process",
                        "priority": severity,
                    })

        return actions
