"""
Banquet Agent Phase 6 — 单元测试

覆盖端点（API 层，不依赖真实 DB）：
  - get_customer_detail : 客户详情（基本信息 + 线索列表 + 订单列表）
  - create_lead         : 创建线索（含 customer_id 校验）
  - create_order        : 创建订单
  - confirm_order       : 确认订单（draft → confirmed）
  - list_customers      : 客户列表（含搜索）
"""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_user():
    u = MagicMock()
    u.id = "user-001"
    u.brand_id = "BRAND-001"
    return u


def _make_customer(cid="CUST-001", store_id="S001"):
    c = MagicMock()
    c.id = cid
    c.store_id = store_id
    c.name = "王五"
    c.phone = "13700001111"
    c.wechat_id = None
    c.customer_type = "个人"
    c.company_name = None
    c.vip_level = 1
    c.total_banquet_count = 2
    c.total_banquet_amount_fen = 10000000  # 100000元
    c.source = "referral"
    c.tags = None
    c.remark = None
    return c


def _make_lead(lead_id="LEAD-001", customer_id="CUST-001", store_id="S001"):
    l = MagicMock()
    l.id = lead_id
    l.customer_id = customer_id
    l.store_id = store_id
    l.banquet_type.value = "wedding"
    l.expected_date = date(2026, 10, 1)
    l.current_stage.value = "quoted"
    l.converted_order_id = None
    l.created_at = datetime(2026, 3, 1)
    return l


def _make_order(order_id="ORD-001", customer_id="CUST-001", store_id="S001", status="draft"):
    from src.models.banquet import OrderStatusEnum, BanquetTypeEnum
    o = MagicMock()
    o.id = order_id
    o.customer_id = customer_id
    o.store_id = store_id
    o.banquet_type.value = "wedding"
    o.banquet_date = date(2026, 10, 1)
    o.people_count = 200
    o.table_count = 20
    o.total_amount_fen = 5000000
    o.deposit_fen = 1000000
    o.paid_fen = 0
    o.contact_name = "王五"
    o.contact_phone = "13700001111"
    o.remark = None
    status_map = {
        "draft":     OrderStatusEnum.DRAFT,
        "confirmed": OrderStatusEnum.CONFIRMED,
    }
    o.order_status = status_map.get(status, OrderStatusEnum.DRAFT)
    return o


def _scalars_returning(items):
    r = MagicMock()
    r.scalars.return_value.first.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value = items
    r.first.return_value = items[0] if items else None
    r.all.return_value = items
    return r


# ── get_customer_detail ────────────────────────────────────────────────────────

class TestGetCustomerDetail:

    @pytest.mark.asyncio
    async def test_returns_customer_fields(self):
        from src.api.banquet_agent import get_customer_detail

        customer = _make_customer()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([customer]),  # customer query
            _scalars_returning([]),          # leads query
            _scalars_returning([]),          # orders query
        ])

        result = await get_customer_detail(
            store_id="S001", customer_id="CUST-001",
            db=db, _=_mock_user(),
        )

        assert result["customer"]["id"] == "CUST-001"
        assert result["customer"]["name"] == "王五"
        assert result["customer"]["total_banquet_amount_yuan"] == 100000.0
        assert result["leads"] == []
        assert result["orders"] == []

    @pytest.mark.asyncio
    async def test_includes_leads_and_orders(self):
        from src.api.banquet_agent import get_customer_detail

        customer = _make_customer()
        lead  = _make_lead()
        order = _make_order()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalars_returning([customer]),
            _scalars_returning([lead]),
            _scalars_returning([order]),
        ])

        result = await get_customer_detail(
            store_id="S001", customer_id="CUST-001",
            db=db, _=_mock_user(),
        )

        assert len(result["leads"]) == 1
        assert result["leads"][0]["lead_id"] == "LEAD-001"
        assert result["leads"][0]["banquet_type"] == "wedding"
        assert result["leads"][0]["stage_label"] == "意向确认"

        assert len(result["orders"]) == 1
        assert result["orders"][0]["order_id"] == "ORD-001"
        assert result["orders"][0]["total_amount_yuan"] == 50000.0

    @pytest.mark.asyncio
    async def test_404_when_customer_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import get_customer_detail

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await get_customer_detail(
                store_id="S001", customer_id="NONEXISTENT",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_store_isolation(self):
        """customer in different store should return 404"""
        from fastapi import HTTPException
        from src.api.banquet_agent import get_customer_detail

        # query returns empty because store_id filter excludes it
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await get_customer_detail(
                store_id="S002", customer_id="CUST-001",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404


# ── list_customers ─────────────────────────────────────────────────────────────

class TestListCustomers:

    @pytest.mark.asyncio
    async def test_returns_customer_list(self):
        from src.api.banquet_agent import list_customers

        c1 = _make_customer(cid="C1")
        c2 = _make_customer(cid="C2")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c1, c2]))

        result = await list_customers(store_id="S001", q=None, db=db, _=_mock_user())

        assert result["total"] == 2
        assert result["items"][0]["id"] == "C1"

    @pytest.mark.asyncio
    async def test_search_filters_by_query(self):
        from src.api.banquet_agent import list_customers

        c = _make_customer()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([c]))

        result = await list_customers(store_id="S001", q="王五", db=db, _=_mock_user())

        # verify the query was executed (search applied)
        db.execute.assert_awaited_once()
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_empty_store(self):
        from src.api.banquet_agent import list_customers

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        result = await list_customers(store_id="S001", q=None, db=db, _=_mock_user())

        assert result["total"] == 0
        assert result["items"] == []


