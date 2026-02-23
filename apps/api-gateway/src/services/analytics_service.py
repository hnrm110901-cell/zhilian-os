"""
高级分析服务
提供预测分析、异常检测、关联分析等功能
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from collections import defaultdict
import structlog
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from src.models import Order, OrderItem, InventoryItem, FinancialTransaction, Store
from src.core.exceptions import NotFoundError, ValidationError

logger = structlog.get_logger()


class AnalyticsService:
    """高级分析服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def predict_sales(
        self, store_id: str, days_ahead: int = 7
    ) -> Dict[str, Any]:
        """销售预测 - 基于历史数据预测未来销售"""
        # 获取过去N天的销售数据
        end_date = date.today()
        start_date = end_date - timedelta(days=int(os.getenv("ANALYTICS_HISTORY_DAYS", "30")))

        query = select(
            func.date(FinancialTransaction.transaction_date).label("date"),
            func.sum(FinancialTransaction.amount).label("revenue"),
            func.count(FinancialTransaction.id).label("transactions")
        ).where(
            and_(
                FinancialTransaction.store_id == store_id,
                FinancialTransaction.transaction_date >= start_date,
                FinancialTransaction.transaction_date <= end_date,
                FinancialTransaction.transaction_type == "income",
                FinancialTransaction.category == "sales"
            )
        ).group_by(func.date(FinancialTransaction.transaction_date))

        result = await self.db.execute(query)
        historical_data = result.all()

        if not historical_data:
            return {
                "store_id": store_id,
                "predictions": [],
                "confidence": "low",
                "message": "历史数据不足，无法进行预测"
            }

        # 简单的移动平均预测
        # 计算最近7天的平均值
        recent_data = historical_data[-7:] if len(historical_data) >= 7 else historical_data
        avg_revenue = sum(d.revenue for d in recent_data) / len(recent_data)
        avg_transactions = sum(d.transactions for d in recent_data) / len(recent_data)

        # 计算趋势（简单线性趋势）
        if len(historical_data) >= 7:
            first_week_avg = sum(d.revenue for d in historical_data[:7]) / 7
            last_week_avg = sum(d.revenue for d in historical_data[-7:]) / 7
            trend = (last_week_avg - first_week_avg) / first_week_avg if first_week_avg > 0 else 0
        else:
            trend = 0

        # 从历史数据计算实际周末效应系数
        weekend_revs = [
            d.revenue for d in historical_data
            if date.fromisoformat(str(d.date)).weekday() in [5, 6]
        ]
        weekday_revs = [
            d.revenue for d in historical_data
            if date.fromisoformat(str(d.date)).weekday() not in [5, 6]
        ]
        if weekend_revs and weekday_revs:
            avg_wkend = sum(weekend_revs) / len(weekend_revs)
            avg_wkday = sum(weekday_revs) / len(weekday_revs)
            _default_wkend = float(os.getenv("ANALYTICS_DEFAULT_WEEKEND_FACTOR", "1.2"))
            computed_weekend_factor = round(avg_wkend / avg_wkday, 2) if avg_wkday > 0 else _default_wkend
        else:
            computed_weekend_factor = float(os.getenv("ANALYTICS_DEFAULT_WEEKEND_FACTOR", "1.2"))

        # 生成预测
        predictions = []
        for i in range(1, days_ahead + 1):
            pred_date = end_date + timedelta(days=i)

            # 考虑周末效应（基于历史实际数据）
            weekday = pred_date.weekday()
            weekend_factor = computed_weekend_factor if weekday in [5, 6] else 1.0

            # 应用趋势和周末因素
            predicted_revenue = int(avg_revenue * (1 + trend * i / 30) * weekend_factor)
            predicted_transactions = int(avg_transactions * (1 + trend * i / 30) * weekend_factor)

            predictions.append({
                "date": pred_date.isoformat(),
                "predicted_revenue": predicted_revenue,
                "predicted_transactions": predicted_transactions,
                "confidence": "medium" if i <= 3 else "low",
                "is_weekend": weekday in [5, 6]
            })

        return {
            "store_id": store_id,
            "generated_at": datetime.now().isoformat(),
            "historical_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": len(historical_data)
            },
            "predictions": predictions,
            "trend": round(trend * 100, 2),  # 百分比
            "average_daily_revenue": int(avg_revenue),
        }

    async def detect_anomalies(
        self, store_id: str, metric: str = "revenue", days: int = int(os.getenv("ANALYTICS_ANOMALY_DAYS", "30"))
    ) -> Dict[str, Any]:
        """异常检测 - 检测销售、成本等指标的异常"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # 根据指标类型查询数据
        if metric == "revenue":
            query = select(
                func.date(FinancialTransaction.transaction_date).label("date"),
                func.sum(FinancialTransaction.amount).label("value")
            ).where(
                and_(
                    FinancialTransaction.store_id == store_id,
                    FinancialTransaction.transaction_date >= start_date,
                    FinancialTransaction.transaction_date <= end_date,
                    FinancialTransaction.transaction_type == "income"
                )
            ).group_by(func.date(FinancialTransaction.transaction_date))
        elif metric == "cost":
            query = select(
                func.date(FinancialTransaction.transaction_date).label("date"),
                func.sum(FinancialTransaction.amount).label("value")
            ).where(
                and_(
                    FinancialTransaction.store_id == store_id,
                    FinancialTransaction.transaction_date >= start_date,
                    FinancialTransaction.transaction_date <= end_date,
                    FinancialTransaction.transaction_type == "expense"
                )
            ).group_by(func.date(FinancialTransaction.transaction_date))
        else:
            raise ValidationError(f"不支持的指标类型: {metric}")

        result = await self.db.execute(query)
        data_points = result.all()

        if len(data_points) < 7:
            return {
                "store_id": store_id,
                "metric": metric,
                "anomalies": [],
                "message": "数据不足，无法进行异常检测"
            }

        # 计算统计指标
        values = [d.value for d in data_points]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance ** 0.5

        # 使用3-sigma规则检测异常
        threshold_upper = mean + 3 * std_dev
        threshold_lower = mean - 3 * std_dev

        anomalies = []
        for data_point in data_points:
            if data_point.value > threshold_upper:
                anomalies.append({
                    "date": data_point.date.isoformat(),
                    "value": data_point.value,
                    "expected_range": [int(threshold_lower), int(threshold_upper)],
                    "deviation": round((data_point.value - mean) / std_dev, 2),
                    "type": "high",
                    "severity": "high" if data_point.value > mean + 4 * std_dev else "medium"
                })
            elif data_point.value < threshold_lower:
                anomalies.append({
                    "date": data_point.date.isoformat(),
                    "value": data_point.value,
                    "expected_range": [int(threshold_lower), int(threshold_upper)],
                    "deviation": round((data_point.value - mean) / std_dev, 2),
                    "type": "low",
                    "severity": "high" if data_point.value < mean - 4 * std_dev else "medium"
                })

        return {
            "store_id": store_id,
            "metric": metric,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "statistics": {
                "mean": int(mean),
                "std_dev": int(std_dev),
                "threshold_upper": int(threshold_upper),
                "threshold_lower": int(threshold_lower)
            },
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "anomaly_rate": round(len(anomalies) / len(data_points) * 100, 2)
        }

    async def analyze_associations(
        self, store_id: str, min_support: float = float(os.getenv("ANALYTICS_MIN_SUPPORT", "0.1"))
    ) -> Dict[str, Any]:
        """关联分析 - 分析菜品之间的关联关系"""
        # 获取最近N天的订单数据
        end_date = date.today()
        start_date = end_date - timedelta(days=int(os.getenv("ANALYTICS_HISTORY_DAYS", "30")))

        # 查询订单及其商品
        query = select(Order).where(
            and_(
                Order.store_id == store_id,
                Order.created_at >= datetime.combine(start_date, datetime.min.time()),
                Order.created_at <= datetime.combine(end_date, datetime.max.time()),
                Order.status == "completed"
            )
        )

        result = await self.db.execute(query)
        orders = result.scalars().all()

        if len(orders) < 10:
            return {
                "store_id": store_id,
                "associations": [],
                "message": "订单数据不足，无法进行关联分析"
            }

        # 构建商品共现矩阵
        item_counts = defaultdict(int)
        pair_counts = defaultdict(int)
        total_orders = len(orders)

        for order in orders:
            if not order.items:
                continue

            items = [item.get("name", "") for item in order.items if item.get("name")]

            # 统计单个商品出现次数
            for item in items:
                item_counts[item] += 1

            # 统计商品对出现次数
            for i, item1 in enumerate(items):
                for item2 in items[i + 1:]:
                    pair = tuple(sorted([item1, item2]))
                    pair_counts[pair] += 1

        # 计算关联规则
        associations = []
        for (item1, item2), count in pair_counts.items():
            support = count / total_orders
            if support < min_support:
                continue

            # 计算置信度
            confidence_1_to_2 = count / item_counts[item1] if item_counts[item1] > 0 else 0
            confidence_2_to_1 = count / item_counts[item2] if item_counts[item2] > 0 else 0

            # 计算提升度
            expected = (item_counts[item1] / total_orders) * (item_counts[item2] / total_orders)
            lift = support / expected if expected > 0 else 0

            associations.append({
                "item1": item1,
                "item2": item2,
                "support": round(support, 3),
                "confidence_1_to_2": round(confidence_1_to_2, 3),
                "confidence_2_to_1": round(confidence_2_to_1, 3),
                "lift": round(lift, 2),
                "count": count,
                "strength": "strong" if lift > float(os.getenv("ANALYTICS_LIFT_STRONG", "1.5")) else "moderate" if lift > float(os.getenv("ANALYTICS_LIFT_MODERATE", "1.0")) else "weak"
            })

        # 按提升度排序
        associations.sort(key=lambda x: x["lift"], reverse=True)

        return {
            "store_id": store_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "total_orders": total_orders,
            "unique_items": len(item_counts),
            "associations": associations[:20],  # 返回前20个最强关联
            "min_support": min_support
        }

    async def analyze_time_patterns(
        self, store_id: str, days: int = 30
    ) -> Dict[str, Any]:
        """时段分析 - 分析不同时段的销售模式"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # 查询交易数据
        query = select(
            func.extract('hour', FinancialTransaction.created_at).label("hour"),
            func.extract('dow', FinancialTransaction.created_at).label("day_of_week"),
            func.sum(FinancialTransaction.amount).label("revenue"),
            func.count(FinancialTransaction.id).label("transactions")
        ).where(
            and_(
                FinancialTransaction.store_id == store_id,
                FinancialTransaction.transaction_date >= start_date,
                FinancialTransaction.transaction_date <= end_date,
                FinancialTransaction.transaction_type == "income"
            )
        ).group_by(
            func.extract('hour', FinancialTransaction.created_at),
            func.extract('dow', FinancialTransaction.created_at)
        )

        result = await self.db.execute(query)
        data_points = result.all()

        # 按小时汇总
        hourly_stats = defaultdict(lambda: {"revenue": 0, "transactions": 0, "count": 0})
        for dp in data_points:
            hour = int(dp.hour)
            hourly_stats[hour]["revenue"] += dp.revenue
            hourly_stats[hour]["transactions"] += dp.transactions
            hourly_stats[hour]["count"] += 1

        # 计算每小时平均值
        hourly_analysis = []
        for hour in range(24):
            if hour in hourly_stats:
                stats = hourly_stats[hour]
                avg_revenue = stats["revenue"] / stats["count"]
                avg_transactions = stats["transactions"] / stats["count"]

                # 判断时段类型
                if 6 <= hour < 11:
                    period = "早餐"
                elif 11 <= hour < 14:
                    period = "午餐"
                elif 14 <= hour < 17:
                    period = "下午茶"
                elif 17 <= hour < 21:
                    period = "晚餐"
                else:
                    period = "其他"

                hourly_analysis.append({
                    "hour": hour,
                    "period": period,
                    "avg_revenue": int(avg_revenue),
                    "avg_transactions": int(avg_transactions),
                    "total_days": stats["count"]
                })

        # 找出高峰时段
        if hourly_analysis:
            sorted_by_revenue = sorted(hourly_analysis, key=lambda x: x["avg_revenue"], reverse=True)
            peak_hours = sorted_by_revenue[:3]
        else:
            peak_hours = []

        return {
            "store_id": store_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "hourly_analysis": hourly_analysis,
            "peak_hours": peak_hours,
            "insights": self._generate_time_insights(hourly_analysis)
        }

    def _generate_time_insights(self, hourly_analysis: List[Dict]) -> List[str]:
        """生成时段分析洞察"""
        insights = []

        if not hourly_analysis:
            return ["数据不足，无法生成洞察"]

        # 找出最忙和最闲的时段
        sorted_by_revenue = sorted(hourly_analysis, key=lambda x: x["avg_revenue"], reverse=True)

        if sorted_by_revenue:
            busiest = sorted_by_revenue[0]
            insights.append(f"最繁忙时段: {busiest['hour']}:00 ({busiest['period']})")

            quietest = sorted_by_revenue[-1]
            insights.append(f"最清闲时段: {quietest['hour']}:00 ({quietest['period']})")

        # 分析午餐和晚餐时段
        lunch_hours = [h for h in hourly_analysis if h["period"] == "午餐"]
        dinner_hours = [h for h in hourly_analysis if h["period"] == "晚餐"]

        if lunch_hours and dinner_hours:
            lunch_revenue = sum(h["avg_revenue"] for h in lunch_hours)
            dinner_revenue = sum(h["avg_revenue"] for h in dinner_hours)
            _meal_diff = float(os.getenv("ANALYTICS_MEAL_DIFF_THRESHOLD", "1.2"))

            if dinner_revenue > lunch_revenue * _meal_diff:
                insights.append("晚餐时段营收显著高于午餐，建议增加晚餐时段人员配置")
            elif lunch_revenue > dinner_revenue * _meal_diff:
                insights.append("午餐时段营收显著高于晚餐，建议优化午餐时段服务")

        return insights


# 全局服务实例
def get_analytics_service(db: AsyncSession) -> AnalyticsService:
    """获取分析服务实例"""
    return AnalyticsService(db)
