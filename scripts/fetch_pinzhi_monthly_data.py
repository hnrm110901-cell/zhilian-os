#!/usr/bin/env python3
"""
从品智 API 拉取指定月份的尝在一起真实经营数据（实收金额、订单笔数等）

用于经营分析报告时只使用 API 拉取的真实数据，不使用推算值。
需在已配置尝在一起/品智 API 的环境运行（PINZHI_BASE_URL、PINZHI_TOKEN）。

用法:
  export PINZHI_BASE_URL="http://ip:port/pzcatering-gateway"
  export PINZHI_TOKEN="your_merchant_token"

  # 拉取 2025 年 12 月
  python3 scripts/fetch_pinzhi_monthly_data.py --month 2025-12

  # 拉取 2026 年 1 月
  python3 scripts/fetch_pinzhi_monthly_data.py --month 2026-01

  # 指定门店（可选，不指定则全部门店）
  python3 scripts/fetch_pinzhi_monthly_data.py --month 2025-12 --ognid xxx

输出：月度总营业实收（元）、订单笔数、客单价（元）、及按日明细（可选）。
"""
import argparse
import asyncio
import calendar
import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


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


def _parse_month(month_str: str) -> Tuple[str, str]:
    """'2025-12' -> ('2025-12-01', '2025-12-31')"""
    try:
        year, month = map(int, month_str.split("-"))
        _, last_day = calendar.monthrange(year, month)
        start = f"{year:04d}-{month:02d}-01"
        end = f"{year:04d}-{month:02d}-{last_day:02d}"
        return start, end
    except Exception:
        raise ValueError(f"无效月份格式，应为 yyyy-mm: {month_str}")


def _dates_in_month(month_str: str) -> List[str]:
    from datetime import timedelta
    start, end = _parse_month(month_str)
    out = []
    d = datetime.strptime(start, "%Y-%m-%d")
    end_d = datetime.strptime(end, "%Y-%m-%d")
    while d <= end_d:
        out.append(d.strftime("%Y-%m-%d"))
        d = d + timedelta(days=1)
    return out


def _extract_daily_revenue_from_sum(data: Dict[str, Any]) -> Optional[float]:
    """
    从 queryOgnDailyBizData 返回的 sum 中提取当日总营收（元）。
    品智金额可能为分（整数），此处统一按 分 处理再转为元；若数值明显为元则直接使用。
    """
    sum_obj = data.get("sum") if isinstance(data, dict) else None
    if not sum_obj or not isinstance(sum_obj, dict):
        return None

    # 优先明确的总计字段（常见命名）
    for key in ("totalAmount", "realAmount", "consumeAmount", "totalConsumeAmount", "amount", "revenue"):
        v = sum_obj.get(key)
        if v is not None:
            try:
                x = float(v)
                if x < 0:
                    continue
                # 若数值像「分」（单日几千到几十万），按分转元
                if x >= 100:
                    return x / 100.0
                return x
            except (TypeError, ValueError):
                pass

    # 餐段 0 类型 0 = 全天全部
    v = sum_obj.get("consumeAmount_0_0")
    if v is not None:
        try:
            x = float(v)
            if x >= 0:
                return x / 100.0 if x >= 100 else x
        except (TypeError, ValueError):
            pass

    # 汇总所有 sum 中像金额的数值（若为分则加总后/100）
    total_cents = 0
    for k, v in sum_obj.items():
        if k == "dishList" or not isinstance(v, (int, float)):
            continue
        try:
            x = float(v)
            if x >= 0:
                total_cents += x
        except (TypeError, ValueError):
            pass
    if total_cents > 0:
        return total_cents / 100.0 if total_cents >= 100 else total_cents
    return None


def _extract_daily_revenue_from_store_list(stores: List[Dict]) -> Optional[float]:
    """从 queryStoreSummaryList 返回的门店列表中汇总当日营收（元）。"""
    if not stores or not isinstance(stores, list):
        return None
    total = 0
    for s in stores:
        if not isinstance(s, dict):
            continue
        for key in ("consumeAmount", "amount", "revenue", "totalAmount", "realAmount", "sales"):
            v = s.get(key)
            if v is not None:
                try:
                    x = float(v)
                    if x >= 0:
                        total += x / 100.0 if x >= 100 else x
                        break
                except (TypeError, ValueError):
                    pass
    return total if total > 0 else None


async def fetch_monthly_revenue_from_daily(
    adapter: Any,
    month_str: str,
    use_store_list: bool = False,
    ognid: Optional[str] = None,
) -> Tuple[float, List[Tuple[str, float]]]:
    """
    按日拉取 queryOgnDailyBizData（或 queryStoreSummaryList）汇总月度实收。
    返回 (月度总实收元, [(日期, 当日实收元), ...])
    """
    dates = _dates_in_month(month_str)
    daily_list: List[Tuple[str, float]] = []
    total = 0.0

    for d in dates:
        if use_store_list:
            stores = await adapter.query_store_summary_list(d)
            rev = _extract_daily_revenue_from_store_list(stores)
        else:
            data = await adapter.query_ogn_daily_biz_data(business_date=d, ognid=ognid)
            rev = _extract_daily_revenue_from_sum(data)
        if rev is not None:
            total += rev
            daily_list.append((d, rev))
        await asyncio.sleep(0.1)

    return round(total, 2), daily_list


