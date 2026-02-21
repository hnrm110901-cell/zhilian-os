"""
Task Management API
任务管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import structlog
import uuid

from src.core.dependencies import get_current_active_user
from src.services.task_service import task_service
from src.models.task import TaskStatus, TaskPriority
from src.models.user import User

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    title: str = Field(..., description="任务标题", min_length=1, max_length=200)
    content: str = Field(..., description="任务内容")
    assignee_id: Optional[str] = Field(None, description="指派人ID")
    category: Optional[str] = Field(None, description="任务类别")
    priority: TaskPriority = Field(TaskPriority.NORMAL, description="优先级")
    due_at: Optional[datetime] = Field(None, description="截止时间")


class AssignTaskRequest(BaseModel):
    """指派任务请求"""
    assignee_id: str = Field(..., description="指派人ID")


class CompleteTaskRequest(BaseModel):
    """完成任务请求"""
    result: Optional[str] = Field(None, description="任务结果")
    attachments: Optional[str] = Field(None, description="附件URL列表（JSON格式）")


class UpdateTaskStatusRequest(BaseModel):
    """更新任务状态请求"""
    status: TaskStatus = Field(..., description="新状态")


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    title: str
    content: Optional[str]
    category: Optional[str]
    status: TaskStatus
    priority: TaskPriority
    store_id: str
    creator_id: str
    assignee_id: Optional[str]
    due_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[str]
    attachments: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== API Endpoints ====================


@router.post("/tasks", response_model=dict, summary="创建任务")
async def create_task(
    request: CreateTaskRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    创建新任务

    - **title**: 任务标题（必填）
    - **content**: 任务详细内容（必填）
    - **assignee_id**: 指派给谁（可选）
    - **category**: 任务类别（可选）
    - **priority**: 优先级（默认normal）
    - **due_at**: 截止时间（可选）
    """
    try:
        # 转换assignee_id
        assignee_uuid = None
        if request.assignee_id:
            try:
                assignee_uuid = uuid.UUID(request.assignee_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="无效的assignee_id格式")

        # 创建任务
        task = await task_service.create_task(
            title=request.title,
            content=request.content,
            creator_id=current_user.id,
            store_id=current_user.store_id,
            assignee_id=assignee_uuid,
            category=request.category,
            priority=request.priority,
            due_at=request.due_at
        )

        return {
            "success": True,
            "data": TaskResponse.model_validate(task).model_dump(),
            "message": "任务创建成功"
        }

    except Exception as e:
        logger.error("创建任务失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", response_model=dict, summary="查询任务列表")
async def get_tasks(
    assignee_id: Optional[str] = Query(None, description="指派人ID"),
    creator_id: Optional[str] = Query(None, description="创建人ID"),
    status: Optional[TaskStatus] = Query(None, description="任务状态"),
    category: Optional[str] = Query(None, description="任务类别"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_active_user)
):
    """
    查询任务列表

    支持按指派人、创建人、状态、类别筛选
    支持分页查询
    """
    try:
        # 转换UUID
        assignee_uuid = None
        creator_uuid = None

        if assignee_id:
            try:
                assignee_uuid = uuid.UUID(assignee_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="无效的assignee_id格式")

        if creator_id:
            try:
                creator_uuid = uuid.UUID(creator_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="无效的creator_id格式")

        # 查询任务
        result = await task_service.query_tasks(
            store_id=current_user.store_id,
            assignee_id=assignee_uuid,
            creator_id=creator_uuid,
            status=status,
            category=category,
            page=page,
            page_size=page_size
        )

        # 转换任务列表
        tasks_data = [
            TaskResponse.model_validate(task).model_dump()
            for task in result["tasks"]
        ]

        return {
            "success": True,
            "data": {
                "tasks": tasks_data,
                "pagination": {
                    "total": result["total"],
                    "page": result["page"],
                    "page_size": result["page_size"],
                    "total_pages": result["total_pages"]
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询任务列表失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=dict, summary="获取任务详情")
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """获取指定任务的详细信息"""
    try:
        # 转换task_id
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的task_id格式")

        # 获取任务
        task = await task_service.get_task_by_id(task_uuid)

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 验证权限：只能查看自己门店的任务
        if task.store_id != current_user.store_id:
            raise HTTPException(status_code=403, detail="无权访问该任务")

        return {
            "success": True,
            "data": TaskResponse.model_validate(task).model_dump()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取任务详情失败", task_id=task_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}/assign", response_model=dict, summary="指派任务")
async def assign_task(
    task_id: str,
    request: AssignTaskRequest,
    current_user: User = Depends(get_current_active_user)
):
    """将任务指派给指定用户"""
    try:
        # 转换ID
        try:
            task_uuid = uuid.UUID(task_id)
            assignee_uuid = uuid.UUID(request.assignee_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的ID格式")

        # 指派任务
        task = await task_service.assign_task(
            task_id=task_uuid,
            assignee_id=assignee_uuid,
            current_user_id=current_user.id
        )

        return {
            "success": True,
            "data": TaskResponse.model_validate(task).model_dump(),
            "message": "任务指派成功"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("指派任务失败", task_id=task_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}/complete", response_model=dict, summary="完成任务")
async def complete_task(
    task_id: str,
    request: CompleteTaskRequest,
    current_user: User = Depends(get_current_active_user)
):
    """标记任务为已完成"""
    try:
        # 转换task_id
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的task_id格式")

        # 完成任务
        task = await task_service.complete_task(
            task_id=task_uuid,
            user_id=current_user.id,
            result=request.result,
            attachments=request.attachments
        )

        return {
            "success": True,
            "data": TaskResponse.model_validate(task).model_dump(),
            "message": "任务完成"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("完成任务失败", task_id=task_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}/status", response_model=dict, summary="更新任务状态")
async def update_task_status(
    task_id: str,
    request: UpdateTaskStatusRequest,
    current_user: User = Depends(get_current_active_user)
):
    """更新任务状态"""
    try:
        # 转换task_id
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的task_id格式")

        # 更新状态
        task = await task_service.update_task_status(
            task_id=task_uuid,
            status=request.status,
            user_id=current_user.id
        )

        return {
            "success": True,
            "data": TaskResponse.model_validate(task).model_dump(),
            "message": "任务状态更新成功"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("更新任务状态失败", task_id=task_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}", response_model=dict, summary="删除任务")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """删除任务（软删除）"""
    try:
        # 转换task_id
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的task_id格式")

        # 删除任务
        success = await task_service.delete_task(
            task_id=task_uuid,
            user_id=current_user.id
        )

        return {
            "success": success,
            "message": "任务删除成功"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("删除任务失败", task_id=task_id, error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))
