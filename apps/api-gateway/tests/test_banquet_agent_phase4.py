"""
Banquet Agent Phase 4 — 单元测试

覆盖端点（API 层，不依赖真实 DB）：
  - get_lead_detail         : 线索详情（客户 + 跟进时间线 + 报价列表）
  - accept_quote            : 接受报价单
  - get_contract            : 查询合同
  - create_contract         : 创建合同（自动生成合同号）
  - sign_contract           : 签约（draft → signed）
  - list_profit_snapshots   : 利润快照列表
  - create_profit_snapshot  : 创建/更新利润快照（upsert）
"""

import pytest
import uuid
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_user(user_id="user-001"):
    u = MagicMock()
    u.id = user_id
    return u


def _make_lead(lead_id="LEAD-001", store_id="S001"):
    l = MagicMock()
    l.id = lead_id
    l.store_id = store_id
    l.banquet_type.value = "wedding"
    l.expected_date = date(2026, 9, 18)
    l.expected_people_count = 200
    l.expected_budget_fen = 6000000
    l.preferred_hall_type = None
    l.source_channel = "referral"
    l.current_stage.value = "quoted"
    l.owner_user_id = "user-001"
    l.last_followup_at = None
    l.converted_order_id = None
    l.customer = MagicMock()
    l.customer.name = "李四"
    l.customer.phone = "13900001111"
    l.followups = []
    return l


def _make_followup(followup_id="FUP-001"):
    f = MagicMock()
    f.id = followup_id
    f.followup_type = "call"
    f.content = "客户确认预算范围"
    f.stage_before = None
    f.stage_after = None
    f.next_followup_at = None
    f.created_at = datetime(2026, 3, 9, 10, 0)
    return f


def _make_quote(quote_id="QUOTE-001", lead_id="LEAD-001", store_id="S001"):
    q = MagicMock()
    q.id = quote_id
    q.lead_id = lead_id
    q.store_id = store_id
    q.people_count = 200
    q.table_count = 20
    q.quoted_amount_fen = 5000000
    q.valid_until = date(2026, 6, 1)
    q.is_accepted = False
    q.package_id = None
    q.created_at = datetime(2026, 3, 9, 8, 0)
    return q


def _make_order(order_id="ORD-001", store_id="S001"):
    o = MagicMock()
    o.id = order_id
    o.store_id = store_id
    o.banquet_date = date(2026, 9, 18)
    o.banquet_type.value = "wedding"
    return o


def _make_contract(contract_id="CTR-001", order_id="ORD-001", status="draft"):
    c = MagicMock()
    c.id = contract_id
    c.banquet_order_id = order_id
    c.contract_no = f"BQ-S001-20260301-ORD001"
    c.contract_status = status
    c.file_url = None
    c.signed_at = datetime(2026, 3, 9, 12, 0) if status == "signed" else None
    c.signed_by = "user-001" if status == "signed" else None
    return c


def _make_snapshot(snap_id="SNAP-001", order_id="ORD-001"):
    s = MagicMock()
    s.id = snap_id
    s.banquet_order_id = order_id
    s.revenue_fen = 5000000
    s.ingredient_cost_fen = 1500000
    s.labor_cost_fen = 500000
    s.material_cost_fen = 200000
    s.other_cost_fen = 100000
    s.gross_profit_fen = 2700000
    s.gross_margin_pct = 54.0
    return s


def _scalars_returning(items):
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = items[0] if items else None
    mock_result.scalars.return_value.all.return_value = items
    mock_result.first.return_value = items[0] if items else None
    mock_result.all.return_value = items
    return mock_result


def _scalar_first_returning(value):
    mock_result = MagicMock()
    mock_result.first.return_value = value
    return mock_result


# ── get_lead_detail ────────────────────────────────────────────────────────────

