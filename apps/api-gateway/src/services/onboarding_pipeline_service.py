"""
Onboarding Pipeline Service

5-stage knowledge base construction pipeline:
  Stage 1: Data cleaning    — validate + normalize onboarding_raw_data rows
  Stage 2: KPI calculation  — compute core metrics from imported data
  Stage 3: Baseline compare — compare against industry baseline (baseline_data_service)
  Stage 4: Vector embedding — embed text data into Qdrant enterprise collection
  Stage 5: Knowledge summary — Claude generates 1000-char brand knowledge summary

Entry point: OnboardingPipelineService.run(store_id, db)
Celery wrapper: run_onboarding_pipeline task (tasks/onboarding_tasks.py)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.onboarding import OnboardingRawData, OnboardingTask

logger = structlog.get_logger()

_STAGES = ["data_cleaning", "kpi_calculation", "baseline_compare", "vector_embedding", "knowledge_summary"]


class OnboardingPipelineService:

    def __init__(self, store_id: str, db: AsyncSession):
        self.store_id = store_id
        self.db = db
        self._kpis: Dict[str, Any] = {}
        self._baseline: Dict[str, Any] = {}

    # ── Entry point ────────────────────────────────────────────────────────────

    @classmethod
    async def run(cls, store_id: str, db: AsyncSession) -> Dict[str, Any]:
        """Execute all 5 stages sequentially. Returns final KPI snapshot."""
        svc = cls(store_id=store_id, db=db)
        result: Dict[str, Any] = {"store_id": store_id, "stages": {}}

        for stage in _STAGES:
            await svc._update_task_stage(stage)
            try:
                stage_result = await getattr(svc, f"_stage_{stage}")()
                result["stages"][stage] = {"status": "ok", **stage_result}
                logger.info("onboarding_pipeline_stage_done", store_id=store_id, stage=stage)
            except Exception as exc:
                logger.error("onboarding_pipeline_stage_failed", store_id=store_id, stage=stage, error=str(exc))
                result["stages"][stage] = {"status": "error", "error": str(exc)}
                # Continue pipeline — partial results are better than none

        await svc._mark_build_complete(result)
        return result

    # ── Stage 1: Data cleaning ─────────────────────────────────────────────────

    async def _stage_data_cleaning(self) -> Dict[str, Any]:
        """Validate raw rows, mark invalid ones, return count summary."""
        rows_res = await self.db.execute(select(OnboardingRawData).where(OnboardingRawData.store_id == self.store_id))
        rows = rows_res.scalars().all()

        valid_count, invalid_count = 0, 0
        for row in rows:
            errors = self._validate_row(row.data_type, row.row_data)
            if errors:
                row.is_valid = False
                row.error_msg = "; ".join(errors)
                invalid_count += 1
            else:
                valid_count += 1

        await self.db.commit()
        return {"valid_rows": valid_count, "invalid_rows": invalid_count}

    def _validate_row(self, data_type: str, row_data: Dict) -> List[str]:
        """Basic type-specific validation. Returns list of error strings."""
        errors: List[str] = []

        if data_type == "D04":  # Financial monthly
            month = row_data.get("月份", "")
            if month and len(month) < 4:
                errors.append("月份格式应为 YYYY-MM 或 YYYY")
            revenue = row_data.get("营收", "")
            if revenue:
                try:
                    float(revenue)
                except ValueError:
                    errors.append("营收必须为数字")

        elif data_type == "D05":  # Members
            phone = row_data.get("手机", "")
            if phone and not phone.isdigit():
                errors.append("手机号应为纯数字")

        elif data_type == "D01":  # Dishes
            price = row_data.get("售价", "")
            if price:
                try:
                    float(price)
                except ValueError:
                    errors.append("售价必须为数字")

        return errors

    # ── Stage 2: KPI calculation ───────────────────────────────────────────────

    async def _stage_kpi_calculation(self) -> Dict[str, Any]:
        """Compute core business KPIs from imported data."""
        kpis: Dict[str, Any] = {}

        # Financial KPIs from D04
        d04_rows = await self._get_valid_rows("D04")
        if d04_rows:
            revenues = [float(r.get("营收", 0) or 0) for r in d04_rows]
            food_costs = [float(r.get("食材成本", 0) or 0) for r in d04_rows]
            labor_costs = [float(r.get("人力成本", 0) or 0) for r in d04_rows]
            profits = [float(r.get("利润", 0) or 0) for r in d04_rows]

            avg_revenue = sum(revenues) / len(revenues) if revenues else 0
            avg_food_cost_pct = (sum(food_costs) / sum(revenues) * 100) if sum(revenues) > 0 else 0
            avg_labor_cost_pct = (sum(labor_costs) / sum(revenues) * 100) if sum(revenues) > 0 else 0
            avg_profit_pct = (sum(profits) / sum(revenues) * 100) if sum(revenues) > 0 else 0
            kpis["financial"] = {
                "avg_monthly_revenue_yuan": round(avg_revenue, 2),
                "avg_food_cost_pct": round(avg_food_cost_pct, 2),
                "avg_labor_cost_pct": round(avg_labor_cost_pct, 2),
                "avg_profit_pct": round(avg_profit_pct, 2),
                "months_of_data": len(revenues),
            }

        # Menu KPIs from D01
        d01_rows = await self._get_valid_rows("D01")
        if d01_rows:
            prices = [float(r.get("售价", 0) or 0) for r in d01_rows]
            costs = [float(r.get("成本价", 0) or 0) for r in d01_rows]
            valid_margins = [(p - c) / p * 100 for p, c in zip(prices, costs) if p > 0 and c > 0]
            kpis["menu"] = {
                "total_sku_count": len(d01_rows),
                "avg_price_yuan": round(sum(prices) / len(prices), 2) if prices else 0,
                "avg_gross_margin_pct": round(sum(valid_margins) / len(valid_margins), 2) if valid_margins else None,
            }

        # Member KPIs from D05
        d05_rows = await self._get_valid_rows("D05")
        if d05_rows:
            total_spend = [float(r.get("累计消费", 0) or 0) for r in d05_rows]
            kpis["members"] = {
                "total_member_count": len(d05_rows),
                "avg_total_spend_yuan": round(sum(total_spend) / len(total_spend), 2) if total_spend else 0,
            }

        # Store KPIs from D03
        d03_rows = await self._get_valid_rows("D03")
        if d03_rows:
            kpis["stores"] = {
                "store_count": len(d03_rows),
                "stores": [
                    {"name": r.get("门店名", ""), "area": r.get("面积", ""), "tables": r.get("桌台数", "")} for r in d03_rows
                ],
            }

        self._kpis = kpis
        return kpis

    # ── Stage 3: Baseline comparison ──────────────────────────────────────────

    async def _stage_baseline_compare(self) -> Dict[str, Any]:
        """Compare enterprise KPIs against industry baseline."""
        try:
            from ..services.baseline_data_service import BaselineDataService

            baseline = await BaselineDataService.get_industry_baseline()
        except Exception:
            baseline = {
                "avg_food_cost_pct": 35.0,
                "avg_labor_cost_pct": 25.0,
                "avg_profit_pct": 8.0,
                "avg_gross_margin_pct": 65.0,
            }

        self._baseline = baseline
        comparison: Dict[str, Any] = {}

        fin = self._kpis.get("financial", {})
        if fin:
            comparison["food_cost"] = {
                "enterprise": fin.get("avg_food_cost_pct"),
                "baseline": baseline.get("avg_food_cost_pct"),
                "delta": round((fin.get("avg_food_cost_pct", 0) or 0) - (baseline.get("avg_food_cost_pct") or 35.0), 2),
                "health_score": self._score_lower_is_better(
                    fin.get("avg_food_cost_pct"), baseline.get("avg_food_cost_pct", 35.0)
                ),
            }
            comparison["profit_margin"] = {
                "enterprise": fin.get("avg_profit_pct"),
                "baseline": baseline.get("avg_profit_pct"),
                "delta": round((fin.get("avg_profit_pct", 0) or 0) - (baseline.get("avg_profit_pct") or 8.0), 2),
                "health_score": self._score_higher_is_better(fin.get("avg_profit_pct"), baseline.get("avg_profit_pct", 8.0)),
            }

        menu = self._kpis.get("menu", {})
        if menu and menu.get("avg_gross_margin_pct"):
            comparison["gross_margin"] = {
                "enterprise": menu.get("avg_gross_margin_pct"),
                "baseline": baseline.get("avg_gross_margin_pct"),
                "delta": round((menu.get("avg_gross_margin_pct") or 0) - (baseline.get("avg_gross_margin_pct") or 65.0), 2),
                "health_score": self._score_higher_is_better(
                    menu.get("avg_gross_margin_pct"), baseline.get("avg_gross_margin_pct", 65.0)
                ),
            }

        return {"baseline_comparison": comparison}

    @staticmethod
    def _score_lower_is_better(value: Optional[float], baseline: float) -> int:
        """Score 0-100 where lower enterprise value = higher score."""
        if value is None:
            return 50
        delta_pct = (value - baseline) / baseline * 100
        if delta_pct <= -10:
            return 95
        elif delta_pct <= -5:
            return 85
        elif delta_pct <= 0:
            return 75
        elif delta_pct <= 5:
            return 60
        elif delta_pct <= 15:
            return 45
        return 30

    @staticmethod
    def _score_higher_is_better(value: Optional[float], baseline: float) -> int:
        """Score 0-100 where higher enterprise value = higher score."""
        if value is None:
            return 50
        delta_pct = (value - baseline) / baseline * 100 if baseline else 0
        if delta_pct >= 20:
            return 95
        elif delta_pct >= 10:
            return 85
        elif delta_pct >= 0:
            return 72
        elif delta_pct >= -10:
            return 58
        elif delta_pct >= -25:
            return 42
        return 28

    # ── Stage 4: Vector embedding ──────────────────────────────────────────────

    async def _stage_vector_embedding(self) -> Dict[str, Any]:
        """
        Embed text data into Qdrant collection 'enterprise_{store_id}'.
        Embeds: D01 dish descriptions, D04 financial summaries, D09 reviews.
        """
        try:
            from ..services.vector_db_service import VectorDBService

            vdb = VectorDBService()
            collection = f"enterprise_{self.store_id}"
            embedded_count = 0

            # Embed dish names (D01)
            d01_rows = await self._get_valid_rows("D01")
            if d01_rows:
                texts = [
                    f"菜品: {r.get('菜名', '')} 分类: {r.get('分类', '')} 售价: {r.get('售价', '')}" for r in d01_rows[:500]
                ]
                await vdb.upsert_texts(collection=collection, texts=texts, category="dish")
                embedded_count += len(texts)

            # Embed reviews (D09)
            d09_rows = await self._get_valid_rows("D09")
            if d09_rows:
                texts = [r.get("评价内容", "") for r in d09_rows[:1000] if r.get("评价内容")]
                await vdb.upsert_texts(collection=collection, texts=texts, category="review")
                embedded_count += len(texts)

            return {"collection": collection, "embedded_count": embedded_count}
        except Exception as exc:
            logger.warning("vector_embedding_skipped", error=str(exc))
            return {"embedded_count": 0, "note": "向量化跳过（VectorDB不可用）"}

    # ── Stage 5: Knowledge summary ─────────────────────────────────────────────

    async def _stage_knowledge_summary(self) -> Dict[str, Any]:
        """Use Claude to generate a 500-word brand knowledge summary."""
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic()

            kpi_json = json.dumps(self._kpis, ensure_ascii=False, indent=2)
            baseline_json = json.dumps(self._baseline, ensure_ascii=False)

            prompt = f"""你是一位资深餐饮管理顾问。基于以下企业经营数据，生成一份约500字的企业知识摘要，供AI Agent参考。

