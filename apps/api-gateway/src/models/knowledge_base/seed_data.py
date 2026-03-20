"""行业字典种子数据 — 餐饮行业标准分类树与枚举。

调用 seed_industry_dictionary(session) 即可将所有预置数据写入。
使用 UPSERT 逻辑，重复运行不会报错。
"""

from __future__ import annotations

# 行业字典种子数据定义
# 格式: (dict_type, dict_code, dict_name_zh, dict_name_en, parent_code, level, sort_order)

DISH_CATEGORY_DATA = [
    # 一级分类
    ("dish_category", "hot_dish", "热菜", "Hot Dish", None, 1, 1),
    ("dish_category", "cold_dish", "凉菜", "Cold Dish", None, 1, 2),
    ("dish_category", "soup", "汤羹", "Soup", None, 1, 3),
    ("dish_category", "staple", "主食", "Staple", None, 1, 4),
    ("dish_category", "snack", "小吃点心", "Snack", None, 1, 5),
    ("dish_category", "bbq", "烧烤铁板", "BBQ", None, 1, 6),
    ("dish_category", "hotpot", "火锅锅物", "Hotpot", None, 1, 7),
    ("dish_category", "salad", "沙拉轻食", "Salad", None, 1, 8),
    ("dish_category", "dessert", "甜品", "Dessert", None, 1, 9),
    ("dish_category", "beverage", "饮品", "Beverage", None, 1, 10),
    ("dish_category", "combo", "套餐组合", "Combo", None, 1, 11),
    ("dish_category", "braised", "酱卤熟食", "Braised", None, 1, 12),
    ("dish_category", "precooked", "预制复热菜", "Precooked", None, 1, 13),
    # 热菜二级
    ("dish_category", "hot_beef", "牛肉类", "Beef", "hot_dish", 2, 1),
    ("dish_category", "hot_lamb", "羊肉类", "Lamb", "hot_dish", 2, 2),
    ("dish_category", "hot_pork", "猪肉类", "Pork", "hot_dish", 2, 3),
    ("dish_category", "hot_chicken", "鸡肉类", "Chicken", "hot_dish", 2, 4),
    ("dish_category", "hot_duck", "鸭鹅类", "Duck/Goose", "hot_dish", 2, 5),
    ("dish_category", "hot_seafood", "水产类", "Seafood", "hot_dish", 2, 6),
    ("dish_category", "hot_egg", "蛋类", "Egg", "hot_dish", 2, 7),
    ("dish_category", "hot_tofu", "豆制品类", "Tofu", "hot_dish", 2, 8),
    ("dish_category", "hot_veggie", "蔬菜类", "Vegetable", "hot_dish", 2, 9),
    ("dish_category", "hot_mushroom", "菌菇类", "Mushroom", "hot_dish", 2, 10),
    ("dish_category", "hot_mixed", "综合拼配类", "Mixed", "hot_dish", 2, 11),
    # 凉菜二级
    ("dish_category", "cold_meat", "肉类凉菜", "Meat Cold", "cold_dish", 2, 1),
    ("dish_category", "cold_veggie", "蔬菜凉菜", "Veggie Cold", "cold_dish", 2, 2),
    ("dish_category", "cold_seafood", "海鲜凉菜", "Seafood Cold", "cold_dish", 2, 3),
    ("dish_category", "cold_tofu", "豆制品凉菜", "Tofu Cold", "cold_dish", 2, 4),
    ("dish_category", "cold_braised", "酱卤前菜", "Braised Cold", "cold_dish", 2, 5),
    # 汤羹二级
    ("dish_category", "soup_clear", "清汤", "Clear Soup", "soup", 2, 1),
    ("dish_category", "soup_thick", "浓汤", "Thick Soup", "soup", 2, 2),
    ("dish_category", "soup_stew", "炖汤", "Stew", "soup", 2, 3),
    ("dish_category", "soup_congee", "羹类", "Congee", "soup", 2, 4),
    ("dish_category", "soup_hotpot_base", "火锅汤底", "Hotpot Base", "soup", 2, 5),
    # 主食二级
    ("dish_category", "staple_rice", "米饭类", "Rice", "staple", 2, 1),
    ("dish_category", "staple_fried_rice", "炒饭类", "Fried Rice", "staple", 2, 2),
    ("dish_category", "staple_noodle", "面条类", "Noodle", "staple", 2, 3),
    ("dish_category", "staple_soup_noodle", "汤面类", "Soup Noodle", "staple", 2, 4),
    ("dish_category", "staple_rice_noodle", "粉类", "Rice Noodle", "staple", 2, 5),
    ("dish_category", "staple_porridge", "粥类", "Porridge", "staple", 2, 6),
    ("dish_category", "staple_dumpling", "饺子馄饨类", "Dumpling", "staple", 2, 7),
    ("dish_category", "staple_bun", "包点类", "Bun", "staple", 2, 8),
    ("dish_category", "staple_western", "披萨意面类", "Pizza/Pasta", "staple", 2, 9),
    # 小吃点心二级
    ("dish_category", "snack_chinese", "中式点心", "Chinese Dim Sum", "snack", 2, 1),
    ("dish_category", "snack_western", "西式烘焙", "Western Bakery", "snack", 2, 2),
    ("dish_category", "snack_fried", "油炸小吃", "Fried Snack", "snack", 2, 3),
    ("dish_category", "snack_street", "街头小吃", "Street Food", "snack", 2, 4),
    ("dish_category", "snack_local", "特色地方小吃", "Local Specialty", "snack", 2, 5),
    # 甜品二级
    ("dish_category", "dessert_chinese", "中式甜品", "Chinese Dessert", "dessert", 2, 1),
    ("dish_category", "dessert_western", "西式甜品", "Western Dessert", "dessert", 2, 2),
    ("dish_category", "dessert_ice", "冰品", "Ice Cream", "dessert", 2, 3),
    ("dish_category", "dessert_pudding", "布丁奶冻", "Pudding", "dessert", 2, 4),
    ("dish_category", "dessert_pastry", "糕点", "Pastry", "dessert", 2, 5),
    # 饮品二级
    ("dish_category", "bev_tea", "茶饮", "Tea", "beverage", 2, 1),
    ("dish_category", "bev_coffee", "咖啡", "Coffee", "beverage", 2, 2),
    ("dish_category", "bev_juice", "果汁", "Juice", "beverage", 2, 3),
    ("dish_category", "bev_milk", "奶饮", "Milk Drink", "beverage", 2, 4),
    ("dish_category", "bev_alcohol", "酒精饮品", "Alcohol", "beverage", 2, 5),
    ("dish_category", "bev_special", "特色饮料", "Specialty", "beverage", 2, 6),
]

