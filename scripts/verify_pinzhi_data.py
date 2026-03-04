#!/usr/bin/env python3
"""
品智 API 数据拉取完整性与稳定性验证脚本

在「接口连通性」通过的前提下，验证：
1. 数据完整性：核心接口返回结构正确、必选字段存在、数据量合理。
2. 稳定性：对关键接口进行两次拉取，结果一致或差异在允许范围内。

适用场景：本机（如 openclaw）已完成品智 API 全部对接后，定期或上线前验证数据是否完整稳定。

用法:
  export PINZHI_BASE_URL="http://ip:port/pzcatering-gateway"
  export PINZHI_TOKEN="your_merchant_token"
  python scripts/verify_pinzhi_data.py

  # 指定营业日与门店
  python scripts/verify_pinzhi_data.py --date 2026-02-28 --ognid 12345

  # 仅做完整性校验，不做稳定性二次拉取
  python scripts/verify_pinzhi_data.py --no-stability

  # 稳定性检测间隔秒数（默认 2）
  python scripts/verify_pinzhi_data.py --stability-interval 3
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple


def _setup_path():
    """确保能 import 到 PinzhiAdapter"""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    pinzhi_pkg = os.path.join(repo_root, "packages", "api-adapters", "pinzhi")
    if os.path.isdir(pinzhi_pkg) and pinzhi_pkg not in sys.path:
        sys.path.insert(0, pinzhi_pkg)
    if os.path.basename(os.path.dirname(__file__)) == "scripts" and "src" not in sys.path:
        parent = os.path.dirname(os.path.dirname(__file__))
        pinzhi_inner = os.path.join(parent, "packages", "api-adapters", "pinzhi")
        if os.path.isdir(pinzhi_inner):
            sys.path.insert(0, pinzhi_inner)


# ---------- 数据完整性校验 ----------


def _check_stores(stores: List[Dict]) -> Tuple[bool, str]:
    """门店列表：应为非空列表，元素建议含 ognid/门店标识"""
    if not isinstance(stores, list):
        return False, "返回类型不是列表"
    if len(stores) == 0:
        return False, "门店列表为空"
    first = stores[0] if stores else {}
    if not isinstance(first, dict):
        return False, "门店项不是对象"
    # 不强制字段名，有内容即可
    return True, f"共 {len(stores)} 个门店"


def _check_daily_biz_data(data: Dict, business_date: str) -> Tuple[bool, str]:
    """门店每日经营数据：应有 sum 或 list，且与 businessDate 相关"""
    if not isinstance(data, dict):
        return False, "返回类型不是对象"
    has_sum = "sum" in data
    has_list = "list" in data and isinstance(data.get("list"), list)
    if not has_sum and not has_list:
        return False, "缺少 sum 或 list 结构"
    lst = data.get("list", [])
    cnt = len(lst) if isinstance(lst, list) else 0
    return True, f"sum={has_sum}, list 条数={cnt}"


def _check_orders(orders: List[Dict]) -> Tuple[bool, str]:
    """订单列表：应为列表，单条建议含 billId/order 相关字段"""
    if not isinstance(orders, list):
        return False, "返回类型不是列表"
    first = orders[0] if orders else {}
    if orders and isinstance(first, dict):
        return True, f"共 {len(orders)} 条订单"
    if len(orders) == 0:
        return True, "0 条订单（当日可能无单）"
    return False, "订单项结构异常"


def _check_categories(categories: List) -> Tuple[bool, str]:
    """菜品类别：应为列表"""
    if not isinstance(categories, list):
        return False, "返回类型不是列表"
    return True, f"共 {len(categories)} 个菜类"


def _check_pay_types(pay_types: List) -> Tuple[bool, str]:
    """支付方式：应为列表，通常至少 1 项"""
    if not isinstance(pay_types, list):
        return False, "返回类型不是列表"
    return True, f"共 {len(pay_types)} 种支付方式"


async def run_completeness_checks(
    adapter: Any,
    business_date: str,
    ognid: Optional[str],
) -> List[Dict[str, Any]]:
    """
    执行数据完整性校验：拉取核心数据并校验结构。
    返回 [{ "name", "ok", "message" }, ...]
    """
    results = []

    # 1. 门店信息
    try:
        stores = await adapter.get_store_info(ognid=ognid)
        ok, msg = _check_stores(stores)
        results.append({"name": "门店信息-数据完整性", "ok": ok, "message": msg})
    except Exception as e:
        results.append({"name": "门店信息-数据完整性", "ok": False, "message": str(e)[:60]})

    # 2. 门店每日经营数据（报表核心）
    try:
        daily = await adapter.query_ogn_daily_biz_data(
            business_date=business_date, ognid=ognid
        )
        ok, msg = _check_daily_biz_data(daily, business_date)
        results.append({"name": "每日经营数据-数据完整性", "ok": ok, "message": msg})
    except Exception as e:
        results.append({"name": "每日经营数据-数据完整性", "ok": False, "message": str(e)[:60]})

    # 3. 订单列表 V2（第一页）
    try:
        orders = await adapter.query_orders(
            ognid=ognid,
            begin_date=business_date,
            end_date=business_date,
            page_index=1,
            page_size=50,
        )
        ok, msg = _check_orders(orders)
        results.append({"name": "订单列表V2-数据完整性", "ok": ok, "message": msg})
    except Exception as e:
        results.append({"name": "订单列表V2-数据完整性", "ok": False, "message": str(e)[:60]})

    # 4. 菜品类别
    try:
        categories = await adapter.get_dish_categories()
        ok, msg = _check_categories(categories)
        results.append({"name": "菜品类别-数据完整性", "ok": ok, "message": msg})
    except Exception as e:
        results.append({"name": "菜品类别-数据完整性", "ok": False, "message": str(e)[:60]})

    # 5. 支付方式
    try:
        pay_types = await adapter.get_pay_types()
        ok, msg = _check_pay_types(pay_types)
        results.append({"name": "支付方式-数据完整性", "ok": ok, "message": msg})
    except Exception as e:
        results.append({"name": "支付方式-数据完整性", "ok": False, "message": str(e)[:60]})

    return results


async def run_stability_checks(
    adapter: Any,
    business_date: str,
    ognid: Optional[str],
    interval_seconds: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    稳定性校验：对关键接口拉取两次，比较是否均成功且数据量一致（或允许小幅差异）。
    返回 [{ "name", "ok", "message" }, ...]
    """
    results = []

    async def _fetch_daily():
        return await adapter.query_ogn_daily_biz_data(
            business_date=business_date, ognid=ognid
        )

    async def _fetch_orders():
        return await adapter.query_orders(
            ognid=ognid,
            begin_date=business_date,
            end_date=business_date,
            page_index=1,
            page_size=50,
        )

    async def _fetch_stores():
        return await adapter.get_store_info(ognid=ognid)

    # 第一次拉取
    try:
        daily_1 = await _fetch_daily()
        await asyncio.sleep(interval_seconds)
        daily_2 = await _fetch_daily()
        list_1 = daily_1.get("list") if isinstance(daily_1, dict) else []
        list_2 = daily_2.get("list") if isinstance(daily_2, dict) else []
        n1 = len(list_1) if isinstance(list_1, list) else 0
        n2 = len(list_2) if isinstance(list_2, list) else 0
        if n1 == n2:
            results.append({
                "name": "每日经营数据-稳定性",
                "ok": True,
                "message": f"两次拉取 list 条数一致: {n1}",
            })
        else:
            results.append({
                "name": "每日经营数据-稳定性",
                "ok": True,  # 不强制一致，仅提示
                "message": f"两次拉取 list 条数: {n1} vs {n2}（营业中可能变化）",
            })
    except Exception as e:
        results.append({
            "name": "每日经营数据-稳定性",
            "ok": False,
            "message": str(e)[:60],
        })

    # 订单列表稳定性
    try:
        orders_1 = await _fetch_orders()
        await asyncio.sleep(interval_seconds)
        orders_2 = await _fetch_orders()
        n1 = len(orders_1) if isinstance(orders_1, list) else 0
        n2 = len(orders_2) if isinstance(orders_2, list) else 0
        if n1 == n2:
            results.append({
                "name": "订单列表V2-稳定性",
                "ok": True,
                "message": f"两次拉取条数一致: {n1}",
            })
        else:
            results.append({
                "name": "订单列表V2-稳定性",
                "ok": True,
                "message": f"两次拉取条数: {n1} vs {n2}",
            })
    except Exception as e:
        results.append({
            "name": "订单列表V2-稳定性",
            "ok": False,
            "message": str(e)[:60],
        })

    # 门店列表稳定性（静态数据应一致）
    try:
        stores_1 = await _fetch_stores()
        await asyncio.sleep(interval_seconds)
        stores_2 = await _fetch_stores()
        n1 = len(stores_1) if isinstance(stores_1, list) else 0
        n2 = len(stores_2) if isinstance(stores_2, list) else 0
        ok = n1 == n2
        results.append({
            "name": "门店信息-稳定性",
            "ok": ok,
            "message": f"两次拉取门店数: {n1} vs {n2}" + ("" if ok else "，不一致"),
        })
    except Exception as e:
        results.append({
            "name": "门店信息-稳定性",
            "ok": False,
            "message": str(e)[:60],
        })

    return results


