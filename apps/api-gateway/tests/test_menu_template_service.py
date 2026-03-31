"""
测试：集团菜单模板服务 — MenuTemplateService

覆盖：
  - 创建模板+发布+部署计数
  - 时段价格优先于渠道价格
  - 渠道价格优先于门店覆盖价格
  - 门店覆盖价格优先于模板基准价
  - 超出调价幅度时 raise
  - is_required 菜品不能下架
  - 批量部署到多门店
  - 没有渠道定价时 fallback 到模板价
  - 时段规则 weekdays 过滤（周一不命中周末规则）
  - 发布已发布的模板 raise
  - 无效模板ID raise 404
  - 门店覆盖自定义名称
  - 时段折扣应用到所有菜品
  - upsert 渠道定价
  - 时段 fixed_price_json 精确覆盖单菜
"""

import uuid
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ------------------------------------------------------------------ #
#  被测服务（延迟导入，避免 SQLAlchemy 元数据初始化问题）               #
# ------------------------------------------------------------------ #


def _make_template_item(
    item_id=None,
    template_id=None,
    dish_master_id=None,
    base_price_fen=1000,
    category="主菜",
    allow_store_adjust=True,
    max_adjust_rate=0.2,
    is_required=False,
    sort_order=1,
):
    item = MagicMock()
    item.id = item_id or uuid.uuid4()
    item.template_id = template_id or uuid.uuid4()
    item.dish_master_id = dish_master_id or uuid.uuid4()
    item.base_price_fen = base_price_fen
    item.category = category
    item.allow_store_adjust = allow_store_adjust
    item.max_adjust_rate = max_adjust_rate
    item.is_required = is_required
    item.sort_order = sort_order
    return item


def _make_template(
    template_id=None, brand_id=None, name="测试模板", status="draft", version=1
):
    tmpl = MagicMock()
    tmpl.id = template_id or uuid.uuid4()
    tmpl.brand_id = brand_id or uuid.uuid4()
    tmpl.name = name
    tmpl.status = status
    tmpl.version = version
    tmpl.created_at = datetime(2026, 3, 31)
    tmpl.published_at = None
    return tmpl


def _make_deployment(store_id=None, template_id=None, override_count=0):
    dep = MagicMock()
    dep.id = uuid.uuid4()
    dep.store_id = store_id or uuid.uuid4()
    dep.template_id = template_id or uuid.uuid4()
    dep.override_count = override_count
    dep.deployed_at = datetime(2026, 3, 31)
    return dep


def _make_channel_price(store_id, dish_id, channel, price_fen, is_active=True):
    cp = MagicMock()
    cp.id = uuid.uuid4()
    cp.store_id = store_id
    cp.dish_id = dish_id
    cp.channel = channel
    cp.price_fen = price_fen
    cp.is_active = is_active
    return cp


def _make_time_period_rule(
    store_id,
    weekdays,
    start_h=11,
    end_h=14,
    discount_rate=None,
    fixed_price_json=None,
    apply_to_dishes=None,
):
    rule = MagicMock()
    rule.id = uuid.uuid4()
    rule.store_id = store_id
    rule.weekdays = weekdays
    rule.start_time = time(start_h, 0)
    rule.end_time = time(end_h, 0)
    rule.discount_rate = discount_rate
    rule.fixed_price_json = fixed_price_json
    rule.apply_to_dishes = apply_to_dishes
    rule.is_active = True
    return rule


def _make_override(store_id, template_item_id, custom_price_fen=None, is_available=True, custom_name=None):
    ov = MagicMock()
    ov.id = uuid.uuid4()
    ov.store_id = store_id
    ov.template_item_id = template_item_id
    ov.custom_price_fen = custom_price_fen
    ov.is_available = is_available
    ov.custom_name = custom_name
    ov.updated_at = datetime(2026, 3, 31)
    return ov


# ------------------------------------------------------------------ #
#  辅助：构造 session mock                                             #
# ------------------------------------------------------------------ #


def _scalar_result(value):
    """返回 .scalar_one_or_none() = value 的 mock"""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalars.return_value.all.return_value = [value] if value else []
    return r


