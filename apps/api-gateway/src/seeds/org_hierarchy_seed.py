"""
初始化示例集团的组织层级树
运行：docker exec -it -w /app zhilian-api python3 -m src.seeds.org_hierarchy_seed
"""
import asyncio
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select as sa_select
from src.models.org_config import OrgConfig as OrgConfigModel
from src.core.config import get_settings
from src.services.org_hierarchy_service import OrgHierarchyService
from src.models.org_config import ConfigKey

logger = structlog.get_logger()
settings = get_settings()


SAMPLE_TREE = [
    # (id, name, node_type, parent_id, store_type, operation_mode)
    ("grp-demo",       "屯象示例集团",   "group",  None,           None,         None),
    ("brd-zhengcan",   "示例正餐品牌",   "brand",  "grp-demo",     None,         None),
    ("brd-kuaican",    "示例快餐品牌",   "brand",  "grp-demo",     None,         None),
    ("reg-south",      "华南区",        "region", "brd-zhengcan", None,         None),
    ("reg-east",       "华东区",        "region", "brd-zhengcan", None,         None),
    ("sto-gz-001",     "广州旗舰店",     "store",  "reg-south",   "flagship",   "direct"),
    ("sto-sz-001",     "深圳购物中心店", "store",  "reg-south",   "mall",       "direct"),
    ("sto-sh-frc-001", "上海加盟店A",   "store",  "reg-east",    "franchise",  "franchise"),
    ("dept-gz-front",  "广州旗舰-前厅", "department", "sto-gz-001", None,       None),
    ("dept-gz-kitchen","广州旗舰-后厨", "department", "sto-gz-001", None,       None),
]

SAMPLE_CONFIGS = [
    # (node_id, key, value, value_type, is_override)
    # 集团级默认配置
    ("grp-demo", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS,    "6",    "int",   False),
    ("grp-demo", ConfigKey.MIN_REST_HOURS_BETWEEN_SHIFTS,"8",    "int",   False),
    ("grp-demo", ConfigKey.PROBATION_DAYS,               "90",   "int",   False),
    ("grp-demo", ConfigKey.OVERTIME_MULTIPLIER,          "1.5",  "float", False),
    ("grp-demo", ConfigKey.FOOD_COST_RATIO_TARGET,       "0.35", "float", False),
    ("grp-demo", ConfigKey.ATTENDANCE_GRACE_MINUTES,     "5",    "int",   False),
    # 快餐品牌：连续上班天数更严
    ("brd-kuaican", ConfigKey.MAX_CONSECUTIVE_WORK_DAYS, "5",    "int",   True),
    ("brd-kuaican", ConfigKey.SPLIT_SHIFT_ALLOWED,       "true", "bool",  True),
    # 华东区（上海）：劳动法加班系数更高
    ("reg-east", ConfigKey.OVERTIME_MULTIPLIER,          "2.0",  "float", True),
    # 加盟店：试用期更短（加盟商自定义）
    ("sto-sh-frc-001", ConfigKey.PROBATION_DAYS,         "30",   "int",   True),
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        svc = OrgHierarchyService(db)
        created_nodes = skipped_nodes = created_configs = skipped_configs = 0

        # 节点
        for id_, name, node_type, parent_id, store_type, op_mode in SAMPLE_TREE:
            existing = await svc.get_node(id_)
            if existing:
                skipped_nodes += 1
                continue
            await svc.create_node(
                id_=id_, name=name, node_type=node_type, parent_id=parent_id,
                store_type=store_type, operation_mode=op_mode,
            )
            created_nodes += 1
            logger.info("写入节点", id=id_, name=name)

        # 配置
        for node_id, key, value, value_type, is_override in SAMPLE_CONFIGS:
            # 检查是否已有配置，跳过（避免覆盖用户修改）
            existing_cfg_result = await db.execute(
                sa_select(OrgConfigModel).where(
                    OrgConfigModel.org_node_id == node_id,
                    OrgConfigModel.config_key == key,
                )
            )
            if existing_cfg_result.scalar_one_or_none():
                skipped_configs += 1
                continue
            await svc.set_config(
                node_id=node_id, key=key, value=value,
                value_type=value_type, is_override=is_override,
            )
            created_configs += 1

        await db.commit()

    print(f"\n组织层级种子数据写入完成:")
    print(f"  节点  — 新增: {created_nodes}, 跳过: {skipped_nodes}")
    print(f"  配置  — 新增: {created_configs}, 跳过: {skipped_configs}")


if __name__ == "__main__":
    asyncio.run(seed())
