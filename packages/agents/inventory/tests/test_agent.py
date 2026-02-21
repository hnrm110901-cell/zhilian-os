"""
智能库存预警Agent单元测试
Unit tests for Intelligent Inventory Alert Agent
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
    PredictionResult
)


@pytest.fixture
def agent():
    """创建测试用的Agent实例"""
    return InventoryAgent(
        store_id="STORE001",
        pinzhi_adapter=None,  # 使用模拟数据
        alert_thresholds={
            "low_stock_ratio": 0.3,
            "critical_stock_ratio": 0.1,
            "expiring_soon_days": 7,
            "expiring_urgent_days": 3,
        }
    )


@pytest.mark.asyncio
async def test_monitor_inventory_all_categories(agent):
    """测试监控所有分类的库存"""
    inventory = await agent.monitor_inventory()

    assert len(inventory) > 0
    assert all("item_id" in item for item in inventory)
    assert all("current_stock" in item for item in inventory)
    assert all("status" in item for item in inventory)


@pytest.mark.asyncio
async def test_monitor_inventory_specific_category(agent):
    """测试监控特定分类的库存"""
    inventory = await agent.monitor_inventory(category="meat")

    assert len(inventory) > 0
    assert all(item["category"] == "meat" for item in inventory)


@pytest.mark.asyncio
async def test_analyze_inventory_status_sufficient(agent):
    """测试库存充足状态分析"""
    item: InventoryItem = {
        "item_id": "TEST001",
        "item_name": "测试物料",
        "category": "test",
        "unit": "kg",
        "current_stock": 100.0,
        "safe_stock": 50.0,
        "min_stock": 20.0,
        "max_stock": 150.0,
        "unit_cost": 1000,
        "supplier_id": "SUP001",
        "lead_time_days": 2,
        "expiration_date": None,
        "location": "仓库A"
    }

    status = agent._analyze_inventory_status(item)
    assert status == InventoryStatus.SUFFICIENT


@pytest.mark.asyncio
async def test_analyze_inventory_status_low(agent):
    """测试库存偏低状态分析"""
    item: InventoryItem = {
        "item_id": "TEST002",
        "item_name": "测试物料",
        "category": "test",
        "unit": "kg",
        "current_stock": 10.0,  # 低于安全库存的30%
        "safe_stock": 50.0,
        "min_stock": 20.0,
        "max_stock": 150.0,
        "unit_cost": 1000,
        "supplier_id": "SUP001",
        "lead_time_days": 2,
        "expiration_date": None,
        "location": "仓库A"
    }

    status = agent._analyze_inventory_status(item)
    assert status == InventoryStatus.LOW


@pytest.mark.asyncio
async def test_analyze_inventory_status_critical(agent):
    """测试库存严重不足状态分析"""
    item: InventoryItem = {
        "item_id": "TEST003",
        "item_name": "测试物料",
        "category": "test",
        "unit": "kg",
        "current_stock": 15.0,  # 低于最低库存
        "safe_stock": 50.0,
        "min_stock": 20.0,
        "max_stock": 150.0,
        "unit_cost": 1000,
        "supplier_id": "SUP001",
        "lead_time_days": 2,
        "expiration_date": None,
        "location": "仓库A"
    }

    status = agent._analyze_inventory_status(item)
    assert status == InventoryStatus.CRITICAL


@pytest.mark.asyncio
async def test_analyze_inventory_status_out_of_stock(agent):
    """测试缺货状态分析"""
    item: InventoryItem = {
        "item_id": "TEST004",
        "item_name": "测试物料",
        "category": "test",
        "unit": "kg",
        "current_stock": 0.0,
        "safe_stock": 50.0,
        "min_stock": 20.0,
        "max_stock": 150.0,
        "unit_cost": 1000,
        "supplier_id": "SUP001",
        "lead_time_days": 2,
        "expiration_date": None,
        "location": "仓库A"
    }

    status = agent._analyze_inventory_status(item)
    assert status == InventoryStatus.OUT_OF_STOCK


@pytest.mark.asyncio
async def test_predict_consumption_moving_average(agent):
    """测试移动平均预测"""
    result = await agent.predict_consumption(
        item_id="INV001",
        history_days=30,
        forecast_days=7,
        method=PredictionMethod.MOVING_AVERAGE
    )

    assert result["item_id"] == "INV001"
    assert result["predicted_consumption"] > 0
    assert 0 <= result["confidence"] <= 1
    assert result["method"] == PredictionMethod.MOVING_AVERAGE


@pytest.mark.asyncio
async def test_predict_consumption_weighted_average(agent):
    """测试加权平均预测"""
    result = await agent.predict_consumption(
        item_id="INV002",
        history_days=30,
        forecast_days=7,
        method=PredictionMethod.WEIGHTED_AVERAGE
    )

    assert result["item_id"] == "INV002"
    assert result["predicted_consumption"] > 0
    assert result["method"] == PredictionMethod.WEIGHTED_AVERAGE


@pytest.mark.asyncio
async def test_predict_consumption_linear_regression(agent):
    """测试线性回归预测"""
    result = await agent.predict_consumption(
        item_id="INV003",
        history_days=30,
        forecast_days=7,
        method=PredictionMethod.LINEAR_REGRESSION
    )

    assert result["item_id"] == "INV003"
    assert result["predicted_consumption"] >= 0
    assert result["method"] == PredictionMethod.LINEAR_REGRESSION


@pytest.mark.asyncio
async def test_predict_consumption_seasonal(agent):
    """测试季节性预测"""
    result = await agent.predict_consumption(
        item_id="INV004",
        history_days=30,
        forecast_days=7,
        method=PredictionMethod.SEASONAL
    )

    assert result["item_id"] == "INV004"
    assert result["predicted_consumption"] >= 0
    assert result["method"] == PredictionMethod.SEASONAL


@pytest.mark.asyncio
async def test_generate_restock_alerts(agent):
    """测试生成补货提醒"""
    alerts = await agent.generate_restock_alerts()

    assert isinstance(alerts, list)
    # 应该有一些低库存的物料需要补货
    assert len(alerts) > 0

    for alert in alerts:
        assert "alert_id" in alert
        assert "item_id" in alert
        assert "alert_level" in alert
        assert alert["alert_level"] in [
            AlertLevel.INFO,
            AlertLevel.WARNING,
            AlertLevel.URGENT,
            AlertLevel.CRITICAL
        ]


@pytest.mark.asyncio
async def test_generate_restock_alerts_by_category(agent):
    """测试按分类生成补货提醒"""
    alerts = await agent.generate_restock_alerts(category="dairy")

    assert isinstance(alerts, list)
    # 牛奶库存很低,应该有提醒
    assert len(alerts) > 0


@pytest.mark.asyncio
async def test_check_expiration(agent):
    """测试检查保质期预警"""
    alerts = await agent.check_expiration()

    assert isinstance(alerts, list)
    # 应该有一些即将过期的物料
    assert len(alerts) > 0

    for alert in alerts:
        assert "alert_id" in alert
        assert "item_id" in alert
        assert "expiration_date" in alert
        assert "days_until_expiration" in alert
        assert "alert_level" in alert
        assert "recommended_action" in alert


@pytest.mark.asyncio
async def test_check_expiration_urgent(agent):
    """测试紧急过期预警"""
    alerts = await agent.check_expiration()

    # 找到即将过期的物料(牛奶2天后过期)
    urgent_alerts = [
        a for a in alerts
        if a["days_until_expiration"] <= 3
    ]

    assert len(urgent_alerts) > 0
    assert all(
        a["alert_level"] in [AlertLevel.URGENT, AlertLevel.CRITICAL]
        for a in urgent_alerts
    )


@pytest.mark.asyncio
async def test_optimize_stock_levels(agent):
    """测试优化库存水平"""
    optimization = await agent.optimize_stock_levels(
        item_id="INV001",
        analysis_days=90
    )

    assert optimization["item_id"] == "INV001"
    assert "current_levels" in optimization
    assert "recommended_levels" in optimization
    assert "statistics" in optimization

    # 检查推荐的库存水平
    recommended = optimization["recommended_levels"]
    assert recommended["safe_stock"] > 0
    assert recommended["min_stock"] > 0
    assert recommended["max_stock"] > recommended["safe_stock"]


@pytest.mark.asyncio
async def test_get_inventory_report(agent):
    """测试获取库存综合报告"""
    report = await agent.get_inventory_report()

    assert report["store_id"] == "STORE001"
    assert "report_date" in report
    assert "summary" in report
    assert "inventory" in report
    assert "restock_alerts" in report
    assert "expiration_alerts" in report

    # 检查摘要信息
    summary = report["summary"]
    assert summary["total_items"] > 0
    assert summary["total_value_fen"] > 0
    assert "status_distribution" in summary


@pytest.mark.asyncio
async def test_get_inventory_report_by_category(agent):
    """测试按分类获取库存报告"""
    report = await agent.get_inventory_report(category="meat")

    assert report["category"] == "meat"
    assert all(
        item["category"] == "meat"
        for item in report["inventory"]
    )


def test_predict_moving_average_empty_history(agent):
    """测试空历史数据的移动平均预测"""
    result = agent._predict_moving_average([], 7)
    assert result == 0.0


def test_predict_weighted_average_empty_history(agent):
    """测试空历史数据的加权平均预测"""
    result = agent._predict_weighted_average([], 7)
    assert result == 0.0


def test_predict_linear_regression_insufficient_data(agent):
    """测试数据不足的线性回归预测"""
    history: List[ConsumptionRecord] = [
        {
            "date": datetime.now().date().isoformat(),
            "item_id": "TEST001",
            "quantity": 10.0,
            "reason": "sales"
        }
    ]
    result = agent._predict_linear_regression(history, 7)
    assert result == 0.0


def test_calculate_confidence_empty_history(agent):
    """测试空历史数据的置信度计算"""
    confidence = agent._calculate_confidence([])
    assert confidence == 0.5


def test_calculate_confidence_single_record(agent):
    """测试单条记录的置信度计算"""
    history: List[ConsumptionRecord] = [
        {
            "date": datetime.now().date().isoformat(),
            "item_id": "TEST001",
            "quantity": 10.0,
            "reason": "sales"
        }
    ]
    confidence = agent._calculate_confidence(history)
    assert 0 <= confidence <= 1


def test_generate_mock_inventory_all(agent):
    """测试生成所有分类的模拟库存"""
    inventory = agent._generate_mock_inventory()
    assert len(inventory) == 5


def test_generate_mock_inventory_by_category(agent):
    """测试生成特定分类的模拟库存"""
    inventory = agent._generate_mock_inventory(category="meat")
    assert len(inventory) == 1
    assert inventory[0]["category"] == "meat"


@pytest.mark.asyncio
async def test_concurrent_operations(agent):
    """测试并发操作"""
    import asyncio

    # 同时执行多个操作
    tasks = [
        agent.monitor_inventory(),
        agent.generate_restock_alerts(),
        agent.check_expiration()
    ]

    results = await asyncio.gather(*tasks)

    assert len(results) == 3
    assert isinstance(results[0], list)  # inventory
    assert isinstance(results[1], list)  # restock_alerts
    assert isinstance(results[2], list)  # expiration_alerts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
