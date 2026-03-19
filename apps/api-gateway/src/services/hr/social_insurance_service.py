"""SocialInsuranceService — 社保计算（长沙2025年度费率）

个人部分：养老8% + 医疗2% + 失业0.5% + 公积金5-12%
缴费基数上下限：3800~19000元/月
"""
import structlog

logger = structlog.get_logger()

# 长沙2025年度社保费率（个人部分）
_RATES = {
    "pension": 0.08,           # 养老保险
    "medical": 0.02,           # 医疗保险
    "unemployment": 0.005,     # 失业保险
}

# 缴费基数上下限（元/月）
_BASE_FLOOR_YUAN = 3800.0
_BASE_CEILING_YUAN = 19000.0


class SocialInsuranceService:
    """社保计算服务（纯函数，无DB依赖）"""

    def calculate_employee_portion(
        self,
        gross_yuan: float,
        housing_fund_rate: float = 0.05,
    ) -> dict:
        """计算员工个人社保缴纳部分

        Args:
            gross_yuan: 税前工资（元）
            housing_fund_rate: 公积金比例（5%-12%，默认5%）

        Returns:
            dict with pension_yuan, medical_yuan, unemployment_yuan,
            housing_fund_yuan, total_yuan
        """
        # 缴费基数 = gross，但有上下限
        base = max(_BASE_FLOOR_YUAN, min(gross_yuan, _BASE_CEILING_YUAN))

        pension = round(base * _RATES["pension"], 2)
        medical = round(base * _RATES["medical"], 2)
        unemployment = round(base * _RATES["unemployment"], 2)
        housing_fund = round(base * housing_fund_rate, 2)
        total = round(pension + medical + unemployment + housing_fund, 2)

        return {
            "base_yuan": base,
            "pension_yuan": pension,
            "medical_yuan": medical,
            "unemployment_yuan": unemployment,
            "housing_fund_yuan": housing_fund,
            "total_yuan": total,
        }
