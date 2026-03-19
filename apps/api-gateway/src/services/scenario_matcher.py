"""
场景匹配器（Scenario Matcher）

职责：
  1. 识别门店当前经营场景（7种典型场景）
  2. 在历史决策日志和案例数据中检索最相似的案例
  3. 返回历史案例的执行结果和推荐动作

7种典型场景（按成本率 × 营收趋势 × 节假日分类）：
  A. 节假日高峰期（is_holiday=True, revenue_trend=up）
  B. 工作日正常期（平稳）
  C. 成本超标期（cost_rate > 35%）
  D. 营收下行期（revenue_trend=down, not holiday）
  E. 新品上市期（new_dish_count > 0）
  F. 损耗高发期（waste_rate > 5%）
  G. 周末经营期（day_of_week >= 5）

设计原则：
  - 纯函数 `classify_scenario` 可独立测试，无 DB 依赖
  - 历史匹配使用参数化 SQL（遵循 L010/L011）
  - 相似度评分基于场景类型 + 成本率差距 + 营收量级
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 场景类型常量 ──────────────────────────────────────────────────────────────
SCENARIO_HOLIDAY_PEAK = "holiday_peak"  # A: 节假日高峰
SCENARIO_WEEKDAY_NORMAL = "weekday_normal"  # B: 工作日正常
SCENARIO_HIGH_COST = "high_cost"  # C: 成本超标
SCENARIO_REVENUE_DOWN = "revenue_down"  # D: 营收下行
SCENARIO_NEW_DISH = "new_dish"  # E: 新品上市
SCENARIO_HIGH_WASTE = "high_waste"  # F: 损耗高发
SCENARIO_WEEKEND = "weekend"  # G: 周末经营

# 优先级（数字越小越优先，用于场景叠加时取最高优先级）
_SCENARIO_PRIORITY: Dict[str, int] = {
    SCENARIO_HIGH_COST: 1,
    SCENARIO_HIGH_WASTE: 2,
    SCENARIO_HOLIDAY_PEAK: 3,
    SCENARIO_REVENUE_DOWN: 4,
    SCENARIO_WEEKEND: 5,
    SCENARIO_NEW_DISH: 6,
    SCENARIO_WEEKDAY_NORMAL: 7,
}

_SCENARIO_LABELS: Dict[str, str] = {
    SCENARIO_HOLIDAY_PEAK: "节假日高峰期",
    SCENARIO_WEEKDAY_NORMAL: "工作日正常期",
    SCENARIO_HIGH_COST: "成本超标期",
    SCENARIO_REVENUE_DOWN: "营收下行期",
    SCENARIO_NEW_DISH: "新品上市期",
    SCENARIO_HIGH_WASTE: "损耗高发期",
    SCENARIO_WEEKEND: "周末经营期",
}

# 场景阈值（可环境变量覆盖）
_COST_HIGH_THRESHOLD = float(os.getenv("SCENARIO_COST_HIGH_PCT", "35.0"))  # %
_WASTE_HIGH_THRESHOLD = float(os.getenv("SCENARIO_WASTE_HIGH_PCT", "5.0"))  # %
_REVENUE_DOWN_PCT = float(os.getenv("SCENARIO_REVENUE_DOWN_PCT", "-10.0"))  # %（负数）


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：场景分类（无 DB 依赖，可单元测试）
# ════════════════════════════════════════════════════════════════════════════════


def classify_scenario(
    cost_rate_pct: float,
    waste_rate_pct: float,
    revenue_wow_pct: float,  # 营收周环比（%，正=增长，负=下降）
    day_of_week: int,  # 0=周一, 6=周日
    is_holiday: bool = False,
    new_dish_count: int = 0,
) -> str:
    """
    根据当前门店经营指标分类场景。

    Args:
        cost_rate_pct:   实际食材成本率（%，如 32.5）
        waste_rate_pct:  损耗率（%，如 4.2）
        revenue_wow_pct: 营收周环比（%，如 -15.0 表示下降15%）
        day_of_week:     周几（0=周一, 6=周日）
        is_holiday:      是否节假日
        new_dish_count:  近7天新上菜品数量

    Returns:
        场景类型字符串（见 SCENARIO_* 常量）
    """
    # 按优先级顺序判断
    if cost_rate_pct >= _COST_HIGH_THRESHOLD:
        return SCENARIO_HIGH_COST

    if waste_rate_pct >= _WASTE_HIGH_THRESHOLD:
        return SCENARIO_HIGH_WASTE

    if is_holiday:
        return SCENARIO_HOLIDAY_PEAK

    if revenue_wow_pct <= _REVENUE_DOWN_PCT:
        return SCENARIO_REVENUE_DOWN

    if day_of_week >= 5:  # 周六/周日
        return SCENARIO_WEEKEND

    if new_dish_count > 0:
        return SCENARIO_NEW_DISH

    return SCENARIO_WEEKDAY_NORMAL


def get_scenario_label(scenario_type: str) -> str:
    """返回场景的中文标签"""
    return _SCENARIO_LABELS.get(scenario_type, "未知场景")


def score_case_similarity(
    current_cost_pct: float,
    current_revenue: int,  # 分
    case_cost_pct: float,
    case_revenue: int,  # 分
    scenario_match: bool,
) -> float:
    """
    计算当前状态与历史案例的相似度评分（0.0–1.0）。

    评分公式：
      - 场景类型匹配：+0.40
      - 成本率接近度：+0.35 × (1 - |delta_cost| / 20)，delta > 20% 得 0分
      - 营收量级接近度：+0.25 × (1 - |delta_rev| / revenue_scale)

    Args:
        current_cost_pct:  当前成本率（%）
        current_revenue:   当前营业额（分）
        case_cost_pct:     历史案例成本率（%）
        case_revenue:      历史案例营业额（分）
        scenario_match:    场景类型是否相同

    Returns:
        相似度评分（0.0–1.0）
    """
    score = 0.0

    if scenario_match:
        score += 0.40

    # 成本率接近度
    cost_delta = abs(current_cost_pct - case_cost_pct)
    if cost_delta <= 20.0:
        score += 0.35 * (1.0 - cost_delta / 20.0)

    # 营收量级接近度（以较大值为基准）
    max_rev = max(current_revenue, case_revenue, 1)
    rev_delta = abs(current_revenue - case_revenue) / max_rev
    if rev_delta <= 1.0:
        score += 0.25 * (1.0 - rev_delta)

    return round(score, 3)


# ════════════════════════════════════════════════════════════════════════════════
# 核心：ScenarioMatcher
# ════════════════════════════════════════════════════════════════════════════════


class ScenarioMatcher:
    """场景匹配器：识别当前场景，检索历史相似案例，返回推荐动作"""

    # ── 场景识别 ────────────────────────────────────────────────────────────────

    @staticmethod
    async def identify_current_scenario(
        store_id: str,
        db: AsyncSession,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        自动识别门店当前经营场景。

        数据来源：最近7天的 orders + inventory_transactions，
        与上周同期对比计算营收环比。

        Returns:
            {
              store_id, scenario_type, scenario_label,
              metrics: {cost_rate_pct, waste_rate_pct, revenue_wow_pct, ...},
              as_of
            }
        """
        today = as_of or date.today()
        week_start = today - timedelta(days=7)
        prev_start = today - timedelta(days=14)
        prev_end = today - timedelta(days=7)

        # 近7天营收
        row = await db.execute(
            text(
                "SELECT COALESCE(SUM(total_amount), 0) FROM orders "
                "WHERE store_id = :sid AND created_at >= :start AND created_at < :end"
            ),
            {"sid": store_id, "start": week_start, "end": today},
        )
        revenue_fen = int(row.scalar() or 0)

        # 上周营收（环比分母）
        row = await db.execute(
            text(
                "SELECT COALESCE(SUM(total_amount), 0) FROM orders "
                "WHERE store_id = :sid AND created_at >= :start AND created_at < :end"
            ),
            {"sid": store_id, "start": prev_start, "end": prev_end},
        )
        prev_revenue_fen = int(row.scalar() or 0)

        # 近7天实际成本
        row = await db.execute(
            text(
                "SELECT COALESCE(ABS(SUM(total_cost)), 0) FROM inventory_transactions "
                "WHERE store_id = :sid AND transaction_type = 'usage' "
                "AND transaction_time >= :start AND transaction_time < :end"
            ),
            {"sid": store_id, "start": week_start, "end": today},
        )
        actual_cost_fen = int(row.scalar() or 0)

        # 近7天损耗
        row = await db.execute(
            text(
                "SELECT COALESCE(ABS(SUM(total_cost)), 0) FROM inventory_transactions "
                "WHERE store_id = :sid AND transaction_type = 'waste' "
                "AND transaction_time >= :start AND transaction_time < :end"
            ),
            {"sid": store_id, "start": week_start, "end": today},
        )
        waste_cost_fen = int(row.scalar() or 0)

        # 近7天新菜品数（通过 dish create_at 判断）
        row = await db.execute(
            text("SELECT COUNT(*) FROM dishes " "WHERE store_id = :sid AND created_at >= :start"),
            {"sid": store_id, "start": week_start},
        )
        new_dish_count = int(row.scalar() or 0)

        # 计算指标
        cost_rate_pct = round(actual_cost_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0
        waste_rate_pct = round(waste_cost_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0
        revenue_wow_pct = round((revenue_fen - prev_revenue_fen) / prev_revenue_fen * 100, 1) if prev_revenue_fen > 0 else 0.0

        day_of_week = today.weekday()  # 0=周一
        # 简单节假日判断（可扩展为外部日历服务）
        is_holiday = _is_chinese_public_holiday(today)

        scenario_type = classify_scenario(
            cost_rate_pct=cost_rate_pct,
            waste_rate_pct=waste_rate_pct,
            revenue_wow_pct=revenue_wow_pct,
            day_of_week=day_of_week,
            is_holiday=is_holiday,
            new_dish_count=new_dish_count,
        )

        return {
            "store_id": store_id,
            "scenario_type": scenario_type,
            "scenario_label": get_scenario_label(scenario_type),
            "metrics": {
                "cost_rate_pct": cost_rate_pct,
                "waste_rate_pct": waste_rate_pct,
                "revenue_wow_pct": revenue_wow_pct,
                "revenue_yuan": round(revenue_fen / 100, 2),
                "day_of_week": day_of_week,
                "is_holiday": is_holiday,
                "new_dish_count": new_dish_count,
            },
            "as_of": str(today),
        }

    # ── 历史相似案例检索 ─────────────────────────────────────────────────────────

    @staticmethod
    async def find_similar_cases(
        store_id: str,
        scenario_type: str,
        cost_rate_pct: float,
        revenue_fen: int,
        db: AsyncSession,
        max_results: int = 5,
        lookback_days: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        检索历史上最相似的经营案例（决策日志 + 结果）。

        策略：
          1. 在最近 lookback_days 内查找同一门店的决策记录
          2. 过滤出已有执行结果的（outcome IS NOT NULL）
          3. 按决策对应的场景类型 + 成本率差距打分排序
          4. 返回 Top max_results

        Args:
            store_id:      门店 ID
            scenario_type: 当前场景类型
            cost_rate_pct: 当前成本率（%）
            revenue_fen:   当前营业额（分）
            db:            数据库会话
            max_results:   返回结果数量上限
            lookback_days: 检索历史天数

        Returns:
            [
              {
                decision_id, action, outcome, expected_saving_yuan,
                actual_saving_yuan, context, similarity_score, created_at
              }
            ]
        """
        since = date.today() - timedelta(days=lookback_days)

        rows = await db.execute(
            text(
                "SELECT id, ai_suggestion, outcome, created_at "
                "FROM decision_log "
                "WHERE store_id = :sid "
                "AND outcome IS NOT NULL "
                "AND created_at >= :since "
                "ORDER BY created_at DESC "
                "LIMIT :n"
            ),
            {"sid": store_id, "since": since, "n": max_results * 3},
        )

        cases = []
        for r in rows.fetchall():
            suggestion = r.ai_suggestion if isinstance(r.ai_suggestion, dict) else {}
            case_cost_pct = float(suggestion.get("theoretical_cost_pct", cost_rate_pct))
            case_revenue = int(suggestion.get("revenue_fen", revenue_fen))
            case_scenario = suggestion.get("scenario_type", "")
            scenario_match = case_scenario == scenario_type

            sim_score = score_case_similarity(
                current_cost_pct=cost_rate_pct,
                current_revenue=revenue_fen,
                case_cost_pct=case_cost_pct,
                case_revenue=case_revenue,
                scenario_match=scenario_match,
            )

            cases.append(
                {
                    "decision_id": r.id,
                    "action": suggestion.get("action", ""),
                    "outcome": r.outcome,
                    "expected_saving_yuan": float(suggestion.get("expected_saving_yuan", 0)),
                    "actual_saving_yuan": float(suggestion.get("actual_saving_yuan", 0)),
                    "context": {
                        "scenario_type": case_scenario,
                        "cost_rate_pct": case_cost_pct,
                    },
                    "similarity_score": sim_score,
                    "created_at": str(r.created_at),
                }
            )

        # 按相似度降序排序，取 Top max_results
        cases.sort(key=lambda c: c["similarity_score"], reverse=True)
        return cases[:max_results]

    # ── 推荐动作 ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_recommended_actions(
        store_id: str,
        scenario_type: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        根据场景类型 + 历史案例成功率，生成推荐动作列表。

        逻辑：
          1. 找出同场景下 outcome=success 的历史决策
          2. 按 expected_saving_yuan 降序取 Top 5
          3. 组合成推荐动作列表，附成功率统计

        Returns:
            {
              scenario_type, scenario_label,
              recommended_actions: [{action, success_rate, avg_saving_yuan, sample_count}],
              generated_at
            }
        """
        rows = await db.execute(
            text(
                "SELECT ai_suggestion, outcome "
                "FROM decision_log "
                "WHERE store_id = :sid "
                "AND created_at >= CURRENT_DATE - (:days * INTERVAL '1 day') "
                "ORDER BY created_at DESC "
                "LIMIT 100"
            ),
            {"sid": store_id, "days": 90},
        )

        # 按 action 聚合成功率
        action_stats: Dict[str, Dict[str, Any]] = {}
        for r in rows.fetchall():
            suggestion = r.ai_suggestion if isinstance(r.ai_suggestion, dict) else {}
            action = suggestion.get("action", "")
            if not action:
                continue

            if action not in action_stats:
                action_stats[action] = {
                    "action": action,
                    "total": 0,
                    "success": 0,
                    "total_saving": 0.0,
                }
            action_stats[action]["total"] += 1
            action_stats[action]["total_saving"] += float(suggestion.get("expected_saving_yuan", 0))
            if r.outcome == "success":
                action_stats[action]["success"] += 1

        recommended = []
        for stats in sorted(
            action_stats.values(),
            key=lambda s: s["total_saving"],
            reverse=True,
        )[:5]:
            total = stats["total"]
            success = stats["success"]
            recommended.append(
                {
                    "action": stats["action"],
                    "success_rate_pct": round(success / total * 100, 1) if total > 0 else 0.0,
                    "avg_saving_yuan": round(stats["total_saving"] / total, 2) if total > 0 else 0.0,
                    "sample_count": total,
                }
            )

        return {
            "scenario_type": scenario_type,
            "scenario_label": get_scenario_label(scenario_type),
            "recommended_actions": recommended,
            "generated_at": datetime.utcnow().isoformat(),
        }


# ════════════════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════════════════

# 简化版中国法定节假日判断（按月日匹配，精确度有限）
# 生产环境可替换为调用外部日历 API（`external_factors_adapter.py`）
_FIXED_HOLIDAYS: set = {
    (1, 1),  # 元旦
    (5, 1),  # 劳动节
    (10, 1),
    (10, 2),
    (10, 3),  # 国庆节
}


def _is_chinese_public_holiday(d: date) -> bool:
    """粗略判断是否为固定节假日（不含春节等农历节日）"""
    return (d.month, d.day) in _FIXED_HOLIDAYS
