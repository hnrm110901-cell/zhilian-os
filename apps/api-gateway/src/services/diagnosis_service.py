"""
L4 门店健康诊断服务（Diagnosis Service）

整合三大组件：
  UniversalReasoningEngine  — 规则推理（250+ 条，全维度）
  CausalGraphService        — Neo4j 因果图谱（供应链 / 设备 / 员工模式）
  CrossStoreKnowledgeService — L3 同伴组百分位上下文

输出 StoreHealthReport（整体分 + 6 维度详情 + 行动清单 + 改善方案）
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.reasoning_engine import (
    ALL_DIMENSIONS,
    StoreHealthReport,
    UniversalReasoningEngine,
)
from src.services.causal_graph_service import CausalGraphService

logger = structlog.get_logger()


class DiagnosisService:
    """
    门店健康一键诊断服务

    使用方式::

        async with get_db_session() as session:
            svc = DiagnosisService(session)
            report = await svc.run_full_diagnosis(
                store_id="STORE001",
                kpi_context={"waste_rate": 0.15, "food_cost_ratio": 0.32},
            )
            # report.overall_score  → 68.5
            # report.severity_summary → "P2"
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 主入口 ────────────────────────────────────────────────────────────────

    async def run_full_diagnosis(
        self,
        store_id:    str,
        kpi_context: Dict[str, Any],
        dimensions:  Optional[List[str]] = None,
    ) -> StoreHealthReport:
        """
        全维度门店健康诊断。

        执行步骤：
          1. 从 L3 cross_store_metrics 获取同伴组百分位上下文
          2. 从 Neo4j 获取因果图谱提示（供应链 / 设备 / 员工）
          3. UniversalReasoningEngine 规则推理（250+ 条规则）
          4. 结果合并，写入 reasoning_reports 物化表

        Args:
            store_id:    目标门店 ID
            kpi_context: KPI 实际值（如 {"waste_rate": 0.15, "labor_cost_ratio": 0.38}）
            dimensions:  指定推理维度（默认全部 6 维度）

        Returns:
            StoreHealthReport — 整体分 / 维度详情 / 行动清单 / 因果洞察
        """
        # Step 1: 同伴组上下文（L3）
        peer_context = await self._fetch_peer_context(store_id)

        # Step 2: 因果图谱提示（Neo4j）
        causal_hints = await self._fetch_causal_hints(store_id)

        # Step 3: 推理引擎
        engine = UniversalReasoningEngine(self.db)
        report = await engine.diagnose(
            store_id=store_id,
            kpi_context=kpi_context,
            dimensions=dimensions or ALL_DIMENSIONS,
            peer_context=peer_context,
            causal_hints=causal_hints,
        )

        logger.info(
            "门店诊断完成",
            store_id=store_id,
            overall_score=report.overall_score,
            severity=report.severity_summary,
        )
        return report

    # ── 历史报告查询 ──────────────────────────────────────────────────────────

    async def get_diagnosis_history(
        self,
        store_id:  str,
        days:      int = 30,
        dimension: Optional[str] = None,
    ) -> List[Dict]:
        """查询门店推理报告历史（供趋势图表展示）"""
        engine     = UniversalReasoningEngine(self.db)
        start_date = date.today() - timedelta(days=days)
        reports    = await engine.list_reports(
            store_id=store_id,
            start_date=start_date,
            dimension=dimension,
        )
        return [
            {
                "report_id":   str(r.id),
                "report_date": r.report_date.isoformat(),
                "dimension":   r.dimension,
                "severity":    r.severity,
                "root_cause":  r.root_cause,
                "confidence":  r.confidence,
                "is_actioned": r.is_actioned,
            }
            for r in reports
        ]

    # ── 跨店改善方案 ──────────────────────────────────────────────────────────

    async def get_cross_store_improvement_plan(
        self,
        store_id:    str,
        metric_name: str = "waste_rate",
    ) -> Dict:
        """
        基于 SIMILAR_TO 图谱边，生成跨店学习改善方案。

        对应知识规则 CROSS-045~050（最佳实践传播）。
        """
        causal_svc = CausalGraphService()
        try:
            hints = await causal_svc.get_cross_store_learning_hints(
                store_id,
                metric_name=f"{metric_name}_p30d",
            )
        except Exception:
            hints = []
        finally:
            causal_svc.close()

        if not hints:
            return {
                "store_id":    store_id,
                "metric":      metric_name,
                "status":      "no_better_peers_found",
                "suggestions": [],
            }

        return {
            "store_id":    store_id,
            "metric":      metric_name,
            "status":      "improvement_candidates_found",
            "suggestions": hints,
            "next_step": (
                f"联系以上同类门店深入交流 {metric_name} 优化经验，"
                f"重点对比操作流程和采购策略差异"
            ),
        }

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _fetch_peer_context(self, store_id: str) -> Dict[str, float]:
        """从 L3 物化表拉取同伴组百分位上下文"""
        try:
            from src.services.cross_store_knowledge_service import (
                CrossStoreKnowledgeService,
            )
            l3_svc     = CrossStoreKnowledgeService(self.db)
            benchmarks = await l3_svc.get_all_benchmarks(store_id)
            if not benchmarks:
                return {}

            ctx: Dict[str, float] = {}
            for bm in benchmarks:
                metric = bm.get("metric_name", "")
                for pct_key, pct_label in [
                    ("peer_p25", "peer.p25"),
                    ("peer_p50", "peer.p50"),
                    ("peer_p75", "peer.p75"),
                    ("peer_p90", "peer.p90"),
                ]:
                    val = bm.get(pct_key)
                    if val is not None:
                        # 每个 metric 独立存储：waste_rate.peer.p50
                        ctx[f"{metric}.{pct_label.replace('peer.', 'peer_')}"] = val

                # 通用 peer.pXX 取 waste_rate 作代表值
                if metric == "waste_rate":
                    for pct_key, pct_label in [
                        ("peer_p25", "peer.p25"),
                        ("peer_p50", "peer.p50"),
                        ("peer_p75", "peer.p75"),
                        ("peer_p90", "peer.p90"),
                    ]:
                        val = bm.get(pct_key)
                        if val is not None:
                            ctx[pct_label] = val
                    pct_in_peer = bm.get("percentile_in_peer")
                    if pct_in_peer is not None:
                        ctx["peer.percentile"] = float(pct_in_peer)
                    peer_group = bm.get("peer_group")
                    if peer_group:
                        ctx["peer_group"] = peer_group  # type: ignore[assignment]

            return ctx
        except Exception as e:
            logger.warning(
                "获取同伴组上下文失败（非致命）",
                store_id=store_id,
                error=str(e),
            )
            return {}

    async def _fetch_causal_hints(self, store_id: str) -> List[str]:
        """从 Neo4j 获取因果图谱提示（失败不阻断推理）"""
        causal_svc = CausalGraphService()
        try:
            return await causal_svc.get_full_causal_summary(store_id)
        except Exception as e:
            logger.warning(
                "Neo4j 因果提示获取失败（非致命）",
                store_id=store_id,
                error=str(e),
            )
            return []
        finally:
            causal_svc.close()
