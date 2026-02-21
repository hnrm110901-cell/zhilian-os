"""
Reconciliation API
对账管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
import structlog
import uuid

from src.core.dependencies import get_current_active_user
from src.services.reconcile_service import reconcile_service
from src.models.reconciliation import ReconciliationStatus
from src.models.user import User

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class PerformReconciliationRequest(BaseModel):
    """执行对账请求"""
    reconciliation_date: Optional[date] = Field(None, description="对账日期（默认昨天）")
    threshold: Optional[float] = Field(None, description="差异阈值百分比（默认2%）", ge=0, le=100)


class ConfirmReconciliationRequest(BaseModel):
    """确认对账请求"""
    resolution: Optional[str] = Field(None, description="解决方案说明")


class ReconciliationRecordResponse(BaseModel):
    """对账记录响应"""
    id: str
    store_id: str
    reconciliation_date: date
    pos_total_amount: int
    pos_order_count: int
    pos_transaction_count: int
    actual_total_amount: int
    actual_order_count: int
    actual_transaction_count: int
    diff_amount: int
    diff_ratio: float
    diff_order_count: int
    diff_transaction_count: int
    status: ReconciliationStatus
    discrepancies: Optional[list]
    notes: Optional[str]
    confirmed_by: Optional[str]
    confirmed_at: Optional[str]
    resolution: Optional[str]
    alert_sent: str
    alert_sent_at: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== API Endpoints ====================


@router.post("/reconciliation/perform", response_model=dict, summary="执行对账")
async def perform_reconciliation(
    request: PerformReconciliationRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    执行对账操作

    - **reconciliation_date**: 对账日期（可选，默认昨天）
    - **threshold**: 差异阈值百分比（可选，默认2%）

    对账流程：
    1. 获取POS数据和实际订单数据
    2. 计算金额、订单数、交易笔数的差异
    3. 如果差异超过阈值，触发预警通知
    """
    try:
        record = await reconcile_service.perform_reconciliation(
            store_id=current_user.store_id,
            reconciliation_date=request.reconciliation_date,
            threshold=request.threshold
        )

        return {
            "success": True,
            "data": ReconciliationRecordResponse.model_validate(record).model_dump(),
            "message": "对账完成"
        }

    except Exception as e:
        logger.error("执行对账失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation/records", response_model=dict, summary="查询对账记录")
async def get_reconciliation_records(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    status: Optional[ReconciliationStatus] = Query(None, description="对账状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_active_user)
):
    """
    查询对账记录列表

    支持按日期范围、状态筛选
    支持分页查询
    """
    try:
        result = await reconcile_service.query_reconciliation_records(
            store_id=current_user.store_id,
            start_date=start_date,
            end_date=end_date,
            status=status,
            page=page,
            page_size=page_size
        )

        # 转换记录列表
        records_data = [
            ReconciliationRecordResponse.model_validate(record).model_dump()
            for record in result["records"]
        ]

        return {
            "success": True,
            "data": {
                "records": records_data,
                "pagination": {
                    "total": result["total"],
                    "page": result["page"],
                    "page_size": result["page_size"],
                    "total_pages": result["total_pages"]
                }
            }
        }

    except Exception as e:
        logger.error("查询对账记录失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation/records/{record_id}", response_model=dict, summary="获取对账记录详情")
async def get_reconciliation_record(
    record_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """获取指定对账记录的详细信息"""
    try:
        # 转换record_id
        try:
            record_uuid = uuid.UUID(record_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的record_id格式")

        # 这里简化处理，实际应该通过service获取
        # 暂时返回错误，提示需要实现
        raise HTTPException(status_code=501, detail="功能开发中")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取对账记录详情失败", record_id=record_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation/date/{reconciliation_date}", response_model=dict, summary="获取指定日期的对账记录")
async def get_reconciliation_by_date(
    reconciliation_date: date,
    current_user: User = Depends(get_current_active_user)
):
    """获取指定日期的对账记录"""
    try:
        record = await reconcile_service.get_reconciliation_record(
            store_id=current_user.store_id,
            reconciliation_date=reconciliation_date
        )

        if not record:
            raise HTTPException(status_code=404, detail="对账记录不存在")

        return {
            "success": True,
            "data": ReconciliationRecordResponse.model_validate(record).model_dump()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取对账记录失败", reconciliation_date=str(reconciliation_date), error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/reconciliation/records/{record_id}/confirm", response_model=dict, summary="确认对账记录")
async def confirm_reconciliation(
    record_id: str,
    request: ConfirmReconciliationRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    确认对账记录

    用于店长或财务确认差异已核查处理
    """
    try:
        # 转换record_id
        try:
            record_uuid = uuid.UUID(record_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的record_id格式")

        success = await reconcile_service.confirm_reconciliation(
            record_id=record_uuid,
            user_id=current_user.id,
            resolution=request.resolution
        )

        if not success:
            raise HTTPException(status_code=404, detail="对账记录不存在")

        return {
            "success": True,
            "message": "对账记录已确认"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("确认对账记录失败", record_id=record_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation/summary", response_model=dict, summary="获取对账汇总")
async def get_reconciliation_summary(
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取对账汇总统计

    返回最近N天的对账情况汇总
    """
    try:
        # 简化实现，返回基本统计
        # 实际应该从数据库聚合统计
        return {
            "success": True,
            "data": {
                "total_records": 0,
                "matched_count": 0,
                "mismatched_count": 0,
                "pending_count": 0,
                "total_diff_amount": 0,
                "avg_diff_ratio": 0.0
            },
            "message": "功能开发中"
        }

    except Exception as e:
        logger.error("获取对账汇总失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))
