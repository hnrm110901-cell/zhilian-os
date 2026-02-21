"""
智能库存预警Agent - Intelligent Inventory Alert Agent

核心功能 Core Features:
1. 实时库存监控 - Real-time inventory monitoring
2. 消耗预测 - Consumption prediction
3. 智能补货提醒 - Intelligent restocking alerts
4. 保质期管理 - Expiration management
5. 多级预警 - Multi-level alerts
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from enum import Enum
from typing import TypedDict, List, Optional, Dict, Any
from statistics import mean, stdev
import sys
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()


class AlertLevel(str, Enum):
    """预警级别 Alert Level"""
    INFO = "info"  # 信息提示
    WARNING = "warning"  # 警告
    URGENT = "urgent"  # 紧急
    CRITICAL = "critical"  # 严重


class InventoryStatus(str, Enum):
    """库存状态 Inventory Status"""
    SUFFICIENT = "sufficient"  # 充足
    LOW = "low"  # 偏低
    CRITICAL = "critical"  # 严重不足
    OUT_OF_STOCK = "out_of_stock"  # 缺货
    EXPIRING_SOON = "expiring_soon"  # 即将过期


class PredictionMethod(str, Enum):
    """预测方法 Prediction Method"""
    MOVING_AVERAGE = "moving_average"  # 移动平均
    WEIGHTED_AVERAGE = "weighted_average"  # 加权平均
    LINEAR_REGRESSION = "linear_regression"  # 线性回归
    SEASONAL = "seasonal"  # 季节性预测


class InventoryItem(TypedDict):
    """库存项目 Inventory Item"""
    item_id: str  # 物料ID
    item_name: str  # 物料名称
    category: str  # 分类
    unit: str  # 单位
    current_stock: float  # 当前库存
    safe_stock: float  # 安全库存
    min_stock: float  # 最低库存
    max_stock: float  # 最高库存
    unit_cost: int  # 单位成本(分)
    supplier_id: Optional[str]  # 供应商ID
    lead_time_days: int  # 采购周期(天)
    expiration_date: Optional[str]  # 保质期(ISO格式)
    location: str  # 存放位置


class ConsumptionRecord(TypedDict):
    """消耗记录 Consumption Record"""
    date: str  # 日期(ISO格式)
    item_id: str  # 物料ID
    quantity: float  # 消耗数量
    reason: str  # 消耗原因(sales/waste/transfer)


class RestockAlert(TypedDict):
    """补货提醒 Restock Alert"""
    alert_id: str  # 提醒ID
    item_id: str  # 物料ID
    item_name: str  # 物料名称
    current_stock: float  # 当前库存
    recommended_quantity: float  # 建议补货数量
    alert_level: AlertLevel  # 预警级别
    reason: str  # 原因
    estimated_stockout_date: Optional[str]  # 预计缺货日期
    created_at: str  # 创建时间


class ExpirationAlert(TypedDict):
    """保质期预警 Expiration Alert"""
    alert_id: str  # 提醒ID
    item_id: str  # 物料ID
    item_name: str  # 物料名称
    current_stock: float  # 当前库存
    expiration_date: str  # 过期日期
    days_until_expiration: int  # 距离过期天数
    alert_level: AlertLevel  # 预警级别
    recommended_action: str  # 建议操作
    created_at: str  # 创建时间


class PredictionResult(TypedDict):
    """预测结果 Prediction Result"""
    item_id: str  # 物料ID
    prediction_date: str  # 预测日期
    predicted_consumption: float  # 预测消耗量
    confidence: float  # 置信度(0-1)
    method: PredictionMethod  # 预测方法
    days_until_stockout: Optional[int]  # 预计缺货天数


class InventoryAgent(BaseAgent):
    """
    智能库存预警Agent

    工作流程 Workflow:
    1. monitor_inventory() - 监控库存状态
    2. predict_consumption() - 预测消耗趋势
    3. generate_restock_alerts() - 生成补货提醒
    4. check_expiration() - 检查保质期
    5. optimize_stock_levels() - 优化库存水平
    """

    def __init__(
        self,
        store_id: str,
        pinzhi_adapter: Optional[Any] = None,
        alert_thresholds: Optional[Dict[str, float]] = None
    ):
        """
        初始化库存预警Agent

        Args:
            store_id: 门店ID
            pinzhi_adapter: 品智收银适配器
            alert_thresholds: 预警阈值配置
        """
        super().__init__()
        self.store_id = store_id
        self.pinzhi_adapter = pinzhi_adapter
        self.alert_thresholds = alert_thresholds or {
            "low_stock_ratio": 0.3,  # 低库存比例(当前/安全库存)
            "critical_stock_ratio": 0.1,  # 严重不足比例
            "expiring_soon_days": 7,  # 即将过期天数
            "expiring_urgent_days": 3,  # 紧急过期天数
        }
        self.logger = logger.bind(agent="inventory", store_id=store_id)

    def get_supported_actions(self) -> List[str]:
        """获取支持的操作列表"""
        return [
            "monitor_inventory", "predict_consumption", "generate_restock_alerts",
            "check_expiration", "optimize_stock_levels", "get_inventory_report"
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """
        执行Agent操作

        Args:
            action: 操作名称
            params: 操作参数

        Returns:
            AgentResponse: 统一的响应格式
        """
        try:
            if action == "monitor_inventory":
                result = await self.monitor_inventory(
                    category=params.get("category")
                )
                return AgentResponse(success=True, data=result)
            elif action == "predict_consumption":
                result = await self.predict_consumption(
                    item_id=params["item_id"],
                    history_days=params.get("history_days", 30),
                    forecast_days=params.get("forecast_days", 7),
                    method=params.get("method", PredictionMethod.WEIGHTED_AVERAGE)
                )
                return AgentResponse(success=True, data=result)
            elif action == "generate_restock_alerts":
                result = await self.generate_restock_alerts(
                    category=params.get("category")
                )
                return AgentResponse(success=True, data=result)
            elif action == "check_expiration":
                result = await self.check_expiration(
                    category=params.get("category")
                )
                return AgentResponse(success=True, data=result)
            elif action == "optimize_stock_levels":
                result = await self.optimize_stock_levels(
                    item_id=params["item_id"],
                    analysis_days=params.get("analysis_days", 90)
                )
                return AgentResponse(success=True, data=result)
            elif action == "get_inventory_report":
                result = await self.get_inventory_report(
                    category=params.get("category")
                )
                return AgentResponse(success=True, data=result)
            else:
                return AgentResponse(
                    success=False,
                    data=None,
                    error=f"Unsupported action: {action}"
                )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                error=str(e)
            )

    async def monitor_inventory(
        self,
        category: Optional[str] = None
    ) -> List[InventoryItem]:
        """
        监控库存状态

        Args:
            category: 物料分类(可选)

        Returns:
            库存项目列表
        """
        self.logger.info("monitoring_inventory", category=category)

        try:
            # 从品智系统获取库存数据
            if self.pinzhi_adapter:
                inventory_data = await self.pinzhi_adapter.get_inventory(
                    store_id=self.store_id,
                    category=category
                )
            else:
                # 模拟数据
                inventory_data = self._generate_mock_inventory(category)

            # 分析库存状态
            analyzed_items = []
            for item in inventory_data:
                status = self._analyze_inventory_status(item)
                item["status"] = status
                analyzed_items.append(item)

            self.logger.info(
                "inventory_monitored",
                total_items=len(analyzed_items),
                category=category
            )

            return analyzed_items

        except Exception as e:
            self.logger.error("monitor_inventory_failed", error=str(e))
            raise

    def _analyze_inventory_status(self, item: InventoryItem) -> InventoryStatus:
        """分析库存状态"""
        current = item["current_stock"]
        safe = item["safe_stock"]
        min_stock = item["min_stock"]

        if current <= 0:
            return InventoryStatus.OUT_OF_STOCK
        elif current <= min_stock:
            return InventoryStatus.CRITICAL
        elif current <= safe * self.alert_thresholds["low_stock_ratio"]:
            return InventoryStatus.LOW
        else:
            return InventoryStatus.SUFFICIENT

    async def predict_consumption(
        self,
        item_id: str,
        history_days: int = 30,
        forecast_days: int = 7,
        method: PredictionMethod = PredictionMethod.WEIGHTED_AVERAGE
    ) -> PredictionResult:
        """
        预测物料消耗趋势

        Args:
            item_id: 物料ID
            history_days: 历史数据天数
            forecast_days: 预测天数
            method: 预测方法

        Returns:
            预测结果
        """
        self.logger.info(
            "predicting_consumption",
            item_id=item_id,
            history_days=history_days,
            forecast_days=forecast_days,
            method=method
        )

        try:
            # 获取历史消耗数据
            consumption_history = await self._get_consumption_history(
                item_id=item_id,
                days=history_days
            )

            # 根据方法进行预测
            if method == PredictionMethod.MOVING_AVERAGE:
                predicted = self._predict_moving_average(consumption_history, forecast_days)
            elif method == PredictionMethod.WEIGHTED_AVERAGE:
                predicted = self._predict_weighted_average(consumption_history, forecast_days)
            elif method == PredictionMethod.LINEAR_REGRESSION:
                predicted = self._predict_linear_regression(consumption_history, forecast_days)
            else:
                predicted = self._predict_seasonal(consumption_history, forecast_days)

            # 计算置信度
            confidence = self._calculate_confidence(consumption_history)

            # 获取当前库存
            inventory = await self.monitor_inventory()
            current_item = next((i for i in inventory if i["item_id"] == item_id), None)

            # 计算预计缺货天数
            days_until_stockout = None
            if current_item and predicted > 0:
                days_until_stockout = int(current_item["current_stock"] / predicted)

            result: PredictionResult = {
                "item_id": item_id,
                "prediction_date": datetime.now().isoformat(),
                "predicted_consumption": predicted,
                "confidence": confidence,
                "method": method,
                "days_until_stockout": days_until_stockout
            }

            self.logger.info(
                "consumption_predicted",
                item_id=item_id,
                predicted=predicted,
                confidence=confidence,
                days_until_stockout=days_until_stockout
            )

            return result

        except Exception as e:
            self.logger.error("predict_consumption_failed", error=str(e), item_id=item_id)
            raise

    async def _get_consumption_history(
        self,
        item_id: str,
        days: int
    ) -> List[ConsumptionRecord]:
        """获取历史消耗数据"""
        # 模拟历史数据
        history = []
        base_consumption = 10.0

        for i in range(days):
            date = (datetime.now() - timedelta(days=days-i)).date().isoformat()
            # 添加随机波动
            import random
            quantity = base_consumption + random.uniform(-3, 3)

            record: ConsumptionRecord = {
                "date": date,
                "item_id": item_id,
                "quantity": max(0, quantity),
                "reason": "sales"
            }
            history.append(record)

        return history

    def _predict_moving_average(
        self,
        history: List[ConsumptionRecord],
        forecast_days: int
    ) -> float:
        """移动平均预测"""
        if not history:
            return 0.0

        # 使用最近7天的平均值
        recent_days = min(7, len(history))
        recent_consumption = [h["quantity"] for h in history[-recent_days:]]
        daily_avg = mean(recent_consumption)

        return daily_avg * forecast_days

    def _predict_weighted_average(
        self,
        history: List[ConsumptionRecord],
        forecast_days: int
    ) -> float:
        """加权平均预测(近期权重更高)"""
        if not history:
            return 0.0

        # 使用指数加权
        weights = [0.5 ** i for i in range(len(history))]
        weights.reverse()  # 最近的权重最高

        weighted_sum = sum(h["quantity"] * w for h, w in zip(history, weights))
        weight_total = sum(weights)

        daily_avg = weighted_sum / weight_total if weight_total > 0 else 0

        return daily_avg * forecast_days

    def _predict_linear_regression(
        self,
        history: List[ConsumptionRecord],
        forecast_days: int
    ) -> float:
        """线性回归预测"""
        if len(history) < 2:
            return 0.0

        # 简单线性回归
        n = len(history)
        x = list(range(n))
        y = [h["quantity"] for h in history]

        x_mean = mean(x)
        y_mean = mean(y)

        # 计算斜率和截距
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return y_mean * forecast_days

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # 预测未来消耗
        future_x = n + forecast_days - 1
        predicted_daily = slope * future_x + intercept

        return max(0, predicted_daily * forecast_days)

    def _predict_seasonal(
        self,
        history: List[ConsumptionRecord],
        forecast_days: int
    ) -> float:
        """季节性预测(考虑周期性)"""
        if len(history) < 7:
            return self._predict_moving_average(history, forecast_days)

        # 按星期几分组
        weekday_consumption = {}
        for record in history:
            date = datetime.fromisoformat(record["date"])
            weekday = date.weekday()
            if weekday not in weekday_consumption:
                weekday_consumption[weekday] = []
            weekday_consumption[weekday].append(record["quantity"])

        # 计算每个星期几的平均消耗
        weekday_avg = {
            day: mean(quantities)
            for day, quantities in weekday_consumption.items()
        }

        # 预测未来几天
        total_predicted = 0.0
        current_date = datetime.now()

        for i in range(forecast_days):
            future_date = current_date + timedelta(days=i)
            weekday = future_date.weekday()
            daily_prediction = weekday_avg.get(weekday, mean(weekday_avg.values()))
            total_predicted += daily_prediction

        return total_predicted

    def _calculate_confidence(self, history: List[ConsumptionRecord]) -> float:
        """计算预测置信度"""
        if len(history) < 2:
            return 0.5

        quantities = [h["quantity"] for h in history]
        avg = mean(quantities)

        if avg == 0:
            return 0.5

        # 使用变异系数(CV)计算置信度
        std = stdev(quantities) if len(quantities) > 1 else 0
        cv = std / avg if avg > 0 else 1

        # CV越小,置信度越高
        confidence = max(0.0, min(1.0, 1 - cv))

        return confidence

    async def generate_restock_alerts(
        self,
        category: Optional[str] = None
    ) -> List[RestockAlert]:
        """
        生成补货提醒

        Args:
            category: 物料分类(可选)

        Returns:
            补货提醒列表
        """
        self.logger.info("generating_restock_alerts", category=category)

        try:
            # 获取库存数据
            inventory = await self.monitor_inventory(category=category)

            alerts = []
            for item in inventory:
                # 检查是否需要补货
                alert = await self._check_restock_needed(item)
                if alert:
                    alerts.append(alert)

            # 按预警级别排序
            alerts.sort(
                key=lambda x: ["info", "warning", "urgent", "critical"].index(x["alert_level"])
            )

            self.logger.info(
                "restock_alerts_generated",
                total_alerts=len(alerts),
                critical=sum(1 for a in alerts if a["alert_level"] == AlertLevel.CRITICAL),
                urgent=sum(1 for a in alerts if a["alert_level"] == AlertLevel.URGENT)
            )

            return alerts

        except Exception as e:
            self.logger.error("generate_restock_alerts_failed", error=str(e))
            raise

    async def _check_restock_needed(self, item: InventoryItem) -> Optional[RestockAlert]:
        """检查是否需要补货"""
        current = item["current_stock"]
        safe = item["safe_stock"]
        min_stock = item["min_stock"]

        # 判断预警级别
        alert_level = None
        reason = ""

        if current <= 0:
            alert_level = AlertLevel.CRITICAL
            reason = "缺货 Out of stock"
        elif current <= min_stock:
            alert_level = AlertLevel.CRITICAL
            reason = f"库存低于最低库存 Below minimum stock ({min_stock})"
        elif current <= safe * self.alert_thresholds["critical_stock_ratio"]:
            alert_level = AlertLevel.URGENT
            reason = f"库存严重不足 Critically low stock"
        elif current <= safe * self.alert_thresholds["low_stock_ratio"]:
            alert_level = AlertLevel.WARNING
            reason = f"库存偏低 Low stock"

        if not alert_level:
            return None

        # 预测消耗并计算建议补货量
        try:
            prediction = await self.predict_consumption(
                item_id=item["item_id"],
                forecast_days=item["lead_time_days"]
            )

            # 建议补货量 = 最高库存 - 当前库存 + 采购周期内预计消耗
            recommended_quantity = (
                item["max_stock"] - current + prediction["predicted_consumption"]
            )

            estimated_stockout_date = None
            if prediction["days_until_stockout"]:
                stockout_date = datetime.now() + timedelta(days=prediction["days_until_stockout"])
                estimated_stockout_date = stockout_date.isoformat()

        except Exception:
            # 如果预测失败,使用简单计算
            recommended_quantity = item["max_stock"] - current
            estimated_stockout_date = None

        alert: RestockAlert = {
            "alert_id": f"restock_{item['item_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "item_id": item["item_id"],
            "item_name": item["item_name"],
            "current_stock": current,
            "recommended_quantity": max(0, recommended_quantity),
            "alert_level": alert_level,
            "reason": reason,
            "estimated_stockout_date": estimated_stockout_date,
            "created_at": datetime.now().isoformat()
        }

        return alert

    async def check_expiration(
        self,
        category: Optional[str] = None
    ) -> List[ExpirationAlert]:
        """
        检查保质期预警

        Args:
            category: 物料分类(可选)

        Returns:
            保质期预警列表
        """
        self.logger.info("checking_expiration", category=category)

        try:
            # 获取库存数据
            inventory = await self.monitor_inventory(category=category)

            alerts = []
            current_date = datetime.now()

            for item in inventory:
                if not item.get("expiration_date"):
                    continue

                expiration_date = datetime.fromisoformat(item["expiration_date"])
                days_until_expiration = (expiration_date - current_date).days

                # 判断预警级别
                alert_level = None
                recommended_action = ""

                if days_until_expiration < 0:
                    alert_level = AlertLevel.CRITICAL
                    recommended_action = "立即下架处理 Remove immediately"
                elif days_until_expiration <= self.alert_thresholds["expiring_urgent_days"]:
                    alert_level = AlertLevel.URGENT
                    recommended_action = "紧急促销或内部消耗 Urgent promotion or internal use"
                elif days_until_expiration <= self.alert_thresholds["expiring_soon_days"]:
                    alert_level = AlertLevel.WARNING
                    recommended_action = "安排促销活动 Plan promotion"

                if alert_level:
                    alert: ExpirationAlert = {
                        "alert_id": f"expiration_{item['item_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "item_id": item["item_id"],
                        "item_name": item["item_name"],
                        "current_stock": item["current_stock"],
                        "expiration_date": item["expiration_date"],
                        "days_until_expiration": days_until_expiration,
                        "alert_level": alert_level,
                        "recommended_action": recommended_action,
                        "created_at": datetime.now().isoformat()
                    }
                    alerts.append(alert)

            # 按过期时间排序
            alerts.sort(key=lambda x: x["days_until_expiration"])

            self.logger.info(
                "expiration_checked",
                total_alerts=len(alerts),
                expired=sum(1 for a in alerts if a["days_until_expiration"] < 0),
                expiring_soon=sum(1 for a in alerts if 0 <= a["days_until_expiration"] <= 7)
            )

            return alerts

        except Exception as e:
            self.logger.error("check_expiration_failed", error=str(e))
            raise

    async def optimize_stock_levels(
        self,
        item_id: str,
        analysis_days: int = 90
    ) -> Dict[str, Any]:
        """
        优化库存水平(安全库存、最低库存、最高库存)

        Args:
            item_id: 物料ID
            analysis_days: 分析天数

        Returns:
            优化建议
        """
        self.logger.info(
            "optimizing_stock_levels",
            item_id=item_id,
            analysis_days=analysis_days
        )

        try:
            # 获取历史消耗数据
            consumption_history = await self._get_consumption_history(
                item_id=item_id,
                days=analysis_days
            )

            if not consumption_history:
                raise ValueError(f"No consumption history for item {item_id}")

            # 计算统计指标
            quantities = [h["quantity"] for h in consumption_history]
            daily_avg = mean(quantities)
            daily_std = stdev(quantities) if len(quantities) > 1 else 0

            # 获取当前库存配置
            inventory = await self.monitor_inventory()
            current_item = next((i for i in inventory if i["item_id"] == item_id), None)

            if not current_item:
                raise ValueError(f"Item {item_id} not found in inventory")

            lead_time = current_item["lead_time_days"]

            # 计算优化后的库存水平
            # 安全库存 = 日均消耗 * 采购周期 + 安全系数 * 标准差 * sqrt(采购周期)
            safety_factor = 1.65  # 95%服务水平
            safe_stock = daily_avg * lead_time + safety_factor * daily_std * (lead_time ** 0.5)

            # 最低库存 = 日均消耗 * 采购周期
            min_stock = daily_avg * lead_time

            # 最高库存 = 安全库存 + 经济订货批量
            # 简化计算: 最高库存 = 安全库存 * 2
            max_stock = safe_stock * 2

            optimization = {
                "item_id": item_id,
                "analysis_period_days": analysis_days,
                "current_levels": {
                    "safe_stock": current_item["safe_stock"],
                    "min_stock": current_item["min_stock"],
                    "max_stock": current_item["max_stock"]
                },
                "recommended_levels": {
                    "safe_stock": round(safe_stock, 2),
                    "min_stock": round(min_stock, 2),
                    "max_stock": round(max_stock, 2)
                },
                "statistics": {
                    "daily_avg_consumption": round(daily_avg, 2),
                    "daily_std_consumption": round(daily_std, 2),
                    "lead_time_days": lead_time
                },
                "optimization_date": datetime.now().isoformat()
            }

            self.logger.info(
                "stock_levels_optimized",
                item_id=item_id,
                recommended_safe_stock=optimization["recommended_levels"]["safe_stock"]
            )

            return optimization

        except Exception as e:
            self.logger.error("optimize_stock_levels_failed", error=str(e), item_id=item_id)
            raise

    async def get_inventory_report(
        self,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取库存综合报告

        Args:
            category: 物料分类(可选)

        Returns:
            库存报告
        """
        self.logger.info("generating_inventory_report", category=category)

        try:
            # 并发执行多个任务
            inventory_task = self.monitor_inventory(category=category)
            restock_alerts_task = self.generate_restock_alerts(category=category)
            expiration_alerts_task = self.check_expiration(category=category)

            inventory, restock_alerts, expiration_alerts = await asyncio.gather(
                inventory_task,
                restock_alerts_task,
                expiration_alerts_task
            )

            # 统计库存状态
            status_counts = {}
            total_value = 0

            for item in inventory:
                status = item.get("status", InventoryStatus.SUFFICIENT)
                status_counts[status] = status_counts.get(status, 0) + 1
                total_value += item["current_stock"] * item["unit_cost"]

            report = {
                "store_id": self.store_id,
                "report_date": datetime.now().isoformat(),
                "category": category,
                "summary": {
                    "total_items": len(inventory),
                    "total_value_fen": total_value,
                    "status_distribution": status_counts,
                    "restock_alerts_count": len(restock_alerts),
                    "expiration_alerts_count": len(expiration_alerts)
                },
                "inventory": inventory,
                "restock_alerts": restock_alerts,
                "expiration_alerts": expiration_alerts
            }

            self.logger.info(
                "inventory_report_generated",
                total_items=len(inventory),
                restock_alerts=len(restock_alerts),
                expiration_alerts=len(expiration_alerts)
            )

            return report

        except Exception as e:
            self.logger.error("get_inventory_report_failed", error=str(e))
            raise

    def _generate_mock_inventory(self, category: Optional[str] = None) -> List[InventoryItem]:
        """生成模拟库存数据"""
        mock_items = [
            {
                "item_id": "INV001",
                "item_name": "鸡胸肉",
                "category": "meat",
                "unit": "kg",
                "current_stock": 15.5,
                "safe_stock": 50.0,
                "min_stock": 20.0,
                "max_stock": 100.0,
                "unit_cost": 2500,  # 25元/kg
                "supplier_id": "SUP001",
                "lead_time_days": 2,
                "expiration_date": (datetime.now() + timedelta(days=5)).isoformat(),
                "location": "冷藏区A1"
            },
            {
                "item_id": "INV002",
                "item_name": "番茄",
                "category": "vegetable",
                "unit": "kg",
                "current_stock": 8.0,
                "safe_stock": 30.0,
                "min_stock": 10.0,
                "max_stock": 60.0,
                "unit_cost": 800,  # 8元/kg
                "supplier_id": "SUP002",
                "lead_time_days": 1,
                "expiration_date": (datetime.now() + timedelta(days=3)).isoformat(),
                "location": "常温区B2"
            },
            {
                "item_id": "INV003",
                "item_name": "食用油",
                "category": "condiment",
                "unit": "L",
                "current_stock": 45.0,
                "safe_stock": 40.0,
                "min_stock": 20.0,
                "max_stock": 80.0,
                "unit_cost": 1500,  # 15元/L
                "supplier_id": "SUP003",
                "lead_time_days": 3,
                "expiration_date": (datetime.now() + timedelta(days=180)).isoformat(),
                "location": "仓库C3"
            },
            {
                "item_id": "INV004",
                "item_name": "大米",
                "category": "grain",
                "unit": "kg",
                "current_stock": 120.0,
                "safe_stock": 100.0,
                "min_stock": 50.0,
                "max_stock": 200.0,
                "unit_cost": 600,  # 6元/kg
                "supplier_id": "SUP004",
                "lead_time_days": 2,
                "expiration_date": None,
                "location": "仓库C1"
            },
            {
                "item_id": "INV005",
                "item_name": "牛奶",
                "category": "dairy",
                "unit": "L",
                "current_stock": 2.0,
                "safe_stock": 20.0,
                "min_stock": 10.0,
                "max_stock": 40.0,
                "unit_cost": 1200,  # 12元/L
                "supplier_id": "SUP005",
                "lead_time_days": 1,
                "expiration_date": (datetime.now() + timedelta(days=2)).isoformat(),
                "location": "冷藏区A2"
            }
        ]

        if category:
            return [item for item in mock_items if item["category"] == category]

        return mock_items
