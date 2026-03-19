"""
种子脚本：正式开通三个种子客户商户后台
- 尝在一起（品智收银 + 微生活会员 + 喰星云供应链）
- 最黔线（品智收银 + 微生活会员）
- 尚宫厨（品智收银 + 微生活会员 + 微生活卡券中心）

运行方式：
  cd apps/api-gateway
  python scripts/seed_real_merchants.py

脚本幂等：重复运行不会创建重复记录。
"""
import os
import sys
import uuid
import json
from datetime import datetime

# ── 路径设置 ──────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# 转换 async URL → sync URL（与 alembic/env.py 逻辑一致）
raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/tunxiang"
)
sync_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
engine = create_engine(sync_url, echo=False)

from src.models.base import Base
from src.models.organization import Group, Brand
from src.models.store import Store
from src.models.user import User, UserRole
from src.models.integration import (
    ExternalSystem, IntegrationType, IntegrationStatus
)
from src.core.security import get_password_hash


# ══════════════════════════════════════════════════════════════════════════════
#  商户配置清单
# ══════════════════════════════════════════════════════════════════════════════

MERCHANTS = [
    # ── 尝在一起 ──────────────────────────────────────────────────────────────
    {
        "group": {
            "group_id": "GRP_CZYZ0001",
            "group_name": "尝在一起餐饮管理有限公司",
            "legal_entity": "尝在一起法人代表",
            "unified_social_credit_code": "91430100CZYZ000001",
            "industry_type": "chinese_formal",
            "contact_person": "尝在一起联系人",
            "contact_phone": "0731-00000001",
            "address": "湖南省长沙市",
        },
        "brand": {
            "brand_id": "BRD_CZYZ0001",
            "group_id": "GRP_CZYZ0001",
            "brand_name": "尝在一起",
            "cuisine_type": "hunan",
            "avg_ticket_yuan": 80,
            "target_food_cost_pct": 35,
            "target_labor_cost_pct": 22,
            "target_rent_cost_pct": 10,
            "target_waste_pct": 3,
            "status": "active",
        },
        "admin_user": {
            "username": "czyz_admin",
            "email": "admin@czyz.com",
            "password": "czyz@2026",
            "full_name": "尝在一起管理员",
            "role": UserRole.STORE_MANAGER,
            "brand_id": "BRD_CZYZ0001",
        },
        # 品智收银配置（一个域名 + 全局 Token + 各店独立 Token）
        "pinzhi": {
            "base_url": "https://czyq.pinzhikeji.net/pzcatering-gateway",
            "api_token": "3bbc9bed2b42c1e1b3cca26389fbb81c",
        },
        # 易订预订系统配置（接口凭证待确认，管理后台账号如下）
        "yiding": {
            "base_url": "https://open.zhidianfan.com/yidingopen/",
            "stores": [
                {
                    "name": "尝在一起闲鲜餐厅",
                    "portal_username": "czyq001",
                    "portal_password": "24683791S",
                    "appid": "",   # ⚠️ 待填写：需从易订获取API appid
                    "secret": "",  # ⚠️ 待填写：需从易订获取API secret
                },
                {
                    "name": "浏阳市永安镇尝在一起闲鲜餐厅",
                    "portal_username": "cznlp000",
                    "portal_password": "24503791S",
                    "appid": "",   # ⚠️ 待填写
                    "secret": "",  # ⚠️ 待填写
                },
            ],
        },
        # 微生活会员系统配置（奥琦玮旗下，api.acewill.net）
        "weishenghuo": {
            "base_url": "https://api.acewill.net",
            "app_id": "dp25MLoc2gnXE7A223ZiVv",
            "app_key": "3d2eaa5f9b9a6a6746a18d28e770b501",
            "merchant_id": "1275413383",  # ✅ 已配置
        },
        # 喰星云供应链配置（奥琦玮旗下，尝在一起专属实例）
        "chixingyun": {
            "base_url": "http://czyqss.scmacewill.cn",
            "app_key": "changzaiyiqi",
            "app_secret": "WmRpv8OlR1UR",
        },
        "stores": [
            {
                "id": "CZYZ-2461",
                "name": "文化城店",
                "code": "CZYZ-WH001",
                "city": "长沙",
                "brand_name": "尝在一起文化城店",
                "pinzhi_store_id": 2461,
                "pinzhi_store_token": "752b4b16a863ce47def11cf33b1b521f",
                "pinzhi_oms_id": 2461,
            },
            {
                "id": "CZYZ-7269",
                "name": "浏小鲜",
                "code": "CZYZ-LXX001",
                "city": "长沙",
                "brand_name": "浏小鲜",
                "pinzhi_store_id": 7269,
                "pinzhi_store_token": "f5cc1a27db6e215ae7bb5512b6b57981",
                "pinzhi_oms_id": 7269,
            },
            {
                "id": "CZYZ-19189",
                "name": "永安店",
                "code": "CZYZ-YA001",
                "city": "长沙",
                "brand_name": "尝在一起永安店",
                "pinzhi_store_id": 19189,
                "pinzhi_store_token": "56cd51b69211297104a0608f6a696b80",
                "pinzhi_oms_id": 19189,
            },
        ],
    },

    # ── 最黔线 ────────────────────────────────────────────────────────────────
    {
        "group": {
            "group_id": "GRP_ZQX0001",
            "group_name": "老江菜馆餐饮管理有限公司",
            "legal_entity": "最黔线法人代表",
            "unified_social_credit_code": "91430100ZQX0000001",
            "industry_type": "chinese_formal",
            "contact_person": "最黔线联系人",
            "contact_phone": "0731-00000002",
            "address": "湖南省长沙市",
        },
        "brand": {
            "brand_id": "BRD_ZQX0001",
            "group_id": "GRP_ZQX0001",
            "brand_name": "最黔线",
            "cuisine_type": "guizhou",
            "avg_ticket_yuan": 75,
            "target_food_cost_pct": 36,
            "target_labor_cost_pct": 23,
            "target_rent_cost_pct": 10,
            "target_waste_pct": 3,
            "status": "active",
        },
        "admin_user": {
            "username": "zqx_admin",
            "email": "admin@zuiqianxian.com",
            "password": "zqx@2026",
            "full_name": "最黔线管理员",
            "role": UserRole.STORE_MANAGER,
            "brand_id": "BRD_ZQX0001",
        },
        "pinzhi": {
            "base_url": "https://ljcg.pinzhikeji.net/pzcatering-gateway",
            "api_token": "47a428538d350fac1640a51b6bbda68c",
        },
        # 微生活会员系统配置（奥琦玮旗下）
        "weishenghuo": {
            "base_url": "https://api.acewill.net",
            "app_id": "dp2C8kqBMmGrHUVpBjqAw8q3",
            "app_key": "56573c798c8ab0dc565e704190207f12",
            "merchant_id": "1827518239",  # ✅ 已配置
        },
        "stores": [
            {
                "id": "ZQX-20529",
                "name": "马家湾店",
                "code": "ZQX-MJW001",
                "city": "长沙",
                "brand_name": "老江菜馆",
                "pinzhi_store_id": 20529,
                "pinzhi_store_token": "29cdb6acac3615070bb853afcbb32f60",
                "pinzhi_oms_id": 20529,
            },
            {
                "id": "ZQX-32109",
                "name": "东欣万象店",
                "code": "ZQX-DXWX001",
                "city": "长沙",
                "brand_name": "易善缘最黔线",
                "pinzhi_store_id": 32109,
                "pinzhi_store_token": "ed2c948284d09cf9e096e9d965936aa3",
                "pinzhi_oms_id": 32109,
            },
            {
                "id": "ZQX-32304",
                "name": "合众路店",
                "code": "ZQX-HZL001",
                "city": "长沙",
                "brand_name": "最黔线合众路店",
                "pinzhi_store_id": 32304,
                "pinzhi_store_token": "43f0b54db12b0618ea612b2a0a4d2675",
                "pinzhi_oms_id": 32304,
            },
            {
                "id": "ZQX-32305",
                "name": "广州路店",
                "code": "ZQX-GZL001",
                "city": "长沙",
                "brand_name": "最黔线广州路店",
                "pinzhi_store_id": 32305,
                "pinzhi_store_token": "a8a4e4daf86875d4a4e0254b6eb7191e",
                "pinzhi_oms_id": 32305,
            },
            {
                "id": "ZQX-32306",
                "name": "昆明路店",
                "code": "ZQX-KML001",
                "city": "长沙",
                "brand_name": "彧乡食最黔线",
                "pinzhi_store_id": 32306,
                "pinzhi_store_token": "d656668d285a100c851bbe149d4364f3",
                "pinzhi_oms_id": 32306,
            },
            {
                "id": "ZQX-32309",
                "name": "仁怀店",
                "code": "ZQX-RH001",
                "city": "仁怀",
                "brand_name": "最黔线仁怀店",
                "pinzhi_store_id": 32309,
                "pinzhi_store_token": "36bf0644e5703adc8a4d1ddd7b8f0e95",
                "pinzhi_oms_id": 32309,
            },
        ],
    },

    # ── 尚宫厨 ────────────────────────────────────────────────────────────────
    {
        "group": {
            "group_id": "GRP_SGC0001",
            "group_name": "尚宫厨餐饮管理有限公司",
            "legal_entity": "尚宫厨法人代表",
            "unified_social_credit_code": "91430100SGC0000001",
            "industry_type": "chinese_formal",
            "contact_person": "尚宫厨联系人",
            "contact_phone": "0731-00000003",
            "address": "湖南省长沙市",
        },
        "brand": {
            "brand_id": "BRD_SGC0001",
            "group_id": "GRP_SGC0001",
            "brand_name": "尚宫厨",
            "cuisine_type": "hunan",
            "avg_ticket_yuan": 180,
            "target_food_cost_pct": 33,
            "target_labor_cost_pct": 25,
            "target_rent_cost_pct": 12,
            "target_waste_pct": 2.5,
            "status": "active",
        },
        "admin_user": {
            "username": "sgc_admin",
            "email": "admin@shanggongchu.com",
            "password": "sgc@2026",
            "full_name": "尚宫厨管理员",
            "role": UserRole.STORE_MANAGER,
            "brand_id": "BRD_SGC0001",
        },
        "pinzhi": {
            "base_url": "https://xcsgc.pinzhikeji.net/pzcatering-gateway",
            "api_token": "8275cf74d1943d7a32531d2d4f889870",
        },
        # 微生活会员系统配置（奥琦玮旗下）
        "weishenghuo": {
            "base_url": "https://api.acewill.net",
            "app_id": "dp0X0jl45wauwdGgkRETITz",
            "app_key": "649738234c7426bfa0dbfa431c92a750",
            "merchant_id": "1549254243",  # ✅ 已配置（心传尚宫厨）
        },
        # 微生活卡券中心（尚宫厨独有）
        "weishenghuo_coupon": {
            "base_url": "https://apigateway.acewill.net",
            "app_id": "1549254243_6",
            "app_key": "d650652396b1bab5434d51c44c4d1436",
            "platforms": ["DOUYIN", "ALIPAY", "KUAISHOU", "XHS", "VIDEONUMBER",
                          "BANK", "QITIAN", "JD", "TAOBAO", "SHANGOU", "AMAP"],
        },
        "stores": [
            {
                "id": "SGC-2463",
                "name": "采霞街店",
                "code": "SGC-CXJ001",
                "city": "长沙",
                "brand_name": "尚宫厨",
                "pinzhi_store_id": 2463,
                "pinzhi_store_token": "852f1d34c75af0b8eb740ef47f133130",
                "pinzhi_oms_id": 2463,
            },
            {
                "id": "SGC-7896",
                "name": "湘江水岸店",
                "code": "SGC-XJSA001",
                "city": "长沙",
                "brand_name": "心传尚宫厨",
                "pinzhi_store_id": 7896,
                "pinzhi_store_token": "27a36f2feea6d3a914438f6cb32108c3",
                "pinzhi_oms_id": 7896,
            },
            {
                "id": "SGC-24777",
                "name": "乐城店",
                "code": "SGC-LC001",
                "city": "长沙",
                "brand_name": "尚宫厨乐城店",
                "pinzhi_store_id": 24777,
                "pinzhi_store_token": "5cbfb449112f698218e0b1be1a3bc7c6",
                "pinzhi_oms_id": 24777,
            },
            {
                "id": "SGC-36199",
                "name": "啫匠亲城店",
                "code": "SGC-ZJQC001",
                "city": "长沙",
                "brand_name": "尚宫厨啫匠亲城店",
                "pinzhi_store_id": 36199,
                "pinzhi_store_token": "08f3791e15f48338405728a3a92fcd7f",
                "pinzhi_oms_id": 36199,
            },
            {
                "id": "SGC-41405",
                "name": "酃湖雅院店",
                "code": "SGC-LHYY001",
                "city": "株洲",
                "brand_name": "尚宫厨酃湖雅院店",
                "pinzhi_store_id": 41405,
                "pinzhi_store_token": "bb7e89dcd0ac339b51631eca99e51c9b",
                "pinzhi_oms_id": 41405,
            },
        ],
    },
]


