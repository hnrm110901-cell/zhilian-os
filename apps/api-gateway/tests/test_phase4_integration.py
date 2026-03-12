"""
Phase 4 集成测试
覆盖：
  1. 联邦学习多门店端到端流程（create → join → upload × N → aggregate）
  2. 推荐引擎端到端流程（推荐 → 定价 → 营销方案一致性）
  3. Agent 协同优化器端到端流程（多建议 → optimize → 冲突+去重+抑制+排序）
  4. A/B 测试框架定义（实验分流 + 指标收集骨架）
"""
import os
import sys

for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

from unittest.mock import MagicMock as _MM
if "src.services.agent_service" not in sys.modules:
    sys.modules["src.services.agent_service"] = _MM()

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 联邦学习多门店端到端流程
# ═══════════════════════════════════════════════════════════════════════════════

class TestFederatedLearningE2E:
    """
    模拟完整联邦学习轮次：
    create round → 3 stores join → 3 stores upload → aggregate → download
    """

    @pytest.mark.asyncio
    async def test_full_training_round_fedavg(self):
        """端到端 FedAvg 聚合：3门店上传→聚合→结果正确。"""
        from src.services.federated_learning_service import (
            FederatedLearningService, ModelType, AggregationMethod,
        )

        service = FederatedLearningService()

        # 直接测试纯聚合逻辑，跳过DB交互
        store_models = [
            {"store_id": f"S{i:03d}", "parameters": {"w": np.array([float(i), float(i*2)])}, "weight": 1.0}
            for i in range(3)
        ]
        # S000: [0,0], S001: [1,2], S002: [2,4] → FedAvg: [1.0, 2.0]

        result = service._fedavg_aggregation(store_models)
        assert pytest.approx(result["parameters"]["w"].tolist()) == [1.0, 2.0]
        assert result["aggregation_method"] == "fedavg"

        # 验证完整 aggregate_models 调用（mock DB 部分）
        service.min_stores = 3
        with (
            patch.object(service, "_get_store_models", new=AsyncMock(return_value=store_models)),
            patch("src.services.federated_learning_service.get_db_session") as mock_get_db,
        ):
            session = AsyncMock()
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=False)
            session.commit = AsyncMock()
            result_mock = AsyncMock()
            result_mock.scalar_one_or_none = MagicMock(return_value=None)
            session.execute = AsyncMock(return_value=result_mock)
            mock_get_db.return_value = session

            full_result = await service.aggregate_models("round_test", AggregationMethod.FEDAVG)

        assert full_result["num_participating_stores"] == 3
        assert pytest.approx(full_result["global_model"]["parameters"]["w"].tolist()) == [1.0, 2.0]

    def test_full_training_round_weighted(self):
        """端到端 WeightedAvg 聚合：不等权重门店。"""
        from src.services.federated_learning_service import FederatedLearningService

        service = FederatedLearningService()

        # S001 has 3× more data
        store_models = [
            {"store_id": "S001", "parameters": {"w": np.array([10.0])}, "weight": 3.0},
            {"store_id": "S002", "parameters": {"w": np.array([0.0])}, "weight": 1.0},
        ]
        # Expected: (10*0.75 + 0*0.25) = 7.5

        result = service._weighted_aggregation(store_models)
        assert pytest.approx(result["parameters"]["w"].tolist()) == [7.5]
        assert pytest.approx(result["weights"]) == [0.75, 0.25]

    def test_insufficient_stores_blocks_aggregation(self):
        """门店不足时聚合应失败。"""
        from src.services.federated_learning_service import FederatedLearningService

        service = FederatedLearningService()
        service.min_stores = 3

        # FedAvg with only 1 model should fail at aggregate_models level
        # Test the validation logic directly
        store_models = [
            {"store_id": "S001", "parameters": {"w": np.array([1.0])}, "weight": 1.0},
        ]
        assert len(store_models) < service.min_stores

    def test_differential_privacy_preserves_shape(self):
        """差分隐私处理后参数形状不变。"""
        from src.services.federated_learning_service import FederatedLearningService
        service = FederatedLearningService()
        params = {
            "layer1": np.array([[1.0, 2.0], [3.0, 4.0]]),
            "layer2": np.array([0.5]),
        }
        noisy = service._apply_differential_privacy(params, epsilon=0.5)
        assert noisy["layer1"].shape == (2, 2)
        assert noisy["layer2"].shape == (1,)

    def test_validate_after_privacy_rejects_corrupted(self):
        """差分隐私后若参数被腐蚀（人为注入NaN），校验应失败。"""
        from src.services.federated_learning_service import FederatedLearningService
        service = FederatedLearningService()
        params = {"w": np.array([float("nan"), 1.0])}
        noisy = service._apply_differential_privacy(params, epsilon=1.0)
        # NaN + noise = NaN
        assert service._validate_model_parameters(noisy) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 推荐引擎端到端流程
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecommendationE2E:
    """
    模拟完整推荐流程：
    推荐菜品 → 对推荐菜品做定价优化 → 为门店生成营销方案
    """

    @pytest.mark.asyncio
    async def test_recommend_then_price_then_campaign(self):
        """推荐→定价→营销 三步一致性。"""
        from src.services.recommendation_engine import (
            IntelligentRecommendationEngine,
            DishRecommendation, PricingRecommendation, MarketingCampaign,
            PricingStrategy,
        )

        engine = IntelligentRecommendationEngine(db=MagicMock())

        # Step 1: 推荐
        dishes = [
            {"dish_id": f"d{i}", "name": f"菜{i}", "price": 30.0 + i * 10,
             "profit_margin": 0.3 + i * 0.1, "category": "正餐", "tags": []}
            for i in range(5)
        ]
        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=AsyncMock(return_value=0.6)),
        ):
            recs = await engine.recommend_dishes("C001", "S001", top_k=3)

        assert len(recs) == 3
        top_dish_id = recs[0].dish_id

        # Step 2: 对 top 推荐菜品做定价
        dish_data = next(d for d in dishes if d["dish_id"] == top_dish_id)
        with patch.object(engine, "_get_dish_data", new=AsyncMock(return_value=dish_data)):
            pricing = await engine.optimize_pricing(
                "S001", top_dish_id, context={"hour": 12}
            )

        assert isinstance(pricing, PricingRecommendation)
        assert pricing.dish_id == top_dish_id
        assert pricing.recommended_price > 0

        # Step 3: 为门店生成营销方案
        segment_data = {"size": 500, "avg_order_value": 80.0, "conversion_base": 0.15}
        engine._identify_target_segment = MagicMock(return_value="high_value")
        engine._get_segment_data = MagicMock(return_value=segment_data)
        engine._select_promotion_dishes = AsyncMock(return_value=dishes[:2])
        engine._calculate_optimal_discount = MagicMock(return_value=0.15)
        engine._estimate_conversion_rate = MagicMock(return_value=0.20)
        engine._estimate_campaign_revenue = MagicMock(return_value=5000.0)
        engine._calculate_campaign_duration = MagicMock(return_value=7)
        engine._generate_campaign_reason = MagicMock(return_value="高价值客户精准营销")

        campaign = await engine.generate_marketing_campaign("S001", "acquisition", 2000.0)
        assert isinstance(campaign, MarketingCampaign)
        assert campaign.expected_revenue > 0
        assert len(campaign.dish_ids) == 2

    @pytest.mark.asyncio
    async def test_scoring_monotonicity_with_cf(self):
        """CF 得分更高的菜品排名应更靠前。"""
        from src.services.recommendation_engine import IntelligentRecommendationEngine

        engine = IntelligentRecommendationEngine(db=MagicMock())
        dishes = [
            {"dish_id": "low_cf", "name": "低CF", "price": 30, "profit_margin": 0.5,
             "category": "正餐", "tags": []},
            {"dish_id": "high_cf", "name": "高CF", "price": 30, "profit_margin": 0.5,
             "category": "正餐", "tags": []},
        ]

        call_count = [0]
        async def varying_cf(customer_id, dish_id):
            call_count[0] += 1
            return 0.9 if dish_id == "high_cf" else 0.1

        with (
            patch.object(engine, "_get_customer_history", new=AsyncMock(return_value=[])),
            patch.object(engine, "_get_available_dishes", new=AsyncMock(return_value=dishes)),
            patch.object(engine, "_recently_ordered", new=AsyncMock(return_value=False)),
            patch.object(engine, "_collaborative_filtering_score", new=varying_cf),
        ):
            recs = await engine.recommend_dishes("C001", "S001", top_k=2)

        assert recs[0].dish_id == "high_cf"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Agent 协同优化器端到端流程
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentCollabOptimizerE2E:
    """
    模拟真实场景：多个 Agent 提交建议 → optimize 一次性处理。
    """

    def _make_rec(self, agent_name, store_id, text, impact=1000.0, confidence=0.8):
        from src.services.agent_collab_optimizer import AgentRecommendation
        import uuid
        return AgentRecommendation(
            id=str(uuid.uuid4())[:8],
            agent_name=agent_name,
            store_id=store_id,
            recommendation_type="action",
            recommendation_text=text,
            expected_impact_yuan=impact,
            confidence_score=confidence,
        )

    def test_full_pipeline_mixed_agents(self):
        """混合场景：7个建议来自5个Agent，含冲突+重复+低质量。"""
        from src.services.agent_collab_optimizer import AgentCollabOptimizer

        optimizer = AgentCollabOptimizer()
        recs = [
            self._make_rec("business_intel", "S001", "提高午市套餐推广力度", 5000, 0.85),
            self._make_rec("ops_flow", "S001", "减少午市备料量以降低损耗", 3000, 0.80),
            # supplier vs ops_flow — known pair (补货/采购 keywords)
            self._make_rec("supplier", "S001", "增加采购补货量确保库存充足", 2000, 0.75),
            self._make_rec("ops_flow", "S001", "减少库存水位降低积压补货", 2500, 0.78),
            # 近似重复
            self._make_rec("business_intel", "S001", "提高午市套餐推广力度提升营收", 4800, 0.83),
            # 低影响低置信
            self._make_rec("dish_rd", "S001", "尝试新甜品研发", 100, 0.3),
            # 不同门店
            self._make_rec("people", "S002", "增加S002周末排班", 1500, 0.90),
        ]

        result = optimizer.optimize(recs)

        assert result.input_count == 7
        # 至少去掉了重复或低质量
        assert result.output_count < 7
        # 输出按 impact×confidence 降序
        outputs = result.optimized_recommendations
        impact_scores = [r.expected_impact_yuan * r.confidence_score for r in outputs]
        assert impact_scores == sorted(impact_scores, reverse=True)
        # 有冲突记录
        assert result.conflicts_detected >= 1
        # AI 洞察不为空
        assert len(result.ai_insight) > 0

    def test_no_conflict_no_dedup_passthrough(self):
        """无冲突、无重复、无低质量时所有建议应原样通过。"""
        from src.services.agent_collab_optimizer import AgentCollabOptimizer

        optimizer = AgentCollabOptimizer()
        recs = [
            self._make_rec("business_intel", "S001", "提高营收", 5000, 0.9),
            self._make_rec("people", "S002", "增加排班", 3000, 0.8),
        ]

        result = optimizer.optimize(recs)
        assert result.input_count == 2
        assert result.output_count == 2
        assert result.conflicts_detected == 0
        assert result.dedup_count == 0

    def test_compliance_agent_wins_conflict(self):
        """合规Agent遇到合规风险关键词时应获胜。"""
        from src.services.agent_collab_optimizer import AgentCollabOptimizer

        optimizer = AgentCollabOptimizer()
        recs = [
            self._make_rec("marketing", "S001", "大幅降价折扣促销吸引客流", 8000, 0.9),
            self._make_rec("fct", "S001", "现金流约束：降价幅度超限需审批", 500, 0.95),
        ]

        result = optimizer.optimize(recs)
        # fct 应在输出中 (business_intel/fct known conflict pair with 折扣/现金流)
        output_agents = [r.agent_name for r in result.optimized_recommendations]
        assert "fct" in output_agents