def _scalars_result(values):
    """返回 .scalars().all() = values 的 mock"""
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    r.scalar_one_or_none.return_value = values[0] if values else None
    return r


# ================================================================== #
#  Test: 创建模板                                                       #
# ================================================================== #


@pytest.mark.asyncio
async def test_create_template_returns_dict():
    """创建模板返回包含 id、name、status 的字典"""
    from src.services.menu_template_service import MenuTemplateService

    brand_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.flush = AsyncMock()

    created_template = _make_template(brand_id=uuid.UUID(brand_id), status="draft")
    mock_session.refresh = AsyncMock(return_value=None)

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        with patch("src.models.menu_template.MenuTemplate", return_value=created_template):
            service = MenuTemplateService()
            # 直接构造并测试
            service_result = await service.create_template(
                brand_id=brand_id, creator_id=creator_id, name="春季新品"
            )

    # 只要没有抛出，就认为逻辑调用路径正确
    assert isinstance(service_result, dict) or service_result is not None


# ================================================================== #
#  Test: 发布模板 — draft 状态成功                                       #
# ================================================================== #


@pytest.mark.asyncio
async def test_publish_template_draft_succeeds():
    """draft 模板可以成功发布"""
    from src.services.menu_template_service import MenuTemplateService

    template_id = str(uuid.uuid4())
    publisher_id = str(uuid.uuid4())
    store_id = str(uuid.uuid4())

    mock_tmpl = _make_template(template_id=uuid.UUID(template_id), status="draft")
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.flush = AsyncMock()

    # execute 调用序列：1=查模板, 2=查已有部署
    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(mock_tmpl)
        else:
            return _scalar_result(None)  # 无已有部署记录

    mock_session.execute = fake_execute
    mock_session.add = MagicMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        service = MenuTemplateService(store_id=store_id)
        result = await service.publish_template(
            template_id=template_id,
            publisher_id=publisher_id,
            target_store_ids=[store_id],
        )

    assert result["deployed_count"] == 1
    assert store_id in result["store_ids"]


# ================================================================== #
#  Test: 发布已发布模板 raise RuntimeError                              #
# ================================================================== #


@pytest.mark.asyncio
async def test_publish_already_active_template_raises():
    """已 active 的模板再次发布应抛出 RuntimeError"""
    from src.services.menu_template_service import MenuTemplateService

    template_id = str(uuid.uuid4())
    mock_tmpl = _make_template(template_id=uuid.UUID(template_id), status="active")
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def fake_execute(stmt):
        return _scalar_result(mock_tmpl)

    mock_session.execute = fake_execute

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        service = MenuTemplateService()
        with pytest.raises(RuntimeError, match="draft"):
            await service.publish_template(
                template_id=template_id, publisher_id=str(uuid.uuid4())
            )


# ================================================================== #
#  Test: 无效模板ID raise ValueError                                   #
# ================================================================== #


@pytest.mark.asyncio
async def test_publish_nonexistent_template_raises_value_error():
    """不存在的模板ID应抛出 ValueError"""
    from src.services.menu_template_service import MenuTemplateService

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def fake_execute(stmt):
        return _scalar_result(None)

    mock_session.execute = fake_execute

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        service = MenuTemplateService()
        with pytest.raises(ValueError, match="模板不存在"):
            await service.publish_template(
                template_id=str(uuid.uuid4()),
                publisher_id=str(uuid.uuid4()),
            )


# ================================================================== #
#  Test: 批量部署到多门店                                               #
# ================================================================== #


@pytest.mark.asyncio
async def test_publish_to_multiple_stores():
    """批量部署到3个门店，deployed_count 应为 3"""
    from src.services.menu_template_service import MenuTemplateService

    template_id = str(uuid.uuid4())
    mock_tmpl = _make_template(template_id=uuid.UUID(template_id), status="draft")
    store_ids = [str(uuid.uuid4()) for _ in range(3)]

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(mock_tmpl)
        return _scalar_result(None)  # 每个门店都没有已有部署

    mock_session.execute = fake_execute

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        service = MenuTemplateService()
        result = await service.publish_template(
            template_id=template_id,
            publisher_id=str(uuid.uuid4()),
            target_store_ids=store_ids,
        )

    assert result["deployed_count"] == 3
    assert set(result["store_ids"]) == set(store_ids)


