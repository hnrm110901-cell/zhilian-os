"""
风味本体论（Flavor Ontology）
12 维向量空间中的食材/菜品风味表示与匹配。

12 维风味指纹：
  [酸, 甜, 苦, 辣, 鲜, 咸, 烟熏, 发酵, 坚果, 花草, 木质, 奶香]

核心能力：
  - 食材风味指纹管理
  - 替代食材推荐（余弦相似度）
  - 菜品风味画像合成
  - 菜品与消费者口味偏好匹配
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

# 12 维名称
FLAVOR_DIMENSIONS = [
    "酸", "甜", "苦", "辣", "鲜", "咸",
    "烟熏", "发酵", "坚果", "花草", "木质", "奶香",
]


@dataclass
class FlavorVector:
    """12 维风味指纹，每个维度 0.0-1.0"""
    name: str
    values: List[float] = field(default_factory=lambda: [0.0] * 12)

    def __post_init__(self):
        if len(self.values) != 12:
            raise ValueError(f"风味向量必须 12 维，实际 {len(self.values)} 维")
        self.values = [max(0.0, min(1.0, v)) for v in self.values]

    def to_dict(self) -> Dict[str, float]:
        return {d: round(v, 2) for d, v in zip(FLAVOR_DIMENSIONS, self.values)}


@dataclass
class SubstituteResult:
    """替代食材推荐结果"""
    original_name: str
    substitute_name: str
    similarity: float          # 0-1 余弦相似度
    flavor_diff: Dict[str, float]  # 各维度差异
    cost_ratio: Optional[float] = None  # 替代品/原品 成本比


@dataclass
class DishFlavorProfile:
    """菜品风味合成画像"""
    dish_name: str
    composite_vector: FlavorVector
    dominant_flavors: List[str]    # 主导风味（前3）
    ingredient_contributions: List[Dict]  # 各食材贡献


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度"""
    if len(a) != len(b):
        raise ValueError("向量维度不一致")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def flavor_distance(a: List[float], b: List[float]) -> Dict[str, float]:
    """逐维度差异"""
    return {
        FLAVOR_DIMENSIONS[i]: round(a[i] - b[i], 2)
        for i in range(min(len(a), len(b), 12))
        if abs(a[i] - b[i]) > 0.05
    }


def composite_flavor(
    ingredients: List[Tuple[FlavorVector, float]],
) -> FlavorVector:
    """
    合成菜品风味画像。
    ingredients: [(食材风味向量, 权重/用量比例)]
    权重归一化后加权平均。
    """
    if not ingredients:
        return FlavorVector(name="空菜品")

    total_weight = sum(w for _, w in ingredients)
    if total_weight == 0:
        return FlavorVector(name="空菜品")

    result = [0.0] * 12
    for fv, weight in ingredients:
        ratio = weight / total_weight
        for i in range(12):
            result[i] += fv.values[i] * ratio

    return FlavorVector(name="合成", values=result)


def dominant_flavors(vec: FlavorVector, top_n: int = 3) -> List[str]:
    """提取主导风味维度"""
    pairs = list(zip(FLAVOR_DIMENSIONS, vec.values))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return [name for name, val in pairs[:top_n] if val > 0.1]


# ── 内置食材风味库（湘菜核心食材） ─────────────────────────────────────────────

