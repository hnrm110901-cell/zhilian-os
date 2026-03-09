"""
Banquet Agent Phase 13 — 单元测试

覆盖端点：
  - list_store_quotes / get_single_quote / patch_quote / delete_quote
  - get_target_progress (on_track / behind / no_target_404)
  - get_target_trend (N months / missing months)
  - score_leads / get_lead_score
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


def _scalar_returning(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _make_quote(qid="Q-001", lead_id="LEAD-001", store_id="S001",
                amount_fen=500000, accepted=False,
                valid_until=None):
    q = MagicMock()
    q.id = qid
    q.lead_id = lead_id
    q.store_id = store_id
    q.people_count = 100
    q.table_count = 10
    q.quoted_amount_fen = amount_fen
    q.is_accepted = accepted
    q.valid_until = valid_until or (date.today() + timedelta(days=7))
    q.created_at = datetime.utcnow()
    q.menu_snapshot = None
    return q


def _make_target(store_id="S001", year=2026, month=3, target_fen=10000000):
    t = MagicMock()
    t.store_id = store_id
    t.year = year
    t.month = month
    t.target_fen = target_fen   # 100000 yuan
    return t


def _make_lead(lid="LEAD-001", stage="quoted", budget_fen=6000000,
               last_followup_days=3, has_date=True, has_tables=True):
    from src.models.banquet import LeadStageEnum
    l = MagicMock()
    l.id = lid
    l.store_id = "S001"
    l.current_stage = LeadStageEnum.QUOTED if stage == "quoted" else LeadStageEnum.NEW
    l.expected_budget_fen = budget_fen
    l.last_followup_at = datetime.utcnow() - timedelta(days=last_followup_days)
    l.expected_date = date.today() + timedelta(days=60) if has_date else None
    l.expected_people_count = 80 if has_tables else None
    return l


# ── TestQuoteManagement ──────────────────────────────────────────────────────

class TestQuoteManagement:

    @pytest.mark.asyncio
    async def test_list_store_quotes_returns_items(self):
        from src.api.banquet_agent import list_store_quotes

        q1 = _make_quote("Q-001")
        q2 = _make_quote("Q-002", amount_fen=800000)

        count_result = _scalar_returning(2)
        items_result = _scalars_returning([q1, q2])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await list_store_quotes(store_id="S001", status="all",
                                         page=1, page_size=20,
                                         db=db, _=_mock_user())

        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["items"][0]["quoted_amount_yuan"] == 5000.0

    @pytest.mark.asyncio
    async def test_get_single_quote_found(self):
        from src.api.banquet_agent import get_single_quote

        q = _make_quote()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([q]))

        result = await get_single_quote(store_id="S001", lead_id="LEAD-001",
                                         quote_id="Q-001", db=db, _=_mock_user())

        assert result["quote_id"] == "Q-001"
        assert result["quoted_amount_yuan"] == 5000.0
        assert result["is_accepted"] is False

    @pytest.mark.asyncio
    async def test_patch_quote_updates_amount(self):
        from src.api.banquet_agent import patch_quote

        q = _make_quote(amount_fen=500000, accepted=False)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([q]))
        db.commit = AsyncMock()

        class _Body:
            quoted_amount_yuan = 6000.0
            valid_until = None
            remark = None

        result = await patch_quote(store_id="S001", lead_id="LEAD-001",
                                    quote_id="Q-001", body=_Body(),
                                    db=db, _=_mock_user())

        assert q.quoted_amount_fen == 600000
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_quote_soft_revokes(self):
        from src.api.banquet_agent import delete_quote

        q = _make_quote(accepted=False)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([q]))
        db.commit = AsyncMock()

        result = await delete_quote(store_id="S001", lead_id="LEAD-001",
                                     quote_id="Q-001", db=db, _=_mock_user())

        assert result["revoked"] is True
        assert q.valid_until == date.today()
        db.commit.assert_called_once()


# ── TestTargetProgress ───────────────────────────────────────────────────────

class TestTargetProgress:

    @pytest.mark.asyncio
    async def test_target_progress_on_track(self):
        from src.api.banquet_agent import get_target_progress

        target = _make_target(target_fen=10000000)  # 100000 yuan

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([target]),   # target lookup
            _scalar_returning(8000000),     # actual revenue_fen (80000 yuan)
        ])

        result = await get_target_progress(store_id="S001", year=2026, month=3,
                                            db=db, _=_mock_user())

        assert result["target_yuan"] == 100000.0
        assert result["actual_yuan"] == 80000.0
        assert result["achievement_pct"] == 80.0
        assert "gap_yuan" in result
        assert "on_track" in result

    @pytest.mark.asyncio
    async def test_target_progress_behind(self):
        from src.api.banquet_agent import get_target_progress

        target = _make_target(target_fen=10000000)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([target]),
            _scalar_returning(500000),   # only 5000 yuan actual — way behind
        ])

        result = await get_target_progress(store_id="S001", year=2026, month=3,
                                            db=db, _=_mock_user())

        assert result["achievement_pct"] < 10
        assert result["gap_yuan"] > 0

    @pytest.mark.asyncio
    async def test_target_progress_404_when_no_target(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import get_target_progress

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await get_target_progress(store_id="S001", year=2026, month=3,
                                       db=db, _=_mock_user())
        assert exc.value.status_code == 404


# ── TestTargetTrend ──────────────────────────────────────────────────────────

class TestTargetTrend:

    @pytest.mark.asyncio
    async def test_target_trend_returns_n_months(self):
        from src.api.banquet_agent import get_target_trend

        t1 = _make_target(year=2026, month=2, target_fen=8000000)
        t2 = _make_target(year=2026, month=3, target_fen=10000000)

        # targets query
        targets_res = _scalars_returning([t1, t2])
        # kpi aggregation
        kpi_row1 = MagicMock(); kpi_row1.y = 2026; kpi_row1.m = 2; kpi_row1.revenue_fen = 7000000
        kpi_row2 = MagicMock(); kpi_row2.y = 2026; kpi_row2.m = 3; kpi_row2.revenue_fen = 5000000
        kpi_res = MagicMock(); kpi_res.all.return_value = [kpi_row1, kpi_row2]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[targets_res, kpi_res])

        result = await get_target_trend(store_id="S001", months=3,
                                         db=db, _=_mock_user())

        assert len(result["months"]) == 3
        months_map = {r["month"]: r for r in result["months"]}
        assert months_map["2026-02"]["target_yuan"] == 80000.0
        assert months_map["2026-03"]["actual_yuan"] == 50000.0

    @pytest.mark.asyncio
    async def test_target_trend_missing_months_default_zero(self):
        from src.api.banquet_agent import get_target_trend

        targets_res = _scalars_returning([])   # no targets at all
        kpi_res = MagicMock(); kpi_res.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[targets_res, kpi_res])

        result = await get_target_trend(store_id="S001", months=3,
                                         db=db, _=_mock_user())

        assert len(result["months"]) == 3
        for row in result["months"]:
            assert row["target_yuan"] == 0
            assert row["actual_yuan"] == 0


# ── TestLeadScoring ──────────────────────────────────────────────────────────

class TestLeadScoring:

    @pytest.mark.asyncio
    async def test_score_calculation_rules(self):
        from src.api.banquet_agent import _compute_lead_score

        lead = _make_lead(
            stage="quoted",
            budget_fen=6000000,    # 60000 yuan → score=20
            last_followup_days=3,  # recency→15
            has_date=True,
            has_tables=True,
        )

        result = _compute_lead_score(lead)

        assert result["breakdown"]["stage_score"] == 30        # quoted
        assert result["breakdown"]["budget_score"] == 20       # 40000–79999
        assert result["breakdown"]["recency_score"] == 15      # ≤7 days
        assert result["breakdown"]["completeness_score"] == 15 # all 3 fields
        assert result["score"] == 80
        assert result["grade"] == "A"

    @pytest.mark.asyncio
    async def test_batch_score_writes_log(self):
        from src.api.banquet_agent import score_leads

        lead1 = _make_lead("L-001", stage="quoted")
        lead2 = _make_lead("L-002", stage="new", budget_fen=None,
                           last_followup_days=60, has_date=False, has_tables=False)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([lead1, lead2]))
        db.add = MagicMock()
        db.commit = AsyncMock()

        result = await score_leads(store_id="S001", db=db,
                                    current_user=_mock_user())

        assert result["scored_count"] == 2
        assert db.add.call_count == 2
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_lead_score_reads_latest_log(self):
        from src.api.banquet_agent import get_lead_score

        lead = _make_lead()
        log = MagicMock()
        log.action_result = {"score": 75, "grade": "A",
                              "breakdown": {"stage_score": 30, "budget_score": 20,
                                            "recency_score": 15, "completeness_score": 10}}
        log.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([lead]),   # lead existence check
            _scalars_returning([log]),    # latest log
        ])

        result = await get_lead_score(store_id="S001", lead_id="LEAD-001",
                                       db=db, _=_mock_user())

        assert result["score"] == 75
        assert result["grade"] == "A"
        assert result["scored_at"] is not None
