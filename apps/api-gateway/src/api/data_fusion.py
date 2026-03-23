"""
数据融合引擎 REST API

端点：
  POST   /api/v1/data-fusion/projects              创建融合项目
  GET    /api/v1/data-fusion/projects               列出融合项目
  GET    /api/v1/data-fusion/projects/{project_id}  查看项目详情+进度
  POST   /api/v1/data-fusion/projects/{project_id}/start  启动项目
  POST   /api/v1/data-fusion/tasks/{task_id}/retry  重试失败任务
  POST   /api/v1/data-fusion/backfill/csv           CSV文件导入
  GET    /api/v1/data-fusion/health-report/{store_id}  获取经营体检报告
  GET    /api/v1/data-fusion/bff/hq/{brand_id}      总部融合驾驶舱BFF
"""

from datetime import date, datetime
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.services.data_fusion_engine import DataFusionEngine
from src.services.entity_resolver import EntityResolver
from src.services.historical_backfill import HistoricalBackfill
from src.services.knowledge_generator import KnowledgeGenerator
from src.services.timeline_assembler import TimelineAssembler

router = APIRouter(prefix="/api/v1/data-fusion", tags=["data-fusion"])
logger = structlog.get_logger()

# ── 单例（生产环境应由 DI 容器管理） ─────────────────────────────────────────

_engine = DataFusionEngine()
_resolver = EntityResolver()
_backfill = HistoricalBackfill(entity_resolver=_resolver)
_knowledge = KnowledgeGenerator()
_timeline = TimelineAssembler()


# ── 请求/响应模型 ─────────────────────────────────────────────────────────────

class SourceSystemIn(BaseModel):
    system_type: str = Field(..., description="来源系统标识，如 pinzhi/tiancai")
    category: str = Field("pos", description="系统类别: pos/reservation/member/supplier/finance")
    channel: str = Field("api", description="数据采集通道: api/file/db_mirror")
    config: Dict = Field(default_factory=dict)
    priority: int = Field(0)


class CreateProjectIn(BaseModel):
    brand_id: str = Field(..., description="品牌ID")
    name: str = Field(..., description="项目名称")
    source_systems: List[SourceSystemIn]
    store_ids: Optional[List[str]] = Field(None, description="门店ID列表")
    entity_types: Optional[List[str]] = Field(None, description="要融合的实体类型")
    date_range_start: Optional[date] = Field(None, description="历史数据回溯起点")
    date_range_end: Optional[date] = Field(None, description="数据截止日期")


class CsvBackfillIn(BaseModel):
    task_id: str = Field("manual", description="关联的融合任务ID")
    entity_type: str = Field(..., description="实体类型: dish/customer/ingredient/order")
    source_system: str = Field(..., description="来源系统标识")
    csv_content: str = Field(..., description="CSV文本内容")
    id_field: str = Field("id", description="CSV中的ID列名")
    name_field: str = Field("name", description="CSV中的名称列名")


# ── 项目管理端点 ──────────────────────────────────────────────────────────────

@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(body: CreateProjectIn):
    """创建融合项目并自动拆分任务"""
    plan = _engine.create_project(
        brand_id=body.brand_id,
        name=body.name,
        source_systems=[s.model_dump() for s in body.source_systems],
        store_ids=body.store_ids,
        entity_types=body.entity_types,
        date_range_start=body.date_range_start,
        date_range_end=body.date_range_end,
    )
    return {
        "project_id": plan.project_id,
        "name": plan.project_name,
        "total_tasks": plan.total_tasks,
        "entity_types": plan.entity_types,
        "tasks": [
            {
                "id": t["id"],
                "source_system": t["source_system"],
                "entity_type": t["entity_type"],
                "channel": t["channel"],
                "priority": t["priority"],
            }
            for t in plan.tasks
        ],
    }


@router.get("/projects")
async def list_projects(
    brand_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """列出融合项目"""
    projects = []
    for pid, proj in _engine._projects.items():
        if brand_id and proj.get("brand_id") != brand_id:
            continue
        if status_filter and proj.get("status") != status_filter:
            continue
        projects.append({
            "id": pid,
            "name": proj.get("name"),
            "brand_id": proj.get("brand_id"),
            "status": proj.get("status"),
            "total_tasks": proj.get("total_tasks"),
            "completed_tasks": proj.get("completed_tasks"),
            "total_records_imported": proj.get("total_records_imported"),
            "created_at": proj.get("created_at"),
        })
    return {"items": projects, "total": len(projects)}


@router.get("/projects/{project_id}")
async def get_project_progress(project_id: str):
    """查看项目详情和实时进度"""
    progress = _engine.get_project_progress(project_id)
    if not progress:
        raise HTTPException(status_code=404, detail="融合项目不存在")
    return {
        "project_id": progress.project_id,
        "status": progress.status,
        "progress_pct": progress.progress_pct,
        "total_tasks": progress.total_tasks,
        "completed_tasks": progress.completed_tasks,
        "running_tasks": progress.running_tasks,
        "failed_tasks": progress.failed_tasks,
        "total_records_imported": progress.total_records_imported,
        "total_entities_resolved": progress.total_entities_resolved,
        "total_conflicts": progress.total_conflicts,
        "knowledge_generated": progress.knowledge_generated,
        "health_report_generated": progress.health_report_generated,
        "tasks": [
            {
                "task_id": t.task_id,
                "status": t.status,
                "progress_pct": t.progress_pct,
                "processed_count": t.processed_count,
                "success_count": t.success_count,
                "error_count": t.error_count,
                "last_error": t.last_error,
            }
            for t in progress.tasks
        ],
    }


@router.post("/projects/{project_id}/start")
async def start_project(project_id: str):
    """启动融合项目（获取下一批待执行任务）"""
    next_tasks = _engine.get_next_tasks(project_id, limit=5)
    if not next_tasks:
        return {"message": "没有待执行的任务", "tasks": []}
    return {
        "message": f"返回 {len(next_tasks)} 个待执行任务",
        "tasks": [
            {
                "id": t["id"],
                "source_system": t["source_system"],
                "entity_type": t["entity_type"],
                "channel": t["channel"],
                "priority": t["priority"],
                "date_range_start": str(t.get("date_range_start", "")),
                "date_range_end": str(t.get("date_range_end", "")),
            }
            for t in next_tasks
        ],
    }


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    """重试失败的任务（从断点续传）"""
    success = _engine.retry_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="任务不存在或状态不允许重试")
    return {"message": "任务已重新加入队列", "task_id": task_id}


