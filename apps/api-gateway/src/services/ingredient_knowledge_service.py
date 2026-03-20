"""
原材料知识库服务（Ingredient Knowledge Service）

将 GI/原生态原材料档案内化为屯象OS可成长的知识库。

核心能力：
  1. 原材料主数据管理（244+ GI 原材料 + 扩展）
  2. 品类分类体系（13大类 → 二级分类 → SKU）
  3. 产地溯源（省份 + 产区 + GI认证状态）
  4. 餐饮应用映射（原料 → 菜系 → 适用品类 → 风味特征）
  5. 供应链评估（季节性 + 稳定性 + 采购等级）
  6. 知识增长机制（从POS数据/采购单自动发现新原料）
  7. 与风味本体论对接（自动生成12维风味向量）

数据来源：
  - china_gi_eco_restaurant_database.xlsx（244条中国GI原材料）
  - gi_restaurant_materials.md（全球GI补充）
  - POS菜品BOM反向提取
  - 供应商报价单自动识别
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class IngredientRecord:
    """原材料知识库记录"""
    record_id: str
    category_l1: str                 # 一级品类（13大类）
    category_l2: str                 # 二级品类
    ingredient_name: str             # 原料名称（含产地特征）
    standard_name: str               # 标准商品名（统一SKU）
    origin_region: str               # 主要产区
    province: str                    # 省份
    attribute_type: str              # GI/原生态候选 等
    gi_status: str                   # GI核验状态
    eco_level: str                   # 原生态属性（高/中/低）
    green_cert: str                  # 绿色/有机/名特优新认证
    flavor_profile: str              # 代表风味特征
    cuisine_application: str         # 餐饮应用菜系
    dish_categories: str             # 适用品类
    supply_season: str               # 供应季节
    supply_stability: str            # 年供货稳定性
    spec_grade: str                  # 规格等级
    acceptance_standard: str         # 验收标准
    risk_points: str                 # 风险点
    purchase_grade: str              # 采购等级（A/B/C）
    source_category: str             # 来源分类
    data_source: str                 # 数据来源
    notes: str = ""
    flavor_vector: Optional[List[float]] = None  # 12维风味向量（对接风味本体论）
    created_at: str = ""
    updated_at: str = ""


# ── 13大品类体系 ──────────────────────────────────────────────────────────────

CATEGORY_TAXONOMY = {
    "粮食与主食原料": {
        "subcategories": ["粮食/大米", "粮食/面粉", "粮食/杂粮", "米粉/米线"],
        "default_flavor_dims": [0, 0.2, 0, 0, 0.1, 0, 0, 0, 0, 0, 0, 0],  # 微甜
    },
    "杂粮、豆类与薯芋": {
        "subcategories": ["杂粮", "豆类", "薯芋"],
        "default_flavor_dims": [0, 0.2, 0, 0, 0.2, 0, 0, 0, 0.1, 0, 0, 0],
    },
    "食用油与油料": {
        "subcategories": ["植物油", "动物油", "特种油"],
        "default_flavor_dims": [0, 0, 0, 0, 0.1, 0, 0, 0, 0.3, 0, 0, 0.1],
    },
    "蔬菜与山野菜": {
        "subcategories": ["叶菜", "根茎", "瓜果", "山野菜", "芽苗"],
        "default_flavor_dims": [0.1, 0.1, 0.1, 0, 0.2, 0, 0, 0, 0, 0.2, 0, 0],
    },
    "食用菌、藻类与竹笋": {
        "subcategories": ["食用菌", "藻类", "竹笋"],
        "default_flavor_dims": [0, 0, 0, 0, 0.8, 0, 0, 0.1, 0, 0, 0.3, 0],
    },
    "水果、坚果与干果": {
        "subcategories": ["鲜果", "坚果", "干果"],
        "default_flavor_dims": [0.3, 0.6, 0, 0, 0.1, 0, 0, 0, 0.4, 0.1, 0, 0],
    },
    "茶叶、花草与饮品原料": {
        "subcategories": ["绿茶", "红茶", "白茶", "花草茶", "饮品原料"],
        "default_flavor_dims": [0, 0.1, 0.3, 0, 0, 0, 0, 0, 0, 0.7, 0.2, 0],
    },
    "香辛料、药食同源与调香原料": {
        "subcategories": ["香辛料", "药食同源", "调香"],
        "default_flavor_dims": [0, 0, 0.1, 0.5, 0.1, 0, 0.1, 0, 0, 0.3, 0.2, 0],
    },
    "畜禽肉蛋": {
        "subcategories": ["猪肉", "牛肉", "羊肉", "禽肉", "蛋类"],
        "default_flavor_dims": [0, 0.1, 0, 0, 0.7, 0.1, 0, 0, 0, 0, 0, 0.1],
    },
    "水产与水生食材": {
        "subcategories": ["鱼类", "虾蟹", "贝类", "水生植物"],
        "default_flavor_dims": [0, 0.1, 0, 0, 0.9, 0.1, 0, 0, 0, 0, 0, 0],
    },
    "发酵调味品与基础调料": {
        "subcategories": ["酱油/醋", "豆酱/辣酱", "腐乳/豆豉", "基础调料"],
        "default_flavor_dims": [0.2, 0.1, 0, 0.2, 0.6, 0.8, 0, 0.7, 0, 0, 0, 0],
    },
    "腌腊、熟制与地方加工食材": {
        "subcategories": ["腌腊", "熟制", "地方特产"],
        "default_flavor_dims": [0.1, 0.1, 0, 0.1, 0.5, 0.7, 0.6, 0.4, 0, 0, 0.1, 0],
    },
    "糖、蜜、盐及其他特色原料": {
        "subcategories": ["糖", "蜜", "盐", "特色原料"],
        "default_flavor_dims": [0, 0.8, 0, 0, 0, 0.3, 0, 0, 0, 0, 0, 0.1],
    },
}

# ── 省份补全映射（基于产区自动推断） ────────────────────────────────────────────

REGION_PROVINCE_MAP = {
    "五常": "黑龙江", "盘锦": "辽宁", "兴化": "江苏", "饶河": "黑龙江",
    "舒兰": "吉林", "万年": "江西", "丰城": "江西", "遂昌": "浙江",
    "响水": "江苏", "庆安": "黑龙江", "宁夏": "宁夏", "青稞": "西藏",
    "恩施": "湖北", "信阳": "河南", "安吉": "浙江", "西湖": "浙江",
    "武夷山": "福建", "祁门": "安徽", "六安": "安徽", "正山": "福建",
    "安溪": "福建", "云南": "云南", "凤凰": "广东", "洞庭": "湖南",
    "郫都": "四川", "平遥": "山西", "镇江": "江苏", "永川": "重庆",
    "古田": "福建", "庆元": "浙江", "汝城": "湖南", "靖州": "湖南",
    "洞口": "湖南", "新晃": "湖南", "攸县": "湖南", "茶陵": "湖南",
    "宁乡": "湖南", "长沙": "湖南", "湘西": "湖南", "张家界": "湖南",
    "永顺": "湖南", "浏阳": "湖南", "临武": "湖南", "桃源": "湖南",
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def auto_fill_province(region: str, existing_province: str) -> str:
    """根据产区自动补全省份"""
    if existing_province and existing_province != "待补充":
        return existing_province
    for keyword, province in REGION_PROVINCE_MAP.items():
        if keyword in region:
            return province
    return "待补充"


def generate_flavor_vector(
    category_l1: str,
    flavor_profile: str,
    ingredient_name: str,
) -> List[float]:
    """
    基于品类和风味描述生成12维风味向量。
    初始版本使用品类默认值 + 关键词微调。
    """
    # 品类基础向量
    cat_def = CATEGORY_TAXONOMY.get(category_l1, {})
    base = list(cat_def.get("default_flavor_dims", [0.0] * 12))

    # 风味关键词微调
    flavor_adjustments = {
        "辣": (3, 0.3), "麻": (3, 0.2), "鲜": (4, 0.2), "甜": (1, 0.2),
        "酸": (0, 0.2), "咸": (5, 0.2), "苦": (2, 0.1), "香": (9, 0.2),
        "烟熏": (6, 0.3), "发酵": (7, 0.3), "坚果": (8, 0.2),
        "花": (9, 0.2), "木": (10, 0.2), "奶": (11, 0.2),
        "米香": (8, 0.1), "谷香": (8, 0.1),
    }

    text = f"{flavor_profile} {ingredient_name}"
    for keyword, (dim_idx, delta) in flavor_adjustments.items():
        if keyword in text:
            base[dim_idx] = min(1.0, base[dim_idx] + delta)

    return [round(v, 2) for v in base]


def identify_data_gaps(records: List[IngredientRecord]) -> Dict:
    """
    识别数据缺口，生成补全优先级清单。
    """
    gaps = {
        "missing_province": [],
        "missing_green_cert": [],
        "missing_flavor_vector": [],
        "low_quality_records": [],
    }

    for r in records:
        if not r.province or r.province == "待补充":
            gaps["missing_province"].append(r.record_id)
        if not r.green_cert or r.green_cert == "待补充":
            gaps["missing_green_cert"].append(r.record_id)
        if not r.flavor_vector:
            gaps["missing_flavor_vector"].append(r.record_id)
        missing_count = sum(1 for v in [r.province, r.green_cert, r.spec_grade]
                          if not v or v == "待补充")
        if missing_count >= 2:
            gaps["low_quality_records"].append(r.record_id)

    return {
        "total_records": len(records),
        "missing_province": len(gaps["missing_province"]),
        "missing_green_cert": len(gaps["missing_green_cert"]),
        "missing_flavor_vector": len(gaps["missing_flavor_vector"]),
        "low_quality_records": len(gaps["low_quality_records"]),
        "completeness_pct": round(
            (1 - len(gaps["low_quality_records"]) / max(len(records), 1)) * 100, 1
        ),
        "detail": gaps,
    }


def enrich_record(record: IngredientRecord) -> IngredientRecord:
    """
    自动补全单条记录的缺失字段。
    1. 省份：基于产区推断
    2. 风味向量：基于品类+风味描述生成
    3. 更新时间戳
    """
    record.province = auto_fill_province(record.origin_region, record.province)
    if not record.flavor_vector:
        record.flavor_vector = generate_flavor_vector(
            record.category_l1, record.flavor_profile, record.ingredient_name,
        )
    record.updated_at = datetime.utcnow().isoformat()
    return record


def discover_new_ingredients_from_bom(
    bom_items: List[Dict],
    existing_names: set,
) -> List[Dict]:
    """
    从BOM数据中发现知识库尚未收录的原料。

    Args:
        bom_items: BOM明细 [{"ingredient_name": "xx", "category": "xx", ...}]
        existing_names: 已收录的原料名集合

    Returns:
        新发现的原料列表（需人工审核后入库）
    """
    discovered = []
    for item in bom_items:
        name = item.get("ingredient_name", "")
        if name and name not in existing_names:
            discovered.append({
                "ingredient_name": name,
                "source": "bom_discovery",
                "category_guess": item.get("category", "待分类"),
                "first_seen_at": datetime.utcnow().isoformat(),
                "needs_review": True,
            })
            existing_names.add(name)  # 去重

    if discovered:
        logger.info("BOM发现新原料", count=len(discovered),
                    names=[d["ingredient_name"] for d in discovered[:5]])
    return discovered


# ── 服务类 ────────────────────────────────────────────────────────────────────

class IngredientKnowledgeService:
    """
    原材料知识库服务。

    知识增长路径：
    1. 初始导入（Excel 244条 + MD补充）
    2. 自动补全（省份推断 + 风味向量生成）
    3. BOM反向发现（采购单/菜品配方中的新原料）
    4. 供应商数据融合（价格/季节性/质量评级）
    5. 人工审核入库（新原料经厨师长/采购确认后正式入库）
    """

    def __init__(self):
        self._records: Dict[str, IngredientRecord] = {}

    def import_records(self, records: List[IngredientRecord]) -> int:
        """批量导入并自动补全"""
        count = 0
        for r in records:
            enriched = enrich_record(r)
            self._records[enriched.record_id] = enriched
            count += 1
        logger.info("知识库导入", imported=count, total=len(self._records))
        return count

    def get_record(self, record_id: str) -> Optional[IngredientRecord]:
        return self._records.get(record_id)

    def search(
        self,
        keyword: str = "",
        category_l1: str = "",
        province: str = "",
        purchase_grade: str = "",
        limit: int = 50,
    ) -> List[IngredientRecord]:
        """多条件搜索"""
        results = []
        for r in self._records.values():
            if keyword and keyword not in r.ingredient_name and keyword not in r.standard_name:
                continue
            if category_l1 and r.category_l1 != category_l1:
                continue
            if province and r.province != province:
                continue
            if purchase_grade and r.purchase_grade != purchase_grade:
                continue
            results.append(r)
            if len(results) >= limit:
                break
        return results

    def get_data_quality_report(self) -> Dict:
        """数据质量报告"""
        return identify_data_gaps(list(self._records.values()))

    def get_category_stats(self) -> List[Dict]:
        """品类统计"""
        stats: Dict[str, Dict] = {}
        for r in self._records.values():
            cat = r.category_l1
            if cat not in stats:
                stats[cat] = {"category": cat, "total": 0, "a_grade": 0, "b_grade": 0, "c_grade": 0}
            stats[cat]["total"] += 1
            if r.purchase_grade == "A":
                stats[cat]["a_grade"] += 1
            elif r.purchase_grade == "B":
                stats[cat]["b_grade"] += 1
            elif r.purchase_grade == "C":
                stats[cat]["c_grade"] += 1
        return sorted(stats.values(), key=lambda x: x["total"], reverse=True)

    def discover_from_bom(self, bom_items: List[Dict]) -> List[Dict]:
        """从BOM发现新原料"""
        existing = {r.ingredient_name for r in self._records.values()}
        existing.update(r.standard_name for r in self._records.values())
        return discover_new_ingredients_from_bom(bom_items, existing)

    def export_for_flavor_ontology(self) -> List[Dict]:
        """导出为风味本体论格式（对接 FlavorOntologyService）"""
        exports = []
        for r in self._records.values():
            if r.flavor_vector:
                exports.append({
                    "name": r.standard_name or r.ingredient_name,
                    "values": r.flavor_vector,
                    "source": "gi_knowledge_base",
                    "category": r.category_l1,
                })
        return exports
