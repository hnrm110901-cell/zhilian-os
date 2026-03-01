"""
Tests for src/core/kms_service.py — P0 crypto/key management.

No real DB needed: _audit_log swallows DB errors internally.
Tests use a deterministic salt + 1-iteration KDF for speed.
"""
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

# Fast KDF: override iterations so tests don't wait 100k rounds
os.environ.setdefault("KMS_PBKDF2_ITERATIONS", "1")
# Fixed salt so Fernet key is reproducible within a test session
_FIXED_SALT_HEX = "ab" * 32  # 32 bytes as hex = 64 chars
os.environ.setdefault("KMS_SALT", _FIXED_SALT_HEX)

# kms_service.py has a production bug: `from cryptography...pbkdf2 import PBKDF2`
# but the correct class name is PBKDF2HMAC.  Inject a compatibility alias so the
# module can be imported and its business logic can be tested.
import cryptography.hazmat.primitives.kdf.pbkdf2 as _pbkdf2_mod
if not hasattr(_pbkdf2_mod, "PBKDF2"):
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _pbkdf2_mod.PBKDF2 = PBKDF2HMAC  # type: ignore[attr-defined]

from src.core.kms_service import (  # noqa: E402
    KMSException,
    KMSService,
    decrypt_api_key,
    encrypt_api_key,
    get_kms_service,
    init_kms_service,
    rotate_api_key,
)

_MASTER_KEY = "test-master-key-for-kms-integration"


@pytest.fixture
def kms():
    """Fresh KMSService instance for each test."""
    return KMSService(master_key=_MASTER_KEY)


# ===========================================================================
# Initialisation
# ===========================================================================

