"""OkrCascadeService — 目标级联分解引擎

支持年度→季度→月度→门店的全链路目标拆分：
  - 季节性权重（餐饮行业淡旺季）
  - 智能门店分配（按容量/潜力/均分）
  - 一键全链路级联
  - 级联健康度检查
"""

from __future__ import annotations

import json
import uuid
from calendar import monthrange
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 季节性权重（餐饮行业经验值，可覆盖） ────────────────────────────────────
DEFAULT_QUARTER_WEIGHTS = {
    1: 0.20,  # Q1 春节后淡季
    2: 0.28,  # Q2 旺季
    3: 0.24,  # Q3 平季
    4: 0.28,  # Q4 旺季（年末聚餐）
}


class OkrCascadeService:
    """目标级联分解引擎 — 年度→季度→月度→门店"""

    # ─────────────────────────────────────────────────────────────────────
    # 方法1: 年度→季度拆分
    # ─────────────────────────────────────────────────────────────────────
    async def cascade_annual_to_quarters(
        self,
        session: AsyncSession,
        brand_id: str,
        objective_id: str,
        quarter_weights: Optional[Dict[int, float]] = None,
    ) -> Dict[str, Any]:
        """将年度目标自动拆分为4个季度子目标

        Args:
            quarter_weights: 自定义季度权重，如 {1: 0.20, 2: 0.28, 3: 0.24, 4: 0.28}

        Returns:
            {"parent_id": "...", "quarters": [{"id": "...", "period_value": 1, ...}, ...]}
        """
        weights = quarter_weights or DEFAULT_QUARTER_WEIGHTS

        # 验证权重和为1
        total_weight = sum(weights.values())
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"季度权重之和必须为1.0，当前为 {total_weight:.2f}"
            )

        # 查询父目标
        parent = await self._fetch_objective(session, objective_id, brand_id)
        if parent is None:
            raise ValueError(f"目标不存在: {objective_id}")

        if parent["period_type"] != "annual":
            raise ValueError(
                f"只能对年度目标执行季度拆分，当前类型: {parent['period_type']}"
            )

        target_value = parent["target_value"]
        floor_value = parent.get("floor_value") or 0
        stretch_value = parent.get("stretch_value") or 0

        quarters: List[Dict[str, Any]] = []

        for q in range(1, 5):
            w = weights[q]
            q_target = int(target_value * w)
            q_floor = int(floor_value * w) if floor_value else None
            q_stretch = int(stretch_value * w) if stretch_value else None

            q_id = str(uuid.uuid4())
            await session.execute(
                text("""
                    INSERT INTO business_objectives
                        (id, brand_id, store_id, parent_id, level,
                         fiscal_year, period_type, period_value,
                         objective_name, metric_code, target_value,
                         floor_value, stretch_value, unit,
                         bsc_dimension, status)
                    VALUES
                        (:id, :brand_id, :store_id, :parent_id, :level,
                         :fiscal_year, 'quarter', :period_value,
                         :objective_name, :metric_code, :target_value,
                         :floor_value, :stretch_value, :unit,
                         :bsc_dimension, 'active')
                """),
                {
                    "id": q_id,
                    "brand_id": brand_id,
                    "store_id": parent.get("store_id"),
                    "parent_id": objective_id,
                    "level": parent["level"],
                    "fiscal_year": parent["fiscal_year"],
                    "period_value": q,
                    "objective_name": f"{parent['objective_name']} - Q{q}",
                    "metric_code": parent["metric_code"],
                    "target_value": q_target,
                    "floor_value": q_floor,
                    "stretch_value": q_stretch,
                    "unit": parent["unit"],
                    "bsc_dimension": parent["bsc_dimension"],
                },
            )

            quarters.append({
                "id": q_id,
                "period_value": q,
                "weight": w,
                "target_value_fen": q_target,
                "target_value_yuan": round(q_target / 100, 2),
                "floor_value_yuan": round(q_floor / 100, 2) if q_floor else None,
                "stretch_value_yuan": round(q_stretch / 100, 2) if q_stretch else None,
            })

        logger.info(
            "okr_cascade.annual_to_quarters.done",
            brand_id=brand_id,
            parent_id=objective_id,
            target_yuan=round(target_value / 100, 2),
        )

        return {
            "parent_id": objective_id,
            "fiscal_year": parent["fiscal_year"],
            "metric_code": parent["metric_code"],
            "annual_target_yuan": round(target_value / 100, 2),
            "quarters": quarters,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 方法2: 季度→月度拆分
    # ─────────────────────────────────────────────────────────────────────
    async def cascade_quarter_to_months(
        self,
        session: AsyncSession,
        brand_id: str,
        objective_id: str,
    ) -> Dict[str, Any]:
        """将季度目标按月份天数权重拆分为3个月度子目标

        Returns:
            {"parent_id": "...", "months": [{"id": "...", "month": 4, ...}, ...]}
        """
        parent = await self._fetch_objective(session, objective_id, brand_id)
        if parent is None:
            raise ValueError(f"目标不存在: {objective_id}")

        if parent["period_type"] != "quarter":
            raise ValueError(
                f"只能对季度目标执行月度拆分，当前类型: {parent['period_type']}"
            )

        quarter = parent["period_value"]
        fiscal_year = parent["fiscal_year"]
        target_value = parent["target_value"]
        floor_value = parent.get("floor_value") or 0
        stretch_value = parent.get("stretch_value") or 0

        # 计算季度内3个月的天数权重
        start_month = (quarter - 1) * 3 + 1
        month_range = range(start_month, start_month + 3)
        month_days = {m: monthrange(fiscal_year, m)[1] for m in month_range}
        total_days = sum(month_days.values())

        months: List[Dict[str, Any]] = []

        for m in month_range:
            weight = month_days[m] / total_days
            m_target = int(target_value * weight)
            m_floor = int(floor_value * weight) if floor_value else None
            m_stretch = int(stretch_value * weight) if stretch_value else None

            m_id = str(uuid.uuid4())
            await session.execute(
                text("""
                    INSERT INTO business_objectives
                        (id, brand_id, store_id, parent_id, level,
                         fiscal_year, period_type, period_value,
                         objective_name, metric_code, target_value,
                         floor_value, stretch_value, unit,
                         bsc_dimension, status)
                    VALUES
                        (:id, :brand_id, :store_id, :parent_id, :level,
                         :fiscal_year, 'month', :period_value,
                         :objective_name, :metric_code, :target_value,
                         :floor_value, :stretch_value, :unit,
                         :bsc_dimension, 'active')
                """),
                {
                    "id": m_id,
                    "brand_id": brand_id,
                    "store_id": parent.get("store_id"),
                    "parent_id": objective_id,
                    "level": parent["level"],
                    "fiscal_year": fiscal_year,
                    "period_value": m,
                    "objective_name": f"{parent['objective_name']} - {m}月",
                    "metric_code": parent["metric_code"],
                    "target_value": m_target,
                    "floor_value": m_floor,
                    "stretch_value": m_stretch,
                    "unit": parent["unit"],
                    "bsc_dimension": parent["bsc_dimension"],
                },
            )

            months.append({
                "id": m_id,
                "month": m,
                "days": month_days[m],
                "weight": round(weight, 4),
                "target_value_fen": m_target,
                "target_value_yuan": round(m_target / 100, 2),
            })

        logger.info(
            "okr_cascade.quarter_to_months.done",
            brand_id=brand_id,
            parent_id=objective_id,
            quarter=quarter,
        )

        return {
            "parent_id": objective_id,
            "quarter": quarter,
            "quarter_target_yuan": round(target_value / 100, 2),
            "months": months,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 方法3: 智能门店分配引擎
    # ─────────────────────────────────────────────────────────────────────
    async def smart_allocation(
        self,
        session: AsyncSession,
        brand_id: str,
        source_id: str,
        target_store_ids: List[str],
        method: str = "by_capacity",
    ) -> Dict[str, Any]:
        """智能分配目标到多家门店

        Args:
            method: by_capacity | by_potential | by_equal

        Returns:
            {"source_id": "...", "method": "...",
             "allocations": [{"store_id": "...", "target_yuan": ..., "reason": "..."}, ...]}
        """
        if not target_store_ids:
            raise ValueError("目标门店列表不能为空")

        source = await self._fetch_objective(session, source_id, brand_id)
        if source is None:
            raise ValueError(f"源目标不存在: {source_id}")

        total_target = source["target_value"]
        store_count = len(target_store_ids)

        # 获取门店能力数据
        store_data = await self._fetch_store_capabilities(
            session, brand_id, target_store_ids
        )

        # 计算各门店权重
        if method == "by_capacity":
            weights = self._calc_capacity_weights(store_data, target_store_ids)
        elif method == "by_potential":
            weights = self._calc_potential_weights(store_data, target_store_ids)
        elif method == "by_equal":
            equal_w = 1.0 / store_count
            weights = {sid: equal_w for sid in target_store_ids}
        else:
            raise ValueError(f"不支持的分配方式: {method}")

        allocations: List[Dict[str, Any]] = []

        # 分配并写入子目标（尾差修正）
        allocated_sum = 0
        sorted_stores = sorted(target_store_ids)

        for i, store_id in enumerate(sorted_stores):
            w = weights.get(store_id, 1.0 / store_count)

            if i == len(sorted_stores) - 1:
                # 最后一家店吃掉尾差
                store_target = total_target - allocated_sum
            else:
                store_target = int(total_target * w)
                allocated_sum += store_target

            reason = self._build_allocation_reason(
                method, w, store_data.get(store_id, {})
            )

            s_id = str(uuid.uuid4())
            await session.execute(
                text("""
                    INSERT INTO business_objectives
                        (id, brand_id, store_id, parent_id, level,
                         fiscal_year, period_type, period_value,
                         objective_name, metric_code, target_value,
                         floor_value, stretch_value, unit,
                         bsc_dimension, status)
                    VALUES
                        (:id, :brand_id, :store_id, :parent_id, 'store',
                         :fiscal_year, :period_type, :period_value,
                         :objective_name, :metric_code, :target_value,
                         :floor_value, :stretch_value, :unit,
                         :bsc_dimension, 'active')
                """),
                {
                    "id": s_id,
                    "brand_id": brand_id,
                    "store_id": store_id,
                    "parent_id": source_id,
                    "fiscal_year": source["fiscal_year"],
                    "period_type": source["period_type"],
                    "period_value": source["period_value"],
                    "objective_name": f"{source['objective_name']} - 门店分配",
                    "metric_code": source["metric_code"],
                    "target_value": store_target,
                    "floor_value": int(
                        (source.get("floor_value") or 0) * w
                    ) if source.get("floor_value") else None,
                    "stretch_value": int(
                        (source.get("stretch_value") or 0) * w
                    ) if source.get("stretch_value") else None,
                    "unit": source["unit"],
                    "bsc_dimension": source["bsc_dimension"],
                },
            )

            allocations.append({
                "id": s_id,
                "store_id": store_id,
                "weight": round(w, 4),
                "target_value_fen": store_target,
                "target_value_yuan": round(store_target / 100, 2),
                "reason": reason,
            })

        logger.info(
            "okr_cascade.smart_allocation.done",
            brand_id=brand_id,
            source_id=source_id,
            method=method,
            store_count=store_count,
        )

        return {
            "source_id": source_id,
            "method": method,
            "total_target_yuan": round(total_target / 100, 2),
            "allocations": allocations,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 方法4: 一键全链路级联
    # ─────────────────────────────────────────────────────────────────────
    async def auto_cascade_full(
        self,
        session: AsyncSession,
        brand_id: str,
        annual_objective_id: str,
        store_ids: List[str],
        quarter_weights: Optional[Dict[int, float]] = None,
        allocation_method: str = "by_capacity",
    ) -> Dict[str, Any]:
        """一键完成全链路级联：年度→季度→月度→门店

        Returns:
            {"annual_id": "...", "quarter_results": [...],
             "month_results": [...], "store_results": [...]}
        """
        logger.info(
            "okr_cascade.auto_cascade_full.start",
            brand_id=brand_id,
            annual_id=annual_objective_id,
            store_count=len(store_ids),
        )

        # 1. 年度 → 季度
        quarter_result = await self.cascade_annual_to_quarters(
            session, brand_id, annual_objective_id, quarter_weights
        )

        # 2. 每个季度 → 月度
        month_results: List[Dict[str, Any]] = []
        for q in quarter_result["quarters"]:
            month_result = await self.cascade_quarter_to_months(
                session, brand_id, q["id"]
            )
            month_results.append(month_result)

        # 3. 每个月度目标 → 门店分配
        store_results: List[Dict[str, Any]] = []
        for mr in month_results:
            for m in mr["months"]:
                store_result = await self.smart_allocation(
                    session, brand_id, m["id"], store_ids, allocation_method
                )
                store_results.append(store_result)

        total_objectives = (
            len(quarter_result["quarters"])
            + sum(len(mr["months"]) for mr in month_results)
            + sum(len(sr["allocations"]) for sr in store_results)
        )

        logger.info(
            "okr_cascade.auto_cascade_full.done",
            brand_id=brand_id,
            total_objectives_created=total_objectives,
        )

        return {
            "annual_id": annual_objective_id,
            "total_objectives_created": total_objectives,
            "quarter_results": quarter_result,
            "month_results": month_results,
            "store_results": store_results,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 方法5: 级联健康度检查
    # ─────────────────────────────────────────────────────────────────────
    async def check_cascade_health(
        self,
        session: AsyncSession,
        brand_id: str,
        fiscal_year: int,
    ) -> Dict[str, Any]:
        """检查目标级联的健康度

        验证：
          - 子目标之和是否等于父目标
          - 有无孤立目标（有parent_id但parent不存在）
          - 有无缺失月份（季度目标下少于3个月度目标）

        Returns:
            {"healthy": True/False, "issues": [...], "summary": {...}}
        """
        logger.info(
            "okr_cascade.check_health.start",
            brand_id=brand_id,
            fiscal_year=fiscal_year,
        )

        issues: List[Dict[str, Any]] = []

        # 1. 检查子目标之和 vs 父目标
        sum_check_result = await session.execute(
            text("""
                WITH parent_child AS (
                    SELECT
                        p.id AS parent_id,
                        p.objective_name AS parent_name,
                        p.target_value AS parent_target,
                        p.period_type AS parent_period,
                        COALESCE(SUM(c.target_value), 0) AS children_sum,
                        COUNT(c.id) AS child_count
                    FROM business_objectives p
                    LEFT JOIN business_objectives c ON c.parent_id = p.id
                    WHERE p.brand_id = :brand_id
                      AND p.fiscal_year = :fiscal_year
                      AND p.status = 'active'
                    GROUP BY p.id, p.objective_name, p.target_value, p.period_type
                )
                SELECT parent_id, parent_name, parent_target,
                       parent_period, children_sum, child_count
                FROM parent_child
                WHERE child_count > 0
                  AND ABS(children_sum - parent_target) > 1
            """),
            {"brand_id": brand_id, "fiscal_year": fiscal_year},
        )

        for row in sum_check_result.fetchall():
            diff_fen = abs(row[4] - row[2])
            issues.append({
                "type": "sum_mismatch",
                "severity": "warning" if diff_fen < 100 else "error",
                "parent_id": str(row[0]),
                "parent_name": row[1],
                "parent_target_yuan": round(row[2] / 100, 2),
                "children_sum_yuan": round(row[4] / 100, 2),
                "diff_yuan": round(diff_fen / 100, 2),
                "message": (
                    f"目标'{row[1]}'的子目标之和"
                    f"(¥{round(row[4] / 100, 2)}) "
                    f"与父目标(¥{round(row[2] / 100, 2)})不一致，"
                    f"差额¥{round(diff_fen / 100, 2)}"
                ),
            })

        # 2. 检查孤立目标
        orphan_result = await session.execute(
            text("""
                SELECT o.id, o.objective_name, o.parent_id
                FROM business_objectives o
                LEFT JOIN business_objectives p ON o.parent_id = p.id
                WHERE o.brand_id = :brand_id
                  AND o.fiscal_year = :fiscal_year
                  AND o.parent_id IS NOT NULL
                  AND p.id IS NULL
            """),
            {"brand_id": brand_id, "fiscal_year": fiscal_year},
        )

        for row in orphan_result.fetchall():
            issues.append({
                "type": "orphan_objective",
                "severity": "error",
                "objective_id": str(row[0]),
                "objective_name": row[1],
                "missing_parent_id": str(row[2]),
                "message": f"目标'{row[1]}'引用的父目标不存在",
            })

        # 3. 检查季度目标下的月度覆盖
        month_coverage_result = await session.execute(
            text("""
                SELECT
                    q.id AS quarter_id,
                    q.objective_name,
                    q.period_value AS quarter,
                    COUNT(m.id) AS month_count,
                    ARRAY_AGG(m.period_value ORDER BY m.period_value)
                        FILTER (WHERE m.id IS NOT NULL) AS months
                FROM business_objectives q
                LEFT JOIN business_objectives m
                    ON m.parent_id = q.id AND m.period_type = 'month'
                WHERE q.brand_id = :brand_id
                  AND q.fiscal_year = :fiscal_year
                  AND q.period_type = 'quarter'
                  AND q.status = 'active'
                GROUP BY q.id, q.objective_name, q.period_value
                HAVING COUNT(m.id) < 3
            """),
            {"brand_id": brand_id, "fiscal_year": fiscal_year},
        )

        for row in month_coverage_result.fetchall():
            quarter = row[2]
            existing_months = row[4] or []
            expected_months = list(range((quarter - 1) * 3 + 1, quarter * 3 + 1))
            missing = [m for m in expected_months if m not in existing_months]

            issues.append({
                "type": "missing_months",
                "severity": "warning",
                "quarter_id": str(row[0]),
                "objective_name": row[1],
                "quarter": quarter,
                "existing_months": existing_months,
                "missing_months": missing,
                "message": (
                    f"Q{quarter}目标'{row[1]}'缺少{len(missing)}个月度目标: "
                    f"{', '.join(f'{m}月' for m in missing)}"
                ),
            })

        # 汇总
        error_count = sum(1 for i in issues if i["severity"] == "error")
        warning_count = sum(1 for i in issues if i["severity"] == "warning")
        healthy = error_count == 0

        logger.info(
            "okr_cascade.check_health.done",
            brand_id=brand_id,
            fiscal_year=fiscal_year,
            healthy=healthy,
            error_count=error_count,
            warning_count=warning_count,
        )

        return {
            "healthy": healthy,
            "fiscal_year": fiscal_year,
            "summary": {
                "error_count": error_count,
                "warning_count": warning_count,
                "total_issues": len(issues),
            },
            "issues": issues,
        }

    # ═════════════════════════════════════════════════════════════════════
    # 私有方法
    # ═════════════════════════════════════════════════════════════════════

    async def _fetch_objective(
        self,
        session: AsyncSession,
        objective_id: str,
        brand_id: str,
    ) -> Optional[Dict[str, Any]]:
        """查询单个目标"""
        result = await session.execute(
            text("""
                SELECT id, brand_id, store_id, parent_id, level,
                       fiscal_year, period_type, period_value,
                       objective_name, metric_code, target_value,
                       floor_value, stretch_value, unit, bsc_dimension, status
                FROM business_objectives
                WHERE id = :id AND brand_id = :brand_id
            """),
            {"id": objective_id, "brand_id": brand_id},
        )
        row = result.fetchone()
        if row is None:
            return None

        return {
            "id": str(row[0]),
            "brand_id": row[1],
            "store_id": row[2],
            "parent_id": str(row[3]) if row[3] else None,
            "level": row[4],
            "fiscal_year": row[5],
            "period_type": row[6],
            "period_value": row[7],
            "objective_name": row[8],
            "metric_code": row[9],
            "target_value": row[10],
            "floor_value": row[11],
            "stretch_value": row[12],
            "unit": row[13],
            "bsc_dimension": row[14],
            "status": row[15],
        }

    async def _fetch_store_capabilities(
        self,
        session: AsyncSession,
        brand_id: str,
        store_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """查询门店能力数据（座位数、面积、历史营收、模型评分）"""
        result = await session.execute(
            text("""
                SELECT
                    s.id,
                    COALESCE(s.seats, 0) AS seats,
                    0 AS area_sqm,
                    COALESCE(rev.avg_revenue_fen, 0) AS avg_revenue_fen,
                    0 AS store_model_score
                FROM stores s
                LEFT JOIN LATERAL (
                    SELECT AVG(revenue) AS avg_revenue_fen
                    FROM store_pnl
                    WHERE store_id = s.id
                      AND brand_id = :brand_id
                      AND report_date >= CURRENT_DATE - INTERVAL '90 days'
                ) rev ON TRUE
                WHERE s.id = ANY(:store_ids)
                  AND s.brand_id = :brand_id
            """),
            {"brand_id": brand_id, "store_ids": store_ids},
        )

        data: Dict[str, Dict[str, Any]] = {}
        for row in result.fetchall():
            data[row[0]] = {
                "seats": int(row[1]),
                "area_sqm": int(row[2]),
                "avg_revenue_fen": int(row[3]),
                "store_model_score": float(row[4]),
            }

        return data

    def _calc_capacity_weights(
        self,
        store_data: Dict[str, Dict[str, Any]],
        store_ids: List[str],
    ) -> Dict[str, float]:
        """按综合容量计算权重：seats×0.4 + area×0.3 + historical_revenue×0.3"""
        scores: Dict[str, float] = {}

        # 归一化各维度
        all_seats = [store_data.get(s, {}).get("seats", 0) for s in store_ids]
        all_area = [store_data.get(s, {}).get("area_sqm", 0) for s in store_ids]
        all_rev = [store_data.get(s, {}).get("avg_revenue_fen", 0) for s in store_ids]

        max_seats = max(all_seats) if max(all_seats) > 0 else 1
        max_area = max(all_area) if max(all_area) > 0 else 1
        max_rev = max(all_rev) if max(all_rev) > 0 else 1

        for sid in store_ids:
            d = store_data.get(sid, {})
            norm_seats = d.get("seats", 0) / max_seats
            norm_area = d.get("area_sqm", 0) / max_area
            norm_rev = d.get("avg_revenue_fen", 0) / max_rev

            score = norm_seats * 0.4 + norm_area * 0.3 + norm_rev * 0.3
            # 保底：每家店至少得到均分的50%
            scores[sid] = max(score, 0.5 / len(store_ids))

        # 归一化为权重
        total = sum(scores.values())
        return {sid: s / total for sid, s in scores.items()}

    def _calc_potential_weights(
        self,
        store_data: Dict[str, Dict[str, Any]],
        store_ids: List[str],
    ) -> Dict[str, float]:
        """按潜力评分分配：分数低的分配少一些（能力匹配）"""
        scores: Dict[str, float] = {}

        for sid in store_ids:
            d = store_data.get(sid, {})
            model_score = d.get("store_model_score", 0.5)
            # 确保有一个合理的底分
            scores[sid] = max(model_score, 0.1)

        total = sum(scores.values())
        if total == 0:
            equal_w = 1.0 / len(store_ids)
            return {sid: equal_w for sid in store_ids}

        return {sid: s / total for sid, s in scores.items()}

    def _build_allocation_reason(
        self,
        method: str,
        weight: float,
        store_info: Dict[str, Any],
    ) -> str:
        """生成分配理由说明"""
        pct = round(weight * 100, 1)

        if method == "by_capacity":
            seats = store_info.get("seats", 0)
            rev_yuan = round(store_info.get("avg_revenue_fen", 0) / 100, 2)
            return (
                f"综合容量评分分配{pct}%"
                f"（座位{seats}个，近90天日均营收¥{rev_yuan}）"
            )
        elif method == "by_potential":
            score = store_info.get("store_model_score", 0)
            return f"潜力评分{score:.2f}，分配{pct}%"
        elif method == "by_equal":
            return f"均分分配{pct}%"

        return f"分配{pct}%"
