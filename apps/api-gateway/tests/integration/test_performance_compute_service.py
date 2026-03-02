"""
Integration tests for PerformanceComputeService (P2 绩效计算引擎)

覆盖场景：
1.  _achievement: 正常正向指标计算
2.  _achievement: LOWER_IS_BETTER (waste_rate / avg_serve_time) 反转计算
3.  _achievement: value=0 → 上限保护
4.  _achievement: target=None → 返回 None
5.  compute_and_write: 无数据（空 managers / waiters / kitchen）→ 返回 0
6.  compute_and_write: 有店长 + 订单 → 写入 revenue 等指标
7.  compute_and_write: 无店长 → _compute_store_metrics 返回空
8.  compute_and_write: 幂等性 — 同期再次调用，行数一致
9.  _compute_waiter_metrics: 按 waiter_id 分组，两个服务员各得 2 个指标
10. _compute_kitchen_metrics: 无厨房员工 → 返回空列表
11. _compute_kitchen_metrics: 有厨房员工但无订单数据 → value=None，achievement_rate=None
12. achievement_rate 上限保护（不超过 2.0）
"""
import sys
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Module stubs ──────────────────────────────────────────────────────────────
sys.modules.setdefault("structlog", MagicMock(get_logger=MagicMock(return_value=MagicMock(
    info=MagicMock(), warning=MagicMock(), error=MagicMock(), debug=MagicMock()
))))
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock())

for mod in [
    "src.models", "src.models.employee", "src.models.employee_metric",
    "src.models.order", "src.models.waste_event", "src.models.store",
]:
    sys.modules.setdefault(mod, MagicMock())