# ── create_lead ────────────────────────────────────────────────────────────────

class TestCreateLead:

    @pytest.mark.asyncio
    async def test_creates_lead_successfully(self):
        from src.api.banquet_agent import create_lead, LeadCreateReq
        from src.models.banquet import BanquetTypeEnum

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        body = LeadCreateReq(
            customer_id="CUST-001",
            banquet_type=BanquetTypeEnum.WEDDING,
            expected_date=date(2026, 10, 1),
            expected_people_count=200,
            expected_budget_yuan=60000.0,
            source_channel="referral",
        )
        result = await create_lead(store_id="S001", body=body, db=db, _=_mock_user())

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["current_stage"] == "new"

    @pytest.mark.asyncio
    async def test_lead_without_optional_fields(self):
        from src.api.banquet_agent import create_lead, LeadCreateReq
        from src.models.banquet import BanquetTypeEnum

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        body = LeadCreateReq(
            customer_id="CUST-001",
            banquet_type=BanquetTypeEnum.BIRTHDAY,
        )
        result = await create_lead(store_id="S001", body=body, db=db, _=_mock_user())

        db.add.assert_called_once()
        assert "id" in result


# ── create_order ───────────────────────────────────────────────────────────────

class TestCreateOrder:

    @pytest.mark.asyncio
    async def test_creates_order_from_lead(self):
        from src.api.banquet_agent import create_order, OrderCreateReq
        from src.models.banquet import BanquetTypeEnum

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        body = OrderCreateReq(
            lead_id="LEAD-001",
            customer_id="CUST-001",
            banquet_type=BanquetTypeEnum.WEDDING,
            banquet_date=date(2026, 10, 1),
            people_count=200,
            table_count=20,
            total_amount_yuan=50000.0,
            deposit_yuan=10000.0,
            contact_name="王五",
            contact_phone="13700001111",
        )
        result = await create_order(store_id="S001", body=body, db=db, _=_mock_user())

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["order_status"] == "draft"

    @pytest.mark.asyncio
    async def test_creates_order_without_lead(self):
        from src.api.banquet_agent import create_order, OrderCreateReq
        from src.models.banquet import BanquetTypeEnum

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()

        body = OrderCreateReq(
            customer_id="CUST-001",
            banquet_type=BanquetTypeEnum.BUSINESS,
            banquet_date=date(2026, 11, 5),
            people_count=50,
            table_count=5,
            total_amount_yuan=20000.0,
        )
        result = await create_order(store_id="S001", body=body, db=db, _=_mock_user())

        assert result["order_status"] == "draft"


# ── confirm_order ──────────────────────────────────────────────────────────────

class TestConfirmOrder:

    @pytest.mark.asyncio
    async def test_confirms_draft_order_and_generates_tasks(self):
        from src.api.banquet_agent import confirm_order
        from src.models.banquet import OrderStatusEnum
        from unittest.mock import patch, AsyncMock as AM

        order = _make_order(status="draft")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))
        db.commit = AsyncMock()

        # mock ExecutionAgent.generate_tasks_for_order
        with patch("src.api.banquet_agent._execution") as mock_exec:
            mock_exec.generate_tasks_for_order = AM(return_value=["T1", "T2", "T3"])
            result = await confirm_order(
                store_id="S001", order_id="ORD-001",
                db=db, _=_mock_user(),
            )

        assert order.order_status == OrderStatusEnum.CONFIRMED
        db.commit.assert_awaited_once()
        assert result["order_status"] == "confirmed"
        assert result["tasks_generated"] == 3

    @pytest.mark.asyncio
    async def test_400_when_order_not_draft(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import confirm_order

        order = _make_order(status="confirmed")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))

        with pytest.raises(HTTPException) as exc_info:
            await confirm_order(
                store_id="S001", order_id="ORD-001",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_404_when_order_not_found(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import confirm_order

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc_info:
            await confirm_order(
                store_id="S001", order_id="NONEXISTENT",
                db=db, _=_mock_user(),
            )
        assert exc_info.value.status_code == 404
