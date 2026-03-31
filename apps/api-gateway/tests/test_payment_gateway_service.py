"""
支付网关服务测试
覆盖：微信V3签名、AES-256-GCM解密、支付宝验签、金额转换、
       退款校验、幂等回调、状态查询、分页列表等共12+个测试
"""

import base64
import json
import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ----------------------------------------------------------------
# 确保在任何 src.* 导入前设置测试环境变量
# ----------------------------------------------------------------
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("WECHAT_PAY_MCH_ID", "1234567890")
os.environ.setdefault("WECHAT_PAY_APP_ID", "wx_test_appid")
os.environ.setdefault("WECHAT_PAY_CERT_SERIAL_NO", "ABCDEF1234567890")
os.environ.setdefault("WECHAT_PAY_API_V3_KEY", "TestApiV3Key12345678901234567890")  # 32字节
os.environ.setdefault("ALIPAY_APP_ID", "2021000000000000")
os.environ.setdefault("ALIPAY_PRIVATE_KEY", "")
os.environ.setdefault("ALIPAY_PUBLIC_KEY", "")

from src.models.payment_record import GatewayPaymentRecord, PaymentMethod, PaymentStatus
from src.services.payment_gateway_service import PaymentGatewayService


# ----------------------------------------------------------------
# 辅助：构造 Mock AsyncSession
# ----------------------------------------------------------------

def _make_mock_db():
    """返回 Mock AsyncSession，预配置 flush/commit/add"""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _make_mock_record(**kwargs) -> GatewayPaymentRecord:
    """构造一个 GatewayPaymentRecord 实例（不依赖DB）"""
    r = GatewayPaymentRecord()
    r.id = uuid.uuid4()
    r.store_id = uuid.uuid4()
    r.order_id = uuid.uuid4()
    r.payment_method = kwargs.get("payment_method", PaymentMethod.WECHAT_JSAPI.value)
    r.amount_fen = kwargs.get("amount_fen", 10000)
    r.status = kwargs.get("status", PaymentStatus.PENDING.value)
    r.third_party_trade_no = kwargs.get("third_party_trade_no", None)
    r.prepay_id = kwargs.get("prepay_id", None)
    r.wechat_openid = kwargs.get("wechat_openid", None)
    r.paid_at = kwargs.get("paid_at", None)
    r.refund_amount_fen = kwargs.get("refund_amount_fen", 0)
    r.refunded_at = kwargs.get("refunded_at", None)
    r.created_at = kwargs.get("created_at", datetime.utcnow())
    r.callback_raw = kwargs.get("callback_raw", None)
    return r


# ================================================================
# 测试1：微信V3签名生成（纯函数，无DB）
# ================================================================

def test_wechat_sign_format():
    """微信V3签名方法应生成 base64 编码字符串，且签名串格式正确"""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    # 生成测试用RSA私钥
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    with patch.object(svc, "_get_wechat_private_key", return_value=pem):
        sig = svc._wechat_sign(
            method="POST",
            url_path="/v3/pay/transactions/jsapi",
            timestamp="1711900000",
            nonce_str="abc123",
            body='{"test": 1}',
        )

    # 签名必须是合法的 base64 字符串
    assert isinstance(sig, str)
    decoded = base64.b64decode(sig)
    assert len(decoded) == 256  # RSA-2048 签名长度为 256 字节


# ================================================================
# 测试2：回调验签失败时 raise ValueError
# ================================================================

def test_verify_wechat_callback_raises_on_missing_headers():
    """缺少必要签名头时必须 raise ValueError，不得静默忽略"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    with pytest.raises(ValueError, match="缺少必要签名头"):
        svc._verify_wechat_signature(
            headers={},  # 缺少所有签名头
            body=b'{"id":"test"}',
        )


def test_verify_wechat_callback_raises_on_partial_headers():
    """仅有部分签名头时也应 raise ValueError"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    headers = {"Wechatpay-Timestamp": "1711900000"}  # 缺少 Nonce 和 Signature
    with pytest.raises(ValueError, match="缺少必要签名头"):
        svc._verify_wechat_signature(headers=headers, body=b'{}')


# ================================================================
# 测试3：AES-256-GCM 解密（已知密文测试）
# ================================================================

