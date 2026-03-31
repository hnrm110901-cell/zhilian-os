"""
金蝶ERP凭证同步服务
将屯象OS的财务数据自动生成金蝶标准凭证格式并推送到金蝶云星空API。

环境变量配置（必须在生产环境中设置，不得硬编码）：
  KINGDEE_API_BASE      金蝶云星空API基础URL（默认 https://api.kingdee.com/jdy/v2）
  KINGDEE_APP_ID        金蝶应用 App ID
  KINGDEE_APP_SECRET    金蝶应用 App Secret
  KINGDEE_ACCT_ID       金蝶账套ID

会计科目映射（可通过环境变量覆盖，不硬编码科目编号）：
  ACCT_MAIN_REVENUE     主营业务收入科目编号（默认 6001）
  ACCT_MAIN_COST        主营业务成本科目编号（默认 6401）
  ACCT_MGMT_EXPENSE     管理费用科目编号（默认 6602）
  ACCT_LABOR_COST       人工成本科目编号（默认 6405）
  ACCT_CASH             现金/银行存款科目编号（默认 1002）
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# ── 金蝶API配置（从环境变量读取） ─────────────────────────────────────────────
KINGDEE_API_BASE = os.getenv("KINGDEE_API_BASE", "https://api.kingdee.com/jdy/v2")
KINGDEE_APP_ID = os.getenv("KINGDEE_APP_ID", "")
KINGDEE_APP_SECRET = os.getenv("KINGDEE_APP_SECRET", "")
KINGDEE_ACCT_ID = os.getenv("KINGDEE_ACCT_ID", "")

# ── 会计科目映射（从环境变量读取，便于不同账套调整） ─────────────────────────────
ACCT_MAIN_REVENUE = os.getenv("ACCT_MAIN_REVENUE", "6001")    # 主营业务收入（贷）
ACCT_MAIN_COST = os.getenv("ACCT_MAIN_COST", "6401")          # 主营业务成本（借）
ACCT_MGMT_EXPENSE = os.getenv("ACCT_MGMT_EXPENSE", "6602")    # 管理费用/营业损耗（借）
ACCT_LABOR_COST = os.getenv("ACCT_LABOR_COST", "6405")        # 人工成本（借）
ACCT_CASH = os.getenv("ACCT_CASH", "1002")                    # 银行存款（借/贷）


class KingdeeSyncService:
    """金蝶ERP凭证同步服务"""

    def __init__(self):
        self._session = None  # HTTP 客户端（懒初始化）

    # ─────────────────────────────────────────────
    # 主入口：同步日账凭证
    # ─────────────────────────────────────────────

    async def sync_daily_voucher(
        self, store_id: str, date_: date, pnl_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成并同步日账凭证到金蝶。

        流程：
          1. 接收 FinanceAnalyticsService 提供的当日 P&L 数据
          2. 按会计科目映射生成凭证条目
          3. 调用金蝶 API 推送
          4. 将同步状态写入本地日志（finance_kingdee_sync_log）

        Args:
            store_id : 门店ID
            date_    : 凭证日期
            pnl_data : get_real_daily_profit() 返回的P&L字典

        Returns:
            {voucher_no, status, entries_count, message}
        """
        if not KINGDEE_APP_ID or not KINGDEE_APP_SECRET:
            logger.warning(
                "kingdee_sync_skipped",
                reason="KINGDEE_APP_ID or KINGDEE_APP_SECRET not configured",
                store_id=store_id,
            )
            return {
                "voucher_no": None,
                "status": "skipped",
                "entries_count": 0,
                "message": "金蝶API未配置，请设置环境变量 KINGDEE_APP_ID / KINGDEE_APP_SECRET",
            }

        # 1. 生成凭证条目
        entries = await self.map_to_accounting_entries(pnl_data)
        if not entries:
            return {
                "voucher_no": None,
                "status": "empty",
                "entries_count": 0,
                "message": "无财务数据，跳过凭证生成",
            }

        # 2. 构建金蝶凭证请求体
        voucher_payload = self._build_voucher_payload(store_id, date_, entries)

        # 3. 推送到金蝶API
        try:
            result = await self._push_to_kingdee(voucher_payload)
            voucher_no = result.get("voucher_no", "")
            logger.info(
                "kingdee_voucher_synced",
                store_id=store_id,
                date=date_.isoformat(),
                voucher_no=voucher_no,
                entries_count=len(entries),
            )
            return {
                "voucher_no": voucher_no,
                "status": "success",
                "entries_count": len(entries),
                "message": f"凭证已同步，凭证号：{voucher_no}",
            }
        except Exception as exc:
            logger.error(
                "kingdee_voucher_sync_failed",
                store_id=store_id,
                date=date_.isoformat(),
                error=str(exc),
            )
            return {
                "voucher_no": None,
                "status": "failed",
                "entries_count": len(entries),
                "message": f"同步失败：{str(exc)}",
            }

    # ─────────────────────────────────────────────
    # 财务数据 → 会计凭证映射
    # ─────────────────────────────────────────────

    async def map_to_accounting_entries(
        self, pnl_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        财务数据 → 会计凭证条目映射。

        会计分录规则（餐饮企业）：
          营收   → 借：银行存款/现金   贷：主营业务收入
          食材   → 借：主营业务成本   贷：原材料/库存（凭证期间由内部系统处理）
          损耗   → 借：管理费用-营业损耗   贷：原材料
          薪资   → 借：人工成本   贷：应付职工薪酬

        Args:
            pnl_data: get_real_daily_profit() 返回的P&L字典

        Returns:
            凭证条目列表，每条：{acct_code, acct_name, debit_yuan, credit_yuan, summary}
        """
        entries = []

        revenue_yuan = float(pnl_data.get("revenue_yuan", 0))
        ingredient_cost_yuan = float(pnl_data.get("ingredient_cost_yuan", 0))
        labor_cost_yuan = float(pnl_data.get("labor_cost_yuan", 0))
        waste_cost_yuan = float(pnl_data.get("waste_cost_yuan", 0))

        if revenue_yuan <= 0:
            return entries

        # 分录1：营收确认（借：银行存款 贷：主营业务收入）
        entries.append(
            {
                "acct_code": ACCT_CASH,
                "acct_name": "银行存款",
                "debit_yuan": round(revenue_yuan, 2),
                "credit_yuan": 0.0,
                "summary": "当日餐饮营收入账",
            }
        )
        entries.append(
            {
                "acct_code": ACCT_MAIN_REVENUE,
                "acct_name": "主营业务收入",
                "debit_yuan": 0.0,
                "credit_yuan": round(revenue_yuan, 2),
                "summary": "当日餐饮营收确认",
            }
        )

        # 分录2：食材成本（借：主营业务成本 贷：库存商品）
        if ingredient_cost_yuan > 0:
            entries.append(
                {
                    "acct_code": ACCT_MAIN_COST,
                    "acct_name": "主营业务成本",
                    "debit_yuan": round(ingredient_cost_yuan, 2),
                    "credit_yuan": 0.0,
                    "summary": "当日食材领用成本",
                }
            )
            entries.append(
                {
                    "acct_code": "1405",  # 库存商品（通用科目，不受环境变量影响）
                    "acct_name": "库存商品",
                    "debit_yuan": 0.0,
                    "credit_yuan": round(ingredient_cost_yuan, 2),
                    "summary": "当日食材领用出库",
                }
            )

        # 分录3：损耗（借：管理费用-营业损耗 贷：库存商品）
        if waste_cost_yuan > 0:
            entries.append(
                {
                    "acct_code": ACCT_MGMT_EXPENSE,
                    "acct_name": "管理费用-营业损耗",
                    "debit_yuan": round(waste_cost_yuan, 2),
                    "credit_yuan": 0.0,
                    "summary": "当日食材损耗",
                }
            )
            entries.append(
                {
                    "acct_code": "1405",
                    "acct_name": "库存商品",
                    "debit_yuan": 0.0,
                    "credit_yuan": round(waste_cost_yuan, 2),
                    "summary": "当日损耗出库",
                }
            )

        # 分录4：人工成本（借：人工成本 贷：应付职工薪酬）
        if labor_cost_yuan > 0:
            entries.append(
                {
                    "acct_code": ACCT_LABOR_COST,
                    "acct_name": "人工成本",
                    "debit_yuan": round(labor_cost_yuan, 2),
                    "credit_yuan": 0.0,
                    "summary": "当日薪资分摊",
                }
            )
            entries.append(
                {
                    "acct_code": "2211",  # 应付职工薪酬（通用科目）
                    "acct_name": "应付职工薪酬",
                    "debit_yuan": 0.0,
                    "credit_yuan": round(labor_cost_yuan, 2),
                    "summary": "当日薪资计提",
                }
            )

        return entries

    # ─────────────────────────────────────────────
    # 同步状态查询
    # ─────────────────────────────────────────────

    async def get_sync_status(
        self, store_id: str, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        查询指定日期范围内金蝶同步状态。
        返回每日：{date, status, voucher_no, synced_at, message}

        注意：当前实现返回占位数据。
        完整实现需要 finance_kingdee_sync_log 表（配合 z81 迁移）。
        """
        from datetime import timedelta

        results = []
        current = start_date
        while current <= end_date:
            results.append(
                {
                    "date": current.isoformat(),
                    "store_id": store_id,
                    "status": "not_synced",  # not_synced / success / failed / skipped
                    "voucher_no": None,
                    "synced_at": None,
                    "message": "尚未同步",
                }
            )
            current += timedelta(days=1)

        return results

    async def retry_failed_sync(
        self, store_id: str, date_: date, pnl_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        重试失败的同步。
        直接调用 sync_daily_voucher，调用方需要传入对应日期的 P&L 数据。
        """
        logger.info(
            "kingdee_retry_sync",
            store_id=store_id,
            date=date_.isoformat(),
        )
        return await self.sync_daily_voucher(store_id, date_, pnl_data)

    # ─────────────────────────────────────────────
    # 内部工具方法
    # ─────────────────────────────────────────────

    def _build_voucher_payload(
        self, store_id: str, date_: date, entries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        构建金蝶云星空凭证 API 请求体格式。
        参考：金蝶云星空开放API v2 凭证录入接口规范。
        """
        return {
            "AccountID": KINGDEE_ACCT_ID,
            "FormId": "GL_VOUCHER",
            "Data": {
                "FDate": date_.isoformat(),
                "FAttachment": 0,
                "FMemo": f"屯象OS日账凭证 - 门店{store_id} - {date_.isoformat()}",
                "FEntryList": [
                    {
                        "FAccount": entry["acct_code"],
                        "FExplanation": entry["summary"],
                        "FDebit": entry["debit_yuan"],
                        "FCredit": entry["credit_yuan"],
                    }
                    for entry in entries
                ],
            },
        }

    async def _push_to_kingdee(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用金蝶云星空 API 推送凭证。
        使用 aiohttp 进行异步 HTTP 请求。
        """
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError(
                "aiohttp 未安装，请执行 pip install aiohttp 后重试"
            )

        # 构建鉴权头（金蝶 OAuth2 Bearer Token 方式）
        token = await self._get_kingdee_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        url = f"{KINGDEE_API_BASE}/voucher/save"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    raise RuntimeError(
                        f"金蝶API返回错误 HTTP {resp.status}: {body[:200]}"
                    )
                result = await resp.json()
                if not result.get("Result", {}).get("ResponseStatus", {}).get("IsSuccess", False):
                    errs = result.get("Result", {}).get("ResponseStatus", {}).get("Errors", [])
                    raise RuntimeError(f"金蝶凭证保存失败：{errs}")
                return {
                    "voucher_no": result.get("Result", {}).get("FNumber", ""),
                    "raw": result,
                }

    async def _get_kingdee_token(self) -> str:
        """
        获取金蝶云星空 OAuth2 Access Token。
        生产环境应加 Redis 缓存（token 有效期通常 2 小时）。
        """
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError("aiohttp 未安装")

        token_url = f"{KINGDEE_API_BASE}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "appId": KINGDEE_APP_ID,
            "appSec": KINGDEE_APP_SECRET,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                token_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"金蝶Token获取失败 HTTP {resp.status}: {body[:200]}"
                    )
                result = await resp.json()
                token = result.get("access_token", "")
                if not token:
                    raise RuntimeError("金蝶Token返回为空，请检查 KINGDEE_APP_ID/APP_SECRET")
                return token
