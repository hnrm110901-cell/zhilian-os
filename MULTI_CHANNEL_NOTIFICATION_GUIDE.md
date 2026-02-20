# 多渠道通知集成指南

## 概述

本文档详细说明如何配置和集成智链OS的多渠道通知系统,包括邮件、短信、微信、飞书等渠道。

## 配置管理

所有通知渠道的配置都通过环境变量管理,支持以下配置方式:

### 1. 环境变量文件 (.env)

在项目根目录创建 `.env` 文件:

```bash
# 邮件配置
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=noreply@example.com
EMAIL_SMTP_PASSWORD=your_password
EMAIL_SMTP_FROM_NAME=智链OS
EMAIL_SMTP_USE_TLS=true

# 短信配置 (阿里云)
SMS_PROVIDER=aliyun
SMS_ALIYUN_ACCESS_KEY_ID=your_access_key
SMS_ALIYUN_ACCESS_KEY_SECRET=your_secret
SMS_ALIYUN_SMS_SIGN_NAME=智链OS

# 微信配置 (企业微信)
WECHAT_TYPE=corp
WECHAT_CORP_ID=your_corp_id
WECHAT_CORP_SECRET=your_corp_secret
WECHAT_AGENT_ID=your_agent_id

# 飞书配置
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret

# 通知系统配置
NOTIFICATION_ENABLED_CHANNELS=email,sms,wechat,system
NOTIFICATION_MAX_RETRY_ATTEMPTS=3
NOTIFICATION_RETRY_DELAY_SECONDS=5
NOTIFICATION_ENABLE_FALLBACK=true
NOTIFICATION_FALLBACK_CHANNEL=email
```

### 2. Docker环境变量

在 `docker-compose.yml` 中配置:

```yaml
services:
  api-gateway:
    environment:
      - EMAIL_SMTP_HOST=smtp.gmail.com
      - EMAIL_SMTP_USER=noreply@example.com
      - EMAIL_SMTP_PASSWORD=${EMAIL_PASSWORD}
      - SMS_PROVIDER=aliyun
      - SMS_ALIYUN_ACCESS_KEY_ID=${ALIYUN_KEY}
      - WECHAT_CORP_ID=${WECHAT_CORP_ID}
```

## 邮件通知集成

### Gmail配置

1. 启用两步验证
2. 生成应用专用密码
3. 配置环境变量:

```bash
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=your-email@gmail.com
EMAIL_SMTP_PASSWORD=your-app-password
EMAIL_SMTP_USE_TLS=true
```

### 企业邮箱配置

#### 腾讯企业邮箱

```bash
EMAIL_SMTP_HOST=smtp.exmail.qq.com
EMAIL_SMTP_PORT=465
EMAIL_SMTP_USER=noreply@yourcompany.com
EMAIL_SMTP_PASSWORD=your_password
EMAIL_SMTP_USE_TLS=false
```

#### 阿里云企业邮箱

```bash
EMAIL_SMTP_HOST=smtp.mxhichina.com
EMAIL_SMTP_PORT=465
EMAIL_SMTP_USER=noreply@yourcompany.com
EMAIL_SMTP_PASSWORD=your_password
EMAIL_SMTP_USE_TLS=false
```

### 测试邮件发送

```python
from src.services.multi_channel_notification import multi_channel_notification_service, NotificationChannel

# 发送测试邮件
result = await multi_channel_notification_service.send_notification(
    channels=[NotificationChannel.EMAIL],
    recipient="test@example.com",
    title="测试邮件",
    content="这是一封测试邮件",
    extra_data={
        "html_content": "<h1>测试邮件</h1><p>这是一封测试邮件</p>"
    }
)

print(f"发送结果: {result}")
```

## 短信通知集成

### 阿里云短信

#### 1. 开通服务

1. 登录阿里云控制台
2. 开通短信服务
3. 创建签名和模板
4. 获取AccessKey