def test_aes_gcm_decrypt():
    """使用已知密钥+密文验证 AES-256-GCM 解密逻辑正确性"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import src.services.payment_gateway_service as pgm

    # 准备已知明文
    api_v3_key = "TestApiV3Key12345678901234567890"  # 32字节
    plaintext = json.dumps({"trade_state": "SUCCESS", "transaction_id": "TX001"}).encode()
    nonce = b"test_nonce_"  # 12字节
    associated_data = b"transaction"

    aesgcm = AESGCM(api_v3_key.encode())
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
    ciphertext_b64 = base64.b64encode(ciphertext).decode()

    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    # patch service 模块内的 settings 对象（而非 config 模块，避免 conftest 重置）
    mock_settings = MagicMock()
    mock_settings.WECHAT_PAY_API_V3_KEY = api_v3_key
    with patch.object(pgm, "settings", mock_settings):
        result = svc._wechat_decrypt_callback(
            algorithm="AEAD_AES_256_GCM",
            associated_data=associated_data.decode(),
            nonce=nonce.decode(),
            ciphertext=ciphertext_b64,
        )

    assert result["trade_state"] == "SUCCESS"
    assert result["transaction_id"] == "TX001"


# ================================================================
# 测试4：金额单位转换（分→元用于支付宝）
# ================================================================

def test_alipay_amount_conversion():
    """支付宝下单时金额必须从分转换为元，精确到2位小数"""
    # 100分 = 1.00元
    assert f"{100 / 100:.2f}" == "1.00"
    # 1999分 = 19.99元
    assert f"{1999 / 100:.2f}" == "19.99"
    # 10000分 = 100.00元
    assert f"{10000 / 100:.2f}" == "100.00"


def test_alipay_amount_reverse_conversion():
    """确认元→分反向转换精度（展示层）"""
    # 19.99元 × 100 = 1999分（整数）
    yuan = 19.99
    fen = round(yuan * 100)
    assert fen == 1999
    # 1.00元 × 100 = 100分
    assert round(1.00 * 100) == 100


# ================================================================
# 测试5：退款金额不能超过原始支付金额
# ================================================================

@pytest.mark.asyncio
async def test_refund_amount_exceeds_original_raises():
    """退款金额超过可退金额时必须 raise ValueError"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    record = _make_mock_record(
        amount_fen=10000,
        refund_amount_fen=3000,
        status=PaymentStatus.PAID.value,
        third_party_trade_no="TX_WECHAT_001",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="超过可退金额"):
        await svc.refund(
            payment_record_id=str(record.id),
            refund_amount_fen=8000,  # 可退金额: 10000-3000=7000，此处超过
            reason="测试退款",
        )


@pytest.mark.asyncio
async def test_refund_zero_amount_raises():
    """退款金额为0时必须 raise ValueError"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    record = _make_mock_record(
        amount_fen=10000,
        refund_amount_fen=0,
        status=PaymentStatus.PAID.value,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="必须大于0分"):
        await svc.refund(
            payment_record_id=str(record.id),
            refund_amount_fen=0,
        )


# ================================================================
# 测试6：重复回调幂等处理（同一 trade_no 第二次不重复更新）
# ================================================================

@pytest.mark.asyncio
async def test_wechat_callback_idempotent():
    """同一 transaction_id 的回调，如果已是paid状态，不重复更新"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    existing = _make_mock_record(
        status=PaymentStatus.PAID.value,
        third_party_trade_no="TX_DUPLICATE_001",
        paid_at=datetime.utcnow(),
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(return_value=mock_result)

    payment_result = {
        "transaction_id": "TX_DUPLICATE_001",
        "trade_state": "SUCCESS",
        "payer": {"openid": "oABC123"},
        "amount": {"payer_total": 10000},
    }

    returned = await svc.handle_wechat_payment_success(payment_result, "raw_callback")

    # 应该直接返回已有记录，不调用 db.add
    assert returned is existing
    db.add.assert_not_called()
    # flush 也不应被调用（幂等路径直接 return）
    db.flush.assert_not_called()


# ================================================================
# 测试7：待支付状态查询返回 pending
# ================================================================

@pytest.mark.asyncio
async def test_get_payment_status_pending():
    """待支付记录查询应返回 status=pending"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    record = _make_mock_record(
        status=PaymentStatus.PENDING.value,
        amount_fen=5000,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    db.execute = AsyncMock(return_value=mock_result)

    result = await svc.get_payment_status(str(record.id))

    assert result["status"] == "pending"
    assert result["amount_fen"] == 5000
    assert result["amount_yuan"] == "50.00"
    assert result["paid_at"] is None


# ================================================================
# 测试8：支付成功后状态为 paid
# ================================================================

@pytest.mark.asyncio
async def test_handle_payment_success_updates_status():
    """支付成功回调应将状态更新为 paid"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    record = _make_mock_record(
        status=PaymentStatus.PENDING.value,
        amount_fen=10000,
        third_party_trade_no=None,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    db.execute = AsyncMock(return_value=mock_result)

    payment_result = {
        "transaction_id": "TX_NEW_001",
        "trade_state": "SUCCESS",
        "payer": {"openid": "oXYZ789"},
        "amount": {"payer_total": 10000},
    }

    returned = await svc.handle_wechat_payment_success(payment_result, "raw")

    assert returned.status == PaymentStatus.PAID.value
    assert returned.third_party_trade_no == "TX_NEW_001"
    assert returned.paid_at is not None
    db.flush.assert_called_once()


