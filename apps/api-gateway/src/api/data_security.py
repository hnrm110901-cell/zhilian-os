"""
数据安全 API — AES-256-GCM 密钥管理 + 加密覆盖率审计

端点：
  POST  /api/v1/security/keys/{store_id}           为门店生成密钥
  GET   /api/v1/security/keys/{store_id}           查询门店密钥列表
  POST  /api/v1/security/keys/{store_id}/rotate    密钥轮换
  POST  /api/v1/security/keys/{key_id}/revoke      吊销密钥（危险）

  GET   /api/v1/security/coverage/{store_id}       加密覆盖率报告
  POST  /api/v1/security/encrypt                   加密任意文本（测试用）
  POST  /api/v1/security/decrypt                   解密任意文本（测试用）
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user, require_role
from src.models.user import User, UserRole
from src.services.data_encryption_service import DataEncryptionService

router = APIRouter(prefix="/api/v1/security", tags=["data_security"])

# 仅管理员和财务可管理密钥
_admin_only = require_role(UserRole.ADMIN, UserRole.FINANCE)


# ── Schemas ───────────────────────────────────────────────────────────────────

class KeyOut(BaseModel):
    id: str
    store_id: str
    key_version: int
    key_alias: Optional[str]
    algorithm: str
    status: str
    is_active: bool
    purpose: str
    activated_at: Optional[str]
    expires_at: Optional[str]

    model_config = {"from_attributes": True}


class EncryptIn(BaseModel):
    store_id: str
    plaintext: str = Field(..., max_length=10000)
    purpose: str = Field("data_encryption")


class EncryptOut(BaseModel):
    store_id: str
    key_version: int
    ciphertext: str


class DecryptIn(BaseModel):
    store_id: str
    ciphertext: str
    purpose: str = Field("data_encryption")


# ── 密钥管理端点 ──────────────────────────────────────────────────────────────

@router.post("/keys/{store_id}", response_model=KeyOut, status_code=status.HTTP_201_CREATED)
async def create_store_key(
    store_id: str,
    purpose: str = "data_encryption",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin_only),
):
    """为门店生成新的 AES-256-GCM 数据加密密钥"""
    svc = DataEncryptionService(db)
    # 检查是否已有激活密钥
    existing = await svc.list_keys(store_id, purpose)
    if any(k.is_active for k in existing):
        raise HTTPException(
            status_code=409,
            detail="门店已有激活密钥，请使用 rotate 接口进行轮换",
        )
    key = await svc.create_key(
        store_id=store_id,
        purpose=purpose,
        created_by=str(current_user.id),
    )
    await db.commit()
    return _key_to_out(key)


@router.get("/keys/{store_id}", response_model=List[KeyOut])
async def list_store_keys(
    store_id: str,
    purpose: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin_only),
):
    """查询门店所有密钥版本（不返回 DEK 明文）"""
    svc = DataEncryptionService(db)
    keys = await svc.list_keys(store_id, purpose)
    return [_key_to_out(k) for k in keys]


@router.post("/keys/{store_id}/rotate")
async def rotate_store_key(
    store_id: str,
    purpose: str = "data_encryption",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin_only),
):
    """密钥轮换 — 停用旧 DEK，生成新 DEK"""
    svc = DataEncryptionService(db)
    try:
        old_key, new_key = await svc.rotate_key(
            store_id=store_id,
            rotated_by=str(current_user.id),
            purpose=purpose,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {
        "message": "密钥轮换成功",
        "old_version": old_key.key_version,
        "new_version": new_key.key_version,
        "new_key_id": str(new_key.id),
    }


@router.post("/keys/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),  # 仅超管
):
    """
    ⚠️ 吊销密钥（极危险：使用此密钥加密的数据将永久不可恢复）

    仅在密钥泄露事件中使用，需 ADMIN 权限。
    """
    svc = DataEncryptionService(db)
    ok = await svc.revoke_key(key_id, revoked_by=str(current_user.id))
    if not ok:
        raise HTTPException(status_code=404, detail="密钥不存在")
    await db.commit()
    return {"message": "密钥已吊销（使用此密钥加密的数据不可恢复）", "key_id": key_id}


# ── 加密覆盖率审计 ────────────────────────────────────────────────────────────

@router.get("/coverage/{store_id}")
async def get_encryption_coverage(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_admin_only),
):
    """查询门店数据加密覆盖率报告"""
    svc = DataEncryptionService(db)
    return await svc.get_encryption_coverage(store_id)


# ── 加密/解密测试端点（仅开发环境）──────────────────────────────────────────

@router.post("/encrypt", response_model=EncryptOut)
async def encrypt_text(
    payload: EncryptIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """加密任意文本（使用门店当前激活密钥）"""
    svc = DataEncryptionService(db)
    key = await svc.get_or_create_key(payload.store_id, payload.purpose)
    ciphertext = svc.encrypt(payload.plaintext, key)
    await db.commit()
    return EncryptOut(
        store_id=payload.store_id,
        key_version=key.key_version,
        ciphertext=ciphertext,
    )


@router.post("/decrypt")
async def decrypt_text(
    payload: DecryptIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解密文本（自动选择对应版本密钥）"""
    svc = DataEncryptionService(db)
    keys = await svc.list_keys(payload.store_id, payload.purpose)
    if not keys:
        raise HTTPException(status_code=404, detail="门店无可用密钥")

    # 尝试所有密钥版本（从新到旧）
    for key in keys:
        try:
            plaintext = svc.decrypt(payload.ciphertext, key)
            return {"plaintext": plaintext, "key_version": key.key_version}
        except Exception:
            continue

    raise HTTPException(status_code=400, detail="解密失败：密文损坏或密钥不匹配")


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _key_to_out(key) -> dict:
    return {
        "id": str(key.id),
        "store_id": key.store_id,
        "key_version": key.key_version,
        "key_alias": key.key_alias,
        "algorithm": key.algorithm.value if hasattr(key.algorithm, "value") else key.algorithm,
        "status": key.status.value if hasattr(key.status, "value") else key.status,
        "is_active": key.is_active,
        "purpose": key.purpose,
        "activated_at": key.activated_at.isoformat() if key.activated_at else None,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
    }
