"""
挂账管理服务
管理客户挂账（赊账）、还款、额度控制、对账单生成
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class AccountStatus(str, Enum):
    """挂账账户状态"""
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class TransactionType(str, Enum):
    """交易类型"""
    CHARGE = "charge"      # 挂账消费
    PAYMENT = "payment"    # 还款
    ADJUSTMENT = "adjustment"  # 调账


@dataclass
class CreditTransaction:
    """挂账交易记录"""
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str = ""
    transaction_type: TransactionType = TransactionType.CHARGE
    amount_fen: int = 0  # 金额（分）
    balance_after_fen: int = 0  # 交易后余额（分）
    order_id: str = ""  # 关联订单号
    operator_id: str = ""
    note: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def amount_yuan(self) -> float:
        return round(self.amount_fen / 100, 2)

    @property
    def balance_after_yuan(self) -> float:
        return round(self.balance_after_fen / 100, 2)


@dataclass
class CreditAccount:
    """挂账账户"""
    account_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    customer_name: str = ""
    customer_phone: str = ""
    company_name: str = ""  # 单位名称（企业挂账）
    credit_limit_fen: int = 0  # 授信额度（分）
    balance_fen: int = 0  # 当前欠款余额（分），正值表示欠款
    status: AccountStatus = AccountStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_charge_at: Optional[datetime] = None
    last_payment_at: Optional[datetime] = None

    @property
    def credit_limit_yuan(self) -> float:
        return round(self.credit_limit_fen / 100, 2)

    @property
    def balance_yuan(self) -> float:
        return round(self.balance_fen / 100, 2)

    @property
    def available_fen(self) -> int:
        """可用额度（分）"""
        return max(0, self.credit_limit_fen - self.balance_fen)

    @property
    def available_yuan(self) -> float:
        return round(self.available_fen / 100, 2)


class CreditAccountService:
    """挂账管理服务"""

    def __init__(self):
        self._accounts: Dict[str, CreditAccount] = {}
        self._transactions: Dict[str, List[CreditTransaction]] = {}

    def create_account(
        self,
        store_id: str,
        customer_name: str,
        credit_limit_fen: int,
        customer_phone: str = "",
        company_name: str = "",
    ) -> CreditAccount:
        """创建挂账账户"""
        if credit_limit_fen <= 0:
            raise ValueError("授信额度必须大于0")
        account = CreditAccount(
            store_id=store_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            company_name=company_name,
            credit_limit_fen=credit_limit_fen,
        )
        self._accounts[account.account_id] = account
        self._transactions[account.account_id] = []
        logger.info("创建挂账账户", account_id=account.account_id, customer=customer_name,
                     limit_yuan=account.credit_limit_yuan)
        return account

    def charge_to_account(
        self,
        account_id: str,
        amount_fen: int,
        order_id: str = "",
        operator_id: str = "",
        note: str = "",
    ) -> CreditTransaction:
        """
        挂账消费（检查额度）
        :raises ValueError: 额度不足或账户冻结
        """
        account = self._get_account(account_id)
        if account.status == AccountStatus.FROZEN:
            raise ValueError("账户已冻结，无法挂账")
        if account.status == AccountStatus.CLOSED:
            raise ValueError("账户已关闭")
        if amount_fen <= 0:
            raise ValueError("挂账金额必须大于0")
        if amount_fen > account.available_fen:
            raise ValueError(
                f"额度不足: 可用{account.available_yuan}元, 需要{round(amount_fen/100,2)}元"
            )

        account.balance_fen += amount_fen
        account.last_charge_at = datetime.now(timezone.utc)

        txn = CreditTransaction(
            account_id=account_id,
            transaction_type=TransactionType.CHARGE,
            amount_fen=amount_fen,
            balance_after_fen=account.balance_fen,
            order_id=order_id,
            operator_id=operator_id,
            note=note,
        )
        self._transactions[account_id].append(txn)
        logger.info("挂账消费", account_id=account_id, amount_yuan=txn.amount_yuan,
                     balance_yuan=account.balance_yuan)
        return txn

    def record_payment(
        self,
        account_id: str,
        amount_fen: int,
        operator_id: str = "",
        note: str = "",
    ) -> CreditTransaction:
        """记录还款"""
        account = self._get_account(account_id)
        if amount_fen <= 0:
            raise ValueError("还款金额必须大于0")

        account.balance_fen = max(0, account.balance_fen - amount_fen)
        account.last_payment_at = datetime.now(timezone.utc)

        txn = CreditTransaction(
            account_id=account_id,
            transaction_type=TransactionType.PAYMENT,
            amount_fen=amount_fen,
            balance_after_fen=account.balance_fen,
            operator_id=operator_id,
            note=note,
        )
        self._transactions[account_id].append(txn)
        logger.info("挂账还款", account_id=account_id, amount_yuan=txn.amount_yuan,
                     balance_yuan=account.balance_yuan)
        return txn

    def get_balance(self, account_id: str) -> Dict:
        """查询余额"""
        account = self._get_account(account_id)
        return {
            "account_id": account_id,
            "customer_name": account.customer_name,
            "balance_fen": account.balance_fen,
            "balance_yuan": account.balance_yuan,
            "credit_limit_fen": account.credit_limit_fen,
            "credit_limit_yuan": account.credit_limit_yuan,
            "available_fen": account.available_fen,
            "available_yuan": account.available_yuan,
            "status": account.status.value,
        }

    def adjust_limit(self, account_id: str, new_limit_fen: int, operator_id: str = "") -> CreditAccount:
        """调整授信额度"""
        account = self._get_account(account_id)
        if new_limit_fen <= 0:
            raise ValueError("授信额度必须大于0")
        old_limit = account.credit_limit_fen
        account.credit_limit_fen = new_limit_fen
        logger.info("调整授信额度", account_id=account_id,
                     old_yuan=round(old_limit/100, 2), new_yuan=account.credit_limit_yuan)
        return account

    def freeze(self, account_id: str, reason: str = "") -> CreditAccount:
        """冻结账户"""
        account = self._get_account(account_id)
        account.status = AccountStatus.FROZEN
        logger.info("冻结挂账账户", account_id=account_id, reason=reason)
        return account

    def unfreeze(self, account_id: str) -> CreditAccount:
        """解冻账户"""
        account = self._get_account(account_id)
        if account.status != AccountStatus.FROZEN:
            raise ValueError("账户未冻结")
        account.status = AccountStatus.ACTIVE
        logger.info("解冻挂账账户", account_id=account_id)
        return account

    def get_statement(self, account_id: str, start_date: Optional[datetime] = None,
                      end_date: Optional[datetime] = None) -> Dict:
        """获取对账单"""
        account = self._get_account(account_id)
        txns = self._transactions.get(account_id, [])
        if start_date:
            txns = [t for t in txns if t.created_at >= start_date]
        if end_date:
            txns = [t for t in txns if t.created_at <= end_date]

        total_charge = sum(t.amount_fen for t in txns if t.transaction_type == TransactionType.CHARGE)
        total_payment = sum(t.amount_fen for t in txns if t.transaction_type == TransactionType.PAYMENT)

        return {
            "account_id": account_id,
            "customer_name": account.customer_name,
            "company_name": account.company_name,
            "period_start": start_date.isoformat() if start_date else None,
            "period_end": end_date.isoformat() if end_date else None,
            "total_charge_fen": total_charge,
            "total_charge_yuan": round(total_charge / 100, 2),
            "total_payment_fen": total_payment,
            "total_payment_yuan": round(total_payment / 100, 2),
            "current_balance_fen": account.balance_fen,
            "current_balance_yuan": account.balance_yuan,
            "transactions": [
                {
                    "id": t.transaction_id,
                    "type": t.transaction_type.value,
                    "amount_fen": t.amount_fen,
                    "amount_yuan": t.amount_yuan,
                    "balance_after_yuan": t.balance_after_yuan,
                    "order_id": t.order_id,
                    "note": t.note,
                    "time": t.created_at.isoformat(),
                }
                for t in txns
            ],
        }

    def get_overdue_accounts(self, overdue_days: int = 30) -> List[Dict]:
        """获取逾期账户列表"""
        now = datetime.now(timezone.utc)
        overdue = []
        for account in self._accounts.values():
            if account.balance_fen <= 0:
                continue
            # 以最后挂账时间为基准判断逾期
            last_activity = account.last_payment_at or account.last_charge_at
            if last_activity is None:
                continue
            days_since = (now - last_activity).days
            if days_since >= overdue_days:
                overdue.append({
                    "account_id": account.account_id,
                    "customer_name": account.customer_name,
                    "company_name": account.company_name,
                    "balance_fen": account.balance_fen,
                    "balance_yuan": account.balance_yuan,
                    "overdue_days": days_since,
                    "last_activity": last_activity.isoformat(),
                })
        # 按逾期天数倒序
        overdue.sort(key=lambda x: x["overdue_days"], reverse=True)
        return overdue

    def _get_account(self, account_id: str) -> CreditAccount:
        if account_id not in self._accounts:
            raise ValueError(f"挂账账户不存在: {account_id}")
        return self._accounts[account_id]
