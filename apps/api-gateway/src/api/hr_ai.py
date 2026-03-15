"""
HR AI决策API — Claude驱动的人力智能
提供离职风险预测、全店风险扫描、AI成长计划、薪资竞争力分析。
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db
from src.services.hr_ai_decision_service import HRAIDecisionService
from src.services.hr_growth_agent_service import generate_growth_plan

logger = structlog.get_logger()

router = APIRouter(prefix="/hr/ai", tags=["hr_ai"])

_service = HRAIDecisionService()


class GrowthPlanRequest(BaseModel):
    employee_id: str
    store_id: str


@router.get("/turnover-risk/{employee_id}")
async def get_turnover_risk(
    employee_id: str,
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    单员工离职风险分析（Claude AI + 规则引擎融合）

    返回：
    - risk_score: 0-100 风险评分
    - risk_level: low/medium/high/critical
    - signals: 风险信号列表（考勤、绩效、工龄等6维度）
    - ai_analysis: Claude生成的中文分析（LLM不可用时为null）
    - recommendations: 带¥影响的行动建议
    - replacement_cost_yuan: 估算重新招聘+培训成本
    - data_source: "ai+rules" 或 "rules_only"
    """
    try:
        result = await _service.predict_turnover_risk(db, employee_id, store_id)
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "turnover_risk_api_error",
            employee_id=employee_id,
            store_id=store_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="离职风险分析失败")


@router.get("/turnover-scan/{store_id}")
async def scan_store_turnover(
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    全店离职风险扫描

    对所有活跃员工进行规则引擎快速评分，
    对Top10高风险员工调用Claude做门店级分析。

    返回：
    - total_active: 活跃员工总数
    - high_risk_count / medium_risk_count: 各级风险人数
    - at_risk_employees: 风险排名Top20
    - store_analysis: Claude生成的门店级人力风险分析
    - store_recommendations: 门店级行动建议（含¥影响）
    - total_replacement_cost_yuan: 高风险员工总替换成本
    """
    try:
        return await _service.scan_store_turnover_risk(db, store_id)
    except Exception as e:
        logger.error(
            "turnover_scan_api_error",
            store_id=store_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="全店风险扫描失败")


# ── AI 成长计划 ─────────────────────────────────────────

@router.post("/growth-plan/generate")
async def ai_generate_growth_plan(
    body: GrowthPlanRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    AI生成成长计划 -- Claude驱动

    基于员工技能差距、绩效趋势、职业路径，生成个性化成长计划。
    LLM不可用时自动降级为规则引擎。

    返回：
    - plan_id: 成长计划ID
    - tasks: 任务列表（含完成标准、时间节点、推荐课程）
    - ai_reasoning: AI生成此计划的核心逻辑
    - llm_used: 是否使用了LLM（false=规则引擎降级）
    """
    logger.info(
        "hr_ai_growth_plan_request",
        employee_id=body.employee_id,
        store_id=body.store_id,
    )

    try:
        result = await generate_growth_plan(db, body.store_id, body.employee_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        await db.commit()
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "growth_plan_api_error",
            employee_id=body.employee_id,
            store_id=body.store_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="成长计划生成失败")


# ── 薪资竞争力分析 ──────────────────────────────────────

@router.get("/salary-competitiveness/{store_id}")
async def get_salary_competitiveness(
    store_id: str,
    brand_id: Optional[str] = Query("", description="品牌ID（可选）"),
    db: AsyncSession = Depends(get_db),
):
    """
    薪资竞争力分析 -- Claude驱动

    分析本店各岗位薪资与市场水平的对比，给出调薪建议和¥影响。

    返回：
    - overall_competitiveness: below_average / average / above_average
    - positions: 各岗位竞争力详情
      - avg_salary_yuan: 当前平均薪资
      - market_estimate_yuan: AI估算市场水平
      - percentile: 百分位（P25=低于75%同行）
      - risk_level: high/medium/low
      - recommendation: 调薪建议含¥金额
      - annual_impact_yuan: 年增加成本（负数）
      - saved_recruitment_yuan: 预计节省招聘成本
      - net_impact_yuan: 净收益
    - turnover_stats: 近6个月离职数据
    - ai_summary: AI综合分析
    - llm_used: 是否使用了LLM
    """
    logger.info(
        "hr_ai_salary_competitiveness_request",
        store_id=store_id,
        brand_id=brand_id,
    )

    try:
        result = await _service.analyze_salary_competitiveness(
            db, store_id, brand_id or ""
        )
        return result
    except Exception as e:
        logger.error(
            "salary_competitiveness_api_error",
            store_id=store_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="薪资竞争力分析失败")
