"""
Banquet Agent Phase 9 — 单元测试

覆盖端点：
  - get_monthly_trend      : 近 N 月营收/订单数/毛利走势
  - get_package_performance: 套餐效益分析
  - get_upcoming_tasks     : 未来 N 天任务看板（按日期分组）
"""

import pytest
from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, MagicMock


# ── helpers ─────────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id = "user-001"
    u.brand_id = "BRAND-001"
    return u


def _scalars_returning(items):
    r = MagicMock()
    r.scalars.return_value.first.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value = items
    r.first.return_value = items[0] if items else None
    r.all.return_value = items
    return r


def _scalar_result(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _grouped_rows(rows):
    """rows: list of namedtuple-like objects returned by .all()"""
    r = MagicMock()
    r.all.return_value = rows
    return r


def _row(yr, mo, cnt, rev):
    r = MagicMock()
    r.yr = yr
    r.mo = mo
    r.cnt = cnt
    r.rev = rev
    return r


def _profit_row(yr, mo, gp):
    r = MagicMock()
    r.yr = yr
    r.mo = mo
    r.gp = gp
    return r


def _usage_row(cnt, rev, last_date):
    r = MagicMock()
    r.cnt = cnt
    r.rev = rev
    r.last_date = last_date
    return r


def _make_task(task_id="T1", name="备餐", role="kitchen", status="pending",
               order_id="ORD-001", banquet_type=None, due_dt=None):
    from src.models.banquet import TaskStatusEnum, TaskOwnerRoleEnum, BanquetTypeEnum
    t = MagicMock()
    t.id = task_id
    t.task_name = name
    t.owner_role = TaskOwnerRoleEnum(role)
    t.banquet_order_id = order_id
    t.due_time = due_dt or datetime.utcnow() + timedelta(days=1)
    t.task_status = TaskStatusEnum(status)
    bt = banquet_type or BanquetTypeEnum.WEDDING
    return t, bt


def _make_pkg(pkg_id="PKG-001", name="豪华婚宴套餐"):
    p = MagicMock()
    p.id = pkg_id
    p.name = name
    return p


# ── get_monthly_trend ────────────────────────────────────────────────────────

class TestMonthlyTrend:

    @pytest.mark.asyncio
    async def test_returns_correct_months_with_data(self):
        from src.api.banquet_agent import get_monthly_trend

        today = date.today()
        rev_rows = _grouped_rows([
            _row(today.year, today.month, 5, 10_000_000),  # 10万元 = 10,000,000 fen
        ])
        gp_rows = _grouped_rows([
            _profit_row(today.year, today.month, 3_000_000),  # 3万元
        ])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[rev_rows, gp_rows])

        result = await get_monthly_trend(store_id="S001", months=6, db=db, _=_mock_user())

        assert len(result["months"]) == 6
        # Last entry is current month
        last = result["months"][-1]
        assert last["month"] == f"{today.year:04d}-{today.month:02d}"
        assert last["order_count"] == 5
        assert last["revenue_yuan"] == pytest.approx(100000.0)
        assert last["gross_profit_yuan"] == pytest.approx(30000.0)

    @pytest.mark.asyncio
    async def test_zero_fills_months_without_data(self):
        from src.api.banquet_agent import get_monthly_trend

        rev_rows = _grouped_rows([])   # no orders at all
        gp_rows  = _grouped_rows([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[rev_rows, gp_rows])

        result = await get_monthly_trend(store_id="S001", months=3, db=db, _=_mock_user())

        assert len(result["months"]) == 3
        for m in result["months"]:
            assert m["order_count"] == 0
            assert m["revenue_yuan"] == 0.0
            assert m["gross_profit_yuan"] == 0.0

    @pytest.mark.asyncio
    async def test_custom_months_param(self):
        from src.api.banquet_agent import get_monthly_trend

        rev_rows = _grouped_rows([])
        gp_rows  = _grouped_rows([])
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[rev_rows, gp_rows])

        result = await get_monthly_trend(store_id="S001", months=12, db=db, _=_mock_user())

        assert len(result["months"]) == 12


# ── get_package_performance ──────────────────────────────────────────────────

