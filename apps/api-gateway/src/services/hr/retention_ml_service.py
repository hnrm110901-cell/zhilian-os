"""RetentionMLService — C级 ML 离职风险预测.

冷启动策略: 标记样本 < 50 时回退到启发式规则（同 B级 RetentionRiskService）。
模型存储: joblib 序列化 → Redis key hr:retention_model:{store_id}，TTL 7天。

特征:
  tenure_days       — employment_assignments.start_date 在职天数
  achievement_count — person_achievements 近90天成就数
  recent_signal_avg — retention_signals 近30天均值 (0-1)
"""
import io
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import sqlalchemy as sa
import structlog

logger = structlog.get_logger()

_MIN_TRAIN_SAMPLES = 50
_REDIS_TTL_SECONDS = 7 * 24 * 3600
_REDIS_KEY_TEMPLATE = "hr:retention_model:{store_id}"
_HIGH_RISK_THRESHOLD = 0.70
_MEDIUM_RISK_THRESHOLD = 0.40

_INTERVENTIONS = {
    "high": {
        "action": "安排一对一面谈",
        "estimated_impact": "降低离职概率 23%",
        "confidence": 0.68,
    },
    "medium": {
        "action": "了解近期诉求，酌情调整排班",
        "estimated_impact": "降低离职概率 12%",
        "confidence": 0.55,
    },
    "low": {
        "action": "保持正常关注",
        "estimated_impact": "维持现状",
        "confidence": 0.80,
    },
}


def _classify_risk(score: float) -> str:
    if score >= _HIGH_RISK_THRESHOLD:
        return "high"
    if score >= _MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def _heuristic_score(
    tenure_days: int, achievement_count: int, recent_signal_avg: float
) -> float:
    """B级启发式评分 (与 RetentionRiskService 相同逻辑)."""
    baseline = 0.3
    new_hire = 0.2 if tenure_days < 90 else 0.0
    no_achieve = 0.2 if achievement_count == 0 else 0.0
    signal = (1.0 - recent_signal_avg) * 0.5 if recent_signal_avg > 0 else 0.15
    return min(1.0, baseline + new_hire + no_achieve + signal)


