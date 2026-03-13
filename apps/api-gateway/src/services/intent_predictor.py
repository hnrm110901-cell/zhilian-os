"""
客户意向预测 — Phase P4 (屯象独有)
基于客户行为特征预测成交概率，排序跟进优先级
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger()


class IntentPredictor:
    """客户意向预测器"""

    async def predict_intent(
        self,
        session: AsyncSession,
        store_id: str,
        customer_name: str,
        current_stage: str,
        event_type: str = "wedding",
        target_date: Optional[str] = None,
        table_count: Optional[int] = None,
        estimated_value_yuan: float = 0,
        follow_up_count: int = 0,
        days_since_first_contact: int = 0,
        competitor_mentioned: bool = False,
    ) -> Dict[str, Any]:
        """预测单个客户的成交概率"""
        features = self._extract_features(
            current_stage=current_stage,
            event_type=event_type,
            target_date=target_date,
            table_count=table_count,
            estimated_value_yuan=estimated_value_yuan,
            follow_up_count=follow_up_count,
            days_since_first_contact=days_since_first_contact,
            competitor_mentioned=competitor_mentioned,
        )
        probability = self._calculate_probability(features)
        priority = self._calculate_priority(probability, estimated_value_yuan, target_date)

        return {
            "customer_name": customer_name,
            "conversion_probability": round(probability, 2),
            "priority_score": round(priority, 2),
            "priority_level": "high" if priority >= 70 else "medium" if priority >= 40 else "low",
            "key_signals": self._identify_signals(features),
            "recommended_action": self._recommend_action(current_stage, probability, features),
            "predicted_at": datetime.utcnow().isoformat(),
        }

    async def rank_leads(
        self,
        session: AsyncSession,
        store_id: str,
        leads: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """批量预测并按优先级排序"""
        predictions = []
        for lead in leads:
            pred = await self.predict_intent(
                session=session,
                store_id=store_id,
                **lead,
            )
            predictions.append(pred)

        predictions.sort(key=lambda x: x["priority_score"], reverse=True)
        return predictions

    def _extract_features(self, **kwargs) -> Dict[str, float]:
        """提取预测特征"""
        stage_scores = {
            "lead": 0.1, "intent": 0.3, "room_lock": 0.6,
            "negotiation": 0.7, "signed": 0.95, "completed": 1.0, "lost": 0.05,
        }

        features = {
            "stage_score": stage_scores.get(kwargs["current_stage"], 0.1),
            "has_target_date": 1.0 if kwargs.get("target_date") else 0.0,
            "table_count_norm": min((kwargs.get("table_count") or 0) / 30, 1.0),
            "value_norm": min(kwargs.get("estimated_value_yuan", 0) / 100000, 1.0),
            "follow_up_engagement": min(kwargs.get("follow_up_count", 0) / 10, 1.0),
            "time_pressure": 0.0,
            "competitor_risk": 0.3 if kwargs.get("competitor_mentioned") else 0.0,
        }

        # 时间紧迫度
        if kwargs.get("target_date"):
            try:
                days_to_event = (date.fromisoformat(kwargs["target_date"]) - date.today()).days
                if days_to_event <= 7:
                    features["time_pressure"] = 1.0
                elif days_to_event <= 30:
                    features["time_pressure"] = 0.7
                elif days_to_event <= 90:
                    features["time_pressure"] = 0.3
            except (ValueError, TypeError):
                pass

        # 跟进周期衰减
        days = kwargs.get("days_since_first_contact", 0)
        if days > 30:
            features["engagement_decay"] = max(0, 1.0 - (days - 30) / 60)
        else:
            features["engagement_decay"] = 1.0

        return features

    def _calculate_probability(self, features: Dict[str, float]) -> float:
        """基于特征计算成交概率（规则引擎，后续接入ML模型）"""
        weights = {
            "stage_score": 0.35,
            "has_target_date": 0.1,
            "follow_up_engagement": 0.15,
            "time_pressure": 0.1,
            "value_norm": 0.05,
            "engagement_decay": 0.15,
            "competitor_risk": -0.1,
        }

        score = sum(features.get(k, 0) * w for k, w in weights.items())
        return max(0.01, min(0.99, score))

    def _calculate_priority(
        self, probability: float, value_yuan: float, target_date: Optional[str],
    ) -> float:
        """计算跟进优先级（0-100）"""
        # 期望价值 = 概率 × 金额
        ev = probability * value_yuan
        ev_score = min(ev / 50000, 1.0) * 40

        # 概率分
        prob_score = probability * 30

        # 时间紧迫度
        time_score = 0
        if target_date:
            try:
                days = (date.fromisoformat(target_date) - date.today()).days
                if days <= 7:
                    time_score = 30
                elif days <= 14:
                    time_score = 20
                elif days <= 30:
                    time_score = 10
            except (ValueError, TypeError):
                pass

        return ev_score + prob_score + time_score

    def _identify_signals(self, features: Dict[str, float]) -> List[str]:
        """识别关键信号"""
        signals = []
        if features["stage_score"] >= 0.6:
            signals.append("已进入高意向阶段")
        if features["has_target_date"] > 0:
            signals.append("有明确宴会日期")
        if features["time_pressure"] >= 0.7:
            signals.append("距离宴会日期较近，需要尽快推进")
        if features["follow_up_engagement"] >= 0.5:
            signals.append("跟进互动频繁，客户活跃")
        if features["competitor_risk"] > 0:
            signals.append("有竞对比较，需要差异化")
        if features.get("engagement_decay", 1.0) < 0.5:
            signals.append("客户活跃度下降，需要重新激活")
        return signals

    def _recommend_action(
        self, stage: str, probability: float, features: Dict[str, float],
    ) -> str:
        """推荐下一步行动"""
        if probability >= 0.7:
            if stage == "negotiation":
                return "主动让步促成签约"
            if stage == "room_lock":
                return "安排合同细节沟通"
            return "加快推进到下一阶段"

        if probability >= 0.4:
            if features.get("competitor_risk", 0) > 0:
                return "强调差异化优势，安排对比方案"
            return "增加跟进频次，深入了解需求"

        if features.get("engagement_decay", 1.0) < 0.5:
            return "发送限时优惠重新激活客户兴趣"

        return "保持定期跟进，培育客户关系"


intent_predictor = IntentPredictor()
