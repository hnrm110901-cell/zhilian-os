"""
跨客户食材价格基准网络 API

端点：
  GET  /report       — 完整价格基准报告
  GET  /suggestions  — 供应商优化建议
  GET  /saving       — 总节省潜力
"""
from datetime import date
from fastapi import APIRouter, Query

from src.services.price_benchmark_network import (
    PriceDataPoint,
    generate_price_report,
    aggregate_price_benchmark,
    generate_supplier_suggestions,
    compute_total_saving_potential,
)

router = APIRouter(prefix="/api/v1/price-benchmark", tags=["price-benchmark"])


def _demo_pool() -> list[PriceDataPoint]:
    """演示全网匿名价格池（生产环境替换为真实多租户聚合）"""
    import random
    random.seed(42)
    items = [
        ("鲈鱼", "seafood", "kg", 1800),
        ("五花肉", "meat", "kg", 1200),
        ("西兰花", "vegetable", "kg", 600),
        ("大豆油", "oil", "bottle", 4500),
        ("老抽", "seasoning", "bottle", 800),
    ]
    pool = []
    for name, cat, unit, base in items:
        for i in range(12):
            cost = base + random.randint(-300, 500)
            pool.append(PriceDataPoint(
                ingredient_name=name, category=cat, city="上海",
                unit=unit, unit_cost_fen=cost, purchase_date="2026-03",
            ))
    return pool


def _demo_your_prices() -> list[PriceDataPoint]:
    """演示客户自己的价格"""
    return [
        PriceDataPoint("鲈鱼", "seafood", "上海", "kg", 2200, "2026-03"),
        PriceDataPoint("五花肉", "meat", "上海", "kg", 1500, "2026-03"),
        PriceDataPoint("西兰花", "vegetable", "上海", "kg", 650, "2026-03"),
        PriceDataPoint("大豆油", "oil", "上海", "bottle", 4800, "2026-03"),
        PriceDataPoint("老抽", "seasoning", "上海", "bottle", 850, "2026-03"),
    ]


@router.get("/stores/{store_id}/report")
async def get_price_benchmark_report(store_id: str):
    """完整价格基准报告"""
    pool = _demo_pool()
    your = _demo_your_prices()
    qty = {"鲈鱼": 80, "五花肉": 120, "西兰花": 60, "大豆油": 20, "老抽": 30}
    report = generate_price_report(pool, your, qty)
    return {"store_id": store_id, **report}


@router.get("/stores/{store_id}/suggestions")
async def get_supplier_suggestions(
    store_id: str,
    top_n: int = Query(default=5, ge=1, le=20),
):
    """供应商优化建议"""
    pool = _demo_pool()
    your = _demo_your_prices()
    benchmarks = aggregate_price_benchmark(pool, your)
    suggestions = generate_supplier_suggestions(benchmarks, top_n=top_n)
    return {
        "store_id": store_id,
        "suggestions": [
            {
                "ingredient": s.ingredient_name,
                "current_yuan": round(s.current_price_fen / 100, 2),
                "benchmark_yuan": round(s.benchmark_p25_fen / 100, 2),
                "saving_pct": s.saving_pct,
                "suggestion": s.suggestion,
                "source": s.anonymous_source,
            }
            for s in suggestions
        ],
    }


@router.get("/stores/{store_id}/saving")
async def get_total_saving(store_id: str):
    """总节省潜力"""
    pool = _demo_pool()
    your = _demo_your_prices()
    qty = {"鲈鱼": 80, "五花肉": 120, "西兰花": 60, "大豆油": 20, "老抽": 30}
    benchmarks = aggregate_price_benchmark(pool, your)
    saving = compute_total_saving_potential(benchmarks, qty)
    return {"store_id": store_id, **saving}