BUILTIN_FLAVORS: Dict[str, List[float]] = {
    #              酸   甜   苦   辣   鲜   咸   烟熏 发酵 坚果 花草 木质 奶香
    "剁椒":       [0.2, 0.0, 0.0, 0.9, 0.3, 0.7, 0.0, 0.6, 0.0, 0.0, 0.0, 0.0],
    "小米椒":     [0.1, 0.0, 0.0, 0.95,0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "花椒":       [0.0, 0.0, 0.1, 0.7, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.3, 0.0],
    "线椒":       [0.1, 0.1, 0.0, 0.75,0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "豆豉":       [0.1, 0.0, 0.1, 0.2, 0.7, 0.8, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0],
    "腊肉":       [0.0, 0.1, 0.0, 0.1, 0.6, 0.8, 0.9, 0.3, 0.0, 0.0, 0.2, 0.0],
    "腊肠":       [0.0, 0.2, 0.0, 0.2, 0.5, 0.7, 0.8, 0.2, 0.0, 0.0, 0.1, 0.0],
    "酸菜":       [0.9, 0.0, 0.0, 0.1, 0.3, 0.5, 0.0, 0.7, 0.0, 0.0, 0.0, 0.0],
    "紫苏":       [0.0, 0.0, 0.1, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.8, 0.2, 0.0],
    "香菜":       [0.0, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.7, 0.1, 0.0],
    "蒜":         [0.0, 0.0, 0.0, 0.3, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "姜":         [0.0, 0.0, 0.0, 0.4, 0.2, 0.0, 0.0, 0.0, 0.0, 0.1, 0.2, 0.0],
    "猪肉":       [0.0, 0.1, 0.0, 0.0, 0.7, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
    "牛肉":       [0.0, 0.0, 0.0, 0.0, 0.8, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "鸡肉":       [0.0, 0.1, 0.0, 0.0, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "鱼(淡水)":   [0.0, 0.1, 0.0, 0.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "虾":         [0.0, 0.2, 0.0, 0.0, 0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "豆腐":       [0.0, 0.1, 0.0, 0.0, 0.3, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1],
    "臭豆腐":     [0.0, 0.0, 0.1, 0.0, 0.4, 0.2, 0.0, 0.9, 0.0, 0.0, 0.0, 0.0],
    "笋":         [0.0, 0.1, 0.1, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0],
    "莲藕":       [0.0, 0.3, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0],
    "茶油":       [0.0, 0.0, 0.1, 0.0, 0.1, 0.0, 0.0, 0.0, 0.3, 0.1, 0.4, 0.0],
    "芝麻":       [0.0, 0.1, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.0],
    "桂花":       [0.0, 0.6, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.9, 0.1, 0.1],
    "黑松露":     [0.0, 0.1, 0.1, 0.0, 0.8, 0.1, 0.0, 0.2, 0.3, 0.0, 0.7, 0.0],
    "鸡蛋":       [0.0, 0.1, 0.0, 0.0, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3],
    "米粉":       [0.0, 0.1, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "折耳根":     [0.0, 0.0, 0.2, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.4, 0.3, 0.0],
    "辣椒油":     [0.0, 0.0, 0.0, 0.8, 0.2, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0],
    "酱油":       [0.0, 0.1, 0.0, 0.0, 0.6, 0.9, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0],
}


# ── 服务类 ────────────────────────────────────────────────────────────────────

class FlavorOntologyService:
    """
    风味本体论服务。

    内置 30 种湘菜核心食材的风味指纹，支持扩展。
    """

    def __init__(self):
        self._flavors: Dict[str, FlavorVector] = {}
        for name, values in BUILTIN_FLAVORS.items():
            self._flavors[name] = FlavorVector(name=name, values=values)

    def get_flavor(self, ingredient_name: str) -> Optional[FlavorVector]:
        """获取食材风味向量"""
        return self._flavors.get(ingredient_name)

    def add_flavor(self, name: str, values: List[float]) -> FlavorVector:
        """添加/更新食材风味"""
        fv = FlavorVector(name=name, values=values)
        self._flavors[name] = fv
        return fv

    def list_ingredients(self) -> List[str]:
        """列出所有已有食材"""
        return list(self._flavors.keys())

    def find_substitutes(
        self,
        ingredient_name: str,
        top_n: int = 5,
        min_similarity: float = 0.7,
        cost_map: Optional[Dict[str, float]] = None,
    ) -> List[SubstituteResult]:
        """
        查找替代食材。

        Args:
            ingredient_name: 原食材名
            top_n: 返回前 N 个
            min_similarity: 最低相似度门槛
            cost_map: 食材成本字典（用于计算成本比）

        Returns:
            替代推荐列表，按相似度降序
        """
        original = self._flavors.get(ingredient_name)
        if not original:
            return []

        results = []
        for name, fv in self._flavors.items():
            if name == ingredient_name:
                continue
            sim = cosine_similarity(original.values, fv.values)
            if sim >= min_similarity:
                cost_ratio = None
                if cost_map and ingredient_name in cost_map and name in cost_map:
                    orig_cost = cost_map[ingredient_name]
                    if orig_cost > 0:
                        cost_ratio = round(cost_map[name] / orig_cost, 2)

                results.append(SubstituteResult(
                    original_name=ingredient_name,
                    substitute_name=name,
                    similarity=round(sim, 3),
                    flavor_diff=flavor_distance(original.values, fv.values),
                    cost_ratio=cost_ratio,
                ))

        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_n]

    def build_dish_profile(
        self,
        dish_name: str,
        ingredients: List[Tuple[str, float]],
    ) -> DishFlavorProfile:
        """
        合成菜品风味画像。

        Args:
            dish_name: 菜品名称
            ingredients: [(食材名, 用量权重)]

        Returns:
            DishFlavorProfile
        """
        vectors_with_weights = []
        contributions = []

        for name, weight in ingredients:
            fv = self._flavors.get(name)
            if fv:
                vectors_with_weights.append((fv, weight))
                contributions.append({
                    "ingredient": name,
                    "weight": weight,
                    "dominant": dominant_flavors(fv, top_n=2),
                })

        composite = composite_flavor(vectors_with_weights)
        composite.name = dish_name

        return DishFlavorProfile(
            dish_name=dish_name,
            composite_vector=composite,
            dominant_flavors=dominant_flavors(composite),
            ingredient_contributions=contributions,
        )

    def match_preference(
        self,
        dish_profile: FlavorVector,
        customer_preference: FlavorVector,
    ) -> float:
        """
        计算菜品与消费者口味偏好的匹配度。
        返回 0-100 分。
        """
        sim = cosine_similarity(dish_profile.values, customer_preference.values)
        return round(sim * 100, 1)