#### 2. 配置

```bash
SMS_PROVIDER=aliyun
SMS_ALIYUN_ACCESS_KEY_ID=LTAI5t...
SMS_ALIYUN_ACCESS_KEY_SECRET=xxx...
SMS_ALIYUN_SMS_SIGN_NAME=智链OS
SMS_ALIYUN_SMS_REGION=cn-hangzhou
```

#### 3. 安装SDK

```bash
pip install aliyun-python-sdk-core
pip install aliyun-python-sdk-dysmsapi
```

#### 4. 使用示例

```python
# 发送短信
result = await multi_channel_notification_service.send_notification(
    channels=[NotificationChannel.SMS],
    recipient="13800138000",
    title="验证码",
    content="您的验证码是1234",
    extra_data={
        "template_code": "SMS_123456",
        "template_params": {
            "code": "1234"
        }
    }
)
```

### 腾讯云短信

#### 1. 开通服务

1. 登录腾讯云控制台
2. 开通短信服务
3. 创建应用和模板
4. 获取SecretId和SecretKey

#### 2. 配置

```bash
SMS_PROVIDER=tencent
SMS_TENCENT_SECRET_ID=AKIDxxx...
SMS_TENCENT_SECRET_KEY=xxx...
SMS_TENCENT_SMS_APP_ID=1400xxx
SMS_TENCENT_SMS_SIGN=智链OS
```

#### 3. 安装SDK

```bash
pip install tencentcloud-sdk-python
```

## 微信通知集成

### 企业微信

#### 1. 创建企业微信应用

1. 登录企业微信管理后台
2. 应用管理 -> 创建应用
3. 获取AgentId和Secret
4. 记录CorpId

#### 2. 配置

```bash
WECHAT_TYPE=corp
WECHAT_CORP_ID=ww1234567890abcdef
WECHAT_CORP_SECRET=xxx...
WECHAT_AGENT_ID=1000002
```

#### 3. 安装依赖

```bash
pip install requests
```

#### 4. 使用示例

```python
# 发送企业微信消息
result = await multi_channel_notification_service.send_notification(
    channels=[NotificationChannel.WECHAT],
    recipient="zhangsan",  # 企业微信UserID
    title="库存预警",
    content="鸡肉库存不足,请及时补货"
)
```

### 微信公众号

#### 1. 创建公众号

1. 注册微信公众号
2. 获取AppID和AppSecret
3. 创建模板消息

#### 2. 配置

```bash
WECHAT_TYPE=official
WECHAT_APP_ID=wx1234567890abcdef
WECHAT_APP_SECRET=xxx...
```

#### 3. 使用示例

```python
# 发送模板消息
result = await multi_channel_notification_service.send_notification(
    channels=[NotificationChannel.WECHAT],
    recipient="oABC123xyz",  # 用户OpenID
    title="订单确认",
    content="您的订单已确认",
    extra_data={
        "template_id": "xxx",
        "url": "https://example.com/order/123"
    }
)
```

## 飞书通知集成

### 1. 创建飞书应用

1. 登录飞书开放平台
2. 创建企业自建应用
3. 获取App ID和App Secret
4. 添加权限: 发送消息

### 2. 配置

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx...
```

### 3. 安装SDK

```bash
pip install lark-oapi
```

### 4. 使用示例

```python
from src.services.feishu_service import feishu_service