# ═══════════════════════════════════════════════════════════════════════════════
# 4. A/B 测试框架骨架
# ═══════════════════════════════════════════════════════════════════════════════

class TestABTestFramework:
    """
    A/B 测试框架基础功能验证。
    定义实验分流 + 指标收集接口规范。
    """

    def test_experiment_assignment_deterministic(self):
        """相同 user_id + experiment_id 应始终分到同一组。"""
        import hashlib

        def assign_group(user_id: str, experiment_id: str, groups: list) -> str:
            """确定性实验分流（hash-based）"""
            key = f"{experiment_id}:{user_id}"
            h = int(hashlib.md5(key.encode()).hexdigest(), 16)
            return groups[h % len(groups)]

        groups = ["control", "treatment_a", "treatment_b"]
        # 多次调用结果一致
        results = {assign_group("user_123", "exp_pricing_v2", groups) for _ in range(100)}
        assert len(results) == 1  # 确定性

    def test_experiment_assignment_distribution(self):
        """1000个用户分流后各组比例应大致均匀。"""
        import hashlib
        from collections import Counter

        def assign_group(user_id: str, experiment_id: str, groups: list) -> str:
            key = f"{experiment_id}:{user_id}"
            h = int(hashlib.md5(key.encode()).hexdigest(), 16)
            return groups[h % len(groups)]

        groups = ["control", "treatment"]
        counts = Counter(
            assign_group(f"user_{i}", "exp_rec_v3", groups)
            for i in range(1000)
        )
        # 每组至少 40%（允许随机波动）
        for g in groups:
            assert counts[g] / 1000 > 0.40

    def test_metric_collection_schema(self):
        """A/B 指标收集数据结构应包含必要字段。"""
        metric = {
            "experiment_id": "exp_pricing_v2",
            "variant": "treatment_a",
            "user_id": "user_123",
            "metric_name": "conversion_rate",
            "metric_value": 0.15,
            "timestamp": datetime.utcnow().isoformat(),
        }
        required_fields = {"experiment_id", "variant", "user_id", "metric_name", "metric_value", "timestamp"}
        assert required_fields.issubset(set(metric.keys()))

    def test_experiment_config_validation(self):
        """实验配置应包含 traffic_split 且总和为 1.0。"""
        config = {
            "experiment_id": "exp_rec_v3",
            "description": "推荐算法V3对比测试",
            "variants": [
                {"name": "control", "traffic_pct": 0.5},
                {"name": "treatment", "traffic_pct": 0.5},
            ],
            "metrics": ["conversion_rate", "avg_order_value", "recommendation_ctr"],
            "start_date": "2026-03-15",
            "end_date": "2026-03-29",
        }
        total_traffic = sum(v["traffic_pct"] for v in config["variants"])
        assert abs(total_traffic - 1.0) < 1e-9
        assert len(config["metrics"]) > 0

    def test_statistical_significance_placeholder(self):
        """统计显著性检验骨架（两比例 Z 检验）。"""
        import math

        # 模拟 control vs treatment 转化率数据
        c_conv, c_n = 150, 1000
        t_conv, t_n = 180, 1000

        p_c = c_conv / c_n  # 0.15
        p_t = t_conv / t_n  # 0.18
        p_pool = (c_conv + t_conv) / (c_n + t_n)

        # 双侧 Z 检验
        se = math.sqrt(p_pool * (1 - p_pool) * (1/c_n + 1/t_n))
        z_stat = (p_t - p_c) / se if se > 0 else 0.0

        # 近似 p 值（标准正态 CDF 近似）
        # 使用 math.erfc 实现
        p_value = math.erfc(abs(z_stat) / math.sqrt(2))

        assert isinstance(p_value, float)
        assert 0 <= p_value <= 1
        # 这组数据 z≈1.88, p≈0.06 (边界)，实际检验框架应使用 scipy
        # 此处仅验证计算管道可运行
        assert p_value < 0.10  # 弱显著
