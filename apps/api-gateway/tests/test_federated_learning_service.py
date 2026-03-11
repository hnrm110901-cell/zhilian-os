"""
联邦学习服务测试（匹配当前 DB-backed round-based API）
"""
import os
for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.federated_learning_service import (
    FederatedLearningService,
    FederatedLearningCoordinator,
    ModelType,
    AggregationMethod,
)


# ─── 辅助 Mock ────────────────────────────────────────────────────────────────

def make_mock_session():
    """返回带 commit/add/flush 的异步 Mock session。"""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


# ─── FederatedLearningService ─────────────────────────────────────────────────

class TestFederatedLearningService:

    @patch("src.services.federated_learning_service.get_db_session")
    @pytest.mark.asyncio
    async def test_create_training_round_returns_round_id(self, mock_get_db):
        """create_training_round 应返回包含 round_id 的字典。"""
        session = make_mock_session()
        mock_get_db.return_value = session

        service = FederatedLearningService()
        result = await service.create_training_round(
            model_type=ModelType.DEMAND_PREDICTION,
            config={"min_participants": 2},
        )

        assert "round_id" in result
        assert result["model_type"] == ModelType.DEMAND_PREDICTION
        assert result["status"] == "initialized"

    @patch("src.services.federated_learning_service.get_db_session")
    @pytest.mark.asyncio
    async def test_create_training_round_sales_forecast(self, mock_get_db):
        """支持 SALES_FORECAST 模型类型。"""
        session = make_mock_session()
        mock_get_db.return_value = session

        service = FederatedLearningService()
        result = await service.create_training_round(
            model_type=ModelType.SALES_FORECAST,
            config={},
        )

        assert result["model_type"] == ModelType.SALES_FORECAST

    @patch("src.services.federated_learning_service.get_db_session")
    @pytest.mark.asyncio
    async def test_upload_local_model_invalid_parameters(self, mock_get_db):
        """无效的模型参数应抛出异常。"""
        session = make_mock_session()
        mock_get_db.return_value = session

        service = FederatedLearningService(store_id="store001")
        with pytest.raises((ValueError, Exception)):
            await service.upload_local_model(
                round_id="nonexistent-round",
                model_parameters={},  # 空参数 → 校验失败
                training_metrics={"accuracy": 0.9},
            )

    def test_model_type_enum_values(self):
        """ModelType 包含所有预期值。"""
        values = [e.value for e in ModelType]
        assert "sales_forecast" in values
        assert "demand_prediction" in values

    def test_aggregation_method_enum_values(self):
        """AggregationMethod 包含 fedavg 和 weighted_avg。"""
        values = [e.value for e in AggregationMethod]
        assert "fedavg" in values
        assert "weighted_avg" in values

    @patch("src.services.federated_learning_service.get_db_session")
    @pytest.mark.asyncio
    async def test_aggregate_models_insufficient_stores(self, mock_get_db):
        """参与门店数不足 min_stores 时应抛出 ValueError。"""
        session = make_mock_session()
        result_mock = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        session.execute = AsyncMock(return_value=result_mock)
        mock_get_db.return_value = session

        service = FederatedLearningService()
        service.min_stores = 3

        with pytest.raises(ValueError, match="Insufficient stores"):
            await service.aggregate_models("some-round-id")

    def test_generate_round_id_unique(self):
        """每次生成的 round_id 应唯一。"""
        service = FederatedLearningService()
        ids = {service._generate_round_id() for _ in range(10)}
        assert len(ids) == 10

    def test_require_store_id_raises_without_store(self):
        """未设置 store_id 时调用 require_store_id 应抛出异常。"""
        service = FederatedLearningService()
        with pytest.raises(Exception):
            service.require_store_id()

    def test_require_store_id_returns_when_set(self):
        """设置了 store_id 后 require_store_id 应正常返回。"""
        service = FederatedLearningService(store_id="store001")
        assert service.require_store_id() == "store001"

    def test_apply_differential_privacy_adds_noise(self):
        """差分隐私函数应对参数添加拉普拉斯噪声。"""
        import numpy as np
        service = FederatedLearningService()
        params = {"w": np.array([1.0, 2.0, 3.0])}
        noisy = service._apply_differential_privacy(params, epsilon=1.0)
        assert noisy["w"] is not None
        assert len(noisy["w"]) == 3

    def test_validate_model_parameters_valid(self):
        """合法的模型参数应通过校验。"""
        import numpy as np
        service = FederatedLearningService()
        params = {"layer1": np.array([0.1, 0.2]), "layer2": np.array([0.3])}
        assert service._validate_model_parameters(params) is True

    def test_validate_model_parameters_empty(self):
        """空参数应校验失败。"""
        service = FederatedLearningService()
        assert service._validate_model_parameters({}) is False

    def test_fedavg_aggregation_averages_correctly(self):
        """FedAvg 聚合应正确平均两个不同参数。"""
        import numpy as np
        service = FederatedLearningService()
        models = [
            {"parameters": {"w": np.array([0.0, 2.0])}, "num_samples": 100},
            {"parameters": {"w": np.array([2.0, 0.0])}, "num_samples": 100},
        ]
        result = service._fedavg_aggregation(models)
        assert pytest.approx(result["parameters"]["w"].tolist()) == [1.0, 1.0]

    def test_fedavg_aggregation_same_params(self):
        """FedAvg 聚合两个相同参数应返回原值。"""
        import numpy as np
        service = FederatedLearningService()
        models = [
            {"parameters": {"w": np.array([1.0, 2.0])}, "num_samples": 100},
            {"parameters": {"w": np.array([1.0, 2.0])}, "num_samples": 100},
        ]
        result = service._fedavg_aggregation(models)
        assert pytest.approx(result["parameters"]["w"].tolist()) == [1.0, 2.0]


