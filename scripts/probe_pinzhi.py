"""探测品智API正确的base_url"""
import urllib.request
import urllib.error

urls = [
    "http://czyq.pinzhikeji.net:8899/pzcatering-gateway/pinzhi/queryOrderListV2.do",
    "http://czyq.pinzhikeji.net:8899/pinzhi/queryOrderListV2.do",
    "http://czyq.pinzhikeji.net/pinzhi/queryOrderListV2.do",
    "https://czyq.pinzhikeji.net/pinzhi/queryOrderListV2.do",
    "http://czyq.pinzhikeji.net:8899/pzcatering-gateway/pinzhi/storeInfo.do",
    "http://czyq.pinzhikeji.net:8899/pinzhi/storeInfo.do",
    "http://czyq.pinzhikeji.net/pinzhi/storeInfo.do",
    "https://czyq.pinzhikeji.net/pinzhi/storeInfo.do",
]

for u in urls:
    try:
        r = urllib.request.Request(u, method="GET")
        resp = urllib.request.urlopen(r, timeout=5)
        print(f"{resp.status} {u}")
    except urllib.error.HTTPError as e:
        print(f"{e.code} {u}")
    except Exception as e:
        err = str(e)[:50]
        print(f"ERR {u} -> {err}")
