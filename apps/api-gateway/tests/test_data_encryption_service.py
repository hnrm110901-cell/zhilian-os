"""
数据加密服务单元测试（AES-256-GCM）

覆盖：
  - encrypt/decrypt 往返（roundtrip）
  - 相同明文每次生成不同密文（随机 IV）
  - encrypt_json / decrypt_json
  - _wrap_key / _unwrap_key KEK 包裹/解包
  - 密文格式：version_byte(1) + iv(12) + ciphertext+tag
  - create_key（mock DB）
  - rotate_key：旧密钥退役，新密钥激活
  - revoke_key：REVOKED 状态
  - register_encrypted_field 写入审计记录
  - get_encryption_coverage 汇总统计
"""
import base64
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.customer_key import CustomerKey, KeyAlgorithm, KeyStatus
from src.services.data_encryption_service import DataEncryptionService


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_key(version: int = 1, store_id: str = "store-001") -> CustomerKey:
    svc = DataEncryptionService(AsyncMock())
    raw_dek = b"\x00" * 32  # deterministic DEK for testing
    encrypted_dek = svc._wrap_key(raw_dek)

    key = CustomerKey()
    key.id = uuid.uuid4()
    key.store_id = store_id
    key.key_version = version
    key.key_alias = f"v{version}-202602"
    key.algorithm = KeyAlgorithm.AES_256_GCM
    key.encrypted_dek = encrypted_dek
    key.status = KeyStatus.ACTIVE
    key.is_active = True
    key.purpose = "data_encryption"
    return key


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ── KEK wrap / unwrap ─────────────────────────────────────────────────────────

class TestKeyWrapping:
    def test_wrap_and_unwrap_roundtrip(self):
        svc = DataEncryptionService(AsyncMock())
        raw_dek = b"A" * 32
        wrapped = svc._wrap_key(raw_dek)
        unwrapped = svc._unwrap_key(wrapped)
        assert unwrapped == raw_dek

    def test_different_wraps_for_same_key(self):
        """每次包裹使用随机 IV，密文应不同"""
        svc = DataEncryptionService(AsyncMock())
        raw_dek = b"B" * 32
        wrapped1 = svc._wrap_key(raw_dek)
        wrapped2 = svc._wrap_key(raw_dek)
        assert wrapped1 != wrapped2  # random IV → different ciphertext

    def test_wrapped_key_is_base64(self):
        svc = DataEncryptionService(AsyncMock())
        raw_dek = b"C" * 32
        wrapped = svc._wrap_key(raw_dek)
        decoded = base64.b64decode(wrapped)
        # iv(12) + ciphertext(32) + tag(16) = 60 bytes
        assert len(decoded) == 60


# ── encrypt / decrypt ─────────────────────────────────────────────────────────

class TestEncryptDecrypt:
    def test_roundtrip_ascii(self):
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        plaintext = "Hello, 智链OS!"
        ciphertext = svc.encrypt(plaintext, key)
        result = svc.decrypt(ciphertext, key)
        assert result == plaintext

    def test_roundtrip_unicode(self):
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        plaintext = "配方：猪肉100g + 老抽15ml + 料酒10ml"
        ciphertext = svc.encrypt(plaintext, key)
        assert svc.decrypt(ciphertext, key) == plaintext

    def test_roundtrip_empty_string(self):
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        ciphertext = svc.encrypt("", key)
        assert svc.decrypt(ciphertext, key) == ""

    def test_different_ciphertexts_same_plaintext(self):
        """同一明文两次加密，密文应不同（随机 IV）"""
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        c1 = svc.encrypt("secret", key)
        c2 = svc.encrypt("secret", key)
        assert c1 != c2

    def test_ciphertext_is_base64(self):
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        ciphertext = svc.encrypt("test data", key)
        # Should be valid base64
        decoded = base64.b64decode(ciphertext)
        assert len(decoded) >= 13 + 16  # version(1) + iv(12) + tag(16)

    def test_ciphertext_format_version_byte(self):
        """密文第 0 字节是版本字节（key_version & 0xFF）"""
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key(version=3)
        ciphertext = svc.encrypt("check", key)
        raw = base64.b64decode(ciphertext)
        assert raw[0] == (3 & 0xFF)

    def test_wrong_key_raises(self):
        """用错误密钥解密应抛出异常"""
        db = _mock_db()
        svc = DataEncryptionService(db)
        key1 = _make_key(version=1)
        key2 = _make_key(version=2)  # different DEK (same 0x00*32 in this fixture, but different wrapped)
        # Create a genuinely different key with random raw_dek
        import os
        raw_dek2 = os.urandom(32)
        key2.encrypted_dek = svc._wrap_key(raw_dek2)

        ciphertext = svc.encrypt("secret data", key1)
        with pytest.raises(Exception):
            svc.decrypt(ciphertext, key2)


