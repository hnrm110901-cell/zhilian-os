"""
Phase 2 — SCRM & 外卖归因 单元测试

覆盖：
1. test_bind_member_on_add_contact_existing_member  — 添加外部联系人时绑定已有会员
2. test_bind_member_on_add_contact_new_member       — 添加外部联系人时创建新会员
3. test_send_welcome_message_by_lifecycle_state     — 根据生命周期状态发送差异化欢迎语
4. test_attribute_meituan_order_with_phone_match    — 美团订单手机号归因成功
5. test_attribute_meituan_order_anonymous_fallback  — 美团订单手机号为空降级匿名
6. test_omnichannel_history_merges_all_channels     — 多渠道消费历史统一视图
7. test_transfer_customer_updates_staff_id          — 员工离职迁移更新关联关系
"""

import uuid
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Helpers — Mock 工厂
# ═══════════════════════════════════════════════════════════════════════


def _make_db():
    """返回 AsyncSession Mock"""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    return db


def _make_consumer(phone="13800138000", openid="ext_wecom_001"):
    """构造 ConsumerIdentity Mock"""
    c = MagicMock()
    c.id = uuid.uuid4()
    c.primary_phone = phone
    c.wechat_openid = openid
    c.is_merged = False
    c.display_name = "测试客户"
    c.gender = "unknown"
    c.wechat_nickname = "小明"
    c.wechat_avatar_url = None
    c.tags = ["老客户"]
    c.dietary_restrictions = []
    c.anniversary = None
    c.total_order_count = 5
    c.total_order_amount_fen = 50000
    c.first_order_at = datetime(2024, 1, 1)
    c.last_order_at = datetime(2026, 3, 1)
    c.rfm_recency_days = 10
    c.rfm_frequency = 5
    c.rfm_monetary_fen = 50000
    return c


def _make_member(rfm_level="S2"):
    """构造 PrivateDomainMember Mock"""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.rfm_level = rfm_level
    m.r_score = 4
    m.f_score = 3
    m.m_score = 3
    m.recency_days = 10
    m.frequency = 5
    m.monetary = 50000
    m.consumer_id = uuid.uuid4()
    m.wechat_openid = "ext_wecom_001"
    m.channel_source = "wecom:staff_001"
    return m


def _make_profile(lifecycle="repeat", brand_id="BRAND-001"):
    """构造 BrandConsumerProfile Mock"""
    p = MagicMock()
    p.id = uuid.uuid4()
    p.brand_id = brand_id
    p.brand_level = "银卡"
    p.brand_points = 100
    p.brand_balance_fen = 2000
    p.brand_order_count = 5
    p.brand_order_amount_fen = 50000
    p.brand_first_order_at = datetime(2024, 1, 1)
    p.brand_last_order_at = datetime(2026, 3, 1)
    p.lifecycle_state = lifecycle
    p.registration_channel = "pos"
    p.is_active = True
    return p


def _scalar_result(value):
    """模拟 db.execute(...).scalar_one_or_none() 的返回路径"""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    result.scalar_one = MagicMock(return_value=value)
    result.scalars.return_value.all = MagicMock(return_value=[value] if value else [])
    return result


# ═══════════════════════════════════════════════════════════════════════
# 测试：WeComSCRMService
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bind_member_on_add_contact_existing_member():
    """
    场景：外部联系人手机号能查到已有 ConsumerIdentity。
    期望：更新 PrivateDomainMember，返回已有 consumer_id。
    """
    from src.services.wecom_scrm_service import WeComSCRMService

    svc = WeComSCRMService()
    db = _make_db()
    existing_consumer = _make_consumer(phone="13800138000", openid="ext_001")

    # 模拟：_get_external_contact_phone 返回手机号
    svc._get_external_contact_phone = AsyncMock(return_value="13800138000")

    # 模拟：db.execute 查 ConsumerIdentity 返回已有记录
    db.execute = AsyncMock(return_value=_scalar_result(existing_consumer))

    # 模拟：_upsert_private_domain_wecom_id
    svc._upsert_private_domain_wecom_id = AsyncMock()

    result = await svc.bind_member_on_add_external_contact(
        db=db,
        wecom_userid="staff_001",
        external_userid="ext_001",
        store_id="STORE-001",
    )

    assert result == str(existing_consumer.id)
    svc._upsert_private_domain_wecom_id.assert_called_once()


