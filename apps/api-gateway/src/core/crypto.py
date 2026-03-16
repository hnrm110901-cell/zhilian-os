"""
列级加密工具 — AES-256-GCM
用于加密身份证号、银行卡号等PII字段
密钥从环境变量 FIELD_ENCRYPTION_KEY 读取（32字节 base64）

加密输出格式: "ENC:" + base64(nonce_12bytes + ciphertext + tag_16bytes)
未加密的历史数据（不以 "ENC:" 开头）解密时原样返回，兼容渐进式迁移。

合规依据:
  - 《个人信息保护法》第五十一条 — 加密等安全技术措施
  - PCI-DSS Requirement 3.4 — 存储时不可读
"""

import base64
import os
from typing import Optional

import structlog

logger = structlog.get_logger()

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False
    logger.warning(
        "cryptography 包未安装，字段加密功能不可用，敏感数据将以明文存储",
        hint="pip install cryptography>=42.0.0",
    )


class FieldCrypto:
    """字段级加密/解密（AES-256-GCM）

    使用方式:
        from src.core.crypto import field_crypto
        encrypted = field_crypto.encrypt("110101199001011234")
        plain = field_crypto.decrypt(encrypted)
        masked = field_crypto.mask("110101199001011234", "id_card")
    """

    _PREFIX = "ENC:"

    def __init__(self, key: Optional[bytes] = None):
        if key is None:
            key_b64 = os.environ.get("FIELD_ENCRYPTION_KEY", "")
            if not key_b64:
                logger.warning(
                    "FIELD_ENCRYPTION_KEY 未设置，字段加密降级为明文",
                    env="development",
                )
                self._key = None
                return
            try:
                key = base64.b64decode(key_b64)
            except Exception as exc:
                raise ValueError("FIELD_ENCRYPTION_KEY base64 解码失败") from exc
        if len(key) != 32:
            raise ValueError(
                f"FIELD_ENCRYPTION_KEY 必须为 32 字节（当前 {len(key)} 字节），"
                '请使用: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"'
            )
        if not _HAS_CRYPTOGRAPHY:
            raise RuntimeError(
                "提供了 FIELD_ENCRYPTION_KEY 但 cryptography 包未安装，" "无法启用加密: pip install cryptography>=42.0.0"
            )
        self._key = key

    # ── 加密 ──────────────────────────────────────────────

    def encrypt(self, plaintext: str) -> str:
        """加密明文 → 返回 'ENC:' + base64(nonce + ciphertext + tag)

        - key 未配置或 plaintext 为空时原样返回
        - 已加密的值（以 ENC: 开头）不会重复加密
        """
        if not self._key or not plaintext:
            return plaintext or ""
        if plaintext.startswith(self._PREFIX):
            return plaintext  # 已加密，幂等
        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return self._PREFIX + base64.b64encode(nonce + ct).decode("ascii")

    # ── 解密 ──────────────────────────────────────────────

    def decrypt(self, ciphertext: str) -> str:
        """解密 → 明文

        - key 未配置时原样返回
        - 未加密的历史数据（不以 ENC: 开头）原样返回
        """
        if not self._key or not ciphertext:
            return ciphertext or ""
        if not ciphertext.startswith(self._PREFIX):
            return ciphertext  # 历史明文数据，原样返回
        try:
            raw = base64.b64decode(ciphertext[len(self._PREFIX) :])
        except Exception:
            logger.error("字段解密 base64 解码失败", value_prefix=ciphertext[:20])
            return ciphertext
        if len(raw) < 12 + 16:
            logger.error("字段解密数据长度异常", length=len(raw))
            return ciphertext
        nonce = raw[:12]
        ct = raw[12:]
        try:
            aesgcm = AESGCM(self._key)
            return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
        except Exception:
            logger.error("字段解密失败（密钥不匹配或数据损坏）")
            return ciphertext

    # ── 脱敏 ──────────────────────────────────────────────

    def mask(self, plaintext: str, field_type: str = "id_card") -> str:
        """脱敏显示（用于列表页等无需完整数据的场景）

        field_type:
          id_card      → 110101****1234
          bank_account → 6222****5678
          phone        → 138****5678
        """
        if not plaintext:
            return ""
        if field_type == "id_card" and len(plaintext) >= 15:
            return plaintext[:6] + "****" + plaintext[-4:]
        elif field_type == "bank_account" and len(plaintext) >= 8:
            return plaintext[:4] + "****" + plaintext[-4:]
        elif field_type == "phone" and len(plaintext) >= 7:
            return plaintext[:3] + "****" + plaintext[-4:]
        return plaintext[:2] + "****"

    # ── 工具方法 ──────────────────────────────────────────

    def is_encrypted(self, value: str) -> bool:
        """判断值是否已加密"""
        return bool(value and value.startswith(self._PREFIX))

    @property
    def enabled(self) -> bool:
        """加密功能是否启用"""
        return self._key is not None


# 全局单例 — 启动时初始化一次
field_crypto = FieldCrypto()
