"""菜品组合矩阵分析 API — Phase 6 Month 10"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.menu_matrix_service import (
    compute_menu_matrix,
    get_menu_matrix,
    get_matrix_summary,
    get_top_actions,
    get_dish_quadrant_history,
)

router = APIRouter(prefix='/api/v1/menu-matrix', tags=['menu-matrix'])

_VALID_QUADRANTS  = {'star', 'cash_cow', 'question_mark', 'dog'}
_VALID_ACTIONS    = {'promote', 'maintain', 'develop', 'retire'}
_VALID_PRIORITIES = {'high', 'medium', 'low'}


@router.post('/compute/{store_id}')
async def api_compute_matrix(
    store_id: str,
    period: str = Query(..., description='YYYY-MM'),
    prev_period: Optional[str] = Query(None, description='YYYY-MM，默认取上月'),
    db: AsyncSession = Depends(get_db),
):
    """触发 BCG 矩阵分析并写入数据库（幂等）。"""
    result = await compute_menu_matrix(db, store_id, period, prev_period)
    return {'ok': True, 'data': result}


@router.get('/{store_id}')
async def api_get_matrix(
    store_id: str,
    period: str = Query(..., description='YYYY-MM'),
    quadrant: Optional[str] = Query(None, description='star/cash_cow/question_mark/dog'),
    action: Optional[str] = Query(None, description='promote/maintain/develop/retire'),
    priority: Optional[str] = Query(None, description='high/medium/low'),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询矩阵明细，支持象限/行动/优先级单独筛选（互斥，优先级 quadrant > action > priority）。"""
    if quadrant and quadrant not in _VALID_QUADRANTS:
        return {'ok': False, 'error': f'quadrant 必须是 {_VALID_QUADRANTS} 之一'}
    if action and action not in _VALID_ACTIONS:
        return {'ok': False, 'error': f'action 必须是 {_VALID_ACTIONS} 之一'}
    if priority and priority not in _VALID_PRIORITIES:
        return {'ok': False, 'error': f'priority 必须是 {_VALID_PRIORITIES} 之一'}
    rows = await get_menu_matrix(db, store_id, period,
                                  quadrant=quadrant, action=action,
                                  priority=priority, limit=limit)
    return {'ok': True, 'data': rows}


@router.get('/summary/{store_id}')
async def api_get_summary(
    store_id: str,
    period: str = Query(..., description='YYYY-MM'),
    db: AsyncSession = Depends(get_db),
):
    """按象限聚合统计（菜品数、总营收、预期影响）。"""
    result = await get_matrix_summary(db, store_id, period)
    return {'ok': True, 'data': result}


@router.get('/actions/{store_id}')
async def api_get_top_actions(
    store_id: str,
    period: str = Query(..., description='YYYY-MM'),
    action: str = Query('promote', description='promote/maintain/develop/retire'),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """按推荐行动类型，返回预期影响最大的菜品。"""
    if action not in _VALID_ACTIONS:
        return {'ok': False, 'error': f'action 必须是 {_VALID_ACTIONS} 之一'}
    rows = await get_top_actions(db, store_id, period, action=action, limit=limit)
    return {'ok': True, 'data': rows}


@router.get('/dish/{store_id}/{dish_id}')
async def api_get_dish_history(
    store_id: str,
    dish_id: str,
    periods: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期的象限变迁历史。"""
    rows = await get_dish_quadrant_history(db, store_id, dish_id, periods=periods)
    return {'ok': True, 'data': rows}


@router.get('/meta/quadrants')
async def api_meta_quadrants():
    """返回象限枚举说明。"""
    return {
        'ok': True,
        'data': [
            {
                'quadrant': 'star',
                'label': '明星菜',
                'description': '高营收 + 高增长，重点推广',
                'action': 'promote',
                'color': '#faad14',
            },
            {
                'quadrant': 'cash_cow',
                'label': '现金牛菜',
                'description': '高营收 + 低增长，稳定维护',
                'action': 'maintain',
                'color': '#52c41a',
            },
            {
                'quadrant': 'question_mark',
                'label': '问题菜',
                'description': '低营收 + 高增长，挖掘潜力',
                'action': 'develop',
                'color': '#1677ff',
            },
            {
                'quadrant': 'dog',
                'label': '瘦狗菜',
                'description': '低营收 + 低增长，考虑退出',
                'action': 'retire',
                'color': '#ff4d4f',
            },
        ],
    }