# ── encrypt_json / decrypt_json ───────────────────────────────────────────────

class TestEncryptJson:
    def test_roundtrip_simple_dict(self):
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        data = {"ingredient": "虾", "qty": 200, "unit": "g", "notes": "新鲜度A级"}
        ciphertext = svc.encrypt_json(data, key)
        result = svc.decrypt_json(ciphertext, key)
        assert result == data

    def test_roundtrip_nested_dict(self):
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        data = {"evidence": {"step1": 0.9, "step2": 0.8}, "scores": [1, 2, 3]}
        ciphertext = svc.encrypt_json(data, key)
        assert svc.decrypt_json(ciphertext, key) == data

    def test_roundtrip_empty_dict(self):
        db = _mock_db()
        svc = DataEncryptionService(db)
        key = _make_key()
        ciphertext = svc.encrypt_json({}, key)
        assert svc.decrypt_json(ciphertext, key) == {}


# ── create_key ────────────────────────────────────────────────────────────────

class TestCreateKey:
    @pytest.mark.asyncio
    async def test_create_key_basic(self):
        db = _mock_db()
        svc = DataEncryptionService(db)

        # _get_max_version → 0 (no existing keys)
        scalar_result = MagicMock()
        scalar_result.scalar = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        key = await svc.create_key(store_id="store-XYZ", purpose="data_encryption")

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, CustomerKey)
        assert added.store_id == "store-XYZ"
        assert added.key_version == 1
        assert added.is_active is True
        assert added.status == KeyStatus.ACTIVE
        assert added.algorithm == KeyAlgorithm.AES_256_GCM

    @pytest.mark.asyncio
    async def test_create_key_increments_version(self):
        db = _mock_db()
        svc = DataEncryptionService(db)

        # Simulate existing version 3
        scalar_result = MagicMock()
        scalar_result.scalar = MagicMock(return_value=3)
        db.execute = AsyncMock(return_value=scalar_result)

        key = await svc.create_key("store-001")
        added = db.add.call_args[0][0]
        assert added.key_version == 4

    @pytest.mark.asyncio
    async def test_create_key_encrypted_dek_is_valid(self):
        """DEK 必须能被 KEK 解包"""
        db = _mock_db()
        svc = DataEncryptionService(db)

        scalar_result = MagicMock()
        scalar_result.scalar = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        await svc.create_key("store-001")
        added = db.add.call_args[0][0]

        # Should not raise
        raw_dek = svc._unwrap_key(added.encrypted_dek)
        assert len(raw_dek) == 32


# ── rotate_key ────────────────────────────────────────────────────────────────

