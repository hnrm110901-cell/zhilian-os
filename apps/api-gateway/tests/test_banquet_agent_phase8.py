"""
Banquet Agent Phase 8 — 单元测试

覆盖端点：
  - get_order_beo    : BEO 执行单（订单 + 任务分组）
  - get_receivables  : 应收账款列表
  - sync_kpi         : KPI 日报同步（upsert）
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id = "user-001"
    u.brand_id = "BRAND-001"
    return u


def _make_order(
    order_id="ORD-001",
    store_id="S001",
    status="confirmed",
    banquet_date=None,
    total_amount_fen=5000000,
    paid_fen=1000000,
    has_package=False,
    has_bookings=False,
    tasks=None,
):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum, DepositStatusEnum
    o = MagicMock()
    o.id = order_id
    o.store_id = store_id
    o.banquet_type = BanquetTypeEnum.WEDDING
    o.banquet_date = banquet_date or date(2026, 10, 1)
    o.people_count = 200
    o.table_count = 20
    o.contact_name = "王五"
    o.contact_phone = "13700001111"
    o.remark = None
    o.total_amount_fen = total_amount_fen
    o.paid_fen = paid_fen
    status_map = {s.value: s for s in OrderStatusEnum}
    o.order_status = status_map.get(status, OrderStatusEnum.CONFIRMED)
    o.deposit_status = DepositStatusEnum.PARTIAL

    # package
    if has_package:
        pkg = MagicMock()
        pkg.name = "豪华婚宴套餐"
        o.package = pkg
    else:
        o.package = None

    # bookings
    if has_bookings:
        booking = MagicMock()
        booking.hall_id = "HALL-001"
        o.bookings = [booking]
    else:
        o.bookings = []

    # tasks
    o.tasks = tasks or []

    return o


def _make_task(task_id="TASK-001", name="备餐", role="kitchen", status="pending"):
    t = MagicMock()
    t.id = task_id
    t.task_name = name
    t.owner_role = role
    t.due_time = datetime(2026, 10, 1, 9, 0)
    t.task_status = MagicMock()
    t.task_status.value = status
    return t


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
    r.first.return_value = (value, value)  # for count+sum tuples
    return r


def _count_sum_result(count, total):
    r = MagicMock()
    r.first.return_value = (count, total)
    return r


# ── get_order_beo ──────────────────────────────────────────────────────────────

class TestGetOrderBeo:

    @pytest.mark.asyncio
    async def test_returns_beo_with_tasks_grouped_by_role(self):
        from src.api.banquet_agent import get_order_beo

        tasks = [
            _make_task("T1", "备餐",  "kitchen", "pending"),
            _make_task("T2", "摆台",  "service", "pending"),
            _make_task("T3", "炒菜",  "kitchen", "done"),
        ]
        order = _make_order(tasks=tasks)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_beo(store_id="S001", order_id="ORD-001", db=db, _=_mock_user())

        assert result["order_id"] == "ORD-001"
        assert result["banquet_type"] == "wedding"
        assert result["total_amount_yuan"] == pytest.approx(50000.0)
        assert result["paid_yuan"] == pytest.approx(10000.0)
        assert result["balance_yuan"] == pytest.approx(40000.0)
        assert len(result["tasks_by_role"]["kitchen"]) == 2
        assert len(result["tasks_by_role"]["service"]) == 1

    @pytest.mark.asyncio
    async def test_returns_beo_no_tasks_no_package(self):
        from src.api.banquet_agent import get_order_beo

        order = _make_order()  # no tasks, no package
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_beo(store_id="S001", order_id="ORD-001", db=db, _=_mock_user())

        assert result["tasks_by_role"] == {}
        assert result["package_name"] is None
        assert result["hall_name"] is None

    @pytest.mark.asyncio
    async def test_returns_package_name(self):
        from src.api.banquet_agent import get_order_beo

        order = _make_order(has_package=True)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_order_beo(store_id="S001", order_id="ORD-001", db=db, _=_mock_user())

        assert result["package_name"] == "豪华婚宴套餐"

    @pytest.mark.asyncio
    async def test_404_when_order_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import get_order_beo

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await get_order_beo(store_id="S001", order_id="NONEXISTENT", db=db, _=_mock_user())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_hall_name_loaded_when_booking_exists(self):
        from src.api.banquet_agent import get_order_beo

        order = _make_order(has_bookings=True)
        hall = MagicMock()
        hall.name = "大宴会厅"

        db = AsyncMock()
        # first call: order, second call: hall
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),
            _scalars_returning([hall]),
        ])

        result = await get_order_beo(store_id="S001", order_id="ORD-001", db=db, _=_mock_user())

        assert result["hall_name"] == "大宴会厅"


# ── get_receivables ────────────────────────────────────────────────────────────

class TestGetReceivables:

    @pytest.mark.asyncio
    async def test_returns_outstanding_orders(self):
        from src.api.banquet_agent import get_receivables

        o1 = _make_order("O1", total_amount_fen=5000000, paid_fen=1000000,
                          banquet_date=date(2026, 5, 10))
        o2 = _make_order("O2", total_amount_fen=3000000, paid_fen=500000,
                          banquet_date=date(2026, 6, 15))

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o1, o2]))

        result = await get_receivables(store_id="S001", db=db, _=_mock_user())

        assert result["order_count"] == 2
        # total outstanding: (5000000-1000000 + 3000000-500000) / 100 = 65000
        assert result["total_outstanding_yuan"] == pytest.approx(65000.0)
        assert result["orders"][0]["order_id"] == "O1"
        assert result["orders"][0]["balance_yuan"] == pytest.approx(40000.0)

    @pytest.mark.asyncio
    async def test_empty_when_no_outstanding(self):
        from src.api.banquet_agent import get_receivables

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_receivables(store_id="S001", db=db, _=_mock_user())

        assert result["order_count"] == 0
        assert result["total_outstanding_yuan"] == 0.0
        assert result["orders"] == []

    @pytest.mark.asyncio
    async def test_days_until_event_is_correct(self):
        from src.api.banquet_agent import get_receivables
        from datetime import date as _date

        future_date = _date.today() + timedelta(days=14)
        o = _make_order(banquet_date=future_date, total_amount_fen=2000000, paid_fen=500000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await get_receivables(store_id="S001", db=db, _=_mock_user())

        assert result["orders"][0]["days_until_event"] == 14


# ── sync_kpi ───────────────────────────────────────────────────────────────────

class TestSyncKpi:

    @pytest.mark.asyncio
    async def test_creates_new_kpi_row(self):
        from src.api.banquet_agent import sync_kpi

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _count_sum_result(3, 15000000),   # order count + revenue
            _scalar_result(2000000),           # gross profit
            _scalar_result(20),                # lead count
            _scalar_result(5),                 # won count
            _scalars_returning([]),            # existing KPI (not found → create)
        ])
        db.add = MagicMock()
        db.commit = AsyncMock()

        result = await sync_kpi(store_id="S001", sync_date="2026-03-09", db=db, _=_mock_user())

        assert result["synced"] is True
        assert result["date"] == "2026-03-09"
        assert result["order_count"] == 3
        assert result["revenue_yuan"] == pytest.approx(150000.0)
        assert result["gross_profit_yuan"] == pytest.approx(20000.0)
        assert result["conversion_rate_pct"] == pytest.approx(25.0)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_kpi_row(self):
        from src.api.banquet_agent import sync_kpi

        existing_kpi = MagicMock()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _count_sum_result(2, 8000000),
            _scalar_result(1000000),
            _scalar_result(10),
            _scalar_result(2),
            _scalars_returning([existing_kpi]),  # found → update
        ])
        db.commit = AsyncMock()

        result = await sync_kpi(store_id="S001", sync_date="2026-03-09", db=db, _=_mock_user())

        assert result["synced"] is True
        assert existing_kpi.order_count == 2
        assert existing_kpi.revenue_fen == 8000000

    @pytest.mark.asyncio
    async def test_defaults_to_today_when_no_date(self):
        from src.api.banquet_agent import sync_kpi
        from datetime import date as _date

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _count_sum_result(0, 0),
            _scalar_result(0),
            _scalar_result(0),
            _scalar_result(0),
            _scalars_returning([]),
        ])
        db.add = MagicMock()
        db.commit = AsyncMock()

        result = await sync_kpi(store_id="S001", sync_date=None, db=db, _=_mock_user())

        assert result["date"] == _date.today().isoformat()

    @pytest.mark.asyncio
    async def test_400_on_invalid_date_format(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import sync_kpi

        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await sync_kpi(store_id="S001", sync_date="not-a-date", db=db, _=_mock_user())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_zero_conversion_when_no_leads(self):
        from src.api.banquet_agent import sync_kpi

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _count_sum_result(1, 5000000),
            _scalar_result(0),
            _scalar_result(0),   # lead_count = 0
            _scalar_result(0),   # won_count = 0
            _scalars_returning([]),
        ])
        db.add = MagicMock()
        db.commit = AsyncMock()

        result = await sync_kpi(store_id="S001", sync_date="2026-03-09", db=db, _=_mock_user())

        assert result["conversion_rate_pct"] == 0.0
