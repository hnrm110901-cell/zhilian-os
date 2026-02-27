"""
推理规则库 API — 知识资产管理 + 行业基准对比

端点：
  GET   /api/v1/rules/                     查询规则列表（支持过滤）
  POST  /api/v1/rules/                     创建新规则
  GET   /api/v1/rules/{rule_id}            查询单条规则
  PUT   /api/v1/rules/{rule_id}/activate   激活规则
  PUT   /api/v1/rules/{rule_id}/archive    归档规则
  POST  /api/v1/rules/match                规则匹配（给定上下文→返回匹配规则）
  GET   /api/v1/rules/stats                规则库统计
  POST  /api/v1/rules/seed                 初始化预置规则（admin）

  GET   /api/v1/benchmarks/{industry}      查询行业基准
  POST  /api/v1/benchmarks/compare         与行业基准对比
  POST  /api/v1/benchmarks/seed            初始化基准数据（admin）
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user, require_role
from src.models.knowledge_rule import RuleCategory, RuleStatus, RuleType
from src.models.user import User, UserRole
from src.services.knowledge_rule_service import KnowledgeRuleService

router = APIRouter(tags=["knowledge_rules"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RuleCreateIn(BaseModel):
    rule_code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    category: RuleCategory
    rule_type: RuleType = RuleType.THRESHOLD
    condition: Dict[str, Any]
    conclusion: Dict[str, Any]
    base_confidence: float = Field(0.7, ge=0, le=1)
    weight: float = Field(1.0, gt=0)
    industry_type: str = Field("general", max_length=50)
    applicable_store_ids: Optional[List[str]] = None
    applicable_dish_categories: Optional[List[str]] = None
    source: str = Field("expert", max_length=50)
    is_public: bool = False
    tags: Optional[List[str]] = None


class RuleMatchIn(BaseModel):
    context: Dict[str, Any] = Field(..., description="业务上下文度量值")
    category: Optional[RuleCategory] = None


class BenchmarkCompareIn(BaseModel):
    industry_type: str = Field(..., description="行业类型：seafood/hotpot/fastfood")
    actual_values: Dict[str, float] = Field(..., description="实际指标值 {metric_name: value}")


# ── 规则端点 ──────────────────────────────────────────────────────────────────

@router.get("/api/v1/rules/stats")
async def get_rule_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """规则库统计（总数、激活数、分类分布）"""
    svc = KnowledgeRuleService(db)
    return await svc.get_rule_stats()


@router.get("/api/v1/rules/")
async def list_rules(
    category: Optional[RuleCategory] = Query(None),
    status: Optional[RuleStatus] = Query(None),
    industry_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询规则列表"""
    svc = KnowledgeRuleService(db)
    rules = await svc.list_rules(
        category=category,
        status=status,
        industry_type=industry_type,
        source=source,
        limit=limit,
        offset=offset,
    )
    return {
        "rules": [_rule_to_dict(r) for r in rules],
        "count": len(rules),
        "offset": offset,
    }


