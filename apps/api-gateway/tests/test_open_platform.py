"""
测试 Phase 2 aPaaS — 开放平台
- register_developer（ISV 开发者注册）
- list_capabilities（能力目录）
- get_platform_stats（平台统计）
"""
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/zhilian")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.api.open_platform import (  # noqa: E402
    CAPABILITIES,
    TIER_CONFIG,
    _hash_secret,
    _email_exists,
)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

class TestHashSecret:
    def test_deterministic(self):
        assert _hash_secret("abc") == _hash_secret("abc")

    def test_different_secrets_differ(self):
        assert _hash_secret("abc") != _hash_secret("xyz")

    def test_length(self):
        # SHA-256 hex = 64 chars
        assert len(_hash_secret("anything")) == 64


# ── 能力目录 ─────────────────────────────────────────────────────────────────

class TestCapabilities:
    def test_all_levels_present(self):
        levels = {c["level"] for c in CAPABILITIES}
        assert levels == {1, 2, 3, 4}

    def test_total_count(self):
        assert len(CAPABILITIES) >= 12  # at least 3 per level

    def test_each_capability_has_required_fields(self):
        for cap in CAPABILITIES:
            for field in ["level", "key", "name", "description", "tier_required"]:
                assert field in cap, f"缺少字段 {field} in {cap}"

    def test_free_caps_are_level1(self):
        free_caps = [c for c in CAPABILITIES if c["tier_required"] == "free"]
        assert all(c["level"] == 1 for c in free_caps)

    def test_enterprise_caps_are_level4(self):
        ent_caps = [c for c in CAPABILITIES if c["tier_required"] == "enterprise"]
        assert all(c["level"] == 4 for c in ent_caps)


# ── 套餐定价 ─────────────────────────────────────────────────────────────────

class TestTierConfig:
    def test_all_tiers_present(self):
        for tier in ["free", "basic", "pro", "enterprise"]:
            assert tier in TIER_CONFIG

    def test_rate_limits_ascending(self):
        limits = [TIER_CONFIG[t]["rate_limit_rpm"] for t in ["free", "basic", "pro", "enterprise"]]
        assert limits == sorted(limits)

    def test_free_is_zero_price(self):
        assert TIER_CONFIG["free"]["price_yuan"] == 0

    def test_enterprise_highest_rate(self):
        assert TIER_CONFIG["enterprise"]["rate_limit_rpm"] == max(
            v["rate_limit_rpm"] for v in TIER_CONFIG.values()
        )


# ── _email_exists ─────────────────────────────────────────────────────────────

class TestEmailExists:
    def _make_session(self, found: bool) -> AsyncMock:
        session = AsyncMock()
        result = MagicMock()
        result.first.return_value = (1,) if found else None
        session.execute = AsyncMock(return_value=result)
        return session

    def test_found(self):
        session = self._make_session(True)
        result = asyncio.run(_email_exists(session, "a@b.com"))
        assert result is True

    def test_not_found(self):
        session = self._make_session(False)
        result = asyncio.run(_email_exists(session, "x@y.com"))
        assert result is False


# ── register_developer endpoint ───────────────────────────────────────────────

class TestRegisterDeveloper:
    """通过直接调用 register_developer 函数测试（patch DB）"""

    def _make_db(self) -> AsyncMock:
        session = AsyncMock()
        result = MagicMock()
        result.first.return_value = None  # email 不存在
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        return session

    def test_returns_api_key_with_prefix(self):
        from src.api.open_platform import register_developer, RegisterDeveloperRequest
        db = self._make_db()
        req = RegisterDeveloperRequest(name="测试开发者", email="dev@test.com", tier="free")
        resp = asyncio.run(register_developer(req, db))
        assert resp.api_key.startswith("zlos_")

    def test_api_secret_not_empty(self):
        from src.api.open_platform import register_developer, RegisterDeveloperRequest
        db = self._make_db()
        req = RegisterDeveloperRequest(name="测试开发者", email="dev2@test.com", tier="basic")
        resp = asyncio.run(register_developer(req, db))
        assert len(resp.api_secret) > 20

    def test_rate_limit_matches_tier_free(self):
        from src.api.open_platform import register_developer, RegisterDeveloperRequest
        db = self._make_db()
        req = RegisterDeveloperRequest(name="Free Dev", email="free@test.com", tier="free")
        resp = asyncio.run(register_developer(req, db))
        assert resp.rate_limit_rpm == 60

    def test_rate_limit_matches_tier_pro(self):
        from src.api.open_platform import register_developer, RegisterDeveloperRequest
        db = self._make_db()
        req = RegisterDeveloperRequest(name="Pro Dev", email="pro@test.com", tier="pro")
        resp = asyncio.run(register_developer(req, db))
        assert resp.rate_limit_rpm == 1000

    def test_invalid_tier_defaults_to_free(self):
        from src.api.open_platform import register_developer, RegisterDeveloperRequest
        db = self._make_db()
        req = RegisterDeveloperRequest(name="Bad Tier", email="bad@test.com", tier="platinum")
        resp = asyncio.run(register_developer(req, db))
        assert resp.tier == "free"

    def test_duplicate_email_raises_409(self):
        from fastapi import HTTPException
        from src.api.open_platform import register_developer, RegisterDeveloperRequest
        # make email already exist
        db = AsyncMock()
        result = MagicMock()
        result.first.return_value = (1,)  # found
        db.execute = AsyncMock(return_value=result)
        req = RegisterDeveloperRequest(name="Dup", email="dup@test.com", tier="free")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(register_developer(req, db))
        assert exc_info.value.status_code == 409
