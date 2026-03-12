# 企业集成支持矩阵

更新日期：2026-03-12

本文档以 `apps/api-gateway/src/api/enterprise.py` 的当前实现为准，描述企业微信、飞书、钉钉在智链OS中的真实支持状态。

## 总览

| 平台 | OAuth登录 | 发送消息 | 用户查询 | Webhook校验 | Agent文本回复 | 生产级Webhook |
|------|-----------|----------|----------|-------------|---------------|----------------|
| 企业微信 | 已支持 | 已支持 | 已支持 | 已支持 | 已支持 | 条件支持 |
| 飞书 | 已支持 | 已支持 | 已支持 | 已支持 | 已支持 | 条件支持 |
| 钉钉 | 已支持 | 未支持 | 未支持 | 未支持 | 未支持 | 未支持 |

## 企业微信

已支持：
- OAuth 回调登录
- 文本、Markdown、卡片消息发送
- 用户列表、用户详情、配置状态查询
- Webhook URL 验证
- 消息签名校验与消息解密
- 文本消息触发私域 Agent 回复

生产条件：
- `WECHAT_CORP_ID`
- `WECHAT_CORP_SECRET`
- `WECHAT_AGENT_ID`
- `WECHAT_TOKEN`
- `WECHAT_ENCODING_AES_KEY`

说明：
- 如果未配置 `WECHAT_TOKEN` 或 `WECHAT_ENCODING_AES_KEY`，发送能力仍可用，但 webhook 不具备生产级安全校验。

## 飞书

已支持：
- OAuth 回调登录
- 文本、Post、Interactive 消息发送
- 用户列表、用户详情、配置状态查询
- Webhook URL 验证
- Token 校验
- 签名校验
- 事件类型白名单
- `event_id` 幂等去重
- 文本消息触发 Agent 回复

生产条件：
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_VERIFICATION_TOKEN`
- `FEISHU_ENCRYPT_KEY`

Webhook 说明：
- 当前允许的事件类型：
  - `url_verification`
  - `im.message.receive_v1`
- 若只配置 `FEISHU_VERIFICATION_TOKEN`，可做基础来源校验
- 若同时配置 `FEISHU_ENCRYPT_KEY`，可启用签名校验

## 钉钉

当前仅支持：
- OAuth 回调登录

未支持：
- 消息发送
- 用户查询
- Webhook 接入

## API 对应关系

关键接口：
- `GET /api/v1/enterprise/support-matrix`
- `GET /api/v1/enterprise/wechat/status`
- `GET /api/v1/enterprise/feishu/status`
- `POST /api/v1/enterprise/wechat/webhook`
- `POST /api/v1/enterprise/feishu/webhook`

说明：
- 建议前端和运维后台优先读取 `support-matrix`，不要手写平台支持状态。