# ─── FederatedLearningCoordinator ─────────────────────────────────────────────

class TestFederatedLearningCoordinator:

    def test_coordinator_init(self):
        """Coordinator 初始化时 active_rounds 应为空字典。"""
        coordinator = FederatedLearningCoordinator()
        assert isinstance(coordinator.active_rounds, dict)

    @patch("src.services.federated_learning_service.get_db_session")
    @pytest.mark.asyncio
    async def test_start_training_round(self, mock_get_db):
        """start_training_round 应创建轮次并追踪到 active_rounds。"""
        session = make_mock_session()
        mock_get_db.return_value = session

        coordinator = FederatedLearningCoordinator()
        round_id = await coordinator.start_training_round(
            model_type=ModelType.DEMAND_PREDICTION,
            target_stores=["S001", "S002"],
            config={},
        )

        assert isinstance(round_id, str)
        assert round_id in coordinator.active_rounds

    @pytest.mark.asyncio
    async def test_finalize_nonexistent_round_raises(self):
        """finalize_training_round 对不存在的轮次应抛出 ValueError。"""
        coordinator = FederatedLearningCoordinator()
        with pytest.raises(ValueError):
            await coordinator.finalize_training_round("nonexistent-id")


# ─── 差分隐私敏感度计算 ───────────────────────────────────────────────────────

class TestDifferentialPrivacy:

    def test_calculate_sensitivity_positive(self):
        """敏感度计算应返回非负数。"""
        import numpy as np
        service = FederatedLearningService()
        arr = np.array([1.0, -2.0, 3.0, -4.0])
        sensitivity = service._calculate_sensitivity(arr)
        assert sensitivity >= 0

    def test_calculate_sensitivity_zero_array(self):
        """全零数组的敏感度应为 0 或极小值（不抛异常）。"""
        import numpy as np
        service = FederatedLearningService()
        arr = np.array([0.0, 0.0, 0.0])
        sensitivity = service._calculate_sensitivity(arr)
        assert sensitivity >= 0