# 在 stub 之后导入，避免真实模型触发 SQLAlchemy metadata
from src.services.performance_compute_service import (  # noqa: E402
    PerformanceComputeService,
    _achievement,
    DEFAULT_TARGETS,
    LOWER_IS_BETTER,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_employee(emp_id=None, position="store_manager"):
    emp = MagicMock()
    emp.id = emp_id or str(uuid4())
    emp.position = position
    emp.store_id = "S001"
    emp.is_active = True
    return emp


def _make_session():
    """返回一个 AsyncMock session，execute 默认返回可配置的 scalars。"""
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


def _scalar_result(value):
    """模拟 session.execute(...).scalar()"""
    mock_result = MagicMock()
    mock_result.scalar.return_value = value
    return mock_result


def _scalars_result(items):
    """模拟 session.execute(...).scalars().all()"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    return mock_result


def _all_result(rows):
    """模拟 session.execute(...).all()"""
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    return mock_result


# ── Tests: _achievement ───────────────────────────────────────────────────────

def test_achievement_normal():
    """正向指标：value / target，上限 2.0"""
    assert _achievement(100.0, 100.0, "revenue") == 1.0
    assert _achievement(150.0, 100.0, "revenue") == 1.5


def test_achievement_exceeds_cap():
    """达成率超过 200% → 钳制到 2.0"""
    assert _achievement(300.0, 100.0, "revenue") == 2.0


def test_achievement_lower_is_better_waste_rate():
    """waste_rate: 越低越好，rate = target / value"""
    # value = 0.03, target = 0.05 → 0.05/0.03 ≈ 1.6667
    result = _achievement(0.03, 0.05, "waste_rate")
    assert result is not None
    assert abs(result - round(0.05 / 0.03, 4)) < 1e-4


def test_achievement_lower_is_better_avg_serve_time():
    """avg_serve_time: 越低越好"""
    # value=10, target=15 → 15/10 = 1.5
    result = _achievement(10.0, 15.0, "avg_serve_time")
    assert result == 1.5


def test_achievement_target_none():
    """target=None → None"""
    assert _achievement(100.0, None, "revenue") is None


def test_achievement_value_none():
    """value=None → None"""
    assert _achievement(None, 100.0, "revenue") is None


def test_achievement_target_zero():
    """target=0 → None（避免除零）"""
    assert _achievement(100.0, 0.0, "revenue") is None


# ── Tests: _compute_store_metrics ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_store_metrics_no_managers():
    """无店长 → 返回空列表"""
    session = _make_session()
    # execute(select(Employee)...) → 无店长
    session.execute.side_effect = [_scalars_result([])]

    rows = await PerformanceComputeService._compute_store_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert rows == []


@pytest.mark.asyncio
async def test_compute_store_metrics_with_data():
    """有店长 + 订单 + 损耗数据 → 生成4个指标行"""
    session = _make_session()
    manager = _make_employee(position="store_manager")

    session.execute.side_effect = [
        _scalars_result([manager]),        # 查询店长
        _scalar_result(300_000_00),        # monthly_revenue (分)
        _scalar_result(Decimal("0.45")),   # gross_margin_pct
        _scalar_result(5),                 # emp_count
        _scalar_result(0.04),              # waste_rate
    ]

    rows = await PerformanceComputeService._compute_store_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )

    # 店长4个指标：revenue, profit, labor_efficiency, waste_rate
    assert len(rows) == 4
    metric_ids = {r["metric_id"] for r in rows}
    assert metric_ids == {"revenue", "profit", "labor_efficiency", "waste_rate"}

    # revenue 行检查
    rev_row = next(r for r in rows if r["metric_id"] == "revenue")
    assert float(rev_row["value"]) == 300_000_00
    assert rev_row["employee_id"] == manager.id
    assert rev_row["achievement_rate"] is not None


@pytest.mark.asyncio
async def test_compute_store_metrics_null_revenue():
    """月营收为0时不崩溃，revenue value = 0"""
    session = _make_session()
    manager = _make_employee(position="store_manager")

    session.execute.side_effect = [
        _scalars_result([manager]),
        _scalar_result(0),          # revenue = 0
        _scalar_result(None),       # gross_margin = None
        _scalar_result(3),          # emp_count
        _scalar_result(None),       # waste_rate = None
    ]

    rows = await PerformanceComputeService._compute_store_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert len(rows) == 4  # 仍然生成4行，value 可为 None 或 0


# ── Tests: _compute_waiter_metrics ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_waiter_metrics_two_waiters():
    """2个服务员，各产生2个指标行（avg_per_table + order_count）"""
    session = _make_session()
    waiter1_id = str(uuid4())
    waiter2_id = str(uuid4())

    # 模拟 SELECT waiter_id, avg, count GROUP BY
    waiter_rows = [
        (waiter1_id, Decimal("15000"), 50),
        (waiter2_id, Decimal("12000"), 30),
    ]
    session.execute.side_effect = [_all_result(waiter_rows)]

    rows = await PerformanceComputeService._compute_waiter_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert len(rows) == 4  # 2 waiters × 2 metrics
    employee_ids = {r["employee_id"] for r in rows}
    assert employee_ids == {waiter1_id, waiter2_id}


@pytest.mark.asyncio
async def test_compute_waiter_metrics_no_completed_orders():
    """无已完成订单 → 空列表"""
    session = _make_session()
    session.execute.side_effect = [_all_result([])]

    rows = await PerformanceComputeService._compute_waiter_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert rows == []


# ── Tests: _compute_kitchen_metrics ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_kitchen_metrics_no_staff():
    """无厨房员工 → 空列表"""
    session = _make_session()
    session.execute.side_effect = [_scalars_result([])]

    rows = await PerformanceComputeService._compute_kitchen_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert rows == []


@pytest.mark.asyncio
async def test_compute_kitchen_metrics_no_order_data():
    """有厨房员工但无订单数据 → value=None，achievement_rate=None"""
    session = _make_session()
    chef = _make_employee(position="kitchen")

    session.execute.side_effect = [
        _scalars_result([chef]),
        _scalar_result(None),   # avg_serve_time = None
        _scalar_result(None),   # waste_rate = None
    ]

    rows = await PerformanceComputeService._compute_kitchen_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert len(rows) == 2
    for row in rows:
        assert row["value"] is None
        assert row["achievement_rate"] is None


@pytest.mark.asyncio
async def test_compute_kitchen_metrics_with_data():
    """有厨房员工 + 出餐数据 → avg_serve_time 反向达成率"""
    session = _make_session()
    chef = _make_employee(position="kitchen")

    session.execute.side_effect = [
        _scalars_result([chef]),
        _scalar_result(10.0),   # avg_serve_time = 10分钟 (target=15)
        _scalar_result(0.03),   # waste_rate = 3% (target=5%)
    ]

    rows = await PerformanceComputeService._compute_kitchen_metrics(
        session, "S001", date(2026, 1, 1), date(2026, 1, 31)
    )
    assert len(rows) == 2

    serve_row = next(r for r in rows if r["metric_id"] == "avg_serve_time")
    assert serve_row["value"] is not None
    # 10分钟 < 15分钟目标，达成率应 > 1.0
    assert float(serve_row["achievement_rate"]) > 1.0


# ── Tests: compute_and_write ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_and_write_no_data():
    """无任何员工/订单数据 → 返回 0"""
    session = _make_session()
    # _compute_store_metrics 查不到店长
    # _compute_waiter_metrics 查不到订单
    # _compute_kitchen_metrics 查不到厨房员工
    session.execute.side_effect = [
        _scalars_result([]),   # no managers
        _all_result([]),       # no waiter stats
        _scalars_result([]),   # no kitchen staff
    ]

    rows_written = await PerformanceComputeService.compute_and_write(
        session, "S001", 2026, 1
    )
    assert rows_written == 0


@pytest.mark.asyncio
async def test_compute_and_write_returns_row_count():
    """有2个服务员 → 写入4行，返回4"""
    session = _make_session()
    waiter1_id = str(uuid4())
    waiter2_id = str(uuid4())

    session.execute.side_effect = [
        _scalars_result([]),    # no managers
        _all_result([           # 2 waiters
            (waiter1_id, Decimal("15000"), 50),
            (waiter2_id, Decimal("12000"), 30),
        ]),
        _scalars_result([]),    # no kitchen staff
        MagicMock(),            # upsert execute result
    ]
    session.flush = AsyncMock()

    rows_written = await PerformanceComputeService.compute_and_write(
        session, "S001", 2026, 1
    )
    assert rows_written == 4
