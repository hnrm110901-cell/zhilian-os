"""
实体解析服务 — 跨系统实体识别与合并
对标 Palantir Foundry 的 Object Linking & Resolution

核心能力：
  1. 精确匹配：external_id 直接命中 → confidence 1.0
  2. 名称匹配：规范名完全匹配 → confidence 0.98
  3. 模糊匹配：Jaccard 相似度 + 领域规则 → confidence 0.6~0.92
  4. 冲突检测：多源数据不一致时自动记录冲突
  5. 人工确认：低置信度映射标记待确认

使用方式：
  resolver = EntityResolver(db_session)
  result = await resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
  # result.canonical_id = "xxx", result.confidence = 0.98, result.is_new = False
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# ── 解析结果 ──────────────────────────────────────────────────────────────────

@dataclass
class ResolveResult:
    """实体解析结果"""
    canonical_id: str
    canonical_name: str
    confidence: float
    match_method: str          # exact_id / exact_name / fuzzy_name / new
    is_new: bool               # 是否新建的实体
    is_confirmed: bool = False
    conflict_fields: list = field(default_factory=list)


@dataclass
class BatchResolveResult:
    """批量解析结果"""
    total: int
    resolved: int
    new_entities: int
    conflicts: int
    results: List[ResolveResult] = field(default_factory=list)


# ── 文本规范化工具 ────────────────────────────────────────────────────────────

def _normalize_dish_name(name: str) -> str:
    """
    菜品名称规范化：去除规格、份量、营销前缀等噪声
    "招牌剁椒鱼头(大份)" → "剁椒鱼头"
    "【必点】秘制红烧肉 买一送一" → "秘制红烧肉"
    """
    if not name:
        return ""
    # 去除括号及内容（中英文括号）
    cleaned = re.sub(r'[（(][^）)]*[）)]', '', name)
    # 去除方括号及内容
    cleaned = re.sub(r'[【\[][^】\]]*[】\]]', '', cleaned)
    # 去除常见营销前缀
    for prefix in ["招牌", "特色", "秘制", "本店", "限时", "新品", "必点"]:
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix) + 1:
            cleaned = cleaned[len(prefix):]
    # 去除份量后缀
    for suffix in ["大份", "小份", "中份", "半份", "例", "位", "份",
                    "买一送一", "特价", "加量"]:
        cleaned = cleaned.replace(suffix, "")
    return cleaned.strip()


def _normalize_customer_phone(phone: str) -> str:
    """手机号规范化：去除前缀、空格、横线"""
    if not phone:
        return ""
    cleaned = re.sub(r'[\s\-+]', '', phone)
    # 去除国际区号前缀
    if cleaned.startswith("86") and len(cleaned) == 13:
        cleaned = cleaned[2:]
    if cleaned.startswith("+86") and len(cleaned) == 14:
        cleaned = cleaned[3:]
    return cleaned


def _normalize_ingredient_name(name: str) -> str:
    """食材名称规范化：去除品牌、规格"""
    if not name:
        return ""
    cleaned = re.sub(r'[（(][^）)]*[）)]', '', name)
    # 去除重量规格
    cleaned = re.sub(r'\d+[gGkK克斤两]', '', cleaned)
    return cleaned.strip()


def _jaccard_similarity(a: str, b: str) -> float:
    """
    字符级 Jaccard 相似度（2-gram）
    用于中文菜品/食材名的模糊匹配
    """
    if not a or not b:
        return 0.0
    # 生成2-gram集合
    set_a = set(a[i:i + 2] for i in range(len(a) - 1)) if len(a) > 1 else {a}
    set_b = set(b[i:i + 2] for i in range(len(b) - 1)) if len(b) > 1 else {b}
    intersection = set_a & set_b
    union = set_a | set_b
    if not union:
        return 0.0
    return len(intersection) / len(union)


# ── 规范化器注册表 ────────────────────────────────────────────────────────────

NORMALIZERS = {
    "dish": _normalize_dish_name,
    "ingredient": _normalize_ingredient_name,
    "customer": lambda name: (name or "").strip(),
    "supplier": lambda name: (name or "").strip(),
    "employee": lambda name: (name or "").strip(),
    "order": lambda name: (name or "").strip(),
    "store": lambda name: (name or "").strip(),
}

# 各实体类型的模糊匹配阈值
FUZZY_THRESHOLDS = {
    "dish": 0.65,        # 菜品名差异较大（前缀/后缀多），阈值适当放低
    "ingredient": 0.70,  # 食材相对标准化
    "customer": 0.90,    # 客户名必须高度匹配
    "supplier": 0.80,    # 供应商名相对标准化
    "employee": 0.85,    # 员工名必须准确
    "order": 1.0,        # 订单不做模糊匹配
    "store": 0.85,
}


class EntityResolver:
    """
    跨系统实体解析器

    解析流程：
    1. 精确ID匹配：查找已有的 FusionEntityMap(source_system, external_id)
    2. 精确名称匹配：规范化后完全匹配
    3. 模糊名称匹配：Jaccard 2-gram 相似度超过阈值
    4. 新建实体：无匹配时创建新的 canonical_id

    特殊规则：
    - 客户实体：优先用手机号匹配（精确），再用名称
    - 订单实体：只做精确ID匹配（订单号唯一）
    - 菜品实体：名称规范化后匹配（去份量/营销前缀）
    """

    def __init__(self, entity_maps: Optional[List[Dict]] = None):
        """
        初始化解析器

        Args:
            entity_maps: 已有的实体映射列表（从DB加载），每项包含：
                entity_type, canonical_id, canonical_name,
                source_system, external_id, external_name, confidence
        """
        # 构建内存索引
        self._by_external_id: Dict[str, Dict] = {}   # key: "{entity_type}:{source}:{ext_id}"
        self._by_canonical_name: Dict[str, List[Dict]] = {}  # key: "{entity_type}:{normalized_name}"
        self._by_canonical_id: Dict[str, Dict] = {}   # key: "{entity_type}:{canonical_id}"

        for em in (entity_maps or []):
            self._index_entity_map(em)

    def _index_entity_map(self, em: Dict) -> None:
        """将实体映射加入内存索引"""
        etype = em.get("entity_type", "")
        source = em.get("source_system", "")
        ext_id = em.get("external_id", "")
        canonical_id = em.get("canonical_id", "")
        canonical_name = em.get("canonical_name", "")

        # 按外部ID索引
        ext_key = f"{etype}:{source}:{ext_id}"
        self._by_external_id[ext_key] = em

        # 按规范名索引
        normalizer = NORMALIZERS.get(etype, lambda x: (x or "").strip())
        normalized = normalizer(canonical_name)
        if normalized:
            name_key = f"{etype}:{normalized}"
            if name_key not in self._by_canonical_name:
                self._by_canonical_name[name_key] = []
            self._by_canonical_name[name_key].append(em)

        # 按canonical_id索引
        cid_key = f"{etype}:{canonical_id}"
        self._by_canonical_id[cid_key] = em

    def resolve(
        self,
        entity_type: str,
        source_system: str,
        external_id: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> ResolveResult:
        """
        解析单个实体

        Args:
            entity_type: 实体类型 (dish/ingredient/customer/supplier/employee/order)
            source_system: 来源系统标识
            external_id: 外部系统中的原始ID
            name: 实体名称（可选）
            phone: 手机号（仅customer类型使用）
            metadata: 额外元数据

        Returns:
            ResolveResult 包含 canonical_id + 置信度 + 匹配方法
        """
        # Step 1: 精确ID匹配
        ext_key = f"{entity_type}:{source_system}:{external_id}"
        if ext_key in self._by_external_id:
            existing = self._by_external_id[ext_key]
            return ResolveResult(
                canonical_id=existing["canonical_id"],
                canonical_name=existing.get("canonical_name", ""),
                confidence=1.0,
                match_method="exact_id",
                is_new=False,
                is_confirmed=existing.get("is_confirmed", False),
            )

        # Step 2: 客户手机号精确匹配
        if entity_type == "customer" and phone:
            normalized_phone = _normalize_customer_phone(phone)
            result = self._match_customer_by_phone(
                normalized_phone, source_system, external_id, name
            )
            if result:
                return result

        # Step 3: 精确名称匹配
        normalizer = NORMALIZERS.get(entity_type, lambda x: (x or "").strip())
        normalized_name = normalizer(name) if name else ""
        if normalized_name:
            name_key = f"{entity_type}:{normalized_name}"
            if name_key in self._by_canonical_name:
                existing_list = self._by_canonical_name[name_key]
                best = existing_list[0]
                return ResolveResult(
                    canonical_id=best["canonical_id"],
                    canonical_name=best.get("canonical_name", normalized_name),
                    confidence=0.98,
                    match_method="exact_name",
                    is_new=False,
                    is_confirmed=best.get("is_confirmed", False),
                )

        # Step 4: 模糊名称匹配
        if normalized_name and entity_type != "order":
            fuzzy_result = self._fuzzy_match(entity_type, normalized_name)
            if fuzzy_result:
                return fuzzy_result

        # Step 5: 新建实体
        new_id = str(uuid.uuid4())
        display_name = normalized_name or name or external_id
        new_map = {
            "entity_type": entity_type,
            "canonical_id": new_id,
            "canonical_name": display_name,
            "source_system": source_system,
            "external_id": external_id,
            "external_name": name,
            "confidence": 1.0 if external_id else 0.5,
            "is_confirmed": False,
        }
        self._index_entity_map(new_map)

        logger.info(
            "entity_resolver.new_entity",
            entity_type=entity_type,
            canonical_id=new_id,
            name=display_name,
            source=source_system,
        )

        return ResolveResult(
            canonical_id=new_id,
            canonical_name=display_name,
            confidence=1.0 if external_id else 0.5,
            match_method="new",
            is_new=True,
        )

    def _match_customer_by_phone(
        self,
        phone: str,
        source_system: str,
        external_id: str,
        name: Optional[str],
    ) -> Optional[ResolveResult]:
        """按手机号匹配客户"""
        # 遍历已有的customer类型映射，查找手机号匹配
        for key, em in self._by_external_id.items():
            if not key.startswith("customer:"):
                continue
            em_meta = em.get("external_metadata") or {}
            em_phone = _normalize_customer_phone(em_meta.get("phone", ""))
            if em_phone and em_phone == phone:
                return ResolveResult(
                    canonical_id=em["canonical_id"],
                    canonical_name=em.get("canonical_name", name or ""),
                    confidence=0.99,
                    match_method="exact_phone",
                    is_new=False,
                    is_confirmed=em.get("is_confirmed", False),
                )
        return None

    def _fuzzy_match(
        self, entity_type: str, normalized_name: str
    ) -> Optional[ResolveResult]:
        """模糊名称匹配"""
        threshold = FUZZY_THRESHOLDS.get(entity_type, 0.80)
        best_score = 0.0
        best_match: Optional[Dict] = None

        # 遍历同类型的所有规范名
        prefix = f"{entity_type}:"
        for name_key, map_list in self._by_canonical_name.items():
            if not name_key.startswith(prefix):
                continue
            existing_name = name_key[len(prefix):]
            score = _jaccard_similarity(normalized_name, existing_name)
            if score > best_score:
                best_score = score
                best_match = map_list[0]

        if best_match and best_score >= threshold:
            confidence = round(best_score * 0.92, 4)  # Jaccard × 0.92 作为置信度
            return ResolveResult(
                canonical_id=best_match["canonical_id"],
                canonical_name=best_match.get("canonical_name", ""),
                confidence=confidence,
                match_method="fuzzy_name",
                is_new=False,
                is_confirmed=False,  # 模糊匹配不自动确认
            )
        return None

    def batch_resolve(
        self,
        entity_type: str,
        source_system: str,
        items: List[Dict],
    ) -> BatchResolveResult:
        """
        批量实体解析

        Args:
            entity_type: 实体类型
            source_system: 来源系统
            items: 待解析列表，每项至少包含 external_id，可选 name/phone/metadata

        Returns:
            BatchResolveResult
        """
        results = []
        new_count = 0
        conflict_count = 0

        for item in items:
            result = self.resolve(
                entity_type=entity_type,
                source_system=source_system,
                external_id=item.get("external_id", ""),
                name=item.get("name"),
                phone=item.get("phone"),
                metadata=item.get("metadata"),
            )
            results.append(result)
            if result.is_new:
                new_count += 1
            if result.conflict_fields:
                conflict_count += 1

        return BatchResolveResult(
            total=len(items),
            resolved=len(results),
            new_entities=new_count,
            conflicts=conflict_count,
            results=results,
        )

    def detect_conflict(
        self,
        entity_type: str,
        canonical_id: str,
        field_name: str,
        source_a: str,
        value_a: Any,
        source_b: str,
        value_b: Any,
    ) -> Optional[Dict]:
        """
        检测字段级冲突

        Returns:
            冲突记录 dict 或 None（无冲突）
        """
        # 相同值不算冲突
        if value_a == value_b:
            return None
        # None vs 有值不算冲突（补充数据）
        if value_a is None or value_b is None:
            return None

        return {
            "entity_type": entity_type,
            "canonical_id": canonical_id,
            "field_name": field_name,
            "source_a_system": source_a,
            "source_a_value": json.dumps(value_a, ensure_ascii=False, default=str),
            "source_b_system": source_b,
            "source_b_value": json.dumps(value_b, ensure_ascii=False, default=str),
        }

    def get_entity_map_records(self) -> List[Dict]:
        """导出所有实体映射记录（用于持久化到DB）"""
        seen = set()
        records = []
        for em in self._by_external_id.values():
            key = f"{em.get('entity_type')}:{em.get('source_system')}:{em.get('external_id')}"
            if key not in seen:
                seen.add(key)
                records.append(em)
        return records
