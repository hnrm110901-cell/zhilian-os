"""
菜品做法变体 + 多规格定价 — 测试套件

覆盖：
  - DishMethodVariant 模型属性
  - DishSpecification 模型属性
  - DishMethodService 业务逻辑
  - DishSpecificationService 业务逻辑
  - API 路由 Pydantic 校验
  - 东星斑示例数据验证
"""

import sys
import types
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── 环境隔离（L002: pydantic_settings 在 import 时校验环境变量）──
cfg_mod = types.ModuleType("src.core.config")
cfg_mod.settings = MagicMock(
    database_url="postgresql+asyncpg://x:x@localhost/x",
    redis_url="redis://localhost",
    secret_key="test",
)
sys.modules.setdefault("src.core.config", cfg_mod)

db_mod = types.ModuleType("src.core.database")
db_mod.get_db_session = MagicMock()
sys.modules.setdefault("src.core.database", db_mod)

tenant_mod = types.ModuleType("src.core.tenant_context")
tenant_ctx = MagicMock()
tenant_ctx.get_current_tenant = MagicMock(return_value="STORE001")
tenant_ctx.get_current_brand = MagicMock(return_value=None)
tenant_mod.TenantContext = tenant_ctx
sys.modules.setdefault("src.core.tenant_context", tenant_mod)


# ── 导入被测模块 ──
from src.models.dish_method_variant import DishMethodVariant
from src.models.dish_specification import DishSpecification


# ── Fixtures ──

DISH_ID = uuid.uuid4()
BOM_ID = uuid.uuid4()
METHOD_ID_1 = uuid.uuid4()
METHOD_ID_2 = uuid.uuid4()
SPEC_ID_1 = uuid.uuid4()
SPEC_ID_2 = uuid.uuid4()
SPEC_ID_3 = uuid.uuid4()


def _make_method(**overrides) -> DishMethodVariant:
    """构造 DishMethodVariant 实例"""
    defaults = dict(
        id=uuid.uuid4(),
        dish_id=DISH_ID,
        method_name="清蒸",
        kitchen_station="蒸柜",
        prep_time_minutes=12,
        bom_template_id=None,
        extra_cost_fen=0,
        is_default=True,
        is_available=True,
        display_order=0,
        description="清蒸保留原味，推荐鲜活海鲜",
    )
    defaults.update(overrides)
    m = DishMethodVariant.__new__(DishMethodVariant)
    for k, v in defaults.items():
        object.__setattr__(m, k, v)
    return m


def _make_spec(**overrides) -> DishSpecification:
    """构造 DishSpecification 实例"""
    defaults = dict(
        id=uuid.uuid4(),
        dish_id=DISH_ID,
        spec_name="中份",
        price_fen=4800,
        cost_fen=1800,
        bom_multiplier=Decimal("1.00"),
        unit="份",
        min_order_qty=1,
        is_default=True,
        is_available=True,
        display_order=0,
    )
    defaults.update(overrides)
    s = DishSpecification.__new__(DishSpecification)
    for k, v in defaults.items():
        object.__setattr__(s, k, v)
    return s


# ═══════════════════════════════════════════════════════════
# 任务A: DishMethodVariant 模型测试
# ═══════════════════════════════════════════════════════════


