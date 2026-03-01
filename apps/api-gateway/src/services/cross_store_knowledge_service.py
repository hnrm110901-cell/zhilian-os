"""
L3 跨店知识聚合核心服务

职责：
  1. classify_store_tier()       — 按座位数/营收目标自动划分层级
  2. compute_pairwise_similarity() — 两两门店相似度矩阵
  3. build_peer_groups()          — 按 tier+region 构建同伴组
  4. get_peer_benchmarks()        — 给定门店，计算同伴组 p25/p50/p75/p90
  5. materialize_metrics()        — 批量写入 cross_store_metrics + Neo4j
  6. get_bom_variance_across_stores() — 跨店 BOM 一致性分析
  7. get_best_practice_stores()   — 各指标同组 Top N 门店
  8. sync_store_graph()           — 写 Store 节点 + 三类跨店边到 Neo4j

相似度公式：
  score = 0.40 × menu_jaccard
        + 0.20 × region_score   (same_region=1.0, same_city=0.5, other=0.2)
        + 0.20 × tier_score     (same_tier=1.0, else=0.3)
        + 0.20 × capacity_ratio (min_seats/max_seats)

门店层级（tier）划分：
  premium  : seats > 200 或 monthly_target > 50万
  standard : seats 80-200 或 monthly_target 20-50万
  fastfood : seats < 80 或 monthly_target < 20万
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cross_store import CrossStoreMetric, StorePeerGroup, StoreSimilarityCache
from src.models.store import Store
from src.models.dish import Dish
from src.models.bom import BOMTemplate, BOMItem

logger = structlog.get_logger()

# ── 常量 ──────────────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.55   # 写入 Neo4j SIMILAR_TO 的最低阈值
MIN_PEER_GROUP_SIZE  = 2      # 同伴组最少门店数（低于此则归入"全国"组）

TIER_THRESHOLDS = {
    "premium":  {"min_seats": 201, "min_monthly_revenue": 500_000},
    "standard": {"min_seats": 80,  "min_monthly_revenue": 200_000},
    # fastfood: 其余
}

# 相似度各维度权重
W_MENU     = 0.40
W_REGION   = 0.20
W_TIER     = 0.20
W_CAPACITY = 0.20

# 物化指标名单
MATERIALIZE_METRICS = [
    "waste_rate",
    "cost_ratio",
    "bom_compliance",
    "labor_ratio",
    "revenue_per_seat",
    "menu_coverage",
]


# ── 纯函数工具（无 IO，可单元测试）──────────────────────────────────────────

def classify_store_tier(store: Store) -> str:
    """根据座位数和月营收目标划分门店层级"""
    seats   = store.seats or 0
    revenue = float(store.monthly_revenue_target or 0)

    if seats > TIER_THRESHOLDS["premium"]["min_seats"] or \
       revenue > TIER_THRESHOLDS["premium"]["min_monthly_revenue"]:
        return "premium"
    elif seats >= TIER_THRESHOLDS["standard"]["min_seats"] or \
         revenue >= TIER_THRESHOLDS["standard"]["min_monthly_revenue"]:
        return "standard"
    else:
        return "fastfood"


def _dish_name_set(dishes: List[Dish]) -> frozenset:
    return frozenset(d.name.strip().lower() for d in dishes if d.name)


def compute_similarity(
    store_a:   Store,
    store_b:   Store,
    dishes_a:  List[Dish],
    dishes_b:  List[Dish],
) -> Dict:
    """
    计算两家门店的相似度（返回分量明细，方便可解释性）

    Returns dict with keys:
      similarity_score, menu_overlap, region_match, tier_match, capacity_ratio
    """
    # 1. 菜单 Jaccard
    names_a = _dish_name_set(dishes_a)
    names_b = _dish_name_set(dishes_b)
    union   = names_a | names_b
    menu_jaccard = len(names_a & names_b) / len(union) if union else 0.0

    # 2. 区域相似度
    region_a = store_a.region or ""
    region_b = store_b.region or ""
    city_a   = store_a.city   or ""
    city_b   = store_b.city   or ""
    if region_a and region_a == region_b:
        region_score = 1.0
    elif city_a and city_a == city_b:
        region_score = 0.5
    else:
        region_score = 0.2

    # 3. 层级匹配
    tier_a = classify_store_tier(store_a)
    tier_b = classify_store_tier(store_b)
    tier_score = 1.0 if tier_a == tier_b else 0.3

    # 4. 容量比率
    seats_a = store_a.seats or 100
    seats_b = store_b.seats or 100
    capacity_ratio = min(seats_a, seats_b) / max(seats_a, seats_b)

    score = (
        W_MENU     * menu_jaccard
        + W_REGION   * region_score
        + W_TIER     * tier_score
        + W_CAPACITY * capacity_ratio
    )
    return {
        "similarity_score": round(score,           4),
        "menu_overlap":     round(menu_jaccard,    4),
        "region_match":     region_a == region_b,
        "tier_match":       tier_a == tier_b,
        "capacity_ratio":   round(capacity_ratio,  4),
    }


def compute_percentiles(values: List[float]) -> Dict[str, float]:
    """
    计算 p25/p50/p75/p90，至少需要 2 个值；
    1 个值时四分位均等于该值。
    """
    n = len(values)
    if n == 0:
        return {"p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0}
    if n == 1:
        v = values[0]
        return {"p25": v, "p50": v, "p75": v, "p90": v}

    sv = sorted(values)

    def _percentile(pct: float) -> float:
        idx = (n - 1) * pct
        lo  = int(idx)
        hi  = min(lo + 1, n - 1)
        return sv[lo] + (sv[hi] - sv[lo]) * (idx - lo)

    return {
        "p25": round(_percentile(0.25), 6),
        "p50": round(_percentile(0.50), 6),
        "p75": round(_percentile(0.75), 6),
        "p90": round(_percentile(0.90), 6),
    }


def compute_percentile_rank(value: float, peer_values: List[float]) -> float:
    """计算 value 在 peer_values 中的百分位排名（0–100）"""
    if not peer_values:
        return 50.0
    below = sum(1 for v in peer_values if v < value)
    return round(below / len(peer_values) * 100, 1)


# ── 主服务 ────────────────────────────────────────────────────────────────────

class CrossStoreKnowledgeService:
    """
    L3 跨店知识聚合服务

    调用示例：
        svc = CrossStoreKnowledgeService(db)
        await svc.materialize_metrics(lookback_days=30)
        benchmarks = await svc.get_peer_benchmarks("STORE001", "waste_rate")
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 相似度矩阵 ────────────────────────────────────────────────────────────

    async def compute_pairwise_similarity(
        self,
        store_ids: Optional[List[str]] = None,
    ) -> List[StoreSimilarityCache]:
        """
        计算所有门店两两相似度并写入 store_similarity_cache。
        若 store_ids 为 None，则处理全库激活门店。
        返回写入/更新的记录列表。
        """
        stores = await self._load_stores(store_ids)
        if len(stores) < 2:
            return []

        # 批量加载菜品（减少 N+1 查询）
        all_dishes = await self._load_dishes_by_store(
            [s.id for s in stores]
        )

        written: List[StoreSimilarityCache] = []
        for i in range(len(stores)):
            for j in range(i + 1, len(stores)):
                sa = stores[i]
                sb = stores[j]
                # 保证 store_a_id < store_b_id
                if sa.id > sb.id:
                    sa, sb = sb, sa

                sim = compute_similarity(
                    sa, sb,
                    all_dishes.get(sa.id, []),
                    all_dishes.get(sb.id, []),
                )
                rec = await self._upsert_similarity(sa.id, sb.id, sim)
                written.append(rec)

        await self.db.flush()
        logger.info(
            "相似度矩阵计算完毕",
            store_count=len(stores),
            pairs=len(written),
        )
        return written

    # ── 同伴组构建 ────────────────────────────────────────────────────────────

    async def build_peer_groups(
        self,
        store_ids: Optional[List[str]] = None,
    ) -> List[StorePeerGroup]:
        """
        按 tier + region 分组，写入 store_peer_groups。
        组内门店数不足 MIN_PEER_GROUP_SIZE 的，归入 "{tier}_全国" 组。
        """
        stores = await self._load_stores(store_ids)
        groups: Dict[str, List[str]] = {}

        for store in stores:
            tier   = store.tier or classify_store_tier(store)
            region = store.region or "全国"
            key    = f"{tier}_{region}"
            groups.setdefault(key, []).append(store.id)

        # 小组归并到全国兜底组
        national_merge: Dict[str, List[str]] = {}
        final_groups: Dict[str, List[str]]   = {}

        for key, ids in groups.items():
            tier = key.split("_")[0]
            if len(ids) < MIN_PEER_GROUP_SIZE:
                national_key = f"{tier}_全国"
                national_merge.setdefault(national_key, []).extend(ids)
            else:
                final_groups[key] = ids

        # 合并小组
        for key, ids in national_merge.items():
            final_groups.setdefault(key, []).extend(ids)

        saved: List[StorePeerGroup] = []
        for key, ids in final_groups.items():
            parts  = key.split("_", 1)
            tier   = parts[0] if len(parts) > 0 else ""
            region = parts[1] if len(parts) > 1 else "全国"
            saved.append(await self._upsert_peer_group(key, tier, region, ids))

        await self.db.flush()
        logger.info("同伴组构建完毕", group_count=len(saved))
        return saved

    # ── 同伴组 Benchmark 查询 ─────────────────────────────────────────────────

    async def get_peer_benchmarks(
        self,
        store_id:    str,
        metric_name: str,
        metric_date: Optional[date] = None,
    ) -> Optional[Dict]:
        """
        返回指定门店在同伴组中的百分位信息。

        Returns::
            {
              "store_id": "STORE001",
              "metric_name": "waste_rate",
              "value": 0.12,
              "peer_group": "standard_华东",
              "peer_count": 8,
              "percentile_in_peer": 72.5,
              "peer_p25": 0.06, "peer_p50": 0.09,
              "peer_p75": 0.14, "peer_p90": 0.18,
              "gap_to_median": 0.03,
              "verdict": "below_median"
            }
        """
        d = metric_date or (date.today() - timedelta(days=1))
        stmt = (
            select(CrossStoreMetric)
            .where(
                and_(
                    CrossStoreMetric.store_id    == store_id,
                    CrossStoreMetric.metric_name == metric_name,
                    CrossStoreMetric.metric_date == d,
                )
            )
            .limit(1)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if not row:
            return None

        gap = row.value - (row.peer_p50 or 0)
        verdict = (
            "top_quartile"  if (row.percentile_in_peer or 0) >= 75 else
            "above_median"  if (row.percentile_in_peer or 0) >= 50 else
            "below_median"  if (row.percentile_in_peer or 0) >= 25 else
            "bottom_quartile"
        )
        return {
            "store_id":          store_id,
            "metric_name":       metric_name,
            "metric_date":       d.isoformat(),
            "value":             row.value,
            "peer_group":        row.peer_group,
            "peer_count":        row.peer_count,
            "percentile_in_peer": row.percentile_in_peer,
            "peer_p25":          row.peer_p25,
            "peer_p50":          row.peer_p50,
            "peer_p75":          row.peer_p75,
            "peer_p90":          row.peer_p90,
            "gap_to_median":     round(gap, 4),
            "verdict":           verdict,
        }

    async def get_all_benchmarks(
        self,
        store_id:    str,
        metric_date: Optional[date] = None,
    ) -> List[Dict]:
        """获取某门店所有指标的 Benchmark 快照"""
        results = []
        for metric in MATERIALIZE_METRICS:
            bm = await self.get_peer_benchmarks(store_id, metric, metric_date)
            if bm:
                results.append(bm)
        return results

    # ── 日维度物化 ────────────────────────────────────────────────────────────

    async def materialize_metrics(
        self,
        target_date:  Optional[date] = None,
        store_ids:    Optional[List[str]] = None,
        lookback_days: int = 30,
    ) -> Dict[str, int]:
        """
        计算并写入 cross_store_metrics。

        指标来源：
          waste_rate      — WasteEvent.variance_pct > 0 的平均偏差（近 lookback_days）
          cost_ratio      — InventoryTransaction.total_cost / Order.total_amount 近 30 天
          bom_compliance  — BOM 实际用量/标准用量合规率（近 30 天有 WasteEvent 数据的门店）
          menu_coverage   — Dish 数量 / 全品牌 Dish 名称总数
          revenue_per_seat — 占位符，需接入真实 Order 数据
          labor_ratio     — 占位符，需接入 HR 数据

        当前实现：waste_rate 和 menu_coverage 有真实计算，其余为结构占位符。
        """
        d = target_date or (date.today() - timedelta(days=1))
        stores = await self._load_stores(store_ids)

        # 确保同伴组已建立
        await self.build_peer_groups([s.id for s in stores])
        peer_group_map = await self._load_peer_group_map()   # store_id → group_key

        # 计算各门店 waste_rate（近 lookback_days 的平均损耗超标率）
        waste_rates  = await self._compute_waste_rates(stores, lookback_days)
        menu_coverages = await self._compute_menu_coverages(stores)

        metric_values: Dict[str, Dict[str, float]] = {
            "waste_rate":   waste_rates,
            "menu_coverage": menu_coverages,
        }

        written = 0
        for metric_name, store_vals in metric_values.items():
            if not store_vals:
                continue
            # 分组计算百分位
            groups: Dict[str, List[Tuple[str, float]]] = {}
            for sid, val in store_vals.items():
                gk = peer_group_map.get(sid, "unknown_全国")
                groups.setdefault(gk, []).append((sid, val))

            for group_key, entries in groups.items():
                vals  = [v for _, v in entries]
                pcts  = compute_percentiles(vals)
                for sid, val in entries:
                    prank = compute_percentile_rank(val, vals)
                    await self._upsert_metric(
                        store_id=sid,
                        metric_date=d,
                        metric_name=metric_name,
                        value=val,
                        peer_group=group_key,
                        peer_count=len(vals),
                        peer_p25=pcts["p25"],
                        peer_p50=pcts["p50"],
                        peer_p75=pcts["p75"],
                        peer_p90=pcts["p90"],
                        percentile_in_peer=prank,
                    )
                    written += 1

        await self.db.flush()
        logger.info("跨店指标物化完成", metric_rows=written, date=d.isoformat())
        return {"written": written, "date": d.isoformat()}

    # ── BOM 一致性分析 ────────────────────────────────────────────────────────

    async def get_bom_variance_across_stores(
        self,
        dish_name:  Optional[str] = None,
        min_stores: int = 2,
    ) -> List[Dict]:
        """
        跨店 BOM 一致性：找出相同菜品在不同门店用量差异最大的食材。

        Returns list of::
            {
              "dish_id": "...",
              "dish_name": "海鲜粥",
              "ingredient_id": "INV_001",
              "store_count": 5,
              "mean_qty": 175.0,
              "max_qty": 210.0,
              "min_qty": 140.0,
              "variance_pct": 0.2,      # (max-min)/mean
              "stores": [{"store_id", "qty"}, ...]
            }
        """
        # 查询所有激活 BOM 的明细（跨门店）
        stmt = (
            select(
                BOMItem.ingredient_id,
                BOMItem.standard_qty,
                BOMItem.unit,
                BOMTemplate.store_id,
                BOMTemplate.dish_id,
            )
            .join(BOMTemplate, BOMItem.bom_id == BOMTemplate.id)
            .where(BOMTemplate.is_active.is_(True))
        )
        rows = (await self.db.execute(stmt)).all()

        # 按 dish_id + ingredient_id 聚合
        agg: Dict[Tuple, List] = {}
        for row in rows:
            key = (str(row.dish_id), row.ingredient_id)
            agg.setdefault(key, []).append(
                {"store_id": row.store_id, "qty": float(row.standard_qty or 0)}
            )

        results = []
        for (dish_id, ing_id), entries in agg.items():
            if len(entries) < min_stores:
                continue
            qtys = [e["qty"] for e in entries]
            mean = statistics.mean(qtys)
            if mean == 0:
                continue
            variance_pct = (max(qtys) - min(qtys)) / mean
            results.append({
                "dish_id":      dish_id,
                "ingredient_id": ing_id,
                "store_count":  len(entries),
                "mean_qty":     round(mean,         4),
                "max_qty":      round(max(qtys),    4),
                "min_qty":      round(min(qtys),    4),
                "variance_pct": round(variance_pct, 4),
                "stores":       entries,
            })

        # 按 variance_pct 降序
        results.sort(key=lambda x: x["variance_pct"], reverse=True)
        return results

    # ── 最佳实践门店 ──────────────────────────────────────────────────────────

    async def get_best_practice_stores(
        self,
        metric_name:    str,
        top_n:          int  = 5,
        direction:      str  = "lower_better",
        peer_group_key: Optional[str] = None,
        metric_date:    Optional[date] = None,
    ) -> List[Dict]:
        """
        返回同组内某指标表现最佳的 Top N 门店。

        direction = "lower_better"  → 值越小越好（损耗率/成本率）
        direction = "higher_better" → 值越大越好（菜单覆盖率）
        """
        d = metric_date or (date.today() - timedelta(days=1))
        stmt = select(CrossStoreMetric).where(
            and_(
                CrossStoreMetric.metric_name == metric_name,
                CrossStoreMetric.metric_date == d,
            )
        )
        if peer_group_key:
            stmt = stmt.where(CrossStoreMetric.peer_group == peer_group_key)

        rows = (await self.db.execute(stmt)).scalars().all()
        if not rows:
            return []

        sorted_rows = sorted(
            rows,
            key=lambda r: r.value,
            reverse=(direction == "higher_better"),
        )
        return [
            {
                "rank":              i + 1,
                "store_id":          r.store_id,
                "value":             r.value,
                "peer_group":        r.peer_group,
                "percentile_in_peer": r.percentile_in_peer,
            }
            for i, r in enumerate(sorted_rows[:top_n])
        ]

    # ── Neo4j 跨店图同步 ─────────────────────────────────────────────────────

    async def sync_store_graph(
        self,
        store_ids:   Optional[List[str]] = None,
        metric_date: Optional[date] = None,
    ) -> Dict:
        """
        将 Store 节点 + SIMILAR_TO / BENCHMARK_OF / SHARES_RECIPE 边批量写入 Neo4j。
        """
        try:
            from src.ontology.data_sync import OntologyDataSync
            sync = OntologyDataSync()
        except Exception as e:
            logger.warning("Neo4j 连接失败，跳过图同步", error=str(e))
            return {"skipped": True}

        stores = await self._load_stores(store_ids)
        d      = metric_date or (date.today() - timedelta(days=1))
        peer_group_map = await self._load_peer_group_map()

        # 1. 写 Store 节点（含物化 KPI）
        for store in stores:
            tier       = store.tier or classify_store_tier(store)
            waste_bm   = await self.get_peer_benchmarks(store.id, "waste_rate",   d)
            coverage_bm = await self.get_peer_benchmarks(store.id, "menu_coverage", d)
            sync.upsert_store(
                store_id=store.id,
                name=store.name,
                region=store.region or "",
                city=store.city or "",
                tier=tier,
                seats=store.seats or 0,
                area=float(store.area or 0),
                status=store.status or "active",
                opening_date=store.opening_date or "",
                peer_group=peer_group_map.get(store.id, ""),
                waste_rate_p30d=waste_bm["value"] if waste_bm else None,
                menu_coverage_p30d=coverage_bm["value"] if coverage_bm else None,
            )

        # 2. 写 SIMILAR_TO 边
        sims = (await self.db.execute(
            select(StoreSimilarityCache).where(
                StoreSimilarityCache.similarity_score >= SIMILARITY_THRESHOLD
            )
        )).scalars().all()
        for sim in sims:
            sync.create_similar_to_edge(
                store_a_id=sim.store_a_id,
                store_b_id=sim.store_b_id,
                similarity_score=sim.similarity_score,
                menu_overlap=sim.menu_overlap,
                tier_match=sim.tier_match,
                region_match=sim.region_match,
            )

        # 3. 写 SHARES_RECIPE 边（variance_pct > 10% 的 BOM 差异）
        variances = await self.get_bom_variance_across_stores(min_stores=2)
        for item in variances:
            if item["variance_pct"] < 0.10:
                continue
            store_entries = item["stores"]
            for i in range(len(store_entries)):
                for j in range(i + 1, len(store_entries)):
                    sync.create_shares_recipe_edge(
                        store_a_id=store_entries[i]["store_id"],
                        store_b_id=store_entries[j]["store_id"],
                        dish_id=item["dish_id"],
                        ingredient_id=item["ingredient_id"],
                        variance_pct=item["variance_pct"],
                        mean_qty=item["mean_qty"],
                    )

        # 4. 写 WasteEvent OCCURRED_IN Store（最近 100 条）
        from src.models.waste_event import WasteEvent
        from sqlalchemy import desc
        waste_stmt = (
            select(WasteEvent.event_id, WasteEvent.store_id)
            .order_by(desc(WasteEvent.created_at))
            .limit(100)
        )
        waste_rows = (await self.db.execute(waste_stmt)).all()
        for row in waste_rows:
            sync.link_waste_to_store(
                event_id=row.event_id,
                store_id=row.store_id,
            )

        sync.close()
        logger.info(
            "跨店图同步完成",
            stores=len(stores),
            similar_edges=len(sims),
            recipe_variances=len([v for v in variances if v["variance_pct"] >= 0.10]),
        )
        return {
            "stores_synced":     len(stores),
            "similar_to_edges":  len(sims),
            "shares_recipe_edges": len(
                [v for v in variances if v["variance_pct"] >= 0.10]
            ),
        }

    # ── 相似门店查询 ──────────────────────────────────────────────────────────

    async def get_similar_stores(
        self,
        store_id:   str,
        top_n:      int   = 5,
        min_score:  float = SIMILARITY_THRESHOLD,
    ) -> List[Dict]:
        """获取与目标门店最相似的 Top N 门店"""
        stmt = (
            select(StoreSimilarityCache)
            .where(
                and_(
                    (StoreSimilarityCache.store_a_id == store_id)
                    | (StoreSimilarityCache.store_b_id == store_id),
                    StoreSimilarityCache.similarity_score >= min_score,
                )
            )
            .order_by(StoreSimilarityCache.similarity_score.desc())
            .limit(top_n)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        results = []
        for r in rows:
            peer_id = r.store_b_id if r.store_a_id == store_id else r.store_a_id
            results.append({
                "peer_store_id":  peer_id,
                "similarity_score": r.similarity_score,
                "menu_overlap":   r.menu_overlap,
                "region_match":   r.region_match,
                "tier_match":     r.tier_match,
                "capacity_ratio": r.capacity_ratio,
            })
        return results

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _load_stores(self, store_ids: Optional[List[str]]) -> List[Store]:
        stmt = select(Store).where(Store.is_active.is_(True))
        if store_ids:
            stmt = stmt.where(Store.id.in_(store_ids))
        return list((await self.db.execute(stmt)).scalars().all())

    async def _load_dishes_by_store(
        self, store_ids: List[str]
    ) -> Dict[str, List[Dish]]:
        stmt = select(Dish).where(Dish.store_id.in_(store_ids))
        rows = (await self.db.execute(stmt)).scalars().all()
        result: Dict[str, List[Dish]] = {}
        for d in rows:
            result.setdefault(d.store_id, []).append(d)
        return result

    async def _load_peer_group_map(self) -> Dict[str, str]:
        """返回 {store_id: group_key} 映射"""
        stmt = select(StorePeerGroup)
        groups = (await self.db.execute(stmt)).scalars().all()
        mapping: Dict[str, str] = {}
        for g in groups:
            for sid in (g.store_ids or []):
                mapping[sid] = g.group_key
        return mapping

    async def _compute_waste_rates(
        self, stores: List[Store], lookback_days: int
    ) -> Dict[str, float]:
        """
        用 WasteEvent.variance_pct 平均值作为 waste_rate 代理指标。
        （真实实现应接入 InventoryTransaction 数据）
        """
        from src.models.waste_event import WasteEvent
        since = datetime.utcnow() - timedelta(days=lookback_days)
        result: Dict[str, float] = {}

        for store in stores:
            stmt = (
                select(WasteEvent.variance_pct)
                .where(
                    and_(
                        WasteEvent.store_id == store.id,
                        WasteEvent.created_at >= since,
                        WasteEvent.variance_pct.isnot(None),
                    )
                )
                .limit(200)
            )
            rows = (await self.db.execute(stmt)).scalars().all()
            vals = [float(r) for r in rows if r is not None]
            result[store.id] = round(statistics.mean(vals), 4) if vals else 0.0

        return result

    async def _compute_menu_coverages(
        self, stores: List[Store]
    ) -> Dict[str, float]:
        """菜品覆盖率 = 本店菜品数 / 全品牌菜品名集合大小"""
        all_stmt = select(Dish.name).where(Dish.name.isnot(None))
        all_names = set(
            (await self.db.execute(all_stmt)).scalars().all()
        )
        total = len(all_names) or 1
        result: Dict[str, float] = {}

        for store in stores:
            stmt = select(Dish.name).where(
                and_(Dish.store_id == store.id, Dish.name.isnot(None))
            )
            names = set((await self.db.execute(stmt)).scalars().all())
            result[store.id] = round(len(names) / total, 4)

        return result

    async def _upsert_similarity(
        self, store_a: str, store_b: str, sim: Dict
    ) -> StoreSimilarityCache:
        stmt = select(StoreSimilarityCache).where(
            and_(
                StoreSimilarityCache.store_a_id == store_a,
                StoreSimilarityCache.store_b_id == store_b,
            )
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.similarity_score = sim["similarity_score"]
            existing.menu_overlap     = sim["menu_overlap"]
            existing.region_match     = sim["region_match"]
            existing.tier_match       = sim["tier_match"]
            existing.capacity_ratio   = sim["capacity_ratio"]
            existing.computed_at      = datetime.utcnow()
            return existing
        rec = StoreSimilarityCache(
            store_a_id=store_a, store_b_id=store_b, **sim,
            computed_at=datetime.utcnow(),
        )
        self.db.add(rec)
        return rec

    async def _upsert_peer_group(
        self, key: str, tier: str, region: str, store_ids: List[str]
    ) -> StorePeerGroup:
        stmt = select(StorePeerGroup).where(StorePeerGroup.group_key == key)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.store_ids   = store_ids
            existing.store_count = len(store_ids)
            existing.updated_at  = datetime.utcnow()
            return existing
        g = StorePeerGroup(
            group_key=key, tier=tier, region=region,
            store_ids=store_ids, store_count=len(store_ids),
        )
        self.db.add(g)
        return g

    async def _upsert_metric(
        self, store_id: str, metric_date: date, metric_name: str,
        value: float, peer_group: str, peer_count: int,
        peer_p25: float, peer_p50: float, peer_p75: float, peer_p90: float,
        percentile_in_peer: float,
    ) -> None:
        stmt = select(CrossStoreMetric).where(
            and_(
                CrossStoreMetric.store_id    == store_id,
                CrossStoreMetric.metric_date == metric_date,
                CrossStoreMetric.metric_name == metric_name,
            )
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.value             = value
            existing.peer_group        = peer_group
            existing.peer_count        = peer_count
            existing.peer_p25          = peer_p25
            existing.peer_p50          = peer_p50
            existing.peer_p75          = peer_p75
            existing.peer_p90          = peer_p90
            existing.percentile_in_peer = percentile_in_peer
        else:
            self.db.add(CrossStoreMetric(
                store_id=store_id,
                metric_date=metric_date,
                metric_name=metric_name,
                value=value,
                peer_group=peer_group,
                peer_count=peer_count,
                peer_p25=peer_p25,
                peer_p50=peer_p50,
                peer_p75=peer_p75,
                peer_p90=peer_p90,
                percentile_in_peer=percentile_in_peer,
            ))
