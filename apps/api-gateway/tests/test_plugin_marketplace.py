"""Tests for Phase 3 Month 4 — Plugin Marketplace API"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

with patch("src.core.config", create=True):
    from src.api.plugin_marketplace import (
        CATEGORIES,
        PRICE_TYPES,
        _parse_tags,
        _row_to_dict,
        submit_plugin,
        review_plugin,
        install_plugin,
        uninstall_plugin,
        get_marketplace_stats,
        list_plugins,
        admin_list_plugins,
        SubmitPluginRequest,
        ReviewPluginRequest,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_db(first_return=None, scalar_return=None, fetchall_return=None):
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.first.return_value = first_return
    execute_result.scalar.return_value = scalar_return or 0
    execute_result.fetchall.return_value = fetchall_return or []
    db.execute.return_value = execute_result
    return db


def make_row(**kwargs):
    row = MagicMock()
    row._mapping = kwargs
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# ── Constants ──────────────────────────────────────────────────────────────────


class TestConstants:
    def test_categories_has_five_entries(self):
        assert len(CATEGORIES) == 5

    def test_pos_integration_in_categories(self):
        assert "pos_integration" in CATEGORIES

    def test_price_types_has_three_entries(self):
        assert len(PRICE_TYPES) == 3

    def test_free_in_price_types(self):
        assert "free" in PRICE_TYPES


# ── Helpers ────────────────────────────────────────────────────────────────────


class TestHelpers:
    def test_parse_tags_json_string(self):
        p = {"tags": '["a", "b"]'}
        result = _parse_tags(p)
        assert result["tags"] == ["a", "b"]

    def test_parse_tags_already_list(self):
        p = {"tags": ["x"]}
        result = _parse_tags(p)
        assert result["tags"] == ["x"]

    def test_parse_tags_invalid_json_returns_empty(self):
        p = {"tags": "not-json"}
        result = _parse_tags(p)
        assert result["tags"] == []


# ── Submit plugin ──────────────────────────────────────────────────────────────


class TestSubmitPlugin:
    @pytest.mark.asyncio
    async def test_submit_valid_plugin(self):
        dev_row = make_row(id="dev_abc", status="active")
        db = AsyncMock()

        call_count = 0
        async def execute_side(sql, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # dev check
                result.first.return_value = dev_row
            elif call_count == 2:  # slug check
                result.first.return_value = None
            else:
                result.first.return_value = None
            return result

        db.execute.side_effect = execute_side

        body = SubmitPluginRequest(
            developer_id="dev_abc",
            name="美团订单同步",
            slug="meituan-order-sync",
            description="同步美团外卖订单到智链OS",
            category="pos_integration",
        )
        result = await submit_plugin(body, db)
        assert result["plugin_id"].startswith("plg_")
        assert result["status"] == "pending_review"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_category_returns_400(self):
        body = SubmitPluginRequest(
            developer_id="dev_x",
            name="Test",
            slug="test-plugin",
            description="desc",
            category="invalid_cat",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await submit_plugin(body, AsyncMock())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_nonexistent_developer_returns_404(self):
        db = make_db(first_return=None)
        body = SubmitPluginRequest(
            developer_id="dev_missing",
            name="Test",
            slug="test-x",
            description="desc",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await submit_plugin(body, db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_suspended_developer_returns_403(self):
        dev_row = make_row(id="dev_s", status="suspended")
        db = make_db(first_return=dev_row)
        body = SubmitPluginRequest(
            developer_id="dev_s",
            name="Test",
            slug="test-susp",
            description="desc",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await submit_plugin(body, db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_slug_returns_409(self):
        dev_row = make_row(id="dev_ok", status="active")
        slug_row = make_row(exists=1)
        db = AsyncMock()
        call_count = 0

        async def execute_side(sql, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.first.return_value = dev_row if call_count == 1 else slug_row
            return result

        db.execute.side_effect = execute_side
        body = SubmitPluginRequest(
            developer_id="dev_ok",
            name="Dup",
            slug="existing-slug",
            description="desc",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await submit_plugin(body, db)
        assert exc_info.value.status_code == 409


# ── Admin review ───────────────────────────────────────────────────────────────


class TestAdminReview:
    @pytest.mark.asyncio
    async def test_approve_publishes_plugin(self):
        plugin_row = make_row(id="plg_1", status="pending_review")
        db = make_db(first_return=plugin_row)
        body = ReviewPluginRequest(approved=True, note="LGTM")
        result = await review_plugin("plg_1", body, db)
        assert result["status"] == "published"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_changes_status_to_rejected(self):
        plugin_row = make_row(id="plg_2", status="pending_review")
        db = make_db(first_return=plugin_row)
        body = ReviewPluginRequest(approved=False, note="接口不符合规范")
        result = await review_plugin("plg_2", body, db)
        assert result["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_without_note_returns_400(self):
        plugin_row = make_row(id="plg_3", status="pending_review")
        db = make_db(first_return=plugin_row)
        body = ReviewPluginRequest(approved=False, note=None)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await review_plugin("plg_3", body, db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_nonexistent_plugin_returns_404(self):
        db = make_db(first_return=None)
        body = ReviewPluginRequest(approved=True)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await review_plugin("plg_missing", body, db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_already_reviewed_returns_409(self):
        plugin_row = make_row(id="plg_5", status="published")
        db = make_db(first_return=plugin_row)
        body = ReviewPluginRequest(approved=True)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await review_plugin("plg_5", body, db)
        assert exc_info.value.status_code == 409


# ── Install plugin ─────────────────────────────────────────────────────────────


class TestInstallPlugin:
    @pytest.mark.asyncio
    async def test_install_published_plugin(self):
        plugin_row = make_row(id="plg_pub", name="美团同步", status="published")
        db = AsyncMock()
        call_count = 0

        async def execute_side(sql, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:   # plugin lookup
                result.first.return_value = plugin_row
            elif call_count == 2:  # existing installation check
                result.first.return_value = None
            else:
                result.first.return_value = None
            return result

        db.execute.side_effect = execute_side
        result = await install_plugin("STORE001", "plg_pub", db)
        assert result["installation_id"].startswith("inst_")
        assert result["status"] == "active"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_published_returns_400(self):
        plugin_row = make_row(id="plg_draft", name="Draft", status="pending_review")
        db = make_db(first_return=plugin_row)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await install_plugin("STORE001", "plg_draft", db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_nonexistent_plugin_returns_404(self):
        db = make_db(first_return=None)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await install_plugin("STORE001", "plg_none", db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_already_installed_returns_409(self):
        plugin_row = make_row(id="plg_dup", name="Dup", status="published")
        install_row = make_row(id="inst_existing")
        db = AsyncMock()
        call_count = 0

        async def execute_side(sql, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.first.return_value = plugin_row if call_count == 1 else install_row
            return result

        db.execute.side_effect = execute_side
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await install_plugin("STORE001", "plg_dup", db)
        assert exc_info.value.status_code == 409


# ── Uninstall plugin ───────────────────────────────────────────────────────────


class TestUninstallPlugin:
    @pytest.mark.asyncio
    async def test_uninstall_installed_plugin(self):
        install_row = make_row(id="inst_abc")
        db = make_db(first_return=install_row)
        result = await uninstall_plugin("STORE001", "plg_pub", db)
        assert "卸载" in result["message"]
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uninstall_not_installed_returns_404(self):
        db = make_db(first_return=None)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await uninstall_plugin("STORE001", "plg_none", db)
        assert exc_info.value.status_code == 404


# ── Stats ──────────────────────────────────────────────────────────────────────


class TestMarketplaceStats:
    @pytest.mark.asyncio
    async def test_stats_structure(self):
        stats_row = make_row(
            published_count=10,
            pending_review_count=2,
            active_developers=5,
            total_installs=100,
        )
        db = AsyncMock()
        call_count = 0

        async def execute_side(sql, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.first.return_value = stats_row
            else:
                result.fetchall.return_value = []
            return result

        db.execute.side_effect = execute_side
        result = await get_marketplace_stats(db)
        assert "published_plugins" in result
        assert "pending_review" in result
        assert "active_developers" in result
        assert "total_installs" in result
        assert "categories" in result

    @pytest.mark.asyncio
    async def test_stats_categories_match_constants(self):
        stats_row = make_row(
            published_count=0,
            pending_review_count=0,
            active_developers=0,
            total_installs=0,
        )
        db = AsyncMock()
        call_count = 0

        async def execute_side(sql, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.first.return_value = stats_row
            else:
                result.fetchall.return_value = []
            return result

        db.execute.side_effect = execute_side
        result = await get_marketplace_stats(db)
        assert result["categories"] == CATEGORIES
