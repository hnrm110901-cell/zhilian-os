"""
移动盘点 API 路由

Phase 2.2 功能对等模块 — 面向手机/平板的库存盘点接口。
前缀: /api/v1/stocktake
"""

from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.mobile_stocktake_service import (
    StocktakeScope,
    mobile_stocktake_service,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/stocktake", tags=["移动盘点"])


# ============================================================
# 请求/响应模型（Pydantic）
# ============================================================

class CreateStocktakeRequest(BaseModel):
    """创建盘点请求"""
    store_id: str = Field(..., description="门店ID")
    scope: StocktakeScope = Field(..., description="盘点范围: full/partial/spot_check")
    created_by: str = Field("", description="创建人ID")
    category: str = Field("", description="类别（scope=partial时必填）")


class CountRequest(BaseModel):
    """单项盘点录入请求"""
    ingredient_id: str = Field(..., description="食材ID")
    ingredient_name: str = Field(..., description="食材名称")
    system_qty: float = Field(..., ge=0, description="系统库存数量")
    counted_qty: float = Field(..., ge=0, description="实盘数量")
    unit: str = Field("kg", description="单位")
    unit_cost_fen: int = Field(0, ge=0, description="单位成本（分）")
    location: str = Field("", description="存放位置")
    note: str = Field("", description="备注")


class BatchCountRequest(BaseModel):
    """批量盘点录入请求"""
    counts: List[CountRequest] = Field(..., min_length=1, description="盘点明细列表")


class ApproveRequest(BaseModel):
    """审批请求"""
    approver_id: str = Field(..., description="审批人ID")


class RejectRequest(BaseModel):
    """驳回请求"""
    reason: str = Field(..., min_length=1, description="驳回原因")


class CountRecordResponse(BaseModel):
    """盘点记录响应"""
    record_id: str
    ingredient_id: str
    ingredient_name: str
    system_qty: float
    counted_qty: float
    unit: str
    variance: float
    variance_rate: float
    unit_cost_fen: int
    variance_fen: int
    variance_yuan: str              # ¥金额（元，展示用）
    location: str
    note: str
    needs_investigation: bool
    counted_at: str


class StocktakeResponse(BaseModel):
    """盘点会话响应"""
    stocktake_id: str
    store_id: str
    scope: str
    status: str
    category: str
    record_count: int
    created_by: str
    created_at: str
    submitted_at: str
    approved_by: str
    approved_at: str


class BatchResultResponse(BaseModel):
    """批量录入结果响应"""
    stocktake_id: str
    success_count: int
    failed_count: int
    failures: List[dict]


class VarianceItemResponse(BaseModel):
    """差异明细响应"""
    ingredient_id: str
    ingredient_name: str
    system_qty: float
    counted_qty: float
    unit: str
    variance: float
    variance_rate: float
    variance_fen: int
    variance_yuan: str
    needs_investigation: bool


class VarianceReportResponse(BaseModel):
    """差异报告响应"""
    stocktake_id: str
    store_id: str
    total_items: int
    matched_items: int
    variance_items: int
    investigation_items: int
    total_variance_fen: int
    total_variance_yuan: str
    items: List[VarianceItemResponse]


class VarianceSummaryResponse(BaseModel):
    """差异摘要响应"""
    stocktake_id: str
    store_id: str
    total_items: int
    variance_items: int
    investigation_items: int
    total_variance_fen: int
    total_variance_yuan: str        # ¥金额展示
    positive_variance_fen: int      # 盘盈
    positive_variance_yuan: str
    negative_variance_fen: int      # 盘亏
    negative_variance_yuan: str
    top_losses: List[dict]


# ============================================================
# 辅助函数
# ============================================================

def _fen_to_yuan(fen: int) -> str:
    """分转元，保留2位小数，带¥前缀"""
    return f"¥{fen / 100:.2f}"


def _stocktake_to_response(stocktake) -> StocktakeResponse:
    """将服务层Stocktake转换为API响应"""
    return StocktakeResponse(
        stocktake_id=stocktake.stocktake_id,
        store_id=stocktake.store_id,
        scope=stocktake.scope.value,
        status=stocktake.status.value,
        category=stocktake.category,
        record_count=len(stocktake.records),
        created_by=stocktake.created_by,
        created_at=stocktake.created_at,
        submitted_at=stocktake.submitted_at,
        approved_by=stocktake.approved_by,
        approved_at=stocktake.approved_at,
    )


def _record_to_response(record) -> CountRecordResponse:
    """将盘点记录转换为API响应"""
    return CountRecordResponse(
        record_id=record.record_id,
        ingredient_id=record.ingredient_id,
        ingredient_name=record.ingredient_name,
        system_qty=record.system_qty,
        counted_qty=record.counted_qty,
        unit=record.unit,
        variance=record.variance,
        variance_rate=record.variance_rate,
        unit_cost_fen=record.unit_cost_fen,
        variance_fen=record.variance_fen,
        variance_yuan=_fen_to_yuan(record.variance_fen),
        location=record.location,
        note=record.note,
        needs_investigation=record.needs_investigation,
        counted_at=record.counted_at,
    )


# ============================================================
# API 路由
# ============================================================

@router.post("/sessions", summary="创建盘点会话")
async def create_stocktake(req: CreateStocktakeRequest):
    """
    创建盘点会话

    scope 说明：
    - full: 全盘（所有食材）
    - partial: 分类盘（需指定 category）
    - spot_check: 抽盘（随机20%品项）
    """
    try:
        stocktake = mobile_stocktake_service.create_stocktake(
            store_id=req.store_id,
            scope=req.scope,
            created_by=req.created_by,
            category=req.category,
        )
        return {"success": True, "data": _stocktake_to_response(stocktake)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("stocktake.create_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{stocktake_id}/count", summary="录入盘点")
async def add_count(stocktake_id: str, req: CountRequest):
    """录入单个品项的实盘数量"""
    try:
        record = mobile_stocktake_service.add_count(
            stocktake_id=stocktake_id,
            ingredient_id=req.ingredient_id,
            ingredient_name=req.ingredient_name,
            system_qty=req.system_qty,
            counted_qty=req.counted_qty,
            unit=req.unit,
            unit_cost_fen=req.unit_cost_fen,
            location=req.location,
            note=req.note,
        )
        return {"success": True, "data": _record_to_response(record)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("stocktake.count_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{stocktake_id}/batch-count", summary="批量录入盘点")
async def batch_count(stocktake_id: str, req: BatchCountRequest):
    """批量录入多个品项的实盘数量（部分失败不影响其他品项）"""
    try:
        counts_data = [
            {
                "ingredient_id": c.ingredient_id,
                "ingredient_name": c.ingredient_name,
                "system_qty": c.system_qty,
                "counted_qty": c.counted_qty,
                "unit": c.unit,
                "unit_cost_fen": c.unit_cost_fen,
                "location": c.location,
                "note": c.note,
            }
            for c in req.counts
        ]
        result = mobile_stocktake_service.batch_count(stocktake_id, counts_data)
        return {
            "success": True,
            "data": BatchResultResponse(
                stocktake_id=result.stocktake_id,
                success_count=result.success_count,
                failed_count=result.failed_count,
                failures=result.failures,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("stocktake.batch_count_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{stocktake_id}/variance", summary="差异报告")
async def get_variance(stocktake_id: str):
    """获取盘点差异报告（详细版，含每个品项的差异）"""
    try:
        report = mobile_stocktake_service.calculate_variance(stocktake_id)
        items = [
            VarianceItemResponse(
                ingredient_id=item.ingredient_id,
                ingredient_name=item.ingredient_name,
                system_qty=item.system_qty,
                counted_qty=item.counted_qty,
                unit=item.unit,
                variance=item.variance,
                variance_rate=item.variance_rate,
                variance_fen=item.variance_fen,
                variance_yuan=_fen_to_yuan(item.variance_fen),
                needs_investigation=item.needs_investigation,
            )
            for item in report.items
        ]
        return {
            "success": True,
            "data": VarianceReportResponse(
                stocktake_id=report.stocktake_id,
                store_id=report.store_id,
                total_items=report.total_items,
                matched_items=report.matched_items,
                variance_items=report.variance_items,
                investigation_items=report.investigation_items,
                total_variance_fen=report.total_variance_fen,
                total_variance_yuan=_fen_to_yuan(report.total_variance_fen),
                items=items,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("stocktake.variance_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{stocktake_id}/summary", summary="差异摘要")
async def get_variance_summary(stocktake_id: str):
    """
    获取差异摘要（含¥金额影响）

    包含盘盈/盘亏金额、亏损TOP5等关键指标。
    """
    try:
        summary = mobile_stocktake_service.get_variance_summary(stocktake_id)
        return {
            "success": True,
            "data": VarianceSummaryResponse(
                stocktake_id=summary.stocktake_id,
                store_id=summary.store_id,
                total_items=summary.total_items,
                variance_items=summary.variance_items,
                investigation_items=summary.investigation_items,
                total_variance_fen=summary.total_variance_fen,
                total_variance_yuan=summary.total_variance_yuan,
                positive_variance_fen=summary.positive_variance_fen,
                positive_variance_yuan=_fen_to_yuan(summary.positive_variance_fen),
                negative_variance_fen=summary.negative_variance_fen,
                negative_variance_yuan=_fen_to_yuan(summary.negative_variance_fen),
                top_losses=summary.top_losses,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("stocktake.summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{stocktake_id}/approve", summary="审批通过")
async def approve_stocktake(stocktake_id: str, req: ApproveRequest):
    """审批通过盘点，系统库存将按实盘数量调整"""
    try:
        stocktake = mobile_stocktake_service.approve_stocktake(
            stocktake_id=stocktake_id,
            approver_id=req.approver_id,
        )
        return {"success": True, "data": _stocktake_to_response(stocktake)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("stocktake.approve_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{stocktake_id}/reject", summary="驳回盘点")
async def reject_stocktake(stocktake_id: str, req: RejectRequest):
    """驳回盘点，需提供驳回原因"""
    try:
        stocktake = mobile_stocktake_service.reject_stocktake(
            stocktake_id=stocktake_id,
            reason=req.reason,
        )
        return {"success": True, "data": _stocktake_to_response(stocktake)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("stocktake.reject_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
