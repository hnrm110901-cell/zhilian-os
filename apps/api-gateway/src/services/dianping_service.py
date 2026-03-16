"""
大众点评评论监控服务
提供评论同步、情感分析、统计汇总、关键词云等业务逻辑
"""

import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.dianping_review import DianpingReview

logger = structlog.get_logger()

# ── 情感分析关键词 ─────────────────────────────────────────────────

POSITIVE_KEYWORDS = [
    "好吃",
    "推荐",
    "满意",
    "不错",
    "优秀",
    "新鲜",
    "干净",
    "热情",
    "实惠",
    "好评",
    "喜欢",
    "美味",
    "赞",
    "超棒",
    "惊喜",
]
NEGATIVE_KEYWORDS = [
    "难吃",
    "差评",
    "不满",
    "投诉",
    "差",
    "脏",
    "慢",
    "贵",
    "凉了",
    "态度差",
    "不新鲜",
    "等太久",
    "失望",
    "难以下咽",
    "退款",
]

# ── Mock数据生成（模拟大众点评API返回） ─────────────────────────────

_MOCK_AUTHORS = [
    "美食达人小王",
    "吃货日记",
    "老饕客",
    "小红薯爱吃",
    "湘菜控",
    "快乐星球",
    "深夜食堂",
    "周末觅食",
    "辣妹子",
    "嘴巴停不下来",
]

_MOCK_AVATARS = [
    "https://img.dianping.com/avatar/u1.jpg",
    "https://img.dianping.com/avatar/u2.jpg",
    "https://img.dianping.com/avatar/u3.jpg",
    None,
]

_MOCK_CONTENTS = [
    "菜品很新鲜，服务态度也不错，推荐他家的招牌湘菜！下次还会再来。",
    "等了很久才上菜，味道一般般，性价比不高。",
    "环境很好，适合聚餐，菜品分量足，价格实惠，好评！",
    "上菜速度太慢了，等了将近一个小时，态度差，不会再来了。",
    "朋友推荐来的，果然没有失望！剁椒鱼头超级好吃，五星好评。",
    "中规中矩吧，没有特别惊喜，但也不差。就是停车不方便。",
    "味道很赞，食材新鲜，老板人也很热情。满意！",
    "差评！菜是凉的，催了好几次服务员才来，体验很差。",
    "第一次来就被种草了，干净卫生，菜品精致，适合约会。",
    "团购价格实惠，菜量也足够，几个人一起吃很划算。推荐推荐！",
    "口味偏咸，不太合我口味，不过服务还是可以的。",
    "惊喜满满！甜品特别好吃，环境超棒，拍照出片。",
]


