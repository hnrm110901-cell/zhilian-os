"""
Banquet Agent Phase 5 — 单元测试

覆盖端点（API 层，不依赖真实 DB / Redis）：
  - list_halls            : 厅房列表
  - create_hall           : 创建厅房
  - update_hall           : 编辑厅房
  - deactivate_hall       : 停用厅房（软删除）
  - list_packages         : 套餐列表
  - create_package        : 创建套餐
  - update_package        : 编辑套餐
  - deactivate_package    : 下架套餐
  - settle_order          : 结算订单（completed → settled + profit snapshot upsert）
  - push_scan             : 推送扫描（D-7/D-1/逾期/停滞，Redis best-effort）
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id = "user-001"
    return u


def _make_hall(hall_id="HALL-001", store_id="S001", is_active=True):
    h = MagicMock()
    h.id = hall_id
    h.store_id = store_id
    h.name = "一号宴会厅"
    h.hall_type.value = "banquet_hall"
    h.max_tables = 20
    h.max_people = 200
    h.min_spend_fen = 2000000
    h.floor_area_m2 = 500.0
    h.description = "豪华宴会厅"
    h.is_active = is_active
    return h


def _make_package(pkg_id="PKG-001", store_id="S001", is_active=True):
    p = MagicMock()
    p.id = pkg_id
    p.store_id = store_id
    p.name = "经典婚宴套餐"
    p.banquet_type.value = "wedding"
    p.suggested_price_fen = 30000_00   # 30000元
    p.cost_fen = 12000_00              # 12000元
    p.target_people_min = 100
    p.target_people_max = 300
    p.description = "含8道热菜"
    p.is_active = is_active
    return p


def _make_order(order_id="ORD-001", store_id="S001", status_value="completed"):
    from src.models.banquet import OrderStatusEnum
    o = MagicMock()
    o.id = order_id
    o.store_id = store_id
    o.banquet_type.value = "wedding"
    o.banquet_date = date(2026, 9, 18)
    status_map = {
        "completed":  OrderStatusEnum.COMPLETED,
        "confirmed":  OrderStatusEnum.CONFIRMED,
        "settled":    OrderStatusEnum.SETTLED,
    }
    o.order_status = status_map.get(status_value, OrderStatusEnum.COMPLETED)
    return o


def _make_snapshot(snap_id="SNAP-001", order_id="ORD-001"):
    s = MagicMock()
    s.id = snap_id
    s.banquet_order_id = order_id
    s.revenue_fen = 5000000
    s.ingredient_cost_fen = 1500000
    s.labor_cost_fen = 500000
    s.material_cost_fen = 0
    s.other_cost_fen = 100000
    s.gross_profit_fen = 2900000
    s.gross_margin_pct = 58.0
    return s


def _scalars_returning(items):
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = items[0] if items else None
    mock_result.scalars.return_value.all.return_value = items
    mock_result.first.return_value = items[0] if items else None
    mock_result.all.return_value = items
    return mock_result


# ── list_halls ─────────────────────────────────────────────────────────────────

class TestListHalls:

    @pytest.mark.asyncio
    async def test_returns_active_halls(self):
        from src.api.banquet_agent import list_halls

        hall = _make_hall()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([hall]))

        result = await list_halls(store_id="S001", active_only=True, db=db, _=_mock_user())

        assert len(result) == 1
        assert result[0]["hall_id"] == "HALL-001"
        assert result[0]["name"] == "一号宴会厅"
        assert result[0]["min_spend_yuan"] == 20000.0

    @pytest.mark.asyncio
    async def test_returns_all_halls_when_not_active_only(self):
        from src.api.banquet_agent import list_halls

        halls = [_make_hall(hall_id="H1"), _make_hall(hall_id="H2", is_active=False)]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning(halls))

        result = await list_halls(store_id="S001", active_only=False, db=db, _=_mock_user())

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_list(self):
        from src.api.banquet_agent import list_halls

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await list_halls(store_id="S001", active_only=True, db=db, _=_mock_user())

        assert result == []


# ── create_hall ────────────────────────────────────────────────────────────────

class TestCreateHall:

    @pytest.mark.asyncio
    async def test_creates_hall_successfully(self):
        from src.api.banquet_agent import create_hall, HallCreateReq

        db = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        body = HallCreateReq(
            name="二号厅",
            hall_type="main_hall",
            max_tables=15,
            max_people=150,
            min_spend_yuan=15000.0,
        )
        result = await create_hall(store_id="S001", body=body, db=db, _=_mock_user())

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["name"] == "二号厅"
        assert result["is_active"] is True

    @pytest.mark.asyncio
    async def test_400_for_invalid_hall_type(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import create_hall, HallCreateReq

        db = AsyncMock()
        body = HallCreateReq(
            name="测试厅",
            hall_type="invalid_type",
            max_people=100,
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_hall(store_id="S001", body=body, db=db, _=_mock_user())

        assert exc_info.value.status_code == 400


# ── update_hall ────────────────────────────────────────────────────────────────

class TestUpdateHall:

    @pytest.mark.asyncio
    async def test_updates_hall_name(self):
        from src.api.banquet_agent import update_hall, HallUpdateReq

        hall = _make_hall()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([hall]))
        db.commit = AsyncMock()

        body = HallUpdateReq(name="更新后名称", max_people=250)
        result = await update_hall(
            store_id="S001", hall_id="HALL-001", body=body, db=db, _=_mock_user()
        )

        assert hall.name == "更新后名称"
        assert hall.max_people == 250
        db.commit.assert_awaited_once()
        assert result["updated"] is True

    @pytest.mark.asyncio
    async def test_404_when_hall_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import update_hall, HallUpdateReq

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await update_hall(
                store_id="S001", hall_id="NONEXISTENT",
                body=HallUpdateReq(), db=db, _=_mock_user()
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_partial_update_only_touches_provided_fields(self):
        from src.api.banquet_agent import update_hall, HallUpdateReq

        hall = _make_hall()
        original_max_people = hall.max_people
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([hall]))
        db.commit = AsyncMock()

        # only update min_spend, leave max_people untouched
        body = HallUpdateReq(min_spend_yuan=25000.0)
        await update_hall(
            store_id="S001", hall_id="HALL-001", body=body, db=db, _=_mock_user()
        )

        assert hall.min_spend_fen == 2500000
        assert hall.max_people == original_max_people  # unchanged


# ── deactivate_hall ────────────────────────────────────────────────────────────

class TestDeactivateHall:

    @pytest.mark.asyncio
    async def test_soft_deletes_hall(self):
        from src.api.banquet_agent import deactivate_hall

        hall = _make_hall()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([hall]))
        db.commit = AsyncMock()

        result = await deactivate_hall(
            store_id="S001", hall_id="HALL-001", db=db, _=_mock_user()
        )

        assert hall.is_active is False
        db.commit.assert_awaited_once()
        assert result["is_active"] is False

    @pytest.mark.asyncio
    async def test_404_when_hall_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import deactivate_hall

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await deactivate_hall(
                store_id="S001", hall_id="NONEXISTENT", db=db, _=_mock_user()
            )
        assert exc_info.value.status_code == 404


# ── list_packages ──────────────────────────────────────────────────────────────

class TestListPackages:

    @pytest.mark.asyncio
    async def test_returns_active_packages_with_margin(self):
        from src.api.banquet_agent import list_packages

        pkg = _make_package()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([pkg]))

        result = await list_packages(
            store_id="S001", active_only=True, banquet_type=None,
            db=db, _=_mock_user()
        )

        assert len(result) == 1
        assert result[0]["package_id"] == "PKG-001"
        assert result[0]["suggested_price_yuan"] == 30000.0
        assert result[0]["cost_yuan"] == 12000.0
        assert result[0]["gross_margin_pct"] == 60.0

    @pytest.mark.asyncio
    async def test_empty_when_no_packages(self):
        from src.api.banquet_agent import list_packages

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await list_packages(
            store_id="S001", active_only=True, banquet_type=None,
            db=db, _=_mock_user()
        )
        assert result == []


# ── create_package ─────────────────────────────────────────────────────────────

class TestCreatePackage:

    @pytest.mark.asyncio
    async def test_creates_package_successfully(self):
        from src.api.banquet_agent import create_package, PackageCreateReq

        db = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        body = PackageCreateReq(
            name="豪华婚宴套餐",
            banquet_type="wedding",
            suggested_price_yuan=50000.0,
            cost_yuan=20000.0,
            target_people_min=200,
            target_people_max=500,
        )
        result = await create_package(store_id="S001", body=body, db=db, _=_mock_user())

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["name"] == "豪华婚宴套餐"
        assert result["is_active"] is True

    @pytest.mark.asyncio
    async def test_400_for_invalid_banquet_type(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import create_package, PackageCreateReq

        db = AsyncMock()
        body = PackageCreateReq(
            name="测试套餐",
            banquet_type="invalid_type",
            suggested_price_yuan=10000.0,
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_package(store_id="S001", body=body, db=db, _=_mock_user())
        assert exc_info.value.status_code == 400


# ── update_package ─────────────────────────────────────────────────────────────

class TestUpdatePackage:

    @pytest.mark.asyncio
    async def test_updates_price_and_description(self):
        from src.api.banquet_agent import update_package, PackageUpdateReq

        pkg = _make_package()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([pkg]))
        db.commit = AsyncMock()

        body = PackageUpdateReq(suggested_price_yuan=35000.0, description="新描述")
        result = await update_package(
            store_id="S001", pkg_id="PKG-001", body=body, db=db, _=_mock_user()
        )

        assert pkg.suggested_price_fen == 3500000
        assert pkg.description == "新描述"
        assert result["updated"] is True

    @pytest.mark.asyncio
    async def test_404_when_package_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import update_package, PackageUpdateReq

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await update_package(
                store_id="S001", pkg_id="NONEXISTENT",
                body=PackageUpdateReq(), db=db, _=_mock_user()
            )
        assert exc_info.value.status_code == 404


# ── deactivate_package ─────────────────────────────────────────────────────────

class TestDeactivatePackage:

    @pytest.mark.asyncio
    async def test_deactivates_package(self):
        from src.api.banquet_agent import deactivate_package

        pkg = _make_package()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([pkg]))
        db.commit = AsyncMock()

        result = await deactivate_package(
            store_id="S001", pkg_id="PKG-001", db=db, _=_mock_user()
        )

        assert pkg.is_active is False
        assert result["is_active"] is False

    @pytest.mark.asyncio
    async def test_404_when_package_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import deactivate_package

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await deactivate_package(
                store_id="S001", pkg_id="NONEXISTENT", db=db, _=_mock_user()
            )
        assert exc_info.value.status_code == 404


# ── settle_order ───────────────────────────────────────────────────────────────

class TestSettleOrder:

    @pytest.mark.asyncio
    async def test_settles_completed_order_and_creates_snapshot(self):
        from src.api.banquet_agent import settle_order, SettleOrderReq
        from src.models.banquet import OrderStatusEnum

        order = _make_order(status_value="completed")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),  # order lookup
            _scalars_returning([]),       # no existing snapshot
        ])
        db.commit = AsyncMock()
        db.add = MagicMock()

        body = SettleOrderReq(
            revenue_yuan=50000.0,
            ingredient_cost_yuan=15000.0,
            labor_cost_yuan=5000.0,
        )
        result = await settle_order(
            store_id="S001", order_id="ORD-001", body=body,
            db=db, _=_mock_user(),
        )

        assert order.order_status == OrderStatusEnum.SETTLED
        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["status"] == "settled"
        assert result["gross_profit_yuan"] == 30000.0
        assert result["gross_margin_pct"] == 60.0

    @pytest.mark.asyncio
    async def test_settles_and_updates_existing_snapshot(self):
        from src.api.banquet_agent import settle_order, SettleOrderReq

        order = _make_order(status_value="completed")
        existing_snap = _make_snapshot()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),
            _scalars_returning([existing_snap]),
        ])
        db.commit = AsyncMock()
        db.add = MagicMock()

        body = SettleOrderReq(revenue_yuan=60000.0, ingredient_cost_yuan=20000.0)
        await settle_order(
            store_id="S001", order_id="ORD-001", body=body,
            db=db, _=_mock_user(),
        )

        db.add.assert_not_called()
        assert existing_snap.revenue_fen == 6000000

    @pytest.mark.asyncio
    async def test_400_when_order_not_completed(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import settle_order, SettleOrderReq

        order = _make_order(status_value="confirmed")  # not completed
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        with pytest.raises(HTTPException) as exc_info:
            await settle_order(
                store_id="S001", order_id="ORD-001",
                body=SettleOrderReq(revenue_yuan=50000.0),
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_404_when_order_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import settle_order, SettleOrderReq

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await settle_order(
                store_id="S001", order_id="NONEXISTENT",
                body=SettleOrderReq(revenue_yuan=50000.0),
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404


# ── push_scan ──────────────────────────────────────────────────────────────────

class TestPushScan:

    @pytest.mark.asyncio
    async def test_returns_sent_count_for_upcoming_orders(self):
        from src.api.banquet_agent import push_scan
        from src.models.banquet import OrderStatusEnum

        # One D-1 order, no overdue tasks, no stale leads
        order = _make_order(status_value="confirmed")
        order.banquet_type.value = "wedding"

        mock_upcoming = _scalars_returning([order])
        mock_empty    = _scalars_returning([])

        db = AsyncMock()
        # push_scan issues multiple queries: d1, d7, overdue tasks, stale leads
        db.execute = AsyncMock(side_effect=[
            mock_upcoming,   # D-1 orders
            mock_empty,      # D-7 orders
            mock_empty,      # overdue tasks
            mock_empty,      # stale leads
        ])

        # Redis is imported lazily inside push_scan; missing redis is silently swallowed
        result = await push_scan(store_id="S001", db=db, _=_mock_user())

        assert result["sent"] >= 1
        assert "details" in result
        assert any(d["type"] == "banquet_reminder" for d in result["details"])

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_to_push(self):
        from src.api.banquet_agent import push_scan

        mock_empty = _scalars_returning([])
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            mock_empty,  # D-1
            mock_empty,  # D-7
            mock_empty,  # overdue tasks
            mock_empty,  # stale leads
        ])

        # Redis is imported lazily inside push_scan; missing redis is silently swallowed
        result = await push_scan(store_id="S001", db=db, _=_mock_user())

        assert result["sent"] == 0
        assert result["details"] == []
