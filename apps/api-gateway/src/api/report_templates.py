"""
自定义报表模板 API
支持报表模板 CRUD、按模板生成报表、定时订阅管理
"""
from typing import Any, Dict, List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.core.dependencies import get_current_active_user
from src.models import User
from src.services.custom_report_service import custom_report_service, DATA_SOURCE_FIELDS

router = APIRouter()


# ------------------------------------------------------------------ #
# Pydantic 模型                                                        #
# ------------------------------------------------------------------ #

class ColumnDef(BaseModel):
    field: str
    label: str


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    data_source: str = Field(..., description="数据源: transactions/inventory/orders/kpi")
    columns: List[ColumnDef] = Field(..., description="要展示的字段列表")
    filters: Optional[Dict[str, Any]] = None
    sort_by: Optional[List[Dict[str, str]]] = None
    default_format: str = Field("xlsx", description="默认导出格式: csv/xlsx")
    is_public: bool = False


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    columns: Optional[List[ColumnDef]] = None
    filters: Optional[Dict[str, Any]] = None
    sort_by: Optional[List[Dict[str, str]]] = None
    default_format: Optional[str] = None
    is_public: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    data_source: str
    columns: List[Dict]
    filters: Optional[Dict]
    sort_by: Optional[List]
    default_format: str
    is_public: bool
    created_by: str
    store_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class ScheduledReportCreateRequest(BaseModel):
    template_id: str
    frequency: str = Field(..., description="频率: daily/weekly/monthly")
    run_at: str = Field("06:00", description="执行时间 HH:MM（UTC）")
    channels: List[str] = Field(..., description="推送渠道: system/email")
    format: str = Field("xlsx", description="导出格式: csv/xlsx")
    recipients: Optional[List[str]] = None
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="周几执行（0=周一，weekly时有效）")
    day_of_month: Optional[int] = Field(None, ge=1, le=28, description="几号执行（monthly时有效）")


class ScheduledReportUpdateRequest(BaseModel):
    frequency: Optional[str] = None
    run_at: Optional[str] = None
    channels: Optional[List[str]] = None
    format: Optional[str] = None
    recipients: Optional[List[str]] = None
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    day_of_month: Optional[int] = Field(None, ge=1, le=28)
    is_active: Optional[bool] = None


# ------------------------------------------------------------------ #
# 数据源元数据                                                          #
# ------------------------------------------------------------------ #

