"""
Banquet Agent Phase 11 — 单元测试

覆盖端点：
  - list_templates / create_template / update_template / deactivate_template
  - report_exception / list_exceptions / resolve_exception
  - create_customer_with_lead
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ── helpers ─────────────────────────────────────────────────────────────────

def _mock_user(uid="user-001"):
    u = MagicMock()
    u.id = uid
    u.brand_id = "BRAND-001"
    return u


def _scalars_returning(items):
    r = MagicMock()
    r.scalars.return_value.first.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value = items
    return r


def _make_template(tid="TPL-1", name="婚宴标准模板", bt=None, task_defs=None):
    from src.models.banquet import BanquetTypeEnum
    t = MagicMock()
    t.id = tid
    t.template_name = name
    t.banquet_type = BanquetTypeEnum.WEDDING if bt is None else bt
    t.task_defs = task_defs or [
        {"task_name": "确认菜单", "owner_role": "kitchen", "days_before": 7},
        {"task_name": "厅房布置", "owner_role": "decor",   "days_before": 1},
    ]
    t.version = 1
    t.is_active = True
    t.created_at = datetime.utcnow()
    return t


def _make_order(oid="ORD-001"):
    from src.models.banquet import BanquetTypeEnum
    o = MagicMock()
    o.id = oid
    o.store_id = "S001"
    o.banquet_type = BanquetTypeEnum.WEDDING
    return o


def _make_exception(eid="EXC-1", etype="late", severity="medium",
                    order_id="ORD-001", status="open"):
    from src.models.banquet import BanquetTypeEnum
    e = MagicMock()
    e.id = eid
    e.banquet_order_id = order_id
    e.exception_type = etype
    e.description = "食材迟到30分钟"
    e.severity = severity
    e.owner_user_id = "user-001"
    e.status = status
    e.created_at = datetime.utcnow()
    e.resolved_at = None
    return e


def _make_customer(cid="CUST-1", name="李四", phone="13900139000"):
    c = MagicMock()
    c.id = cid
    c.name = name
    c.phone = phone
    return c


# ── TestTemplates ─────────────────────────────────────────────────────────────

class TestTemplates:

    @pytest.mark.asyncio
    async def test_list_returns_active_templates(self):
        from src.api.banquet_agent import list_templates

        tpl = _make_template()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([tpl]))

        result = await list_templates(store_id="S001", banquet_type=None, db=db, _=_mock_user())

        assert len(result) == 1
        assert result[0]["template_id"] == "TPL-1"
        assert result[0]["task_count"] == 2
        assert result[0]["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_template_stores_task_defs(self):
        from src.api.banquet_agent import create_template

        class _Body:
            template_name = "满月酒模板"
            banquet_type  = "full_moon"
            task_defs     = [{"task_name": "备品", "owner_role": "service", "days_before": 2}]

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda t: setattr(t, "banquet_type",
            __import__("src.models.banquet", fromlist=["BanquetTypeEnum"]).BanquetTypeEnum.FULL_MOON
            if hasattr(__import__("src.models.banquet", fromlist=["BanquetTypeEnum"]).BanquetTypeEnum, "FULL_MOON") else t.banquet_type))

        result = await create_template(store_id="S001", body=_Body(), db=db, _=_mock_user())

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result["template_name"] == "满月酒模板"
        assert result["task_count"] == 1

    @pytest.mark.asyncio
    async def test_deactivate_sets_is_active_false(self):
        from src.api.banquet_agent import deactivate_template

        tpl = _make_template()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([tpl]))
        db.commit = AsyncMock()

        result = await deactivate_template(store_id="S001", template_id="TPL-1",
                                           db=db, _=_mock_user())

        assert result["is_active"] is False
        assert tpl.is_active is False

    @pytest.mark.asyncio
    async def test_deactivate_404_on_missing(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import deactivate_template

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await deactivate_template(store_id="S001", template_id="NONE",
                                      db=db, _=_mock_user())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_template_bumps_version_when_task_defs_change(self):
        from src.api.banquet_agent import update_template

        tpl = _make_template()

        class _Body:
            template_name = None
            banquet_type  = None
            task_defs     = [{"task_name": "新任务", "owner_role": "kitchen", "days_before": 3}]
            is_active     = None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([tpl]))
        db.commit = AsyncMock()

        result = await update_template(store_id="S001", template_id="TPL-1",
                                       body=_Body(), db=db, _=_mock_user())

        assert result["version"] == 2
        assert result["task_count"] == 1


# ── TestExceptions ────────────────────────────────────────────────────────────

class TestExceptions:

    @pytest.mark.asyncio
    async def test_report_exception_creates_record(self):
        from src.api.banquet_agent import report_exception

        order = _make_order()

        class _Body:
            exception_type = "late"
            description    = "食材晚到了"
            severity       = "medium"

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([order]))
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda e: (
            setattr(e, "status", "open") or
            setattr(e, "created_at", datetime.utcnow())
        ))

        result = await report_exception(store_id="S001", order_id="ORD-001",
                                        body=_Body(), db=db, current_user=_mock_user())

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result["exception_type"] == "late"
        assert result["severity"] == "medium"
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_report_exception_404_on_unknown_order(self):
        from fastapi import HTTPException
        from src.api.banquet_agent import report_exception

        class _Body:
            exception_type = "missing"
            description    = "少了桌花"
            severity       = "low"

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([]))

        with pytest.raises(HTTPException) as exc:
            await report_exception(store_id="S001", order_id="GHOST",
                                   body=_Body(), db=db, current_user=_mock_user())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_exceptions_filters_by_status(self):
        from src.api.banquet_agent import list_exceptions

        exc1 = _make_exception(eid="E1", status="open")
        order = _make_order()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[
            (exc1, order.banquet_type)
        ])))

        result = await list_exceptions(store_id="S001", status="open",
                                       order_id=None, db=db, _=_mock_user())

        assert len(result) == 1
        assert result[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_resolve_exception_updates_status(self):
        from src.api.banquet_agent import resolve_exception

        exc = _make_exception(status="open")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([exc]))
        db.commit = AsyncMock()

        result = await resolve_exception(store_id="S001", exception_id="EXC-1",
                                         db=db, _=_mock_user())

        assert result["status"] == "resolved"
        assert exc.status == "resolved"
        assert exc.resolved_at is not None


# ── TestCustomerWithLead ─────────────────────────────────────────────────────

class TestCustomerWithLead:

    @pytest.mark.asyncio
    async def test_creates_new_customer_and_lead(self):
        from src.api.banquet_agent import create_customer_with_lead

        class _Body:
            customer_name   = "王五"
            phone           = "13700137000"
            banquet_type    = "wedding"
            expected_date   = "2026-09-18"
            expected_tables = 20
            budget_yuan     = 80000.0
            remark          = None

        db = AsyncMock()
        # No existing customer found
        db.execute = AsyncMock(return_value=_scalars_returning([]))
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        result = await create_customer_with_lead(store_id="S001", body=_Body(),
                                                  db=db, current_user=_mock_user())

        # add called twice: customer + lead
        assert db.add.call_count == 2
        assert "customer_id" in result
        assert "lead_id" in result

    @pytest.mark.asyncio
    async def test_reuses_existing_customer_by_phone(self):
        from src.api.banquet_agent import create_customer_with_lead

        existing_customer = _make_customer()

        class _Body:
            customer_name   = "李四"
            phone           = "13900139000"
            banquet_type    = "birthday"
            expected_date   = None
            expected_tables = None
            budget_yuan     = None
            remark          = None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_returning([existing_customer]))
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        result = await create_customer_with_lead(store_id="S001", body=_Body(),
                                                  db=db, current_user=_mock_user())

        # add called only once: lead (customer reused)
        assert db.add.call_count == 1
        assert result["customer_id"] == "CUST-1"
