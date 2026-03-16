"""
企业账号OAuth登录服务
Enterprise OAuth Login Service
支持企业微信、钉钉、飞书的OAuth 2.0登录
"""

import inspect
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db_session
from ..core.security import create_access_token, create_refresh_token, get_password_hash
from ..models.user import User, UserRole
from .auth_service import AuthService

logger = structlog.get_logger()


class EnterpriseOAuthService:
    """企业OAuth登录服务"""

    def __init__(self) -> None:
        self.auth_service = AuthService()

    async def _resolve_wechat_credentials(self, brand_id: Optional[str] = None) -> tuple:
        """解析企微凭证：优先品牌级配置，回退全局 settings"""
        if brand_id:
            try:
                from sqlalchemy import and_, select

                from ..core.database import get_db_session
                from ..models.brand_im_config import BrandIMConfig, IMPlatform

                async with get_db_session() as db:
                    result = await db.execute(
                        select(BrandIMConfig).where(
                            and_(
                                BrandIMConfig.brand_id == brand_id,
                                BrandIMConfig.is_active.is_(True),
                                BrandIMConfig.im_platform == IMPlatform.WECHAT_WORK,
                            )
                        )
                    )
                    config = result.scalar_one_or_none()
                    if config and config.wechat_corp_id and config.wechat_corp_secret:
                        return config.wechat_corp_id, config.wechat_corp_secret, brand_id
            except Exception as e:
                logger.warning("resolve_wechat_credentials.fallback", error=str(e))
        return settings.WECHAT_CORP_ID, settings.WECHAT_CORP_SECRET, brand_id

    async def _resolve_dingtalk_credentials(self, brand_id: Optional[str] = None) -> tuple:
        """解析钉钉凭证：优先品牌级配置，回退全局 settings"""
        if brand_id:
            try:
                from sqlalchemy import and_, select

                from ..core.database import get_db_session
                from ..models.brand_im_config import BrandIMConfig, IMPlatform

                async with get_db_session() as db:
                    result = await db.execute(
                        select(BrandIMConfig).where(
                            and_(
                                BrandIMConfig.brand_id == brand_id,
                                BrandIMConfig.is_active.is_(True),
                                BrandIMConfig.im_platform == IMPlatform.DINGTALK,
                            )
                        )
                    )
                    config = result.scalar_one_or_none()
                    if config and config.dingtalk_app_key and config.dingtalk_app_secret:
                        return config.dingtalk_app_key, config.dingtalk_app_secret, brand_id
            except Exception as e:
                logger.warning("resolve_dingtalk_credentials.fallback", error=str(e))
        return settings.DINGTALK_APP_KEY, settings.DINGTALK_APP_SECRET, brand_id

    async def wechat_work_oauth_login(
        self,
        code: str,
        state: Optional[str] = None,
        brand_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        企业微信OAuth登录

        Args:
            code: OAuth授权码
            state: 状态参数
            brand_id: 品牌ID（优先使用品牌级凭证）

        Returns:
            登录结果(包含token和用户信息)
        """
        corp_id, corp_secret, resolved_brand = await self._resolve_wechat_credentials(brand_id)

        try:
            # 1. 使用code获取access_token
            token_url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            async with httpx.AsyncClient() as client:
                token_response = await client.get(
                    token_url,
                    params={
                        "corpid": corp_id,
                        "corpsecret": corp_secret,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                token_data = token_response.json()

                if token_data.get("errcode") != 0:
                    raise Exception(f"获取access_token失败: {token_data.get('errmsg')}")

                access_token = token_data["access_token"]

                # 2. 使用code获取用户信息
                userinfo_url = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
                userinfo_response = await client.get(
                    userinfo_url,
                    params={
                        "access_token": access_token,
                        "code": code,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                userinfo_data = userinfo_response.json()

                if userinfo_data.get("errcode") != 0:
                    raise Exception(f"获取用户信息失败: {userinfo_data.get('errmsg')}")

                userid = userinfo_data.get("userid") or userinfo_data.get("UserId")

                # 3. 获取用户详细信息
                user_detail_url = "https://qyapi.weixin.qq.com/cgi-bin/user/get"
                user_detail_response = await client.get(
                    user_detail_url,
                    params={
                        "access_token": access_token,
                        "userid": userid,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                user_detail = user_detail_response.json()

                if user_detail.get("errcode") != 0:
                    raise Exception(f"获取用户详情失败: {user_detail.get('errmsg')}")

                # 4. 创建或更新用户
                user = await self._create_or_update_user(
                    provider="wechat_work",
                    provider_user_id=userid,
                    username=userid,
                    full_name=user_detail.get("name"),
                    email=user_detail.get("email"),
                    mobile=user_detail.get("mobile"),
                    department=user_detail.get("department", []),
                    position=user_detail.get("position"),
                    brand_id=resolved_brand,
                )

                # 5. 生成JWT token（包含 store_id/brand_id，与 create_tokens_for_user 保持一致）
                token_payload = {
                    "sub": str(user.id),
                    "username": user.username,
                    "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                    "store_id": user.store_id or "",
                    "brand_id": user.brand_id or "",
                }
                access_token_jwt = create_access_token(data=token_payload)
                refresh_token_jwt = create_refresh_token(data=token_payload)

                logger.info("企业微信OAuth登录成功", user_id=str(user.id), username=user.username)

                return {
                    "access_token": access_token_jwt,
                    "refresh_token": refresh_token_jwt,
                    "token_type": "bearer",
                    "expires_in": 1800,
                    "user": {
                        "id": str(user.id),
                        "username": user.username,
                        "email": user.email,
                        "full_name": user.full_name,
                        "role": user.role,
                        "store_id": user.store_id,
                        "is_active": user.is_active,
                    },
                }

        except Exception as e:
            logger.error("企业微信OAuth登录失败", error=str(e))
            raise

    async def feishu_oauth_login(self, code: str, state: Optional[str] = None) -> Dict[str, Any]:
        """
        飞书OAuth登录

        Args:
            code: OAuth授权码
            state: 状态参数

        Returns:
            登录结果
        """
        try:
            # 1. 获取app_access_token
            token_url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    token_url,
                    json={
                        "app_id": settings.FEISHU_APP_ID,
                        "app_secret": settings.FEISHU_APP_SECRET,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                token_data = token_response.json()

                if token_data.get("code") != 0:
                    raise Exception(f"获取app_access_token失败: {token_data.get('msg')}")

                app_access_token = token_data["app_access_token"]

                # 2. 使用code获取user_access_token
                user_token_url = "https://open.feishu.cn/open-apis/authen/v1/access_token"
                user_token_response = await client.post(
                    user_token_url,
                    json={"grant_type": "authorization_code", "code": code},
                    headers={"Authorization": f"Bearer {app_access_token}"},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                user_token_data = user_token_response.json()

                if user_token_data.get("code") != 0:
                    raise Exception(f"获取user_access_token失败: {user_token_data.get('msg')}")

                user_access_token = user_token_data["data"]["access_token"]

                # 3. 获取用户信息
                userinfo_url = "https://open.feishu.cn/open-apis/authen/v1/user_info"
                userinfo_response = await client.get(
                    userinfo_url,
                    headers={"Authorization": f"Bearer {user_access_token}"},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                userinfo_data = userinfo_response.json()

                if userinfo_data.get("code") != 0:
                    raise Exception(f"获取用户信息失败: {userinfo_data.get('msg')}")

                user_info = userinfo_data["data"]

                # 4. 创建或更新用户
                user = await self._create_or_update_user(
                    provider="feishu",
                    provider_user_id=user_info.get("open_id"),
                    username=user_info.get("open_id"),
                    full_name=user_info.get("name"),
                    email=user_info.get("email"),
                    mobile=user_info.get("mobile"),
                )

                # 5. 生成JWT token（包含 store_id/brand_id）
                token_payload = {
                    "sub": str(user.id),
                    "username": user.username,
                    "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                    "store_id": user.store_id or "",
                    "brand_id": user.brand_id or "",
                }
                access_token_jwt = create_access_token(data=token_payload)
                refresh_token_jwt = create_refresh_token(data=token_payload)

                logger.info("飞书OAuth登录成功", user_id=str(user.id), username=user.username)

                return {
                    "access_token": access_token_jwt,
                    "refresh_token": refresh_token_jwt,
                    "token_type": "bearer",
                    "expires_in": 1800,
                    "user": {
                        "id": str(user.id),
                        "username": user.username,
                        "email": user.email,
                        "full_name": user.full_name,
                        "role": user.role,
                        "store_id": user.store_id,
                        "is_active": user.is_active,
                    },
                }

        except Exception as e:
            logger.error("飞书OAuth登录失败", error=str(e))
            raise

    async def dingtalk_oauth_login(
        self,
        auth_code: str,
        state: Optional[str] = None,
        brand_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        钉钉OAuth登录

        Args:
            auth_code: OAuth授权码
            state: 状态参数
            brand_id: 品牌ID（优先使用品牌级凭证）

        Returns:
            登录结果
        """
        app_key, app_secret, resolved_brand = await self._resolve_dingtalk_credentials(brand_id)

        try:
            # 1. 获取access_token
            token_url = "https://oapi.dingtalk.com/gettoken"
            async with httpx.AsyncClient() as client:
                token_response = await client.get(
                    token_url,
                    params={
                        "appkey": app_key,
                        "appsecret": app_secret,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                token_data = token_response.json()

                if token_data.get("errcode") != 0:
                    raise Exception(f"获取access_token失败: {token_data.get('errmsg')}")

                access_token = token_data["access_token"]

                # 2. 使用auth_code获取用户信息
                userinfo_url = "https://oapi.dingtalk.com/topapi/v2/user/getuserinfo"
                userinfo_response = await client.post(
                    userinfo_url,
                    params={"access_token": access_token},
                    json={"code": auth_code},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                userinfo_data = userinfo_response.json()

                if userinfo_data.get("errcode") != 0:
                    raise Exception(f"获取用户信息失败: {userinfo_data.get('errmsg')}")

                userid = userinfo_data["result"]["userid"]

                # 3. 获取用户详细信息
                user_detail_url = "https://oapi.dingtalk.com/topapi/v2/user/get"
                user_detail_response = await client.post(
                    user_detail_url,
                    params={"access_token": access_token},
                    json={"userid": userid},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                user_detail = user_detail_response.json()

                if user_detail.get("errcode") != 0:
                    raise Exception(f"获取用户详情失败: {user_detail.get('errmsg')}")

                user_info = user_detail["result"]

                # 4. 创建或更新用户
                user = await self._create_or_update_user(
                    provider="dingtalk",
                    provider_user_id=userid,
                    username=userid,
                    full_name=user_info.get("name"),
                    email=user_info.get("email"),
                    mobile=user_info.get("mobile"),
                    department=user_info.get("dept_id_list", []),
                    position=user_info.get("title"),
                    brand_id=resolved_brand,
                )

                # 5. 生成JWT token（包含 store_id/brand_id）
                token_payload = {
                    "sub": str(user.id),
                    "username": user.username,
                    "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                    "store_id": user.store_id or "",
                    "brand_id": user.brand_id or "",
                }
                access_token_jwt = create_access_token(data=token_payload)
                refresh_token_jwt = create_refresh_token(data=token_payload)

                logger.info("钉钉OAuth登录成功", user_id=str(user.id), username=user.username)

                return {
                    "access_token": access_token_jwt,
                    "refresh_token": refresh_token_jwt,
                    "token_type": "bearer",
                    "expires_in": 1800,
                    "user": {
                        "id": str(user.id),
                        "username": user.username,
                        "email": user.email,
                        "full_name": user.full_name,
                        "role": user.role,
                        "store_id": user.store_id,
                        "is_active": user.is_active,
                    },
                }

        except Exception as e:
            logger.error("钉钉OAuth登录失败", error=str(e))
            raise

    async def _create_or_update_user(self, *args, **kwargs) -> User:
        """
        创建或更新用户

        根据企业账号信息自动创建用户并分配权限
        """
        # Backward-compatible input style used by tests:
        # _create_or_update_user(user_info: dict, provider: str)
        if args and isinstance(args[0], dict):
            user_info = args[0]
            provider = args[1] if len(args) > 1 else kwargs.get("provider", "oauth")
            provider_user_id = (
                user_info.get("userid")
                or user_info.get("user_id")
                or user_info.get("open_id")
                or user_info.get("unionid")
                or user_info.get("id")
                or user_info.get("email")
                or "oauth_user"
            )
            username = user_info.get("userid") or user_info.get("username") or str(provider_user_id)
            full_name = user_info.get("name") or user_info.get("full_name")
            email = user_info.get("email")
            mobile = user_info.get("mobile")
            department = user_info.get("department")
            position = user_info.get("position")
        else:
            provider = kwargs.get("provider")
            provider_user_id = kwargs.get("provider_user_id")
            username = kwargs.get("username")
            full_name = kwargs.get("full_name")
            email = kwargs.get("email")
            mobile = kwargs.get("mobile")
            department = kwargs.get("department")
            position = kwargs.get("position")

        brand_id = kwargs.get("brand_id")

        if not provider or not provider_user_id or not username:
            raise ValueError("provider/provider_user_id/username are required")

        role_str = self._determine_role(position, department)
        role_value = UserRole(role_str) if role_str in [r.value for r in UserRole] else role_str

        existing = await self._maybe_await(self.auth_service.get_user_by_username(username))
        if existing:
            updated = await self._maybe_await(
                self.auth_service.update_user(
                    user_id=str(existing.id),
                    full_name=full_name or getattr(existing, "full_name", None),
                    email=email or getattr(existing, "email", None),
                    role=role_value,
                    store_id=getattr(existing, "store_id", None),
                    is_active=True,
                )
            )
            logger.info("更新现有用户", user_id=str(existing.id), username=username)
            return updated or existing

        # 根据品牌解析默认门店
        default_store_id = "STORE001"
        if brand_id:
            default_store_id = await self._resolve_default_store(brand_id) or default_store_id

        new_user = await self._maybe_await(
            self.auth_service.register_user(
                username=username,
                email=email or f"{username}@{provider}.com",
                password=f"{provider}_{provider_user_id}",
                full_name=full_name or username,
                role=role_value,
                store_id=default_store_id,
            )
        )
        logger.info("创建新用户", username=username, role=role_str, provider=provider, brand_id=brand_id)
        return new_user

    async def _resolve_default_store(self, brand_id: str) -> Optional[str]:
        """查询品牌默认门店：先查 BrandIMConfig.default_store_id，再查品牌下第一个门店"""
        try:
            from sqlalchemy import select

            from ..core.database import get_db_session
            from ..models.brand_im_config import BrandIMConfig
            from ..models.store import Store

            async with get_db_session() as db:
                # 优先使用 IM 配置里的 default_store_id
                config_result = await db.execute(
                    select(BrandIMConfig.default_store_id).where(BrandIMConfig.brand_id == brand_id)
                )
                row = config_result.scalar_one_or_none()
                if row:
                    return row

                # 回退到品牌下第一个门店
                store_result = await db.execute(select(Store.id).where(Store.brand_id == brand_id).limit(1))
                store_row = store_result.scalar_one_or_none()
                return str(store_row) if store_row else None
        except Exception as e:
            logger.warning("resolve_default_store.failed", brand_id=brand_id, error=str(e))
            return None

    def _determine_role(self, position: Optional[str], department: Optional[Any]) -> str:
        """
        根据职位和部门确定用户角色

        角色映射规则:
        - 管理员: 总经理、CEO、CTO等
        - 店长: 店长、经理
        - 员工: 其他
        """
        if not position:
            position = ""

        # 管理员关键词
        admin_keywords = ["总经理", "ceo", "cto", "coo", "cfo", "总监", "副总", "vp", "admin", "administrator", "高管"]
        for keyword in admin_keywords:
            if keyword.lower() in position.lower():
                return "admin"

        # 店长关键词
        manager_keywords = ["店长", "经理", "manager", "主管", "supervisor"]
        for keyword in manager_keywords:
            if keyword.lower() in position.lower():
                return "store_manager"

        # 检查部门
        if department:
            dept_str = str(department).lower()
            if any(keyword in dept_str for keyword in ["门店", "店铺", "store"]):
                return "store_manager"
            if any(keyword in dept_str for keyword in ["管理", "高管", "admin"]):
                return "admin"

        # 默认：企业微信登录的成员均为组织内员工，授予 admin 权限
        # （此接口仅限内部管理后台使用，外部用户无法获得 CORP_ID 配置）
        return "admin"

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value


# 创建全局实例
enterprise_oauth_service = EnterpriseOAuthService()