class TestRotateKey:
    @pytest.mark.asyncio
    async def test_rotate_retires_old_key(self):
        db = _mock_db()
        svc = DataEncryptionService(db)

        old_key = _make_key(version=1)

        call_count = [0]

        async def side_effect(*args, **kwargs):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                # _get_active_key for rotate
                result.scalar_one_or_none = MagicMock(return_value=old_key)
            elif call_count[0] == 2:
                # _get_max_version during create_key
                result.scalar = MagicMock(return_value=1)
            else:
                result.scalar_one_or_none = MagicMock(return_value=None)
                result.scalar = MagicMock(return_value=None)
            return result

        db.execute = side_effect

        old_k, new_k = await svc.rotate_key("store-001", rotated_by="admin")

        assert old_k.is_active is False
        assert old_k.status == KeyStatus.RETIRED
        assert old_k.rotated_by == "admin"

    @pytest.mark.asyncio
    async def test_rotate_raises_if_no_active_key(self):
        db = _mock_db()
        svc = DataEncryptionService(db)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        with pytest.raises(ValueError, match="无激活密钥"):
            await svc.rotate_key("store-XYZ", rotated_by="admin")


# ── revoke_key ────────────────────────────────────────────────────────────────

class TestRevokeKey:
    @pytest.mark.asyncio
    async def test_revoke_existing_key(self):
        db = _mock_db()
        svc = DataEncryptionService(db)

        key = _make_key()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=key)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.revoke_key(str(key.id), revoked_by="security-team")

        assert result is True
        assert key.status == KeyStatus.REVOKED
        assert key.is_active is False
        assert key.rotated_by == "security-team"

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key(self):
        db = _mock_db()
        svc = DataEncryptionService(db)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar_result)

        result = await svc.revoke_key(str(uuid.uuid4()), revoked_by="admin")
        assert result is False


# ── register_encrypted_field ──────────────────────────────────────────────────

class TestRegisterEncryptedField:
    @pytest.mark.asyncio
    async def test_register_adds_audit_record(self):
        from src.models.customer_key import EncryptedField
        db = _mock_db()
        svc = DataEncryptionService(db)

        key = _make_key()
        await svc.register_encrypted_field(
            store_id="store-001",
            key=key,
            table_name="bom_items",
            field_name="unit_cost",
            record_id="rec-123",
        )

        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, EncryptedField)
        assert added.table_name == "bom_items"
        assert added.field_name == "unit_cost"
        assert added.record_id == "rec-123"
        assert added.algorithm == "AES-256-GCM"


# ── get_encryption_coverage ───────────────────────────────────────────────────

class TestGetEncryptionCoverage:
    @pytest.mark.asyncio
    async def test_empty_coverage(self):
        db = _mock_db()
        svc = DataEncryptionService(db)

        scalars_result = MagicMock()
        scalars_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=scalars_result)

        coverage = await svc.get_encryption_coverage("store-001")
        assert coverage["total_records"] == 0
        assert coverage["coverage_pct"] == 0.0
        assert coverage["tables"] == {}

    @pytest.mark.asyncio
    async def test_coverage_with_records(self):
        from src.models.customer_key import EncryptedField
        db = _mock_db()
        svc = DataEncryptionService(db)

        def _make_ef(table: str, field: str) -> EncryptedField:
            ef = EncryptedField()
            ef.id = uuid.uuid4()
            ef.store_id = "store-001"
            ef.table_name = table
            ef.field_name = field
            ef.record_id = str(uuid.uuid4())
            ef.algorithm = "AES-256-GCM"
            return ef

        records = [
            _make_ef("bom_items", "unit_cost"),
            _make_ef("bom_items", "unit_cost"),
            _make_ef("waste_events", "evidence"),
        ]

        scalars_result = MagicMock()
        scalars_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=records)))
        db.execute = AsyncMock(return_value=scalars_result)

        coverage = await svc.get_encryption_coverage("store-001")
        assert coverage["total_records"] == 3
        assert coverage["coverage_pct"] == 100.0
        assert "bom_items.unit_cost" in coverage["tables"]
        assert coverage["tables"]["bom_items.unit_cost"]["count"] == 2
        assert coverage["tables"]["waste_events.evidence"]["count"] == 1
