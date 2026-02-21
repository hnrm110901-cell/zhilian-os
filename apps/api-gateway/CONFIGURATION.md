# 环境配置指南

本文档详细说明智链OS API Gateway的所有环境变量配置。

## 配置文件

环境变量通过`.env`文件配置。复制示例文件开始配置:

```bash
cp .env.example .env
```

## 必需配置

以下配置项是系统运行的必需项，必须正确配置。

### 数据库配置

```bash
# PostgreSQL数据库连接URL
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/zhilian_os
```

**说明**:
- 使用asyncpg驱动的PostgreSQL连接字符串
- 格式: `postgresql+asyncpg://用户名:密码@主机:端口/数据库名`
- 示例: `postgresql+asyncpg://zhilian:zhilian@localhost:5432/zhilian_os`

### Redis配置

```bash
# Redis连接URL
REDIS_URL=redis://localhost:6379/0

# Celery消息队列
CELERY_BROKER_URL=redis://localhost:6379/1

# Celery结果存储
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

**说明**:
- 使用不同的Redis数据库编号(0, 1, 2)隔离不同用途
- 格式: `redis://主机:端口/数据库编号`
- 如需密码: `redis://:密码@主机:端口/数据库编号`

### 安全配置

```bash
# 应用密钥（用于加密）
SECRET_KEY=your-secret-key-here-change-in-production

# JWT密钥
JWT_SECRET=your-jwt-secret-key-here-change-in-production

# JWT算法
JWT_ALGORITHM=HS256

# JWT过期时间（秒）
JWT_EXPIRATION=3600
```

**安全建议**:
- 使用强随机字符串作为密钥
- 生产环境必须更改默认密钥
- 建议使用至少32字符的随机字符串
- 生成密钥: `openssl rand -hex 32`

---

## 应用配置

### 基础配置

```bash
# 运行环境: development, staging, production
APP_ENV=development

# 调试模式
APP_DEBUG=true

# 监听地址
APP_HOST=0.0.0.0

# 监听端口
APP_PORT=8000
```

### 日志配置

```bash
# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# 日志格式: json, text
LOG_FORMAT=json
```

### CORS配置

```bash
# 允许的跨域来源（逗号分隔）
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

---

## AI/LLM配置

系统支持多种LLM提供商，根据需要配置。

### 通用LLM配置

```bash
# LLM提供商: openai, anthropic, azure_openai, deepseek
LLM_PROVIDER=deepseek

# 模型名称
LLM_MODEL=deepseek-chat

# API密钥
LLM_API_KEY=your-api-key

# API基础URL
LLM_BASE_URL=https://api.deepseek.com

# 温度参数 (0.0-2.0)
LLM_TEMPERATURE=0.7

# 最大token数
LLM_MAX_TOKENS=2000

# 是否启用LLM
LLM_ENABLED=true
```

### OpenAI配置

```bash
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_API_BASE=https://api.openai.com/v1
MODEL_NAME=gpt-4-turbo-preview
```

### Anthropic配置

```bash
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key
```

---

## 企业集成配置

### 企业微信

```bash
# 企业ID
WECHAT_CORP_ID=your_corp_id

# 企业密钥
WECHAT_CORP_SECRET=your_corp_secret

# 应用AgentID
WECHAT_AGENT_ID=1000001

# 回调Token（用于签名验证）
WECHAT_TOKEN=your_callback_token

# 回调EncodingAESKey（用于消息加密）
WECHAT_ENCODING_AES_KEY=your_encoding_aes_key_43_chars
```

**获取方式**:
1. 登录企业微信管理后台
2. 进入"应用管理" -> 选择应用
3. 查看应用详情获取AgentID和Secret
4. 在"接收消息"设置中配置Token和EncodingAESKey

### 飞书

```bash
# 应用ID
FEISHU_APP_ID=cli_your_app_id

# 应用密钥
FEISHU_APP_SECRET=your_app_secret
```

### 钉钉

```bash
# 应用Key
DINGTALK_APP_KEY=your_app_key

# 应用密钥
DINGTALK_APP_SECRET=your_app_secret
```

### OAuth重定向

```bash
# OAuth登录后的重定向URI
OAUTH_REDIRECT_URI=http://localhost:5173/login
```

---

## 短信服务配置

### 阿里云短信

```bash
# AccessKey ID
ALIYUN_ACCESS_KEY_ID=your_access_key_id

# AccessKey Secret
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret

# 短信签名
ALIYUN_SMS_SIGN_NAME=智链OS

# 短信模板代码
ALIYUN_SMS_TEMPLATE_CODE=SMS_123456789
```

### 腾讯云短信

```bash
# SecretId
TENCENT_SECRET_ID=your_secret_id

# SecretKey
TENCENT_SECRET_KEY=your_secret_key

# 短信应用ID
TENCENT_SMS_APP_ID=1400123456

# 短信签名
TENCENT_SMS_SIGN_NAME=智链OS

# 短信模板ID
TENCENT_SMS_TEMPLATE_ID=123456
```

---

## 语音服务配置

### 百度语音

```bash
# 应用ID
BAIDU_APP_ID=your_app_id

# API Key
BAIDU_API_KEY=your_api_key

