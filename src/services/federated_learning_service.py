"""
Federated Learning Service
联邦学习服务

Phase 4: 智能优化期 (Intelligence Optimization Period)
Enables multi-store model training with privacy protection
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import numpy as np
from dataclasses import dataclass
from sqlalchemy.orm import Session


class ModelType(Enum):
    """Model type enum"""
    DEMAND_FORECAST = "demand_forecast"  # 需求预测
    PRICE_OPTIMIZATION = "price_optimization"  # 价格优化
    STAFF_SCHEDULE = "staff_schedule"  # 排班优化
    INVENTORY_PREDICTION = "inventory_prediction"  # 库存预测
    CUSTOMER_PREFERENCE = "customer_preference"  # 客户偏好


class TrainingStatus(Enum):
    """Training status enum"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ModelUpdate:
    """Model update from a store"""
    store_id: str
    model_type: ModelType
    weights: Dict[str, np.ndarray]
    metrics: Dict[str, float]
    sample_count: int
    timestamp: datetime


@dataclass
class GlobalModel:
    """Global aggregated model"""
    model_type: ModelType
    version: int
    weights: Dict[str, np.ndarray]
    performance_metrics: Dict[str, float]
    participating_stores: List[str]
    created_at: datetime


class FederatedLearningService:
    """
    Federated Learning Service
    联邦学习服务

    Implements federated learning for multi-store model training
    with privacy protection (no raw data sharing).

    Key features:
    1. Multi-store collaborative training
    2. Privacy-preserving (only model weights shared)
    3. Weighted aggregation based on data quality
    4. Automatic model distribution
    5. Performance tracking

    Algorithm: Federated Averaging (FedAvg)
    - Each store trains locally on its own data
    - Stores upload model updates (weights only)
    - Central server aggregates updates
    - Global model distributed back to stores
    """

    def __init__(self, db: Session):
        self.db = db
        # Store local model updates waiting for aggregation
        self.pending_updates: Dict[ModelType, List[ModelUpdate]] = {
            model_type: [] for model_type in ModelType
        }
        # Store global models
        self.global_models: Dict[ModelType, GlobalModel] = {}
        # Training rounds counter
        self.training_rounds: Dict[ModelType, int] = {
            model_type: 0 for model_type in ModelType
        }

    def submit_local_update(
        self,
        store_id: str,
        model_type: ModelType,
        weights: Dict[str, np.ndarray],
        metrics: Dict[str, float],
        sample_count: int
    ) -> Dict[str, Any]:
        """
        Submit local model update from a store
        提交门店本地模型更新

        Args:
            store_id: Store identifier
            model_type: Type of model being updated
            weights: Model weights (parameters)
            metrics: Performance metrics (accuracy, loss, etc.)
            sample_count: Number of training samples used

        Returns:
            Submission confirmation with status
        """
        update = ModelUpdate(
            store_id=store_id,
            model_type=model_type,
            weights=weights,
            metrics=metrics,
            sample_count=sample_count,
            timestamp=datetime.utcnow()
        )

        self.pending_updates[model_type].append(update)

        return {
            "success": True,
            "store_id": store_id,
            "model_type": model_type.value,
            "pending_updates": len(self.pending_updates[model_type]),
            "message": "Local update submitted successfully"
        }

    def aggregate_updates(
        self,
        model_type: ModelType,
        min_participants: int = 3
    ) -> Optional[GlobalModel]:
        """
        Aggregate local updates into global model
        聚合本地更新为全局模型

        Uses Federated Averaging (FedAvg) algorithm:
        - Weighted average based on sample count
        - Quality filtering based on metrics
        - Outlier detection and removal

        Args:
            model_type: Type of model to aggregate
            min_participants: Minimum number of stores required

        Returns:
            Global model if aggregation successful, None otherwise
        """
        updates = self.pending_updates[model_type]

        # Check minimum participants
        if len(updates) < min_participants:
            return None

        # Filter out low-quality updates
        filtered_updates = self._filter_quality_updates(updates)

        if len(filtered_updates) < min_participants:
            return None

        # Calculate weighted average of model weights
        total_samples = sum(u.sample_count for u in filtered_updates)
        aggregated_weights = {}

        # Get all weight keys from first update
        weight_keys = filtered_updates[0].weights.keys()

        for key in weight_keys:
            weighted_sum = np.zeros_like(filtered_updates[0].weights[key])

            for update in filtered_updates:
                weight = update.sample_count / total_samples
                weighted_sum += weight * update.weights[key]

            aggregated_weights[key] = weighted_sum

        # Calculate aggregated performance metrics
        aggregated_metrics = self._aggregate_metrics(filtered_updates)

        # Create global model
        self.training_rounds[model_type] += 1
        global_model = GlobalModel(
            model_type=model_type,
            version=self.training_rounds[model_type],
            weights=aggregated_weights,
            performance_metrics=aggregated_metrics,
            participating_stores=[u.store_id for u in filtered_updates],
            created_at=datetime.utcnow()
        )

        # Store global model
        self.global_models[model_type] = global_model

        # Clear pending updates
        self.pending_updates[model_type] = []

        return global_model

    def get_global_model(
        self,
        model_type: ModelType
    ) -> Optional[GlobalModel]:
        """
        Get latest global model
        获取最新全局模型

        Args:
            model_type: Type of model to retrieve

        Returns:
            Latest global model or None if not available
        """
        return self.global_models.get(model_type)

    def download_global_model(
        self,
        store_id: str,
        model_type: ModelType
    ) -> Optional[Dict[str, Any]]:
        """
        Download global model for a store
        为门店下载全局模型

        Args:
            store_id: Store requesting the model
            model_type: Type of model to download

        Returns:
            Model data including weights and metadata
        """
        global_model = self.global_models.get(model_type)

        if not global_model:
            return None

        return {
            "model_type": model_type.value,
            "version": global_model.version,
            "weights": global_model.weights,
            "performance_metrics": global_model.performance_metrics,
            "participating_stores_count": len(global_model.participating_stores),
            "created_at": global_model.created_at.isoformat(),
            "download_time": datetime.utcnow().isoformat()
        }

    def get_training_status(
        self,
        model_type: ModelType
    ) -> Dict[str, Any]:
        """
        Get training status for a model type
        获取模型训练状态

        Args:
            model_type: Type of model

        Returns:
            Training status information
        """
        pending_count = len(self.pending_updates[model_type])
        global_model = self.global_models.get(model_type)

        return {
            "model_type": model_type.value,
            "training_round": self.training_rounds[model_type],
            "pending_updates": pending_count,
            "has_global_model": global_model is not None,
            "global_model_version": global_model.version if global_model else None,
            "last_update": global_model.created_at.isoformat() if global_model else None
        }

    def get_store_contribution(
        self,
        store_id: str,
        model_type: ModelType
    ) -> Dict[str, Any]:
        """
        Get store's contribution to federated learning
        获取门店对联邦学习的贡献

        Args:
            store_id: Store identifier
            model_type: Type of model

        Returns:
            Contribution statistics
        """
        global_model = self.global_models.get(model_type)

        if not global_model:
            return {
                "store_id": store_id,
                "model_type": model_type.value,
                "participated": False
            }

        participated = store_id in global_model.participating_stores

        # Count historical participation
        participation_count = 0
        if participated:
            participation_count = 1  # Simplified, should track history

        return {
            "store_id": store_id,
            "model_type": model_type.value,
            "participated": participated,
            "participation_count": participation_count,
            "current_version": global_model.version,
            "contribution_rate": participation_count / global_model.version if global_model.version > 0 else 0
        }

    def _filter_quality_updates(
        self,
        updates: List[ModelUpdate]
    ) -> List[ModelUpdate]:
        """
        Filter out low-quality updates
        过滤低质量更新

        Criteria:
        1. Minimum sample count (>= 100)
        2. Reasonable metrics (not NaN, not extreme values)
        3. Outlier detection using z-score
        """
        filtered = []

        for update in updates:
            # Check minimum sample count
            if update.sample_count < 100:
                continue

            # Check metrics validity
            if not self._validate_metrics(update.metrics):
                continue

            filtered.append(update)

        # Outlier detection based on loss metric
        if len(filtered) > 3:
            filtered = self._remove_outliers(filtered)

        return filtered

    def _validate_metrics(self, metrics: Dict[str, float]) -> bool:
        """Validate metrics are reasonable"""
        for key, value in metrics.items():
            if np.isnan(value) or np.isinf(value):
                return False
            # Check reasonable ranges
            if key == "loss" and (value < 0 or value > 1000):
                return False
            if key == "accuracy" and (value < 0 or value > 1):
                return False
        return True

    def _remove_outliers(
        self,
        updates: List[ModelUpdate],
        threshold: float = 3.0
    ) -> List[ModelUpdate]:
        """
        Remove outliers using z-score method
        使用z-score方法移除异常值
        """
        if "loss" not in updates[0].metrics:
            return updates

        losses = [u.metrics["loss"] for u in updates]
        mean_loss = np.mean(losses)
        std_loss = np.std(losses)

        if std_loss == 0:
            return updates

        filtered = []
        for update in updates:
            z_score = abs((update.metrics["loss"] - mean_loss) / std_loss)
            if z_score < threshold:
                filtered.append(update)

        return filtered if len(filtered) >= 3 else updates

    def _aggregate_metrics(
        self,
        updates: List[ModelUpdate]
    ) -> Dict[str, float]:
        """
        Aggregate performance metrics
        聚合性能指标
        """
        if not updates:
            return {}

        # Get all metric keys
        metric_keys = updates[0].metrics.keys()
        aggregated = {}

        for key in metric_keys:
            values = [u.metrics[key] for u in updates]
            aggregated[f"{key}_mean"] = float(np.mean(values))
            aggregated[f"{key}_std"] = float(np.std(values))
            aggregated[f"{key}_min"] = float(np.min(values))
            aggregated[f"{key}_max"] = float(np.max(values))

        return aggregated
