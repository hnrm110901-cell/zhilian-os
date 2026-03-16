"""
退订原因NLP分析 — Phase P4 (屯象独有)
分析退订/输单原因，生成洞察报告
"""

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class CancellationAnalyzer:
    """退订/输单原因分析器"""

    # 原因分类词典
    REASON_CATEGORIES = {
        "price": ["价格", "贵", "便宜", "费用", "报价", "预算", "打折", "优惠"],
        "competitor": ["竞对", "对手", "别家", "其他酒店", "竞争", "比较"],
        "schedule": ["日期", "档期", "时间", "冲突", "改期", "推迟"],
        "quality": ["质量", "服务", "态度", "菜品", "口味", "环境", "卫生"],
        "personal": ["取消", "不办了", "推迟", "家庭原因", "身体原因", "工作原因"],
        "location": ["位置", "交通", "停车", "远", "不方便"],
        "capacity": ["容纳", "桌数", "场地", "太小", "太大"],
    }

    async def analyze_cancellations(
        self,
        session: AsyncSession,
        store_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """分析退订原因分布"""
        # 从销售漏斗获取输单记录
        from src.models.banquet_sales import SalesFunnelRecord

        q = select(SalesFunnelRecord).where(
            SalesFunnelRecord.store_id == store_id,
            SalesFunnelRecord.current_stage == "lost",
        )
        if start_date:
            q = q.where(SalesFunnelRecord.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            q = q.where(SalesFunnelRecord.created_at <= datetime.combine(end_date, datetime.max.time()))

        result = await session.execute(q)
        lost_records = result.scalars().all()

        if not lost_records:
            return {
                "total_lost": 0,
                "period": {"start": str(start_date), "end": str(end_date)},
                "categories": [],
                "top_reasons": [],
                "competitor_analysis": [],
                "insights": ["暂无输单数据"],
                "suggestions": [],
            }

        # 分析原因分类
        reason_counts: Counter = Counter()
        competitor_counts: Counter = Counter()
        raw_reasons: List[str] = []
        total_value = 0

        for record in lost_records:
            reason = record.lost_reason or "未知"
            raw_reasons.append(reason)
            total_value += record.estimated_value or 0

            # 分类
            categorized = False
            for cat, keywords in self.REASON_CATEGORIES.items():
                if any(kw in reason for kw in keywords):
                    reason_counts[cat] += 1
                    categorized = True
                    break
            if not categorized:
                reason_counts["other"] += 1

            # 竞对分析
            if record.lost_to_competitor:
                competitor_counts[record.lost_to_competitor] += 1

        total = len(lost_records)
        category_labels = {
            "price": "价格偏高",
            "competitor": "选择竞对",
            "schedule": "档期冲突",
            "quality": "服务/质量",
            "personal": "个人原因",
            "location": "位置不便",
            "capacity": "场地不合适",
            "other": "其他原因",
        }

        categories = [
            {
                "category": cat,
                "label": category_labels.get(cat, cat),
                "count": count,
                "percentage": round(count / total * 100, 1),
            }
            for cat, count in reason_counts.most_common()
        ]

        competitors = [
            {"name": name, "count": count, "percentage": round(count / total * 100, 1)}
            for name, count in competitor_counts.most_common(5)
        ]

        # 生成洞察
        insights = self._generate_insights(categories, total, total_value)
        suggestions = self._generate_suggestions(categories, competitors)

        return {
            "total_lost": total,
            "total_lost_value_yuan": total_value / 100,
            "period": {
                "start": str(start_date or "all"),
                "end": str(end_date or "all"),
            },
            "categories": categories,
            "top_reasons": raw_reasons[:10],
            "competitor_analysis": competitors,
            "insights": insights,
            "suggestions": suggestions,
            "analyzed_at": datetime.utcnow().isoformat(),
        }

    async def get_daily_summary(
        self,
        session: AsyncSession,
        store_id: str,
    ) -> Dict[str, Any]:
        """生成今日退订摘要（用于日报推送）"""
        today = date.today()
        return await self.analyze_cancellations(
            session,
            store_id,
            start_date=today,
            end_date=today,
        )

    async def get_weekly_trend(
        self,
        session: AsyncSession,
        store_id: str,
    ) -> Dict[str, Any]:
        """最近7天退订趋势"""
        today = date.today()
        week_ago = today - timedelta(days=7)

        analysis = await self.analyze_cancellations(
            session,
            store_id,
            start_date=week_ago,
            end_date=today,
        )

        # 补充趋势数据
        from src.models.banquet_sales import SalesFunnelRecord

        daily_counts = {}
        for i in range(7):
            d = week_ago + timedelta(days=i)
            daily_counts[d.isoformat()] = 0

        q = (
            select(
                func.date(SalesFunnelRecord.updated_at).label("day"),
                func.count().label("cnt"),
            )
            .where(
                SalesFunnelRecord.store_id == store_id,
                SalesFunnelRecord.current_stage == "lost",
                SalesFunnelRecord.updated_at >= datetime.combine(week_ago, datetime.min.time()),
            )
            .group_by("day")
        )

        result = await session.execute(q)
        for row in result:
            daily_counts[str(row.day)] = row.cnt

        analysis["daily_trend"] = [{"date": d, "count": c} for d, c in daily_counts.items()]
        return analysis

    def _generate_insights(
        self,
        categories: List[Dict],
        total: int,
        total_value: int,
    ) -> List[str]:
        """生成分析洞察"""
        insights = []
        if total == 0:
            return ["本期无输单记录"]

        insights.append(f"本期共输单{total}笔，损失金额¥{total_value / 100:,.0f}")

        if categories:
            top = categories[0]
            insights.append(f"输单Top1原因：{top['label']}（{top['percentage']}%，{top['count']}笔）")

        # 价格敏感度
        price_cat = next((c for c in categories if c["category"] == "price"), None)
        if price_cat and price_cat["percentage"] >= 30:
            insights.append("⚠️ 价格敏感度偏高，建议优化定价策略或增强价值感知")

        # 竞对流失
        comp_cat = next((c for c in categories if c["category"] == "competitor"), None)
        if comp_cat and comp_cat["percentage"] >= 20:
            insights.append("⚠️ 竞对流失占比较高，建议加强差异化竞争力")

        return insights

    def _generate_suggestions(
        self,
        categories: List[Dict],
        competitors: List[Dict],
    ) -> List[Dict[str, str]]:
        """生成改进建议"""
        suggestions = []

        for cat in categories[:3]:
            if cat["category"] == "price":
                suggestions.append(
                    {
                        "category": "定价优化",
                        "action": "推出分级套餐（标准/精选/尊享），覆盖不同预算客户",
                        "expected_impact": f"预计减少{cat['count'] // 2}笔价格原因输单",
                    }
                )
            elif cat["category"] == "competitor":
                comp_names = ", ".join(c["name"] for c in competitors[:3])
                suggestions.append(
                    {
                        "category": "竞争策略",
                        "action": f"针对主要竞对（{comp_names}）制作对比方案，突出差异化优势",
                        "expected_impact": "提升竞品PK胜率",
                    }
                )
            elif cat["category"] == "schedule":
                suggestions.append(
                    {
                        "category": "档期管理",
                        "action": "增加高峰期档期供给（临时搭建、分时段排期）",
                        "expected_impact": "减少档期冲突导致的客户流失",
                    }
                )
            elif cat["category"] == "quality":
                suggestions.append(
                    {
                        "category": "服务提升",
                        "action": "加强服务培训，建立试菜机制，提升客户体验",
                        "expected_impact": "改善服务口碑，提升转化率",
                    }
                )

        return suggestions


cancellation_analyzer = CancellationAnalyzer()
