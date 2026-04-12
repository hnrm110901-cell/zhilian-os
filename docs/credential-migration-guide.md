# 屯象OS 商户凭证迁移指南

> 创建日期: 2026-03-27
> 背景: 商户 API 凭证以明文形式存储在 config/merchants/.env.* 文件中，需要迁移到安全的密钥管理方案。

---

## 1. 需要轮换的凭证清单

以下是从各商户 .env 文件和脚本中提取的所有敏感 KEY（不含实际值）：

### 尝在一起（.env.czyz）

| KEY 名称 | 用途 |
|----------|------|
| `CZYZ_PINZHI_BASE_URL` | 品智 POS API 基础地址 |
| `CZYZ_PINZHI_API_TOKEN` | 品智 POS API 认证令牌 |
| `CZYZ_AOQIWEI_BASE_URL` | 奥琦玮 API 基础地址 |
| `CZYZ_AOQIWEI_APP_ID` | 奥琦玮应用 ID |
| `CZYZ_AOQIWEI_APP_KEY` | 奥琦玮应用密钥 |
| `CZYZ_AOQIWEI_MERCHANT_ID` | 奥琦玮商户 ID |

### 最黔线（.env.zqx）

| KEY 名称 | 用途 |
|----------|------|
| `ZQX_PINZHI_BASE_URL` | 品智 POS API 基础地址 |
| `ZQX_PINZHI_API_TOKEN` | 品智 POS API 认证令牌 |
| `ZQX_AOQIWEI_BASE_URL` | 奥琦玮 API 基础地址 |
| `ZQX_AOQIWEI_APP_ID` | 奥琦玮应用 ID |
| `ZQX_AOQIWEI_APP_KEY` | 奥琦玮应用密钥 |
| `ZQX_AOQIWEI_MERCHANT_ID` | 奥琦玮商户 ID |

### 尚宫厨（.env.sgc）

| KEY 名称 | 用途 |
|----------|------|
| `SGC_PINZHI_BASE_URL` | 品智 POS API 基础地址 |
| `SGC_PINZHI_API_TOKEN` | 品智 POS API 认证令牌 |
| `SGC_AOQIWEI_BASE_URL` | 奥琦玮 API 基础地址 |
| `SGC_AOQIWEI_APP_ID` | 奥琦玮应用 ID |
| `SGC_AOQIWEI_APP_KEY` | 奥琦玮应用密钥 |
| `SGC_AOQIWEI_MERCHANT_ID` | 奥琦玮商户 ID |
| `SGC_COUPON_BASE_URL` | 优惠券网关基础地址 |
| `SGC_COUPON_APP_ID` | 优惠券应用 ID |
| `SGC_COUPON_APP_KEY` | 优惠券应用密钥 |
| `SGC_COUPON_PLATFORMS` | 优惠券平台列表（非敏感，但建议一同迁移） |

### 脚本硬编码（已修复）

| 来源 | KEY 名称 | 说明 |
|------|----------|------|
| `scripts/probe_pinzhi_v2.py` | `PINZHI_PROBE_TOKEN` | 已改为环境变量读取，旧 TOKEN 需轮换 |

---

## 2. 迁移到腾讯云密钥管理的步骤

### 方案 A：腾讯云密钥管理服务（SSM）

```bash
# 步骤 1：在腾讯云控制台创建密钥
# 路径：腾讯云控制台 → 凭据管理服务（SSM）→ 创建凭据

# 步骤 2：为每个商户创建一个凭据，命名规范：
#   tunxiang/merchant/{merchant_code}/{key_name}
#   例如：tunxiang/merchant/czyz/PINZHI_API_TOKEN

# 步骤 3：安装腾讯云 SDK
pip install tencentcloud-sdk-python

# 步骤 4：在应用启动时从 SSM 拉取凭证（伪代码）
# from tencentcloud.ssm.v20190923 import ssm_client
# secret = client.GetSecretValue("tunxiang/merchant/czyz/PINZHI_API_TOKEN")
```

### 方案 B：服务器环境变量（过渡方案）

```bash
# 步骤 1：将凭证写入服务器的 /etc/environment 或 systemd service 文件
# 步骤 2：确保文件权限为 600，仅 root 和应用用户可读
# 步骤 3：应用通过 os.getenv() 读取
```