async def fetch_monthly_orders(
    adapter: Any,
    start: str,
    end: str,
    ognid: Optional[str] = None,
    page_size: int = 100,
) -> Tuple[int, float, List[Dict]]:
    """
    全部分页拉取 queryOrderListV2，统计已结账订单笔数及实收汇总（元）。
    品智 realPrice 为分，转为元。
    返回 (笔数, 实收合计元, 订单列表用于核对)
    """
    all_orders: List[Dict] = []
    page = 1
    while True:
        batch = await adapter.query_orders(
            ognid=ognid,
            begin_date=start,
            end_date=end,
            page_index=page,
            page_size=page_size,
        )
        if not batch:
            break
        all_orders.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
        await asyncio.sleep(0.1)

    # 只计已结账 billStatus=1
    settled = [o for o in all_orders if o.get("billStatus") == 1]
    total_cents = sum(int(o.get("realPrice") or 0) for o in settled)
    total_yuan = round(total_cents / 100.0, 2)
    return len(settled), total_yuan, settled


async def main():
    parser = argparse.ArgumentParser(description="从品智 API 拉取指定月份真实经营数据")
    parser.add_argument("--month", required=True, help="月份 yyyy-mm，如 2025-12、2026-01")
    parser.add_argument("--ognid", default=None, help="门店 omsID，不传则全部门店")
    parser.add_argument("--config", default=None, help="YAML 配置文件路径（可选）")
    parser.add_argument("--daily", action="store_true", help="打印按日明细")
    parser.add_argument("--use-store-list", action="store_true", help="用 queryStoreSummaryList 按日汇总营收（否则用 queryOgnDailyBizData）")
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
            sys.exit(1)
    if not base_url or not token:
        print("请设置 PINZHI_BASE_URL 和 PINZHI_TOKEN，或使用 --config 指定 YAML。", file=sys.stderr)
        sys.exit(1)

    _setup_path()
    from src.adapter import PinzhiAdapter

    config = {
        "base_url": base_url.rstrip("/"),
        "token": token,
        "timeout": int(os.getenv("PINZHI_TIMEOUT", "30")),
        "retry_times": 2,
    }
    adapter = PinzhiAdapter(config)
    start, end = _parse_month(args.month)

    try:
        print("=" * 60)
        print(f"尝在一起 · 品智 API 拉取 · {args.month}")
        print("=" * 60)
        print(f"日期范围: {start} ~ {end}")
        print(f"门店: {args.ognid or '全部门店'}")
        print()

        # 1) 月度营收（按日汇总）
        print("[1/2] 拉取月度营收（按日 queryOgnDailyBizData/queryStoreSummaryList）…")
        revenue_from_daily, daily_list = await fetch_monthly_revenue_from_daily(
            adapter, args.month, use_store_list=args.use_store_list, ognid=args.ognid
        )
        print(f"      总营业实收(元): {revenue_from_daily:,.2f}")
        print(f"      总营业实收(万元): {revenue_from_daily / 10000:,.2f}")
        if args.daily and daily_list:
            print("      按日明细:")
            for d, r in daily_list:
                print(f"        {d}: {r:,.2f} 元")
        print()

        # 2) 订单笔数 + 订单实收汇总
        print("[2/2] 拉取订单（queryOrderListV2 全部分页）…")
        order_count, revenue_from_orders, _ = await fetch_monthly_orders(
            adapter, start, end, ognid=args.ognid
        )
        print(f"      订单笔数(已结账): {order_count}")
        print(f"      订单加总实收(元): {revenue_from_orders:,.2f}")
        if order_count > 0:
            aov = revenue_from_orders / order_count
            print(f"      客单价(元): {aov:.2f}")
        print()

        # 对比
        print("--- 汇总（用于经营报告，请以品智报表口径为准核对）---")
        print(f"月份: {args.month}")
        print(f"总营业实收(元): {revenue_from_daily:,.2f}  （来源: 按日经营数据接口）")
        print(f"总营业实收(万元): {revenue_from_daily / 10000:,.2f}")
        print(f"订单笔数: {order_count}")
        print(f"客单价(元): {revenue_from_orders / order_count:.2f}" if order_count else "客单价: —")
        if abs(revenue_from_daily - revenue_from_orders) > 1.0:
            print(f"说明: 按日汇总实收与订单加总实收存在差异（{revenue_from_daily:,.2f} vs {revenue_from_orders:,.2f}），请以品智后台报表导出值为准，并参考《尝在一起-API与报表差异分析与经营报告生成明细》核对口径。")
        print()
        print("以上为从尝在一起品智 API 拉取的真实数据，可直接填入经营分析报告，勿用推算值。")

    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
