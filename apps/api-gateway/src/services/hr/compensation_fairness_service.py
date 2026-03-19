"""CompensationFairnessService — WF-8 薪资公平性分析

触发：每季度定时运行 / 新员工入职时市场对标
能力：同岗薪资分布、异常识别（<P25或>P90）、离职风险关联
"""
import uuid
from decimal import Decimal
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 餐饮行业薪资基准（湖南省，月薪元）
_MARKET_BENCHMARK: dict[str, dict] = {
    "server": {"p25": 3200, "p50": 4000, "p75": 4800, "p90": 5500},
    "chef": {"p25": 4500, "p50": 6000, "p75": 7500, "p90": 9000},
    "head_chef": {"p25": 7000, "p50": 9000, "p75": 11000, "p90": 13000},
    "manager": {"p25": 6000, "p50": 8000, "p75": 10000, "p90": 12000},
    "default": {"p25": 3500, "p50": 4500, "p75": 5500, "p90": 6500},
}


class CompensationFairnessService:

    async def analyze_store(
        self,
        employees: list[dict],
        session: AsyncSession,
    ) -> dict:
        """分析门店薪资分布

        employees: [{person_id, role, salary_yuan, tenure_months}]
        """
        if not employees:
            return {"employee_count": 0, "anomalies": [], "avg_salary_yuan": 0}

        total = sum(e.get("salary_yuan", 0) for e in employees)
        avg = round(total / len(employees), 2)

        anomalies = []
        for e in employees:
            role = e.get("role", "default")
            salary = e.get("salary_yuan", 0)
            benchmark = _MARKET_BENCHMARK.get(role, _MARKET_BENCHMARK["default"])

            if salary < benchmark["p25"]:
                anomalies.append({
                    "person_id": e.get("person_id"),
                    "role": role,
                    "salary_yuan": salary,
                    "benchmark_p50": benchmark["p50"],
                    "deviation_pct": round((salary - benchmark["p50"]) / benchmark["p50"] * 100, 1),
                    "risk": "low_pay",
                    "recommendation": f"薪资低于P25({benchmark['p25']}元)，离职风险↑",
                })
            elif salary > benchmark["p90"]:
                anomalies.append({
                    "person_id": e.get("person_id"),
                    "role": role,
                    "salary_yuan": salary,
                    "benchmark_p50": benchmark["p50"],
                    "deviation_pct": round((salary - benchmark["p50"]) / benchmark["p50"] * 100, 1),
                    "risk": "high_pay",
                    "recommendation": f"薪资高于P90({benchmark['p90']}元)，注意成本控制",
                })

        return {
            "employee_count": len(employees),
            "avg_salary_yuan": avg,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
        }

    async def flag_anomalies(
        self,
        all_employees: list[dict],
        session: AsyncSession,
    ) -> list[dict]:
        """全集团薪资异常扫描"""
        result = await self.analyze_store(all_employees, session)
        return result["anomalies"]

    async def market_benchmark(
        self,
        job_title: str,
        city: str = "长沙",
        session: Optional[AsyncSession] = None,
    ) -> dict:
        """市场薪资对标"""
        role = job_title.lower()
        # 简化映射
        if any(k in role for k in ["服务", "server", "waiter"]):
            role_key = "server"
        elif any(k in role for k in ["厨师长", "head_chef"]):
            role_key = "head_chef"
        elif any(k in role for k in ["厨师", "chef", "cook"]):
            role_key = "chef"
        elif any(k in role for k in ["店长", "manager", "经理"]):
            role_key = "manager"
        else:
            role_key = "default"

        benchmark = _MARKET_BENCHMARK.get(role_key, _MARKET_BENCHMARK["default"])
        return {
            "job_title": job_title,
            "city": city,
            "role_key": role_key,
            **benchmark,
        }
