## Payment Gateway 路由注册

在 main.py 中添加（按顺序）：

```python
from src.api.payment_gateway import router as payment_gateway_router
app.include_router(payment_gateway_router)
```

回调端点 `/api/v1/payments/wechat/callback` 和 `/api/v1/payments/alipay/callback`
需要排除在 JWT 认证中间件之外（如果有统一认证中间件）。

### 新增环境变量（需在 .env 中补充）

```env
# 微信支付V3
WECHAT_PAY_MCH_ID=           # 商户号
WECHAT_PAY_API_V3_KEY=       # APIv3密钥（32字节ASCII）
WECHAT_PAY_CERT_SERIAL_NO=   # 商户证书序列号
WECHAT_PAY_APP_ID=           # 公众号/小程序 AppID
WECHAT_PAY_PRIVATE_KEY=      # 商户私钥（RSA PEM，可不含header/footer）

# 支付宝
ALIPAY_APP_ID=               # 应用ID
ALIPAY_PRIVATE_KEY=          # 应用私钥（RSA2 PEM）
ALIPAY_PUBLIC_KEY=           # 支付宝公钥（验签）
ALIPAY_GATEWAY=https://openapi.alipay.com/gateway.do

# 回调地址基础URL（微信/支付宝回调的域名前缀）
PAYMENT_NOTIFY_BASE_URL=https://api.zlsjos.cn
```

### 数据库迁移

```bash
cd apps/api-gateway
alembic upgrade z70
```

迁移将创建 `gateway_payment_records` 表（含 RLS 隔离策略）。

注意：`payment_records` 表已由 `payment_reconciliation.py`（对账流水场景）占用，
本次支付网关使用独立的 `gateway_payment_records` 表，两者不冲突。
