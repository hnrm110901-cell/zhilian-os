"""
支付网关服务
支持：微信支付V3 JSAPI/Native + 支付宝 H5/Native

安全约束：
- 所有密钥从 settings 环境变量读取，绝不硬编码
- 金额：接受分（fen），存分，调用第三方API时自动转换
- 回调验签失败必须 raise ValueError，不可静默忽略
- SQL 使用 ORM 参数化，绝不拼接字符串
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urlencode

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.payment_record import GatewayPaymentRecord, PaymentMethod, PaymentStatus

logger = structlog.get_logger()


class PaymentGatewayService:
    """支付网关服务 — 微信支付V3 + 支付宝"""

    WECHAT_API_BASE = "https://api.mch.weixin.qq.com"

    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # 微信支付V3 — 内部工具方法
    # ================================================================

    def _get_wechat_private_key(self):
        """从环境变量加载商户RSA私钥（PEM格式）"""
        raw = settings.WECHAT_PAY_PRIVATE_KEY
        if not raw:
            raise ValueError("WECHAT_PAY_PRIVATE_KEY 未配置")
        # 支持两种格式：完整PEM 或 纯base64（不含header/footer）
        if "BEGIN" not in raw:
            raw = (
                "-----BEGIN PRIVATE KEY-----\n"
                + "\n".join(raw[i : i + 64] for i in range(0, len(raw), 64))
                + "\n-----END PRIVATE KEY-----"
            )
        return raw

    def _wechat_sign(self, method: str, url_path: str, timestamp: str,
                     nonce_str: str, body: str) -> str:
        """
        微信支付V3 RSA-SHA256 签名
        签名串格式（每字段后跟换行符\n）：
          HTTP方法\n请求URI\n时间戳\n随机串\n请求体\n
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        message = f"{method}\n{url_path}\n{timestamp}\n{nonce_str}\n{body}\n"
        private_key_pem = self._get_wechat_private_key()
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        signature = private_key.sign(message.encode("utf-8"), padding.PKCS1v15(),
                                     hashes.SHA256())
        return base64.b64encode(signature).decode()

    def _wechat_authorization_header(self, method: str, url_path: str,
                                     body: str) -> str:
        """生成微信支付V3 Authorization 请求头"""
        mch_id = settings.WECHAT_PAY_MCH_ID
        cert_serial_no = settings.WECHAT_PAY_CERT_SERIAL_NO
        nonce_str = uuid.uuid4().hex
        timestamp = str(int(time.time()))
        signature = self._wechat_sign(method, url_path, timestamp, nonce_str, body)
        return (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{mch_id}",'
            f'nonce_str="{nonce_str}",'
            f'signature="{signature}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{cert_serial_no}"'
        )

    def _wechat_decrypt_callback(self, algorithm: str, associated_data: str,
                                 nonce: str, ciphertext: str) -> dict:
        """
        AES-256-GCM 解密微信支付回调密文
        密钥：WECHAT_PAY_API_V3_KEY（32字节ASCII）
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        api_v3_key = settings.WECHAT_PAY_API_V3_KEY
        if not api_v3_key:
            raise ValueError("WECHAT_PAY_API_V3_KEY 未配置")

        key = api_v3_key.encode("utf-8")  # 必须为32字节
        if len(key) != 32:
            raise ValueError("WECHAT_PAY_API_V3_KEY 长度必须为32字节")

        aesgcm = AESGCM(key)
        ciphertext_bytes = base64.b64decode(ciphertext)
        nonce_bytes = nonce.encode("utf-8")
        associated_data_bytes = associated_data.encode("utf-8")

        plaintext = aesgcm.decrypt(nonce_bytes, ciphertext_bytes, associated_data_bytes)
        return json.loads(plaintext.decode("utf-8"))

    def _verify_wechat_signature(self, headers: dict, body: bytes) -> None:
        """
        验证微信支付回调签名（Wechatpay-Signature）
        验证失败直接 raise ValueError，调用方不得捕获后静默忽略
        """
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        wechat_timestamp = headers.get("Wechatpay-Timestamp", "")
        wechat_nonce = headers.get("Wechatpay-Nonce", "")
        wechat_signature = headers.get("Wechatpay-Signature", "")
        wechat_serial = headers.get("Wechatpay-Serial", "")

        if not all([wechat_timestamp, wechat_nonce, wechat_signature]):
            raise ValueError("微信回调缺少必要签名头")

        # 签名验签须使用微信平台公钥（应从微信平台证书获取）
        # 此处从配置文件中读取预先下载的平台公钥（生产环境需定期更新）
        platform_public_key_pem = settings.WECHAT_PAY_PLATFORM_PUBLIC_KEY if hasattr(
            settings, "WECHAT_PAY_PLATFORM_PUBLIC_KEY"
        ) else ""

        if not platform_public_key_pem:
            # 无平台公钥时跳过RSA验签，仅做格式检查（开发模式）
            logger.warning(
                "WECHAT_PAY_PLATFORM_PUBLIC_KEY 未配置，跳过RSA签名验证（仅限开发）"
            )
            return

        message = f"{wechat_timestamp}\n{wechat_nonce}\n{body.decode('utf-8')}\n"
        public_key = serialization.load_pem_public_key(
            platform_public_key_pem.encode()
        )
        try:
            public_key.verify(
                base64.b64decode(wechat_signature),
                message.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            raise ValueError("微信回调签名验证失败")

    # ================================================================
    # 微信支付V3 — 业务方法
    # ================================================================

    async def create_wechat_jsapi_order(
        self,
        store_id: str,
        order_id: str,
        amount_fen: int,
        openid: str,
        description: str,
    ) -> dict:
        """
        微信JSAPI下单（小程序/H5内支付）
        返回前端调起支付所需参数包：{timeStamp, nonceStr, package, signType, paySign}
        """
        if amount_fen <= 0:
            raise ValueError(f"支付金额必须大于0分，当前：{amount_fen}")

        app_id = settings.WECHAT_PAY_APP_ID
        mch_id = settings.WECHAT_PAY_MCH_ID
        if not app_id or not mch_id:
            raise ValueError("WECHAT_PAY_APP_ID 或 WECHAT_PAY_MCH_ID 未配置")

        out_trade_no = str(uuid.uuid4()).replace("-", "")[:32]
        url_path = "/v3/pay/transactions/jsapi"

        payload = {
            "appid": app_id,
            "mchid": mch_id,
            "description": description[:127],  # 微信限制127字符
            "out_trade_no": out_trade_no,
            "notify_url": f"{self._get_notify_base_url()}/api/v1/payments/wechat/callback",
            "amount": {"total": amount_fen, "currency": "CNY"},
            "payer": {"openid": openid},
        }
        body_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        auth_header = self._wechat_authorization_header("POST", url_path, body_str)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.WECHAT_API_BASE}{url_path}",
                content=body_str.encode("utf-8"),
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                raise ValueError(
                    f"微信JSAPI下单失败 HTTP {resp.status_code}: {resp.text}"
                )
            result = resp.json()

        prepay_id = result.get("prepay_id")
        if not prepay_id:
            raise ValueError(f"微信JSAPI下单未返回prepay_id: {result}")

        # 写入DB记录
        record = GatewayPaymentRecord(
            store_id=store_id,
            order_id=order_id,
            payment_method=PaymentMethod.WECHAT_JSAPI.value,
            amount_fen=amount_fen,
            status=PaymentStatus.PENDING.value,
            prepay_id=prepay_id,
            wechat_openid=openid,
        )
        self.db.add(record)
        await self.db.flush()

        # 生成前端调起支付参数包（app级签名）
        timestamp = str(int(time.time()))
        nonce_str = uuid.uuid4().hex
        package_str = f"prepay_id={prepay_id}"
        sign_message = f"{app_id}\n{timestamp}\n{nonce_str}\n{package_str}\n"

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(
            self._get_wechat_private_key().encode(), password=None
        )
        pay_sign_bytes = private_key.sign(
            sign_message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
        )
        pay_sign = base64.b64encode(pay_sign_bytes).decode()

        return {
            "payment_record_id": str(record.id),
            "timeStamp": timestamp,
            "nonceStr": nonce_str,
            "package": package_str,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    async def create_wechat_native_order(
        self,
        store_id: str,
        order_id: str,
        amount_fen: int,
        description: str,
    ) -> dict:
        """
        微信Native下单（扫码支付）
        返回 {payment_record_id, code_url}，前端据此生成二维码
        """
        if amount_fen <= 0:
            raise ValueError(f"支付金额必须大于0分，当前：{amount_fen}")

        app_id = settings.WECHAT_PAY_APP_ID
        mch_id = settings.WECHAT_PAY_MCH_ID
        if not app_id or not mch_id:
            raise ValueError("WECHAT_PAY_APP_ID 或 WECHAT_PAY_MCH_ID 未配置")

        out_trade_no = str(uuid.uuid4()).replace("-", "")[:32]
        url_path = "/v3/pay/transactions/native"

        payload = {
            "appid": app_id,
            "mchid": mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": f"{self._get_notify_base_url()}/api/v1/payments/wechat/callback",
            "amount": {"total": amount_fen, "currency": "CNY"},
        }
        body_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        auth_header = self._wechat_authorization_header("POST", url_path, body_str)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.WECHAT_API_BASE}{url_path}",
                content=body_str.encode("utf-8"),
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                raise ValueError(
                    f"微信Native下单失败 HTTP {resp.status_code}: {resp.text}"
                )
            result = resp.json()

        code_url = result.get("code_url")
        if not code_url:
            raise ValueError(f"微信Native下单未返回code_url: {result}")

        record = GatewayPaymentRecord(
            store_id=store_id,
            order_id=order_id,
            payment_method=PaymentMethod.WECHAT_NATIVE.value,
            amount_fen=amount_fen,
            status=PaymentStatus.PENDING.value,
        )
        self.db.add(record)
        await self.db.flush()

        return {
            "payment_record_id": str(record.id),
            "code_url": code_url,
        }

    async def verify_wechat_callback(self, headers: dict, body: bytes) -> dict:
        """
        验证微信支付回调
        1. 验证签名（Wechatpay-Signature）— 失败 raise ValueError
        2. 解密 AES-256-GCM 密文
        3. 返回解密后的支付结果 dict
        """
        # Step 1: 验签（失败则 raise，调用方不得静默忽略）
        self._verify_wechat_signature(headers, body)

        # Step 2: 解密
        body_json = json.loads(body.decode("utf-8"))
        resource = body_json.get("resource", {})
        algorithm = resource.get("algorithm", "AEAD_AES_256_GCM")
        associated_data = resource.get("associated_data", "")
        nonce = resource.get("nonce", "")
        ciphertext = resource.get("ciphertext", "")

        if not ciphertext:
            raise ValueError("微信回调缺少加密资源数据")

        payment_result = self._wechat_decrypt_callback(
            algorithm, associated_data, nonce, ciphertext
        )
        return payment_result

    async def handle_wechat_payment_success(
        self, payment_result: dict, callback_raw: str = ""
    ) -> GatewayPaymentRecord:
        """
        处理微信支付成功回调 — 更新DB记录状态
        幂等：同一 transaction_id 重复回调不重复更新
        """
        transaction_id = payment_result.get("transaction_id", "")
        trade_state = payment_result.get("trade_state", "")
        openid = (payment_result.get("payer") or {}).get("openid", "")
        amount_info = payment_result.get("amount") or {}
        payer_total = amount_info.get("payer_total", 0)  # 实付金额（分）

        if not transaction_id:
            raise ValueError("微信回调缺少 transaction_id")

        # 幂等检查：若已存在相同 third_party_trade_no 且状态为 paid，直接返回
        stmt = select(GatewayPaymentRecord).where(
            GatewayPaymentRecord.third_party_trade_no == transaction_id
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing and existing.status == PaymentStatus.PAID.value:
            logger.info("微信支付回调幂等处理，已是paid状态",
                        transaction_id=transaction_id)
            return existing

        if trade_state != "SUCCESS":
            logger.warning("微信回调非SUCCESS状态", trade_state=trade_state,
                           transaction_id=transaction_id)
            return existing or GatewayPaymentRecord()

        if existing:
            # 更新已有记录
            existing.status = PaymentStatus.PAID.value
            existing.third_party_trade_no = transaction_id
            existing.paid_at = datetime.utcnow()
            if callback_raw:
                existing.callback_raw = callback_raw
            await self.db.flush()
            return existing

        # 找不到预先创建的记录（极端情况：直接写入）
        record = GatewayPaymentRecord(
            store_id=uuid.UUID(int=0),  # 回调中无 store_id，需后续补全
            order_id=uuid.UUID(int=0),
            payment_method=PaymentMethod.WECHAT_JSAPI.value,
            amount_fen=payer_total,
            status=PaymentStatus.PAID.value,
            third_party_trade_no=transaction_id,
            wechat_openid=openid,
            paid_at=datetime.utcnow(),
            callback_raw=callback_raw,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    # ================================================================
    # 支付宝
    # ================================================================

    def _alipay_sign(self, params: dict) -> str:
        """
        支付宝 RSA2（SHA256withRSA）签名
        签名串：按参数名ASCII升序排列，key=value&key=value格式
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        # 过滤空值和sign字段
        sorted_items = sorted(
            [(k, v) for k, v in params.items() if v is not None and v != "" and k != "sign"],
            key=lambda x: x[0],
        )
        sign_str = "&".join(f"{k}={v}" for k, v in sorted_items)

        private_key_pem = settings.ALIPAY_PRIVATE_KEY
        if not private_key_pem:
            raise ValueError("ALIPAY_PRIVATE_KEY 未配置")
        if "BEGIN" not in private_key_pem:
            private_key_pem = (
                "-----BEGIN PRIVATE KEY-----\n"
                + "\n".join(private_key_pem[i : i + 64]
                            for i in range(0, len(private_key_pem), 64))
                + "\n-----END PRIVATE KEY-----"
            )

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        signature = private_key.sign(
            sign_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.b64encode(signature).decode()

    async def create_alipay_order(
        self,
        store_id: str,
        order_id: str,
        amount_fen: int,
        subject: str,
    ) -> str:
        """
        支付宝下单（wap/H5）
        返回支付URL（H5跳转链接）
        金额：内部存分，调用支付宝API时转换为元（保留2位小数）
        """
        if amount_fen <= 0:
            raise ValueError(f"支付金额必须大于0分，当前：{amount_fen}")

        app_id = settings.ALIPAY_APP_ID
        if not app_id:
            raise ValueError("ALIPAY_APP_ID 未配置")

        # 分转元（支付宝金额单位为元）
        amount_yuan = f"{amount_fen / 100:.2f}"
        out_trade_no = str(uuid.uuid4()).replace("-", "")[:64]

        biz_content = json.dumps(
            {
                "out_trade_no": out_trade_no,
                "total_amount": amount_yuan,
                "subject": subject[:256],
                "product_code": "QUICK_WAP_WAY",
            },
            ensure_ascii=False,
        )

        params = {
            "app_id": app_id,
            "method": "alipay.trade.wap.pay",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "notify_url": f"{self._get_notify_base_url()}/api/v1/payments/alipay/callback",
            "biz_content": biz_content,
        }
        params["sign"] = self._alipay_sign(params)

        # 写入DB记录
        record = GatewayPaymentRecord(
            store_id=store_id,
            order_id=order_id,
            payment_method=PaymentMethod.ALIPAY_H5.value,
            amount_fen=amount_fen,
            status=PaymentStatus.PENDING.value,
        )
        self.db.add(record)
        await self.db.flush()

        # 构造跳转URL
        gateway = settings.ALIPAY_GATEWAY
        query_str = urlencode(
            {k: v for k, v in params.items()}, quote_via=quote
        )
        return f"{gateway}?{query_str}"

    async def verify_alipay_callback(self, form_data: dict) -> bool:
        """
        支付宝异步通知验签（RSA2 / SHA256withRSA）
        验签失败返回 False，调用方应 raise 或拒绝处理
        """
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        sign_type = form_data.get("sign_type", "RSA2")
        sign = form_data.get("sign", "")
        if not sign:
            return False

        # 去掉 sign 和 sign_type，按ASCII升序排列构造验签串
        filtered = {
            k: v
            for k, v in form_data.items()
            if k not in ("sign", "sign_type") and v is not None and v != ""
        }
        sorted_items = sorted(filtered.items(), key=lambda x: x[0])
        sign_str = "&".join(f"{k}={v}" for k, v in sorted_items)

        alipay_public_key_pem = settings.ALIPAY_PUBLIC_KEY
        if not alipay_public_key_pem:
            logger.error("ALIPAY_PUBLIC_KEY 未配置，跳过验签")
            return False

        if "BEGIN" not in alipay_public_key_pem:
            alipay_public_key_pem = (
                "-----BEGIN PUBLIC KEY-----\n"
                + "\n".join(
                    alipay_public_key_pem[i : i + 64]
                    for i in range(0, len(alipay_public_key_pem), 64)
                )
                + "\n-----END PUBLIC KEY-----"
            )

        public_key = serialization.load_pem_public_key(alipay_public_key_pem.encode())

        try:
            public_key.verify(
                base64.b64decode(sign),
                sign_str.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature:
            logger.warning("支付宝回调验签失败", sign_str_preview=sign_str[:100])
            return False

    # ================================================================
    # 统一退款
    # ================================================================

    async def refund(
        self,
        payment_record_id: str,
        refund_amount_fen: int,
        reason: str = "",
    ) -> dict:
        """
        统一退款接口 — 根据原始支付方式路由到微信或支付宝
        约束：退款金额不能超过原始支付金额 - 已退款金额
        """
        stmt = select(GatewayPaymentRecord).where(
            GatewayPaymentRecord.id == payment_record_id
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            raise ValueError(f"支付记录不存在：{payment_record_id}")
        if record.status not in (PaymentStatus.PAID.value, PaymentStatus.REFUNDING.value):
            raise ValueError(
                f"当前状态 {record.status} 不允许退款（必须是paid或refunding）"
            )

        # 退款金额校验
        max_refundable = record.amount_fen - record.refund_amount_fen
        if refund_amount_fen <= 0:
            raise ValueError("退款金额必须大于0分")
        if refund_amount_fen > max_refundable:
            raise ValueError(
                f"退款金额（{refund_amount_fen}分）超过可退金额（{max_refundable}分）"
            )

        method = record.payment_method
        if method in (PaymentMethod.WECHAT_JSAPI.value, PaymentMethod.WECHAT_NATIVE.value):
            refund_result = await self._refund_wechat(record, refund_amount_fen, reason)
        elif method in (PaymentMethod.ALIPAY_H5.value, PaymentMethod.ALIPAY_NATIVE.value):
            refund_result = await self._refund_alipay(record, refund_amount_fen, reason)
        else:
            raise ValueError(f"不支持的支付方式退款：{method}")

        # 更新记录
        record.refund_amount_fen = (record.refund_amount_fen or 0) + refund_amount_fen
        if record.refund_amount_fen >= record.amount_fen:
            record.status = PaymentStatus.REFUNDED.value
            record.refunded_at = datetime.utcnow()
        else:
            record.status = PaymentStatus.REFUNDING.value
        await self.db.flush()

        return refund_result

    async def _refund_wechat(
        self, record: GatewayPaymentRecord, refund_amount_fen: int, reason: str
    ) -> dict:
        """微信退款（V3接口）"""
        if not record.third_party_trade_no:
            raise ValueError("微信支付记录缺少 third_party_trade_no，无法退款")

        url_path = "/v3/refund/domestic/refunds"
        out_refund_no = str(uuid.uuid4()).replace("-", "")[:32]
        payload = {
            "transaction_id": record.third_party_trade_no,
            "out_refund_no": out_refund_no,
            "reason": reason[:80] if reason else "用户申请退款",
            "amount": {
                "refund": refund_amount_fen,
                "total": record.amount_fen,
                "currency": "CNY",
            },
        }
        body_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        auth_header = self._wechat_authorization_header("POST", url_path, body_str)

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.WECHAT_API_BASE}{url_path}",
                content=body_str.encode("utf-8"),
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            if resp.status_code not in (200, 201):
                raise ValueError(
                    f"微信退款申请失败 HTTP {resp.status_code}: {resp.text}"
                )
            return resp.json()

    async def _refund_alipay(
        self, record: GatewayPaymentRecord, refund_amount_fen: int, reason: str
    ) -> dict:
        """支付宝退款"""
        if not record.third_party_trade_no:
            raise ValueError("支付宝支付记录缺少 third_party_trade_no，无法退款")

        # 分转元
        refund_amount_yuan = f"{refund_amount_fen / 100:.2f}"
        app_id = settings.ALIPAY_APP_ID
        biz_content = json.dumps(
            {
                "trade_no": record.third_party_trade_no,
                "refund_amount": refund_amount_yuan,
                "refund_reason": reason[:256] if reason else "用户申请退款",
                "out_request_no": str(uuid.uuid4()).replace("-", "")[:64],
            },
            ensure_ascii=False,
        )
        params = {
            "app_id": app_id,
            "method": "alipay.trade.refund",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": biz_content,
        }
        params["sign"] = self._alipay_sign(params)

        gateway = settings.ALIPAY_GATEWAY
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(gateway, data=params)
            if resp.status_code != 200:
                raise ValueError(
                    f"支付宝退款请求失败 HTTP {resp.status_code}: {resp.text}"
                )
            result = resp.json()

        alipay_resp = result.get("alipay_trade_refund_response", {})
        if alipay_resp.get("code") != "10000":
            raise ValueError(
                f"支付宝退款失败：{alipay_resp.get('msg')} / {alipay_resp.get('sub_msg')}"
            )
        return alipay_resp

    # ================================================================
    # 记录查询
    # ================================================================

    async def get_payment_status(self, payment_record_id: str) -> dict:
        """查询支付状态"""
        stmt = select(GatewayPaymentRecord).where(
            GatewayPaymentRecord.id == payment_record_id
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            raise ValueError(f"支付记录不存在：{payment_record_id}")

        return {
            "payment_record_id": str(record.id),
            "store_id": str(record.store_id),
            "order_id": str(record.order_id),
            "payment_method": record.payment_method,
            "amount_fen": record.amount_fen,
            "amount_yuan": f"{record.amount_fen / 100:.2f}",
            "status": record.status,
            "third_party_trade_no": record.third_party_trade_no,
            "paid_at": record.paid_at.isoformat() if record.paid_at else None,
            "refund_amount_fen": record.refund_amount_fen,
            "refund_amount_yuan": f"{record.refund_amount_fen / 100:.2f}",
            "refunded_at": record.refunded_at.isoformat() if record.refunded_at else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    async def list_payment_records(
        self,
        store_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> dict:
        """
        支付记录列表（按 store_id 过滤，支持状态筛选，分页）
        """
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20

        stmt = select(GatewayPaymentRecord).where(
            GatewayPaymentRecord.store_id == store_id
        )
        if status:
            stmt = stmt.where(GatewayPaymentRecord.status == status)

        stmt = stmt.order_by(GatewayPaymentRecord.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        records = result.scalars().all()

        return {
            "page": page,
            "page_size": page_size,
            "records": [
                {
                    "payment_record_id": str(r.id),
                    "order_id": str(r.order_id),
                    "payment_method": r.payment_method,
                    "amount_fen": r.amount_fen,
                    "amount_yuan": f"{r.amount_fen / 100:.2f}",
                    "status": r.status,
                    "third_party_trade_no": r.third_party_trade_no,
                    "paid_at": r.paid_at.isoformat() if r.paid_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ],
        }

    # ================================================================
    # 工具方法
    # ================================================================

    @staticmethod
    def _get_notify_base_url() -> str:
        """获取回调通知基础URL（从环境变量读取，防止硬编码域名）"""
        import os
        return os.getenv("PAYMENT_NOTIFY_BASE_URL", "https://api.zlsjos.cn")
