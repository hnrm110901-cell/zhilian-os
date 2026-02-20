"""
联邦学习服务测试
Tests for Federated Learning Service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.federated_learning_service import (
    FederatedLearningService,
    DataIsolationManager,
    federated_learning_service,
    data_isolation_manager,
)


class TestFederatedLearningService:
    """FederatedLearningService测试类"""

    def test_init(self):
        """测试服务初始化"""
        service = FederatedLearningService()

        assert service.global_model is None
        assert service.local_models == {}
        assert service.training_rounds == 0
        assert service.participating_stores == []

    @pytest.mark.asyncio
    async def test_initialize_global_model_success(self):
        """测试初始化全局模型成功"""
        service = FederatedLearningService()

        result = await service.initialize_global_model(
            model_type="demand_forecast",
            model_config={"layers": 2, "units": 10}
        )

        assert result["success"] is True
        assert result["model_type"] == "demand_forecast"
        assert result["version"] == 1
        assert service.global_model is not None
        assert service.global_model["model_type"] == "demand_forecast"
        assert service.global_model["version"] == 1

    @pytest.mark.asyncio
    async def test_initialize_global_model_recommendation(self):
        """测试初始化推荐模型"""
        service = FederatedLearningService()

        result = await service.initialize_global_model(
            model_type="recommendation",
            model_config={"embedding_dim": 64}
        )

        assert result["success"] is True
        assert result["model_type"] == "recommendation"

    @pytest.mark.asyncio
    async def test_register_store_success(self):
        """测试注册门店成功"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        result = await service.register_store("store001")

        assert result["success"] is True
        assert result["store_id"] == "store001"
        assert "store001" in service.participating_stores
        assert "store001" in service.local_models
        assert service.local_models["store001"]["training_samples"] == 0

    @pytest.mark.asyncio
    async def test_register_store_duplicate(self):
        """测试重复注册门店"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        result1 = await service.register_store("store001")
        result2 = await service.register_store("store001")

        assert result1["success"] is True
        assert result2["success"] is True
        assert len(service.participating_stores) == 1

    @pytest.mark.asyncio
    async def test_register_multiple_stores(self):
        """测试注册多个门店"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        await service.register_store("store001")
        await service.register_store("store002")
        await service.register_store("store003")

        assert len(service.participating_stores) == 3
        assert len(service.local_models) == 3

    @pytest.mark.asyncio
    async def test_get_global_model_success(self):
        """测试获取全局模型成功"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})
        await service.register_store("store001")

        result = await service.get_global_model("store001")

        assert result["success"] is True
        assert result["model_type"] == "demand_forecast"
        assert result["version"] == 1
        assert "parameters" in result

    @pytest.mark.asyncio
    async def test_get_global_model_not_initialized(self):
        """测试获取未初始化的全局模型"""
        service = FederatedLearningService()

        result = await service.get_global_model("store001")

        assert result["success"] is False
        assert "未初始化" in result["error"]

    @pytest.mark.asyncio
    async def test_get_global_model_auto_register(self):
        """测试获取全局模型时自动注册"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        result = await service.get_global_model("store001")

        assert result["success"] is True
        assert "store001" in service.participating_stores

    @pytest.mark.asyncio
    async def test_upload_local_update_success(self):
        """测试上传本地更新成功"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})
        await service.register_store("store001")

        model_update = {
            "version": 1,
            "parameters": {
                "layer1_weights": [[0.1] * 10 for _ in range(10)],
                "layer1_bias": [0.1] * 10,
            }
        }
        training_metrics = {
            "samples": 100,
            "loss": 0.5,
            "accuracy": 0.85
        }

        result = await service.upload_local_update(
            "store001",
            model_update,
            training_metrics
        )

        assert result["success"] is True
        assert result["store_id"] == "store001"
        assert service.local_models["store001"]["training_samples"] == 100
        assert service.local_models["store001"]["training_loss"] == 0.5
        assert service.local_models["store001"]["training_accuracy"] == 0.85

    @pytest.mark.asyncio
    async def test_upload_local_update_unregistered_store(self):
        """测试未注册门店上传更新"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        result = await service.upload_local_update(
            "store999",
            {"version": 1, "parameters": {}},
            {"samples": 100}
        )

        assert result["success"] is False
        assert "未注册" in result["error"]

    @pytest.mark.asyncio
    async def test_aggregate_models_success(self):
        """测试模型聚合成功"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        # 注册并上传多个门店的更新
        for i in range(3):
            store_id = f"store00{i+1}"
            await service.register_store(store_id)
            await service.upload_local_update(
                store_id,
                {
                    "version": 1,
                    "parameters": {
                        "layer1_weights": [[0.1 * (i+1)] * 10 for _ in range(10)],
                        "layer1_bias": [0.1 * (i+1)] * 10,
                    }
                },
                {"samples": 100 * (i+1)}
            )

        result = await service.aggregate_models()

        assert result["success"] is True
        assert result["new_version"] == 2
        assert result["training_round"] == 1
        assert result["participating_stores"] == 3
        assert service.global_model["version"] == 2
        assert service.training_rounds == 1

    @pytest.mark.asyncio
    async def test_aggregate_models_no_local_models(self):
        """测试没有本地模型时聚合"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        result = await service.aggregate_models()

        assert result["success"] is False
        assert "没有本地模型" in result["error"]

    @pytest.mark.asyncio
    async def test_evaluate_global_model_success(self):
        """测试评估全局模型成功"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})

        test_data = {"samples": 50, "features": [[1, 2, 3]]}
        result = await service.evaluate_global_model(test_data)

        assert result["success"] is True
        assert result["model_version"] == 1
        assert "metrics" in result
        assert "accuracy" in result["metrics"]
        assert "precision" in result["metrics"]
        assert "recall" in result["metrics"]
        assert "f1_score" in result["metrics"]

    @pytest.mark.asyncio
    async def test_get_training_status(self):
        """测试获取训练状态"""
        service = FederatedLearningService()
        await service.initialize_global_model("demand_forecast", {})
        await service.register_store("store001")
        await service.register_store("store002")

        status = await service.get_training_status()

        assert status["training_rounds"] == 0
        assert status["global_model_version"] == 1
        assert status["participating_stores"] == 2
        assert status["local_models_count"] == 2
        assert len(status["stores"]) == 2

    @pytest.mark.asyncio
    async def test_get_training_status_no_model(self):
        """测试未初始化模型时获取状态"""
        service = FederatedLearningService()

        status = await service.get_training_status()

        assert status["training_rounds"] == 0
        assert status["global_model_version"] == 0
        assert status["participating_stores"] == 0

    def test_initialize_parameters(self):
        """测试初始化参数"""
        service = FederatedLearningService()

        params = service._initialize_parameters({"layers": 2})

        assert "layer1_weights" in params
        assert "layer1_bias" in params
        assert "layer2_weights" in params
        assert "layer2_bias" in params
        assert len(params["layer1_weights"]) == 10
        assert len(params["layer1_bias"]) == 10

    def test_federated_averaging_with_samples(self):
        """测试联邦平均算法（有训练样本）"""
        service = FederatedLearningService()

        local_models = {
            "store001": {
                "training_samples": 100,
                "parameters": {
                    "weights": [1.0, 2.0, 3.0],
                    "bias": [0.1, 0.2]
                }
            },
            "store002": {
                "training_samples": 200,
                "parameters": {
                    "weights": [2.0, 3.0, 4.0],
                    "bias": [0.2, 0.3]
                }
            }
        }

        aggregated = service._federated_averaging(local_models)

        # 加权平均: (100*[1,2,3] + 200*[2,3,4]) / 300 = [1.67, 2.67, 3.67]
        assert "weights" in aggregated
        assert "bias" in aggregated
        assert len(aggregated["weights"]) == 3
        assert len(aggregated["bias"]) == 2

    def test_federated_averaging_no_samples(self):
        """测试联邦平均算法（无训练样本）"""
        service = FederatedLearningService()

        local_models = {
            "store001": {
                "training_samples": 0,
                "parameters": {
                    "weights": [1.0, 2.0, 3.0]
                }
            },
            "store002": {
                "training_samples": 0,
                "parameters": {
                    "weights": [2.0, 3.0, 4.0]
                }
            }
        }

        aggregated = service._federated_averaging(local_models)

        # 无样本时返回第一个模型的参数
        assert aggregated["weights"] == [1.0, 2.0, 3.0]

    def test_federated_averaging_2d_arrays(self):
        """测试联邦平均算法（二维数组）"""
        service = FederatedLearningService()

        local_models = {
            "store001": {
                "training_samples": 100,
                "parameters": {
                    "matrix": [[1.0, 2.0], [3.0, 4.0]]
                }
            },
            "store002": {
                "training_samples": 100,
                "parameters": {
                    "matrix": [[2.0, 3.0], [4.0, 5.0]]
                }
            }
        }

        aggregated = service._federated_averaging(local_models)

        assert "matrix" in aggregated
        assert len(aggregated["matrix"]) == 2
        assert len(aggregated["matrix"][0]) == 2


class TestDataIsolationManager:
    """DataIsolationManager测试类"""

    def test_init(self):
        """测试初始化"""
        manager = DataIsolationManager()

        assert manager.store_data_boundaries == {}

    def test_register_store_boundary_success(self):
        """测试注册门店数据边界成功"""
        manager = DataIsolationManager()

        data_policy = {
            "allowed_fields": ["order_id", "amount"],
            "restricted_fields": ["customer_id", "phone"]
        }

        result = manager.register_store_boundary("store001", data_policy)

        assert result is True
        assert "store001" in manager.store_data_boundaries
        assert manager.store_data_boundaries["store001"]["data_policy"] == data_policy

    def test_register_multiple_store_boundaries(self):
        """测试注册多个门店数据边界"""
        manager = DataIsolationManager()

        manager.register_store_boundary("store001", {"policy": "strict"})
        manager.register_store_boundary("store002", {"policy": "moderate"})

        assert len(manager.store_data_boundaries) == 2

    def test_validate_data_access_same_store(self):
        """测试同一门店数据访问"""
        manager = DataIsolationManager()

        result = manager.validate_data_access("store001", "store001", "orders")

        assert result is True

    def test_validate_data_access_different_store(self):
        """测试跨门店数据访问"""
        manager = DataIsolationManager()

        result = manager.validate_data_access("store001", "store002", "orders")

        assert result is False

    def test_validate_data_access_different_data_types(self):
        """测试不同数据类型访问"""
        manager = DataIsolationManager()

        # 同一门店，不同数据类型都应该允许
        assert manager.validate_data_access("store001", "store001", "orders") is True
        assert manager.validate_data_access("store001", "store001", "inventory") is True
        assert manager.validate_data_access("store001", "store001", "customers") is True

    def test_anonymize_data_basic(self):
        """测试基本数据匿名化"""
        manager = DataIsolationManager()

        data = {
            "order_id": "ORD123",
            "customer_id": "CUST456",
            "phone": "13800138000",
            "amount": 100.0
        }

        anonymized = manager.anonymize_data(data)

        assert anonymized["order_id"] == "ORD123"  # 非敏感字段保持不变
        assert anonymized["amount"] == 100.0
        assert anonymized["customer_id"] != "CUST456"  # 敏感字段被哈希
        assert anonymized["phone"] != "13800138000"
        assert len(anonymized["customer_id"]) == 16  # 哈希后长度为16

    def test_anonymize_data_all_sensitive_fields(self):
        """测试所有敏感字段匿名化"""
        manager = DataIsolationManager()

        data = {
            "customer_id": "CUST123",
            "phone": "13800138000",
            "email": "test@example.com",
            "address": "123 Main St",
            "staff_id": "STAFF001",
            "name": "张三"
        }

        anonymized = manager.anonymize_data(data)

        # 所有敏感字段都应该被哈希
        for field in ["customer_id", "phone", "email", "address", "staff_id", "name"]:
            assert anonymized[field] != data[field]
            assert len(anonymized[field]) == 16

    def test_anonymize_data_no_sensitive_fields(self):
        """测试无敏感字段的数据匿名化"""
        manager = DataIsolationManager()

        data = {
            "order_id": "ORD123",
            "amount": 100.0,
            "status": "completed"
        }

        anonymized = manager.anonymize_data(data)

        assert anonymized == data  # 无敏感字段，数据不变

    def test_anonymize_data_different_levels(self):
        """测试不同匿名化级别"""
        manager = DataIsolationManager()

        data = {"customer_id": "CUST123", "phone": "13800138000"}

        anonymized_low = manager.anonymize_data(data, "low")
        anonymized_medium = manager.anonymize_data(data, "medium")
        anonymized_high = manager.anonymize_data(data, "high")

        # 当前实现中，不同级别的结果相同（都是哈希）
        assert anonymized_low["customer_id"] == anonymized_medium["customer_id"]
        assert anonymized_medium["customer_id"] == anonymized_high["customer_id"]

    def test_hash_value(self):
        """测试哈希值生成"""
        manager = DataIsolationManager()

        hash1 = manager._hash_value("test123")
        hash2 = manager._hash_value("test123")
        hash3 = manager._hash_value("test456")

        assert hash1 == hash2  # 相同输入产生相同哈希
        assert hash1 != hash3  # 不同输入产生不同哈希
        assert len(hash1) == 16


class TestGlobalInstances:
    """测试全局实例"""

    def test_federated_learning_service_instance(self):
        """测试federated_learning_service全局实例"""
        assert federated_learning_service is not None
        assert isinstance(federated_learning_service, FederatedLearningService)

    def test_data_isolation_manager_instance(self):
        """测试data_isolation_manager全局实例"""
        assert data_isolation_manager is not None
        assert isinstance(data_isolation_manager, DataIsolationManager)
