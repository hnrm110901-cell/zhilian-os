"""
Banquet Agent Phase 12 — 单元测试

覆盖端点：
  - create_or_refresh_review / get_review / patch_review_rating
  - list_at_risk_orders
  - get_review_summary
  - multi_store_banquet_summary
  - get_exception_stats
"""

import pytest
from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ─────────────────────────────────────────────────────────────────

def _mock_user(uid="user-001", brand_id="BRAND-001"):
    u = MagicMock()
    u.id = uid
    u.brand_id = brand_id
    return u


def _scalars_returning(items):
    r = MagicMock()
    r.scalars.return_value.first.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value = items
    return r


def _scalar_returning(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _make_order(oid="ORD-001", status="completed", banquet_date=None):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id = oid
    o.store_id = "S001"
    o.banquet_type = BanquetTypeEnum.WEDDING
    o.order_status = OrderStatusEnum.COMPLETED if status == "completed" else OrderStatusEnum.CONFIRMED
    o.banquet_date = banquet_date or date.today()
    o.total_amount_fen = 5000000  # 50000 yuan in fen
    return o


def _make_review(rid="REV-001", order_id="ORD-001"):
    r = MagicMock()
    r.id = rid
    r.banquet_order_id = order_id
    r.ai_score = 82.5
    r.ai_summary = "宴会整体顺利"
    r.improvement_tags = ["菜量偏少", "上菜慢"]
    r.customer_rating = None
    r.revenue_yuan = 48000.0
    r.gross_profit_yuan = 14400.0
    r.gross_margin_pct = 30.0
    r.overdue_task_count = 1
    r.exception_count = 0
    r.created_at = datetime.utcnow()
    return r


def _make_exception(eid="EXC-1", etype="late", severity="medium",
                    order_id="ORD-001", status="open",
                    created_at=None, resolved_at=None):
    e = MagicMock()
    e.id = eid
    e.banquet_order_id = order_id
    e.exception_type = etype
    e.severity = severity
    e.status = status
    e.created_at = created_at or datetime.utcnow()
    e.resolved_at = resolved_at
    return e


def _make_kpi_row(store_id="S001", revenue_fen=5000000,
                  profit_fen=1500000, order_count=10, lead_count=20, utilization=75.0):
    r = MagicMock()
    r.store_id = store_id
    r.revenue_fen = revenue_fen
    r.profit_fen = profit_fen
    r.order_count = order_count
    r.lead_count = lead_count
    r.avg_utilization = utilization
    return r


# ── TestReviewPersistence ────────────────────────────────────────────────────

class TestReviewPersistence:

    @pytest.mark.asyncio
    async def test_create_review_for_completed_order(self):
        from src.api.banquet_agent import create_or_refresh_review

        order = _make_order(status="completed")

        db = AsyncMock()
        # 1st call: order lookup, 2nd: overdue tasks, 3rd: exceptions, 4th: profit snapshot, 5th: existing review
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),   # order lookup
            _scalar_returning(1),          # overdue task count
            _scalar_returning(0),          # exception count
            _scalars_returning([]),        # profit snapshot (none)
            _scalars_returning([]),        # existing review (none)
        ])
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda r: None)

        ai_result = {"ai_score": 85.0, "summary": "整体不错", "improvement_tags": ["上菜慢"]}

        mock_agent_instance = MagicMock()
        mock_agent_instance.generate_review = AsyncMock(return_value=ai_result)
        mock_agent_cls = MagicMock(return_value=mock_agent_instance)

        import src.api.banquet_agent as _mod
        original = _mod._ReviewAgent
        _mod._ReviewAgent = mock_agent_cls
        try:
            result = await create_or_refresh_review(
                store_id="S001", order_id="ORD-001",
                db=db, current_user=_mock_user(),
            )
        finally:
            _mod._ReviewAgent = original

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result["ai_score"] == 85.0
        assert result["overdue_task_count"] == 1

    @pytest.mark.asyncio
    async def test_create_review_400_on_non_completed_order(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import create_or_refresh_review

        order = _make_order(status="confirmed")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        with pytest.raises(HTTPException) as exc:
            await create_or_refresh_review(
                store_id="S001", order_id="ORD-001",
                db=db, current_user=_mock_user(),
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_review_returns_data(self):
        from src.api.banquet_agent import get_review

        review = _make_review()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([review]))

        result = await get_review(store_id="S001", order_id="ORD-001",
                                  db=db, _=_mock_user())

        assert result["ai_score"] == 82.5
        assert result["improvement_tags"] == ["菜量偏少", "上菜慢"]

    @pytest.mark.asyncio
    async def test_patch_review_rating_stores_value(self):
        from src.api.banquet_agent import patch_review_rating

        review = _make_review()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([review]))
        db.commit = AsyncMock()

        class _Body:
            rating = 4

        result = await patch_review_rating(
            store_id="S001", order_id="ORD-001",
            body=_Body(), db=db, _=_mock_user(),
        )

        assert result["customer_rating"] == 4
        assert review.customer_rating == 4


# ── TestAtRisk ───────────────────────────────────────────────────────────────

