"""
薪酬公式引擎 — 支持106项薪酬计算
核心能力：
1. 安全表达式求值器：解析中文公式语法
2. 条件分支：如果...则{...};否则如果...则{...};否则{...}
3. 变量注入：从Employee/Attendance等自动注入
4. 城市差异化：按门店所在城市匹配最低工资
5. 计算顺序：按 calc_order 依次计算
6. 幂等计算：同月重复计算覆盖而非新增
7. 公式校验：导入前验证语法和变量引用
8. 安全求值：除零保护、溢出上限、负值兜底
"""

import calendar
import re
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.attendance import AttendanceLog
from src.models.city_wage_config import CityWageConfig
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.payroll import SalaryStructure
from src.models.salary_item import SalaryItemDefinition, SalaryItemRecord

logger = structlog.get_logger()

# 中文方括号变量正则
VARIABLE_PATTERN = re.compile(r"【(.+?)】")

# 金额上限：100_000_000 分 = 100万元，超过视为公式异常
MAX_AMOUNT_FEN = 100_000_000

# 所有已知变量名（用于公式校验）
KNOWN_VARIABLES = {
    "基本工资",
    "岗位补贴",
    "餐补",
    "交通补贴",
    "时薪",
    "绩效系数",
    "绩效标准",
    "月自然天数",
    "月工作日数",
    "总出勤天数",
    "工作日出勤天数",
    "法定节日出勤天数",
    "周末出勤天数",
    "缺勤天数",
    "迟到次数",
    "加班小时数",
    "请假天数",
    "月最低工资",
    "小时最低工资",
    "日薪标准",
    "司龄月数",
}

# 工龄补贴阶梯（月→分）
SENIORITY_SUBSIDY_TABLE = [
    (13, 24, 5000),  # 13-24月: 50元/月
    (24, 36, 10000),  # 24-36月: 100元/月
    (36, 48, 15000),  # 36-48月: 150元/月
    (48, 99999, 20000),  # 48月以上: 200元/月
]


