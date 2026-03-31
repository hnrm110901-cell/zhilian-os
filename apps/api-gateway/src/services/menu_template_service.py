"""
集团菜单模板服务

MenuTemplateService 负责：
- 模板创建、菜品条目管理、发布到门店
- 门店菜品覆盖（个性化定价/下架/改名）
- 渠道定价及时段定价的设置与查询
- 计算门店有效菜单（含四级价格优先级逻辑）
- Redis 缓存（TTL=300秒）

定价优先级（高→低）：
  1. 时段价格（匹配当前时间的 TimePeriodPrice 规则）
  2. 渠道价格（DishChannelPrice 对应 channel）
  3. 门店覆盖价格（StoreDishOverride.custom_price_fen）
  4. 模板基准价（MenuTemplateItem.base_price_fen）
"""

import json
import uuid
from datetime import datetime, time
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from src.core.database import get_db_session
from src.models.channel_pricing import DishChannelPrice, TimePeriodPrice
from src.models.menu_template import (
    MenuTemplate,
    MenuTemplateItem,
    StoreDishOverride,
    StoreMenuDeployment,
)
from src.services.base_service import BaseService

logger = structlog.get_logger()

# Redis 缓存 TTL（秒）
MENU_CACHE_TTL = 300


def _get_time_slot(dt: datetime) -> str:
    """将时间规整为 HH 小时槽，用于 Redis 缓存 key"""
    return dt.strftime("%H")


