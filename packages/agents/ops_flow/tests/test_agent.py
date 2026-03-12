"""
OpsFlowAgent 单元测试 — Phase 13
纯函数 + Agent 类的隔离测试（sys.modules 注入，无 DB 依赖）
"""
import sys
import types
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock
import pytest


# ── sys.modules 注入：屏蔽 SQLAlchemy / DB 依赖 ───────────────────────────────

def _chainable_mock(*args, **kwargs):
    m = MagicMock()
    m.where = _chainable_mock
    m.order_by = _chainable_mock
    m.limit = _chainable_mock
    m.offset = _chainable_mock
    m.filter = _chainable_mock
    m.in_ = _chainable_mock
    return m


_sa = types.ModuleType("sqlalchemy")
_sa.select = _chainable_mock
_sa.and_ = lambda *a, **kw: MagicMock()
_sa.or_ = lambda *a, **kw: MagicMock()
_sa.desc = lambda x: MagicMock()
_sa.func = MagicMock()
_sa.text = MagicMock()
sys.modules.setdefault("sqlalchemy", _sa)

for _mod_name in [
    "sqlalchemy.ext", "sqlalchemy.ext.asyncio",
    "sqlalchemy.dialects", "sqlalchemy.dialects.postgresql",
]:
    _m = types.ModuleType(_mod_name)
    if _mod_name == "sqlalchemy.ext.asyncio":
        _m.AsyncSession = MagicMock
    sys.modules.setdefault(_mod_name, _m)

_src_db = types.ModuleType("src.db")
_src_db.get_db = MagicMock()
sys.modules.setdefault("src.db", _src_db)

_src_models = types.ModuleType("src.models")
sys.modules.setdefault("src.models", _src_models)

# 模拟 ops_flow_agent 模型类
_ops_models = types.ModuleType("src.models.ops_flow_agent")

class _FakeChainEvent:
    id = None; brand_id = None; store_id = None; event_type = None
    severity = "warning"; source_layer = None; source_record_id = None
    title = None; description = None; impact_yuan = None
    event_data = {}; linkage_triggered = False; linkage_count = 0
    resolved_at = None; created_at = datetime.now()
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)

class _FakeChainLinkage:
    id = None; trigger_event_id = None; trigger_layer = None
    target_layer = None; target_action = None; target_record_id = None
    result_summary = None; impact_yuan = None; executed_at = datetime.now()
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)

class _FakeOrderAnomaly:
    id = None; brand_id = None; store_id = None; anomaly_type = None
    time_period = "today"; current_value = None; baseline_value = None
    deviation_pct = None; estimated_revenue_loss_yuan = None
    root_cause = None; recommendations = None; ai_insight = None
    confidence = 0.80; chain_event_id = None; order_count = None
    affected_dish_ids = None; created_at = datetime.now()
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)

class _FakeInventoryAlert:
    id = None; brand_id = None; store_id = None; alert_type = None
    dish_id = None; dish_name = None; current_qty = None; safety_qty = None
    predicted_stockout_hours = None; restock_qty_recommended = None
    estimated_loss_yuan = None; risk_level = "medium"; recommendations = None
    ai_insight = None; confidence = 0.85; chain_event_id = None
    resolved = False; resolved_at = None; created_at = datetime.now()
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)

class _FakeQualityRecord:
    id = None; brand_id = None; store_id = None; dish_id = None
    dish_name = None; quality_score = None; status = None
    issues = None; suggestions = None; image_url = None
    ai_insight = None; confidence = None; chain_event_id = None
    alert_sent = False; created_at = datetime.now()
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)

class _FakeFlowDecision:
    id = None; brand_id = None; store_id = None; decision_title = None
    priority = "P2"; involves_order = False; involves_inventory = False
    involves_quality = False; estimated_revenue_impact_yuan = None
    estimated_cost_saving_yuan = None; recommendations = None
    reasoning = None; ai_insight = None; confidence = 0.80
    status = "pending"; accepted_at = None; created_at = datetime.now()
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)

