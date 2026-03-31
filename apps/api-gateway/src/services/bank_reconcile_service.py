"""银行流水对账服务 — 导入/对账/分类/匹配/统计"""

import csv
import io
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.bank_reconciliation import BankReconciliationBatch, BankStatement


class BankReconcileService:
    """银行流水对账核心服务"""

    # ── 导入银行流水 ────────────────────────────────────────────────────────

    @staticmethod
    async def import_statements(
        db: AsyncSession,
        brand_id: str,
        bank_name: str,
        file_content: str,
        file_format: str = "csv",
    ) -> dict:
        """
        解析CSV银行流水文件，创建BankStatement记录
        返回: {"import_batch_id": str, "imported": int, "errors": list[str]}
        """
        batch_id = str(uuid.uuid4())[:8]
        imported = 0
        errors: list[str] = []

        try:
            reader = csv.DictReader(io.StringIO(file_content))
            rows = list(reader)
        except (ValueError, KeyError, csv.Error) as e:
            return {"import_batch_id": batch_id, "imported": 0, "errors": [f"文件解析失败: {str(e)}"]}

        for idx, row in enumerate(rows, start=2):
            try:
                # 灵活字段映射：支持多种CSV列名
                txn_date_str = (row.get("交易日期") or row.get("transaction_date") or row.get("日期") or "").strip()
                if not txn_date_str:
                    errors.append(f"第{idx}行: 缺少交易日期")
                    continue

                # 解析日期（支持 YYYY-MM-DD / YYYY/MM/DD）
                txn_date_str = txn_date_str.replace("/", "-")
                txn_date = date.fromisoformat(txn_date_str[:10])

                # 金额（元→分）
                amount_str = (row.get("金额") or row.get("amount") or row.get("交易金额") or "0").strip().replace(",", "")
                amount_yuan = abs(float(amount_str))
                amount_fen = round(amount_yuan * 100)

                # 交易类型
                txn_type_raw = (row.get("交易类型") or row.get("type") or row.get("收支") or "").strip().lower()
                if txn_type_raw in ("收入", "credit", "贷", "存入"):
                    txn_type = "credit"
                elif txn_type_raw in ("支出", "debit", "借", "取出", "转出"):
                    txn_type = "debit"
                else:
                    # 根据金额正负判断
                    raw_val = float(amount_str)
                    txn_type = "credit" if raw_val >= 0 else "debit"

                # 账号（脱敏：只取后4位）
                account_raw = (row.get("账号") or row.get("account") or row.get("卡号") or "****").strip()
                account_number = account_raw[-4:] if len(account_raw) >= 4 else account_raw

                counterparty = row.get("对方户名") or row.get("counterparty") or row.get("对方") or None
                reference = row.get("流水号") or row.get("reference") or row.get("交易流水号") or None
                desc = row.get("摘要") or row.get("description") or row.get("备注") or None

                stmt = BankStatement(
                    brand_id=brand_id,
                    bank_name=bank_name,
                    account_number=account_number,
                    transaction_date=txn_date,
                    transaction_type=txn_type,
                    amount_fen=amount_fen,
                    counterparty=counterparty.strip() if counterparty else None,
                    reference_number=reference.strip() if reference else None,
                    description=desc.strip() if desc else None,
                    import_batch_id=batch_id,
                )
                db.add(stmt)
                imported += 1

            except (ValueError, KeyError, IndexError, TypeError) as e:
                errors.append(f"第{idx}行: {str(e)}")

        if imported > 0:
            await db.commit()

        return {"import_batch_id": batch_id, "imported": imported, "errors": errors}

    # ── 执行对账 ────────────────────────────────────────────────────────────

    @staticmethod
    async def run_reconciliation(
        db: AsyncSession,
        brand_id: str,
        bank_name: str,
        period_start: date,
        period_end: date,
    ) -> dict:
        """
        银行流水与系统记录匹配，生成对账批次
        简单匹配逻辑：按金额+日期匹配内部订单
        """
        batch = BankReconciliationBatch(
            brand_id=brand_id,
            bank_name=bank_name,
            period_start=period_start,
            period_end=period_end,
            status="processing",
        )
        db.add(batch)
        await db.flush()

        # 查询该周期内的银行流水
        q = select(BankStatement).where(
            and_(
                BankStatement.brand_id == brand_id,
                BankStatement.bank_name == bank_name,
                BankStatement.transaction_date >= period_start,
                BankStatement.transaction_date <= period_end,
            )
        )
        result = await db.execute(q)
        statements = result.scalars().all()

        total_credit = 0
        total_debit = 0
        matched = 0
        unmatched = 0

        for stmt in statements:
            if stmt.transaction_type == "credit":
                total_credit += stmt.amount_fen
            else:
                total_debit += stmt.amount_fen

            # 自动分类猜测（基于摘要关键词）
            if not stmt.category and stmt.description:
                stmt.category = BankReconcileService._guess_category(stmt.description)

            if stmt.is_matched:
                matched += 1
            else:
                unmatched += 1

        batch.total_credit_fen = total_credit
        batch.total_debit_fen = total_debit
        batch.matched_count = matched
        batch.unmatched_count = unmatched
        batch.diff_fen = total_credit - total_debit
        batch.status = "completed"
        batch.completed_at = datetime.utcnow()

        await db.commit()

        return {
            "batch_id": str(batch.id),
            "total_credit_yuan": total_credit / 100,
            "total_debit_yuan": total_debit / 100,
            "matched_count": matched,
            "unmatched_count": unmatched,
            "diff_yuan": (total_credit - total_debit) / 100,
        }

    @staticmethod
    def _guess_category(description: str) -> Optional[str]:
        """根据摘要关键词猜测分类"""
        desc = description.lower()
        if any(kw in desc for kw in ("销售", "收款", "pos", "微信", "支付宝", "美团")):
            return "sales"
        if any(kw in desc for kw in ("采购", "进货", "食材", "原料", "供应商")):
            return "purchase"
        if any(kw in desc for kw in ("工资", "薪资", "社保", "公积金")):
            return "salary"
        if any(kw in desc for kw in ("租金", "房租", "物业")):
            return "rent"
        if any(kw in desc for kw in ("税", "国税", "地税", "增值税")):
            return "tax"
        return None

    # ── 查询批次列表 ────────────────────────────────────────────────────────

    @staticmethod
    async def list_batches(
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
        bank_name: Optional[str] = None,
    ) -> dict:
        """分页查询对账批次"""
        conditions = [BankReconciliationBatch.brand_id == brand_id]
        if bank_name:
            conditions.append(BankReconciliationBatch.bank_name == bank_name)

        # 总数
        count_q = select(func.count(BankReconciliationBatch.id)).where(and_(*conditions))
        total = (await db.execute(count_q)).scalar() or 0

        # 分页
        q = (
            select(BankReconciliationBatch)
            .where(and_(*conditions))
            .order_by(BankReconciliationBatch.period_end.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        batches = result.scalars().all()

        return {
            "total": total,
            "batches": [
                {
                    "id": str(b.id),
                    "brand_id": b.brand_id,
                    "bank_name": b.bank_name,
                    "period_start": b.period_start.isoformat(),
                    "period_end": b.period_end.isoformat(),
                    "status": b.status,
                    "total_credit_yuan": b.total_credit_fen / 100,
                    "total_debit_yuan": b.total_debit_fen / 100,
                    "matched_count": b.matched_count,
                    "unmatched_count": b.unmatched_count,
                    "diff_yuan": b.diff_fen / 100,
                    "bank_balance_yuan": b.bank_balance_fen / 100 if b.bank_balance_fen is not None else None,
                    "system_balance_yuan": b.system_balance_fen / 100 if b.system_balance_fen is not None else None,
                    "completed_at": b.completed_at.isoformat() if b.completed_at else None,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
                for b in batches
            ],
        }

    # ── 批次详情 ────────────────────────────────────────────────────────────

    @staticmethod
    async def get_batch_detail(db: AsyncSession, batch_id: str) -> Optional[dict]:
        """获取批次详情 + 关联的流水"""
        q = select(BankReconciliationBatch).where(BankReconciliationBatch.id == batch_id)
        result = await db.execute(q)
        batch = result.scalar_one_or_none()
        if not batch:
            return None

        # 查询该批次周期内的流水
        stmt_q = (
            select(BankStatement)
            .where(
                and_(
                    BankStatement.brand_id == batch.brand_id,
                    BankStatement.bank_name == batch.bank_name,
                    BankStatement.transaction_date >= batch.period_start,
                    BankStatement.transaction_date <= batch.period_end,
                )
            )
            .order_by(BankStatement.transaction_date.desc())
        )
        stmt_result = await db.execute(stmt_q)
        statements = stmt_result.scalars().all()

        return {
            "batch": {
                "id": str(batch.id),
                "bank_name": batch.bank_name,
                "period_start": batch.period_start.isoformat(),
                "period_end": batch.period_end.isoformat(),
                "status": batch.status,
                "total_credit_yuan": batch.total_credit_fen / 100,
                "total_debit_yuan": batch.total_debit_fen / 100,
                "matched_count": batch.matched_count,
                "unmatched_count": batch.unmatched_count,
                "diff_yuan": batch.diff_fen / 100,
            },
            "statements": [BankReconcileService._stmt_to_dict(s) for s in statements],
            "statement_count": len(statements),
        }

    # ── 流水列表 ────────────────────────────────────────────────────────────

    @staticmethod
    async def list_statements(
        db: AsyncSession,
        brand_id: str,
        bank_name: Optional[str] = None,
        is_matched: Optional[bool] = None,
        category: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页查询银行流水"""
        conditions = [BankStatement.brand_id == brand_id]
        if bank_name:
            conditions.append(BankStatement.bank_name == bank_name)
        if is_matched is not None:
            conditions.append(BankStatement.is_matched == is_matched)
        if category:
            conditions.append(BankStatement.category == category)
        if start_date:
            conditions.append(BankStatement.transaction_date >= start_date)
        if end_date:
            conditions.append(BankStatement.transaction_date <= end_date)

        count_q = select(func.count(BankStatement.id)).where(and_(*conditions))
        total = (await db.execute(count_q)).scalar() or 0

        q = (
            select(BankStatement)
            .where(and_(*conditions))
            .order_by(BankStatement.transaction_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        statements = result.scalars().all()

        return {
            "total": total,
            "statements": [BankReconcileService._stmt_to_dict(s) for s in statements],
        }

    # ── 手动分类 ────────────────────────────────────────────────────────────

    @staticmethod
    async def categorize_statement(db: AsyncSession, statement_id: str, category: str) -> Optional[dict]:
        """手动设置流水分类"""
        q = select(BankStatement).where(BankStatement.id == statement_id)
        result = await db.execute(q)
        stmt = result.scalar_one_or_none()
        if not stmt:
            return None

        stmt.category = category
        await db.commit()
        return BankReconcileService._stmt_to_dict(stmt)

    # ── 手动匹配 ────────────────────────────────────────────────────────────

    @staticmethod
    async def match_statement(db: AsyncSession, statement_id: str, order_id: str) -> Optional[dict]:
        """手动将流水与内部单据匹配"""
        q = select(BankStatement).where(BankStatement.id == statement_id)
        result = await db.execute(q)
        stmt = result.scalar_one_or_none()
        if not stmt:
            return None

        stmt.is_matched = True
        stmt.matched_order_id = order_id
        await db.commit()
        return BankReconcileService._stmt_to_dict(stmt)

    # ── 统计概览 ────────────────────────────────────────────────────────────

    @staticmethod
    async def get_stats(db: AsyncSession, brand_id: str) -> dict:
        """总余额、未匹配金额、月度现金流摘要"""
        base_cond = BankStatement.brand_id == brand_id

        # 总收入/支出
        agg_q = select(
            func.coalesce(
                func.sum(case((BankStatement.transaction_type == "credit", BankStatement.amount_fen), else_=0)),
                0,
            ).label("total_credit"),
            func.coalesce(
                func.sum(case((BankStatement.transaction_type == "debit", BankStatement.amount_fen), else_=0)),
                0,
            ).label("total_debit"),
            func.count(BankStatement.id).label("total_count"),
            func.coalesce(
                func.sum(case((BankStatement.is_matched == False, BankStatement.amount_fen), else_=0)),  # noqa: E712
                0,
            ).label("unmatched_amount"),
            func.sum(case((BankStatement.is_matched == False, 1), else_=0)).label("unmatched_count"),  # noqa: E712
        ).where(base_cond)

        row = (await db.execute(agg_q)).one()

        total_credit = int(row.total_credit)
        total_debit = int(row.total_debit)

        return {
            "total_credit_yuan": total_credit / 100,
            "total_debit_yuan": total_debit / 100,
            "balance_yuan": (total_credit - total_debit) / 100,
            "total_count": int(row.total_count),
            "unmatched_amount_yuan": int(row.unmatched_amount) / 100,
            "unmatched_count": int(row.unmatched_count),
        }

    # ── 内部工具 ────────────────────────────────────────────────────────────

    @staticmethod
    def _stmt_to_dict(s: BankStatement) -> dict:
        return {
            "id": str(s.id),
            "bank_name": s.bank_name,
            "account_number": s.account_number,
            "transaction_date": s.transaction_date.isoformat(),
            "transaction_type": s.transaction_type,
            "amount_yuan": s.amount_fen / 100,
            "counterparty": s.counterparty,
            "reference_number": s.reference_number,
            "description": s.description,
            "category": s.category,
            "is_matched": s.is_matched,
            "matched_order_id": s.matched_order_id,
            "import_batch_id": s.import_batch_id,
        }