@pytest.mark.asyncio
async def test_bind_member_on_add_contact_new_member():
    """
    场景：外部联系人手机号在 ConsumerIdentity 中不存在。
    期望：创建新 ConsumerIdentity，返回新 consumer_id。
    """
    from src.services.wecom_scrm_service import WeComSCRMService

    svc = WeComSCRMService()
    db = _make_db()

    svc._get_external_contact_phone = AsyncMock(return_value="13900139000")

    # 模拟：db.execute 查 ConsumerIdentity 返回 None（新客户）
    db.execute = AsyncMock(return_value=_scalar_result(None))

    new_cid = uuid.uuid4()
    svc._create_new_consumer_from_wecom = AsyncMock(return_value=str(new_cid))

    result = await svc.bind_member_on_add_external_contact(
        db=db,
        wecom_userid="staff_002",
        external_userid="ext_002",
        store_id="STORE-001",
    )

    assert result == str(new_cid)
    svc._create_new_consumer_from_wecom.assert_called_once_with(
        db, "13900139000", "ext_002", "staff_002", "STORE-001"
    )


@pytest.mark.asyncio
async def test_bind_member_on_add_contact_no_phone():
    """
    场景：无法获取外部联系人手机号（企微 API 未授权）。
    期望：返回 None，不抛异常。
    """
    from src.services.wecom_scrm_service import WeComSCRMService

    svc = WeComSCRMService()
    db = _make_db()

    svc._get_external_contact_phone = AsyncMock(return_value=None)

    result = await svc.bind_member_on_add_external_contact(
        db=db,
        wecom_userid="staff_003",
        external_userid="ext_003",
        store_id="STORE-001",
    )

    assert result is None


@pytest.mark.asyncio
async def test_send_welcome_message_by_lifecycle_state():
    """
    场景：消费者 lifecycle_state = 'repeat'，trigger = 'returning'。
    期望：选择对应话术模板，调用 wechat_service.send_text_message。
    """
    from src.services.wecom_scrm_service import WeComSCRMService, _WELCOME_TEMPLATES

    svc = WeComSCRMService()
    db = _make_db()
    consumer = _make_consumer()
    profile = _make_profile(lifecycle="repeat")

    consumer_id = str(consumer.id)

    with patch(
        "src.repositories.brand_consumer_profile_repo.BrandConsumerProfileRepo.get_by_consumer_and_brand",
        new=AsyncMock(return_value=profile),
    ):
        db.get = AsyncMock(return_value=consumer)

        with patch(
            "src.services.wechat_service.wechat_service.send_text_message",
            new=AsyncMock(return_value={"errcode": 0}),
        ) as mock_send:
            result = await svc.send_welcome_message(
                db=db,
                consumer_id=consumer_id,
                brand_id="BRAND-001",
                trigger="returning",
            )

    assert result is True
    mock_send.assert_called_once()
    # 验证话术内容包含预期话术模板中的关键词
    call_args = mock_send.call_args
    sent_content = call_args[0][0]  # 第一个位置参数
    expected = _WELCOME_TEMPLATES.get(("returning", "repeat"), "")
    assert sent_content == expected


@pytest.mark.asyncio
async def test_send_welcome_message_no_openid():
    """
    场景：消费者无 wechat_openid。
    期望：返回 False，不调用 send_text_message。
    """
    from src.services.wecom_scrm_service import WeComSCRMService

    svc = WeComSCRMService()
    db = _make_db()
    consumer = _make_consumer()
    consumer.wechat_openid = None  # 无 openid

    with patch(
        "src.repositories.brand_consumer_profile_repo.BrandConsumerProfileRepo.get_by_consumer_and_brand",
        new=AsyncMock(return_value=_make_profile()),
    ):
        db.get = AsyncMock(return_value=consumer)
        result = await svc.send_welcome_message(
            db=db,
            consumer_id=str(consumer.id),
            brand_id="BRAND-001",
            trigger="new_customer",
        )

    assert result is False


