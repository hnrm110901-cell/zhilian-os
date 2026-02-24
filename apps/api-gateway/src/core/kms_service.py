"""
KMS密钥管理服务
Key Management Service

核心功能：
1. 密钥加密存储
2. 运行时动态解密
3. 密钥轮换机制
4. 审计日志记录

安全等级：P0 CRITICAL

防止场景：
- 数据库被拖库导致API密钥泄露
- 第三方平台密钥明文存储
- 密钥长期不轮换
"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import base64
import os
import json
import logging
import secrets

logger = logging.getLogger(__name__)


class KMSException(Exception):
    """KMS异常"""
    pass


class KMSService:
    """密钥管理服务"""

    def __init__(self, master_key: Optional[str] = None):
        """
        初始化KMS服务

        Args:
            master_key: 主密钥（从环境变量或安全存储获取）
        """
        # 从环境变量获取主密钥
        self.master_key = master_key or os.getenv("KMS_MASTER_KEY")

        if not self.master_key:
            raise KMSException(
                "Master key not found. Set KMS_MASTER_KEY environment variable."
            )

        # 生成Fernet密钥
        self.fernet = self._generate_fernet_key(self.master_key)

        # 密钥元数据存储
        self.key_metadata = {}

        # 密钥轮换策略（默认90天）
        self.rotation_days = int(os.getenv("KMS_ROTATION_DAYS", "90"))

        logger.info("KMS Service initialized")

    def _generate_fernet_key(self, master_key: str) -> Fernet:
        """
        从主密钥生成Fernet密钥

        Args:
            master_key: 主密钥

        Returns:
            Fernet实例
        """
        # 从环境变量读取盐值；首次启动时随机生成并写回（仅限开发环境）
        salt_hex = os.getenv("KMS_SALT")
        if not salt_hex:
            # 生产环境必须预先设置 KMS_SALT 环境变量
            # 此处仅作为本地开发的安全回退，不应在生产中触发
            logger.warning(
                "KMS_SALT not set. Generating ephemeral salt. "
                "Set KMS_SALT env var in production."
            )
            salt = secrets.token_bytes(32)
        else:
            salt = bytes.fromhex(salt_hex)

        # 使用PBKDF2派生密钥
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=int(os.getenv("KMS_PBKDF2_ITERATIONS", "100000")),
        )

        key = base64.urlsafe_b64encode(
            kdf.derive(master_key.encode())
        )

        return Fernet(key)

    def encrypt_secret(
        self,
        key_id: str,
        plaintext: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        加密密钥

        Args:
            key_id: 密钥ID（唯一标识）
            plaintext: 明文密钥
            metadata: 元数据（用途、所有者等）

        Returns:
            加密后的密文
        """
        try:
            # 加密
            ciphertext = self.fernet.encrypt(plaintext.encode())

            # 存储元数据
            self.key_metadata[key_id] = {
                "created_at": datetime.now().isoformat(),
                "last_rotated": datetime.now().isoformat(),
                "rotation_due": (
                    datetime.now() + timedelta(days=self.rotation_days)
                ).isoformat(),
                "access_count": 0,
                "metadata": metadata or {}
            }

            logger.info(f"Encrypted secret: {key_id}")

            # 审计日志
            self._audit_log("encrypt", key_id, metadata)

            return ciphertext.decode()

        except Exception as e:
            logger.error(f"Encryption failed for {key_id}: {e}")
            raise KMSException(f"加密失败: {e}")

    def decrypt_secret(self, key_id: str, ciphertext: str) -> str:
        """
        解密密钥（运行时）

        Args:
            key_id: 密钥ID
            ciphertext: 密文

        Returns:
            明文密钥
        """
        try:
            # 检查密钥是否需要轮换
            if self._should_rotate(key_id):
                logger.warning(f"Key {key_id} is due for rotation")

            # 解密
            plaintext = self.fernet.decrypt(ciphertext.encode())

            # 更新访问计数
            if key_id in self.key_metadata:
                self.key_metadata[key_id]["access_count"] += 1
                self.key_metadata[key_id]["last_accessed"] = (
                    datetime.now().isoformat()
                )

            logger.debug(f"Decrypted secret: {key_id}")

            # 审计日志
            self._audit_log("decrypt", key_id)

            return plaintext.decode()

        except Exception as e:
            logger.error(f"Decryption failed for {key_id}: {e}")
            raise KMSException(f"解密失败: {e}")

    def rotate_key(
        self,
        key_id: str,
        old_ciphertext: str,
        new_plaintext: Optional[str] = None
    ) -> str:
        """
        密钥轮换

        Args:
            key_id: 密钥ID
            old_ciphertext: 旧密文
            new_plaintext: 新明文（如果为None，则重新加密旧密钥）

        Returns:
            新密文
        """
        try:
            # 如果没有提供新密钥，解密旧密钥
            if new_plaintext is None:
                new_plaintext = self.decrypt_secret(key_id, old_ciphertext)

            # 重新加密
            new_ciphertext = self.fernet.encrypt(new_plaintext.encode())

            # 更新元数据
            if key_id in self.key_metadata:
                self.key_metadata[key_id]["last_rotated"] = (
                    datetime.now().isoformat()
                )
                self.key_metadata[key_id]["rotation_due"] = (
                    datetime.now() + timedelta(days=self.rotation_days)
                ).isoformat()
                self.key_metadata[key_id]["rotation_count"] = (
                    self.key_metadata[key_id].get("rotation_count", 0) + 1
                )

            logger.info(f"Rotated key: {key_id}")

            # 审计日志
            self._audit_log("rotate", key_id)

            return new_ciphertext.decode()

        except Exception as e:
            logger.error(f"Key rotation failed for {key_id}: {e}")
            raise KMSException(f"密钥轮换失败: {e}")

    def _should_rotate(self, key_id: str) -> bool:
        """
        检查密钥是否需要轮换

        Args:
            key_id: 密钥ID

        Returns:
            是否需要轮换
        """
        if key_id not in self.key_metadata:
            return False

        rotation_due = datetime.fromisoformat(
            self.key_metadata[key_id]["rotation_due"]
        )

        return datetime.now() >= rotation_due

    def get_keys_due_for_rotation(self) -> list:
        """
        获取需要轮换的密钥列表

        Returns:
            密钥ID列表
        """
        due_keys = []

        for key_id in self.key_metadata:
            if self._should_rotate(key_id):
                due_keys.append({
                    "key_id": key_id,
                    "rotation_due": self.key_metadata[key_id]["rotation_due"],
                    "days_overdue": (
                        datetime.now() -
                        datetime.fromisoformat(
                            self.key_metadata[key_id]["rotation_due"]
                        )
                    ).days
                })

        return due_keys

    def delete_key(self, key_id: str):
        """
        删除密钥

        Args:
            key_id: 密钥ID
        """
        if key_id in self.key_metadata:
            del self.key_metadata[key_id]
            logger.info(f"Deleted key: {key_id}")

            # 审计日志
            self._audit_log("delete", key_id)
        else:
            logger.warning(f"Key not found: {key_id}")

    def _audit_log(
        self,
        operation: str,
        key_id: str,
        metadata: Optional[Dict] = None
    ):
        """
        审计日志

        Args:
            operation: 操作类型
            key_id: 密钥ID
            metadata: 元数据
        """
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "key_id": key_id,
            "metadata": metadata or {}
        }

        logger.info(f"KMS Audit: {json.dumps(audit_entry)}")

        # 写入审计日志表（异步，不阻塞主流程）
        try:
            import asyncio
            from src.models.audit_log import AuditLog

            async def _save():
                from src.core.database import get_db_session
                async with get_db_session() as session:
                    log = AuditLog(
                        action=f"kms_{operation}",
                        resource_type="encryption_key",
                        resource_id=key_id,
                        user_id="system",
                        description=f"KMS操作: {operation}",
                        changes=metadata or {},
                    )
                    session.add(log)
                    await session.commit()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_save())
        except Exception as e:
            logger.warning(f"KMS审计日志写入失败: {e}")

    def get_key_metadata(self, key_id: str) -> Optional[Dict]:
        """
        获取密钥元数据

        Args:
            key_id: 密钥ID

        Returns:
            元数据
        """
        return self.key_metadata.get(key_id)

    def list_all_keys(self) -> list:
        """
        列出所有密钥

        Returns:
            密钥列表
        """
        return [
            {
                "key_id": key_id,
                **metadata
            }
            for key_id, metadata in self.key_metadata.items()
        ]

    def get_statistics(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息
        """
        total_keys = len(self.key_metadata)
        keys_due_for_rotation = len(self.get_keys_due_for_rotation())

        total_access_count = sum(
            metadata.get("access_count", 0)
            for metadata in self.key_metadata.values()
        )

        return {
            "total_keys": total_keys,
            "keys_due_for_rotation": keys_due_for_rotation,
            "total_access_count": total_access_count,
            "rotation_policy_days": self.rotation_days
        }


# 全局实例
_kms_service = None


def init_kms_service(master_key: Optional[str] = None):
    """初始化KMS服务"""
    global _kms_service
    _kms_service = KMSService(master_key)
    logger.info("KMS Service initialized")


def get_kms_service() -> KMSService:
    """获取KMS服务实例"""
    if _kms_service is None:
        raise KMSException(
            "KMS Service not initialized. "
            "Call init_kms_service() first."
        )
    return _kms_service


# 便捷函数
def encrypt_api_key(key_id: str, api_key: str, provider: str) -> str:
    """
    加密API密钥

    Args:
        key_id: 密钥ID
        api_key: API密钥
        provider: 提供商（meituan/tiancai/aoqiwei等）

    Returns:
        加密后的密文
    """
    kms = get_kms_service()
    return kms.encrypt_secret(
        key_id=key_id,
        plaintext=api_key,
        metadata={"provider": provider, "type": "api_key"}
    )


def decrypt_api_key(key_id: str, encrypted_key: str) -> str:
    """
    解密API密钥

    Args:
        key_id: 密钥ID
        encrypted_key: 加密的密钥

    Returns:
        明文API密钥
    """
    kms = get_kms_service()
    return kms.decrypt_secret(key_id, encrypted_key)


def rotate_api_key(
    key_id: str,
    old_encrypted_key: str,
    new_api_key: str
) -> str:
    """
    轮换API密钥

    Args:
        key_id: 密钥ID
        old_encrypted_key: 旧的加密密钥
        new_api_key: 新的API密钥

    Returns:
        新的加密密文
    """
    kms = get_kms_service()
    return kms.rotate_key(key_id, old_encrypted_key, new_api_key)
