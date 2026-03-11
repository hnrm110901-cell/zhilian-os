"""
供应商管理 Agent 单元测试 — Phase 11
运行：python3 -m pytest packages/agents/supplier/tests/test_agent.py -q
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/zhilian")
os.environ.setdefault("SECRET_KEY",   "test-secret-key")
os.environ.setdefault("REDIS_URL",    "redis://localhost:6379")

import sys
import enum
import types
import importlib
import uuid
from pathlib import Path
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

agent_root = Path(__file__).resolve().parent.parent
repo_root  = agent_root.parent.parent.parent
_api_src   = repo_root / "apps" / "api-gateway"
for p in [str(agent_root), str(repo_root), str(_api_src)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ─────────────────────────────────────────────────────────────────────────────
# 真实 Enum（与 production 一致）
# ─────────────────────────────────────────────────────────────────────────────

class SupplierTierEnum(str, enum.Enum):
    STRATEGIC = "strategic"; PREFERRED = "preferred"; APPROVED = "approved"
    PROBATION = "probation"; SUSPENDED = "suspended"

class QuoteStatusEnum(str, enum.Enum):
    DRAFT = "draft"; SUBMITTED = "submitted"; ACCEPTED = "accepted"
    REJECTED = "rejected"; EXPIRED = "expired"

class ContractStatusEnum(str, enum.Enum):
    DRAFT = "draft"; ACTIVE = "active"; EXPIRING = "expiring"
    EXPIRED = "expired"; TERMINATED = "terminated"

class DeliveryStatusEnum(str, enum.Enum):
    PENDING = "pending"; IN_TRANSIT = "in_transit"; DELIVERED = "delivered"
    REJECTED = "rejected"; PARTIAL = "partial"

class RiskLevelEnum(str, enum.Enum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"

class AlertTypeEnum(str, enum.Enum):
    CONTRACT_EXPIRING  = "contract_expiring"; PRICE_SPIKE = "price_spike"
    DELIVERY_DELAY     = "delivery_delay";    QUALITY_ISSUE = "quality_issue"
    SUPPLY_SHORTAGE    = "supply_shortage";   SINGLE_SOURCE_RISK = "single_source_risk"

class SupplierAgentTypeEnum(str, enum.Enum):
    PRICE_COMPARISON = "price_comparison"; SUPPLIER_RATING = "supplier_rating"
    AUTO_SOURCING = "auto_sourcing"; CONTRACT_RISK = "contract_risk"
    SUPPLY_CHAIN_RISK = "supply_chain_risk"

# ─────────────────────────────────────────────────────────────────────────────
# 构建假 src.models.supplier_agent 模块
# ─────────────────────────────────────────────────────────────────────────────

def _make_model_class(name: str):
    """创建支持 ORM 列属性访问（Column == value）和实例化的 stub 模型类"""
    class _Col:
        """支持 == / >= / <= / in_() 比较（返回 MagicMock，供 and_() 消费）"""
        def __eq__(self, other): return MagicMock()
        def __ge__(self, other): return MagicMock()
        def __le__(self, other): return MagicMock()
        def __ne__(self, other): return MagicMock()
        def in_(self, other):    return MagicMock()

    _col = _Col()

    class _ModelStub:
        # 类级别任意属性（列访问）返回 _col
        def __init_subclass__(cls, **kwargs): super().__init_subclass__(**kwargs)
        def __class_getitem__(cls, item): return cls
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                object.__setattr__(self, k, v)
        def __setattr__(self, k, v):
            object.__setattr__(self, k, v)

    _ModelStub.__name__ = name
    _ModelStub.__qualname__ = name

    # 让类级别的属性访问返回可比较对象
    class _Meta(type):
        def __getattr__(cls, item):
            return _col

    return _Meta(name, (_ModelStub,), {})


fake_sam = types.ModuleType("src.models.supplier_agent")
fake_sam.SupplierTierEnum      = SupplierTierEnum
fake_sam.QuoteStatusEnum       = QuoteStatusEnum
fake_sam.ContractStatusEnum    = ContractStatusEnum
fake_sam.DeliveryStatusEnum    = DeliveryStatusEnum
fake_sam.RiskLevelEnum         = RiskLevelEnum
fake_sam.AlertTypeEnum         = AlertTypeEnum
fake_sam.SupplierAgentTypeEnum = SupplierAgentTypeEnum
for _name in ["SupplierProfile","MaterialCatalog","SupplierQuote","SupplierContract",
               "SupplierDelivery","PriceComparison","SupplierEvaluation",
               "SourcingRecommendation","ContractAlert","SupplyRiskEvent","SupplierAgentLog"]:
    setattr(fake_sam, _name, _make_model_class(_name))

fake_src    = types.ModuleType("src")
fake_models = types.ModuleType("src.models")
fake_src.models    = fake_models
fake_models.supplier_agent = fake_sam
sys.modules.setdefault("src",                      fake_src)
sys.modules.setdefault("src.models",               fake_models)
sys.modules.setdefault("src.models.supplier_agent", fake_sam)

# ─────────────────────────────────────────────────────────────────────────────
# 导入 agent 模块，替换 sqlalchemy 符号
# ─────────────────────────────────────────────────────────────────────────────

_agent_module = importlib.import_module("packages.agents.supplier.src.agent")

def _chainable_mock(*args, **kwargs):
    m = MagicMock()
    m.where    = lambda *a, **kw: m
    m.where    = lambda *a, **kw: m
    m.join     = lambda *a, **kw: m
    m.order_by = lambda *a, **kw: m
    m.offset   = lambda *a, **kw: m
    m.limit    = lambda *a, **kw: m
    m.group_by = lambda *a, **kw: m
    m.in_      = lambda *a, **kw: m
    m.select_from = lambda *a, **kw: m
    return m

_agent_module.select = _chainable_mock
_agent_module.func   = MagicMock(
    count=_chainable_mock, avg=_chainable_mock,
    sum=_chainable_mock, distinct=_chainable_mock,
)
_agent_module.and_   = MagicMock(side_effect=lambda *args: args[0] if args else MagicMock())

# 导入纯函数 + Agent 类
from packages.agents.supplier.src.agent import (
    PriceComparisonAgent, SupplierRatingAgent, AutoSourcingAgent,
    ContractRiskAgent, SupplyChainRiskAgent,
    compute_price_score, compute_delivery_score, compute_quality_score,
    compute_composite_score, classify_supplier_tier, classify_risk_level,
    compute_price_spread_pct, estimate_saving_yuan,
)

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db

def _make_obj(**kw):
    obj = MagicMock()
    for k, v in kw.items():
        setattr(obj, k, v)
    return obj


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputePriceScore:
    def test_well_below_benchmark_returns_100(self):
        assert compute_price_score(8.5, 10.0) == 100.0   # -15% < -10%

    def test_above_20pct_returns_0(self):
        assert compute_price_score(13.0, 10.0) == 0.0    # +30% > +20%

    def test_equal_benchmark_about_67(self):
        score = compute_price_score(10.0, 10.0)           # 0% → 66.7
        assert 60.0 < score < 75.0

    def test_zero_benchmark_returns_50(self):
        assert compute_price_score(8.0, 0.0) == 50.0

    def test_score_always_in_range(self):
        for price in [5.0, 9.0, 10.0, 11.5, 14.0]:
            score = compute_price_score(price, 10.0)
            assert 0.0 <= score <= 100.0


class TestComputeDeliveryScore:
    def test_perfect_on_time(self):
        assert compute_delivery_score(10, 10) == 100.0

    def test_no_on_time(self):
        assert compute_delivery_score(0, 10) == 0.0

    def test_partial(self):
        assert compute_delivery_score(8, 10) == 80.0

    def test_no_deliveries_returns_50(self):
        assert compute_delivery_score(0, 0) == 50.0


class TestComputeQualityScore:
    def test_zero_reject_full_quality_score_positive(self):
        score = compute_quality_score(0.0, 5.0)
        assert score > 0.0

    def test_high_reject_lowers_score(self):
        low = compute_quality_score(0.10, 3.0)
        high = compute_quality_score(0.0, 5.0)
        assert low < high

    def test_no_quality_data_still_positive(self):
        score = compute_quality_score(0.0, None)
        assert score > 0.0

    def test_score_never_negative(self):
        assert compute_quality_score(0.20, 1.0) >= 0.0


class TestComputeCompositeScore:
    def test_all_100_returns_100(self):
        assert compute_composite_score(100, 100, 100, 100) == 100.0

    def test_all_0_returns_0(self):
        assert compute_composite_score(0, 0, 0, 0) == 0.0

    def test_price_30pct_weight(self):
        score = compute_composite_score(100, 0, 0, 0)
        assert abs(score - 30.0) < 0.1

    def test_quality_35pct_weight(self):
        score = compute_composite_score(0, 100, 0, 0)
        assert abs(score - 35.0) < 0.1

    def test_delivery_25pct_weight(self):
        score = compute_composite_score(0, 0, 100, 0)
        assert abs(score - 25.0) < 0.1


class TestClassifySupplierTier:
    def test_90_strategic(self):
        assert classify_supplier_tier(90.0) == SupplierTierEnum.STRATEGIC

    def test_75_preferred(self):
        assert classify_supplier_tier(75.0) == SupplierTierEnum.PREFERRED

    def test_60_approved(self):
        assert classify_supplier_tier(60.0) == SupplierTierEnum.APPROVED

    def test_40_probation(self):
        assert classify_supplier_tier(40.0) == SupplierTierEnum.PROBATION


class TestClassifyRiskLevel:
    def test_high_prob_high_impact_critical(self):
        assert classify_risk_level(0.95, 50000) == RiskLevelEnum.CRITICAL

    def test_low_prob_low_impact_low(self):
        assert classify_risk_level(0.1, 100) == RiskLevelEnum.LOW

    def test_medium_values(self):
        level = classify_risk_level(0.5, 1000)
        assert level in (RiskLevelEnum.MEDIUM, RiskLevelEnum.HIGH)


class TestComputePriceSpread:
    def test_same_price_zero(self):
        assert compute_price_spread_pct([10.0, 10.0]) == 0.0

    def test_double_price_100pct(self):
        assert compute_price_spread_pct([5.0, 10.0]) == 100.0

    def test_empty_returns_0(self):
        assert compute_price_spread_pct([]) == 0.0


class TestEstimateSaving:
    def test_lower_recommended_positive_saving(self):
        assert estimate_saving_yuan(10.0, 8.0, 100) == 200.0

    def test_higher_recommended_negative(self):
        assert estimate_saving_yuan(8.0, 10.0, 100) == -200.0

    def test_same_price_zero(self):
        assert estimate_saving_yuan(10.0, 10.0, 100) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Agent 集成测试（Mock DB）
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriceComparisonAgent:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_quotes(self):
        agent = PriceComparisonAgent()
        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        result = await agent.compare("B1", "MAT1", 100, db, save=False)
        assert result["quote_count"] == 0
        assert result["recommended_supplier_id"] is None

    @pytest.mark.asyncio
    async def test_returns_best_supplier_when_quotes_available(self):
        agent = PriceComparisonAgent()
        db = _make_db()

        q1 = _make_obj(
            id="Q1", supplier_id="SUP1", unit_price_yuan=Decimal("8.5"),
            delivery_days=2, min_order_qty=0,
            status=QuoteStatusEnum.SUBMITTED,
            valid_until=date.today() + timedelta(days=10),
            price_delta_pct=None,
        )
        q2 = _make_obj(
            id="Q2", supplier_id="SUP2", unit_price_yuan=Decimal("9.5"),
            delivery_days=3, min_order_qty=0,
            status=QuoteStatusEnum.SUBMITTED,
            valid_until=date.today() + timedelta(days=10),
            price_delta_pct=None,
        )
        material = _make_obj(
            id="MAT1", material_name="猪五花", benchmark_price_yuan=Decimal("10.0"),
            base_unit="kg",
        )
        profile = _make_obj(delivery_score=80.0, quality_score=75.0)

        calls = [0]
        async def execute(q):
            r = MagicMock()
            if calls[0] == 0:
                r.scalars.return_value.all.return_value = [q1, q2]
            elif calls[0] == 1:
                r.scalar_one_or_none.return_value = material
            else:
                r.scalar_one_or_none.return_value = profile
            calls[0] += 1
            return r

        db.execute = execute
        result = await agent.compare("B1", "MAT1", 100, db, save=False)
        assert result["quote_count"] == 2
        assert result["recommended_supplier_id"] == "SUP1"
        assert result["estimated_saving_yuan"] > 0

    @pytest.mark.asyncio
    async def test_positive_saving_when_below_benchmark(self):
        saving = estimate_saving_yuan(10.0, 8.5, 100)
        assert saving == 150.0


class TestSupplierRatingAgent:
    @pytest.mark.asyncio
    async def test_no_deliveries_returns_valid_composite(self):
        agent = SupplierRatingAgent()
        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        result = await agent.evaluate("B1", "SUP1", "2026-03", db, save=False)
        assert 0 <= result["composite_score"] <= 100
        assert result["delivery_count"] == 0

    @pytest.mark.asyncio
    async def test_high_reject_rate_triggers_action_required(self):
        agent = SupplierRatingAgent()
        db = _make_db()

        d1 = _make_obj(
            delay_days=0, ordered_qty=100, received_qty=70, rejected_qty=30,
            quality_score=2.5, promised_date=date.today() - timedelta(days=5),
        )
        d2 = _make_obj(
            delay_days=0, ordered_qty=100, received_qty=60, rejected_qty=40,
            quality_score=2.0, promised_date=date.today() - timedelta(days=10),
        )
        calls = [0]
        async def execute(q):
            r = MagicMock()
            if calls[0] == 0:
                r.scalars.return_value.all.return_value = [d1, d2]
            else:
                r.scalars.return_value.all.return_value = []
                r.scalar_one_or_none.return_value = None
            calls[0] += 1
            return r

        db.execute = execute
        result = await agent.evaluate("B1", "SUP1", "2026-03", db, save=False)
        assert result["action_required"] is True

    def test_build_action_text_low_score(self):
        agent = SupplierRatingAgent()
        text = agent._build_action_text(45.0, 0.02, 70.0, SupplierTierEnum.PROBATION)
        assert "降级" in text or "整改" in text

    def test_build_action_text_good_score(self):
        agent = SupplierRatingAgent()
        text = agent._build_action_text(90.0, 0.01, 95.0, SupplierTierEnum.STRATEGIC)
        assert "良好" in text


class TestAutoSourcingAgent:
    @pytest.mark.asyncio
    async def test_no_material_returns_not_found(self):
        agent = AutoSourcingAgent()
        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        result = await agent.source("B1", "MAT999", 100, date.today() + timedelta(5), db, save=False)
        assert result["recommended_supplier_id"] is None
        assert "物料目录" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_no_valid_quotes_returns_no_quotes(self):
        agent = AutoSourcingAgent()
        db = _make_db()
        material = _make_obj(id="M1", material_name="番茄", benchmark_price_yuan=Decimal("3.0"),
                             base_unit="kg", preferred_supplier_id="S1")
        calls = [0]
        async def execute(q):
            r = MagicMock()
            if calls[0] == 0:
                r.scalar_one_or_none.return_value = material
            else:
                r.scalars.return_value.all.return_value = []
            calls[0] += 1
            return r
        db.execute = execute
        result = await agent.source("B1", "M1", 50, date.today() + timedelta(3), db, save=False)
        assert result["recommended_supplier_id"] is None

    @pytest.mark.asyncio
    async def test_sourcing_with_valid_quote(self):
        agent = AutoSourcingAgent()
        db = _make_db()
        material = _make_obj(id="M1", material_name="猪里脊", benchmark_price_yuan=Decimal("50.0"),
                             base_unit="kg", preferred_supplier_id="S1", backup_supplier_ids=[])
        quote = _make_obj(
            id="Q1", supplier_id="S1",
            unit_price_yuan=Decimal("45.0"),
            delivery_days=2, min_order_qty=0,
        )
        profile = _make_obj(composite_score=80.0)
        calls = [0]
        async def execute(q):
            r = MagicMock()
            if calls[0] == 0:
                r.scalar_one_or_none.return_value = material
            elif calls[0] == 1:
                r.scalars.return_value.all.return_value = [quote]
            else:
                r.scalar_one_or_none.return_value = profile
            calls[0] += 1
            return r
        db.execute = execute
        result = await agent.source("B1", "M1", 100, date.today() + timedelta(5), db, save=False)
        assert result["recommended_supplier_id"] == "S1"
        assert result["estimated_saving_yuan"] > 0


class TestContractRiskAgent:
    @pytest.mark.asyncio
    async def test_no_contracts_zero_alerts(self):
        agent = ContractRiskAgent()
        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        result = await agent.scan("B1", db, save=False)
        assert result["alerts_created"] == 0
        assert result["scanned_count"] == 0

    def test_7_days_critical(self):
        agent = ContractRiskAgent()
        level, atype = agent._classify_expiry_risk(6)
        assert level == RiskLevelEnum.CRITICAL
        assert atype == AlertTypeEnum.CONTRACT_EXPIRING

    def test_15_days_high(self):
        agent = ContractRiskAgent()
        level, _ = agent._classify_expiry_risk(12)
        assert level == RiskLevelEnum.HIGH

    def test_30_days_medium(self):
        agent = ContractRiskAgent()
        level, _ = agent._classify_expiry_risk(25)
        assert level == RiskLevelEnum.MEDIUM

    def test_60_days_no_alert(self):
        agent = ContractRiskAgent()
        level, atype = agent._classify_expiry_risk(60)
        assert level is None
        assert atype is None

    @pytest.mark.asyncio
    async def test_expiring_contract_generates_alert(self):
        agent = ContractRiskAgent()
        db = _make_db()
        contract = _make_obj(
            id="C1", contract_no="CN-001", contract_name="番茄供应合同",
            supplier_id="S1",
            end_date=date.today() + timedelta(days=10),
            status=ContractStatusEnum.ACTIVE,
            annual_value_yuan=Decimal("120000"),
        )
        calls = [0]
        async def execute(q):
            r = MagicMock()
            if calls[0] == 0:
                r.scalars.return_value.all.return_value = [contract]
            else:
                r.scalar_one_or_none.return_value = None  # 无重复预警
            calls[0] += 1
            return r
        db.execute = execute
        result = await agent.scan("B1", db, save=False)
        assert result["scanned_count"] == 1
        assert len(result["alert_summaries"]) == 1
        assert result["alert_summaries"][0]["risk_level"] in ("high", "critical")


class TestSupplyChainRiskAgent:
    @pytest.mark.asyncio
    async def test_no_materials_zero_risks(self):
        agent = SupplyChainRiskAgent()
        db = _make_db()
        calls = [0]
        async def execute(q):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            r.scalar.return_value = 2
            calls[0] += 1
            return r
        db.execute = execute
        result = await agent.scan("B1", db, save=False)
        assert result["risk_count"] == 0

    @pytest.mark.asyncio
    async def test_price_spike_detected(self):
        agent = SupplyChainRiskAgent()
        db = _make_db()
        material = _make_obj(
            id="M1", material_name="牛里脊",
            benchmark_price_yuan=Decimal("80.0"),
            latest_price_yuan=Decimal("100.0"),  # +25%
            is_active=True, preferred_supplier_id="S1",
            backup_supplier_ids=[], reorder_point_kg=50,
        )
        calls = [0]
        async def execute(q):
            r = MagicMock()
            if calls[0] == 0:
                r.scalars.return_value.all.return_value = [material]
            else:
                r.scalars.return_value.all.return_value = []
                r.scalar.return_value = 2
            calls[0] += 1
            return r
        db.execute = execute
        risks = await agent._check_price_spikes("B1", db)
        assert len(risks) == 1
        assert risks[0]["alert_type"] == AlertTypeEnum.PRICE_SPIKE

    @pytest.mark.asyncio
    async def test_single_source_risk_detected(self):
        agent = SupplyChainRiskAgent()
        db = _make_db()
        material = _make_obj(
            id="M1", material_name="猪前腿",
            is_active=True, preferred_supplier_id="S1", backup_supplier_ids=[],
        )
        calls = [0]
        async def execute(q):
            r = MagicMock()
            if calls[0] == 0:
                r.scalars.return_value.all.return_value = [material]
            else:
                r.scalar.return_value = 1  # 只有1家
            calls[0] += 1
            return r
        db.execute = execute
        risks = await agent._check_single_source("B1", db)
        assert len(risks) >= 1
        assert risks[0]["alert_type"] == AlertTypeEnum.SINGLE_SOURCE_RISK

    @pytest.mark.asyncio
    async def test_no_price_spike_below_threshold(self):
        agent = SupplyChainRiskAgent()
        db = _make_db()
        material = _make_obj(
            id="M2", material_name="土豆",
            benchmark_price_yuan=Decimal("5.0"),
            latest_price_yuan=Decimal("5.5"),  # +10% < 15%
            is_active=True, preferred_supplier_id="S1",
            backup_supplier_ids=[], reorder_point_kg=100,
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [material]
        db.execute = AsyncMock(return_value=result_mock)
        risks = await agent._check_price_spikes("B1", db)
        assert len(risks) == 0
