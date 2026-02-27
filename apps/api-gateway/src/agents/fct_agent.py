"""
FCT Agent - 业财税资金一体化智能体（Phase 3）

支持：get_report（period_summary/aggregate/trend/by_entity/by_region/comparison 同比环比）、explain_voucher、reconciliation_status。
合并部署且 FCT_ENABLED 时注册；独立形态可不使用。
"""
import time
from typing import Dict, Any, List

from src.core.base_agent import BaseAgent, AgentResponse
from src.core.database import get_db_session

import structlog

logger = structlog.get_logger()


class FctAgent(BaseAgent):
    def __init__(self):
        super().__init__(config={})

    def get_supported_actions(self) -> List[str]:
        return [
            "get_report",
            "explain_voucher",
            "reconciliation_status",
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        start = time.time()
        if action not in self.get_supported_actions():
            return AgentResponse(
                success=False,
                error=f"不支持的操作: {action}。支持: {', '.join(self.get_supported_actions())}",
                execution_time=time.time() - start,
            )
        try:
            from src.services.fct_service import fct_service
            async with get_db_session(enable_tenant_isolation=False) as session:
                if action == "get_report":
                    from datetime import date
                    sd = params.get("start_date")
                    ed = params.get("end_date")
                    report_type = params.get("report_type", "period_summary")
                    try:
                        if isinstance(sd, str) and sd:
                            sd = date.fromisoformat(sd)
                        elif sd is None or sd == "":
                            sd = None
                        if isinstance(ed, str) and ed:
                            ed = date.fromisoformat(ed)
                        elif ed is None or ed == "":
                            ed = None
                    except (ValueError, TypeError) as e:
                        return AgentResponse(success=False, error=f"日期格式无效: {e}", execution_time=time.time() - start)
                    tenant_id = params.get("tenant_id", "default")
                    entity_id = params.get("entity_id")
                    if report_type == "aggregate":
                        out = await fct_service.get_report_aggregate(
                            session, tenant_id=tenant_id, entity_id=entity_id, start_date=sd, end_date=ed
                        )
                    elif report_type == "trend":
                        out = await fct_service.get_report_trend(
                            session,
                            tenant_id=tenant_id,
                            entity_id=entity_id,
                            start_date=sd,
                            end_date=ed,
                            group_by=params.get("group_by", "day"),
                        )
                    elif report_type == "by_entity":
                        out = await fct_service.get_report_by_entity(
                            session, tenant_id=tenant_id, start_date=sd, end_date=ed
                        )
                    elif report_type == "by_region":
                        out = await fct_service.get_report_by_region(
                            session, tenant_id=tenant_id, start_date=sd, end_date=ed
                        )
                    elif report_type == "comparison":
                        out = await fct_service.get_report_comparison(
                            session,
                            tenant_id=tenant_id,
                            entity_id=entity_id,
                            start_date=sd,
                            end_date=ed,
                            compare_type=params.get("compare_type", "yoy"),
                        )
                    elif report_type == "plan_vs_actual":
                        out = await fct_service.get_plan_vs_actual(
                            session,
                            tenant_id=tenant_id,
                            entity_id=entity_id,
                            start_date=sd,
                            end_date=ed,
                            granularity=params.get("granularity", "month"),
                        )
                    else:
                        out = await fct_service.get_report_period_summary(
                            session, tenant_id=tenant_id, entity_id=entity_id, start_date=sd, end_date=ed
                        )
                    return AgentResponse(success=True, data=out, execution_time=time.time() - start)
                if action == "explain_voucher":
                    voucher_id = params.get("voucher_id")
                    if not voucher_id:
                        return AgentResponse(success=False, error="缺少 voucher_id", execution_time=time.time() - start)
                    v = await fct_service.get_voucher_by_id(session, voucher_id)
                    if not v:
                        return AgentResponse(success=False, error="凭证不存在", execution_time=time.time() - start)
                    lines = [{"line_no": l.line_no, "account": l.account_code, "debit": float(l.debit or 0), "credit": float(l.credit or 0), "desc": l.description} for l in v.lines]
                    return AgentResponse(
                        success=True,
                        data={"voucher_no": v.voucher_no, "biz_date": str(v.biz_date), "description": v.description, "lines": lines},
                        execution_time=time.time() - start,
                    )
                if action == "reconciliation_status":
                    out = await fct_service.get_cash_reconciliation_status(
                        session, tenant_id=params.get("tenant_id", "default"), entity_id=params.get("entity_id")
                    )
                    return AgentResponse(success=True, data=out, execution_time=time.time() - start)
        except Exception as e:
            logger.error("FctAgent 执行异常", action=action, error=str(e), exc_info=e)
            return AgentResponse(success=False, error=str(e), execution_time=time.time() - start)
        return AgentResponse(success=False, error="unknown", execution_time=time.time() - start)
