#!/usr/bin/env python3
"""
三品牌真实经营数据拉取（品智订单 + 微生活会员 + 喰星云供应链）
拉取 2026-03-01 ~ 2026-03-20 全部门店真实数据，输出 JSON

在生产服务器运行：
  cd /opt/zhilian-os
  python3 scripts/fetch_real_data_all_brands.py

输出文件：scripts/real_data_output.json
"""
import asyncio
import hashlib
import time
import json
import os
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

# ══════════════════════════════════════════════════════════════
#  日期范围
# ══════════════════════════════════════════════════════════════
START_DATE = "2026-03-01"
END_DATE = "2026-03-20"

# ══════════════════════════════════════════════════════════════
#  品智签名 + 请求
# ══════════════════════════════════════════════════════════════

def pinzhi_sign(token: str, params: dict, upper: bool = False) -> str:
    filtered = {k: v for k, v in params.items()
                if k not in ("sign", "pageIndex", "pageSize") and v is not None}
    ordered = OrderedDict(sorted(filtered.items()))
    param_str = "&".join(f"{k}={v}" for k, v in ordered.items())
    param_str += f"&token={token}"
    h = hashlib.md5(param_str.encode()).hexdigest()
    return h.upper() if upper else h


async def pinzhi_request(client, base_url, token, method, endpoint, params=None):
    params = dict(params or {})
    url = f"{base_url}{endpoint}"
    for upper in [False, True]:
        p = dict(params)
        p["sign"] = pinzhi_sign(token, p, upper=upper)
        try:
            if method == "GET":
                resp = await client.get(url, params=p, timeout=20)
            else:
                resp = await client.post(url, data=p, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            success = data.get("success")
            if success is not None and success != 0:
                msg = data.get("msg", "")
                if "sign error" in msg and not upper:
                    continue
                raise Exception(f"品智错误: {msg}")
            errcode = data.get("errcode")
            if errcode is not None and errcode != 0:
                msg = data.get("errmsg", "")
                if "sign error" in msg and not upper:
                    continue
                raise Exception(f"品智错误: {msg}")
            return data
        except Exception as e:
            if "sign error" in str(e) and not upper:
                continue
            raise
    raise Exception("sign error (大小写均失败)")


# ══════════════════════════════════════════════════════════════
#  微生活CRM签名
# ══════════════════════════════════════════════════════════════

def _ksort_recursive(obj):
    if isinstance(obj, bool):
        return 1 if obj else 0
    if isinstance(obj, dict):
        return {k: _ksort_recursive(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_ksort_recursive(item) for item in obj]
    return obj

def _http_build_query(params, prefix=""):
    parts = []
    if isinstance(params, dict):
        items = params.items()
    elif isinstance(params, list):
        items = enumerate(params)
    else:
        if params is not None and params != "":
            parts.append(f"{quote_plus(prefix)}={quote_plus(str(params))}")
        return "&".join(parts)
    for key, value in items:
        full_key = f"{prefix}[{key}]" if prefix else str(key)
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            sub = _http_build_query(value, full_key)
            if sub:
                parts.append(sub)
        else:
            parts.append(f"{quote_plus(full_key)}={quote_plus(str(value))}")
    return "&".join(parts)

def crm_sign(biz_params, appid, appkey, ts):
    sorted_params = _ksort_recursive(biz_params)
    query = _http_build_query(sorted_params)
    query += f"&appid={appid}&appkey={appkey}&v=2.0&ts={ts}"
    return hashlib.md5(query.encode()).hexdigest().lower()

async def crm_request(client, base_url, appid, appkey, endpoint, biz_params=None):
    ts = int(time.time())
    biz = biz_params or {}
    sig = crm_sign(biz, appid, appkey, ts)
    body = {"appid": appid, "v": "2.0", "ts": str(ts), "sig": sig, "fmt": "JSON"}
    if biz:
        body["req"] = json.dumps(biz, ensure_ascii=False)
    resp = await client.post(f"{base_url}{endpoint}", data=body, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    errcode = result.get("errcode", -1)
    if errcode != 0:
        errmsg = result.get("errmsg", "未知")
        raise Exception(f"CRM错误 [{errcode}]: {errmsg}")
    return result.get("res", result)


# ══════════════════════════════════════════════════════════════
#  喰星云供应链签名
# ══════════════════════════════════════════════════════════════

def chixingyun_sign(params: dict, app_secret: str) -> str:
    sorted_items = sorted(params.items())
    param_str = "&".join(f"{k}={v}" for k, v in sorted_items if v is not None and v != "")
    param_str += app_secret
    return hashlib.md5(param_str.encode()).hexdigest()

async def chixingyun_request(client, base_url, app_key, app_secret, endpoint, params=None):
    p = dict(params or {})
    p["appKey"] = app_key
    p["timestamp"] = str(int(time.time() * 1000))
    p["sign"] = chixingyun_sign(p, app_secret)
    url = f"{base_url}{endpoint}"
    resp = await client.post(url, data=p, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ══════════════════════════════════════════════════════════════
#  品牌配置（来自 seed_real_merchants.py）
# ══════════════════════════════════════════════════════════════

BRANDS = {
    "尝在一起": {
        "brand_id": "BRD_CZYZ0001",
        "pinzhi": {
            "base_url": "https://czyq.pinzhikeji.net/pzcatering-gateway",
            "token": "3bbc9bed2b42c1e1b3cca26389fbb81c",
        },
        "stores": [
            {"name": "文化城店", "ognid": "2461", "token": "752b4b16a863ce47def11cf33b1b521f"},
            {"name": "浏小鲜", "ognid": "7269", "token": "f5cc1a27db6e215ae7bb5512b6b57981"},
            {"name": "永安店", "ognid": "19189", "token": "56cd51b69211297104a0608f6a696b80"},
        ],
        "crm": {
            "base_url": "https://api.acewill.net",
            "appid": "dp25MLoc2gnXE7A223ZiVv",
            "appkey": "3d2eaa5f9b9a6a6746a18d28e770b501",
            "merchant_id": "1275413383",
        },
        "chixingyun": {
            "base_url": "http://czyqss.scmacewill.cn",
            "app_key": "changzaiyiqi",
            "app_secret": "WmRpv8OlR1UR",
        },
    },
    "最黔线": {
        "brand_id": "BRD_ZQX0001",
        "pinzhi": {
            "base_url": "https://ljcg.pinzhikeji.net/pzcatering-gateway",
            "token": "47a428538d350fac1640a51b6bbda68c",
        },
        "stores": [
            {"name": "马家湾店", "ognid": "20529", "token": "29cdb6acac3615070bb853afcbb32f60"},
            {"name": "东欣万象店", "ognid": "32109", "token": "ed2c948284d09cf9e096e9d965936aa3"},
            {"name": "合众路店", "ognid": "32304", "token": "43f0b54db12b0618ea612b2a0a4d2675"},
            {"name": "广州路店", "ognid": "32305", "token": "a8a4e4daf86875d4a4e0254b6eb7191e"},
            {"name": "昆明路店", "ognid": "32306", "token": "d656668d285a100c851bbe149d4364f3"},
            {"name": "仁怀店", "ognid": "32309", "token": "36bf0644e5703adc8a4d1ddd7b8f0e95"},
        ],
        "crm": {
            "base_url": "https://api.acewill.net",
            "appid": "dp2C8kqBMmGrHUVpBjqAw8q3",
            "appkey": "56573c798c8ab0dc565e704190207f12",
            "merchant_id": "1827518239",
        },
    },
    "尚宫厨": {
        "brand_id": "BRD_SGC0001",
        "pinzhi": {
            "base_url": "https://xcsgc.pinzhikeji.net/pzcatering-gateway",
            "token": "8275cf74d1943d7a32531d2d4f889870",
        },
        "stores": [
            {"name": "采霞街店", "ognid": "2463", "token": "852f1d34c75af0b8eb740ef47f133130"},
            {"name": "湘江水岸店", "ognid": "7896", "token": "27a36f2feea6d3a914438f6cb32108c3"},
            {"name": "乐城店", "ognid": "24777", "token": "5cbfb449112f698218e0b1be1a3bc7c6"},
            {"name": "啫匠亲城店", "ognid": "36199", "token": "08f3791e15f48338405728a3a92fcd7f"},
            {"name": "酃湖雅院店", "ognid": "41405", "token": "bb7e89dcd0ac339b51631eca99e51c9b"},
        ],
        "crm": {
            "base_url": "https://api.acewill.net",
            "appid": "dp0X0jl45wauwdGgkRETITz",
            "appkey": "649738234c7426bfa0dbfa431c92a750",
            "merchant_id": "1549254243",
        },
    },
}


# ══════════════════════════════════════════════════════════════
#  数据拉取函数
# ══════════════════════════════════════════════════════════════

def dates_in_range(start, end):
    out = []
    d = datetime.strptime(start, "%Y-%m-%d")
    end_d = datetime.strptime(end, "%Y-%m-%d")
    while d <= end_d:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


async def fetch_pinzhi_daily_biz(client, base_url, token, ognid, date):
    """拉取单日单店经营汇总"""
    try:
        data = await pinzhi_request(client, base_url, token, "GET",
            "/pinzhi/queryOgnDailyBizData.do",
            {"businessDate": date, "ognid": ognid})
        return data
    except Exception as e:
        return {"error": str(e)}


async def fetch_pinzhi_order_summary(client, base_url, token, ognid, date):
    """拉取单日单店订单汇总"""
    try:
        data = await pinzhi_request(client, base_url, token, "GET",
            "/pinzhi/queryOrderSummary.do",
            {"ognid": ognid, "businessDate": date})
        return data
    except Exception as e:
        return {"error": str(e)}


async def fetch_pinzhi_orders_page(client, base_url, token, ognid, date, page=1, page_size=100):
    """拉取单日单店订单明细（分页）"""
    try:
        data = await pinzhi_request(client, base_url, token, "POST",
            "/pinzhi/orderNew.do",
            {"ognid": ognid, "businessDate": date, "pageIndex": page, "pageSize": page_size})
        return data
    except Exception as e:
        return {"error": str(e)}


async def fetch_pinzhi_all_orders(client, base_url, token, ognid, date):
    """拉取单日单店全部订单（自动翻页）"""
    all_orders = []
    page = 1
    while True:
        data = await fetch_pinzhi_orders_page(client, base_url, token, ognid, date, page, 100)
        if "error" in data:
            return all_orders, data["error"]
        orders = data.get("data", data.get("res", []))
        if isinstance(orders, dict):
            orders = orders.get("list", orders.get("data", []))
        if not isinstance(orders, list):
            break
        all_orders.extend(orders)
        if len(orders) < 100:
            break
        page += 1
        await asyncio.sleep(0.05)
    return all_orders, None


async def fetch_crm_member_stats(client, crm_config):
    """拉取微生活会员统计"""
    results = {}
    try:
        # 会员列表（第1页，看总数）
        data = await crm_request(client, crm_config["base_url"],
            crm_config["appid"], crm_config["appkey"],
            "/user/list", {"page": 1, "size": 1})
        results["member_list"] = data
    except Exception as e:
        results["member_list_error"] = str(e)

    try:
        # 门店列表
        data = await crm_request(client, crm_config["base_url"],
            crm_config["appid"], crm_config["appkey"],
            "/shop/list", {})
        results["shop_list"] = data
    except Exception as e:
        results["shop_list_error"] = str(e)

    try:
        # 交易统计（如果有）
        data = await crm_request(client, crm_config["base_url"],
            crm_config["appid"], crm_config["appkey"],
            "/deal/statistic", {"begin_date": START_DATE, "end_date": END_DATE})
        results["deal_stats"] = data
    except Exception as e:
        results["deal_stats_error"] = str(e)

    return results


async def fetch_chixingyun_data(client, scm_config):
    """拉取喰星云供应链数据"""
    results = {}
    base = scm_config["base_url"]
    key = scm_config["app_key"]
    secret = scm_config["app_secret"]

    # 尝试常见供应链接口
    endpoints = [
        ("/api/purchase/list", "采购单列表", {"startDate": START_DATE, "endDate": END_DATE, "page": "1", "pageSize": "50"}),
        ("/api/stock/list", "库存列表", {"page": "1", "pageSize": "50"}),
        ("/api/supplier/list", "供应商列表", {"page": "1", "pageSize": "50"}),
        ("/api/goods/list", "商品列表", {"page": "1", "pageSize": "50"}),
    ]

    for endpoint, name, params in endpoints:
        try:
            data = await chixingyun_request(client, base, key, secret, endpoint, params)
            results[name] = data
        except Exception as e:
            results[f"{name}_error"] = str(e)

    return results


# ══════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════

async def main():
    print(f"\n{'█'*60}")
    print(f"  三品牌真实经营数据拉取")
    print(f"  日期范围: {START_DATE} ~ {END_DATE}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'█'*60}\n")

    all_data = {
        "fetch_time": datetime.now().isoformat(),
        "date_range": {"start": START_DATE, "end": END_DATE},
        "brands": {},
    }

    dates = dates_in_range(START_DATE, END_DATE)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for brand_name, bc in BRANDS.items():
            print(f"\n{'='*60}")
            print(f"  {brand_name}")
            print(f"{'='*60}")

            brand_data = {
                "brand_id": bc["brand_id"],
                "stores": {},
                "daily_summary": {},  # 按日汇总（品牌级）
                "crm": {},
                "supply_chain": {},
            }

            pinzhi = bc["pinzhi"]
            base_url = pinzhi["base_url"]
            merchant_token = pinzhi["token"]

            # ── 1. 品智：按日按店拉取经营数据 ──
            total_revenue_fen = 0
            total_orders = 0

            for store in bc["stores"]:
                store_name = store["name"]
                ognid = store["ognid"]
                store_token = store["token"]
                print(f"\n  📍 {store_name} (ognid={ognid})")

                store_data = {
                    "ognid": ognid,
                    "daily": {},
                    "total_revenue_fen": 0,
                    "total_order_count": 0,
                    "total_guest_count": 0,
                }

                for date in dates:
                    # 每日经营汇总
                    biz = await fetch_pinzhi_daily_biz(
                        client, base_url, merchant_token, ognid, date)

                    # 每日订单汇总
                    summary = await fetch_pinzhi_order_summary(
                        client, base_url, merchant_token, ognid, date)

                    # 每日订单明细
                    orders, err = await fetch_pinzhi_all_orders(
                        client, base_url, merchant_token, ognid, date)

                    # 计算当日汇总
                    day_revenue_fen = 0
                    day_order_count = 0
                    day_guest_count = 0

                    if orders:
                        for o in orders:
                            # billStatus=1 已结账
                            if o.get("billStatus") == 1:
                                day_order_count += 1
                                day_revenue_fen += int(o.get("realPrice") or 0)
                                day_guest_count += int(o.get("personNum") or o.get("guestCount") or 0)

                    store_data["daily"][date] = {
                        "biz_summary": biz if "error" not in biz else {"error": biz["error"]},
                        "order_summary": summary if "error" not in summary else {"error": summary["error"]},
                        "order_count": day_order_count,
                        "settled_order_count": day_order_count,
                        "revenue_fen": day_revenue_fen,
                        "revenue_yuan": round(day_revenue_fen / 100, 2),
                        "guest_count": day_guest_count,
                        "raw_orders_sample": orders[:3] if orders else [],  # 保存前3条样本
                        "total_orders_fetched": len(orders) if orders else 0,
                    }

                    store_data["total_revenue_fen"] += day_revenue_fen
                    store_data["total_order_count"] += day_order_count
                    store_data["total_guest_count"] += day_guest_count

                    await asyncio.sleep(0.1)

                store_data["total_revenue_yuan"] = round(store_data["total_revenue_fen"] / 100, 2)
                if store_data["total_order_count"] > 0:
                    store_data["avg_ticket_yuan"] = round(
                        store_data["total_revenue_yuan"] / store_data["total_order_count"], 2)
                else:
                    store_data["avg_ticket_yuan"] = 0

                total_revenue_fen += store_data["total_revenue_fen"]
                total_orders += store_data["total_order_count"]

                print(f"    营收: ¥{store_data['total_revenue_yuan']:,.2f}  "
                      f"订单: {store_data['total_order_count']}笔  "
                      f"客单价: ¥{store_data['avg_ticket_yuan']:.2f}")

                brand_data["stores"][store_name] = store_data

            # 品牌汇总
            brand_data["total_revenue_fen"] = total_revenue_fen
            brand_data["total_revenue_yuan"] = round(total_revenue_fen / 100, 2)
            brand_data["total_order_count"] = total_orders
            if total_orders > 0:
                brand_data["avg_ticket_yuan"] = round(
                    brand_data["total_revenue_yuan"] / total_orders, 2)
            else:
                brand_data["avg_ticket_yuan"] = 0

            print(f"\n  📊 {brand_name} 汇总: ¥{brand_data['total_revenue_yuan']:,.2f}  "
                  f"{total_orders}笔  客单价 ¥{brand_data['avg_ticket_yuan']:.2f}")

            # ── 2. 微生活CRM会员数据 ──
            print(f"\n  👥 拉取微生活会员数据...")
            crm_data = await fetch_crm_member_stats(client, bc["crm"])
            brand_data["crm"] = crm_data
            print(f"    完成: {list(crm_data.keys())}")

            # ── 3. 喰星云供应链（仅尝在一起）──
            if "chixingyun" in bc:
                print(f"\n  📦 拉取喰星云供应链数据...")
                scm_data = await fetch_chixingyun_data(client, bc["chixingyun"])
                brand_data["supply_chain"] = scm_data
                print(f"    完成: {list(scm_data.keys())}")

            all_data["brands"][brand_name] = brand_data

    # ── 输出 JSON ──
    output_path = os.path.join(os.path.dirname(__file__), "real_data_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n\n{'█'*60}")
    print(f"  数据拉取完成！")
    print(f"  输出文件: {output_path}")
    print(f"{'█'*60}")

    # 打印汇总
    print(f"\n{'='*60}")
    print(f"  汇总（{START_DATE} ~ {END_DATE}）")
    print(f"{'='*60}")
    print(f"  {'品牌':<8} {'营收(元)':<16} {'订单数':<10} {'客单价(元)':<12} {'门店数':<8}")
    print(f"  {'-'*54}")
    for bn, bd in all_data["brands"].items():
        print(f"  {bn:<8} ¥{bd['total_revenue_yuan']:>12,.2f} {bd['total_order_count']:>8}笔 "
              f"¥{bd['avg_ticket_yuan']:>8.2f} {len(bd['stores']):>5}家")
    print()


if __name__ == "__main__":
    asyncio.run(main())
