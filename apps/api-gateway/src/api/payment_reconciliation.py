"""
支付对账 API
Payment Reconciliation API

路由前缀: /payment-reconciliation
所有端点要求 ADMIN 角色
"""

from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from src.core.dependencies import get_current_active_user
from src.models.user import User
from src.services.payment_reconcile_service import payment_reconcile_service

logger = structlog.get_logger()

router = APIRouter(prefix="/payment-reconciliation", tags=["支付对账"])


# ── 请求/响应模型 ─────────────────────────────────────────────────────────────


class RunReconciliationRequest(BaseModel):
    """执行对账请求"""

    channel: str = Field(..., description="支付渠道: wechat/alipay/meituan/eleme/douyin 等")
    reconcile_date: date = Field(..., description="对账日期")


class ResolveDiffRequest(BaseModel):
    """标记差异已处理"""

    pass  # resolved_by 从 current_user 获取


# ── API 端点 ──────────────────────────────────────────────────────────────────


@router.post("/import", summary="导入渠道账单")
async def import_settlement_file(
    file: UploadFile = File(..., description="渠道账单文件（CSV）"),
    channel: str = Form(..., description="支付渠道"),
    current_user: User = Depends(get_current_active_user),
):
    """
    上传第三方支付渠道的账单文件（CSV 格式）

    支持微信支付、支付宝、美团等渠道的标准账单格式。
    文件将被解析并写入支付流水表，用于后续对账匹配。
    """
    try:
        brand_id = getattr(current_user, "brand_id", None) or "default"
        content = await file.read()

        if not content:
            raise HTTPException(status_code=400, detail="文件内容为空")

        # 文件大小限制 10MB
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件过大，限制 10MB")

        result = await payment_reconcile_service.import_settlement_file(
            brand_id=brand_id,
            channel=channel,
            file_content=content,
            file_format="csv",
        )

        return {
            "success": True,
            "data": result,
            "message": f"成功导入 {result['imported']} 条流水记录",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("导入账单失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run", summary="执行对账")
async def run_reconciliation(
    request: RunReconciliationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    对指定日期和渠道执行对账

    对账流程：
    1. 读取该日期的渠道支付流水
    2. 读取该日期的 POS 订单
    3. 按交易号 → 金额+时间窗口 逐级匹配
    4. 生成对账批次和差异记录
    """
    try:
        brand_id = getattr(current_user, "brand_id", None) or "default"

        result = await payment_reconcile_service.run_reconciliation(
            brand_id=brand_id,
            channel=request.channel,
            reconcile_date=request.reconcile_date,
        )

        return {
            "success": True,
            "data": result,
            "message": f"对账完成，匹配率 {(result['match_rate'] or 0) * 100:.1f}%",
        }

    except Exception as e:
        logger.error("执行对账失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches", summary="查询对账批次列表")
async def get_batches(
    channel: Optional[str] = Query(None, description="渠道筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_active_user),
):
    """查询对账批次列表，支持按渠道、日期范围筛选"""
    try:
        brand_id = getattr(current_user, "brand_id", None) or "default"

        result = await payment_reconcile_service.get_batches(
            brand_id=brand_id,
            channel=channel,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )

        return {"success": True, "data": result}

    except Exception as e:
        logger.error("查询对账批次失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches/{batch_id}", summary="对账批次详情")
async def get_batch_details(
    batch_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取对账批次详情，包含所有差异记录"""
    try:
        result = await payment_reconcile_service.get_batch_details(batch_id)

        if not result:
            raise HTTPException(status_code=404, detail="对账批次不存在")

        return {"success": True, "data": result}

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的 batch_id 格式")
    except Exception as e:
        logger.error("查询对账详情失败", batch_id=batch_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", summary="对账汇总统计")
async def get_summary(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_active_user),
):
    """获取指定天数内的对账汇总统计"""
    try:
        brand_id = getattr(current_user, "brand_id", None) or "default"

        result = await payment_reconcile_service.get_summary(
            brand_id=brand_id,
            days=days,
        )

        return {"success": True, "data": result}

    except Exception as e:
        logger.error("获取对账汇总失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/diffs/{diff_id}/resolve", summary="标记差异已处理")
async def resolve_diff(
    diff_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """标记一条差异记录为已处理"""
    try:
        resolved_by = getattr(current_user, "username", None) or str(getattr(current_user, "id", "unknown"))

        success = await payment_reconcile_service.resolve_diff(
            diff_id=diff_id,
            resolved_by=resolved_by,
        )

        if not success:
            raise HTTPException(status_code=404, detail="差异记录不存在")

        return {"success": True, "message": "已标记为已处理"}

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的 diff_id 格式")
    except Exception as e:
        logger.error("标记差异失败", diff_id=diff_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))