class TestGetLeadDetail:

    @pytest.mark.asyncio
    async def test_returns_lead_fields(self):
        from src.api.banquet_agent import get_lead_detail
        from src.models.banquet import BanquetLead

        lead = _make_lead()
        # Two execute calls: one for lead, one for quotes
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([lead]),  # lead query
            _scalars_returning([]),      # quotes query
        ])

        result = await get_lead_detail(
            store_id="S001", lead_id="LEAD-001",
            db=db, _=_mock_user(),
        )

        assert result["lead_id"] == "LEAD-001"
        assert result["banquet_type"] == "wedding"
        assert result["contact_name"] == "李四"
        assert result["expected_budget_yuan"] == 60000.0
        assert result["quotes"] == []
        assert result["followups"] == []

    @pytest.mark.asyncio
    async def test_includes_followups_and_quotes(self):
        from src.api.banquet_agent import get_lead_detail

        lead = _make_lead()
        fup = _make_followup()
        lead.followups = [fup]
        quote = _make_quote()

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([lead]),
            _scalars_returning([quote]),
        ])

        result = await get_lead_detail(
            store_id="S001", lead_id="LEAD-001",
            db=db, _=_mock_user(),
        )

        assert len(result["followups"]) == 1
        assert result["followups"][0]["followup_id"] == "FUP-001"
        assert result["followups"][0]["content"] == "客户确认预算范围"
        assert len(result["quotes"]) == 1
        assert result["quotes"][0]["quote_id"] == "QUOTE-001"
        assert result["quotes"][0]["quoted_amount_yuan"] == 50000.0

    @pytest.mark.asyncio
    async def test_404_when_lead_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import get_lead_detail

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await get_lead_detail(
                store_id="S001", lead_id="NONEXISTENT",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404


# ── accept_quote ───────────────────────────────────────────────────────────────

class TestAcceptQuote:

    @pytest.mark.asyncio
    async def test_sets_is_accepted_true(self):
        from src.api.banquet_agent import accept_quote

        quote = _make_quote()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([quote]))
        db.commit = AsyncMock()

        result = await accept_quote(
            store_id="S001", lead_id="LEAD-001", quote_id="QUOTE-001",
            db=db, _=_mock_user(),
        )

        assert quote.is_accepted is True
        db.commit.assert_awaited_once()
        assert result["is_accepted"] is True
        assert result["quote_id"] == "QUOTE-001"

    @pytest.mark.asyncio
    async def test_404_when_quote_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import accept_quote

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await accept_quote(
                store_id="S001", lead_id="LEAD-001", quote_id="NONEXISTENT",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_403_when_store_mismatch(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import accept_quote

        quote = _make_quote(store_id="OTHER-STORE")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([quote]))

        with pytest.raises(HTTPException) as exc_info:
            await accept_quote(
                store_id="S001", lead_id="LEAD-001", quote_id="QUOTE-001",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 403


# ── get_contract ───────────────────────────────────────────────────────────────

class TestGetContract:

    @pytest.mark.asyncio
    async def test_returns_null_when_no_contract(self):
        from src.api.banquet_agent import get_contract

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_first_returning(("ORD-001",)),  # order exists check
            _scalars_returning([]),                  # no contract
        ])

        result = await get_contract(
            store_id="S001", order_id="ORD-001",
            db=db, _=_mock_user(),
        )

        assert result["contract"] is None
        assert result["order_id"] == "ORD-001"

    @pytest.mark.asyncio
    async def test_returns_contract_when_exists(self):
        from src.api.banquet_agent import get_contract

        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_first_returning(("ORD-001",)),
            _scalars_returning([contract]),
        ])

        result = await get_contract(
            store_id="S001", order_id="ORD-001",
            db=db, _=_mock_user(),
        )

        assert result["contract"]["contract_id"] == "CTR-001"
        assert result["contract"]["contract_status"] == "draft"
        assert result["contract"]["signed_at"] is None

    @pytest.mark.asyncio
    async def test_404_when_order_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import get_contract

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_first_returning(None))

        with pytest.raises(HTTPException) as exc_info:
            await get_contract(
                store_id="S001", order_id="NONEXISTENT",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404


# ── create_contract ────────────────────────────────────────────────────────────

class TestCreateContract:

    @pytest.mark.asyncio
    async def test_creates_contract_with_auto_no(self):
        from src.api.banquet_agent import create_contract

        order = _make_order()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),  # order lookup
            _scalars_returning([]),       # no existing contract
        ])
        db.commit = AsyncMock()
        db.add = MagicMock()

        result = await create_contract(
            store_id="S001", order_id="ORD-001",
            db=db, _=_mock_user(),
        )

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["contract_status"] == "draft"
        assert "BQ-S001" in result["contract_no"]

    @pytest.mark.asyncio
    async def test_409_when_contract_already_exists(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import create_contract

        order = _make_order()
        existing = _make_contract()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([order]),
            _scalars_returning([existing]),
        ])

        with pytest.raises(HTTPException) as exc_info:
            await create_contract(
                store_id="S001", order_id="ORD-001",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_404_when_order_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import create_contract

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await create_contract(
                store_id="S001", order_id="NONEXISTENT",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404


# ── sign_contract ──────────────────────────────────────────────────────────────

class TestSignContract:

    @pytest.mark.asyncio
    async def test_signs_draft_contract(self):
        from src.api.banquet_agent import sign_contract, ContractSignReq

        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_first_returning(("ORD-001",)),  # order check
            _scalars_returning([contract]),          # contract lookup
        ])
        db.commit = AsyncMock()

        body = ContractSignReq(signed_by="user-001")
        result = await sign_contract(
            store_id="S001", order_id="ORD-001",
            body=body, db=db, current_user=_mock_user(),
        )

        assert contract.contract_status == "signed"
        db.commit.assert_awaited_once()
        assert result["contract_status"] == "signed"
        assert "signed_at" in result

    @pytest.mark.asyncio
    async def test_400_when_already_signed(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import sign_contract, ContractSignReq

        contract = _make_contract(status="signed")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_first_returning(("ORD-001",)),
            _scalars_returning([contract]),
        ])

        with pytest.raises(HTTPException) as exc_info:
            await sign_contract(
                store_id="S001", order_id="ORD-001",
                body=ContractSignReq(), db=db, current_user=_mock_user(),
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_404_when_contract_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import sign_contract, ContractSignReq

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_first_returning(("ORD-001",)),
            _scalars_returning([]),
        ])

        with pytest.raises(HTTPException) as exc_info:
            await sign_contract(
                store_id="S001", order_id="ORD-001",
                body=ContractSignReq(), db=db, current_user=_mock_user(),
            )
        assert exc_info.value.status_code == 404


