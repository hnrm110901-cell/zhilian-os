"""验证品智API正确的端点名称"""
import hashlib
import os
import urllib.request
import urllib.error
from collections import OrderedDict

TOKEN = os.getenv("PINZHI_PROBE_TOKEN")
if not TOKEN:
    raise ValueError("PINZHI_PROBE_TOKEN environment variable not set")
BASE = "http://czyq.pinzhikeji.net:8899/pzcatering-gateway"

def sign(token, params):
    f = {k: v for k, v in params.items() if k not in ["sign","pageIndex","pageSize"] and v is not None}
    o = OrderedDict(sorted(f.items()))
    s = "&".join(f"{k}={v}" for k, v in o.items()) + f"&token={token}"
    return hashlib.md5(s.encode()).hexdigest()

endpoints = [
    ("/pinzhi/orderNew.do", {"beginDate":"2026-03-16","endDate":"2026-03-16","pageIndex":"1","pageSize":"5"}),
    ("/pinzhi/queryOrderListV2.do", {"beginDate":"2026-03-16","endDate":"2026-03-16","pageIndex":"1","pageSize":"5"}),
    ("/pinzhi/order.do", {"beginDate":"2026-03-16","endDate":"2026-03-16"}),
    ("/pinzhi/organizations.do", {}),
    ("/pinzhi/storeInfo.do", {}),
    ("/pinzhi/reportcategory.do", {}),
    ("/pinzhi/queryOrderSummary.do", {"businessDate":"2026-03-16","ognid":"2461"}),
]

for ep, params in endpoints:
    p = dict(params)
    p["sign"] = sign(TOKEN, p)
    qs = "&".join(f"{k}={v}" for k, v in p.items())
    url = f"{BASE}{ep}?{qs}"
    try:
        r = urllib.request.urlopen(url, timeout=8)
        body = r.read().decode()[:150]
        print(f"{r.status} {ep} -> {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100] if e.fp else ""
        print(f"{e.code} {ep} -> {body[:80]}")
    except Exception as e:
        print(f"ERR {ep} -> {str(e)[:60]}")