CUISINE_DATA = [
    # 中国菜系
    ("cuisine", "sichuan", "川菜", "Sichuan", None, 1, 1),
    ("cuisine", "sichuan_classic", "传统川菜", "Classic Sichuan", "sichuan", 2, 1),
    ("cuisine", "sichuan_jianghu", "江湖川菜", "Jianghu Sichuan", "sichuan", 2, 2),
    ("cuisine", "sichuan_snack", "川式小吃", "Sichuan Snacks", "sichuan", 2, 3),
    ("cuisine", "cantonese", "粤菜", "Cantonese", None, 1, 2),
    ("cuisine", "cantonese_guangfu", "广府菜", "Guangfu", "cantonese", 2, 1),
    ("cuisine", "cantonese_chaoshan", "潮汕菜", "Chaoshan", "cantonese", 2, 2),
    ("cuisine", "cantonese_hakka", "客家菜", "Hakka", "cantonese", 2, 3),
    ("cuisine", "hunan", "湘菜", "Hunan", None, 1, 3),
    ("cuisine", "shandong", "鲁菜", "Shandong", None, 1, 4),
    ("cuisine", "jiangsu", "苏菜", "Jiangsu", None, 1, 5),
    ("cuisine", "zhejiang", "浙菜", "Zhejiang", None, 1, 6),
    ("cuisine", "fujian", "闽菜", "Fujian", None, 1, 7),
    ("cuisine", "anhui", "徽菜", "Anhui", None, 1, 8),
    ("cuisine", "beijing", "北京菜", "Beijing", None, 1, 9),
    ("cuisine", "dongbei", "东北菜", "Northeast", None, 1, 10),
    ("cuisine", "hubei", "湖北菜", "Hubei", None, 1, 11),
    ("cuisine", "yungui", "云贵菜", "Yunnan-Guizhou", None, 1, 12),
    ("cuisine", "xinjiang", "新疆菜", "Xinjiang", None, 1, 13),
    ("cuisine", "northwest", "西北菜", "Northwest", None, 1, 14),
    ("cuisine", "fusion_cn", "融合中餐", "Fusion Chinese", None, 1, 15),
    # 国际菜系
    ("cuisine", "japanese", "日本料理", "Japanese", None, 1, 20),
    ("cuisine", "korean", "韩国料理", "Korean", None, 1, 21),
    ("cuisine", "thai", "泰国料理", "Thai", None, 1, 22),
    ("cuisine", "vietnamese", "越南料理", "Vietnamese", None, 1, 23),
    ("cuisine", "indian", "印度料理", "Indian", None, 1, 24),
    ("cuisine", "italian", "意大利料理", "Italian", None, 1, 25),
    ("cuisine", "french", "法国料理", "French", None, 1, 26),
    ("cuisine", "spanish", "西班牙料理", "Spanish", None, 1, 27),
    ("cuisine", "american", "美式料理", "American", None, 1, 28),
    ("cuisine", "mexican", "墨西哥料理", "Mexican", None, 1, 29),
    ("cuisine", "mediterranean", "地中海料理", "Mediterranean", None, 1, 30),
    ("cuisine", "middle_east", "中东料理", "Middle Eastern", None, 1, 31),
    ("cuisine", "fusion_intl", "现代融合料理", "Modern Fusion", None, 1, 32),
]

