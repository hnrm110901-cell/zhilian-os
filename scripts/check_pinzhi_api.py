#!/usr/bin/env python3
"""
品智餐饮系统 API 对接检测脚本

一次性检测所有接口是否成功，并输出结论：是否可同步数据和报表。

用法:
  # 使用环境变量
  export PINZHI_BASE_URL="http://ip:port/pzcatering-gateway"
  export PINZHI_TOKEN="your_merchant_token"
  python scripts/check_pinzhi_api.py

  # 指定营业日与门店（可选）
  python scripts/check_pinzhi_api.py --date 2026-02-28 --ognid 12345

  # 从项目根目录或 api-adapters/pinzhi 目录运行
  cd zhilian-os && python scripts/check_pinzhi_api.py
  cd zhilian-os/packages/api-adapters/pinzhi && python ../../../scripts/check_pinzhi_api.py
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta


def _setup_path():
    """确保能 import 到 PinzhiAdapter"""
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    pinzhi_pkg = os.path.join(repo_root, "packages", "api-adapters", "pinzhi")
    if os.path.isdir(pinzhi_pkg) and pinzhi_pkg not in sys.path:
        sys.path.insert(0, pinzhi_pkg)
    # 若在 pinzhi 包内运行
    if os.path.basename(os.path.dirname(__file__)) == "scripts" and "src" not in sys.path:
        parent = os.path.dirname(os.path.dirname(__file__))
        pinzhi_inner = os.path.join(parent, "packages", "api-adapters", "pinzhi")
        if os.path.isdir(pinzhi_inner):
            sys.path.insert(0, pinzhi_inner)


async def main():
    parser = argparse.ArgumentParser(description="品智API对接检测")
    parser.add_argument("--date", default=None, help="营业日 yyyy-MM-dd，默认昨天")
    parser.add_argument("--ognid", default=None, help="门店 omsID，可选")
    parser.add_argument("--config", default=None, help="配置文件 YAML 路径（未实现则用环境变量）")
    args = parser.parse_args()

    base_url = os.getenv("PINZHI_BASE_URL")
    token = os.getenv("PINZHI_TOKEN")
    if args.config:
        try:
            import yaml
            with open(args.config, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            pinzhi_cfg = cfg.get("pinzhi", cfg)
            base_url = base_url or pinzhi_cfg.get("base_url")
            token = token or pinzhi_cfg.get("token")
        except Exception as e:
            print(f"读取配置失败: {e}", file=sys.stderr)
    if not base_url or not token:
        print("请设置环境变量 PINZHI_BASE_URL 和 PINZHI_TOKEN，或通过 --config 指定 YAML。", file=sys.stderr)
        sys.exit(1)

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

    print("=" * 70)
    print("品智餐饮系统 API 对接检测")
    print("=" * 70)
    print(f"基础地址: {config['base_url']}")
    print(f"营业日:   {business_date}")
    print(f"门店ognid: {args.ognid or '(未指定)'}")
    print()

    adapter = PinzhiAdapter(config)
    try:
        results = await adapter.run_all_checks(
            business_date=business_date,
            ognid=args.ognid,
        )
    finally:
        await adapter.close()

    # 表头
    print(f"{'接口名称':<28} {'接口':<32} {'结果':<6} {'说明'}")
    print("-" * 70)
    required_ok = True
    required_names = set()
    for r in results:
        name = r["name"]
        endpoint = r["endpoint"]
        ok = r["ok"]
        msg = (r["message"] or "")[:36]
        required = r.get("required", False)
        if required:
            required_names.add(name)
            if not ok:
                required_ok = False
        status = "成功" if ok else "失败"
        req_tag = " [核心]" if required else ""
        print(f"{name:<28} {endpoint:<32} {status:<6} {msg}{req_tag}")
    print("-" * 70)

    # 核心必过：门店信息、门店每日经营数据、订单列表V2、菜品类别、支付方式；有门店时含按门店收入
    core_required = {"门店信息", "门店每日经营数据(报表)", "订单列表V2", "菜品类别", "支付方式"}
    if args.ognid:
        core_required.add("按门店收入数据")
    all_core_ok = all(
        next((x for x in results if x["name"] == n), {}).get("ok", False)
        for n in core_required
    )
    daily_ok = next(
        (x.get("ok") for x in results if x["name"] == "门店每日经营数据(报表)"),
        False,
    )

    if all_core_ok and daily_ok:
        print()
        print("【结论】品智餐饮系统接口全部已正常对接，能同步数据和报表。")
        print("        可继续使用报表与按日/周/月/季生成经营分析。")
    else:
        print()
        print("【结论】部分核心接口未通过，暂不能完整同步报表数据。")
        failed_core = [n for n in core_required if not next((x.get("ok") for x in results if x["name"] == n), False)]
        if failed_core:
            print(f"        未通过核心项: {', '.join(failed_core)}")
        print("        请检查 token（商户管理下申请）、base_url 与网络，或联系品智技术支持。")

    print()
    sys.exit(0 if all_core_ok and daily_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
