"""
菜品研发 Agent — Phase 10
包含5个核心 Agent：
  CostSimAgent      成本仿真 Agent
  PilotRecAgent     试点推荐 Agent
  ReviewAgent       复盘优化 Agent
  LaunchAssistAgent 发布助手 Agent
  RiskAlertAgent    风险预警 Agent
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta
from typing import Optional, Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dish_rd import (
    Dish, DishVersion, Recipe, RecipeVersion, RecipeItem,
    Ingredient, SemiProduct, CostModel, SupplyAssessment,
    PilotTest, LaunchProject, DishFeedback, RetrospectiveReport,
    DishRdAgentLog,
    DishStatusEnum, PilotStatusEnum, LaunchStatusEnum, LaunchTypeEnum,
    LifecycleAssessmentEnum, FeedbackTypeEnum, DishRdAgentTypeEnum,
    SupplyRecommendationEnum, RiskLevelEnum,
)
from src.services.org_hierarchy_service import OrgHierarchyService


# ─────────────────────────────────────────────
# Agent 1: 成本仿真 Agent
# ─────────────────────────────────────────────

class CostSimAgent:
    """
    成本仿真 Agent
    - 基于 RecipeItem BOM 实时计算单份成本与毛利
    - 生成多定价方案对比
    - 原料涨价压力测试
    """

    DEFAULT_LABOR_COST_YUAN    = 2.5   # 默认人效成本/份
    DEFAULT_UTILITY_COST_YUAN  = 0.5   # 默认能耗/份
    TARGET_MARGIN_RATES        = [0.55, 0.60, 0.65, 0.70]

    async def simulate(
        self,
        recipe_version_id: str,
        dish_id: str,
        brand_id: str,
        db: AsyncSession,
        price_sensitivity_pcts: Optional[list[float]] = None,   # 原料涨价测试 [-10%, +10%, +20%]
        save: bool = True,
    ) -> dict:
        """计算成本并生成多定价方案"""
        # 获取配方明细
        items_result = await db.execute(
            select(RecipeItem).where(RecipeItem.recipe_version_id == recipe_version_id)
        )
        items = items_result.scalars().all()

        if not items:
            return self._empty_result(recipe_version_id, dish_id)

        # 逐行计算原料成本
        item_details = []
        ingredient_cost_total = 0.0
        semi_product_cost_total = 0.0

        for item in items:
            unit_price = float(item.unit_price_snapshot or 0)
            qty        = float(item.quantity or 0)
            loss_rate  = float(item.loss_rate_snapshot or 0.05)
            # 有效用量 = 配方用量 / 出成率(考虑损耗)
            effective_qty = qty / (1 - loss_rate) if loss_rate < 1 else qty
            line_cost     = unit_price * effective_qty

            item_details.append({
                "item_type":         item.item_type,
                "item_id":           item.item_id,
                "item_name":         item.item_name_snapshot,
                "quantity":          qty,
                "unit":              item.unit,
                "unit_price_yuan":   unit_price,
                "loss_rate":         loss_rate,
                "effective_qty":     round(effective_qty, 4),
                "line_cost_yuan":    round(line_cost, 4),
            })

            if item.item_type == "ingredient":
                ingredient_cost_total += line_cost
            else:
                semi_product_cost_total += line_cost

        total_ingredient = ingredient_cost_total + semi_product_cost_total
        labor_cost       = self.DEFAULT_LABOR_COST_YUAN
        utility_cost     = self.DEFAULT_UTILITY_COST_YUAN
        total_cost       = total_ingredient + labor_cost + utility_cost

        # 多定价方案
        price_scenarios = []
        for rate in self.TARGET_MARGIN_RATES:
            if total_cost > 0 and rate < 1:
                suggest_price = round(total_cost / (1 - rate), 1)
                margin_amount = round(suggest_price * rate, 2)
            else:
                suggest_price = 0
                margin_amount = 0
            price_scenarios.append({
                "target_margin_rate": rate,
                "suggested_price_yuan": suggest_price,
                "margin_amount_yuan": margin_amount,
            })

        # 取60%毛利率作为默认建议售价
        suggested_price = price_scenarios[1]["suggested_price_yuan"]
        margin_amount   = price_scenarios[1]["margin_amount_yuan"]
        margin_rate     = 0.60

        # 原料涨价压力测试
        stress_tests = []
        for pct in (price_sensitivity_pcts or [0.1, 0.2]):
            stressed_cost     = total_cost + total_ingredient * pct
            stressed_margin   = (suggested_price - stressed_cost) / suggested_price if suggested_price > 0 else 0
            stress_tests.append({
                "price_change_pct": pct,
                "stressed_total_cost": round(stressed_cost, 4),
                "stressed_margin_rate": round(stressed_margin, 4),
                "margin_delta": round(stressed_margin - margin_rate, 4),
            })

        result = {
            "recipe_version_id":         recipe_version_id,
            "dish_id":                   dish_id,
            "item_details":              item_details,
            "ingredient_cost_total":     round(ingredient_cost_total, 4),
            "semi_product_cost_total":   round(semi_product_cost_total, 4),
            "labor_cost_estimate":       labor_cost,
            "utility_cost_estimate":     utility_cost,
            "total_cost":                round(total_cost, 4),
            "suggested_price_yuan":      suggested_price,
            "margin_amount_yuan":        margin_amount,
            "margin_rate":               margin_rate,
            "price_scenarios":           price_scenarios,
            "stress_tests":              stress_tests,
            "calculated_at":             datetime.utcnow().isoformat(),
        }

        if save and db:
            cost_model = CostModel(
                id                      = str(uuid.uuid4()),
                dish_id                 = dish_id,
                recipe_version_id       = recipe_version_id,
                brand_id                = brand_id,
                calculation_basis       = "theoretical",
                ingredient_cost_total   = ingredient_cost_total,
                semi_product_cost_total = semi_product_cost_total,
                labor_cost_estimate     = labor_cost,
                utility_cost_estimate   = utility_cost,
                total_cost              = total_cost,
                suggested_price_yuan    = suggested_price,
                margin_amount_yuan      = margin_amount,
                margin_rate             = margin_rate,
                price_scenarios         = price_scenarios,
                item_details            = item_details,
                calculated_at           = datetime.utcnow(),
            )
            db.add(cost_model)
            await db.commit()
            result["cost_model_id"] = cost_model.id

        return result

    def _empty_result(self, recipe_version_id: str, dish_id: str) -> dict:
        return {
            "recipe_version_id": recipe_version_id,
            "dish_id": dish_id,
            "item_details": [],
            "ingredient_cost_total": 0,
            "semi_product_cost_total": 0,
            "total_cost": 0,
            "suggested_price_yuan": 0,
            "margin_rate": 0,
            "price_scenarios": [],
            "stress_tests": [],
            "calculated_at": datetime.utcnow().isoformat(),
        }


# ─────────────────────────────────────────────
# Agent 2: 试点推荐 Agent
# ─────────────────────────────────────────────

class PilotRecAgent:
    """
    试点推荐 Agent
    - 根据菜品画像（价格带、口味、适用场景）推荐最适合的试点门店
    - 评分依据：菜品类型匹配度、历史新品接受率、门店客群结构
    - 输出推荐门店列表 + 推荐理由 + 建议试点门店数
    """

    MIN_PILOT_STORES      = 3
    MAX_PILOT_STORES      = 8
    DEFAULT_PILOT_DAYS    = 21

    async def recommend_stores(
        self,
        dish_id: str,
        brand_id: str,
        db: AsyncSession,
        available_store_profiles: Optional[list[dict]] = None,  # [{store_id, region, level, new_dish_acceptance_rate}]
        top_n: int = 5,
    ) -> dict:
        """推荐试点门店"""
        # 获取菜品信息
        dish_result = await db.execute(select(Dish).where(Dish.id == dish_id))
        dish = dish_result.scalars().first()
        if not dish:
            return {"error": "菜品不存在", "dish_id": dish_id}

        # 若无实际门店画像，使用示例样本（离线模式）
        if not available_store_profiles:
            available_store_profiles = self._sample_store_profiles()

        # 评分逻辑
        scored_stores = []
        for store in available_store_profiles:
            score = self._score_store(dish, store)
            scored_stores.append({**store, "match_score": score})

        scored_stores.sort(key=lambda x: x["match_score"], reverse=True)
        recommended = scored_stores[:min(top_n, self.MAX_PILOT_STORES)]

        # 推荐试点规模
        pilot_store_count = max(self.MIN_PILOT_STORES, min(len(recommended), top_n))
        pilot_end_date    = (date.today() + timedelta(days=self.DEFAULT_PILOT_DAYS)).isoformat()

        return {
            "dish_id":            dish_id,
            "dish_name":          dish.dish_name,
            "recommended_stores": recommended,
            "pilot_store_count":  pilot_store_count,
            "pilot_duration_days": self.DEFAULT_PILOT_DAYS,
            "suggested_end_date": pilot_end_date,
            "recommendation_reason": self._build_reason(dish, recommended),
            "generated_at":       datetime.utcnow().isoformat(),
        }

    def _score_store(self, dish: Dish, store: dict) -> float:
        """门店匹配评分 0-100"""
        score = 50.0

        # 新品接受率加分
        acceptance = store.get("new_dish_acceptance_rate", 0.5)
        score += acceptance * 30

        # 客群匹配（按门店等级）
        level = store.get("level", "standard")
        if dish.positioning_type and str(dish.positioning_type) in ("profit", "image"):
            if level == "premium":
                score += 15
        elif level == "standard":
            score += 10

        # 区域供应可得性
        if dish.region_scope:
            store_region = store.get("region", "")
            if store_region and any(store_region in str(r) for r in dish.region_scope):
                score += 5

        return min(100.0, score)

    def _build_reason(self, dish: Dish, stores: list[dict]) -> str:
        top = stores[0] if stores else {}
        return (
            f"推荐以{len(stores)}家门店启动「{dish.dish_name}」试点，"
            f"首选{top.get('store_id', '')}（匹配度{top.get('match_score', 0):.0f}分）。"
            f"建议试点周期{self.DEFAULT_PILOT_DAYS}天，重点采集口味评分、出餐时长和退菜率。"
        )

    def _sample_store_profiles(self) -> list[dict]:
        return [
            {"store_id": "S001", "region": "华南", "level": "standard", "new_dish_acceptance_rate": 0.72},
            {"store_id": "S002", "region": "华南", "level": "premium",  "new_dish_acceptance_rate": 0.68},
            {"store_id": "S003", "region": "华东", "level": "standard", "new_dish_acceptance_rate": 0.61},
            {"store_id": "S004", "region": "华东", "level": "standard", "new_dish_acceptance_rate": 0.58},
            {"store_id": "S005", "region": "华北", "level": "standard", "new_dish_acceptance_rate": 0.55},
            {"store_id": "S006", "region": "华北", "level": "premium",  "new_dish_acceptance_rate": 0.63},
            {"store_id": "S007", "region": "西南", "level": "standard", "new_dish_acceptance_rate": 0.49},
        ]


# ─────────────────────────────────────────────
# Agent 3: 复盘优化 Agent
# ─────────────────────────────────────────────

class DishReviewAgent:
    """
    复盘优化 Agent
    - 聚合销售/毛利/退菜/差评/执行偏差数据
    - 输出生命周期判断（keep/optimize/regional_keep/monitor/retire）
    - 生成优化建议列表
    """

    REVIEW_PERIODS = ["30d", "60d", "90d"]

    async def run_review(
        self,
        dish_id: str,
        brand_id: str,
        db: AsyncSession,
        period: str = "30d",
        sales_data: Optional[dict] = None,    # 来自POS的销售摘要
        dry_run: bool = False,
        store_id: Optional[str] = None,       # 用于动态配置解析
    ) -> dict:
        """生成复盘报告"""
        # ── 动态配置解析 ──────────────────────────────────────────────
        _return_rate_alert: float = 0.15
        if store_id:
            try:
                _svc = OrgHierarchyService(db)
                _return_rate_alert = await _svc.resolve(
                    store_id, "dish_return_rate_alert", default=0.15
                )
            except Exception as _e:
                pass  # 降级使用默认值
        # ────────────────────────────────────────────────────────────

        # 获取近期反馈
        days = int(period.replace("d", ""))
        cutoff = datetime.utcnow() - timedelta(days=days)

        feedbacks_result = await db.execute(
            select(DishFeedback).where(
                and_(
                    DishFeedback.dish_id == dish_id,
                    DishFeedback.created_at >= cutoff,
                )
            )
        )
        feedbacks = feedbacks_result.scalars().all()

        # 聚合反馈
        feedback_summary = self._aggregate_feedbacks(feedbacks)
        return_feedbacks = [f for f in feedbacks if f.feedback_type == FeedbackTypeEnum.RETURN]
        complaint_feedbacks = [f for f in feedbacks if f.feedback_type == FeedbackTypeEnum.COMPLAINT]

        # 退菜率估算
        return_count   = len(return_feedbacks)
        total_feedback = len(feedbacks) or 1
        return_rate    = return_count / total_feedback

        # 评分汇总
        taste_scores = [f.rating_score for f in feedbacks if f.rating_score and f.feedback_type == FeedbackTypeEnum.TASTE]
        avg_taste    = round(sum(taste_scores) / len(taste_scores), 2) if taste_scores else None

        # 生命周期判断
        assessment = self._assess_lifecycle(
            avg_taste=avg_taste,
            return_rate=return_rate,
            complaint_count=len(complaint_feedbacks),
            total_feedback=total_feedback,
            sales_data=sales_data,
            return_rate_alert=_return_rate_alert,
        )

        # 优化建议
        suggestions = self._generate_suggestions(
            feedbacks=feedbacks,
            assessment=assessment,
            return_rate=return_rate,
            avg_taste=avg_taste,
            return_rate_alert=_return_rate_alert,
        )

        result = {
            "dish_id":                 dish_id,
            "retrospective_period":    period,
            "total_feedbacks":         total_feedback,
            "return_rate":             round(return_rate, 4),
            "avg_taste_score":         avg_taste,
            "complaint_count":         len(complaint_feedbacks),
            "lifecycle_assessment":    assessment,
            "optimization_suggestions": suggestions,
            "feedback_summary":        feedback_summary,
            "margin_summary":          sales_data.get("margin_summary", {}) if sales_data else {},
            "sales_summary":           sales_data.get("sales_summary", {}) if sales_data else {},
            "generated_at":            datetime.utcnow().isoformat(),
        }

        if not dry_run:
            dish_result = await db.execute(select(Dish).where(Dish.id == dish_id))
            dish = dish_result.scalars().first()
            report = RetrospectiveReport(
                id                      = str(uuid.uuid4()),
                dish_id                 = dish_id,
                brand_id                = brand_id,
                retrospective_period    = period,
                feedback_summary        = feedback_summary,
                lifecycle_assessment    = assessment,
                optimization_suggestions = suggestions,
                conclusion              = self._build_conclusion(assessment, suggestions),
                generated_at            = datetime.utcnow(),
            )
            db.add(report)
            await db.commit()
            result["report_id"] = report.id

        return result

    def _aggregate_feedbacks(self, feedbacks: list) -> dict:
        type_counts: dict[str, int] = {}
        for f in feedbacks:
            key = str(f.feedback_type)
            type_counts[key] = type_counts.get(key, 0) + 1
        return {"by_type": type_counts, "total": len(feedbacks)}

    def _assess_lifecycle(
        self,
        avg_taste: Optional[float],
        return_rate: float,
        complaint_count: int,
        total_feedback: int,
        sales_data: Optional[dict],
        return_rate_alert: float = 0.15,
    ) -> str:
        # 高退菜率或高差评 → 建议淘汰/观察
        if return_rate > return_rate_alert * 2 or complaint_count > total_feedback * 0.2:
            return LifecycleAssessmentEnum.RETIRE.value
        if return_rate > return_rate_alert or complaint_count > total_feedback * 0.1:
            return LifecycleAssessmentEnum.MONITOR.value

        # 口味评分良好
        if avg_taste is not None:
            if avg_taste >= 4.0:
                return LifecycleAssessmentEnum.KEEP.value
            if avg_taste >= 3.5:
                return LifecycleAssessmentEnum.OPTIMIZE.value
            return LifecycleAssessmentEnum.MONITOR.value

        # 无数据时默认观察
        return LifecycleAssessmentEnum.MONITOR.value

    def _generate_suggestions(
        self,
        feedbacks: list,
        assessment: str,
        return_rate: float,
        avg_taste: Optional[float],
        return_rate_alert: float = 0.15,
    ) -> list[str]:
        suggestions = []
        if return_rate > return_rate_alert:
            suggestions.append(f"退菜率 {return_rate:.0%} 偏高，建议排查出品温度与分量一致性")
        if avg_taste is not None and avg_taste < 3.8:
            suggestions.append(f"口味评分 {avg_taste:.1f}（满分5分），建议研发复核调味方向")

        # 差评关键词
        complaint_tags: list[str] = []
        for f in feedbacks:
            if f.feedback_type == FeedbackTypeEnum.COMPLAINT and f.keyword_tags:
                complaint_tags.extend(f.keyword_tags or [])
        if complaint_tags:
            top_tag = max(set(complaint_tags), key=complaint_tags.count)
            suggestions.append(f"高频差评关键词「{top_tag}」，建议专项改善")

        if assessment == LifecycleAssessmentEnum.RETIRE.value:
            suggestions.append("综合评估建议启动下架流程，保留区域门店选择性保留")
        elif assessment == LifecycleAssessmentEnum.OPTIMIZE.value:
            suggestions.append("建议提交配方微调版本，针对主要问题点做定向优化")

        return suggestions or ["当前表现稳定，建议持续监控30天后再次评估"]

    def _build_conclusion(self, assessment: str, suggestions: list[str]) -> str:
        labels = {
            "keep":          "建议保留",
            "optimize":      "建议优化",
            "regional_keep": "建议区域保留",
            "monitor":       "建议观察",
            "retire":        "建议淘汰",
        }
        label = labels.get(assessment, "建议观察")
        return f"生命周期判断：{label}。{'；'.join(suggestions[:2])}"


# ─────────────────────────────────────────────
# Agent 4: 发布助手 Agent
# ─────────────────────────────────────────────

class LaunchAssistAgent:
    """
    发布助手 Agent
    - 检查上市前置条件是否全部就绪
    - 自动生成发布 Checklist 并标记缺项
    - 输出 ready_to_launch 判断 + 缺项清单
    """

    REQUIRED_ITEMS = [
        ("recipe_version", "已发布配方版本"),
        ("cost_model",     "成本模型 & 毛利达标"),
        ("sop",            "标准工艺卡"),
        ("training_pkg",   "培训资料包"),
        ("procurement_pkg","采购清单"),
        ("supply_check",   "供应可行性评估"),
        ("pilot_decision", "试点通过（GO）"),
        ("approval",       "发布审批"),
    ]

    async def check_launch_readiness(
        self,
        dish_id: str,
        brand_id: str,
        launch_project_id: Optional[str],
        db: AsyncSession,
        store_id: Optional[str] = None,       # 用于动态配置解析
    ) -> dict:
        """检查上市发布就绪状态"""
        # ── 动态配置解析 ──────────────────────────────────────────────
        _min_gross_margin: float = 0.50
        if store_id:
            try:
                _svc = OrgHierarchyService(db)
                _min_gross_margin = await _svc.resolve(
                    store_id, "dish_min_gross_margin", default=0.50
                )
            except Exception:
                pass  # 降级使用默认值
        # ────────────────────────────────────────────────────────────

        dish_result = await db.execute(select(Dish).where(Dish.id == dish_id))
        dish = dish_result.scalars().first()
        if not dish:
            return {"error": "菜品不存在"}

        checklist = []
        missing_items = []

        # 1. 检查是否有已通过的配方版本
        recipe_result = await db.execute(
            select(RecipeVersion)
            .join(Recipe, Recipe.id == RecipeVersion.recipe_id)
            .where(
                and_(Recipe.dish_id == dish_id, RecipeVersion.status == "approved")
            )
        )
        has_recipe = recipe_result.scalars().first() is not None
        checklist.append({"key": "recipe_version", "label": "已发布配方版本", "done": has_recipe})
        if not has_recipe:
            missing_items.append("配方版本尚未审批通过")

        # 2. 检查成本模型
        cost_result = await db.execute(
            select(CostModel).where(CostModel.dish_id == dish_id)
        )
        cost_model = cost_result.scalars().first()
        has_cost = cost_model is not None
        margin_ok = float(cost_model.margin_rate or 0) >= _min_gross_margin if cost_model else False
        checklist.append({"key": "cost_model", "label": f"成本模型 & 毛利≥{_min_gross_margin:.0%}", "done": has_cost and margin_ok,
                          "detail": f"当前毛利率 {float(cost_model.margin_rate or 0):.0%}" if cost_model else "无成本数据"})
        if not (has_cost and margin_ok):
            missing_items.append(f"成本模型未建立或毛利率未达{_min_gross_margin:.0%}")

        # 3. 检查 SOP
        from src.models.dish_rd import SOP
        sop_result = await db.execute(
            select(SOP).where(and_(SOP.dish_id == dish_id, SOP.status == "published"))
        )
        has_sop = sop_result.scalars().first() is not None
        checklist.append({"key": "sop", "label": "标准工艺卡（已发布）", "done": has_sop})
        if not has_sop:
            missing_items.append("标准工艺卡尚未发布")

        # 4. 检查试点结论
        pilot_result = await db.execute(
            select(PilotTest).where(
                and_(PilotTest.dish_id == dish_id, PilotTest.decision == "go")
            )
        )
        has_pilot_go = pilot_result.scalars().first() is not None
        checklist.append({"key": "pilot_decision", "label": "试点通过（GO）", "done": has_pilot_go})
        if not has_pilot_go:
            missing_items.append("尚无通过的试点结论（GO）")

        # 5. 检查发布项目的培训包/采购包/通知状态
        if launch_project_id:
            lp_result = await db.execute(select(LaunchProject).where(LaunchProject.id == launch_project_id))
            lp = lp_result.scalars().first()
            if lp:
                training_done    = lp.training_package_status == "sent"
                procurement_done = lp.procurement_package_status == "sent"
                notice_done      = lp.operation_notice_status == "sent"
                approval_done    = lp.approval_status == "approved"
                checklist.extend([
                    {"key": "training_pkg",    "label": "培训资料包已下发",  "done": training_done},
                    {"key": "procurement_pkg", "label": "采购清单已下发",    "done": procurement_done},
                    {"key": "op_notice",       "label": "营运通知已发送",    "done": notice_done},
                    {"key": "approval",        "label": "发布审批通过",      "done": approval_done},
                ])
                if not training_done:    missing_items.append("培训资料包未下发")
                if not procurement_done: missing_items.append("采购清单未下发")
                if not approval_done:    missing_items.append("发布审批尚未通过")

        done_count    = sum(1 for c in checklist if c["done"])
        total_count   = len(checklist)
        ready         = len(missing_items) == 0

        return {
            "dish_id":          dish_id,
            "dish_name":        dish.dish_name,
            "ready_to_launch":  ready,
            "checklist":        checklist,
            "done_count":       done_count,
            "total_count":      total_count,
            "completion_pct":   round(done_count / total_count * 100, 1),
            "missing_items":    missing_items,
            "recommendation":   "已具备上市条件，可启动发布" if ready else f"请先完成以下 {len(missing_items)} 项：{'；'.join(missing_items[:3])}",
            "checked_at":       datetime.utcnow().isoformat(),
        }


# ─────────────────────────────────────────────
# Agent 5: 风险预警 Agent
# ─────────────────────────────────────────────

class RiskAlertAgent:
    """
    风险预警 Agent
    - 扫描所有在研/试点/已发布菜品的风险信号
    - 风险类型：成本超标/供应异常/试点表现差/差评集中/执行偏差
    - 输出风险列表 + 推荐动作
    """

    COST_OVERRUN_THRESHOLD    = 0.45  # 毛利率低于45%触发预警
    POOR_TASTE_THRESHOLD      = 3.5   # 口味评分低于3.5触发
    RETURN_RATE_THRESHOLD     = 0.15  # 退菜率超过15%触发
    COMPLAINT_RATE_THRESHOLD  = 0.10  # 差评率超过10%触发

    async def scan_risks(
        self,
        brand_id: str,
        db: AsyncSession,
        days_back: int = 14,
        dry_run: bool = False,
        store_id: Optional[str] = None,       # 用于动态配置解析
    ) -> dict:
        """扫描品牌下所有菜品的风险信号"""
        # ── 动态配置解析 ──────────────────────────────────────────────
        _return_rate_alert: float = self.RETURN_RATE_THRESHOLD
        if store_id:
            try:
                _svc = OrgHierarchyService(db)
                _return_rate_alert = await _svc.resolve(
                    store_id, "dish_return_rate_alert", default=self.RETURN_RATE_THRESHOLD
                )
            except Exception:
                pass  # 降级使用类默认值
        # ────────────────────────────────────────────────────────────

        cutoff = datetime.utcnow() - timedelta(days=days_back)
        risks  = []

        # 1. 成本毛利率过低的菜品
        cost_result = await db.execute(
            select(CostModel, Dish.dish_name)
            .join(Dish, Dish.id == CostModel.dish_id)
            .where(
                and_(
                    CostModel.brand_id == brand_id,
                    CostModel.margin_rate < self.COST_OVERRUN_THRESHOLD,
                    CostModel.calculated_at >= cutoff,
                )
            )
        )
        for row in cost_result.all():
            cost, dish_name = row[0], row[1]
            risks.append({
                "risk_type":    "cost_overrun",
                "dish_id":      cost.dish_id,
                "dish_name":    dish_name,
                "risk_level":   "high",
                "detail":       f"当前毛利率 {float(cost.margin_rate or 0):.0%}，低于警戒线 {self.COST_OVERRUN_THRESHOLD:.0%}",
                "action":       "建议重新核算成本或调整售价，触发成本仿真Agent",
            })

        # 2. 试点评分过低
        pilot_result = await db.execute(
            select(PilotTest, Dish.dish_name)
            .join(Dish, Dish.id == PilotTest.dish_id)
            .where(
                and_(
                    PilotTest.brand_id == brand_id,
                    PilotTest.pilot_status == PilotStatusEnum.ACTIVE,
                )
            )
        )
        for row in pilot_result.all():
            pilot, dish_name = row[0], row[1]
            taste = pilot.avg_taste_score
            if taste is not None and taste < self.POOR_TASTE_THRESHOLD:
                risks.append({
                    "risk_type":  "poor_pilot_score",
                    "dish_id":    pilot.dish_id,
                    "dish_name":  dish_name,
                    "risk_level": "high" if taste < 3.0 else "medium",
                    "detail":     f"试点口味评分 {taste:.1f}（满分5分），低于{self.POOR_TASTE_THRESHOLD}分预警线",
                    "action":     "建议暂停试点，研发回炉复盘",
                })

        # 3. 近期高退菜率 / 差评聚集
        feedback_result = await db.execute(
            select(
                DishFeedback.dish_id,
                Dish.dish_name,
                func.count().label("total"),
                func.sum(
                    (DishFeedback.feedback_type == FeedbackTypeEnum.RETURN).cast(sa_Integer)
                ).label("returns"),
                func.sum(
                    (DishFeedback.feedback_type == FeedbackTypeEnum.COMPLAINT).cast(sa_Integer)
                ).label("complaints"),
            )
            .join(Dish, Dish.id == DishFeedback.dish_id)
            .where(
                and_(DishFeedback.brand_id == brand_id, DishFeedback.created_at >= cutoff)
            )
            .group_by(DishFeedback.dish_id, Dish.dish_name)
        )
        for row in feedback_result.all():
            total      = row.total or 1
            returns    = row.returns or 0
            complaints = row.complaints or 0
            return_rate    = returns / total
            complaint_rate = complaints / total

            if return_rate > _return_rate_alert:
                risks.append({
                    "risk_type":  "high_return_rate",
                    "dish_id":    row.dish_id,
                    "dish_name":  row.dish_name,
                    "risk_level": "high",
                    "detail":     f"近{days_back}天退菜率 {return_rate:.0%}（{returns}/{total}条反馈）",
                    "action":     "建议追踪退菜原因，检查出品温度/分量/工艺执行",
                })
            if complaint_rate > self.COMPLAINT_RATE_THRESHOLD:
                risks.append({
                    "risk_type":  "complaint_cluster",
                    "dish_id":    row.dish_id,
                    "dish_name":  row.dish_name,
                    "risk_level": "medium",
                    "detail":     f"近{days_back}天差评率 {complaint_rate:.0%}（{complaints}/{total}条反馈）",
                    "action":     "建议差评文本聚类分析，重点关注高频关键词",
                })

        if not dry_run and risks:
            log = DishRdAgentLog(
                id            = str(uuid.uuid4()),
                brand_id      = brand_id,
                agent_type    = DishRdAgentTypeEnum.RISK_ALERT,
                trigger_reason = f"定期扫描 brand={brand_id}",
                output_data   = {"risks": risks},
                recommendation = f"共发现 {len(risks)} 个风险信号",
                executed_at   = datetime.utcnow(),
            )
            db.add(log)
            await db.commit()

        return {
            "brand_id":       brand_id,
            "scan_days":      days_back,
            "risk_count":     len(risks),
            "high_risks":     [r for r in risks if r["risk_level"] == "high"],
            "medium_risks":   [r for r in risks if r["risk_level"] == "medium"],
            "risks":          risks,
            "scanned_at":     datetime.utcnow().isoformat(),
        }


# 修复 RiskAlertAgent 中用到的 Integer cast（SQLAlchemy 语法）
from sqlalchemy import Integer as sa_Integer