class _FakeAgentLog:
    id = None; brand_id = None; agent_type = None; input_params = None
    output_summary = None; impact_yuan = None; duration_ms = None
    success = True; error_message = None; created_at = datetime.now()
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)

_ops_models.OpsChainEvent = _FakeChainEvent
_ops_models.OpsChainLinkage = _FakeChainLinkage
_ops_models.OpsOrderAnomaly = _FakeOrderAnomaly
_ops_models.OpsInventoryAlert = _FakeInventoryAlert
_ops_models.OpsQualityRecord = _FakeQualityRecord
_ops_models.OpsFlowDecision = _FakeFlowDecision
_ops_models.OpsFlowAgentLog = _FakeAgentLog
sys.modules.setdefault("src.models.ops_flow_agent", _ops_models)

# ── 动态加载 agent.py ─────────────────────────────────────────────────────────

import importlib.util, pathlib

_agent_path = pathlib.Path(__file__).parent.parent / "src" / "agent.py"
_spec = importlib.util.spec_from_file_location("ops_flow_agent_module", _agent_path)
_mod = importlib.util.module_from_spec(_spec)
_mod._LLM_ENABLED = False
_spec.loader.exec_module(_mod)

# 纯函数
classify_quality_status = _mod.classify_quality_status
classify_inventory_risk = _mod.classify_inventory_risk
compute_order_deviation = _mod.compute_order_deviation
detect_order_anomaly_type = _mod.detect_order_anomaly_type
estimate_revenue_loss = _mod.estimate_revenue_loss
estimate_inventory_loss = _mod.estimate_inventory_loss
build_chain_alert_title = _mod.build_chain_alert_title
build_ops_optimize_recommendations = _mod.build_ops_optimize_recommendations
compute_total_impact_yuan = _mod.compute_total_impact_yuan
build_ai_insight_text = _mod.build_ai_insight_text
QUALITY_FAIL_THRESHOLD = _mod.QUALITY_FAIL_THRESHOLD
QUALITY_WARN_THRESHOLD = _mod.QUALITY_WARN_THRESHOLD

# Agent 类
ChainAlertAgent = _mod.ChainAlertAgent
OrderAnomalyAgent = _mod.OrderAnomalyAgent
InventoryIntelAgent = _mod.InventoryIntelAgent
QualityInspectionAgent = _mod.QualityInspectionAgent
OpsOptimizeAgent = _mod.OpsOptimizeAgent


# ════════════════════════════════════════════════════════════════════════════
# 纯函数测试
# ════════════════════════════════════════════════════════════════════════════

class TestClassifyQualityStatus:
    def test_pass(self):
        assert classify_quality_status(QUALITY_WARN_THRESHOLD + 1) == "pass"

    def test_pass_at_boundary(self):
        assert classify_quality_status(QUALITY_WARN_THRESHOLD) == "pass"

    def test_warning(self):
        score = (QUALITY_FAIL_THRESHOLD + QUALITY_WARN_THRESHOLD) / 2
        assert classify_quality_status(score) == "warning"

    def test_fail(self):
        assert classify_quality_status(QUALITY_FAIL_THRESHOLD - 1) == "fail"

    def test_zero_score(self):
        assert classify_quality_status(0) == "fail"

    def test_perfect_score(self):
        assert classify_quality_status(100) == "pass"


class TestClassifyInventoryRisk:
    def test_critical_at_boundary(self):
        assert classify_inventory_risk(1.0) == "critical"

    def test_critical_below(self):
        assert classify_inventory_risk(0.5) == "critical"

    def test_high(self):
        assert classify_inventory_risk(1.5) == "high"

    def test_medium(self):
        assert classify_inventory_risk(3.0) == "medium"

    def test_low(self):
        assert classify_inventory_risk(10.0) == "low"

    def test_zero_stockout(self):
        assert classify_inventory_risk(0.0) == "critical"


