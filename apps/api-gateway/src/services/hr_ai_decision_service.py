"""
HR AI 决策服务 — 真正的 Claude 驱动人力智能
不是 if-else 规则引擎，是基于 LLM 的模式识别 + 决策建议。

设计原则：
1. 每个决策点必须有 rule-based fallback（LLM不可用时降级）
2. 每个AI建议必须包含：建议动作 + 预期¥影响 + 置信度
3. 所有LLM输入/输出通过 structlog 记录（可审计）
"""
from __future__ import annotations

import json
import structlog
from datetime import date, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.llm import get_llm_client
from src.core.config import settings

logger = structlog.get_logger()


# ── 系统提示词（餐饮行业专用） ──────────────────────────────────

TURNOVER_SYSTEM_PROMPT = """你是一位资深的餐饮连锁人力资源分析师，拥有10年以上中国餐饮行业HR管理经验。
基于员工的360°画像数据，分析其离职风险并给出具体的留人建议。

你熟悉餐饮行业的特点：
- 一线员工（服务员、厨师）流动率高，行业平均年离职率60-80%
- 核心岗位（厨师长、店长）离职影响极大，替换成本高
- 餐饮员工对薪资、工作环境、同事关系、晋升空间敏感
- 旺季（节假日前）离职风险更高

请严格按以下JSON格式回复，不要包含其他文字：
{
    "risk_score": 82,
    "analysis": "2-3句中文分析，指出关键风险信号和趋势判断",
    "recommendations": [
        {
            "action": "具体的行动建议（中文，一句话）",
            "expected_impact_yuan": -500,
            "confidence": 0.85
        }
    ]
}

规则：
1. risk_score: 0-100的整数风险评分
2. analysis: 结合数据趋势的分析，不要空泛
3. recommendations: 1-3个建议，每个必须含 action/expected_impact_yuan/confidence
4. expected_impact_yuan: 负数=成本，正数=收益（如避免招聘成本）
5. confidence: 0.0-1.0"""


BATCH_SCAN_SYSTEM_PROMPT = """你是一位资深的餐饮连锁人力资源分析师。
现在你需要对一组员工的离职风险评分和信号进行全局分析，找出规律，给出门店级建议。

请严格按以下JSON格式回复，不要包含其他文字：
{
    "store_analysis": "2-3句话的门店人力风险全局分析",
    "top_risk_pattern": "最突出的风险模式（如：新员工流失严重/老员工倦怠期）",
    "store_recommendations": [
        {
            "action": "门店级行动建议",
            "expected_impact_yuan": -2000,
            "confidence": 0.75,
            "affected_count": 5
        }
    ]
}"""


