"""
门店对标分析服务
提供同城同类型门店的横向对比分析
"""
from typing import Dict, List, Optional, Any
from datetime import date, datetime, timedelta
import structlog
import numpy as np

from src.services.base_service import BaseService

logger = structlog.get_logger()


class BenchmarkService(BaseService):
    """
    门店对标分析服务

    帮助门店了解自己在行业中的位置，学习最佳实践
    """

    def __init__(self, store_id: Optional[str] = None):
        super().__init__(store_id)

    async def get_benchmark_report(
        self,
        start_date: date,
        end_date: date,
        dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        获取对标报告

        Args:
            start_date: 开始日期
            end_date: 结束日期
            dimensions: 对标维度列表

        Returns:
            对标报告
        """
        store_id = self.require_store_id()

        # 默认对标维度
        if not dimensions:
            dimensions = [
                "sales",  # 销售额
                "customer_count",  # 客流量
                "average_spend",  # 客单价
                "table_turnover",  # 翻台率
                "labor_cost_ratio",  # 人力成本占比
                "food_cost_ratio",  # 食材成本占比
                "profit_margin",  # 毛利率
                "customer_satisfaction",  # 客户满意度
            ]

        # 1. 获取本门店数据
        own_metrics = await self._get_store_metrics(store_id, start_date, end_date)

        # 2. 获取对标门店数据
        benchmark_stores = await self._get_benchmark_stores(store_id)
        benchmark_metrics = await self._get_benchmark_metrics(
            benchmark_stores,
            start_date,
            end_date
        )

        # 3. 计算排名和分位数
        rankings = self._calculate_rankings(own_metrics, benchmark_metrics, dimensions)

        # 4. 识别优势和劣势
        strengths, weaknesses = self._identify_strengths_weaknesses(rankings)

        # 5. 生成改进建议
        recommendations = self._generate_recommendations(weaknesses, benchmark_metrics)

        # 6. 识别最佳实践
        best_practices = self._identify_best_practices(benchmark_metrics)

        report = {
            "store_id": store_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "own_metrics": own_metrics,
            "benchmark_summary": {
                "total_stores": len(benchmark_stores),
                "city": own_metrics.get("city", "未知"),
                "restaurant_type": own_metrics.get("restaurant_type", "正餐"),
            },
            "rankings": rankings,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
            "best_practices": best_practices,
            "generated_at": datetime.now().isoformat(),
        }

        logger.info(
            "Benchmark report generated",
            store_id=store_id,
            benchmark_stores=len(benchmark_stores),
        )

        return report

    async def _get_store_metrics(
        self,
        store_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        获取门店指标数据

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            指标数据
        """
        # TODO: 从数据库查询实际数据
        # 这里返回模拟数据

        days = (end_date - start_date).days + 1

        metrics = {
            "store_id": store_id,
            "city": "长沙",
            "restaurant_type": "正餐",
            "area": 200,  # 面积（平米）
            "sales": 850000,  # 总销售额
            "customer_count": 2800,  # 总客流量
            "average_spend": 304,  # 客单价
            "table_turnover": 2.8,  # 翻台率
            "labor_cost_ratio": 28.5,  # 人力成本占比（%）
            "food_cost_ratio": 38.2,  # 食材成本占比（%）
            "profit_margin": 33.3,  # 毛利率（%）
            "customer_satisfaction": 4.2,  # 客户满意度（1-5）
            "days": days,
        }

        return metrics

    async def _get_benchmark_stores(self, store_id: str) -> List[str]:
        """
        获取对标门店列表

        筛选条件：
        1. 同城
        2. 同类型
        3. 相似规模（面积差异<30%）

        Args:
            store_id: 本门店ID

        Returns:
            对标门店ID列表
        """
        # TODO: 从数据库查询实际数据
        # 这里返回模拟数据

        benchmark_stores = [
            "STORE002",
            "STORE003",
            "STORE004",
            "STORE005",
            "STORE006",
            "STORE007",
            "STORE008",
            "STORE009",
            "STORE010",
        ]

        return benchmark_stores

    async def _get_benchmark_metrics(
        self,
        store_ids: List[str],
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        获取对标门店的指标数据

        Args:
            store_ids: 门店ID列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            指标数据列表
        """
        # TODO: 从数据库查询实际数据
        # 这里返回模拟数据

        metrics_list = []

        for store_id in store_ids:
            # 生成随机但合理的指标数据
            metrics = {
                "store_id": store_id,
                "sales": np.random.randint(700000, 1200000),
                "customer_count": np.random.randint(2000, 4000),
                "average_spend": np.random.randint(250, 400),
                "table_turnover": round(np.random.uniform(2.0, 3.5), 1),
                "labor_cost_ratio": round(np.random.uniform(25.0, 32.0), 1),
                "food_cost_ratio": round(np.random.uniform(35.0, 42.0), 1),
                "profit_margin": round(np.random.uniform(28.0, 38.0), 1),
                "customer_satisfaction": round(np.random.uniform(3.8, 4.5), 1),
            }
            metrics_list.append(metrics)

        return metrics_list

    def _calculate_rankings(
        self,
        own_metrics: Dict[str, Any],
        benchmark_metrics: List[Dict[str, Any]],
        dimensions: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        计算排名和分位数

        Args:
            own_metrics: 本门店指标
            benchmark_metrics: 对标门店指标列表
            dimensions: 对标维度

        Returns:
            排名信息
        """
        rankings = {}

        for dimension in dimensions:
            # 收集所有门店的该维度数据
            all_values = [m[dimension] for m in benchmark_metrics if dimension in m]
            own_value = own_metrics.get(dimension)

            if own_value is None or not all_values:
                continue

            # 添加本门店数据
            all_values.append(own_value)
            all_values.sort(reverse=True)  # 降序排列（值越大越好）

            # 计算排名
            rank = all_values.index(own_value) + 1
            total = len(all_values)

            # 计算分位数
            percentile = (total - rank + 1) / total * 100

            # 计算统计信息
            mean = np.mean(all_values)
            median = np.median(all_values)
            std = np.std(all_values)

            # 判断是否高于/低于平均值
            vs_mean = ((own_value - mean) / mean * 100) if mean > 0 else 0

            rankings[dimension] = {
                "value": own_value,
                "rank": rank,
                "total": total,
                "percentile": round(percentile, 1),
                "mean": round(mean, 2),
                "median": round(median, 2),
                "std": round(std, 2),
                "vs_mean": round(vs_mean, 1),  # 与平均值的差异（%）
                "level": self._get_performance_level(percentile),
            }

        return rankings

    def _get_performance_level(self, percentile: float) -> str:
        """
        根据分位数判断表现水平

        Args:
            percentile: 分位数（0-100）

        Returns:
            表现水平
        """
        if percentile >= 90:
            return "优秀"
        elif percentile >= 75:
            return "良好"
        elif percentile >= 50:
            return "中等"
        elif percentile >= 25:
            return "待提升"
        else:
            return "需改进"

    def _identify_strengths_weaknesses(
        self,
        rankings: Dict[str, Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        识别优势和劣势

        Args:
            rankings: 排名信息

        Returns:
            (优势列表, 劣势列表)
        """
        strengths = []
        weaknesses = []

        for dimension, data in rankings.items():
            percentile = data["percentile"]

            if percentile >= 75:
                # 优势：排名前25%
                strengths.append({
                    "dimension": dimension,
                    "dimension_name": self._get_dimension_name(dimension),
                    "percentile": percentile,
                    "level": data["level"],
                    "vs_mean": data["vs_mean"],
                })
            elif percentile < 50:
                # 劣势：排名后50%
                weaknesses.append({
                    "dimension": dimension,
                    "dimension_name": self._get_dimension_name(dimension),
                    "percentile": percentile,
                    "level": data["level"],
                    "vs_mean": data["vs_mean"],
                })

        # 按分位数排序
        strengths.sort(key=lambda x: x["percentile"], reverse=True)
        weaknesses.sort(key=lambda x: x["percentile"])

        return strengths, weaknesses

    def _get_dimension_name(self, dimension: str) -> str:
        """获取维度的中文名称"""
        names = {
            "sales": "销售额",
            "customer_count": "客流量",
            "average_spend": "客单价",
            "table_turnover": "翻台率",
            "labor_cost_ratio": "人力成本占比",
            "food_cost_ratio": "食材成本占比",
            "profit_margin": "毛利率",
            "customer_satisfaction": "客户满意度",
        }
        return names.get(dimension, dimension)

    def _generate_recommendations(
        self,
        weaknesses: List[Dict[str, Any]],
        benchmark_metrics: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        生成改进建议

        Args:
            weaknesses: 劣势列表
            benchmark_metrics: 对标门店指标

        Returns:
            建议列表
        """
        recommendations = []

        for weakness in weaknesses[:3]:  # 只针对前3个劣势
            dimension = weakness["dimension"]
            dimension_name = weakness["dimension_name"]

            # 根据不同维度生成针对性建议
            if dimension == "sales":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"销售额低于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 增加营销活动频次；2) 优化菜品结构，推出高毛利菜品；3) 延长营业时间",
                    "priority": "高",
                })
            elif dimension == "customer_count":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"客流量低于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 加强线上推广（美团、大众点评）；2) 推出引流活动；3) 优化门店外观和招牌",
                    "priority": "高",
                })
            elif dimension == "average_spend":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"客单价低于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 推出套餐和组合优惠；2) 培训服务员推荐技巧；3) 增加高价值菜品",
                    "priority": "中",
                })
            elif dimension == "table_turnover":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"翻台率低于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 优化上菜速度；2) 提高服务效率；3) 合理引导客户用餐时长",
                    "priority": "中",
                })
            elif dimension == "labor_cost_ratio":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"人力成本占比高于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 优化排班，提高人效；2) 引入自助点餐系统；3) 培训多技能员工",
                    "priority": "高",
                })
            elif dimension == "food_cost_ratio":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"食材成本占比高于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 优化采购渠道；2) 减少食材浪费；3) 调整菜品配方",
                    "priority": "高",
                })
            elif dimension == "profit_margin":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"毛利率低于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 提高客单价；2) 降低成本；3) 优化菜品结构",
                    "priority": "高",
                })
            elif dimension == "customer_satisfaction":
                recommendations.append({
                    "dimension": dimension_name,
                    "issue": f"客户满意度低于平均水平{abs(weakness['vs_mean']):.1f}%",
                    "recommendation": "建议：1) 加强服务培训；2) 提升菜品质量；3) 改善就餐环境",
                    "priority": "高",
                })

        return recommendations

    def _identify_best_practices(
        self,
        benchmark_metrics: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        识别最佳实践

        找出表现最好的门店及其特点

        Args:
            benchmark_metrics: 对标门店指标

        Returns:
            最佳实践列表
        """
        best_practices = []

        # 找出销售额最高的门店
        top_sales_store = max(benchmark_metrics, key=lambda x: x.get("sales", 0))
        best_practices.append({
            "category": "销售冠军",
            "store_id": top_sales_store["store_id"],
            "highlight": f"月销售额{top_sales_store['sales']/10000:.1f}万元",
            "practice": "该门店通过精准营销和优质服务，实现了高销售额",
        })

        # 找出客单价最高的门店
        top_spend_store = max(benchmark_metrics, key=lambda x: x.get("average_spend", 0))
        best_practices.append({
            "category": "客单价标杆",
            "store_id": top_spend_store["store_id"],
            "highlight": f"客单价{top_spend_store['average_spend']}元",
            "practice": "该门店通过菜品组合和服务员推荐，有效提升客单价",
        })

        # 找出毛利率最高的门店
        top_margin_store = max(benchmark_metrics, key=lambda x: x.get("profit_margin", 0))
        best_practices.append({
            "category": "盈利能力标杆",
            "store_id": top_margin_store["store_id"],
            "highlight": f"毛利率{top_margin_store['profit_margin']}%",
            "practice": "该门店通过成本控制和菜品优化，实现了高毛利率",
        })

        return best_practices