# ══════════════════════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════════════════════

def upsert_group(session: Session, data: dict) -> Group:
    """幂等创建/更新集团"""
    existing = session.get(Group, data["group_id"])
    if existing:
        print(f"  [skip] 集团已存在: {data['group_id']} - {data['group_name']}")
        return existing
    obj = Group(**data)
    session.add(obj)
    print(f"  [add]  集团: {data['group_id']} - {data['group_name']}")
    return obj


def upsert_brand(session: Session, data: dict) -> Brand:
    """幂等创建/更新品牌"""
    existing = session.get(Brand, data["brand_id"])
    if existing:
        print(f"  [skip] 品牌已存在: {data['brand_id']} - {data['brand_name']}")
        return existing
    obj = Brand(**data)
    session.add(obj)
    print(f"  [add]  品牌: {data['brand_id']} - {data['brand_name']}")
    return obj


def upsert_store(session: Session, data: dict, brand_id: str) -> Store:
    """幂等创建/更新门店"""
    existing = session.get(Store, data["id"])
    if existing:
        print(f"    [skip] 门店已存在: {data['id']} - {data['name']}")
        return existing
    obj = Store(
        id=data["id"],
        name=data["name"],
        code=data["code"],
        city=data["city"],
        brand_id=brand_id,
        status="active",
        is_active=True,
        seats=80,
        config={"pinzhi_brand_name": data["brand_name"]},
    )
    session.add(obj)
    print(f"    [add]  门店: {data['id']} - {data['name']} ({data['city']})")
    return obj


