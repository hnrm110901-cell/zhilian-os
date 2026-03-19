"""
IM 组织架构同步服务 — IM 部门层级 → 屯象OS 门店/区域结构

核心功能：
1. 从企微/钉钉拉取完整部门树
2. 按映射规则将部门对应到 Store（门店）
3. 支持自动创建门店（当部门无对应门店时）
4. 同步部门层级到 Store.region 字段

设计原则：
- 复用 IMSyncService 的适配器获取部门列表
- 复用 BrandIMConfig.department_store_mapping 作为映射源
- 不新建表，利用 Store 模型已有字段
"""

import uuid as uuid_mod
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.brand_im_config import BrandIMConfig, IMPlatform
from ..models.store import Store
from ..services.im_sync_service import IMSyncService

logger = structlog.get_logger()


class IMOrgSyncService:
    """IM 组织架构 → 屯象OS 门店结构同步"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_org_structure(
        self,
        brand_id: str,
        auto_create_store: bool = False,
    ) -> Dict[str, Any]:
        """
        同步 IM 平台组织架构到门店结构。

        流程：
        1. 拉取 IM 平台部门树
        2. 构建部门层级关系
        3. 按 department_store_mapping 匹配现有门店
        4. 更新 Store.region 为上级部门名
        5. 可选：为无对应门店的部门自动创建门店

        Returns:
            {
                "departments_total": int,
                "matched": int,
                "region_updated": int,
                "stores_created": int,
                "unmatched": [...],
            }
        """
        # 获取品牌IM配置
        result = await self.db.execute(
            select(BrandIMConfig).where(
                and_(
                    BrandIMConfig.brand_id == brand_id,
                    BrandIMConfig.is_active.is_(True),
                )
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            return {"error": f"品牌 {brand_id} 未配置IM平台"}

        # 拉取部门列表
        sync_service = IMSyncService(self.db)
        try:
            adapter = await sync_service._get_adapter(config)
            raw_departments = await adapter.fetch_departments()
        except Exception as e:
            return {"error": f"拉取部门列表失败: {str(e)}"}

        # 统一部门数据格式
        departments = self._normalize_departments(raw_departments, config.im_platform)

        # 构建部门层级映射 {dept_id: dept_info}
        dept_map = {d["id"]: d for d in departments}
        # 为每个部门计算完整路径（用于 region 字段）
        for dept in departments:
            dept["path"] = self._build_dept_path(dept, dept_map)

        # 获取已有门店
        store_result = await self.db.execute(select(Store).where(Store.brand_id == brand_id))
        existing_stores = {s.name: s for s in store_result.scalars().all()}

        # 获取部门→门店映射
        mapping = config.department_store_mapping or {}

        stats = {
            "departments_total": len(departments),
            "matched": 0,
            "region_updated": 0,
            "stores_created": 0,
            "unmatched": [],
        }

        for dept in departments:
            dept_name = dept["name"]
            dept_id_str = str(dept["id"])
            parent_name = dept.get("parent_name", "")

            # 尝试匹配门店
            matched_store_id = None

            # 1. 检查 department_store_mapping（按名称或ID）
            if dept_name in mapping:
                matched_store_id = mapping[dept_name]
            elif dept_id_str in mapping:
                matched_store_id = mapping[dept_id_str]

            # 2. 按门店名匹配
            if not matched_store_id and dept_name in existing_stores:
                matched_store_id = existing_stores[dept_name].id

            if matched_store_id:
                stats["matched"] += 1

                # 更新 region 字段为上级部门路径
                store_result2 = await self.db.execute(select(Store).where(Store.id == matched_store_id))
                store = store_result2.scalar_one_or_none()
                if store and parent_name:
                    region = dept.get("path", parent_name)
                    if store.region != region:
                        store.region = region
                        stats["region_updated"] += 1

            elif auto_create_store and self._is_leaf_department(dept, departments):
                # 仅为叶子部门（没有子部门的）自动创建门店
                new_store = await self._create_store_from_dept(
                    dept,
                    brand_id,
                    dept.get("path", ""),
                )
                if new_store:
                    existing_stores[dept_name] = new_store
                    # 更新映射
                    if mapping is None:
                        mapping = {}
                    mapping[dept_name] = new_store.id
                    stats["stores_created"] += 1
                    stats["matched"] += 1
            else:
                stats["unmatched"].append(
                    {
                        "dept_id": dept["id"],
                        "dept_name": dept_name,
                        "parent_name": parent_name,
                        "path": dept.get("path", ""),
                    }
                )

        # 保存更新后的映射
        if stats["stores_created"] > 0:
            config.department_store_mapping = mapping

        await self.db.commit()

        logger.info(
            "im_org_sync.done",
            brand_id=brand_id,
            departments=stats["departments_total"],
            matched=stats["matched"],
            region_updated=stats["region_updated"],
            stores_created=stats["stores_created"],
        )

        return stats

    def _normalize_departments(
        self,
        raw_departments: List[Dict[str, Any]],
        platform: IMPlatform,
    ) -> List[Dict[str, Any]]:
        """统一企微/钉钉部门数据格式"""
        departments = []
        is_wechat = platform == IMPlatform.WECHAT_WORK

        for d in raw_departments:
            if is_wechat:
                departments.append(
                    {
                        "id": d.get("id"),
                        "name": d.get("name", ""),
                        "parentid": d.get("parentid", 0),
                    }
                )
            else:
                departments.append(
                    {
                        "id": d.get("dept_id"),
                        "name": d.get("name", ""),
                        "parentid": d.get("parent_id", 1),
                    }
                )

        # 补充 parent_name
        dept_name_map = {d["id"]: d["name"] for d in departments}
        for d in departments:
            d["parent_name"] = dept_name_map.get(d["parentid"], "")

        return departments

    def _build_dept_path(
        self,
        dept: Dict[str, Any],
        dept_map: Dict[Any, Dict[str, Any]],
        max_depth: int = 5,
    ) -> str:
        """构建部门层级路径，如 '华中区/长沙/五一广场店'"""
        path_parts = [dept["name"]]
        current = dept
        depth = 0

        while current.get("parentid") and depth < max_depth:
            parent = dept_map.get(current["parentid"])
            if not parent or parent["id"] == current["id"]:
                break
            # 跳过根部门（ID=1 通常是企业根节点）
            if parent["id"] in (1, "1"):
                break
            path_parts.insert(0, parent["name"])
            current = parent
            depth += 1

        return "/".join(path_parts)

    def _is_leaf_department(
        self,
        dept: Dict[str, Any],
        all_departments: List[Dict[str, Any]],
    ) -> bool:
        """判断是否为叶子部门（没有子部门）"""
        dept_id = dept["id"]
        for d in all_departments:
            if d["parentid"] == dept_id:
                return False
        return True

    async def _create_store_from_dept(
        self,
        dept: Dict[str, Any],
        brand_id: str,
        region: str,
    ) -> Optional[Store]:
        """从部门信息自动创建门店"""
        dept_name = dept["name"]
        # 生成门店编码
        code = f"IM_{str(dept['id'])[:10]}"

        # 检查编码是否已存在
        existing = await self.db.execute(select(Store).where(Store.code == code))
        if existing.scalar_one_or_none():
            return None

        store_id = f"STORE_{uuid_mod.uuid4().hex[:8].upper()}"
        store = Store(
            id=store_id,
            name=dept_name,
            code=code,
            brand_id=brand_id,
            region=region,
            is_active=True,
        )
        self.db.add(store)

        logger.info(
            "im_org_sync.store_created",
            store_id=store_id,
            name=dept_name,
            brand_id=brand_id,
            region=region,
        )
        return store
