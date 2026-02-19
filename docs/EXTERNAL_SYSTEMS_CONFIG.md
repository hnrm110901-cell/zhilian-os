# 外部系统配置指南
## External Systems Configuration Guide

本文档提供智链OS外部系统集成的完整配置指南。

---

## 一、配置概述

智链OS需要对接以下外部系统：

| 系统 | 用途 | 必需性 | 配置复杂度 |
|------|------|--------|-----------|
| 企业微信 | 消息推送、用户管理 | 可选 | ⭐⭐⭐ |
| 飞书 | 消息推送、用户管理 | 可选 | ⭐⭐⭐ |
| 奥琦韦 | 会员系统 | 可选 | ⭐⭐⭐⭐ |
| 品智 | POS收银系统 | 可选 | ⭐⭐⭐⭐ |
| 易订 | 预定排位系统 | 可选 | ⭐⭐⭐ |

---

## 二、企业微信配置

### 2.1 前置条件

- 已注册企业微信
- 有管理员权限
- 企业已认证（部分功能需要）

### 2.2 配置步骤

#### 步骤1: 创建自建应用

1. 登录企业微信管理后台: https://work.weixin.qq.com/
2. 进入「应用管理」→「应用」→「创建应用」
3. 填写应用信息:
   - 应用名称: 智链OS
   - 应用Logo: 上传Logo图片
   - 应用介绍: 餐饮智能管理系统
4. 点击「创建应用」

#### 步骤2: 获取配置信息

1. 在应用详情页获取:
   - **AgentId**: 应用的唯一标识
   - **Secret**: 应用密钥（点击「查看」获取）
2. 在「我的企业」页面获取:
   - **Corp ID**: 企业ID

#### 步骤3: 配置接收消息

1. 在应用详情页，点击「接收消息」→「设置API接收」
2. 填写配置:
   - **URL**: `https://your-domain.com/api/v1/enterprise/wechat/webhook`
   - **Token**: 随机字符串（自己生成）
   - **EncodingAESKey**: 点击「随机生成」
3. 保存配置

#### 步骤4: 设置可见范围

1. 在应用详情页，点击「可见范围」
2. 添加可使用该应用的部门或成员
3. 保存设置

#### 步骤5: 配置IP白名单

1. 在应用详情页，点击「企业可信IP」
2. 添加服务器公网IP地址
3. 保存设置

### 2.3 环境变量配置

在 `.env` 文件中添加:

```bash
# 企业微信配置
WECHAT_CORP_ID=ww1234567890abcdef          # 企业ID
WECHAT_CORP_SECRET=your_secret_here         # 应用Secret
WECHAT_AGENT_ID=1000001                     # 应用AgentId
```

### 2.4 验证配置

```bash
# 检查配置状态
curl -H "Authorization: Bearer <your_token>" \
  http://localhost:8000/api/v1/enterprise/wechat/status

# 发送测试消息
curl -X POST \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "测试消息",
    "touser": "@all",
    "message_type": "text"
  }' \
  http://localhost:8000/api/v1/enterprise/wechat/send-message
```

---

## 三、飞书配置

### 3.1 前置条件

- 已注册飞书企业
- 有管理员权限

### 3.2 配置步骤

#### 步骤1: 创建企业自建应用

1. 登录飞书开放平台: https://open.feishu.cn/
2. 点击「创建企业自建应用」
3. 填写应用信息:
   - 应用名称: 智链OS
   - 应用描述: 餐饮智能管理系统
   - 应用图标: 上传图标
4. 创建应用

#### 步骤2: 获取配置信息

1. 在应用详情页「凭证与基础信息」获取:
   - **App ID**: 应用ID
   - **App Secret**: 应用密钥

#### 步骤3: 开通权限

1. 在「权限管理」页面，开通以下权限:
   - 获取用户基本信息
   - 获取部门基础信息
   - 获取部门组织架构信息
   - 以应用身份发消息
   - 接收消息

#### 步骤4: 配置事件订阅

1. 在「事件订阅」页面，点击「添加事件订阅」
2. 填写配置:
   - **请求地址URL**: `https://your-domain.com/api/v1/enterprise/feishu/webhook`
   - **Encrypt Key**: 自动生成
   - **Verification Token**: 自动生成