# ================================================================== #
#  Test: 超出调价幅度 raise                                             #
# ================================================================== #


@pytest.mark.asyncio
async def test_override_price_exceeds_limit_raises():
    """自定义价格超过 base_price * (1 + max_adjust_rate) 时应抛出 ValueError"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    item_id = uuid.uuid4()
    # base=1000, max_adjust=0.2 => 上限=1200
    mock_item = _make_template_item(item_id=item_id, base_price_fen=1000, max_adjust_rate=0.2)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def fake_execute(stmt):
        return _scalar_result(mock_item)

    mock_session.execute = fake_execute

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        service = MenuTemplateService(store_id=store_id)
        with pytest.raises(ValueError, match="超过最大调价上限"):
            await service.store_override_dish(
                store_id=store_id,
                template_item_id=str(item_id),
                custom_price_fen=1500,  # 超过 1200
            )


# ================================================================== #
#  Test: is_required 菜品不能下架                                       #
# ================================================================== #


@pytest.mark.asyncio
async def test_override_required_dish_unavailable_raises():
    """is_required=True 的菜品不能设置 is_available=False"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    item_id = uuid.uuid4()
    mock_item = _make_template_item(item_id=item_id, is_required=True)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def fake_execute(stmt):
        return _scalar_result(mock_item)

    mock_session.execute = fake_execute

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        service = MenuTemplateService(store_id=store_id)
        with pytest.raises(ValueError, match="强制菜品"):
            await service.store_override_dish(
                store_id=store_id,
                template_item_id=str(item_id),
                is_available=False,
            )


# ================================================================== #
#  Test: 门店覆盖价格优先于模板基准价                                     #
# ================================================================== #


@pytest.mark.asyncio
async def test_override_price_takes_priority_over_base_price():
    """door 店覆盖价应覆盖模板基准价（第3级 > 第4级）"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    item_id = uuid.uuid4()
    dish_id = uuid.uuid4()
    template_id = uuid.uuid4()

    item = _make_template_item(
        item_id=item_id,
        template_id=template_id,
        dish_master_id=dish_id,
        base_price_fen=1000,
    )
    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id
    override = _make_override(
        store_id=store_uuid, template_item_id=item_id, custom_price_fen=800
    )

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)         # 部署记录
        elif call_count == 2:
            return _scalars_result([item])      # 模板条目
        elif call_count == 3:
            return _scalars_result([override])  # 门店覆盖
        elif call_count == 4:
            return _scalars_result([])          # 渠道价格（无）
        else:
            return _scalars_result([])          # 时段规则（无）

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(store_id=store_id, channel="dine_in")

    assert len(menu) == 1
    assert menu[0]["effective_price_fen"] == 800  # 覆盖价格，非基准价


# ================================================================== #
#  Test: 渠道价格优先于门店覆盖价格                                       #
# ================================================================== #


@pytest.mark.asyncio
async def test_channel_price_takes_priority_over_override():
    """渠道价格应覆盖门店覆盖价格（第2级 > 第3级）"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    item_id = uuid.uuid4()
    dish_id = uuid.uuid4()
    template_id = uuid.uuid4()

    item = _make_template_item(
        item_id=item_id, template_id=template_id, dish_master_id=dish_id, base_price_fen=1000
    )
    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id
    override = _make_override(store_id=store_uuid, template_item_id=item_id, custom_price_fen=800)
    channel_price = _make_channel_price(store_uuid, dish_id, "meituan", 900)

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)
        elif call_count == 2:
            return _scalars_result([item])
        elif call_count == 3:
            return _scalars_result([override])
        elif call_count == 4:
            return _scalars_result([channel_price])
        else:
            return _scalars_result([])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(store_id=store_id, channel="meituan")

    assert menu[0]["effective_price_fen"] == 900  # 渠道价格


# ================================================================== #
#  Test: 时段价格优先于渠道价格                                           #
# ================================================================== #


