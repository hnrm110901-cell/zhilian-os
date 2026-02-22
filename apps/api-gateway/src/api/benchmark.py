"""
门店对标分析API端点
"""
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import date

from src.services.benchmark_service import BenchmarkService
from src.core.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


# Pydantic模型
class BenchmarkReportRequest(BaseModel):
    start_date: date
    end_date: date
    dimensions: Optional[List[str]] = None


@router.get("/report")
async def get_benchmark_report(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    dimensions: Optional[str] = Query(None, description="对标维度（逗号分隔）"),
    current_user: User = Depends(get_current_user),
):
    """
    获取门店对标报告

    对比本门店与同城同类型门店的经营指标
    """
    service = BenchmarkService()

    # 解析维度参数
    dimension_list = None
    if dimensions:
        dimension_list = [d.strip() for d in dimensions.split(",")]

    report = await service.get_benchmark_report(
        start_date=start_date,
        end_date=end_date,
        dimensions=dimension_list,
    )

    return report


@router.get("/dimensions")
async def get_available_dimensions(
    current_user: User = Depends(get_current_user),
):
    """
    获取可用的对标维度列表
    """
    dimensions = [
        {
            "key": "sales",
            "name": "销售额",
            "unit": "元",
            "description": "统计期间的总销售额",
        },
        {
            "key": "customer_count",
            "name": "客流量",
            "unit": "人",
            "description": "统计期间的总客流量",
        },
        {
            "key": "average_spend",
            "name": "客单价",
            "unit": "元",
            "description": "平均每位客户的消费金额",
        },
        {
            "key": "table_turnover",
            "name": "翻台率",
            "unit": "次/天",
            "description": "每张桌子每天的使用次数",
        },
        {
            "key": "labor_cost_ratio",
            "name": "人力成本占比",
            "unit": "%",
            "description": "人力成本占总成本的比例",
        },
        {
            "key": "food_cost_ratio",
            "name": "食材成本占比",
            "unit": "%",
            "description": "食材成本占总成本的比例",
        },
        {
            "key": "profit_margin",
            "name": "毛利率",
            "unit": "%",
            "description": "毛利润占销售额的比例",
        },
        {
            "key": "customer_satisfaction",
            "name": "客户满意度",
            "unit": "分",
            "description": "客户评分（1-5分）",
        },
    ]

    return {"dimensions": dimensions}


@router.get("/summary")
async def get_benchmark_summary(
    current_user: User = Depends(get_current_user),
):
    """
    获取对标摘要信息

    快速了解本门店的整体表现
    """
    from datetime import datetime, timedelta

    # 默认查询最近30天
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    service = BenchmarkService()
    report = await service.get_benchmark_report(
        start_date=start_date,
        end_date=end_date,
    )

    # 提取摘要信息
    summary = {
        "period": report["period"],
        "benchmark_stores": report["benchmark_summary"]["total_stores"],
        "overall_ranking": None,
        "strengths_count": len(report["strengths"]),
        "weaknesses_count": len(report["weaknesses"]),
        "top_strength": report["strengths"][0] if report["strengths"] else None,
        "top_weakness": report["weaknesses"][0] if report["weaknesses"] else None,
    }

    # 计算综合排名（所有维度的平均分位数）
    if report["rankings"]:
        percentiles = [r["percentile"] for r in report["rankings"].values()]
        summary["overall_ranking"] = {
            "percentile": round(sum(percentiles) / len(percentiles), 1),
            "level": service._get_performance_level(
                sum(percentiles) / len(percentiles)
            ),
        }

    return summary