3. 订阅事件:
   - 接收消息 (im.message.receive_v1)
4. 保存配置

#### 步骤5: 发布应用

1. 在「版本管理与发布」页面
2. 创建版本并提交审核
3. 审核通过后发布应用

### 3.3 环境变量配置

在 `.env` 文件中添加:

```bash
# 飞书配置
FEISHU_APP_ID=cli_a1234567890abcde          # 应用ID
FEISHU_APP_SECRET=your_secret_here          # 应用Secret
```

### 3.4 验证配置

```bash
# 检查配置状态
curl -H "Authorization: Bearer <your_token>" \
  http://localhost:8000/api/v1/enterprise/feishu/status

# 发送测试消息
curl -X POST \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "测试消息",
    "receive_id": "user_id_here",
    "message_type": "text"
  }' \
  http://localhost:8000/api/v1/enterprise/feishu/send-message
```

---

## 四、奥琦韦会员系统配置

### 4.1 前置条件

- 已购买奥琦韦微生活系统
- 获得API接入权限
- 有系统管理员账号

### 4.2 配置步骤

#### 步骤1: 申请API权限

1. 联系奥琦韦客服或销售
2. 申请API接入权限
3. 签署API使用协议

#### 步骤2: 获取API凭证

1. 登录奥琦韦管理后台
2. 进入「系统设置」→「API管理」
3. 创建API密钥
4. 获取以下信息:
   - **API Key**: API密钥
   - **API Base URL**: API基础地址
   - **商户ID**: 商户标识

#### 步骤3: 配置IP白名单

1. 在API管理页面
2. 添加服务器IP到白名单
3. 保存配置

#### 步骤4: 测试连接

1. 使用提供的测试工具
2. 验证API连接正常
3. 测试基本接口调用

### 4.3 环境变量配置

在 `.env` 文件中添加:

```bash
# 奥琦韦配置
AOQIWEI_API_KEY=your_api_key_here           # API密钥
AOQIWEI_BASE_URL=https://api.aoqiwei.com   # API基础URL
AOQIWEI_TIMEOUT=30                          # 超时时间（秒）
AOQIWEI_RETRY_TIMES=3                       # 重试次数
```

### 4.4 功能说明

奥琦韦适配器提供以下功能:

- ✅ 会员信息查询
- ✅ 会员注册
- ✅ 会员信息修改
- ✅ 交易预览（计算优惠）
- ✅ 交易提交
- ✅ 交易查询
- ✅ 交易撤销
- ✅ 储值充值
- ✅ 储值查询
- ✅ 优惠券查询
- ✅ 优惠券核销

### 4.5 验证配置

```bash
# 测试会员系统连接
curl -H "Authorization: Bearer <your_token>" \
  http://localhost:8000/api/v1/members/test-connection

# 查询会员信息
curl -H "Authorization: Bearer <your_token>" \
  "http://localhost:8000/api/v1/members/query?mobile=13800138000"
```

---

## 五、品智POS系统配置

### 5.1 前置条件

- 已购买品智收银系统
- 获得API接入权限
- 有系统管理员账号

### 5.2 配置步骤

#### 步骤1: 申请API权限

1. 联系品智客服或销售
2. 申请API接入权限
3. 签署API使用协议

#### 步骤2: 获取API凭证

1. 登录品智管理后台
2. 进入「系统管理」→「开放平台」
3. 创建应用
4. 获取以下信息:
   - **Token**: API令牌
   - **API Base URL**: API基础地址
   - **门店编码**: 门店标识

#### 步骤3: 配置权限

1. 在应用管理页面
2. 配置API权限范围:
   - 门店信息查询
   - 菜品信息查询
   - 订单查询
   - 营业数据查询
3. 保存配置

#### 步骤4: 测试连接

1. 使用API测试工具
2. 验证连接正常
3. 测试基本接口

### 5.3 环境变量配置

在 `.env` 文件中添加:

```bash
# 品智配置
PINZHI_TOKEN=your_token_here                # API Token
PINZHI_BASE_URL=https://api.pinzhi.com     # API基础URL
PINZHI_TIMEOUT=30                           # 超时时间（秒）
PINZHI_RETRY_TIMES=3                        # 重试次数
```

### 5.4 功能说明

品智适配器提供以下功能:

- ✅ 门店信息查询
- ✅ 菜品列表查询
- ✅ 菜品详情查询
- ✅ 订单查询
- ✅ 订单详情查询
- ✅ 营业数据查询
- ✅ 销售统计

### 5.5 验证配置

```bash
# 测试POS系统连接
curl -H "Authorization: Bearer <your_token>" \
  http://localhost:8000/api/v1/pos/test-connection

# 查询门店信息
curl -H "Authorization: Bearer <your_token>" \
  http://localhost:8000/api/v1/pos/stores
```

---

## 六、易订预定系统配置

### 6.1 前置条件

- 已购买易订预定系统
- 获得API接入权限

### 6.2 环境变量配置

在 `.env` 文件中添加:

```bash
# 易订配置
YIDING_API_KEY=your_api_key_here            # API密钥
YIDING_BASE_URL=https://api.yiding.com     # API基础URL
YIDING_TIMEOUT=30                           # 超时时间（秒）
```

---

## 七、完整配置示例

### 7.1 .env 文件完整示例

```bash
# ==================== 应用配置 ====================
APP_ENV=production
APP_DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=8000

# ==================== 数据库配置 ====================
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/zhilian_os
REDIS_URL=redis://localhost:6379/0

# ==================== 安全配置 ====================
SECRET_KEY=your-secret-key-here-change-in-production
JWT_SECRET=your-jwt-secret-here-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION=3600

# ==================== Celery配置 ====================
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ==================== AI/LLM配置 ====================
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo-preview
LLM_API_KEY=your-openai-api-key
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
LLM_ENABLED=true

# ==================== 企业微信配置 ====================
WECHAT_CORP_ID=ww1234567890abcdef
WECHAT_CORP_SECRET=your_wechat_secret_here
WECHAT_AGENT_ID=1000001

# ==================== 飞书配置 ====================
FEISHU_APP_ID=cli_a1234567890abcde
FEISHU_APP_SECRET=your_feishu_secret_here

# ==================== 奥琦韦配置 ====================
AOQIWEI_API_KEY=your_aoqiwei_api_key
AOQIWEI_BASE_URL=https://api.aoqiwei.com
AOQIWEI_TIMEOUT=30
AOQIWEI_RETRY_TIMES=3

# ==================== 品智配置 ====================
PINZHI_TOKEN=your_pinzhi_token
PINZHI_BASE_URL=https://api.pinzhi.com
PINZHI_TIMEOUT=30
PINZHI_RETRY_TIMES=3

# ==================== 易订配置 ====================
YIDING_API_KEY=your_yiding_api_key
YIDING_BASE_URL=https://api.yiding.com
YIDING_TIMEOUT=30

# ==================== 向量数据库配置 ====================
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# ==================== CORS配置 ====================
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","https://your-domain.com"]

# ==================== 日志配置 ====================
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 7.2 Docker Compose 环境变量

在 `docker-compose.prod.yml` 中配置:

```yaml
services:
  api-gateway:
    environment:
      # 从.env文件加载
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}

      # 企业微信
      - WECHAT_CORP_ID=${WECHAT_CORP_ID}
      - WECHAT_CORP_SECRET=${WECHAT_CORP_SECRET}
      - WECHAT_AGENT_ID=${WECHAT_AGENT_ID}

      # 飞书
      - FEISHU_APP_ID=${FEISHU_APP_ID}
      - FEISHU_APP_SECRET=${FEISHU_APP_SECRET}

      # 奥琦韦
      - AOQIWEI_API_KEY=${AOQIWEI_API_KEY}
      - AOQIWEI_BASE_URL=${AOQIWEI_BASE_URL}

      # 品智
      - PINZHI_TOKEN=${PINZHI_TOKEN}
      - PINZHI_BASE_URL=${PINZHI_BASE_URL}
```

---

## 八、配置验证

### 8.1 配置检查脚本

创建 `scripts/check_config.py`:

```python
#!/usr/bin/env python3
"""配置检查脚本"""
import os
from typing import Dict, List

