"""
微生活会员系统适配器（奥琦玮旗下，会员 & 交易接口）

Base URL: https://api.acewill.net
文档: https://www.yuque.com/acewillomp/odh93w（密码: cw01）

请求规范（官方文档）：
  - 所有接口仅支持 POST
  - Content-Type: multipart/form-data（不是 JSON！）
  - 业务参数 JSON 放在 req 字段
  - 公共参数: appid, v(2.0), ts(秒级时间戳), sig(MD5签名), fmt(JSON)

签名算法（官方 PHP demo 还原，必须严格遵守）：
  1. 所有业务参数递归按 ASCII key 排序（PHP ksort，3层递归）
  2. PHP http_build_query 等价拼接（RFC 1738，跳过 None/空字符串）
  3. 末尾追加 &appid=X&appkey=X&v=2.0&ts=X（秒级整数时间戳）
  4. 对整体做 MD5（小写 hex）→ 得到 sig
  appkey 仅用于签名计算，不发送到请求体中

响应格式: {"errcode": 0, "errmsg": "OK", "res": {...}}

注意：MD5 是 API 方要求，非我方选择。
"""
import asyncio
import hashlib
import json as _json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx
import structlog

logger = structlog.get_logger()

_API_VERSION = "2.0"


def _ksort_recursive(obj: Any) -> Any:
    """
    递归按 ASCII key 排序，等价于 PHP ksort（3层深度）。
    布尔值转换为 0/1（PHP 类型转换约定）。
    """
    if isinstance(obj, bool):
        return 1 if obj else 0
    if isinstance(obj, dict):
        return {k: _ksort_recursive(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_ksort_recursive(item) for item in obj]
    return obj


def _http_build_query(params: Any, prefix: str = "") -> str:
    """
    PHP http_build_query 等价实现（RFC 1738，application/x-www-form-urlencoded）。

    规则：
    - None 和空字符串跳过（PHP 的 empty() 语义）
    - 嵌套 dict  → prefix[key]=val
    - list        → prefix[0]=val&prefix[1]=val
    - 使用 quote_plus（空格编码为 +）
    """
    parts: List[str] = []

    if isinstance(params, dict):
        items: Any = params.items()
    elif isinstance(params, list):
        items = enumerate(params)
    else:
        # 标量直接返回
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


def _compute_sig(
    biz_params: Dict[str, Any],
    appid: str,
    appkey: str,
    ts: int,
    version: str = _API_VERSION,
) -> str:
    """
    奥琦玮 CRM 签名计算（模块级纯函数，便于测试）。

    算法步骤（严格还原 PHP demo）：
      1. ksort_recursive(biz_params)
      2. http_build_query → query_string
      3. query_string += f"&appid={appid}&appkey={appkey}&v={version}&ts={ts}"
      4. return MD5(query_string).lower()

    警告：不要在调用处打印 appkey，以防凭证泄露。
    """
    sorted_params = _ksort_recursive(biz_params)
    query = _http_build_query(sorted_params)
    query += f"&appid={appid}&appkey={appkey}&v={version}&ts={ts}"
    return hashlib.md5(query.encode("utf-8")).hexdigest().lower()


class AoqiweiCrmAdapter:
    """
    奥琦玮 CRM 会员 & 交易接口适配器。

    对应奥琦玮系统：api.acewill.net（原 welcrm.com，非供应链 openapi.acescm.cn）。
    环境变量：
        AOQIWEI_CRM_BASE_URL — 默认 https://api.acewill.net
        AOQIWEI_CRM_APPID    — CRM AppID
        AOQIWEI_CRM_APPKEY   — CRM AppKey（签名密钥，不发送到请求体）
        AOQIWEI_CRM_TIMEOUT  — 超时秒数，默认 30
        AOQIWEI_CRM_RETRY_TIMES — 重试次数，默认 3
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.base_url = config.get(
            "base_url", os.getenv("AOQIWEI_CRM_BASE_URL", "https://api.acewill.net")
        )
        self.appid = config.get("appid", os.getenv("AOQIWEI_CRM_APPID", ""))
        self.appkey = config.get("appkey", os.getenv("AOQIWEI_CRM_APPKEY", ""))
        self.timeout = config.get(
            "timeout", int(os.getenv("AOQIWEI_CRM_TIMEOUT", "30"))
        )
        self.retry_times = config.get(
            "retry_times", int(os.getenv("AOQIWEI_CRM_RETRY_TIMES", "3"))
        )

        if not self.appid or not self.appkey:
            logger.warning("奥琦玮CRM appid/appkey 未配置，将使用降级模式")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )
        logger.info("奥琦玮CRM适配器初始化", base_url=self.base_url)

    # ── 签名 & 请求构建 ────────────────────────────────────────────────────────

    def _sign(self, biz_params: Dict[str, Any], ts: int) -> str:
        """代理到模块级 _compute_sig，使实例方法可被子类 override。"""
        return _compute_sig(
            biz_params=biz_params,
            appid=self.appid,
            appkey=self.appkey,
            ts=ts,
        )

    def _build_request_body(self, biz_params: Dict[str, Any]) -> Dict[str, str]:
        """
        构建带签名的 multipart/form-data 请求体。

        微生活 API 要求：
          - 业务参数 JSON 序列化后放在 req 字段
          - 公共参数: appid, v, ts, sig, fmt 作为独立表单字段
          - appkey 仅用于签名计算，不包含在发送的请求体中
        """
        ts = int(time.time())
        sig = self._sign(biz_params, ts)
        body: Dict[str, str] = {
            "appid": self.appid,
            "v": _API_VERSION,
            "ts": str(ts),
            "sig": sig,
            "fmt": "JSON",
        }
        if biz_params:
            body["req"] = _json.dumps(biz_params, ensure_ascii=False)
        return body

    async def _request(
        self,
        endpoint: str,
        biz_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        POST 请求（multipart/form-data），带指数退避重试。
        微生活 API 响应格式: {"errcode": 0, "errmsg": "OK", "res": {...}}
        业务错误（errcode != 0）立即抛出，不重试。
        """
        body = self._build_request_body(biz_params or {})
        last_exc: Optional[Exception] = None

        for attempt in range(self.retry_times):
            if attempt > 0:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
            try:
                response = await self._client.post(endpoint, data=body)
                response.raise_for_status()
                result = response.json()

                errcode = result.get("errcode", -1)
                if errcode != 0:
                    errmsg = result.get("errmsg", "未知错误")
                    raise Exception(
                        f"微生活CRM业务错误 [errcode={errcode}]: {errmsg}"
                    )

                return result.get("res", result)

            except Exception as e:
                if "微生活CRM业务错误" in str(e):
                    raise
                last_exc = e
                logger.warning(
                    "CRM请求失败，准备重试",
                    endpoint=endpoint,
                    attempt=attempt + 1,
                    max_attempts=self.retry_times,
                    error=str(e),
                )

        raise Exception(f"CRM请求失败，已重试 {self.retry_times} 次: {last_exc}")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    # ── 交易接口 ──────────────────────────────────────────────────────────────

    async def deal_preview(
        self,
        cno: str,
        shop_id: int,
        cashier_id: int,
        consume_amount: int,
        payment_amount: int,
        payment_mode: int,
        biz_id: str,
        sub_balance: int = 0,
        sub_credit: int = 0,
    ) -> Dict[str, Any]:
        """
        交易预览（计算优惠，不扣款）。

        Args:
            cno:            用户卡号
            shop_id:        门店ID
            cashier_id:     收银员ID（-1 表示 API 调用方）
            consume_amount: 消费总金额（分）
            payment_amount: 实际支付金额（分）
            payment_mode:   支付方式 1=现金 2=银行卡 3=微信 4=支付宝
            biz_id:         收银方全局唯一业务号（最长64位）
            sub_balance:    储值使用金额（分），默认 0
            sub_credit:     积分抵扣金额（分），默认 0

        Returns:
            预览结果（优惠明细、最终应付金额等）
        """
        logger.info(
            "交易预览",
            cno=cno,
            shop_id=shop_id,
            consume_amount=consume_amount,
            biz_id=biz_id,
        )
        try:
            return await self._request(
                "/deal/preview",
                {
                    "cno": cno,
                    "shop_id": shop_id,
                    "cashier_id": cashier_id,
                    "consume_amount": consume_amount,
                    "payment_amount": payment_amount,
                    "payment_mode": payment_mode,
                    "sub_balance": sub_balance,
                    "sub_credit": sub_credit,
                    "biz_id": biz_id,
                },
            )
        except Exception as e:
            logger.warning("交易预览失败", error=str(e))
            return {"success": False, "message": str(e)}

    async def deal_submit(
        self,
        cno: str,
        shop_id: int,
        cashier_id: int,
        consume_amount: int,
        payment_amount: int,
        payment_mode: int,
        biz_id: str,
        sub_balance: int = 0,
        sub_credit: int = 0,
    ) -> Dict[str, Any]:
        """
        交易提交（实际扣款，biz_id 必须全局唯一）。
        参数说明同 deal_preview。
        """
        logger.info(
            "交易提交",
            cno=cno,
            shop_id=shop_id,
            consume_amount=consume_amount,
            biz_id=biz_id,
        )
        try:
            return await self._request(
                "/deal/commit",
                {
                    "cno": cno,
                    "shop_id": shop_id,
                    "cashier_id": cashier_id,
                    "consume_amount": consume_amount,
                    "payment_amount": payment_amount,
                    "payment_mode": payment_mode,
                    "sub_balance": sub_balance,
                    "sub_credit": sub_credit,
                    "biz_id": biz_id,
                },
            )
        except Exception as e:
            logger.warning("交易提交失败", error=str(e))
            return {"success": False, "message": str(e)}

    async def deal_reverse(
        self,
        biz_id: str,
        shop_id: int,
        cashier_id: int,
        reverse_reason: str = "",
    ) -> Dict[str, Any]:
        """
        交易冲正（撤销已提交的交易，原 biz_id 对应交易会被逆向）。

        Args:
            biz_id:         原交易的业务号
            shop_id:        门店ID
            cashier_id:     收银员ID
            reverse_reason: 冲正原因（可选）
        """
        logger.info("交易冲正", biz_id=biz_id, shop_id=shop_id)
        params: Dict[str, Any] = {
            "biz_id": biz_id,
            "shop_id": shop_id,
            "cashier_id": cashier_id,
        }
        if reverse_reason:
            params["reverse_reason"] = reverse_reason
        try:
            return await self._request("/deal/reverse", params)
        except Exception as e:
            logger.warning("交易冲正失败", error=str(e))
            return {"success": False, "message": str(e)}

    # ── 会员接口 ──────────────────────────────────────────────────────────────

    async def get_member_info(
        self,
        cno: Optional[str] = None,
        mobile: Optional[str] = None,
        shop_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取用户基本信息（积分、余额、等级等）。
        cno 与 mobile 至少填写一个。

        Args:
            cno:     用户卡号
            mobile:  手机号
            shop_id: 门店ID（可选）
        """
        if not cno and not mobile:
            raise ValueError("cno 和 mobile 至少填写一个")
        params: Dict[str, Any] = {}
        if cno:
            params["cno"] = cno
        if mobile:
            params["mobile"] = mobile
        if shop_id is not None:
            params["shop_id"] = shop_id

        logger.info("获取会员信息", cno=cno, mobile=mobile)
        try:
            return await self._request("/user/accountBasicsInfo", params)
        except Exception as e:
            logger.warning("获取会员信息失败", error=str(e))
            return {}
