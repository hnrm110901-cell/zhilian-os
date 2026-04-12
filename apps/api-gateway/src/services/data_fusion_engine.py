"""
数据融合引擎 — 多源数据采集编排 + 断点续传 + 进度追踪
对标 Palantir Foundry 的 Pipeline Builder

核心能力：
  1. 创建融合项目：定义来源系统 + 数据范围 + 实体类型
  2. 自动拆分任务：按(系统×实体类型)拆分为独立可并行的任务
  3. 编排执行：按优先级调度任务，支持断点续传
  4. 进度追踪：实时统计导入量/成功率/错误率
  5. 知识库生成触发：全部导入完成后自动触发知识生成管道

使用方式：
  engine = DataFusionEngine()
  project = engine.create_project(brand_id, name, source_systems, ...)
  engine.start_project(project_id)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class SourceSystemConfig:
    """来源系统配置"""
    system_type: str          # pinzhi / tiancai / aoqiwei / meituan / keruyun
    category: str             # pos / reservation / member / supplier / finance / delivery
    channel: str = "api"      # api / file / db_mirror / webhook
    config: Dict = field(default_factory=dict)  # 连接配置（API key等）
    priority: int = 0         # 优先级


@dataclass
class ProjectPlan:
    """融合项目规划"""
    project_id: str
    project_name: str
    brand_id: str
    store_ids: List[str]
    source_systems: List[SourceSystemConfig]
    entity_types: List[str]
    date_range_start: Optional[date]
    date_range_end: Optional[date]
    total_tasks: int
    tasks: List[Dict]


@dataclass
class TaskProgress:
    """任务进度"""
    task_id: str
    status: str
    processed_count: int
    success_count: int
    error_count: int
    duplicate_count: int
    total_estimated: Optional[int]
    progress_pct: float        # 0.0 ~ 100.0
    last_cursor: Optional[str]
    last_error: Optional[str]


@dataclass
class ProjectProgress:
    """项目整体进度"""
    project_id: str
    status: str
    total_tasks: int
    completed_tasks: int
    running_tasks: int
    failed_tasks: int
    total_records_imported: int
    total_entities_resolved: int
    total_conflicts: int
    progress_pct: float
    knowledge_generated: bool
    health_report_generated: bool
    tasks: List[TaskProgress]


# ── 融合引擎 ──────────────────────────────────────────────────────────────────

class DataFusionEngine:
    """
    数据融合引擎

    职责：
    1. 项目规划：根据来源系统和实体类型，自动拆分为可并行的任务
    2. 任务调度：按优先级和依赖关系编排执行
    3. 进度管理：实时追踪每个任务的进度
    4. 错误处理：任务失败后可断点续传
    5. 生命周期：项目从 created → scanning → importing → resolving → generating → completed
    """

    # 每个系统类别支持的实体类型
    CATEGORY_ENTITY_MAP = {
        "pos": ["order", "dish", "customer"],
        "reservation": ["order", "customer"],
        "member": ["customer"],
        "supplier": ["supplier", "ingredient"],
        "finance": ["order"],
        "delivery": ["order", "customer", "dish"],
        "hr": ["employee"],
        "inventory": ["ingredient"],
    }

    # 实体类型优先级（先导入基础数据，再导入关联数据）
    ENTITY_PRIORITY = {
        "store": 100,       # 门店最先
        "dish": 90,         # 菜品次之（订单依赖菜品）
        "ingredient": 85,   # 食材（BOM依赖食材）
        "supplier": 80,     # 供应商
        "employee": 75,     # 员工
        "customer": 70,     # 客户
        "order": 50,        # 订单最后（依赖菜品+客户）
    }

    def __init__(self):
        self._projects: Dict[str, Dict] = {}
        self._tasks: Dict[str, Dict] = {}

    def create_project(
        self,
        brand_id: str,
        name: str,
        source_systems: List[Dict],
        store_ids: Optional[List[str]] = None,
        entity_types: Optional[List[str]] = None,
        date_range_start: Optional[date] = None,
        date_range_end: Optional[date] = None,
    ) -> ProjectPlan:
        """
        创建融合项目并自动拆分任务

        Args:
            brand_id: 品牌ID
            name: 项目名称
            source_systems: 来源系统配置列表
            store_ids: 门店ID列表（None表示品牌下所有门店）
            entity_types: 要融合的实体类型（None表示全部）
            date_range_start: 历史数据回溯起点
            date_range_end: 历史数据截止日期

        Returns:
            ProjectPlan 包含项目ID和自动拆分的任务列表
        """
        project_id = str(uuid.uuid4())
        effective_store_ids = store_ids or ["__brand_level__"]
        effective_entity_types = entity_types or ["order", "dish", "customer", "ingredient"]

        # 解析来源系统配置
        systems = []
        for sys_config in source_systems:
            systems.append(SourceSystemConfig(
                system_type=sys_config.get("system_type", ""),
                category=sys_config.get("category", "pos"),
                channel=sys_config.get("channel", "api"),
                config=sys_config.get("config", {}),
                priority=sys_config.get("priority", 0),
            ))

        # 自动拆分任务：每个(门店 × 系统 × 实体类型)组合 = 一个任务
        tasks = []
        for store_id in effective_store_ids:
            for system in systems:
                # 该系统类别支持的实体类型
                supported = self.CATEGORY_ENTITY_MAP.get(system.category, [])
                for etype in effective_entity_types:
                    if etype not in supported:
                        continue
                    task_id = str(uuid.uuid4())
                    priority = self.ENTITY_PRIORITY.get(etype, 0) + system.priority
                    task = {
                        "id": task_id,
                        "project_id": project_id,
                        "brand_id": brand_id,
                        "store_id": store_id if store_id != "__brand_level__" else None,
                        "source_system": system.system_type,
                        "source_category": system.category,
                        "channel": system.channel,
                        "entity_type": etype,
                        "status": "pending",
                        "priority": priority,
                        "date_range_start": date_range_start,
                        "date_range_end": date_range_end,
                        "batch_size": 100,
                        "processed_count": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "duplicate_count": 0,
                    }
                    tasks.append(task)
                    self._tasks[task_id] = task

        # 按优先级排序（高优先级先执行）
        tasks.sort(key=lambda t: t["priority"], reverse=True)

        project = {
            "id": project_id,
            "brand_id": brand_id,
            "name": name,
            "status": "created",
            "source_systems": [
                {"system_type": s.system_type, "category": s.category,
                 "channel": s.channel}
                for s in systems
            ],
            "entity_types": effective_entity_types,
            "total_tasks": len(tasks),
            "completed_tasks": 0,
            "total_records_imported": 0,
            "total_entities_resolved": 0,
            "total_conflicts": 0,
            "knowledge_generated": False,
            "health_report_generated": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._projects[project_id] = project

        logger.info(
            "fusion_engine.project_created",
            project_id=project_id,
            name=name,
            brand_id=brand_id,
            total_tasks=len(tasks),
            systems=[s.system_type for s in systems],
            entity_types=effective_entity_types,
        )

        return ProjectPlan(
            project_id=project_id,
            project_name=name,
            brand_id=brand_id,
            store_ids=effective_store_ids,
            source_systems=systems,
            entity_types=effective_entity_types,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            total_tasks=len(tasks),
            tasks=tasks,
        )

    def get_project_progress(self, project_id: str) -> Optional[ProjectProgress]:
        """获取项目整体进度"""
        project = self._projects.get(project_id)
        if not project:
            return None

        # 汇总任务进度
        task_progresses = []
        total_imported = 0
        completed = 0
        running = 0
        failed = 0

        for task in self._tasks.values():
            if task.get("project_id") != project_id:
                continue
            status = task.get("status", "pending")
            processed = task.get("processed_count", 0)
            estimated = task.get("total_estimated")
            pct = 0.0
            if estimated and estimated > 0:
                pct = min(100.0, round(processed / estimated * 100, 1))
            elif status == "completed":
                pct = 100.0

            task_progresses.append(TaskProgress(
                task_id=task["id"],
                status=status,
                processed_count=processed,
                success_count=task.get("success_count", 0),
                error_count=task.get("error_count", 0),
                duplicate_count=task.get("duplicate_count", 0),
                total_estimated=estimated,
                progress_pct=pct,
                last_cursor=task.get("last_cursor"),
                last_error=task.get("last_error"),
            ))

            total_imported += task.get("success_count", 0)
            if status == "completed":
                completed += 1
            elif status == "running":
                running += 1
            elif status == "failed":
                failed += 1

        total_tasks = project.get("total_tasks", len(task_progresses))
        overall_pct = 0.0
        if total_tasks > 0:
            overall_pct = round(completed / total_tasks * 100, 1)

        return ProjectProgress(
            project_id=project_id,
            status=project.get("status", "created"),
            total_tasks=total_tasks,
            completed_tasks=completed,
            running_tasks=running,
            failed_tasks=failed,
            total_records_imported=total_imported,
            total_entities_resolved=project.get("total_entities_resolved", 0),
            total_conflicts=project.get("total_conflicts", 0),
            progress_pct=overall_pct,
            knowledge_generated=project.get("knowledge_generated", False),
            health_report_generated=project.get("health_report_generated", False),
            tasks=task_progresses,
        )

    def update_task_progress(
        self,
        task_id: str,
        processed_count: int,
        success_count: int,
        error_count: int,
        duplicate_count: int = 0,
        last_cursor: Optional[str] = None,
        status: Optional[str] = None,
        last_error: Optional[str] = None,
        total_estimated: Optional[int] = None,
    ) -> None:
        """更新任务进度（由 HistoricalBackfill 回调）"""
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("fusion_engine.task_not_found", task_id=task_id)
            return

        task["processed_count"] = processed_count
        task["success_count"] = success_count
        task["error_count"] = error_count
        task["duplicate_count"] = duplicate_count
        if last_cursor is not None:
            task["last_cursor"] = last_cursor
        if status is not None:
            task["status"] = status
        if last_error is not None:
            task["last_error"] = last_error
        if total_estimated is not None:
            task["total_estimated"] = total_estimated

    def get_next_tasks(self, project_id: str, limit: int = 3) -> List[Dict]:
        """获取下一批待执行的任务（按优先级排序）"""
        pending = []
        for task in self._tasks.values():
            if task.get("project_id") != project_id and project_id:
                continue
            if task.get("status") == "pending":
                pending.append(task)

        pending.sort(key=lambda t: t.get("priority", 0), reverse=True)
        return pending[:limit]

    def mark_task_completed(self, task_id: str) -> None:
        """标记任务完成"""
        task = self._tasks.get(task_id)
        if task:
            task["status"] = "completed"
            task["completed_at"] = datetime.utcnow().isoformat()

            # 更新项目完成计数
            project = self._projects.get(task.get("project_id", ""))
            if project:
                project["completed_tasks"] = project.get("completed_tasks", 0) + 1
                project["total_records_imported"] = (
                    project.get("total_records_imported", 0) + task.get("success_count", 0)
                )
                # 检查是否全部任务完成
                if project["completed_tasks"] >= project.get("total_tasks", 0):
                    project["status"] = "resolving"
                    logger.info(
                        "fusion_engine.all_tasks_completed",
                        project_id=project["id"],
                        total_imported=project["total_records_imported"],
                    )

    def mark_task_failed(self, task_id: str, error: str) -> None:
        """标记任务失败"""
        task = self._tasks.get(task_id)
        if task:
            task["status"] = "failed"
            task["last_error"] = error

    def retry_task(self, task_id: str) -> bool:
        """重试失败的任务（从断点续传）"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.get("status") not in ("failed", "paused"):
            return False
        task["status"] = "pending"
        task["last_error"] = None
        logger.info(
            "fusion_engine.task_retry",
            task_id=task_id,
            resume_from=task.get("last_cursor"),
        )
        return True