@pytest.mark.asyncio
async def test_transfer_customer_updates_staff_id():
    """
    场景：离职员工 staff_001 名下有 2 位客户，迁移到接替人 staff_002。
    期望：调用企微 transfer_customer API，更新 channel_source。
    """
    from src.services.wecom_scrm_service import WeComSCRMService

    svc = WeComSCRMService()
    db = _make_db()

    member1 = _make_member()
    member1.wechat_openid = "ext_c001"
    member2 = _make_member()
    member2.wechat_openid = "ext_c002"

    # 模拟查询结果
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all = MagicMock(return_value=[member1, member2])
    db.execute = AsyncMock(return_value=scalars_result)

    # 模拟企微 transfer API 返回成功
    svc._call_wecom_transfer_customer = AsyncMock(
        return_value={"transferred_count": 2, "failed_list": []}
    )

    result = await svc.transfer_customer_on_resignation(
        db=db,
        resigned_userid="staff_001",
        successor_userid="staff_002",
        store_id="STORE-001",
    )

    assert result["total"] == 2
    assert result["transferred"] == 2
    assert result["failed"] == 0
    svc._call_wecom_transfer_customer.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# 测试：DeliveryOrderAttributionService
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_attribute_meituan_order_with_phone_match():
    """
    场景：美团订单含明文手机号，手机号能匹配到已有 ConsumerIdentity。
    期望：写入 omnichannel_order_records，更新 BrandConsumerProfile，返回 consumer_id。
    """
    from src.services.delivery_order_attribution_service import DeliveryOrderAttributionService

    svc = DeliveryOrderAttributionService()
    db = _make_db()
    consumer = _make_consumer(phone="13800138000")

    order_data = {
        "order_id": "MT20260330001",
        "buyer_phone": "13800138000",
        "total_price": 8800,  # 88.00 元
        "created_time": 1743350400000,  # 毫秒时间戳
        "item_count": 3,
    }

    # 幂等检查：首次，未归因
    svc._order_already_attributed = AsyncMock(return_value=False)
    # 手机号查 ConsumerIdentity
    svc._find_or_skip_consumer = AsyncMock(return_value=str(consumer.id))
    # 更新 BrandConsumerProfile
    svc._update_brand_profile = AsyncMock()
    # 写入多渠道记录
    svc._write_omnichannel_record = AsyncMock()
    # 触发 RFM 重算
    svc._trigger_rfm_recalc = AsyncMock()

    result = await svc.attribute_meituan_order(
        db=db,
        order_data=order_data,
        store_id="STORE-001",
        brand_id="BRAND-001",
        group_id="GROUP-001",
    )

    assert result == str(consumer.id)
    svc._update_brand_profile.assert_called_once()
    svc._write_omnichannel_record.assert_called_once()
    svc._trigger_rfm_recalc.assert_called_once_with(
        str(consumer.id), "BRAND-001", "STORE-001"
    )

    # 验证写入的归因状态为 attributed
    write_call_kwargs = svc._write_omnichannel_record.call_args[1]
    assert write_call_kwargs["attribution_status"] == "attributed"
    assert write_call_kwargs["attribution_method"] == "phone_match"
    assert write_call_kwargs["channel"] == "meituan"
    assert write_call_kwargs["external_order_no"] == "MT20260330001"


@pytest.mark.asyncio
async def test_attribute_meituan_order_anonymous_fallback():
    """
    场景：美团订单手机号字段为空（或加密无法解密）。
    期望：写入匿名记录，返回 None，不抛异常。
    """
    from src.services.delivery_order_attribution_service import DeliveryOrderAttributionService

    svc = DeliveryOrderAttributionService()
    db = _make_db()

    order_data = {
        "order_id": "MT20260330002",
        "buyer_phone": None,  # 无手机号
        "total_price": 5500,
        "created_time": 1743350400000,
    }

    svc._order_already_attributed = AsyncMock(return_value=False)
    svc._write_omnichannel_record = AsyncMock()

    result = await svc.attribute_meituan_order(
        db=db,
        order_data=order_data,
        store_id="STORE-001",
        brand_id="BRAND-001",
        group_id="GROUP-001",
    )

    assert result is None
    svc._write_omnichannel_record.assert_called_once()

    # 验证写入的归因状态为 anonymous
    write_call_kwargs = svc._write_omnichannel_record.call_args[1]
    assert write_call_kwargs["attribution_status"] == "anonymous"
    assert write_call_kwargs["consumer_id"] is None


