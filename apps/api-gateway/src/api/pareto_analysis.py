"""
帕累托分析 API — 滑块交互 + 多场景分析 + 行动建议

端点：
  POST /api/v1/analytics/pareto/analyze           — 执行分析
  POST /api/v1/analytics/pareto/action-suggestion  — 生成行动建议
  GET  /api/v1/analytics/pareto/scenes             — 可用分析场景列表
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/analytics/pareto", tags=["帕累托分析"])


# ── 请求模型 ──────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    object_type: str = "store"           # store/sku/member/employee/material/issue
    metric_key: str = "revenue"          # revenue/gross_profit/order_count/waste_amount/...
    selected_ratio: float = 0.2          # 初始聚焦比例
    brand_id: Optional[str] = None
    store_id: Optional[str] = None
    biz_date: Optional[date] = None


class ActionSuggestionRequest(BaseModel):
    analysis_id: str
    selected_ratio: float


# ── 分析缓存（MVP 内存存储） ──────────────────────────────────────────────────

from ..services.pareto_analysis_service import ParetoAnalysisService

_svc = ParetoAnalysisService()
_cache: dict = {}  # {analysis_id: ParetoAnalysisResult}


def _get_demo_data(object_type: str, metric_key: str) -> list:
    """
    生成演示数据（种子客户验证用）。
    生产环境替换为从 POS/DB 查询。
    """
    import random
    random.seed(42)

    if object_type == "store":
        stores = [
            ("CZYZ-2461", "尝在一起文化城店"), ("CZYZ-7269", "浏小鲜"),
            ("CZYZ-19189", "尝在一起永安店"), ("ZQX-20529", "最黔线马家湾店"),
            ("ZQX-32109", "最黔线东欣万象店"), ("ZQX-32304", "最黔线合众路店"),
            ("ZQX-32305", "最黔线广州路店"), ("ZQX-32306", "最黔线昆明路店"),
            ("SGC-2463", "尚宫厨星沙店"), ("SGC-7896", "尚宫厨梅溪湖店"),
            ("SGC-24777", "尚宫厨高铁南站店"), ("SGC-36199", "尚宫厨红星店"),
            ("SGC-41405", "尚宫厨万家丽店"), ("CZYZ-BWM", "半碗码"),
        ]
        return [
            {"id": sid, "name": sname,
             "metric_value": random.randint(50000, 500000),
             "risk_level": random.choice(["low", "low", "low", "medium", "high"]),
             "owner_name": f"{sname}店长"}
            for sid, sname in stores
        ]

    elif object_type == "sku":
        dishes = [
            "剁椒鱼头", "小炒黄牛肉", "松露蒸蛋", "臭豆腐", "口味虾",
            "毛氏红烧肉", "干锅牛蛙", "农家小炒肉", "糖油粑粑", "紫苏桃子姜",
            "酸菜鱼", "辣椒炒肉", "凉拌折耳根", "腊味合蒸", "米豆腐",
            "外婆菜", "土匪猪肝", "芷江鸭", "血粑鸭", "莲藕排骨汤",
        ]
        return [
            {"id": f"SKU_{i:03d}", "name": d,
             "metric_value": random.randint(1000, 80000),
             "risk_level": random.choice(["low", "low", "medium"])}
            for i, d in enumerate(dishes)
        ]

    elif object_type == "member":
        return [
            {"id": f"M_{i:04d}", "name": f"会员{i:04d}",
             "metric_value": random.randint(100, 50000)}
            for i in range(1, 51)
        ]

    return [
        {"id": f"OBJ_{i}", "name": f"对象{i}", "metric_value": random.randint(100, 10000)}
        for i in range(1, 21)
    ]


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.post("/analyze", summary="执行帕累托分析")
async def analyze(req: AnalyzeRequest):
    raw_data = _get_demo_data(req.object_type, req.metric_key)

    result = _svc.analyze(
        raw_items=raw_data,
        object_type=req.object_type,
        metric_key=req.metric_key,
        selected_ratio=req.selected_ratio,
    )

    # 缓存供后续 action-suggestion 使用
    _cache[result.analysis_id] = result

    # 序列化
    return {
        "analysis_id": result.analysis_id,
        "object_type": result.object_type,
        "metric_key": result.metric_key,
        "summary": {
            "selected_ratio": result.summary.selected_ratio,
            "selected_object_count": result.summary.selected_object_count,
            "total_object_count": result.summary.total_object_count,
            "selected_contribution": result.summary.selected_contribution,
            "marginal_gain": result.summary.marginal_gain,
            "recommend_min_ratio": result.summary.recommend_min_ratio,
            "recommend_max_ratio": result.summary.recommend_max_ratio,
            "best_ratio": result.summary.best_ratio,
            "total_metric_value": result.summary.total_metric_value,
            "elbow_point_ratio": result.summary.elbow_point_ratio,
            "tail_start_ratio": result.summary.tail_start_ratio,
        },
        "curve": [
            {"ratio": p.ratio, "cumulative_contribution": p.cumulative_contribution,
             "marginal_gain": p.marginal_gain, "object_count": p.object_count}
            for p in result.curve
        ],
        "items": [
            {"object_id": it.object_id, "object_name": it.object_name,
             "rank": it.rank, "metric_value": it.metric_value,
             "contribution": it.contribution, "cumulative_contribution": it.cumulative_contribution,
             "segment_type": it.segment_type, "risk_level": it.risk_level,
             "owner_name": it.owner_name}
            for it in result.items
        ],
        "insight": {
            "title": result.insight.title,
            "text": result.insight.text,
            "insight_type": result.insight.insight_type,
            "confidence": result.insight.confidence,
            "tags": result.insight.tags,
        },
        "generated_at": result.generated_at,
    }


@router.post("/action-suggestion", summary="生成行动建议")
async def action_suggestion(req: ActionSuggestionRequest):
    cached = _cache.get(req.analysis_id)
    if not cached:
        raise HTTPException(404, "分析结果不存在或已过期，请重新分析")

    actions = _svc.get_action_suggestions(
        cached.items, req.selected_ratio, cached.object_type,
    )

    return {
        "analysis_id": req.analysis_id,
        "selected_ratio": req.selected_ratio,
        "actions": [
            {"action_id": a.action_id, "action_title": a.action_title,
             "action_desc": a.action_desc, "action_type": a.action_type,
             "priority": a.priority, "owner_role": a.owner_role,
             "due_in_days": a.due_in_days,
             "related_object_count": len(a.related_object_ids)}
            for a in actions
        ],
    }


@router.get("/scenes", summary="可用分析场景")
async def list_scenes():
    return {
        "scenes": [
            {"object_type": "store", "label": "门店经营分析",
             "metrics": ["revenue", "gross_profit", "order_count", "customer_count"]},
            {"object_type": "sku", "label": "菜品贡献分析",
             "metrics": ["revenue", "gross_profit", "order_count", "return_rate"]},
            {"object_type": "member", "label": "会员价值分析",
             "metrics": ["total_spend", "visit_count", "repurchase_rate"]},
            {"object_type": "employee", "label": "员工绩效分析",
             "metrics": ["performance_score", "service_count", "complaint_count"]},
            {"object_type": "material", "label": "食材损耗分析",
             "metrics": ["waste_amount", "waste_rate", "cost_variance"]},
            {"object_type": "issue", "label": "异常问题分析",
             "metrics": ["occurrence_count", "loss_amount", "resolution_time"]},
        ],
    }