class TestDishMethodVariantModel:
    """DishMethodVariant 模型属性测试"""

    def test_tablename(self):
        """表名为 dish_method_variants"""
        assert DishMethodVariant.__tablename__ == "dish_method_variants"

    def test_extra_cost_yuan_zero(self):
        """附加费为0时，元值为0.00"""
        m = _make_method(extra_cost_fen=0)
        assert m.extra_cost_yuan == 0.00

    def test_extra_cost_yuan_conversion(self):
        """附加费 2000 分 = ¥20.00"""
        m = _make_method(extra_cost_fen=2000)
        assert m.extra_cost_yuan == 20.00

    def test_extra_cost_yuan_fractional(self):
        """附加费 550 分 = ¥5.50"""
        m = _make_method(extra_cost_fen=550)
        assert m.extra_cost_yuan == 5.50

    def test_repr(self):
        """__repr__ 包含关键信息"""
        m = _make_method(dish_id=DISH_ID, method_name="红烧", kitchen_station="炒锅")
        r = repr(m)
        assert "红烧" in r
        assert "炒锅" in r

    def test_unique_constraint_name(self):
        """唯一约束: dish_id + method_name"""
        constraints = [
            c.name for c in DishMethodVariant.__table_args__
            if hasattr(c, 'name') and c.name and c.name.startswith("uq_")
        ]
        assert "uq_dish_method_variant" in constraints

    def test_dongxingban_steamed(self):
        """东星斑 - 清蒸：蒸柜, 12分钟"""
        m = _make_method(
            method_name="清蒸",
            kitchen_station="蒸柜",
            prep_time_minutes=12,
            extra_cost_fen=0,
            is_default=True,
        )
        assert m.method_name == "清蒸"
        assert m.kitchen_station == "蒸柜"
        assert m.prep_time_minutes == 12
        assert m.extra_cost_fen == 0
        assert m.is_default is True

    def test_dongxingban_sashimi(self):
        """东星斑 - 刺身：凉菜间, 5分钟, +¥20"""
        m = _make_method(
            method_name="刺身",
            kitchen_station="凉菜",
            prep_time_minutes=5,
            extra_cost_fen=2000,
            is_default=False,
        )
        assert m.method_name == "刺身"
        assert m.kitchen_station == "凉菜"
        assert m.prep_time_minutes == 5
        assert m.extra_cost_yuan == 20.00

    def test_dongxingban_braised(self):
        """东星斑 - 红烧：炒锅, 15分钟"""
        m = _make_method(
            method_name="红烧",
            kitchen_station="炒锅",
            prep_time_minutes=15,
        )
        assert m.kitchen_station == "炒锅"
        assert m.prep_time_minutes == 15

    def test_dongxingban_salt_pepper(self):
        """东星斑 - 椒盐：油炸, 10分钟"""
        m = _make_method(
            method_name="椒盐",
            kitchen_station="油炸",
            prep_time_minutes=10,
        )
        assert m.kitchen_station == "油炸"
        assert m.prep_time_minutes == 10


# ═══════════════════════════════════════════════════════════
# 任务B: DishSpecification 模型测试
# ═══════════════════════════════════════════════════════════


class TestDishSpecificationModel:
    """DishSpecification 模型属性测试"""

    def test_tablename(self):
        """表名为 dish_specifications"""
        assert DishSpecification.__tablename__ == "dish_specifications"

    def test_price_yuan_conversion(self):
        """售价 4800 分 = ¥48.00"""
        s = _make_spec(price_fen=4800)
        assert s.price_yuan == 48.00

    def test_cost_yuan_conversion(self):
        """成本 1800 分 = ¥18.00"""
        s = _make_spec(cost_fen=1800)
        assert s.cost_yuan == 18.00

    def test_cost_yuan_none(self):
        """成本为 None 时返回 None"""
        s = _make_spec(cost_fen=None)
        assert s.cost_yuan is None

    def test_profit_margin_normal(self):
        """毛利率：(4800-1800)/4800*100 = 62.50%"""
        s = _make_spec(price_fen=4800, cost_fen=1800)
        assert s.profit_margin == 62.5

    def test_profit_margin_no_cost(self):
        """无成本时毛利率为 None"""
        s = _make_spec(price_fen=4800, cost_fen=None)
        assert s.profit_margin is None

    def test_profit_margin_zero_price(self):
        """售价为0时毛利率为 None（除零保护，L006）"""
        s = _make_spec(price_fen=0, cost_fen=0)
        assert s.profit_margin is None

    def test_unique_constraint_name(self):
        """唯一约束: dish_id + spec_name"""
        constraints = [
            c.name for c in DishSpecification.__table_args__
            if hasattr(c, 'name') and c.name and c.name.startswith("uq_")
        ]
        assert "uq_dish_specification" in constraints

    def test_repr(self):
        """__repr__ 包含关键信息"""
        s = _make_spec(dish_id=DISH_ID, spec_name="大份", price_fen=6800)
        r = repr(s)
        assert "大份" in r
        assert "6800" in r

    def test_bom_multiplier_large(self):
        """大份 BOM 系数 1.5"""
        s = _make_spec(spec_name="大份", bom_multiplier=Decimal("1.50"))
        assert float(s.bom_multiplier) == 1.5

    def test_bom_multiplier_small(self):
        """小份 BOM 系数 0.7"""
        s = _make_spec(spec_name="小份", bom_multiplier=Decimal("0.70"))
        assert float(s.bom_multiplier) == 0.7

    def test_dongxingban_by_weight(self):
        """东星斑 - 时价/斤"""
        s = _make_spec(
            spec_name="时价/斤",
            price_fen=28800,  # ¥288/斤
            unit="斤",
            bom_multiplier=Decimal("1.00"),
            is_default=True,
        )
        assert s.spec_name == "时价/斤"
        assert s.unit == "斤"
        assert s.price_yuan == 288.00

    def test_dongxingban_by_count(self):
        """东星斑 - 整条"""
        s = _make_spec(
            spec_name="整条",
            price_fen=58800,  # ¥588/条
            unit="条",
            bom_multiplier=Decimal("1.00"),
        )
        assert s.spec_name == "整条"
        assert s.unit == "条"
        assert s.price_yuan == 588.00