COOKING_METHOD_DATA = [
    ("cooking_method", "stir_fry", "炒", "Stir-fry", None, 1, 1),
    ("cooking_method", "quick_fry", "爆", "Quick-fry", None, 1, 2),
    ("cooking_method", "pan_fry", "煎", "Pan-fry", None, 1, 3),
    ("cooking_method", "deep_fry", "炸", "Deep-fry", None, 1, 4),
    ("cooking_method", "roast", "烤", "Roast/Grill", None, 1, 5),
    ("cooking_method", "bake", "焗", "Bake", None, 1, 6),
    ("cooking_method", "stew", "炖", "Stew", None, 1, 7),
    ("cooking_method", "braise", "焖", "Braise", None, 1, 8),
    ("cooking_method", "red_cook", "烧", "Red-cook", None, 1, 9),
    ("cooking_method", "lu", "卤", "Lu (spiced braise)", None, 1, 10),
    ("cooking_method", "steam", "蒸", "Steam", None, 1, 11),
    ("cooking_method", "boil", "煮", "Boil", None, 1, 12),
    ("cooking_method", "blanch", "汆", "Blanch", None, 1, 13),
    ("cooking_method", "cold_mix", "拌", "Cold-mix", None, 1, 14),
    ("cooking_method", "marinate", "腌", "Marinate/Cure", None, 1, 15),
    ("cooking_method", "smoke", "熏", "Smoke", None, 1, 16),
    ("cooking_method", "clay_pot", "煲", "Clay-pot", None, 1, 17),
    ("cooking_method", "hotpot", "涮", "Hotpot/Rinse", None, 1, 18),
    ("cooking_method", "cold_prep", "冷制", "Cold preparation", None, 1, 19),
    ("cooking_method", "raw", "生食", "Raw/Sashimi", None, 1, 20),
    ("cooking_method", "reheat", "复热", "Reheat", None, 1, 21),
    ("cooking_method", "dry_pot", "干锅", "Dry-pot", None, 1, 22),
    ("cooking_method", "teppanyaki", "铁板", "Teppanyaki", None, 1, 23),
]

FLAVOR_DATA = [
    ("flavor", "mala", "麻辣", "Mala (Numbing Spicy)", None, 1, 1),
    ("flavor", "xiang_la", "香辣", "Fragrant Spicy", None, 1, 2),
    ("flavor", "suan_la", "酸辣", "Sour Spicy", None, 1, 3),
    ("flavor", "xian_xian", "咸鲜", "Salty Fresh", None, 1, 4),
    ("flavor", "xian_tian", "鲜甜", "Fresh Sweet", None, 1, 5),
    ("flavor", "jiang_xiang", "酱香", "Sauce Fragrant", None, 1, 6),
    ("flavor", "suan_xiang", "蒜香", "Garlic", None, 1, 7),
    ("flavor", "jiao_ma", "椒麻", "Pepper Numbing", None, 1, 8),
    ("flavor", "zi_ran", "孜然", "Cumin", None, 1, 9),
    ("flavor", "ga_li", "咖喱", "Curry", None, 1, 10),
    ("flavor", "nai_xiang", "奶香", "Milky/Creamy", None, 1, 11),
    ("flavor", "yan_xun", "烟熏", "Smoky", None, 1, 12),
    ("flavor", "qing_xian", "清鲜", "Light Fresh", None, 1, 13),
    ("flavor", "tang_cu", "糖醋", "Sweet Sour", None, 1, 14),
    ("flavor", "hei_jiao", "黑椒", "Black Pepper", None, 1, 15),
    ("flavor", "fan_qie", "番茄", "Tomato", None, 1, 16),
    ("flavor", "jie_mo", "芥末", "Wasabi/Mustard", None, 1, 17),
    ("flavor", "ning_meng", "柠檬香草", "Lemon Herb", None, 1, 18),
]

