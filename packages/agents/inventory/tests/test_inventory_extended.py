"""
库存Agent扩展测试
覆盖：补货建议生成逻辑、临期食材预警、库存盘点差异检测、异常输入处理
"""

import pytest
from datetime import datetime, timedelta
from src.agent import (
    InventoryAgent,
    AlertLevel,
    InventoryStatus,
    PredictionMethod,
    InventoryItem,
    ConsumptionRecord,
    RestockAlert,
    ExpirationAlert,
    PredictionResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    """创建测试用的Agent实例"""
    return InventoryAgent(
        store_id="STORE001",
        pinzhi_adapter=None,
        alert_thresholds={
            "low_stock_ratio": 0.3,
            "critical_stock_ratio": 0.1,
            "expiring_soon_days": 7,
            "expiring_urgent_days": 3,
        },
    )


# ── 补货建议生成逻辑 ─────────────────────────────────────────────────────────


class TestRestockAlertGeneration:
    """补货建议生成逻辑测试"""

    @pytest.mark.asyncio
    async def test_restock_alert_for_out_of_stock_item(self, agent):
        """缺货物料必须生成 CRITICAL 级别补货提醒"""
        alerts = await agent.generate_restock_alerts()
        # INV002 (青菜) current_stock=0 → OUT_OF_STOCK
        oos_alerts = [a for a in alerts if a["item_id"] == "INV002"]
        assert len(oos_alerts) > 0, "缺货物料必须生成补货提醒"
        assert oos_alerts[0]["alert_level"] == AlertLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_restock_alert_for_critical_stock_item(self, agent):
        """低于最低库存的物料必须生成 CRITICAL 级别补货提醒"""
        alerts = await agent.generate_restock_alerts()
        # INV005 (鲜牛奶) current_stock=5 < min_stock=10 → CRITICAL
        milk_alerts = [a for a in alerts if a["item_id"] == "INV005"]
        assert len(milk_alerts) > 0, "低于最低库存的物料必须生成补货提醒"
        assert milk_alerts[0]["alert_level"] == AlertLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_restock_recommended_quantity_positive(self, agent):
        """补货建议数量必须为正数"""
        alerts = await agent.generate_restock_alerts()
        for alert in alerts:
            assert alert["recommended_quantity"] >= 0, (
                f"物料 {alert['item_name']} 的建议补货量不能为负"
            )

    @pytest.mark.asyncio
    async def test_restock_alert_includes_stockout_date(self, agent):
        """补货提醒应包含预计缺货日期字段"""
        alerts = await agent.generate_restock_alerts()
        for alert in alerts:
            assert "estimated_stockout_date" in alert, "补货提醒必须包含预计缺货日期"

    @pytest.mark.asyncio
    async def test_sufficient_stock_no_alert(self, agent):
        """库存充足的物料不应生成补货提醒"""
        alerts = await agent.generate_restock_alerts()
        # INV003 (酱油) current_stock=100, safe_stock=30 → SUFFICIENT
        soy_alerts = [a for a in alerts if a["item_id"] == "INV003"]
        assert len(soy_alerts) == 0, "库存充足的物料不应生成补货提醒"


# ── 临期食材预警 ─────────────────────────────────────────────────────────────


class TestExpirationAlerts:
    """临期食材预警测试 — 三硬约束之一：食安合规"""

    @pytest.mark.asyncio
    async def test_expiring_soon_triggers_alert(self, agent):
        """即将过期的物料必须触发预警"""
        alerts = await agent.check_expiration()
        # INV005 (鲜牛奶) 1天后过期 → URGENT
        milk_alerts = [a for a in alerts if a["item_id"] == "INV005"]
        assert len(milk_alerts) > 0, "即将过期的物料必须触发预警"
        assert milk_alerts[0]["alert_level"] in [
            AlertLevel.URGENT, AlertLevel.CRITICAL
        ]

    @pytest.mark.asyncio
    async def test_expired_item_triggers_critical_alert(self, agent, monkeypatch):
        """已过期物料必须触发 CRITICAL 预警"""
        from src.agent import InventoryAgent

        # 注入一个已过期物料
        expired_item = {
            "item_id": "INV_EXPIRED",
            "item_name": "过期牛奶",
            "category": "dairy",
            "unit": "L",
            "current_stock": 10.0,
            "safe_stock": 20.0,
            "min_stock": 10.0,
            "max_stock": 50.0,
            "unit_cost": 1200,
            "supplier_id": None,
            "lead_time_days": 1,
            "expiration_date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
            "location": "",
        }

        def _fake_fetch(self, category=None):
            return [expired_item]

        monkeypatch.setattr(InventoryAgent, "_fetch_inventory_from_db", _fake_fetch)

        alerts = await agent.check_expiration()
        assert len(alerts) > 0, "已过期物料必须触发预警"
        assert alerts[0]["alert_level"] == AlertLevel.CRITICAL
        assert alerts[0]["days_until_expiration"] < 0
        assert "立即下架" in alerts[0]["recommended_action"]

    @pytest.mark.asyncio
    async def test_expiration_alerts_sorted_by_urgency(self, agent, monkeypatch):
        """过期预警应按紧急程度排序（天数最少的排前面）"""
        from src.agent import InventoryAgent

        items = [
            {
                "item_id": "FAR", "item_name": "远期",
                "category": "test", "unit": "kg",
                "current_stock": 10.0, "safe_stock": 20.0,
                "min_stock": 10.0, "max_stock": 50.0,
                "unit_cost": 1000, "supplier_id": None,
                "lead_time_days": 1,
                "expiration_date": (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),
                "location": "",
            },
            {
                "item_id": "NEAR", "item_name": "近期",
                "category": "test", "unit": "kg",
                "current_stock": 10.0, "safe_stock": 20.0,
                "min_stock": 10.0, "max_stock": 50.0,
                "unit_cost": 1000, "supplier_id": None,
                "lead_time_days": 1,
                "expiration_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                "location": "",
            },
        ]

        def _fake_fetch(self, category=None):
            return items

        monkeypatch.setattr(InventoryAgent, "_fetch_inventory_from_db", _fake_fetch)

        alerts = await agent.check_expiration()
        assert len(alerts) == 2
        assert alerts[0]["days_until_expiration"] <= alerts[1]["days_until_expiration"], (
            "过期预警应按紧急程度排序"
        )

    @pytest.mark.asyncio
    async def test_no_expiration_date_no_alert(self, agent, monkeypatch):
        """无保质期信息的物料不应触发过期预警"""
        from src.agent import InventoryAgent

        items = [
            {
                "item_id": "NO_EXP", "item_name": "无保质期物料",
                "category": "condiment", "unit": "瓶",
                "current_stock": 50.0, "safe_stock": 20.0,
                "min_stock": 10.0, "max_stock": 100.0,
                "unit_cost": 500, "supplier_id": None,
                "lead_time_days": 3,
                "expiration_date": None,  # 无保质期
                "location": "",
            },
        ]

        def _fake_fetch(self, category=None):
            return items

        monkeypatch.setattr(InventoryAgent, "_fetch_inventory_from_db", _fake_fetch)

        alerts = await agent.check_expiration()
        assert len(alerts) == 0, "无保质期的物料不应触发过期预警"


# ── 库存盘点差异检测 ─────────────────────────────────────────────────────────


class TestInventoryDiscrepancy:
    """库存盘点差异检测"""

    def test_inventory_status_boundary_out_of_stock(self, agent):
        """库存为0时状态应为 OUT_OF_STOCK"""
        item: InventoryItem = {
            "item_id": "BND_001", "item_name": "边界测试",
            "category": "test", "unit": "kg",
            "current_stock": 0.0, "safe_stock": 50.0,
            "min_stock": 20.0, "max_stock": 150.0,
            "unit_cost": 1000, "supplier_id": None,
            "lead_time_days": 2, "expiration_date": None,
            "location": "仓库A",
        }
        assert agent._analyze_inventory_status(item) == InventoryStatus.OUT_OF_STOCK

    def test_inventory_status_boundary_negative_stock(self, agent):
        """负库存也应为 OUT_OF_STOCK"""
        item: InventoryItem = {
            "item_id": "BND_002", "item_name": "负库存",
            "category": "test", "unit": "kg",
            "current_stock": -5.0, "safe_stock": 50.0,
            "min_stock": 20.0, "max_stock": 150.0,
            "unit_cost": 1000, "supplier_id": None,
            "lead_time_days": 2, "expiration_date": None,
            "location": "仓库A",
        }
        assert agent._analyze_inventory_status(item) == InventoryStatus.OUT_OF_STOCK

    def test_inventory_status_boundary_at_min(self, agent):
        """库存恰好等于最低库存时应为 CRITICAL"""
        item: InventoryItem = {
            "item_id": "BND_003", "item_name": "恰好最低",
            "category": "test", "unit": "kg",
            "current_stock": 20.0, "safe_stock": 50.0,
            "min_stock": 20.0, "max_stock": 150.0,
            "unit_cost": 1000, "supplier_id": None,
            "lead_time_days": 2, "expiration_date": None,
            "location": "仓库A",
        }
        assert agent._analyze_inventory_status(item) == InventoryStatus.CRITICAL

    def test_inventory_status_boundary_above_safe(self, agent):
        """库存远高于安全库存时应为 SUFFICIENT"""
        item: InventoryItem = {
            "item_id": "BND_004", "item_name": "充足库存",
            "category": "test", "unit": "kg",
            "current_stock": 100.0, "safe_stock": 50.0,
            "min_stock": 20.0, "max_stock": 150.0,
            "unit_cost": 1000, "supplier_id": None,
            "lead_time_days": 2, "expiration_date": None,
            "location": "仓库A",
        }
        assert agent._analyze_inventory_status(item) == InventoryStatus.SUFFICIENT


# ── 异常输入处理 ─────────────────────────────────────────────────────────────


class TestAbnormalInputHandling:
    """异常输入处理测试"""

    @pytest.mark.asyncio
    async def test_execute_unsupported_action(self, agent):
        """不支持的 action 应返回失败"""
        response = await agent.execute("fly_to_moon", {})
        assert response.success is False
        assert "Unsupported action" in response.error

    @pytest.mark.asyncio
    async def test_execute_missing_required_params(self, agent):
        """缺少必要参数应返回错误而非崩溃"""
        response = await agent.execute("predict_consumption", {})
        assert response.success is False
        assert response.error is not None

    def test_prediction_empty_history(self, agent):
        """空历史数据的预测应返回0"""
        assert agent._predict_moving_average([], 7) == 0.0
        assert agent._predict_weighted_average([], 7) == 0.0
        assert agent._predict_linear_regression([], 7) == 0.0

    def test_prediction_single_record(self, agent):
        """单条记录的线性回归应返回0"""
        history = [
            {"date": "2024-01-01", "item_id": "T1", "quantity": 10.0, "reason": "sales"}
        ]
        assert agent._predict_linear_regression(history, 7) == 0.0

    def test_confidence_stable_data(self, agent):
        """稳定数据的置信度应较高"""
        history = [
            {"date": f"2024-01-{i:02d}", "item_id": "T1", "quantity": 10.0, "reason": "sales"}
            for i in range(1, 11)
        ]
        confidence = agent._calculate_confidence(history)
        assert confidence > 0.9, "完全稳定的数据置信度应接近1"

    def test_confidence_volatile_data(self, agent):
        """波动数据的置信度应较低"""
        quantities = [10.0, 50.0, 5.0, 80.0, 15.0, 60.0, 8.0, 70.0]
        history = [
            {"date": f"2024-01-{i:02d}", "item_id": "T1", "quantity": q, "reason": "sales"}
            for i, q in enumerate(quantities, 1)
        ]
        confidence = agent._calculate_confidence(history)
        assert confidence < 0.5, "高波动数据的置信度应较低"

    @pytest.mark.asyncio
    async def test_get_supported_actions(self, agent):
        """支持的操作列表应完整"""
        actions = agent.get_supported_actions()
        expected = [
            "monitor_inventory", "predict_consumption",
            "generate_restock_alerts", "check_expiration",
            "optimize_stock_levels", "get_inventory_report",
        ]
        for action in expected:
            assert action in actions, f"缺少操作: {action}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
