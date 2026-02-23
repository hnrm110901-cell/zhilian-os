"""
联邦学习服务
实现门店间的协同学习，保护数据隐私
"""
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np
import structlog
from enum import Enum
import uuid
from sqlalchemy import select, func

from src.services.base_service import BaseService
from src.core.database import get_db_session
from src.models.federated_learning import FLTrainingRound, FLModelUpload, RoundStatus

logger = structlog.get_logger()


class ModelType(str, Enum):
    """模型类型"""
    SALES_FORECAST = "sales_forecast"
    DEMAND_PREDICTION = "demand_prediction"
    CUSTOMER_SEGMENTATION = "customer_segmentation"
    CHURN_PREDICTION = "churn_prediction"


class AggregationMethod(str, Enum):
    """聚合方法"""
    FEDAVG = "fedavg"  # 联邦平均
    FEDPROX = "fedprox"  # 联邦近端
    WEIGHTED_AVG = "weighted_avg"  # 加权平均


class FederatedLearningService(BaseService):
    """
    联邦学习服务

    实现门店间的协同学习：
    1. 各门店本地训练模型
    2. 上传模型参数（不上传原始数据）
    3. 服务器聚合模型参数
    4. 下发全局模型
    """

    def __init__(self, store_id: Optional[str] = None):
        super().__init__(store_id)
        self.min_stores = 3  # 最少参与门店数（可被config覆盖）
        self.aggregation_threshold = 0.8  # 聚合阈值（可被config覆盖）
        # 尝试从环境变量读取
        import os
        if os.getenv("FL_MIN_STORES"):
            self.min_stores = int(os.getenv("FL_MIN_STORES"))
        if os.getenv("FL_AGGREGATION_THRESHOLD"):
            self.aggregation_threshold = float(os.getenv("FL_AGGREGATION_THRESHOLD"))

    async def create_training_round(
        self,
        model_type: ModelType,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        创建训练轮次

        Args:
            model_type: 模型类型
            config: 训练配置

        Returns:
            训练轮次信息
        """
        round_id = self._generate_round_id()

        async with get_db_session() as session:
            record = FLTrainingRound(
                id=round_id,
                model_type=model_type.value if hasattr(model_type, "value") else str(model_type),
                status=RoundStatus.INITIALIZED,
                config=config,
                num_participating_stores=0,
                created_at=datetime.now(),
            )
            session.add(record)
            await session.commit()

        training_round = {
            "round_id": round_id,
            "model_type": model_type,
            "status": "initialized",
            "config": config,
            "participating_stores": [],
            "created_at": datetime.now().isoformat(),
            "min_stores": self.min_stores,
        }

        logger.info(
            "Training round created",
            round_id=round_id,
            model_type=model_type,
        )

        return training_round

    async def join_training_round(
        self,
        round_id: str,
    ) -> Dict[str, Any]:
        """
        门店加入训练轮次

        Args:
            round_id: 训练轮次ID

        Returns:
            加入结果
        """
        store_id = self.require_store_id()

        async with get_db_session() as session:
            result = await session.execute(
                select(FLTrainingRound).where(FLTrainingRound.id == round_id)
            )
            round_record = result.scalar_one_or_none()
            if not round_record:
                raise ValueError(f"训练轮次不存在: {round_id}")
            round_record.status = RoundStatus.COLLECTING
            round_record.num_participating_stores = (round_record.num_participating_stores or 0) + 1
            await session.commit()
            training_config = round_record.config or {}

        logger.info(
            "Store joined training round",
            store_id=store_id,
            round_id=round_id,
        )

        return {
            "round_id": round_id,
            "store_id": store_id,
            "status": "joined",
            "training_config": training_config or {
                "epochs": int(os.getenv("FL_TRAIN_EPOCHS", "10")),
                "batch_size": int(os.getenv("FL_TRAIN_BATCH_SIZE", "32")),
                "learning_rate": float(os.getenv("FL_TRAIN_LEARNING_RATE", "0.001")),
            },
        }

    async def upload_local_model(
        self,
        round_id: str,
        model_parameters: Dict[str, Any],
        training_metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        上传本地训练的模型参数

        Args:
            round_id: 训练轮次ID
            model_parameters: 模型参数（权重）
            training_metrics: 训练指标

        Returns:
            上传结果
        """
        store_id = self.require_store_id()

        # 应用差分隐私
        noisy_parameters = self._apply_differential_privacy(
            model_parameters,
            epsilon=1.0,
        )

        # 验证模型参数
        if not self._validate_model_parameters(noisy_parameters):
            raise ValueError("Invalid model parameters")

        # 序列化 numpy arrays 为 list
        serialized = {
            k: v.tolist() if isinstance(v, np.ndarray) else v
            for k, v in noisy_parameters.items()
        }

        async with get_db_session() as session:
            upload = FLModelUpload(
                id=str(uuid.uuid4()),
                round_id=round_id,
                store_id=store_id,
                model_parameters=serialized,
                training_metrics=training_metrics,
                training_samples=training_metrics.get("samples", 0),
                uploaded_at=datetime.now(),
            )
            session.add(upload)
            await session.commit()

        logger.info(
            "Local model uploaded",
            store_id=store_id,
            round_id=round_id,
            training_loss=training_metrics.get("loss"),
            training_accuracy=training_metrics.get("accuracy"),
        )

        return {
            "round_id": round_id,
            "store_id": store_id,
            "status": "uploaded",
            "upload_time": datetime.now().isoformat(),
        }

    async def aggregate_models(
        self,
        round_id: str,
        method: AggregationMethod = AggregationMethod.FEDAVG,
    ) -> Dict[str, Any]:
        """
        聚合多个门店的模型参数

        Args:
            round_id: 训练轮次ID
            method: 聚合方法

        Returns:
            聚合后的全局模型
        """
        # 从数据库获取所有参与门店的模型参数
        store_models = await self._get_store_models(round_id)

        if len(store_models) < self.min_stores:
            raise ValueError(
                f"Insufficient stores for aggregation. "
                f"Required: {self.min_stores}, Got: {len(store_models)}"
            )

        # 执行聚合
        if method == AggregationMethod.FEDAVG:
            global_model = self._fedavg_aggregation(store_models)
        elif method == AggregationMethod.WEIGHTED_AVG:
            global_model = self._weighted_aggregation(store_models)
        else:
            raise ValueError(f"Unsupported aggregation method: {method}")

        # 保存全局模型到 DB
        global_params_serialized = {
            k: v.tolist() if isinstance(v, np.ndarray) else v
            for k, v in global_model.items()
        }
        async with get_db_session() as session:
            result = await session.execute(
                select(FLTrainingRound).where(FLTrainingRound.id == round_id)
            )
            round_record = result.scalar_one_or_none()
            if round_record:
                round_record.status = RoundStatus.COMPLETED
                round_record.global_model_parameters = global_params_serialized
                round_record.aggregation_method = method.value if hasattr(method, "value") else str(method)
                round_record.completed_at = datetime.now()
                await session.commit()

        logger.info(
            "Models aggregated",
            round_id=round_id,
            method=method,
            num_stores=len(store_models),
        )

        return {
            "round_id": round_id,
            "global_model": global_model,
            "num_participating_stores": len(store_models),
            "aggregation_method": method,
            "aggregated_at": datetime.now().isoformat(),
        }

    def _fedavg_aggregation(
        self,
        store_models: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        FedAvg聚合算法

        计算所有门店模型参数的平均值

        Args:
            store_models: 门店模型列表

        Returns:
            聚合后的全局模型参数
        """
        if not store_models:
            raise ValueError("No models to aggregate")

        # 提取所有模型的参数
        all_parameters = [model["parameters"] for model in store_models]

        # 计算平均值
        global_parameters = {}

        # 假设参数是字典形式 {"layer1": array, "layer2": array, ...}
        for key in all_parameters[0].keys():
            # 收集所有门店该层的参数
            layer_params = [params[key] for params in all_parameters]

            # 计算平均值
            global_parameters[key] = np.mean(layer_params, axis=0)

        logger.debug(
            "FedAvg aggregation completed",
            num_models=len(store_models),
            num_parameters=len(global_parameters),
        )

        return {
            "parameters": global_parameters,
            "aggregation_method": "fedavg",
        }

    def _weighted_aggregation(
        self,
        store_models: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        加权平均聚合

        根据门店的数据量或性能加权

        Args:
            store_models: 门店模型列表

        Returns:
            聚合后的全局模型参数
        """
        if not store_models:
            raise ValueError("No models to aggregate")

        # 提取参数和权重
        all_parameters = [model["parameters"] for model in store_models]
        weights = [model.get("weight", 1.0) for model in store_models]

        # 归一化权重
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]

        # 加权平均
        global_parameters = {}

        for key in all_parameters[0].keys():
            layer_params = [params[key] for params in all_parameters]

            # 加权平均
            weighted_sum = sum(
                param * weight
                for param, weight in zip(layer_params, normalized_weights)
            )
            global_parameters[key] = weighted_sum

        logger.debug(
            "Weighted aggregation completed",
            num_models=len(store_models),
            weights=normalized_weights,
        )

        return {
            "parameters": global_parameters,
            "aggregation_method": "weighted_avg",
            "weights": normalized_weights,
        }

    def _apply_differential_privacy(
        self,
        parameters: Dict[str, Any],
        epsilon: float = 1.0,
    ) -> Dict[str, Any]:
        """
        应用差分隐私保护

        向模型参数添加噪声，保护隐私

        Args:
            parameters: 原始模型参数
            epsilon: 隐私预算（越小越私密，但准确性越低）

        Returns:
            添加噪声后的参数
        """
        noisy_parameters = {}

        for key, value in parameters.items():
            if isinstance(value, np.ndarray):
                # 计算噪声规模
                sensitivity = self._calculate_sensitivity(value)
                noise_scale = sensitivity / epsilon

                # 添加拉普拉斯噪声
                noise = np.random.laplace(0, noise_scale, value.shape)
                noisy_parameters[key] = value + noise
            else:
                noisy_parameters[key] = value

        logger.debug(
            "Differential privacy applied",
            epsilon=epsilon,
            num_parameters=len(parameters),
        )

        return noisy_parameters

    def _calculate_sensitivity(self, parameter: np.ndarray) -> float:
        """
        计算参数的敏感度

        Args:
            parameter: 参数数组

        Returns:
            敏感度值
        """
        # 简化实现：使用L2范数作为敏感度
        return float(np.linalg.norm(parameter))

    def _validate_model_parameters(self, parameters: Dict[str, Any]) -> bool:
        """
        验证模型参数的有效性

        Args:
            parameters: 模型参数

        Returns:
            是否有效
        """
        if not parameters:
            return False

        # 检查参数是否包含NaN或Inf
        for key, value in parameters.items():
            if isinstance(value, np.ndarray):
                if np.isnan(value).any() or np.isinf(value).any():
                    logger.warning(
                        "Invalid parameter detected",
                        key=key,
                        has_nan=np.isnan(value).any(),
                        has_inf=np.isinf(value).any(),
                    )
                    return False

        return True

    async def _get_store_models(self, round_id: str) -> List[Dict[str, Any]]:
        """
        从数据库获取训练轮次中所有门店的模型
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(FLModelUpload).where(FLModelUpload.round_id == round_id)
            )
            uploads = result.scalars().all()

        store_models = []
        for upload in uploads:
            params = upload.model_parameters or {}
            # 反序列化 list → numpy array
            np_params = {
                k: np.array(v) if isinstance(v, list) else v
                for k, v in params.items()
            }
            store_models.append({
                "store_id": upload.store_id,
                "parameters": np_params,
                "weight": 1.0,
                "training_samples": upload.training_samples or 0,
            })

        return store_models

    def _generate_round_id(self) -> str:
        """生成训练轮次ID"""
        from uuid import uuid4
        return f"round_{uuid4().hex[:12]}"

    async def get_training_status(self, round_id: str) -> Dict[str, Any]:
        """
        获取训练轮次状态

        Args:
            round_id: 训练轮次ID

        Returns:
            训练状态信息
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(FLTrainingRound).where(FLTrainingRound.id == round_id)
            )
            round_record = result.scalar_one_or_none()

            if not round_record:
                return {"round_id": round_id, "status": "not_found"}

            uploads_result = await session.execute(
                select(func.count(FLModelUpload.id)).where(FLModelUpload.round_id == round_id)
            )
            completed_stores = int(uploads_result.scalar() or 0)

        total = round_record.num_participating_stores or 0
        progress = completed_stores / total if total > 0 else 0.0

        return {
            "round_id": round_id,
            "status": round_record.status.value if round_record.status else "unknown",
            "participating_stores": total,
            "completed_stores": completed_stores,
            "progress": round(progress, 2),
            "created_at": round_record.created_at.isoformat() if round_record.created_at else None,
            "completed_at": round_record.completed_at.isoformat() if round_record.completed_at else None,
        }

    async def download_global_model(
        self,
        round_id: str,
    ) -> Dict[str, Any]:
        """
        下载全局模型

        Args:
            round_id: 训练轮次ID

        Returns:
            全局模型参数
        """
        store_id = self.require_store_id()

        async with get_db_session() as session:
            result = await session.execute(
                select(FLTrainingRound).where(FLTrainingRound.id == round_id)
            )
            round_record = result.scalar_one_or_none()

        if not round_record or not round_record.global_model_parameters:
            raise ValueError(f"全局模型尚未生成: {round_id}")

        logger.info(
            "Global model downloaded",
            store_id=store_id,
            round_id=round_id,
        )

        return {
            "round_id": round_id,
            "model_version": f"v{round_record.completed_at.strftime('%Y%m%d') if round_record.completed_at else 'unknown'}",
            "parameters": round_record.global_model_parameters,
            "download_time": datetime.now().isoformat(),
        }