企业KPI数据：
{kpi_json}

行业基线参考：
{baseline_json}

请输出结构化摘要，包含：
1. 企业经营概况（2-3句）
2. 核心优势（2条）
3. 主要风险点（2条）
4. Agent重点关注方向（3条具体建议）

请直接输出摘要内容，不要加标题或前言。"""

            message = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            summary = message.content[0].text

            # Store summary in Qdrant if available
            try:
                from ..services.vector_db_service import VectorDBService

                vdb = VectorDBService()
                await vdb.upsert_texts(
                    collection=f"enterprise_{self.store_id}",
                    texts=[summary],
                    category="knowledge_summary",
                )
            except Exception as exc:
                logger.warning("onboarding.vector_upsert_failed", store_id=self.store_id, error=str(exc))

            return {"summary": summary, "word_count": len(summary)}
        except Exception as exc:
            logger.warning("knowledge_summary_skipped", error=str(exc))
            return {"summary": None, "note": "知识摘要跳过（LLM不可用）"}

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _get_valid_rows(self, data_type: str) -> List[Dict]:
        res = await self.db.execute(
            select(OnboardingRawData.row_data).where(
                OnboardingRawData.store_id == self.store_id,
                OnboardingRawData.data_type == data_type,
                OnboardingRawData.is_valid == True,
            )
        )
        return [row[0] for row in res.all()]

    async def _update_task_stage(self, stage: str) -> None:
        res = await self.db.execute(
            select(OnboardingTask).where(
                OnboardingTask.store_id == self.store_id,
                OnboardingTask.step == "build",
            )
        )
        task = res.scalar_one_or_none()
        if task:
            task.updated_at = datetime.utcnow()
            if task.extra:
                task.extra = {**task.extra, "stage": stage}
            else:
                task.extra = {"stage": stage}
            await self.db.commit()

    async def _mark_build_complete(self, result: Dict) -> None:
        res = await self.db.execute(
            select(OnboardingTask).where(
                OnboardingTask.store_id == self.store_id,
                OnboardingTask.step == "build",
            )
        )
        task = res.scalar_one_or_none()
        if task:
            task.status = "completed"
            task.updated_at = datetime.utcnow()
            existing_extra = task.extra or {}
            task.extra = {
                **existing_extra,
                "stage": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "kpis": self._kpis,
            }
            await self.db.commit()
