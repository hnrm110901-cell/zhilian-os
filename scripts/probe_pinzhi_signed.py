"""带签名的品智API探测"""
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error
from collections import OrderedDict

sys.path.insert(0, "/app")

def generate_sign(token, params):
    filtered = {k: v for k, v in params.items()
                if k not in ["sign", "pageIndex", "pageSize"] and v is not None}
    ordered = OrderedDict(sorted(filtered.items()))
    s = "&".join(f"{k}={v}" for k, v in ordered.items())
    s += f"&token={token}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()

# 从数据库读取凭证
try:
    import asyncio
    from sqlalchemy import text
    from src.core.database import get_db_session

    async def get_creds():
        async with get_db_session() as session:
            r = await session.execute(text(
                "SELECT api_endpoint, api_secret, config "
                "FROM external_systems "
                "WHERE provider='pinzhi' AND store_id='CZYZ-2461'"
            ))
            row = r.fetchone()
            if row:
                cfg = row[2] if isinstance(row[2], dict) else (json.loads(row[2]) if row[2] else {})
                return {
                    "api_endpoint": row[0],
                    "token": cfg.get("pinzhi_store_token") or row[1],
                    "config": cfg,
                }
            return None

    creds = asyncio.run(get_creds())
except Exception as e:
    print(f"DB读取失败: {e}")
    creds = None

if not creds:
    print("无法获取凭证")
    sys.exit(1)

base = creds["api_endpoint"]
token = creds["token"]
print(f"base_url: {base}")
print(f"token: {token[:10]}...")

# 测试多个base_url + storeInfo.do
bases = [
    base,
    base.replace("/pzcatering-gateway", ""),
    "https://czyq.pinzhikeji.net",
]

for b in bases:
    params = {}
    sign = generate_sign(token, params)
    url = f"{b}/pinzhi/storeInfo.do?sign={sign}"
    try:
        r = urllib.request.urlopen(url, timeout=5)
        body = r.read().decode()[:200]
        print(f"\n{r.status} {b}/pinzhi/storeInfo.do")
        print(f"  body: {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200] if e.fp else ""
        print(f"\n{e.code} {b}/pinzhi/storeInfo.do")
        print(f"  body: {body}")
    except Exception as e:
        print(f"\nERR {b}/pinzhi/storeInfo.do -> {str(e)[:80]}")
