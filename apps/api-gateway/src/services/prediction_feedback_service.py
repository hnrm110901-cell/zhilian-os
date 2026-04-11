"""
预测反馈闭环服务
核心职责：记录预测 → 回填实际值 → 计算准确率 → 生成预测
实现"预测-验证-改进"的数据飞轮，驱动模型持续优化
"""

import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 支持的预测类型常量
PREDICTION_TYPES = ("revenue", "customer_count", "waste", "material_cost_ratio", "staffing")


class PredictionFeedbackService:
    """预测反馈闭环服务

    业务流程:
    1. generate_predictions: 每晚基于历史数据生成明日各项预测
    2. record_prediction: 将预测结果写入 prediction_log
    3. backfill_actuals: 次日从 operation_snapshots 回填实际值并计算误差
    4. get_prediction_accuracy: 门店维度查看预测准确率
    5. get_accuracy_dashboard: 品牌/总部维度的准确率总览
    """

    # ── 方法1: 记录单条预测 ──────────────────────────────────────────

    async def record_prediction(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        prediction_type: str,
        prediction_date: date,
        predicted_value: float,
        model_version: Optional[str] = None,
        features_used: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """写入一条预测记录到 prediction_log

        Args:
            session: 数据库会话
            store_id: 门店ID
            brand_id: 品牌ID
            prediction_type: 预测类型 (revenue|customer_count|waste|material_cost_ratio|staffing)
            prediction_date: 预测的目标日期（被预测的那一天）
            predicted_value: 预测值（revenue/waste单位为元，customer_count为人数）
            model_version: 模型版本号，用于追踪模型迭代效果
            features_used: 使用的特征集（JSONB），便于回溯分析
        """
        # 校验预测类型
        if prediction_type not in PREDICTION_TYPES:
            raise ValueError(
                f"不支持的预测类型: {prediction_type}，"
                f"合法值: {PREDICTION_TYPES}"
            )

        result = await session.execute(
            text("""
                INSERT INTO prediction_log (
                    brand_id, store_id, prediction_type, prediction_date,
                    predicted_at, predicted_value, model_version, features_used,
                    is_feedback_collected
                ) VALUES (
                    :brand_id, :store_id, :prediction_type, :prediction_date,
                    NOW(), :predicted_value, :model_version,
                    :features_used::jsonb,
                    FALSE
                )
                RETURNING id
            """),
            {
                "brand_id": brand_id,
                "store_id": store_id,
                "prediction_type": prediction_type,
                "prediction_date": prediction_date,
                "predicted_value": predicted_value,
                "model_version": model_version,
                "features_used": (
                    json.dumps(features_used, ensure_ascii=False)
                    if features_used
                    else None
                ),
            },
        )
        row = result.fetchone()

        logger.info(
            "prediction_recorded",
            store_id=store_id,
            prediction_type=prediction_type,
            prediction_date=str(prediction_date),
            predicted_value=predicted_value,
        )

        return {
            "id": str(row.id),
            "store_id": store_id,
            "prediction_type": prediction_type,
            "prediction_date": str(prediction_date),
            "predicted_value": predicted_value,
        }

    # ── 方法2: 回填实际值（核心闭环） ──────────────────────────────────

    async def backfill_actuals(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        target_date: date,
    ) -> Dict[str, Any]:
        """回填指定日期的预测实际值，完成预测-验证闭环

        核心逻辑：
        1. 从 operation_snapshots 获取 target_date 的实际运营数据
        2. 将每种 prediction_type 映射到对应的实际指标
        3. 更新 prediction_log 中未回填的记录，计算误差百分比

        映射关系（predicted_value 存的是元/人数，需要对齐单位）：
        - revenue → revenue_fen / 100（DB存分，predicted存元）
        - customer_count → customer_count（直接对应）
        - waste → waste_value_fen / 100（DB存分，predicted存元）
        - material_cost_ratio → cost_material_fen / revenue_fen * 100（百分比）
        - staffing → employee_count（直接对应）
        """
        # 第一步：从 operation_snapshots 读取当日实际数据
        snapshot_result = await session.execute(
            text("""
                SELECT revenue_fen, customer_count, waste_value_fen,
                       cost_material_fen, employee_count
                  FROM operation_snapshots
                 WHERE store_id = :store_id
                   AND snapshot_date = :target_date
                   AND period_type = 'daily'
            """),
            {"store_id": store_id, "target_date": target_date},
        )
        snapshot = snapshot_result.fetchone()

        if not snapshot:
            logger.warning(
                "backfill_no_snapshot",
                store_id=store_id,
                target_date=str(target_date),
            )
            return {"backfilled_count": 0, "predictions": [], "reason": "当日无运营快照数据"}

        # 第二步：构建 prediction_type → actual_value 的映射
        # revenue_fen 和 waste_value_fen 除以100转为元，与 predicted_value 单位一致
        revenue_fen = snapshot.revenue_fen or 0
        actual_map: Dict[str, Optional[float]] = {
            "revenue": revenue_fen / 100 if revenue_fen else 0,
            "customer_count": float(snapshot.customer_count or 0),
            "waste": (snapshot.waste_value_fen or 0) / 100,
            "staffing": float(snapshot.employee_count or 0),
        }

        # material_cost_ratio 需要特殊处理：食材成本占收入百分比
        if revenue_fen and revenue_fen > 0:
            actual_map["material_cost_ratio"] = round(
                (snapshot.cost_material_fen or 0) / revenue_fen * 100, 2
            )
        else:
            # 营收为0时无法计算食材成本率，设为None跳过回填
            actual_map["material_cost_ratio"] = None

        # 第三步：逐类型更新 prediction_log
        backfilled_predictions: List[Dict[str, Any]] = []
        total_backfilled = 0

        for p_type, actual_value in actual_map.items():
            if actual_value is None:
                # 无法计算的类型跳过
                continue

            # 更新该类型的未回填预测记录，同时计算误差百分比
            # error_pct = |预测值 - 实际值| / 实际值 * 100
            # NULLIF 防止实际值为0时除零
            update_result = await session.execute(
                text("""
                    UPDATE prediction_log
                       SET actual_value = :actual,
                           error_pct = ABS(predicted_value - :actual)
                                       / NULLIF(:actual, 0) * 100,
                           is_feedback_collected = TRUE
                     WHERE store_id = :store_id
                       AND brand_id = :brand_id
                       AND prediction_date = :target_date
                       AND prediction_type = :p_type
                       AND is_feedback_collected = FALSE
                 RETURNING id, predicted_value, error_pct
                """),
                {
                    "actual": actual_value,
                    "store_id": store_id,
                    "brand_id": brand_id,
                    "target_date": target_date,
                    "p_type": p_type,
                },
            )
            rows = update_result.fetchall()

            for row in rows:
                total_backfilled += 1
                backfilled_predictions.append({
                    "type": p_type,
                    "predicted": float(row.predicted_value),
                    "actual": actual_value,
                    "error_pct": round(float(row.error_pct), 2) if row.error_pct else None,
                })

        logger.info(
            "backfill_completed",
            store_id=store_id,
            target_date=str(target_date),
            backfilled_count=total_backfilled,
        )

        return {
            "backfilled_count": total_backfilled,
            "predictions": backfilled_predictions,
        }

    # ── 方法3: 门店级预测准确率 ──────────────────────────────────────

    async def get_prediction_accuracy(
        self,
        session: AsyncSession,
        store_id: str,
        prediction_type: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """查询门店某预测类型的准确率统计

        统计指标：
        - mean_error_pct: 平均误差率
        - median_error_pct: 中位数误差率（percentile_cont，更抗异常值）
        - accuracy_rate: 误差<10%的预测占比（行业通用阈值）
        - trend: 最近7天 vs 之前23天的误差对比，判断是否在改善
        - best_day / worst_day: 最佳/最差预测日期
        """
        if prediction_type not in PREDICTION_TYPES:
            raise ValueError(f"不支持的预测类型: {prediction_type}")

        # 计算日期范围
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # 单条SQL获取所有统计指标（PostgreSQL percentile_cont 支持中位数）
        stats_result = await session.execute(
            text("""
                WITH feedback AS (
                    SELECT prediction_date, predicted_value, actual_value, error_pct
                      FROM prediction_log
                     WHERE store_id = :store_id
                       AND prediction_type = :prediction_type
                       AND is_feedback_collected = TRUE
                       AND prediction_date >= :start_date
                       AND prediction_date <= :end_date
                       AND error_pct IS NOT NULL
                ),
                -- 基础统计
                base_stats AS (
                    SELECT
                        COUNT(*)                                              AS total_count,
                        ROUND(AVG(error_pct)::numeric, 2)                    AS mean_error_pct,
                        ROUND(
                            (PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY error_pct))::numeric, 2
                        )                                                     AS median_error_pct,
                        ROUND(
                            COUNT(*) FILTER (WHERE error_pct < 10)::numeric
                            / NULLIF(COUNT(*), 0) * 100, 2
                        )                                                     AS accuracy_rate
                      FROM feedback
                ),
                -- 最佳/最差日
                extremes AS (
                    SELECT
                        (SELECT prediction_date FROM feedback ORDER BY error_pct ASC  LIMIT 1) AS best_day,
                        (SELECT error_pct      FROM feedback ORDER BY error_pct ASC  LIMIT 1) AS best_error,
                        (SELECT prediction_date FROM feedback ORDER BY error_pct DESC LIMIT 1) AS worst_day,
                        (SELECT error_pct      FROM feedback ORDER BY error_pct DESC LIMIT 1) AS worst_error
                ),
                -- 趋势分析：最近7天 vs 之前天数
                trend_recent AS (
                    SELECT ROUND(AVG(error_pct)::numeric, 2) AS recent_avg
                      FROM feedback
                     WHERE prediction_date > :end_date - INTERVAL '7 days'
                ),
                trend_previous AS (
                    SELECT ROUND(AVG(error_pct)::numeric, 2) AS previous_avg
                      FROM feedback
                     WHERE prediction_date <= :end_date - INTERVAL '7 days'
                )
                SELECT
                    bs.total_count, bs.mean_error_pct, bs.median_error_pct, bs.accuracy_rate,
                    ex.best_day, ex.best_error, ex.worst_day, ex.worst_error,
                    tr.recent_avg, tp.previous_avg
                  FROM base_stats bs, extremes ex, trend_recent tr, trend_previous tp
            """),
            {
                "store_id": store_id,
                "prediction_type": prediction_type,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        row = stats_result.fetchone()

        if not row or not row.total_count:
            return {
                "store_id": store_id,
                "prediction_type": prediction_type,
                "days": days,
                "total_count": 0,
                "message": "该时段无已回填的预测数据",
            }

        # 判断趋势：recent_avg < previous_avg 表示误差在缩小（改善中）
        trend = "improving"  # 默认改善
        if row.recent_avg is not None and row.previous_avg is not None:
            if float(row.recent_avg) > float(row.previous_avg):
                trend = "degrading"  # 误差增大，恶化中
            elif float(row.recent_avg) == float(row.previous_avg):
                trend = "stable"
        else:
            trend = "insufficient_data"  # 数据不足以判断趋势

        return {
            "store_id": store_id,
            "prediction_type": prediction_type,
            "days": days,
            "total_count": row.total_count,
            "mean_error_pct": float(row.mean_error_pct) if row.mean_error_pct else 0,
            "median_error_pct": float(row.median_error_pct) if row.median_error_pct else 0,
            "accuracy_rate": float(row.accuracy_rate) if row.accuracy_rate else 0,
            "trend": trend,
            "recent_7d_avg_error": float(row.recent_avg) if row.recent_avg else None,
            "previous_avg_error": float(row.previous_avg) if row.previous_avg else None,
            "best_day": {
                "date": str(row.best_day) if row.best_day else None,
                "error_pct": float(row.best_error) if row.best_error else None,
            },
            "worst_day": {
                "date": str(row.worst_day) if row.worst_day else None,
                "error_pct": float(row.worst_error) if row.worst_error else None,
            },
        }

    # ── 方法4: 品牌级准确率仪表盘 ──────────────────────────────────

    async def get_accuracy_dashboard(
        self,
        session: AsyncSession,
        brand_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """品牌级预测准确率总览，用于总部HQ看板

        包含两个维度：
        1. 按 prediction_type 分组：各类预测的整体准确率
        2. 按 store_id 排名：哪家店预测最准/最不准（辅助定位数据质量问题）
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # ── 维度1: 按预测类型汇总 ──
        type_result = await session.execute(
            text("""
                SELECT
                    prediction_type,
                    COUNT(*)                                              AS total_count,
                    ROUND(AVG(error_pct)::numeric, 2)                    AS mean_error_pct,
                    ROUND(
                        (PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY error_pct))::numeric, 2
                    )                                                     AS median_error_pct,
                    ROUND(
                        COUNT(*) FILTER (WHERE error_pct < 10)::numeric
                        / NULLIF(COUNT(*), 0) * 100, 2
                    )                                                     AS accuracy_rate
                  FROM prediction_log
                 WHERE brand_id = :brand_id
                   AND is_feedback_collected = TRUE
                   AND prediction_date >= :start_date
                   AND prediction_date <= :end_date
                   AND error_pct IS NOT NULL
                 GROUP BY prediction_type
                 ORDER BY mean_error_pct ASC
            """),
            {
                "brand_id": brand_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        type_rows = type_result.fetchall()

        by_type: List[Dict[str, Any]] = []
        for row in type_rows:
            by_type.append({
                "prediction_type": row.prediction_type,
                "total_count": row.total_count,
                "mean_error_pct": float(row.mean_error_pct) if row.mean_error_pct else 0,
                "median_error_pct": float(row.median_error_pct) if row.median_error_pct else 0,
                "accuracy_rate": float(row.accuracy_rate) if row.accuracy_rate else 0,
            })

        # ── 维度2: 按门店排名（平均误差从低到高） ──
        store_result = await session.execute(
            text("""
                SELECT
                    store_id,
                    COUNT(*)                                              AS total_count,
                    ROUND(AVG(error_pct)::numeric, 2)                    AS mean_error_pct,
                    ROUND(
                        COUNT(*) FILTER (WHERE error_pct < 10)::numeric
                        / NULLIF(COUNT(*), 0) * 100, 2
                    )                                                     AS accuracy_rate
                  FROM prediction_log
                 WHERE brand_id = :brand_id
                   AND is_feedback_collected = TRUE
                   AND prediction_date >= :start_date
                   AND prediction_date <= :end_date
                   AND error_pct IS NOT NULL
                 GROUP BY store_id
                 ORDER BY mean_error_pct ASC
            """),
            {
                "brand_id": brand_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        store_rows = store_result.fetchall()

        by_store: List[Dict[str, Any]] = []
        for row in store_rows:
            by_store.append({
                "store_id": row.store_id,
                "total_count": row.total_count,
                "mean_error_pct": float(row.mean_error_pct) if row.mean_error_pct else 0,
                "accuracy_rate": float(row.accuracy_rate) if row.accuracy_rate else 0,
            })

        # 品牌整体准确率
        overall_accuracy = 0.0
        overall_count = sum(t["total_count"] for t in by_type)
        if overall_count > 0:
            # 加权平均：按各类型的记录数加权
            weighted_sum = sum(
                t["mean_error_pct"] * t["total_count"] for t in by_type
            )
            overall_accuracy = round(
                100 - (weighted_sum / overall_count), 2
            )

        return {
            "brand_id": brand_id,
            "days": days,
            "overall_prediction_count": overall_count,
            "overall_accuracy_score": overall_accuracy,
            "by_prediction_type": by_type,
            "by_store": by_store,
            "best_store": by_store[0] if by_store else None,
            "worst_store": by_store[-1] if by_store else None,
        }

    # ── 方法5: 生成预测（加权移动平均） ──────────────────────────────

    async def generate_predictions(
        self,
        session: AsyncSession,
        store_id: str,
        brand_id: str,
        target_date: date,
    ) -> Dict[str, Any]:
        """基于历史数据生成明日预测（简化版加权移动平均）

        算法说明：
        - 取最近14天的 daily 运营快照数据
        - 权重线性递增：第1天(最旧)权重1，第14天(最新)权重14
        - 加权平均 = sum(value_i * weight_i) / sum(weight_i)
        - 这种加权方式使最新数据对预测影响更大，符合餐饮行业
          "近期趋势比远期历史更有参考价值"的业务特征

        预测类型映射（与 backfill_actuals 保持一致）：
        - revenue: revenue_fen / 100 → 元
        - customer_count: customer_count → 人数
        - waste: waste_value_fen / 100 → 元
        - material_cost_ratio: cost_material_fen / revenue_fen * 100 → 百分比
        - staffing: employee_count → 人数
        """
        # 获取最近14天的 daily 快照，按日期升序排列
        history_days = 14
        history_start = target_date - timedelta(days=history_days)

        history_result = await session.execute(
            text("""
                SELECT snapshot_date, revenue_fen, customer_count,
                       waste_value_fen, cost_material_fen, employee_count
                  FROM operation_snapshots
                 WHERE store_id = :store_id
                   AND period_type = 'daily'
                   AND snapshot_date > :start_date
                   AND snapshot_date < :target_date
                 ORDER BY snapshot_date ASC
            """),
            {
                "store_id": store_id,
                "start_date": history_start,
                "target_date": target_date,
            },
        )
        rows = history_result.fetchall()

        if not rows:
            logger.warning(
                "generate_predictions_no_history",
                store_id=store_id,
                target_date=str(target_date),
            )
            return {
                "store_id": store_id,
                "target_date": str(target_date),
                "predictions": [],
                "reason": "历史数据不足，无法生成预测",
            }

        # ── 构建各指标的历史序列 ──
        # 每行对应一天，按日期升序（最旧在前）
        revenue_series: List[float] = []
        customer_series: List[float] = []
        waste_series: List[float] = []
        cost_ratio_series: List[float] = []
        staffing_series: List[float] = []

        for row in rows:
            rev_fen = row.revenue_fen or 0
            revenue_series.append(rev_fen / 100)  # 转元
            customer_series.append(float(row.customer_count or 0))
            waste_series.append((row.waste_value_fen or 0) / 100)  # 转元
            staffing_series.append(float(row.employee_count or 0))

            # 食材成本率：当天有营收时才能计算
            if rev_fen > 0:
                cost_ratio_series.append(
                    round((row.cost_material_fen or 0) / rev_fen * 100, 2)
                )
            # 营收为0的天不计入成本率序列（避免异常值污染预测）

        # ── 加权移动平均计算 ──
        predictions_output: List[Dict[str, Any]] = []

        type_series_map = {
            "revenue": revenue_series,
            "customer_count": customer_series,
            "waste": waste_series,
            "material_cost_ratio": cost_ratio_series,
            "staffing": staffing_series,
        }

        # 模型版本和特征描述
        model_version = "wma_v1"  # weighted moving average v1

        for p_type, series in type_series_map.items():
            if not series:
                continue

            # 加权移动平均：权重 = 1, 2, 3, ..., n（n = len(series)）
            n = len(series)
            weight_sum = n * (n + 1) / 2  # 等差数列求和
            weighted_value = sum(
                value * (i + 1) for i, value in enumerate(series)
            )
            predicted = round(weighted_value / weight_sum, 2)

            # 特征记录：便于后续分析哪些因素影响预测
            features = {
                "method": "weighted_moving_average",
                "history_days_used": n,
                "history_days_requested": history_days,
                "latest_value": series[-1],
                "series_mean": round(sum(series) / n, 2),
            }

            # 调用 record_prediction 写入数据库
            record = await self.record_prediction(
                session=session,
                store_id=store_id,
                brand_id=brand_id,
                prediction_type=p_type,
                prediction_date=target_date,
                predicted_value=predicted,
                model_version=model_version,
                features_used=features,
            )

            predictions_output.append({
                "type": p_type,
                "predicted_value": predicted,
                "history_days_used": n,
                "prediction_id": record["id"],
            })

        logger.info(
            "predictions_generated",
            store_id=store_id,
            target_date=str(target_date),
            types_predicted=[p["type"] for p in predictions_output],
        )

        return {
            "store_id": store_id,
            "brand_id": brand_id,
            "target_date": str(target_date),
            "model_version": model_version,
            "predictions": predictions_output,
        }
