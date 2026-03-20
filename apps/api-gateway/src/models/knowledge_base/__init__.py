"""屯象OS 连锁餐饮行业知识库 — 三库模型。

三库架构：
1. BOM配方与工艺库 — 从原料到出品的全链路标准
2. 成本结构基准库 — 品牌/业态/门店/菜品成本分析与预警
3. 定价策略与折扣规则库 — 执行价格、促销策略、毛利保护

另附：
- 菜品知识库主档（行业级菜品字典）
- 行业字典（分类树、烹饪方法、风味、过敏原等枚举）
"""

# ── 1. BOM 配方与工艺库 ──
from .bom_recipe import (
    BOMRecipe,
    BOMRecipeCostCalc,
    BOMRecipeItem,
    BOMRecipeProcessStep,
    BOMRecipeServingStandard,
    BOMRecipeStorageRule,
    BOMRecipeVersion,
)

# ── 2. 成本结构基准库 ──
from .cost_benchmark import (
    CostBenchmark,
    CostBenchmarkItem,
    CostBenchmarkVersion,
    CostDishDailyFact,
    CostStoreDailyFact,
    CostWarningRecord,
)

# ── 3. 定价策略与折扣规则库 ──
from .pricing_strategy import (
    CouponTemplate,
    PricingDishRule,
    PricingExecutionSnapshot,
    PricingStrategy,
    PricingStrategyVersion,
    PromotionRule,
)

# ── 4. 菜品知识库主档 ──
from .dish_knowledge import (
    DishKnowledge,
    DishKnowledgeNutrition,
    DishKnowledgeOperationProfile,
    DishKnowledgeTaxonomyTag,
    DishRecipeIngredient,
    DishRecipeVersion,
    IndustryIngredientMaster,
)

# ── 5. 行业字典 ──
from .industry_dictionary import IndustryDictionary

__all__ = [
    # BOM
    "BOMRecipe",
    "BOMRecipeItem",
    "BOMRecipeProcessStep",
    "BOMRecipeServingStandard",
    "BOMRecipeStorageRule",
    "BOMRecipeVersion",
    "BOMRecipeCostCalc",
    # Cost
    "CostBenchmark",
    "CostBenchmarkItem",
    "CostBenchmarkVersion",
    "CostStoreDailyFact",
    "CostDishDailyFact",
    "CostWarningRecord",
    # Pricing
    "PricingStrategy",
    "PricingDishRule",
    "PricingStrategyVersion",
    "PromotionRule",
    "CouponTemplate",
    "PricingExecutionSnapshot",
    # Dish Knowledge
    "DishKnowledge",
    "DishRecipeVersion",
    "DishRecipeIngredient",
    "IndustryIngredientMaster",
    "DishKnowledgeNutrition",
    "DishKnowledgeOperationProfile",
    "DishKnowledgeTaxonomyTag",
    # Dictionary
    "IndustryDictionary",
]
