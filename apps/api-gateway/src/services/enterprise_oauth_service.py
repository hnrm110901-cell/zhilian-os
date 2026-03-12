"""
企业账号OAuth登录服务
Enterprise OAuth Login Service
支持企业微信、钉钉、飞书的OAuth 2.0登录
"""
import os
from typing import Dict, Any, Optional
import inspect
import httpx
import structlog
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db_session
from ..models.user import User, UserRole
from ..core.security import create_access_token, create_refresh_token, get_password_hash
from .auth_service import AuthService

logger = structlog.get_logger()


class EnterpriseOAuthService:
    """企业OAuth登录服务"""
    def __init__(self) -> None:
        self.auth_service = AuthService()

    async def wechat_work_oauth_login(
        self,
        code: str,
        state: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        企业微信OAuth登录

        Args:
            code: OAuth授权码
            state: 状态参数

        Returns:
            登录结果(包含token和用户信息)
        """
        try:
            # 1. 使用code获取access_token
            token_url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            async with httpx.AsyncClient() as client:
                token_response = await client.get(
                    token_url,
                    params={
                        "corpid": settings.WECHAT_CORP_ID,
                        "corpsecret": settings.WECHAT_CORP_SECRET,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                )

                # 5. 生成JWT token
                access_token_jwt = create_access_token(
                    data={"sub": str(user.id), "username": user.username, "role": user.role}
                )
                refresh_token_jwt = create_refresh_token(
                    data={"sub": str(user.id), "username": user.username, "role": user.role}
                )

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
                    }
                }

        except Exception as e:
            logger.error("企业微信OAuth登录失败", error=str(e))
            raise

    async def feishu_oauth_login(
        self,
        code: str,
        state: Optional[str] = None
    ) -> Dict[str, Any]:
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
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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

                # 5. 生成JWT token
                access_token_jwt = create_access_token(
                    data={"sub": str(user.id), "username": user.username, "role": user.role}
                )
                refresh_token_jwt = create_refresh_token(
                    data={"sub": str(user.id), "username": user.username, "role": user.role}
                )

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
                    }
                }

        except Exception as e:
            logger.error("飞书OAuth登录失败", error=str(e))
            raise

    async def dingtalk_oauth_login(
        self,
        auth_code: str,
        state: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        钉钉OAuth登录

        Args:
            auth_code: OAuth授权码
            state: 状态参数

        Returns:
            登录结果
        """
        try:
            # 1. 获取access_token
            token_url = "https://oapi.dingtalk.com/gettoken"
            async with httpx.AsyncClient() as client:
                token_response = await client.get(
                    token_url,
                    params={
                        "appkey": settings.DINGTALK_APP_KEY,
                        "appsecret": settings.DINGTALK_APP_SECRET,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0"))
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
                )

                # 5. 生成JWT token
                access_token_jwt = create_access_token(
                    data={"sub": str(user.id), "username": user.username, "role": user.role}
                )
                refresh_token_jwt = create_refresh_token(
                    data={"sub": str(user.id), "username": user.username, "role": user.role}
                )

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
                    }
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

        new_user = await self._maybe_await(
            self.auth_service.register_user(
                username=username,
                email=email or f"{username}@{provider}.com",
                password=f"{provider}_{provider_user_id}",
                full_name=full_name or username,
                role=role_value,
                store_id="STORE001",
            )
        )
        logger.info("创建新用户", username=username, role=role_str, provider=provider)
        return new_user

    def _determine_role(
        self,
        position: Optional[str],
        department: Optional[Any]
    ) -> str:
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

        # 默认为员工
        return "staff"

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value


# 创建全局实例
enterprise_oauth_service = EnterpriseOAuthService()
