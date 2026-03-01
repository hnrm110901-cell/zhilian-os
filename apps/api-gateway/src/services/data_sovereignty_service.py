"""
数据主权服务（Phase 3）：客户自持密钥、加密导出、断开权
- 加密导出：导出的 JSON 使用客户密钥 AES-256 加密，屯象无法解密。
- 断开权：导出后删除该租户/门店在图谱中的数据，停服后本地可保留导出文件。
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict, List, Optional

import structlog

from src.core.config import settings
from src.ontology import get_ontology_repository
from src.services.ontology_export_service import export_graph_snapshot

logger = structlog.get_logger()


def _aes_key_from_customer(customer_key: str) -> bytes:
    """从客户提供的密钥派生 32 字节 AES-256 密钥。"""
    raw = customer_key.encode("utf-8") if isinstance(customer_key, str) else customer_key
    return hashlib.sha256(raw).digest()


def encrypt_export_json(export_dict: Dict[str, Any], customer_key: str) -> str:
    """使用客户密钥 AES-256-CBC 加密导出 JSON，返回 base64 密文。"""
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        from Crypto.Random import get_random_bytes
    except ImportError:
        raise RuntimeError("需要 pycryptodome 库以支持加密导出: pip install pycryptodome")
    key = _aes_key_from_customer(customer_key)
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plain = json.dumps(export_dict, ensure_ascii=False).encode("utf-8")
    padded = pad(plain, AES.block_size)
    ct = cipher.encrypt(padded)
    return base64.b64encode(iv + ct).decode("ascii")


def decrypt_export_json(encrypted_b64: str, customer_key: str) -> Dict[str, Any]:
    """使用客户密钥解密导出包。"""
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError:
        raise RuntimeError("需要 pycryptodome 库")
    key = _aes_key_from_customer(customer_key)
    raw = base64.b64decode(encrypted_b64)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plain = unpad(cipher.decrypt(ct), AES.block_size)
    return json.loads(plain.decode("utf-8"))


def export_encrypted(
    tenant_id: str = "",
    store_ids: Optional[List[str]] = None,
    customer_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    导出图谱快照并用客户密钥加密。
    customer_key 由调用方传入或使用配置 CUSTOMER_ENCRYPTION_KEY（空则返回明文 JSON，不加密）。
    """
    if not getattr(settings, "DATA_SOVEREIGNTY_ENABLED", False):
        return {"error": "数据主权功能未启用", "encrypted": False}
    store_id = store_ids[0] if store_ids and len(store_ids) == 1 else None
    if store_ids and len(store_ids) > 1:
        # 多门店：分次导出合并（此处简化为不按 store 过滤，导出全部后加密）
        snapshot = export_graph_snapshot(tenant_id=tenant_id, store_id=None)
    else:
        snapshot = export_graph_snapshot(tenant_id=tenant_id, store_id=store_id)
    if snapshot.get("error"):
        return snapshot
    key = customer_key or getattr(settings, "CUSTOMER_ENCRYPTION_KEY", "") or ""
    if key:
        try:
            cipher_b64 = encrypt_export_json(snapshot, key)
            return {"encrypted": True, "cipher_base64": cipher_b64, "algorithm": "AES-256-CBC", "note": "客户自持密钥解密，屯象无法解密"}
        except Exception as e:
            logger.warning("data_sovereignty_encrypt_failed", error=str(e))
            return {"error": f"加密失败: {e}", "encrypted": False}
    return {"encrypted": False, "export": snapshot}


def disconnect_tenant(
    tenant_id: str,
    store_ids: List[str],
    export_first: bool = True,
    customer_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    断开权：先导出（可选加密），再删除图谱中该租户/门店数据。
    调用方需保证 store_ids 属于该 tenant；删除后本地保留导出文件由调用方负责。
    """
    if not getattr(settings, "DATA_SOVEREIGNTY_ENABLED", False):
        return {"error": "数据主权功能未启用", "disconnected": False}
    repo = get_ontology_repository()
    if not repo:
        return {"error": "Neo4j 未启用", "disconnected": False}
    export_result: Dict[str, Any] = {}
    if export_first:
        store_id = store_ids[0] if (store_ids and len(store_ids) == 1) else None
        snapshot = export_graph_snapshot(tenant_id=tenant_id, store_id=store_id)
        key = customer_key or getattr(settings, "CUSTOMER_ENCRYPTION_KEY", "") or ""
        if key:
            try:
                export_result = {"encrypted": True, "cipher_base64": encrypt_export_json(snapshot, key)}
            except Exception as e:
                export_result = {"encrypted": False, "export": snapshot, "encrypt_error": str(e)}
        else:
            export_result = {"encrypted": False, "export": snapshot}
    counts = repo.delete_tenant_data(tenant_id=tenant_id, store_ids=store_ids if store_ids else None)
    logger.info("data_sovereignty_disconnect_done", tenant_id=tenant_id, store_ids=store_ids, counts=counts)
    return {
        "disconnected": True,
        "tenant_id": tenant_id,
        "store_ids": store_ids,
        "deleted_counts": counts,
        "export_before_delete": export_result if export_first else None,
    }
