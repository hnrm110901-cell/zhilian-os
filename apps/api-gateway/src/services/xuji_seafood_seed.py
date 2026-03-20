"""
XujiSeafoodSeedService — 徐记海鲜模拟数据种子

用于 POC 验证：模拟徐记海鲜 2 家门店的真实业务场景
包含：组织架构 + 120名员工 + 岗位定义 + 排班模板 + 薪酬规则 + 旅程模板

徐记海鲜基本信息：
- 品牌：徐记海鲜（高端海鲜连锁，湖南龙头）
- POS：奥琦玮
- 门店规模：单店50-80人
- 特点：高客单价(人均200+)、海鲜损耗管控严格、厨师技能要求高
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 常量定义 ──────────────────────────────────────────

BRAND_ID = "brand_xuji"
BRAND_NAME = "徐记海鲜"

# 两家模拟门店
STORES = [
    {
        "id": "xuji_wuyi",
        "name": "徐记海鲜·五一广场店",
        "address": "长沙市芙蓉区五一广场万达广场4F",
        "city": "长沙",
        "capacity": 180,
        "tables": 45,
    },
    {
        "id": "xuji_meixi",
        "name": "徐记海鲜·梅溪湖店",
        "address": "长沙市岳麓区梅溪湖步步高广场3F",
        "city": "长沙",
        "capacity": 220,
        "tables": 55,
    },
]

# 岗位定义（含餐饮特色岗位）
POSITIONS = [
    # 管理层
    {"code": "store_manager", "name": "店长", "category": "管理",
     "base_salary_fen": 1500000, "headcount_per_store": 1},
    {"code": "asst_manager", "name": "副店长", "category": "管理",
     "base_salary_fen": 1000000, "headcount_per_store": 1},

    # 厨房
    {"code": "head_chef", "name": "厨师长", "category": "厨房",
     "base_salary_fen": 1200000, "headcount_per_store": 1},
    {"code": "sous_chef", "name": "副厨师长", "category": "厨房",
     "base_salary_fen": 900000, "headcount_per_store": 2},
    {"code": "seafood_chef", "name": "海鲜档主厨", "category": "厨房",
     "base_salary_fen": 1000000, "headcount_per_store": 2},
    {"code": "wok_chef", "name": "炒锅师傅", "category": "厨房",
     "base_salary_fen": 800000, "headcount_per_store": 4},
    {"code": "cold_dish", "name": "凉菜师傅", "category": "厨房",
     "base_salary_fen": 600000, "headcount_per_store": 2},
    {"code": "dim_sum", "name": "点心师傅", "category": "厨房",
     "base_salary_fen": 650000, "headcount_per_store": 2},
    {"code": "prep_cook", "name": "切配", "category": "厨房",
     "base_salary_fen": 500000, "headcount_per_store": 4},
    {"code": "kitchen_helper", "name": "厨房帮工", "category": "厨房",
     "base_salary_fen": 400000, "headcount_per_store": 3},

    # 前厅
    {"code": "floor_manager", "name": "楼面经理", "category": "前厅",
     "base_salary_fen": 800000, "headcount_per_store": 1},
    {"code": "captain", "name": "领班", "category": "前厅",
     "base_salary_fen": 600000, "headcount_per_store": 3},
    {"code": "waiter", "name": "服务员", "category": "前厅",
     "base_salary_fen": 450000, "headcount_per_store": 12},
    {"code": "greeter", "name": "迎宾", "category": "前厅",
     "base_salary_fen": 420000, "headcount_per_store": 2},
    {"code": "cashier", "name": "收银员", "category": "前厅",
     "base_salary_fen": 450000, "headcount_per_store": 2},

    # 后勤
    {"code": "purchaser", "name": "采购员", "category": "后勤",
     "base_salary_fen": 600000, "headcount_per_store": 1},
    {"code": "warehouse", "name": "仓管员", "category": "后勤",
     "base_salary_fen": 500000, "headcount_per_store": 1},
    {"code": "cleaner", "name": "保洁员", "category": "后勤",
     "base_salary_fen": 380000, "headcount_per_store": 3},
    {"code": "security", "name": "保安", "category": "后勤",
     "base_salary_fen": 400000, "headcount_per_store": 2},

    # 海鲜特色岗
    {"code": "aquarium_keeper", "name": "海鲜养殖员", "category": "海鲜",
     "base_salary_fen": 550000, "headcount_per_store": 2},
    {"code": "seafood_display", "name": "海鲜展示员", "category": "海鲜",
     "base_salary_fen": 500000, "headcount_per_store": 2},
]

# 班次模板
SHIFT_TEMPLATES = [
    {"name": "早班", "start": "09:00", "end": "14:00", "hours": 5,
     "positions": ["prep_cook", "kitchen_helper", "cleaner", "warehouse"]},
    {"name": "中班", "start": "10:00", "end": "14:30", "hours": 4.5,
     "positions": ["waiter", "greeter", "cashier"]},
    {"name": "晚班", "start": "16:30", "end": "22:00", "hours": 5.5,
     "positions": ["waiter", "greeter", "cashier"]},
    {"name": "通班", "start": "09:30", "end": "22:00", "hours": 10,
     "break_hours": 2.5,
     "positions": ["store_manager", "head_chef", "floor_manager", "purchaser"]},
    {"name": "厨房早班", "start": "08:30", "end": "14:30", "hours": 6,
     "positions": ["wok_chef", "cold_dish", "dim_sum", "seafood_chef"]},
    {"name": "厨房晚班", "start": "15:30", "end": "22:30", "hours": 7,
     "positions": ["wok_chef", "cold_dish", "dim_sum", "seafood_chef"]},
    {"name": "海鲜班", "start": "07:00", "end": "15:00", "hours": 8,
     "positions": ["aquarium_keeper", "seafood_display"]},
]

# 姓氏 + 名（随机组合生成中文名）
_SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
    "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
]
_GIVEN_NAMES = [
    "伟", "芳", "娜", "秀英", "敏", "静", "强", "磊", "洋", "勇",
    "艳", "杰", "军", "丽", "超", "娟", "涛", "明", "华", "飞",
    "平", "刚", "桂英", "建华", "建国", "建军", "建平", "玉兰", "秀兰", "婷",
    "志强", "志明", "志伟", "海燕", "海涛", "海波", "小红", "小明", "小华", "小军",
    "文", "武", "龙", "凤", "鑫", "浩", "宇", "欣", "怡", "佳",
    "瑞", "琳", "雪", "萌", "思", "雨", "晨", "辰", "宁", "悦",
]

# 旅程模板：厨师成长之路（徐记海鲜特色）
CHEF_JOURNEY_STAGES = [
    {
        "name": "新人融入期",
        "description": "熟悉徐记文化、海鲜知识、厨房安全规范",
        "min_days": 3, "max_days": 7, "target_days": 5,
        "icon": "🌱",
        "tasks": [
            {"name": "完成入职培训（徐记文化+食品安全）", "type": "training", "required": True},
            {"name": "熟悉厨房动线和设备位置", "type": "observation", "required": True},
            {"name": "学习海鲜品种识别（20种常见海鲜）", "type": "knowledge", "required": True},
            {"name": "通过卫生安全考核", "type": "exam", "required": True},
        ],
        "milestone_types": ["onboard"],
    },
    {
        "name": "试岗期",
        "description": "在师傅指导下完成基础操作，通过试岗考核",
        "min_days": 14, "max_days": 30, "target_days": 21,
        "icon": "🔧",
        "tasks": [
            {"name": "掌握基础刀工（丝/片/丁/块）", "type": "skill", "required": True},
            {"name": "独立完成3道徐记基础菜品", "type": "practice", "required": True},
            {"name": "学习海鲜宰杀和处理技术", "type": "skill", "required": True},
            {"name": "通过师傅实操考核（≥70分）", "type": "exam", "required": True},
        ],
        "milestone_types": ["trial_pass", "first_solo"],
    },
    {
        "name": "成长期",
        "description": "独立上岗操作，提升出品质量和速度",
        "min_days": 60, "max_days": 90, "target_days": 75,
        "icon": "📈",
        "tasks": [
            {"name": "独立操作本岗位所有菜品", "type": "skill", "required": True},
            {"name": "高峰期出品速度达标", "type": "performance", "required": True},
            {"name": "完成食材成本控制培训", "type": "training", "required": True},
            {"name": "连续2周零投诉", "type": "quality", "required": False},
        ],
        "milestone_types": ["probation_pass", "first_praise"],
    },
    {
        "name": "熟手期",
        "description": "稳定高质量出品，开始关注成本控制和创新",
        "min_days": 90, "max_days": 180, "target_days": 120,
        "icon": "⭐",
        "tasks": [
            {"name": "出品合格率≥98%", "type": "quality", "required": True},
            {"name": "食材损耗率低于岗位基准", "type": "cost", "required": True},
            {"name": "完成至少1个技能升级认证", "type": "certification", "required": True},
            {"name": "提出1条合理化建议并被采纳", "type": "innovation", "required": False},
        ],
        "milestone_types": ["skill_up", "zero_waste_month"],
    },
    {
        "name": "能手期",
        "description": "技能全面、能带新人、参与菜品创新",
        "min_days": 180, "max_days": 365, "target_days": 270,
        "icon": "🏅",
        "tasks": [
            {"name": "掌握至少2个岗位的操作技能", "type": "skill", "required": True},
            {"name": "担任新人师傅（带满1个周期）", "type": "mentoring", "required": True},
            {"name": "参与季度菜品创新会议", "type": "innovation", "required": False},
            {"name": "获得月度/季度优秀员工", "type": "recognition", "required": False},
        ],
        "milestone_types": ["mentor_first", "sales_champion"],
    },
    {
        "name": "匠人期",
        "description": "行业标杆级别，技术精湛、文化传承、创新引领",
        "min_days": 365, "max_days": None, "target_days": 730,
        "icon": "🏆",
        "tasks": [
            {"name": "通过品牌级技能认证（高手/匠人）", "type": "certification", "required": True},
            {"name": "独立研发新菜品并上架", "type": "innovation", "required": True},
            {"name": "累计带出3名合格徒弟", "type": "mentoring", "required": True},
            {"name": "获得年度最佳厨师奖", "type": "recognition", "required": False},
        ],
        "milestone_types": ["promotion", "anniversary", "culture_star"],
    },
]

# 服务员成长之路
WAITER_JOURNEY_STAGES = [
    {
        "name": "新人融入期",
        "description": "熟悉徐记服务标准、菜品知识、礼仪规范",
        "min_days": 3, "max_days": 7, "target_days": 5,
        "icon": "🌱",
        "tasks": [
            {"name": "完成入职培训（徐记文化+服务标准）", "type": "training", "required": True},
            {"name": "熟记菜单（至少80%菜品名称和特色）", "type": "knowledge", "required": True},
            {"name": "学习点餐系统操作", "type": "system", "required": True},
            {"name": "掌握基础服务礼仪", "type": "skill", "required": True},
        ],
        "milestone_types": ["onboard"],
    },
    {
        "name": "见习服务期",
        "description": "跟随老员工学习，逐步独立接待",
        "min_days": 7, "max_days": 21, "target_days": 14,
        "icon": "👀",
        "tasks": [
            {"name": "跟台服务满20桌", "type": "practice", "required": True},
            {"name": "独立完成10桌点餐和上菜", "type": "practice", "required": True},
            {"name": "学习海鲜推荐话术", "type": "knowledge", "required": True},
            {"name": "通过服务流程考核", "type": "exam", "required": True},
        ],
        "milestone_types": ["trial_pass"],
    },
    {
        "name": "独立服务期",
        "description": "独立负责区域服务，提升客户满意度",
        "min_days": 30, "max_days": 60, "target_days": 45,
        "icon": "💪",
        "tasks": [
            {"name": "独立负责区域（4-6桌）", "type": "assignment", "required": True},
            {"name": "客户满意度评分≥4.5/5", "type": "quality", "required": True},
            {"name": "完成酒水推荐培训", "type": "training", "required": False},
            {"name": "首次获得顾客主动表扬", "type": "recognition", "required": False},
        ],
        "milestone_types": ["probation_pass", "first_praise"],
    },
    {
        "name": "优秀服务期",
        "description": "服务技能全面、高客单价推荐、处理投诉",
        "min_days": 90, "max_days": 180, "target_days": 120,
        "icon": "⭐",
        "tasks": [
            {"name": "个人推荐菜品提升桌均消费≥15%", "type": "performance", "required": True},
            {"name": "独立处理客户投诉≥3次", "type": "skill", "required": True},
            {"name": "获得VIP客户回头指名", "type": "recognition", "required": False},
            {"name": "完成领班培训课程", "type": "training", "required": False},
        ],
        "milestone_types": ["skill_up", "sales_champion"],
    },
    {
        "name": "领班储备期",
        "description": "带新人、协调区域、储备管理能力",
        "min_days": 180, "max_days": 365, "target_days": 270,
        "icon": "🏅",
        "tasks": [
            {"name": "担任新人师傅并带满1个周期", "type": "mentoring", "required": True},
            {"name": "代理领班职责满1周", "type": "management", "required": True},
            {"name": "参与排班和人员调度", "type": "management", "required": False},
            {"name": "获得月度服务之星", "type": "recognition", "required": False},
        ],
        "milestone_types": ["mentor_first", "promotion"],
    },
]


class XujiSeafoodSeedService:
    """徐记海鲜模拟数据种子服务"""

    @staticmethod
    async def seed_all(db: AsyncSession) -> dict:
        """一键初始化徐记海鲜全部模拟数据"""
        results = {}

        # 1. 创建门店
        stores = await XujiSeafoodSeedService._seed_stores(db)
        results["stores"] = stores

        # 2. 创建员工
        employees = await XujiSeafoodSeedService._seed_employees(db)
        results["employees"] = employees

        # 3. 创建旅程模板
        journeys = await XujiSeafoodSeedService._seed_journey_templates(db)
        results["journey_templates"] = journeys

        await db.commit()

        logger.info("徐记海鲜模拟数据初始化完成",
                    stores=stores["count"],
                    employees=employees["count"],
                    journey_templates=journeys["count"])

        return results

    @staticmethod
    async def _seed_stores(db: AsyncSession) -> dict:
        """创建门店"""
        from src.models.store import Store

        created = 0
        for s in STORES:
            existing = await db.get(Store, s["id"])
            if existing:
                continue
            store = Store(
                id=s["id"],
                name=s["name"],
                code=s["id"].replace("_", ""),  # xuji_wuyi → xujiwuyi
                brand_id=BRAND_ID,
                address=s.get("address"),
                city=s.get("city"),
                status="active",
            )
            db.add(store)
            created += 1

        if created:
            await db.flush()
        return {"count": created, "store_ids": [s["id"] for s in STORES]}

    @staticmethod
    async def _seed_employees(db: AsyncSession) -> dict:
        """创建模拟员工（基于 Person 模型）"""
        from src.models.hr.person import Person

        import random
        random.seed(42)  # 确保可重复

        created = 0
        name_index = 0

        for store in STORES:
            for pos in POSITIONS:
                for i in range(pos["headcount_per_store"]):
                    # 生成中文名
                    surname = _SURNAMES[name_index % len(_SURNAMES)]
                    given = _GIVEN_NAMES[name_index % len(_GIVEN_NAMES)]
                    name = surname + given
                    name_index += 1

                    # 检查是否已存在
                    from sqlalchemy import select as sa_select
                    check = await db.execute(
                        sa_select(Person).where(
                            Person.name == name,
                            Person.store_id == store["id"],
                        ).limit(1)
                    )
                    if check.scalar_one_or_none():
                        continue

                    # 随机入职日期（过去1-5年）
                    days_ago = random.randint(30, 1800)
                    hire_date = date.today() - timedelta(days=days_ago)

                    # 确定职业阶段
                    if days_ago > 365:
                        career_stage = "senior" if days_ago > 730 else "regular"
                    elif days_ago > 90:
                        career_stage = "regular"
                    else:
                        career_stage = "probation"

                    person = Person(
                        name=name,
                        phone=f"138{random.randint(10000000, 99999999)}",
                        store_id=store["id"],
                        career_stage=career_stage,
                        is_active=True,
                        gender=random.choice(["男", "女"]),
                        birth_date=date(
                            random.randint(1985, 2003),
                            random.randint(1, 12),
                            random.randint(1, 28),
                        ),
                        profile_ext={
                            "position_code": pos["code"],
                            "position_name": pos["name"],
                            "category": pos["category"],
                            "base_salary_fen": pos["base_salary_fen"],
                            "hire_date": hire_date.isoformat(),
                            "brand_id": BRAND_ID,
                        },
                    )
                    db.add(person)
                    created += 1

        if created:
            await db.flush()
        return {"count": created, "brand": BRAND_NAME}

    @staticmethod
    async def _seed_journey_templates(db: AsyncSession) -> dict:
        """创建旅程模板"""
        from src.services.mission_journey_service import MissionJourneyService

        templates_created = 0

        # 厨师成长之路
        result = await MissionJourneyService.create_template(
            db,
            name="厨师成长之路（徐记海鲜）",
            journey_type="career",
            brand_id=BRAND_ID,
            description="从学徒到匠人，记录每一位厨师的成长旅程",
            applicable_positions=["head_chef", "sous_chef", "seafood_chef",
                                  "wok_chef", "cold_dish", "dim_sum",
                                  "prep_cook", "kitchen_helper"],
            estimated_months=24,
            stages=CHEF_JOURNEY_STAGES,
        )
        if "error" not in result:
            templates_created += 1

        # 服务员成长之路
        result = await MissionJourneyService.create_template(
            db,
            name="服务之星成长之路（徐记海鲜）",
            journey_type="career",
            brand_id=BRAND_ID,
            description="从新人到领班，每一次微笑都值得被记住",
            applicable_positions=["waiter", "greeter", "captain",
                                  "floor_manager", "cashier"],
            estimated_months=18,
            stages=WAITER_JOURNEY_STAGES,
        )
        if "error" not in result:
            templates_created += 1

        return {"count": templates_created, "brand": BRAND_NAME}
