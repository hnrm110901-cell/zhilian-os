"""
Banquet Agent Phase 14 — 单元测试

覆盖端点：
  - get_receivables_aging
  - list_overdue_receivables
  - generate_followup_message / list_followup_messages
  - get_halls_monthly_schedule / get_hall_utilization
  - get_quote_stats
  - list_pending_sign_contracts
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock


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


def _rows_returning(rows):
    """Mock for execute().all() — used for join queries."""
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_order(oid="O-001", store_id="S001", total_fen=500000, paid_fen=0,
                status="confirmed", days_ago=10, banquet_type="wedding"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id = oid
    o.store_id = store_id
    o.total_amount_fen = total_fen
    o.paid_fen = paid_fen
    o.order_status = OrderStatusEnum.CONFIRMED if status == "confirmed" else OrderStatusEnum.COMPLETED
    o.banquet_date = date.today() - timedelta(days=days_ago)
    o.banquet_type = BanquetTypeEnum.WEDDING if banquet_type == "wedding" else BanquetTypeEnum.BIRTHDAY
    o.contact_name = "张三"
    o.contact_phone = "13800138000"
    return o


def _make_hall(hid="HALL-001", store_id="S001", name="大宴会厅", max_tables=30):
    from src.models.banquet import BanquetHallType
    h = MagicMock()
    h.id = hid
    h.store_id = store_id
    h.name = name
    h.hall_type = BanquetHallType.MAIN_HALL
    h.max_tables = max_tables
    h.is_active = True
    return h


def _make_booking(bid="BK-001", hall_id="HALL-001", order_id="O-001",
                  slot_date=None, slot_name="dinner"):
    b = MagicMock()
    b.id = bid
    b.hall_id = hall_id
    b.banquet_order_id = order_id
    b.slot_date = slot_date or date.today().replace(day=15)
    b.slot_name = slot_name
    b.is_locked = True
    return b


def _make_lead(lid="LEAD-001", store_id="S001", stage="quoted",
               customer_id="CUST-001", budget_fen=6000000, banquet_type="wedding"):
    from src.models.banquet import LeadStageEnum, BanquetTypeEnum
    l = MagicMock()
    l.id = lid
    l.store_id = store_id
    l.customer_id = customer_id
    l.current_stage = LeadStageEnum.QUOTED if stage == "quoted" else LeadStageEnum.NEW
    l.expected_budget_fen = budget_fen
    l.expected_date = date.today() + timedelta(days=60)
    l.expected_people_count = 80
    l.banquet_type = BanquetTypeEnum.WEDDING
    return l


def _make_customer(cid="CUST-001", name="王大华"):
    c = MagicMock()
    c.id = cid
    c.customer_name = name
    return c


def _make_quote(qid="Q-001", lead_id="LEAD-001", store_id="S001",
                amount_fen=500000, accepted=False):
    q = MagicMock()
    q.id = qid
    q.lead_id = lead_id
    q.store_id = store_id
    q.quoted_amount_fen = amount_fen
    q.is_accepted = accepted
    q.created_at = datetime.utcnow()
    return q


def _make_contract(cid="CTR-001", order_id="O-001", status="draft"):
    c = MagicMock()
    c.id = cid
    c.banquet_order_id = order_id
    c.contract_no = f"CTR-2026-{cid[-3:]}"
    c.contract_status = status
    c.file_url = None
    return c


# ── TestReceivablesAging ─────────────────────────────────────────────────────

class TestReceivablesAging:

    @pytest.mark.asyncio
    async def test_aging_buckets_classify_correctly(self):
        from src.api.banquet_agent import get_receivables_aging

        o_new  = _make_order("O-001", days_ago=15,  total_fen=200000, paid_fen=0)
        o_mid  = _make_order("O-002", days_ago=45,  total_fen=300000, paid_fen=100000)
        o_late = _make_order("O-003", days_ago=100, total_fen=500000, paid_fen=0)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o_new, o_mid, o_late]))

        result = await get_receivables_aging(store_id="S001", db=db, _=_mock_user())

        assert result["buckets"]["0_30"]["count"] == 1
        assert result["buckets"]["31_60"]["count"] == 1
        assert result["buckets"]["over_90"]["count"] == 1
        assert result["total_balance_yuan"] == pytest.approx(
            (200000 + 200000 + 500000) / 100, rel=1e-3
        )

    @pytest.mark.asyncio
    async def test_aging_empty_returns_zero_totals(self):
        from src.api.banquet_agent import get_receivables_aging

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await get_receivables_aging(store_id="S001", db=db, _=_mock_user())

        assert result["total_balance_yuan"] == 0.0
        for bucket in result["buckets"].values():
            assert bucket["count"] == 0

    @pytest.mark.asyncio
    async def test_overdue_list_filters_by_min_days(self):
        from src.api.banquet_agent import list_overdue_receivables

        o = _make_order("O-001", days_ago=40, total_fen=400000, paid_fen=50000)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([o]))

        result = await list_overdue_receivables(
            store_id="S001", min_days=30, db=db, _=_mock_user()
        )

        assert result["total"] == 1
        assert result["items"][0]["days_overdue"] == 40
        assert result["items"][0]["balance_yuan"] == pytest.approx(3500.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_overdue_list_empty(self):
        from src.api.banquet_agent import list_overdue_receivables

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await list_overdue_receivables(
            store_id="S001", min_days=1, db=db, _=_mock_user()
        )

        assert result["total"] == 0
        assert result["items"] == []


# ── TestFollowupMessage ──────────────────────────────────────────────────────

class TestFollowupMessage:

    @pytest.mark.asyncio
    async def test_generate_message_uses_stage_template(self):
        from src.api.banquet_agent import generate_followup_message, _FollowupMsgBody

        lead     = _make_lead(stage="quoted")
        customer = _make_customer()

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([lead]),     # lead lookup
            _scalars_returning([customer]), # customer lookup
        ])
        db.add    = MagicMock()
        db.commit = AsyncMock()

        result = await generate_followup_message(
            store_id="S001", lead_id="LEAD-001",
            body=_FollowupMsgBody(),
            db=db, current_user=_mock_user(),
        )

        assert result["lead_id"] == "LEAD-001"
        assert result["stage"] == "quoted"
        assert "王大华" in result["message"]
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_message_404_on_missing_lead(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import generate_followup_message, _FollowupMsgBody

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await generate_followup_message(
                store_id="S001", lead_id="X",
                body=_FollowupMsgBody(),
                db=db, current_user=_mock_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_followup_messages_reads_logs(self):
        from src.api.banquet_agent import list_followup_messages

        log = MagicMock()
        log.id = "LOG-001"
        log.action_result = {"stage": "quoted", "message": "Hello 客户"}
        log.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([log]))

        result = await list_followup_messages(
            store_id="S001", lead_id="LEAD-001", limit=10,
            db=db, _=_mock_user(),
        )

        assert result["total"] == 1
        assert result["items"][0]["message"] == "Hello 客户"


# ── TestHallSchedule ─────────────────────────────────────────────────────────

class TestHallSchedule:

    @pytest.mark.asyncio
    async def test_monthly_schedule_returns_matrix(self):
        from src.api.banquet_agent import get_halls_monthly_schedule

        hall    = _make_hall()
        booking = _make_booking(slot_date=date(2026, 3, 15))
        order   = _make_order(days_ago=-6)   # future order

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([hall]),       # halls query
            _rows_returning([(booking, order)]),  # bookings join query
        ])

        result = await get_halls_monthly_schedule(
            store_id="S001", year=2026, month=3,
            db=db, _=_mock_user(),
        )

        assert result["year"] == 2026
        assert result["month"] == 3
        assert len(result["halls"]) == 1
        assert len(result["dates"]) == 31   # March has 31 days

        hall_data = result["halls"][0]
        assert hall_data["hall_name"] == "大宴会厅"
        # Find day 15
        day15 = next(d for d in hall_data["days"] if d["date"] == "2026-03-15")
        assert day15["booked"] is True

    @pytest.mark.asyncio
    async def test_hall_utilization_computes_pct(self):
        from src.api.banquet_agent import get_hall_utilization

        hall = _make_hall()
        # 5 bookings in a 31-day month → 5 / (31*2) slots
        bookings = [
            _make_booking(f"BK-{i}", slot_date=date(2026, 3, i + 1))
            for i in range(5)
        ]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([hall]),
            _scalars_returning(bookings),
        ])

        result = await get_hall_utilization(
            store_id="S001", hall_id="HALL-001",
            year=2026, month=3, db=db, _=_mock_user(),
        )

        assert result["booked_slots"] == 5
        assert result["total_slots"] == 62   # 31 * 2
        assert result["utilization_pct"] == pytest.approx(5 / 62 * 100, rel=1e-2)

    @pytest.mark.asyncio
    async def test_hall_utilization_404_on_missing_hall(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import get_hall_utilization

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await get_hall_utilization(
                store_id="S001", hall_id="NO-HALL",
                year=2026, month=3, db=db, _=_mock_user(),
            )
        assert exc.value.status_code == 404


# ── TestAnalytics ─────────────────────────────────────────────────────────────

class TestAnalytics:

    @pytest.mark.asyncio
    async def test_quote_stats_acceptance_rate(self):
        from src.models.banquet import BanquetTypeEnum
        from src.api.banquet_agent import get_quote_stats

        q1 = _make_quote("Q-001", accepted=True,  amount_fen=500000)
        q2 = _make_quote("Q-002", accepted=False, amount_fen=300000)
        lead = _make_lead()

        # Build (quote, lead) tuples
        rows = [(q1, lead), (q2, lead)]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning(rows))

        result = await get_quote_stats(
            store_id="S001", year=2026, month=3,
            db=db, _=_mock_user(),
        )

        assert result["total_quotes"] == 2
        assert result["accepted_quotes"] == 1
        assert result["acceptance_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_pending_sign_contracts_sorted_by_date(self):
        from src.api.banquet_agent import list_pending_sign_contracts

        o1 = _make_order("O-001", days_ago=-10)   # banquet 10 days from now
        o2 = _make_order("O-002", days_ago=-30)   # banquet 30 days from now
        c1 = _make_contract("CTR-001", "O-001", "draft")
        c2 = _make_contract("CTR-002", "O-002", "draft")

        # rows sorted by banquet_date asc — nearer date first
        rows = [(c1, o1), (c2, o2)]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_returning(rows))

        result = await list_pending_sign_contracts(
            store_id="S001", db=db, _=_mock_user(),
        )

        assert result["total"] == 2
        # First item should be the one with nearer banquet_date
        assert result["items"][0]["contract_id"] == "CTR-001"
        assert result["items"][0]["days_until"] > 0
