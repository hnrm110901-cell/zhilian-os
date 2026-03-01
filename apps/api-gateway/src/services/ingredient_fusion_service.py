"""
L2 融合层核心服务 — IngredientFusionService

职责：
  1. resolve_or_create  — 将外部源的食材 ID 解析为规范 canonical_id
                          （按优先级：exact_id → exact_name → fuzzy → new）
  2. batch_resolve      — 批量解析，供 L1 适配器接入后的流水线使用
  3. get_mapping        — 查询某规范 ID 的完整映射记录
  4. get_conflicts      — 列出置信度低或存在冲突的映射
  5. merge_canonical_ids — 人工合并两个规范 ID（经 HitL 审批后调用）
  6. reconcile_unit_cost — 多源成本置信度加权计算

融合算法：
  Step 1. 精确命中 external_ids JSONB 字段
          → confidence = 1.0, method = exact_id
  Step 2. 规范名精确匹配（同 category）
          → confidence = 0.98, method = exact_name
  Step 3. 字符级 bigram Jaccard 模糊匹配（同 category 优先）
          → confidence = jaccard × SOURCE_NAME_WEIGHT
          → 阈值 FUZZY_MATCH_THRESHOLD = 0.65
  Step 4. 无匹配 → 新建规范条目
          → confidence = source_reliability[source_system]

数据源可靠度权重（SOURCE_RELIABILITY）：
  supplier_invoice  0.95   最权威（合同价）
  pinzhi            0.85   品智 POS 实测
  tiancai           0.80   天财商龙
  aoqiwei           0.75   澳奇韦
  meituan           0.70   外卖平台（可能含包装费）
  yiding            0.60   易订（预订系统，成本数据较粗）
  manual            0.55   人工录入
  unknown           0.40   来源不明
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ingredient_mapping import IngredientMapping, FusionAuditLog, FusionMethod

logger = structlog.get_logger()

# ── 常量 ──────────────────────────────────────────────────────────────────────

FUZZY_MATCH_THRESHOLD = 0.65     # Jaccard ≥ 此值才考虑别名匹配
CONFLICT_COST_THRESHOLD = 0.20   # 成本偏差超 20% 标记冲突

SOURCE_RELIABILITY: Dict[str, float] = {
    "supplier_invoice": 0.95,
    "pinzhi":           0.85,
    "tiancai":          0.80,
    "aoqiwei":          0.75,
    "meituan":          0.70,
    "yiding":           0.60,
    "manual":           0.55,
    "unknown":          0.40,
}

# 成本加权使用与可靠度相同的权重
SOURCE_COST_WEIGHT = SOURCE_RELIABILITY

# canonical_id 前缀生成用
CATEGORY_PREFIX: Dict[str, str] = {
    "meat":       "MEAT",
    "seafood":    "SEAF",
    "vegetable":  "VEG",
    "dry_goods":  "DRY",
    "dairy":      "DAIR",
    "beverage":   "BEV",
    "condiment":  "COND",
    "grain":      "GRAN",
    "fruit":      "FRIT",
    "other":      "MISC",
}


# ── 数据类 ────────────────────────────────────────────────────────────────────

@dataclass
class FusionInput:
    source_system: str
    external_id:   str
    name:          str
    category:      Optional[str] = None
    unit:          Optional[str] = None
    cost_fen:      Optional[int] = None
    submitted_by:  Optional[str] = None


@dataclass
class FusionResult:
    canonical_id:   str
    canonical_name: str
    confidence:     float
    method:         str
    is_new:         bool = False
    conflict_flag:  bool = False
    evidence:       Dict = field(default_factory=dict)


@dataclass
class SourceCost:
    source_system: str
    cost_fen:      int
    confidence:    float = 1.0


# ── 工具函数（无 IO，可单元测试）─────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """规范化名称：去空格、全角→半角、小写"""
    name = name.strip().lower()
    # 全角字符转半角
    result = []
    for ch in name:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        else:
            result.append(ch)
    name = "".join(result)
    # 去除常见噪声字符（括号、连字符）
    name = re.sub(r"[\s\-_（）()\[\]【】·•]", "", name)
    return name


def _char_bigrams(s: str) -> frozenset:
    """字符级 bigram 集合"""
    if len(s) < 2:
        return frozenset({s}) if s else frozenset()
    return frozenset(s[i:i + 2] for i in range(len(s) - 1))


def _jaccard(s1: str, s2: str) -> float:
    """基于字符 bigram 的 Jaccard 相似度"""
    b1 = _char_bigrams(_normalize_name(s1))
    b2 = _char_bigrams(_normalize_name(s2))
    if not b1 and not b2:
        return 1.0
    if not b1 or not b2:
        return 0.0
    return len(b1 & b2) / len(b1 | b2)


def reconcile_unit_cost(costs: List[SourceCost]) -> Tuple[int, float]:
    """
    多源成本置信度加权均值

    Returns:
        (weighted_cost_fen, composite_confidence)

    Example:
        costs = [
            SourceCost("supplier_invoice", 3800, 0.95),
            SourceCost("pinzhi",           3500, 0.85),
        ]
        → weighted = (3800×0.95 + 3500×0.85) / (0.95+0.85) ≈ 3658
        → confidence = min(composite, 1.0)
    """
    if not costs:
        return 0, 0.0

    total_weight = sum(c.confidence for c in costs)
    if total_weight == 0:
        return costs[0].cost_fen, 0.0

    weighted_cost = sum(c.cost_fen * c.confidence for c in costs) / total_weight

    # 成本一致性检验：偏差 > 20% → 降低组合置信度
    avg = weighted_cost
    max_deviation = max(abs(c.cost_fen - avg) / avg for c in costs if avg > 0)
    consistency_factor = max(0.5, 1.0 - max_deviation) if max_deviation > CONFLICT_COST_THRESHOLD else 1.0

    composite_confidence = min(total_weight / len(costs) * consistency_factor, 1.0)
    return int(round(weighted_cost)), composite_confidence


def _generate_canonical_id(name: str, category: Optional[str]) -> str:
    """
    生成确定性规范 ID
    格式：ING-{CATEGORY_PREFIX}-{HASH6}
    """
    prefix = CATEGORY_PREFIX.get(category or "", "MISC")
    hash6 = uuid.uuid5(uuid.NAMESPACE_DNS, _normalize_name(name)).hex[:6].upper()
    return f"ING-{prefix}-{hash6}"


# ── 核心服务 ──────────────────────────────────────────────────────────────────

class IngredientFusionService:
    """
    L2 融合层食材解析服务

    调用入口：
        svc = IngredientFusionService(db)
        result = await svc.resolve_or_create(
            source_system="pinzhi",
            external_id="12345",
            name="草鱼片",
            category="seafood",
            unit="kg",
            cost_fen=3500,
        )
        # result.canonical_id == "ING-SEAF-A3F2B1"
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 主入口：解析或新建 ───────────────────────────────────────────────────

    async def resolve_or_create(
        self,
        source_system: str,
        external_id:   str,
        name:          str,
        category:      Optional[str] = None,
        unit:          Optional[str] = None,
        cost_fen:      Optional[int] = None,
        submitted_by:  Optional[str] = None,
    ) -> FusionResult:
        """
        四步解析逻辑（按置信度从高到低）：
          1. exact_id    — external_ids JSONB 精确命中
          2. exact_name  — canonical_name 精确匹配
          3. fuzzy_name  — bigram Jaccard ≥ FUZZY_MATCH_THRESHOLD
          4. new         — 新建规范条目
        """
        source_reliability = SOURCE_RELIABILITY.get(source_system, 0.40)

        # Step 1: 精确 external_id 命中
        result = await self._match_by_external_id(source_system, external_id)
        if result:
            await self._update_source_cost_internal(
                result, source_system, cost_fen, source_reliability
            )
            await self._write_audit(
                entity_type="ingredient",
                canonical_id=result.canonical_id,
                action="alias_to_existing",
                source_system=source_system,
                raw_external_id=external_id,
                raw_name=name,
                matched_canonical_id=result.canonical_id,
                confidence=1.0,
                method=FusionMethod.EXACT_ID,
                evidence={"step": "exact_id", "external_id": external_id},
                created_by=submitted_by,
            )
            await self.db.flush()
            return FusionResult(
                canonical_id=result.canonical_id,
                canonical_name=result.canonical_name,
                confidence=1.0,
                method=FusionMethod.EXACT_ID,
            )

        # Step 2: 规范名精确匹配
        result = await self._match_by_exact_name(name, category)
        if result:
            await self._register_external_id(result, source_system, external_id)
            await self._update_source_cost_internal(
                result, source_system, cost_fen, source_reliability
            )
            await self._write_audit(
                entity_type="ingredient",
                canonical_id=result.canonical_id,
                action="alias_to_existing",
                source_system=source_system,
                raw_external_id=external_id,
                raw_name=name,
                matched_canonical_id=result.canonical_id,
                confidence=0.98,
                method=FusionMethod.EXACT_NAME,
                evidence={"step": "exact_name", "canonical_name": result.canonical_name},
                created_by=submitted_by,
            )
            await self.db.flush()
            return FusionResult(
                canonical_id=result.canonical_id,
                canonical_name=result.canonical_name,
                confidence=0.98,
                method=FusionMethod.EXACT_NAME,
            )

        # Step 3: 模糊名称匹配
        best, best_score = await self._match_fuzzy(name, category)
        if best and best_score >= FUZZY_MATCH_THRESHOLD:
            conf = best_score * 0.92   # 稍微降低置信度（非精确）
            await self._register_external_id(best, source_system, external_id)
            # 追加 alias（如果不重复）
            if name not in (best.aliases or []):
                best.aliases = (best.aliases or []) + [name]
            await self._update_source_cost_internal(
                best, source_system, cost_fen, source_reliability
            )
            await self._write_audit(
                entity_type="ingredient",
                canonical_id=best.canonical_id,
                action="alias_to_existing",
                source_system=source_system,
                raw_external_id=external_id,
                raw_name=name,
                matched_canonical_id=best.canonical_id,
                confidence=conf,
                method=FusionMethod.FUZZY_NAME,
                evidence={
                    "step": "fuzzy",
                    "jaccard_score": round(best_score, 4),
                    "canonical_name": best.canonical_name,
                },
                created_by=submitted_by,
            )
            await self.db.flush()
            return FusionResult(
                canonical_id=best.canonical_id,
                canonical_name=best.canonical_name,
                confidence=conf,
                method=FusionMethod.FUZZY_NAME,
                evidence={"jaccard_score": round(best_score, 4)},
            )

        # Step 4: 新建规范条目
        canonical_id = _generate_canonical_id(name, category)
        # 避免哈希碰撞
        canonical_id = await self._ensure_unique_canonical_id(canonical_id, name)

        source_costs_init = {}
        canonical_cost = None
        if cost_fen is not None:
            source_costs_init = {
                source_system: {
                    "cost_fen": cost_fen,
                    "confidence": source_reliability,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            }
            canonical_cost = cost_fen

        mapping = IngredientMapping(
            canonical_id=canonical_id,
            canonical_name=name,
            aliases=[],
            category=category,
            unit=unit,
            external_ids={source_system: external_id} if external_id else {},
            source_costs=source_costs_init,
            canonical_cost_fen=canonical_cost,
            fusion_confidence=source_reliability,
            fusion_method=FusionMethod.NEW,
            conflict_flag=False,
            merge_of=[],
            is_active=True,
        )
        self.db.add(mapping)

        await self._write_audit(
            entity_type="ingredient",
            canonical_id=canonical_id,
            action="create_canonical",
            source_system=source_system,
            raw_external_id=external_id,
            raw_name=name,
            matched_canonical_id=None,
            confidence=source_reliability,
            method=FusionMethod.NEW,
            evidence={
                "step": "new_canonical",
                "generated_id": canonical_id,
                "category": category,
            },
            created_by=submitted_by,
        )
        await self.db.flush()

        logger.info(
            "新建规范食材条目",
            canonical_id=canonical_id,
            name=name,
            source=source_system,
        )
        return FusionResult(
            canonical_id=canonical_id,
            canonical_name=name,
            confidence=source_reliability,
            method=FusionMethod.NEW,
            is_new=True,
        )

    # ── 批量解析 ──────────────────────────────────────────────────────────────

    async def batch_resolve(self, items: List[FusionInput]) -> List[FusionResult]:
        """批量解析，逐条调用 resolve_or_create，返回顺序与输入一致"""
        results = []
        for item in items:
            r = await self.resolve_or_create(
                source_system=item.source_system,
                external_id=item.external_id,
                name=item.name,
                category=item.category,
                unit=item.unit,
                cost_fen=item.cost_fen,
                submitted_by=item.submitted_by,
            )
            results.append(r)
        await self.db.commit()
        return results

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def get_mapping(self, canonical_id: str) -> Optional[IngredientMapping]:
        stmt = select(IngredientMapping).where(
            IngredientMapping.canonical_id == canonical_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_conflicts(self, confidence_threshold: float = 0.70) -> List[IngredientMapping]:
        """列出置信度低或存在冲突的映射（供人工审核）"""
        stmt = select(IngredientMapping).where(
            and_(
                IngredientMapping.is_active.is_(True),
                (IngredientMapping.conflict_flag.is_(True))
                | (IngredientMapping.fusion_confidence < confidence_threshold),
            )
        ).order_by(IngredientMapping.fusion_confidence.asc())
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    async def list_mappings(
        self,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[IngredientMapping], int]:
        """分页列出规范映射"""
        stmt = select(IngredientMapping).where(IngredientMapping.is_active.is_(True))
        count_stmt = select(func.count()).select_from(IngredientMapping).where(
            IngredientMapping.is_active.is_(True)
        )
        if category:
            stmt = stmt.where(IngredientMapping.category == category)
            count_stmt = count_stmt.where(IngredientMapping.category == category)

        total = (await self.db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(IngredientMapping.canonical_name).offset(
            (page - 1) * page_size
        ).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows), total

    # ── 人工合并 ──────────────────────────────────────────────────────────────

    async def merge_canonical_ids(
        self,
        keep_id:   str,
        merge_id:  str,
        reason:    str,
        merged_by: Optional[str] = None,
    ) -> Optional[IngredientMapping]:
        """
        将 merge_id 合并入 keep_id：
          - 将 merge_id 的 external_ids 并入 keep_id
          - 将 merge_id 的 aliases 并入 keep_id
          - 将 merge_id 的 source_costs 合并，重新计算规范成本
          - 软删除 merge_id（is_active = False）
          - 写入审计日志
        """
        keep = await self.get_mapping(keep_id)
        merge = await self.get_mapping(merge_id)
        if not keep or not merge:
            return None

        # 合并 external_ids
        merged_ext = {**merge.external_ids, **keep.external_ids}
        keep.external_ids = merged_ext

        # 合并 aliases
        all_aliases = list(set(
            (keep.aliases or [])
            + (merge.aliases or [])
            + [merge.canonical_name]
        ))
        keep.aliases = all_aliases

        # 合并 source_costs，重新计算规范成本
        merged_costs = {**merge.source_costs, **keep.source_costs}
        keep.source_costs = merged_costs
        cost_list = [
            SourceCost(
                source_system=src,
                cost_fen=v["cost_fen"],
                confidence=v.get("confidence", 0.5),
            )
            for src, v in merged_costs.items()
            if isinstance(v, dict) and "cost_fen" in v
        ]
        if cost_list:
            weighted, conf = reconcile_unit_cost(cost_list)
            keep.canonical_cost_fen = weighted
            keep.fusion_confidence = min(max(keep.fusion_confidence, conf), 1.0)

        # merge_of 记录
        keep.merge_of = list(set((keep.merge_of or []) + [merge_id]))
        keep.fusion_method = FusionMethod.MANUAL
        keep.conflict_flag = False
        keep.updated_at = datetime.utcnow()

        # 软删除 merge_id
        merge.is_active = False

        await self._write_audit(
            entity_type="ingredient",
            canonical_id=keep_id,
            action="merge",
            source_system="system",
            raw_external_id=merge_id,
            raw_name=merge.canonical_name,
            matched_canonical_id=keep_id,
            confidence=keep.fusion_confidence,
            method=FusionMethod.MANUAL,
            evidence={"reason": reason, "merged_id": merge_id},
            created_by=merged_by,
        )
        await self.db.flush()
        logger.info("规范ID合并", keep_id=keep_id, merge_id=merge_id, reason=reason)
        return keep

    # ── 成本更新 ──────────────────────────────────────────────────────────────

    async def update_source_cost(
        self,
        canonical_id:  str,
        source_system: str,
        cost_fen:      int,
        confidence:    Optional[float] = None,
    ) -> Optional[IngredientMapping]:
        """单源成本更新，自动重新加权"""
        mapping = await self.get_mapping(canonical_id)
        if not mapping:
            return None
        conf = confidence or SOURCE_RELIABILITY.get(source_system, 0.40)
        await self._update_source_cost_internal(mapping, source_system, cost_fen, conf)
        await self.db.flush()
        return mapping

    # ── 审计日志查询 ──────────────────────────────────────────────────────────

    async def get_audit_log(
        self,
        canonical_id: Optional[str] = None,
        source_system: Optional[str] = None,
        limit: int = 100,
    ) -> List[FusionAuditLog]:
        stmt = select(FusionAuditLog).order_by(FusionAuditLog.created_at.desc())
        if canonical_id:
            stmt = stmt.where(FusionAuditLog.canonical_id == canonical_id)
        if source_system:
            stmt = stmt.where(FusionAuditLog.source_system == source_system)
        stmt = stmt.limit(limit)
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _match_by_external_id(
        self, source_system: str, external_id: str
    ) -> Optional[IngredientMapping]:
        """在 external_ids JSONB 中精确匹配 source_system → external_id"""
        # PostgreSQL: external_ids->>'pinzhi' = '12345'
        stmt = select(IngredientMapping).where(
            and_(
                IngredientMapping.is_active.is_(True),
                IngredientMapping.external_ids[source_system].as_string() == external_id,
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _match_by_exact_name(
        self, name: str, category: Optional[str]
    ) -> Optional[IngredientMapping]:
        """规范名精确匹配，优先同分类"""
        norm = _normalize_name(name)
        stmt = select(IngredientMapping).where(
            and_(
                IngredientMapping.is_active.is_(True),
                func.lower(IngredientMapping.canonical_name) == norm,
            )
        )
        if category:
            stmt = stmt.where(IngredientMapping.category == category)
        result = (await self.db.execute(stmt)).scalar_one_or_none()
        if result:
            return result
        # 不限分类再查一次
        if category:
            stmt2 = select(IngredientMapping).where(
                and_(
                    IngredientMapping.is_active.is_(True),
                    func.lower(IngredientMapping.canonical_name) == norm,
                )
            ).limit(1)
            return (await self.db.execute(stmt2)).scalar_one_or_none()
        return None

    async def _match_fuzzy(
        self, name: str, category: Optional[str]
    ) -> Tuple[Optional[IngredientMapping], float]:
        """
        遍历同 category 的规范条目，计算 bigram Jaccard，
        返回得分最高的候选与得分。
        全库候选过多时，PostgreSQL ILIKE + Python 精排更高效。
        """
        # 先用 LIKE 粗筛（取名称前 2 字）
        prefix = _normalize_name(name)[:2] if len(name) >= 2 else _normalize_name(name)
        stmt = select(IngredientMapping).where(
            IngredientMapping.is_active.is_(True)
        )
        if category:
            stmt = stmt.where(IngredientMapping.category == category)
        # 加 ILIKE 粗筛（PostgreSQL 不区分大小写）
        if prefix:
            stmt = stmt.where(
                IngredientMapping.canonical_name.ilike(f"%{prefix}%")
            )
        candidates = (await self.db.execute(stmt)).scalars().all()

        best_mapping = None
        best_score   = 0.0
        for mapping in candidates:
            score = _jaccard(name, mapping.canonical_name)
            if score > best_score:
                best_score   = score
                best_mapping = mapping
        return best_mapping, best_score

    async def _register_external_id(
        self,
        mapping: IngredientMapping,
        source_system: str,
        external_id: str,
    ) -> None:
        """将新的 source → external_id 追加到映射的 external_ids"""
        ext = dict(mapping.external_ids or {})
        if source_system not in ext:
            ext[source_system] = external_id
            mapping.external_ids = ext
            mapping.updated_at = datetime.utcnow()

    async def _update_source_cost_internal(
        self,
        mapping: IngredientMapping,
        source_system: str,
        cost_fen: Optional[int],
        reliability: float,
    ) -> None:
        """更新 source_costs，重新计算加权规范成本"""
        if cost_fen is None:
            return
        costs = dict(mapping.source_costs or {})
        costs[source_system] = {
            "cost_fen":   cost_fen,
            "confidence": reliability,
            "updated_at": datetime.utcnow().isoformat(),
        }
        mapping.source_costs = costs

        # 重新加权
        cost_list = [
            SourceCost(src, v["cost_fen"], v.get("confidence", 0.5))
            for src, v in costs.items()
            if isinstance(v, dict) and "cost_fen" in v
        ]
        if cost_list:
            weighted, composite = reconcile_unit_cost(cost_list)
            mapping.canonical_cost_fen = weighted
            # 成本一致性差时标记冲突
            if composite < 0.6:
                mapping.conflict_flag = True
                logger.warning(
                    "成本来源冲突",
                    canonical_id=mapping.canonical_id,
                    composite_confidence=composite,
                )
        mapping.updated_at = datetime.utcnow()

    async def _ensure_unique_canonical_id(self, base_id: str, name: str) -> str:
        """处理哈希碰撞：若 base_id 已被其他食材占用则追加序号"""
        stmt = select(IngredientMapping).where(
            IngredientMapping.canonical_id == base_id
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if not existing:
            return base_id
        # 已被不同食材占用 → 追加 UUID 后 4 位
        suffix = uuid.uuid4().hex[:4].upper()
        return f"{base_id}-{suffix}"

    async def _write_audit(
        self,
        entity_type: str,
        canonical_id: Optional[str],
        action: str,
        source_system: Optional[str],
        raw_external_id: Optional[str],
        raw_name: Optional[str],
        matched_canonical_id: Optional[str],
        confidence: Optional[float],
        method: Optional[str],
        evidence: Optional[dict],
        created_by: Optional[str],
    ) -> None:
        log = FusionAuditLog(
            entity_type=entity_type,
            canonical_id=canonical_id,
            action=action,
            source_system=source_system,
            raw_external_id=raw_external_id,
            raw_name=raw_name,
            matched_canonical_id=matched_canonical_id,
            confidence=confidence,
            fusion_method=method,
            evidence=evidence,
            created_by=created_by,
        )
        self.db.add(log)