# Secret Key
BAIDU_SECRET_KEY=your_secret_key
```

### 讯飞语音

```bash
# 应用ID
XUNFEI_APP_ID=your_app_id

# API Key
XUNFEI_API_KEY=your_api_key

# API Secret
XUNFEI_API_SECRET=your_api_secret
```

---

## 向量数据库配置

```bash
# Qdrant服务地址
QDRANT_URL=http://localhost:6333

# Qdrant API密钥（可选）
QDRANT_API_KEY=

# 嵌入模型
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# 嵌入维度
EMBEDDING_DIMENSION=384

# 是否启用神经系统
NEURAL_SYSTEM_ENABLED=true
```

---

## 联邦学习配置

```bash
# 最小参与门店数
FL_MIN_STORES=3

# 聚合阈值
FL_AGGREGATION_THRESHOLD=0.8

# 学习率
FL_LEARNING_RATE=0.01
```

---

## 外部API配置

### 美团等位

```bash
# 开发者ID
MEITUAN_DEVELOPER_ID=your_developer_id

# 签名密钥
MEITUAN_SIGN_KEY=your_sign_key

# 业务ID（到店餐饮排队）
MEITUAN_BUSINESS_ID=49
```

### 奥琦韦

```bash
# API密钥
AOQIWEI_API_KEY=your_api_key

# API基础URL
AOQIWEI_BASE_URL=https://api.aoqiwei.com

# 超时时间（秒）
AOQIWEI_TIMEOUT=30

# 重试次数
AOQIWEI_RETRY_TIMES=3
```

### 品智

```bash
# Token
PINZHI_TOKEN=your_token

# API基础URL
PINZHI_BASE_URL=https://api.pinzhi.com

# 超时时间（秒）
PINZHI_TIMEOUT=30

# 重试次数
PINZHI_RETRY_TIMES=3
```

---

## 配置示例

### 开发环境

```bash
# .env.development
APP_ENV=development
APP_DEBUG=true
LOG_LEVEL=DEBUG

DATABASE_URL=postgresql+asyncpg://zhilian:zhilian@localhost:5432/zhilian_os_dev
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

SECRET_KEY=dev-secret-key-change-in-production
JWT_SECRET=dev-jwt-secret-change-in-production

LLM_PROVIDER=deepseek
LLM_API_KEY=your-deepseek-api-key
LLM_ENABLED=true

CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 生产环境

```bash
# .env.production
APP_ENV=production
APP_DEBUG=false
LOG_LEVEL=INFO

DATABASE_URL=postgresql+asyncpg://zhilian:strong_password@db.example.com:5432/zhilian_os
REDIS_URL=redis://:redis_password@redis.example.com:6379/0
CELERY_BROKER_URL=redis://:redis_password@redis.example.com:6379/1
CELERY_RESULT_BACKEND=redis://:redis_password@redis.example.com:6379/2

SECRET_KEY=production-secret-key-32-chars-minimum
JWT_SECRET=production-jwt-secret-32-chars-minimum

LLM_PROVIDER=openai
LLM_API_KEY=sk-your-production-openai-key
LLM_ENABLED=true

WECHAT_CORP_ID=your_production_corp_id
WECHAT_CORP_SECRET=your_production_secret
WECHAT_AGENT_ID=1000001
WECHAT_TOKEN=your_production_token
WECHAT_ENCODING_AES_KEY=your_production_aes_key

CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

---

## 配置验证

启动应用前验证配置:

```bash
# 检查必需的环境变量
python3 -c "from src.core.config import settings; print('配置加载成功')"

# 测试数据库连接
python3 -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from src.core.config import settings

async def test():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute('SELECT 1')
    print('数据库连接成功')

asyncio.run(test())
"

# 测试Redis连接
redis-cli -u $REDIS_URL ping
```

---

## 安全最佳实践

1. **密钥管理**
   - 使用环境变量或密钥管理服务
   - 不要将密钥提交到版本控制
   - 定期轮换密钥

2. **生产环境**
   - 禁用调试模式 (`APP_DEBUG=false`)
   - 使用强密码和密钥
   - 限制CORS来源
   - 使用HTTPS

3. **数据库**
   - 使用强密码
   - 限制网络访问
   - 定期备份

4. **Redis**
   - 设置密码
   - 限制网络访问
   - 使用不同的数据库编号隔离数据

---

## 故障排查

### 配置未加载

检查`.env`文件是否存在且格式正确:
```bash
cat .env | grep -v '^#' | grep -v '^$'
```

### 数据库连接失败

检查连接字符串格式和数据库服务状态:
```bash
psql $DATABASE_URL -c "SELECT 1"
```

### Redis连接失败

检查Redis服务和连接字符串:
```bash
redis-cli -u $REDIS_URL ping
```

### 企业微信配置错误

验证配置参数:
- CORP_ID: 企业ID，格式如 `ww1234567890abcdef`
- AGENT_ID: 应用ID，纯数字
- TOKEN: 回调Token，3-32字符
- ENCODING_AES_KEY: 回调密钥，固定43字符

---

## 参考资料

- [FastAPI配置文档](https://fastapi.tiangolo.com/advanced/settings/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [企业微信API文档](https://developer.work.weixin.qq.com/document/)
- [PostgreSQL连接字符串](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
- [Redis连接URL](https://redis.io/docs/connect/clients/python/)
