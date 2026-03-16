"""
IM 通讯录同步 API — 商户 IM 平台配置 + 通讯录同步
"""

import uuid as uuid_mod
from datetime import date, datetime, timedelta
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.brand_im_config import BrandIMConfig, IMPlatform, IMSyncLog
from ..models.user import User
from ..services.im_attendance_sync import IMAttendanceSyncService
from ..services.im_milestone_notifier import IMMilestoneNotifier
from ..services.im_onboarding_robot import IMOnboardingRobot
from ..services.im_org_sync import IMOrgSyncService
from ..services.im_sync_service import IMSyncService

logger = structlog.get_logger()
router = APIRouter()


# ── 请求模型 ──────────────────────────────────────────


class IMConfigRequest(BaseModel):
    brand_id: str
    im_platform: str  # wechat_work / dingtalk

    # 企微
    wechat_corp_id: Optional[str] = None
    wechat_corp_secret: Optional[str] = None
    wechat_agent_id: Optional[str] = None
    wechat_token: Optional[str] = None
    wechat_encoding_aes_key: Optional[str] = None

    # 钉钉
    dingtalk_app_key: Optional[str] = None
    dingtalk_app_secret: Optional[str] = None
    dingtalk_agent_id: Optional[str] = None
    dingtalk_aes_key: Optional[str] = None
    dingtalk_token: Optional[str] = None

    # 同步选项
    sync_enabled: bool = True
    auto_create_user: bool = True
    auto_disable_user: bool = True
    default_store_id: Optional[str] = None
    department_store_mapping: Optional[dict] = None  # {"部门名": "STORE_ID"}


class IMConfigUpdateRequest(BaseModel):
    wechat_corp_id: Optional[str] = None
    wechat_corp_secret: Optional[str] = None
    wechat_agent_id: Optional[str] = None
    wechat_token: Optional[str] = None
    wechat_encoding_aes_key: Optional[str] = None

    dingtalk_app_key: Optional[str] = None
    dingtalk_app_secret: Optional[str] = None
    dingtalk_agent_id: Optional[str] = None
    dingtalk_aes_key: Optional[str] = None
    dingtalk_token: Optional[str] = None

    sync_enabled: Optional[bool] = None
    auto_create_user: Optional[bool] = None
    auto_disable_user: Optional[bool] = None
    default_store_id: Optional[str] = None
    department_store_mapping: Optional[dict] = None


class DeptStoreMappingRequest(BaseModel):
    mapping: dict  # {"部门名": "STORE_ID"}


# ── IM 配置管理 ──────────────────────────────────────