@pytest.mark.asyncio
async def test_attribute_meituan_order_idempotent():
    """
    场景：同一美团订单被重复推送（幂等检查）。
    期望：直接返回已归因的 consumer_id，不重复写入。
    """
    from src.services.delivery_order_attribution_service import DeliveryOrderAttributionService

    svc = DeliveryOrderAttributionService()
    db = _make_db()
    consumer = _make_consumer()

    order_data = {
        "order_id": "MT20260330003",
        "buyer_phone": "13800138000",
        "total_price": 3000,
        "created_time": 1743350400000,
    }

    # 幂等检查：已归因
    svc._order_already_attributed = AsyncMock(return_value=True)
    svc._get_existing_attribution = AsyncMock(return_value=str(consumer.id))
    svc._write_omnichannel_record = AsyncMock()

    result = await svc.attribute_meituan_order(
        db=db,
        order_data=order_data,
        store_id="STORE-001",
        brand_id="BRAND-001",
        group_id="GROUP-001",
    )

    assert result == str(consumer.id)
    # 已归因订单不应再次写入
    svc._write_omnichannel_record.assert_not_called()


@pytest.mark.asyncio
async def test_omnichannel_history_merges_all_channels():
    """
    场景：消费者有美团、饿了么、堂食三渠道消费记录。
    期望：get_omnichannel_order_history 返回统一格式的历史列表，包含所有渠道。
    """
    from src.services.delivery_order_attribution_service import DeliveryOrderAttributionService

    svc = DeliveryOrderAttributionService()
    db = _make_db()
    consumer = _make_consumer()

    # 模拟 db.execute 返回多渠道数据
    mock_rows = [
        {
            "id": uuid.uuid4(),
            "channel": "meituan",
            "order_no": "MT001",
            "amount_fen": 8800,
            "item_count": 3,
            "store_id": "STORE-001",
            "created_at": datetime(2026, 3, 25),
            "attribution_status": "attributed",
            "attribution_method": "phone_match",
        },
        {
            "id": uuid.uuid4(),
            "channel": "eleme",
            "order_no": "EL001",
            "amount_fen": 6600,
            "item_count": 2,
            "store_id": "STORE-001",
            "created_at": datetime(2026, 3, 20),
            "attribution_status": "attributed",
            "attribution_method": "phone_match",
        },
        {
            "id": uuid.uuid4(),
            "channel": "pos",
            "order_no": "POS001",
            "amount_fen": 15000,
            "item_count": 5,
            "store_id": "STORE-001",
            "created_at": datetime(2026, 3, 10),
            "attribution_status": "attributed",
            "attribution_method": "phone_match",
        },
    ]

    # 构造 mappings 返回值
    mock_result = MagicMock()
    mock_result.mappings.return_value.all = MagicMock(return_value=mock_rows)
    db.execute = AsyncMock(return_value=mock_result)

    history = await svc.get_omnichannel_order_history(
        db=db,
        consumer_id=str(consumer.id),
        brand_id="BRAND-001",
        limit=50,
    )

    assert len(history) == 3

    # 验证渠道覆盖
    channels = {h["channel"] for h in history}
    assert "meituan" in channels
    assert "eleme" in channels
    assert "pos" in channels

    # 验证金额转换（分 → 元）
    meituan_record = next(h for h in history if h["channel"] == "meituan")
    assert meituan_record["amount_fen"] == 8800
    assert meituan_record["amount_yuan"] == 88.0

    # 验证字段存在
    for record in history:
        assert "order_no" in record
        assert "amount_fen" in record
        assert "amount_yuan" in record
        assert "store_id" in record
        assert "created_at" in record
        assert "attribution_status" in record