class TestAtRisk:

    @pytest.mark.asyncio
    async def test_at_risk_unpaid_balance(self):
        from src.api.banquet_agent import list_at_risk_orders
        from src.models.banquet import OrderStatusEnum

        order = _make_order(status="confirmed")
        order.order_status = OrderStatusEnum.CONFIRMED
        order.banquet_date = date.today() + timedelta(days=5)
        order.total_amount_fen = 5000000   # 50000 yuan

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),   # orders query
            _scalar_returning(0),          # overdue tasks
            _scalar_returning(1000000),    # paid_fen (10000 yuan, 40000 unpaid)
            _scalar_returning(0),          # open exceptions
        ])

        result = await list_at_risk_orders(store_id="S001", days=14,
                                           db=db, _=_mock_user())

        assert len(result) == 1
        assert result[0]["risk_score"] >= 1
        assert any("余款" in r for r in result[0]["risk_reasons"])

    @pytest.mark.asyncio
    async def test_at_risk_overdue_tasks(self):
        from src.api.banquet_agent import list_at_risk_orders
        from src.models.banquet import OrderStatusEnum

        order = _make_order(status="confirmed")
        order.order_status = OrderStatusEnum.PREPARING
        order.banquet_date = date.today() + timedelta(days=3)
        order.total_amount_fen = 0  # no balance risk

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),
            _scalar_returning(3),   # 3 overdue tasks
            _scalar_returning(0),   # paid_fen
            _scalar_returning(0),   # open exceptions
        ])

        result = await list_at_risk_orders(store_id="S001", days=14,
                                           db=db, _=_mock_user())

        assert len(result) == 1
        assert any("待执行" in r for r in result[0]["risk_reasons"])

    @pytest.mark.asyncio
    async def test_at_risk_no_risk_returns_empty(self):
        from src.api.banquet_agent import list_at_risk_orders
        from src.models.banquet import OrderStatusEnum

        order = _make_order(status="confirmed")
        order.order_status = OrderStatusEnum.CONFIRMED
        order.banquet_date = date.today() + timedelta(days=7)
        order.total_amount_fen = 0

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),
            _scalar_returning(0),   # no overdue tasks
            _scalar_returning(0),   # paid_fen
            _scalar_returning(0),   # no open exceptions
        ])

        result = await list_at_risk_orders(store_id="S001", days=14,
                                           db=db, _=_mock_user())

        # risk_score == 0 → excluded
        assert result == []


# ── TestMultiStoreSummary ────────────────────────────────────────────────────

class TestMultiStoreSummary:

    @pytest.mark.asyncio
    async def test_multi_store_aggregates_kpis(self):
        from src.api.banquet_agent import multi_store_banquet_summary

        kpi1 = _make_kpi_row("S001", 5000000, 1500000, 10, 20, 75.0)
        kpi2 = _make_kpi_row("S002", 3000000,  900000,  6, 15, 60.0)

        stores_result = MagicMock()
        stores_result.all.return_value = [("S001",), ("S002",)]
        kpi_result = MagicMock()
        kpi_result.all.return_value = [kpi1, kpi2]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[stores_result, kpi_result])

        result = await multi_store_banquet_summary(
            year=2026, month=3,
            db=db, current_user=_mock_user(),
        )

        assert len(result) == 2
        # sorted by revenue desc
        assert result[0]["store_id"] == "S001"
        assert result[0]["revenue_yuan"] == 50000.0
        assert result[1]["revenue_yuan"] == 30000.0

    @pytest.mark.asyncio
    async def test_multi_store_403_without_brand(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import multi_store_banquet_summary

        user_no_brand = _mock_user()
        user_no_brand.brand_id = None

        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await multi_store_banquet_summary(
                year=2026, month=3,
                db=db, current_user=user_no_brand,
            )
        assert exc.value.status_code == 403


# ── TestExceptionStats ───────────────────────────────────────────────────────

class TestExceptionStats:

    @pytest.mark.asyncio
    async def test_exception_stats_groups_by_type(self):
        from src.api.banquet_agent import get_exception_stats

        now = datetime.utcnow()
        exc1 = _make_exception("E1", "late",    "medium", status="open")
        exc2 = _make_exception("E2", "late",    "high",   status="resolved",
                                created_at=now - timedelta(hours=4),
                                resolved_at=now)
        exc3 = _make_exception("E3", "missing", "low",    status="open")

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([exc1, exc2, exc3]))

        result = await get_exception_stats(store_id="S001", year=2026, month=3,
                                           db=db, _=_mock_user())

        assert result["total"] == 3
        type_map = {item["type"]: item for item in result["by_type"]}
        assert type_map["late"]["count"] == 2
        assert type_map["late"]["resolved"] == 1
        assert type_map["missing"]["count"] == 1
        assert result["avg_resolution_hours"] == 4.0

    @pytest.mark.asyncio
    async def test_exception_stats_empty_returns_zero(self):
        from src.api.banquet_agent import get_exception_stats

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_exception_stats(store_id="S001", year=2026, month=3,
                                           db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["by_type"] == []
        assert result["avg_resolution_hours"] is None
