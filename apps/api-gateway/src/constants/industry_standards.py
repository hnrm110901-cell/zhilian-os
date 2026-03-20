"""
餐饮行业标准字典（Industry Standard Dictionary）

行业不变的底层规律编码化——菜系分类、成本结构、岗位编码、运营时段。
所有枚举值为系统内唯一标识符，不允许散落自由文本。

使用方式：
    from src.constants.industry_standards import CuisineType, CostCategoryL1, ...
"""

import enum


# ─────────────────────────────────────────────────────────────────────────────
# 1. 菜系分类（Cuisine Type）
# ─────────────────────────────────────────────────────────────────────────────

class CuisineType(str, enum.Enum):
    """餐饮业态/菜系标准分类"""

    # 中式正餐
    HUNAN = "hunan"              # 湘菜
    CANTONESE = "cantonese"      # 粤菜
    SICHUAN = "sichuan"          # 川菜
    SHANDONG = "shandong"        # 鲁菜
    JIANGSU = "jiangsu"          # 苏菜/淮扬菜
    ZHEJIANG = "zhejiang"        # 浙菜
    FUJIAN = "fujian"            # 闽菜
    ANHUI = "anhui"              # 徽菜
    GUIZHOU = "guizhou"          # 黔菜

    # 特色业态
    HOTPOT = "hotpot"            # 火锅
    SEAFOOD = "seafood"          # 海鲜
    BBQ = "bbq"                  # 烧烤
    NOODLE = "noodle"            # 粉面
    DIM_SUM = "dim_sum"          # 茶点/早茶

    # 快餐/简餐
    FAST_FOOD = "fast_food"      # 快餐
    CAFETERIA = "cafeteria"      # 团餐/食堂
    BAKERY = "bakery"            # 烘焙

    # 通用
    GENERAL = "general"          # 通用（未分类）