### 方案 C：Docker Secrets（如使用 Docker Swarm/Compose）

```bash
# 步骤 1：创建 docker secret
echo "实际TOKEN值" | docker secret create czyz_pinzhi_token -

# 步骤 2：在 docker-compose.yml 中引用
# services:
#   api-gateway:
#     secrets:
#       - czyz_pinzhi_token

# 步骤 3：应用从 /run/secrets/czyz_pinzhi_token 读取
```

---

## 3. 本地开发环境变量配置

### 3.1 创建本地 .env 文件（不提交到 Git）

```bash
# 在项目根目录创建 .env.local（已被 .gitignore 忽略）
cp config/merchants/.env.czyz.example .env.local

# 填入开发环境的凭证（向项目负责人获取）
```

### 3.2 推荐使用 direnv 管理环境变量

```bash
# 安装 direnv
brew install direnv

# 在项目根目录创建 .envrc
# 内容示例：
# export CZYZ_PINZHI_API_TOKEN="开发环境TOKEN"
# export CZYZ_AOQIWEI_APP_KEY="开发环境KEY"
# export PINZHI_PROBE_TOKEN="开发环境探测TOKEN"

# 启用
direnv allow
```

### 3.3 环境变量命名规范

所有商户凭证环境变量遵循以下命名规则：
```
{商户代码}_{系统}_{字段}
```

例如：
- `CZYZ_PINZHI_API_TOKEN` — 尝在一起的品智 API Token
- `SGC_AOQIWEI_APP_KEY` — 尚宫厨的奥琦玮 App Key
- `PINZHI_PROBE_TOKEN` — 品智 API 探测脚本专用 Token

---

## 4. 清除 Git 历史中的凭证（需要手动执行）

> **警告**: 以下操作会重写 Git 历史，属于破坏性操作。
> 执行前必须：
> 1. 确认所有团队成员已推送本地变更
> 2. 备份当前仓库
> 3. 通知所有协作者重新 clone 仓库

### 4.1 安装 git-filter-repo

```bash
# 需要手动执行
brew install git-filter-repo
```

### 4.2 清除包含凭证的文件历史

```bash
# 需要手动执行 — 清除商户 .env 文件的所有历史记录
git filter-repo --path config/merchants/.env.czyz --invert-paths
git filter-repo --path config/merchants/.env.zqx --invert-paths
git filter-repo --path config/merchants/.env.sgc --invert-paths
```

### 4.3 清除 probe 脚本旧版本中的硬编码 TOKEN

```bash
# 需要手动执行 — 使用 blob 回调替换历史中的 TOKEN
git filter-repo --blob-callback '
import re
data = blob.data
# 替换所有32位十六进制字符串（可能是 TOKEN/KEY）
data = re.sub(rb"[a-f0-9]{32}", b"REDACTED_CREDENTIAL", data)
blob.data = data
'
```

### 4.4 强制推送清理后的历史

```bash
# 需要手动执行 — 确认无误后推送
git push origin --force --all
git push origin --force --tags
```

### 4.5 通知所有协作者

清理完成后，所有协作者需要：
```bash
# 删除旧的本地仓库
rm -rf tunxiang

# 重新 clone
git clone <仓库地址>
```

---

## 5. 凭证轮换检查清单

完成迁移后，逐项确认：

- [ ] 所有 .env 文件中的 TOKEN/KEY 已在对应平台（品智、奥琦玮）重新生成
- [ ] 新凭证已存储到腾讯云 SSM / 服务器环境变量
- [ ] 应用代码已改为从环境变量/SSM 读取凭证
- [ ] `scripts/probe_pinzhi_v2.py` 已使用 `PINZHI_PROBE_TOKEN` 环境变量
- [ ] `scripts/setup-git-secrets.sh` 已执行，pre-commit 钩子已生效
- [ ] Git 历史已清理（git-filter-repo）
- [ ] 旧凭证已在各平台吊销/失效
- [ ] 所有协作者已重新 clone 仓库

---

*本文档由屯象OS安全加固流程生成，请在执行每一步前仔细确认。*