class HRAIDecisionService:
    """HR AI决策服务 — Claude驱动的人力智能"""

    # ─── 1. 单员工离职风险预测 ──────────────────────────────

    async def predict_turnover_risk(
        self, db: AsyncSession, employee_id: str, store_id: str
    ) -> Dict[str, Any]:
        """
        多信号融合离职风险预测。

        输入信号（6维360°画像）：
        1. 考勤趋势：近3个月出勤率变化
        2. 绩效变化：最近两次绩效评分趋势
        3. 加班时长：月均加班是否异常
        4. 同岗离职率：同岗位近6个月离职率
        5. 工龄：入职天数（1年内离职风险最高）
        6. 最近调薪：距上次调薪天数

        返回：risk_score + signals + ai_analysis + recommendations + replacement_cost
        """
        # Step 1: 收集员工360°数据
        profile = await self._build_employee_profile(db, employee_id, store_id)
        if profile.get("error"):
            return {
                "risk_score": 0,
                "risk_level": "unknown",
                "signals": [],
                "ai_analysis": None,
                "recommendations": [],
                "replacement_cost_yuan": 0,
                "data_source": "error",
                "error": profile["error"],
            }

        # Step 2: 规则引擎计算基础风险分（始终计算，作为fallback和参考）
        rule_score = self._calculate_rule_based_score(profile)

        # Step 3: 调用Claude进行深度分析
        ai_analysis = await self._llm_turnover_analysis(profile)

        # Step 4: 融合结果
        replacement_cost = self._estimate_replacement_cost(profile)

        if ai_analysis:
            final_score = ai_analysis.get("risk_score", rule_score)
            result = {
                "risk_score": final_score,
                "risk_level": self._score_to_level(final_score),
                "signals": profile["signals"],
                "ai_analysis": ai_analysis.get("analysis", ""),
                "recommendations": ai_analysis.get("recommendations", []),
                "replacement_cost_yuan": replacement_cost,
                "data_source": "ai+rules",
            }
        else:
            # LLM不可用 → 降级到规则引擎
            result = {
                "risk_score": rule_score,
                "risk_level": self._score_to_level(rule_score),
                "signals": profile["signals"],
                "ai_analysis": None,
                "recommendations": self._rule_based_recommendations(
                    rule_score, profile, replacement_cost
                ),
                "replacement_cost_yuan": replacement_cost,
                "data_source": "rules_only",
            }

        # ── 飞轮自动记录：每次AI分析都写入决策记录 ──
        await self._record_to_flywheel(db, store_id, profile, result)

        return result

    # ─── 2. 全店离职风险扫描 ───────────────────────────────

    async def scan_store_turnover_risk(
        self, db: AsyncSession, store_id: str
    ) -> Dict[str, Any]:
        """扫描全店离职风险，返回风险排名 + 门店级AI分析"""
        # 查询所有活跃员工
        emp_result = await db.execute(text("""
            SELECT id, name, position, hire_date, seniority_months
            FROM employees
            WHERE store_id = :store_id AND is_active = true
        """), {"store_id": store_id})
        employees = [dict(r) for r in emp_result.mappings()]

        if not employees:
            return {
                "store_id": store_id,
                "total_active": 0,
                "at_risk_employees": [],
                "store_analysis": None,
                "store_recommendations": [],
            }

        # 为每位员工快速计算规则风险分（不调LLM，批量效率优先）
        risk_list = []
        for emp in employees:
            profile = await self._build_employee_profile(
                db, emp["id"], store_id
            )
            if profile.get("error"):
                continue
            score = self._calculate_rule_based_score(profile)
            replacement_cost = self._estimate_replacement_cost(profile)
            risk_list.append({
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "position": emp["position"],
                "risk_score": score,
                "risk_level": self._score_to_level(score),
                "signals": profile["signals"],
                "replacement_cost_yuan": replacement_cost,
            })

        # 按风险分降序排列
        risk_list.sort(key=lambda x: -x["risk_score"])

        # 对Top10高风险员工，调用Claude做门店级分析
        top_risks = risk_list[:10]
        store_ai = await self._llm_store_scan_analysis(top_risks, store_id)

        high_risk = [r for r in risk_list if r["risk_level"] in ("critical", "high")]
        medium_risk = [r for r in risk_list if r["risk_level"] == "medium"]

        total_replacement = sum(r["replacement_cost_yuan"] for r in high_risk)

        return {
            "store_id": store_id,
            "total_active": len(employees),
            "high_risk_count": len(high_risk),
            "medium_risk_count": len(medium_risk),
            "at_risk_employees": risk_list[:20],
            "total_replacement_cost_yuan": total_replacement,
            "store_analysis": store_ai.get("store_analysis") if store_ai else None,
            "top_risk_pattern": store_ai.get("top_risk_pattern") if store_ai else None,
            "store_recommendations": (
                store_ai.get("store_recommendations", []) if store_ai else []
            ),
            "data_source": "ai+rules" if store_ai else "rules_only",
        }

    # ─── 数据收集 ─────────────────────────────────────────

    async def _build_employee_profile(
        self, db: AsyncSession, employee_id: str, store_id: str
    ) -> Dict[str, Any]:
        """构建员工360°画像"""
        # 基本信息
        emp_result = await db.execute(text("""
            SELECT id, name, position, hire_date, employment_type,
                   seniority_months, grade_level, daily_wage_standard_fen
            FROM employees
            WHERE id = :emp_id AND store_id = :store_id AND is_active = true
        """), {"emp_id": employee_id, "store_id": store_id})
        emp = emp_result.mappings().first()
        if not emp:
            return {"error": "employee_not_found"}

        emp = dict(emp)
        today = date.today()
        hire_date = emp.get("hire_date")
        tenure_days = (today - hire_date).days if hire_date else 0

        signals: List[Dict[str, Any]] = []

        # ── 信号1: 考勤趋势（近3个月出勤率） ──
        attendance_trend = []
        for months_ago in [3, 2, 1]:
            month_start = today.replace(day=1) - timedelta(days=30 * months_ago)
            month_start = month_start.replace(day=1)
            month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

            att_result = await db.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status IN ('normal', 'late')) AS present
                FROM attendance_logs
                WHERE employee_id = :emp_id AND store_id = :store_id
                  AND work_date >= :start AND work_date <= :end
            """), {
                "emp_id": employee_id, "store_id": store_id,
                "start": month_start, "end": month_end,
            })
            row = att_result.mappings().first()
            total = row["total"] if row else 0
            present = row["present"] if row else 0
            rate = round(present / max(total, 1) * 100, 1)
            attendance_trend.append(rate)

        # 出勤率下降信号
        if len(attendance_trend) >= 2 and attendance_trend[-1] < attendance_trend[0] - 5:
            drop = round(attendance_trend[0] - attendance_trend[-1], 1)
            signals.append({
                "signal": "考勤下降",
                "detail": f"近3月出勤率: {attendance_trend[0]}% → {attendance_trend[1]}% → {attendance_trend[2]}%",
                "weight": 0.3,
            })

        # ── 信号2: 绩效变化（最近两次） ──
        perf_result = await db.execute(text("""
            SELECT total_score, level, review_period
            FROM performance_reviews
            WHERE employee_id = :emp_id AND store_id = :store_id
              AND status = 'completed'
            ORDER BY review_period DESC
            LIMIT 3
        """), {"emp_id": employee_id, "store_id": store_id})
        perf_rows = [dict(r) for r in perf_result.mappings()]
        performance_trend = [
            float(r["total_score"]) for r in perf_rows if r.get("total_score")
        ]

        if len(performance_trend) >= 2 and performance_trend[0] < performance_trend[1]:
            last_level = perf_rows[0].get("level", "")
            prev_level = perf_rows[1].get("level", "")
            signals.append({
                "signal": "绩效下滑",
                "detail": f"{prev_level} → {last_level}（{performance_trend[1]} → {performance_trend[0]}）",
                "weight": 0.25,
            })

        # 绩效等级C/D
        if perf_rows and perf_rows[0].get("level") in ("C", "D"):
            signals.append({
                "signal": "绩效评级低",
                "detail": f"最近绩效等级: {perf_rows[0]['level']}",
                "weight": 0.2,
            })

        # ── 信号3: 加班时长（近30天） ──
        ot_result = await db.execute(text("""
            SELECT COALESCE(SUM(overtime_hours), 0) AS total_ot,
                   COUNT(*) AS work_days
            FROM attendance_logs
            WHERE employee_id = :emp_id AND store_id = :store_id
              AND work_date >= :since
        """), {
            "emp_id": employee_id, "store_id": store_id,
            "since": today - timedelta(days=30),
        })
        ot_row = ot_result.mappings().first()
        total_ot = float(ot_row["total_ot"]) if ot_row else 0
        if total_ot > 40:  # 月加班超40小时
            signals.append({
                "signal": "加班过多",
                "detail": f"近30天加班{total_ot:.0f}小时",
                "weight": 0.15,
            })

        # ── 信号4: 同岗位离职率（近6个月） ──
        position = emp.get("position", "")
        peer_result = await db.execute(text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE ec.change_type IN ('resign', 'dismiss')
                ) AS resigned,
                COUNT(DISTINCT e.id) AS total_peers
            FROM employees e
            LEFT JOIN employee_changes ec ON ec.employee_id = e.id
                AND ec.change_type IN ('resign', 'dismiss')
                AND ec.effective_date >= :since
            WHERE e.store_id = :store_id AND e.position = :position
        """), {
            "store_id": store_id, "position": position,
            "since": today - timedelta(days=180),
        })
        peer_row = peer_result.mappings().first()
        total_peers = peer_row["total_peers"] if peer_row else 1
        resigned_peers = peer_row["resigned"] if peer_row else 0
        peer_turnover_rate = round(resigned_peers / max(total_peers, 1), 2)

        if peer_turnover_rate > 0.2:
            signals.append({
                "signal": "同岗离职率高",
                "detail": f"{position}岗位近6月离职率{peer_turnover_rate*100:.0f}%",
                "weight": 0.15,
            })

        # ── 信号5: 工龄（1年内离职风险最高） ──
        if tenure_days < 365:
            months = tenure_days // 30
            signals.append({
                "signal": "新员工高风险期",
                "detail": f"入职仅{months}个月",
                "weight": 0.2,
            })

        # ── 信号6: 最近调薪 ──
        salary_result = await db.execute(text("""
            SELECT effective_date, from_salary_fen, to_salary_fen
            FROM employee_changes
            WHERE employee_id = :emp_id AND change_type = 'salary_adj'
            ORDER BY effective_date DESC
            LIMIT 1
        """), {"emp_id": employee_id})
        salary_row = salary_result.mappings().first()
        days_since_raise = 9999
        if salary_row:
            days_since_raise = (today - salary_row["effective_date"]).days
        elif hire_date:
            days_since_raise = tenure_days

        if days_since_raise > 365:
            signals.append({
                "signal": "长期未调薪",
                "detail": f"距上次调薪{days_since_raise}天",
                "weight": 0.15,
            })

        return {
            "employee": {
                "id": emp["id"],
                "name": emp["name"],
                "position": position,
                "hire_date": str(hire_date) if hire_date else None,
                "tenure_days": tenure_days,
                "employment_type": emp.get("employment_type", "regular"),
                "grade_level": emp.get("grade_level"),
                "seniority_months": emp.get("seniority_months") or (tenure_days // 30),
            },
            "attendance_trend": attendance_trend,
            "performance_trend": performance_trend,
            "peer_turnover_rate": peer_turnover_rate,
            "days_since_last_raise": days_since_raise,
            "overtime_hours_30d": total_ot,
            "signals": signals,
        }

    # ─── LLM 调用 ────────────────────────────────────────

    async def _llm_turnover_analysis(
        self, profile: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """调用Claude分析单员工离职风险"""
        if not getattr(settings, "LLM_ENABLED", False):
            logger.info("turnover_risk_llm_skipped", reason="LLM_ENABLED=false")
            return None

        try:
            prompt = (
                "请分析以下餐饮连锁门店员工的离职风险：\n"
                f"{json.dumps(profile, ensure_ascii=False, default=str)}"
            )

            response = await get_llm_client().generate(
                prompt=prompt,
                system_prompt=TURNOVER_SYSTEM_PROMPT,
                max_tokens=800,
                temperature=0.3,
            )

            # 提取JSON（处理可能的```json包裹）
            result = self._parse_llm_json(response)

            logger.info(
                "turnover_risk_ai_analysis",
                employee_id=profile["employee"]["id"],
                ai_score=result.get("risk_score"),
                recommendation_count=len(result.get("recommendations", [])),
            )
            return result

        except Exception as e:
            logger.warning(
                "turnover_risk_llm_failed",
                employee_id=profile["employee"]["id"],
                error=str(e),
            )
            return None

    async def _llm_store_scan_analysis(
        self, top_risks: List[Dict], store_id: str
    ) -> Optional[Dict[str, Any]]:
        """调用Claude做门店级风险分析"""
        if not getattr(settings, "LLM_ENABLED", False):
            return None

        if not top_risks:
            return None

        try:
            # 精简数据避免token浪费
            summary = [
                {
                    "name": r["employee_name"],
                    "position": r["position"],
                    "risk_score": r["risk_score"],
                    "signals": [s["signal"] for s in r.get("signals", [])],
                }
                for r in top_risks
            ]

            prompt = (
                f"以下是门店 {store_id} 离职风险最高的员工列表，"
                "请分析门店整体人力风险并给出门店级建议：\n"
                f"{json.dumps(summary, ensure_ascii=False, default=str)}"
            )

            response = await get_llm_client().generate(
                prompt=prompt,
                system_prompt=BATCH_SCAN_SYSTEM_PROMPT,
                max_tokens=600,
                temperature=0.3,
            )

            result = self._parse_llm_json(response)

            logger.info(
                "store_scan_ai_analysis",
                store_id=store_id,
                top_risk_count=len(top_risks),
            )
            return result

        except Exception as e:
            logger.warning(
                "store_scan_llm_failed",
                store_id=store_id,
                error=str(e),
            )
            return None

    # ─── 规则引擎（fallback） ─────────────────────────────

    def _calculate_rule_based_score(self, profile: Dict[str, Any]) -> int:
        """规则引擎计算基础风险分（LLM降级方案）"""
        score = 0

        # 考勤下降 (+20)
        trend = profile.get("attendance_trend", [])
        if len(trend) >= 2 and trend[-1] < trend[0] - 5:
            score += 20

        # 绩效下滑 (+15)
        perf = profile.get("performance_trend", [])
        if len(perf) >= 2 and perf[0] < perf[1]:
            score += 15

        # 绩效C/D (+10)
        signals = profile.get("signals", [])
        if any(s.get("signal") == "绩效评级低" for s in signals):
            score += 10

        # 工龄不足1年 (+15)
        tenure = profile.get("employee", {}).get("tenure_days", 999)
        if tenure < 365:
            score += 15

        # 同岗离职率高 (+20)
        if profile.get("peer_turnover_rate", 0) > 0.2:
            score += 20

        # 超过12个月未调薪 (+15)
        if profile.get("days_since_last_raise", 0) > 365:
            score += 15

        # 加班过多 (+10)
        if profile.get("overtime_hours_30d", 0) > 40:
            score += 10

        return min(score, 100)

    def _rule_based_recommendations(
        self, score: int, profile: Dict[str, Any], replacement_cost: float
    ) -> List[Dict[str, Any]]:
        """规则引擎生成建议（LLM不可用时使用）"""
        recs = []
        signals = profile.get("signals", [])
        signal_names = [s.get("signal", "") for s in signals]

        if score >= 60:
            recs.append({
                "action": "建议立即安排1对1谈话，了解员工真实诉求",
                "expected_impact_yuan": -200,
                "confidence": 0.8,
            })

        if "长期未调薪" in signal_names:
            recs.append({
                "action": "考虑调薪¥300-500/月以提升稳定性",
                "expected_impact_yuan": -4800,
                "vs_replacement_yuan": replacement_cost,
                "confidence": 0.65,
            })

        if "考勤下降" in signal_names:
            recs.append({
                "action": "关注出勤情况，排查是否有个人或工作环境问题",
                "expected_impact_yuan": -100,
                "confidence": 0.7,
            })

        if "绩效下滑" in signal_names or "绩效评级低" in signal_names:
            recs.append({
                "action": "制定绩效改进计划(PIP)，提供培训支持",
                "expected_impact_yuan": -800,
                "confidence": 0.6,
            })

        if "新员工高风险期" in signal_names:
            recs.append({
                "action": "安排导师/师傅带教，加强新员工关怀",
                "expected_impact_yuan": -300,
                "confidence": 0.75,
            })

        # 至少返回一条建议
        if not recs:
            recs.append({
                "action": "建议定期沟通，关注员工状态变化",
                "expected_impact_yuan": 0,
                "confidence": 0.5,
            })

        return recs

    # ─── 工具方法 ─────────────────────────────────────────

    @staticmethod
    def _score_to_level(score: int) -> str:
        """风险分 → 风险等级"""
        if score >= 80:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    @staticmethod
    def _estimate_replacement_cost(profile: Dict[str, Any]) -> float:
        """估算替换成本（招聘+培训+产能损失），单位：元"""
        position = profile.get("employee", {}).get("position", "")
        # 餐饮行业替换成本经验值
        REPLACEMENT_COSTS = {
            "chef": 25000,
            "head_chef": 45000,
            "厨师": 25000,
            "厨师长": 45000,
            "manager": 30000,
            "store_manager": 50000,
            "店长": 50000,
            "waiter": 8000,
            "服务员": 8000,
            "cashier": 10000,
            "收银员": 10000,
            "楼面经理": 35000,
        }
        base = REPLACEMENT_COSTS.get(position, 15000)
        # 工龄越长替换成本越高（经验积累不可替代）
        tenure_days = profile.get("employee", {}).get("tenure_days", 0)
        multiplier = min(1.0 + tenure_days / 365 * 0.2, 2.0)
        return round(base * multiplier, 2)

    # ─── 3. 薪资竞争力分析 ──────────────────────────────────

    # 餐饮行业各岗位市场参考薪资（元/月，二线城市基准）
    MARKET_SALARY_REFERENCE = {
        "waiter": {"p25": 3800, "p50": 4500, "p75": 5500},
        "cashier": {"p25": 3500, "p50": 4200, "p75": 5000},
        "chef": {"p25": 5500, "p50": 7000, "p75": 9000},
        "kitchen": {"p25": 3500, "p50": 4500, "p75": 5500},
        "shift_leader": {"p25": 5000, "p50": 6000, "p75": 7500},
        "manager": {"p25": 6000, "p50": 8000, "p75": 10000},
        "store_manager": {"p25": 8000, "p50": 10000, "p75": 13000},
    }

    SALARY_SYSTEM_PROMPT = """你是一位餐饮行业薪酬分析师，拥有丰富的中国二三线城市餐饮连锁薪资调研经验。
基于门店各岗位当前薪资数据和市场参考水平，分析薪资竞争力。

你熟悉餐饮行业的薪资特点：
- 一线员工（服务员/传菜员）薪资弹性小，但离职对运营影响大
- 厨师/厨师长是核心人才，替换成本极高
- 管理岗薪资要有足够吸引力防止被竞对挖角
- 招聘一个新员工的隐性成本约为月薪的2-3倍

请严格按以下JSON格式回复，不要包含其他文字：
{
    "overall_competitiveness": "below_average|average|above_average",
    "positions": [
        {
            "position": "岗位名",
            "avg_salary_yuan": 4500,
            "market_estimate_yuan": 5200,
            "percentile": 25,
            "risk_level": "high|medium|low",
            "recommendation": "具体建议含¥金额",
            "annual_impact_yuan": -12000,
            "saved_recruitment_yuan": 24000,
            "net_impact_yuan": 12000
        }
    ],
    "ai_summary": "综合分析文字（中文，2-4句话）"
}

规则：
1. percentile: 本店薪资在市场中的百分位（P25=低于75%同行）
2. annual_impact_yuan: 调薪导致的年增加成本（负数）
3. saved_recruitment_yuan: 预计节省的招聘培训成本（正数）
4. net_impact_yuan = saved_recruitment_yuan + annual_impact_yuan
5. 综合考虑离职数据给出务实建议"""

    async def analyze_salary_competitiveness(
        self, db: AsyncSession, store_id: str, brand_id: str = ""
    ) -> Dict[str, Any]:
        """
        薪资竞争力分析 -- Claude驱动

        输入：
        - 本店各岗位当前薪资分布
        - 近6个月离职原因分布（薪资原因占比）

        输出：
        - overall_competitiveness: below_average / average / above_average
        - positions: 各岗位竞争力详情 + ¥影响
        - ai_summary: Claude生成的综合分析
        """

        # 1. 收集本店各岗位当前薪资分布
        today = date.today()
        recent_month = f"{today.year}-{today.month:02d}"
        last_month_date = today.replace(day=1) - timedelta(days=1)
        last_month = f"{last_month_date.year}-{last_month_date.month:02d}"

        salary_result = await db.execute(text("""
            SELECT e.position,
                   COUNT(DISTINCT e.id) AS headcount,
                   AVG(p.net_pay_fen) AS avg_pay_fen,
                   MIN(p.net_pay_fen) AS min_pay_fen,
                   MAX(p.net_pay_fen) AS max_pay_fen
            FROM employees e
            JOIN payroll_records p ON p.employee_id = e.id
            WHERE e.store_id = :store_id
              AND e.is_active = true
              AND p.pay_month IN (:m1, :m2)
            GROUP BY e.position
        """), {"store_id": store_id, "m1": recent_month, "m2": last_month})
        position_rows = [dict(r) for r in salary_result.mappings()]

        # 2. 收集近6个月离职数据
        six_months_ago = today - timedelta(days=180)
        turnover_result = await db.execute(text("""
            SELECT COUNT(*) AS total_exits,
                   COUNT(*) FILTER (
                       WHERE remark ILIKE '%薪%'
                          OR remark ILIKE '%工资%'
                          OR remark ILIKE '%待遇%'
                          OR remark ILIKE '%收入%'
                   ) AS salary_exits
            FROM employee_changes
            WHERE store_id = :store_id
              AND change_type = 'resign'
              AND effective_date >= :since
        """), {"store_id": store_id, "since": six_months_ago})
        turnover = turnover_result.mappings().first()
        total_exits = int(turnover["total_exits"]) if turnover else 0
        salary_exits = int(turnover["salary_exits"]) if turnover else 0
        salary_exit_ratio = round(
            salary_exits / max(total_exits, 1) * 100, 1
        )

        # 3. 构建岗位数据
        position_data = []
        for row in position_rows:
            if not row.get("position") or not row.get("avg_pay_fen"):
                continue
            avg_yuan = round(float(row["avg_pay_fen"]) / 100, 2)
            position_data.append({
                "position": row["position"],
                "headcount": row["headcount"],
                "avg_salary_yuan": avg_yuan,
                "min_salary_yuan": round(float(row.get("min_pay_fen") or 0) / 100, 2),
                "max_salary_yuan": round(float(row.get("max_pay_fen") or 0) / 100, 2),
            })

        # 4. 尝试使用 LLM 生成分析
        try:
            if getattr(settings, "LLM_ENABLED", False) and position_data:
                analysis_context = {
                    "store_id": store_id,
                    "position_salaries": position_data,
                    "turnover_stats": {
                        "total_exits_6m": total_exits,
                        "salary_related_exits": salary_exits,
                        "salary_exit_ratio_pct": salary_exit_ratio,
                    },
                    "market_reference": self.MARKET_SALARY_REFERENCE,
                }

                logger.info(
                    "salary_competitiveness_llm_request",
                    store_id=store_id,
                    positions_count=len(position_data),
                )

                response = await get_llm_client().generate(
                    prompt=json.dumps(
                        analysis_context, ensure_ascii=False, default=str
                    ),
                    system_prompt=self.SALARY_SYSTEM_PROMPT,
                    max_tokens=1500,
                    temperature=0.3,
                )

                parsed = self._parse_llm_json(response)

                logger.info(
                    "salary_competitiveness_llm_success",
                    store_id=store_id,
                    overall=parsed.get("overall_competitiveness"),
                )

                return {
                    "store_id": store_id,
                    "overall_competitiveness": parsed.get(
                        "overall_competitiveness", "average"
                    ),
                    "positions": parsed.get("positions", []),
                    "turnover_stats": {
                        "total_exits_6m": total_exits,
                        "salary_related_exits": salary_exits,
                        "salary_exit_ratio_pct": salary_exit_ratio,
                    },
                    "ai_summary": parsed.get("ai_summary", ""),
                    "llm_used": True,
                }

        except Exception as e:
            logger.warning(
                "salary_competitiveness_llm_fallback",
                store_id=store_id,
                error=str(e),
            )

        # 5. 规则引擎回退
        return self._rule_based_salary_analysis(
            store_id, position_data, total_exits, salary_exits, salary_exit_ratio
        )

    def _rule_based_salary_analysis(
        self,
        store_id: str,
        position_data: List[Dict[str, Any]],
        total_exits: int,
        salary_exits: int,
        salary_exit_ratio: float,
    ) -> Dict[str, Any]:
        """规则引擎薪资竞争力分析（LLM不可用时降级）"""
        positions_result = []
        total_annual_impact = 0.0
        total_saved_recruitment = 0.0
        below_count = 0

        for pd in position_data:
            pos = pd["position"]
            avg = pd["avg_salary_yuan"]
            ref = self.MARKET_SALARY_REFERENCE.get(
                pos, {"p25": avg, "p50": avg, "p75": avg}
            )
            market_p50 = ref["p50"]

            # 百分位估算
            if avg <= ref["p25"]:
                percentile = 25
            elif avg <= ref["p50"]:
                percentile = 50
            elif avg <= ref["p75"]:
                percentile = 75
            else:
                percentile = 90

            # 风险判定
            if percentile <= 25:
                risk = "high"
                below_count += 1
            elif percentile <= 50:
                risk = "medium"
            else:
                risk = "low"

            # 调薪建议 + ¥影响
            headcount = pd.get("headcount", 1)
            annual_impact = 0.0
            saved_recruitment = 0.0
            recommendation = ""

            if risk == "high":
                recommended = round(market_p50 * 0.95)
                gap = recommended - avg
                annual_impact = round(-gap * headcount * 12, 2)
                saved_recruitment = round(headcount * 0.2 * 3000, 2)
                recommendation = (
                    f"建议调至¥{recommended:,.0f}，预计降低离职率20%"
                )
            elif risk == "medium":
                recommended = round(market_p50)
                gap = max(recommended - avg, 0)
                annual_impact = round(-gap * headcount * 12, 2)
                saved_recruitment = round(headcount * 0.1 * 3000, 2)
                recommendation = (
                    f"薪资接近市场水平，建议小幅调整至¥{recommended:,.0f}"
                )
            else:
                recommendation = "薪资具有竞争力，建议保持当前水平"

            net_impact = round(saved_recruitment + annual_impact, 2)
            total_annual_impact += annual_impact
            total_saved_recruitment += saved_recruitment

            positions_result.append({
                "position": pos,
                "headcount": headcount,
                "avg_salary_yuan": avg,
                "market_estimate_yuan": market_p50,
                "percentile": percentile,
                "risk_level": risk,
                "recommendation": recommendation,
                "annual_impact_yuan": annual_impact,
                "saved_recruitment_yuan": saved_recruitment,
                "net_impact_yuan": net_impact,
            })

        # 整体竞争力判定
        if not positions_result:
            overall = "average"
        elif below_count > len(positions_result) / 2:
            overall = "below_average"
        elif below_count == 0:
            overall = "above_average"
        else:
            overall = "average"

        total_net = round(total_saved_recruitment + total_annual_impact, 2)
        ai_summary = (
            f"本店共{len(positions_result)}个岗位参与分析，"
            f"其中{below_count}个岗位薪资低于市场P25水平。"
            f"近6个月离职{total_exits}人，薪资原因占比{salary_exit_ratio}%。"
            f"若按建议调整，年增加人力成本¥{abs(total_annual_impact):,.0f}，"
            f"预计节省招聘成本¥{total_saved_recruitment:,.0f}，"
            f"净影响¥{total_net:,.0f}。（规则引擎分析）"
        )

        return {
            "store_id": store_id,
            "overall_competitiveness": overall,
            "positions": positions_result,
            "turnover_stats": {
                "total_exits_6m": total_exits,
                "salary_related_exits": salary_exits,
                "salary_exit_ratio_pct": salary_exit_ratio,
            },
            "ai_summary": ai_summary,
            "llm_used": False,
        }

    # ─── 工具方法 ─────────────────────────────────────────

    @staticmethod
    def _score_to_level(score: int) -> str:
        """风险分 -> 风险等级"""
        if score >= 80:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    @staticmethod
    def _estimate_replacement_cost(profile: Dict[str, Any]) -> float:
        """估算替换成本（招聘+培训+产能损失），单位：元"""
        position = profile.get("employee", {}).get("position", "")
        # 餐饮行业替换成本经验值
        REPLACEMENT_COSTS = {
            "chef": 25000,
            "head_chef": 45000,
            "厨师": 25000,
            "厨师长": 45000,
            "manager": 30000,
            "store_manager": 50000,
            "店长": 50000,
            "waiter": 8000,
            "服务员": 8000,
            "cashier": 10000,
            "收银员": 10000,
            "楼面经理": 35000,
        }
        base = REPLACEMENT_COSTS.get(position, 15000)
        # 工龄越长替换成本越高（经验积累不可替代）
        tenure_days = profile.get("employee", {}).get("tenure_days", 0)
        multiplier = min(1.0 + tenure_days / 365 * 0.2, 2.0)
        return round(base * multiplier, 2)

    @staticmethod
    def _parse_llm_json(response: str) -> Dict[str, Any]:
        """解析LLM返回的JSON，处理```json包裹等情况"""
        text = response.strip()
        # 去除可能的 ```json ... ``` 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首尾的```行
            start = 1 if lines[0].startswith("```") else 0
            end = -1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[start:end]).strip()
        return json.loads(text)

    # ─── 飞轮集成 ─────────────────────────────────────────

    async def _record_to_flywheel(
        self,
        db: AsyncSession,
        store_id: str,
        profile: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """将AI决策结果自动写入决策飞轮，异步执行不阻塞主流程"""
        try:
            from src.services.decision_flywheel_service import DecisionFlywheelService

            flywheel = DecisionFlywheelService()
            employee = profile.get("employee", {})

            # 取第一条建议的预测影响作为整体预测
            recs = result.get("recommendations", [])
            predicted_fen = 0
            confidence = 0.0
            recommendation_text = ""
            if recs:
                first = recs[0]
                predicted_fen = int(
                    first.get("expected_impact_yuan", 0) * 100
                )
                confidence = first.get("confidence", 0.5)
                recommendation_text = first.get("action", "")

            # 查品牌ID
            brand_result = await db.execute(text(
                "SELECT brand_id FROM stores WHERE store_id = :sid LIMIT 1"
            ), {"sid": store_id})
            brand_row = brand_result.mappings().first()
            brand_id = brand_row["brand_id"] if brand_row else "unknown"

            await flywheel.record_decision(
                db=db,
                brand_id=brand_id,
                store_id=store_id,
                decision_type="turnover_risk",
                module="hr_ai",
                source=result.get("data_source", "rules_only"),
                target_type="employee",
                target_id=employee.get("id", ""),
                target_name=employee.get("name", ""),
                recommendation=recommendation_text,
                predicted_impact_fen=predicted_fen,
                confidence=confidence,
                risk_score=result.get("risk_score"),
                ai_analysis=result.get("ai_analysis"),
                context_snapshot={
                    "signals": result.get("signals", []),
                    "replacement_cost_yuan": result.get("replacement_cost_yuan"),
                    "all_recommendations": recs,
                },
            )
        except Exception as e:
            # 飞轮记录失败不影响主流程
            logger.warning(
                "flywheel_record_failed",
                error=str(e),
                employee_id=profile.get("employee", {}).get("id"),
            )