@router.post("/api/v1/rules/", status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新推理规则"""
    svc = KnowledgeRuleService(db)
    existing = await svc.get_by_code(payload.rule_code)
    if existing:
        raise HTTPException(status_code=409, detail=f"规则编码 {payload.rule_code} 已存在")
    rule = await svc.create_rule({
        **payload.model_dump(),
        "status": RuleStatus.DRAFT,
        "contributed_by": str(current_user.id),
    })
    await db.commit()
    return _rule_to_dict(rule)


@router.get("/api/v1/rules/{rule_id}")
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询单条规则详情"""
    svc = KnowledgeRuleService(db)
    rule = await svc.get_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _rule_to_dict(rule)


@router.put("/api/v1/rules/{rule_id}/activate")
async def activate_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """激活规则（draft→active）"""
    svc = KnowledgeRuleService(db)
    ok = await svc.activate_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.commit()
    return {"message": "规则已激活", "rule_id": rule_id}


@router.put("/api/v1/rules/{rule_id}/archive")
async def archive_rule(
    rule_id: str,
    superseded_by: Optional[str] = Query(None, description="替代规则 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """归档规则"""
    svc = KnowledgeRuleService(db)
    ok = await svc.archive_rule(rule_id, superseded_by=superseded_by)
    if not ok:
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.commit()
    return {"message": "规则已归档", "rule_id": rule_id}


@router.post("/api/v1/rules/match")
async def match_rules(
    payload: RuleMatchIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    规则匹配引擎 — 给定业务上下文，返回最匹配的推理规则

    示例 context::

        {"waste_rate": 0.18, "window_days": 3, "consecutive": true}
    """
    svc = KnowledgeRuleService(db)
    matched = await svc.match_rules(payload.context, category=payload.category)
    return {
        "matched_count": len(matched),
        "top_rule": matched[0] if matched else None,
        "all_matches": matched,
    }


@router.post("/api/v1/rules/seed")
async def seed_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """初始化预置推理规则（200 条）"""
    svc = KnowledgeRuleService(db)
    result = await svc.seed_rules()
    await db.commit()
    return {**result, "message": "规则种子数据初始化完成"}


# ── 行业基准端点 ──────────────────────────────────────────────────────────────

@router.get("/api/v1/benchmarks/{industry_type}")
async def get_benchmarks(
    industry_type: str,
    metric_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询行业基准数据（seafood / hotpot / fastfood）"""
    svc = KnowledgeRuleService(db)
    benchmarks = await svc.get_benchmarks(industry_type, metric_name)
    return {
        "industry_type": industry_type,
        "benchmarks": [_benchmark_to_dict(b) for b in benchmarks],
        "count": len(benchmarks),
    }


@router.post("/api/v1/benchmarks/compare")
async def compare_to_benchmark(
    payload: BenchmarkCompareIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    门店实际指标与行业基准对比

    返回每项指标的分位数区间和差距分析
    """
    svc = KnowledgeRuleService(db)
    results = await svc.compare_to_benchmark(
        payload.industry_type, payload.actual_values
    )
    above = sum(1 for r in results if r["status"] == "above_median")
    return {
        "industry_type": payload.industry_type,
        "metrics_count": len(results),
        "above_median_count": above,
        "below_median_count": len(results) - above,
        "comparisons": results,
    }


@router.post("/api/v1/benchmarks/seed")
async def seed_benchmarks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """初始化行业基准数据（30 条：3 行业 × 10 指标）"""
    svc = KnowledgeRuleService(db)
    result = await svc.seed_benchmarks()
    await db.commit()
    return {**result, "message": "行业基准数据初始化完成"}


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _rule_to_dict(r) -> dict:
    return {
        "id": str(r.id),
        "rule_code": r.rule_code,
        "name": r.name,
        "category": r.category.value if hasattr(r.category, "value") else r.category,
        "rule_type": r.rule_type.value if hasattr(r.rule_type, "value") else r.rule_type,
        "condition": r.condition,
        "conclusion": r.conclusion,
        "base_confidence": r.base_confidence,
        "weight": r.weight,
        "industry_type": r.industry_type,
        "status": r.status.value if hasattr(r.status, "value") else r.status,
        "hit_count": r.hit_count,
        "accuracy_rate": r.accuracy_rate,
        "is_public": r.is_public,
        "tags": r.tags,
        "source": r.source,
    }


def _benchmark_to_dict(b) -> dict:
    return {
        "industry_type": b.industry_type,
        "metric_name": b.metric_name,
        "description": b.description,
        "p25": b.p25_value,
        "p50": b.p50_value,
        "p75": b.p75_value,
        "p90": b.p90_value,
        "unit": b.unit,
        "direction": b.direction,
        "data_source": b.data_source,
        "sample_size": b.sample_size,
    }