class TestComputeOrderDeviation:
    def test_positive(self):
        assert compute_order_deviation(12.0, 10.0) == pytest.approx(20.0)

    def test_negative(self):
        assert compute_order_deviation(8.0, 10.0) == pytest.approx(-20.0)

    def test_zero_baseline(self):
        assert compute_order_deviation(5.0, 0.0) == 0.0

    def test_no_change(self):
        assert compute_order_deviation(10.0, 10.0) == 0.0


class TestDetectOrderAnomalyType:
    def test_detects_refund_spike(self):
        assert detect_order_anomaly_type({"refund_rate": 0.10}, {"refund_rate": 0.02}) == "refund_spike"

    def test_detects_revenue_drop(self):
        assert detect_order_anomaly_type({"revenue_yuan": 6000.0}, {"revenue_yuan": 10000.0}) == "revenue_drop"

    def test_no_anomaly(self):
        metrics = {"refund_rate": 0.021, "revenue_yuan": 9900.0}
        baseline = {"refund_rate": 0.02, "revenue_yuan": 10000.0}
        assert detect_order_anomaly_type(metrics, baseline) is None

    def test_missing_key_skipped(self):
        assert detect_order_anomaly_type({}, {"refund_rate": 0.02}) is None

    def test_returns_worst(self):
        # refund_rate 偏差400%，revenue 偏差40% → 选 refund_spike
        result = detect_order_anomaly_type(
            {"refund_rate": 0.10, "revenue_yuan": 7000.0},
            {"refund_rate": 0.02, "revenue_yuan": 10000.0},
        )
        assert result == "refund_spike"


class TestEstimateRevenueLoss:
    def test_revenue_drop_loss(self):
        assert estimate_revenue_loss("revenue_drop", 7000, 10000, 10000) == pytest.approx(3000.0)

    def test_revenue_no_loss_when_higher(self):
        assert estimate_revenue_loss("revenue_drop", 11000, 10000, 10000) == 0.0

    def test_refund_spike_loss(self):
        # extra_rate=0.06, loss=10000*0.06=600
        assert estimate_revenue_loss("refund_spike", 0.08, 0.02, 10000) == pytest.approx(600.0)

    def test_avg_order_drop_loss(self):
        # drop_rate=0.20, loss=10000*0.20*0.5=1000
        assert estimate_revenue_loss("avg_order_drop", 80, 100, 10000) == pytest.approx(1000.0)

    def test_unknown_type_zero(self):
        assert estimate_revenue_loss("unknown_type", 0.5, 0.3, 10000) == 0.0


class TestEstimateInventoryLoss:
    def test_basic(self):
        # shortfall=10, loss=10*50*0.3=150
        assert estimate_inventory_loss(10, 20, 50.0) == pytest.approx(150.0)

    def test_above_safety_no_loss(self):
        assert estimate_inventory_loss(30, 20, 50.0) == 0.0

    def test_zero_stock(self):
        assert estimate_inventory_loss(0, 20, 50.0) == pytest.approx(300.0)


class TestBuildChainAlertTitle:
    def test_critical_order(self):
        t = build_chain_alert_title("order_anomaly", "S001", "critical")
        assert "🔴 紧急" in t and "S001" in t and "订单异常" in t

    def test_warning_inventory(self):
        t = build_chain_alert_title("inventory_low", "S002", "warning")
        assert "🟡 预警" in t and "库存不足" in t

    def test_info_quality(self):
        t = build_chain_alert_title("quality_fail", "S003", "critical")
        assert "质检失败" in t