class DianpingService:
    """大众点评评论监控服务"""

    async def sync_reviews(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        从大众点评同步评论（当前使用Mock数据）

        Returns:
            同步结果：synced（新增）、skipped（已存在）、total（本次拉取总数）
        """
        synced = 0
        skipped = 0
        num_reviews = random.randint(3, 8)

        for i in range(num_reviews):
            ext_review_id = f"dp_{brand_id}_{store_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"

            # 检查是否已存在
            exists = await db.execute(select(DianpingReview.id).where(DianpingReview.review_id == ext_review_id))
            if exists.scalar_one_or_none():
                skipped += 1
                continue

            rating = random.choices([5, 4, 3, 2, 1], weights=[35, 30, 15, 10, 10])[0]
            content = random.choice(_MOCK_CONTENTS)
            review_date = datetime.now() - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23),
            )

            review = DianpingReview(
                brand_id=brand_id,
                store_id=store_id,
                review_id=ext_review_id,
                author_name=random.choice(_MOCK_AUTHORS),
                author_avatar_url=random.choice(_MOCK_AVATARS),
                rating=rating,
                content=content,
                images=random.choice(
                    [
                        None,
                        [
                            "https://img.dianping.com/photo/r1.jpg",
                            "https://img.dianping.com/photo/r2.jpg",
                        ],
                    ]
                ),
                review_date=review_date,
                source=random.choice(["dianping", "meituan"]),
                is_read=False,
            )
            db.add(review)
            synced += 1

        await db.commit()

        # 对新增评论做情感分析
        if synced > 0:
            unanalyzed = await db.execute(
                select(DianpingReview).where(
                    and_(
                        DianpingReview.brand_id == brand_id,
                        DianpingReview.store_id == store_id,
                        DianpingReview.sentiment.is_(None),
                    )
                )
            )
            for review in unanalyzed.scalars().all():
                self._analyze_sentiment_for_review(review)
            await db.commit()

        logger.info("评论同步完成", brand_id=brand_id, store_id=store_id, synced=synced, skipped=skipped)
        return {"synced": synced, "skipped": skipped, "total": num_reviews}

    async def list_reviews(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sentiment: Optional[str] = None,
        rating: Optional[int] = None,
        is_read: Optional[bool] = None,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询评论列表，支持多条件筛选"""
        conditions = [DianpingReview.brand_id == brand_id]
        if store_id:
            conditions.append(DianpingReview.store_id == store_id)
        if sentiment:
            conditions.append(DianpingReview.sentiment == sentiment)
        if rating is not None:
            conditions.append(DianpingReview.rating == rating)
        if is_read is not None:
            conditions.append(DianpingReview.is_read == is_read)
        if keyword:
            conditions.append(DianpingReview.content.ilike(f"%{keyword}%"))

        where_clause = and_(*conditions)

        # 总数
        count_q = select(func.count(DianpingReview.id)).where(where_clause)
        total = (await db.execute(count_q)).scalar() or 0

        # 分页数据
        query = (
            select(DianpingReview)
            .where(where_clause)
            .order_by(desc(DianpingReview.review_date))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        reviews = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "reviews": [self._to_dict(r) for r in reviews],
        }

    async def get_review(self, db: AsyncSession, review_id: str) -> Optional[Dict[str, Any]]:
        """获取单条评论详情"""
        result = await db.execute(select(DianpingReview).where(DianpingReview.review_id == review_id))
        review = result.scalar_one_or_none()
        return self._to_dict(review) if review else None

    async def reply_review(
        self,
        db: AsyncSession,
        review_id: str,
        reply_content: str,
    ) -> Dict[str, Any]:
        """保存商家回复"""
        result = await db.execute(select(DianpingReview).where(DianpingReview.review_id == review_id))
        review = result.scalar_one_or_none()
        if not review:
            raise ValueError(f"评论不存在: {review_id}")

        review.reply_content = reply_content
        review.reply_date = datetime.now()
        review.is_read = True
        await db.commit()
        await db.refresh(review)

        logger.info("商家回复已保存", review_id=review_id)
        return self._to_dict(review)

    async def mark_read(self, db: AsyncSession, review_ids: List[str]) -> int:
        """批量标记为已读"""
        result = await db.execute(select(DianpingReview).where(DianpingReview.review_id.in_(review_ids)))
        reviews = result.scalars().all()
        count = 0
        for review in reviews:
            if not review.is_read:
                review.is_read = True
                count += 1
        await db.commit()
        return count

    async def analyze_sentiment(self, db: AsyncSession, review_id: str) -> Dict[str, Any]:
        """对单条评论进行情感分析"""
        result = await db.execute(select(DianpingReview).where(DianpingReview.review_id == review_id))
        review = result.scalar_one_or_none()
        if not review:
            raise ValueError(f"评论不存在: {review_id}")

        self._analyze_sentiment_for_review(review)
        await db.commit()
        await db.refresh(review)
        return self._to_dict(review)

    async def get_stats(self, db: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """获取品牌评论统计概览"""
        base_cond = DianpingReview.brand_id == brand_id

        # 总评论数 & 平均评分
        summary = await db.execute(
            select(
                func.count(DianpingReview.id).label("total"),
                func.avg(DianpingReview.rating).label("avg_rating"),
            ).where(base_cond)
        )
        row = summary.one()
        total = row.total or 0
        avg_rating = float(row.avg_rating) if row.avg_rating else 0.0

        # 情感分布
        sentiment_q = await db.execute(
            select(
                DianpingReview.sentiment,
                func.count(DianpingReview.id),
            )
            .where(base_cond)
            .group_by(DianpingReview.sentiment)
        )
        sentiment_dist = {s or "unknown": c for s, c in sentiment_q.all()}

        # 未读数
        unread_q = await db.execute(
            select(func.count(DianpingReview.id)).where(and_(base_cond, DianpingReview.is_read == False))
        )
        unread_count = unread_q.scalar() or 0

        # 近7天每日评论数趋势
        seven_days_ago = datetime.now() - timedelta(days=7)
        trend_q = await db.execute(
            select(
                func.date_trunc("day", DianpingReview.review_date).label("day"),
                func.count(DianpingReview.id).label("count"),
                func.avg(DianpingReview.rating).label("avg_r"),
            )
            .where(and_(base_cond, DianpingReview.review_date >= seven_days_ago))
            .group_by("day")
            .order_by("day")
        )
        trend = [
            {
                "date": str(r.day.date()) if r.day else None,
                "count": r.count,
                "avg_rating": round(float(r.avg_r), 2) if r.avg_r else 0,
            }
            for r in trend_q.all()
        ]

        return {
            "total_reviews": total,
            "avg_rating": round(avg_rating, 2),
            "sentiment_distribution": sentiment_dist,
            "unread_count": unread_count,
            "recent_trend": trend,
        }

    async def get_keyword_cloud(self, db: AsyncSession, brand_id: str) -> List[Dict[str, Any]]:
        """获取品牌关键词云数据（按频次排序）"""
        result = await db.execute(
            select(DianpingReview.keywords).where(
                and_(
                    DianpingReview.brand_id == brand_id,
                    DianpingReview.keywords.isnot(None),
                )
            )
        )
        # 汇总所有关键词频次
        freq: Dict[str, int] = {}
        for (kw_list,) in result.all():
            if isinstance(kw_list, list):
                for kw in kw_list:
                    freq[kw] = freq.get(kw, 0) + 1

        # 按频次降序，取前30
        sorted_kws = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:30]
        return [{"keyword": k, "count": v} for k, v in sorted_kws]

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _analyze_sentiment_for_review(self, review: DianpingReview) -> None:
        """基于关键词的简单情感分析"""
        content = review.content or ""
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in content)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in content)

        # 评分也作为情感信号
        if review.rating >= 4:
            pos_count += 1
        elif review.rating <= 2:
            neg_count += 1

        total = pos_count + neg_count
        if total == 0:
            review.sentiment = "neutral"
            review.sentiment_score = Decimal("0.5000")
        elif pos_count > neg_count:
            review.sentiment = "positive"
            score = min(pos_count / (total + 1), 1.0)
            review.sentiment_score = Decimal(str(round(0.5 + score * 0.5, 4)))
        else:
            review.sentiment = "negative"
            score = min(neg_count / (total + 1), 1.0)
            review.sentiment_score = Decimal(str(round(0.5 - score * 0.5, 4)))

        # 提取出现的关键词
        found_keywords = []
        for kw in POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS:
            if kw in content:
                found_keywords.append(kw)
        review.keywords = found_keywords if found_keywords else None

    @staticmethod
    def _to_dict(review: DianpingReview) -> Dict[str, Any]:
        """模型转字典"""
        return {
            "id": str(review.id),
            "brand_id": review.brand_id,
            "store_id": review.store_id,
            "review_id": review.review_id,
            "author_name": review.author_name,
            "author_avatar_url": review.author_avatar_url,
            "rating": review.rating,
            "content": review.content,
            "images": review.images,
            "review_date": review.review_date.isoformat() if review.review_date else None,
            "sentiment": review.sentiment,
            "sentiment_score": float(review.sentiment_score) if review.sentiment_score else None,
            "keywords": review.keywords,
            "reply_content": review.reply_content,
            "reply_date": review.reply_date.isoformat() if review.reply_date else None,
            "is_read": review.is_read,
            "source": review.source,
            "created_at": review.created_at.isoformat() if review.created_at else None,
        }
