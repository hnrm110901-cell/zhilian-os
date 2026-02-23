"""
增强的销售预测服务
集成节假日、天气、商圈活动等多维度特征
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
import structlog
import numpy as np
import os

from src.services.forecast_features import ChineseHolidays, WeatherImpact, BusinessDistrictEvents
from src.services.base_service import BaseService

logger = structlog.get_logger()


class EnhancedForecastService(BaseService):
    """
    增强的销售预测服务
    """

    def __init__(self, store_id: Optional[str] = None, restaurant_type: str = "正餐"):
        super().__init__(store_id)
        self.restaurant_type = restaurant_type

    async def forecast_sales(
        self,
        target_date: date,
        weather_forecast: Optional[Dict[str, Any]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        预测指定日期的销售额

        Args:
            target_date: 目标日期
            weather_forecast: 天气预报 {"temperature": 25, "weather": "晴天"}
            events: 商圈活动列表 [{"type": "大型展会", "impact": 1.8}]

        Returns:
            预测结果
        """
        store_id = self.require_store_id()

        # 1. 获取历史基准数据 + 计算真实周末系数
        historical_baseline = await self._get_historical_baseline(target_date)
        computed_weekend_factor = await self._compute_weekend_factor(store_id)

        # 2. 计算各维度影响因子
        factors = self._calculate_impact_factors(
            target_date,
            weather_forecast,
            events,
            weekend_factor=computed_weekend_factor
        )

        # 3. 综合预测
        base_sales = historical_baseline["average_sales"]
        predicted_sales = base_sales

        # 应用各维度影响因子
        for factor_name, factor_value in factors.items():
            predicted_sales *= factor_value

        # 4. 计算置信区间
        std_dev = historical_baseline["std_dev"]
        confidence_interval = {
            "lower": max(0, predicted_sales - float(os.getenv("FORECAST_CONFIDENCE_Z", "1.96")) * std_dev),  # 95%置信区间下限
            "upper": predicted_sales + float(os.getenv("FORECAST_CONFIDENCE_Z", "1.96")) * std_dev,  # 95%置信区间上限
        }

        # 5. 生成预测说明
        explanation = self._generate_explanation(factors, historical_baseline)

        result = {
            "target_date": target_date.isoformat(),
            "predicted_sales": round(predicted_sales, 2),
            "confidence_interval": confidence_interval,
            "baseline_sales": round(base_sales, 2),
            "impact_factors": factors,
            "explanation": explanation,
            "model_version": "enhanced_v1.0",
            "confidence_level": self._calculate_confidence_level(historical_baseline),
        }

        logger.info(
            "Sales forecast generated",
            store_id=store_id,
            target_date=target_date.isoformat(),
            predicted_sales=predicted_sales,
        )

        return result

    def _calculate_impact_factors(
        self,
        target_date: date,
        weather_forecast: Optional[Dict[str, Any]],
        events: Optional[List[Dict[str, Any]]],
        weekend_factor: float = float(os.getenv("FORECAST_WEEKEND_FACTOR", "1.4")),
    ) -> Dict[str, float]:
        """
        计算各维度影响因子

        Returns:
            影响因子字典
        """
        factors = {}

        # 1. 星期因子
        weekday = target_date.weekday()
        if weekday in [5, 6]:  # 周末
            factors["weekend_factor"] = weekend_factor
        else:
            factors["weekday_factor"] = 1.0

        # 2. 节假日因子
        holiday_impact = ChineseHolidays.get_holiday_impact_score(target_date)
        if holiday_impact > 1.0:
            factors["holiday_factor"] = holiday_impact

        # 3. 节假日时期因子（节前、节中、节后）
        holiday_period = ChineseHolidays.get_holiday_period(target_date)
        if holiday_period == "节前":
            factors["pre_holiday_factor"] = float(os.getenv("FORECAST_PRE_HOLIDAY_FACTOR", "1.2"))
        elif holiday_period == "节后":
            factors["post_holiday_factor"] = float(os.getenv("FORECAST_POST_HOLIDAY_FACTOR", "0.9"))

        # 4. 天气因子
        if weather_forecast:
            temperature = weather_forecast.get("temperature")
            weather_type = weather_forecast.get("weather")

            if temperature is not None:
                temp_impact = WeatherImpact.get_temperature_impact(
                    temperature,
                    self.restaurant_type
                )
                if temp_impact != 1.0:
                    factors["temperature_factor"] = temp_impact

            if weather_type:
                weather_impact = WeatherImpact.get_weather_impact(weather_type)
                if weather_impact != 1.0:
                    factors["weather_factor"] = weather_impact

        # 5. 商圈活动因子
        if events:
            event_impact = 1.0
            for event in events:
                event_type = event.get("type")
                if event_type:
                    event_impact *= BusinessDistrictEvents.get_event_impact(event_type)

            if event_impact != 1.0:
                factors["event_factor"] = event_impact

        # 6. 月份季节因子
        month = target_date.month
        if month in [1, 2]:  # 冬季，火锅旺季
            if self.restaurant_type == "火锅":
                factors["season_factor"] = float(os.getenv("FORECAST_HOTPOT_WINTER_FACTOR", "1.3"))
        elif month in [7, 8]:  # 夏季，火锅淡季
            if self.restaurant_type == "火锅":
                factors["season_factor"] = float(os.getenv("FORECAST_HOTPOT_SUMMER_FACTOR", "0.8"))

        return factors

    async def _compute_weekend_factor(self, store_id: str) -> float:
        """从过去30天DailyReport计算实际周末/工作日营收比"""
        try:
            from sqlalchemy import select, func as sa_func
            from src.core.database import get_db_session
            from src.models.daily_report import DailyReport
            cutoff = date.today() - timedelta(days=int(os.getenv("FORECAST_HISTORY_DAYS", "30")))
            async with get_db_session() as session:
                result = await session.execute(
                    select(DailyReport.report_date, DailyReport.total_revenue).where(
                        DailyReport.store_id == store_id,
                        DailyReport.report_date >= cutoff,
                    )
                )
                rows = result.all()
            if not rows:
                return float(os.getenv("FORECAST_DEFAULT_WEEKEND_FACTOR", "1.4"))
            weekend_revs = [float(r.total_revenue) for r in rows if r.report_date.weekday() in [5, 6]]
            weekday_revs = [float(r.total_revenue) for r in rows if r.report_date.weekday() not in [5, 6]]
            if weekend_revs and weekday_revs:
                factor = sum(weekend_revs) / len(weekend_revs) / (sum(weekday_revs) / len(weekday_revs))
                return round(max(1.0, min(float(os.getenv("FORECAST_WEEKEND_FACTOR_MAX", "2.5")), factor)), 2)
        except Exception as e:
            logger.warning("周末系数计算失败，使用默认值", error=str(e))
        return float(os.getenv("FORECAST_DEFAULT_WEEKEND_FACTOR", "1.4"))

    async def _get_historical_baseline(self, target_date: date) -> Dict[str, float]:
        """
        获取历史基准数据

        Args:
            target_date: 目标日期

        Returns:
            历史基准数据
        """
        from sqlalchemy import select
        from src.core.database import get_db_session
        from src.models.daily_report import DailyReport

        store_id = self.store_id
        weekday = target_date.weekday()
        samples = []

        if store_id:
            async with get_db_session() as session:
                for weeks_ago in range(1, 9):
                    past_date = target_date - timedelta(weeks=weeks_ago)
                    result = await session.execute(
                        select(DailyReport.total_revenue).where(
                            DailyReport.store_id == store_id,
                            DailyReport.report_date == past_date,
                        )
                    )
                    row = result.scalar_one_or_none()
                    if row is not None:
                        samples.append(float(row) / 100.0)

        if len(samples) >= 3:
            return {
                "average_sales": float(np.mean(samples)),
                "std_dev": float(np.std(samples)),
                "sample_count": len(samples),
            }

        # Fallback to industry baseline
        is_weekend = weekday in [5, 6]
        if self.restaurant_type == "火锅":
            base_sales = int(os.getenv("FORECAST_HOTPOT_WEEKEND_SALES", "68000")) if is_weekend else int(os.getenv("FORECAST_HOTPOT_WEEKDAY_SALES", "42000"))
            std_dev = int(os.getenv("FORECAST_HOTPOT_WEEKEND_STD", "11000")) if is_weekend else int(os.getenv("FORECAST_HOTPOT_WEEKDAY_STD", "7000"))
        elif self.restaurant_type == "快餐":
            base_sales = int(os.getenv("FORECAST_FASTFOOD_WEEKEND_SALES", "25000")) if is_weekend else int(os.getenv("FORECAST_FASTFOOD_WEEKDAY_SALES", "18000"))
            std_dev = int(os.getenv("FORECAST_FASTFOOD_WEEKEND_STD", "4500")) if is_weekend else int(os.getenv("FORECAST_FASTFOOD_WEEKDAY_STD", "3500"))
        else:
            base_sales = int(os.getenv("FORECAST_RESTAURANT_WEEKEND_SALES", "55000")) if is_weekend else int(os.getenv("FORECAST_RESTAURANT_WEEKDAY_SALES", "35000"))
            std_dev = int(os.getenv("FORECAST_RESTAURANT_WEEKEND_STD", "9000")) if is_weekend else int(os.getenv("FORECAST_RESTAURANT_WEEKDAY_STD", "6000"))

        return {
            "average_sales": base_sales,
            "std_dev": std_dev,
            "sample_count": 0,
        }

    def _generate_explanation(
        self,
        factors: Dict[str, float],
        historical_baseline: Dict[str, float]
    ) -> str:
        """
        生成预测说明

        Args:
            factors: 影响因子
            historical_baseline: 历史基准

        Returns:
            预测说明文本
        """
        explanations = []

        base_sales = historical_baseline["average_sales"]
        explanations.append(f"基于历史同类型日期的平均销售额{base_sales:.0f}元")

        # 解释各个因子
        if "weekend_factor" in factors:
            explanations.append("周末客流增加40%")

        if "holiday_factor" in factors:
            impact = factors["holiday_factor"]
            if impact >= float(os.getenv("FORECAST_HOLIDAY_IMPACT_THRESHOLD", "2.0")):
                explanations.append(f"法定节假日，预计客流增加{(impact-1)*100:.0f}%")

        if "pre_holiday_factor" in factors:
            explanations.append("节前消费高峰，预计增加20%")

        if "post_holiday_factor" in factors:
            explanations.append("节后消费回落，预计减少10%")

        if "temperature_factor" in factors:
            impact = factors["temperature_factor"]
            if impact > 1.0:
                explanations.append(f"低温天气利好{self.restaurant_type}，增加{(impact-1)*100:.0f}%")
            elif impact < 1.0:
                explanations.append(f"极端天气影响客流，减少{(1-impact)*100:.0f}%")

        if "weather_factor" in factors:
            impact = factors["weather_factor"]
            if impact < 1.0:
                explanations.append(f"恶劣天气影响，预计减少{(1-impact)*100:.0f}%")

        if "event_factor" in factors:
            impact = factors["event_factor"]
            if impact > 1.0:
                explanations.append(f"商圈活动带动，预计增加{(impact-1)*100:.0f}%")
            elif impact < 1.0:
                explanations.append(f"周边不利因素，预计减少{(1-impact)*100:.0f}%")

        if "season_factor" in factors:
            impact = factors["season_factor"]
            if impact > 1.0:
                explanations.append(f"旺季效应，预计增加{(impact-1)*100:.0f}%")
            elif impact < 1.0:
                explanations.append(f"淡季影响，预计减少{(1-impact)*100:.0f}%")

        return "；".join(explanations) + "。"

    def _calculate_confidence_level(self, historical_baseline: Dict[str, float]) -> str:
        """
        计算预测置信度等级

        Args:
            historical_baseline: 历史基准数据

        Returns:
            置信度等级：high/medium/low
        """
        sample_count = historical_baseline.get("sample_count", 0)

        if sample_count >= int(os.getenv("FORECAST_HIGH_CONFIDENCE_SAMPLES", "30")):
            return "high"
        elif sample_count >= int(os.getenv("FORECAST_MED_CONFIDENCE_SAMPLES", "10")):
            return "medium"
        else:
            return "low"

    async def forecast_traffic(
        self,
        target_date: date,
        meal_period: str,
        weather_forecast: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        预测客流量

        Args:
            target_date: 目标日期
            meal_period: 用餐时段（早餐/午餐/晚餐）
            weather_forecast: 天气预报

        Returns:
            客流预测结果
        """
        # 获取基准客流
        day_type = "周末" if target_date.weekday() in [5, 6] else "工作日"

        # 从数据库获取历史客流数据（过去8周同星期）
        from src.core.database import get_db_session
        from src.models.daily_report import DailyReport
        from sqlalchemy import select, func

        historical_traffic = None
        async with get_db_session() as session:
            dates = [target_date - timedelta(weeks=w) for w in range(1, 9)]
            result = await session.execute(
                select(func.avg(DailyReport.customer_count)).where(
                    DailyReport.store_id == self.store_id,
                    DailyReport.report_date.in_(dates),
                    DailyReport.customer_count > 0,
                )
            )
            avg_traffic = result.scalar()
            if avg_traffic and avg_traffic > 0:
                historical_traffic = float(avg_traffic)
        from src.services.baseline_data_service import IndustryBaselineData

        baseline = IndustryBaselineData.get_traffic_baseline(
            self.restaurant_type,
            day_type,
            meal_period
        )

        if historical_traffic:
            base_traffic = historical_traffic
        elif baseline:
            base_traffic = baseline["平均客流"]
        else:
            return {"error": "No baseline data available"}

        # 计算影响因子
        factors = self._calculate_impact_factors(target_date, weather_forecast, None)

        # 应用因子
        predicted_traffic = base_traffic
        for factor_value in factors.values():
            predicted_traffic *= factor_value

        return {
            "target_date": target_date.isoformat(),
            "meal_period": meal_period,
            "predicted_traffic": round(predicted_traffic),
            "baseline_traffic": base_traffic,
            "impact_factors": factors,
        }
