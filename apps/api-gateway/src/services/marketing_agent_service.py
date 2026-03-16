"""
营销智能体服务
Marketing Agent Service

核心功能：
1. 顾客画像向量化
2. 流失风险预测
3. 智能发券策略
4. 个性化推荐
5. 私域运营自动化

业务价值：
- 客流提升：15-25%
- 复购率提升：30%
- 客单价提升：10-15%
- 私域转化率：20%+
"""

import logging
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel
from sqlalchemy import func, select
from src.core.database import get_db_session
from src.models.dish import Dish
from src.models.order import Order, OrderItem, OrderStatus

logger = logging.getLogger(__name__)


class CustomerSegment(str, Enum):
    """客户分群"""

    HIGH_VALUE = "high_value"  # 高价值客户
    POTENTIAL = "potential"  # 潜力客户
    AT_RISK = "at_risk"  # 流失风险客户
    LOST = "lost"  # 已流失客户
    NEW = "new"  # 新客户


class MarketingChannel(str, Enum):
    """营销渠道"""

    WECHAT = "wechat"  # 企业微信
    SMS = "sms"  # 短信
    APP_PUSH = "app_push"  # APP推送
    IN_STORE = "in_store"  # 店内营销


class CouponStrategy(BaseModel):
    """优惠券策略"""

    coupon_type: str  # 券类型（满减/折扣/代金）
    amount: Decimal  # 金额
    threshold: Optional[Decimal]  # 门槛
    valid_days: int  # 有效天数
    target_segment: CustomerSegment  # 目标客群
    expected_conversion: float  # 预期转化率
    expected_roi: float  # 预期ROI


class MarketingCampaign(BaseModel):
    """营销活动"""

    campaign_id: str
    name: str
    objective: str  # 目标（拉新/促活/挽回）
    target_segment: CustomerSegment
    channel: MarketingChannel
    coupon_strategy: CouponStrategy
    start_time: datetime
    end_time: datetime
    budget: Decimal
    expected_reach: int  # 预期触达人数