def upsert_admin_user(session: Session, data: dict) -> User:
    """幂等创建管理员账号"""
    from sqlalchemy import select
    stmt = select(User).where(User.username == data["username"])
    existing = session.execute(stmt).scalar_one_or_none()
    if existing:
        print(f"  [skip] 用户已存在: {data['username']}")
        return existing
    obj = User(
        id=uuid.uuid4(),
        username=data["username"],
        email=data["email"],
        hashed_password=get_password_hash(data["password"]),
        full_name=data["full_name"],
        role=data["role"],
        is_active=True,
        brand_id=data["brand_id"],
    )
    session.add(obj)
    print(f"  [add]  用户: {data['username']} / {data['password']} ({data['full_name']})")
    return obj


def upsert_external_system(
    session: Session,
    name: str,
    sys_type: IntegrationType,
    provider: str,
    api_endpoint: str,
    api_key: str,
    api_secret: str,
    store_id: str | None,
    config: dict,
    brand_id: str,
) -> ExternalSystem:
    """幂等创建外部系统集成配置（按 store_id + provider 判断唯一性）"""
    from sqlalchemy import select
    stmt = select(ExternalSystem).where(
        ExternalSystem.store_id == store_id,
        ExternalSystem.provider == provider,
        ExternalSystem.type == sys_type,
    )
    existing = session.execute(stmt).scalar_one_or_none()
    if existing:
        # 更新凭证（密钥可能变更）
        existing.api_key = api_key
        existing.api_secret = api_secret
        existing.api_endpoint = api_endpoint
        existing.config = {**existing.config, **config} if existing.config else config
        existing.status = IntegrationStatus.ACTIVE
        print(f"    [upd]  集成: {name} (store={store_id})")
        return existing
    obj = ExternalSystem(
        id=uuid.uuid4(),
        name=name,
        type=sys_type,
        provider=provider,
        version="v1",
        status=IntegrationStatus.ACTIVE,
        store_id=store_id,
        api_endpoint=api_endpoint,
        api_key=api_key,
        api_secret=api_secret,
        config={**config, "brand_id": brand_id},
        sync_enabled=True,
        sync_interval=300,
        created_by="seed_real_merchants",
    )
    session.add(obj)
    print(f"    [add]  集成: {name} (store={store_id or 'brand-level'})")
    return obj


