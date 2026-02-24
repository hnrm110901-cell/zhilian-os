"""
AI决策演进度量 Dashboard API
AI Evolution Dashboard

让客户用数据回答：AI这周帮我省了多少钱？AI变聪明了吗？
"""
from fastapi import APIRouter, Query
from typing import Optional

from src.services.ai_evolution_service import AIEvolutionService

router = APIRouter()
_svc = AIEvolutionService()


@router.get("/api/v1/ai-evolution/adoption-rate")
async def get_adoption_rate(
    store_id: Optional[str] = Query(None, description="门店ID，不传则统计全部门店"),
    days: int = Query(7, ge=1, le=365, description="统计天数"),
):
    """
    AI建议采纳率

    返回指定周期内：总建议数、采纳数、修改数、拒绝数及各自比率。
    """
    return await _svc.get_adoption_rate(store_id=store_id, days=days)


@router.get("/api/v1/ai-evolution/outcome-summary")
async def get_outcome_summary(
    store_id: Optional[str] = Query(None, description="门店ID"),
    days: int = Query(30, ge=1, le=365, description="统计天数"),
):
    """
    采纳后实际效果汇总

    返回：成功率、累计节省成本（元）、营收影响（元）、平均结果偏差。
    """
    return await _svc.get_outcome_summary(store_id=store_id, days=days)


@router.get("/api/v1/ai-evolution/weekly-trend")
async def get_weekly_trend(
    store_id: Optional[str] = Query(None, description="门店ID"),
    weeks: int = Query(8, ge=2, le=52, description="统计周数"),
):
    """
    周维度采纳率趋势

    返回按周排列的采纳率列表，用于前端折线图展示AI进化曲线。
    """
    return await _svc.get_weekly_trend(store_id=store_id, weeks=weeks)


@router.get("/api/v1/ai-evolution/hitl-escalations")
async def get_hitl_escalation_trend(
    store_id: Optional[str] = Query(None, description="门店ID"),
    days: int = Query(30, ge=1, le=365, description="统计天数"),
):
    """
    HITL升级次数趋势

    高风险操作需人工介入的频率。趋势下降说明AI决策质量提升，门店对AI信任度增加。
    """
    return await _svc.get_hitl_escalation_trend(store_id=store_id, days=days)


@router.get("/api/v1/ai-evolution/agent-performance")
async def get_agent_performance(
    store_id: Optional[str] = Query(None, description="门店ID"),
    days: int = Query(30, ge=1, le=365, description="统计天数"),
):
    """
    各Agent建议质量对比

    返回每个Agent类型的采纳率、平均置信度、累计成本影响，
    用于识别哪个Agent最值得信任、哪个需要优化。
    """
    return await _svc.get_agent_performance(store_id=store_id, days=days)


@router.get("/api/v1/ai-evolution/summary")
async def get_evolution_summary(
    store_id: Optional[str] = Query(None, description="门店ID"),
):
    """
    AI演进总览（Dashboard首屏）

    聚合最近7天采纳率、最近30天效果、HITL趋势，一次返回Dashboard所需全部核心指标。
    """
    adoption = await _svc.get_adoption_rate(store_id=store_id, days=7)
    outcome = await _svc.get_outcome_summary(store_id=store_id, days=30)
    hitl = await _svc.get_hitl_escalation_trend(store_id=store_id, days=30)
    agents = await _svc.get_agent_performance(store_id=store_id, days=30)

    return {
        "store_id": store_id,
        "last_7d_adoption": adoption,
        "last_30d_outcome": outcome,
        "last_30d_hitl": hitl,
        "agent_performance": agents,
    }