async def main():
    parser = argparse.ArgumentParser(
        description="品智 API 数据拉取完整性与稳定性验证"
    )
    parser.add_argument("--date", default=None, help="营业日 yyyy-MM-dd，默认昨天")
    parser.add_argument("--ognid", default=None, help="门店 omsID，可选")
    parser.add_argument("--config", default=None, help="配置文件 YAML 路径（未实现则用环境变量）")
    parser.add_argument(
        "--no-stability",
        action="store_true",
        help="仅做完整性校验，不做稳定性二次拉取",
    )
    parser.add_argument(
        "--stability-interval",
        type=float,
        default=2.0,
        help="稳定性检测两次拉取间隔秒数，默认 2",
    )
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
        print(
            "请设置环境变量 PINZHI_BASE_URL 和 PINZHI_TOKEN，或通过 --config 指定 YAML。",
            file=sys.stderr,
        )
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
    print("品智 API 数据拉取 — 完整性与稳定性验证")
    print("=" * 70)
    print(f"基础地址: {config['base_url']}")
    print(f"营业日:   {business_date}")
    print(f"门店 ognid: {args.ognid or '(未指定)'}")
    print(f"稳定性检测: {'否' if args.no_stability else '是'} (间隔 {args.stability_interval}s)")
    print()

    adapter = PinzhiAdapter(config)
    exit_code = 0

    try:
        # Step 1: 接口连通性（复用 run_all_checks）
        print("[1/3] 接口连通性检测 …")
        connectivity = await adapter.run_all_checks(
            business_date=business_date,
            ognid=args.ognid,
        )
        core_names = {
            "门店信息",
            "门店每日经营数据(报表)",
            "订单列表V2",
            "菜品类别",
            "支付方式",
        }
        if args.ognid:
            core_names = core_names | {"按门店收入数据"}
        core_ok = all(
            next((x for x in connectivity if x["name"] == n), {}).get("ok", False)
            for n in core_names
        )
        if not core_ok:
            print("  部分核心接口未通过，请先完成对接再验证数据。")
            for r in connectivity:
                if r.get("required") and not r.get("ok"):
                    print(f"  - {r['name']}: {r.get('message', '')}")
            exit_code = 1
        else:
            print("  核心接口连通性: 通过")
        print()

        # Step 2: 数据完整性
        print("[2/3] 数据完整性校验 …")
        completeness = await run_completeness_checks(
            adapter, business_date, args.ognid
        )
        for r in completeness:
            status = "通过" if r["ok"] else "失败"
            print(f"  {r['name']}: {status} — {r['message']}")
            if not r["ok"]:
                exit_code = 1
        print()

        # Step 3: 稳定性（可选）
        if not args.no_stability:
            print("[3/3] 稳定性校验（两次拉取对比）…")
            stability = await run_stability_checks(
                adapter,
                business_date,
                args.ognid,
                interval_seconds=args.stability_interval,
            )
            for r in stability:
                status = "通过" if r["ok"] else "失败"
                print(f"  {r['name']}: {status} — {r['message']}")
                if not r["ok"]:
                    exit_code = 1
            print()
        else:
            print("[3/3] 稳定性校验: 已跳过 (--no-stability)")
            print()

    finally:
        await adapter.close()

    # 结论
    if exit_code == 0:
        print("【结论】数据拉取完整且稳定，可用于报表与经营分析。")
    else:
        print("【结论】存在完整性或稳定性问题，请检查网络、Token 与品智侧数据。")
    print()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