# 发送飞书消息
await feishu_service.send_message(
    user_id="ou_xxx",
    message="订单已确认,请及时处理"
)
```

## 模板通知

### 使用预定义模板

```python
# 使用库存预警模板
result = await multi_channel_notification_service.send_template_notification(
    template_name="inventory_low",
    recipient="manager@example.com",
    item_name="鸡肉",
    current_stock=5
)
```

### 自定义模板

在 `multi_channel_notification.py` 中添加模板:

```python
TEMPLATES = {
    "custom_template": {
        "title": "自定义通知",
        "content": "这是自定义内容: {custom_field}",
        "channels": [NotificationChannel.EMAIL, NotificationChannel.SMS],
        "priority": "normal",
    }
}
```

## 重试和故障转移

### 重试机制

系统自动重试失败的通知发送:

```bash
# 配置重试次数和延迟
NOTIFICATION_MAX_RETRY_ATTEMPTS=3
NOTIFICATION_RETRY_DELAY_SECONDS=5
```

### 故障转移

当主渠道失败时,自动切换到备用渠道:

```bash
# 启用故障转移
NOTIFICATION_ENABLE_FALLBACK=true
# 备用渠道
NOTIFICATION_FALLBACK_CHANNEL=email
```

## 监控和日志

### 查看发送日志

```bash
# 查看通知发送日志
tail -f logs/notification.log | grep "通知发送"

# 查看失败日志
tail -f logs/notification.log | grep "发送失败"
```

### Prometheus监控

```promql
# 通知发送成功率
rate(notification_sent_total{status="success"}[5m]) /
rate(notification_sent_total[5m])

# 各渠道发送量
sum by (channel) (rate(notification_sent_total[5m]))

# 发送失败率
rate(notification_sent_total{status="failed"}[5m])
```

## 最佳实践

### 1. 渠道选择

- **紧急通知**: SMS + WeChat
- **重要通知**: Email + System
- **一般通知**: System
- **营销通知**: WeChat + Email

### 2. 内容优化

- 标题简洁明了 (< 50字符)
- 内容清晰具体 (< 200字符)
- 包含可操作信息
- 避免敏感信息

### 3. 频率控制

```python
# 限制发送频率
from datetime import datetime, timedelta

last_sent = {}

def can_send(user_id, notification_type):
    key = f"{user_id}:{notification_type}"
    if key in last_sent:
        if datetime.now() - last_sent[key] < timedelta(minutes=5):
            return False
    last_sent[key] = datetime.now()
    return True
```

### 4. 成本优化

- 优先使用免费渠道(System, Email)
- 短信用于重要通知
- 批量发送降低成本
- 定期清理过期通知

## 故障排查

### 邮件发送失败

**问题**: 邮件发送失败,提示认证错误

**解决方案**:
1. 检查SMTP用户名和密码
2. 确认是否启用了两步验证
3. 使用应用专用密码
4. 检查SMTP端口和TLS设置

### 短信发送失败

**问题**: 短信发送失败,提示签名不存在

**解决方案**:
1. 确认签名已审核通过
2. 检查签名名称是否正确
3. 确认模板已审核通过
4. 检查AccessKey权限

### 微信消息发送失败

**问题**: 企业微信消息发送失败

**解决方案**:
1. 确认CorpId和Secret正确
2. 检查AgentId是否正确
3. 确认用户在通讯录中
4. 检查应用可见范围

## 安全建议

### 1. 凭证管理

- 使用环境变量存储敏感信息
- 不要将凭证提交到代码仓库
- 定期轮换API密钥
- 使用密钥管理服务(如AWS Secrets Manager)

### 2. 访问控制

- 限制通知发送权限
- 记录所有发送操作
- 实施速率限制
- 监控异常发送行为

### 3. 数据保护

- 加密存储通知内容
- 定期清理历史通知
- 脱敏敏感信息
- 遵守数据保护法规

## 更新日志

### v1.0.0 (2026-02-20)
- ✅ 实现邮件通知(SMTP)
- ✅ 实现短信通知(阿里云/腾讯云)
- ✅ 实现微信通知(企业微信/公众号)
- ✅ 实现飞书通知
- ✅ 添加重试机制
- ✅ 添加故障转移
- ✅ 添加配置管理
- ✅ 完成集成文档

## 技术支持

如有问题,请联系:
- 技术支持邮箱: support@zhilian-os.com
- GitHub Issues: https://github.com/zhilian-os/issues
