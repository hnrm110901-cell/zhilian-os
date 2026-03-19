"""在 Docker 容器内部运行的集成测试脚本"""
import json
import os
import urllib.request
import urllib.error

API = "http://127.0.0.1:8000"

def req(method, path, data=None, token=None):
    url = API + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=30)
        return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except:
            return {"error": str(e)}, e.code
    except Exception as e:
        return {"error": str(e)}, 0

print("===== 屯象OS 集成验证 =====\n")

# 1. 登录
print("[1/5] 登录...")
body, code = req("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin123"})
tk = body.get("access_token", "")
if not tk:
    print(f"  失败({code}): {body}")
    exit(1)
print(f"  成功 (token: {tk[:20]}...)")

# 2. 商户列表
print("\n[2/5] 商户列表...")
body, code = req("GET", "/api/v1/merchants", token=tk)
if isinstance(body, list):
    for m in body:
        print(f"  {m.get('brand_name','?')} ({m.get('brand_id','?')}) - {m.get('store_count',0)}店 - {m.get('status','?')}")
else:
    print(f"  ({code}) {json.dumps(body, ensure_ascii=False)[:200]}")

# 3. 订单统计
print("\n[3/5] 订单统计...")
try:
    body, code = req("GET", "/api/v1/orders/stats", token=tk)
    print(f"  ({code}) {json.dumps(body, ensure_ascii=False)[:200]}")
except:
    print("  (端点不可用)")

# 4. 品智POS同步
print("\n[4/5] 品智POS同步测试...")
from datetime import date, timedelta
yesterday = (date.today() - timedelta(days=1)).isoformat()
print(f"  同步日期: {yesterday}")
body, code = req("POST", "/api/v1/integrations/pos-sync", {
    "adapter": "pinzhi",
    "sync_date": yesterday,
    "store_ids": ["CZYZ-2461"]
}, token=tk)
if code == 200 and "stores" in body:
    for s in body["stores"]:
        print(f"  门店: {s.get('store_name','?')} | DB: {s.get('orders_in_db',0)} | POS: {s.get('pos_orders',0)} | 差异: {s.get('diff_orders',0)}")
    print(f"  成功: {body.get('success', False)}")
else:
    print(f"  ({code}) {json.dumps(body, ensure_ascii=False)[:300]}")

# 5. 外部系统健康检查
print("\n[5/5] 外部系统健康检查...")
body, code = req("GET", "/api/v1/external-systems", token=tk)
if isinstance(body, dict) and code == 200:
    for k, v in body.items():
        if isinstance(v, dict):
            print(f"  {k}: {v.get('status','?')} - {v.get('message','')}")
        else:
            print(f"  {k}: {v}")
else:
    print(f"  ({code}) {json.dumps(body, ensure_ascii=False)[:200]}")

print("\n===== 验证完成 =====")
