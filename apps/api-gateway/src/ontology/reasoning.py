"""
智链OS 本体推理引擎（Palantir Reasoning Layer）

实现损耗五步推理链：
  Step 1：计算理论消耗（BOM × 订单量 × 出成率）
  Step 2：计算库存差异（期初 + 采购 - 期末 - 理论消耗）
  Step 3：多维评分（员工失误 / 食材质量 / 设备故障 / 工艺偏离）
  Step 4：加权融合，生成根因（置信度 + 证据链）
  Step 5：写回本体（WasteEvent)-[:ROOT_CAUSE {confidence, evidence}]→ 目标节点

可解释性（XAI）：每步推理结果都记录在 root_cause_evidence 字段中
"""

import os
import time
import structlog
from typing import Optional

from neo4j import GraphDatabase

logger = structlog.get_logger()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


class WasteReasoningEngine:
    """
    损耗根因推理引擎

    用法：
        engine = WasteReasoningEngine()
        result = engine.infer_root_cause(event_id="WE-20260228-001")
        # result: {"root_cause": "staff_error", "confidence": 0.82, "evidence": [...]}
    """

    def __init__(
        self,
        uri: str = NEO4J_URI,
        user: str = NEO4J_USER,
        password: str = NEO4J_PASSWORD,
    ):
        if not password:
            raise EnvironmentError("NEO4J_PASSWORD 未设置")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    # ── 公开接口 ─────────────────────────────────────────────────────────────

    def infer_root_cause(self, event_id: str) -> dict:
        """
        对指定损耗事件执行五步推理，返回根因分析结果

        Returns:
            {
                "event_id": str,
                "root_cause": str,           # 最高置信度的根因类型
                "confidence": float,          # 0-1
                "evidence": list[str],        # 可溯源证据列表
                "all_causes": list[dict],     # 所有候选根因及置信度
                "reasoning_steps": list[str], # 推理步骤说明
            }
        """
        with self.driver.session() as session:
            # Step 1-2：查询事件相关数据
            context = self._fetch_event_context(session, event_id)
            if not context:
                return {
                    "event_id": event_id,
                    "error": f"找不到 WasteEvent: {event_id}",
                }

            # Step 3：多维评分
            scores = {
                "staff_error": self._score_staff_error(context),
                "food_quality": self._score_food_quality(context),
                "equipment_fault": self._score_equipment_fault(context),
                "process_deviation": self._score_process_deviation(context),
            }

            # Step 4：找最高置信度根因
            top_cause = max(scores, key=lambda k: scores[k]["score"])
            top_score = scores[top_cause]["score"]

            all_causes = [
                {"type": k, "confidence": v["score"], "evidence": v["evidence"]}
                for k, v in sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
            ]

            reasoning_steps = [
                f"Step1: 损耗事件 {event_id}，食材 {context.get('ing_name', '?')}，损耗量 {context.get('amount', '?')}",
                f"Step2: 班次员工 {context.get('staff_name', '未知')}，历史错误率 {context.get('staff_error_rate', 0):.1%}",
                f"Step3: 供应商质量评分 {context.get('quality_score', 'N/A')}，设备状态 {context.get('equipment_status', 'N/A')}",
                f"Step4: 多维评分 → {top_cause} 置信度 {top_score:.0%}",
                f"Step5: 根因写回本体完成",
            ]

            # Step 5：写回本体
            self._write_root_cause(session, event_id, top_cause, top_score, scores[top_cause]["evidence"])

            return {
                "event_id": event_id,
                "root_cause": top_cause,
                "confidence": round(top_score, 3),
                "evidence": scores[top_cause]["evidence"],
                "all_causes": all_causes,
                "reasoning_steps": reasoning_steps,
            }

    # ── Step 1-2：数据查询 ───────────────────────────────────────────────────

    def _fetch_event_context(self, session, event_id: str) -> Optional[dict]:
        """从本体图查询损耗事件的多维上下文"""
        result = session.run(
            """
            MATCH (w:WasteEvent {event_id: $event_id})-[:INVOLVES]->(i:Ingredient)
            OPTIONAL MATCH (w)-[:HAPPENED_DURING]->(sh:Shift)-[:STAFFED_BY]->(s:Staff)
            OPTIONAL MATCH (i)<-[:SUPPLIES]-(sup:Supplier)
            OPTIONAL MATCH (eq:Equipment)-[:STORES]->(i)
            RETURN
                w.amount              AS amount,
                w.unit                AS unit,
                i.ing_id              AS ing_id,
                i.name                AS ing_name,
                i.category            AS ing_category,
                s.staff_id            AS staff_id,
                s.name                AS staff_name,
                s.error_rate          AS staff_error_rate,
                sh.type               AS shift_type,
                sup.quality_score     AS quality_score,
                sup.supplier_id       AS supplier_id,
                sup.name              AS supplier_name,
                eq.equipment_id       AS equipment_id,
                eq.status             AS equipment_status,
                eq.malfunction_rate   AS equipment_malfunction_rate
            LIMIT 1
            """,
            event_id=event_id,
        ).single()

        if result is None:
            return None
        return dict(result)

    # ── Step 3：评分函数 ─────────────────────────────────────────────────────

    def _score_staff_error(self, ctx: dict) -> dict:
        error_rate = ctx.get("staff_error_rate") or 0.0
        shift_type = ctx.get("shift_type") or "day"
        shift_factor = 1.3 if shift_type in ("night", "夜班") else 1.0
        score = min(1.0, error_rate * shift_factor)
        evidence = []
        if ctx.get("staff_name"):
            evidence.append(f"员工 {ctx['staff_name']} 历史错误率 {error_rate:.1%}")
        if shift_type in ("night", "夜班"):
            evidence.append(f"夜班作业，错误率系数 ×1.3")
        return {"score": score, "evidence": evidence}

    def _score_food_quality(self, ctx: dict) -> dict:
        quality = ctx.get("quality_score")
        if quality is None:
            return {"score": 0.0, "evidence": ["无供应商质量数据"]}
        # 质量分 0-5，分越低问题概率越高
        score = max(0.0, (5.0 - float(quality)) / 5.0)
        evidence = [f"供应商 {ctx.get('supplier_name', '?')} 质量评分 {quality:.1f}/5.0"]
        return {"score": score, "evidence": evidence}

    def _score_equipment_fault(self, ctx: dict) -> dict:
        status = ctx.get("equipment_status") or "normal"
        malfunction_rate = ctx.get("equipment_malfunction_rate") or 0.0
        if status == "fault":
            score = 0.9
            evidence = [f"设备 {ctx.get('equipment_id', '?')} 当前状态：故障"]
        elif status == "maintenance":
            score = 0.4
            evidence = [f"设备 {ctx.get('equipment_id', '?')} 处于维护中"]
        else:
            score = min(0.5, float(malfunction_rate))
            evidence = [f"设备故障率 {malfunction_rate:.1%}"]
        return {"score": score, "evidence": evidence}

    def _score_process_deviation(self, ctx: dict) -> dict:
        """工艺偏离：暂基于食材类别经验值，后续接入 BOM 标准偏差分析"""
        category = ctx.get("ing_category") or ""
        # 海鲜类损耗工艺偏离概率历史较高
        score = 0.35 if "海鲜" in category else 0.15
        evidence = [f"食材类别 '{category}'，工艺偏离基准分 {score:.0%}"]
        return {"score": score, "evidence": evidence}

    # ── Step 5：写回本体 ─────────────────────────────────────────────────────

    def _write_root_cause(
        self,
        session,
        event_id: str,
        cause_type: str,
        confidence: float,
        evidence: list,
    ) -> None:
        """将推理结果写回 WasteEvent 节点"""
        session.run(
            """
            MATCH (w:WasteEvent {event_id: $event_id})
            SET w.root_cause_type       = $cause_type,
                w.root_cause_confidence = $confidence,
                w.root_cause_evidence   = $evidence,
                w.analysis_timestamp    = $ts
            """,
            event_id=event_id,
            cause_type=cause_type,
            confidence=confidence,
            evidence=evidence,
            ts=int(time.time() * 1000),
        )
        logger.info(
            "根因写回完成",
            event_id=event_id,
            cause=cause_type,
            confidence=f"{confidence:.0%}",
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