class TestBuildOpsOptimizeRecommendations:
    def test_empty_inputs(self):
        assert build_ops_optimize_recommendations([], [], []) == []

    def test_order_anomaly_rec(self):
        recs = build_ops_optimize_recommendations(
            [{"anomaly_type": "refund_spike", "estimated_revenue_loss_yuan": 800}], [], []
        )
        assert len(recs) == 1
        assert recs[0]["layer"] == "order"
        assert recs[0]["expected_yuan"] == 800

    def test_inventory_alert_rec(self):
        recs = build_ops_optimize_recommendations(
            [], [{"dish_name": "番茄炒蛋", "restock_qty_recommended": 50,
                  "estimated_loss_yuan": 300, "risk_level": "high"}], []
        )
        assert recs[0]["layer"] == "inventory"
        assert "番茄炒蛋" in recs[0]["action"]

    def test_critical_inventory_has_urgent_timeline(self):
        recs = build_ops_optimize_recommendations(
            [], [{"dish_name": "招牌菜", "restock_qty_recommended": 100,
                  "estimated_loss_yuan": 2000, "risk_level": "critical"}], []
        )
        assert recs[0]["timeline"] == "4小时内"

    def test_quality_fail_rec(self):
        recs = build_ops_optimize_recommendations([], [], [{"dish_name": "红烧肉"}])
        assert recs[0]["layer"] == "quality"
        assert recs[0]["priority"] == "P0"

    def test_sorted_by_priority(self):
        recs = build_ops_optimize_recommendations(
            [{"anomaly_type": "refund_spike", "estimated_revenue_loss_yuan": 100}],
            [],
            [{"dish_name": "菜A"}],
        )
        priorities = [r["priority"] for r in recs]
        assert priorities == sorted(priorities)


class TestComputeTotalImpactYuan:
    def test_sum(self):
        recs = [{"expected_yuan": 100.0}, {"expected_yuan": 250.5}, {"expected_yuan": 0.0}]
        assert compute_total_impact_yuan(recs) == pytest.approx(350.5)

    def test_empty(self):
        assert compute_total_impact_yuan([]) == 0.0


class TestBuildAiInsightText:
    def test_all_normal(self):
        assert "正常" in build_ai_insight_text(0, 0, 0, 0)

    def test_all_issues(self):
        text = build_ai_insight_text(2, 3, 1, 1500)
        assert "订单异常" in text
        assert "库存不足" in text
        assert "质检不合格" in text

    def test_only_inventory(self):
        text = build_ai_insight_text(0, 2, 0, 200)
        assert "库存不足" in text


# ════════════════════════════════════════════════════════════════════════════
# Agent 类测试
# ════════════════════════════════════════════════════════════════════════════

def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    # execute 返回空列表（默认无历史记录）
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.one.return_value = (0, None)
    mock_result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=mock_result)
    return db


class TestChainAlertAgent:
    @pytest.mark.asyncio
    async def test_trigger_order_creates_2_linkages(self):
        agent = ChainAlertAgent()
        result = await agent.trigger_chain(
            db=_make_db(), brand_id="b1", store_id="s1",
            source_layer="order", event_type="order_anomaly",
            severity="warning", source_record_id="rec1",
            title="订单告警", impact_yuan=300.0,
        )
        assert result["linkage_count"] == 2
        target_layers = {lk["target_layer"] for lk in result["linkages"]}
        assert target_layers == {"inventory", "quality"}

    @pytest.mark.asyncio
    async def test_trigger_inventory_creates_2_linkages(self):
        agent = ChainAlertAgent()
        result = await agent.trigger_chain(
            db=_make_db(), brand_id="b1", store_id="s1",
            source_layer="inventory", event_type="inventory_low",
            severity="critical", source_record_id="rec2",
            title="库存告警", impact_yuan=0.0,
        )
        layers = {lk["target_layer"] for lk in result["linkages"]}
        assert layers == {"order", "quality"}

    @pytest.mark.asyncio
    async def test_trigger_quality_creates_2_linkages(self):
        agent = ChainAlertAgent()
        result = await agent.trigger_chain(
            db=_make_db(), brand_id="b1", store_id="s1",
            source_layer="quality", event_type="quality_fail",
            severity="critical", source_record_id="rec3",
            title="质检失败", impact_yuan=0.0,
        )
        layers = {lk["target_layer"] for lk in result["linkages"]}
        assert layers == {"inventory", "order"}

    @pytest.mark.asyncio
    async def test_event_id_is_uuid(self):
        agent = ChainAlertAgent()
        result = await agent.trigger_chain(
            db=_make_db(), brand_id="b1", store_id="s1",
            source_layer="order", event_type="order_anomaly",
            severity="info", source_record_id="r0",
            title="测试", impact_yuan=0.0,
        )
        # event_id should be a valid UUID string
        uid = result["event_id"]
        assert len(uid) == 36 and uid.count("-") == 4


