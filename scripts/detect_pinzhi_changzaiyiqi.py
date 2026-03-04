#!/usr/bin/env python3
"""
检测：对接品智 API、拉取尝在一起数据是否实现

在已配置 PINZHI_BASE_URL、PINZHI_TOKEN（尝在一起）的环境运行，
依次执行接口连通性检测与一次月度数据拉取，并输出结论。

用法:
  export PINZHI_BASE_URL="http://ip:port/pzcatering-gateway"
  export PINZHI_TOKEN="your_token"
  python3 scripts/detect_pinzhi_changzaiyiqi.py

  # 指定检测用的营业日（默认昨天）
  python3 scripts/detect_pinzhi_changzaiyiqi.py --date 2026-01-31
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta


def _setup_path():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pinzhi_pkg = os.path.join(repo_root, "packages", "api-adapters", "pinzhi")
    if os.path.isdir(pinzhi_pkg) and pinzhi_pkg not in sys.path:
        sys.path.insert(0, pinzhi_pkg)
    if os.path.basename(os.path.dirname(__file__)) == "scripts":
        parent = os.path.dirname(os.path.dirname(__file__))
        pinzhi_inner = os.path.join(parent, "packages", "api-adapters", "pinzhi")
        if os.path.isdir(pinzhi_inner) and pinzhi_inner not in sys.path:
            sys.path.insert(0, pinzhi_inner)


async def main():
    parser = argparse.ArgumentParser(description="检测品智API对接与尝在一起数据拉取是否实现")
    parser.add_argument("--date", default=None, help="营业日 yyyy-MM-dd，默认昨天")
    args = parser.parse_args()

    base_url = os.getenv("PINZHI_BASE_URL")
    token = os.getenv("PINZHI_TOKEN")
    if not base_url or not token:
        print("【未配置】请设置 PINZHI_BASE_URL 和 PINZHI_TOKEN（尝在一起商户 token）")
        print("→ 对接品智 API、拉取尝在一起数据：无法在本机检测，需在已配置环境运行本脚本。")
        sys.exit(2)

    _setup_path()
    from src.adapter import PinzhiAdapter

    config = {
        "base_url": base_url.rstrip("/"),
        "token": token,
        "timeout": int(os.getenv("PINZHI_TIMEOUT", "30")),
        "retry_times": 2,
    }
    business_date = args.date
    if not business_date:
        business_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print("=" * 60)
    print("检测：对接品智 API · 拉取尝在一起数据")
    print("=" * 60)
    print(f"BASE_URL: {config['base_url']}")
    print(f"营业日:   {business_date}")
    print()

    adapter = PinzhiAdapter(config)
    try:
        # 1) 接口连通性
        print("[1/2] 接口连通性…")
        results = await adapter.run_all_checks(business_date=business_date, ognid=None)
        core_names = {"门店信息", "门店每日经营数据(报表)", "订单列表V2", "菜品类别", "支付方式"}
        core_ok = all(
            next((x for x in results if x["name"] == n), {}).get("ok", False)
            for n in core_names
        )
        if not core_ok:
            failed = [n for n in core_names if not next((x.get("ok") for x in results if x["name"] == n), False)]
            print(f"      结果: 未通过。未通过核心项: {', '.join(failed)}")
            print()
            print("【结论】对接品智 API 在本环境未通过（核心接口不可用），拉取尝在一起数据未实现。")
            print("        请检查 PINZHI_BASE_URL、PINZHI_TOKEN 及网络，或联系品智技术支持。")
            sys.exit(1)
        print("      结果: 通过（核心接口可用）")
        print()

        # 2) 拉取单日经营数据 + 一页订单，验证「能拉取到数据」
        print(f"[2/2] 拉取 {business_date} 单日数据（验证可拉取）…")
        data = await adapter.query_ogn_daily_biz_data(business_date=business_date, ognid=None)
        sum_obj = (data or {}).get("sum") or {}
        daily_rev = None
        for key in ("totalAmount", "realAmount", "consumeAmount_0_0", "consumeAmount"):
            v = sum_obj.get(key)
            if v is not None:
                try:
                    x = float(v)
                    if x >= 0:
                        daily_rev = x / 100.0 if x >= 100 else x
                        break
                except (TypeError, ValueError):
                    pass
        orders = await adapter.query_orders(
            begin_date=business_date, end_date=business_date, page_index=1, page_size=10
        )
        settled = [o for o in (orders or []) if o.get("billStatus") == 1]
        order_count = len(settled)
        revenue_orders = sum(int(o.get("realPrice") or 0) for o in settled) / 100.0

        if daily_rev is not None:
            print(f"      当日经营数据汇总(元): {daily_rev:,.2f}")
        else:
            print("      当日经营数据: 无 sum 或无法解析（可能当日无数据）")
        print(f"      订单样本(已结账): {order_count} 笔")
        if order_count > 0:
            print(f"      样本实收(元): {revenue_orders:,.2f}")
        print()

        print("【结论】对接品智 API 已实现，可拉取尝在一起数据。")
        print("        上述数据即当前 Token 对应主体（尝在一起）的 API 拉取结果，可与品智后台报表比对。")
        print("        详细检测说明见: docs/尝在一起-品智API对接检测说明.md")
        sys.exit(0)

    except Exception as e:
        print(f"检测异常: {e}")
        print()
        print("【结论】对接或拉取过程中发生异常，请检查配置与网络后重试。")
        sys.exit(1)
    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