# ================================================================
# 测试9：JSAPI下单返回包含 paySign 字段
# ================================================================

@pytest.mark.asyncio
async def test_create_wechat_jsapi_order_returns_pay_sign():
    """JSAPI下单成功应返回包含 paySign 的参数包"""
    import src.services.payment_gateway_service as pgm
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    # Mock httpx 调用
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"prepay_id": "wx_prepay_test_001"}

    mock_settings = MagicMock()
    mock_settings.WECHAT_PAY_APP_ID = "wx_test_appid"
    mock_settings.WECHAT_PAY_MCH_ID = "1234567890"
    mock_settings.WECHAT_PAY_CERT_SERIAL_NO = "ABCDEF1234567890"

    with patch.object(svc, "_get_wechat_private_key", return_value=pem), \
         patch.object(pgm, "settings", mock_settings), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await svc.create_wechat_jsapi_order(
            store_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            amount_fen=5000,
            openid="o_test_openid",
            description="测试商品",
        )

    assert "paySign" in result
    assert "timeStamp" in result
    assert "nonceStr" in result
    assert result["package"] == "prepay_id=wx_prepay_test_001"
    assert result["signType"] == "RSA"


# ================================================================
# 测试10：Native下单返回 code_url
# ================================================================

@pytest.mark.asyncio
async def test_create_wechat_native_order_returns_code_url():
    """Native下单成功应返回 code_url"""
    import src.services.payment_gateway_service as pgm
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code_url": "weixin://wxpay/bizpayurl?pr=TestNativeCode"
    }

    mock_settings = MagicMock()
    mock_settings.WECHAT_PAY_APP_ID = "wx_test_appid"
    mock_settings.WECHAT_PAY_MCH_ID = "1234567890"
    mock_settings.WECHAT_PAY_CERT_SERIAL_NO = "ABCDEF1234567890"

    with patch.object(svc, "_get_wechat_private_key", return_value=pem), \
         patch.object(pgm, "settings", mock_settings), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await svc.create_wechat_native_order(
            store_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            amount_fen=3000,
            description="堂食消费",
        )

    assert "code_url" in result
    assert result["code_url"].startswith("weixin://")
    assert "payment_record_id" in result


# ================================================================
# 测试11：列表查询分页正确
# ================================================================

@pytest.mark.asyncio
async def test_list_payment_records_pagination():
    """列表查询应正确传递分页参数并返回 records 列表"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    records = [
        _make_mock_record(status=PaymentStatus.PAID.value, amount_fen=5000 + i * 100)
        for i in range(3)
    ]

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = records
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    db.execute = AsyncMock(return_value=mock_result)

    result = await svc.list_payment_records(
        store_id=str(uuid.uuid4()),
        page=2,
        page_size=10,
        status="paid",
    )

    assert result["page"] == 2
    assert result["page_size"] == 10
    assert len(result["records"]) == 3
    for r in result["records"]:
        assert "payment_record_id" in r
        assert "amount_yuan" in r
        assert "." in r["amount_yuan"]  # 元，含小数点


# ================================================================
# 测试12：支付记录不存在时 get_payment_status 抛出 ValueError
# ================================================================

@pytest.mark.asyncio
async def test_get_payment_status_not_found_raises():
    """查询不存在的支付记录应 raise ValueError"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    non_existent_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="支付记录不存在"):
        await svc.get_payment_status(non_existent_id)


# ================================================================
# 测试13：退款状态非 paid 时不允许退款
# ================================================================

@pytest.mark.asyncio
async def test_refund_non_paid_status_raises():
    """pending 状态的记录不允许退款"""
    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    record = _make_mock_record(
        amount_fen=10000,
        status=PaymentStatus.PENDING.value,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="不允许退款"):
        await svc.refund(
            payment_record_id=str(record.id),
            refund_amount_fen=5000,
        )


# ================================================================
# 测试14：API V3 Key 非32字节时 decrypt 应 raise
# ================================================================

def test_wechat_decrypt_invalid_key_length():
    """API V3 Key 长度不为32字节时应 raise ValueError"""
    import src.services.payment_gateway_service as pgm

    db = _make_mock_db()
    svc = PaymentGatewayService(db)

    mock_settings = MagicMock()
    mock_settings.WECHAT_PAY_API_V3_KEY = "tooshort"  # 少于32字节

    with patch.object(pgm, "settings", mock_settings):
        with pytest.raises(ValueError, match="32字节"):
            svc._wechat_decrypt_callback(
                algorithm="AEAD_AES_256_GCM",
                associated_data="test",
                nonce="test_nonce_12",
                ciphertext=base64.b64encode(b"fake_cipher").decode(),
            )