# ── 数据导入端点 ──────────────────────────────────────────────────────────────

@router.post("/backfill/csv")
async def backfill_from_csv(body: CsvBackfillIn):
    """从CSV内容批量导入"""
    result = _backfill.backfill_from_csv(
        task_id=body.task_id,
        entity_type=body.entity_type,
        source_system=body.source_system,
        csv_content=body.csv_content,
        id_field=body.id_field,
        name_field=body.name_field,
    )
    return {
        "status": result.status,
        "processed_count": result.processed_count,
        "success_count": result.success_count,
        "error_count": result.error_count,
        "duplicate_count": result.duplicate_count,
        "errors": result.errors[:10],  # 最多返回10条错误
    }


# ── 经营体检报告端点 ──────────────────────────────────────────────────────────

@router.get("/health-report/{store_id}")
async def get_health_report(
    store_id: str,
    brand_id: str = Query(..., description="品牌ID"),
):
    """
    获取经营体检报告

    基于历史融合数据生成6维分析报告：
    营收健康度 / 成本真相 / 菜品表现 / 会员资产 / 人效分析 / 供应商评估
    """
    report = _knowledge.generate_health_report(
        store_id=store_id,
        brand_id=brand_id,
        timeline=None,  # 从DB加载时间线（当前为演示模式）
        orders=None,
        dishes=None,
        customers=None,
        employees=None,
        suppliers=None,
    )
    return {
        "store_id": report.store_id,
        "brand_id": report.brand_id,
        "report_date": report.report_date,
        "data_period": report.data_period,
        "overall_health_score": report.overall_health_score,
        "revenue_summary": report.revenue_summary,
        "cost_summary": report.cost_summary,
        "dish_quadrant_summary": report.dish_quadrant_summary,
        "customer_summary": report.customer_summary,
        "staff_efficiency": {
            "total_employees": report.staff_efficiency.total_employees,
            "revenue_per_person_per_hour_yuan": round(
                report.staff_efficiency.revenue_per_person_per_hour_fen / 100, 2
            ),
            "peak_hour_gap": report.staff_efficiency.peak_hour_gap,
            "recommendation": report.staff_efficiency.recommendation,
        } if report.staff_efficiency else None,
        "ai_recommendations": report.ai_recommendations,
    }


# ── BFF 驾驶舱 ───────────────────────────────────────────────────────────────

@router.get("/bff/hq/{brand_id}")
async def bff_hq_fusion_dashboard(brand_id: str):
    """
    总部数据融合驾驶舱 BFF

    一次请求返回：
    - 融合项目概览（进行中/已完成）
    - 各门店数据接入状态
    - 知识库生成进度
    - 最新体检报告摘要
    """
    # 汇总项目状态
    projects = []
    total_imported = 0
    total_resolved = 0
    total_conflicts = 0

    for pid, proj in _engine._projects.items():
        if proj.get("brand_id") != brand_id:
            continue
        projects.append({
            "id": pid,
            "name": proj.get("name"),
            "status": proj.get("status"),
            "progress_pct": round(
                proj.get("completed_tasks", 0) / max(proj.get("total_tasks", 1), 1) * 100,
                1,
            ),
            "total_records_imported": proj.get("total_records_imported", 0),
            "knowledge_generated": proj.get("knowledge_generated", False),
        })
        total_imported += proj.get("total_records_imported", 0)
        total_resolved += proj.get("total_entities_resolved", 0)
        total_conflicts += proj.get("total_conflicts", 0)

    return {
        "brand_id": brand_id,
        "summary": {
            "total_projects": len(projects),
            "active_projects": sum(1 for p in projects if p["status"] not in ("completed", "failed")),
            "total_records_imported": total_imported,
            "total_entities_resolved": total_resolved,
            "total_conflicts_pending": total_conflicts,
        },
        "projects": projects,
    }