INGREDIENT_CATEGORY_DATA = [
    ("ingredient_category", "meat_poultry", "肉禽类", "Meat & Poultry", None, 1, 1),
    ("ingredient_category", "meat_pork", "猪肉", "Pork", "meat_poultry", 2, 1),
    ("ingredient_category", "meat_beef", "牛肉", "Beef", "meat_poultry", 2, 2),
    ("ingredient_category", "meat_lamb", "羊肉", "Lamb", "meat_poultry", 2, 3),
    ("ingredient_category", "meat_chicken", "鸡肉", "Chicken", "meat_poultry", 2, 4),
    ("ingredient_category", "meat_duck", "鸭肉", "Duck", "meat_poultry", 2, 5),
    ("ingredient_category", "meat_offal", "内脏杂碎", "Offal", "meat_poultry", 2, 6),
    ("ingredient_category", "seafood", "水产类", "Seafood", None, 1, 2),
    ("ingredient_category", "seafood_fish", "鱼类", "Fish", "seafood", 2, 1),
    ("ingredient_category", "seafood_shrimp", "虾蟹", "Shrimp/Crab", "seafood", 2, 2),
    ("ingredient_category", "seafood_shellfish", "贝类", "Shellfish", "seafood", 2, 3),
    ("ingredient_category", "seafood_frozen", "冻品", "Frozen Seafood", "seafood", 2, 4),
    ("ingredient_category", "vegetable", "蔬菜类", "Vegetable", None, 1, 3),
    ("ingredient_category", "veg_leaf", "叶菜", "Leafy", "vegetable", 2, 1),
    ("ingredient_category", "veg_root", "根茎", "Root", "vegetable", 2, 2),
    ("ingredient_category", "veg_fruit", "果实", "Fruit Veg", "vegetable", 2, 3),
    ("ingredient_category", "mushroom", "菌菇类", "Mushroom", None, 1, 4),
    ("ingredient_category", "grain", "粮油米面", "Grain & Oil", None, 1, 5),
    ("ingredient_category", "seasoning", "调味品", "Seasoning", None, 1, 6),
    ("ingredient_category", "seasoning_soy", "酱油类", "Soy Sauce", "seasoning", 2, 1),
    ("ingredient_category", "seasoning_vinegar", "醋类", "Vinegar", "seasoning", 2, 2),
    ("ingredient_category", "seasoning_paste", "酱类", "Paste", "seasoning", 2, 3),
    ("ingredient_category", "seasoning_spice", "香辛料", "Spice", "seasoning", 2, 4),
    ("ingredient_category", "seasoning_sugar", "糖盐", "Sugar/Salt", "seasoning", 2, 5),
    ("ingredient_category", "nut_bean", "坚果豆制", "Nut & Bean", None, 1, 7),
    ("ingredient_category", "dairy_egg", "蛋奶类", "Dairy & Egg", None, 1, 8),
    ("ingredient_category", "alcohol_bev", "酒水饮料", "Alcohol & Beverage", None, 1, 9),
    ("ingredient_category", "packaging", "包材物料", "Packaging", None, 1, 10),
]

ALLERGEN_DATA = [
    ("allergen", "peanut", "花生", "Peanut", None, 1, 1),
    ("allergen", "soybean", "大豆", "Soybean", None, 1, 2),
    ("allergen", "milk", "乳制品", "Milk/Dairy", None, 1, 3),
    ("allergen", "egg", "蛋类", "Egg", None, 1, 4),
    ("allergen", "wheat", "小麦/麸质", "Wheat/Gluten", None, 1, 5),
    ("allergen", "tree_nut", "坚果", "Tree Nut", None, 1, 6),
    ("allergen", "fish", "鱼类", "Fish", None, 1, 7),
    ("allergen", "shellfish", "甲壳类", "Shellfish", None, 1, 8),
    ("allergen", "sesame", "芝麻", "Sesame", None, 1, 9),
    ("allergen", "celery", "芹菜", "Celery", None, 1, 10),
    ("allergen", "mustard", "芥末", "Mustard", None, 1, 11),
    ("allergen", "sulfite", "亚硫酸盐", "Sulfite", None, 1, 12),
]

