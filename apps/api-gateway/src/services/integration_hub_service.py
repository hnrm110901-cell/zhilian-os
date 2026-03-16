"""
Integration Hub Service
集成中心服务 — 统一管理所有外部集成的健康状态和同步记录
"""

import os
from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.integration_hub import IntegrationHubStatus

logger = structlog.get_logger()

# ── 默认集成注册表 ────────────────────────────────────────────────────────────
# 15 个预置集成，自动写入数据库

INTEGRATION_REGISTRY: list[dict] = [
    # POS 适配器
    {"key": "pinzhi", "name": "品智收银", "category": "pos"},
    {"key": "tiancai", "name": "天财商龙", "category": "pos"},
    {"key": "aoqiwei", "name": "奥琦玮", "category": "pos"},
    {"key": "meituan", "name": "美团SaaS", "category": "pos"},
    # 外卖渠道
    {"key": "eleme", "name": "饿了么", "category": "channel"},
    {"key": "douyin", "name": "抖音", "category": "channel"},
    # 财务对账
    {"key": "nuonuo", "name": "诺诺发票", "category": "financial"},
    {"key": "payment_recon", "name": "支付对账", "category": "financial"},
    {"key": "bank_recon", "name": "银行对账", "category": "financial"},
    # 合规管理
    {"key": "food_safety", "name": "食品安全", "category": "compliance"},
    {"key": "health_certs", "name": "健康证", "category": "compliance"},
    # 评论监控
    {"key": "dianping", "name": "大众点评", "category": "review"},
    # 采购供应
    {"key": "supplier_b2b", "name": "供应商B2B", "category": "procurement"},
    # IM 集成
    {"key": "wechat_work", "name": "企业微信", "category": "im"},
    {"key": "dingtalk", "name": "钉钉", "category": "im"},
]

# 每个集成对应的环境变量，用于健康检查时判断配置是否完成
_ENV_VAR_MAP: dict[str, list[str]] = {
    "pinzhi": ["PINZHI_API_KEY"],
    "tiancai": ["TIANCAI_APP_KEY", "TIANCAI_APP_SECRET"],
    "aoqiwei": ["AOQIWEI_APP_KEY", "AOQIWEI_APP_SECRET"],
    "meituan": ["MEITUAN_APP_KEY"],
    "eleme": ["ELEME_APP_KEY", "ELEME_APP_SECRET"],
    "douyin": ["DOUYIN_APP_KEY", "DOUYIN_APP_SECRET"],
    "nuonuo": ["NUONUO_APP_KEY"],
    "payment_recon": ["PAYMENT_RECON_ENABLED"],
    "bank_recon": ["BANK_RECON_ENABLED"],
    "food_safety": ["FOOD_SAFETY_API_KEY"],
    "health_certs": ["HEALTH_CERT_API_KEY"],
    "dianping": ["DIANPING_APP_KEY"],
    "supplier_b2b": ["SUPPLIER_B2B_API_KEY"],
    "wechat_work": ["WECHAT_WORK_CORP_ID", "WECHAT_WORK_AGENT_SECRET"],
    "dingtalk": ["DINGTALK_APP_KEY", "DINGTALK_APP_SECRET"],
}

# 分类中文名
CATEGORY_LABELS: dict[str, str] = {
    "pos": "POS适配器",
    "channel": "外卖渠道",
    "financial": "财务对账",
    "compliance": "合规管理",
    "review": "评论监控",
    "procurement": "采购供应",
    "im": "IM集成",
}


