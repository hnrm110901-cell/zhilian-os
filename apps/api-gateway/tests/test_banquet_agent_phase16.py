"""
Banquet Agent Phase 16 — 单元测试

覆盖端点：
  - get_brand_comparison / get_benchmark
  - get_upcoming_anniversaries
  - get_win_back_candidates
  - generate_anniversary_message / generate_win_back_message
  - get_outreach_history
  - get_executive_summary
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock
from collections import defaultdict


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


def _rows_returning(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_order(oid="O-001", store_id="S001", cid="CUST-001",
                status="confirmed", days_ago=30, total_fen=500000,
                btype="wedding"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id = oid
    o.store_id = store_id
    o.customer_id = cid
    o.order_status = (
        OrderStatusEnum.CONFIRMED  if status == "confirmed"  else
        OrderStatusEnum.COMPLETED  if status == "completed"  else
        OrderStatusEnum.CANCELLED
    )
    o.banquet_date = date.today() - timedelta(days=days_ago)
    o.banquet_type = BanquetTypeEnum.WEDDING if btype == "wedding" else BanquetTypeEnum.BIRTHDAY
    o.total_amount_fen = total_fen
    o.contact_name = "张三"
    o.contact_phone = "138"
    o.created_at = datetime.utcnow() - timedelta(days=days_ago + 5)
    return o


def _make_customer(cid="CUST-001", name="王大华", phone="138"):
    c = MagicMock()
    c.id = cid
    c.customer_name = name
    c.phone = phone
    return c


def _make_task(tid="T-001", oid="O-001", status="done"):
    from src.models.banquet import TaskStatusEnum
    t = MagicMock()
    t.id = tid
    t.banquet_order_id = oid
    t.task_status = TaskStatusEnum.DONE if status == "done" else TaskStatusEnum.PENDING
    return t


def _make_exception(eid="E-001", oid="O-001"):
    e = MagicMock()
    e.id = eid
    e.banquet_order_id = oid
    return e


def _make_store(sid="S001", name="一号店", brand_id="BRAND-001"):
    s = MagicMock()
    s.id   = sid
    s.name = name
    s.brand_id = brand_id
    return s


# ── TestBrandComparison ───────────────────────────────────────────────────────

class TestBrandComparison:

    @pytest.mark.asyncio
    async def test_comparison_returns_self_rank(self):
        from src.api.banquet_agent import get_brand_comparison

        store = _make_store("S001")
        order = _make_order(store_id="S001", status="confirmed", total_fen=600000)

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            n = call_count[0]
            # Call sequence:
            # 1: stores query → returns [(S001, "一号店")]
            # 2: BanquetOrder for S001 → returns [order]
            # 3: lead count → 0
            # 4: hist orders (repeat rate) → []
            if n == 1:
                r = MagicMock()
                r.all.return_value = [("S001", "一号店")]
                return r
            elif n == 2:
                return _scalars_returning([order])
            elif n == 3:
                return _scalar_returning(2)   # 2 leads
            elif n == 4:
                return _rows_returning([("CUST-001", 1)])
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_brand_comparison(
            store_id="S001", year=2026, month=3, db=db, _=_mock_user()
        )

        assert result["total_stores"] == 1
        assert result["self_rank"] == 1
        assert len(result["stores"]) == 1
        assert result["stores"][0]["is_self"] is True
        assert result["stores"][0]["revenue_yuan"] == pytest.approx(6000.0)

    @pytest.mark.asyncio
    async def test_benchmark_returns_deltas(self):
        from src.api.banquet_agent import get_benchmark

        # Mock get_brand_comparison to return controlled data
        from unittest.mock import patch, AsyncMock as AM

        mock_comp = {
            "year": 2026, "month": 3,
            "total_stores": 2,
            "self_rank": 1,
            "stores": [
                {"store_id": "S001", "store_name": "一号店",
                 "revenue_yuan": 8000.0, "order_count": 4,
                 "conversion_rate_pct": 50.0, "repeat_rate_pct": 30.0,
                 "is_self": True, "rank": 1},
                {"store_id": "S002", "store_name": "二号店",
                 "revenue_yuan": 4000.0, "order_count": 2,
                 "conversion_rate_pct": 25.0, "repeat_rate_pct": 10.0,
                 "is_self": False, "rank": 2},
            ],
            "brand_avg": {
                "store_id": "brand_avg", "store_name": "品牌均值",
                "revenue_yuan": 6000.0, "order_count": 3,
                "conversion_rate_pct": 37.5, "repeat_rate_pct": 20.0,
                "is_self": False, "rank": None,
            },
        }

        with patch("src.api.banquet_agent.get_brand_comparison", new=AM(return_value=mock_comp)):
            db = AsyncMock()
            result = await get_benchmark(
                store_id="S001", year=2026, month=3, db=db, _=_mock_user()
            )

        assert result["self_rank"] == 1
        assert result["total_stores"] == 2
        rev_metric = next(m for m in result["metrics"] if m["metric"] == "revenue_yuan")
        # Store 8000 vs avg 6000 → delta = +33.3%
        assert rev_metric["delta_pct"] > 0
        assert rev_metric["status"] == "above"


# ── TestAnniversaryAlerts ─────────────────────────────────────────────────────

class TestAnniversaryAlerts:

    @pytest.mark.asyncio
    async def test_anniversary_within_days_returned(self):
        from src.api.banquet_agent import get_upcoming_anniversaries

        today = date.today()
        # Order from last year, same month+day as 5 days from now
        anniversary_day = today + timedelta(days=5)
        order = _make_order(status="completed", cid="CUST-001")
        order.banquet_date = date(today.year - 1, anniversary_day.month, anniversary_day.day)
        cust  = _make_customer()

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([order])
            return _scalars_returning([cust])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_upcoming_anniversaries(
            store_id="S001", days=30, db=db, _=_mock_user()
        )

        assert result["total"] == 1
        assert result["items"][0]["days_until"] == 5
        assert result["items"][0]["customer_id"] == "CUST-001"

    @pytest.mark.asyncio
    async def test_anniversary_outside_window_not_returned(self):
        from src.api.banquet_agent import get_upcoming_anniversaries

        today = date.today()
        # Order from last year, anniversary 60 days from now (outside 30-day window)
        anniversary_day = today + timedelta(days=60)
        try:
            bd = date(today.year - 1, anniversary_day.month, anniversary_day.day)
        except ValueError:
            return  # Skip if date invalid

        order = _make_order(status="completed")
        order.banquet_date = bd

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_upcoming_anniversaries(
            store_id="S001", days=30, db=db, _=_mock_user()
        )

        assert result["total"] == 0


# ── TestWinBackCandidates ─────────────────────────────────────────────────────

class TestWinBackCandidates:

    @pytest.mark.asyncio
    async def test_churned_customer_returned(self):
        from src.api.banquet_agent import get_win_back_candidates

        # Order 400 days ago → exceeds 12 months (360 days)
        order = _make_order(status="completed", days_ago=400, total_fen=300000)
        cust  = _make_customer()

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _scalars_returning([order])
            return _scalars_returning([cust])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_win_back_candidates(
            store_id="S001", months=12, db=db, _=_mock_user()
        )

        assert result["total"] == 1
        assert result["items"][0]["days_since"] >= 360
        assert result["items"][0]["total_yuan"] == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_recent_customer_not_returned(self):
        from src.api.banquet_agent import get_win_back_candidates

        # Order only 30 days ago → not churned
        order = _make_order(status="completed", days_ago=30)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        result = await get_win_back_candidates(
            store_id="S001", months=12, db=db, _=_mock_user()
        )

        assert result["total"] == 0


# ── TestOutreachMessages ──────────────────────────────────────────────────────

class TestOutreachMessages:

    @pytest.mark.asyncio
    async def test_anniversary_message_contains_customer_name(self):
        from src.api.banquet_agent import generate_anniversary_message, _OutreachBody

        cust  = _make_customer(name="李梅梅")
        order = _make_order(status="completed")

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([cust]),
            _scalars_returning([order]),
        ])
        db.add    = MagicMock()
        db.commit = AsyncMock()

        result = await generate_anniversary_message(
            store_id="S001", customer_id="CUST-001",
            body=_OutreachBody(),
            db=db, current_user=_mock_user(),
        )

        assert "李梅梅" in result["message"]
        assert result["outreach_type"] == "anniversary"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_win_back_message_contains_customer_name(self):
        from src.api.banquet_agent import generate_win_back_message, _OutreachBody

        cust  = _make_customer(name="赵大鹏")
        order = _make_order(status="completed", days_ago=400)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([cust]),
            _scalars_returning([order]),
        ])
        db.add    = MagicMock()
        db.commit = AsyncMock()

        result = await generate_win_back_message(
            store_id="S001", customer_id="CUST-001",
            body=_OutreachBody(),
            db=db, current_user=_mock_user(),
        )

        assert "赵大鹏" in result["message"]
        assert result["outreach_type"] == "win_back"
        assert result["days_since"] >= 360

    @pytest.mark.asyncio
    async def test_anniversary_message_404_on_missing_customer(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import generate_anniversary_message, _OutreachBody

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await generate_anniversary_message(
                store_id="S001", customer_id="NO-CUST",
                body=_OutreachBody(),
                db=db, current_user=_mock_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_outreach_history_reads_action_logs(self):
        from src.api.banquet_agent import get_outreach_history

        log = MagicMock()
        log.id = "LOG-001"
        log.action_type = "anniversary_message"
        log.action_result = {
            "outreach_type": "anniversary",
            "channel": "wechat",
            "message": "尊敬的王大华，周年快乐",
        }
        log.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([log]))

        result = await get_outreach_history(
            store_id="S001", customer_id="CUST-001",
            limit=10,
            db=db, _=_mock_user()
        )

        assert result["total"] == 1
        assert result["items"][0]["outreach_type"] == "anniversary"
        assert "周年快乐" in result["items"][0]["message"]


# ── TestExecutiveSummary ──────────────────────────────────────────────────────

class TestExecutiveSummary:

    @pytest.mark.asyncio
    async def test_summary_contains_all_10_metrics(self):
        from src.api.banquet_agent import get_executive_summary

        order = _make_order(status="confirmed", total_fen=500000)
        task  = _make_task(status="done")
        exc   = _make_exception()

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1:   return _scalars_returning([order])       # orders
            elif n == 2: return _scalar_returning(2)              # lead count
            elif n == 3: return _scalars_returning([task])        # tasks
            elif n == 4: return _scalars_returning([exc])         # exceptions
            elif n == 5: return _rows_returning([("C001", 2)])    # hist (repeat)
            elif n == 6: return _scalars_returning([])            # revenue target
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_executive_summary(
            store_id="S001", year=2026, month=3, db=db, _=_mock_user()
        )

        assert result["year"]  == 2026
        assert result["month"] == 3
        m = result["metrics"]
        assert "revenue_yuan"          in m
        assert "order_count"           in m
        assert "avg_order_yuan"        in m
        assert "conversion_rate_pct"   in m
        assert "task_completion_pct"   in m
        assert "exception_rate_pct"    in m
        assert "repeat_rate_pct"       in m
        assert "cancellation_rate_pct" in m
        assert "revenue_lost_yuan"     in m
        assert "target_achievement_pct" in m
        assert isinstance(result["highlights"], list)
        assert isinstance(result["risks"], list)

    @pytest.mark.asyncio
    async def test_summary_empty_store_returns_zeros(self):
        from src.api.banquet_agent import get_executive_summary

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 2:
                return _scalar_returning(0)      # lead count — uses .scalar()
            elif n == 5:
                return _rows_returning([])       # hist repeat — uses .all()
            return _scalars_returning([])        # all other calls use .scalars()

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_executive_summary(
            store_id="S001", year=2026, month=3, db=db, _=_mock_user()
        )

        assert result["metrics"]["revenue_yuan"]    == 0.0
        assert result["metrics"]["order_count"]     == 0
        assert result["metrics"]["cancellation_rate_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_summary_high_cancel_rate_generates_risk(self):
        from src.api.banquet_agent import get_executive_summary

        confirmed = _make_order("O-001", status="confirmed", total_fen=500000)
        cancelled = [
            _make_order(f"O-{i}", status="cancelled", total_fen=200000)
            for i in range(2, 6)
        ]
        all_orders = [confirmed] + cancelled  # 1 confirmed, 4 cancelled → 80% cancel rate

        call_n = [0]
        def side_effect(*a, **kw):
            call_n[0] += 1
            n = call_n[0]
            if n == 1: return _scalars_returning(all_orders)
            elif n == 2: return _scalar_returning(5)
            elif n == 3: return _scalars_returning([])   # tasks
            elif n == 4: return _scalars_returning([])   # exc
            elif n == 5: return _rows_returning([])      # hist
            elif n == 6: return _scalars_returning([])   # target
            return _scalars_returning([])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effect)

        result = await get_executive_summary(
            store_id="S001", year=2026, month=3, db=db, _=_mock_user()
        )

        assert result["metrics"]["cancellation_rate_pct"] > 15
        assert any("取消率" in r for r in result["risks"])