DIETARY_TAG_DATA = [
    ("dietary_tag", "vegetarian", "素食", "Vegetarian", None, 1, 1),
    ("dietary_tag", "vegan", "纯素", "Vegan", None, 1, 2),
    ("dietary_tag", "halal", "清真", "Halal", None, 1, 3),
    ("dietary_tag", "gluten_free", "无麸质", "Gluten-free", None, 1, 4),
    ("dietary_tag", "low_fat", "低脂", "Low-fat", None, 1, 5),
    ("dietary_tag", "low_sugar", "低糖", "Low-sugar", None, 1, 6),
    ("dietary_tag", "high_protein", "高蛋白", "High-protein", None, 1, 7),
    ("dietary_tag", "lactose_free", "无乳糖", "Lactose-free", None, 1, 8),
    ("dietary_tag", "keto", "生酮", "Keto", None, 1, 9),
    ("dietary_tag", "contains_meat", "含肉", "Contains Meat", None, 1, 10),
    ("dietary_tag", "plant_based", "植物来源", "Plant-based", None, 1, 11),
    ("dietary_tag", "animal_based", "动物来源", "Animal-based", None, 1, 12),
]

COST_CATEGORY_DATA = [
    # 一级成本分类(18项)
    ("cost_category", "food_cost", "食材成本", "Food Cost", None, 1, 1),
    ("cost_category", "food_fresh_meat", "生鲜肉类", "Fresh Meat", "food_cost", 2, 1),
    ("cost_category", "food_seafood", "水产冻品", "Seafood", "food_cost", 2, 2),
    ("cost_category", "food_vegetable", "蔬菜菌菇", "Vegetable", "food_cost", 2, 3),
    ("cost_category", "food_grain", "粮油米面", "Grain & Oil", "food_cost", 2, 4),
    ("cost_category", "food_seasoning", "调味品", "Seasoning", "food_cost", 2, 5),
    ("cost_category", "food_beverage", "酒水饮料", "Beverage", "food_cost", 2, 6),
    ("cost_category", "food_dessert", "甜品原料", "Dessert Ingredient", "food_cost", 2, 7),
    ("cost_category", "packaging_cost", "包材成本", "Packaging Cost", None, 1, 2),
    ("cost_category", "beverage_material", "饮品耗材成本", "Beverage Material", None, 1, 3),
    ("cost_category", "seasoning_material", "调料耗材成本", "Seasoning Material", None, 1, 4),
    ("cost_category", "labor_cost", "人工成本", "Labor Cost", None, 1, 5),
    ("cost_category", "labor_salary", "工资薪酬", "Salary", "labor_cost", 2, 1),
    ("cost_category", "labor_social", "社保公积金", "Social Insurance", "labor_cost", 2, 2),
    ("cost_category", "labor_bonus", "奖金绩效", "Bonus", "labor_cost", 2, 3),
    ("cost_category", "labor_overtime", "加班费", "Overtime", "labor_cost", 2, 4),
    ("cost_category", "labor_temp", "临时工/小时工", "Temp/Hourly", "labor_cost", 2, 5),
    ("cost_category", "rent_cost", "房租物业", "Rent & Property", None, 1, 6),
    ("cost_category", "utility_cost", "水电燃气", "Utility", None, 1, 7),
    ("cost_category", "platform_commission", "外卖平台佣金", "Platform Commission", None, 1, 8),
    ("cost_category", "payment_fee", "支付手续费", "Payment Fee", None, 1, 9),
    ("cost_category", "marketing_cost", "营销投放", "Marketing", None, 1, 10),
    ("cost_category", "depreciation", "设备折旧", "Depreciation", None, 1, 11),
    ("cost_category", "waste_cost", "损耗报废", "Waste & Disposal", None, 1, 12),
    ("cost_category", "logistics_cost", "仓配物流", "Logistics", None, 1, 13),
    ("cost_category", "cleaning_cost", "清洁消杀", "Cleaning", None, 1, 14),
    ("cost_category", "maintenance_cost", "维修维保", "Maintenance", None, 1, 15),
    ("cost_category", "it_cost", "信息化系统费用", "IT Cost", None, 1, 16),
    ("cost_category", "hq_overhead", "总部管理分摊", "HQ Overhead", None, 1, 17),
    ("cost_category", "tax_cost", "税费", "Tax", None, 1, 18),
]

