"""
统一门店健康指数（StoreHealthIndex）— Single Source of Truth

解决的问题：
  系统中原有 4 套健康分引擎（store_health_service / private_domain_health_service /
  diagnosis_service / ceo_dashboard_service），同一门店有 4 个互相矛盾的健康分，
  没有任何一个被定义为"权威值"。

设计原则：
  - 本服务是唯一的权威健康分出口，所有 Dashboard 应从此接口取数
  - 三大支柱聚合，权重经过业务验证：
      运营健康  40% — 营收/翻台/成本/客诉/人效（复用 StoreHealthService）
      私域健康  35% — 会员/留存/信号/旅程/增长（复用 PrivateDomainHealthService）
      AI 诊断   25% — 损耗/效率/成本/质量/库存（复用 UniversalReasoningEngine 最新报告）
  - 缺失支柱按已有支柱归一化，不返回 0
  - 快照写入 store_health_snapshots，支持历史趋势查询

等级阈值（统一标准）：
  优秀 85+  /  良好 70-84  /  待改善 50-69  /  预警 <50
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 三大支柱权重 ──────────────────────────────────────────────────────────────
_PILLAR_WEIGHTS: Dict[str, float] = {
    "operational":     0.40,
    "private_domain":  0.35,
    "ai_diagnosis":    0.25,
}

# ── 等级阈值 ──────────────────────────────────────────────────────────────────
def _classify(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "needs_improvement"
    return "alert"

_LEVEL_LABEL = {
    "excellent":        "优秀",
    "good":             "良好",
    "needs_improvement":"待改善",
    "alert":            "预警",
}
_LEVEL_COLOR = {
    "excellent":        "green",
    "good":             "blue",
    "needs_improvement":"orange",
    "alert":            "red",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数
# ═══════════════════════════════════════════════════════════════════════════════

def aggregate_pillars(pillar_scores: Dict[str, Optional[float]]) -> float:
    """
    按可用支柱归一化聚合，缺失支柱不影响其他支柱的计算。

    Args:
        pillar_scores: {"operational": 72.0, "private_domain": None, "ai_diagnosis": 68.0}

    Returns:
        0-100 综合分
    """
    available = {k: v for k, v in pillar_scores.items() if v is not None}
    if not available:
        return 50.0
    total_weight = sum(_PILLAR_WEIGHTS.get(k, 0.0) for k in available)
    if total_weight <= 0:
        return 50.0
    weighted_sum = sum(v * _PILLAR_WEIGHTS[k] for k, v in available.items())
    return round(weighted_sum / total_weight, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# 各支柱数据获取（每个独立 try/except，互不影响）
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_operational_score(store_id: str, db: AsyncSession) -> Optional[float]:
    """从 StoreHealthService 获取运营健康分（0-100）"""
    try:
        from src.services.store_health_service import StoreHealthService
        result = await StoreHealthService.get_store_score(
            store_id=store_id, target_date=date.today(), db=db
        )
        return float(result.get("score", 0)) if result else None
    except Exception as exc:
        logger.warning("health_index.operational_failed", store_id=store_id, error=str(exc))
        return None


async def _get_private_domain_score(store_id: str, db: AsyncSession) -> Optional[float]:
    """从 PrivateDomainHealthService 获取私域健康分（0-100）"""
    try:
        from src.services.private_domain_health_service import calculate_health_score
        result = await calculate_health_score(store_id, db)
        return float(result.get("total_score", 0)) if result else None
    except Exception as exc:
        logger.warning("health_index.private_domain_failed", store_id=store_id, error=str(exc))
        return None


async def _get_ai_diagnosis_score(store_id: str, db: AsyncSession) -> Optional[float]:
    """
    从最新 L4 推理报告中取综合健康分（0-100）。
    无报告时返回 None（降级，不阻塞）。
    """
    try:
        row = (await db.execute(
            text("""
                SELECT overall_health_score
                FROM reasoning_reports
                WHERE store_id = :sid
                ORDER BY report_date DESC
                LIMIT 1
            """),
            {"sid": store_id},
        )).fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return None
    except Exception as exc:
        logger.warning("health_index.ai_diagnosis_failed", store_id=store_id, error=str(exc))
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 主接口
# ═══════════════════════════════════════════════════════════════════════════════

async def get_store_health_index(
    store_id: str,
    db: AsyncSession,
    save_snapshot: bool = True,
) -> Dict[str, Any]:
    """
    获取门店统一健康指数（权威单一出口）。

    Returns:
        {
          "store_id":        str,
          "score":           float,       # 综合 0-100
          "level":           str,         # excellent | good | needs_improvement | alert
          "level_label":     str,         # 优秀 | 良好 | 待改善 | 预警
          "level_color":     str,
          "pillars": {
              "operational":    {"score": float|None, "weight": 0.40, "label": "运营健康"},
              "private_domain": {"score": float|None, "weight": 0.35, "label": "私域健康"},
              "ai_diagnosis":   {"score": float|None, "weight": 0.25, "label": "AI诊断"},
          },
          "computed_at":     str (ISO),
          "trend":           list[dict],  # 近 7 天快照
        }
    """
    op_score, pd_score, ai_score = (
        await _get_operational_score(store_id, db),
        await _get_private_domain_score(store_id, db),
        await _get_ai_diagnosis_score(store_id, db),
    )

    pillar_scores = {
        "operational":    op_score,
        "private_domain": pd_score,
        "ai_diagnosis":   ai_score,
    }
    composite = aggregate_pillars(pillar_scores)
    level = _classify(composite)
    computed_at = datetime.utcnow()

    if save_snapshot:
        await _save_snapshot(store_id, composite, pillar_scores, computed_at, db)

    trend = await _get_trend(store_id, db)

    return {
        "store_id":    store_id,
        "score":       composite,
        "level":       level,
        "level_label": _LEVEL_LABEL[level],
        "level_color": _LEVEL_COLOR[level],
        "pillars": {
            "operational":    {"score": op_score, "weight": 0.40, "label": "运营健康"},
            "private_domain": {"score": pd_score, "weight": 0.35, "label": "私域健康"},
            "ai_diagnosis":   {"score": ai_score, "weight": 0.25, "label": "AI诊断"},
        },
        "computed_at": computed_at.isoformat(),
        "trend":       trend,
    }


async def get_multi_store_health_index(
    store_ids: List[str],
    db: AsyncSession,
) -> List[Dict[str, Any]]:
    """
    批量获取多门店健康指数，按综合分降序排列。
    单店失败静默跳过，不影响其他门店。
    """
    results = []
    for store_id in store_ids:
        try:
            r = await get_store_health_index(store_id, db, save_snapshot=False)
            results.append(r)
        except Exception as exc:
            logger.warning("health_index.store_failed", store_id=store_id, error=str(exc))
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── 快照 helpers ──────────────────────────────────────────────────────────────

async def _save_snapshot(
    store_id: str,
    composite: float,
    pillars: Dict[str, Optional[float]],
    ts: datetime,
    db: AsyncSession,
) -> None:
    """写入历史快照（ON CONFLICT 幂等：同一天同一门店只保留最新值）"""
    try:
        await db.execute(
            text("""
                INSERT INTO store_health_snapshots
                    (store_id, snapshot_date, composite_score,
                     operational_score, private_domain_score, ai_diagnosis_score,
                     computed_at)
                VALUES
                    (:sid, :dt, :comp, :op, :pd, :ai, :ts)
                ON CONFLICT (store_id, snapshot_date)
                DO UPDATE SET
                    composite_score      = EXCLUDED.composite_score,
                    operational_score    = EXCLUDED.operational_score,
                    private_domain_score = EXCLUDED.private_domain_score,
                    ai_diagnosis_score   = EXCLUDED.ai_diagnosis_score,
                    computed_at          = EXCLUDED.computed_at
            """),
            {
                "sid":  store_id,
                "dt":   ts.date(),
                "comp": composite,
                "op":   pillars.get("operational"),
                "pd":   pillars.get("private_domain"),
                "ai":   pillars.get("ai_diagnosis"),
                "ts":   ts,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("health_index.snapshot_failed", store_id=store_id, error=str(exc))
        await db.rollback()


async def _get_trend(store_id: str, db: AsyncSession, days: int = 7) -> List[Dict]:
    """查询近 N 天历史快照，用于前端趋势图。"""
    try:
        rows = (await db.execute(
            text("""
                SELECT snapshot_date, composite_score,
                       operational_score, private_domain_score, ai_diagnosis_score
                FROM store_health_snapshots
                WHERE store_id = :sid
                  AND snapshot_date >= CURRENT_DATE - (:days * INTERVAL '1 day')
                ORDER BY snapshot_date ASC
            """),
            {"sid": store_id, "days": days},
        )).fetchall()
        return [
            {
                "date":            str(r[0]),
                "score":           round(float(r[1]), 1) if r[1] else None,
                "operational":     round(float(r[2]), 1) if r[2] else None,
                "private_domain":  round(float(r[3]), 1) if r[3] else None,
                "ai_diagnosis":    round(float(r[4]), 1) if r[4] else None,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("health_index.trend_failed", store_id=store_id, error=str(exc))
        return []
