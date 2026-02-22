"""
RaaS定价服务 (Result-as-a-Service Pricing Service)
按效果付费的商业模式实现

核心理念: 不卖软件，卖结果
- 基础版: 免费试用3个月
- 效果版: 省下成本的20%作为服务费
- 增长版: 增加营收的15%作为分成
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel
from sqlalchemy.orm import Session
import structlog

logger = structlog.get_logger()


class PricingTier(str, Enum):
    """定价层级"""
    FREE_TRIAL = "free_trial"  # 基础版（免费试用）
    COST_SAVING = "cost_saving"  # 效果版（按省下的成本分成）
    REVENUE_GROWTH = "revenue_growth"  # 增长版（按增加的营收分成）
    MODEL_MARKETPLACE = "model_marketplace"  # 模型版（一次性购买）


class CostCategory(str, Enum):
    """成本类别"""
    FOOD_WASTE = "food_waste"  # 食材损耗
    LABOR_COST = "labor_cost"  # 人工成本
    ENERGY_COST = "energy_cost"  # 能源成本
    INVENTORY_COST = "inventory_cost"  # 库存成本


class RevenueCategory(str, Enum):
    """营收类别"""
    CUSTOMER_TRAFFIC = "customer_traffic"  # 客流增加
    AVERAGE_ORDER_VALUE = "average_order_value"  # 客单价提升
    REPEAT_RATE = "repeat_rate"  # 复购率提升


class EffectMetrics(BaseModel):
    """效果指标"""
    # 成本节省
    food_waste_saved: float = 0.0  # 食材损耗节省（元）
    labor_cost_saved: float = 0.0  # 人工成本节省（元）
    energy_cost_saved: float = 0.0  # 能源成本节省（元）
    inventory_cost_saved: float = 0.0  # 库存成本节省（元）
    total_cost_saved: float = 0.0  # 总成本节省（元）

    # 营收增长
    revenue_from_traffic: float = 0.0  # 客流增加带来的营收（元）
    revenue_from_aov: float = 0.0  # 客单价提升带来的营收（元）
    revenue_from_repeat: float = 0.0  # 复购率提升带来的营收（元）
    total_revenue_growth: float = 0.0  # 总营收增长（元）

    # 计费金额
    cost_saving_fee: float = 0.0  # 成本节省分成（20%）
    revenue_growth_fee: float = 0.0  # 营收增长分成（15%）
    total_fee: float = 0.0  # 总计费金额（元）


class BaselineMetrics(BaseModel):
    """基线指标（试用期前3个月的平均值）"""
    # 成本基线
    avg_food_waste_rate: float  # 平均食材损耗率（%）
    avg_labor_cost: float  # 平均人工成本（元/月）
    avg_energy_cost: float  # 平均能源成本（元/月）
    avg_inventory_turnover: float  # 平均库存周转率（次/月）

    # 营收基线
    avg_daily_revenue: float  # 平均日营业额（元）
    avg_customer_count: float  # 平均日客流量（人）
    avg_order_value: float  # 平均客单价（元）
    avg_repeat_rate: float  # 平均复购率（%）

    # 基线时间范围
    baseline_start_date: datetime
    baseline_end_date: datetime


class RaaSPricingService:
    """RaaS定价服务"""

    # 分成比例
    COST_SAVING_COMMISSION = 0.20  # 成本节省分成20%
    REVENUE_GROWTH_COMMISSION = 0.15  # 营收增长分成15%

    # 免费试用期
    FREE_TRIAL_DAYS = 90  # 3个月免费试用

    def __init__(self, db: Session):
        self.db = db

    async def calculate_baseline(
        self,
        store_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> BaselineMetrics:
        """
        计算基线指标

        在免费试用期开始前，收集门店过去3个月的运营数据作为基线
        """
        logger.info(
            "计算基线指标",
            store_id=store_id,
            start_date=start_date,
            end_date=end_date
        )

        # TODO: 从数据库查询历史数据
        # 这里使用模拟数据
        baseline = BaselineMetrics(
            # 成本基线
            avg_food_waste_rate=8.0,  # 8%食材损耗率
            avg_labor_cost=50000.0,  # 5万元/月人工成本
            avg_energy_cost=8000.0,  # 8千元/月能源成本
            avg_inventory_turnover=12.0,  # 12次/月库存周转

            # 营收基线
            avg_daily_revenue=70000.0,  # 7万元/天营业额
            avg_customer_count=500.0,  # 500人/天客流量
            avg_order_value=140.0,  # 140元客单价
            avg_repeat_rate=25.0,  # 25%复购率

            # 基线时间范围
            baseline_start_date=start_date,
            baseline_end_date=end_date
        )

        return baseline

    async def calculate_effect_metrics(
        self,
        store_id: str,
        baseline: BaselineMetrics,
        current_period_start: datetime,
        current_period_end: datetime
    ) -> EffectMetrics:
        """
        计算效果指标

        对比基线和当前期间的数据，计算实际产生的效果
        """
        logger.info(
            "计算效果指标",
            store_id=store_id,
            period_start=current_period_start,
            period_end=current_period_end
        )

        # TODO: 从数据库查询当前期间数据
        # 这里使用模拟数据（假设使用智链OS后的改善）
        current_food_waste_rate = 3.0  # 降低到3%
        current_labor_cost = 45000.0  # 降低到4.5万元
        current_energy_cost = 7500.0  # 降低到7.5千元
        current_inventory_turnover = 15.0  # 提升到15次/月

        current_daily_revenue = 82000.0  # 提升到8.2万元/天
        current_customer_count = 575.0  # 提升到575人/天
        current_order_value = 155.0  # 提升到155元
        current_repeat_rate = 32.0  # 提升到32%

        # 计算成本节省
        days_in_period = (current_period_end - current_period_start).days
        months_in_period = days_in_period / 30.0

        # 食材损耗节省
        baseline_food_cost = baseline.avg_daily_revenue * baseline.avg_food_waste_rate / 100 * days_in_period
        current_food_cost = current_daily_revenue * current_food_waste_rate / 100 * days_in_period
        food_waste_saved = max(0, baseline_food_cost - current_food_cost)

        # 人工成本节省
        labor_cost_saved = max(0, (baseline.avg_labor_cost - current_labor_cost) * months_in_period)

        # 能源成本节省
        energy_cost_saved = max(0, (baseline.avg_energy_cost - current_energy_cost) * months_in_period)

        # 库存成本节省（周转率提升意味着库存成本降低）
        inventory_improvement = (current_inventory_turnover - baseline.avg_inventory_turnover) / baseline.avg_inventory_turnover
        inventory_cost_saved = max(0, baseline.avg_daily_revenue * 0.3 * inventory_improvement * days_in_period)

        total_cost_saved = food_waste_saved + labor_cost_saved + energy_cost_saved + inventory_cost_saved

        # 计算营收增长
        baseline_total_revenue = baseline.avg_daily_revenue * days_in_period
        current_total_revenue = current_daily_revenue * days_in_period

        # 客流增加带来的营收
        traffic_growth = (current_customer_count - baseline.avg_customer_count) / baseline.avg_customer_count
        revenue_from_traffic = baseline_total_revenue * traffic_growth

        # 客单价提升带来的营收
        aov_growth = (current_order_value - baseline.avg_order_value) / baseline.avg_order_value
        revenue_from_aov = baseline_total_revenue * aov_growth

        # 复购率提升带来的营收
        repeat_growth = (current_repeat_rate - baseline.avg_repeat_rate) / 100
        revenue_from_repeat = baseline_total_revenue * repeat_growth

        total_revenue_growth = max(0, current_total_revenue - baseline_total_revenue)

        # 计算计费金额
        cost_saving_fee = total_cost_saved * self.COST_SAVING_COMMISSION
        revenue_growth_fee = total_revenue_growth * self.REVENUE_GROWTH_COMMISSION
        total_fee = cost_saving_fee + revenue_growth_fee

        metrics = EffectMetrics(
            # 成本节省
            food_waste_saved=food_waste_saved,
            labor_cost_saved=labor_cost_saved,
            energy_cost_saved=energy_cost_saved,
            inventory_cost_saved=inventory_cost_saved,
            total_cost_saved=total_cost_saved,

            # 营收增长
            revenue_from_traffic=revenue_from_traffic,
            revenue_from_aov=revenue_from_aov,
            revenue_from_repeat=revenue_from_repeat,
            total_revenue_growth=total_revenue_growth,

            # 计费金额
            cost_saving_fee=cost_saving_fee,
            revenue_growth_fee=revenue_growth_fee,
            total_fee=total_fee
        )

        logger.info(
            "效果指标计算完成",
            store_id=store_id,
            total_cost_saved=total_cost_saved,
            total_revenue_growth=total_revenue_growth,
            total_fee=total_fee
        )

        return metrics

    async def get_pricing_tier(
        self,
        store_id: str,
        current_date: datetime
    ) -> PricingTier:
        """
        获取门店当前的定价层级
        """
        # TODO: 从数据库查询门店的订阅信息
        # 这里使用简单逻辑判断

        # 假设门店的开始使用日期
        start_date = current_date - timedelta(days=120)

        # 如果在免费试用期内
        if (current_date - start_date).days <= self.FREE_TRIAL_DAYS:
            return PricingTier.FREE_TRIAL

        # 试用期结束后，根据门店选择返回对应层级
        # TODO: 从数据库查询门店选择的层级
        return PricingTier.COST_SAVING

    async def generate_monthly_bill(
        self,
        store_id: str,
        year: int,
        month: int
    ) -> Dict:
        """
        生成月度账单
        """
        logger.info("生成月度账单", store_id=store_id, year=year, month=month)

        # 计算当月时间范围
        period_start = datetime(year, month, 1)
        if month == 12:
            period_end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = datetime(year, month + 1, 1) - timedelta(days=1)

        # 获取定价层级
        pricing_tier = await self.get_pricing_tier(store_id, period_end)

        # 如果是免费试用期，账单金额为0
        if pricing_tier == PricingTier.FREE_TRIAL:
            return {
                "store_id": store_id,
                "year": year,
                "month": month,
                "pricing_tier": pricing_tier,
                "total_fee": 0.0,
                "message": "免费试用期，无需付费"
            }

        # 获取基线指标
        baseline_start = period_start - timedelta(days=90)
        baseline_end = period_start - timedelta(days=1)
        baseline = await self.calculate_baseline(store_id, baseline_start, baseline_end)

        # 计算效果指标
        effect_metrics = await self.calculate_effect_metrics(
            store_id,
            baseline,
            period_start,
            period_end
        )

        # 生成账单
        bill = {
            "store_id": store_id,
            "year": year,
            "month": month,
            "pricing_tier": pricing_tier,
            "baseline": baseline.dict(),
            "effect_metrics": effect_metrics.dict(),
            "total_fee": effect_metrics.total_fee,
            "message": f"本月为您节省成本 ¥{effect_metrics.total_cost_saved:,.2f}，增加营收 ¥{effect_metrics.total_revenue_growth:,.2f}"
        }

        return bill


# 全局服务实例
raas_pricing_service: Optional[RaaSPricingService] = None


def get_raas_pricing_service(db: Session) -> RaaSPricingService:
    """获取RaaS定价服务实例"""
    return RaaSPricingService(db)