class TestPackagePerformance:

    @pytest.mark.asyncio
    async def test_returns_usage_and_revenue(self):
        from src.api.banquet_agent import get_package_performance

        pkg = _make_pkg()
        usage = _usage_row(cnt=8, rev=400_000_00, last_date=date(2026, 2, 14))

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([pkg]),
            MagicMock(first=MagicMock(return_value=usage)),
            _scalar_result(32.5),
        ])

        result = await get_package_performance(
            store_id="S001", pkg_id="PKG-001", db=db, _=_mock_user()
        )

        assert result["usage_count"] == 8
        assert result["total_revenue_yuan"] == pytest.approx(400000.0)
        assert result["avg_gross_margin_pct"] == pytest.approx(32.5)
        assert result["last_used_date"] == "2026-02-14"
        assert result["package_name"] == "豪华婚宴套餐"

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_orders(self):
        from src.api.banquet_agent import get_package_performance

        pkg = _make_pkg()
        usage = _usage_row(cnt=0, rev=None, last_date=None)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([pkg]),
            MagicMock(first=MagicMock(return_value=usage)),
            _scalar_result(None),
        ])

        result = await get_package_performance(
            store_id="S001", pkg_id="PKG-001", db=db, _=_mock_user()
        )

        assert result["usage_count"] == 0
        assert result["total_revenue_yuan"] == 0.0
        assert result["avg_gross_margin_pct"] is None
        assert result["last_used_date"] is None

    @pytest.mark.asyncio
    async def test_404_on_unknown_package(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import get_package_performance

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await get_package_performance(
                store_id="S001", pkg_id="NONEXISTENT", db=db, _=_mock_user()
            )
        assert exc.value.status_code == 404


# ── get_upcoming_tasks ───────────────────────────────────────────────────────

class TestUpcomingTasks:

    @pytest.mark.asyncio
    async def test_returns_days_grouped_by_date(self):
        from src.api.banquet_agent import get_upcoming_tasks

        t1, bt1 = _make_task("T1", "备餐",  "kitchen", "pending",  due_dt=datetime.utcnow() + timedelta(days=1))
        t2, bt2 = _make_task("T2", "摆台",  "service", "pending",  due_dt=datetime.utcnow() + timedelta(days=1))
        t3, bt3 = _make_task("T3", "采购",  "purchase","done",     due_dt=datetime.utcnow() + timedelta(days=2))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[
            (t1, bt1), (t2, bt2), (t3, bt3)
        ])))

        result = await get_upcoming_tasks(
            store_id="S001", days=7, owner_role=None, db=db, _=_mock_user()
        )

        assert result["total_pending"] == 2
        assert result["total_done"] == 1
        # Should have 2 different dates
        assert len(result["days"]) == 2

    @pytest.mark.asyncio
    async def test_empty_when_no_tasks(self):
        from src.api.banquet_agent import get_upcoming_tasks

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        result = await get_upcoming_tasks(
            store_id="S001", days=7, owner_role=None, db=db, _=_mock_user()
        )

        assert result["total_pending"] == 0
        assert result["total_done"] == 0
        assert result["days"] == []

    @pytest.mark.asyncio
    async def test_role_filter_passed_to_query(self):
        """Role filter should not raise — query executes cleanly with role param"""
        from src.api.banquet_agent import get_upcoming_tasks

        t1, bt1 = _make_task("T1", "炒菜", "kitchen", "pending")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[
            (t1, bt1)
        ])))

        result = await get_upcoming_tasks(
            store_id="S001", days=7, owner_role="kitchen", db=db, _=_mock_user()
        )

        assert result["total_pending"] == 1

    @pytest.mark.asyncio
    async def test_days_sorted_ascending(self):
        from src.api.banquet_agent import get_upcoming_tasks

        t1, bt1 = _make_task("T1", due_dt=datetime.utcnow() + timedelta(days=3))
        t2, bt2 = _make_task("T2", due_dt=datetime.utcnow() + timedelta(days=1))
        db = AsyncMock()
        # Return in reverse order — grouping should still sort ascending
        db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[
            (t1, bt1), (t2, bt2)
        ])))

        result = await get_upcoming_tasks(
            store_id="S001", days=7, owner_role=None, db=db, _=_mock_user()
        )

        dates = [d["date"] for d in result["days"]]
        assert dates == sorted(dates)