@pytest.mark.asyncio
async def test_omnichannel_history_invalid_consumer_id():
    """
    场景：传入无效的 consumer_id（非 UUID 格式）。
    期望：返回空列表，不抛异常。
    """
    from src.services.delivery_order_attribution_service import DeliveryOrderAttributionService

    svc = DeliveryOrderAttributionService()
    db = _make_db()

    result = await svc.get_omnichannel_order_history(
        db=db,
        consumer_id="not-a-valid-uuid",
        brand_id="BRAND-001",
        limit=50,
    )

    assert result == []


@pytest.mark.asyncio
async def test_batch_backfill_meituan_attribution():
    """
    场景：批量回填历史美团订单归因（10笔，7笔有手机号归因成功，3笔匿名）。
    期望：返回统计字典 total/attributed/anonymous/error。
    """
    from src.services.delivery_order_attribution_service import DeliveryOrderAttributionService

    svc = DeliveryOrderAttributionService()
    db = _make_db()
    consumer = _make_consumer()

    # 模拟历史订单：7笔有手机号，3笔无手机号
    historical_orders = [
        {"order_id": f"MT_H_{i:03d}", "buyer_phone": "13800138000", "total_price": 5000, "created_time": 1743350400000}
        for i in range(7)
    ] + [
        {"order_id": f"MT_ANON_{i:03d}", "buyer_phone": None, "total_price": 3000, "created_time": 1743350400000}
        for i in range(3)
    ]

    svc._fetch_meituan_historical_orders = AsyncMock(return_value=historical_orders)

    # attribute_meituan_order：有手机号返回 consumer_id，无手机号返回 None
    async def mock_attribute(db, order_data, store_id, brand_id, group_id):
        return str(consumer.id) if order_data.get("buyer_phone") else None

    svc.attribute_meituan_order = mock_attribute

    result = await svc.batch_backfill_meituan_attribution(
        db=db,
        store_id="STORE-001",
        brand_id="BRAND-001",
        group_id="GROUP-001",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 30),
        app_auth_token="test_token",
    )

    assert result["total"] == 10
    assert result["attributed"] == 7
    assert result["anonymous"] == 3
    assert result["error"] == 0


# ═══════════════════════════════════════════════════════════════════════
# 测试：WeComSCRMService — 私域行为同步
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sync_behavior_updates_lifecycle():
    """
    场景：客户发出 purchase_intent 行为，已有 ConsumerIdentity。
    期望：调用 upsert_profile 更新 lifecycle_state，发布行为事件。
    """
    from src.services.wecom_scrm_service import WeComSCRMService

    svc = WeComSCRMService()
    db = _make_db()
    consumer = _make_consumer(openid="ext_behavior_001")

    db.execute = AsyncMock(return_value=_scalar_result(consumer))

    metadata = {
        "brand_id": "BRAND-001",
        "group_id": "GROUP-001",
        "store_id": "STORE-001",
    }

    with patch(
        "src.repositories.brand_consumer_profile_repo.BrandConsumerProfileRepo.upsert_profile",
        new=AsyncMock(return_value=_make_profile()),
    ) as mock_upsert:
        result = await svc.sync_private_domain_behavior_to_cdp(
            db=db,
            external_userid="ext_behavior_001",
            behavior_type="purchase_intent",
            metadata=metadata,
        )

    assert result is True
    # purchase_intent 应触发 lifecycle_state → repeat
    mock_upsert.assert_called_once()
    call_kwargs = mock_upsert.call_args[1]
    assert call_kwargs["lifecycle_state"] == "repeat"


@pytest.mark.asyncio
async def test_sync_behavior_no_consumer_returns_false():
    """
    场景：external_userid 无匹配的 ConsumerIdentity。
    期望：返回 False，不更新 profile。
    """
    from src.services.wecom_scrm_service import WeComSCRMService

    svc = WeComSCRMService()
    db = _make_db()

    db.execute = AsyncMock(return_value=_scalar_result(None))

    result = await svc.sync_private_domain_behavior_to_cdp(
        db=db,
        external_userid="ext_unknown_999",
        behavior_type="click_menu",
        metadata={"brand_id": "BRAND-001", "group_id": "GROUP-001"},
    )

    assert result is False
