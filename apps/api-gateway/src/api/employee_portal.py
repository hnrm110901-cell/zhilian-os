"""
Employee Portal API — 员工自助门户端点（乐才平替核心）

路由前缀: /api/v1/employee-portal
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.lecai_replacement_service import LeCaiReplacementService

router = APIRouter(prefix="/api/v1/employee-portal", tags=["员工自助门户"])


@router.get("/my-overview/{person_id}")
async def get_my_overview(
    person_id: UUID,
    month: Optional[str] = Query(None, description="YYYY-MM，默认当月"),
    db: AsyncSession = Depends(get_db),
):
    """员工自助门户首页 — 一次请求获取全部数据

    返回：基本信息 + 考勤 + 薪资 + 假期 + 旅程
    """
    return await LeCaiReplacementService.get_my_overview(
        db, person_id, month=month,
    )


@router.get("/my-attendance/{person_id}")
async def get_my_attendance(
    person_id: UUID,
    month: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """我的考勤月报"""
    return await LeCaiReplacementService.get_my_attendance(
        db, person_id, month,
    )


@router.get("/my-payslip/{person_id}")
async def get_my_payslip(
    person_id: UUID,
    month: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """我的薪资条"""
    return await LeCaiReplacementService.get_my_payslip(
        db, person_id, month,
    )


@router.get("/my-schedule/{person_id}")
async def get_my_schedule(
    person_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """我的排班"""
    return await LeCaiReplacementService.get_my_schedule(
        db, person_id, start_date, end_date,
    )


@router.get("/feature-matrix")
async def get_feature_matrix():
    """乐才 vs 屯象OS 功能对标矩阵

    用于商务演示和客户沟通
    """
    return LeCaiReplacementService.get_feature_matrix()


# ── 徐记海鲜模拟数据 ──────────────────────────────────


@router.post("/seed/xuji-seafood")
async def seed_xuji_seafood(
    db: AsyncSession = Depends(get_db),
):
    """一键初始化徐记海鲜模拟数据

    创建：2家门店 + 120名员工 + 旅程模板
    """
    from src.services.xuji_seafood_seed import XujiSeafoodSeedService
    return await XujiSeafoodSeedService.seed_all(db)