def check_config() -> Dict[str, bool]:
    """检查所有配置项"""
    results = {}

    # 必需配置
    required = [
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "JWT_SECRET",
    ]

    # 可选配置
    optional = {
        "企业微信": ["WECHAT_CORP_ID", "WECHAT_CORP_SECRET", "WECHAT_AGENT_ID"],
        "飞书": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
        "奥琦韦": ["AOQIWEI_API_KEY", "AOQIWEI_BASE_URL"],
        "品智": ["PINZHI_TOKEN", "PINZHI_BASE_URL"],
    }

    print("=== 配置检查 ===\n")

    # 检查必需配置
    print("必需配置:")
    for key in required:
        value = os.getenv(key)
        status = "✅" if value else "❌"
        results[key] = bool(value)
        print(f"  {status} {key}")

    print()

    # 检查可选配置
    for system, keys in optional.items():
        print(f"{system}配置:")
        all_configured = True
        for key in keys:
            value = os.getenv(key)
            status = "✅" if value else "⚠️"
            results[key] = bool(value)
            all_configured = all_configured and bool(value)
            print(f"  {status} {key}")

        if all_configured:
            print(f"  ✅ {system}已完整配置")
        else:
            print(f"  ⚠️ {system}配置不完整（可选）")
        print()

    return results

if __name__ == "__main__":
    check_config()
```

### 8.2 API健康检查

```bash
# 检查所有外部系统状态
curl -H "Authorization: Bearer <your_token>" \
  http://localhost:8000/api/v1/health/external-systems
```

---

## 九、常见问题

### 9.1 企业微信

**Q: 消息发送失败，提示"invalid corpid"**
A: 检查WECHAT_CORP_ID是否正确，注意不要包含空格

**Q: 获取access_token失败**
A: 检查WECHAT_CORP_SECRET是否正确，确认IP在白名单中

**Q: 消息回调不生效**
A: 检查webhook URL是否可公网访问，确认Token和EncodingAESKey配置正确

### 9.2 飞书

**Q: 获取tenant_access_token失败**
A: 检查FEISHU_APP_ID和FEISHU_APP_SECRET是否正确

**Q: 发送消息失败，提示"no permission"**
A: 检查应用权限是否开通，确认应用已发布

**Q: 事件订阅验证失败**
A: 检查webhook URL返回的challenge值是否正确

### 9.3 奥琦韦

**Q: API调用失败，提示"invalid api key"**
A: 检查AOQIWEI_API_KEY是否正确，确认API权限已开通

**Q: 会员查询失败**
A: 检查会员卡号或手机号格式是否正确

### 9.4 品智

**Q: API调用失败，提示"invalid token"**
A: 检查PINZHI_TOKEN是否正确，确认token未过期

**Q: 门店信息查询为空**
A: 检查门店编码是否正确，确认门店已在系统中配置

---

## 十、安全建议

### 10.1 密钥管理

1. ✅ 使用环境变量存储敏感信息
2. ✅ 不要将密钥提交到代码仓库
3. ✅ 定期轮换API密钥
4. ✅ 使用密钥管理服务（如AWS Secrets Manager）

### 10.2 网络安全

1. ✅ 使用HTTPS加密传输
2. ✅ 配置IP白名单
3. ✅ 启用请求签名验证
4. ✅ 限制API调用频率

### 10.3 日志审计

1. ✅ 记录所有API调用
2. ✅ 监控异常请求
3. ✅ 定期审查日志
4. ✅ 设置告警规则

---

## 十一、技术支持

### 11.1 联系方式

- 技术支持邮箱: support@zhilian-os.com
- 技术文档: https://docs.zhilian-os.com
- GitHub Issues: https://github.com/zhilian-os/zhilian-os/issues

### 11.2 外部系统支持

- 企业微信: https://work.weixin.qq.com/api/doc
- 飞书: https://open.feishu.cn/document
- 奥琦韦: 联系客服获取API文档
- 品智: 联系客服获取API文档

---

**文档版本**: v1.0.0
**更新日期**: 2026年2月19日