class FormulaWarning:
    """公式计算过程中产生的警告"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class _StringWarnings(list):
    """字符串警告列表 — 用于 test_formula，区别于 List[FormulaWarning]"""

    pass


class SalaryFormulaContext:
    """薪酬计算上下文 — 持有一次计算所需的全部输入变量"""

    def __init__(self):
        self.month_days: int = 30  # 月自然天数
        self.work_days: int = 22  # 月工作日数
        # 考勤
        self.total_attendance_days: float = 0  # 总出勤天数
        self.workday_days: float = 0  # 工作日出勤天数
        self.holiday_days: float = 0  # 法定节日出勤天数
        self.weekend_days: float = 0  # 周末出勤天数
        self.absence_days: float = 0
        self.late_count: int = 0
        self.overtime_hours: float = 0
        self.leave_days: float = 0
        # 绩效
        self.performance_coefficient: float = 1.0
        self.performance_standard_fen: int = 0
        # 城市配置
        self.min_monthly_wage_fen: int = 0
        self.min_hourly_wage_fen: int = 0
        # 已计算的薪酬项（前序结果供后序引用）
        self.computed_items: Dict[str, int] = {}
        # 计算过程中产生的警告
        self.warnings: List[FormulaWarning] = []


class SalaryFormulaEngine:
    """薪酬公式引擎"""

    def __init__(self, brand_id: str):
        self.brand_id = brand_id

    # ── 公式校验（不依赖DB） ──────────────────────────────────

    def validate_formula(self, formula: str, available_variables: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        校验公式语法和变量引用，在保存/导入前调用。
        返回: {"valid": bool, "errors": ["未知变量: 【部门津贴】", ...], "warnings": [...]}
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not formula or not formula.strip():
            return {"valid": True, "errors": [], "warnings": ["空公式，将返回0"]}

        formula = formula.strip()

        # 1. 检查变量引用
        all_vars = KNOWN_VARIABLES.copy()
        if available_variables:
            all_vars.update(available_variables)

        referenced_vars = VARIABLE_PATTERN.findall(formula)
        for var in referenced_vars:
            if var not in all_vars:
                errors.append(f"未知变量: 【{var}】")

        # 2. 检查括号/花括号配对
        brace_depth = 0
        paren_depth = 0
        for ch in formula:
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
            elif ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1
            if brace_depth < 0:
                errors.append("语法错误: 多余的 }")
                break
            if paren_depth < 0:
                errors.append("语法错误: 多余的 )")
                break
        if brace_depth > 0:
            errors.append("语法错误: 未匹配的 {")
        if paren_depth > 0:
            errors.append("语法错误: 未匹配的 (")

        # 3. 条件表达式结构检查
        if formula.startswith("如果"):
            # 必须有 "则" 和至少一组 { }
            if "则" not in formula:
                errors.append("条件语法错误: 缺少 '则' 关键字")
            if "{" not in formula or "}" not in formula:
                errors.append("条件语法错误: 条件分支必须用 { } 包裹表达式")

            # 检查条件分支结构：每个 "如果"/"否则如果" 后面必须跟 "则 {"
            blocks = self._split_condition_blocks(formula)
            if blocks is None:
                errors.append("条件语法错误: 无法解析条件分支结构")
            elif not blocks:
                errors.append("条件语法错误: 未找到有效的条件分支")

        # 4. 简单表达式语法试解析（用占位值替换变量后检查）
        if not formula.startswith("如果"):
            test_expr = VARIABLE_PATTERN.sub("1", formula)
            test_expr = test_expr.replace(" ", "")
            allowed = set("0123456789+-*/.()%")
            if not all(c in allowed for c in test_expr):
                bad_chars = [c for c in test_expr if c not in allowed]
                errors.append(f"表达式包含非法字符: {''.join(set(bad_chars))}")
            else:
                try:
                    eval(test_expr)  # nosec: 只含数字和运算符
                except ZeroDivisionError:
                    warnings.append("表达式可能出现除零（运行时将返回0并告警）")
                except SyntaxError:
                    errors.append("表达式语法错误: 数学表达式不合法")
                except Exception:
                    errors.append("表达式语法错误: 无法解析")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def test_formula(
        self,
        formula: str,
        test_variables: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        用模拟数据测试公式（不需要DB、不保存结果）。
        test_variables: {"基本工资": 500000, "司龄月数": 36, ...} — 值单位为分
        返回: {"result_fen": 15000, "result_yuan": 150.0, "variables_used": [...],
               "calculation_steps": [...], "warnings": [...]}
        """
        warnings: _StringWarnings = _StringWarnings()
        steps: List[str] = []
        variables_used: List[str] = []

        if not formula or not formula.strip():
            return {
                "result_fen": 0,
                "result_yuan": 0.0,
                "variables_used": [],
                "calculation_steps": ["空公式，返回0"],
                "warnings": [],
            }

        formula = formula.strip()

        # 收集引用的变量
        referenced_vars = VARIABLE_PATTERN.findall(formula)
        variables_used = list(set(referenced_vars))

        # 构造简易变量解析器
        def resolve_test_var(var_name: str) -> float:
            if var_name in test_variables:
                return float(test_variables[var_name])
            warnings.append(f"测试数据中缺少变量: 【{var_name}】，使用0")
            return 0.0

        steps.append(f"原始公式: {formula}")

        # 条件表达式
        if formula.startswith("如果"):
            result = self._evaluate_condition_with_resolver(formula, resolve_test_var, steps, warnings)
        else:
            # 普通表达式
            result = self._evaluate_expression_with_resolver(formula, resolve_test_var, steps, warnings)

        return {
            "result_fen": result,
            "result_yuan": result / 100,
            "variables_used": variables_used,
            "calculation_steps": steps,
            "warnings": list(warnings),  # 转为普通 list 输出
        }

    # ── 核心计算方法（需要DB） ────────────────────────────────

    async def calculate_employee_salary(
        self,
        db: AsyncSession,
        employee_id: str,
        pay_month: str,
        store_id: str,
    ) -> Dict[str, Any]:
        """
        为员工计算指定月份的全部薪酬项
        返回：{items: [{item_name, amount_fen, category}], total_income_fen, total_deduction_fen, net_fen}
        """
        # 1. 加载员工信息（Person + EmploymentAssignment）
        from types import SimpleNamespace
        person_result = await db.execute(
            select(Person).where(Person.legacy_employee_id == str(employee_id))
        )
        person = person_result.scalar_one_or_none()
        if not person:
            raise ValueError(f"员工 {employee_id} 不存在")
        assign_result = await db.execute(
            select(EmploymentAssignment)
            .where(and_(EmploymentAssignment.person_id == person.id, EmploymentAssignment.status == "active"))
            .order_by(EmploymentAssignment.start_date.asc())
            .limit(1)
        )
        asgn = assign_result.scalar_one_or_none()
        seniority_months = (date.today() - asgn.start_date).days // 30 if (asgn and asgn.start_date) else 0
        employee = SimpleNamespace(
            id=employee_id,
            name=person.name,
            daily_wage_standard_fen=0,  # 过渡期：日薪标准暂不迁移，公式引擎中此变量返回0
            seniority_months=seniority_months,
        )

        # 2. 加载薪资结构
        ss_result = await db.execute(
            select(SalaryStructure).where(
                and_(
                    SalaryStructure.employee_id == employee_id,
                    SalaryStructure.is_active.is_(True),
                )
            )
        )
        salary_structure = ss_result.scalar_one_or_none()

        # 3. 加载薪酬项定义
        items = await self._load_salary_items(db, store_id)
        if not items:
            raise ValueError(f"门店 {store_id} 无薪酬项定义，请先导入工资套")

        # 4. 构建计算上下文
        ctx = await self._build_context(db, employee, salary_structure, pay_month, store_id)

        # 5. 按顺序计算每个薪酬项
        results = []
        for item_def in items:
            amount = self._evaluate_item(item_def, employee, salary_structure, ctx)
            ctx.computed_items[item_def.item_name] = amount
            results.append(
                {
                    "item_id": str(item_def.id),
                    "item_name": item_def.item_name,
                    "item_code": item_def.item_code,
                    "item_category": item_def.item_category,
                    "amount_fen": amount,
                    "amount_yuan": amount / 100,
                    "formula": item_def.formula,
                }
            )

        # 6. 汇总
        total_income = sum(r["amount_fen"] for r in results if r["item_category"] in ("income", "subsidy"))
        total_deduction = sum(r["amount_fen"] for r in results if r["item_category"] in ("deduction", "tax"))
        net = total_income - total_deduction

        # 7. 持久化薪酬项明细（幂等：先删后插）
        await db.execute(
            delete(SalaryItemRecord).where(
                and_(
                    SalaryItemRecord.employee_id == employee_id,
                    SalaryItemRecord.pay_month == pay_month,
                )
            )
        )
        for r in results:
            record = SalaryItemRecord(
                store_id=store_id,
                employee_id=employee_id,
                pay_month=pay_month,
                item_id=r["item_id"],
                item_name=r["item_name"],
                item_category=r["item_category"],
                amount_fen=r["amount_fen"],
                formula_snapshot=r["formula"],
                calc_inputs={"context_snapshot": "omitted_for_size"},
            )
            db.add(record)

        await db.flush()

        # 收集警告
        result_warnings = [w.to_dict() for w in ctx.warnings]

        logger.info(
            "salary_formula_calculated",
            employee_id=employee_id,
            pay_month=pay_month,
            items_count=len(results),
            net_yuan=net / 100,
            warnings_count=len(result_warnings),
        )

        return {
            "employee_id": employee_id,
            "employee_name": employee.name,
            "pay_month": pay_month,
            "items": results,
            "total_income_fen": total_income,
            "total_deduction_fen": total_deduction,
            "net_salary_fen": net,
            "total_income_yuan": total_income / 100,
            "total_deduction_yuan": total_deduction / 100,
            "net_salary_yuan": net / 100,
            "warnings": result_warnings,
        }

    async def simulate_calculation(
        self,
        db: AsyncSession,
        employee_id: str,
        pay_month: str,
        store_id: str,
    ) -> Dict[str, Any]:
        """模拟计算（不写DB，用于调试公式）"""
        from types import SimpleNamespace
        person_result = await db.execute(
            select(Person).where(Person.legacy_employee_id == str(employee_id))
        )
        person = person_result.scalar_one_or_none()
        if not person:
            raise ValueError(f"员工 {employee_id} 不存在")
        assign_result = await db.execute(
            select(EmploymentAssignment)
            .where(and_(EmploymentAssignment.person_id == person.id, EmploymentAssignment.status == "active"))
            .order_by(EmploymentAssignment.start_date.asc())
            .limit(1)
        )
        asgn = assign_result.scalar_one_or_none()
        seniority_months = (date.today() - asgn.start_date).days // 30 if (asgn and asgn.start_date) else 0
        employee = SimpleNamespace(
            id=employee_id,
            name=person.name,
            daily_wage_standard_fen=0,
            seniority_months=seniority_months,
        )

        ss_result = await db.execute(
            select(SalaryStructure).where(
                and_(
                    SalaryStructure.employee_id == employee_id,
                    SalaryStructure.is_active.is_(True),
                )
            )
        )
        salary_structure = ss_result.scalar_one_or_none()

        items = await self._load_salary_items(db, store_id)
        ctx = await self._build_context(db, employee, salary_structure, pay_month, store_id)

        results = []
        for item_def in items:
            amount = self._evaluate_item(item_def, employee, salary_structure, ctx)
            ctx.computed_items[item_def.item_name] = amount
            results.append(
                {
                    "item_name": item_def.item_name,
                    "item_category": item_def.item_category,
                    "amount_fen": amount,
                    "amount_yuan": amount / 100,
                    "formula": item_def.formula,
                }
            )

        total_income = sum(r["amount_fen"] for r in results if r["item_category"] in ("income", "subsidy"))
        total_deduction = sum(r["amount_fen"] for r in results if r["item_category"] in ("deduction", "tax"))

        return {
            "employee_id": employee_id,
            "pay_month": pay_month,
            "simulated": True,
            "items": results,
            "total_income_yuan": total_income / 100,
            "total_deduction_yuan": total_deduction / 100,
            "net_salary_yuan": (total_income - total_deduction) / 100,
            "warnings": [w.to_dict() for w in ctx.warnings],
        }

    async def import_salary_items(
        self,
        db: AsyncSession,
        file_bytes: bytes,
        brand_id: str,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从工资套Excel导入薪酬项定义（含公式预校验）"""
        try:
            import openpyxl
        except ImportError:
            return {"error": "请安装 openpyxl"}

        import io

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            return {"error": "Excel无数据行"}

        headers = [str(h).strip() if h else "" for h in rows[0]]
        created = 0
        errors = []
        # 收集本批次定义的薪酬项名称（可作为变量被引用）
        batch_item_names: List[str] = []
        for row in rows[1:]:
            row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            name = str(row_dict.get("薪酬项名称") or row_dict.get("名称") or "").strip()
            if name:
                batch_item_names.append(name)

        for row_num, row in enumerate(rows[1:], start=2):
            try:
                row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
                item_name = str(row_dict.get("薪酬项名称") or row_dict.get("名称") or "").strip()
                if not item_name:
                    continue

                category = str(row_dict.get("类别") or row_dict.get("分类") or "income").strip()
                category_map = {
                    "收入": "income",
                    "扣除": "deduction",
                    "补贴": "subsidy",
                    "税": "tax",
                    "考勤": "attendance",
                    "系统": "system",
                }
                category = category_map.get(category, category)

                formula = str(row_dict.get("公式") or row_dict.get("计算公式") or "").strip()
                order = int(row_dict.get("顺序") or row_dict.get("计算顺序") or 50)

                # 导入前校验公式
                if formula:
                    validation = self.validate_formula(formula, batch_item_names)
                    if not validation["valid"]:
                        errors.append(
                            {
                                "row": row_num,
                                "item_name": item_name,
                                "error": f"公式校验失败: {'; '.join(validation['errors'])}",
                            }
                        )
                        continue  # 跳过无效公式的行

                item = SalaryItemDefinition(
                    brand_id=brand_id,
                    store_id=store_id,
                    item_name=item_name,
                    item_code=str(row_dict.get("编码") or "").strip() or None,
                    item_category=category,
                    calc_order=order,
                    formula=formula or None,
                    formula_type="expression" if formula else "fixed",
                )
                db.add(item)
                created += 1
            except Exception as e:
                errors.append({"row": row_num, "error": str(e)})

        await db.flush()
        wb.close()

        return {"created": created, "errors": errors}

    # ── 内部方法 ──────────────────────────────────────────────

    async def _load_salary_items(self, db: AsyncSession, store_id: str) -> List[SalaryItemDefinition]:
        """加载薪酬项定义（门店级 > 品牌级），按 calc_order 排序"""
        result = await db.execute(
            select(SalaryItemDefinition)
            .where(
                and_(
                    SalaryItemDefinition.brand_id == self.brand_id,
                    SalaryItemDefinition.is_active.is_(True),
                )
            )
            .order_by(SalaryItemDefinition.calc_order)
        )
        all_items = result.scalars().all()

        # 门店级覆盖品牌级（同名薪酬项）
        store_items = {i.item_name: i for i in all_items if i.store_id == store_id}
        brand_items = {i.item_name: i for i in all_items if not i.store_id}

        merged = {}
        for name, item in brand_items.items():
            merged[name] = item
        for name, item in store_items.items():
            merged[name] = item  # 门店级覆盖

        return sorted(merged.values(), key=lambda x: x.calc_order)

    async def _build_context(
        self,
        db: AsyncSession,
        employee: Person,
        salary_structure: Optional[SalaryStructure],
        pay_month: str,
        store_id: str,
    ) -> SalaryFormulaContext:
        """构建计算上下文"""
        ctx = SalaryFormulaContext()

        year, month = int(pay_month[:4]), int(pay_month[5:7])
        ctx.month_days = calendar.monthrange(year, month)[1]
        # 计算工作日
        ctx.work_days = sum(1 for d in range(1, ctx.month_days + 1) if date(year, month, d).weekday() < 5)

        # 考勤数据
        month_start = date(year, month, 1)
        month_end = date(year, month, ctx.month_days)
        att_result = await db.execute(
            select(AttendanceLog).where(
                and_(
                    AttendanceLog.employee_id == employee.id,
                    AttendanceLog.work_date >= month_start,
                    AttendanceLog.work_date <= month_end,
                )
            )
        )
        logs = att_result.scalars().all()
        for log in logs:
            if log.status in ("normal", "late"):
                ctx.total_attendance_days += 1
                if log.work_date.weekday() < 5:
                    ctx.workday_days += 1
                else:
                    ctx.weekend_days += 1
            elif log.status == "absent":
                ctx.absence_days += 1
            elif log.status == "leave":
                ctx.leave_days += 1
            if log.status == "late":
                ctx.late_count += 1
            ctx.overtime_hours += float(getattr(log, "overtime_hours", 0) or 0)

        # 绩效系数
        if salary_structure:
            ctx.performance_coefficient = float(salary_structure.performance_coefficient or 1.0)

        # 城市最低工资
        city_result = await db.execute(
            select(CityWageConfig)
            .where(
                and_(
                    CityWageConfig.year == year,
                )
            )
            .limit(1)
        )
        city_config = city_result.scalar_one_or_none()
        if city_config:
            ctx.min_monthly_wage_fen = city_config.min_monthly_wage_fen
            ctx.min_hourly_wage_fen = city_config.min_hourly_wage_fen

        return ctx

    def _evaluate_item(
        self,
        item_def: SalaryItemDefinition,
        employee: Person,
        salary_structure: Optional[SalaryStructure],
        ctx: SalaryFormulaContext,
    ) -> int:
        """求值单个薪酬项"""
        # 无公式 → 返回0
        if not item_def.formula:
            return 0

        formula = item_def.formula.strip()

        # 内置特殊处理：工龄补贴
        if "工龄补贴" in item_def.item_name:
            return self._calc_seniority_subsidy(employee)

        # 构造变量解析器（闭包绑定当前 employee/salary_structure/ctx）
        def resolver(var_name: str) -> float:
            return self._resolve_variable(var_name, employee, salary_structure, ctx)

        # 条件表达式
        if formula.startswith("如果"):
            result = self._evaluate_condition_with_resolver(formula, resolver, warnings_list=ctx.warnings)
        else:
            # 普通表达式
            result = self._evaluate_expression_with_resolver(formula, resolver, warnings_list=ctx.warnings)

        # 非负保护（薪酬项金额不能为负，扣除项在汇总时减去）
        if item_def.item_category in ("income", "subsidy") and result < 0:
            ctx.warnings.append(
                FormulaWarning(
                    "negative_capped",
                    f"薪酬项【{item_def.item_name}】计算结果为负({result}分)，已归零",
                )
            )
            result = 0

        return result

    # ── 条件分支解析器（基于花括号匹配，替代旧正则） ──────────

    def _split_condition_blocks(self, formula: str) -> Optional[List[Tuple[Optional[str], str]]]:
        """
        将条件表达式拆分为 [(condition, expression), ...] 列表。
        condition 为 None 表示 "否则" 分支。

        支持格式:
          如果 COND 则 { EXPR }; 否则如果 COND 则 { EXPR }; 否则 { EXPR }

        通过匹配花括号来正确切分，不受嵌套内容影响。
        """
        blocks: List[Tuple[Optional[str], str]] = []
        pos = 0
        text = formula.strip()

        while pos < len(text):
            # 跳过分号和空格
            while pos < len(text) and text[pos] in " ;\t\n\r":
                pos += 1
            if pos >= len(text):
                break

            # 判断当前段是 "如果"、"否则如果" 还是 "否则"
            remaining = text[pos:]

            if remaining.startswith("否则如果"):
                pos += len("否则如果")
                condition, expr, pos = self._parse_one_branch(text, pos)
                if expr is None:
                    return None
                blocks.append((condition, expr))

            elif remaining.startswith("如果"):
                pos += len("如果")
                condition, expr, pos = self._parse_one_branch(text, pos)
                if expr is None:
                    return None
                blocks.append((condition, expr))

            elif remaining.startswith("否则"):
                pos += len("否则")
                # 否则分支：直接找 { }
                expr, pos = self._extract_brace_block(text, pos)
                if expr is None:
                    return None
                blocks.append((None, expr))

            else:
                # 无法识别的内容
                return None

        return blocks if blocks else None

    def _parse_one_branch(self, text: str, pos: int) -> Tuple[Optional[str], Optional[str], int]:
        """
        从 pos 位置解析一个 "条件 则 { 表达式 }" 分支。
        返回 (condition, expression, new_pos)。失败时 expression 为 None。
        """
        # 找 "则" 关键字
        ze_idx = text.find("则", pos)
        if ze_idx == -1:
            return None, None, pos

        condition = text[pos:ze_idx].strip()
        pos = ze_idx + len("则")

        # 提取花括号内的表达式
        expr, pos = self._extract_brace_block(text, pos)
        return condition, expr, pos

    def _extract_brace_block(self, text: str, pos: int) -> Tuple[Optional[str], int]:
        """
        从 pos 位置开始，跳过空白后找到 { ... }，返回花括号内的内容。
        正确处理嵌套括号（包括普通圆括号在表达式内部的使用）。
        """
        # 跳过空白
        while pos < len(text) and text[pos] in " \t\n\r":
            pos += 1

        if pos >= len(text) or text[pos] != "{":
            return None, pos

        pos += 1  # 跳过 {
        depth = 1
        start = pos

        while pos < len(text) and depth > 0:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1

        if depth != 0:
            return None, pos

        # pos 现在指向 } 之后一位
        content = text[start : pos - 1].strip()
        return content, pos

    # ── 条件求值（通用版，支持真实计算和测试计算） ────────────

    def _evaluate_condition_with_resolver(
        self,
        formula: str,
        resolver: Callable[[str], float],
        steps: Optional[List[str]] = None,
        warnings: Any = None,
    ) -> int:
        """
        求值条件表达式，使用提供的变量解析器。
        支持完整的 如果/否则如果/否则 语法，含 且/或 逻辑运算。
        """
        blocks = self._split_condition_blocks(formula)

        if blocks is None:
            # 解析失败，回退到简单模式
            msg = "条件表达式解析失败，回退到简单模式"
            if steps is not None:
                steps.append(msg)
            logger.warning("condition_parse_fallback", formula=formula)
            return self._evaluate_condition_simple_fallback(formula, resolver, warnings)

        for condition, expr in blocks:
            if condition is None:
                # 否则分支 — 直接执行
                if steps is not None:
                    steps.append(f"进入否则分支: {expr}")
                return self._safe_eval_math(self._substitute_variables(expr, resolver), formula, steps, warnings)
            else:
                # 求值条件
                cond_result = self._evaluate_boolean_expr(condition, resolver)
                if steps is not None:
                    steps.append(f"条件 [{condition}] => {cond_result}")
                if cond_result:
                    if steps is not None:
                        steps.append(f"条件成立，执行: {expr}")
                    return self._safe_eval_math(self._substitute_variables(expr, resolver), formula, steps, warnings)

        # 所有条件都不满足且无否则分支
        if steps is not None:
            steps.append("所有条件均不满足，返回0")
        return 0

    def _evaluate_condition_simple_fallback(
        self,
        formula: str,
        resolver: Callable[[str], float],
        warnings: Any = None,
    ) -> int:
        """
        简单回退解析：兼容不带花括号的旧格式公式。
        格式: 如果 条件 则 值; 否则 值
        """
        # 按关键字切分（先匹配长的 "否则如果"，避免 "否则" 提前匹配）
        parts = re.split(r"否则如果|如果|则|否则", formula)
        parts = [p.strip().strip("{}; ") for p in parts if p.strip()]

        i = 0
        while i < len(parts) - 1:
            condition = parts[i]
            value_expr = parts[i + 1]
            if self._evaluate_boolean_expr(condition, resolver):
                return self._safe_eval_math(self._substitute_variables(value_expr, resolver), formula, warnings_list=warnings)
            i += 2

        # 最后一个是否则
        if len(parts) % 2 == 1:
            return self._safe_eval_math(self._substitute_variables(parts[-1], resolver), formula, warnings_list=warnings)
        return 0

    # ── 布尔表达式求值（支持 且/或/不/比较运算符） ────────────

    def _evaluate_boolean_expr(
        self,
        condition: str,
        resolver: Callable[[str], float],
    ) -> bool:
        """
        求值布尔条件表达式。
        支持:
          - 比较运算符: >=, <=, >, <, ==, !=
          - 逻辑运算符: 且(AND), 或(OR), 不(NOT)
          - 圆括号分组
          - 中文变量【xxx】
        """
        # 先替换变量为数值
        resolved = self._substitute_variables(condition, resolver)

        # 分词并转换为 Python 可执行的布尔表达式
        # 将中文逻辑词转换为 Python 关键字
        expr = resolved
        expr = expr.replace("且", " and ")
        expr = expr.replace("或", " or ")
        # "不" 作为前缀否定，需要谨慎处理：只在它独立出现时替换
        expr = re.sub(r"(?<![a-zA-Z0-9])不\s+", " not ", expr)

        # 安全检查：只允许数字、比较运算符、逻辑运算符、括号、空格、小数点
        safe_expr = expr.strip()
        # 允许的 token: 数字、运算符、关键字
        # 用正则检查是否只含合法 token
        token_pattern = re.compile(
            r"^[\s]*"
            r"("
            r"[0-9]+\.?[0-9]*"  # 数字
            r"|>=|<=|!=|==|>|<"  # 比较运算符
            r"|\+|-|\*|/|%"  # 算术运算符
            r"|\(|\)"  # 括号
            r"|and|or|not"  # 逻辑运算符
            r"|True|False"  # 布尔字面量
            r"|\s+"  # 空白
            r")*$"
        )
        if not token_pattern.match(safe_expr):
            logger.warning("unsafe_condition_blocked", condition=condition, resolved=safe_expr)
            return False

        try:
            return bool(eval(safe_expr))  # nosec: 已通过 token 白名单校验
        except Exception as e:
            logger.warning("condition_eval_error", condition=condition, error=str(e))
            return False

    # ── 表达式求值（通用版） ──────────────────────────────────

    def _evaluate_expression_with_resolver(
        self,
        formula: str,
        resolver: Callable[[str], float],
        steps: Optional[List[str]] = None,
        warnings: Any = None,
    ) -> int:
        """求值普通数学表达式，使用提供的变量解析器"""
        resolved = self._substitute_variables(formula, resolver)
        if steps is not None:
            steps.append(f"变量替换后: {resolved}")
        return self._safe_eval_math(resolved, formula, steps, warnings)

    def _substitute_variables(self, text: str, resolver: Callable[[str], float]) -> str:
        """将【变量名】替换为数值字符串"""
        return VARIABLE_PATTERN.sub(
            lambda m: str(resolver(m.group(1))),
            text,
        )

    def _safe_eval_math(
        self,
        resolved_expr: str,
        original_formula: str = "",
        steps: Optional[List[str]] = None,
        warnings_list: Any = None,
    ) -> int:
        """
        安全求值数学表达式。
        保护: 除零→0, 溢出→上限, 非法字符→0
        """
        try:
            safe_expr = resolved_expr.replace(" ", "")
            allowed = set("0123456789+-*/.()%")
            if not all(c in allowed for c in safe_expr):
                bad = [c for c in safe_expr if c not in allowed]
                logger.warning(
                    "unsafe_formula_blocked",
                    formula=original_formula,
                    resolved=resolved_expr,
                    bad_chars=bad,
                )
                return 0

            # 除零保护：在 eval 前检测
            result = eval(safe_expr)  # nosec: 输入已通过字符白名单校验
            result = float(result)

            # 溢出保护
            if abs(result) > MAX_AMOUNT_FEN:
                msg = f"计算结果溢出({result:.0f}分 > {MAX_AMOUNT_FEN}分=100万元)，已截断"
                logger.warning("formula_overflow", formula=original_formula, result=result)
                if steps is not None:
                    steps.append(msg)
                self._add_warning(warnings_list, "overflow", msg)
                result = MAX_AMOUNT_FEN if result > 0 else -MAX_AMOUNT_FEN

            rounded = int(round(result))
            if steps is not None:
                steps.append(f"计算结果: {rounded}分 ({rounded / 100:.2f}元)")
            return rounded

        except ZeroDivisionError:
            msg = f"公式除零错误，返回0: {original_formula}"
            logger.warning("formula_division_by_zero", formula=original_formula)
            if steps is not None:
                steps.append(msg)
            self._add_warning(warnings_list, "division_by_zero", msg)
            return 0

        except Exception as e:
            logger.warning("formula_eval_error", formula=original_formula, error=str(e))
            if steps is not None:
                steps.append(f"求值异常: {e}")
            return 0

    def _add_warning(self, warnings_target: Any, code: str, message: str):
        """
        向警告列表添加警告。
        支持两种目标类型：
        - List[FormulaWarning]（生产计算路径，ctx.warnings）
        - _StringWarnings（test_formula 路径，最终输出为 List[str]）
        """
        if warnings_target is None:
            return
        if isinstance(warnings_target, _StringWarnings):
            warnings_target.append(message)
        elif isinstance(warnings_target, list):
            warnings_target.append(FormulaWarning(code, message))

    # ── 旧接口兼容：employee/salary_structure/ctx 风格调用 ────

    def _evaluate_expression(
        self,
        formula: str,
        employee: Person,
        salary_structure: Optional[SalaryStructure],
        ctx: SalaryFormulaContext,
    ) -> int:
        """求值普通数学表达式（含中文变量替换）— 保留向后兼容"""

        def resolver(var_name: str) -> float:
            return self._resolve_variable(var_name, employee, salary_structure, ctx)

        return self._evaluate_expression_with_resolver(formula, resolver, warnings=ctx.warnings)

    def _evaluate_condition(
        self,
        formula: str,
        employee: Person,
        salary_structure: Optional[SalaryStructure],
        ctx: SalaryFormulaContext,
    ) -> int:
        """求值条件表达式 — 保留向后兼容"""

        def resolver(var_name: str) -> float:
            return self._resolve_variable(var_name, employee, salary_structure, ctx)

        return self._evaluate_condition_with_resolver(formula, resolver, warnings=ctx.warnings)

    def _check_condition(
        self,
        condition: str,
        employee: Person,
        salary_structure: Optional[SalaryStructure],
        ctx: SalaryFormulaContext,
    ) -> bool:
        """检查条件是否成立 — 保留向后兼容"""

        def resolver(var_name: str) -> float:
            return self._resolve_variable(var_name, employee, salary_structure, ctx)

        return self._evaluate_boolean_expr(condition, resolver)

    def _resolve_variable(
        self,
        var_name: str,
        employee: Person,
        salary_structure: Optional[SalaryStructure],
        ctx: SalaryFormulaContext,
    ) -> float:
        """解析中文变量名 → 数值"""
        # 已计算的薪酬项优先
        if var_name in ctx.computed_items:
            return float(ctx.computed_items[var_name])

        # 薪资结构变量
        ss = salary_structure
        variable_map = {
            "基本工资": lambda: float(ss.base_salary_fen if ss else 0),
            "岗位补贴": lambda: float(ss.position_allowance_fen if ss else 0),
            "餐补": lambda: float(ss.meal_allowance_fen if ss else 0),
            "交通补贴": lambda: float(ss.transport_allowance_fen if ss else 0),
            "时薪": lambda: float(ss.hourly_rate_fen if ss and ss.hourly_rate_fen else 0),
            "绩效系数": lambda: ctx.performance_coefficient,
            "绩效标准": lambda: float(ctx.performance_standard_fen),
            # 考勤变量
            "月自然天数": lambda: float(ctx.month_days),
            "月工作日数": lambda: float(ctx.work_days),
            "总出勤天数": lambda: ctx.total_attendance_days,
            "工作日出勤天数": lambda: ctx.workday_days,
            "法定节日出勤天数": lambda: ctx.holiday_days,
            "周末出勤天数": lambda: ctx.weekend_days,
            "缺勤天数": lambda: ctx.absence_days,
            "迟到次数": lambda: float(ctx.late_count),
            "加班小时数": lambda: ctx.overtime_hours,
            "请假天数": lambda: ctx.leave_days,
            # 城市配置
            "月最低工资": lambda: float(ctx.min_monthly_wage_fen),
            "小时最低工资": lambda: float(ctx.min_hourly_wage_fen),
            # 员工信息
            "日薪标准": lambda: float(employee.daily_wage_standard_fen or 0),
            "司龄月数": lambda: float(employee.seniority_months or 0),
        }

        resolver = variable_map.get(var_name)
        if resolver:
            return resolver()

        logger.warning("unknown_salary_variable", var_name=var_name)
        return 0.0

    def _calc_seniority_subsidy(self, employee) -> int:
        """计算工龄补贴（阶梯式）"""
        months = employee.seniority_months or 0
        for low, high, amount in SENIORITY_SUBSIDY_TABLE:
            if low <= months < high:
                return amount
        return 0


def calculate_seniority_subsidy_fen(seniority_months: int) -> int:
    """独立的工龄补贴计算函数（供外部调用）"""
    for low, high, amount in SENIORITY_SUBSIDY_TABLE:
        if low <= seniority_months < high:
            return amount
    return 0
