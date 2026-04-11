"""
标杆引擎服务 (Benchmark Engine Service)

基于 BSC 四维度（财务/客户/流程/学习）提供：
1. 同品牌门店排名
2. 标杆门店匹配（规模相近 + 业绩更优）
3. 差距分析 + 规则引擎改善建议
4. 品牌级跨门店洞察（HQ 看板）
5. 单店综合评分卡（"体检报告"）
"""

from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 常量 ─────────────────────────────────────────────────────────────────

# 门店分层阈值（基于 store_model_score）
TIER_THRESHOLDS = {"A": 80, "B": 60, "C": 40}  # >=80 A, >=60 B, >=40 C, <40 D

# BSC 评分卡权重
BSC_WEIGHTS = {
    "financial": 0.35,
    "customer": 0.25,
    "process": 0.25,
    "learning": 0.15,
}

# 金额字段列表（DB 存分，需转元）
FEN_FIELDS = {
    "revenue_fen", "cost_material_fen", "cost_labor_fen",
    "waste_value_fen", "avg_ticket_fen", "total_revenue_fen",
    "revenue_per_seat_fen", "revenue_per_employee_fen",
}


def _fen_to_yuan(value: Optional[int]) -> Optional[float]:
    """分转元，保留2位小数"""
    if value is None:
        return None
    return round(value / 100, 2)


def _safe_div(a, b, default=0.0):
    """安全除法"""
    if not b:
        return default
    return a / b


def _pct_gap(current, benchmark, default=0.0):
    """计算差距百分比：(benchmark - current) / benchmark"""
    if not benchmark:
        return default
    return round((benchmark - current) / abs(benchmark) * 100, 2)


def _stats(values: List[float]) -> Dict[str, float]:
    """计算均值和标准差"""
    if not values:
        return {"mean": 0.0, "std": 0.0}
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return {"mean": round(mean, 4), "std": round(variance ** 0.5, 4)}


