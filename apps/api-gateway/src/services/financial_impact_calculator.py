"""
财务影响计算器（Financial Impact Calculator）

职责：将经营指标变化转化为 ¥ 金额影响。
设计原则：
  - 纯函数，无 IO，无外部依赖
  - 每个方法返回包含 ¥ 字段的 dict（单位：元，保留2位小数）
  - 可被 DecisionPriorityEngine、FoodCostService、WasteGuardService 复用
"""

from __future__ import annotations

from typing import List


class FinancialImpactCalculator:
    """¥ 影响计算工具集（全静态方法，无状态）"""

    # ── 成本率改善 ──────────────────────────────────────────────────────────────

    @staticmethod
    def cost_rate_improvement(
        monthly_revenue_yuan: float,
        current_rate_pct: float,
        target_rate_pct: float,
    ) -> dict:
        """
        成本率降低对应的 ¥ 节省额。

        Args:
            monthly_revenue_yuan: 月营收（元）
            current_rate_pct:  当前成本率（%，如 36.5）
            target_rate_pct:   目标成本率（%，如 34.5）

        Returns:
            {
                "monthly_saving_yuan": float,
                "annual_saving_yuan":  float,
                "rate_improvement_pct": float,  # 差值（正数=节省）
            }
        """
        delta = current_rate_pct - target_rate_pct
        monthly = round(monthly_revenue_yuan * delta / 100, 2)
        return {
            "monthly_saving_yuan": monthly,
            "annual_saving_yuan": round(monthly * 12, 2),
            "rate_improvement_pct": round(delta, 2),
        }

    # ── 采购决策 ────────────────────────────────────────────────────────────────

    @staticmethod
    def purchase_decision(
        unit_cost_yuan: float,
        quantity: float,
        urgency_surcharge_pct: float = 0.0,
    ) -> dict:
        """
        计算采购决策的 ¥ 成本与预期收益。

        Args:
            unit_cost_yuan:       单位成本（元）
            quantity:             采购数量
            urgency_surcharge_pct: 紧急采购溢价（%，如临时加量 10% 溢价）

        Returns:
            {
                "purchase_cost_yuan":   float,  # 总采购成本
                "surcharge_yuan":       float,  # 溢价金额
                "total_cost_yuan":      float,  # 含溢价总成本
            }
        """
        base = round(unit_cost_yuan * quantity, 2)
        surcharge = round(base * urgency_surcharge_pct / 100, 2)
        return {
            "purchase_cost_yuan": base,
            "surcharge_yuan": surcharge,
            "total_cost_yuan": round(base + surcharge, 2),
        }

    # ── 损耗减少 ────────────────────────────────────────────────────────────────

    @staticmethod
    def waste_reduction(
        waste_items: List[dict],
        reduction_rate_pct: float = 30.0,
    ) -> dict:
        """
        估算损耗治理的 ¥ 收益。

        Args:
            waste_items: 损耗列表，每项含 {"item_name": str, "waste_cost_yuan": float}
            reduction_rate_pct: 预期可减少的比例（%，默认30%）

        Returns:
            {
                "total_waste_yuan":        float,  # 当前总损耗
                "potential_saving_yuan":   float,  # 可减少的 ¥ 节省
                "reduction_rate_pct":      float,
                "top_items":               list,   # 前3损耗项
            }
        """
        total = sum(item.get("waste_cost_yuan", 0.0) for item in waste_items)
        saving = round(total * reduction_rate_pct / 100, 2)
        sorted_items = sorted(
            waste_items, key=lambda x: x.get("waste_cost_yuan", 0.0), reverse=True
        )
        return {
            "total_waste_yuan": round(total, 2),
            "potential_saving_yuan": saving,
            "reduction_rate_pct": reduction_rate_pct,
            "top_items": sorted_items[:3],
        }

    # ── 人效优化 ────────────────────────────────────────────────────────────────

    @staticmethod
    def staffing_optimization(
        current_labor_cost_yuan: float,
        efficiency_gain_pct: float,
    ) -> dict:
        """
        排班优化的 ¥ 节省估算。

        Args:
            current_labor_cost_yuan: 当前人工成本（元，通常是月成本）
            efficiency_gain_pct:     效率提升比例（%，如 8 表示8%）

        Returns:
            {
                "labor_saving_yuan":  float,  # 节省的人工成本
                "annual_saving_yuan": float,
            }
        """
        saving = round(current_labor_cost_yuan * efficiency_gain_pct / 100, 2)
        return {
            "labor_saving_yuan": saving,
            "annual_saving_yuan": round(saving * 12, 2),
        }

    # ── 决策 ROI ────────────────────────────────────────────────────────────────

    @staticmethod
    def decision_roi(
        expected_saving_yuan: float,
        expected_cost_yuan: float,
    ) -> dict:
        """
        单条决策的 ROI 计算。

        Returns:
            {
                "net_benefit_yuan": float,
                "roi_multiple":     float,   # saving / cost，0 表示成本为0
                "roi_pct":          float,   # (saving - cost) / cost × 100
            }
        """
        net = round(expected_saving_yuan - expected_cost_yuan, 2)
        if expected_cost_yuan > 0:
            roi_multiple = round(expected_saving_yuan / expected_cost_yuan, 2)
            roi_pct = round((expected_saving_yuan - expected_cost_yuan) / expected_cost_yuan * 100, 1)
        else:
            roi_multiple = 0.0
            roi_pct = 0.0
        return {
            "net_benefit_yuan": net,
            "roi_multiple": roi_multiple,
            "roi_pct": roi_pct,
        }

    # ── 菜品定价影响 ────────────────────────────────────────────────────────────

    @staticmethod
    def menu_price_impact(
        dish_name: str,
        food_cost_fen: int,
        current_price_yuan: float,
        target_food_cost_pct: float = 32.0,
    ) -> dict:
        """
        根据目标食材成本率计算合理售价或成本节省空间。

        Args:
            dish_name:            菜品名称
            food_cost_fen:        当前食材成本（分）
            current_price_yuan:   当前售价（元）
            target_food_cost_pct: 目标食材成本率（%）

        Returns:
            {
                "dish_name":             str,
                "current_food_cost_pct": float,
                "target_food_cost_pct":  float,
                "gap_pct":               float,   # 正数=超出目标
                "suggested_price_yuan":  float,   # 达到目标成本率的建议售价
                "cost_saving_per_dish":  float,   # 每份可节省（元），若已达标则为0
            }
        """
        food_cost_yuan = food_cost_fen / 100
        if current_price_yuan > 0:
            current_pct = round(food_cost_yuan / current_price_yuan * 100, 2)
        else:
            current_pct = 0.0

        gap = round(current_pct - target_food_cost_pct, 2)
        suggested_price = round(food_cost_yuan / (target_food_cost_pct / 100), 2) if target_food_cost_pct > 0 else 0.0
        cost_saving = max(0.0, round(food_cost_yuan - current_price_yuan * target_food_cost_pct / 100, 2))

        return {
            "dish_name": dish_name,
            "current_food_cost_pct": current_pct,
            "target_food_cost_pct": target_food_cost_pct,
            "gap_pct": gap,
            "suggested_price_yuan": suggested_price,
            "cost_saving_per_dish": cost_saving,
        }