# ── list_profit_snapshots ──────────────────────────────────────────────────────

class TestListProfitSnapshots:

    @pytest.mark.asyncio
    async def test_returns_snapshot_list(self):
        from src.api.banquet_agent import list_profit_snapshots

        snap = _make_snapshot()
        order = _make_order()
        row = (snap, order.banquet_date, order.banquet_type)

        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await list_profit_snapshots(
            store_id="S001", month=None,
            db=db, _=_mock_user(),
        )

        assert len(result) == 1
        assert result[0]["snapshot_id"] == "SNAP-001"
        assert result[0]["revenue_yuan"] == 50000.0
        assert result[0]["gross_profit_yuan"] == 27000.0
        assert result[0]["gross_margin_pct"] == 54.0

    @pytest.mark.asyncio
    async def test_filters_by_month(self):
        from src.api.banquet_agent import list_profit_snapshots

        mock_result = MagicMock()
        mock_result.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await list_profit_snapshots(
            store_id="S001", month="2026-09",
            db=db, _=_mock_user(),
        )

        assert result == []
        # verify execute was called (month filter applied, no crash)
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_month_format_returns_all(self):
        from src.api.banquet_agent import list_profit_snapshots

        mock_result = MagicMock()
        mock_result.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        # invalid format should not crash — filters silently ignored
        result = await list_profit_snapshots(
            store_id="S001", month="invalid-month",
            db=db, _=_mock_user(),
        )
        assert result == []


# ── create_profit_snapshot ─────────────────────────────────────────────────────

class TestCreateProfitSnapshot:

    @pytest.mark.asyncio
    async def test_creates_new_snapshot(self):
        from src.api.banquet_agent import create_profit_snapshot, ProfitSnapshotReq

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_first_returning(("ORD-001",)),  # order check
            _scalars_returning([]),                  # no existing snapshot
        ])
        db.commit = AsyncMock()
        db.add = MagicMock()

        body = ProfitSnapshotReq(
            revenue_yuan=50000.0,
            ingredient_cost_yuan=15000.0,
            labor_cost_yuan=5000.0,
        )
        result = await create_profit_snapshot(
            store_id="S001", order_id="ORD-001",
            body=body, db=db, _=_mock_user(),
        )

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["revenue_yuan"] == 50000.0
        assert result["gross_profit_yuan"] == 30000.0  # 50000 - 15000 - 5000
        assert result["gross_margin_pct"] == 60.0

    @pytest.mark.asyncio
    async def test_updates_existing_snapshot(self):
        from src.api.banquet_agent import create_profit_snapshot, ProfitSnapshotReq

        existing = _make_snapshot()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_first_returning(("ORD-001",)),
            _scalars_returning([existing]),
        ])
        db.commit = AsyncMock()
        db.add = MagicMock()

        body = ProfitSnapshotReq(
            revenue_yuan=60000.0,
            ingredient_cost_yuan=20000.0,
            labor_cost_yuan=8000.0,
        )
        result = await create_profit_snapshot(
            store_id="S001", order_id="ORD-001",
            body=body, db=db, _=_mock_user(),
        )

        # existing snapshot should be updated, not a new one created
        db.add.assert_not_called()
        db.commit.assert_awaited_once()
        assert existing.revenue_fen == 6000000
        assert existing.gross_profit_fen == (6000000 - 2000000 - 800000)

    @pytest.mark.asyncio
    async def test_404_when_order_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import create_profit_snapshot, ProfitSnapshotReq

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_first_returning(None))

        with pytest.raises(HTTPException) as exc_info:
            await create_profit_snapshot(
                store_id="S001", order_id="NONEXISTENT",
                body=ProfitSnapshotReq(revenue_yuan=1000.0),
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404