class BenchmarkEngineService:
    """标杆引擎服务 — BSC 四维度对标分析 + 改善建议"""

    # ═════════════════════════════════════════════════════════════════════
    # 方法1: 同品牌门店排名
    # ═════════════════════════════════════════════════════════════════════

    async def get_peer_ranking(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        period_type: str = "monthly",
        metric: str = "revenue_fen",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """同品牌门店排名。

        从 operation_snapshots 获取最近一个完整周期数据，
        按指定 metric 排序，返回排名、Top3/Bottom3、与第一名差距。
        """

        # 1. 获取最近一个完整周期的 snapshot_date
        latest_row = (
            await session.execute(
                text("""
                    SELECT MAX(snapshot_date) AS latest_date
                      FROM operation_snapshots
                     WHERE brand_id    = :brand_id
                       AND period_type = :period_type
                """),
                {"brand_id": brand_id, "period_type": period_type},
            )
        ).mappings().first()

        if not latest_row or not latest_row["latest_date"]:
            logger.warning("peer_ranking.no_data", brand_id=brand_id)
            return {"ranking": None, "message": "暂无数据"}

        latest_date = latest_row["latest_date"]

        # 2. 白名单校验 metric（防注入）
        allowed_metrics = {
            "revenue_fen", "customer_count", "order_count",
            "avg_ticket_fen", "table_turnover_rate",
            "cost_material_fen", "cost_labor_fen", "waste_value_fen",
        }
        if metric not in allowed_metrics:
            logger.warning("peer_ranking.invalid_metric", metric=metric)
            return {"ranking": None, "message": f"不支持的指标: {metric}"}

        # 3. 查询所有同品牌门店该周期数据（metric 通过白名单验证后安全拼入）
        rows = (
            await session.execute(
                text(f"""
                    SELECT os.store_id,
                           s.name AS store_name,
                           os.{metric} AS metric_value
                      FROM operation_snapshots os
                      JOIN stores s ON s.id = os.store_id
                     WHERE os.brand_id      = :brand_id
                       AND os.period_type   = :period_type
                       AND os.snapshot_date = :latest_date
                       AND s.is_active = true
                     ORDER BY os.{metric} DESC
                     LIMIT :lmt
                """),
                {
                    "brand_id": brand_id,
                    "period_type": period_type,
                    "latest_date": latest_date,
                    "lmt": limit,
                },
            )
        ).mappings().all()

        if not rows:
            return {"ranking": None, "message": "暂无门店数据"}

        # 4. 构建排名列表
        ranked = []
        my_rank = None
        my_value = None
        top_value = None

        for idx, r in enumerate(rows, 1):
            val = r["metric_value"] or 0
            if idx == 1:
                top_value = val

            is_yuan = metric in FEN_FIELDS
            display_val = _fen_to_yuan(val) if is_yuan else val

            entry = {
                "rank": idx,
                "store_id": r["store_id"],
                "store_name": r["store_name"],
                "value": display_val,
            }
            ranked.append(entry)

            if str(r["store_id"]) == str(store_id):
                my_rank = idx
                my_value = val

        total = len(ranked)
        top3 = ranked[:3]
        bottom3 = ranked[-3:] if total >= 3 else ranked

        # 与第一名的差距
        gap_to_first = None
        if my_value is not None and top_value is not None:
            raw_gap = top_value - my_value
            is_yuan = metric in FEN_FIELDS
            gap_to_first = {
                "value": _fen_to_yuan(raw_gap) if is_yuan else raw_gap,
                "percentage": round(_safe_div(raw_gap, top_value) * 100, 2),
            }

        return {
            "period_type": period_type,
            "snapshot_date": str(latest_date),
            "metric": metric,
            "my_rank": my_rank,
            "total_stores": total,
            "top3": top3,
            "bottom3": bottom3,
            "my_entry": next((e for e in ranked if str(e["store_id"]) == str(store_id)), None),
            "gap_to_first": gap_to_first,
        }

    # ═════════════════════════════════════════════════════════════════════
    # 方法2: 标杆门店匹配
    # ═════════════════════════════════════════════════════════════════════

    async def find_benchmark_stores(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        top_n: int = 3,
    ) -> Dict[str, Any]:
        """找到与目标门店规模相近但业绩更好的标杆门店。

        相似度 = w1 * seats差异归一化 + w2 * area差异归一化 + w3 * 商圈相同
        筛选：同品牌、active、营收或利润率高于目标门店
        """

        # 1. 获取目标门店基础信息
        target = (
            await session.execute(
                text("""
                    SELECT id, name, city, district, area, seats
                      FROM stores
                     WHERE id       = :store_id
                       AND brand_id = :brand_id
                """),
                {"store_id": store_id, "brand_id": brand_id},
            )
        ).mappings().first()

        if not target:
            logger.warning("benchmark.store_not_found", store_id=store_id)
            return {"benchmarks": [], "message": "门店不存在"}

        # 2. 获取目标门店最新月度快照
        target_snap = (
            await session.execute(
                text("""
                    SELECT revenue_fen, cost_material_fen, cost_labor_fen,
                           customer_count, order_count, avg_ticket_fen,
                           table_turnover_rate, waste_value_fen, employee_count
                      FROM operation_snapshots
                     WHERE store_id    = :store_id
                       AND brand_id    = :brand_id
                       AND period_type = 'monthly'
                     ORDER BY snapshot_date DESC
                     LIMIT 1
                """),
                {"store_id": store_id, "brand_id": brand_id},
            )
        ).mappings().first()

        if not target_snap:
            return {"benchmarks": [], "message": "目标门店暂无运营数据"}

        target_revenue = target_snap["revenue_fen"] or 0

        # 3. 获取目标门店最新 PNL 的 gross_margin
        target_pnl = (
            await session.execute(
                text("""
                    SELECT gross_margin, operating_margin, material_cost_ratio,
                           labor_cost_ratio, revenue_per_seat_fen, revenue_per_employee_fen
                      FROM store_pnl
                     WHERE store_id    = :store_id
                       AND period_type = 'monthly'
                     ORDER BY period_date DESC
                     LIMIT 1
                """),
                {"store_id": store_id},
            )
        ).mappings().first()

        target_gross_margin = float(target_pnl["gross_margin"] or 0) if target_pnl else 0

        # 4. 获取同品牌所有活跃门店 + 最新快照 + PNL
        candidates = (
            await session.execute(
                text("""
                    SELECT s.id AS store_id, s.name, s.city, s.district,
                           s.area, s.seats,
                           os.revenue_fen, os.cost_material_fen, os.cost_labor_fen,
                           os.customer_count, os.order_count, os.avg_ticket_fen,
                           os.table_turnover_rate, os.waste_value_fen, os.employee_count,
                           pnl.gross_margin, pnl.operating_margin, pnl.material_cost_ratio,
                           pnl.labor_cost_ratio
                      FROM stores s
                      JOIN LATERAL (
                           SELECT * FROM operation_snapshots
                            WHERE store_id   = s.id
                              AND brand_id   = :brand_id
                              AND period_type = 'monthly'
                            ORDER BY snapshot_date DESC
                            LIMIT 1
                      ) os ON true
                      LEFT JOIN LATERAL (
                           SELECT * FROM store_pnl
                            WHERE store_id   = s.id
                              AND period_type = 'monthly'
                            ORDER BY period_date DESC
                            LIMIT 1
                      ) pnl ON true
                     WHERE s.brand_id  = :brand_id
                       AND s.is_active = true
                       AND s.id       != :store_id
                       AND (os.revenue_fen > :target_revenue
                            OR COALESCE(pnl.gross_margin, 0) > :target_gm)
                """),
                {
                    "brand_id": brand_id,
                    "store_id": store_id,
                    "target_revenue": target_revenue,
                    "target_gm": target_gross_margin,
                },
            )
        ).mappings().all()

        if not candidates:
            return {"benchmarks": [], "message": "暂无符合条件的标杆门店"}

        # 5. 计算相似度并排序
        target_seats = target["seats"] or 0
        target_area = target["area"] or 0
        target_district = target["district"] or ""

        scored = []
        for c in candidates:
            c_seats = c["seats"] or 0
            c_area = c["area"] or 0
            c_district = c["district"] or ""

            # 归一化差异（差异越小分越高）
            seats_sim = 1.0 - min(abs(c_seats - target_seats) / max(target_seats, 1), 1.0)
            area_sim = 1.0 - min(abs(c_area - target_area) / max(target_area, 1), 1.0)
            district_sim = 1.0 if c_district == target_district else 0.0

            similarity = 0.4 * seats_sim + 0.4 * area_sim + 0.2 * district_sim

            scored.append({
                "store_id": c["store_id"],
                "store_name": c["name"],
                "city": c["city"],
                "district": c_district,
                "seats": c_seats,
                "area": float(c_area),
                "similarity_score": round(similarity, 3),
                "comparison": {
                    "revenue_yuan": _fen_to_yuan(c["revenue_fen"]),
                    "target_revenue_yuan": _fen_to_yuan(target_revenue),
                    "gross_margin": float(c["gross_margin"] or 0),
                    "target_gross_margin": target_gross_margin,
                    "operating_margin": float(c["operating_margin"] or 0),
                    "material_cost_ratio": float(c["material_cost_ratio"] or 0),
                    "customer_count": c["customer_count"],
                    "avg_ticket_yuan": _fen_to_yuan(c["avg_ticket_fen"]),
                    "table_turnover_rate": float(c["table_turnover_rate"] or 0),
                },
            })

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        benchmarks = scored[:top_n]

        return {
            "store_id": store_id,
            "target_store": {
                "name": target["name"],
                "seats": target_seats,
                "area": float(target_area),
                "district": target_district,
                "revenue_yuan": _fen_to_yuan(target_revenue),
                "gross_margin": target_gross_margin,
            },
            "benchmarks": benchmarks,
        }

    # ═════════════════════════════════════════════════════════════════════
    # 方法3: 差距分析（BSC 四维）
    # ═════════════════════════════════════════════════════════════════════

    async def gap_analysis(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
    ) -> Dict[str, Any]:
        """BSC 四维度差距分析：财务/客户/流程/学习。

        对每个指标计算：当前值、品牌均值、标杆值、差距百分比、改善建议。
        """

        # 1. 获取目标门店最新月度快照 + PNL
        store_data = (
            await session.execute(
                text("""
                    SELECT os.revenue_fen, os.cost_material_fen, os.cost_labor_fen,
                           os.customer_count, os.order_count, os.avg_ticket_fen,
                           os.table_turnover_rate, os.waste_value_fen, os.employee_count,
                           os.snapshot_date,
                           pnl.gross_margin, pnl.operating_margin,
                           pnl.material_cost_ratio, pnl.labor_cost_ratio,
                           pnl.revenue_per_employee_fen
                      FROM operation_snapshots os
                      LEFT JOIN LATERAL (
                           SELECT * FROM store_pnl
                            WHERE store_id   = os.store_id
                              AND period_type = 'monthly'
                            ORDER BY period_date DESC
                            LIMIT 1
                      ) pnl ON true
                     WHERE os.store_id    = :store_id
                       AND os.brand_id    = :brand_id
                       AND os.period_type = 'monthly'
                     ORDER BY os.snapshot_date DESC
                     LIMIT 1
                """),
                {"store_id": store_id, "brand_id": brand_id},
            )
        ).mappings().first()

        if not store_data:
            return {"dimensions": [], "message": "暂无运营数据"}

        snapshot_date = store_data["snapshot_date"]

        # 2. 品牌均值
        brand_avg = (
            await session.execute(
                text("""
                    SELECT AVG(os.revenue_fen)          AS avg_revenue_fen,
                           AVG(os.customer_count)       AS avg_customer_count,
                           AVG(os.order_count)          AS avg_order_count,
                           AVG(os.avg_ticket_fen)       AS avg_ticket_fen,
                           AVG(os.table_turnover_rate)  AS avg_turnover_rate,
                           AVG(os.waste_value_fen)      AS avg_waste_fen,
                           AVG(os.employee_count)       AS avg_employee_count,
                           AVG(pnl.gross_margin)        AS avg_gross_margin,
                           AVG(pnl.operating_margin)    AS avg_operating_margin,
                           AVG(pnl.material_cost_ratio) AS avg_material_cost_ratio,
                           AVG(pnl.labor_cost_ratio)    AS avg_labor_cost_ratio,
                           AVG(pnl.revenue_per_employee_fen) AS avg_rev_per_emp_fen
                      FROM operation_snapshots os
                      JOIN stores s ON s.id = os.store_id AND s.is_active = true
                      LEFT JOIN LATERAL (
                           SELECT * FROM store_pnl
                            WHERE store_id   = os.store_id
                              AND period_type = 'monthly'
                            ORDER BY period_date DESC
                            LIMIT 1
                      ) pnl ON true
                     WHERE os.brand_id      = :brand_id
                       AND os.period_type   = 'monthly'
                       AND os.snapshot_date = :snapshot_date
                """),
                {"brand_id": brand_id, "snapshot_date": snapshot_date},
            )
        ).mappings().first()

        # 3. 标杆值（Top3 门店均值）
        benchmark_avg = (
            await session.execute(
                text("""
                    SELECT AVG(sub.revenue_fen)          AS bm_revenue_fen,
                           AVG(sub.customer_count)       AS bm_customer_count,
                           AVG(sub.order_count)          AS bm_order_count,
                           AVG(sub.avg_ticket_fen)       AS bm_ticket_fen,
                           AVG(sub.table_turnover_rate)  AS bm_turnover_rate,
                           AVG(sub.waste_value_fen)      AS bm_waste_fen,
                           AVG(sub.employee_count)       AS bm_employee_count,
                           AVG(sub.gross_margin)         AS bm_gross_margin,
                           AVG(sub.operating_margin)     AS bm_operating_margin,
                           AVG(sub.material_cost_ratio)  AS bm_material_cost_ratio,
                           AVG(sub.labor_cost_ratio)     AS bm_labor_cost_ratio,
                           AVG(sub.revenue_per_employee_fen) AS bm_rev_per_emp_fen
                      FROM (
                           SELECT os.revenue_fen, os.customer_count, os.order_count,
                                  os.avg_ticket_fen, os.table_turnover_rate,
                                  os.waste_value_fen, os.employee_count,
                                  pnl.gross_margin, pnl.operating_margin,
                                  pnl.material_cost_ratio, pnl.labor_cost_ratio,
                                  pnl.revenue_per_employee_fen
                             FROM operation_snapshots os
                             JOIN stores s ON s.id = os.store_id AND s.is_active = true
                             LEFT JOIN LATERAL (
                                  SELECT * FROM store_pnl
                                   WHERE store_id   = os.store_id
                                     AND period_type = 'monthly'
                                   ORDER BY period_date DESC
                                   LIMIT 1
                             ) pnl ON true
                            WHERE os.brand_id      = :brand_id
                              AND os.period_type   = 'monthly'
                              AND os.snapshot_date = :snapshot_date
                            ORDER BY os.revenue_fen DESC
                            LIMIT 3
                      ) sub
                """),
                {"brand_id": brand_id, "snapshot_date": snapshot_date},
            )
        ).mappings().first()

        if not brand_avg or not benchmark_avg:
            return {"dimensions": [], "message": "品牌数据不足"}

        # 4. 构建 BSC 四维度差距分析
        dimensions = self._build_gap_dimensions(store_data, brand_avg, benchmark_avg)

        return {
            "store_id": store_id,
            "snapshot_date": str(snapshot_date),
            "dimensions": dimensions,
        }

    def _build_gap_dimensions(
        self,
        store: Any,
        brand_avg: Any,
        benchmark: Any,
    ) -> List[Dict[str, Any]]:
        """构建 BSC 四维度差距明细 + 规则引擎建议"""

        def _f(v):
            """安全取浮点"""
            return float(v) if v is not None else 0.0

        # ── 财务维度 ──────────────────────────────────────────────────
        financial_metrics = [
            {
                "name": "营收",
                "unit": "yuan",
                "current": _fen_to_yuan(store["revenue_fen"]),
                "brand_avg": _fen_to_yuan(int(_f(brand_avg["avg_revenue_fen"]))),
                "benchmark": _fen_to_yuan(int(_f(benchmark["bm_revenue_fen"]))),
            },
            {
                "name": "毛利率",
                "unit": "%",
                "current": round(_f(store["gross_margin"]) * 100, 2),
                "brand_avg": round(_f(brand_avg["avg_gross_margin"]) * 100, 2),
                "benchmark": round(_f(benchmark["bm_gross_margin"]) * 100, 2),
            },
            {
                "name": "食材成本率",
                "unit": "%",
                "current": round(_f(store["material_cost_ratio"]) * 100, 2),
                "brand_avg": round(_f(brand_avg["avg_material_cost_ratio"]) * 100, 2),
                "benchmark": round(_f(benchmark["bm_material_cost_ratio"]) * 100, 2),
                "lower_is_better": True,
            },
            {
                "name": "营业利润率",
                "unit": "%",
                "current": round(_f(store["operating_margin"]) * 100, 2),
                "brand_avg": round(_f(brand_avg["avg_operating_margin"]) * 100, 2),
                "benchmark": round(_f(benchmark["bm_operating_margin"]) * 100, 2),
            },
        ]

        # ── 客户维度 ──────────────────────────────────────────────────
        customer_metrics = [
            {
                "name": "客流量",
                "unit": "人",
                "current": int(_f(store["customer_count"])),
                "brand_avg": round(_f(brand_avg["avg_customer_count"])),
                "benchmark": round(_f(benchmark["bm_customer_count"])),
            },
            {
                "name": "客单价",
                "unit": "yuan",
                "current": _fen_to_yuan(store["avg_ticket_fen"]),
                "brand_avg": _fen_to_yuan(int(_f(brand_avg["avg_ticket_fen"]))),
                "benchmark": _fen_to_yuan(int(_f(benchmark["bm_ticket_fen"]))),
            },
            {
                "name": "翻台率",
                "unit": "次",
                "current": round(_f(store["table_turnover_rate"]), 2),
                "brand_avg": round(_f(brand_avg["avg_turnover_rate"]), 2),
                "benchmark": round(_f(benchmark["bm_turnover_rate"]), 2),
            },
        ]

        # ── 流程维度 ──────────────────────────────────────────────────
        # 损耗率 = waste_value_fen / revenue_fen
        current_waste_ratio = round(
            _safe_div(_f(store["waste_value_fen"]), _f(store["revenue_fen"])) * 100, 2
        )
        avg_waste_ratio = round(
            _safe_div(_f(brand_avg["avg_waste_fen"]), _f(brand_avg["avg_revenue_fen"])) * 100, 2
        )
        bm_waste_ratio = round(
            _safe_div(_f(benchmark["bm_waste_fen"]), _f(benchmark["bm_revenue_fen"])) * 100, 2
        )

        process_metrics = [
            {
                "name": "损耗率",
                "unit": "%",
                "current": current_waste_ratio,
                "brand_avg": avg_waste_ratio,
                "benchmark": bm_waste_ratio,
                "lower_is_better": True,
            },
            {
                "name": "订单量",
                "unit": "单",
                "current": int(_f(store["order_count"])),
                "brand_avg": round(_f(brand_avg["avg_order_count"])),
                "benchmark": round(_f(benchmark["bm_order_count"])),
            },
        ]

        # ── 学习维度 ──────────────────────────────────────────────────
        current_rev_per_emp = _fen_to_yuan(store["revenue_per_employee_fen"]) or (
            _fen_to_yuan(int(_safe_div(_f(store["revenue_fen"]), _f(store["employee_count"]))))
        )
        avg_rev_per_emp = _fen_to_yuan(
            int(_f(brand_avg["avg_rev_per_emp_fen"]))
        ) or _fen_to_yuan(
            int(_safe_div(_f(brand_avg["avg_revenue_fen"]), max(_f(brand_avg["avg_employee_count"]), 1)))
        )
        bm_rev_per_emp = _fen_to_yuan(
            int(_f(benchmark["bm_rev_per_emp_fen"]))
        ) or _fen_to_yuan(
            int(_safe_div(_f(benchmark["bm_revenue_fen"]), max(_f(benchmark["bm_employee_count"]), 1)))
        )

        learning_metrics = [
            {
                "name": "员工数",
                "unit": "人",
                "current": int(_f(store["employee_count"])),
                "brand_avg": round(_f(brand_avg["avg_employee_count"])),
                "benchmark": round(_f(benchmark["bm_employee_count"])),
            },
            {
                "name": "人效(人均营收)",
                "unit": "yuan",
                "current": current_rev_per_emp,
                "brand_avg": avg_rev_per_emp,
                "benchmark": bm_rev_per_emp,
            },
        ]

        # ── 为每个指标计算差距 + 建议 ─────────────────────────────────
        all_dims = [
            ("financial", "财务", financial_metrics),
            ("customer", "客户", customer_metrics),
            ("process", "流程", process_metrics),
            ("learning", "学习与成长", learning_metrics),
        ]

        result = []
        for dim_key, dim_label, metrics in all_dims:
            enriched = []
            for m in metrics:
                lower_better = m.get("lower_is_better", False)
                cur = m["current"] or 0
                avg = m["brand_avg"] or 0
                bm = m["benchmark"] or 0

                if lower_better:
                    gap_vs_avg = round(cur - avg, 2)
                    gap_vs_bm = round(cur - bm, 2)
                else:
                    gap_vs_avg = round(avg - cur, 2)
                    gap_vs_bm = round(bm - cur, 2)

                gap_pct_avg = _pct_gap(cur, avg) if not lower_better else (
                    round((cur - avg) / max(abs(avg), 0.01) * 100, 2)
                )

                advice = self._rule_engine_advice(m["name"], cur, avg, bm, lower_better)

                enriched.append({
                    **m,
                    "gap_vs_avg": gap_vs_avg,
                    "gap_vs_benchmark": gap_vs_bm,
                    "gap_pct_vs_avg": gap_pct_avg,
                    "advice": advice,
                })

            result.append({
                "dimension": dim_key,
                "dimension_label": dim_label,
                "metrics": enriched,
            })

        return result

    def _rule_engine_advice(
        self,
        metric_name: str,
        current: float,
        avg: float,
        benchmark: float,
        lower_is_better: bool = False,
    ) -> Optional[str]:
        """规则引擎：基于当前值 vs 均值产生改善建议"""
        if not avg:
            return None

        if lower_is_better:
            deviation = (current - avg) / max(abs(avg), 0.01)
        else:
            deviation = (avg - current) / max(abs(avg), 0.01)

        rules = {
            "食材成本率": [
                (0.03, "建议检查供应商价格和损耗管理，食材成本率高于均值{pct}%"),
                (0.05, "食材成本率严重偏高，建议立即审查BOM配方和采购价格"),
            ],
            "翻台率": [
                (0.20, "建议优化出餐速度和翻台流程，翻台率低于均值{pct}%"),
                (0.35, "翻台率显著偏低，建议排查服务流程瓶颈和菜单结构"),
            ],
            "人效(人均营收)": [
                (0.15, "建议优化排班，减少闲时人力，人效低于均值{pct}%"),
                (0.30, "人效严重偏低，建议重新评估人员编制和技能培训"),
            ],
            "客流量": [
                (0.15, "客流低于均值{pct}%，建议加强营销引流和会员复购运营"),
                (0.30, "客流严重不足，建议排查选址/口碑/竞争因素"),
            ],
            "客单价": [
                (0.10, "客单价偏低{pct}%，建议优化菜单结构和推荐搭配策略"),
                (0.25, "客单价显著偏低，建议引入高毛利套餐和升级单品"),
            ],
            "毛利率": [
                (0.05, "毛利率低于均值{pct}%，建议检查食材损耗和定价策略"),
                (0.10, "毛利率严重偏低，建议全面审查成本结构"),
            ],
            "营业利润率": [
                (0.05, "营业利润率偏低{pct}%，建议控制可变成本"),
                (0.15, "利润率严重偏低，需综合优化成本和收入结构"),
            ],
            "损耗率": [
                (0.03, "损耗率高于均值{pct}%，建议加强备料管控和效期管理"),
                (0.08, "损耗率严重偏高，建议引入损耗追踪和问责机制"),
            ],
            "营收": [
                (0.15, "营收低于均值{pct}%，建议从客流和客单价两端发力"),
            ],
            "订单量": [
                (0.15, "订单量偏低{pct}%，建议优化线上渠道和高峰时段承接能力"),
            ],
        }

        metric_rules = rules.get(metric_name)
        if not metric_rules:
            return None

        pct_str = str(round(abs(deviation) * 100, 1))

        # 从高阈值到低阈值匹配
        for threshold, template in reversed(metric_rules):
            if deviation >= threshold:
                return template.format(pct=pct_str)

        return None

    # ═════════════════════════════════════════════════════════════════════
    # 方法4: 品牌级跨门店洞察（HQ 看板）
    # ═════════════════════════════════════════════════════════════════════

    async def cross_store_insights(
        self,
        session: AsyncSession,
        brand_id: str,
        period_type: str = "monthly",
    ) -> Dict[str, Any]:
        """品牌级跨门店洞察：KPI汇总、最佳/最差门店、异常检测、分层、改善优先级。"""

        # 1. 获取最新周期
        latest_row = (
            await session.execute(
                text("""
                    SELECT MAX(snapshot_date) AS latest_date
                      FROM operation_snapshots
                     WHERE brand_id    = :brand_id
                       AND period_type = :period_type
                """),
                {"brand_id": brand_id, "period_type": period_type},
            )
        ).mappings().first()

        if not latest_row or not latest_row["latest_date"]:
            return {"message": "暂无数据"}

        latest_date = latest_row["latest_date"]

        # 2. 获取所有门店数据
        all_stores = (
            await session.execute(
                text("""
                    SELECT s.id AS store_id, s.name AS store_name,
                           os.revenue_fen, os.cost_material_fen, os.cost_labor_fen,
                           os.customer_count, os.order_count, os.avg_ticket_fen,
                           os.table_turnover_rate, os.waste_value_fen, os.employee_count,
                           pnl.gross_margin, pnl.operating_margin,
                           pnl.material_cost_ratio, pnl.labor_cost_ratio,
                           bt.store_model_score
                      FROM operation_snapshots os
                      JOIN stores s ON s.id = os.store_id AND s.is_active = true
                      LEFT JOIN LATERAL (
                           SELECT * FROM store_pnl
                            WHERE store_id   = os.store_id
                              AND period_type = :period_type
                            ORDER BY period_date DESC
                            LIMIT 1
                      ) pnl ON true
                      LEFT JOIN LATERAL (
                           SELECT store_model_score FROM breakeven_tracker
                            WHERE store_id = os.store_id
                            ORDER BY calc_month DESC
                            LIMIT 1
                      ) bt ON true
                     WHERE os.brand_id      = :brand_id
                       AND os.period_type   = :period_type
                       AND os.snapshot_date = :latest_date
                     ORDER BY os.revenue_fen DESC
                """),
                {
                    "brand_id": brand_id,
                    "period_type": period_type,
                    "latest_date": latest_date,
                },
            )
        ).mappings().all()

        if not all_stores:
            return {"message": "暂无门店数据"}

        # ── 品牌整体 KPI 汇总 ────────────────────────────────────────
        total_revenue = sum(r["revenue_fen"] or 0 for r in all_stores)
        gm_values = [float(r["gross_margin"] or 0) for r in all_stores if r["gross_margin"]]
        mat_values = [float(r["material_cost_ratio"] or 0) for r in all_stores if r["material_cost_ratio"]]
        labor_values = [float(r["labor_cost_ratio"] or 0) for r in all_stores if r["labor_cost_ratio"]]
        turnover_values = [float(r["table_turnover_rate"] or 0) for r in all_stores if r["table_turnover_rate"]]

        brand_kpi = {
            "total_revenue_yuan": _fen_to_yuan(total_revenue),
            "store_count": len(all_stores),
            "avg_gross_margin": round(_safe_div(sum(gm_values), len(gm_values)) * 100, 2) if gm_values else 0,
            "avg_material_cost_ratio": round(_safe_div(sum(mat_values), len(mat_values)) * 100, 2) if mat_values else 0,
            "avg_labor_cost_ratio": round(_safe_div(sum(labor_values), len(labor_values)) * 100, 2) if labor_values else 0,
            "avg_table_turnover": round(_safe_div(sum(turnover_values), len(turnover_values)), 2) if turnover_values else 0,
        }

        # ── 最佳/最差门店 ────────────────────────────────────────────
        def _store_summary(r) -> Dict:
            return {
                "store_id": r["store_id"],
                "store_name": r["store_name"],
                "revenue_yuan": _fen_to_yuan(r["revenue_fen"]),
                "gross_margin": round(float(r["gross_margin"] or 0) * 100, 2),
                "customer_count": r["customer_count"],
                "table_turnover_rate": round(float(r["table_turnover_rate"] or 0), 2),
            }

        best_stores = [_store_summary(r) for r in all_stores[:3]]
        worst_stores = [_store_summary(r) for r in all_stores[-3:]]

        # ── 异常门店检测（偏离均值 > 2 标准差）──────────────────────
        anomalies = []
        anomaly_metrics = {
            "revenue_fen": [r["revenue_fen"] or 0 for r in all_stores],
            "gross_margin": [float(r["gross_margin"] or 0) for r in all_stores],
            "material_cost_ratio": [float(r["material_cost_ratio"] or 0) for r in all_stores],
            "table_turnover_rate": [float(r["table_turnover_rate"] or 0) for r in all_stores],
        }

        metric_labels = {
            "revenue_fen": "营收",
            "gross_margin": "毛利率",
            "material_cost_ratio": "食材成本率",
            "table_turnover_rate": "翻台率",
        }

        for metric_key, values in anomaly_metrics.items():
            st = _stats(values)
            mean, std = st["mean"], st["std"]
            if std <= 0:
                continue

            for i, r in enumerate(all_stores):
                v = values[i]
                z = (v - mean) / std
                if abs(z) >= 2.0:
                    anomalies.append({
                        "store_id": r["store_id"],
                        "store_name": r["store_name"],
                        "metric": metric_labels.get(metric_key, metric_key),
                        "value": _fen_to_yuan(int(v)) if metric_key.endswith("_fen") else round(v * 100, 2) if metric_key in ("gross_margin", "material_cost_ratio") else round(v, 2),
                        "z_score": round(z, 2),
                        "direction": "above" if z > 0 else "below",
                    })

        # ── 门店分层（A/B/C/D）基于 store_model_score ────────────────
        tiers = {"A": [], "B": [], "C": [], "D": []}
        for r in all_stores:
            score = float(r["store_model_score"] or 0)
            if score >= TIER_THRESHOLDS["A"]:
                tier = "A"
            elif score >= TIER_THRESHOLDS["B"]:
                tier = "B"
            elif score >= TIER_THRESHOLDS["C"]:
                tier = "C"
            else:
                tier = "D"
            tiers[tier].append({
                "store_id": r["store_id"],
                "store_name": r["store_name"],
                "score": score,
            })

        tier_summary = {k: {"count": len(v), "stores": v} for k, v in tiers.items()}

        # ── 改善优先级（提升空间最大的门店）─────────────────────────
        improvement_priority = []
        for r in all_stores:
            rev = r["revenue_fen"] or 0
            gm = float(r["gross_margin"] or 0)
            score = float(r["store_model_score"] or 0)

            # 综合提升空间 = 营收差距 + 毛利率差距 + 分数偏低
            avg_rev = _safe_div(total_revenue, len(all_stores))
            avg_gm = _safe_div(sum(gm_values), len(gm_values)) if gm_values else 0

            rev_gap = max(avg_rev - rev, 0) / max(avg_rev, 1)
            gm_gap = max(avg_gm - gm, 0) / max(avg_gm, 0.01)
            score_gap = max(60 - score, 0) / 60

            potential = 0.4 * rev_gap + 0.35 * gm_gap + 0.25 * score_gap
            improvement_priority.append({
                "store_id": r["store_id"],
                "store_name": r["store_name"],
                "improvement_potential": round(potential, 3),
                "revenue_yuan": _fen_to_yuan(rev),
                "gross_margin_pct": round(gm * 100, 2),
                "model_score": score,
            })

        improvement_priority.sort(key=lambda x: x["improvement_potential"], reverse=True)

        return {
            "brand_id": brand_id,
            "period_type": period_type,
            "snapshot_date": str(latest_date),
            "brand_kpi": brand_kpi,
            "best_stores": best_stores,
            "worst_stores": worst_stores,
            "anomalies": anomalies,
            "tier_summary": tier_summary,
            "improvement_priority": improvement_priority[:10],
        }

    # ═════════════════════════════════════════════════════════════════════
    # 方法5: 单店综合评分卡（"体检报告"）
    # ═════════════════════════════════════════════════════════════════════

    async def get_store_scorecard(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
    ) -> Dict[str, Any]:
        """单店综合评分卡 — BSC 四维度各 0-100 分 + 加权总分 + 百分位排名。"""

        # 1. 门店数据 + PNL + 盈亏平衡分数
        store_data = (
            await session.execute(
                text("""
                    SELECT os.revenue_fen, os.cost_material_fen, os.cost_labor_fen,
                           os.customer_count, os.order_count, os.avg_ticket_fen,
                           os.table_turnover_rate, os.waste_value_fen, os.employee_count,
                           os.snapshot_date,
                           pnl.gross_margin, pnl.operating_margin,
                           pnl.material_cost_ratio, pnl.labor_cost_ratio,
                           pnl.revenue_per_employee_fen,
                           bt.store_model_score
                      FROM operation_snapshots os
                      LEFT JOIN LATERAL (
                           SELECT * FROM store_pnl
                            WHERE store_id   = os.store_id
                              AND period_type = 'monthly'
                            ORDER BY period_date DESC
                            LIMIT 1
                      ) pnl ON true
                      LEFT JOIN LATERAL (
                           SELECT store_model_score FROM breakeven_tracker
                            WHERE store_id = os.store_id
                            ORDER BY calc_month DESC
                            LIMIT 1
                      ) bt ON true
                     WHERE os.store_id    = :store_id
                       AND os.brand_id    = :brand_id
                       AND os.period_type = 'monthly'
                     ORDER BY os.snapshot_date DESC
                     LIMIT 1
                """),
                {"store_id": store_id, "brand_id": brand_id},
            )
        ).mappings().first()

        if not store_data:
            return {"message": "暂无运营数据"}

        snapshot_date = store_data["snapshot_date"]

        # 2. 品牌范围数据（用于百分位排名计算）
        all_peers = (
            await session.execute(
                text("""
                    SELECT os.store_id,
                           os.revenue_fen, os.customer_count, os.avg_ticket_fen,
                           os.table_turnover_rate, os.waste_value_fen,
                           os.order_count, os.employee_count,
                           pnl.gross_margin, pnl.operating_margin,
                           pnl.material_cost_ratio, pnl.revenue_per_employee_fen,
                           bt.store_model_score
                      FROM operation_snapshots os
                      JOIN stores s ON s.id = os.store_id AND s.is_active = true
                      LEFT JOIN LATERAL (
                           SELECT * FROM store_pnl
                            WHERE store_id   = os.store_id
                              AND period_type = 'monthly'
                            ORDER BY period_date DESC
                            LIMIT 1
                      ) pnl ON true
                      LEFT JOIN LATERAL (
                           SELECT store_model_score FROM breakeven_tracker
                            WHERE store_id = os.store_id
                            ORDER BY calc_month DESC
                            LIMIT 1
                      ) bt ON true
                     WHERE os.brand_id      = :brand_id
                       AND os.period_type   = 'monthly'
                       AND os.snapshot_date = :snapshot_date
                """),
                {"brand_id": brand_id, "snapshot_date": snapshot_date},
            )
        ).mappings().all()

        # 3. 计算 BSC 四维度评分
        scores = self._calc_bsc_scores(store_data, all_peers)

        # 4. 加权总分
        weighted_total = round(
            scores["financial"]["score"] * BSC_WEIGHTS["financial"]
            + scores["customer"]["score"] * BSC_WEIGHTS["customer"]
            + scores["process"]["score"] * BSC_WEIGHTS["process"]
            + scores["learning"]["score"] * BSC_WEIGHTS["learning"],
            1,
        )

        # 5. 同品牌百分位排名
        peer_totals = []
        for p in all_peers:
            p_scores = self._calc_bsc_scores(p, all_peers)
            p_total = (
                p_scores["financial"]["score"] * BSC_WEIGHTS["financial"]
                + p_scores["customer"]["score"] * BSC_WEIGHTS["customer"]
                + p_scores["process"]["score"] * BSC_WEIGHTS["process"]
                + p_scores["learning"]["score"] * BSC_WEIGHTS["learning"]
            )
            peer_totals.append(p_total)

        below_count = sum(1 for t in peer_totals if t < weighted_total)
        percentile = round(below_count / max(len(peer_totals), 1) * 100, 1)

        # 6. 最大改善机会点
        dim_scores = {
            "financial": scores["financial"]["score"],
            "customer": scores["customer"]["score"],
            "process": scores["process"]["score"],
            "learning": scores["learning"]["score"],
        }
        weakest_dim = min(dim_scores, key=dim_scores.get)
        dim_labels = {
            "financial": "财务健康度",
            "customer": "客户活力度",
            "process": "运营效率度",
            "learning": "组织能力度",
        }

        return {
            "store_id": store_id,
            "snapshot_date": str(snapshot_date),
            "dimensions": scores,
            "weighted_total": weighted_total,
            "percentile_rank": percentile,
            "total_peers": len(peer_totals),
            "biggest_opportunity": {
                "dimension": weakest_dim,
                "dimension_label": dim_labels[weakest_dim],
                "current_score": dim_scores[weakest_dim],
                "potential_gain": round(100 - dim_scores[weakest_dim], 1),
            },
        }

    def _calc_bsc_scores(
        self,
        store: Any,
        all_peers: List[Any],
    ) -> Dict[str, Dict[str, Any]]:
        """计算 BSC 四维度评分（0-100）。"""

        def _f(v):
            return float(v) if v is not None else 0.0

        def _percentile_score(value: float, all_values: List[float], higher_better: bool = True) -> float:
            """基于百分位计算评分（0-100），百分位越高分越高"""
            if not all_values:
                return 50.0
            sorted_v = sorted(all_values)
            n = len(sorted_v)
            below = sum(1 for v in sorted_v if v < value)
            pct = below / max(n, 1) * 100
            return round(pct, 1) if higher_better else round(100 - pct, 1)

        # ── 收集同行数据用于百分位 ────────────────────────────────────
        peer_gm = [_f(p["gross_margin"]) for p in all_peers if p["gross_margin"]]
        peer_mat = [_f(p["material_cost_ratio"]) for p in all_peers if p["material_cost_ratio"]]
        peer_om = [_f(p["operating_margin"]) for p in all_peers if p["operating_margin"]]
        peer_cust = [_f(p["customer_count"]) for p in all_peers if p["customer_count"]]
        peer_ticket = [_f(p["avg_ticket_fen"]) for p in all_peers if p["avg_ticket_fen"]]
        peer_turnover = [_f(p["table_turnover_rate"]) for p in all_peers if p["table_turnover_rate"]]
        peer_waste = [
            _safe_div(_f(p["waste_value_fen"]), _f(p["revenue_fen"]))
            for p in all_peers
            if p["waste_value_fen"] is not None and p["revenue_fen"]
        ]
        peer_orders = [_f(p["order_count"]) for p in all_peers if p["order_count"]]
        peer_rev_emp = [_f(p["revenue_per_employee_fen"]) for p in all_peers if p["revenue_per_employee_fen"]]

        # ── 财务健康度 ────────────────────────────────────────────────
        gm_score = _percentile_score(_f(store["gross_margin"]), peer_gm)
        mat_score = _percentile_score(_f(store["material_cost_ratio"]), peer_mat, higher_better=False)
        om_score = _percentile_score(_f(store["operating_margin"]), peer_om)
        be_score = min(_f(store.get("store_model_score", 0) or 0), 100)

        financial_score = round(0.30 * gm_score + 0.25 * mat_score + 0.25 * om_score + 0.20 * be_score, 1)

        # ── 客户活力度 ────────────────────────────────────────────────
        cust_score = _percentile_score(_f(store["customer_count"]), peer_cust)
        ticket_score = _percentile_score(_f(store["avg_ticket_fen"]), peer_ticket)
        turnover_score = _percentile_score(_f(store["table_turnover_rate"]), peer_turnover)

        customer_score = round(0.35 * cust_score + 0.30 * ticket_score + 0.35 * turnover_score, 1)

        # ── 运营效率度 ────────────────────────────────────────────────
        store_waste_ratio = _safe_div(_f(store["waste_value_fen"]), _f(store["revenue_fen"]))
        waste_score = _percentile_score(store_waste_ratio, peer_waste, higher_better=False)
        order_score = _percentile_score(_f(store["order_count"]), peer_orders)

        process_score = round(0.50 * waste_score + 0.50 * order_score, 1)

        # ── 组织能力度 ────────────────────────────────────────────────
        rev_emp = _f(store.get("revenue_per_employee_fen", 0) or 0)
        if not rev_emp:
            rev_emp = _safe_div(_f(store["revenue_fen"]), _f(store["employee_count"]))
        emp_eff_score = _percentile_score(rev_emp, peer_rev_emp)

        learning_score = round(emp_eff_score, 1)

        return {
            "financial": {
                "label": "财务健康度",
                "score": financial_score,
                "sub_scores": {
                    "gross_margin": gm_score,
                    "material_cost": mat_score,
                    "operating_margin": om_score,
                    "breakeven": be_score,
                },
            },
            "customer": {
                "label": "客户活力度",
                "score": customer_score,
                "sub_scores": {
                    "customer_count": cust_score,
                    "avg_ticket": ticket_score,
                    "table_turnover": turnover_score,
                },
            },
            "process": {
                "label": "运营效率度",
                "score": process_score,
                "sub_scores": {
                    "waste_ratio": waste_score,
                    "order_count": order_score,
                },
            },
            "learning": {
                "label": "组织能力度",
                "score": learning_score,
                "sub_scores": {
                    "revenue_per_employee": emp_eff_score,
                },
            },
        }
