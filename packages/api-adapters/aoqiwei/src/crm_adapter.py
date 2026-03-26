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
import uuid
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

    # ── 会员查询/管理接口 ────────────────────────────────────────────────────

    async def query_member(
        self,
        card_no: Optional[str] = None,
        mobile: Optional[str] = None,
        openid: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        会员查询（支持卡号、手机号、微信openid三种查询方式）。

        三个参数至少填写一个，优先级：card_no > mobile > openid。
        查无结果返回 None（降级），不抛异常。

        Args:
            card_no: 会员卡号
            mobile:  手机号
            openid:  微信openid

        Returns:
            会员信息字典，包含余额(fen+yuan)、积分、等级等；查无返回 None
        """
        if not card_no and not mobile and not openid:
            raise ValueError("card_no、mobile、openid 至少填写一个")

        params: Dict[str, Any] = {}
        if card_no:
            params["cno"] = card_no
        if mobile:
            params["mobile"] = mobile
        if openid:
            params["openid"] = openid

        logger.info("查询会员", card_no=card_no, mobile=mobile)
        try:
            result = await self._request("/user/accountBasicsInfo", params)
            if not result:
                return None
            # 金额标准化：原始余额(分) + 转换后余额(元)
            balance_fen = result.get("balance", 0)
            result["balance_fen"] = balance_fen
            result["balance_yuan"] = round(balance_fen / 100, 2)
            return result
        except Exception as e:
            logger.warning("查询会员失败，返回降级数据", error=str(e))
            return None

    async def add_member(
        self,
        mobile: str,
        name: str,
        sex: int = 1,
        birthday: Optional[str] = None,
        card_type: int = 1,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        新增会员（开卡）。

        Args:
            mobile:    手机号（必填）
            name:      姓名（必填）
            sex:       性别 1=男 2=女
            birthday:  生日，格式 YYYY-MM-DD
            card_type: 卡类型 1=电子卡 2=实体卡
            store_id:  注册门店ID

        Returns:
            新会员信息（含 cno 卡号）
        """
        if not mobile:
            raise ValueError("mobile 不能为空")
        if not name:
            raise ValueError("name 不能为空")
        if sex not in (1, 2):
            raise ValueError(f"sex 必须为 1(男) 或 2(女)，实际值: {sex}")

        params: Dict[str, Any] = {
            "mobile": mobile,
            "name": name,
            "sex": sex,
            "card_type": card_type,
        }
        if birthday:
            params["birthday"] = birthday
        if store_id:
            params["shop_id"] = store_id

        logger.info("新增会员", mobile=mobile, name=name, store_id=store_id)
        try:
            return await self._request("/user/register", params)
        except Exception as e:
            logger.error("新增会员失败", error=str(e), mobile=mobile)
            return {"success": False, "message": str(e)}

    async def update_member(
        self,
        card_no: str,
        update_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        更新会员信息。

        Args:
            card_no:     会员卡号（必填）
            update_data: 可更新字段 — name, sex, birthday, mobile 等

        Returns:
            更新结果
        """
        if not card_no:
            raise ValueError("card_no 不能为空")

        params: Dict[str, Any] = {"cno": card_no}
        # 只传允许更新的字段，防止注入无关参数
        _allowed_fields = {"name", "sex", "birthday", "mobile", "address", "email", "id_card"}
        for key, val in update_data.items():
            if key in _allowed_fields and val is not None:
                params[key] = val

        logger.info("更新会员信息", card_no=card_no, fields=list(update_data.keys()))
        try:
            return await self._request("/user/update", params)
        except Exception as e:
            logger.error("更新会员信息失败", error=str(e), card_no=card_no)
            return {"success": False, "message": str(e)}

    # ── 积分接口 ──────────────────────────────────────────────────────────────

    async def query_member_points(
        self,
        card_no: str,
    ) -> Dict[str, Any]:
        """
        查询会员积分余额及明细。

        Args:
            card_no: 会员卡号

        Returns:
            积分信息（points 当前积分, points_history 历史累计）
        """
        if not card_no:
            raise ValueError("card_no 不能为空")

        logger.info("查询会员积分", card_no=card_no)
        try:
            result = await self._request(
                "/user/credit/query",
                {"cno": card_no},
            )
            return result if result else {"points": 0, "points_history": 0}
        except Exception as e:
            logger.warning("查询会员积分失败，返回降级数据", error=str(e))
            return {"points": 0, "points_history": 0}

    async def points_exchange(
        self,
        card_no: str,
        points: int,
        exchange_type: str,
        shop_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        积分兑换（兑礼品/抵扣现金等）。

        Args:
            card_no:       会员卡号
            points:        兑换积分数量（正整数）
            exchange_type: 兑换类型（gift=礼品, cash=现金抵扣, coupon=兑券）
            shop_id:       门店ID（可选）

        Returns:
            兑换结果，含实际扣减积分数
        """
        if not card_no:
            raise ValueError("card_no 不能为空")
        if points <= 0:
            raise ValueError(f"points 必须为正整数，实际值: {points}")
        if exchange_type not in ("gift", "cash", "coupon"):
            raise ValueError(f"exchange_type 必须为 gift/cash/coupon，实际值: {exchange_type}")

        params: Dict[str, Any] = {
            "cno": card_no,
            "credit": points,
            "exchange_type": exchange_type,
        }
        if shop_id is not None:
            params["shop_id"] = shop_id

        logger.info("积分兑换", card_no=card_no, points=points, exchange_type=exchange_type)
        try:
            return await self._request("/user/credit/exchange", params)
        except Exception as e:
            logger.error("积分兑换失败", error=str(e), card_no=card_no)
            return {"success": False, "message": str(e)}

    # ── 交易接口（高层封装，供 member_service 调用）─────────────────────────────

    async def trade_preview(
        self,
        card_no: str,
        store_id: str,
        cashier: str,
        amount: int,
        dish_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        交易预览（member_service 层调用入口，内部代理到 deal_preview）。

        Args:
            card_no:   会员卡号
            store_id:  门店ID
            cashier:   收银员标识
            amount:    消费总金额（分）
            dish_list: 菜品列表（可选，用于精确计算优惠）

        Returns:
            预览结果（优惠明细、最终应付金额等），金额同时提供 fen 和 yuan
        """
        biz_id = f"TP_{uuid.uuid4().hex[:16]}"
        result = await self.deal_preview(
            cno=card_no,
            shop_id=int(store_id) if store_id.isdigit() else 0,
            cashier_id=int(cashier) if cashier.lstrip("-").isdigit() else -1,
            consume_amount=amount,
            payment_amount=amount,
            payment_mode=3,
            biz_id=biz_id,
        )
        # 金额标准化
        if "final_amount" in result:
            result["final_amount_fen"] = result["final_amount"]
            result["final_amount_yuan"] = round(result["final_amount"] / 100, 2)
        return result

    async def trade_submit(
        self,
        card_no: str,
        store_id: str,
        cashier: str,
        amount: int,
        pay_type: int,
        trade_no: str,
        discount_plan: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        交易提交（member_service 层调用入口，内部代理到 deal_submit）。

        Args:
            card_no:        会员卡号
            store_id:       门店ID
            cashier:        收银员标识
            amount:         实付金额（分）
            pay_type:       支付方式 1=现金 2=银行卡 3=微信 4=支付宝
            trade_no:       第三方流水号（全局唯一）
            discount_plan:  抵扣方案 {"sub_balance": 分, "sub_credit": 分}

        Returns:
            交易结果，金额同时提供 fen 和 yuan
        """
        sub_balance = (discount_plan or {}).get("sub_balance", 0)
        sub_credit = (discount_plan or {}).get("sub_credit", 0)

        result = await self.deal_submit(
            cno=card_no,
            shop_id=int(store_id) if store_id.isdigit() else 0,
            cashier_id=int(cashier) if cashier.lstrip("-").isdigit() else -1,
            consume_amount=amount,
            payment_amount=amount,
            payment_mode=pay_type,
            biz_id=trade_no,
            sub_balance=sub_balance,
            sub_credit=sub_credit,
        )
        # 金额标准化
        if isinstance(result.get("amount"), int):
            result["amount_fen"] = result["amount"]
            result["amount_yuan"] = round(result["amount"] / 100, 2)
        return result

    async def trade_query(
        self,
        trade_id: Optional[str] = None,
        trade_no: Optional[str] = None,
        card_no: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        交易记录查询（支持按交易ID、流水号、卡号+日期范围查询）。

        Args:
            trade_id:   微生活交易ID
            trade_no:   第三方流水号
            card_no:    会员卡号
            start_date: 开始日期 YYYY-MM-DD
            end_date:   结束日期 YYYY-MM-DD

        Returns:
            交易记录列表，每条记录金额同时提供 fen 和 yuan
        """
        params: Dict[str, Any] = {}
        if trade_id:
            params["trade_id"] = trade_id
        if trade_no:
            params["biz_id"] = trade_no
        if card_no:
            params["cno"] = card_no
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        logger.info("查询交易记录", trade_id=trade_id, trade_no=trade_no, card_no=card_no)
        try:
            result = await self._request("/deal/query", params)
            # 结果可能是列表或包含 list 字段的字典
            records = result if isinstance(result, list) else result.get("list", [])
            # 金额标准化
            for record in records:
                for field in ("consume_amount", "payment_amount"):
                    if field in record and isinstance(record[field], int):
                        record[f"{field}_yuan"] = round(record[field] / 100, 2)
            return records
        except Exception as e:
            logger.warning("查询交易记录失败，返回空列表", error=str(e))
            return []

    async def trade_cancel(
        self,
        trade_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        交易撤销（对已完成的交易做逆向冲正）。

        Args:
            trade_id: 微生活交易ID 或原始 biz_id
            reason:   撤销原因

        Returns:
            撤销结果
        """
        if not trade_id:
            raise ValueError("trade_id 不能为空")

        logger.info("交易撤销", trade_id=trade_id, reason=reason)
        try:
            return await self._request(
                "/deal/cancel",
                {
                    "biz_id": trade_id,
                    "reason": reason,
                },
            )
        except Exception as e:
            logger.error("交易撤销失败", error=str(e), trade_id=trade_id)
            return {"success": False, "message": str(e)}

    # ── 储值（充值）接口 ──────────────────────────────────────────────────────

    async def recharge_submit(
        self,
        card_no: str,
        store_id: str,
        cashier: str,
        amount: int,
        pay_type: int,
        trade_no: str,
    ) -> Dict[str, Any]:
        """
        储值充值提交。

        Args:
            card_no:  会员卡号
            store_id: 充值门店ID
            cashier:  收银员标识
            amount:   充值金额（分）
            pay_type: 支付方式 1=现金 2=银行卡 3=微信 4=支付宝
            trade_no: 第三方流水号（全局唯一）

        Returns:
            充值结果，含充值后余额(fen+yuan)
        """
        if not card_no:
            raise ValueError("card_no 不能为空")
        if amount <= 0:
            raise ValueError(f"amount 必须为正整数（分），实际值: {amount}")

        params: Dict[str, Any] = {
            "cno": card_no,
            "shop_id": int(store_id) if store_id.isdigit() else 0,
            "cashier_id": int(cashier) if cashier.lstrip("-").isdigit() else -1,
            "recharge_amount": amount,
            "payment_mode": pay_type,
            "biz_id": trade_no,
        }

        logger.info("储值充值", card_no=card_no, amount=amount, store_id=store_id)
        try:
            result = await self._request("/recharge/commit", params)
            # 金额标准化
            if isinstance(result.get("balance"), int):
                result["balance_fen"] = result["balance"]
                result["balance_yuan"] = round(result["balance"] / 100, 2)
            result["recharge_amount_fen"] = amount
            result["recharge_amount_yuan"] = round(amount / 100, 2)
            return result
        except Exception as e:
            logger.error("储值充值失败", error=str(e), card_no=card_no)
            return {"success": False, "message": str(e)}

    async def recharge_query(
        self,
        card_no: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询储值/充值记录。

        Args:
            card_no:    会员卡号
            start_date: 开始日期 YYYY-MM-DD
            end_date:   结束日期 YYYY-MM-DD

        Returns:
            储值记录（含当前余额及充值历史）
        """
        if not card_no:
            raise ValueError("card_no 不能为空")

        params: Dict[str, Any] = {"cno": card_no}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        logger.info("查询储值记录", card_no=card_no)
        try:
            result = await self._request("/recharge/query", params)
            # 金额标准化
            if isinstance(result.get("balance"), int):
                result["balance_fen"] = result["balance"]
                result["balance_yuan"] = round(result["balance"] / 100, 2)
            return result if result else {"balance_fen": 0, "balance_yuan": 0.0, "records": []}
        except Exception as e:
            logger.warning("查询储值记录失败，返回降级数据", error=str(e))
            return {"balance_fen": 0, "balance_yuan": 0.0, "records": []}

    # ── 优惠券接口 ────────────────────────────────────────────────────────────

    async def coupon_list(
        self,
        card_no: str,
        store_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询会员可用优惠券列表。

        Args:
            card_no:  会员卡号
            store_id: 门店ID（可选，用于过滤门店可用券）

        Returns:
            优惠券列表，每张券包含 face_value_fen/face_value_yuan
        """
        if not card_no:
            raise ValueError("card_no 不能为空")

        params: Dict[str, Any] = {"cno": card_no}
        if store_id:
            params["shop_id"] = int(store_id) if store_id.isdigit() else 0

        logger.info("查询优惠券", card_no=card_no, store_id=store_id)
        try:
            result = await self._request("/coupon/list", params)
            coupons = result if isinstance(result, list) else result.get("list", [])
            # 金额标准化：面值
            for coupon in coupons:
                if isinstance(coupon.get("face_value"), int):
                    coupon["face_value_fen"] = coupon["face_value"]
                    coupon["face_value_yuan"] = round(coupon["face_value"] / 100, 2)
            return coupons
        except Exception as e:
            logger.warning("查询优惠券失败，返回空列表", error=str(e))
            return []

    async def coupon_use(
        self,
        code: str,
        store_id: str,
        cashier: str,
        amount: int,
    ) -> Dict[str, Any]:
        """
        优惠券核销。

        Args:
            code:     券码
            store_id: 门店ID
            cashier:  收银员标识
            amount:   消费金额（分），用于判断是否满足使用门槛

        Returns:
            核销结果
        """
        if not code:
            raise ValueError("code 不能为空")
        if amount < 0:
            raise ValueError(f"amount 不能为负数，实际值: {amount}")

        params: Dict[str, Any] = {
            "coupon_code": code,
            "shop_id": int(store_id) if store_id.isdigit() else 0,
            "cashier_id": int(cashier) if cashier.lstrip("-").isdigit() else -1,
            "consume_amount": amount,
        }

        logger.info("券码核销", code=code, store_id=store_id, amount=amount)
        try:
            result = await self._request("/coupon/use", params)
            # 金额标准化
            if isinstance(result.get("discount_amount"), int):
                result["discount_amount_fen"] = result["discount_amount"]
                result["discount_amount_yuan"] = round(result["discount_amount"] / 100, 2)
            return result
        except Exception as e:
            logger.error("券码核销失败", error=str(e), code=code)
            return {"success": False, "message": str(e)}

    # ── 原有交易接口（底层，直接对接微生活API路径）────────────────────────────

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
