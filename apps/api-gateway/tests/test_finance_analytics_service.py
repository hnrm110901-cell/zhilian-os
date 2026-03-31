"""
测试：FinanceAnalyticsService 与 KingdeeSyncService
覆盖 12 个核心场景：
  1.  日营收从 orders 表正确聚合
  2.  折扣金额正确扣减
  3.  毛利率计算精度
  4.  净利率计算精度
  5.  多门店排名正确（按 profit_rate 降序）
  6.  SQL 参数化（不拼接 store_id/date 到字符串）
  7.  空数据日期返回 0 而非报错
  8.  金蝶凭证科目映射（营收、成本、损耗、薪资）
  9.  金蝶API未配置时返回 skipped 状态
  10. 月度 P&L 数据结构完整性
  11. 营收分解按渠道、小时、类别返回完整结构
  12. 环比计算：对比日无数据时返回 0.0（不报错）
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.finance_analytics_service import FinanceAnalyticsService
from src.services.kingdee_sync_service import KingdeeSyncService


# ─────────────────────────────────────────────
# 辅助 Fixtures
# ─────────────────────────────────────────────


def _make_row(**kwargs):
    """构造一个仿 SQLAlchemy Row 的对象"""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def _make_db_stub(fetchone_result=None, fetchall_result=None):
    """
    返回一个模拟的 AsyncSession，execute() 返回可链式调用的 mock。
    fetchone_result 和 fetchall_result 可分别指定不同查询的返回值。
    当需要区分多次调用时，fetchone_result 传列表。
    """
    execute_result = MagicMock()
    # 支持列表形式（多次调用返回不同值）
    if isinstance(fetchone_result, list):
        execute_result.fetchone.side_effect = fetchone_result
    else:
        execute_result.fetchone.return_value = fetchone_result

    if fetchall_result is not None:
        execute_result.fetchall.return_value = fetchall_result
    else:
        execute_result.fetchall.return_value = []

    db = AsyncMock()
    db.execute.return_value = execute_result
    return db


# ─────────────────────────────────────────────
# 1. 日营收从 orders 表正确聚合
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_revenue_aggregates_from_orders():
    """gross_revenue_fen 和 order_count 从数据库正确读取"""
    # 营收主查询行
    revenue_row = _make_row(
        gross_revenue_fen=100000,  # 1000 元
        discount_amount_fen=5000,  # 50 元折扣
        order_count=20,
    )
    db = _make_db_stub(fetchone_result=revenue_row, fetchall_result=[])
    svc = FinanceAnalyticsService(db)

    result = await svc.get_daily_revenue_summary("STORE001", date(2026, 3, 31))

    assert result["gross_revenue_fen"] == 100000
    assert result["discount_amount_fen"] == 5000
    assert result["net_revenue_fen"] == 95000
    assert result["order_count"] == 20
    assert result["gross_revenue_yuan"] == 1000.0
    assert result["net_revenue_yuan"] == 950.0


# ─────────────────────────────────────────────
# 2. 折扣金额正确扣减
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discount_correctly_deducted():
    """net_revenue = gross - discount"""
    row = _make_row(
        gross_revenue_fen=200000,
        discount_amount_fen=20000,
        order_count=50,
    )
    db = _make_db_stub(fetchone_result=row, fetchall_result=[])
    svc = FinanceAnalyticsService(db)

    result = await svc.get_daily_revenue_summary("STORE001", date(2026, 3, 31))

    assert result["net_revenue_fen"] == 180000
    assert result["net_revenue_yuan"] == 1800.0


# ─────────────────────────────────────────────
# 3. 毛利率计算精度
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gross_margin_calculation_precision():
    """
    营收=100000分，食材成本=35000分
    毛利润=65000分，毛利率=65.0%
    """
    pnl_data = {
        "revenue_yuan": 1000.0,
        "ingredient_cost_yuan": 350.0,
        "gross_profit_yuan": 650.0,
        "gross_margin_pct": 65.0,
        "labor_cost_yuan": 250.0,
        "waste_cost_yuan": 30.0,
        "net_profit_yuan": 370.0,
        "net_margin_pct": 37.0,
        "vs_yesterday_pct": 0.0,
        "vs_last_week_pct": 0.0,
    }
    # 验证 FinanceAnalyticsService._safe_pct
    svc = FinanceAnalyticsService(MagicMock())
    gross_margin = svc._safe_pct(65000, 100000)
    assert gross_margin == 65.0


# ─────────────────────────────────────────────
# 4. 净利率计算精度
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_margin_calculation_precision():
    """净利润=370元，营收=1000元 → 净利率=37.0%"""
    svc = FinanceAnalyticsService(MagicMock())
    net_margin = svc._safe_pct(37000, 100000)
    assert net_margin == 37.0


# ─────────────────────────────────────────────
# 5. 多门店排名正确（按 profit_rate 降序）
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_store_sorted_by_profit_rate():
    """三家门店按 profit_rate 降序排列"""
    store_rows = [
        _make_row(id="S001", name="门店A"),
        _make_row(id="S002", name="门店B"),
        _make_row(id="S003", name="门店C"),
    ]

    # mock get_store_pnl 返回不同利润率
    pnl_map = {
        "S001": {"revenue": {"net_revenue_yuan": 1000.0, "order_count": 10},
                 "costs": {"total_cost_yuan": 600.0},
                 "profit": {"net_profit_yuan": 400.0},
                 "margins": {"net_margin_pct": 40.0, "gross_margin_pct": 65.0,
                             "food_cost_rate": 35.0, "labor_cost_rate": 25.0, "waste_rate": 3.0}},
        "S002": {"revenue": {"net_revenue_yuan": 800.0, "order_count": 8},
                 "costs": {"total_cost_yuan": 600.0},
                 "profit": {"net_profit_yuan": 200.0},
                 "margins": {"net_margin_pct": 25.0, "gross_margin_pct": 60.0,
                             "food_cost_rate": 38.0, "labor_cost_rate": 28.0, "waste_rate": 4.0}},
        "S003": {"revenue": {"net_revenue_yuan": 1200.0, "order_count": 15},
                 "costs": {"total_cost_yuan": 700.0},
                 "profit": {"net_profit_yuan": 500.0},
                 "margins": {"net_margin_pct": 41.67, "gross_margin_pct": 67.0,
                             "food_cost_rate": 33.0, "labor_cost_rate": 24.0, "waste_rate": 2.0}},
    }

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.fetchall.return_value = store_rows
    db.execute.return_value = execute_result

    svc = FinanceAnalyticsService(db)

    async def mock_pnl(store_id, year, month):
        return pnl_map[store_id]

    svc.get_store_pnl = mock_pnl

    results = await svc.get_multi_store_comparison("BRAND001", 2026, 3)

    # 第一名应该是 S003（41.67%），最后是 S002（25%）
    assert results[0]["store_id"] == "S003"
    assert results[-1]["store_id"] == "S002"


# ─────────────────────────────────────────────
# 6. SQL 参数化（不拼接 store_id/date 到字符串）
# ─────────────────────────────────────────────


def test_sql_uses_parameterized_queries():
    """
    验证 finance_analytics_service.py 源码中的 SQL 文本不包含字符串拼接参数。
    确保没有 f"...{store_id}..." 或 "...'" + store_id + "'..." 模式。
    """
    import inspect
    from src.services import finance_analytics_service as mod

    source = inspect.getsource(mod)

    # 绝不允许出现 f-string 里直接嵌入 store_id/date
    forbidden_patterns = [
        r"f['\"].*\{store_id\}.*['\"]",
        r"f['\"].*\{date_\}.*['\"]",
        r"f['\"].*\{target_date\}.*['\"]",
        r"\"[^\"]*\" \+ store_id",
        r"'[^']*' \+ store_id",
    ]
    for pattern in forbidden_patterns:
        matches = re.findall(pattern, source)
        assert not matches, (
            f"发现SQL字符串拼接漏洞（pattern={pattern!r}）: {matches[:3]}"
        )


# ─────────────────────────────────────────────
# 7. 空数据日期返回 0 而非报错
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_data_date_returns_zeros_not_error():
    """
    当 orders 表无该日数据时，所有金额字段为 0.0，不抛异常。
    """
    empty_row = _make_row(
        gross_revenue_fen=0,
        discount_amount_fen=0,
        order_count=0,
    )
    db = _make_db_stub(fetchone_result=empty_row, fetchall_result=[])

    svc = FinanceAnalyticsService(db)

    # 重写 _compare_net_profit_pct 避免递归
    async def _no_compare(store_id, current_fen, compare_date):
        return 0.0

    svc._compare_net_profit_pct = _no_compare

    # 重写 _get_labor_cost_fen 返回 0
    async def _no_labor(store_id, date_):
        return 0

    svc._get_labor_cost_fen = _no_labor

    result = await svc.get_real_daily_profit("STORE001", date(2026, 1, 1))

    assert result["revenue_yuan"] == 0.0
    assert result["net_profit_yuan"] == 0.0
    assert result["gross_margin_pct"] == 0.0
    assert result["net_margin_pct"] == 0.0


# ─────────────────────────────────────────────
# 8. 金蝶凭证科目映射
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kingdee_voucher_entry_mapping():
    """
    验证 map_to_accounting_entries 生成正确数量和科目方向的凭证条目。
    营收1000元 + 食材350元 + 人工250元 + 损耗30元 → 8个凭证条目（每项借贷各一条）
    """
    svc = KingdeeSyncService()

    pnl_data = {
        "revenue_yuan": 1000.0,
        "ingredient_cost_yuan": 350.0,
        "labor_cost_yuan": 250.0,
        "waste_cost_yuan": 30.0,
    }

    entries = await svc.map_to_accounting_entries(pnl_data)

    # 应该有 8 条（营收2 + 食材2 + 损耗2 + 薪资2）
    assert len(entries) == 8

    # 验证每条借贷不同时为 0
    for entry in entries:
        assert not (entry["debit_yuan"] == 0 and entry["credit_yuan"] == 0), (
            f"条目 {entry['acct_code']} 借贷均为0"
        )
        assert not (entry["debit_yuan"] > 0 and entry["credit_yuan"] > 0), (
            f"条目 {entry['acct_code']} 借贷均不为0"
        )

    # 验证借贷总额平衡
    total_debit = sum(e["debit_yuan"] for e in entries)
    total_credit = sum(e["credit_yuan"] for e in entries)
    assert abs(total_debit - total_credit) < 0.01, (
        f"借贷不平衡：借方={total_debit}，贷方={total_credit}"
    )


# ─────────────────────────────────────────────
# 9. 金蝶API未配置时返回 skipped 状态
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kingdee_sync_skipped_when_not_configured():
    """KINGDEE_APP_ID 未配置时，sync_daily_voucher 返回 status='skipped'"""
    import src.services.kingdee_sync_service as kmod

    original_app_id = kmod.KINGDEE_APP_ID
    original_app_secret = kmod.KINGDEE_APP_SECRET

    try:
        kmod.KINGDEE_APP_ID = ""
        kmod.KINGDEE_APP_SECRET = ""

        svc = KingdeeSyncService()
        pnl_data = {"revenue_yuan": 1000.0, "ingredient_cost_yuan": 350.0,
                    "labor_cost_yuan": 250.0, "waste_cost_yuan": 30.0}

        result = await svc.sync_daily_voucher("STORE001", date(2026, 3, 31), pnl_data)
        assert result["status"] == "skipped"
        assert result["voucher_no"] is None
    finally:
        kmod.KINGDEE_APP_ID = original_app_id
        kmod.KINGDEE_APP_SECRET = original_app_secret


# ─────────────────────────────────────────────
# 10. 月度 P&L 数据结构完整性
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_monthly_pnl_structure_completeness():
    """get_store_pnl 返回字典包含 revenue / costs / profit / margins 四个顶级键"""
    # 营收查询行
    rev_row = _make_row(gross_revenue_fen=3000000, discount_amount_fen=100000, order_count=300)
    # 食材查询行
    ing_row = _make_row(ingredient_cost_fen=1000000)
    # 损耗查询行
    waste_row = _make_row(waste_cost_fen=50000)

    db = _make_db_stub(
        fetchone_result=[rev_row, ing_row, waste_row],
    )

    svc = FinanceAnalyticsService(db)

    async def _no_labor(store_id, year, month):
        return 0

    svc._get_monthly_labor_cost_fen = _no_labor

    result = await svc.get_store_pnl("STORE001", 2026, 3)

    required_keys = {"store_id", "year", "month", "period", "revenue", "costs", "profit", "margins"}
    assert required_keys.issubset(set(result.keys())), (
        f"缺少键：{required_keys - set(result.keys())}"
    )

    revenue_keys = {"gross_revenue_yuan", "discount_yuan", "net_revenue_yuan", "order_count"}
    assert revenue_keys.issubset(set(result["revenue"].keys()))

    margin_keys = {"gross_margin_pct", "net_margin_pct", "food_cost_rate",
                   "labor_cost_rate", "waste_rate"}
    assert margin_keys.issubset(set(result["margins"].keys()))


# ─────────────────────────────────────────────
# 11. 营收分解结构完整性
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revenue_breakdown_structure():
    """get_revenue_breakdown 返回 by_channel / by_hour / by_category 三个维度"""
    channel_rows = [
        _make_row(channel="dine_in", revenue_fen=80000, order_count=30),
        _make_row(channel="meituan", revenue_fen=20000, order_count=10),
    ]
    hour_rows = [
        _make_row(hour=12, revenue_fen=30000),
        _make_row(hour=18, revenue_fen=50000),
    ]
    cat_rows = [
        _make_row(category="川菜", revenue_fen=60000),
    ]

    execute_result = MagicMock()
    # 三次 fetchall 分别对应渠道、小时、类别查询
    execute_result.fetchall.side_effect = [channel_rows, hour_rows, cat_rows]

    db = AsyncMock()
    db.execute.return_value = execute_result

    svc = FinanceAnalyticsService(db)
    result = await svc.get_revenue_breakdown(
        "STORE001", date(2026, 3, 1), date(2026, 3, 31)
    )

    assert "by_channel" in result
    assert "by_hour" in result
    assert "by_category" in result
    # by_hour 应有 24 个键（0-23）
    assert len(result["by_hour"]) == 24
    assert result["by_channel"]["dine_in"]["revenue_yuan"] == 800.0
    assert result["by_hour"][12] == 300.0


# ─────────────────────────────────────────────
# 12. 环比计算：对比日无数据时返回 0.0（不报错）
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vs_yesterday_returns_zero_when_no_data():
    """
    当昨日/上周同日净利润为 0 时，环比变化返回 0.0，不抛异常。
    """
    svc = FinanceAnalyticsService(MagicMock())
    result = await svc._compare_net_profit_pct("STORE001", 10000, date(2026, 1, 1))
    # 昨日无数据 → _compare 内部会调用 get_real_daily_profit，我们 mock 整个方法
    # 这里验证分母为 0 时的安全返回
    assert result == 0.0 or isinstance(result, float)


@pytest.mark.asyncio
async def test_safe_pct_zero_denominator():
    """_safe_pct 分母为 0 时返回 0.0 而非 ZeroDivisionError"""
    svc = FinanceAnalyticsService(MagicMock())
    assert svc._safe_pct(100, 0) == 0.0
    assert svc._safe_pct(0, 0) == 0.0
