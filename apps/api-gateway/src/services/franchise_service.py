"""
加盟商管理服务
处理加盟商注册、合同管理、月度提成计算、逾期检查
"""

import random
import string
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crypto import field_crypto
from src.models.franchise import (
    FranchiseContract,
    FranchiseRoyalty,
    Franchisee,
    FranchiseePortalAccess,
)

logger = structlog.get_logger()


def _generate_contract_no(franchisee_id: str, brand_id: str) -> str:
    """生成合同编号：FC-{品牌前缀}-{年月}-{随机4位}"""
    ym = datetime.utcnow().strftime("%Y%m")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    brand_prefix = (brand_id[:4]).upper() if len(brand_id) >= 4 else brand_id.upper()
    return f"FC-{brand_prefix}-{ym}-{suffix}"


def _calc_royalty_fen(gross_revenue_fen: int, royalty_rate: float) -> int:
    """精确计算提成：先 float 乘法，再 round 到整数分，避免浮点累积误差"""
    return round(float(gross_revenue_fen) * float(royalty_rate))


class FranchiseService:
    """加盟商管理服务"""

    # ------------------------------------------------------------------ #
    # 加盟商管理
    # ------------------------------------------------------------------ #

    async def create_franchisee(
        self,
        db: AsyncSession,
        brand_id: str,
        company_name: str,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        bank_account: Optional[str] = None,
        tax_no: Optional[str] = None,
    ) -> Dict[str, Any]:
        """注册新加盟商。bank_account 存储前使用 AES-256-GCM 加密。"""
        # 银行账号加密存储
        encrypted_bank = field_crypto.encrypt(bank_account) if bank_account else None

        franchisee = Franchisee(
            brand_id=brand_id,
            company_name=company_name,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            bank_account=encrypted_bank,
            tax_no=tax_no,
            status="active",
        )
        db.add(franchisee)
        await db.flush()
        await db.refresh(franchisee)

        result = franchisee.to_dict()
        # 返回脱敏银行账号（不暴露原文或密文）
        if bank_account:
            result["bank_account_masked"] = field_crypto.mask(bank_account, "bank_account")
        logger.info("加盟商已创建", franchisee_id=str(franchisee.id), company=company_name)
        return result

    async def list_franchisees(
        self,
        db: AsyncSession,
        brand_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """获取品牌下加盟商列表"""
        query = select(Franchisee).where(Franchisee.brand_id == brand_id)
        if status:
            query = query.where(Franchisee.status == status)
        query = query.order_by(Franchisee.created_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        items = result.scalars().all()

        count_query = select(func.count(Franchisee.id)).where(Franchisee.brand_id == brand_id)
        if status:
            count_query = count_query.where(Franchisee.status == status)
        count_result = await db.execute(count_query)
        total = count_result.scalar_one()

        return {
            "items": [f.to_dict() for f in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_franchisee(
        self, db: AsyncSession, franchisee_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取加盟商详情"""
        result = await db.execute(
            select(Franchisee).where(Franchisee.id == franchisee_id)
        )
        franchisee = result.scalar_one_or_none()
        if not franchisee:
            return None
        return franchisee.to_dict()

    # ------------------------------------------------------------------ #
    # 合同管理
    # ------------------------------------------------------------------ #

    async def create_contract(
        self,
        db: AsyncSession,
        franchisee_id: str,
        brand_id: str,
        store_id: Optional[str],
        contract_type: str,
        franchise_fee_fen: int,
        royalty_rate: float,
        marketing_fund_rate: float,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """签订加盟合同，自动生成合同编号"""
        if start_date >= end_date:
            raise ValueError("合同结束日期必须晚于开始日期")

        contract_no = _generate_contract_no(str(franchisee_id), brand_id)
        # 保证合同编号唯一（最多重试 5 次）
        for _ in range(5):
            existing = await db.execute(
                select(FranchiseContract).where(FranchiseContract.contract_no == contract_no)
            )
            if not existing.scalar_one_or_none():
                break
            contract_no = _generate_contract_no(str(franchisee_id), brand_id)

        contract = FranchiseContract(
            franchisee_id=franchisee_id,
            brand_id=brand_id,
            store_id=store_id,
            contract_no=contract_no,
            contract_type=contract_type,
            franchise_fee_fen=franchise_fee_fen,
            royalty_rate=royalty_rate,
            marketing_fund_rate=marketing_fund_rate,
            start_date=start_date,
            end_date=end_date,
            status="draft",
        )
        db.add(contract)
        await db.flush()
        await db.refresh(contract)

        logger.info(
            "加盟合同已创建",
            contract_id=str(contract.id),
            contract_no=contract_no,
            franchisee_id=str(franchisee_id),
        )
        return contract.to_dict()

    async def get_contract(
        self, db: AsyncSession, contract_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取合同详情"""
        result = await db.execute(
            select(FranchiseContract).where(FranchiseContract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        if not contract:
            return None
        return contract.to_dict()

    async def renew_contract(
        self,
        db: AsyncSession,
        contract_id: str,
        new_end_date: date,
        updated_terms: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """合同续签：更新到期日，可选更新费率条款，renewal_count +1"""
        result = await db.execute(
            select(FranchiseContract).where(FranchiseContract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise ValueError(f"合同不存在: {contract_id}")
        if contract.status == "terminated":
            raise ValueError("已终止的合同不能续签")

        contract.end_date = new_end_date
        contract.renewal_count = (contract.renewal_count or 0) + 1
        if updated_terms:
            if "royalty_rate" in updated_terms:
                contract.royalty_rate = float(updated_terms["royalty_rate"])
            if "marketing_fund_rate" in updated_terms:
                contract.marketing_fund_rate = float(updated_terms["marketing_fund_rate"])
            if "franchise_fee_fen" in updated_terms:
                contract.franchise_fee_fen = int(updated_terms["franchise_fee_fen"])
        contract.status = "active"

        await db.flush()
        await db.refresh(contract)
        logger.info(
            "合同续签成功",
            contract_id=contract_id,
            new_end_date=str(new_end_date),
            renewal_count=contract.renewal_count,
        )
        return contract.to_dict()

    # ------------------------------------------------------------------ #
    # 提成计算与结算
    # ------------------------------------------------------------------ #

    async def calculate_monthly_royalty(
        self,
        db: AsyncSession,
        contract_id: str,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """
        计算月度提成：
        1. 查询该门店该月总营收（从 orders 表聚合）
        2. 计算 royalty = gross_revenue * royalty_rate
        3. 计算 marketing_fund = gross_revenue * marketing_fund_rate
        4. 创建/更新 FranchiseRoyalty 记录（status=pending）
        5. 返回计算明细
        """
        # 获取合同信息
        contract_result = await db.execute(
            select(FranchiseContract).where(FranchiseContract.id == contract_id)
        )
        contract = contract_result.scalar_one_or_none()
        if not contract:
            raise ValueError(f"合同不存在: {contract_id}")
        if not contract.store_id:
            raise ValueError(f"合同 {contract_id} 未关联门店，无法计算提成")

        # 从 orders 表聚合月度营收（按 store_id + 创建月份）
        # 使用参数化查询，严格遵守安全规范
        revenue_sql = text(
            """
            SELECT COALESCE(SUM(final_amount), 0) AS total_fen
            FROM orders
            WHERE store_id = :store_id
              AND EXTRACT(YEAR  FROM created_at) = :year
              AND EXTRACT(MONTH FROM created_at) = :month
              AND status NOT IN ('cancelled', 'refunded')
            """
        )
        rev_result = await db.execute(
            revenue_sql,
            {"store_id": contract.store_id, "year": year, "month": month},
        )
        gross_revenue_fen = int(rev_result.scalar_one() or 0)

        # 精确提成计算（先 float，再 round 到整数分）
        royalty_amount_fen = _calc_royalty_fen(gross_revenue_fen, contract.royalty_rate)
        marketing_fund_fen = _calc_royalty_fen(gross_revenue_fen, contract.marketing_fund_rate)
        total_due_fen = royalty_amount_fen + marketing_fund_fen

        # 设置账期（次月 15 日为默认结算日）
        if month == 12:
            due_date = date(year + 1, 1, 15)
        else:
            due_date = date(year, month + 1, 15)

        # 检查是否已有记录（幂等）
        existing_result = await db.execute(
            select(FranchiseRoyalty).where(
                and_(
                    FranchiseRoyalty.contract_id == contract_id,
                    FranchiseRoyalty.period_year == year,
                    FranchiseRoyalty.period_month == month,
                )
            )
        )
        royalty = existing_result.scalar_one_or_none()

        if royalty:
            # 已存在则更新（重算）
            if royalty.status in ("paid",):
                raise ValueError(f"该期提成已支付，不能重新计算: {year}-{month:02d}")
            royalty.gross_revenue_fen = gross_revenue_fen
            royalty.royalty_amount_fen = royalty_amount_fen
            royalty.marketing_fund_fen = marketing_fund_fen
            royalty.total_due_fen = total_due_fen
            royalty.due_date = due_date
        else:
            royalty = FranchiseRoyalty(
                contract_id=contract_id,
                franchisee_id=contract.franchisee_id,
                store_id=contract.store_id,
                period_year=year,
                period_month=month,
                gross_revenue_fen=gross_revenue_fen,
                royalty_amount_fen=royalty_amount_fen,
                marketing_fund_fen=marketing_fund_fen,
                total_due_fen=total_due_fen,
                status="pending",
                due_date=due_date,
            )
            db.add(royalty)

        await db.flush()
        await db.refresh(royalty)

        logger.info(
            "月度提成计算完成",
            contract_id=contract_id,
            period=f"{year}-{month:02d}",
            gross_revenue_yuan=round(gross_revenue_fen / 100, 2),
            royalty_yuan=round(royalty_amount_fen / 100, 2),
            total_due_yuan=round(total_due_fen / 100, 2),
        )
        return royalty.to_dict()

    async def mark_royalty_paid(
        self,
        db: AsyncSession,
        royalty_id: str,
        payment_reference: str,
    ) -> Dict[str, Any]:
        """标记提成已收到，记录付款凭证号"""
        result = await db.execute(
            select(FranchiseRoyalty).where(FranchiseRoyalty.id == royalty_id)
        )
        royalty = result.scalar_one_or_none()
        if not royalty:
            raise ValueError(f"提成记录不存在: {royalty_id}")
        if royalty.status == "paid":
            raise ValueError(f"该提成记录已标记为已付: {royalty_id}")

        royalty.status = "paid"
        royalty.paid_at = datetime.utcnow()
        royalty.payment_reference = payment_reference

        await db.flush()
        await db.refresh(royalty)

        logger.info(
            "提成已标记为已付",
            royalty_id=royalty_id,
            payment_reference=payment_reference,
            total_yuan=round(royalty.total_due_fen / 100, 2),
        )
        return royalty.to_dict()

    async def get_royalty_history(
        self,
        db: AsyncSession,
        contract_id: str,
        months: int = 12,
    ) -> List[Dict[str, Any]]:
        """获取合同近 N 个月的提成历史（含支付状态）"""
        result = await db.execute(
            select(FranchiseRoyalty)
            .where(FranchiseRoyalty.contract_id == contract_id)
            .order_by(FranchiseRoyalty.period_year.desc(), FranchiseRoyalty.period_month.desc())
            .limit(months)
        )
        items = result.scalars().all()
        return [r.to_dict() for r in items]

    # ------------------------------------------------------------------ #
    # 逾期检查（Celery 定时任务调用）
    # ------------------------------------------------------------------ #

    async def check_overdue_royalties(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        将所有 due_date < today 且 status=pending 的提成标记为 overdue。
        返回逾期记录列表（供告警推送使用）。
        """
        today = date.today()
        result = await db.execute(
            select(FranchiseRoyalty).where(
                and_(
                    FranchiseRoyalty.status == "pending",
                    FranchiseRoyalty.due_date < today,
                )
            )
        )
        overdue_items = result.scalars().all()

        updated = []
        for item in overdue_items:
            item.status = "overdue"
            updated.append(item.to_dict())

        if updated:
            await db.flush()
            logger.warning(
                "逾期提成已批量更新",
                count=len(updated),
                total_overdue_yuan=round(sum(i["total_due_fen"] for i in updated) / 100, 2),
            )
        return updated

    # ------------------------------------------------------------------ #
    # 仪表盘聚合（BFF）
    # ------------------------------------------------------------------ #

    async def get_franchisee_dashboard(
        self, db: AsyncSession, franchisee_id: str
    ) -> Dict[str, Any]:
        """
        加盟商视角仪表盘（BFF 聚合）：
        - 旗下门店列表及近 30 日营收
        - 待支付提成总额
        - 合同到期预警（90 天内）
        - 最近结算记录
        """
        today = date.today()
        warning_date = today + timedelta(days=90)

        # 1. 获取加盟商名下合同
        contracts_result = await db.execute(
            select(FranchiseContract).where(
                and_(
                    FranchiseContract.franchisee_id == franchisee_id,
                    FranchiseContract.status.in_(["active", "signed"]),
                )
            )
        )
        contracts = contracts_result.scalars().all()
        store_ids = [c.store_id for c in contracts if c.store_id]
        contract_ids = [str(c.id) for c in contracts]

        # 2. 待支付提成总额
        pending_result = await db.execute(
            select(func.coalesce(func.sum(FranchiseRoyalty.total_due_fen), 0)).where(
                and_(
                    FranchiseRoyalty.franchisee_id == franchisee_id,
                    FranchiseRoyalty.status.in_(["pending", "overdue"]),
                )
            )
        )
        pending_total_fen = int(pending_result.scalar_one() or 0)

        # 3. 合同到期预警（90 天内到期）
        expiring_contracts = [
            c.to_dict()
            for c in contracts
            if c.end_date and today <= c.end_date <= warning_date
        ]

        # 4. 最近 6 条结算记录
        recent_result = await db.execute(
            select(FranchiseRoyalty)
            .where(FranchiseRoyalty.franchisee_id == franchisee_id)
            .order_by(FranchiseRoyalty.period_year.desc(), FranchiseRoyalty.period_month.desc())
            .limit(6)
        )
        recent_royalties = [r.to_dict() for r in recent_result.scalars().all()]

        # 5. 近 30 日各门店营收（从 orders 聚合）
        store_revenues = []
        if store_ids:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            rev_sql = text(
                """
                SELECT store_id,
                       COALESCE(SUM(final_amount), 0) AS total_fen,
                       COUNT(*) AS order_count
                FROM orders
                WHERE store_id = ANY(:store_ids)
                  AND created_at >= :since
                  AND status NOT IN ('cancelled', 'refunded')
                GROUP BY store_id
                """
            )
            rev_result = await db.execute(
                rev_sql, {"store_ids": store_ids, "since": thirty_days_ago}
            )
            for row in rev_result.fetchall():
                store_revenues.append(
                    {
                        "store_id": row.store_id,
                        "revenue_30d_fen": int(row.total_fen),
                        "revenue_30d_yuan": round(float(row.total_fen) / 100, 2),
                        "order_count_30d": int(row.order_count),
                    }
                )

        return {
            "franchisee_id": franchisee_id,
            "active_contracts": len(contracts),
            "store_ids": store_ids,
            "pending_royalty_fen": pending_total_fen,
            "pending_royalty_yuan": round(pending_total_fen / 100, 2),
            "expiring_contracts_90d": expiring_contracts,
            "recent_royalties": recent_royalties,
            "store_revenues_30d": store_revenues,
            "as_of": datetime.utcnow().isoformat(),
        }

    async def get_brand_franchise_overview(
        self, db: AsyncSession, brand_id: str
    ) -> Dict[str, Any]:
        """
        品牌方视角：所有加盟商总览
        - 加盟商数量/活跃数
        - 本月应收提成合计
        - 逾期未付加盟商
        - 合同到期预警（90 天内）
        """
        today = date.today()
        warning_date = today + timedelta(days=90)
        current_year = today.year
        current_month = today.month

        # 加盟商统计
        total_result = await db.execute(
            select(func.count(Franchisee.id)).where(Franchisee.brand_id == brand_id)
        )
        total_franchisees = int(total_result.scalar_one() or 0)

        active_result = await db.execute(
            select(func.count(Franchisee.id)).where(
                and_(Franchisee.brand_id == brand_id, Franchisee.status == "active")
            )
        )
        active_franchisees = int(active_result.scalar_one() or 0)

        # 本月应收提成（从 franchise_royalties 聚合）
        monthly_sql = text(
            """
            SELECT COALESCE(SUM(fr.total_due_fen), 0) AS total_fen
            FROM franchise_royalties fr
            JOIN franchise_contracts fc ON fc.id = fr.contract_id
            WHERE fc.brand_id = :brand_id
              AND fr.period_year  = :year
              AND fr.period_month = :month
            """
        )
        monthly_result = await db.execute(
            monthly_sql,
            {"brand_id": brand_id, "year": current_year, "month": current_month},
        )
        monthly_due_fen = int(monthly_result.scalar_one() or 0)

        # 逾期未付（status=overdue 且 brand 下）
        overdue_sql = text(
            """
            SELECT COUNT(DISTINCT fr.franchisee_id) AS cnt,
                   COALESCE(SUM(fr.total_due_fen), 0) AS total_fen
            FROM franchise_royalties fr
            JOIN franchise_contracts fc ON fc.id = fr.contract_id
            WHERE fc.brand_id = :brand_id
              AND fr.status = 'overdue'
            """
        )
        overdue_result = await db.execute(overdue_sql, {"brand_id": brand_id})
        overdue_row = overdue_result.fetchone()
        overdue_franchisee_count = int(overdue_row.cnt or 0) if overdue_row else 0
        overdue_total_fen = int(overdue_row.total_fen or 0) if overdue_row else 0

        # 合同到期预警（90 天内）
        expiring_result = await db.execute(
            select(FranchiseContract).where(
                and_(
                    FranchiseContract.brand_id == brand_id,
                    FranchiseContract.status.in_(["active", "signed"]),
                    FranchiseContract.end_date >= today,
                    FranchiseContract.end_date <= warning_date,
                )
            )
        )
        expiring_contracts = [c.to_dict() for c in expiring_result.scalars().all()]

        return {
            "brand_id": brand_id,
            "total_franchisees": total_franchisees,
            "active_franchisees": active_franchisees,
            "monthly_due_fen": monthly_due_fen,
            "monthly_due_yuan": round(monthly_due_fen / 100, 2),
            "overdue_franchisee_count": overdue_franchisee_count,
            "overdue_total_fen": overdue_total_fen,
            "overdue_total_yuan": round(overdue_total_fen / 100, 2),
            "expiring_contracts_90d": expiring_contracts,
            "as_of": datetime.utcnow().isoformat(),
        }