# 菜系中文映射（用于展示）
CUISINE_LABELS: dict[str, str] = {
    CuisineType.HUNAN: "湘菜",
    CuisineType.CANTONESE: "粤菜",
    CuisineType.SICHUAN: "川菜",
    CuisineType.SHANDONG: "鲁菜",
    CuisineType.JIANGSU: "苏菜/淮扬菜",
    CuisineType.ZHEJIANG: "浙菜",
    CuisineType.FUJIAN: "闽菜",
    CuisineType.ANHUI: "徽菜",
    CuisineType.GUIZHOU: "黔菜",
    CuisineType.HOTPOT: "火锅",
    CuisineType.SEAFOOD: "海鲜",
    CuisineType.BBQ: "烧烤",
    CuisineType.NOODLE: "粉面",
    CuisineType.DIM_SUM: "茶点/早茶",
    CuisineType.FAST_FOOD: "快餐",
    CuisineType.CAFETERIA: "团餐/食堂",
    CuisineType.BAKERY: "烘焙",
    CuisineType.GENERAL: "通用",
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. 成本分类标准（Cost Category）
# ─────────────────────────────────────────────────────────────────────────────

class CostCategoryL1(str, enum.Enum):
    """一级成本分类"""
    FOOD = "food_cost"           # 食材成本
    LABOR = "labor_cost"         # 人力成本
    RENT = "rent_cost"           # 租金成本
    UTILITY = "utility_cost"     # 能源成本
    DEPRECIATION = "depreciation"  # 折旧摊销
    MARKETING = "marketing_cost"   # 营销费用


class CostCategoryL2(str, enum.Enum):
    """二级成本分类"""
    # 食材
    MAIN_INGREDIENT = "main_ingredient"   # 主料
    AUXILIARY = "auxiliary"                 # 辅料
    SEASONING = "seasoning"                # 调料
    DISPOSABLE = "disposable"              # 一次性耗材

    # 人力
    BASE_SALARY = "base_salary"            # 固定工资
    BONUS = "bonus"                        # 绩效奖金
    SOCIAL_INSURANCE = "social_insurance"  # 社保公积金
    PART_TIME = "part_time"                # 临时工/小时工

    # 能源
    WATER_ELECTRICITY = "water_electricity"  # 水电
    GAS = "gas"                              # 燃气

    # 营销
    PLATFORM_FEE = "platform_fee"          # 平台佣金
    DISCOUNT = "discount"                  # 促销折扣
    PRIVATE_DOMAIN = "private_domain"      # 私域运营


# 二级→一级映射
COST_L2_TO_L1: dict[CostCategoryL2, CostCategoryL1] = {
    CostCategoryL2.MAIN_INGREDIENT: CostCategoryL1.FOOD,
    CostCategoryL2.AUXILIARY: CostCategoryL1.FOOD,
    CostCategoryL2.SEASONING: CostCategoryL1.FOOD,
    CostCategoryL2.DISPOSABLE: CostCategoryL1.FOOD,
    CostCategoryL2.BASE_SALARY: CostCategoryL1.LABOR,
    CostCategoryL2.BONUS: CostCategoryL1.LABOR,
    CostCategoryL2.SOCIAL_INSURANCE: CostCategoryL1.LABOR,
    CostCategoryL2.PART_TIME: CostCategoryL1.LABOR,
    CostCategoryL2.WATER_ELECTRICITY: CostCategoryL1.UTILITY,
    CostCategoryL2.GAS: CostCategoryL1.UTILITY,
    CostCategoryL2.PLATFORM_FEE: CostCategoryL1.MARKETING,
    CostCategoryL2.DISCOUNT: CostCategoryL1.MARKETING,
    CostCategoryL2.PRIVATE_DOMAIN: CostCategoryL1.MARKETING,
}


# ─────────────────────────────────────────────────────────────────────────────
# 3. 营业时段标准（Meal Period）
# ─────────────────────────────────────────────────────────────────────────────

class MealPeriodStandard(str, enum.Enum):
    """标准营业时段（6档细分）

    注意：workforce.py 中的 MealPeriodType 是旧版 4 档枚举（morning/lunch/dinner/all_day），
    被 StaffingAdvice 和 LaborDemandForecast 的 DB 列使用。
    两者映射关系见下方 MEAL_PERIOD_COMPAT_MAP。
    """
    BREAKFAST = "breakfast"       # 06:00-10:00
    LUNCH = "lunch"               # 10:30-14:00
    AFTERNOON = "afternoon"       # 14:00-17:00
    DINNER = "dinner"             # 17:00-21:00
    LATE_NIGHT = "late_night"     # 21:00-02:00
    ALL_DAY = "all_day"           # 全天


# 各时段默认时间范围（HH:MM）
MEAL_PERIOD_HOURS: dict[str, tuple[str, str]] = {
    MealPeriodStandard.BREAKFAST: ("06:00", "10:00"),
    MealPeriodStandard.LUNCH: ("10:30", "14:00"),
    MealPeriodStandard.AFTERNOON: ("14:00", "17:00"),
    MealPeriodStandard.DINNER: ("17:00", "21:00"),
    MealPeriodStandard.LATE_NIGHT: ("21:00", "02:00"),
    MealPeriodStandard.ALL_DAY: ("00:00", "23:59"),
}

# 新版 MealPeriodStandard → 旧版 MealPeriodType(workforce.py) 兼容映射
# MealPeriodType 有 4 个值: morning/lunch/dinner/all_day
# MealPeriodStandard 有 6 个值（新增 breakfast/afternoon/late_night）
MEAL_PERIOD_COMPAT_MAP: dict[str, str] = {
    MealPeriodStandard.BREAKFAST: "morning",      # breakfast → morning
    MealPeriodStandard.LUNCH: "lunch",             # 直接对应
    MealPeriodStandard.AFTERNOON: "lunch",         # afternoon 归入 lunch 时段
    MealPeriodStandard.DINNER: "dinner",           # 直接对应
    MealPeriodStandard.LATE_NIGHT: "dinner",       # late_night 归入 dinner 时段
    MealPeriodStandard.ALL_DAY: "all_day",         # 直接对应
}


# ─────────────────────────────────────────────────────────────────────────────
# 4. 日期类型标准（Day Type）
# ─────────────────────────────────────────────────────────────────────────────

class DayType(str, enum.Enum):
    """营业日类型"""
    WEEKDAY = "weekday"              # 工作日
    WEEKEND = "weekend"              # 周末
    HOLIDAY = "holiday"              # 法定假日
    FESTIVAL = "festival"            # 节日（春节/中秋/情人节等）
    LOCAL_EVENT = "local_event"      # 本地事件（展会/演出/赛事）
    WEATHER_EXTREME = "weather_extreme"  # 极端天气日


# ─────────────────────────────────────────────────────────────────────────────
# 5. 岗位编码标准（Job Code）
# ─────────────────────────────────────────────────────────────────────────────

class JobLevel(str, enum.Enum):
    """岗位层级"""
    HQ = "hq"              # 总部
    REGION = "region"       # 区域
    STORE = "store"         # 门店
    KITCHEN = "kitchen"     # 后厨（门店子类）
    SUPPORT = "support"     # 支持部门


class JobCategory(str, enum.Enum):
    """岗位类别"""
    MANAGEMENT = "management"           # 管理岗
    FRONT_OF_HOUSE = "front_of_house"   # 前厅
    BACK_OF_HOUSE = "back_of_house"     # 后厨
    SUPPORT_DEPT = "support_dept"       # 支持部门


# 标准岗位编码（与 job_standards_seed.py 保持一致）
class JobCode(str, enum.Enum):
    """15个规范岗位编码"""
    CEO = "ceo"
    COO = "coo"
    AREA_MANAGER = "area_manager"
    SUPERVISOR = "supervisor"
    STORE_MANAGER = "store_manager"
    SHIFT_MANAGER = "shift_manager"
    CHEF_MANAGER = "chef_manager"
    COOK = "cook"
    WAITER = "waiter"
    CASHIER = "cashier"
    HR_MANAGER = "hr_manager"
    TRAINER = "trainer"
    PROCUREMENT_MANAGER = "procurement_manager"
    FOOD_SAFETY_MANAGER = "food_safety_manager"
    FINANCE_MANAGER = "finance_manager"


# 岗位编码→层级编码映射（用于标准化 EmploymentAssignment.position 查找）
JOB_CODE_PREFIX: dict[str, str] = {
    JobCode.CEO: "HQ-CEO",
    JobCode.COO: "HQ-COO",
    JobCode.AREA_MANAGER: "RG-AM",
    JobCode.SUPERVISOR: "RG-SUP",
    JobCode.STORE_MANAGER: "ST-MGR",
    JobCode.SHIFT_MANAGER: "ST-SHIFT",
    JobCode.CHEF_MANAGER: "KT-HEAD",
    JobCode.COOK: "KT-COOK",
    JobCode.WAITER: "ST-WAIT",
    JobCode.CASHIER: "ST-CASH",
    JobCode.HR_MANAGER: "HQ-HR",
    JobCode.TRAINER: "SP-TRAIN",
    JobCode.PROCUREMENT_MANAGER: "HQ-PROC",
    JobCode.FOOD_SAFETY_MANAGER: "HQ-FSM",
    JobCode.FINANCE_MANAGER: "HQ-FIN",
}


# ─────────────────────────────────────────────────────────────────────────────
# 6. 食材存储标准（Storage Type）
# ─────────────────────────────────────────────────────────────────────────────

class StorageType(str, enum.Enum):
    """食材存储方式"""
    COLD_CHAIN = "cold_chain"    # 冷藏 (0-4℃)
    FROZEN = "frozen"            # 冷冻 (<-18℃)
    DRY = "dry"                  # 干货
    FRESH = "fresh"              # 鲜品（当日）
    LIVE = "live"                # 活鲜


class IngredientUnit(str, enum.Enum):
    """食材计量单位"""
    KG = "kg"
    G = "g"
    L = "L"
    ML = "mL"
    PIECE = "piece"              # 个/只/条
    BOX = "box"
    BAG = "bag"
    BARREL = "barrel"            # 桶


class QualityGrade(str, enum.Enum):
    """食材质量等级"""
    A = "A"    # 优
    B = "B"    # 良
    C = "C"    # 合格
    D = "D"    # 不合格


class WasteReason(str, enum.Enum):
    """损耗原因分类"""
    EXPIRED = "expired"                # 过期
    DAMAGED = "damaged"                # 损坏
    OVERPRODUCTION = "overproduction"  # 备料过多
    COOKING_LOSS = "cooking_loss"      # 烹饪损耗（出成率）
    THEFT = "theft"                    # 偷盗/人为
    QUALITY_REJECT = "quality_reject"  # 验收不合格


# ─────────────────────────────────────────────────────────────────────────────
# 7. 用工类型标准
# ─────────────────────────────────────────────────────────────────────────────

class EmploymentType(str, enum.Enum):
    """用工类型"""
    FULL_TIME = "full_time"       # 全职
    HOURLY = "hourly"             # 小时工
    OUTSOURCED = "outsourced"     # 外包
    DISPATCHED = "dispatched"     # 劳务派遣
    PARTNER = "partner"           # 合伙人


class WorkHourType(str, enum.Enum):
    """工时制度"""
    STANDARD = "standard"         # 标准工时（8h/天, 40h/周）
    FLEXIBLE = "flexible"         # 综合计算工时
    SHIFT = "shift"               # 不定时工时（轮班制）


# ─────────────────────────────────────────────────────────────────────────────
# 8. 行业成本基准线常量（快速查询用，完整数据在 industry_benchmarks 表）
# ─────────────────────────────────────────────────────────────────────────────

# 各菜系食材成本率基准（p50 中位数，%）
FOOD_COST_BENCHMARK_P50: dict[str, float] = {
    CuisineType.HUNAN: 33.0,
    CuisineType.CANTONESE: 35.0,
    CuisineType.SICHUAN: 32.0,
    CuisineType.HOTPOT: 38.0,
    CuisineType.SEAFOOD: 40.0,
    CuisineType.FAST_FOOD: 30.0,
    CuisineType.NOODLE: 28.0,
    CuisineType.BBQ: 35.0,
    CuisineType.GUIZHOU: 32.0,
    CuisineType.GENERAL: 33.0,
    CuisineType.SHANDONG: 34.0,
    CuisineType.JIANGSU: 35.0,
    CuisineType.ZHEJIANG: 34.0,
    CuisineType.FUJIAN: 36.0,
    CuisineType.ANHUI: 32.0,
    CuisineType.DIM_SUM: 30.0,
    CuisineType.CAFETERIA: 35.0,
    CuisineType.BAKERY: 28.0,
}

# 人力成本率基准（p50 中位数，%）
LABOR_COST_BENCHMARK_P50: dict[str, float] = {
    CuisineType.HUNAN: 22.0,
    CuisineType.CANTONESE: 24.0,
    CuisineType.SICHUAN: 21.0,
    CuisineType.HOTPOT: 18.0,
    CuisineType.SEAFOOD: 20.0,
    CuisineType.FAST_FOOD: 25.0,
    CuisineType.NOODLE: 20.0,
    CuisineType.BBQ: 19.0,
    CuisineType.GUIZHOU: 21.0,
    CuisineType.GENERAL: 22.0,
    CuisineType.SHANDONG: 22.0,
    CuisineType.JIANGSU: 23.0,
    CuisineType.ZHEJIANG: 23.0,
    CuisineType.FUJIAN: 21.0,
    CuisineType.ANHUI: 20.0,
    CuisineType.DIM_SUM: 26.0,
    CuisineType.CAFETERIA: 28.0,
    CuisineType.BAKERY: 22.0,
}

# 租金成本率基准（p50 中位数，%）
RENT_COST_BENCHMARK_P50: dict[str, float] = {
    CuisineType.HUNAN: 10.0,
    CuisineType.CANTONESE: 12.0,
    CuisineType.SICHUAN: 10.0,
    CuisineType.HOTPOT: 8.0,
    CuisineType.SEAFOOD: 9.0,
    CuisineType.FAST_FOOD: 15.0,
    CuisineType.NOODLE: 12.0,
    CuisineType.BBQ: 10.0,
    CuisineType.GUIZHOU: 9.0,
    CuisineType.GENERAL: 10.0,
    CuisineType.SHANDONG: 10.0,
    CuisineType.JIANGSU: 12.0,
    CuisineType.ZHEJIANG: 13.0,
    CuisineType.FUJIAN: 10.0,
    CuisineType.ANHUI: 8.0,
    CuisineType.DIM_SUM: 14.0,
    CuisineType.CAFETERIA: 12.0,
    CuisineType.BAKERY: 15.0,
}