class FederatedLearningCoordinator:
    """
    联邦学习协调器

    管理多个训练轮次和门店协调
    """

    def __init__(self):
        self.active_rounds: Dict[str, Dict[str, Any]] = {}

    async def start_training_round(
        self,
        model_type: ModelType,
        target_stores: List[str],
        config: Dict[str, Any],
    ) -> str:
        """
        启动训练轮次

        Args:
            model_type: 模型类型
            target_stores: 目标门店列表
            config: 训练配置

        Returns:
            训练轮次ID
        """
        service = FederatedLearningService()
        training_round = await service.create_training_round(model_type, config)

        round_id = training_round["round_id"]
        self.active_rounds[round_id] = training_round

        logger.info(
            "Training round started",
            round_id=round_id,
            model_type=model_type,
            num_target_stores=len(target_stores),
        )

        return round_id

    async def monitor_training_progress(
        self,
        round_id: str,
    ) -> Dict[str, Any]:
        """
        监控训练进度

        Args:
            round_id: 训练轮次ID

        Returns:
            进度信息
        """
        if round_id not in self.active_rounds:
            raise ValueError(f"Training round {round_id} not found")

        service = FederatedLearningService()
        status = await service.get_training_status(round_id)

        return status

    async def finalize_training_round(
        self,
        round_id: str,
    ) -> Dict[str, Any]:
        """
        完成训练轮次

        Args:
            round_id: 训练轮次ID

        Returns:
            最终结果
        """
        if round_id not in self.active_rounds:
            raise ValueError(f"Training round {round_id} not found")

        service = FederatedLearningService()

        # 聚合模型
        result = await service.aggregate_models(round_id)

        # 更新状态
        self.active_rounds[round_id]["status"] = "completed"
        self.active_rounds[round_id]["completed_at"] = datetime.now().isoformat()

        logger.info(
            "Training round finalized",
            round_id=round_id,
            num_stores=result["num_participating_stores"],
        )

        return result
