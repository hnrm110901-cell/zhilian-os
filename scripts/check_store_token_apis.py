"""
用门店Token测试品智接口（菜品、员工、桌台等）
品智技术确认：部分接口需要门店Token而非商户Token
"""
import asyncio
import hashlib
from collections import OrderedDict
from datetime import datetime, timedelta
import httpx


def pinzhi_sign(token, params):
    filtered = {k: v for k, v in params.items()
                if k not in ("sign", "pageIndex", "pageSize") and v is not None}
    ordered = OrderedDict(sorted(filtered.items()))
    param_str = "&".join(f"{k}={v}" for k, v in ordered.items())
    param_str += f"&token={token}"
    return hashlib.md5(param_str.encode()).hexdigest()


async def try_endpoint(client, base_url, token, method, endpoint, params, label=""):
    p = dict(params)
    p["sign"] = pinzhi_sign(token, p)
    url = f"{base_url}{endpoint}"
    try:
        if method == "GET":
            resp = await client.get(url, params=p, timeout=15)
        else:
            resp = await client.post(url, data=p, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # 检查错误
        success = data.get("success")
        if success is not None and success != 0:
            return False, f"品智错误: {data.get('msg', '?')}"
        errcode = data.get("errcode")
        if errcode is not None and errcode != 0:
            return False, f"品智错误: {data.get('errmsg', '?')}"
        # 统计条数
        for key in ("res", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return True, f"共{len(val)}条"
        return True, "成功"
    except Exception as e:
        return False, str(e)[:60]


async def main():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 测试用：尝在一起文化城店
    tests = [
        {
            "brand": "尝在一起",
            "base_url": "https://czyq.pinzhikeji.net/pzcatering-gateway",
            "merchant_token": "3bbc9bed2b42c1e1b3cca26389fbb81c",
            "store": {"name": "文化城店", "ognid": "2461", "token": "752b4b16a863ce47def11cf33b1b521f"},
        },
        {
            "brand": "最黔线",
            "base_url": "https://ljcg.pinzhikeji.net/pzcatering-gateway",
            "merchant_token": "47a428538d350fac1640a51b6bbda68c",
            "store": {"name": "马家湾店", "ognid": "20529", "token": "29cdb6acac3615070bb853afcbb32f60"},
        },
        {
            "brand": "尚宫厨",
            "base_url": "https://xcsgc.pinzhikeji.net/pzcatering-gateway",
            "merchant_token": "8275cf74d1943d7a32531d2d4f889870",
            "store": {"name": "星沙店", "ognid": "2463", "token": "852f1d34c75af0b8eb740ef47f133130"},
        },
    ]

    # 要测试的接口（之前用商户Token失败的）
    endpoints = [
        ("POST", "菜品列表(querydishes)", "/pinzhi/querydishes.do", {"updatetime": 0}),
        ("POST", "菜品列表(DishesInfo)", "/pinzhi/queryDishesInfo.do", {"updatetime": 0}),
        ("GET",  "菜品列表(DishesInfo GET)", "/pinzhi/queryDishesInfo.do", {"updatetime": 0}),
        ("GET",  "员工(employe)", "/pinzhi/employe.do", {}),
        ("GET",  "员工(queryUserInfo)", "/pinzhi/queryUserInfo.do", {}),
        ("GET",  "桌台(queryTable)", "/pinzhi/queryTable.do", {}),
        ("GET",  "做法配料", "/pinzhi/queryPractice.do", {}),
        ("GET",  "订单V1(order.do)", "/pinzhi/order.do", {"beginDate": yesterday, "endDate": yesterday, "pageIndex": 1, "pageSize": 5}),
    ]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for t in tests:
            store = t["store"]
            print(f"\n{'='*60}")
            print(f"  {t['brand']} — {store['name']} (ognid={store['ognid']})")
            print(f"{'='*60}")

            for method, name, endpoint, params in endpoints:
                # 带 ognid 的参数
                p_with_ognid = {**params, "ognid": store["ognid"]}
                p_without_ognid = dict(params)

                # 1. 门店Token + ognid
                ok, msg = await try_endpoint(client, t["base_url"], store["token"],
                                             method, endpoint, p_with_ognid)
                if ok:
                    print(f"  ✅ {name:<28} 门店Token+ognid → {msg}")
                    continue

                # 2. 门店Token 无 ognid
                ok2, msg2 = await try_endpoint(client, t["base_url"], store["token"],
                                               method, endpoint, p_without_ognid)
                if ok2:
                    print(f"  ✅ {name:<28} 门店Token → {msg2}")
                    continue

                # 3. 商户Token + ognid
                ok3, msg3 = await try_endpoint(client, t["base_url"], t["merchant_token"],
                                               method, endpoint, p_with_ognid)
                if ok3:
                    print(f"  ✅ {name:<28} 商户Token+ognid → {msg3}")
                    continue

                # 全失败
                print(f"  ❌ {name:<28} 门店({msg[:30]}) / 商户({msg3[:30]})")


if __name__ == "__main__":
    asyncio.run(main())