@router.get("/report-templates/data-sources")
async def get_data_sources(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取所有支持的数据源及其可用字段

    用于前端构建报表模板时的字段选择器。
    """
    return {
        "data_sources": [
            {"source": source, "fields": fields}
            for source, fields in DATA_SOURCE_FIELDS.items()
        ]
    }


# ------------------------------------------------------------------ #
# 报表模板 CRUD                                                        #
# ------------------------------------------------------------------ #

@router.get("/report-templates", response_model=List[TemplateResponse])
async def list_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取报表模板列表（自己创建的 + 公开模板）
    """
    templates, total = await custom_report_service.list_templates(
        user_id=str(current_user.id),
        store_id=current_user.store_id,
        skip=skip,
        limit=limit,
    )
    return [TemplateResponse(**t.to_dict()) for t in templates]


@router.post("/report-templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    request: TemplateCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    创建报表模板

    示例（财务交易报表）：
    ```json
    {
      "name": "月度收入明细",
      "data_source": "transactions",
      "columns": [
        {"field": "transaction_date", "label": "日期"},
        {"field": "category", "label": "分类"},
        {"field": "amount", "label": "金额（元）"}
      ],
      "filters": {"transaction_type": "income"},
      "default_format": "xlsx"
    }
    ```
    """
    try:
        template = await custom_report_service.create_template(
            name=request.name,
            data_source=request.data_source,
            columns=[c.model_dump() for c in request.columns],
            user_id=str(current_user.id),
            description=request.description,
            filters=request.filters,
            sort_by=request.sort_by,
            default_format=request.default_format,
            is_public=request.is_public,
            store_id=current_user.store_id,
        )
        return TemplateResponse(**template.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/report-templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """获取单个报表模板"""
    template = await custom_report_service.get_template(template_id, str(current_user.id))
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权限访问")
    return TemplateResponse(**template.to_dict())


@router.put("/report-templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    request: TemplateUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """更新报表模板（只有创建者可以修改）"""
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    if "columns" in update_data:
        update_data["columns"] = [c.model_dump() if hasattr(c, "model_dump") else c for c in update_data["columns"]]

    template = await custom_report_service.update_template(
        template_id=template_id,
        user_id=str(current_user.id),
        **update_data,
    )
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在或无权限修改")
    return TemplateResponse(**template.to_dict())


@router.delete("/report-templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """删除报表模板（只有创建者可以删除）"""
    success = await custom_report_service.delete_template(template_id, str(current_user.id))
    if not success:
        raise HTTPException(status_code=404, detail="模板不存在或无权限删除")
    return {"success": True, "message": "模板已删除"}


# ------------------------------------------------------------------ #
# 报表生成                                                              #
# ------------------------------------------------------------------ #

@router.get("/report-templates/{template_id}/generate")
async def generate_report(
    template_id: str,
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    store_id: Optional[str] = Query(None, description="门店ID（覆盖模板默认值）"),
    format: Optional[str] = Query(None, description="导出格式: csv/xlsx（覆盖模板默认值）"),
    current_user: User = Depends(get_current_active_user),
):
    """
    按模板生成并下载报表

    - 日期范围、门店、格式均可在请求时覆盖模板默认值
    - 返回文件下载响应
    """
    try:
        content, filename, media_type = await custom_report_service.generate_report(
            template_id=template_id,
            user_id=str(current_user.id),
            start_date=start_date,
            end_date=end_date,
            store_id=store_id or current_user.store_id,
            fmt=format,
        )
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))


# ------------------------------------------------------------------ #
# 定时报表订阅                                                          #
# ------------------------------------------------------------------ #

@router.get("/scheduled-reports")
async def list_scheduled_reports(
    current_user: User = Depends(get_current_active_user),
):
    """获取当前用户的定时报表订阅列表"""
    reports = await custom_report_service.list_scheduled_reports(str(current_user.id))
    return {"reports": [r.to_dict() for r in reports], "total": len(reports)}


@router.post("/scheduled-reports", status_code=201)
async def create_scheduled_report(
    request: ScheduledReportCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    创建定时报表订阅

    示例（每天早上 8 点通过系统通知推送）：
    ```json
    {
      "template_id": "...",
      "frequency": "daily",
      "run_at": "08:00",
      "channels": ["system"],
      "format": "xlsx"
    }
    ```
    """
    try:
        sr = await custom_report_service.create_scheduled_report(
            template_id=request.template_id,
            user_id=str(current_user.id),
            frequency=request.frequency,
            run_at=request.run_at,
            channels=request.channels,
            fmt=request.format,
            recipients=request.recipients,
            day_of_week=request.day_of_week,
            day_of_month=request.day_of_month,
        )
        return sr.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/scheduled-reports/{scheduled_id}")
async def update_scheduled_report(
    scheduled_id: str,
    request: ScheduledReportUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """更新定时报表订阅"""
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    sr = await custom_report_service.update_scheduled_report(
        scheduled_id=scheduled_id,
        user_id=str(current_user.id),
        **update_data,
    )
    if not sr:
        raise HTTPException(status_code=404, detail="订阅不存在或无权限修改")
    return sr.to_dict()


@router.delete("/scheduled-reports/{scheduled_id}")
async def delete_scheduled_report(
    scheduled_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """删除定时报表订阅"""
    success = await custom_report_service.delete_scheduled_report(scheduled_id, str(current_user.id))
    if not success:
        raise HTTPException(status_code=404, detail="订阅不存在或无权限删除")
    return {"success": True, "message": "订阅已删除"}