class MarketingAgentService:
    """营销智能体服务"""

    def __init__(self, db):
        self.db = db

    # ==================== 顾客画像 ====================

    async def build_customer_profile(self, customer_id: str, tenant_id: str) -> Dict[str, Any]:
        """
        构建顾客画像

        Args:
            customer_id: 顾客ID
            tenant_id: 租户ID

        Returns:
            顾客画像
        """
        # 1. 基础信息
        basic_info = await self._get_customer_basic_info(customer_id)

        # 2. 消费行为
        consumption = await self._analyze_consumption_behavior(customer_id)

        # 3. 口味偏好（向量化）
        taste_vector = await self._vectorize_taste_preference(customer_id)

        # 4. 价值评估
        value_score = await self._calculate_customer_value(customer_id)

        # 5. 流失风险
        churn_risk = await self._predict_churn_risk(customer_id)

        profile = {
            "customer_id": customer_id,
            "basic_info": basic_info,
            "consumption": consumption,
            "taste_vector": taste_vector,
            "value_score": value_score,
            "churn_risk": churn_risk,
            "segment": self._determine_segment(value_score, churn_risk),
            "updated_at": datetime.now(),
        }

        logger.info(f"Built customer profile for {customer_id}")

        return profile

    async def _get_customer_basic_info(self, customer_id: str) -> Dict:
        """获取顾客基础信息"""
        # customer_id 为手机号
        async with get_db_session() as session:
            result = await session.execute(
                select(Order.customer_name, Order.customer_phone).where(Order.customer_phone == customer_id).limit(1)
            )
            row = result.one_or_none()

        return {
            "name": row[0] if row else "未知",
            "phone": customer_id,
            "gender": "unknown",
            "age": None,
            "register_date": None,
            "member_level": "regular",
        }

    async def _analyze_consumption_behavior(self, customer_id: str) -> Dict:
        """分析消费行为"""
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    func.count(Order.id),
                    func.coalesce(func.sum(Order.final_amount), 0),
                    func.max(Order.order_time),
                ).where(
                    Order.customer_phone == customer_id,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            row = result.one()

            # 推断偏好时段（按小时统计）
            hour_result = await session.execute(
                select(func.extract("hour", Order.order_time)).where(
                    Order.customer_phone == customer_id,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            hours = [int(h[0]) for h in hour_result.all() if h[0] is not None]

            # 推断偏好星期（按星期统计）
            dow_result = await session.execute(
                select(func.extract("dow", Order.order_time)).where(
                    Order.customer_phone == customer_id,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            days = [int(d[0]) for d in dow_result.all() if d[0] is not None]

            # 获取最常点的菜品
            dish_result = await session.execute(
                select(OrderItem.item_name, func.sum(OrderItem.quantity).label("qty"))
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.customer_phone == customer_id,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
                .group_by(OrderItem.item_name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(5)
            )
            favorite_dishes = [row_d[0] for row_d in dish_result.all()]

        total_orders = int(row[0] or 0)
        total_amount = Decimal(str(row[1] or 0)) / 100
        last_order_time = row[2]

        avg_order_amount = round(float(total_amount / total_orders), 1) if total_orders > 0 else 0.0
        last_order_date = last_order_time.strftime("%Y-%m-%d") if last_order_time else None
        days_since_last = (datetime.now() - last_order_time).days if last_order_time else 999

        # 推断偏好时段
        if hours:
            avg_hour = sum(hours) / len(hours)
            if avg_hour < int(os.getenv("MARKETING_BREAKFAST_END_HOUR", "10")):
                preferred_time = "早餐"
            elif avg_hour < int(os.getenv("MARKETING_LUNCH_END_HOUR", "14")):
                preferred_time = "午餐"
            else:
                preferred_time = "晚餐"
        else:
            preferred_time = "晚餐"

        # 推断偏好星期
        if days:
            from collections import Counter

            most_common_dow = Counter(days).most_common(1)[0][0]
            day_names = {0: "周日", 1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六"}
            preferred_day = day_names.get(most_common_dow, "周末")
        else:
            preferred_day = "周末"

        return {
            "total_orders": total_orders,
            "total_amount": total_amount,
            "avg_order_amount": avg_order_amount,
            "last_order_date": last_order_date,
            "days_since_last_order": days_since_last,
            "favorite_dishes": favorite_dishes,
            "preferred_time": preferred_time,
            "preferred_day": preferred_day,
        }

    async def _vectorize_taste_preference(self, customer_id: str) -> List[float]:
        """向量化口味偏好（基于历史订单菜品类别统计）"""
        # 5维特征向量：[辣度偏好, 素食偏好, 海鲜偏好, 肉类偏好, 甜品偏好]
        async with get_db_session() as session:
            result = await session.execute(
                select(OrderItem.item_name, func.sum(OrderItem.quantity).label("qty"))
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.customer_phone == customer_id,
                    Order.status == OrderStatus.COMPLETED,
                )
                .group_by(OrderItem.item_name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(20)
            )
            items = result.all()

        if not items:
            return [0.5, 0.2, 0.3, 0.6, 0.2]

        total_qty = sum(r.qty for r in items)
        keywords = {
            "spicy": ["辣", "麻", "椒", "火锅"],
            "veg": ["素", "蔬菜", "豆腐", "菌"],
            "seafood": ["鱼", "虾", "蟹", "海鲜", "贝"],
            "meat": ["肉", "牛", "猪", "鸡", "鸭", "羊"],
            "sweet": ["甜", "糕", "饮", "奶", "果"],
        }
        scores = {k: 0.0 for k in keywords}
        for row in items:
            weight = row.qty / total_qty
            for key, kws in keywords.items():
                if any(kw in row.item_name for kw in kws):
                    scores[key] += weight

        return [
            min(1.0, scores["spicy"] * 2),
            min(1.0, scores["veg"] * 2),
            min(1.0, scores["seafood"] * 2),
            min(1.0, scores["meat"] * 2),
            min(1.0, scores["sweet"] * 2),
        ]

    async def _calculate_customer_value(self, customer_id: str) -> float:
        """计算顾客价值（RFM模型）"""
        # R (Recency): 最近一次消费
        # F (Frequency): 消费频次
        # M (Monetary): 消费金额

        consumption = await self._analyze_consumption_behavior(customer_id)

        # 简化的RFM评分
        _r_mult = float(os.getenv("RFM_RECENCY_MULTIPLIER", "2"))
        _f_mult = float(os.getenv("RFM_FREQUENCY_MULTIPLIER", "4"))
        _m_div = float(os.getenv("RFM_MONETARY_DIVISOR", "100"))
        r_score = 100 - min(consumption["days_since_last_order"] * _r_mult, 100)
        f_score = min(consumption["total_orders"] * _f_mult, 100)
        m_score = min(consumption["total_amount"] / _m_div, 100)

        # 加权平均
        _r_weight = float(os.getenv("RFM_RECENCY_WEIGHT", "0.3"))
        _f_weight = float(os.getenv("RFM_FREQUENCY_WEIGHT", "0.3"))
        _m_weight = float(os.getenv("RFM_MONETARY_WEIGHT", "0.4"))
        value_score = r_score * _r_weight + f_score * _f_weight + m_score * _m_weight

        return value_score

    async def _predict_churn_risk(self, customer_id: str) -> float:
        """预测流失风险"""
        consumption = await self._analyze_consumption_behavior(customer_id)

        # 简化的流失风险模型（天数阈值支持环境变量覆盖）
        days_since_last = consumption["days_since_last_order"]
        _low_days = int(os.getenv("CHURN_LOW_RISK_DAYS", "7"))
        _mid_days = int(os.getenv("CHURN_MID_RISK_DAYS", "30"))
        _high_days = int(os.getenv("CHURN_HIGH_RISK_DAYS", "60"))

        if days_since_last < _low_days:
            risk = float(os.getenv("CHURN_RISK_LOW", "0.1"))  # 低风险
        elif days_since_last < _mid_days:
            risk = float(os.getenv("CHURN_RISK_MID", "0.3"))  # 中风险
        elif days_since_last < _high_days:
            risk = float(os.getenv("CHURN_RISK_HIGH", "0.6"))  # 高风险
        else:
            risk = float(os.getenv("CHURN_RISK_CRITICAL", "0.9"))  # 极高风险

        return risk

    def _determine_segment(self, value_score: float, churn_risk: float) -> CustomerSegment:
        """确定客户分群"""
        if value_score > float(os.getenv("SEGMENT_HIGH_VALUE_SCORE", "70")) and churn_risk < float(
            os.getenv("SEGMENT_HIGH_VALUE_CHURN", "0.3")
        ):
            return CustomerSegment.HIGH_VALUE
        elif value_score > float(os.getenv("SEGMENT_POTENTIAL_SCORE", "50")) and churn_risk < float(
            os.getenv("SEGMENT_POTENTIAL_CHURN", "0.5")
        ):
            return CustomerSegment.POTENTIAL
        elif value_score > float(os.getenv("SEGMENT_AT_RISK_SCORE", "40")) and churn_risk > float(
            os.getenv("SEGMENT_AT_RISK_CHURN", "0.5")
        ):
            return CustomerSegment.AT_RISK
        elif churn_risk > float(os.getenv("SEGMENT_LOST_CHURN", "0.8")):
            return CustomerSegment.LOST
        else:
            return CustomerSegment.NEW

    # ==================== 智能营销决策 ====================

    async def generate_coupon_strategy(self, scenario: str, tenant_id: str, context: Optional[Dict] = None) -> CouponStrategy:
        """
        生成发券策略

        Args:
            scenario: 场景（客流下降/新品上市/会员日等）
            tenant_id: 租户ID
            context: 上下文信息

        Returns:
            优惠券策略
        """
        logger.info(f"Generating coupon strategy for scenario: {scenario}")

        # 从 Store 配置读取优惠券参数
        cfg: Dict = {}
        try:
            from src.models.store import Store

            async with get_db_session() as session:
                store_result = await session.execute(select(Store).where(Store.id == tenant_id))
                store = store_result.scalar_one_or_none()
                if store and store.config:
                    cfg = store.config
        except Exception as _e:
            logger.warning("读取Store优惠券配置失败，使用默认值", error=str(_e))

        if scenario == "traffic_decline":
            return CouponStrategy(
                coupon_type="满减券",
                amount=Decimal(str(cfg.get("coupon_traffic_decline_amount", "20.0"))),
                threshold=Decimal(str(cfg.get("coupon_traffic_decline_threshold", "100.0"))),
                valid_days=int(cfg.get("coupon_traffic_decline_days", 7)),
                target_segment=CustomerSegment.AT_RISK,
                expected_conversion=float(cfg.get("coupon_traffic_decline_conversion", 0.25)),
                expected_roi=float(cfg.get("coupon_traffic_decline_roi", 3.5)),
            )

        elif scenario == "new_product_launch":
            return CouponStrategy(
                coupon_type="代金券",
                amount=Decimal(str(cfg.get("coupon_new_product_amount", "15.0"))),
                threshold=None,
                valid_days=int(cfg.get("coupon_new_product_days", 14)),
                target_segment=CustomerSegment.HIGH_VALUE,
                expected_conversion=float(cfg.get("coupon_new_product_conversion", 0.35)),
                expected_roi=float(cfg.get("coupon_new_product_roi", 4.2)),
            )

        elif scenario == "member_day":
            return CouponStrategy(
                coupon_type="折扣券",
                amount=Decimal(str(cfg.get("coupon_member_day_discount", "0.88"))),
                threshold=Decimal(str(cfg.get("coupon_member_day_threshold", "50.0"))),
                valid_days=int(cfg.get("coupon_member_day_valid_days", os.getenv("MARKETING_MEMBER_DAY_VALID_DAYS", "1"))),
                target_segment=CustomerSegment.POTENTIAL,
                expected_conversion=float(cfg.get("coupon_member_day_conversion", 0.40)),
                expected_roi=float(cfg.get("coupon_member_day_roi", 5.0)),
            )

        else:
            return CouponStrategy(
                coupon_type="满减券",
                amount=Decimal(str(cfg.get("coupon_default_amount", "10.0"))),
                threshold=Decimal(str(cfg.get("coupon_default_threshold", "50.0"))),
                valid_days=int(cfg.get("coupon_default_days", 7)),
                target_segment=CustomerSegment.NEW,
                expected_conversion=float(cfg.get("coupon_default_conversion", 0.20)),
                expected_roi=float(cfg.get("coupon_default_roi", 2.8)),
            )

    async def create_marketing_campaign(self, objective: str, tenant_id: str, budget: float) -> MarketingCampaign:
        """
        创建营销活动

        Args:
            objective: 目标（拉新/促活/挽回）
            tenant_id: 租户ID
            budget: 预算

        Returns:
            营销活动
        """
        # 根据目标选择策略
        if objective == "acquisition":
            # 拉新
            target_segment = CustomerSegment.NEW
            scenario = "new_customer"
        elif objective == "activation":
            # 促活
            target_segment = CustomerSegment.POTENTIAL
            scenario = "member_day"
        elif objective == "retention":
            # 挽回
            target_segment = CustomerSegment.AT_RISK
            scenario = "traffic_decline"
        else:
            target_segment = CustomerSegment.HIGH_VALUE
            scenario = "default"

        # 生成优惠券策略
        coupon_strategy = await self.generate_coupon_strategy(scenario, tenant_id)

        # 计算预期触达人数
        budget_decimal = Decimal(str(budget))
        expected_reach = int(budget_decimal / coupon_strategy.amount)

        campaign = MarketingCampaign(
            campaign_id=f"CAMP_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            name=f"{objective}营销活动",
            objective=objective,
            target_segment=target_segment,
            channel=MarketingChannel.WECHAT,
            coupon_strategy=coupon_strategy,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(days=int(os.getenv("MARKETING_CAMPAIGN_DAYS", "7"))),
            budget=budget_decimal,
            expected_reach=expected_reach,
        )

        logger.info(f"Created marketing campaign: {campaign.campaign_id}")

        return campaign

    # ==================== 个性化推荐 ====================

    async def recommend_dishes(self, customer_id: str, tenant_id: str, top_k: int = 5) -> List[Dict]:
        """
        个性化菜品推荐

        Args:
            customer_id: 顾客ID
            tenant_id: 租户ID
            top_k: 推荐数量

        Returns:
            推荐菜品列表
        """
        # 1. 获取顾客口味向量
        taste_vector = await self._vectorize_taste_preference(customer_id)

        # 2. 从数据库查询门店可售菜品（按评分+销量排序）
        async with get_db_session() as session:
            result = await session.execute(
                select(Dish)
                .where(
                    Dish.store_id == tenant_id,
                    Dish.is_available == True,
                )
                .order_by(
                    Dish.rating.desc(),
                    Dish.total_sales.desc(),
                )
                .limit(top_k * 3)
            )
            dishes = result.scalars().all()

        # 3. 返回 Top K（无嵌入模型时按评分排序）
        recommendations = [
            {
                "dish_id": str(d.id),
                "dish_name": d.name,
                "price": str(Decimal(str(d.price)) / 100) if d.price else "0.00",
                "similarity": round(float(d.rating or 4.0) / 5.0, 2),
                "reason": "门店热门推荐" if d.is_recommended else "基于评分推荐",
            }
            for d in dishes
        ]

        return recommendations[:top_k]

    # ==================== 私域运营自动化 ====================

    async def auto_trigger_marketing(self, trigger_type: str, customer_id: str, tenant_id: str):
        """
        自动触发营销

        Args:
            trigger_type: 触发类型（生日/流失预警/复购提醒）
            customer_id: 顾客ID
            tenant_id: 租户ID
        """
        if trigger_type == "birthday":
            # 生日营销
            await self._send_birthday_coupon(customer_id, tenant_id)

        elif trigger_type == "churn_warning":
            # 流失预警
            await self._send_winback_offer(customer_id, tenant_id)

        elif trigger_type == "repurchase_reminder":
            # 复购提醒
            await self._send_repurchase_reminder(customer_id, tenant_id)

    async def _send_birthday_coupon(self, customer_id: str, tenant_id: str):
        """发送生日优惠券"""
        cfg: Dict = {}
        try:
            from src.models.store import Store

            async with get_db_session() as session:
                store_result = await session.execute(select(Store).where(Store.id == tenant_id))
                store = store_result.scalar_one_or_none()
                if store and store.config:
                    cfg = store.config
        except Exception as e:
            logger.warning("store_config_query_failed", error=str(e))

        coupon = {
            "type": "生日专享券",
            "amount": Decimal(str(cfg.get("birthday_coupon_amount", "50.0"))),
            "threshold": Decimal(str(cfg.get("birthday_coupon_threshold", "100.0"))),
            "valid_days": int(cfg.get("birthday_coupon_days", 7)),
        }

        message = f"🎂 生日快乐！送您{coupon['amount']}元生日券，满{coupon['threshold']}可用"

        try:
            from src.services.wechat_work_message_service import WeChatWorkMessageService

            wechat = WeChatWorkMessageService()
            await wechat.send_text_message(customer_id, message)
        except Exception as e:
            logger.warning(f"企微发送生日券失败: {e}")
        logger.info(f"Sent birthday coupon to {customer_id}")

    async def _send_winback_offer(self, customer_id: str, tenant_id: str):
        """发送挽回优惠"""
        cfg: Dict = {}
        try:
            from src.models.store import Store

            async with get_db_session() as session:
                store_result = await session.execute(select(Store).where(Store.id == tenant_id))
                store = store_result.scalar_one_or_none()
                if store and store.config:
                    cfg = store.config
        except Exception as e:
            logger.warning("store_config_query_failed", error=str(e))

        coupon = {
            "type": "专属挽回券",
            "amount": Decimal(str(cfg.get("winback_coupon_amount", "30.0"))),
            "threshold": Decimal(str(cfg.get("winback_coupon_threshold", "80.0"))),
            "valid_days": int(cfg.get("winback_coupon_days", 14)),
        }

        message = f"好久不见！特别为您准备了{coupon['amount']}元优惠券，期待您的光临"

        try:
            from src.services.wechat_work_message_service import WeChatWorkMessageService

            wechat = WeChatWorkMessageService()
            await wechat.send_text_message(customer_id, message)
        except Exception as e:
            logger.warning(f"企微发送挽回券失败: {e}")
        logger.info(f"Sent winback offer to {customer_id}")

    async def _send_repurchase_reminder(self, customer_id: str, tenant_id: str):
        """发送复购提醒"""
        # 获取顾客喜欢的菜品
        profile = await self.build_customer_profile(customer_id, tenant_id)
        favorite_dishes = profile["consumption"]["favorite_dishes"]

        message = f"您喜欢的{favorite_dishes[0]}又上新了，欢迎品尝！"

        try:
            from src.services.wechat_work_message_service import WeChatWorkMessageService

            wechat = WeChatWorkMessageService()
            await wechat.send_text_message(customer_id, message)
        except Exception as e:
            logger.warning(f"企微发送复购提醒失败: {e}")
        logger.info(f"Sent repurchase reminder to {customer_id}")

    # ==================== 营销效果分析 ====================

    async def analyze_campaign_performance(self, campaign_id: str) -> Dict[str, Any]:
        """
        分析营销活动效果

        Args:
            campaign_id: 活动ID

        Returns:
            效果分析
        """
        # 从数据库查询活动数据
        from src.models.marketing_campaign import MarketingCampaign

        async with get_db_session() as session:
            result = await session.execute(select(MarketingCampaign).where(MarketingCampaign.id == campaign_id))
            campaign = result.scalar_one_or_none()

        if campaign:
            reach = campaign.reach_count or 0
            conversion = campaign.conversion_count or 0
            revenue = campaign.revenue_generated or 0.0
            cost = campaign.actual_cost or campaign.budget or 0.0
            conversion_rate = conversion / reach if reach > 0 else 0.0
            roi = (revenue - cost) / cost if cost > 0 else 0.0
            avg_order = revenue / conversion if conversion > 0 else 0.0
            performance = {
                "campaign_id": campaign_id,
                "reach": reach,
                "conversion": conversion,
                "conversion_rate": round(conversion_rate, 4),
                "revenue": revenue,
                "cost": cost,
                "roi": round(roi, 2),
                "avg_order_amount": round(avg_order, 2),
            }
        else:
            performance = {
                "campaign_id": campaign_id,
                "reach": 0,
                "conversion": 0,
                "conversion_rate": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
                "roi": 0.0,
                "avg_order_amount": 0.0,
            }

        return performance

    # ==================== 批量客群分析 ====================

    async def get_store_segment_summary(self, store_id: str) -> Dict[str, Any]:
        """
        获取门店客群分布摘要（批量 RFM 计算）

        一条 SQL 聚合门店所有顾客的消费指标，然后逐行计算 RFM 分群，
        返回各客群人数 + 占比，供前端饼图和 KPI 卡片使用。
        """
        async with get_db_session() as session:
            now = datetime.now()
            stmt = (
                select(
                    Order.customer_phone,
                    func.count(Order.id).label("order_count"),
                    func.coalesce(func.sum(Order.final_amount), 0).label("total_amount"),
                    func.max(Order.order_time).label("last_order_time"),
                )
                .where(
                    Order.store_id == store_id,
                    Order.customer_phone.isnot(None),
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
                .group_by(Order.customer_phone)
            )

            rows = (await session.execute(stmt)).all()

        _r_mult = float(os.getenv("RFM_RECENCY_MULTIPLIER", "2"))
        _f_mult = float(os.getenv("RFM_FREQUENCY_MULTIPLIER", "4"))
        _m_div = float(os.getenv("RFM_MONETARY_DIVISOR", "100"))
        _r_w = float(os.getenv("RFM_RECENCY_WEIGHT", "0.3"))
        _f_w = float(os.getenv("RFM_FREQUENCY_WEIGHT", "0.3"))
        _m_w = float(os.getenv("RFM_MONETARY_WEIGHT", "0.4"))
        _churn_low = int(os.getenv("CHURN_LOW_RISK_DAYS", "7"))
        _churn_mid = int(os.getenv("CHURN_MID_RISK_DAYS", "30"))
        _churn_high = int(os.getenv("CHURN_HIGH_RISK_DAYS", "60"))

        segments: Dict[str, int] = {s.value: 0 for s in CustomerSegment}
        for row in rows:
            days_since = (now - row.last_order_time).days if row.last_order_time else 999
            total_amount = float(row.total_amount or 0) / 100
            total_orders = int(row.order_count or 0)

            r_score = 100 - min(days_since * _r_mult, 100)
            f_score = min(total_orders * _f_mult, 100)
            m_score = min(total_amount / _m_div, 100) if _m_div > 0 else 0.0
            value_score = r_score * _r_w + f_score * _f_w + m_score * _m_w

            if days_since < _churn_low:
                churn_risk = float(os.getenv("CHURN_RISK_LOW", "0.1"))
            elif days_since < _churn_mid:
                churn_risk = float(os.getenv("CHURN_RISK_MID", "0.3"))
            elif days_since < _churn_high:
                churn_risk = float(os.getenv("CHURN_RISK_HIGH", "0.6"))
            else:
                churn_risk = float(os.getenv("CHURN_RISK_CRITICAL", "0.9"))

            seg = self._determine_segment(value_score, churn_risk)
            segments[seg.value] += 1

        total = len(rows)
        return {
            "store_id": store_id,
            "total_customers": total,
            "segments": segments,
            "segments_pct": {k: round(v / total * 100, 1) if total > 0 else 0.0 for k, v in segments.items()},
            "computed_at": now.isoformat(),
        }

    async def get_at_risk_customers(
        self,
        store_id: str,
        limit: int = 50,
        risk_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        获取流失风险客户列表

        查询最近一次消费距今超过 CHURN_MID_RISK_DAYS 天的客户，
        按流失风险从高到低排序，返回前 limit 条。
        """
        _churn_mid = int(os.getenv("CHURN_MID_RISK_DAYS", "30"))
        _churn_high = int(os.getenv("CHURN_HIGH_RISK_DAYS", "60"))
        _churn_risk_mid = float(os.getenv("CHURN_RISK_MID", "0.3"))
        _churn_risk_high = float(os.getenv("CHURN_RISK_HIGH", "0.6"))
        _churn_risk_critical = float(os.getenv("CHURN_RISK_CRITICAL", "0.9"))

        async with get_db_session() as session:
            now = datetime.now()
            cutoff = now - timedelta(days=_churn_mid)

            stmt = (
                select(
                    Order.customer_phone,
                    Order.customer_name,
                    func.count(Order.id).label("order_count"),
                    func.coalesce(func.sum(Order.final_amount), 0).label("total_amount"),
                    func.max(Order.order_time).label("last_order_time"),
                )
                .where(
                    Order.store_id == store_id,
                    Order.customer_phone.isnot(None),
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
                .group_by(Order.customer_phone, Order.customer_name)
                .having(func.max(Order.order_time) < cutoff)
                .order_by(func.max(Order.order_time).asc())
                .limit(limit * 2)  # fetch extra to apply risk_threshold filter
            )
            rows = (await session.execute(stmt)).all()

        result = []
        for row in rows:
            days_since = (now - row.last_order_time).days if row.last_order_time else 999
            total_amount_yuan = round(float(row.total_amount or 0) / 100, 2)

            if days_since < _churn_mid:
                churn_risk = _churn_risk_mid
            elif days_since < _churn_high:
                churn_risk = _churn_risk_high
            else:
                churn_risk = _churn_risk_critical

            if churn_risk < risk_threshold:
                continue

            result.append(
                {
                    "customer_phone": row.customer_phone,
                    "customer_name": row.customer_name or "未知",
                    "order_count": int(row.order_count or 0),
                    "total_amount_yuan": total_amount_yuan,
                    "last_order_date": row.last_order_time.strftime("%Y-%m-%d") if row.last_order_time else None,
                    "days_since_last_order": days_since,
                    "churn_risk": churn_risk,
                    "segment": (
                        CustomerSegment.LOST.value if churn_risk >= _churn_risk_critical else CustomerSegment.AT_RISK.value
                    ),
                    "recommended_action": "重新激活营销" if churn_risk >= _churn_risk_critical else "发送挽回优惠券",
                }
            )

        result.sort(key=lambda x: x["churn_risk"], reverse=True)
        return result[:limit]

    # ==================== 企微批量自动触达 ====================

    async def trigger_batch_churn_recovery(
        self,
        store_id: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        批量触达流失风险客户（企微自动挽回）

        流程：
          1. 拉取本门店所有 at_risk/lost 客户
          2. 对每位客户检查频控（FrequencyCapEngine），勿扰时段/当日已发则跳过
          3. 发送个性化挽回消息（企微文本消息）
          4. 记录发送，递增频控计数器
          5. 返回 {sent, skipped_freq_cap, errors, dry_run}

        dry_run=True 时只统计，不实际发送。
        """
        customers = await self.get_at_risk_customers(store_id, limit=100, risk_threshold=0.5)

        sent = 0
        skipped_freq_cap = 0
        errors = 0

        # 惰性初始化频控引擎和企微服务
        freq_engine = None
        wechat = None
        try:
            import redis.asyncio as aioredis
            from src.services.frequency_cap_engine import FrequencyCapEngine

            _redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis = aioredis.from_url(_redis_url, decode_responses=True)
            freq_engine = FrequencyCapEngine(_redis)
        except Exception as e:
            logger.warning("freq_cap_init_failed: %s", str(e))

        if not dry_run:
            try:
                from src.services.wechat_work_message_service import WeChatWorkMessageService

                wechat = WeChatWorkMessageService()
            except Exception as e:
                logger.warning("wechat_service_init_failed: %s", str(e))

        for customer in customers:
            phone = customer["customer_phone"]
            churn_risk = customer["churn_risk"]
            days_since = customer["days_since_last_order"]

            # dry_run：直接计入 sent，不检查频控也不实际发送
            if dry_run:
                sent += 1
                continue

            # 频控检查（仅非 dry_run 时生效）
            if freq_engine:
                try:
                    if not await freq_engine.can_send(phone, store_id, "wxwork"):
                        skipped_freq_cap += 1
                        continue
                except Exception:
                    pass  # 频控故障时降级允许

            # 构建个性化消息
            if churn_risk >= float(os.getenv("CHURN_RISK_CRITICAL", "0.9")):
                msg = f"好久不见！您已有{days_since}天未到访，特为您准备了专属挽回券，期待再次相聚～"
            else:
                msg = f"您好，{days_since}天没来啦！我们有新菜上线，欢迎回来尝鲜，专属优惠等您～"

            try:
                if wechat:
                    await wechat.send_text_message(phone, msg)
                # 记录发送
                if freq_engine:
                    try:
                        await freq_engine.record_send(phone, store_id, "wxwork")
                    except Exception as exc:
                        logger.debug("marketing.freq_record_failed", phone=phone, store_id=store_id, error=str(exc))
                sent += 1
            except Exception as e:
                logger.warning("batch_churn_send_failed", phone=phone, error=str(e))
                errors += 1

        logger.info(
            "batch_churn_recovery_done: store=%s sent=%d skipped=%d errors=%d dry_run=%s",
            store_id,
            sent,
            skipped_freq_cap,
            errors,
            dry_run,
        )
        return {
            "store_id": store_id,
            "total_at_risk": len(customers),
            "sent": sent,
            "skipped_freq_cap": skipped_freq_cap,
            "errors": errors,
            "dry_run": dry_run,
        }

    # ==================== 营销效果追踪 ====================

    async def get_campaign_roi_summary(
        self,
        store_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        门店营销活动 ROI 汇总（近 N 天）

        返回：总活动数/活跃活动/总触达人数/总转化/转化率/总营收¥/总成本¥/综合ROI
        同时返回按 campaign_type 细分的子汇总，供前端饼图/柱图使用。
        """
        from src.models.marketing_campaign import MarketingCampaign as MCModel

        cutoff = datetime.now() - timedelta(days=days)

        async with get_db_session() as session:
            stmt = select(MCModel).where(
                MCModel.store_id == store_id,
                MCModel.created_at >= cutoff,
            )
            rows = (await session.execute(stmt)).scalars().all()

        total = len(rows)
        active = sum(1 for r in rows if r.status == "active")
        reach = sum(r.reach_count or 0 for r in rows)
        conversion = sum(r.conversion_count or 0 for r in rows)
        revenue = sum(float(r.revenue_generated or 0) for r in rows)
        cost = sum(float(r.actual_cost or r.budget or 0) for r in rows)
        roi = round((revenue - cost) / cost, 4) if cost > 0 else 0.0
        conv_rate = round(conversion / reach, 4) if reach > 0 else 0.0

        # 细分 by campaign_type
        by_type: Dict[str, Dict] = {}
        for r in rows:
            t = r.campaign_type or "其他"
            if t not in by_type:
                by_type[t] = {"count": 0, "reach": 0, "conversion": 0, "revenue": 0.0, "cost": 0.0}
            by_type[t]["count"] += 1
            by_type[t]["reach"] += r.reach_count or 0
            by_type[t]["conversion"] += r.conversion_count or 0
            by_type[t]["revenue"] += float(r.revenue_generated or 0)
            by_type[t]["cost"] += float(r.actual_cost or r.budget or 0)

        return {
            "store_id": store_id,
            "days": days,
            "total_campaigns": total,
            "active_campaigns": active,
            "total_reach": reach,
            "total_conversion": conversion,
            "conversion_rate": conv_rate,
            "total_revenue_yuan": round(revenue, 2),
            "total_cost_yuan": round(cost, 2),
            "overall_roi": roi,
            "by_type": by_type,
            "computed_at": datetime.now().isoformat(),
        }

    async def record_campaign_attribution(
        self,
        campaign_id: str,
        delta_reach: int = 0,
        delta_conversion: int = 0,
        delta_revenue: float = 0.0,
        delta_cost: float = 0.0,
    ) -> bool:
        """
        活动归因打点：累加触达/转化/营收/成本到 marketing_campaigns 记录。
        供 POS 订单关联营销活动时调用。
        """
        from sqlalchemy import update
        from src.models.marketing_campaign import MarketingCampaign as MCModel

        async with get_db_session() as session:
            stmt = (
                update(MCModel)
                .where(MCModel.id == campaign_id)
                .values(
                    reach_count=MCModel.reach_count + delta_reach,
                    conversion_count=MCModel.conversion_count + delta_conversion,
                    revenue_generated=MCModel.revenue_generated + delta_revenue,
                    actual_cost=MCModel.actual_cost + delta_cost,
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def get_statistics(self) -> Dict[str, Any]:
        """获取营销统计"""
        try:
            from src.models.marketing_campaign import MarketingCampaign

            async with get_db_session() as session:
                result = await session.execute(
                    select(
                        func.count(MarketingCampaign.id),
                        func.sum(func.cast(MarketingCampaign.status == "active", func.Integer)),
                        func.coalesce(func.sum(MarketingCampaign.reach_count), 0),
                        func.coalesce(func.sum(MarketingCampaign.conversion_count), 0),
                        func.coalesce(
                            func.avg(
                                (MarketingCampaign.revenue_generated - MarketingCampaign.actual_cost)
                                / func.nullif(MarketingCampaign.actual_cost, 0)
                            ),
                            0.0,
                        ),
                    )
                )
                row = result.one()
            return {
                "total_campaigns": int(row[0] or 0),
                "active_campaigns": int(row[1] or 0),
                "total_reach": int(row[2] or 0),
                "total_conversion": int(row[3] or 0),
                "avg_roi": round(float(row[4] or 0.0), 4),
            }
        except Exception:
            return {
                "total_campaigns": 0,
                "active_campaigns": 0,
                "total_reach": 0,
                "total_conversion": 0,
                "avg_roi": 0.0,
            }


# 全局实例
_marketing_agent = None


def init_marketing_agent(db):
    """初始化营销智能体"""
    global _marketing_agent
    _marketing_agent = MarketingAgentService(db)
    logger.info("Marketing Agent initialized")


def get_marketing_agent() -> MarketingAgentService:
    """获取营销智能体实例"""
    if _marketing_agent is None:
        raise Exception("Marketing Agent not initialized")
    return _marketing_agent