class IntegrationHubService:
    """集成中心核心服务"""

    async def _ensure_defaults(self, db: AsyncSession) -> None:
        """确保默认集成记录存在，不存在则批量创建"""
        result = await db.execute(select(IntegrationHubStatus.integration_key))
        existing_keys = {row[0] for row in result.fetchall()}

        new_records = []
        for entry in INTEGRATION_REGISTRY:
            if entry["key"] not in existing_keys:
                new_records.append(
                    IntegrationHubStatus(
                        integration_key=entry["key"],
                        display_name=entry["name"],
                        category=entry["category"],
                        status="not_configured",
                    )
                )

        if new_records:
            db.add_all(new_records)
            await db.flush()
            logger.info("integration_hub.defaults_created", count=len(new_records))

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def get_all_statuses(self, db: AsyncSession) -> list[dict]:
        """获取所有集成状态，自动补齐缺失的默认条目"""
        await self._ensure_defaults(db)
        result = await db.execute(
            select(IntegrationHubStatus).order_by(
                IntegrationHubStatus.category,
                IntegrationHubStatus.display_name,
            )
        )
        rows = result.scalars().all()
        return [r.to_dict() for r in rows]

    async def get_dashboard_summary(self, db: AsyncSession) -> dict:
        """仪表盘概览：总数、各状态计数、24h 同步量、Top 错误"""
        await self._ensure_defaults(db)

        result = await db.execute(select(IntegrationHubStatus))
        rows = result.scalars().all()

        total = len(rows)
        healthy = sum(1 for r in rows if r.status == "healthy")
        degraded = sum(1 for r in rows if r.status == "degraded")
        error = sum(1 for r in rows if r.status == "error")
        disconnected = sum(1 for r in rows if r.status == "disconnected")
        not_configured = sum(1 for r in rows if r.status == "not_configured")

        total_syncs_today = sum(r.sync_count_today for r in rows)
        total_errors_today = sum(r.error_count_today for r in rows)

        # 最近错误（按 last_error_at 倒序，取前 10）
        recent_errors = sorted(
            [r for r in rows if r.last_error_at],
            key=lambda r: r.last_error_at,
            reverse=True,
        )[:10]

        return {
            "total": total,
            "healthy": healthy,
            "degraded": degraded,
            "error": error,
            "disconnected": disconnected,
            "not_configured": not_configured,
            "total_syncs_today": total_syncs_today,
            "total_errors_today": total_errors_today,
            "recent_errors": [
                {
                    "integration_key": r.integration_key,
                    "display_name": r.display_name,
                    "error_message": r.last_error_message,
                    "error_at": r.last_error_at.isoformat() if r.last_error_at else None,
                }
                for r in recent_errors
            ],
        }

    async def get_category_summary(self, db: AsyncSession) -> list[dict]:
        """按分类汇总健康状态"""
        await self._ensure_defaults(db)

        result = await db.execute(select(IntegrationHubStatus))
        rows = result.scalars().all()

        categories: dict[str, dict] = {}
        for r in rows:
            cat = r.category
            if cat not in categories:
                categories[cat] = {
                    "category": cat,
                    "label": CATEGORY_LABELS.get(cat, cat),
                    "total": 0,
                    "healthy": 0,
                    "degraded": 0,
                    "error": 0,
                    "disconnected": 0,
                    "not_configured": 0,
                    "integrations": [],
                }
            bucket = categories[cat]
            bucket["total"] += 1
            if r.status in bucket:
                bucket[r.status] += 1
            bucket["integrations"].append(r.to_dict())

        return list(categories.values())

    # ── 写入 ──────────────────────────────────────────────────────────────────

    async def update_status(
        self,
        db: AsyncSession,
        key: str,
        status: str,
        error_msg: Optional[str] = None,
    ) -> dict:
        """更新指定集成的状态"""
        result = await db.execute(select(IntegrationHubStatus).where(IntegrationHubStatus.integration_key == key))
        row = result.scalar_one_or_none()
        if not row:
            raise ValueError(f"未知的集成标识: {key}")

        row.status = status
        if error_msg:
            row.last_error_message = error_msg
            row.last_error_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()

        await db.flush()
        return row.to_dict()

    async def record_sync(
        self,
        db: AsyncSession,
        key: str,
        success: bool,
        error_msg: Optional[str] = None,
    ) -> dict:
        """记录一次同步事件（成功或失败）"""
        result = await db.execute(select(IntegrationHubStatus).where(IntegrationHubStatus.integration_key == key))
        row = result.scalar_one_or_none()
        if not row:
            raise ValueError(f"未知的集成标识: {key}")

        now = datetime.utcnow()
        row.sync_count_today += 1

        if success:
            row.last_sync_at = now
            row.status = "healthy"
        else:
            row.error_count_today += 1
            row.last_error_at = now
            row.last_error_message = error_msg
            # 连续错误过多则降级
            if row.error_count_today >= 10:
                row.status = "error"
            elif row.error_count_today >= 3:
                row.status = "degraded"

        row.updated_at = now
        await db.flush()
        return row.to_dict()

    async def health_check_all(self, db: AsyncSession) -> list[dict]:
        """
        全量健康探测：
        1. 检查环境变量是否配置齐全（config_complete）
        2. 对已配置的集成，检查最后同步时间是否超过阈值
        """
        await self._ensure_defaults(db)
        result = await db.execute(select(IntegrationHubStatus))
        rows = result.scalars().all()

        now = datetime.utcnow()
        results = []

        for row in rows:
            # 检查环境变量
            env_vars = _ENV_VAR_MAP.get(row.integration_key, [])
            config_ok = all(os.environ.get(v) for v in env_vars) if env_vars else False
            row.config_complete = config_ok

            if not config_ok:
                row.status = "not_configured"
            elif row.last_sync_at:
                # 超过 1 小时无同步视为 degraded，超过 4 小时视为 disconnected
                age = now - row.last_sync_at
                if age > timedelta(hours=4):
                    row.status = "disconnected"
                elif age > timedelta(hours=1):
                    row.status = "degraded"
                elif row.error_count_today == 0:
                    row.status = "healthy"
            else:
                # 已配置但从未同步
                row.status = "disconnected"

            row.updated_at = now
            results.append(row.to_dict())

        await db.flush()
        logger.info("integration_hub.health_check_complete", count=len(results))
        return results

    async def reset_daily_counts(self, db: AsyncSession) -> int:
        """重置每日计数器（凌晨定时调用）"""
        stmt = update(IntegrationHubStatus).values(sync_count_today=0, error_count_today=0, updated_at=datetime.utcnow())
        result = await db.execute(stmt)
        await db.flush()
        count = result.rowcount
        logger.info("integration_hub.daily_counts_reset", rows=count)
        return count


# 模块级单例
integration_hub_service = IntegrationHubService()
