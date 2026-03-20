"""
IM 通讯录同步服务 — 企微/钉钉 → 屯象OS 员工花名册 + 系统账号

核心流程：
1. 从 IM 平台拉取全量/增量通讯录
2. 与本地 employees 表对比（以 wechat_userid / dingtalk_userid 为关联键）
3. 新增 → 创建 Employee + 可选创建 User 系统账号
4. 更新 → 同步姓名/手机/职位/部门等字段
5. 离职 → 标记 Employee.is_active=False + 禁用 User 账号
6. 记录 IMSyncLog

设计原则：
- 平台差异封装在 Adapter 中，同步逻辑统一
- 每次同步幂等，可重复执行
- 向后兼容：无 BrandIMConfig 时使用全局 settings 配置
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.security import get_password_hash
from ..models.brand_im_config import BrandIMConfig, IMPlatform, IMSyncLog
from ..models.hr.person import Person
from ..models.hr.employment_assignment import EmploymentAssignment
from ..models.user import User, UserRole

logger = structlog.get_logger()


# ── 统一人员数据结构 ──────────────────────────────────────


@dataclass
class PlatformMember:
    """IM 平台拉取到的人员标准结构"""

    userid: str  # 平台内唯一ID
    name: str
    mobile: Optional[str] = None
    email: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None  # 部门名称
    department_ids: List[int] = field(default_factory=list)
    is_active: bool = True  # 平台上是否在职
    avatar_url: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


# ── 平台适配器抽象 ───────────────────────────────────────


class IMPlatformAdapter(ABC):
    """IM 平台通讯录适配器抽象"""

    @abstractmethod
    async def get_access_token(self) -> str: ...

    @abstractmethod
    async def fetch_all_members(self) -> List[PlatformMember]:
        """拉取全量通讯录成员"""
        ...

    @abstractmethod
    async def fetch_departments(self) -> List[Dict[str, Any]]:
        """拉取部门树"""
        ...


class WeChatWorkAdapter(IMPlatformAdapter):
    """企业微信通讯录适配器"""

    def __init__(self, corp_id: str, corp_secret: str):
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self.base_url = "https://qyapi.weixin.qq.com/cgi-bin"
        self._token: Optional[str] = None

    async def get_access_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/gettoken",
                params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
                timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise Exception(f"企微获取token失败: {data.get('errmsg')}")
            self._token = data["access_token"]
            return self._token

    async def fetch_departments(self) -> List[Dict[str, Any]]:
        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/department/list",
                params={"access_token": token},
                timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise Exception(f"企微获取部门失败: {data.get('errmsg')}")
            return data.get("department", [])

    async def fetch_all_members(self) -> List[PlatformMember]:
        """递归拉取根部门下所有成员"""
        token = await self.get_access_token()
        departments = await self.fetch_departments()

        # 建部门ID→名称映射
        dept_map = {d["id"]: d["name"] for d in departments}

        members: Dict[str, PlatformMember] = {}

        async with httpx.AsyncClient() as client:
            for dept in departments:
                dept_id = dept["id"]
                resp = await client.get(
                    f"{self.base_url}/user/list",
                    params={
                        "access_token": token,
                        "department_id": dept_id,
                        "fetch_child": 0,
                    },
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    logger.warning("企微获取部门成员失败", dept_id=dept_id, error=data.get("errmsg"))
                    continue

                for u in data.get("userlist", []):
                    uid = u.get("userid")
                    if uid in members:
                        continue
                    dept_ids = u.get("department", [])
                    dept_name = dept_map.get(dept_ids[0], "") if dept_ids else ""
                    members[uid] = PlatformMember(
                        userid=uid,
                        name=u.get("name", ""),
                        mobile=u.get("mobile"),
                        email=u.get("email"),
                        position=u.get("position"),
                        department=dept_name,
                        department_ids=dept_ids,
                        is_active=u.get("status", 1) == 1,
                        avatar_url=u.get("avatar"),
                        raw=u,
                    )

        return list(members.values())


class DingTalkAdapter(IMPlatformAdapter):
    """钉钉通讯录适配器"""

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = "https://oapi.dingtalk.com"
        self._token: Optional[str] = None

    async def get_access_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/gettoken",
                params={"appkey": self.app_key, "appsecret": self.app_secret},
                timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise Exception(f"钉钉获取token失败: {data.get('errmsg')}")
            self._token = data["access_token"]
            return self._token

    async def fetch_departments(self) -> List[Dict[str, Any]]:
        token = await self.get_access_token()
        all_depts: List[Dict[str, Any]] = []

        async with httpx.AsyncClient() as client:
            # 获取子部门列表（从根部门1开始递归）
            async def _fetch_sub(parent_id: int):
                resp = await client.post(
                    f"{self.base_url}/topapi/v2/department/listsub",
                    params={"access_token": token},
                    json={"dept_id": parent_id},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    return
                for d in data.get("result", []):
                    all_depts.append(d)
                    await _fetch_sub(d["dept_id"])

            await _fetch_sub(1)

        return all_depts

    async def fetch_all_members(self) -> List[PlatformMember]:
        token = await self.get_access_token()
        departments = await self.fetch_departments()

        dept_map = {d["dept_id"]: d["name"] for d in departments}
        # 加根部门
        dept_map[1] = "根部门"

        members: Dict[str, PlatformMember] = {}
        dept_ids_to_scan = [1] + [d["dept_id"] for d in departments]

        async with httpx.AsyncClient() as client:
            for dept_id in dept_ids_to_scan:
                cursor = 0
                while True:
                    resp = await client.post(
                        f"{self.base_url}/topapi/v2/user/list",
                        params={"access_token": token},
                        json={"dept_id": dept_id, "cursor": cursor, "size": 100},
                        timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                    )
                    data = resp.json()
                    if data.get("errcode") != 0:
                        logger.warning("钉钉获取部门成员失败", dept_id=dept_id, error=data.get("errmsg"))
                        break

                    result = data.get("result", {})
                    for u in result.get("list", []):
                        uid = u.get("userid")
                        if uid in members:
                            continue
                        dept_ids_list = u.get("dept_id_list", [])
                        dept_name = dept_map.get(dept_ids_list[0], "") if dept_ids_list else ""
                        members[uid] = PlatformMember(
                            userid=uid,
                            name=u.get("name", ""),
                            mobile=u.get("mobile"),
                            email=u.get("email"),
                            position=u.get("title"),
                            department=dept_name,
                            department_ids=dept_ids_list,
                            is_active=u.get("active", True),
                            avatar_url=u.get("avatar"),
                            raw=u,
                        )

                    if not result.get("has_more"):
                        break
                    cursor = result.get("next_cursor", 0)

        return list(members.values())


# ── 统一同步服务 ──────────────────────────────────────────


class IMSyncService:
    """
    IM 通讯录同步服务。

    核心方法：
    - sync_roster(brand_id, trigger) — 全量同步
    - handle_member_event(brand_id, event_type, member_data) — 增量事件处理
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 获取适配器 ──

    async def _get_adapter(self, config: BrandIMConfig) -> IMPlatformAdapter:
        if config.im_platform == IMPlatform.WECHAT_WORK:
            return WeChatWorkAdapter(
                corp_id=config.wechat_corp_id or settings.WECHAT_CORP_ID,
                corp_secret=config.wechat_corp_secret or settings.WECHAT_CORP_SECRET,
            )
        elif config.im_platform == IMPlatform.DINGTALK:
            return DingTalkAdapter(
                app_key=config.dingtalk_app_key or settings.DINGTALK_APP_KEY,
                app_secret=config.dingtalk_app_secret or settings.DINGTALK_APP_SECRET,
            )
        raise ValueError(f"不支持的IM平台: {config.im_platform}")

    async def _get_config(self, brand_id: str) -> Optional[BrandIMConfig]:
        result = await self.db.execute(
            select(BrandIMConfig).where(and_(BrandIMConfig.brand_id == brand_id, BrandIMConfig.is_active.is_(True)))
        )
        return result.scalar_one_or_none()

    # ── 全量同步 ──

    async def sync_roster(
        self,
        brand_id: str,
        trigger: str = "manual",
    ) -> Dict[str, Any]:
        """
        全量同步 IM 通讯录 → employees + users。

        流程：
        1. 拉取平台全量成员
        2. 按 im_userid 匹配本地 employees
        3. 新增 → 创建 Employee（+ 可选 User）
        4. 已有 → 更新姓名/手机/职位
        5. 本地有但平台无 → 标记离职（+ 禁用 User）
        """
        config = await self._get_config(brand_id)
        if not config:
            return {"error": f"品牌 {brand_id} 未配置IM平台"}

        sync_log = IMSyncLog(
            id=uuid.uuid4(),
            brand_id=brand_id,
            im_platform=config.im_platform.value if hasattr(config.im_platform, "value") else str(config.im_platform),
            trigger=trigger,
            status="running",
            started_at=datetime.utcnow(),
        )
        self.db.add(sync_log)
        await self.db.flush()

        stats = {
            "added": 0,
            "updated": 0,
            "disabled": 0,
            "user_created": 0,
            "user_disabled": 0,
            "errors": [],
        }

        try:
            adapter = await self._get_adapter(config)
            platform_members = await adapter.fetch_all_members()
            sync_log.total_platform_members = len(platform_members)

            is_wechat = config.im_platform == IMPlatform.WECHAT_WORK
            userid_field = "wechat_userid" if is_wechat else "dingtalk_userid"

            # 获取该品牌所有门店
            from ..models.store import Store

            store_result = await self.db.execute(select(Store.id).where(Store.brand_id == brand_id))
            brand_store_ids = [r[0] for r in store_result.all()]
            default_store = config.default_store_id or (brand_store_ids[0] if brand_store_ids else None)

            if not default_store:
                raise ValueError("品牌下无门店，无法同步员工")

            # 获取本地该品牌所有人员（按 im_userid 索引）
            local_employees = {}
            for store_id in brand_store_ids:
                emp_result = await self.db.execute(
                    select(Person).where(Person.store_id == store_id)
                )
                for person in emp_result.scalars().all():
                    im_uid = getattr(person, userid_field, None)
                    if im_uid:
                        local_employees[im_uid] = person

            # 平台上有的 userid 集合
            platform_uids = set()

            for member in platform_members:
                platform_uids.add(member.userid)

                if not member.is_active:
                    # 平台上已离职
                    if member.userid in local_employees:
                        person = local_employees[member.userid]
                        if person.is_active:
                            await self._disable_person(person, config, stats)
                    continue

                if member.userid in local_employees:
                    # 更新现有人员
                    person = local_employees[member.userid]
                    changed = self._update_person_fields(person, member)
                    if changed:
                        stats["updated"] += 1
                    # 确保在职状态
                    if not person.is_active:
                        person.is_active = True
                        person.career_stage = "regular"
                        stats["updated"] += 1
                else:
                    # 新增人员 — 按部门映射门店
                    resolved_store = self._resolve_store_by_dept(member.department, config, default_store)
                    try:
                        await self._create_person(member, resolved_store, userid_field, config, stats)
                    except Exception as e:
                        stats["errors"].append(
                            {
                                "userid": member.userid,
                                "name": member.name,
                                "error": str(e),
                            }
                        )

            # 本地有但平台无 → 标记离职
            for im_uid, person in local_employees.items():
                if im_uid not in platform_uids and person.is_active:
                    await self._disable_person(person, config, stats)

            # 更新配置的同步状态
            config.last_sync_at = datetime.utcnow()
            config.last_sync_status = "success" if not stats["errors"] else "partial"
            config.last_sync_message = f"同步完成: +{stats['added']} ~{stats['updated']} -{stats['disabled']}"
            config.last_sync_stats = {
                "added": stats["added"],
                "updated": stats["updated"],
                "disabled": stats["disabled"],
                "user_created": stats["user_created"],
                "user_disabled": stats["user_disabled"],
            }

            # 更新日志
            sync_log.status = config.last_sync_status
            sync_log.message = config.last_sync_message
            sync_log.added_count = stats["added"]
            sync_log.updated_count = stats["updated"]
            sync_log.disabled_count = stats["disabled"]
            sync_log.user_created_count = stats["user_created"]
            sync_log.user_disabled_count = stats["user_disabled"]
            sync_log.error_count = len(stats["errors"])
            sync_log.errors = stats["errors"] if stats["errors"] else None
            sync_log.finished_at = datetime.utcnow()

            await self.db.commit()

            logger.info(
                "im_sync_completed",
                brand_id=brand_id,
                platform=config.im_platform.value if hasattr(config.im_platform, "value") else str(config.im_platform),
                added=stats["added"],
                updated=stats["updated"],
                disabled=stats["disabled"],
            )

            return {
                "brand_id": brand_id,
                "platform": config.im_platform.value if hasattr(config.im_platform, "value") else str(config.im_platform),
                "total_platform_members": len(platform_members),
                "added": stats["added"],
                "updated": stats["updated"],
                "disabled": stats["disabled"],
                "user_created": stats["user_created"],
                "user_disabled": stats["user_disabled"],
                "error_count": len(stats["errors"]),
                "errors": stats["errors"][:10],
                "message": config.last_sync_message,
            }

        except Exception as e:
            sync_log.status = "failed"
            sync_log.message = str(e)
            sync_log.finished_at = datetime.utcnow()
            config.last_sync_status = "failed"
            config.last_sync_message = str(e)
            await self.db.commit()
            logger.error("im_sync_failed", brand_id=brand_id, error=str(e))
            raise

    # ── 增量事件处理（回调触发）──

    async def handle_member_event(
        self,
        brand_id: str,
        event_type: str,
        member_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        处理 IM 平台通讯录变更事件（企微/钉钉回调）。

        event_type:
        - create_user / user_add_org   → 新增员工
        - update_user / user_modify_org → 更新员工
        - delete_user / user_leave_org  → 员工离职
        """
        config = await self._get_config(brand_id)
        if not config:
            return {"error": f"品牌 {brand_id} 未配置IM平台"}

        is_wechat = config.im_platform == IMPlatform.WECHAT_WORK
        userid_field = "wechat_userid" if is_wechat else "dingtalk_userid"

        userid = member_data.get("UserID") or member_data.get("userid")
        if not userid:
            return {"error": "missing userid"}

        # 查本地
        from ..models.store import Store

        store_result = await self.db.execute(select(Store.id).where(Store.brand_id == brand_id))
        brand_store_ids = [r[0] for r in store_result.all()]
        default_store = config.default_store_id or (brand_store_ids[0] if brand_store_ids else None)

        # 查现有人员
        emp_result = await self.db.execute(
            select(Person).where(getattr(Person, userid_field) == userid)
        )
        existing_person = emp_result.scalar_one_or_none()

        stats = {
            "added": 0,
            "updated": 0,
            "disabled": 0,
            "user_created": 0,
            "user_disabled": 0,
            "errors": [],
        }

        if event_type in ("create_user", "user_add_org"):
            if existing_person:
                # 已存在，激活
                existing_person.is_active = True
                existing_person.career_stage = "regular"
                stats["updated"] += 1
            else:
                # 拉取详情
                try:
                    adapter = await self._get_adapter(config)
                    member = await self._fetch_member_detail(adapter, userid, is_wechat)
                    if member and default_store:
                        await self._create_person(member, default_store, userid_field, config, stats)
                except Exception as e:
                    stats["errors"].append({"userid": userid, "error": str(e)})

        elif event_type in ("update_user", "user_modify_org"):
            if existing_person:
                try:
                    adapter = await self._get_adapter(config)
                    member = await self._fetch_member_detail(adapter, userid, is_wechat)
                    if member:
                        self._update_person_fields(existing_person, member)
                        stats["updated"] += 1
                except Exception as e:
                    stats["errors"].append({"userid": userid, "error": str(e)})

        elif event_type in ("delete_user", "user_leave_org"):
            if existing_person and existing_person.is_active:
                await self._disable_person(existing_person, config, stats)

        # 记录日志
        sync_log = IMSyncLog(
            id=uuid.uuid4(),
            brand_id=brand_id,
            im_platform=config.im_platform.value if hasattr(config.im_platform, "value") else str(config.im_platform),
            trigger="callback",
            status="success" if not stats["errors"] else "partial",
            message=f"event={event_type}, userid={userid}",
            total_platform_members=0,
            added_count=stats["added"],
            updated_count=stats["updated"],
            disabled_count=stats["disabled"],
            user_created_count=stats["user_created"],
            user_disabled_count=stats["user_disabled"],
            error_count=len(stats["errors"]),
            errors=stats["errors"] if stats["errors"] else None,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
        )
        self.db.add(sync_log)
        await self.db.commit()

        return {
            "event_type": event_type,
            "userid": userid,
            "added": stats["added"],
            "updated": stats["updated"],
            "disabled": stats["disabled"],
        }

    # ── 内部方法 ──

    async def _fetch_member_detail(self, adapter: IMPlatformAdapter, userid: str, is_wechat: bool) -> Optional[PlatformMember]:
        """从平台拉取单个成员详情"""
        token = await adapter.get_access_token()
        async with httpx.AsyncClient() as client:
            if is_wechat:
                resp = await client.get(
                    f"https://qyapi.weixin.qq.com/cgi-bin/user/get",
                    params={"access_token": token, "userid": userid},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    return None
                return PlatformMember(
                    userid=userid,
                    name=data.get("name", ""),
                    mobile=data.get("mobile"),
                    email=data.get("email"),
                    position=data.get("position"),
                    department=str(data.get("department", [])),
                    is_active=data.get("status", 1) == 1,
                    raw=data,
                )
            else:
                resp = await client.post(
                    f"https://oapi.dingtalk.com/topapi/v2/user/get",
                    params={"access_token": token},
                    json={"userid": userid},
                    timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    return None
                u = data.get("result", {})
                return PlatformMember(
                    userid=userid,
                    name=u.get("name", ""),
                    mobile=u.get("mobile"),
                    email=u.get("email"),
                    position=u.get("title"),
                    department=str(u.get("dept_id_list", [])),
                    is_active=u.get("active", True),
                    raw=u,
                )

    async def _create_person(
        self,
        member: PlatformMember,
        store_id: str,
        userid_field: str,
        config: BrandIMConfig,
        stats: Dict,
    ):
        """创建新 Person + EmploymentAssignment + 可选创建系统账号"""
        emp_id = f"EMP_{uuid.uuid4().hex[:8].upper()}"
        person = Person(
            legacy_employee_id=emp_id,
            store_id=store_id,
            name=member.name,
            phone=member.mobile,
            email=member.email,
            is_active=True,
            career_stage="regular",
        )
        setattr(person, userid_field, member.userid)
        self.db.add(person)
        await self.db.flush()  # 获取 person.id

        # 创建在岗关系
        mapped_position = self._map_position(member.position)
        ea = EmploymentAssignment(
            person_id=person.id,
            org_node_id=store_id,
            position=mapped_position,
            employment_type="full_time",
            start_date=date.today(),
            status="active",
        )
        self.db.add(ea)
        stats["added"] += 1

        # 自动创建系统账号
        if config.auto_create_user:
            await self._create_user_for_person(person, member, config, userid_field, stats)

        # 触发入职引导机器人（Phase 4 #10）
        try:
            from ..services.im_onboarding_robot import IMOnboardingRobot

            robot = IMOnboardingRobot(self.db)
            await robot.trigger_onboarding(
                person.legacy_employee_id, brand_id=config.brand_id,
            )
        except Exception as e:
            logger.warning(
                "im_sync.onboarding_trigger_failed",
                person_id=str(person.id), error=str(e),
            )

    async def _create_user_for_person(
        self,
        person: Person,
        member: PlatformMember,
        config: BrandIMConfig,
        userid_field: str,
        stats: Dict,
    ):
        """为人员创建系统账号"""
        username = member.userid
        existing = await self.db.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            return

        role = self._determine_role(member.position)
        is_wechat = userid_field == "wechat_userid"

        user = User(
            id=uuid.uuid4(),
            username=username,
            email=member.email or f"{username}@im.sync",
            hashed_password=get_password_hash(f"im_sync_{member.userid}"),
            full_name=member.name,
            role=role,
            is_active=True,
            brand_id=config.brand_id,
            store_id=person.store_id,
            phone=member.mobile,
        )
        if is_wechat:
            user.wechat_user_id = member.userid
        else:
            user.dingtalk_user_id = member.userid

        self.db.add(user)
        stats["user_created"] += 1

    async def _disable_person(
        self,
        person: Person,
        config: BrandIMConfig,
        stats: Dict,
    ):
        """标记人员离职 + 结束在岗关系 + 禁用系统账号"""
        person.is_active = False
        person.career_stage = "resigned"
        stats["disabled"] += 1

        # 结束所有在岗关系
        ea_result = await self.db.execute(
            select(EmploymentAssignment).where(
                and_(
                    EmploymentAssignment.person_id == person.id,
                    EmploymentAssignment.status == "active",
                )
            )
        )
        for ea in ea_result.scalars().all():
            ea.status = "ended"
            ea.end_date = date.today()

        if config.auto_disable_user:
            is_wechat = config.im_platform == IMPlatform.WECHAT_WORK
            if is_wechat and person.wechat_userid:
                user_result = await self.db.execute(
                    select(User).where(User.wechat_user_id == person.wechat_userid)
                )
            elif not is_wechat and person.dingtalk_userid:
                user_result = await self.db.execute(
                    select(User).where(User.dingtalk_user_id == person.dingtalk_userid)
                )
            else:
                return

            user = user_result.scalar_one_or_none()
            if user and user.is_active:
                user.is_active = False
                stats["user_disabled"] += 1

    def _update_person_fields(self, person: Person, member: PlatformMember) -> bool:
        """更新人员字段，返回是否有变更"""
        changed = False
        if member.name and member.name != person.name:
            person.name = member.name
            changed = True
        if member.mobile and member.mobile != person.phone:
            person.phone = member.mobile
            changed = True
        if member.email and member.email != person.email:
            person.email = member.email
            changed = True
        # position 更新需要通过 EmploymentAssignment，此处仅做标记
        # 全量同步中 position 变更需要单独处理（暂不自动更新 EA）
        return changed

    def _resolve_store_by_dept(
        self,
        department_name: Optional[str],
        config: BrandIMConfig,
        fallback_store: str,
    ) -> str:
        """按 IM 部门名称映射到屯象OS门店ID"""
        mapping = config.department_store_mapping
        if not mapping or not department_name:
            return fallback_store
        # 精确匹配
        if department_name in mapping:
            return mapping[department_name]
        # 模糊匹配：部门名包含映射中的关键字
        for keyword, store_id in mapping.items():
            if keyword in department_name:
                return store_id
        return fallback_store

    def _map_position(self, platform_position: Optional[str]) -> str:
        """IM 平台职位 → 屯象OS标准岗位映射"""
        if not platform_position:
            return "waiter"
        pos = platform_position.lower()
        mapping = {
            "店长": "store_manager",
            "经理": "store_manager",
            "manager": "store_manager",
            "助理": "assistant_manager",
            "副店长": "assistant_manager",
            "楼面": "floor_manager",
            "前厅经理": "floor_manager",
            "领班": "team_leader",
            "厨师长": "head_chef",
            "行政总厨": "head_chef",
            "厨师": "chef",
            "炒锅": "chef",
            "切配": "chef",
            "档口": "station_manager",
            "服务员": "waiter",
            "库管": "warehouse_manager",
            "仓管": "warehouse_manager",
            "财务": "finance",
            "会计": "finance",
            "出纳": "finance",
            "采购": "procurement",
            "客户经理": "customer_manager",
        }
        for keyword, role in mapping.items():
            if keyword in pos:
                return role
        return "waiter"

    def _determine_role(self, position: Optional[str]) -> UserRole:
        """根据职位确定用户角色"""
        mapped = self._map_position(position)
        try:
            return UserRole(mapped)
        except ValueError:
            return UserRole.WAITER