class MenuTemplateService(BaseService):
    """集团菜单模板+多渠道定价服务"""

    def __init__(self, store_id: Optional[str] = None):
        super().__init__(store_id=store_id)
        self._redis = None  # 延迟初始化 Redis

    async def _get_redis(self):
        """延迟获取 Redis 客户端（降级友好）"""
        if self._redis is None:
            try:
                import aioredis

                from src.core.config import settings

                self._redis = await aioredis.from_url(
                    settings.REDIS_URL, encoding="utf-8", decode_responses=True
                )
            except Exception as e:
                logger.warning("Redis 连接失败，缓存降级", error=str(e))
                self._redis = None
        return self._redis

    async def _cache_get(self, key: str) -> Optional[Any]:
        """从 Redis 读取缓存，失败时返回 None（离线降级）"""
        try:
            redis = await self._get_redis()
            if redis is None:
                return None
            raw = await redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("Redis get 失败", key=key, error=str(e))
        return None

    async def _cache_set(self, key: str, value: Any, ttl: int = MENU_CACHE_TTL):
        """写入 Redis 缓存，失败时静默忽略"""
        try:
            redis = await self._get_redis()
            if redis is None:
                return
            await redis.setex(key, ttl, json.dumps(value, default=str))
        except Exception as e:
            logger.warning("Redis set 失败", key=key, error=str(e))

    async def _invalidate_store_menu_cache(self, store_id: str):
        """清除指定门店的菜单缓存（所有渠道和时段）"""
        try:
            redis = await self._get_redis()
            if redis is None:
                return
            pattern = f"menu:store:{store_id}:*"
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
        except Exception as e:
            logger.warning("Redis cache invalidation 失败", store_id=store_id, error=str(e))

    # ------------------------------------------------------------------ #
    #  模板管理                                                             #
    # ------------------------------------------------------------------ #

    async def create_template(
        self, brand_id: str, creator_id: str, name: str
    ) -> Dict:
        """
        创建草稿模板

        Args:
            brand_id: 品牌ID（UUID字符串）
            creator_id: 创建人ID（UUID字符串）
            name: 模板名称

        Returns:
            dict: 新建模板信息
        """
        async with get_db_session() as session:
            template = MenuTemplate(
                id=uuid.uuid4(),
                brand_id=uuid.UUID(str(brand_id)),
                created_by=uuid.UUID(str(creator_id)),
                name=name,
                status="draft",
                apply_scope="all_stores",
                version=1,
            )
            session.add(template)
            await session.flush()
            await session.refresh(template)

            logger.info(
                "菜单模板已创建",
                template_id=str(template.id),
                brand_id=brand_id,
                name=name,
            )
            return {
                "id": str(template.id),
                "name": template.name,
                "brand_id": str(template.brand_id),
                "status": template.status,
                "version": template.version,
                "created_at": template.created_at.isoformat() if template.created_at else None,
            }

    async def add_template_item(
        self,
        template_id: str,
        dish_master_id: str,
        base_price_fen: int,
        category: str = "",
        allow_adjust: bool = True,
        max_adjust_rate: float = 0.2,
        is_required: bool = False,
    ) -> Dict:
        """
        向模板添加菜品条目

        Args:
            template_id: 模板ID
            dish_master_id: 集团菜品主档ID
            base_price_fen: 基准价格（分）
            category: 分类名称
            allow_adjust: 是否允许门店调价
            max_adjust_rate: 最大调价幅度（如 0.2 = 20%）
            is_required: 是否为总部强制菜品

        Returns:
            dict: 新建模板条目信息

        Raises:
            ValueError: 模板不存在或不是草稿状态
        """
        async with get_db_session() as session:
            # 校验模板存在
            result = await session.execute(
                select(MenuTemplate).where(
                    MenuTemplate.id == uuid.UUID(str(template_id))
                )
            )
            template = result.scalar_one_or_none()
            if not template:
                raise ValueError(f"模板不存在: {template_id}")

            # 计算排序号（当前条目数 + 1）
            count_result = await session.execute(
                select(MenuTemplateItem).where(
                    MenuTemplateItem.template_id == uuid.UUID(str(template_id))
                )
            )
            current_items = count_result.scalars().all()
            sort_order = len(current_items) + 1

            item = MenuTemplateItem(
                id=uuid.uuid4(),
                template_id=uuid.UUID(str(template_id)),
                dish_master_id=uuid.UUID(str(dish_master_id)),
                category=category,
                base_price_fen=base_price_fen,
                sort_order=sort_order,
                allow_store_adjust=allow_adjust,
                max_adjust_rate=max_adjust_rate,
                is_required=is_required,
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)

            return {
                "id": str(item.id),
                "template_id": str(item.template_id),
                "dish_master_id": str(item.dish_master_id),
                "category": item.category,
                "base_price_fen": item.base_price_fen,
                "sort_order": item.sort_order,
                "allow_store_adjust": item.allow_store_adjust,
                "max_adjust_rate": item.max_adjust_rate,
                "is_required": item.is_required,
            }

    async def publish_template(
        self,
        template_id: str,
        publisher_id: str,
        target_store_ids: Optional[List[str]] = None,
    ) -> Dict:
        """
        发布模板到门店

        1. 校验模板状态必须是 draft
        2. 更新状态为 active + published_at
        3. 批量创建 StoreMenuDeployment（支持批量到多门店）

        Args:
            template_id: 模板ID
            publisher_id: 发布人ID
            target_store_ids: 目标门店ID列表（None=当前门店）

        Returns:
            dict: {deployed_count, store_ids, template_id}

        Raises:
            ValueError: 模板不存在
            RuntimeError: 模板不是 draft 状态
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(MenuTemplate).where(
                    MenuTemplate.id == uuid.UUID(str(template_id))
                )
            )
            template = result.scalar_one_or_none()
            if not template:
                raise ValueError(f"模板不存在: {template_id}")
            if template.status != "draft":
                raise RuntimeError(
                    f"模板状态必须是 draft 才能发布，当前状态: {template.status}"
                )

            # 更新模板状态
            template.status = "active"
            template.published_at = datetime.utcnow()
            session.add(template)

            # 确定目标门店列表
            if not target_store_ids:
                store_id = self.get_store_id()
                store_ids = [store_id] if store_id else []
            else:
                store_ids = target_store_ids

            deployed_store_ids = []
            now = datetime.utcnow()
            pub_uuid = uuid.UUID(str(publisher_id))
            tmpl_uuid = uuid.UUID(str(template_id))

            for sid in store_ids:
                if not sid:
                    continue
                store_uuid = uuid.UUID(str(sid))
                # 检查是否已有部署记录
                existing = await session.execute(
                    select(StoreMenuDeployment).where(
                        and_(
                            StoreMenuDeployment.store_id == store_uuid,
                            StoreMenuDeployment.template_id == tmpl_uuid,
                        )
                    )
                )
                dep = existing.scalar_one_or_none()
                if dep:
                    # 更新已有记录
                    dep.deployed_at = now
                    dep.deployed_by = pub_uuid
                    session.add(dep)
                else:
                    dep = StoreMenuDeployment(
                        id=uuid.uuid4(),
                        store_id=store_uuid,
                        template_id=tmpl_uuid,
                        deployed_at=now,
                        deployed_by=pub_uuid,
                        override_count=0,
                    )
                    session.add(dep)
                deployed_store_ids.append(str(sid))

            await session.flush()

            logger.info(
                "模板已发布",
                template_id=template_id,
                deployed_count=len(deployed_store_ids),
            )
            return {
                "template_id": template_id,
                "deployed_count": len(deployed_store_ids),
                "store_ids": deployed_store_ids,
            }

    # ------------------------------------------------------------------ #
    #  门店有效菜单                                                          #
    # ------------------------------------------------------------------ #

    async def get_store_effective_menu(
        self,
        store_id: str,
        channel: str = "dine_in",
        current_time: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        获取门店有效菜单（核心方法）

        定价优先级（高→低）：
        1. 时段价格
        2. 渠道价格
        3. 门店覆盖价格
        4. 模板基准价

        过滤 is_available=False 的条目。
        结果缓存至 Redis，key=menu:store:{store_id}:{channel}:{time_slot}，TTL=300s

        Args:
            store_id: 门店ID
            channel: 渠道（dine_in/meituan/eleme/douyin/miniprogram/corporate）
            current_time: 当前时间（None=now，用于测试注入）

        Returns:
            list[dict]: 有效菜单条目列表
        """
        if current_time is None:
            current_time = datetime.utcnow()

        time_slot = _get_time_slot(current_time)
        cache_key = f"menu:store:{store_id}:{channel}:{time_slot}"

        # 先查缓存
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        store_uuid = uuid.UUID(str(store_id))

        async with get_db_session() as session:
            # 1. 查找该门店的活跃部署
            dep_result = await session.execute(
                select(StoreMenuDeployment)
                .join(
                    MenuTemplate,
                    MenuTemplate.id == StoreMenuDeployment.template_id,
                )
                .where(
                    and_(
                        StoreMenuDeployment.store_id == store_uuid,
                        MenuTemplate.status == "active",
                    )
                )
                .order_by(StoreMenuDeployment.deployed_at.desc())
                .limit(1)
            )
            deployment = dep_result.scalar_one_or_none()
            if not deployment:
                return []

            # 2. 查询模板条目
            items_result = await session.execute(
                select(MenuTemplateItem).where(
                    MenuTemplateItem.template_id == deployment.template_id
                ).order_by(MenuTemplateItem.sort_order)
            )
            template_items = items_result.scalars().all()
            if not template_items:
                return []

            item_ids = [item.id for item in template_items]

            # 3. 批量查询门店覆盖
            overrides_result = await session.execute(
                select(StoreDishOverride).where(
                    and_(
                        StoreDishOverride.store_id == store_uuid,
                        StoreDishOverride.template_item_id.in_(item_ids),
                    )
                )
            )
            overrides_map = {
                ov.template_item_id: ov
                for ov in overrides_result.scalars().all()
            }

            # 4. 批量查询渠道定价
            dish_ids = [item.dish_master_id for item in template_items]
            channel_prices_result = await session.execute(
                select(DishChannelPrice).where(
                    and_(
                        DishChannelPrice.store_id == store_uuid,
                        DishChannelPrice.dish_id.in_(dish_ids),
                        DishChannelPrice.channel == channel,
                        DishChannelPrice.is_active.is_(True),
                    )
                )
            )
            channel_price_map = {
                cp.dish_id: cp.price_fen
                for cp in channel_prices_result.scalars().all()
            }

            # 5. 查询时段定价规则
            current_time_only = current_time.time()
            current_weekday = current_time.isoweekday()  # 1=周一，7=周日
            period_result = await session.execute(
                select(TimePeriodPrice).where(
                    and_(
                        TimePeriodPrice.store_id == store_uuid,
                        TimePeriodPrice.is_active.is_(True),
                    )
                )
            )
            active_period_rules = period_result.scalars().all()

            # 筛选当前时间命中的时段规则
            matched_period_rules = []
            for rule in active_period_rules:
                if current_weekday not in (rule.weekdays or []):
                    continue
                if not (rule.start_time <= current_time_only <= rule.end_time):
                    continue
                matched_period_rules.append(rule)

            # 6. 组装有效菜单
            effective_menu = []
            for item in template_items:
                override = overrides_map.get(item.id)

                # 过滤不可售菜品
                if override and not override.is_available:
                    continue

                # 确定有效价格（四级优先级）
                effective_price = item.base_price_fen  # 第4级：模板基准价

                # 第3级：门店覆盖价
                if override and override.custom_price_fen is not None:
                    effective_price = override.custom_price_fen

                # 第2级：渠道价格
                ch_price = channel_price_map.get(item.dish_master_id)
                if ch_price is not None:
                    effective_price = ch_price

                # 第1级：时段价格（优先使用 fixed_price_json，其次 discount_rate）
                for rule in matched_period_rules:
                    dish_id_str = str(item.dish_master_id)
                    if rule.fixed_price_json and dish_id_str in rule.fixed_price_json:
                        effective_price = int(rule.fixed_price_json[dish_id_str])
                        break
                    if rule.apply_to_dishes is None or item.dish_master_id in (rule.apply_to_dishes or []):
                        if rule.discount_rate is not None:
                            effective_price = int(effective_price * rule.discount_rate)
                            break

                effective_menu.append({
                    "template_item_id": str(item.id),
                    "dish_master_id": str(item.dish_master_id),
                    "category": item.category,
                    "name": (override.custom_name if override and override.custom_name else None),
                    "effective_price_fen": effective_price,
                    "base_price_fen": item.base_price_fen,
                    "sort_order": item.sort_order,
                    "is_required": item.is_required,
                    "channel": channel,
                })

        # 写入缓存
        await self._cache_set(cache_key, effective_menu)

        return effective_menu

    # ------------------------------------------------------------------ #
    #  门店覆盖                                                              #
    # ------------------------------------------------------------------ #

    async def store_override_dish(
        self,
        store_id: str,
        template_item_id: str,
        custom_price_fen: Optional[int] = None,
        is_available: bool = True,
        custom_name: Optional[str] = None,
    ) -> Dict:
        """
        门店覆盖菜品配置

        1. 校验 custom_price_fen 不能超过 base_price * (1 + max_adjust_rate)
        2. is_required=True 的菜品不能设置 is_available=False

        Args:
            store_id: 门店ID
            template_item_id: 模板条目ID
            custom_price_fen: 自定义价格（分），None=继承模板价
            is_available: 是否上架
            custom_name: 自定义名称

        Returns:
            dict: 覆盖记录信息

        Raises:
            ValueError: 校验失败（超价/强制下架）
        """
        store_uuid = uuid.UUID(str(store_id))
        item_uuid = uuid.UUID(str(template_item_id))

        async with get_db_session() as session:
            # 查询模板条目
            item_result = await session.execute(
                select(MenuTemplateItem).where(
                    MenuTemplateItem.id == item_uuid
                )
            )
            item = item_result.scalar_one_or_none()
            if not item:
                raise ValueError(f"模板条目不存在: {template_item_id}")

            # 校验：强制菜品不能下架
            if item.is_required and not is_available:
                raise ValueError(
                    f"菜品 {template_item_id} 是总部强制菜品，不能设置下架"
                )

            # 校验：自定义价格不能超过调价上限
            if custom_price_fen is not None:
                max_price = int(item.base_price_fen * (1 + item.max_adjust_rate))
                if custom_price_fen > max_price:
                    raise ValueError(
                        f"自定义价格 {custom_price_fen} 超过最大调价上限 {max_price}（分）"
                    )

            # 查找现有覆盖记录（upsert）
            ov_result = await session.execute(
                select(StoreDishOverride).where(
                    and_(
                        StoreDishOverride.store_id == store_uuid,
                        StoreDishOverride.template_item_id == item_uuid,
                    )
                )
            )
            override = ov_result.scalar_one_or_none()

            now = datetime.utcnow()
            if override:
                override.custom_price_fen = custom_price_fen
                override.is_available = is_available
                override.custom_name = custom_name
                override.updated_at = now
            else:
                override = StoreDishOverride(
                    id=uuid.uuid4(),
                    store_id=store_uuid,
                    template_item_id=item_uuid,
                    custom_price_fen=custom_price_fen,
                    is_available=is_available,
                    custom_name=custom_name,
                    updated_at=now,
                )
                session.add(override)

                # 增加部署记录的 override_count
                dep_result = await session.execute(
                    select(StoreMenuDeployment).where(
                        and_(
                            StoreMenuDeployment.store_id == store_uuid,
                            StoreMenuDeployment.template_id == item.template_id,
                        )
                    )
                )
                dep = dep_result.scalar_one_or_none()
                if dep:
                    dep.override_count = (dep.override_count or 0) + 1
                    session.add(dep)

            await session.flush()

            # 清除该门店菜单缓存
            await self._invalidate_store_menu_cache(store_id)

            logger.info(
                "门店菜品覆盖已保存",
                store_id=store_id,
                template_item_id=template_item_id,
            )
            return {
                "id": str(override.id),
                "store_id": str(override.store_id),
                "template_item_id": str(override.template_item_id),
                "custom_price_fen": override.custom_price_fen,
                "is_available": override.is_available,
                "custom_name": override.custom_name,
            }

    # ------------------------------------------------------------------ #
    #  渠道定价                                                              #
    # ------------------------------------------------------------------ #

    async def set_channel_price(
        self, store_id: str, dish_id: str, channel: str, price_fen: int
    ) -> Dict:
        """
        设置/更新渠道定价（upsert）

        Args:
            store_id: 门店ID
            dish_id: 菜品ID（对应 MenuTemplateItem.dish_master_id）
            channel: 渠道名称
            price_fen: 渠道价格（分）

        Returns:
            dict: 渠道定价记录
        """
        store_uuid = uuid.UUID(str(store_id))
        dish_uuid = uuid.UUID(str(dish_id))

        async with get_db_session() as session:
            result = await session.execute(
                select(DishChannelPrice).where(
                    and_(
                        DishChannelPrice.store_id == store_uuid,
                        DishChannelPrice.dish_id == dish_uuid,
                        DishChannelPrice.channel == channel,
                    )
                )
            )
            cp = result.scalar_one_or_none()
            if cp:
                cp.price_fen = price_fen
                cp.is_active = True
            else:
                cp = DishChannelPrice(
                    id=uuid.uuid4(),
                    store_id=store_uuid,
                    dish_id=dish_uuid,
                    channel=channel,
                    price_fen=price_fen,
                    is_active=True,
                )
                session.add(cp)
            await session.flush()

            # 清除该门店菜单缓存
            await self._invalidate_store_menu_cache(store_id)

            return {
                "id": str(cp.id),
                "store_id": str(cp.store_id),
                "dish_id": str(cp.dish_id),
                "channel": cp.channel,
                "price_fen": cp.price_fen,
                "is_active": cp.is_active,
            }

    # ------------------------------------------------------------------ #
    #  时段定价                                                              #
    # ------------------------------------------------------------------ #

    async def set_time_period_price(
        self,
        store_id: str,
        name: str,
        period_type: str,
        start_time: time,
        end_time: time,
        weekdays: List[int],
        discount_rate: Optional[float] = None,
        fixed_prices: Optional[Dict[str, int]] = None,
    ) -> Dict:
        """
        创建时段定价规则

        Args:
            store_id: 门店ID
            name: 规则名称
            period_type: 时段类型（lunch/dinner/breakfast/late_night/holiday/weekend）
            start_time: 开始时间
            end_time: 结束时间
            weekdays: 适用星期列表（[1-7]，1=周一）
            discount_rate: 折扣率（如 0.8=八折），与 fixed_prices 二选一
            fixed_prices: 固定价格映射 {dish_id_str: price_fen}

        Returns:
            dict: 时段定价规则记录
        """
        store_uuid = uuid.UUID(str(store_id))

        async with get_db_session() as session:
            rule = TimePeriodPrice(
                id=uuid.uuid4(),
                store_id=store_uuid,
                name=name,
                period_type=period_type,
                start_time=start_time,
                end_time=end_time,
                weekdays=weekdays,
                discount_rate=discount_rate,
                fixed_price_json=fixed_prices,
                is_active=True,
            )
            session.add(rule)
            await session.flush()
            await session.refresh(rule)

            # 清除该门店菜单缓存
            await self._invalidate_store_menu_cache(store_id)

            return {
                "id": str(rule.id),
                "store_id": str(rule.store_id),
                "name": rule.name,
                "period_type": rule.period_type,
                "start_time": rule.start_time.isoformat(),
                "end_time": rule.end_time.isoformat(),
                "weekdays": rule.weekdays,
                "discount_rate": rule.discount_rate,
                "fixed_price_json": rule.fixed_price_json,
                "is_active": rule.is_active,
            }

    # ------------------------------------------------------------------ #
    #  单菜品有效价格查询                                                      #
    # ------------------------------------------------------------------ #

    async def get_effective_price(
        self,
        store_id: str,
        dish_id: str,
        channel: str = "dine_in",
        timestamp: Optional[datetime] = None,
    ) -> int:
        """
        查询单个菜品实时有效价格（分）

        按优先级：时段价 > 渠道价 > 门店覆盖价 > 模板基准价

        Args:
            store_id: 门店ID
            dish_id: 菜品ID（dish_master_id）
            channel: 渠道
            timestamp: 查询时间点（None=now）

        Returns:
            int: 有效价格（分）

        Raises:
            ValueError: 菜品在门店无效菜单中找不到
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # 复用 get_store_effective_menu 并过滤
        menu = await self.get_store_effective_menu(
            store_id=store_id, channel=channel, current_time=timestamp
        )
        for item in menu:
            if item["dish_master_id"] == str(dish_id):
                return item["effective_price_fen"]

        raise ValueError(f"菜品 {dish_id} 在门店 {store_id} 的有效菜单中不存在")

    # ------------------------------------------------------------------ #
    #  模板覆盖率统计                                                         #
    # ------------------------------------------------------------------ #

    async def get_template_coverage(self, brand_id: str) -> Dict:
        """
        查询品牌模板覆盖情况：已部署/未部署门店数

        Args:
            brand_id: 品牌ID

        Returns:
            dict: {total_templates, active_templates, deployed_store_count,
                   template_details: [{template_id, name, deployed_count}]}
        """
        brand_uuid = uuid.UUID(str(brand_id))

        async with get_db_session() as session:
            # 查询品牌下所有模板
            templates_result = await session.execute(
                select(MenuTemplate).where(
                    MenuTemplate.brand_id == brand_uuid
                ).order_by(MenuTemplate.created_at.desc())
            )
            templates = templates_result.scalars().all()

            template_details = []
            total_deployed = 0
            for tmpl in templates:
                # 查询每个模板的部署数
                dep_result = await session.execute(
                    select(StoreMenuDeployment).where(
                        StoreMenuDeployment.template_id == tmpl.id
                    )
                )
                deps = dep_result.scalars().all()
                dep_count = len(deps)
                total_deployed += dep_count
                template_details.append({
                    "template_id": str(tmpl.id),
                    "name": tmpl.name,
                    "status": tmpl.status,
                    "version": tmpl.version,
                    "deployed_count": dep_count,
                    "published_at": tmpl.published_at.isoformat() if tmpl.published_at else None,
                })

            active_templates = [t for t in templates if t.status == "active"]

            return {
                "brand_id": brand_id,
                "total_templates": len(templates),
                "active_templates": len(active_templates),
                "deployed_store_count": total_deployed,
                "template_details": template_details,
            }