class RetentionMLService:
    """C级 ML 预测服务 — Redis模型优先，冷启动降级到启发式."""

    def __init__(self, session, redis_client=None) -> None:
        self._session = session
        self._redis = redis_client

    async def predict(
        self, person_id: uuid.UUID, store_id: str
    ) -> Dict[str, Any]:
        """返回结构化预测结果 (spec §2.7)."""
        features = await self._fetch_person_features(person_id)
        model_payload = self._load_model_from_redis(store_id)

        if model_payload is not None:
            score, source = self._ml_predict(features, model_payload)
            model_trained_at = model_payload.get("trained_at")
            sample_count = model_payload.get("sample_count", 0)
        else:
            score = _heuristic_score(
                features.get("tenure_days", 180),
                features.get("achievement_count", 0),
                features.get("recent_signal_avg", 0.5),
            )
            source = "heuristic"
            model_trained_at = None
            sample_count = 0

        level = _classify_risk(score)
        intervention = dict(_INTERVENTIONS[level])
        intervention["deadline"] = (
            datetime.utcnow() + timedelta(days=14)
        ).strftime("%Y-%m-%d")

        result: Dict[str, Any] = {
            "person_id": str(person_id),
            "risk_score": round(score, 4),
            "risk_level": level,
            "prediction_source": source,
            "intervention": intervention,
        }
        if model_trained_at:
            result["model_trained_at"] = model_trained_at
            result["sample_count"] = sample_count

        logger.info(
            "retention_ml.predict",
            person_id=str(person_id),
            store_id=store_id,
            risk_level=level,
            source=source,
        )
        return result

    async def train_for_store(self, store_id: str) -> Dict[str, Any]:
        """训练模型并存入 Redis。样本不足时返回 cold_start=True."""
        rows = await self._fetch_training_data(store_id)
        if len(rows) < _MIN_TRAIN_SAMPLES:
            logger.info("retention_ml.cold_start", store_id=store_id, n=len(rows))
            return {"cold_start": True, "sample_count": len(rows), "store_id": store_id}

        X = [
            [
                float(r.tenure_days or 0),
                float(r.achievement_count or 0),
                float(r.recent_signal_avg or 0.5),
            ]
            for r in rows
        ]
        y = [int(bool(r.is_churned)) for r in rows]

        from sklearn.linear_model import LogisticRegression
        import joblib

        model = LogisticRegression(max_iter=500, class_weight="balanced")
        model.fit(X, y)

        trained_at = datetime.utcnow().isoformat()
        payload = {"model": model, "trained_at": trained_at, "sample_count": len(rows)}

        buf = io.BytesIO()
        joblib.dump(payload, buf)
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id)
        if self._redis:
            self._redis.setex(key, _REDIS_TTL_SECONDS, buf.getvalue())

        logger.info("retention_ml.trained", store_id=store_id, samples=len(rows))
        return {"cold_start": False, "sample_count": len(rows), "trained_at": trained_at}

    # ─── Private ──────────────────────────────────────────────────────────────

    def _load_model_from_redis(self, store_id: str) -> Optional[Dict]:
        if not self._redis:
            return None
        key = _REDIS_KEY_TEMPLATE.format(store_id=store_id)
        raw = self._redis.get(key)
        if not raw:
            return None
        try:
            import joblib
            return joblib.load(io.BytesIO(raw))
        except Exception as exc:
            logger.warning("retention_ml.model_load_failed", error=str(exc))
            return None

    def _ml_predict(self, features: dict, payload: dict) -> tuple:
        model = payload["model"]
        X = [[
            float(features.get("tenure_days", 0)),
            float(features.get("achievement_count", 0)),
            float(features.get("recent_signal_avg", 0.5)),
        ]]
        proba = model.predict_proba(X)[0]
        return float(proba[1]), "ml"

    async def _fetch_person_features(self, person_id: uuid.UUID) -> Dict[str, Any]:
        """单人特征向量查询."""
        result = await self._session.execute(
            sa.text("""
                SELECT
                    COALESCE(EXTRACT(DAY FROM NOW() - ea.start_date)::int, 180) AS tenure_days,
                    COALESCE((
                        SELECT COUNT(*) FROM person_achievements pa
                        WHERE pa.person_id = :pid
                          AND pa.achieved_at >= NOW() - INTERVAL '90 days'
                    ), 0) AS achievement_count,
                    COALESCE((
                        SELECT AVG(rs.signal_value) FROM retention_signals rs
                        WHERE rs.person_id = :pid
                          AND rs.recorded_at >= NOW() - INTERVAL '30 days'
                    ), 0.5) AS recent_signal_avg
                FROM employment_assignments ea
                WHERE ea.person_id = :pid AND ea.status = 'active'
                ORDER BY ea.created_at DESC LIMIT 1
            """),
            {"pid": str(person_id)},
        )
        row = result.fetchone()
        if row:
            return {
                "tenure_days": int(row.tenure_days or 180),
                "achievement_count": int(row.achievement_count or 0),
                "recent_signal_avg": float(row.recent_signal_avg or 0.5),
            }
        # 无数据时返回保守默认值
        return {"tenure_days": 180, "achievement_count": 0, "recent_signal_avg": 0.5}

    async def _fetch_training_data(self, store_id: str):
        """拉取训练样本（带 is_churned 标签）."""
        result = await self._session.execute(
            sa.text("""
                SELECT
                    EXTRACT(DAY FROM COALESCE(ea.end_date, NOW()) - ea.start_date)::int AS tenure_days,
                    COALESCE((
                        SELECT COUNT(*) FROM person_achievements pa
                        WHERE pa.person_id = p.id
                          AND pa.achieved_at >= NOW() - INTERVAL '90 days'
                    ), 0) AS achievement_count,
                    COALESCE((
                        SELECT AVG(rs.signal_value) FROM retention_signals rs
                        WHERE rs.person_id = p.id
                          AND rs.recorded_at >= NOW() - INTERVAL '30 days'
                    ), 0.5) AS recent_signal_avg,
                    CASE WHEN ea.status = 'terminated'
                         AND ea.end_date >= NOW() - INTERVAL '30 days'
                    THEN TRUE ELSE FALSE END AS is_churned
                FROM persons p
                JOIN employment_assignments ea ON ea.person_id = p.id
                JOIN org_nodes on_ ON on_.id = ea.org_node_id
                WHERE on_.store_id = :store_id AND ea.start_date IS NOT NULL
                LIMIT 500
            """),
            {"store_id": store_id},
        )
        return result.fetchall()