# ══════════════════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════════════════

def seed():
    with Session(engine) as session:
        for m in MERCHANTS:
            brand_name = m["brand"]["brand_name"]
            brand_id = m["brand"]["brand_id"]
            print(f"\n{'='*60}")
            print(f"  商户：{brand_name}")
            print(f"{'='*60}")

            # 1. 集团
            upsert_group(session, m["group"])

            # 2. 品牌
            upsert_brand(session, m["brand"])

            # 3. 管理员账号
            upsert_admin_user(session, m["admin_user"])

            # 4. 门店 + 品智POS集成
            for store_data in m["stores"]:
                store = upsert_store(session, store_data, brand_id)
                pinzhi = m["pinzhi"]
                upsert_external_system(
                    session=session,
                    name=f"品智收银 - {store_data['name']}",
                    sys_type=IntegrationType.POS,
                    provider="pinzhi",
                    api_endpoint=pinzhi["base_url"],
                    api_key=pinzhi["api_token"],
                    api_secret=store_data["pinzhi_store_token"],  # 门店 Token 存 secret
                    store_id=store_data["id"],
                    config={
                        "pinzhi_store_id": store_data["pinzhi_store_id"],
                        "pinzhi_oms_id": store_data["pinzhi_oms_id"],
                        "pinzhi_store_token": store_data["pinzhi_store_token"],
                        "pinzhi_base_url": pinzhi["base_url"],
                        "brand_name": store_data["brand_name"],
                    },
                    brand_id=brand_id,
                )

            # 5. 微生活会员系统集成（奥琦玮旗下，品牌级）
            first_store_id = m["stores"][0]["id"]
            wsh = m["weishenghuo"]
            merchant_id_status = "✅ 已配置" if wsh["merchant_id"] else "⚠️  待填写"
            print(f"  [info] 微生活商户号: {wsh['merchant_id'] or '【待填写】'} {merchant_id_status}")
            upsert_external_system(
                session=session,
                name=f"微生活会员 - {brand_name}",
                sys_type=IntegrationType.MEMBER,
                provider="weishenghuo",
                api_endpoint=wsh["base_url"],
                api_key=wsh["app_id"],
                api_secret=wsh["app_key"],
                store_id=None,  # 品牌级别，不绑定单店
                config={
                    "weishenghuo_app_id": wsh["app_id"],
                    "weishenghuo_app_key": wsh["app_key"],
                    "weishenghuo_merchant_id": wsh["merchant_id"],
                    "merchant_id_pending": wsh["merchant_id"] == "",
                    "sign_algorithm": "MD5(appId+appKey+timestamp+merchantId)",
                    "brand_id": brand_id,
                },
                brand_id=brand_id,
            )

            # 6. 喰星云供应链集成（奥琦玮旗下，仅配置了的商户）
            if "chixingyun" in m:
                scm = m["chixingyun"]
                upsert_external_system(
                    session=session,
                    name=f"喰星云供应链 - {brand_name}",
                    sys_type=IntegrationType.SUPPLIER,
                    provider="chixingyun",
                    api_endpoint=scm["base_url"],
                    api_key=scm["app_key"],
                    api_secret=scm["app_secret"],
                    store_id=None,  # 品牌级别
                    config={
                        "chixingyun_base_url": scm["base_url"],
                        "chixingyun_app_key": scm["app_key"],
                        "sign_algorithm": "MD5(sorted_params+appSecret)",
                        "brand_id": brand_id,
                    },
                    brand_id=brand_id,
                )

            # 7. 微生活卡券中心（仅尚宫厨）
            if "weishenghuo_coupon" in m:
                coupon = m["weishenghuo_coupon"]
                upsert_external_system(
                    session=session,
                    name=f"微生活卡券中心 - {brand_name}",
                    sys_type=IntegrationType.MEMBER,
                    provider="weishenghuo_coupon",
                    api_endpoint=coupon["base_url"],
                    api_key=coupon["app_id"],
                    api_secret=coupon["app_key"],
                    store_id=None,
                    config={
                        "coupon_app_id": coupon["app_id"],
                        "coupon_app_key": coupon["app_key"],
                        "supported_platforms": coupon["platforms"],
                        "brand_id": brand_id,
                    },
                    brand_id=brand_id,
                )

        session.commit()
        print(f"\n{'='*60}")
        print("  ✅ 所有商户数据写入成功！")
        print(f"{'='*60}")
        _print_summary()


def _print_summary():
    print("""
┌──────────────────────────────────────────────────────────┐
│                    商户开通摘要                            │
├──────────────┬──────────┬────────────┬───────────────────┤
│ 商户         │ 门店数   │ 登录账号   │ 微生活商户号       │
├──────────────┼──────────┼────────────┼───────────────────┤
│ 尝在一起     │ 3家      │ czyz_admin │ ✅ 1275413383      │
│ 最黔线       │ 6家      │ zqx_admin  │ ✅ 1827518239      │
│ 尚宫厨       │ 5家      │ sgc_admin  │ ✅ 1549254243      │
└──────────────┴──────────┴────────────┴───────────────────┘

✅ 所有商户号已配置完毕！
  奥琦玮子系统: 品智收银(POS) + 微生活(会员) + 喰星云(供应链)

  品智数据同步（Celery 定时任务）默认每5分钟拉取一次订单数据
     启动命令: celery -A src.core.celery_tasks worker --beat -l info
""")


if __name__ == "__main__":
    seed()
