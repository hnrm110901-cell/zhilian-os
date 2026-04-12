#!/usr/bin/env python3
"""
Ontology月度Consolidation辅助脚本

功能:
  - 读取指定客户的Ontology快照文件
  - 分析快照各部分的完整度和时效性
  - 输出consolidation提示（提醒审查哪些部分）
  - 标记超过90天未更新的规则为"待重新验证"

重要约束:
  - 本脚本不会自动修改Ontology内容
  - 所有变更建议需要创始人确认后手动执行
  - 仅作为月度审查的辅助工具

用法:
  python scripts/ontology-consolidation.py                          # 检查所有客户快照
  python scripts/ontology-consolidation.py --customer czyz          # 检查指定客户
  python scripts/ontology-consolidation.py --customer czyz --days 60  # 自定义过期天数
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── 配置 ─────────────────────────────────────────────────────────────────────

SNAPSHOTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "ontology-snapshots"
)

TEMPLATE_FILENAME = "template.md"

# 客户快照文件名到中文名的映射
CUSTOMER_MAP = {
    "czyz": ("czyz-changzaiyiqi.md", "尝在一起"),
    "zqx": ("zqx-zuiqianxian.md", "最黔线"),
    "sgc": ("sgc-shanggongchu.md", "尚宫厨"),
}

# 需要检查是否填写的关键标记
UNFILLED_MARKERS = ["待创始人填写", "待填写", "待接入", "待确认"]

# ANSI颜色码
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def parse_snapshot_date(content: str) -> datetime | None:
    """从快照内容中解析'最后consolidation'日期"""
    match = re.search(r"最后consolidation:\s*(\d{4}-\d{2}-\d{2})", content)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            return None
    return None


def parse_creation_date(content: str) -> datetime | None:
    """从快照内容中解析'创建日期'"""
    match = re.search(r"创建日期:\s*(\d{4}-\d{2}-\d{2})", content)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            return None
    return None


def count_unfilled(content: str) -> list[tuple[str, int]]:
    """统计各种未填写标记的数量"""
    results = []
    for marker in UNFILLED_MARKERS:
        count = content.count(marker)
        if count > 0:
            results.append((marker, count))
    return results


def extract_sections(content: str) -> list[tuple[str, str]]:
    """提取Markdown二级标题及其内容"""
    sections = []
    parts = re.split(r"^## ", content, flags=re.MULTILINE)
    for part in parts[1:]:  # 跳过标题前的内容
        lines = part.strip().split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections.append((title, body))
    return sections


def check_section_completeness(title: str, body: str) -> tuple[str, str]:
    """
    检查单个section的完整度
    返回: (状态, 描述)
    状态: "ok" | "warning" | "critical"
    """
    unfilled_count = sum(body.count(m) for m in UNFILLED_MARKERS)

    if unfilled_count == 0 and len(body.strip()) > 20:
        return "ok", "已填写"
    elif unfilled_count > 0:
        return "critical", f"有 {unfilled_count} 处待填写"
    elif len(body.strip()) < 20:
        return "warning", "内容过少，建议补充"
    return "ok", "已填写"


def check_consolidation_log(content: str) -> list[str]:
    """检查Consolidation日志的最近记录"""
    issues = []
    # 查找日志表格中的日期
    dates = re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|", content)
    if not dates:
        issues.append("Consolidation日志为空，从未进行过审查")
    else:
        latest = max(dates)
        try:
            latest_dt = datetime.strptime(latest, "%Y-%m-%d")
            days_ago = (datetime.now() - latest_dt).days
            if days_ago > 90:
                issues.append(f"最近一次consolidation在 {days_ago} 天前 ({latest})，超过90天")
            elif days_ago > 60:
                issues.append(f"最近一次consolidation在 {days_ago} 天前 ({latest})，接近90天阈值")
        except ValueError:
            pass
    return issues


# ── 主检查逻辑 ────────────────────────────────────────────────────────────────

def analyze_snapshot(filepath: str, customer_name: str, expire_days: int) -> dict:
    """分析单个客户的Ontology快照"""
    result = {
        "customer": customer_name,
        "filepath": filepath,
        "exists": False,
        "issues": [],
        "warnings": [],
        "info": [],
        "sections": [],
    }

    if not os.path.exists(filepath):
        result["issues"].append(f"快照文件不存在: {filepath}")
        return result

    result["exists"] = True

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. 检查日期时效性
    last_consolidation = parse_snapshot_date(content)
    creation_date = parse_creation_date(content)

    if last_consolidation:
        days_since = (datetime.now() - last_consolidation).days
        if days_since > expire_days:
            result["issues"].append(
                f"快照已 {days_since} 天未consolidation（阈值: {expire_days}天），"
                f"最后更新: {last_consolidation.strftime('%Y-%m-%d')}。"
                f"建议: 标记所有业务规则为「待重新验证」"
            )
        elif days_since > expire_days * 2 // 3:
            result["warnings"].append(
                f"距上次consolidation已 {days_since} 天，接近 {expire_days} 天阈值"
            )
        else:
            result["info"].append(
                f"上次consolidation: {last_consolidation.strftime('%Y-%m-%d')} ({days_since}天前)"
            )
    else:
        result["issues"].append("未找到'最后consolidation'日期字段")

    # 2. 检查未填写项
    unfilled = count_unfilled(content)
    if unfilled:
        total = sum(c for _, c in unfilled)
        detail = ", ".join(f"'{m}'x{c}" for m, c in unfilled)
        result["issues"].append(f"共有 {total} 处未填写内容: {detail}")

    # 3. 逐section检查
    sections = extract_sections(content)
    for title, body in sections:
        status, desc = check_section_completeness(title, body)
        result["sections"].append((title, status, desc))

    # 4. 检查Consolidation日志
    log_issues = check_consolidation_log(content)
    for issue in log_issues:
        result["warnings"].append(issue)

    return result


def print_report(result: dict):
    """打印单个客户的分析报告"""
    print(f"\n{'='*70}")
    print(f"{BOLD}{CYAN}  客户: {result['customer']}{RESET}")
    print(f"  文件: {result['filepath']}")
    print(f"{'='*70}")

    if not result["exists"]:
        print(f"\n  {RED}[缺失] 快照文件不存在，需要创建{RESET}")
        return

    # 打印issues (红色)
    if result["issues"]:
        print(f"\n  {RED}{BOLD}[需要处理] {len(result['issues'])} 个问题:{RESET}")
        for i, issue in enumerate(result["issues"], 1):
            print(f"  {RED}  {i}. {issue}{RESET}")

    # 打印warnings (黄色)
    if result["warnings"]:
        print(f"\n  {YELLOW}{BOLD}[注意] {len(result['warnings'])} 个警告:{RESET}")
        for i, warning in enumerate(result["warnings"], 1):
            print(f"  {YELLOW}  {i}. {warning}{RESET}")

    # 打印info (绿色)
    if result["info"]:
        for info in result["info"]:
            print(f"\n  {GREEN}[正常] {info}{RESET}")

    # 打印section状态
    if result["sections"]:
        print(f"\n  {BOLD}各部分状态:{RESET}")
        for title, status, desc in result["sections"]:
            if status == "ok":
                icon = f"{GREEN}[完整]{RESET}"
            elif status == "warning":
                icon = f"{YELLOW}[不足]{RESET}"
            else:
                icon = f"{RED}[待填]{RESET}"
            print(f"    {icon} {title}: {desc}")


def print_consolidation_checklist(customer_name: str):
    """打印月度consolidation检查清单"""
    print(f"\n{'─'*70}")
    print(f"{BOLD}{CYAN}  月度Consolidation检查清单 — {customer_name}{RESET}")
    print(f"{'─'*70}")
    checklist = [
        "[ ] 1. 与创始人确认: 本月是否有新的业务规则变更?",
        "[ ] 2. 检查成本管理目标: 食材/人力/租金/损耗目标是否需要调整?",
        "[ ] 3. 审查因果判断: 已验证的因果关系是否仍然成立?",
        "[ ] 4. 处理待验证假设: 本月是否有假设被数据验证或否定?",
        "[ ] 5. 检查废弃规则: 是否有规则不再适用需要归档?",
        "[ ] 6. 更新本体层节点统计: 从Neo4j导出最新节点数量",
        "[ ] 7. 确认外部系统集成状态: POS/会员/供应链连接是否正常?",
        "[ ] 8. 更新Consolidation日志: 记录本次审查的变更内容",
        "[ ] 9. 更新快照版本号和'最后consolidation'日期",
    ]
    for item in checklist:
        print(f"  {item}")


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ontology月度Consolidation辅助脚本"
    )
    parser.add_argument(
        "--customer", "-c",
        type=str,
        default=None,
        help="客户代号 (czyz/zqx/sgc)，不指定则检查所有客户"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=90,
        help="过期天数阈值，默认90天"
    )
    parser.add_argument(
        "--checklist",
        action="store_true",
        help="输出月度consolidation检查清单"
    )
    args = parser.parse_args()

    print(f"\n{BOLD}Ontology Consolidation 审查报告{RESET}")
    print(f"审查日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"过期阈值: {args.days} 天")

    # 确定要检查的客户
    if args.customer:
        if args.customer not in CUSTOMER_MAP:
            print(f"\n{RED}未知客户代号: {args.customer}{RESET}")
            print(f"可用客户: {', '.join(CUSTOMER_MAP.keys())}")
            sys.exit(1)
        customers = {args.customer: CUSTOMER_MAP[args.customer]}
    else:
        customers = CUSTOMER_MAP

    # 同时扫描目录中未在映射表中的快照文件
    if os.path.isdir(SNAPSHOTS_DIR):
        for f in sorted(os.listdir(SNAPSHOTS_DIR)):
            if f.endswith(".md") and f != TEMPLATE_FILENAME:
                # 检查是否已在映射表中
                already_mapped = any(fn == f for fn, _ in CUSTOMER_MAP.values())
                if not already_mapped:
                    key = f.replace(".md", "")
                    customers[key] = (f, f.replace(".md", ""))

    # 执行检查
    all_results = []
    for key, (filename, name) in customers.items():
        filepath = os.path.join(SNAPSHOTS_DIR, filename)
        result = analyze_snapshot(filepath, name, args.days)
        all_results.append(result)
        print_report(result)

        if args.checklist:
            print_consolidation_checklist(name)

    # 汇总
    print(f"\n{'='*70}")
    print(f"{BOLD}  汇总{RESET}")
    print(f"{'='*70}")

    total_issues = sum(len(r["issues"]) for r in all_results)
    total_warnings = sum(len(r["warnings"]) for r in all_results)
    missing = sum(1 for r in all_results if not r["exists"])

    if total_issues == 0 and total_warnings == 0 and missing == 0:
        print(f"\n  {GREEN}{BOLD}所有快照状态良好{RESET}")
    else:
        if missing > 0:
            print(f"  {RED}缺失快照: {missing} 个客户{RESET}")
        if total_issues > 0:
            print(f"  {RED}需要处理: {total_issues} 个问题{RESET}")
        if total_warnings > 0:
            print(f"  {YELLOW}注意事项: {total_warnings} 个警告{RESET}")

    print(f"\n  提示: 使用 --checklist 参数可输出月度审查检查清单")
    print(f"  提示: 所有变更建议需创始人确认后手动执行，本脚本不自动修改快照内容\n")

    # 如果有过期快照，返回非零退出码
    if total_issues > 0 or missing > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
