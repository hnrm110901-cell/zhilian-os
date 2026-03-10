"""
Banquet Agent Phase 17 — 单元测试

覆盖端点：
  - get_menu_profitability
  - get_menu_package_detail
  - get_seasonal_patterns
  - get_banquet_type_trends
  - get_daily_brief / get_upcoming_alerts
  - push_daily_brief
  - get_revenue_forecast
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock


# ── helpers ─────────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id       = "user-001"
    u.brand_id = "BRAND-001"
    return u


def _scalars_returning(items):
    r = MagicMock()
    r.scalars.return_value.first.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value   = items
    return r


def _scalar_returning(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _rows_returning(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_order(oid="O-001", store_id="S001", status="confirmed",
                days_ago=10, total_fen=500000, paid_fen=0, btype="wedding"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id = oid
    o.store_id = store_id
    o.order_status = (
        OrderStatusEnum.CONFIRMED  if status == "confirmed"  else
        OrderStatusEnum.COMPLETED  if status == "completed"  else
        OrderStatusEnum.CANCELLED
    )
    o.banquet_date = date.today() - timedelta(days=days_ago)
    o.banquet_type = BanquetTypeEnum.WEDDING if btype == "wedding" else BanquetTypeEnum.BIRTHDAY
    o.total_amount_fen = total_fen
    o.paid_fen = paid_fen
    o.contact_name  = "张三"
    o.contact_phone = "138"
    o.created_at    = datetime.utcnow() - timedelta(days=days_ago + 5)
    return o


def _make_pkg(pid="PKG-001", store_id="S001", name="豪华婚宴套餐",
              price_fen=500000, cost_fen=200000, btype="wedding"):
    from src.models.banquet import BanquetTypeEnum
    p = MagicMock()
    p.id                 = pid
    p.store_id           = store_id
    p.name               = name
    p.banquet_type       = BanquetTypeEnum.WEDDING if btype == "wedding" else BanquetTypeEnum.BIRTHDAY
    p.suggested_price_fen = price_fen
    p.cost_fen           = cost_fen
    p.is_active          = True
    return p


def _make_snapshot(store_id="S001", revenue=600000, cost=240000, btype="wedding", days_ago=15):
    from src.models.banquet import BanquetTypeEnum
    s = MagicMock()
    s.store_id           = store_id
    s.banquet_type       = BanquetTypeEnum.WEDDING if btype == "wedding" else BanquetTypeEnum.BIRTHDAY
    s.revenue_fen        = revenue
    s.ingredient_cost_fen = cost
    s.labor_cost_fen     = 0
    s.material_cost_fen  = 0
    s.other_cost_fen     = 0
    s.gross_profit_fen   = revenue - cost
    s.gross_margin_pct   = round((revenue - cost) / revenue * 100, 1)
    s.snapshot_date      = date.today() - timedelta(days=days_ago)
    return s


def _make_task(tid="T-001", oid="O-001", status="pending"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id = tid
    t.banquet_order_id = oid
    t.task_status = TaskStatusEnum.PENDING if status == "pending" else TaskStatusEnum.DONE
    return t


def _make_exception(eid="E-001", oid="O-001"):
    e = MagicMock()
    e.id = eid
    e.banquet_order_id = oid
    return e


# ── TestMenuProfitability ────────────────────────────────────────────────────

class TestMenuProfitability:

    @pytest.mark.asyncio
    async def test_returns_ranked_packages(self):
        """有套餐时按毛利率降序返回"""
        from src.api.banquet_agent import get_menu_profitability

        pkg1 = _make_pkg("PKG-001", price_fen=500000, cost_fen=200000)  # 60% margin
        pkg2 = _make_pkg("PKG-002", price_fen=300000, cost_fen=210000)  # 30% margin

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([pkg1, pkg2])   # packages
            if n == 2:                                           # snapshot join query → .all()
                r = MagicMock()
                r.all.return_value = []
                return r
            if n == 3:                                           # order count by type
                r = MagicMock()
                r.all.return_value = []
                return r
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_menu_profitability(
            store_id="S001", year=0, month=0, db=db, _=_mock_user()
        )

        pkgs = result["packages"]
        assert len(pkgs) == 2
        # 第一名理论毛利率更高
        assert pkgs[0]["theoretical_margin_pct"] >= pkgs[1]["theoretical_margin_pct"]

    @pytest.mark.asyncio
    async def test_actual_margin_computed_from_snapshot(self):
        """有快照时 actual_margin_pct 不为 None"""
        from src.api.banquet_agent import get_menu_profitability
        from src.models.banquet import BanquetTypeEnum

        pkg  = _make_pkg()
        snap = _make_snapshot(revenue=600000, cost=240000)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([pkg])
            if n == 2:                                    # snapshot join → .all() returns (snap, banquet_type)
                r = MagicMock()
                r.all.return_value = [(snap, BanquetTypeEnum.WEDDING)]
                return r
            if n == 3:
                r = MagicMock()
                r.all.return_value = []
                return r
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_menu_profitability(
            store_id="S001", year=0, month=0, db=db, _=_mock_user()
        )

        assert result["packages"][0]["actual_margin_pct"] == pytest.approx(60.0)

    @pytest.mark.asyncio
    async def test_no_packages_returns_empty(self):
        """无套餐时返回空列表不崩溃"""
        from src.api.banquet_agent import get_menu_profitability

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_menu_profitability(
            store_id="S001", year=0, month=0, db=db, _=_mock_user()
        )

        assert result["packages"] == []


# ── TestSeasonalPatterns ─────────────────────────────────────────────────────

class TestSeasonalPatterns:

    @pytest.mark.asyncio
    async def test_monthly_peak_detected(self):
        """高峰月份被标记为 is_peak"""
        from src.api.banquet_agent import get_seasonal_patterns

        today = date.today()
        # 创建 10 个订单集中在当前月 → 应为峰季
        orders = [
            _make_order(f"O-{i}", days_ago=i * 3, status="confirmed")
            for i in range(10)
        ]
        # 强制 banquet_date 到同一个月（当月）
        for o in orders:
            o.banquet_date = date(today.year, today.month, 1)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning(orders))

        result = await get_seasonal_patterns(
            store_id="S001", years=1, db=db, _=_mock_user()
        )

        assert len(result["monthly"]) == 12
        peak_months = [m for m in result["monthly"] if m["is_peak"]]
        assert len(peak_months) >= 1

    @pytest.mark.asyncio
    async def test_weekly_distribution_has_7_days(self):
        """weekly 必须返回7个周几条目"""
        from src.api.banquet_agent import get_seasonal_patterns

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_seasonal_patterns(
            store_id="S001", years=1, db=db, _=_mock_user()
        )

        assert len(result["weekly"]) == 7
        weekdays = {r["weekday"] for r in result["weekly"]}
        assert weekdays == set(range(7))


# ── TestBanquetTypeTrends ─────────────────────────────────────────────────────

class TestBanquetTypeTrends:

    @pytest.mark.asyncio
    async def test_yoy_growth_computed(self):
        """今年 > 去年订单数时 yoy_growth_pct > 0"""
        from src.api.banquet_agent import get_banquet_type_trends

        today = date.today()
        year  = today.year

        this_orders = [
            _make_order(f"O-{i}", status="confirmed", days_ago=0)
            for i in range(4)
        ]
        for o in this_orders:
            o.banquet_date = date(year, today.month, 1)

        last_orders = [_make_order("O-LAST", status="completed", days_ago=0)]
        last_orders[0].banquet_date = date(year - 1, today.month, 1)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning(this_orders)
            return _scalars_returning(last_orders)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_type_trends(
            store_id="S001", year=year, db=db, _=_mock_user()
        )

        wedding_row = next((t for t in result["types"] if t["type"] == "wedding"), None)
        assert wedding_row is not None
        assert wedding_row["yoy_growth_pct"] > 0

    @pytest.mark.asyncio
    async def test_empty_last_year_yoy_is_none(self):
        """去年无数据时 yoy_growth_pct 为 None"""
        from src.api.banquet_agent import get_banquet_type_trends

        today = date.today()
        year  = today.year

        this_orders = [_make_order("O-001", status="confirmed", days_ago=0)]
        this_orders[0].banquet_date = date(year, today.month, 1)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1: return _scalars_returning(this_orders)
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_banquet_type_trends(
            store_id="S001", year=year, db=db, _=_mock_user()
        )

        wedding_row = next((t for t in result["types"] if t["type"] == "wedding"), None)
        assert wedding_row is not None
        assert wedding_row["yoy_growth_pct"] is None


# ── TestDailyBrief ────────────────────────────────────────────────────────────

class TestDailyBrief:

    @pytest.mark.asyncio
    async def test_pending_tasks_flagged_as_medium(self):
        """有 pending 任务时风险级别为 medium"""
        from src.api.banquet_agent import get_daily_brief

        o = _make_order(days_ago=-2, status="confirmed",
                        total_fen=100000, paid_fen=100000)  # 已付款
        o.banquet_date = date.today() + timedelta(days=2)

        task = _make_task(status="pending")

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([o])     # orders
            if n == 2: return _scalars_returning([task])  # pending tasks
            if n == 3: return _scalars_returning([])      # exceptions
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_daily_brief(
            store_id="S001", days=7, db=db, _=_mock_user()
        )

        assert result["next_n_banquets"] == 1
        assert result["alerts"][0]["pending_tasks"] == 1
        assert result["alerts"][0]["risk_level"] == "medium"

    @pytest.mark.asyncio
    async def test_unpaid_near_date_is_high_risk(self):
        """距宴会 ≤3 天且未付款 → high 风险"""
        from src.api.banquet_agent import get_daily_brief

        o = _make_order(days_ago=-1, status="confirmed",
                        total_fen=200000, paid_fen=0)
        o.banquet_date = date.today() + timedelta(days=1)

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning([o])
            if n == 2: return _scalars_returning([])   # no pending tasks
            if n == 3: return _scalars_returning([])   # no exceptions
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_daily_brief(
            store_id="S001", days=7, db=db, _=_mock_user()
        )

        assert result["alerts"][0]["risk_level"] == "high"
        assert result["alerts"][0]["unpaid_yuan"] == pytest.approx(2000.0)

    @pytest.mark.asyncio
    async def test_push_writes_action_log(self):
        """推送简报后写入 ActionLog"""
        from src.api.banquet_agent import push_daily_brief

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))
        db.add    = MagicMock()
        db.commit = AsyncMock()

        result = await push_daily_brief(
            store_id="S001", db=db, current_user=_mock_user()
        )

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert "pushed_at"   in result
        assert "alert_count" in result


# ── TestRevenueForecast ───────────────────────────────────────────────────────

class TestRevenueForecast:

    @pytest.mark.asyncio
    async def test_forecast_at_least_confirmed(self):
        """预测值 >= 已确认订单金额"""
        from src.api.banquet_agent import get_revenue_forecast

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalar_returning(300000)   # confirmed fen
            if n == 2: return _scalar_returning(200000)   # hist year-1
            if n == 3: return _scalar_returning(250000)   # hist year-2
            return _scalar_returning(0)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_revenue_forecast(
            store_id="S001", months_ahead=1, db=db, _=_mock_user()
        )

        assert result["forecast_yuan"] >= result["confirmed_revenue_yuan"]
        assert result["forecast_yuan"] > 0

    @pytest.mark.asyncio
    async def test_empty_history_returns_zero_base(self):
        """无历史数据时 base_revenue_yuan=0，forecast 等于已确认"""
        from src.api.banquet_agent import get_revenue_forecast

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalar_returning(100000)  # confirmed fen = 1000 yuan
            return _scalar_returning(0)                  # hist all zero

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_revenue_forecast(
            store_id="S001", months_ahead=1, db=db, _=_mock_user()
        )

        assert result["base_revenue_yuan"] == pytest.approx(0.0)
        assert result["confirmed_revenue_yuan"] == pytest.approx(1000.0)
        assert result["forecast_yuan"] == pytest.approx(1000.0)