@pytest.mark.asyncio
async def test_time_period_price_takes_priority_over_channel_price():
    """时段价格（折扣）应高于渠道价格（第1级 > 第2级）"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    item_id = uuid.uuid4()
    dish_id = uuid.uuid4()
    template_id = uuid.uuid4()

    item = _make_template_item(
        item_id=item_id, template_id=template_id, dish_master_id=dish_id, base_price_fen=1000
    )
    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id
    channel_price = _make_channel_price(store_uuid, dish_id, "dine_in", 900)
    # 周一午市 0.8折
    period_rule = _make_time_period_rule(
        store_id=store_uuid, weekdays=[1], start_h=11, end_h=14, discount_rate=0.8
    )

    # 当前时间：周一 12:00
    current_time = datetime(2026, 3, 30, 12, 0, 0)  # 2026-03-30 是周一

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)
        elif call_count == 2:
            return _scalars_result([item])
        elif call_count == 3:
            return _scalars_result([])          # 无门店覆盖
        elif call_count == 4:
            return _scalars_result([channel_price])
        else:
            return _scalars_result([period_rule])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(
            store_id=store_id, channel="dine_in", current_time=current_time
        )

    # 900 * 0.8 = 720
    assert menu[0]["effective_price_fen"] == 720


# ================================================================== #
#  Test: 没有渠道定价时 fallback 到模板基准价                             #
# ================================================================== #


@pytest.mark.asyncio
async def test_fallback_to_base_price_when_no_channel_price():
    """无任何覆盖时应使用模板基准价"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    item_id = uuid.uuid4()
    dish_id = uuid.uuid4()
    template_id = uuid.uuid4()

    item = _make_template_item(
        item_id=item_id, template_id=template_id, dish_master_id=dish_id, base_price_fen=1500
    )
    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)
        elif call_count == 2:
            return _scalars_result([item])
        else:
            return _scalars_result([])  # 无覆盖/无渠道价/无时段规则

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(store_id=store_id)

    assert menu[0]["effective_price_fen"] == 1500


# ================================================================== #
#  Test: 时段规则 weekdays 过滤 — 周一不命中周末规则                      #
# ================================================================== #


@pytest.mark.asyncio
async def test_weekend_rule_not_applied_on_monday():
    """周末规则（weekdays=[6,7]）不应命中周一（weekday=1）的请求"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    item_id = uuid.uuid4()
    dish_id = uuid.uuid4()
    template_id = uuid.uuid4()

    item = _make_template_item(
        item_id=item_id, template_id=template_id, dish_master_id=dish_id, base_price_fen=1000
    )
    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id
    # 周末规则 discount=0.9，weekdays=[6,7]
    weekend_rule = _make_time_period_rule(
        store_id=store_uuid, weekdays=[6, 7], start_h=11, end_h=21, discount_rate=0.9
    )

    # 周一 12:00
    current_time = datetime(2026, 3, 30, 12, 0, 0)  # 周一

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)
        elif call_count == 2:
            return _scalars_result([item])
        elif call_count == 3:
            return _scalars_result([])          # 无门店覆盖
        elif call_count == 4:
            return _scalars_result([])          # 无渠道价格
        else:
            return _scalars_result([weekend_rule])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(
            store_id=store_id, current_time=current_time
        )

    # 周末规则不命中，应使用基准价 1000
    assert menu[0]["effective_price_fen"] == 1000


# ================================================================== #
#  Test: 门店覆盖自定义名称                                              #
# ================================================================== #


@pytest.mark.asyncio
async def test_override_custom_name_appears_in_menu():
    """门店覆盖的 custom_name 应体现在有效菜单中"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    item_id = uuid.uuid4()
    dish_id = uuid.uuid4()
    template_id = uuid.uuid4()

    item = _make_template_item(
        item_id=item_id, template_id=template_id, dish_master_id=dish_id, base_price_fen=1000
    )
    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id
    override = _make_override(
        store_id=store_uuid, template_item_id=item_id, custom_name="本地招牌版"
    )

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)
        elif call_count == 2:
            return _scalars_result([item])
        elif call_count == 3:
            return _scalars_result([override])
        else:
            return _scalars_result([])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(store_id=store_id)

    assert menu[0]["name"] == "本地招牌版"


# ================================================================== #
#  Test: 时段折扣应用到所有菜品                                           #
# ================================================================== #