BUSINESS_TYPE_DATA = [
    ("business_type", "fine_dining", "正餐", "Fine Dining", None, 1, 1),
    ("business_type", "fast_casual", "快餐", "Fast Casual", None, 1, 2),
    ("business_type", "hotpot", "火锅", "Hotpot", None, 1, 3),
    ("business_type", "bbq", "烧烤", "BBQ", None, 1, 4),
    ("business_type", "tea_drink", "茶饮", "Tea & Drink", None, 1, 5),
    ("business_type", "catering", "团餐", "Catering", None, 1, 6),
    ("business_type", "bakery", "烘焙", "Bakery", None, 1, 7),
    ("business_type", "noodle_shop", "面馆粉店", "Noodle Shop", None, 1, 8),
    ("business_type", "dim_sum", "茶楼点心", "Dim Sum", None, 1, 9),
    ("business_type", "western", "西餐", "Western", None, 1, 10),
    ("business_type", "japanese", "日料", "Japanese", None, 1, 11),
    ("business_type", "korean", "韩料", "Korean", None, 1, 12),
]

PROCESS_STAGE_DATA = [
    ("process_stage", "prep", "初加工", "Preparation", None, 1, 1),
    ("process_stage", "marinate", "腌制", "Marination", None, 1, 2),
    ("process_stage", "cook", "烹调", "Cooking", None, 1, 3),
    ("process_stage", "plating", "装盘", "Plating", None, 1, 4),
    ("process_stage", "reheat", "复热", "Reheating", None, 1, 5),
    ("process_stage", "package", "打包外卖", "Packaging", None, 1, 6),
]

MATERIAL_TYPE_DATA = [
    ("material_type", "main", "主料", "Main Ingredient", None, 1, 1),
    ("material_type", "sub", "辅料", "Sub Ingredient", None, 1, 2),
    ("material_type", "seasoning", "调味料", "Seasoning", None, 1, 3),
    ("material_type", "spice", "香辛料", "Spice", None, 1, 4),
    ("material_type", "additive", "添加辅料", "Additive", None, 1, 5),
    ("material_type", "packaging", "包材/随餐物料", "Packaging", None, 1, 6),
]

MENU_ROLE_DATA = [
    ("menu_role", "traffic", "招牌引流", "Traffic Driver", None, 1, 1),
    ("menu_role", "profit", "利润贡献", "Profit Maker", None, 1, 2),
    ("menu_role", "filler", "菜单补充", "Menu Filler", None, 1, 3),
    ("menu_role", "anchor", "套餐锚点", "Combo Anchor", None, 1, 4),
    ("menu_role", "seasonal", "应季限定", "Seasonal", None, 1, 5),
    ("menu_role", "new_launch", "新品试销", "New Launch", None, 1, 6),
]

PRICE_BAND_DATA = [
    ("price_band", "low", "低价位", "Low", None, 1, 1),
    ("price_band", "mid", "中价位", "Mid", None, 1, 2),
    ("price_band", "high", "高价位", "High", None, 1, 3),
    ("price_band", "premium", "高端", "Premium", None, 1, 4),
]

# 汇总所有种子数据
ALL_SEED_DATA = (
    DISH_CATEGORY_DATA
    + CUISINE_DATA
    + COOKING_METHOD_DATA
    + FLAVOR_DATA
    + INGREDIENT_CATEGORY_DATA
    + ALLERGEN_DATA
    + DIETARY_TAG_DATA
    + COST_CATEGORY_DATA
    + BUSINESS_TYPE_DATA
    + PROCESS_STAGE_DATA
    + MATERIAL_TYPE_DATA
    + MENU_ROLE_DATA
    + PRICE_BAND_DATA
)


def get_seed_rows() -> list[dict]:
    """将种子数据转换为字典列表，可直接用于 bulk_insert。"""
    import uuid

    rows = []
    for item in ALL_SEED_DATA:
        dict_type, dict_code, dict_name_zh, dict_name_en, parent_code, level, sort_order = item
        rows.append({
            "id": uuid.uuid4(),
            "dict_type": dict_type,
            "dict_code": dict_code,
            "dict_name_zh": dict_name_zh,
            "dict_name_en": dict_name_en,
            "parent_code": parent_code,
            "level": level,
            "sort_order": sort_order,
            "is_active": True,
            "is_system": True,
        })
    return rows
