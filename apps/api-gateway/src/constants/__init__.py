"""餐饮行业标准常量包"""

from .industry_standards import (
    # 枚举
    CostCategoryL1,
    CostCategoryL2,
    CuisineType,
    DayType,
    EmploymentType,
    IngredientUnit,
    JobCategory,
    JobCode,
    JobLevel,
    MealPeriodStandard,
    QualityGrade,
    StorageType,
    WasteReason,
    WorkHourType,
    # 映射字典
    COST_L2_TO_L1,
    CUISINE_LABELS,
    FOOD_COST_BENCHMARK_P50,
    JOB_CODE_PREFIX,
    LABOR_COST_BENCHMARK_P50,
    MEAL_PERIOD_HOURS,
    RENT_COST_BENCHMARK_P50,
)

__all__ = [
    # 枚举
    "CuisineType",
    "CostCategoryL1",
    "CostCategoryL2",
    "MealPeriodStandard",
    "DayType",
    "JobLevel",
    "JobCategory",
    "JobCode",
    "StorageType",
    "IngredientUnit",
    "QualityGrade",
    "WasteReason",
    "EmploymentType",
    "WorkHourType",
    # 映射字典
    "CUISINE_LABELS",
    "COST_L2_TO_L1",
    "MEAL_PERIOD_HOURS",
    "JOB_CODE_PREFIX",
    "FOOD_COST_BENCHMARK_P50",
    "LABOR_COST_BENCHMARK_P50",
    "RENT_COST_BENCHMARK_P50",
]