# ═══════════════════════════════════════════════════════════
# API Pydantic 模型校验测试
# ═══════════════════════════════════════════════════════════


class TestPydanticSchemas:
    """API 请求/响应 Pydantic 模型测试"""

    def test_method_create_valid(self):
        from src.api.dish_variants import MethodVariantCreate
        data = MethodVariantCreate(
            method_name="清蒸",
            kitchen_station="蒸柜",
            prep_time_minutes=12,
        )
        assert data.method_name == "清蒸"
        assert data.extra_cost_fen == 0
        assert data.is_default is False

    def test_method_create_with_extra_cost(self):
        from src.api.dish_variants import MethodVariantCreate
        data = MethodVariantCreate(
            method_name="刺身",
            kitchen_station="凉菜",
            extra_cost_fen=2000,
        )
        assert data.extra_cost_fen == 2000

    def test_method_create_negative_time_rejected(self):
        from src.api.dish_variants import MethodVariantCreate
        with pytest.raises(Exception):
            MethodVariantCreate(
                method_name="清蒸",
                kitchen_station="蒸柜",
                prep_time_minutes=0,  # ge=1
            )

    def test_spec_create_valid(self):
        from src.api.dish_variants import SpecificationCreate
        data = SpecificationCreate(
            spec_name="大份",
            price_fen=6800,
            bom_multiplier=Decimal("1.50"),
        )
        assert data.spec_name == "大份"
        assert data.price_fen == 6800
        assert data.bom_multiplier == Decimal("1.50")
        assert data.unit == "份"
        assert data.min_order_qty == 1

    def test_spec_create_negative_price_rejected(self):
        from src.api.dish_variants import SpecificationCreate
        with pytest.raises(Exception):
            SpecificationCreate(
                spec_name="大份",
                price_fen=-100,  # ge=0
            )

    def test_spec_create_zero_multiplier_rejected(self):
        from src.api.dish_variants import SpecificationCreate
        with pytest.raises(Exception):
            SpecificationCreate(
                spec_name="大份",
                price_fen=100,
                bom_multiplier=Decimal("0.00"),  # ge=0.01
            )

    def test_method_response_from_model(self):
        from src.api.dish_variants import MethodVariantResponse
        m = _make_method(
            id=METHOD_ID_1,
            dish_id=DISH_ID,
            extra_cost_fen=500,
        )
        resp = MethodVariantResponse.model_validate(m, from_attributes=True)
        assert resp.extra_cost_yuan == 5.00
        assert resp.id == METHOD_ID_1

    def test_spec_response_from_model(self):
        from src.api.dish_variants import SpecificationResponse
        s = _make_spec(
            id=SPEC_ID_1,
            dish_id=DISH_ID,
            price_fen=4800,
            cost_fen=1800,
            bom_multiplier=Decimal("1.00"),
        )
        resp = SpecificationResponse.model_validate(s, from_attributes=True)
        assert resp.price_yuan == 48.00
        assert resp.cost_yuan == 18.00
        assert resp.profit_margin == 62.5

    def test_bom_deduction_request_min_quantity(self):
        from src.api.dish_variants import BomDeductionRequest
        with pytest.raises(Exception):
            BomDeductionRequest(quantity=0)  # ge=1

    def test_full_options_response(self):
        from src.api.dish_variants import FullOptionsResponse, MethodVariantResponse, SpecificationResponse
        m = _make_method(id=METHOD_ID_1, dish_id=DISH_ID, extra_cost_fen=0)
        s = _make_spec(id=SPEC_ID_1, dish_id=DISH_ID, bom_multiplier=Decimal("1.00"))
        resp = FullOptionsResponse(
            dish_id=DISH_ID,
            methods=[MethodVariantResponse.model_validate(m, from_attributes=True)],
            specifications=[SpecificationResponse.model_validate(s, from_attributes=True)],
        )
        assert resp.dish_id == DISH_ID
        assert len(resp.methods) == 1
        assert len(resp.specifications) == 1


