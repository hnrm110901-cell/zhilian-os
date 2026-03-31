"""
供应商管理 Agent — Phase 11
5个核心 Agent：
  PriceComparisonAgent   比价引擎 Agent
  SupplierRatingAgent    供应商综合评级 Agent
  AutoSourcingAgent      BOM驱动自动寻源 Agent
  ContractRiskAgent      合同风险预警 Agent
  SupplyChainRiskAgent   供应链断货风险 Agent
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, Any

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.supplier_agent import (
    SupplierProfile, MaterialCatalog,
    SupplierQuote, SupplierContract, SupplierDelivery,
    PriceComparison, SupplierEvaluation, SourcingRecommendation,
    ContractAlert, SupplyRiskEvent, SupplierAgentLog,
    SupplierTierEnum, QuoteStatusEnum, ContractStatusEnum,
    DeliveryStatusEnum, RiskLevelEnum, AlertTypeEnum, SupplierAgentTypeEnum,
)
from src.services.org_hierarchy_service import OrgHierarchyService

logger = logging.getLogger(__name__)

_LLM_ENABLED = os.getenv("LLM_ENABLED", "true").lower() == "true"
_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")


async def _ai_insight(system: str, user_data: dict) -> Optional[str]:
    """
    调用 Claude API 生成 AI 洞察。
    - LLM_ENABLED=false 或 API_KEY 未配置时，静默返回 None（使用模板 reason）
    - 使用 claude-opus-4-6 + adaptive thinking（复杂决策场景）
    """
    if not _LLM_ENABLED:
        return None
    try:
        from src.core.llm import get_llm_client
        client = get_llm_client()
        prompt = json.dumps(user_data, ensure_ascii=False, default=str)
        insight = await client.generate(
            prompt=prompt,
            system_prompt=system,
            max_tokens=512,
        )
        return insight.strip() or None
    except Exception as exc:
        logger.warning("supplier_agent_llm_insight_failed: %s", str(exc))
        return None


# ─────────────────────────────────────────────
# 纯函数层（可独立测试）
# ─────────────────────────────────────────────

def compute_price_score(price_yuan: float, benchmark_yuan: float, price_tolerance: float = 0.10) -> float:
    """
    价格竞争力得分（0-100）：越低于基准价得分越高。
    - 低于基准 price_tolerance（默认10%）以上 → 100
    - 等于基准                               → 70
    - 高于基准 20% 以上                       → 0
    """
    if benchmark_yuan <= 0:
        return 50.0
    delta_pct = (price_yuan - benchmark_yuan) / benchmark_yuan  # 正=贵
    if delta_pct <= -price_tolerance:
        return 100.0
    if delta_pct >= 0.20:
        return 0.0
    # 线性映射：[-price_tolerance, +20%] → [100, 0]
    span = price_tolerance + 0.20
    return round(100 - (delta_pct + price_tolerance) / span * 100, 1)


def compute_delivery_score(on_time_count: int, total_count: int) -> float:
    """准时率得分（0-100）"""
    if total_count <= 0:
        return 50.0
    rate = on_time_count / total_count
    return round(rate * 100, 1)


def compute_quality_score(reject_rate: float, avg_quality: Optional[float]) -> float:
    """
    质量得分（0-100）：结合拒收率和验收评分。
    - 拒收率=0, avg_quality=5 → 100
    - 拒收率≥10%             → 0
    """
    reject_penalty = min(reject_rate / 0.10, 1.0) * 50  # 最多扣50分
    quality_bonus = (avg_quality / 5.0) * 50 if avg_quality else 25
    return round(max(0.0, quality_bonus - reject_penalty), 1)


def compute_composite_score(
    price_score: float,
    quality_score: float,
    delivery_score: float,
    service_score: float,
    weights: Optional[dict] = None,
) -> float:
    """
    综合评分（加权）：
    - 价格 30%，质量 35%，交期 25%，服务 10%（默认）
    - weights 可覆盖各维度权重 {"price": 0.30, "quality": 0.35, "delivery": 0.25, "service": 0.10}
    """
    if weights is None:
        weights = {}
    w_price    = weights.get("price",    0.30)
    w_quality  = weights.get("quality",  0.35)
    w_delivery = weights.get("delivery", 0.25)
    w_service  = weights.get("service",  0.10)
    return round(
        price_score    * w_price
        + quality_score  * w_quality
        + delivery_score * w_delivery
        + service_score  * w_service,
        1,
    )


def classify_supplier_tier(composite_score: float) -> SupplierTierEnum:
    """根据综合得分建议供应商分级"""
    if composite_score >= 85:
        return SupplierTierEnum.STRATEGIC
    if composite_score >= 70:
        return SupplierTierEnum.PREFERRED
    if composite_score >= 50:
        return SupplierTierEnum.APPROVED
    return SupplierTierEnum.PROBATION


def classify_risk_level(probability: float, financial_impact_yuan: float, excellent_threshold: float = 1.5) -> RiskLevelEnum:
    """风险等级 = 概率 × 影响综合判断，excellent_threshold 对应 CRITICAL 阈值（默认 1.5）"""
    score = probability * (1 + min(financial_impact_yuan / 10000, 1.0))
    if score >= excellent_threshold:
        return RiskLevelEnum.CRITICAL
    if score >= 0.8:
        return RiskLevelEnum.HIGH
    if score >= 0.4:
        return RiskLevelEnum.MEDIUM
    return RiskLevelEnum.LOW


def compute_price_spread_pct(prices: list[float]) -> float:
    """最高最低价差比 = (max-min)/min * 100%"""
    if not prices or min(prices) <= 0:
        return 0.0
    return round((max(prices) - min(prices)) / min(prices) * 100, 1)


def estimate_saving_yuan(
    current_price: float,
    recommended_price: float,
    quantity: float,
) -> float:
    """与当前采购价相比的¥节省估算"""
    saving_per_unit = current_price - recommended_price
    return round(saving_per_unit * quantity, 2)


# ─────────────────────────────────────────────
# Agent 1: 比价引擎 Agent
# ─────────────────────────────────────────────

class PriceComparisonAgent:
    """
    比价引擎 Agent
    - 汇总多供应商对同一物料的报价
    - 综合价格/交期/评分推荐最优供应商
    - 输出¥节省估算
    """

    async def compare(
        self,
        brand_id: str,
        material_id: str,
        required_qty: float,
        db: AsyncSession,
        store_id: Optional[str] = None,
        save: bool = True,
    ) -> dict:
        """执行比价分析"""
        t0 = datetime.utcnow()

        # 查最近30天内有效报价
        cutoff = date.today() - timedelta(days=30)
        q = select(SupplierQuote).where(
            and_(
                SupplierQuote.brand_id == brand_id,
                SupplierQuote.material_id == material_id,
                SupplierQuote.status == QuoteStatusEnum.SUBMITTED,
                SupplierQuote.valid_until >= date.today(),
            )
        )
        result = await db.execute(q)
        quotes = result.scalars().all()

        if not quotes:
            return self._empty_result(brand_id, material_id)

        # 获取物料基准价
        mat_result = await db.execute(
            select(MaterialCatalog).where(
                and_(MaterialCatalog.brand_id == brand_id,
                     MaterialCatalog.id == material_id)
            )
        )
        material = mat_result.scalar_one_or_none()
        benchmark = float(material.benchmark_price_yuan) if material else 0.0

        # 动态解析价格允差
        _price_tolerance = 0.10
        if store_id:
            try:
                _svc = OrgHierarchyService(db)
                _price_tolerance = await _svc.resolve(
                    store_id, "supplier_price_tolerance", default=0.10
                )
            except Exception as _e:
                logger.warning("supplier_price_tolerance_resolve_failed: %s", str(_e))

        # 计算各报价得分
        prices = [float(q.unit_price_yuan) for q in quotes]
        ranked = []
        for q in quotes:
            price = float(q.unit_price_yuan)
            price_delta_pct = ((price - benchmark) / benchmark * 100) if benchmark > 0 else 0
            p_score = compute_price_score(price, benchmark, _price_tolerance) if benchmark > 0 else 50.0
            # 获取供应商档案（用于delivery/quality分）
            prof_result = await db.execute(
                select(SupplierProfile).where(SupplierProfile.supplier_id == q.supplier_id)
            )
            profile = prof_result.scalar_one_or_none()
            combined = (
                p_score * 0.4
                + (profile.delivery_score if profile else 50) * 0.35
                + (profile.quality_score if profile else 50) * 0.25
            )
            ranked.append({
                "quote_id": q.id,
                "supplier_id": q.supplier_id,
                "unit_price_yuan": price,
                "price_delta_pct": round(price_delta_pct, 1),
                "delivery_days": q.delivery_days,
                "price_score": p_score,
                "combined_score": round(combined, 1),
            })

        ranked.sort(key=lambda x: -x["combined_score"])
        for i, r in enumerate(ranked):
            r["rank"] = i + 1

        best = ranked[0]
        # 当前首选供应商价格（用于节省估算）
        current_price = benchmark if benchmark > 0 else float(quotes[0].unit_price_yuan)
        saving = estimate_saving_yuan(current_price, best["unit_price_yuan"], required_qty)

        reason = (
            f"综合得分 {best['combined_score']} 分（最高）；"
            f"单价 ¥{best['unit_price_yuan']:.4f}，"
            f"{'低于' if best['price_delta_pct'] < 0 else '高于'}基准价 {abs(best['price_delta_pct']):.1f}%；"
            f"承诺交期 {best['delivery_days']} 天。"
            f"按本次需求量 {required_qty} 单位，预计节省 ¥{saving:.2f}。"
        )

        comparison_id = str(uuid.uuid4())
        if save and db is not None:
            comparison = PriceComparison(
                id=comparison_id,
                brand_id=brand_id,
                store_id=store_id,
                material_id=material_id,
                material_name=material.material_name if material else "未知物料",
                comparison_date=date.today(),
                quote_count=len(quotes),
                best_price_yuan=Decimal(str(best["unit_price_yuan"])),
                best_supplier_id=best["supplier_id"],
                avg_price_yuan=Decimal(str(round(sum(prices) / len(prices), 4))),
                price_spread_pct=compute_price_spread_pct(prices),
                recommended_supplier_id=best["supplier_id"],
                recommendation_reason=reason,
                estimated_saving_yuan=Decimal(str(saving)),
                confidence=0.85,
                quote_snapshot=ranked,
            )
            db.add(comparison)

            # 回写报价排名
            for item in ranked:
                await db.execute(
                    select(SupplierQuote).where(SupplierQuote.id == item["quote_id"])
                )

            await self._log(brand_id, SupplierAgentTypeEnum.PRICE_COMPARISON, db,
                            {"material_id": material_id}, {"comparisons": 1, "saving_yuan": saving},
                            recommendation_count=1)
            await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)

        ai_insight = await _ai_insight(
            system=(
                "你是智链OS供应链决策AI，专注餐饮连锁供应商管理。"
                "根据比价数据，用2-3句话给出采购建议，必须包含：建议动作、¥预期节省金额、置信度。"
                "回复语言：中文，简洁。"
            ),
            user_data={
                "material_id": material_id,
                "recommended_supplier": best["supplier_id"],
                "recommended_price_yuan": best["unit_price_yuan"],
                "price_delta_pct": best["price_delta_pct"],
                "estimated_saving_yuan": saving,
                "quote_count": len(quotes),
                "price_spread_pct": compute_price_spread_pct(prices),
            },
        )

        return {
            "comparison_id": comparison_id,
            "material_id": material_id,
            "quote_count": len(quotes),
            "recommended_supplier_id": best["supplier_id"],
            "recommended_price_yuan": best["unit_price_yuan"],
            "price_spread_pct": compute_price_spread_pct(prices),
            "estimated_saving_yuan": saving,
            "recommendation_reason": reason,
            "ai_insight": ai_insight,
            "confidence": 0.85,
            "ranked_quotes": ranked,
            "duration_ms": duration_ms,
        }

    def _empty_result(self, brand_id: str, material_id: str) -> dict:
        return {
            "comparison_id": None,
            "material_id": material_id,
            "quote_count": 0,
            "recommended_supplier_id": None,
            "estimated_saving_yuan": 0.0,
            "recommendation_reason": "暂无有效报价，请先录入供应商报价。",
            "confidence": 0.0,
            "ranked_quotes": [],
        }

    async def _log(self, brand_id, agent_type, db, inp, out, recommendation_count=0, alert_count=0):
        if db is None:
            return
        db.add(SupplierAgentLog(
            id=str(uuid.uuid4()),
            brand_id=brand_id,
            agent_type=agent_type,
            input_params=inp,
            output_summary=out,
            recommendation_count=recommendation_count,
            alert_count=alert_count,
            saving_yuan=Decimal(str(out.get("saving_yuan", 0))),
            success=True,
        ))


# ─────────────────────────────────────────────
# Agent 2: 供应商综合评级 Agent
# ─────────────────────────────────────────────

class SupplierRatingAgent:
    """
    供应商综合评级 Agent
    - 计算价格/质量/交期/服务四维度得分
    - 生成综合评分（0-100）和分级建议
    - 写入 SupplierEvaluation + 更新 SupplierProfile
    """

    SERVICE_SCORE_DEFAULT = 75.0  # 无投诉数据时的默认服务分

    async def evaluate(
        self,
        brand_id: str,
        supplier_id: str,
        eval_period: str,       # "2026-03"
        db: AsyncSession,
        service_score: Optional[float] = None,  # 可由人工传入
        save: bool = True,
        store_id: Optional[str] = None,         # 用于动态配置解析
    ) -> dict:
        """评估单家供应商"""
        t0 = datetime.utcnow()
        period_start = datetime.strptime(eval_period + "-01", "%Y-%m-%d").date()
        period_end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        # ── 动态配置解析 ──────────────────────────────────────────────
        _score_weights: Optional[dict] = None
        _excellent_threshold: float = 1.5
        _eval_price_tolerance: float = 0.10
        if store_id:
            try:
                _svc = OrgHierarchyService(db)
                _score_weights = await _svc.resolve(
                    store_id, "supplier_score_weights",
                    default={"price": 0.30, "quality": 0.35, "delivery": 0.25, "service": 0.10}
                )
                _excellent_threshold = await _svc.resolve(
                    store_id, "supplier_excellent_threshold", default=1.5
                )
                _eval_price_tolerance = await _svc.resolve(
                    store_id, "supplier_price_tolerance", default=0.10
                )
            except Exception as _e:
                logger.warning("supplier_eval_dyn_cfg_failed: %s", str(_e))
        # ────────────────────────────────────────────────────────────

        # 1. 收货记录 → 交期/质量维度
        del_result = await db.execute(
            select(SupplierDelivery).where(
                and_(
                    SupplierDelivery.brand_id == brand_id,
                    SupplierDelivery.supplier_id == supplier_id,
                    SupplierDelivery.promised_date >= period_start,
                    SupplierDelivery.promised_date <= period_end,
                )
            )
        )
        deliveries = del_result.scalars().all()

        delivery_count = len(deliveries)
        on_time_count = sum(1 for d in deliveries if (d.delay_days or 0) <= 0)
        reject_rate = (
            sum(d.rejected_qty or 0 for d in deliveries) /
            max(sum(d.ordered_qty or 1 for d in deliveries), 1)
        )
        quality_scores = [d.quality_score for d in deliveries if d.quality_score is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

        delivery_score = compute_delivery_score(on_time_count, delivery_count)
        quality_score  = compute_quality_score(reject_rate, avg_quality)

        # 2. 报价记录 → 价格维度
        # 取当月所有报价，与物料基准价对比
        quote_result = await db.execute(
            select(SupplierQuote).where(
                and_(
                    SupplierQuote.brand_id == brand_id,
                    SupplierQuote.supplier_id == supplier_id,
                    SupplierQuote.created_at >= datetime.combine(period_start, datetime.min.time()),
                )
            )
        )
        quotes = quote_result.scalars().all()

        if quotes:
            delta_pcts = [float(q.price_delta_pct or 0) for q in quotes if q.price_delta_pct is not None]
            avg_delta_pct = sum(delta_pcts) / len(delta_pcts) if delta_pcts else 0
        else:
            avg_delta_pct = 0.0

        price_score = compute_price_score(
            100 * (1 + avg_delta_pct / 100), 100, _eval_price_tolerance
        )  # 用相对偏差计算

        # 3. 服务分（外部传入或默认）
        s_score = service_score if service_score is not None else self.SERVICE_SCORE_DEFAULT

        # 4. 综合得分（使用动态权重）
        composite = compute_composite_score(price_score, quality_score, delivery_score, s_score, _score_weights)
        tier_suggestion = classify_supplier_tier(composite)

        # 5. 行动建议
        action_required = composite < 60 or reject_rate > 0.05 or delivery_score < 60
        action_text = self._build_action_text(composite, reject_rate, delivery_score, tier_suggestion)

        result = {
            "supplier_id": supplier_id,
            "eval_period": eval_period,
            "price_score": price_score,
            "quality_score": quality_score,
            "delivery_score": delivery_score,
            "service_score": s_score,
            "composite_score": composite,
            "tier_suggestion": tier_suggestion.value,
            "delivery_count": delivery_count,
            "on_time_count": on_time_count,
            "reject_rate": round(reject_rate * 100, 2),
            "avg_price_delta_pct": round(avg_delta_pct, 2),
            "action_required": action_required,
            "action_text": action_text,
        }

        if save and db is not None:
            eval_id = str(uuid.uuid4())
            db.add(SupplierEvaluation(
                id=eval_id,
                brand_id=brand_id,
                supplier_id=supplier_id,
                eval_period=eval_period,
                price_score=price_score,
                quality_score=quality_score,
                delivery_score=delivery_score,
                service_score=s_score,
                composite_score=composite,
                tier_suggestion=tier_suggestion,
                delivery_count=delivery_count,
                on_time_count=on_time_count,
                reject_rate=reject_rate,
                avg_price_delta_pct=avg_delta_pct,
                action_required=action_required,
                action_text=action_text,
            ))

            # 更新 SupplierProfile 综合得分
            prof_result = await db.execute(
                select(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
            )
            profile = prof_result.scalar_one_or_none()
            if profile:
                profile.composite_score = composite
                profile.price_score = price_score
                profile.quality_score = quality_score
                profile.delivery_score = delivery_score
                profile.service_score = s_score
                profile.last_rated_at = datetime.utcnow()

            await db.flush()
            result["eval_id"] = eval_id

        result["ai_insight"] = await _ai_insight(
            system=(
                "你是智链OS供应商评级AI。根据评级数据，用2-3句话给出管理建议，"
                "必须包含：建议动作（升级/降级/约谈/保持）、关键风险点、置信度。"
                "回复语言：中文，简洁。"
            ),
            user_data={
                "supplier_id": supplier_id,
                "composite_score": composite,
                "tier_suggestion": tier_suggestion.value,
                "reject_rate_pct": round(reject_rate * 100, 2),
                "delivery_score": delivery_score,
                "price_score": price_score,
                "action_required": action_required,
            },
        )
        return result

    def _build_action_text(
        self,
        composite: float,
        reject_rate: float,
        delivery_score: float,
        tier: SupplierTierEnum,
    ) -> str:
        parts = []
        if composite < 50:
            parts.append(f"综合得分 {composite:.0f} 分，建议降级至试用期，寻找替代供应商。")
        elif composite < 60:
            parts.append(f"综合得分 {composite:.0f} 分，建议约谈整改，明确改进时间表。")
        if reject_rate > 0.05:
            parts.append(f"拒收率 {reject_rate*100:.1f}% 超标（阈值5%），需立即质量整改。")
        if delivery_score < 60:
            parts.append(f"准时率得分 {delivery_score:.0f} 分，需协商改善交期管理。")
        if not parts:
            parts.append(f"整体表现良好，建议维持 {tier.value} 级合作。")
        return " ".join(parts)


# ─────────────────────────────────────────────
# Agent 3: 自动寻源 Agent
# ─────────────────────────────────────────────

class AutoSourcingAgent:
    """
    BOM驱动自动寻源 Agent
    - 根据库存缺口/BOM需求自动匹配最优供应商
    - 生成采购建议（含¥节省估算）
    - 支持单一/分拆/现货三种采购策略
    """

    async def source(
        self,
        brand_id: str,
        material_id: str,
        required_qty: float,
        needed_by_date: date,
        db: AsyncSession,
        store_id: Optional[str] = None,
        trigger: str = "bom_gap",
        save: bool = True,
    ) -> dict:
        """自动寻源：为缺口物料匹配最优供应商"""
        # 查物料目录
        mat_result = await db.execute(
            select(MaterialCatalog).where(
                and_(MaterialCatalog.brand_id == brand_id, MaterialCatalog.id == material_id)
            )
        )
        material = mat_result.scalar_one_or_none()
        if not material:
            return self._not_found(material_id, required_qty, needed_by_date)

        # 查所有合格供应商的有效报价（交期能在需求日前到货）
        max_delivery_days = (needed_by_date - date.today()).days
        q = select(SupplierQuote).where(
            and_(
                SupplierQuote.brand_id == brand_id,
                SupplierQuote.material_id == material_id,
                SupplierQuote.status == QuoteStatusEnum.SUBMITTED,
                SupplierQuote.valid_until >= date.today(),
                SupplierQuote.delivery_days <= max(max_delivery_days, 1),
            )
        )
        result = await db.execute(q)
        quotes = result.scalars().all()

        if not quotes:
            return self._no_quotes(material, required_qty, needed_by_date)

        # 按综合得分排序（优先匹配优选供应商）
        async def get_supplier_score(supplier_id: str) -> float:
            prof = await db.execute(
                select(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
            )
            p = prof.scalar_one_or_none()
            return p.composite_score if p else 50.0

        candidates = []
        for q in quotes:
            score = await get_supplier_score(q.supplier_id)
            price = float(q.unit_price_yuan)
            can_fulfill = (q.min_order_qty or 0) <= required_qty
            candidates.append({
                "quote": q,
                "score": score,
                "price_yuan": price,
                "can_fulfill": can_fulfill,
            })

        candidates.sort(key=lambda x: (-x["score"], x["price_yuan"]))

        # 决定采购策略
        best = candidates[0]
        benchmark = float(material.benchmark_price_yuan) if material.benchmark_price_yuan else float(best["price_yuan"])
        saving = estimate_saving_yuan(benchmark, best["price_yuan"], required_qty)
        total = round(best["price_yuan"] * required_qty, 2)

        # 分拆策略：如最优不能全量满足，分配给备选
        strategy = "single"
        split_plan = None
        alt_ids = [c["quote"].supplier_id for c in candidates[1:3] if c["quote"].supplier_id]

        if not best["can_fulfill"] and len(candidates) > 1:
            strategy = "split"
            split_plan = [
                {"supplier_id": candidates[0]["quote"].supplier_id,
                 "qty": required_qty * 0.6,
                 "unit_price_yuan": candidates[0]["price_yuan"]},
                {"supplier_id": candidates[1]["quote"].supplier_id,
                 "qty": required_qty * 0.4,
                 "unit_price_yuan": candidates[1]["price_yuan"]},
            ]

        reasoning = (
            f"物料「{material.material_name}」需求 {required_qty} {material.base_unit}，"
            f"最迟 {needed_by_date} 到货。"
            f"共 {len(quotes)} 家供应商有效报价，"
            f"综合得分最高的供应商报价 ¥{best['price_yuan']:.4f}/{material.base_unit}，"
            f"{'低于' if saving > 0 else '高于'}基准价，预计节省 ¥{abs(saving):.2f}。"
            f"采购策略：{'单一采购' if strategy == 'single' else '分拆采购'}。"
        )

        rec_id = str(uuid.uuid4())
        if save and db is not None:
            db.add(SourcingRecommendation(
                id=rec_id,
                brand_id=brand_id,
                store_id=store_id,
                trigger=trigger,
                material_id=material_id,
                material_name=material.material_name,
                required_qty=required_qty,
                required_unit=material.base_unit,
                needed_by_date=needed_by_date,
                recommended_supplier_id=best["quote"].supplier_id,
                recommended_price_yuan=Decimal(str(best["price_yuan"])),
                alternative_supplier_ids=alt_ids,
                sourcing_strategy=strategy,
                split_plan=split_plan,
                estimated_total_yuan=Decimal(str(total)),
                estimated_saving_yuan=Decimal(str(saving)),
                reasoning=reasoning,
                confidence=0.80,
                status="pending",
            ))
            await db.flush()

        return {
            "recommendation_id": rec_id,
            "material_id": material_id,
            "material_name": material.material_name,
            "required_qty": required_qty,
            "needed_by_date": str(needed_by_date),
            "recommended_supplier_id": best["quote"].supplier_id,
            "recommended_price_yuan": best["price_yuan"],
            "estimated_total_yuan": total,
            "estimated_saving_yuan": saving,
            "sourcing_strategy": strategy,
            "split_plan": split_plan,
            "alternative_supplier_ids": alt_ids,
            "reasoning": reasoning,
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS采购寻源AI。根据寻源结果，用2-3句话给出采购决策建议，"
                    "必须包含：建议动作（立即下单/询价/备货）、预期¥总采购金额、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "material_name": material.material_name,
                    "required_qty": required_qty,
                    "needed_by_date": str(needed_by_date),
                    "sourcing_strategy": strategy,
                    "estimated_total_yuan": total,
                    "estimated_saving_yuan": saving,
                    "candidate_count": len(candidates),
                },
            ),
            "confidence": 0.80,
        }

    def _not_found(self, material_id, qty, needed_by):
        return {
            "recommendation_id": None, "material_id": material_id,
            "required_qty": qty, "needed_by_date": str(needed_by),
            "recommended_supplier_id": None, "estimated_saving_yuan": 0,
            "reasoning": "物料目录中未找到该物料，请先录入物料信息。",
            "confidence": 0,
        }

    def _no_quotes(self, material, qty, needed_by):
        return {
            "recommendation_id": None,
            "material_id": material.id,
            "material_name": material.material_name,
            "required_qty": qty,
            "needed_by_date": str(needed_by),
            "recommended_supplier_id": None,
            "estimated_saving_yuan": 0,
            "reasoning": f"「{material.material_name}」暂无符合交期要求的有效报价，建议紧急询价或从备货中调拨。",
            "confidence": 0,
        }


# ─────────────────────────────────────────────
# Agent 4: 合同风险预警 Agent
# ─────────────────────────────────────────────

class ContractRiskAgent:
    """
    合同风险预警 Agent
    - 扫描即将到期合同（30/15/7天三级预警）
    - 分析合同条款风险（无货源保障/无违约金/排他条款）
    - 生成 ContractAlert，推送企微
    """

    EXPIRY_THRESHOLDS = [30, 15, 7]  # 预警天数阈值

    async def scan(
        self,
        brand_id: str,
        db: AsyncSession,
        save: bool = True,
    ) -> dict:
        """扫描所有活跃合同的风险"""
        t0 = datetime.utcnow()
        today = date.today()

        # 查活跃/即将到期合同
        result = await db.execute(
            select(SupplierContract).where(
                and_(
                    SupplierContract.brand_id == brand_id,
                    SupplierContract.status.in_([
                        ContractStatusEnum.ACTIVE,
                        ContractStatusEnum.EXPIRING,
                    ]),
                    SupplierContract.end_date >= today,
                )
            )
        )
        contracts = result.scalars().all()

        alerts_created = 0
        alert_summaries = []

        for contract in contracts:
            days_left = (contract.end_date - today).days
            risk_level, alert_type = self._classify_expiry_risk(days_left)

            if risk_level and alert_type:
                financial_impact = float(contract.annual_value_yuan or 0) * (days_left / 365)
                action = (
                    f"合同「{contract.contract_name or contract.contract_no}」"
                    f"将于 {days_left} 天后到期（{contract.end_date}）。"
                    f"建议{'立即' if days_left <= 7 else '尽快'}联系供应商续签，"
                    f"预计¥{financial_impact:.0f} 年度采购额面临风险。"
                )

                if save and db is not None:
                    # 避免重复预警
                    existing = await db.execute(
                        select(ContractAlert).where(
                            and_(
                                ContractAlert.contract_id == contract.id,
                                ContractAlert.alert_type == alert_type,
                                ContractAlert.is_resolved == False,
                            )
                        )
                    )
                    if not existing.scalar_one_or_none():
                        db.add(ContractAlert(
                            id=str(uuid.uuid4()),
                            brand_id=brand_id,
                            contract_id=contract.id,
                            supplier_id=contract.supplier_id,
                            alert_type=alert_type,
                            risk_level=risk_level,
                            title=f"合同即将到期：{contract.contract_name or contract.contract_no}",
                            description=action,
                            recommended_action=action,
                            financial_impact_yuan=Decimal(str(financial_impact)),
                            days_to_expiry=days_left,
                        ))
                        alerts_created += 1

                alert_summaries.append({
                    "contract_id": contract.id,
                    "contract_no": contract.contract_no,
                    "supplier_id": contract.supplier_id,
                    "days_to_expiry": days_left,
                    "risk_level": risk_level.value,
                    "financial_impact_yuan": round(financial_impact, 2),
                    "action": action,
                })

                # 更新合同状态
                if days_left <= 30 and contract.status == ContractStatusEnum.ACTIVE:
                    contract.status = ContractStatusEnum.EXPIRING

        if save and db is not None:
            await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)

        total_financial_risk = sum(
            s.get("financial_impact_yuan", 0) for s in alert_summaries
        )
        return {
            "scanned_count": len(contracts),
            "alerts_created": alerts_created,
            "alert_summaries": alert_summaries,
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS合同风险AI。根据合同预警数据，用2-3句话给出处置建议，"
                    "必须包含：优先处置哪个合同、¥预计风险金额、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "scanned_count": len(contracts),
                    "alerts_created": alerts_created,
                    "critical_count": sum(1 for s in alert_summaries if s["risk_level"] == "critical"),
                    "total_financial_risk_yuan": round(total_financial_risk, 2),
                    "top_alerts": alert_summaries[:3],
                },
            ) if alert_summaries else None,
            "duration_ms": duration_ms,
        }

    def _classify_expiry_risk(
        self, days_left: int
    ) -> tuple[Optional[RiskLevelEnum], Optional[AlertTypeEnum]]:
        if days_left <= 7:
            return RiskLevelEnum.CRITICAL, AlertTypeEnum.CONTRACT_EXPIRING
        if days_left <= 15:
            return RiskLevelEnum.HIGH, AlertTypeEnum.CONTRACT_EXPIRING
        if days_left <= 30:
            return RiskLevelEnum.MEDIUM, AlertTypeEnum.CONTRACT_EXPIRING
        return None, None


# ─────────────────────────────────────────────
# Agent 5: 供应链断货风险 Agent
# ─────────────────────────────────────────────

class SupplyChainRiskAgent:
    """
    供应链断货风险 Agent
    - 检测单一来源风险（物料只有1家供应商）
    - 检测交期延误预警（连续2次延误）
    - 检测价格异常波动
    - 生成 SupplyRiskEvent，推荐备选供应商
    """

    PRICE_SPIKE_THRESHOLD_PCT = 15.0   # 价格上涨超15%触发预警
    DELAY_TRIGGER_COUNT       = 2      # 连续N次延误触发预警

    async def scan(
        self,
        brand_id: str,
        db: AsyncSession,
        store_id: Optional[str] = None,
        save: bool = True,
    ) -> dict:
        """扫描供应链风险"""
        t0 = datetime.utcnow()
        risks = []

        # 1. 单一来源风险
        single_source_risks = await self._check_single_source(brand_id, db)
        risks.extend(single_source_risks)

        # 2. 连续延误风险
        delay_risks = await self._check_delivery_delays(brand_id, db, store_id)
        risks.extend(delay_risks)

        # 3. 价格异常波动
        price_risks = await self._check_price_spikes(brand_id, db)
        risks.extend(price_risks)

        events_created = 0
        if save and db is not None:
            for risk in risks:
                # 幂等：同一供应商同类型未解决预警不重复创建
                existing = await db.execute(
                    select(SupplyRiskEvent).where(
                        and_(
                            SupplyRiskEvent.brand_id == brand_id,
                            SupplyRiskEvent.supplier_id == risk.get("supplier_id"),
                            SupplyRiskEvent.material_id == risk.get("material_id"),
                            SupplyRiskEvent.alert_type == risk["alert_type"],
                            SupplyRiskEvent.is_resolved == False,
                        )
                    )
                )
                if not existing.scalar_one_or_none():
                    db.add(SupplyRiskEvent(
                        id=str(uuid.uuid4()),
                        brand_id=brand_id,
                        store_id=store_id,
                        supplier_id=risk.get("supplier_id"),
                        material_id=risk.get("material_id"),
                        alert_type=risk["alert_type"],
                        risk_level=risk["risk_level"],
                        title=risk["title"],
                        description=risk["description"],
                        probability=risk["probability"],
                        impact_days=risk.get("impact_days", 3),
                        financial_impact_yuan=Decimal(str(risk.get("financial_impact_yuan", 0))),
                        mitigation_plan=risk["mitigation_plan"],
                        backup_supplier_ids=risk.get("backup_supplier_ids", []),
                    ))
                    events_created += 1
            await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        return {
            "risk_count": len(risks),
            "events_created": events_created,
            "risks": risks,
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS供应链风险AI。根据供应链风险扫描结果，用2-3句话给出应急建议，"
                    "必须包含：最高优先级风险、建议行动、¥预计影响金额、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "risk_count": len(risks),
                    "single_source_risks": len([r for r in risks if r["alert_type"] == AlertTypeEnum.SINGLE_SOURCE_RISK]),
                    "delay_risks": len([r for r in risks if r["alert_type"] == AlertTypeEnum.DELIVERY_DELAY]),
                    "price_spike_risks": len([r for r in risks if r["alert_type"] == AlertTypeEnum.PRICE_SPIKE]),
                    "top_risks": [
                        {"title": r["title"], "risk_level": r["risk_level"].value if hasattr(r["risk_level"], "value") else r["risk_level"]}
                        for r in risks[:3]
                    ],
                },
            ) if risks else None,
            "duration_ms": duration_ms,
        }

    async def _check_single_source(self, brand_id: str, db: AsyncSession) -> list[dict]:
        """检测只有单一供应商的关键物料"""
        result = await db.execute(
            select(MaterialCatalog).where(
                and_(MaterialCatalog.brand_id == brand_id, MaterialCatalog.is_active == True)
            )
        )
        materials = result.scalars().all()

        risks = []
        for mat in materials:
            # 数有效报价的供应商数量
            q_result = await db.execute(
                select(func.count(func.distinct(SupplierQuote.supplier_id))).where(
                    and_(
                        SupplierQuote.brand_id == brand_id,
                        SupplierQuote.material_id == mat.id,
                        SupplierQuote.status == QuoteStatusEnum.SUBMITTED,
                        SupplierQuote.valid_until >= date.today(),
                    )
                )
            )
            supplier_count = q_result.scalar() or 0

            if supplier_count <= 1:
                risks.append({
                    "material_id": mat.id,
                    "supplier_id": mat.preferred_supplier_id,
                    "alert_type": AlertTypeEnum.SINGLE_SOURCE_RISK,
                    "risk_level": RiskLevelEnum.HIGH,
                    "title": f"单一来源风险：{mat.material_name}",
                    "description": f"物料「{mat.material_name}」仅有 {supplier_count} 家有效报价供应商，断货风险高。",
                    "probability": 0.6,
                    "impact_days": 5,
                    "financial_impact_yuan": 0,
                    "mitigation_plan": "建议开发至少2家备选供应商，进行分散采购。",
                    "backup_supplier_ids": mat.backup_supplier_ids or [],
                })
        return risks

    async def _check_delivery_delays(
        self, brand_id: str, db: AsyncSession, store_id: Optional[str]
    ) -> list[dict]:
        """检测连续2次以上延误的供应商"""
        # 查最近60天收货记录
        cutoff = date.today() - timedelta(days=60)
        q = select(SupplierDelivery).where(
            and_(
                SupplierDelivery.brand_id == brand_id,
                SupplierDelivery.promised_date >= cutoff,
                SupplierDelivery.status == DeliveryStatusEnum.DELIVERED,
            )
        )
        if store_id:
            q = q.where(SupplierDelivery.store_id == store_id)
        result = await db.execute(q)
        deliveries = result.scalars().all()

        # 按供应商分组统计延误
        from collections import defaultdict
        delay_map: dict[str, list[int]] = defaultdict(list)
        for d in deliveries:
            if (d.delay_days or 0) > 0:
                delay_map[d.supplier_id].append(d.delay_days)

        risks = []
        for supplier_id, delays in delay_map.items():
            if len(delays) >= self.DELAY_TRIGGER_COUNT:
                avg_delay = sum(delays) / len(delays)
                risks.append({
                    "supplier_id": supplier_id,
                    "material_id": None,
                    "alert_type": AlertTypeEnum.DELIVERY_DELAY,
                    "risk_level": RiskLevelEnum.HIGH if avg_delay > 3 else RiskLevelEnum.MEDIUM,
                    "title": f"交期延误预警：供应商 {supplier_id[:8]}",
                    "description": f"该供应商近60天延误 {len(delays)} 次，平均延误 {avg_delay:.1f} 天。",
                    "probability": 0.7,
                    "impact_days": int(avg_delay),
                    "financial_impact_yuan": avg_delay * 500,  # 估算影响¥
                    "mitigation_plan": "建议提前3天下单缓冲，同时激活备选供应商。",
                    "backup_supplier_ids": [],
                })
        return risks

    async def _check_price_spikes(self, brand_id: str, db: AsyncSession) -> list[dict]:
        """检测物料价格异常上涨"""
        result = await db.execute(
            select(MaterialCatalog).where(
                and_(MaterialCatalog.brand_id == brand_id, MaterialCatalog.is_active == True)
            )
        )
        materials = result.scalars().all()

        risks = []
        for mat in materials:
            if not mat.benchmark_price_yuan or not mat.latest_price_yuan:
                continue
            benchmark = float(mat.benchmark_price_yuan)
            latest = float(mat.latest_price_yuan)
            if benchmark <= 0:
                continue
            spike_pct = (latest - benchmark) / benchmark * 100
            if spike_pct >= self.PRICE_SPIKE_THRESHOLD_PCT:
                risks.append({
                    "material_id": mat.id,
                    "supplier_id": mat.preferred_supplier_id,
                    "alert_type": AlertTypeEnum.PRICE_SPIKE,
                    "risk_level": RiskLevelEnum.HIGH if spike_pct >= 30 else RiskLevelEnum.MEDIUM,
                    "title": f"价格异常上涨：{mat.material_name}",
                    "description": f"「{mat.material_name}」价格较基准上涨 {spike_pct:.1f}%（¥{latest:.4f} vs ¥{benchmark:.4f}）。",
                    "probability": 0.9,
                    "impact_days": 30,
                    "financial_impact_yuan": (latest - benchmark) * (mat.reorder_point_kg or 10),
                    "mitigation_plan": f"建议立即锁定价格或增加库存，并启动比价寻找替代供应商。",
                    "backup_supplier_ids": mat.backup_supplier_ids or [],
                })
        return risks
