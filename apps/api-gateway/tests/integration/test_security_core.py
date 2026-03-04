"""
Tests for src/core/security.py — JWT auth + bcrypt password utilities.

Covers the paths missing from the broken tests/test_security.py:
  - create_refresh_token / decode_refresh_token (never tested)
  - Cross-type rejection: refresh token → decode_access_token → 401
  - Cross-type rejection: access token  → decode_refresh_token → 401
  - bcrypt 72-byte truncation behaviour
  - Expired-token 401 for both token types

All tests inject a deterministic SECRET_KEY via monkeypatch so no
real env-vars are required.
"""
import sys
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

# Pre-stub src.core.config so security.py can be imported without env-vars.
if "src.core.config" not in sys.modules:
    _cfg_mod = MagicMock()
    _cfg_mod.settings = MagicMock()
    sys.modules["src.core.config"] = _cfg_mod

from src.core.security import (  # noqa: E402
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)

_TEST_SECRET = "zhilian-os-test-secret-key-for-jwt!!"


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch):
    """Give security.py a deterministic SECRET_KEY for every test."""
    import src.core.security as _sec
    monkeypatch.setattr(_sec, "settings", MagicMock(SECRET_KEY=_TEST_SECRET))


# ===========================================================================
# Password hashing & verification
# ===========================================================================

class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        pw = "correct-horse-battery-staple"
        assert verify_password(pw, get_password_hash(pw)) is True

    def test_wrong_password_returns_false(self):
        hashed = get_password_hash("original")
        assert verify_password("different", hashed) is False

    def test_bcrypt_72_byte_truncation(self):
        """Passwords that differ only after byte 72 must match each other."""
        base = "A" * 72
        long_a = base + "X"
        long_b = base + "Y"
        hashed = get_password_hash(long_a)
        # long_b differs only after position 72 → truncated to same prefix
        assert verify_password(long_b, hashed) is True

    def test_hash_format_is_bcrypt(self):
        hashed = get_password_hash("any-password")
        assert hashed.startswith("$2b$")


class TestGetPasswordHash:
    def test_round_trip(self):
        pw = "test-password-123"
        assert verify_password(pw, get_password_hash(pw)) is True

    def test_same_password_different_hashes(self):
        """Each call uses a fresh salt."""
        pw = "same-password"
        assert get_password_hash(pw) != get_password_hash(pw)

    def test_hash_is_string(self):
        assert isinstance(get_password_hash("pw"), str)


# ===========================================================================
# create_access_token
# ===========================================================================

class TestCreateAccessToken:
    def test_returns_nonempty_string(self):
        token = create_access_token({"sub": "u1"})
        assert isinstance(token, str) and len(token) > 0

    def test_type_claim_is_access(self):
        token = create_access_token({"sub": "u1"})
        payload = jwt.decode(token, _TEST_SECRET, algorithms=[ALGORITHM])
        assert payload["type"] == "access"

    def test_payload_data_preserved(self):
        token = create_access_token({"sub": "u42", "role": "manager"})
        payload = jwt.decode(token, _TEST_SECRET, algorithms=[ALGORITHM])
        assert payload["sub"] == "u42"
        assert payload["role"] == "manager"

    def test_custom_expires_delta_reflected(self):
        import time
        now = int(time.time())
        delta = timedelta(minutes=5)
        token = create_access_token({"sub": "u1"}, expires_delta=delta)
        payload = jwt.decode(token, _TEST_SECRET, algorithms=[ALGORITHM])
        # exp should be within ~5 minutes of now
        assert now + 270 < payload["exp"] < now + 330


# ===========================================================================
# create_refresh_token
# ===========================================================================

class TestCreateRefreshToken:
    def test_returns_nonempty_string(self):
        token = create_refresh_token({"sub": "u1"})
        assert isinstance(token, str) and len(token) > 0

    def test_type_claim_is_refresh(self):
        token = create_refresh_token({"sub": "u1"})
        payload = jwt.decode(token, _TEST_SECRET, algorithms=[ALGORITHM])
        assert payload["type"] == "refresh"

    def test_custom_expires_delta(self):
        import time
        now = int(time.time())
        delta = timedelta(days=1)
        token = create_refresh_token({"sub": "u1"}, expires_delta=delta)
        payload = jwt.decode(token, _TEST_SECRET, algorithms=[ALGORITHM])
        assert now + 86100 < payload["exp"] < now + 86500

    def test_differs_from_access_token(self):
        data = {"sub": "u1"}
        assert create_access_token(data) != create_refresh_token(data)


# ===========================================================================
# decode_access_token
# ===========================================================================

class TestDecodeAccessToken:
    def test_valid_access_token_returns_payload(self):
        token = create_access_token({"sub": "u99", "store_id": "S1"})
        payload = decode_access_token(token)
        assert payload["sub"] == "u99"
        assert payload["store_id"] == "S1"
        assert "exp" in payload

    def test_refresh_token_rejected_as_access(self):
        """Using a refresh token where an access token is expected → 401."""
        token = create_refresh_token({"sub": "u1"})
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401
        assert "令牌类型" in exc_info.value.detail

    def test_garbage_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        token = create_access_token({"sub": "u1"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401

    def test_tampered_signature_raises_401(self):
        token = create_access_token({"sub": "u1"})
        # Flip the last character of the signature
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered)
        assert exc_info.value.status_code == 401


# ===========================================================================
# decode_refresh_token
# ===========================================================================

class TestDecodeRefreshToken:
    def test_valid_refresh_token_returns_payload(self):
        token = create_refresh_token({"sub": "u77"})
        payload = decode_refresh_token(token)
        assert payload["sub"] == "u77"
        assert "exp" in payload

    def test_access_token_rejected_as_refresh(self):
        """Using an access token where a refresh token is expected → 401."""
        token = create_access_token({"sub": "u1"})
        with pytest.raises(HTTPException) as exc_info:
            decode_refresh_token(token)
        assert exc_info.value.status_code == 401
        assert "令牌类型" in exc_info.value.detail

    def test_garbage_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_refresh_token("garbage.jwt.here")
        assert exc_info.value.status_code == 401

    def test_expired_refresh_token_raises_401(self):
        token = create_refresh_token({"sub": "u1"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(HTTPException) as exc_info:
            decode_refresh_token(token)
        assert exc_info.value.status_code == 401