@router.get("/merchants/{brand_id}/im/config")
async def get_im_config(
    brand_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取品牌 IM 平台配置"""
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config:
        return {"configured": False, "brand_id": brand_id}

    return {
        "configured": True,
        "brand_id": config.brand_id,
        "im_platform": config.im_platform.value if hasattr(config.im_platform, "value") else str(config.im_platform),
        "wechat_corp_id": config.wechat_corp_id,
        "wechat_agent_id": config.wechat_agent_id,
        "has_wechat_secret": bool(config.wechat_corp_secret),
        "dingtalk_app_key": config.dingtalk_app_key,
        "dingtalk_agent_id": config.dingtalk_agent_id,
        "has_dingtalk_secret": bool(config.dingtalk_app_secret),
        "sync_enabled": config.sync_enabled,
        "auto_create_user": config.auto_create_user,
        "auto_disable_user": config.auto_disable_user,
        "default_store_id": config.default_store_id,
        "department_store_mapping": config.department_store_mapping,
        "last_sync_at": str(config.last_sync_at) if config.last_sync_at else None,
        "last_sync_status": config.last_sync_status,
        "last_sync_message": config.last_sync_message,
        "last_sync_stats": config.last_sync_stats,
        "is_active": config.is_active,
    }


@router.post("/merchants/{brand_id}/im/config")
async def save_im_config(
    brand_id: str,
    body: IMConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """保存/更新品牌 IM 平台配置"""
    # 验证平台类型
    try:
        platform = IMPlatform(body.im_platform)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不支持的IM平台: {body.im_platform}，仅支持 wechat_work / dingtalk")

    # 验证必填字段
    if platform == IMPlatform.WECHAT_WORK:
        if not body.wechat_corp_id or not body.wechat_corp_secret:
            raise HTTPException(status_code=400, detail="企业微信需要填写 corp_id 和 corp_secret")
    elif platform == IMPlatform.DINGTALK:
        if not body.dingtalk_app_key or not body.dingtalk_app_secret:
            raise HTTPException(status_code=400, detail="钉钉需要填写 app_key 和 app_secret")

    # 查找或创建
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()

    if config:
        # 更新
        config.im_platform = platform
        config.wechat_corp_id = body.wechat_corp_id
        config.wechat_corp_secret = body.wechat_corp_secret
        config.wechat_agent_id = body.wechat_agent_id
        config.wechat_token = body.wechat_token
        config.wechat_encoding_aes_key = body.wechat_encoding_aes_key
        config.dingtalk_app_key = body.dingtalk_app_key
        config.dingtalk_app_secret = body.dingtalk_app_secret
        config.dingtalk_agent_id = body.dingtalk_agent_id
        config.dingtalk_aes_key = body.dingtalk_aes_key
        config.dingtalk_token = body.dingtalk_token
        config.sync_enabled = body.sync_enabled
        config.auto_create_user = body.auto_create_user
        config.auto_disable_user = body.auto_disable_user
        config.default_store_id = body.default_store_id
        if body.department_store_mapping is not None:
            config.department_store_mapping = body.department_store_mapping
        config.is_active = True
    else:
        config = BrandIMConfig(
            id=uuid_mod.uuid4(),
            brand_id=brand_id,
            im_platform=platform,
            wechat_corp_id=body.wechat_corp_id,
            wechat_corp_secret=body.wechat_corp_secret,
            wechat_agent_id=body.wechat_agent_id,
            wechat_token=body.wechat_token,
            wechat_encoding_aes_key=body.wechat_encoding_aes_key,
            dingtalk_app_key=body.dingtalk_app_key,
            dingtalk_app_secret=body.dingtalk_app_secret,
            dingtalk_agent_id=body.dingtalk_agent_id,
            dingtalk_aes_key=body.dingtalk_aes_key,
            dingtalk_token=body.dingtalk_token,
            sync_enabled=body.sync_enabled,
            auto_create_user=body.auto_create_user,
            auto_disable_user=body.auto_disable_user,
            default_store_id=body.default_store_id,
            department_store_mapping=body.department_store_mapping,
        )
        db.add(config)

    await db.commit()

    platform_label = "企业微信" if platform == IMPlatform.WECHAT_WORK else "钉钉"
    return {
        "brand_id": brand_id,
        "im_platform": platform.value,
        "message": f"{platform_label}配置保存成功",
    }


@router.put("/merchants/{brand_id}/im/config")
async def update_im_config(
    brand_id: str,
    body: IMConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新 IM 配置（部分更新）"""
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="未找到IM配置，请先创建")

    update_fields = body.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if value is not None:
            setattr(config, field, value)

    await db.commit()
    return {"brand_id": brand_id, "updated": True}


# ── 通讯录同步 ──────────────────────────────────────


