#!/usr/bin/env python3
"""
生成多品牌运营分析报告（CLI脚本）

为尝在一起、最黔线、尚宫厨生成指定日期范围的综合运营分析报告。
输出格式：HTML（可浏览器打印为PDF）+ JSON。

用法:
  cd apps/api-gateway

  # 生成 2026年3月1日-20日报告（默认全部品牌）
  python scripts/generate_ops_analysis_report.py \\
    --start 2026-03-01 --end 2026-03-20

  # 仅生成尝在一起的报告
  python scripts/generate_ops_analysis_report.py \\
    --start 2026-03-01 --end 2026-03-20 \\
    --brand BRD_CZYZ0001

  # 指定输出目录
  python scripts/generate_ops_analysis_report.py \\
    --start 2026-03-01 --end 2026-03-20 \\
    --output-dir /tmp/reports

环境变量:
  DATABASE_URL — 数据库连接串（默认: postgresql+asyncpg://postgres:password@localhost:5432/tunxiang）
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime

# 路径设置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GATEWAY_DIR = os.path.join(SCRIPT_DIR, "..")
sys.path.insert(0, GATEWAY_DIR)


async def main(start_date: date, end_date: date, brand_ids: list, output_dir: str):
    """生成报告主流程"""
    from src.core.database import get_db_session
    from src.services.ops_analysis_report_service import OpsAnalysisReportService

    print(f"\n{'='*60}")
    print(f"  屯象OS · 多品牌运营分析报告生成器")
    print(f"  报告周期: {start_date} 至 {end_date}")
    print(f"  品牌范围: {'全部种子客户' if not brand_ids else ', '.join(brand_ids)}")
    print(f"{'='*60}\n")

    os.makedirs(output_dir, exist_ok=True)

    async with get_db_session() as db:
        # 生成JSON报告
        print("[1/3] 生成报告数据...")
        report = await OpsAnalysisReportService.generate(
            db=db,
            start_date=start_date,
            end_date=end_date,
            brand_ids=brand_ids or None,
        )

        # 保存JSON
        json_path = os.path.join(
            output_dir,
            f"ops_analysis_{start_date}_{end_date}.json",
        )
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"    ✓ JSON: {json_path}")

        # 生成HTML报告
        print("[2/3] 生成HTML报告...")
        html = await OpsAnalysisReportService.generate_html(
            db=db,
            start_date=start_date,
            end_date=end_date,
            brand_ids=brand_ids or None,
        )
        html_path = os.path.join(
            output_dir,
            f"ops_analysis_{start_date}_{end_date}.html",
        )
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"    ✓ HTML: {html_path}")

        # 打印摘要
        print("\n[3/3] 报告摘要:")
        print(f"    报告周期: {report['period']}")
        print(f"    品牌数量: {report['brand_count']}")
        print()

        for c in report.get("cross_brand_comparison", []):
            status_icon = {"正常": "✅", "偏高": "⚠️", "超标": "❌"}.get(
                c["cost_status"], "❓"
            )
            print(f"    【{c['brand_name']}】")
            print(f"      营收: ¥{c['revenue_yuan']:,.0f}")
            print(f"      订单: {c['orders']:,} 单")
            print(f"      客单价: ¥{c['avg_ticket_yuan']:.0f}")
            print(f"      成本率: {c['food_cost_pct']:.1f}% {status_icon}")
            print(f"      损耗率: {c['waste_pct']:.1f}%")
            print(f"      决策采纳: {c['decision_adoption_pct']:.0f}%")
            print(f"      AI节省: ¥{c['saving_yuan']:,.0f}")
            print()

    print(f"{'='*60}")
    print(f"  报告生成完成！")
    print(f"  HTML报告路径: {html_path}")
    print(f"  （用浏览器打开即可打印为PDF）")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="生成多品牌运营分析报告"
    )
    parser.add_argument(
        "--start", required=True,
        help="开始日期 (yyyy-mm-dd)"
    )
    parser.add_argument(
        "--end", required=True,
        help="结束日期 (yyyy-mm-dd)"
    )
    parser.add_argument(
        "--brand", action="append", default=[],
        help="品牌ID (可多次指定，不指定则全部)"
    )
    parser.add_argument(
        "--output-dir", default="./reports",
        help="输出目录 (默认: ./reports)"
    )

    args = parser.parse_args()

    try:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    except ValueError as e:
        print(f"日期格式错误: {e}")
        sys.exit(1)

    if start > end:
        print("错误: 开始日期不能晚于结束日期")
        sys.exit(1)

    asyncio.run(main(start, end, args.brand, args.output_dir))
