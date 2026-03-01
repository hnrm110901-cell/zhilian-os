"""
客户密钥管理模型（数据主权 — AES-256-GCM）

设计原则（Palantir 数据主权）：
  - 每个客户（门店/租户）持有独立的数据加密密钥（DEK）
  - DEK 由主密钥（KEK）加密保管，KEK 存储于环境变量/KMS
  - 密钥轮换：新 DEK 不删除旧 DEK，历史数据可用旧版解密
  - 全密钥操作审计日志

密钥层级：
  KEK（Key Encryption Key） ← 存储于 SECRET_KEY 环境变量
  ↓ 加密保管
  DEK（Data Encryption Key） ← 存储于此表
  ↓ 加密保护
  业务数据（WasteEvent.evidence / BOMItem.unit_cost / Order.details 等）
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, Enum, Index
from sqlalchemy.dialects.postgresql import UUID
from src.models.base import Base, TimestampMixin


class KeyStatus(str, enum.Enum):
    ACTIVE = "active"       # 当前加密主键
    ROTATING = "rotating"   # 轮换中
    RETIRED = "retired"     # 已停用（仅用于解密历史数据）
    REVOKED = "revoked"     # 已吊销（数据不可恢复）


class KeyAlgorithm(str, enum.Enum):
    AES_256_GCM = "AES-256-GCM"
    AES_256_CBC = "AES-256-CBC"  # 向后兼容


class CustomerKey(Base, TimestampMixin):
    """
    客户数据加密密钥（DEK）表

    每个门店（store_id）可拥有多版 DEK，当前激活的 is_active=True。
    DEK 明文（256 bit）经 KEK 包裹后以 encrypted_dek 存储。
    """
    __tablename__ = "customer_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)

    # 密钥版本（用于历史解密）
    key_version = Column(Integer, nullable=False, default=1)
    key_alias = Column(String(100))  # 可读别名，如 "v1-2026-03"

    # 算法
    algorithm = Column(
        Enum(KeyAlgorithm),
        nullable=False,
        default=KeyAlgorithm.AES_256_GCM,
    )

    # 加密后的 DEK（KEK 包裹，Base64 编码）
    encrypted_dek = Column(Text, nullable=False)

    # 元数据
    status = Column(Enum(KeyStatus), nullable=False, default=KeyStatus.ACTIVE)
    is_active = Column(Boolean, nullable=False, default=True)

    # 有效期
    activated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    rotated_at = Column(DateTime, nullable=True)
    rotated_by = Column(String(100))

    # 密钥用途（细粒度控制）
    purpose = Column(String(50), default="data_encryption")  # data_encryption / audit_log / export

    __table_args__ = (
        Index("idx_customer_key_store_active", "store_id", "is_active"),
        Index("idx_customer_key_store_version", "store_id", "key_version"),
    )

    def __repr__(self):
        return f"<CustomerKey(store={self.store_id}, v{self.key_version}, {self.status.value})>"


class EncryptedField(Base, TimestampMixin):
    """
    加密字段审计注册表

    记录哪些表/字段的哪些行被哪个密钥版本加密，用于批量重加密和审计。
    """
    __tablename__ = "encrypted_field_audit"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    key_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # FK to customer_keys.id

    table_name = Column(String(100), nullable=False)
    field_name = Column(String(100), nullable=False)
    record_id = Column(String(100), nullable=False)   # 被加密记录的主键

    encrypted_at = Column(DateTime, default=datetime.utcnow)
    algorithm = Column(String(20), default="AES-256-GCM")

    __table_args__ = (
        Index("idx_enc_audit_store_table", "store_id", "table_name"),
        Index("idx_enc_audit_key_id", "key_id"),
    )