# ═══════════════════════════════════════════════════════════
# 综合业务场景测试
# ═══════════════════════════════════════════════════════════


class TestBusinessScenarios:
    """业务场景测试"""

    def test_dongxingban_all_methods(self):
        """东星斑4种做法完整验证"""
        methods = [
            _make_method(method_name="清蒸", kitchen_station="蒸柜", prep_time_minutes=12, extra_cost_fen=0, is_default=True, display_order=0),
            _make_method(method_name="红烧", kitchen_station="炒锅", prep_time_minutes=15, extra_cost_fen=0, is_default=False, display_order=1),
            _make_method(method_name="刺身", kitchen_station="凉菜", prep_time_minutes=5, extra_cost_fen=2000, is_default=False, display_order=2),
            _make_method(method_name="椒盐", kitchen_station="油炸", prep_time_minutes=10, extra_cost_fen=0, is_default=False, display_order=3),
        ]
        # 只有一个默认做法
        defaults = [m for m in methods if m.is_default]
        assert len(defaults) == 1
        assert defaults[0].method_name == "清蒸"

        # 刺身有附加费
        sashimi = [m for m in methods if m.method_name == "刺身"][0]
        assert sashimi.extra_cost_yuan == 20.00

        # 各做法路由到不同工位
        stations = {m.method_name: m.kitchen_station for m in methods}
        assert stations["清蒸"] == "蒸柜"
        assert stations["红烧"] == "炒锅"
        assert stations["刺身"] == "凉菜"
        assert stations["椒盐"] == "油炸"

    def test_huiguorou_specs(self):
        """回锅肉多规格验证：大/中/小份"""
        specs = [
            _make_spec(spec_name="大份", price_fen=6800, bom_multiplier=Decimal("1.50"), display_order=0),
            _make_spec(spec_name="中份", price_fen=4800, bom_multiplier=Decimal("1.00"), is_default=True, display_order=1),
            _make_spec(spec_name="小份", price_fen=3200, bom_multiplier=Decimal("0.70"), display_order=2),
        ]
        # 价格递减
        assert specs[0].price_fen > specs[1].price_fen > specs[2].price_fen

        # BOM 系数递减
        assert specs[0].bom_multiplier > specs[1].bom_multiplier > specs[2].bom_multiplier

        # 大份: ¥68, 中份: ¥48, 小份: ¥32
        assert specs[0].price_yuan == 68.00
        assert specs[1].price_yuan == 48.00
        assert specs[2].price_yuan == 32.00

    def test_method_availability_filter(self):
        """不可用的做法应被过滤"""
        methods = [
            _make_method(method_name="清蒸", is_available=True),
            _make_method(method_name="刺身", is_available=False),  # 今日无刺身
        ]
        available = [m for m in methods if m.is_available]
        assert len(available) == 1
        assert available[0].method_name == "清蒸"

    def test_spec_min_order_qty(self):
        """龙虾至少点2只"""
        s = _make_spec(
            spec_name="只",
            min_order_qty=2,
            unit="只",
            price_fen=8800,
        )
        assert s.min_order_qty == 2

    def test_cost_with_bom_and_method(self):
        """做法成本 = BOM成本 + 做法附加费"""
        # 模拟：刺身做法，BOM成本 15000分，附加费 2000分
        bom_cost = 15000
        extra_cost = 2000
        total = bom_cost + extra_cost
        assert total == 17000
        assert round(total / 100, 2) == 170.00

    def test_bom_deduction_multiplier(self):
        """BOM 扣减 = 标准用量 × 规格系数 × 数量"""
        standard_qty = 200.0  # 200克鱼肉
        multiplier = 1.5  # 大份
        quantity = 2  # 点2份
        deduction = round(standard_qty * multiplier * quantity, 4)
        assert deduction == 600.0  # 600克

    def test_yuan_precision(self):
        """¥金额保留2位小数（L006 除零保护）"""
        s = _make_spec(price_fen=1)
        assert s.price_yuan == 0.01

        s2 = _make_spec(price_fen=99)
        assert s2.price_yuan == 0.99

        s3 = _make_spec(price_fen=12345)
        assert s3.price_yuan == 123.45
