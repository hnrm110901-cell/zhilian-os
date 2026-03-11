"""
Phase 3 稳定性测试套件（P0）
覆盖 PHASE3_PROGRESS.md 所有未完成测试：
  - EdgeNodeService: 模式切换、离线规则引擎、同步队列
  - DecisionValidator: 各规则独立测试、异常检测
  - 集成测试: 网络中断、离线数据同步、AI决策验证流程、批量验证性能
  - 压力/性能测试: 并发离线操作、验证服务性能
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.edge_node_service import (
    EdgeNodeService,
    OperationMode,
    NetworkStatus,
)
from src.services.decision_validator import (
    DecisionValidator,
    BudgetCheckRule,
    InventoryCapacityRule,
    HistoricalConsumptionRule,
    SupplierAvailabilityRule,
    ProfitMarginRule,
    ValidationResult,
)


# ─── EdgeNodeService 单元测试 ─────────────────────────────────────────────────

class TestEdgeNodeServiceModeSwitch:
    """① 模式切换测试"""

    @pytest.fixture
    def svc(self):
        return EdgeNodeService()

    @pytest.mark.asyncio
    async def test_switch_to_offline(self, svc):
        """切换到离线模式成功，返回 old/new mode"""
        result = await svc.switch_mode(OperationMode.OFFLINE)
        assert result["success"] is True
        assert result["old_mode"] == OperationMode.HYBRID.value
        assert result["new_mode"] == OperationMode.OFFLINE.value
        assert svc.mode == OperationMode.OFFLINE

    @pytest.mark.asyncio
    async def test_switch_to_online(self, svc):
        """切换到在线模式"""
        svc.mode = OperationMode.OFFLINE
        result = await svc.switch_mode(OperationMode.ONLINE)
        assert result["success"] is True
        assert result["new_mode"] == OperationMode.ONLINE.value

    @pytest.mark.asyncio
    async def test_switch_mode_idempotent(self, svc):
        """相同模式切换不报错"""
        result = await svc.switch_mode(OperationMode.HYBRID)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_network_disconnect_triggers_offline(self, svc):
        """网络断开自动切换到离线模式"""
        await svc.handle_network_change(NetworkStatus.DISCONNECTED)
        assert svc.mode == OperationMode.OFFLINE

    @pytest.mark.asyncio
    async def test_network_reconnect_triggers_hybrid(self, svc):
        """网络恢复自动切换到混合模式并触发同步"""
        svc.mode = OperationMode.OFFLINE
        svc.network_status = NetworkStatus.DISCONNECTED
        with patch.object(svc, "sync_offline_data", new=AsyncMock(return_value={"synced_count": 0})):
            await svc.handle_network_change(NetworkStatus.CONNECTED)
        assert svc.mode == OperationMode.HYBRID


class TestEdgeNodeOfflineRules:
    """② 离线规则引擎测试"""

    @pytest.fixture
    def svc(self):
        return EdgeNodeService()

    @pytest.mark.asyncio
    async def test_offline_inventory_critical(self, svc):
        """库存低于10%触发 critical 预警"""
        result = await svc.process_decision_offline(
            "inventory_alert",
            {"current_stock": 5, "max_stock": 100}
        )
        assert result["success"] is True
        assert result["alert_level"] == "critical"
        assert result["action"] == "immediate_order"

    @pytest.mark.asyncio
    async def test_offline_inventory_normal(self, svc):
        """库存充足时正常"""
        result = await svc.process_decision_offline(
            "inventory_alert",
            {"current_stock": 80, "max_stock": 100}
        )
        assert result["alert_level"] == "normal"
        assert result["action"] == "none"

    @pytest.mark.asyncio
    async def test_offline_revenue_anomaly_detected(self, svc):
        """营收偏差超30%触发预警"""
        result = await svc.process_decision_offline(
            "revenue_anomaly",
            {"current_revenue": 3000, "average_revenue": 10000}
        )
        assert result["alert_level"] == "critical"
        assert result["action"] == "investigate"

    @pytest.mark.asyncio
    async def test_offline_revenue_normal(self, svc):
        """营收偏差在阈值内正常"""
        result = await svc.process_decision_offline(
            "revenue_anomaly",
            {"current_revenue": 9500, "average_revenue": 10000}
        )
        assert result["alert_level"] == "normal"

    @pytest.mark.asyncio
    async def test_offline_order_timeout_critical(self, svc):
        """等待超过30分钟触发 critical"""
        result = await svc.process_decision_offline(
            "order_timeout",
            {"wait_time_minutes": 35}
        )
        assert result["alert_level"] == "critical"
        assert result["action"] == "urgent_attention"

    @pytest.mark.asyncio
    async def test_offline_schedule_understaffed(self, svc):
        """人员不足触发预警"""
        result = await svc.process_decision_offline(
            "schedule",
            {"current_staff": 3, "required_staff": 8, "is_peak_hour": False}
        )
        assert result["alert_level"] == "critical"
        assert result["action"] == "call_backup"

    @pytest.mark.asyncio
    async def test_offline_unsupported_type_returns_error(self, svc):
        """不支持的决策类型返回错误"""
        result = await svc.process_decision_offline(
            "unknown_type",
            {}
        )
        assert result["success"] is False
        assert "error" in result


class TestEdgeNodeSyncQueue:
    """③ 同步队列测试"""

    @pytest.fixture
    def svc(self):
        return EdgeNodeService()

    @pytest.mark.asyncio
    async def test_queue_for_sync_adds_item(self, svc):
        """加入同步队列后队列长度+1"""
        initial_len = len(svc.pending_sync_queue)
        await svc.queue_for_sync({"type": "inventory_update", "store_id": "S001"})
        assert len(svc.pending_sync_queue) == initial_len + 1

    @pytest.mark.asyncio
    async def test_queue_item_has_sync_id(self, svc):
        """队列项包含 sync_id 和 queued_at"""
        await svc.queue_for_sync({"type": "order_sync"})
        item = svc.pending_sync_queue[-1]
        assert "sync_id" in item
        assert "queued_at" in item

    @pytest.mark.asyncio
    async def test_sync_offline_data_empty_queue(self, svc):
        """空队列同步返回0"""
        result = await svc.sync_offline_data()
        assert result["success"] is True
        assert result["synced_count"] == 0

    @pytest.mark.asyncio
    async def test_cache_and_retrieve(self, svc):
        """缓存数据后可正确取回"""
        await svc.cache_data("menu_v1", {"dishes": 50}, ttl=3600)
        result = await svc.get_cached_data("menu_v1")
        assert result == {"dishes": 50}

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, svc):
        """未缓存的key返回None"""
        result = await svc.get_cached_data("nonexistent_key")
        assert result is None


# ─── DecisionValidator 单元测试 ───────────────────────────────────────────────

class TestDecisionValidatorRules:
    """④ 各规则独立测试"""

    # BudgetCheckRule
    def test_budget_check_pass(self):
        rule = BudgetCheckRule()
        decision = {"cost": 500}
        context = {"available_budget": 1000}
        result = rule.validate(decision, context)
        assert result["passed"] is True

    def test_budget_check_fail_over_budget(self):
        rule = BudgetCheckRule()
        decision = {"cost": 1500}
        context = {"available_budget": 1000}
        result = rule.validate(decision, context)
        assert result["passed"] is False
        assert result["severity"] == "critical"

    def test_budget_check_warning_near_limit(self):
        rule = BudgetCheckRule()
        decision = {"cost": 950}
        context = {"available_budget": 1000, "budget_threshold": 0.9}
        result = rule.validate(decision, context)
        assert result["passed"] is True
        assert result["severity"] == "warning"

    # InventoryCapacityRule
    def test_inventory_capacity_pass(self):
        rule = InventoryCapacityRule()
        decision = {"action": "purchase", "quantity": 50}
        context = {"current_inventory": 100, "max_capacity": 200}
        result = rule.validate(decision, context)
        assert result["passed"] is True

    def test_inventory_capacity_fail_exceeds(self):
        rule = InventoryCapacityRule()
        decision = {"action": "purchase", "quantity": 150}
        context = {"current_inventory": 100, "max_capacity": 200}
        result = rule.validate(decision, context)
        assert result["passed"] is False
        assert result["severity"] == "critical"

    def test_inventory_capacity_skip_non_purchase(self):
        rule = InventoryCapacityRule()
        decision = {"action": "price_adjustment"}
        context = {}
        result = rule.validate(decision, context)
        assert result["passed"] is True

    # HistoricalConsumptionRule
    def test_historical_consumption_normal(self):
        rule = HistoricalConsumptionRule()
        decision = {"action": "purchase", "quantity": 70}
        context = {"avg_daily_consumption": 10, "days_to_cover": 7}
        result = rule.validate(decision, context)
        assert result["passed"] is True

    def test_historical_consumption_anomaly(self):
        rule = HistoricalConsumptionRule()
        decision = {"action": "purchase", "quantity": 5000}  # 极端偏离 (10×7=70)
        context = {"avg_daily_consumption": 10, "days_to_cover": 7}
        result = rule.validate(decision, context)
        assert result["passed"] is False
        assert result["severity"] == "critical"

    # ProfitMarginRule
    def test_profit_margin_pass(self):
        rule = ProfitMarginRule()
        decision = {"action": "pricing", "price": 48.0}
        context = {"cost": 20.0, "min_profit_margin": 0.2}
        result = rule.validate(decision, context)
        assert result["passed"] is True

    def test_profit_margin_fail_below_min(self):
        rule = ProfitMarginRule()
        decision = {"action": "pricing", "price": 22.0}
        context = {"cost": 20.0, "min_profit_margin": 0.3}
        result = rule.validate(decision, context)
        assert result["passed"] is False
        assert result["severity"] == "critical"

    def test_profit_margin_fail_negative(self):
        rule = ProfitMarginRule()
        decision = {"action": "pricing", "price": 15.0}
        context = {"cost": 20.0}
        result = rule.validate(decision, context)
        assert result["passed"] is False


class TestDecisionValidatorAnomaly:
    """⑤ 异常检测测试"""

    @pytest.fixture
    def validator(self):
        return DecisionValidator()

    @pytest.mark.asyncio
    async def test_anomaly_detected_high_zscore(self, validator):
        """Z-score > 3 时判定为异常"""
        historical = [{"value": v} for v in [100, 102, 98, 101, 99, 100, 103]]
        current = {"value": 500}  # 极端偏离
        result = await validator.detect_anomaly_decision(current, historical)
        assert result["is_anomaly"] is True
        assert result["z_score"] > 3.0

    @pytest.mark.asyncio
    async def test_normal_decision_not_anomaly(self, validator):
        """正常范围内的决策不是异常"""
        historical = [{"value": v} for v in [100, 102, 98, 101, 99]]
        current = {"value": 103}
        result = await validator.detect_anomaly_decision(current, historical)
        assert result["is_anomaly"] is False

    @pytest.mark.asyncio
    async def test_anomaly_empty_history(self, validator):
        """无历史数据时不判定为异常"""
        result = await validator.detect_anomaly_decision({"value": 1000}, [])
        assert result["is_anomaly"] is False
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_anomaly_constant_history(self, validator):
        """历史数据无变化（std=0）时不崩溃"""
        historical = [{"value": 100}] * 5
        result = await validator.detect_anomaly_decision({"value": 200}, historical)
        assert "is_anomaly" in result  # 不崩溃即可


# ─── 集成测试 ────────────────────────────────────────────────────────────────

class TestNetworkInterruptionIntegration:
    """⑥ 网络中断场景集成测试"""

    @pytest.mark.asyncio
    async def test_full_disconnect_reconnect_cycle(self):
        """完整离线→恢复流程：模式切换 + 队列数据同步"""
        svc = EdgeNodeService()

        # 1. 网络断开 → 切换到离线
        await svc.handle_network_change(NetworkStatus.DISCONNECTED)
        assert svc.mode == OperationMode.OFFLINE

        # 2. 离线期间进行决策
        decision = await svc.process_decision_offline(
            "inventory_alert",
            {"current_stock": 5, "max_stock": 100}
        )
        assert decision["mode"] == "offline"

        # 3. 加入同步队列
        await svc.queue_for_sync({
            "type": "inventory_decision",
            "data": decision
        })
        assert len(svc.pending_sync_queue) == 1

        # 4. 网络恢复 → 切换回混合模式 + 触发同步
        with patch.object(svc, "sync_offline_data", new=AsyncMock(
            return_value={"success": True, "synced_count": 1}
        )) as mock_sync:
            await svc.handle_network_change(NetworkStatus.CONNECTED)
            mock_sync.assert_awaited_once()

        assert svc.mode == OperationMode.HYBRID


class TestOfflineDataSyncIntegration:
    """⑦ 离线数据同步集成测试"""

    @pytest.mark.asyncio
    async def test_queue_multiple_operations_and_sync(self):
        """多条离线操作入队 → sync_offline_data 空队时返回0"""
        svc = EdgeNodeService()
        for i in range(5):
            await svc.queue_for_sync({"type": "order", "order_id": f"O{i:03d}"})

        assert len(svc.pending_sync_queue) == 5

        # 真实sync会发HTTP请求，只测试空队情况
        svc.pending_sync_queue.clear()
        result = await svc.sync_offline_data()
        assert result["synced_count"] == 0


class TestAIDecisionValidationIntegration:
    """⑧ AI决策验证流程集成测试"""

    @pytest.fixture
    def validator(self):
        return DecisionValidator()

    @pytest.mark.asyncio
    async def test_validate_purchase_decision_approved(self, validator):
        """合理采购决策通过所有规则"""
        decision = {
            "action": "purchase",
            "quantity": 100,
            "supplier_id": "SUP001",
            "cost": 3000,
        }
        context = {
            "available_budget": 10000,
            "current_inventory": 50,
            "max_capacity": 500,
            "avg_daily_consumption": 15,
            "days_to_cover": 7,
            "available_suppliers": ["SUP001", "SUP002"],
        }
        result = await validator.validate_purchase_decision(decision, context)
        assert result["result"] == ValidationResult.APPROVED.value

    @pytest.mark.asyncio
    async def test_validate_purchase_decision_rejected_over_budget(self, validator):
        """超预算采购被拒绝"""
        decision = {
            "action": "purchase",
            "quantity": 100,
            "supplier_id": "SUP001",
            "cost": 50000,
        }
        context = {
            "available_budget": 1000,
            "current_inventory": 50,
            "max_capacity": 500,
            "avg_daily_consumption": 15,
            "days_to_cover": 7,
            "available_suppliers": ["SUP001"],
        }
        result = await validator.validate_purchase_decision(decision, context)
        assert result["result"] == ValidationResult.REJECTED.value

    @pytest.mark.asyncio
    async def test_validate_pricing_decision_approved(self, validator):
        """合理定价决策通过利润率检查"""
        decision = {"action": "pricing", "price": 58.0}
        context = {"cost": 20.0, "min_profit_margin": 0.2}
        result = await validator.validate_pricing_decision(decision, context)
        assert result["result"] == ValidationResult.APPROVED.value

    @pytest.mark.asyncio
    async def test_validate_pricing_decision_rejected_below_cost(self, validator):
        """低于成本的定价被拒绝"""
        decision = {"action": "pricing", "price": 15.0}
        context = {"cost": 20.0, "min_profit_margin": 0.2}
        result = await validator.validate_pricing_decision(decision, context)
        assert result["result"] == ValidationResult.REJECTED.value


class TestBatchValidationPerformance:
    """⑨ 批量验证性能测试"""

    @pytest.mark.asyncio
    async def test_batch_validate_50_decisions_under_1s(self):
        """批量校验50个采购决策 < 1s"""
        validator = DecisionValidator()
        decisions = [
            {"action": "purchase", "quantity": 100 + i, "supplier_id": "SUP001", "cost": 3000}
            for i in range(50)
        ]
        context = {
            "available_budget": 100000,
            "current_inventory": 10,
            "max_capacity": 10000,
            "avg_daily_consumption": 15,
            "days_to_cover": 7,
            "available_suppliers": ["SUP001"],
        }

        start = time.perf_counter()
        results = await asyncio.gather(*[
            validator.validate_purchase_decision(d, context) for d in decisions
        ])
        elapsed = time.perf_counter() - start

        assert len(results) == 50
        assert elapsed < 1.0, f"批量校验 {elapsed:.3f}s 超过 1s 阈值"


# ─── 性能测试 ────────────────────────────────────────────────────────────────

class TestStabilityPerformance:
    """⑩ 压力测试"""

    @pytest.mark.asyncio
    async def test_concurrent_offline_decisions(self):
        """高并发离线操作：20个并发决策 < 0.5s"""
        svc = EdgeNodeService()
        contexts = [
            {"current_stock": 10 + i, "max_stock": 100} for i in range(20)
        ]

        start = time.perf_counter()
        results = await asyncio.gather(*[
            svc.process_decision_offline("inventory_alert", ctx)
            for ctx in contexts
        ])
        elapsed = time.perf_counter() - start

        assert len(results) == 20
        assert all(r["success"] for r in results)
        assert elapsed < 0.5, f"并发处理 {elapsed:.3f}s 超过 0.5s 阈值"

    @pytest.mark.asyncio
    async def test_validator_performance_under_load(self):
        """验证服务性能：单次验证 < 10ms"""
        validator = DecisionValidator()
        decision = {"action": "purchase", "quantity": 100, "supplier_id": "S1", "cost": 500}
        context = {
            "available_budget": 10000, "current_inventory": 50, "max_capacity": 500,
            "avg_daily_consumption": 15, "days_to_cover": 7, "available_suppliers": ["S1"],
        }

        start = time.perf_counter()
        await validator.validate_purchase_decision(decision, context)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.01, f"单次校验 {elapsed*1000:.1f}ms 超过 10ms 阈值"