class TestOrderAnomalyAgent:
    @pytest.mark.asyncio
    async def test_no_anomaly(self):
        agent = OrderAnomalyAgent()
        result = await agent.detect_anomaly(
            db=_make_db(), brand_id="b1", store_id="s1",
            metrics={"refund_rate": 0.02},
            baseline={"refund_rate": 0.02},
        )
        assert result["anomaly_detected"] is False

    @pytest.mark.asyncio
    async def test_anomaly_detected_with_chain(self):
        agent = OrderAnomalyAgent()
        result = await agent.detect_anomaly(
            db=_make_db(), brand_id="b1", store_id="s1",
            metrics={"refund_rate": 0.10},
            baseline={"refund_rate": 0.02},
            daily_revenue_yuan=10000,
        )
        assert result["anomaly_detected"] is True
        assert result["anomaly_type"] == "refund_spike"
        assert result["chain_event_id"] is not None
        assert len(result["chain_linkages"]) == 2
        assert result["estimated_revenue_loss_yuan"] > 0

    @pytest.mark.asyncio
    async def test_critical_on_large_deviation(self):
        agent = OrderAnomalyAgent()
        result = await agent.detect_anomaly(
            db=_make_db(), brand_id="b1", store_id="s1",
            metrics={"refund_rate": 0.15},
            baseline={"refund_rate": 0.02},
        )
        assert result["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_warning_on_moderate_deviation(self):
        # deviation = (0.025-0.02)/0.02 * 100 = 25% → anomaly detected, below 50% → warning
        agent = OrderAnomalyAgent()
        result = await agent.detect_anomaly(
            db=_make_db(), brand_id="b1", store_id="s1",
            metrics={"refund_rate": 0.025},
            baseline={"refund_rate": 0.02},
        )
        assert result["anomaly_detected"] is True
        assert result["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_revenue_drop_anomaly(self):
        agent = OrderAnomalyAgent()
        result = await agent.detect_anomaly(
            db=_make_db(), brand_id="b1", store_id="s1",
            metrics={"revenue_yuan": 5000.0},
            baseline={"revenue_yuan": 10000.0},
            daily_revenue_yuan=10000,
        )
        assert result["anomaly_detected"] is True
        assert result["anomaly_type"] == "revenue_drop"
        assert result["estimated_revenue_loss_yuan"] == pytest.approx(5000.0)


class TestInventoryIntelAgent:
    @pytest.mark.asyncio
    async def test_zero_consumption_no_alert(self):
        agent = InventoryIntelAgent()
        result = await agent.check_stock(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id="d1", dish_name="鱼香肉丝",
            current_qty=50, safety_qty=20, hourly_consumption=0.0,
        )
        assert result["alert"] is False

    @pytest.mark.asyncio
    async def test_abundant_stock_no_alert(self):
        agent = InventoryIntelAgent()
        result = await agent.check_stock(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id="d1", dish_name="番茄蛋",
            current_qty=200, safety_qty=20, hourly_consumption=2.0,
        )
        assert result["alert"] is False
        assert result["risk_level"] == "low"

    @pytest.mark.asyncio
    async def test_critical_triggers_chain(self):
        agent = InventoryIntelAgent()
        result = await agent.check_stock(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id="d1", dish_name="招牌菜",
            current_qty=1, safety_qty=20, hourly_consumption=5.0,
        )
        assert result["alert"] is True
        assert result["risk_level"] == "critical"
        assert result["chain_event_id"] is not None
        assert len(result["chain_linkages"]) == 2

    @pytest.mark.asyncio
    async def test_restock_qty_calculated(self):
        agent = InventoryIntelAgent()
        result = await agent.check_stock(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id="d1", dish_name="招牌菜",
            current_qty=5, safety_qty=20, hourly_consumption=3.0,
        )
        # restock = max(0, 20-5 + 3*8) = max(0, 15+24) = 39
        assert result.get("restock_qty_recommended", 0) > 0

    @pytest.mark.asyncio
    async def test_batch_check(self):
        agent = InventoryIntelAgent()
        items = [
            {"dish_id": "d1", "dish_name": "菜A", "current_qty": 1,
             "safety_qty": 20, "hourly_consumption": 5.0},
            {"dish_id": "d2", "dish_name": "菜B", "current_qty": 100,
             "safety_qty": 20, "hourly_consumption": 1.0},
        ]
        result = await agent.batch_check(db=_make_db(), brand_id="b1", store_id="s1", items=items)
        assert result["total_checked"] == 2
        assert result["alert_count"] == 1
        assert result["ok_count"] == 1
        assert result["total_estimated_loss_yuan"] >= 0


class TestQualityInspectionAgent:
    @pytest.mark.asyncio
    async def test_pass_no_chain(self):
        agent = QualityInspectionAgent()
        result = await agent.inspect(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id="d1", dish_name="红烧肉", quality_score=95.0,
        )
        assert result["status"] == "pass"
        assert result["chain_event_id"] is None

    @pytest.mark.asyncio
    async def test_fail_triggers_chain(self):
        agent = QualityInspectionAgent()
        result = await agent.inspect(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id="d1", dish_name="白切鸡", quality_score=60.0,
            issues=[{"severity": "high", "description": "颜色异常"}],
        )
        assert result["status"] == "fail"
        assert result["chain_event_id"] is not None
        assert len(result["chain_linkages"]) == 2

    @pytest.mark.asyncio
    async def test_warning_triggers_chain(self):
        agent = QualityInspectionAgent()
        score = (QUALITY_FAIL_THRESHOLD + QUALITY_WARN_THRESHOLD) / 2
        result = await agent.inspect(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id=None, dish_name="炒青菜", quality_score=score,
        )
        assert result["status"] == "warning"
        assert result["chain_event_id"] is not None

    @pytest.mark.asyncio
    async def test_issues_generate_suggestions(self):
        agent = QualityInspectionAgent()
        result = await agent.inspect(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id=None, dish_name="卤猪蹄", quality_score=50.0,
            issues=[{"severity": "high", "description": "口感过硬"}],
        )
        assert len(result["suggestions"]) > 0

    @pytest.mark.asyncio
    async def test_no_issues_still_has_suggestions(self):
        agent = QualityInspectionAgent()
        result = await agent.inspect(
            db=_make_db(), brand_id="b1", store_id="s1",
            dish_id=None, dish_name="麻辣烫", quality_score=50.0,
        )
        assert len(result["suggestions"]) >= 1


class TestOpsOptimizeAgent:
    @pytest.mark.asyncio
    async def test_empty_data_returns_zero_impact(self):
        agent = OpsOptimizeAgent()
        result = await agent.generate_decision(
            db=_make_db(), brand_id="b1", store_id="s1", lookback_hours=24
        )
        assert result["total_estimated_impact_yuan"] == 0.0
        assert result["order_anomaly_count"] == 0
        assert result["inventory_alert_count"] == 0
        assert result["quality_fail_count"] == 0

    @pytest.mark.asyncio
    async def test_decision_has_required_fields(self):
        agent = OpsOptimizeAgent()
        result = await agent.generate_decision(
            db=_make_db(), brand_id="b1", store_id="s1", lookback_hours=24
        )
        for field in ["decision_id", "priority", "title", "recommendations",
                      "ai_insight", "confidence"]:
            assert field in result

    @pytest.mark.asyncio
    async def test_priority_is_valid(self):
        agent = OpsOptimizeAgent()
        result = await agent.generate_decision(
            db=_make_db(), brand_id="b1", store_id="s1", lookback_hours=24
        )
        assert result["priority"] in ("P0", "P1", "P2", "P3")