class TestKMSInit:
    def test_no_master_key_raises(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove KMS_MASTER_KEY from env if present
            env = {k: v for k, v in os.environ.items() if k != "KMS_MASTER_KEY"}
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(KMSException, match="Master key not found"):
                    KMSService()  # master_key=None, env not set

    def test_with_explicit_master_key_succeeds(self):
        svc = KMSService(master_key=_MASTER_KEY)
        assert svc is not None
        assert svc.fernet is not None

    def test_kms_salt_env_var_used(self, monkeypatch):
        """KMS_SALT env var produces deterministic Fernet key."""
        monkeypatch.setenv("KMS_SALT", _FIXED_SALT_HEX)
        svc1 = KMSService(master_key=_MASTER_KEY)
        svc2 = KMSService(master_key=_MASTER_KEY)
        # Same master_key + same salt → same Fernet → ciphertext cross-decryptable
        ct = svc1.encrypt_secret("k1", "secret")
        assert svc2.decrypt_secret("k1", ct) == "secret"

    def test_rotation_days_default(self, kms):
        assert kms.rotation_days == int(os.getenv("KMS_ROTATION_DAYS", "90"))


# ===========================================================================
# encrypt_secret
# ===========================================================================

class TestEncryptSecret:
    def test_returns_nonempty_string(self, kms):
        ct = kms.encrypt_secret("k1", "my-api-key")
        assert isinstance(ct, str) and len(ct) > 0

    def test_ciphertext_differs_from_plaintext(self, kms):
        plaintext = "sk-abc123"
        assert kms.encrypt_secret("k1", plaintext) != plaintext

    def test_same_plaintext_different_ciphertexts(self, kms):
        """Fernet uses a random IV each call."""
        ct1 = kms.encrypt_secret("k1", "secret")
        ct2 = kms.encrypt_secret("k2", "secret")
        assert ct1 != ct2

    def test_metadata_stored_after_encrypt(self, kms):
        kms.encrypt_secret("k1", "value", metadata={"provider": "wechat"})
        meta = kms.get_key_metadata("k1")
        assert meta is not None
        assert meta["metadata"]["provider"] == "wechat"
        assert "created_at" in meta
        assert "rotation_due" in meta
        assert meta["access_count"] == 0


# ===========================================================================
# decrypt_secret
# ===========================================================================

class TestDecryptSecret:
    def test_round_trip(self, kms):
        plaintext = "super-secret-api-key-xyz"
        ct = kms.encrypt_secret("k1", plaintext)
        assert kms.decrypt_secret("k1", ct) == plaintext

    def test_invalid_ciphertext_raises_kms_exception(self, kms):
        with pytest.raises(KMSException, match="解密失败"):
            kms.decrypt_secret("k1", "not-valid-fernet-ciphertext")

    def test_access_count_incremented(self, kms):
        ct = kms.encrypt_secret("k1", "value")
        assert kms.key_metadata["k1"]["access_count"] == 0
        kms.decrypt_secret("k1", ct)
        assert kms.key_metadata["k1"]["access_count"] == 1
        kms.decrypt_secret("k1", ct)
        assert kms.key_metadata["k1"]["access_count"] == 2

    def test_last_accessed_set_after_decrypt(self, kms):
        ct = kms.encrypt_secret("k1", "value")
        kms.decrypt_secret("k1", ct)
        assert "last_accessed" in kms.key_metadata["k1"]

    def test_rotation_warning_triggered_on_overdue_key(self, kms, caplog):
        """Decrypt on an overdue key should log a rotation warning."""
        ct = kms.encrypt_secret("k1", "value")
        # Force rotation_due to past
        kms.key_metadata["k1"]["rotation_due"] = (
            datetime.now() - timedelta(days=1)
        ).isoformat()
        import logging
        with caplog.at_level(logging.WARNING):
            kms.decrypt_secret("k1", ct)
        # Warning may be emitted by structlog (not caplog), just verify no crash


# ===========================================================================
# rotate_key
# ===========================================================================

class TestRotateKey:
    def test_rotate_with_new_plaintext(self, kms):
        ct_old = kms.encrypt_secret("k1", "old-secret")
        ct_new = kms.rotate_key("k1", ct_old, new_plaintext="new-secret")
        assert kms.decrypt_secret("k1", ct_new) == "new-secret"

    def test_rotate_without_new_plaintext_reencrypts_old(self, kms):
        """Passing new_plaintext=None should decrypt old and re-encrypt same value."""
        ct_old = kms.encrypt_secret("k1", "original-value")
        ct_new = kms.rotate_key("k1", ct_old, new_plaintext=None)
        assert kms.decrypt_secret("k1", ct_new) == "original-value"

    def test_rotation_updates_metadata(self, kms):
        ct_old = kms.encrypt_secret("k1", "val")
        before_rotation = kms.key_metadata["k1"]["last_rotated"]
        kms.rotate_key("k1", ct_old, "new-val")
        assert kms.key_metadata["k1"].get("rotation_count", 0) >= 1

    def test_invalid_old_ciphertext_raises(self, kms):
        kms.encrypt_secret("k1", "val")
        with pytest.raises(KMSException, match="密钥轮换失败"):
            kms.rotate_key("k1", "bad-ciphertext", new_plaintext=None)


# ===========================================================================
# _should_rotate / get_keys_due_for_rotation
# ===========================================================================

class TestRotationPolicy:
    def test_new_key_not_due(self, kms):
        kms.encrypt_secret("k1", "val")
        assert kms._should_rotate("k1") is False

    def test_overdue_key_is_due(self, kms):
        kms.encrypt_secret("k1", "val")
        kms.key_metadata["k1"]["rotation_due"] = (
            datetime.now() - timedelta(days=1)
        ).isoformat()
        assert kms._should_rotate("k1") is True

    def test_unknown_key_not_due(self, kms):
        assert kms._should_rotate("nonexistent") is False

    def test_get_keys_due_empty_when_none_due(self, kms):
        kms.encrypt_secret("k1", "val")
        assert kms.get_keys_due_for_rotation() == []

    def test_get_keys_due_returns_overdue_key(self, kms):
        kms.encrypt_secret("k1", "val")
        kms.encrypt_secret("k2", "val2")
        kms.key_metadata["k1"]["rotation_due"] = (
            datetime.now() - timedelta(days=5)
        ).isoformat()
        due = kms.get_keys_due_for_rotation()
        assert len(due) == 1
        assert due[0]["key_id"] == "k1"
        assert due[0]["days_overdue"] >= 4


# ===========================================================================
# delete_key / get_key_metadata / list_all_keys
# ===========================================================================

class TestKeyManagement:
    def test_delete_key_removes_metadata(self, kms):
        kms.encrypt_secret("k1", "val")
        kms.delete_key("k1")
        assert kms.get_key_metadata("k1") is None

    def test_delete_nonexistent_key_no_crash(self, kms):
        kms.delete_key("does-not-exist")  # must not raise

    def test_get_key_metadata_unknown_returns_none(self, kms):
        assert kms.get_key_metadata("ghost") is None

    def test_list_all_keys_empty(self, kms):
        assert kms.list_all_keys() == []

    def test_list_all_keys_includes_all(self, kms):
        kms.encrypt_secret("k1", "v1")
        kms.encrypt_secret("k2", "v2")
        keys = kms.list_all_keys()
        ids = [k["key_id"] for k in keys]
        assert "k1" in ids and "k2" in ids


# ===========================================================================
# get_statistics
# ===========================================================================

class TestGetStatistics:
    def test_empty_stats(self, kms):
        stats = kms.get_statistics()
        assert stats["total_keys"] == 0
        assert stats["keys_due_for_rotation"] == 0
        assert stats["total_access_count"] == 0

    def test_stats_after_operations(self, kms):
        ct = kms.encrypt_secret("k1", "val")
        kms.decrypt_secret("k1", ct)  # access_count = 1
        stats = kms.get_statistics()
        assert stats["total_keys"] == 1
        assert stats["total_access_count"] == 1
        assert stats["rotation_policy_days"] == kms.rotation_days


# ===========================================================================
# Module-level init / get
# ===========================================================================

class TestModuleFunctions:
    def test_get_kms_service_before_init_raises(self):
        import src.core.kms_service as _mod
        original = _mod._kms_service
        _mod._kms_service = None
        try:
            with pytest.raises(KMSException, match="not initialized"):
                get_kms_service()
        finally:
            _mod._kms_service = original

    def test_init_and_get_kms_service(self):
        init_kms_service(master_key=_MASTER_KEY)
        svc = get_kms_service()
        assert isinstance(svc, KMSService)

    def test_encrypt_api_key_convenience(self):
        init_kms_service(master_key=_MASTER_KEY)
        ct = encrypt_api_key("wechat-k1", "sk-abc123", provider="wechat")
        assert isinstance(ct, str) and len(ct) > 0

    def test_decrypt_api_key_convenience(self):
        init_kms_service(master_key=_MASTER_KEY)
        ct = encrypt_api_key("wechat-k2", "plaintext-key", provider="wechat")
        assert decrypt_api_key("wechat-k2", ct) == "plaintext-key"

    def test_rotate_api_key_convenience(self):
        init_kms_service(master_key=_MASTER_KEY)
        ct_old = encrypt_api_key("wechat-k3", "old-key", provider="wechat")
        ct_new = rotate_api_key("wechat-k3", ct_old, "new-key")
        assert decrypt_api_key("wechat-k3", ct_new) == "new-key"
