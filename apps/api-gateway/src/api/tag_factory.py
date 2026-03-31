"""
标签工厂 API — Phase 3

标签规则的 CRUD、预览、会员标签查询与批量重评估。

路由：
  GET    /api/v1/brand/{brand_id}/tags/rules            列出标签规则
  POST   /api/v1/brand/{brand_id}/tags/rules            创建规则
  PUT    /api/v1/brand/{brand_id}/tags/rules/{rule_id}  更新规则
  DELETE /api/v1/brand/{brand_id}/tags/rules/{rule_id}  停用规则
  POST   /api/v1/brand/{brand_id}/tags/rules/preview    预览命中人数
  GET    /api/v1/consumer/{consumer_id}/tags            查询会员当前标签
  POST   /api/v1/brand/{brand_id}/tags/batch-evaluate   触发批量重评估
"""

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User
from ..services.tag_factory_service import (
    ConditionValidationError,
    SUPPORTED_CONDITIONS,
    VALID_LOGIC,
    tag_factory_service,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / Response 模型
# --------------------------------------------------------------------------- #

class ConditionSchema(BaseModel):
    field: str = Field(..., description=f"条件字段，合法值: {list(SUPPORTED_CONDITIONS)}")
    op: str = Field(..., description="操作符，如 gt / gte / lt / in / within 等")
    value: Any = Field(..., description="阈值（整数、字符串列表或天数）")

    @validator("field")
    def field_must_be_supported(cls, v: str) -> str:
        if v not in SUPPORTED_CONDITIONS:
            raise ValueError(f"不支持的字段: {v!r}，合法字段: {list(SUPPORTED_CONDITIONS)}")
        return v

    @validator("op")
    def op_must_match_field(cls, v: str, values: dict) -> str:
        field = values.get("field")
        if field and field in SUPPORTED_CONDITIONS:
            allowed_ops = SUPPORTED_CONDITIONS[field]["ops"]
            if v not in allowed_ops:
                raise ValueError(f"字段 {field!r} 不支持操作符 {v!r}，合法: {allowed_ops}")
        return v


class CreateRuleRequest(BaseModel):
    tag_name: str = Field(..., min_length=1, max_length=100, description="标签名称，如"高价值客户"")
    tag_code: str = Field(..., min_length=1, max_length=50, description="标签代码，如 high_value（唯一）")
    conditions: List[ConditionSchema] = Field(..., description="规则条件列表")
    logic: str = Field(default="AND", description="条件组合逻辑：AND 或 OR")
    priority: int = Field(default=100, ge=0, le=9999, description="优先级，越大越优先")
    is_active: bool = Field(default=True)

    @validator("logic")
    def logic_must_be_valid(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in VALID_LOGIC:
            raise ValueError(f"logic 必须是 AND 或 OR，当前: {v!r}")
        return v_upper


class UpdateRuleRequest(BaseModel):
    tag_name: Optional[str] = Field(None, min_length=1, max_length=100)
    tag_code: Optional[str] = Field(None, min_length=1, max_length=50)
    conditions: Optional[List[ConditionSchema]] = None
    logic: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0, le=9999)
    is_active: Optional[bool] = None

    @validator("logic")
    def logic_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v_upper = v.upper()
        if v_upper not in VALID_LOGIC:
            raise ValueError(f"logic 必须是 AND 或 OR，当前: {v!r}")
        return v_upper


class PreviewRuleRequest(BaseModel):
    conditions: List[ConditionSchema]
    logic: str = Field(default="AND")
    limit: int = Field(default=100, ge=1, le=500)

    @validator("logic")
    def logic_must_be_valid(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in VALID_LOGIC:
            raise ValueError(f"logic 必须是 AND 或 OR，当前: {v!r}")
        return v_upper


class BatchEvaluateRequest(BaseModel):
    consumer_ids: List[str] = Field(..., min_items=1, max_items=1000)
    persist: bool = Field(default=True, description="是否将结果写入 consumer_tag_snapshots")


# --------------------------------------------------------------------------- #
# 辅助：从 user 中提取 group_id（按项目约定从 user 属性获取）
# --------------------------------------------------------------------------- #

def _get_group_id(current_user: User) -> str:
    group_id = getattr(current_user, "group_id", None) or getattr(current_user, "store_id", "default")
    return str(group_id)


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #

@router.get("/brand/{brand_id}/tags/rules", summary="列出标签规则")
async def list_tag_rules(
    brand_id: str,
    include_group_rules: bool = Query(default=True, description="是否包含集团通用规则（brand_id='*'）"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """列出指定品牌的所有激活标签规则（含集团通用规则）。"""
    group_id = _get_group_id(current_user)
    rules = await tag_factory_service.list_rules(
        brand_id=brand_id,
        group_id=group_id,
        include_group_rules=include_group_rules,
        session=db,
    )
    return {"brand_id": brand_id, "total": len(rules), "rules": rules}


@router.post("/brand/{brand_id}/tags/rules", summary="创建标签规则")
async def create_tag_rule(
    brand_id: str,
    body: CreateRuleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """创建标签规则，返回 rule_id。tag_code 在同品牌下唯一。"""
    group_id = _get_group_id(current_user)
    try:
        rule_id = await tag_factory_service.create_rule(
            rule_data={
                "tag_name": body.tag_name,
                "tag_code": body.tag_code,
                "conditions": [c.dict() for c in body.conditions],
                "logic": body.logic,
                "priority": body.priority,
                "is_active": body.is_active,
            },
            brand_id=brand_id,
            group_id=group_id,
            created_by=str(getattr(current_user, "id", "unknown")),
            session=db,
        )
        await db.commit()
        return {"rule_id": rule_id, "brand_id": brand_id, "tag_code": body.tag_code}
    except ConditionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("create_tag_rule_failed", brand_id=brand_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="创建规则失败")


@router.put("/brand/{brand_id}/tags/rules/{rule_id}", summary="更新标签规则")
async def update_tag_rule(
    brand_id: str,
    rule_id: str,
    body: UpdateRuleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """更新规则（支持停用 is_active=false / 修改条件 / 改优先级）。"""
    updates = body.dict(exclude_none=True)
    if "conditions" in updates:
        updates["conditions"] = [c.dict() if hasattr(c, "dict") else c for c in (body.conditions or [])]

    try:
        ok = await tag_factory_service.update_rule(rule_id=rule_id, updates=updates, session=db)
        if not ok:
            raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在或无变更")
        await db.commit()
        return {"rule_id": rule_id, "updated": True}
    except ConditionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("update_tag_rule_failed", rule_id=rule_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="更新规则失败")


@router.delete("/brand/{brand_id}/tags/rules/{rule_id}", summary="停用标签规则")
async def deactivate_tag_rule(
    brand_id: str,
    rule_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """软删除：将规则 is_active 置为 False，不物理删除。"""
    try:
        ok = await tag_factory_service.update_rule(
            rule_id=rule_id,
            updates={"is_active": False},
            session=db,
        )
        if not ok:
            raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")
        await db.commit()
        return {"rule_id": rule_id, "is_active": False, "message": "规则已停用"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("deactivate_tag_rule_failed", rule_id=rule_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="停用规则失败")


@router.post("/brand/{brand_id}/tags/rules/preview", summary="预览规则命中人数")
async def preview_tag_rule(
    brand_id: str,
    body: PreviewRuleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    预览：规则将命中多少会员（不实际打标签）。
    基于最多 10000 条档案的估算，返回命中人数 + 命中率 + 样本 consumer_id。
    """
    group_id = _get_group_id(current_user)
    try:
        result = await tag_factory_service.preview_rule(
            conditions=[c.dict() for c in body.conditions],
            logic=body.logic,
            brand_id=brand_id,
            group_id=group_id,
            limit=body.limit,
            session=db,
        )
        return result
    except ConditionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("preview_tag_rule_failed", brand_id=brand_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="预览失败")


@router.get("/consumer/{consumer_id}/tags", summary="查询会员当前标签")
async def get_consumer_tags(
    consumer_id: str,
    brand_id: str = Query(..., description="品牌 ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """查询会员在指定品牌下的当前快照标签（来自 consumer_tag_snapshots）。"""
    result = await tag_factory_service.get_consumer_tags(
        consumer_id=consumer_id,
        brand_id=brand_id,
        session=db,
    )
    return {"consumer_id": consumer_id, "brand_id": brand_id, **result}


@router.post("/brand/{brand_id}/tags/batch-evaluate", summary="触发批量重评估")
async def batch_evaluate_tags(
    brand_id: str,
    body: BatchEvaluateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    对指定会员列表重新评估所有激活规则。
    persist=true 时将结果写入 consumer_tag_snapshots。
    最多支持 1000 个 consumer_id 每次请求。
    """
    group_id = _get_group_id(current_user)
    try:
        tag_map = await tag_factory_service.batch_evaluate_tags(
            brand_id=brand_id,
            group_id=group_id,
            consumer_ids=body.consumer_ids,
            session=db,
        )

        if body.persist:
            for consumer_id, tag_codes in tag_map.items():
                await tag_factory_service.persist_tag_snapshot(
                    consumer_id=consumer_id,
                    brand_id=brand_id,
                    group_id=group_id,
                    tag_codes=tag_codes,
                    session=db,
                )
            await db.commit()

        summary = {cid: tags for cid, tags in tag_map.items()}
        return {
            "brand_id": brand_id,
            "evaluated_count": len(summary),
            "persisted": body.persist,
            "results": summary,
        }
    except Exception as exc:
        logger.error("batch_evaluate_tags_failed", brand_id=brand_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="批量评估失败")