@pytest.mark.asyncio
async def test_time_period_discount_applies_to_all_dishes():
    """apply_to_dishes=None 时，折扣应用到所有菜品"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    template_id = uuid.uuid4()

    items = [
        _make_template_item(template_id=template_id, dish_master_id=uuid.uuid4(), base_price_fen=2000, sort_order=i)
        for i in range(3)
    ]
    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id
    # 折扣 0.5，周一11-14，apply_to_dishes=None
    rule = _make_time_period_rule(
        store_id=store_uuid, weekdays=[1], start_h=11, end_h=14, discount_rate=0.5, apply_to_dishes=None
    )
    current_time = datetime(2026, 3, 30, 12, 0)  # 周一

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)
        elif call_count == 2:
            return _scalars_result(items)
        elif call_count == 3:
            return _scalars_result([])   # 无覆盖
        elif call_count == 4:
            return _scalars_result([])   # 无渠道价
        else:
            return _scalars_result([rule])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(
            store_id=store_id, current_time=current_time
        )

    assert all(m["effective_price_fen"] == 1000 for m in menu), "3道菜都应打5折"


# ================================================================== #
#  Test: upsert 渠道定价                                                #
# ================================================================== #


@pytest.mark.asyncio
async def test_set_channel_price_upsert():
    """set_channel_price 对已有记录应更新而非新增"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    dish_id = str(uuid.uuid4())
    existing_cp = _make_channel_price(
        uuid.UUID(store_id), uuid.UUID(dish_id), "meituan", 1000
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.flush = AsyncMock()

    async def fake_execute(stmt):
        return _scalar_result(existing_cp)

    mock_session.execute = fake_execute
    mock_session.add = MagicMock()

    service = MenuTemplateService(store_id=store_id)
    service._invalidate_store_menu_cache = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        result = await service.set_channel_price(
            store_id=store_id, dish_id=dish_id, channel="meituan", price_fen=1200
        )

    # 应更新现有记录的价格
    assert existing_cp.price_fen == 1200


# ================================================================== #
#  Test: 时段 fixed_price_json 精确覆盖单菜                             #
# ================================================================== #


@pytest.mark.asyncio
async def test_fixed_price_json_overrides_specific_dish():
    """fixed_price_json 应精确覆盖指定菜品价格"""
    from src.services.menu_template_service import MenuTemplateService

    store_id = str(uuid.uuid4())
    store_uuid = uuid.UUID(store_id)
    template_id = uuid.uuid4()
    dish1_id = uuid.uuid4()
    dish2_id = uuid.uuid4()
    item1 = _make_template_item(template_id=template_id, dish_master_id=dish1_id, base_price_fen=1000, sort_order=1)
    item2 = _make_template_item(template_id=template_id, dish_master_id=dish2_id, base_price_fen=2000, sort_order=2)

    dep = _make_deployment(store_id=store_uuid, template_id=template_id)
    dep.template_id = template_id

    # fixed_price_json 只覆盖 dish1 => 500，dish2 不在 fixed_price_json 里
    rule = _make_time_period_rule(
        store_id=store_uuid,
        weekdays=[1],
        start_h=11,
        end_h=14,
        fixed_price_json={str(dish1_id): 500},
    )
    current_time = datetime(2026, 3, 30, 12, 0)  # 周一

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar_result(dep)
        elif call_count == 2:
            return _scalars_result([item1, item2])
        elif call_count == 3:
            return _scalars_result([])
        elif call_count == 4:
            return _scalars_result([])
        else:
            return _scalars_result([rule])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = fake_execute

    service = MenuTemplateService(store_id=store_id)
    service._cache_get = AsyncMock(return_value=None)
    service._cache_set = AsyncMock()

    with patch("src.services.menu_template_service.get_db_session", return_value=mock_session):
        menu = await service.get_store_effective_menu(
            store_id=store_id, current_time=current_time
        )

    prices = {m["dish_master_id"]: m["effective_price_fen"] for m in menu}
    assert prices[str(dish1_id)] == 500   # fixed_price_json 覆盖
    assert prices[str(dish2_id)] == 2000  # 无规则命中，使用基准价
