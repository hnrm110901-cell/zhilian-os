"""
消费者预测服务 — AI 预测标签（统计规则引擎，无外部 ML 依赖）

基于 brand_consumer_profiles 字段计算：
- churn_score: 流失风险评分 [0, 1]
- upgrade_probability: 等级升级概率 [0, 1]
- clv_fen: 客户生命周期价值（分）

批量预测结果持久化到 consumer_prediction_snapshots 表。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 会员等级升序序列（用于判断下一等级）
_LEVEL_ORDER = ["普通", "银卡", "金卡", "钻石"]

# 各生命周期状态对应的流失基础权重
_LIFECYCLE_CHURN_WEIGHT: Dict[str, float] = {
    "lead": 0.2,
    "registered": 0.25,
    "repeat": 0.1,
    "vip": 0.05,
    "at_risk": 0.4,
    "dormant": 0.6,
    "lost": 0.9,
}

# 各等级升卡所需积分门槛（分制，参考典型餐饮会员体系）
_LEVEL_POINTS_THRESHOLD: Dict[str, int] = {
    "银卡": 1000,
    "金卡": 5000,
    "钻石": 20000,
}

# CLV 分段（分）：VIP > 50 万分 = 5000 元
_CLV_SEGMENTS = [
    (500_000, "vip"),
    (200_000, "high"),
    (50_000, "medium"),
    (0, "low"),
]


class ConsumerPredictionService:
    """
    基于 brand_consumer_profiles 的 AI 预测标签服务。
    使用统计规则（不依赖外部 ML 服务）。
    """

    # ── 单人预测 ────────────────────────────────────────────────────────────

    async def predict_churn_risk(
        self, consumer_id: str, brand_id: str, session: AsyncSession
    ) -> Dict[str, Any]:
        """
        流失预警预测。

        算法（统计规则）：
        1. days_since_last_order = now - brand_last_order_at
        2. avg_order_interval = 总天数 / brand_order_count（至少7天下限）
        3. churn_score = clamp(days_since_last_order / (2 × avg_order_interval), 0, 1)
        4. lifecycle_state 加权叠加
        """
        profile = await self._load_profile(consumer_id, brand_id, session)
        if profile is None:
            return self._empty_churn_result(consumer_id, brand_id)

        now = datetime.utcnow()
        last_order_at: Optional[datetime] = profile["brand_last_order_at"]
        first_order_at: Optional[datetime] = profile["brand_first_order_at"]
        order_count: int = profile["brand_order_count"] or 0
        lifecycle: str = profile["lifecycle_state"] or "registered"

        # 从未消费过的消费者
        if last_order_at is None:
            days_since = 0
            avg_interval = 30.0
        else:
            days_since = (now - last_order_at).days
            if order_count >= 2 and first_order_at is not None:
                total_span = max((last_order_at - first_order_at).days, 1)
                avg_interval = max(total_span / (order_count - 1), 7.0)
            else:
                avg_interval = 30.0  # 默认30天消费周期

        # churn_score = 超出平均间隔2倍时视为高风险
        raw_score = days_since / (2.0 * avg_interval) if avg_interval > 0 else 0.0
        # 叠加生命周期状态权重
        lifecycle_weight = _LIFECYCLE_CHURN_WEIGHT.get(lifecycle, 0.2)
        churn_score = min(raw_score * 0.7 + lifecycle_weight * 0.3, 1.0)
        churn_score = max(0.0, churn_score)

        risk_level = self._classify_risk(churn_score)
        recommended_action = self._churn_recommended_action(risk_level, days_since)

        # 预计流失日期：剩余安全天数 = avg_interval - days_since
        safe_days_left = max(int(avg_interval - days_since), 0)
        predicted_churn_date = (now + timedelta(days=safe_days_left)).date()

        return {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "churn_score": round(churn_score, 3),
            "risk_level": risk_level,
            "days_since_last_order": days_since,
            "avg_order_interval_days": round(avg_interval, 1),
            "lifecycle_state": lifecycle,
            "recommended_action": recommended_action,
            "predicted_churn_date": predicted_churn_date.isoformat(),
            "predicted_at": now.isoformat(),
        }

    async def predict_upgrade_probability(
        self, consumer_id: str, brand_id: str, session: AsyncSession
    ) -> Dict[str, Any]:
        """
        等级升级预测。

        算法：
        1. 获取当前 brand_level 和 brand_points
        2. 确定下一等级及所需积分
        3. 计算近似月消费速率（brand_order_amount_fen / 活跃月数）
        4. 估算积分增速（1元=1分简化模型）
        5. upgrade_probability = clamp(1 - points_gap / (avg_monthly_points × 3), 0, 1)
        """
        profile = await self._load_profile(consumer_id, brand_id, session)
        if profile is None:
            return self._empty_upgrade_result(consumer_id, brand_id)

        current_level: str = profile["brand_level"] or "普通"
        current_points: int = profile["brand_points"] or 0
        order_amount_fen: int = profile["brand_order_amount_fen"] or 0
        first_order_at: Optional[datetime] = profile["brand_first_order_at"]
        now = datetime.utcnow()

        # 查找下一等级
        try:
            level_idx = _LEVEL_ORDER.index(current_level)
        except ValueError:
            level_idx = 0
        has_next = level_idx < len(_LEVEL_ORDER) - 1
        next_level = _LEVEL_ORDER[level_idx + 1] if has_next else None
        next_threshold = _LEVEL_POINTS_THRESHOLD.get(next_level, 0) if next_level else None

        if next_level is None or next_threshold is None:
            # 已达最高等级
            return {
                "consumer_id": consumer_id,
                "brand_id": brand_id,
                "current_level": current_level,
                "next_level": None,
                "upgrade_probability_30d": 0.0,
                "points_gap": 0,
                "estimated_days_to_upgrade": None,
                "recommended_action": "维护最高等级权益，推荐专属活动",
                "predicted_at": now.isoformat(),
            }

        points_gap = max(next_threshold - current_points, 0)

        # 月均积分速率（简化：1分/元，即 amount_fen / 100 = 元 = 积分）
        active_months = 1.0
        if first_order_at is not None:
            active_months = max((now - first_order_at).days / 30.0, 1.0)
        monthly_points_rate = (order_amount_fen / 100.0) / active_months  # 分→元

        if monthly_points_rate <= 0:
            upgrade_probability = 0.0
            estimated_days = None
        else:
            # 30天内可积累的积分
            points_in_30d = monthly_points_rate
            if points_gap == 0:
                upgrade_probability = 1.0
                estimated_days = 0
            else:
                prob = points_in_30d / points_gap
                upgrade_probability = min(max(prob, 0.0), 1.0)
                estimated_days = int(points_gap / (monthly_points_rate / 30.0)) if monthly_points_rate > 0 else None

        recommended_action = (
            "积分兑换提醒，距升级仅差{}积分，推荐下次消费触发".format(points_gap)
            if upgrade_probability >= 0.5
            else "消费刺激券，加速积分积累"
        )

        return {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "current_level": current_level,
            "next_level": next_level,
            "upgrade_probability_30d": round(upgrade_probability, 3),
            "points_gap": points_gap,
            "current_points": current_points,
            "estimated_days_to_upgrade": estimated_days,
            "recommended_action": recommended_action,
            "predicted_at": now.isoformat(),
        }

    async def estimate_clv(
        self, consumer_id: str, brand_id: str, session: AsyncSession
    ) -> Dict[str, Any]:
        """
        客户生命周期价值（CLV）估算。

        公式：CLV = avg_order_value × purchase_frequency_per_month × estimated_lifetime_months
        estimated_lifetime_months 根据 lifecycle_state 和 churn_risk 估算。
        """
        profile = await self._load_profile(consumer_id, brand_id, session)
        if profile is None:
            return self._empty_clv_result(consumer_id, brand_id)

        order_count: int = profile["brand_order_count"] or 0
        order_amount_fen: int = profile["brand_order_amount_fen"] or 0
        lifecycle: str = profile["lifecycle_state"] or "registered"
        first_order_at: Optional[datetime] = profile["brand_first_order_at"]
        now = datetime.utcnow()

        if order_count == 0:
            avg_order_value_fen = 0
            purchase_freq_per_month = 0.0
        else:
            avg_order_value_fen = order_amount_fen // order_count
            active_months = max(
                (now - first_order_at).days / 30.0 if first_order_at else 1.0, 1.0
            )
            purchase_freq_per_month = order_count / active_months

        # 根据生命周期状态估算剩余活跃月数
        lifecycle_lifetime_map: Dict[str, float] = {
            "lead": 3.0,
            "registered": 6.0,
            "repeat": 18.0,
            "vip": 36.0,
            "at_risk": 4.0,
            "dormant": 1.5,
            "lost": 0.5,
        }
        estimated_active_months = lifecycle_lifetime_map.get(lifecycle, 6.0)

        clv_fen = int(avg_order_value_fen * purchase_freq_per_month * estimated_active_months)
        avg_monthly_spend_fen = int(avg_order_value_fen * purchase_freq_per_month)

        # CLV 分段
        clv_segment = "low"
        for threshold, seg in _CLV_SEGMENTS:
            if clv_fen >= threshold:
                clv_segment = seg
                break

        return {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "clv_fen": clv_fen,
            "clv_yuan": f"{clv_fen / 100:.2f}",
            "avg_monthly_spend_fen": avg_monthly_spend_fen,
            "avg_monthly_spend_yuan": f"{avg_monthly_spend_fen / 100:.2f}",
            "estimated_active_months": round(estimated_active_months, 1),
            "clv_segment": clv_segment,
            "predicted_at": now.isoformat(),
        }

    # ── 批量预测 ─────────────────────────────────────────────────────────────

    async def batch_predict_brand_consumers(
        self,
        brand_id: str,
        prediction_types: List[str],
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        批量预测品牌内所有活跃会员。
        prediction_types 可指定子集：["churn", "upgrade", "clv"]
        结果持久化到 consumer_prediction_snapshots 表。
        """
        # 拉取品牌内所有活跃消费者
        rows = await session.execute(
            text(
                """
                SELECT id::text AS consumer_id,
                       brand_id,
                       group_id,
                       brand_level,
                       brand_points,
                       brand_order_count,
                       brand_order_amount_fen,
                       brand_first_order_at,
                       brand_last_order_at,
                       lifecycle_state
                FROM brand_consumer_profiles
                WHERE brand_id = :brand_id
                  AND is_active = TRUE
                """
            ),
            {"brand_id": brand_id},
        )
        profiles = rows.fetchall()

        total = len(profiles)
        high_churn_count = 0
        upgrade_ready_count = 0
        high_clv_count = 0

        for row in profiles:
            consumer_id = row.consumer_id
            group_id = row.group_id

            churn_score: Optional[float] = None
            churn_risk_level: Optional[str] = None
            upgrade_probability: Optional[float] = None
            upgrade_next_level: Optional[str] = None
            upgrade_days: Optional[int] = None
            clv_fen: Optional[int] = None
            clv_segment: Optional[str] = None
            now = datetime.utcnow()

            if "churn" in prediction_types:
                churn_result = await self.predict_churn_risk(consumer_id, brand_id, session)
                churn_score = churn_result["churn_score"]
                churn_risk_level = churn_result["risk_level"]
                if churn_score >= 0.7:
                    high_churn_count += 1

            if "upgrade" in prediction_types:
                upgrade_result = await self.predict_upgrade_probability(consumer_id, brand_id, session)
                upgrade_probability = upgrade_result["upgrade_probability_30d"]
                upgrade_next_level = upgrade_result.get("next_level")
                upgrade_days = upgrade_result.get("estimated_days_to_upgrade")
                if upgrade_probability is not None and upgrade_probability >= 0.6:
                    upgrade_ready_count += 1

            if "clv" in prediction_types:
                clv_result = await self.estimate_clv(consumer_id, brand_id, session)
                clv_fen = clv_result["clv_fen"]
                clv_segment = clv_result["clv_segment"]
                if clv_segment in ("high", "vip"):
                    high_clv_count += 1

            # 持久化或更新快照（ON CONFLICT UPSERT）
            await session.execute(
                text(
                    """
                    INSERT INTO consumer_prediction_snapshots
                        (id, consumer_id, brand_id, group_id,
                         churn_score, churn_risk_level, churn_predicted_at,
                         upgrade_probability, upgrade_next_level, upgrade_days_estimated, upgrade_predicted_at,
                         clv_fen, clv_segment, clv_calculated_at,
                         last_batch_run_at)
                    VALUES
                        (gen_random_uuid(), :consumer_id::uuid, :brand_id, :group_id,
                         :churn_score, :churn_risk_level, :churn_predicted_at,
                         :upgrade_probability, :upgrade_next_level, :upgrade_days, :upgrade_predicted_at,
                         :clv_fen, :clv_segment, :clv_calculated_at,
                         NOW())
                    ON CONFLICT (consumer_id, brand_id) DO UPDATE SET
                        churn_score           = EXCLUDED.churn_score,
                        churn_risk_level      = EXCLUDED.churn_risk_level,
                        churn_predicted_at    = EXCLUDED.churn_predicted_at,
                        upgrade_probability   = EXCLUDED.upgrade_probability,
                        upgrade_next_level    = EXCLUDED.upgrade_next_level,
                        upgrade_days_estimated = EXCLUDED.upgrade_days_estimated,
                        upgrade_predicted_at  = EXCLUDED.upgrade_predicted_at,
                        clv_fen               = EXCLUDED.clv_fen,
                        clv_segment           = EXCLUDED.clv_segment,
                        clv_calculated_at     = EXCLUDED.clv_calculated_at,
                        last_batch_run_at     = NOW()
                    """
                ),
                {
                    "consumer_id": consumer_id,
                    "brand_id": brand_id,
                    "group_id": group_id,
                    "churn_score": churn_score,
                    "churn_risk_level": churn_risk_level,
                    "churn_predicted_at": now if churn_score is not None else None,
                    "upgrade_probability": upgrade_probability,
                    "upgrade_next_level": upgrade_next_level,
                    "upgrade_days": upgrade_days,
                    "upgrade_predicted_at": now if upgrade_probability is not None else None,
                    "clv_fen": clv_fen,
                    "clv_segment": clv_segment,
                    "clv_calculated_at": now if clv_fen is not None else None,
                },
            )

        await session.commit()

        logger.info(
            "batch_predict_completed",
            brand_id=brand_id,
            total=total,
            high_churn=high_churn_count,
            upgrade_ready=upgrade_ready_count,
            high_clv=high_clv_count,
        )

        return {
            "total_processed": total,
            "high_churn_risk_count": high_churn_count,
            "upgrade_ready_count": upgrade_ready_count,
            "high_clv_count": high_clv_count,
            "predictions_saved": True,
            "prediction_types": prediction_types,
            "run_at": datetime.utcnow().isoformat(),
        }

    async def get_at_risk_consumers(
        self,
        brand_id: str,
        session: AsyncSession,
        risk_threshold: float = 0.7,
        limit: int = 100,
    ) -> List[Dict]:
        """获取高流失风险会员列表（按 churn_score 倒序）"""
        rows = await session.execute(
            text(
                """
                SELECT consumer_id::text,
                       brand_id,
                       churn_score,
                       churn_risk_level,
                       churn_predicted_at,
                       last_batch_run_at
                FROM consumer_prediction_snapshots
                WHERE brand_id = :brand_id
                  AND churn_score >= :threshold
                ORDER BY churn_score DESC
                LIMIT :limit
                """
            ),
            {"brand_id": brand_id, "threshold": risk_threshold, "limit": limit},
        )
        return [dict(row._mapping) for row in rows.fetchall()]

    async def get_upgrade_ready_consumers(
        self,
        brand_id: str,
        session: AsyncSession,
        probability_threshold: float = 0.6,
        limit: int = 100,
    ) -> List[Dict]:
        """获取接近升级的会员列表（按 upgrade_probability 倒序）"""
        rows = await session.execute(
            text(
                """
                SELECT consumer_id::text,
                       brand_id,
                       upgrade_probability,
                       upgrade_next_level,
                       upgrade_days_estimated,
                       last_batch_run_at
                FROM consumer_prediction_snapshots
                WHERE brand_id = :brand_id
                  AND upgrade_probability >= :threshold
                  AND upgrade_next_level IS NOT NULL
                ORDER BY upgrade_probability DESC
                LIMIT :limit
                """
            ),
            {"brand_id": brand_id, "threshold": probability_threshold, "limit": limit},
        )
        return [dict(row._mapping) for row in rows.fetchall()]

    # ── 内部辅助 ─────────────────────────────────────────────────────────────

    async def _load_profile(
        self, consumer_id: str, brand_id: str, session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """从 brand_consumer_profiles 加载单条档案，返回 dict 或 None。"""
        rows = await session.execute(
            text(
                """
                SELECT id,
                       brand_level,
                       brand_points,
                       brand_order_count,
                       brand_order_amount_fen,
                       brand_first_order_at,
                       brand_last_order_at,
                       lifecycle_state,
                       group_id
                FROM brand_consumer_profiles
                WHERE consumer_id = :cid::uuid
                  AND brand_id   = :bid
                LIMIT 1
                """
            ),
            {"cid": consumer_id, "bid": brand_id},
        )
        row = rows.fetchone()
        if row is None:
            return None
        return dict(row._mapping)

    @staticmethod
    def _classify_risk(score: float) -> str:
        if score >= 0.85:
            return "critical"
        if score >= 0.65:
            return "high"
        if score >= 0.40:
            return "medium"
        return "low"

    @staticmethod
    def _churn_recommended_action(risk_level: str, days_since: int) -> str:
        if risk_level == "critical":
            return f"立即企微一对一挽回，配合高价值优惠券（已{days_since}天未消费）"
        if risk_level == "high":
            return f"发送专属回归优惠SMS+企微推送（已{days_since}天未消费）"
        if risk_level == "medium":
            return "定向内容触达，展示新品/活动"
        return "维持常规触达频率"

    @staticmethod
    def _empty_churn_result(consumer_id: str, brand_id: str) -> Dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "churn_score": 0.0,
            "risk_level": "low",
            "days_since_last_order": 0,
            "avg_order_interval_days": 30.0,
            "lifecycle_state": "unknown",
            "recommended_action": "档案不存在，请先建档",
            "predicted_churn_date": None,
            "predicted_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _empty_upgrade_result(consumer_id: str, brand_id: str) -> Dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "current_level": "unknown",
            "next_level": None,
            "upgrade_probability_30d": 0.0,
            "points_gap": 0,
            "estimated_days_to_upgrade": None,
            "recommended_action": "档案不存在，请先建档",
            "predicted_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _empty_clv_result(consumer_id: str, brand_id: str) -> Dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "clv_fen": 0,
            "clv_yuan": "0.00",
            "avg_monthly_spend_fen": 0,
            "avg_monthly_spend_yuan": "0.00",
            "estimated_active_months": 0.0,
            "clv_segment": "low",
            "predicted_at": datetime.utcnow().isoformat(),
        }


# 单例
consumer_prediction_service = ConsumerPredictionService()
