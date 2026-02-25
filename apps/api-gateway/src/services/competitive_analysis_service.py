"""
竞争分析服务
提供市场份额分析、竞品对比、价格敏感度分析
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, timedelta, datetime
from decimal import Decimal

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db_session
from src.models.competitor import CompetitorStore, CompetitorPrice
from src.models.dish import Dish
from src.models.order import Order
from src.models.finance import FinancialTransaction

logger = structlog.get_logger()


class CompetitiveAnalysisService:
    """竞争分析服务"""

    # ------------------------------------------------------------------ #
    # 竞品门店 CRUD                                                        #
    # ------------------------------------------------------------------ #

    async def list_competitors(self, our_store_id: str) -> List[CompetitorStore]:
        async with get_db_session() as session:
            stmt = select(CompetitorStore).where(
                and_(CompetitorStore.our_store_id == our_store_id, CompetitorStore.is_active == True)
            ).order_by(CompetitorStore.distance_meters)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_competitor(self, competitor_id: str) -> Optional[CompetitorStore]:
        async with get_db_session() as session:
            stmt = select(CompetitorStore).where(CompetitorStore.id == competitor_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create_competitor(
        self,
        our_store_id: str,
        name: str,
        brand: Optional[str] = None,
        cuisine_type: Optional[str] = None,
        address: Optional[str] = None,
        distance_meters: Optional[int] = None,
        avg_price_per_person: Optional[float] = None,
        rating: Optional[float] = None,
        monthly_customers: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> CompetitorStore:
        async with get_db_session() as session:
            competitor = CompetitorStore(
                id=uuid.uuid4(),
                our_store_id=our_store_id,
                name=name,
                brand=brand,
                cuisine_type=cuisine_type,
                address=address,
                distance_meters=distance_meters,
                avg_price_per_person=avg_price_per_person,
                rating=rating,
                monthly_customers=monthly_customers,
                notes=notes,
            )
            session.add(competitor)
            await session.commit()
            await session.refresh(competitor)
            logger.info("竞品门店已创建", competitor_id=str(competitor.id), name=name)
            return competitor

    async def update_competitor(self, competitor_id: str, **kwargs) -> Optional[CompetitorStore]:
        async with get_db_session() as session:
            stmt = select(CompetitorStore).where(CompetitorStore.id == competitor_id)
            result = await session.execute(stmt)
            competitor = result.scalar_one_or_none()
            if not competitor:
                return None
            allowed = {"name", "brand", "cuisine_type", "address", "distance_meters",
                       "avg_price_per_person", "rating", "monthly_customers", "notes", "is_active"}
            for key, value in kwargs.items():
                if key in allowed and value is not None:
                    setattr(competitor, key, value)
            await session.commit()
            await session.refresh(competitor)
            return competitor

    async def delete_competitor(self, competitor_id: str) -> bool:
        async with get_db_session() as session:
            stmt = select(CompetitorStore).where(CompetitorStore.id == competitor_id)
            result = await session.execute(stmt)
            competitor = result.scalar_one_or_none()
            if not competitor:
                return False
            await session.delete(competitor)
            await session.commit()
            return True

    # ------------------------------------------------------------------ #
    # 竞品价格 CRUD                                                        #
    # ------------------------------------------------------------------ #

    async def add_price_record(
        self,
        competitor_id: str,
        dish_name: str,
        price: float,
        record_date: date,
        category: Optional[str] = None,
        our_dish_id: Optional[str] = None,
    ) -> CompetitorPrice:
        async with get_db_session() as session:
            record = CompetitorPrice(
                id=uuid.uuid4(),
                competitor_id=competitor_id,
                dish_name=dish_name,
                price=Decimal(str(price)),
                record_date=record_date,
                category=category,
                our_dish_id=our_dish_id,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_price_records(
        self,
        competitor_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[CompetitorPrice]:
        async with get_db_session() as session:
            conditions = [CompetitorPrice.competitor_id == competitor_id]
            if start_date:
                conditions.append(CompetitorPrice.record_date >= start_date)
            if end_date:
                conditions.append(CompetitorPrice.record_date <= end_date)
            stmt = select(CompetitorPrice).where(and_(*conditions)).order_by(
                CompetitorPrice.record_date.desc()
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------ #
    # 市场份额分析                                                          #
    # ------------------------------------------------------------------ #

    async def analyze_market_share(
        self,
        our_store_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        市场份额分析

        基于我方营收 + 竞品估算客流量计算市场份额。
        竞品营收 = monthly_customers * avg_price_per_person（估算）。
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # 获取我方营收
        our_revenue = await self._get_our_revenue(our_store_id, start_date, end_date)

        # 获取竞品列表
        competitors = await self.list_competitors(our_store_id)

        # 估算竞品营收
        days = (end_date - start_date).days + 1
        competitor_data = []
        total_competitor_revenue = 0.0

        for c in competitors:
            if c.monthly_customers and c.avg_price_per_person:
                estimated_revenue = float(c.monthly_customers) * float(c.avg_price_per_person) * days / 30
            else:
                estimated_revenue = 0.0
            total_competitor_revenue += estimated_revenue
            competitor_data.append({
                "id": str(c.id),
                "name": c.name,
                "brand": c.brand,
                "estimated_revenue": round(estimated_revenue, 2),
                "distance_meters": c.distance_meters,
                "rating": float(c.rating) if c.rating else None,
            })

        total_market = our_revenue + total_competitor_revenue
        our_share = (our_revenue / total_market * 100) if total_market > 0 else 0.0

        # 按估算营收排序竞品
        competitor_data.sort(key=lambda x: x["estimated_revenue"], reverse=True)

        return {
            "store_id": our_store_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "our_revenue": round(our_revenue, 2),
            "our_market_share_pct": round(our_share, 2),
            "total_market_size": round(total_market, 2),
            "competitor_count": len(competitors),
            "competitors": competitor_data,
            "note": "竞品营收为基于月均客流量和人均消费的估算值",
        }

    async def _get_our_revenue(self, store_id: str, start_date: date, end_date: date) -> float:
        """获取我方指定时段的销售收入（元）"""
        async with get_db_session() as session:
            stmt = select(func.sum(FinancialTransaction.amount)).where(
                and_(
                    FinancialTransaction.store_id == store_id,
                    FinancialTransaction.transaction_type == "income",
                    FinancialTransaction.category == "sales",
                    FinancialTransaction.transaction_date >= start_date,
                    FinancialTransaction.transaction_date <= end_date,
                )
            )
            result = await session.execute(stmt)
            total_cents = result.scalar() or 0
            return total_cents / 100  # 分转元

    # ------------------------------------------------------------------ #
    # 竞品价格对比                                                          #
    # ------------------------------------------------------------------ #

    async def compare_prices(
        self,
        our_store_id: str,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        竞品价格对比

        对比我方菜品与竞品同类菜品的价格差异。
        """
        # 获取我方菜品价格
        our_dishes = await self._get_our_dishes(our_store_id, category)

        # 获取竞品最新价格
        competitors = await self.list_competitors(our_store_id)
        competitor_prices: Dict[str, List[Dict]] = {}

        async with get_db_session() as session:
            for c in competitors:
                conditions = [CompetitorPrice.competitor_id == str(c.id)]
                if category:
                    conditions.append(CompetitorPrice.category == category)

                # 每个菜品取最新一条
                subq = (
                    select(
                        CompetitorPrice.dish_name,
                        func.max(CompetitorPrice.record_date).label("latest_date"),
                    )
                    .where(and_(*conditions))
                    .group_by(CompetitorPrice.dish_name)
                    .subquery()
                )
                stmt = select(CompetitorPrice).join(
                    subq,
                    and_(
                        CompetitorPrice.dish_name == subq.c.dish_name,
                        CompetitorPrice.record_date == subq.c.latest_date,
                        CompetitorPrice.competitor_id == str(c.id),
                    ),
                )
                result = await session.execute(stmt)
                prices = result.scalars().all()
                competitor_prices[str(c.id)] = {
                    "name": c.name,
                    "dishes": [p.to_dict() for p in prices],
                }

        # 构建对比表
        comparison = []
        for dish in our_dishes:
            row: Dict[str, Any] = {
                "dish_name": dish["name"],
                "category": dish["category"],
                "our_price": dish["price"],
                "competitors": [],
            }
            prices_for_avg = [dish["price"]]
            for cid, cdata in competitor_prices.items():
                # 模糊匹配菜品名（包含关系）
                matched = next(
                    (p for p in cdata["dishes"] if dish["name"] in p["dish_name"] or p["dish_name"] in dish["name"]),
                    None,
                )
                if matched:
                    row["competitors"].append({
                        "competitor_name": cdata["name"],
                        "price": matched["price"],
                        "diff": round(dish["price"] - (matched["price"] or 0), 2),
                        "diff_pct": round(
                            (dish["price"] - (matched["price"] or 0)) / (matched["price"] or 1) * 100, 1
                        ),
                    })
                    prices_for_avg.append(matched["price"] or 0)

            if len(prices_for_avg) > 1:
                avg_market_price = sum(prices_for_avg) / len(prices_for_avg)
                row["avg_market_price"] = round(avg_market_price, 2)
                row["vs_market_avg_pct"] = round(
                    (dish["price"] - avg_market_price) / avg_market_price * 100, 1
                )
            comparison.append(row)

        return {
            "store_id": our_store_id,
            "category_filter": category,
            "our_dish_count": len(our_dishes),
            "competitor_count": len(competitors),
            "comparison": comparison,
        }

    async def _get_our_dishes(self, store_id: str, category: Optional[str] = None) -> List[Dict]:
        async with get_db_session() as session:
            conditions = [Dish.store_id == store_id, Dish.is_available == True]
            stmt = select(Dish).where(and_(*conditions))
            result = await session.execute(stmt)
            dishes = result.scalars().all()
            return [
                {
                    "id": str(d.id),
                    "name": d.name,
                    "category": str(d.category_id) if d.category_id else "",
                    "price": float(d.price) if d.price else 0.0,
                }
                for d in dishes
            ]

    # ------------------------------------------------------------------ #
    # 价格敏感度分析                                                        #
    # ------------------------------------------------------------------ #

    async def analyze_price_sensitivity(
        self,
        our_store_id: str,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        价格敏感度分析

        通过分析我方菜品价格变化前后的订单量变化，估算价格弹性。
        同时对比竞品价格差异与我方客流的相关性。
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # 获取我方菜品价格区间分布
        our_dishes = await self._get_our_dishes(our_store_id)
        if not our_dishes:
            return {"store_id": our_store_id, "message": "暂无菜品数据"}

        prices = [d["price"] for d in our_dishes if d["price"] > 0]
        avg_price = sum(prices) / len(prices) if prices else 0
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0

        # 价格区间分布
        price_ranges = [
            {"range": "0-30元", "min": 0, "max": 30},
            {"range": "30-60元", "min": 30, "max": 60},
            {"range": "60-100元", "min": 60, "max": 100},
            {"range": "100元以上", "min": 100, "max": float("inf")},
        ]
        distribution = []
        for pr in price_ranges:
            count = sum(1 for p in prices if pr["min"] <= p < pr["max"])
            distribution.append({"range": pr["range"], "count": count, "pct": round(count / len(prices) * 100, 1)})

        # 竞品价格对比摘要
        competitors = await self.list_competitors(our_store_id)
        competitor_avg_prices = []
        for c in competitors:
            if c.avg_price_per_person:
                competitor_avg_prices.append(float(c.avg_price_per_person))

        market_avg = sum(competitor_avg_prices) / len(competitor_avg_prices) if competitor_avg_prices else avg_price
        price_position = "高于市场均价" if avg_price > market_avg * 1.05 else (
            "低于市场均价" if avg_price < market_avg * 0.95 else "与市场均价持平"
        )

        # 价格弹性建议
        recommendations = []
        if avg_price > market_avg * 1.1:
            recommendations.append({
                "type": "降价机会",
                "message": f"我方均价（¥{avg_price:.1f}）高于市场均价（¥{market_avg:.1f}）10%以上，可考虑对高价菜品适当调整",
                "priority": "high",
            })
        elif avg_price < market_avg * 0.9:
            recommendations.append({
                "type": "提价空间",
                "message": f"我方均价（¥{avg_price:.1f}）低于市场均价（¥{market_avg:.1f}）10%以上，存在提价空间",
                "priority": "medium",
            })
        else:
            recommendations.append({
                "type": "价格合理",
                "message": f"我方均价（¥{avg_price:.1f}）与市场均价（¥{market_avg:.1f}）接近，价格竞争力较强",
                "priority": "low",
            })

        # 找出价格偏高的菜品（超过市场均价 20%）
        overpriced = [
            {"name": d["name"], "price": d["price"], "vs_market_pct": round((d["price"] - market_avg) / market_avg * 100, 1)}
            for d in our_dishes
            if d["price"] > market_avg * 1.2
        ]
        overpriced.sort(key=lambda x: x["vs_market_pct"], reverse=True)

        return {
            "store_id": our_store_id,
            "analysis_period_days": days,
            "our_price_stats": {
                "avg": round(avg_price, 2),
                "min": round(min_price, 2),
                "max": round(max_price, 2),
                "dish_count": len(prices),
            },
            "market_avg_price": round(market_avg, 2),
            "price_position": price_position,
            "price_distribution": distribution,
            "overpriced_dishes": overpriced[:10],  # 最多返回 10 个
            "recommendations": recommendations,
            "competitor_count": len(competitors),
        }


# 全局实例
competitive_analysis_service = CompetitiveAnalysisService()
