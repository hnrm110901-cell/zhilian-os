"""
动态BOM联邦学习服务
Federated BOM (Bill of Materials) Learning Service

核心价值：
- 跨门店学习食材损耗规律
- 数据不出域，只共享模型参数
- 季节性、区域性损耗率预测

应用场景：
- 冬季vs夏季辣椒损耗率差异
- 长三角vs珠三角食材保存规律
- 节假日vs平日食材消耗模式
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pydantic import BaseModel
import numpy as np
import logging

logger = logging.getLogger(__name__)


class IngredientLossPattern(BaseModel):
    """食材损耗模式"""
    ingredient_id: str
    ingredient_name: str
    season: str                    # spring/summer/autumn/winter
    region: str                    # 区域
    average_loss_rate: float       # 平均损耗率
    std_loss_rate: float           # 损耗率标准差
    peak_loss_days: List[int]      # 高损耗日期
    optimal_order_quantity: float  # 最优订货量
    confidence: float              # 置信度


class BOMModelUpdate(BaseModel):
    """BOM模型更新"""
    store_id: str
    ingredient_id: str
    local_loss_rate: float
    local_samples: int
    model_gradients: List[float]   # 模型梯度（用于联邦聚合）
    timestamp: datetime


class FederatedBOMService:
    """动态BOM联邦学习服务"""

    def __init__(self):
        self.global_models = {}        # 全局模型
        self.local_models = {}         # 本地模型
        self.loss_patterns = {}        # 损耗模式库

    async def train_local_model(
        self,
        store_id: str,
        ingredient_id: str,
        historical_data: List[Dict]
    ) -> BOMModelUpdate:
        """
        训练本地模型

        Args:
            store_id: 门店ID
            ingredient_id: 食材ID
            historical_data: 历史数据（采购量、实际使用量、损耗量）

        Returns:
            模型更新（包含梯度）
        """
        logger.info(
            f"Training local BOM model for store {store_id}, "
            f"ingredient {ingredient_id}"
        )

        # 提取特征
        features = self._extract_features(historical_data)

        # 计算本地损耗率
        local_loss_rate = self._calculate_loss_rate(historical_data)

        # 训练本地模型（简化版线性回归）
        model_gradients = self._train_linear_model(features, historical_data)

        return BOMModelUpdate(
            store_id=store_id,
            ingredient_id=ingredient_id,
            local_loss_rate=local_loss_rate,
            local_samples=len(historical_data),
            model_gradients=model_gradients,
            timestamp=datetime.now()
        )

    def _extract_features(
        self,
        historical_data: List[Dict]
    ) -> np.ndarray:
        """提取特征"""
        features = []

        for record in historical_data:
            # 特征：季节、温度、湿度、存储天数
            feature_vector = [
                self._encode_season(record.get("date")),
                record.get("temperature", 20.0),
                record.get("humidity", 60.0),
                record.get("storage_days", 3),
                1 if record.get("is_holiday", False) else 0,
                record.get("purchase_quantity", 0),
            ]
            features.append(feature_vector)

        return np.array(features)

    def _encode_season(self, date: datetime) -> int:
        """编码季节"""
        month = date.month
        if month in [3, 4, 5]:
            return 0  # 春季
        elif month in [6, 7, 8]:
            return 1  # 夏季
        elif month in [9, 10, 11]:
            return 2  # 秋季
        else:
            return 3  # 冬季

    def _calculate_loss_rate(
        self,
        historical_data: List[Dict]
    ) -> float:
        """计算损耗率"""
        total_purchase = sum(
            record.get("purchase_quantity", 0)
            for record in historical_data
        )
        total_loss = sum(
            record.get("loss_quantity", 0)
            for record in historical_data
        )

        if total_purchase == 0:
            return 0.0

        return total_loss / total_purchase

    def _train_linear_model(
        self,
        features: np.ndarray,
        historical_data: List[Dict]
    ) -> List[float]:
        """训练线性模型（简化版）"""
        # 目标：预测损耗量
        targets = np.array([
            record.get("loss_quantity", 0)
            for record in historical_data
        ])

        # 简化的梯度下降
        n_features = features.shape[1]
        weights = np.random.randn(n_features) * 0.01
        learning_rate = 0.01
        epochs = 10

        for epoch in range(epochs):
            # 前向传播
            predictions = np.dot(features, weights)

            # 计算损失
            loss = np.mean((predictions - targets) ** 2)

            # 反向传播
            gradients = 2 * np.dot(features.T, (predictions - targets)) / len(targets)

            # 更新权重
            weights -= learning_rate * gradients

            if epoch % 5 == 0:
                logger.debug(f"Epoch {epoch}, Loss: {loss:.4f}")

        # 返回梯度（用于联邦聚合）
        return gradients.tolist()

    async def federated_aggregate(
        self,
        updates: List[BOMModelUpdate]
    ) -> Dict[str, Any]:
        """
        联邦聚合

        Args:
            updates: 来自各门店的模型更新

        Returns:
            聚合后的全局模型
        """
        if not updates:
            return {}

        ingredient_id = updates[0].ingredient_id

        logger.info(
            f"Federated aggregation for ingredient {ingredient_id}, "
            f"{len(updates)} stores"
        )

        # FedAvg算法：加权平均
        total_samples = sum(update.local_samples for update in updates)

        # 聚合梯度
        aggregated_gradients = np.zeros(len(updates[0].model_gradients))

        for update in updates:
            weight = update.local_samples / total_samples
            aggregated_gradients += (
                np.array(update.model_gradients) * weight
            )

        # 聚合损耗率
        aggregated_loss_rate = sum(
            update.local_loss_rate * update.local_samples
            for update in updates
        ) / total_samples

        # 更新全局模型
        self.global_models[ingredient_id] = {
            "gradients": aggregated_gradients.tolist(),
            "loss_rate": aggregated_loss_rate,
            "num_stores": len(updates),
            "total_samples": total_samples,
            "updated_at": datetime.now()
        }

        logger.info(
            f"Global model updated: loss_rate={aggregated_loss_rate:.4f}"
        )

        return self.global_models[ingredient_id]

    async def predict_loss_rate(
        self,
        ingredient_id: str,
        season: str,
        region: str,
        temperature: float,
        humidity: float,
        storage_days: int
    ) -> float:
        """
        预测损耗率

        Args:
            ingredient_id: 食材ID
            season: 季节
            region: 区域
            temperature: 温度
            humidity: 湿度
            storage_days: 存储天数

        Returns:
            预测的损耗率
        """
        # 获取全局模型
        global_model = self.global_models.get(ingredient_id)

        if not global_model:
            logger.warning(
                f"No global model for ingredient {ingredient_id}, "
                f"using default loss rate"
            )
            return 0.05  # 默认5%损耗率

        # 构造特征向量
        season_code = {"spring": 0, "summer": 1, "autumn": 2, "winter": 3}
        features = np.array([
            season_code.get(season, 0),
            temperature,
            humidity,
            storage_days,
            0,  # is_holiday
            100,  # purchase_quantity (假设)
        ])

        # 使用全局模型预测
        gradients = np.array(global_model["gradients"])
        predicted_loss = np.dot(features, gradients)

        # 转换为损耗率
        predicted_loss_rate = max(0.0, min(1.0, predicted_loss / 100))

        logger.info(
            f"Predicted loss rate for {ingredient_id}: {predicted_loss_rate:.4f}"
        )

        return predicted_loss_rate

    async def discover_loss_patterns(
        self,
        ingredient_id: str,
        region: str
    ) -> IngredientLossPattern:
        """
        发现损耗模式

        Args:
            ingredient_id: 食材ID
            region: 区域

        Returns:
            损耗模式
        """
        # 从全局模型中提取模式
        global_model = self.global_models.get(ingredient_id, {})

        # 分析季节性模式
        seasonal_loss_rates = {}
        for season in ["spring", "summer", "autumn", "winter"]:
            loss_rate = await self.predict_loss_rate(
                ingredient_id=ingredient_id,
                season=season,
                region=region,
                temperature=20.0,
                humidity=60.0,
                storage_days=3
            )
            seasonal_loss_rates[season] = loss_rate

        # 找出损耗率最高的季节
        peak_season = max(seasonal_loss_rates, key=seasonal_loss_rates.get)

        # 计算最优订货量
        average_loss_rate = np.mean(list(seasonal_loss_rates.values()))
        optimal_order_quantity = 100 / (1 - average_loss_rate)  # 简化计算

        # 分析高损耗日期（损耗率超过均值+1个标准差的季节对应的月份）
        std_loss = np.std(list(seasonal_loss_rates.values()))
        threshold = average_loss_rate + std_loss
        season_months = {
            "spring": [3, 4, 5],
            "summer": [6, 7, 8],
            "autumn": [9, 10, 11],
            "winter": [12, 1, 2],
        }
        peak_loss_days = []
        for season, rate in seasonal_loss_rates.items():
            if rate >= threshold:
                peak_loss_days.extend([f"{m}月" for m in season_months.get(season, [])])

        return IngredientLossPattern(
            ingredient_id=ingredient_id,
            ingredient_name=f"Ingredient_{ingredient_id}",
            season=peak_season,
            region=region,
            average_loss_rate=average_loss_rate,
            std_loss_rate=np.std(list(seasonal_loss_rates.values())),
            peak_loss_days=peak_loss_days,
            optimal_order_quantity=optimal_order_quantity,
            confidence=0.8 if global_model else 0.3
        )

    async def detect_anomaly(
        self,
        store_id: str,
        ingredient_id: str,
        current_loss_rate: float
    ) -> Dict[str, Any]:
        """
        检测异常损耗

        Args:
            store_id: 门店ID
            ingredient_id: 食材ID
            current_loss_rate: 当前损耗率

        Returns:
            异常检测结果
        """
        # 获取全局模型
        global_model = self.global_models.get(ingredient_id)

        if not global_model:
            return {
                "is_anomaly": False,
                "reason": "No global model available"
            }

        # 计算偏差
        global_loss_rate = global_model["loss_rate"]
        deviation = abs(current_loss_rate - global_loss_rate)
        threshold = global_loss_rate * 0.5  # 50%偏差阈值

        is_anomaly = deviation > threshold

        if is_anomaly:
            logger.warning(
                f"Anomaly detected for store {store_id}, "
                f"ingredient {ingredient_id}: "
                f"current={current_loss_rate:.4f}, "
                f"global={global_loss_rate:.4f}"
            )

        return {
            "is_anomaly": is_anomaly,
            "current_loss_rate": current_loss_rate,
            "global_loss_rate": global_loss_rate,
            "deviation": deviation,
            "threshold": threshold,
            "severity": "high" if deviation > threshold * 2 else "medium",
            "recommendation": (
                "检查食材存储条件和操作规范"
                if is_anomaly else "损耗率正常"
            )
        }

    async def sync_knowledge_across_regions(
        self,
        source_region: str,
        target_region: str,
        ingredient_id: str
    ) -> Dict[str, Any]:
        """
        跨区域知识同步

        场景：长三角发现的规律同步给珠三角

        Args:
            source_region: 源区域
            target_region: 目标区域
            ingredient_id: 食材ID

        Returns:
            同步结果
        """
        logger.info(
            f"Syncing knowledge from {source_region} to {target_region} "
            f"for ingredient {ingredient_id}"
        )

        # 获取源区域的损耗模式
        source_pattern = await self.discover_loss_patterns(
            ingredient_id, source_region
        )

        # 应用到目标区域（带置信度衰减）
        target_pattern = source_pattern.copy()
        target_pattern.region = target_region
        target_pattern.confidence *= 0.7  # 跨区域置信度衰减

        # 存储到模式库
        pattern_key = f"{target_region}_{ingredient_id}"
        self.loss_patterns[pattern_key] = target_pattern

        return {
            "source_region": source_region,
            "target_region": target_region,
            "ingredient_id": ingredient_id,
            "synced_loss_rate": target_pattern.average_loss_rate,
            "confidence": target_pattern.confidence,
            "recommendation": (
                f"建议{target_region}参考{source_region}的食材管理经验"
            )
        }

    def get_model_statistics(self) -> Dict[str, Any]:
        """获取模型统计"""
        return {
            "total_global_models": len(self.global_models),
            "total_loss_patterns": len(self.loss_patterns),
            "models": [
                {
                    "ingredient_id": ing_id,
                    "loss_rate": model["loss_rate"],
                    "num_stores": model["num_stores"],
                    "updated_at": model["updated_at"].isoformat()
                }
                for ing_id, model in self.global_models.items()
            ]
        }


# 全局实例
federated_bom = FederatedBOMService()
