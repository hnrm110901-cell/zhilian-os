"""TaxService — 中国个人所得税计算（累计预扣法）

适用于居民个人工资薪金所得。
起征点：5000元/月
7级超额累进税率表（年度累计）
"""
import structlog

logger = structlog.get_logger()

# 7级税率表（年度累计应纳税所得额，税率，速算扣除数）— 单位：元
_BRACKETS = [
    (36000.0,    0.03,  0.0),
    (144000.0,   0.10,  2520.0),
    (300000.0,   0.20,  16920.0),
    (420000.0,   0.25,  31920.0),
    (660000.0,   0.30,  52920.0),
    (960000.0,   0.35,  85920.0),
    (float('inf'), 0.45, 181920.0),
]

_MONTHLY_DEDUCTION_YUAN = 5000.0  # 月度起征点


class TaxService:
    """个人所得税计算服务（纯函数，无DB依赖）"""

    def calculate_monthly_tax(
        self,
        ytd_taxable_yuan: float,
        current_month_taxable_yuan: float,
    ) -> float:
        """累计预扣法计算当月个税

        Args:
            ytd_taxable_yuan: 本年度截至上月的累计应纳税所得额（元）
            current_month_taxable_yuan: 本月应纳税所得额（元）= 税前-社保-5000

        Returns:
            当月应预扣税额（元）
        """
        if current_month_taxable_yuan <= 0:
            return 0.0

        # 累计应纳税所得额 = 截至上月 + 本月
        ytd_total = ytd_taxable_yuan + current_month_taxable_yuan

        # 计算截至本月累计应纳税额
        tax_ytd_total = self._calc_cumulative_tax(ytd_total)
        # 计算截至上月累计应纳税额
        tax_ytd_prev = self._calc_cumulative_tax(ytd_taxable_yuan)

        # 本月税额 = 截至本月 - 截至上月
        monthly_tax = round(max(0, tax_ytd_total - tax_ytd_prev), 2)
        return monthly_tax

    def _calc_cumulative_tax(self, cumulative_taxable_yuan: float) -> float:
        """查表计算累计应纳税额"""
        if cumulative_taxable_yuan <= 0:
            return 0.0
        for ceiling, rate, deduction in _BRACKETS:
            if cumulative_taxable_yuan <= ceiling:
                return round(cumulative_taxable_yuan * rate - deduction, 2)
        # Should not reach here
        return round(cumulative_taxable_yuan * 0.45 - 181920.0, 2)
