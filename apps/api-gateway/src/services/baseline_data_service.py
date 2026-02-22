"""
行业基线数据服务
为新客户提供行业标准数据，解决AI冷启动问题
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()


class IndustryBaselineData:
    """
    餐饮行业基线数据
    基于湖南地区中餐连锁品牌的平均指标
    """

    # 客流量基线数据（按餐厅类型和时段）
    TRAFFIC_BASELINE = {
        "快餐": {
            "工作日": {
                "早餐": {"平均客流": 120, "标准差": 25},
                "午餐": {"平均客流": 280, "标准差": 45},
                "晚餐": {"平均客流": 200, "标准差": 35},
            },
            "周末": {
                "早餐": {"平均客流": 150, "标准差": 30},
                "午餐": {"平均客流": 350, "标准差": 55},
                "晚餐": {"平均客流": 280, "标准差": 45},
            },
        },
        "正餐": {
            "工作日": {
                "午餐": {"平均客流": 180, "标准差": 35},
                "晚餐": {"平均客流": 220, "标准差": 40},
            },
            "周末": {
                "午餐": {"平均客流": 280, "标准差": 50},
                "晚餐": {"平均客流": 320, "标准差": 60},
            },
        },
        "火锅": {
            "工作日": {
                "午餐": {"平均客流": 150, "标准差": 30},
                "晚餐": {"平均客流": 280, "标准差": 50},
            },
            "周末": {
                "午餐": {"平均客流": 250, "标准差": 45},
                "晚餐": {"平均客流": 380, "标准差": 70},
            },
        },
    }

    # 销售额基线数据（元/天）
    REVENUE_BASELINE = {
        "快餐": {
            "工作日": {"平均": 18000, "标准差": 3500},
            "周末": {"平均": 25000, "标准差": 4500},
        },
        "正餐": {
            "工作日": {"平均": 35000, "标准差": 6000},
            "周末": {"平均": 55000, "标准差": 9000},
        },
        "火锅": {
            "工作日": {"平均": 42000, "标准差": 7000},
            "周末": {"平均": 68000, "标准差": 11000},
        },
    }

    # 客单价基线数据（元/人）
    AVERAGE_SPEND_BASELINE = {
        "快餐": {"平均": 35, "标准差": 8},
        "正餐": {"平均": 85, "标准差": 15},
        "火锅": {"平均": 120, "标准差": 25},
    }

    # 翻台率基线数据（次/天）
    TABLE_TURNOVER_BASELINE = {
        "快餐": {
            "工作日": {"平均": 4.5, "标准差": 0.8},
            "周末": {"平均": 5.2, "标准差": 0.9},
        },
        "正餐": {
            "工作日": {"平均": 2.8, "标准差": 0.5},
            "周末": {"平均": 3.5, "标准差": 0.6},
        },
        "火锅": {
            "工作日": {"平均": 2.5, "标准差": 0.4},
            "周末": {"平均": 3.2, "标准差": 0.5},
        },
    }

    # 食材损耗率基线（%）
    FOOD_WASTE_BASELINE = {
        "蔬菜类": {"平均": 8.5, "标准差": 2.0},
        "肉类": {"平均": 5.2, "标准差": 1.5},
        "海鲜类": {"平均": 12.0, "标准差": 3.0},
        "干货类": {"平均": 2.5, "标准差": 0.8},
    }

    # 人力成本占比基线（%）
    LABOR_COST_BASELINE = {
        "快餐": {"平均": 22.0, "标准差": 3.0},
        "正餐": {"平均": 28.0, "标准差": 4.0},
        "火锅": {"平均": 25.0, "标准差": 3.5},
    }

    # 食材成本占比基线（%）
    FOOD_COST_BASELINE = {
        "快餐": {"平均": 35.0, "标准差": 4.0},
        "正餐": {"平均": 38.0, "标准差": 5.0},
        "火锅": {"平均": 42.0, "标准差": 6.0},
    }

    # 员工配置基线（人/100平米）
    STAFF_BASELINE = {
        "快餐": {
            "前厅": {"平均": 3.5, "标准差": 0.8},
            "后厨": {"平均": 4.0, "标准差": 1.0},
        },
        "正餐": {
            "前厅": {"平均": 5.0, "标准差": 1.0},
            "后厨": {"平均": 6.0, "标准差": 1.2},
        },
        "火锅": {
            "前厅": {"平均": 4.5, "标准差": 0.9},
            "后厨": {"平均": 5.0, "标准差": 1.0},
        },
    }

    # 库存周转天数基线
    INVENTORY_TURNOVER_BASELINE = {
        "蔬菜类": {"平均": 2.0, "标准差": 0.5},
        "肉类": {"平均": 3.0, "标准差": 0.8},
        "海鲜类": {"平均": 1.5, "标准差": 0.3},
        "干货类": {"平均": 15.0, "标准差": 5.0},
        "调料类": {"平均": 30.0, "标准差": 10.0},
    }

    @classmethod
    def get_traffic_baseline(
        cls, restaurant_type: str, day_type: str, meal_period: str
    ) -> Optional[Dict[str, float]]:
        """
        获取客流量基线数据

        Args:
            restaurant_type: 餐厅类型（快餐/正餐/火锅）
            day_type: 日期类型（工作日/周末）
            meal_period: 用餐时段（早餐/午餐/晚餐）

        Returns:
            包含平均客流和标准差的字典
        """
        try:
            return cls.TRAFFIC_BASELINE[restaurant_type][day_type][meal_period]
        except KeyError:
            logger.warning(
                "Traffic baseline not found",
                restaurant_type=restaurant_type,
                day_type=day_type,
                meal_period=meal_period,
            )
            return None

    @classmethod
    def get_revenue_baseline(
        cls, restaurant_type: str, day_type: str
    ) -> Optional[Dict[str, float]]:
        """获取销售额基线数据"""
        try:
            return cls.REVENUE_BASELINE[restaurant_type][day_type]
        except KeyError:
            logger.warning(
                "Revenue baseline not found",
                restaurant_type=restaurant_type,
                day_type=day_type,
            )
            return None

    @classmethod
    def get_average_spend_baseline(
        cls, restaurant_type: str
    ) -> Optional[Dict[str, float]]:
        """获取客单价基线数据"""
        try:
            return cls.AVERAGE_SPEND_BASELINE[restaurant_type]
        except KeyError:
            logger.warning(
                "Average spend baseline not found", restaurant_type=restaurant_type
            )
            return None

    @classmethod
    def get_all_baselines(cls, restaurant_type: str) -> Dict[str, Any]:
        """
        获取指定餐厅类型的所有基线数据

        Args:
            restaurant_type: 餐厅类型

        Returns:
            包含所有基线数据的字典
        """
        return {
            "traffic": cls.TRAFFIC_BASELINE.get(restaurant_type, {}),
            "revenue": cls.REVENUE_BASELINE.get(restaurant_type, {}),
            "average_spend": cls.AVERAGE_SPEND_BASELINE.get(restaurant_type, {}),
            "table_turnover": cls.TABLE_TURNOVER_BASELINE.get(restaurant_type, {}),
            "labor_cost": cls.LABOR_COST_BASELINE.get(restaurant_type, {}),
            "food_cost": cls.FOOD_COST_BASELINE.get(restaurant_type, {}),
            "staff": cls.STAFF_BASELINE.get(restaurant_type, {}),
            "food_waste": cls.FOOD_WASTE_BASELINE,
            "inventory_turnover": cls.INVENTORY_TURNOVER_BASELINE,
        }


class BaselineDataService:
    """
    基线数据服务
    管理行业基线数据的存储和检索
    """

    def __init__(self, store_id: str, restaurant_type: str = "正餐"):
        self.store_id = store_id
        self.restaurant_type = restaurant_type
        logger.info(
            "BaselineDataService initialized",
            store_id=store_id,
            restaurant_type=restaurant_type,
        )

    async def check_data_sufficiency(self) -> Dict[str, Any]:
        """
        检查客户数据是否充足

        Returns:
            包含数据充足性评估的字典
        """
        from sqlalchemy import select, func
        from src.core.database import get_db_session
        from src.models.order import Order
        from src.models.daily_report import DailyReport
        from src.models.inventory import InventoryItem

        async with get_db_session() as session:
            orders_result = await session.execute(
                select(func.count(Order.id)).where(Order.store_id == self.store_id)
            )
            orders_count = int(orders_result.scalar() or 0)

            days_result = await session.execute(
                select(func.count(func.distinct(DailyReport.report_date))).where(
                    DailyReport.store_id == self.store_id
                )
            )
            days_of_data = int(days_result.scalar() or 0)

            inventory_result = await session.execute(
                select(func.count(InventoryItem.id)).where(
                    InventoryItem.store_id == self.store_id
                )
            )
            inventory_records = int(inventory_result.scalar() or 0)

        threshold = {"orders": 100, "days": 30, "inventory": 50}
        is_sufficient = (
            orders_count >= threshold["orders"]
            and days_of_data >= threshold["days"]
            and inventory_records >= threshold["inventory"]
        )

        return {
            "orders_count": orders_count,
            "days_of_data": days_of_data,
            "inventory_records": inventory_records,
            "is_sufficient": is_sufficient,
            "threshold": threshold,
        }

    async def should_use_baseline(self) -> bool:
        """
        判断是否应该使用行业基线数据

        Returns:
            True if should use baseline data
        """
        sufficiency = await self.check_data_sufficiency()
        return not sufficiency["is_sufficient"]

    def get_baseline_recommendation(
        self, query_type: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        基于行业基线数据生成建议

        Args:
            query_type: 查询类型（traffic/revenue/inventory等）
            context: 上下文信息

        Returns:
            包含建议和数据来源的字典
        """
        baseline_data = IndustryBaselineData.get_all_baselines(self.restaurant_type)

        recommendation = {
            "data_source": "industry_baseline",
            "restaurant_type": self.restaurant_type,
            "baseline_data": baseline_data,
            "recommendation": self._generate_recommendation(query_type, baseline_data, context),
            "confidence": "medium",  # 基线数据的置信度为中等
            "note": "此建议基于湖南地区同类型餐厅的行业平均数据。随着您的数据积累，系统将提供更精准的个性化建议。",
        }

        logger.info(
            "Generated baseline recommendation",
            store_id=self.store_id,
            query_type=query_type,
            data_source="industry_baseline",
        )

        return recommendation

    def _generate_recommendation(
        self, query_type: str, baseline_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """
        根据查询类型和基线数据生成具体建议

        Args:
            query_type: 查询类型
            baseline_data: 基线数据
            context: 上下文信息

        Returns:
            建议文本
        """
        if query_type == "traffic_forecast":
            return self._generate_traffic_recommendation(baseline_data, context)
        elif query_type == "inventory_planning":
            return self._generate_inventory_recommendation(baseline_data, context)
        elif query_type == "staff_scheduling":
            return self._generate_staff_recommendation(baseline_data, context)
        elif query_type == "cost_analysis":
            return self._generate_cost_recommendation(baseline_data, context)
        else:
            return "根据行业数据，建议您持续关注关键运营指标，并与行业平均水平进行对比。"

    def _generate_traffic_recommendation(
        self, baseline_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """生成客流预测建议"""
        day_type = context.get("day_type", "工作日")
        meal_period = context.get("meal_period", "午餐")

        traffic_data = baseline_data.get("traffic", {}).get(day_type, {}).get(meal_period, {})

        if traffic_data:
            avg_traffic = traffic_data.get("平均客流", 0)
            std_dev = traffic_data.get("标准差", 0)

            return (
                f"根据行业数据，{day_type}{meal_period}时段的平均客流为{avg_traffic}人，"
                f"正常波动范围在{avg_traffic - std_dev:.0f}-{avg_traffic + std_dev:.0f}人之间。"
                f"建议您按此标准准备食材和安排人员。"
            )

        return "暂无相关时段的行业数据。"

    def _generate_inventory_recommendation(
        self, baseline_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """生成库存规划建议"""
        turnover_data = baseline_data.get("inventory_turnover", {})

        recommendations = []
        for category, data in turnover_data.items():
            avg_days = data.get("平均", 0)
            recommendations.append(f"{category}建议{avg_days:.1f}天周转一次")

        return "根据行业标准，" + "；".join(recommendations) + "。"

    def _generate_staff_recommendation(
        self, baseline_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """生成人员配置建议"""
        staff_data = baseline_data.get("staff", {})
        area = context.get("area", 100)  # 默认100平米

        front_staff = staff_data.get("前厅", {}).get("平均", 0) * (area / 100)
        kitchen_staff = staff_data.get("后厨", {}).get("平均", 0) * (area / 100)

        return (
            f"根据您的餐厅面积（{area}平米），建议配置前厅人员{front_staff:.0f}人，"
            f"后厨人员{kitchen_staff:.0f}人。"
        )

    def _generate_cost_recommendation(
        self, baseline_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """生成成本分析建议"""
        labor_cost = baseline_data.get("labor_cost", {}).get("平均", 0)
        food_cost = baseline_data.get("food_cost", {}).get("平均", 0)

        return (
            f"根据行业标准，{self.restaurant_type}的人力成本占比应控制在{labor_cost:.1f}%左右，"
            f"食材成本占比应控制在{food_cost:.1f}%左右。建议您定期对比实际成本与行业标准。"
        )
