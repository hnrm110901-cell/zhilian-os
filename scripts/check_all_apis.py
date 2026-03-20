"""
三品牌 API 接口全面健康检查
检测 尝在一起、最黔线、尚宫厨 的品智收银 + 微生活CRM 接口连通性
独立脚本，无内部依赖
"""
import asyncio
import hashlib
import time
import json
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx


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


async def pinzhi_request(client: httpx.AsyncClient, base_url: str, token: str,
                         method: str, endpoint: str, params: dict = None,
                         retry_upper: bool = True) -> dict:
    """发送品智请求，sign error 时自动重试大写签名"""
    params = dict(params or {})
    url = f"{base_url}{endpoint}"

    for upper in ([False, True] if retry_upper else [False]):
        p = dict(params)
        p["sign"] = pinzhi_sign(token, p, upper=upper)
        try:
            if method == "GET":
                resp = await client.get(url, params=p, timeout=15)
            else:
                resp = await client.post(url, data=p, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            success = data.get("success")
            if success is not None and success != 0:
                msg = data.get("msg", "未知")
                if "sign error" in msg and not upper:
                    continue  # 重试大写
                raise Exception(f"品智错误: {msg}")
            errcode = data.get("errcode")
            if errcode is not None and errcode != 0:
                msg = data.get("errmsg", "未知")
                if "sign error" in msg and not upper:
                    continue
                raise Exception(f"品智错误: {msg}")
            return data
        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            if "sign error" in str(e) and not upper:
                continue
            raise
    raise Exception("品智错误: sign error (大小写均失败)")


# ══════════════════════════════════════════════════════════════
#  微生活CRM签名（奥琦玮 api.acewill.net）
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


def crm_sign(biz_params: dict, appid: str, appkey: str, ts: int) -> str:
    sorted_params = _ksort_recursive(biz_params)
    query = _http_build_query(sorted_params)
    query += f"&appid={appid}&appkey={appkey}&v=2.0&ts={ts}"
    return hashlib.md5(query.encode()).hexdigest().lower()


async def crm_request(client: httpx.AsyncClient, base_url: str,
                      appid: str, appkey: str, endpoint: str,
                      biz_params: dict = None) -> dict:
    ts = int(time.time())
    biz = biz_params or {}
    sig = crm_sign(biz, appid, appkey, ts)
    body = {
        "appid": appid,
        "v": "2.0",
        "ts": str(ts),
        "sig": sig,
        "fmt": "JSON",
    }
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
#  品牌配置
# ══════════════════════════════════════════════════════════════

BRANDS = {
    "尝在一起": {
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
    },
    "最黔线": {
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
        "pinzhi": {
            "base_url": "https://xcsgc.pinzhikeji.net/pzcatering-gateway",
            "token": "8275cf74d1943d7a32531d2d4f889870",
        },
        "stores": [
            {"name": "星沙店", "ognid": "2463", "token": "852f1d34c75af0b8eb740ef47f133130"},
            {"name": "梅溪湖店", "ognid": "7896", "token": "27a36f2feea6d3a914438f6cb32108c3"},
            {"name": "高铁南站店", "ognid": "24777", "token": "5cbfb449112f698218e0b1be1a3bc7c6"},
            {"name": "红星店", "ognid": "36199", "token": "08f3791e15f48338405728a3a92fcd7f"},
            {"name": "万家丽店", "ognid": "41405", "token": "bb7e89dcd0ac339b51631eca99e51c9b"},
        ],
        "crm": {
            "base_url": "https://api.acewill.net",
            "appid": "dp0X0jl45wauwdGgkRETITz",
            "appkey": "649738234c7426bfa0dbfa431c92a750",
            "merchant_id": "1549254243",
        },
    },
}


def count_items(data: dict) -> str:
    for key in ("res", "data"):
        val = data.get(key)
        if isinstance(val, list):
            return f"共{len(val)}条"
        if isinstance(val, dict):
            if "list" in val:
                return f"共{len(val['list'])}条"
            if "sum" in val:
                return "有汇总数据"
    return "成功"


async def check_pinzhi(brand_name: str, config: dict, stores: list):
    """检查品智收银全部接口"""
    print(f"\n{'='*60}")
    print(f"  品智收银 — {brand_name}")
    print(f"  {config['base_url']}")
    print(f"{'='*60}")

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    base = config["base_url"]
    token = config["token"]
    first_ognid = stores[0]["ognid"] if stores else ""
    results = []

    # 品智核心接口 (method, name, endpoint, params, required)
    checks = [
        ("GET",  "门店信息",        "/pinzhi/organizations.do",        {},                                          True),
        ("GET",  "菜品类别",        "/pinzhi/reportcategory.do",       {},                                          True),
        ("GET",  "菜品列表",        "/pinzhi/queryDishesInfo.do",      {"updatetime": 0},                           True),
        ("GET",  "支付方式",        "/pinzhi/payment.do",              {},                                          True),
        ("GET",  "每日经营数据",    "/pinzhi/queryOgnDailyBizData.do", {"businessDate": yesterday},                  True),
        ("GET",  "门店收入汇总",    "/pinzhi/queryOrderSummary.do",    {"ognid": first_ognid, "businessDate": yesterday}, True),
        ("POST", "订单列表",        "/pinzhi/orderNew.do",             {"ognid": first_ognid, "businessDate": yesterday, "pageIndex": 1, "pageSize": 5}, True),
        ("GET",  "挂账客户",        "/pinzhi/paymentCustomer.do",      {},                                          False),
        ("GET",  "桌台信息",        "/pinzhi/queryTable.do",           {"ognid": first_ognid},                       False),
        ("GET",  "员工列表",        "/pinzhi/queryUserInfo.do",        {"ognid": first_ognid, "storeId": first_ognid}, False),
    ]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for method, name, endpoint, params, required in checks:
            try:
                data = await pinzhi_request(client, base, token, method, endpoint, params)
                msg = count_items(data)
                tag = " [核心]" if required else ""
                print(f"  ✅ {name:<14}{tag} {msg}")
                results.append({"name": name, "ok": True, "msg": msg, "required": required, "data": data})
            except Exception as e:
                err = str(e)[:60]
                tag = " [核心]" if required else ""
                # 对于非核心接口 404，尝试备选路径
                if "404" in err and not required:
                    print(f"  ⚠️  {name:<14}{tag} 该网关未部署此接口")
                else:
                    print(f"  ❌ {name:<14}{tag} {err}")
                results.append({"name": name, "ok": False, "msg": err, "required": required})

        # 门店独立 Token 测试
        print(f"\n  --- 门店独立 Token ---")
        for store in stores:
            try:
                data = await pinzhi_request(client, base, store["token"], "GET",
                                            "/pinzhi/organizations.do",
                                            {"ognid": store["ognid"]})
                items = data.get("res", data.get("data", []))
                n = len(items) if isinstance(items, list) else 1
                print(f"  ✅ {store['name']:<12} ognid={store['ognid']} ({n}条)")
            except Exception as e:
                print(f"  ❌ {store['name']:<12} ognid={store['ognid']} {str(e)[:50]}")

    return results


async def check_crm(brand_name: str, config: dict):
    """检查微生活 CRM 连通性（api.acewill.net，POST + multipart签名）"""
    print(f"\n{'='*60}")
    print(f"  微生活CRM — {brand_name}")
    print(f"  merchant_id: {config['merchant_id']}")
    print(f"{'='*60}")

    crm_tests = [
        ("会员查询(手机号)", "/user/accountBasicsInfo", {"mobile": "13800000000"}),
        ("交易预览(连通测试)", "/deal/preview", {"cno": "test", "shop_id": 1, "cashier_id": -1,
                                                   "consume_amount": 100, "payment_amount": 100,
                                                   "payment_mode": 1, "biz_id": f"test_{int(time.time())}"}),
    ]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for name, endpoint, biz_params in crm_tests:
            try:
                result = await crm_request(
                    client, config["base_url"],
                    config["appid"], config["appkey"],
                    endpoint, biz_params
                )
                if isinstance(result, dict):
                    # 有返回数据说明接口连通
                    print(f"  ✅ {name:<20} 连通成功")
                else:
                    print(f"  ✅ {name:<20} 连通成功")
            except Exception as e:
                err = str(e)
                # 业务错误但接口连通也算成功（如"会员不存在"说明接口本身是通的）
                if "业务错误" in err or "CRM错误" in err:
                    # 提取 errcode
                    if "用户不存在" in err or "会员不存在" in err or "not found" in err.lower():
                        print(f"  ✅ {name:<20} 连通成功（测试号无数据，正常）")
                    elif "签名" in err or "sign" in err.lower() or "sig" in err.lower():
                        print(f"  ❌ {name:<20} 签名验证失败: {err[:50]}")
                    else:
                        print(f"  ⚠️  {name:<20} 接口连通，业务返回: {err[:50]}")
                else:
                    print(f"  ❌ {name:<20} {err[:60]}")


async def print_basic_data(brand_name: str, results: list):
    """从检查结果中提取并展示基础资料"""
    for r in results:
        if not r.get("ok") or "data" not in r:
            continue
        data = r["data"]
        if r["name"] == "门店信息":
            items = data.get("res", data.get("data", []))
            if isinstance(items, list) and items:
                print(f"\n  🏪 {brand_name} 门店 ({len(items)}家):")
                for s in items:
                    ognid = s.get("ognid", s.get("id", "?"))
                    name = s.get("ognName", s.get("name", "?"))
                    print(f"     {name} (ognid={ognid})")
        elif r["name"] == "菜品类别":
            items = data.get("data", [])
            if isinstance(items, list):
                print(f"  📂 {brand_name} 菜品类别: {len(items)}个")
        elif r["name"] == "菜品列表":
            items = data.get("data", [])
            if isinstance(items, list) and items:
                print(f"  🍽️  {brand_name} 菜品: {len(items)}个（前5）:")
                for d in items[:5]:
                    name = d.get("dishName", d.get("name", "?"))
                    price = d.get("dishPrice", d.get("price", 0))
                    if isinstance(price, (int, float)) and price > 100:
                        price = price / 100
                    print(f"     {name} ¥{price}")


async def main():
    print("\n" + "█" * 60)
    print("  屯象OS — 三品牌 API 全面健康检查")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█" * 60)

    all_summary = {}

    for brand_name, bc in BRANDS.items():
        # 1. 品智收银
        results = await check_pinzhi(brand_name, bc["pinzhi"], bc["stores"])

        # 2. 微生活 CRM
        await check_crm(brand_name, bc["crm"])

        # 3. 基础资料展示
        await print_basic_data(brand_name, results)

        passed = sum(1 for r in results if r["ok"])
        total = len(results)
        core_passed = sum(1 for r in results if r["ok"] and r["required"])
        core_total = sum(1 for r in results if r["required"])

        all_summary[brand_name] = {
            "total": f"{passed}/{total}",
            "core": f"{core_passed}/{core_total}",
        }

    # 汇总
    print("\n\n" + "█" * 60)
    print("  汇总报告")
    print("█" * 60)
    print(f"\n  {'品牌':<10} {'总通过':<12} {'核心接口':<12}")
    print("  " + "-" * 34)
    for brand_name, data in all_summary.items():
        print(f"  {brand_name:<10} {data['total']:<12} {data['core']:<12}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