@router.post("/merchants/{brand_id}/im/sync")
async def trigger_sync(
    brand_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """手动触发全量通讯录同步"""
    service = IMSyncService(db)
    try:
        result = await service.sync_roster(brand_id, trigger="manual")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.get("/merchants/{brand_id}/im/sync-logs")
async def get_sync_logs(
    brand_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取通讯录同步日志"""
    result = await db.execute(
        select(IMSyncLog).where(IMSyncLog.brand_id == brand_id).order_by(IMSyncLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(log.id),
                "im_platform": log.im_platform,
                "trigger": log.trigger,
                "status": log.status,
                "message": log.message,
                "total_platform_members": log.total_platform_members,
                "added_count": log.added_count,
                "updated_count": log.updated_count,
                "disabled_count": log.disabled_count,
                "user_created_count": log.user_created_count,
                "user_disabled_count": log.user_disabled_count,
                "error_count": log.error_count,
                "started_at": str(log.started_at) if log.started_at else None,
                "finished_at": str(log.finished_at) if log.finished_at else None,
            }
            for log in logs
        ],
    }


# ── IM 平台连接测试 ──────────────────────────────────


@router.post("/merchants/{brand_id}/im/test-connection")
async def test_im_connection(
    brand_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """测试 IM 平台连接（验证凭证是否有效）"""
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="未找到IM配置")

    service = IMSyncService(db)
    try:
        adapter = await service._get_adapter(config)
        token = await adapter.get_access_token()
        departments = await adapter.fetch_departments()

        platform_label = "企业微信" if config.im_platform == IMPlatform.WECHAT_WORK else "钉钉"
        return {
            "connected": True,
            "platform": platform_label,
            "department_count": len(departments),
            "message": f"{platform_label}连接成功，发现 {len(departments)} 个部门",
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "message": "连接失败，请检查凭证配置",
        }


# ── 部门→门店映射 ──────────────────────────────────


@router.get("/merchants/{brand_id}/im/departments")
async def list_im_departments(
    brand_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取 IM 平台部门列表（用于配置部门→门店映射）"""
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="未找到IM配置")

    service = IMSyncService(db)
    try:
        adapter = await service._get_adapter(config)
        departments = await adapter.fetch_departments()

        # 统一格式
        if config.im_platform == IMPlatform.WECHAT_WORK:
            items = [{"id": d.get("id"), "name": d.get("name"), "parentid": d.get("parentid")} for d in departments]
        else:
            items = [{"id": d.get("dept_id"), "name": d.get("name"), "parentid": d.get("parent_id")} for d in departments]

        return {
            "brand_id": brand_id,
            "departments": items,
            "current_mapping": config.department_store_mapping or {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取部门列表失败: {str(e)}")


@router.put("/merchants/{brand_id}/im/department-mapping")
async def update_department_mapping(
    brand_id: str,
    body: DeptStoreMappingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新部门→门店映射"""
    result = await db.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="未找到IM配置")

    config.department_store_mapping = body.mapping
    await db.commit()

    return {
        "brand_id": brand_id,
        "department_store_mapping": config.department_store_mapping,
        "message": f"已映射 {len(body.mapping)} 个部门到门店",
    }


# ── 考勤数据同步 ──────────────────────────────────


@router.post("/merchants/{brand_id}/im/attendance-sync")
async def sync_attendance(
    brand_id: str,
    days: int = Query(7, ge=1, le=31, description="同步天数（默认7天）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """从 IM 平台同步打卡/考勤数据"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    service = IMAttendanceSyncService(db)
    try:
        result = await service.sync_attendance(brand_id, start_date, end_date)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"考勤同步失败: {str(e)}")


# ── 组织架构同步（Phase 4 #13）──────────────────────


class OrgSyncRequest(BaseModel):
    auto_create_store: bool = False  # 是否为无对应门店的叶子部门自动创建门店


@router.post("/merchants/{brand_id}/im/org-sync")
async def sync_org_structure(
    brand_id: str,
    body: Optional[OrgSyncRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    同步 IM 平台组织架构 → 屯象OS 门店/区域结构。

    - 拉取 IM 部门树
    - 按 department_store_mapping 匹配已有门店
    - 更新 Store.region 为上级部门路径
    - 可选 auto_create_store 为叶子部门自动创建门店
    """
    auto_create = body.auto_create_store if body else False
    service = IMOrgSyncService(db)
    try:
        result = await service.sync_org_structure(
            brand_id,
            auto_create_store=auto_create,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"组织架构同步失败: {str(e)}")


# ── 入职引导机器人（Phase 4 #10）──────────────────────


@router.post("/merchants/{brand_id}/im/onboarding/{employee_id}")
async def trigger_onboarding(
    brand_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """手动触发单个员工的入职引导（自动推送 IM 消息 + 创建入职计划）"""
    robot = IMOnboardingRobot(db)
    try:
        result = await robot.trigger_onboarding(employee_id, brand_id=brand_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入职引导失败: {str(e)}")


# ── 里程碑通知（Phase 4 #21）──────────────────────


@router.post("/merchants/{brand_id}/im/notify-milestone/{milestone_id}")
async def notify_milestone(
    brand_id: str,
    milestone_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """手动触发单个里程碑 IM 通知"""
    notifier = IMMilestoneNotifier(db)
    try:
        result = await notifier.notify_milestone(milestone_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"里程碑通知失败: {str(e)}")


@router.post("/merchants/{brand_id}/im/sweep-milestones")
async def sweep_unnotified_milestones(
    brand_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量推送所有未通知的里程碑"""
    notifier = IMMilestoneNotifier(db)
    try:
        result = await notifier.sweep_unnotified_milestones(brand_id=brand_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"里程碑批量通知失败: {str(e)}")
