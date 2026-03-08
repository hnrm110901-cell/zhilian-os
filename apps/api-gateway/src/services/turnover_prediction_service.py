"""员工流失风险预测服务。"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.store import Store
from ..repositories import EmployeeRepository
from .wechat_service import wechat_service


def estimate_replacement_cost(monthly_salary: float) -> float:
    """离职替换成本估算：月薪 * 50%。"""
    return round(max(0.0, monthly_salary) * 0.5, 2)


def normalize_attendance_risk(attendance_anomaly_count: int) -> float:
    """考勤异常风险归一化。"""
    return min(1.0, max(0, attendance_anomaly_count) / 8.0)


def normalize_fairness_risk(fairness_score: float) -> float:
    """公平性得分风险归一化（分数越低风险越高）。"""
    score = max(0.0, min(100.0, fairness_score))
    return round(1 - score / 100.0, 4)


def normalize_consecutive_days_risk(consecutive_work_days: int) -> float:
    """连续工作天数风险归一化。"""
    days = max(0, consecutive_work_days)
    if days <= 6:
        return 0.0
    return min(1.0, (days - 6) / 8.0)


def normalize_salary_volatility_risk(salary_volatility_rate: float) -> float:
    """工资波动率风险归一化。"""
    rate = max(0.0, salary_volatility_rate)
    return min(1.0, rate / 0.30)


def compute_turnover_risk_score(feature_risks: Dict[str, float]) -> float:
    """按权重计算总流失风险分（0-1）。"""
    weights = {
        "attendance": 0.35,
        "fairness": 0.25,
        "consecutive_days": 0.20,
        "salary_volatility": 0.20,
    }

    score = sum(feature_risks.get(name, 0.0) * weight for name, weight in weights.items())
    return round(max(0.0, min(1.0, score)), 4)


def top_risk_factors(feature_risks: Dict[str, float], top_n: int = 2) -> List[Tuple[str, float]]:
    """取最主要风险因子。"""
    ranked = sorted(feature_risks.items(), key=lambda item: item[1], reverse=True)
    return ranked[: max(1, top_n)]


class TurnoverPredictionService:
    """员工流失风险预测服务。"""

    async def predict_employee_turnover(
        self,
        employee_id: str,
        db: AsyncSession,
        monthly_salary: Optional[float] = None,
    ) -> Dict[str, Any]:
        """预测 90 天内流失风险，并在高风险时通知店长。"""
        employee = await EmployeeRepository.get_by_id(db, employee_id)
        if not employee:
            raise ValueError("employee_not_found")

        preferences = employee.preferences or {}
        attendance_anomaly_count = int(preferences.get("attendance_anomaly_count", 0) or 0)
        fairness_score = float(preferences.get("shift_fairness_score", 100.0) or 100.0)
        consecutive_work_days = int(preferences.get("consecutive_work_days", 0) or 0)
        salary_volatility_rate = float(preferences.get("salary_volatility_rate", 0.0) or 0.0)

        feature_risks = {
            "attendance": normalize_attendance_risk(attendance_anomaly_count),
            "fairness": normalize_fairness_risk(fairness_score),
            "consecutive_days": normalize_consecutive_days_risk(consecutive_work_days),
            "salary_volatility": normalize_salary_volatility_risk(salary_volatility_rate),
        }

        risk_score = compute_turnover_risk_score(feature_risks)
        major_factors = top_risk_factors(feature_risks, top_n=2)

        salary = float(monthly_salary if monthly_salary is not None else preferences.get("monthly_salary", 0.0) or 0.0)
        replacement_cost = estimate_replacement_cost(salary)

        alert_sent = False
        if risk_score > 0.7:
            store = await db.get(Store, employee.store_id)
            if store and store.manager_id:
                message = (
                    f"【员工流失预警】\n"
                    f"门店: {employee.store_id}\n"
                    f"员工: {employee.name}({employee.id})\n"
                    f"90天离职风险: {risk_score:.2f}\n"
                    f"主要因子: {major_factors[0][0]}={major_factors[0][1]:.2f}, {major_factors[1][0]}={major_factors[1][1]:.2f}\n"
                    f"估算替换成本: ¥{replacement_cost:.2f}"
                )
                try:
                    await wechat_service.send_text_message(content=message, touser=str(store.manager_id))
                    alert_sent = True
                except Exception:
                    alert_sent = False

        return {
            "employee_id": employee.id,
            "store_id": employee.store_id,
            "risk_score_90d": risk_score,
            "major_risk_factors": [
                {"name": name, "score": score}
                for name, score in major_factors
            ],
            "replacement_cost_yuan": replacement_cost,
            "alert_sent": alert_sent,
        }
