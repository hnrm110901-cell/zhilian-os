# 私域运营 Agent 企业微信应用规划及兼容智链OS 整体系统

## 一、目标与范围

将**私域运营 Agent** 作为企业微信（企微）上的**可对话应用**落地，使门店/运营人员在企业微信内通过自然语言获取用户画像、实时指标、推荐建议、排班与库存建议等能力；同时与智链OS 现有企微能力（OAuth 登录、事件推送、管理后台）统一兼容，保证整体系统一致运行。

| 维度 | 说明 |
|------|------|
| **应用形态** | 企微「自建应用」或「客服/会话」型应用，支持接收用户消息并回复 |
| **核心交互** | 用户发文本 → 回调接收 → 私域 Agent（如 nl_query）→ 企微 API 回发文本/卡片 |
| **兼容范围** | api-gateway 统一入口、现有 WeChat 配置与回调、OAuth 用户、触发规则、管理后台（PrivateDomainPage） |

---

## 二、智链OS 现有企业微信能力梳理

### 2.1 已有组件

| 组件 | 位置 | 作用 |
|------|------|------|
| **WeChatService** | api-gateway/src/services/wechat_service.py | 获取 token、发送文本/Markdown/卡片消息、部门用户 |
| **WeChatWorkMessageService** | wechat_work_message_service.py | 带 Redis 缓存的 token、按 user_id 发文本 |
| **WeChatTriggerService** | wechat_trigger_service.py | 事件驱动推送（订单/预订/会员/支付/库存等），规则配置 + Celery 任务 |
| **WeChatCrypto** | utils/wechat_crypto.py | 回调 URL 校验、消息加解密、XML 解析 |
| **企微回调** | api/enterprise.py：GET/POST `/wechat/webhook` | URL 校验(GET)、接收消息(POST)、解密后仅打日志并返回 success，**未对接 Agent** |
| **企微 OAuth** | api/auth.py：`/oauth/wechat-work/callback` | 员工登录、创建/绑定 User、角色映射 |
| **配置项** | core/config.py | WECHAT_CORP_ID、WECHAT_CORP_SECRET、WECHAT_AGENT_ID、WECHAT_TOKEN、WECHAT_ENCODING_AES_KEY |

### 2.2 私域运营侧已有能力

- **API**：`/api/v1/private-domain/*`（看板、RFM、信号、旅程、流失风险、**POST /execute**、GET /actions）
- **Agent**：packages/agents/private_domain（原有 10 个 action + 用户增长 18 个 action，含 **nl_query**）
- **前端**：PrivateDomainPage（看板、RFM、信号、旅程、差评处理等）

---

## 三、企业微信应用规划

### 3.1 应用形态建议

| 方案 | 说明 | 适用 |
|------|------|------|
| **A. 复用现有自建应用** | 当前 WECHAT_AGENT_ID 对应一个应用，回调已收到消息，仅需在 POST /wechat/webhook 内根据消息内容调用私域 Agent 并回复 | 快速上线、一个应用兼顾「通知+对话」 |
| **B. 独立「私域运营」应用** | 新建一个自建应用专用于私域对话，配置独立 AgentId、独立回调 URL（如 /wechat/private-domain/webhook） | 权限与菜单独立、与通知类应用分离 |

推荐先 **A**，后续可按需拆 **B**。

### 3.2 消息流（与智链OS 兼容）

```
企业微信用户 → 发送文本
    ↓
企业微信服务器 → POST 智链OS /wechat/webhook（或 /wechat/private-domain/webhook）
    ↓
api-gateway：验签、解密、解析 XML（FromUserName、MsgType、Content）
    ↓
消息分发：若为文本且目标为「私域应用」→ 私域 Agent 处理
    ↓
调用 PrivateDomainAgent.execute("nl_query", {"query": Content, "context": {...}})
    ↓
得到 answer（+ 可选 data 摘要）
    ↓
WeChatService.send_text_message(content=answer, touser=FromUserName)
  或 卡片/Markdown（需按企微 API 格式）
    ↓
企业微信服务器 → 用户收到回复
```

- **兼容点**：同一 api-gateway、同一 WeChatService/WeChatCrypto、同一套 WECHAT_* 配置；仅增加「文本消息 → 私域 Agent → 发回」一条链路。
- **store_id / 身份**：FromUserName 为企业微信 UserId，可与智链OS User 表（企业微信 OAuth 登录时写入的 wechat_user_id）关联，得到当前用户所属门店/角色，再传入 `params.store_id` 或 `params.context`，供 Agent 按门店过滤或做权限提示。

### 3.3 应用菜单与工作台（可选）

- **菜单**：在企微管理后台为自建应用配置「发送消息」及菜单项（如「今日数据」「用户画像」「我的门店」），菜单可发事件或关键字，回调收到后按 EventKey/Content 调用对应 action（如 realtime_metrics、user_portrait），或统一走 nl_query。
- **工作台**：若使用「应用主页」，可配置为智链OS 管理后台的 H5 链接（如 PrivateDomainPage 的移动端或单独简版），需与现有 web 路由、登录态（Cookie/Token）或企微 JSSDK 鉴权兼容。

### 3.4 主动推送与事件协同

- **现有 WeChatTriggerService**：已支持 order.*、reservation.*、member.*、payment.*、inventory.* 等事件触发企微推送。
- **私域相关扩展**：可在触发规则中增加私域侧事件（如 `private_domain.churn_alert`、`private_domain.bad_review`），由私域 Agent 或业务流程在产生告警时发布到神经系统/事件总线，再由既有 trigger 服务按规则推送到企微，无需重复建推送通道。
- **推送内容**：可复用现有 message_template 或接入私域 Agent 的 anomaly_alert、feedback_analysis 等输出的摘要。

---

## 四、与智链OS 整体系统的兼容性

### 4.1 架构位置

```
                    企业微信端
                         │
     ┌───────────────────┼───────────────────┐
     │                   │                   │
  应用菜单/工作台    用户发送消息           事件推送（订单/预订/库存…）
     │                   │                   │
     └───────────────────┼───────────────────┘
                         ▼
              智链OS api-gateway
                         │
     ┌───────────────────┼───────────────────┬─────────────────────┐
     │                   │                     │                     │
 /wechat/webhook    /api/v1/private-domain   /api/v1/wechat/      其他 API
 (接收消息)           (管理端/开放调用)        triggers
     │                   │                     │
     │                   ▼                     ▼
     │           PrivateDomainAgent      WeChatTriggerService
     │           (execute/nl_query)      (规则+Celery+WeChatService)
     └───────────► 调用 Agent ◄────────────────┘
                         │
                         ▼
               packages/agents/private_domain
               + 神经系统 / 其他 Agent（按需）
```

- 私域 Agent 仅作为「能力提供方」，不替代现有 WeChat 服务；企微回调与私域 API 共用同一 Agent 实现。
- 管理后台（Web）继续走 /api/v1/private-domain/* 与 OAuth；企微端对话走 webhook → Agent → 回复。

### 4.2 配置与部署

| 项 | 说明 |
|----|------|
| **环境变量** | 沿用现有 WECHAT_CORP_ID、WECHAT_CORP_SECRET、WECHAT_AGENT_ID、WECHAT_TOKEN、WECHAT_ENCODING_AES_KEY；若采用独立私域应用，可增加 WECHAT_PRIVATE_DOMAIN_AGENT_ID 与对应 Secret/Token/AESKey。 |
| **回调 URL** | 企业微信后台配置「接收消息」模式，URL 填智链OS 暴露的 https://<domain>/api/v1/wechat/webhook（或独立路径），GET 用于校验、POST 用于收消息。 |
| **白名单** | 企微要求回调 URL 可公网访问；智链OS 若在内网，需通过网关/反向代理暴露并配置 IP 白名单（企微服务器 IP）。 |

### 4.3 权限与多门店

- **OAuth 与 User**：企业微信登录后智链OS 的 User 与 wechat_user_id、门店、角色已绑定；webhook 收到的 FromUserName 可查 User 表得到 store_id/role。
- **私域接口**：管理端调用 /api/v1/private-domain/execute 时已带登录态，store_id 由前端或 Query 传入；企微回调侧由 FromUserName 解析出的 store_id 写入 params，保证「谁问就按谁的门店答」。
- **权限**：若需区分「仅店长可问经营数据」，可在 webhook 处理链中根据 User 的 role 做 action 白名单或提示「无权限」。

### 4.4 与神经系统 / 其他 Agent 的协同

- **神经系统**：私域 Agent 如需实时订单/会员数据，可依赖现有事件或 API；后续若将「用户问→答案」沉淀为可检索知识，可写入神经系统供 RAG。
- **其他 Agent**：决策/排班/库存等 Agent 已注册在智链OS；私域对话中若识别到明确场景（如「下周排班」），可在 nl_query 或单独 action 中内部调用对应 Agent，再汇总成一句话回复（当前以私域自身能力为主，扩展点预留）。

---

## 五、实施建议（分阶段）与实现状态

| 阶段 | 内容 | 与整体系统兼容要点 | 状态 |
|------|------|----------------------|------|
| **P0** | 在现有 POST /wechat/webhook 中：对文本消息解析 Content，调用 PrivateDomainAgent.execute("nl_query", {"query": Content})，将返回的 answer 用 WeChatService.send_text_message 回发给 FromUserName；未配置或解密失败时保持现有「返回 success」行为。 | 不新增路由、不破坏现有回调；仅增加分支逻辑。 | ✅ 已实现（apps/api-gateway/src/api/enterprise.py） |
| **P1** | FromUserName → User/store_id 解析，将 store_id 传入 nl_query params，便于「今日数据」「用户画像」等按门店返回；可选菜单/EventKey 映射到固定 action。 | 复用现有 User 表与 OAuth 绑定关系。 | ✅ 已实现（webhook 内按 wechat_user_id 查 User.store_id，失败则 default） |
| **P2** | 私域相关事件（流失预警、差评）接入 WeChatTriggerService 或神经系统，推送到企微；可选独立「私域运营」应用与独立回调 URL。 | 与现有 trigger 规则、Celery、WeChatService 一致。 |
| **P3** | 应用工作台链接到 H5 看板；富文本/卡片回复（Markdown 或卡片模板）；意图识别与多轮对话增强。 | 与现有 web 路由、企微 JSSDK 文档对齐。 |

---

## 六、小结

- **企业微信应用**：以「接收用户消息 → 调用私域 Agent（nl_query）→ 企微 API 回复」为主线，复用现有回调与发信能力。
- **兼容智链OS**：同一 api-gateway、同一配置与认证体系、同一 PrivateDomainAgent；企微端作为新入口，与 Web 管理端、事件推送并列，不替代现有模块。
- **扩展性**：store_id/角色从 User 解析、私域事件接入 trigger、多应用/多回调可选，便于后续按门店与角色做细粒度控制与更多企微能力接入。

以上规划可直接用于排期与产品/运维对齐。

### 已实现说明（P0 + P1）

- **位置**：`apps/api-gateway/src/api/enterprise.py`，POST `/wechat/webhook` 分支。
- **逻辑**：当 `MsgType == "text"` 且 `FromUserName` 非空时，取 `Content`；若企微已配置则调用私域 Agent（`PrivateDomainAgent.execute("nl_query", {"query": content, "store_id": store_id})`），将返回的 `answer` 用 `WeChatService.send_text_message` 回发给发信人；回复长度截断至 2000 字符。Agent 或发信失败时仅打日志并仍返回 `"success"`，不影响企微回调。
- **store_id**：通过 `User.wechat_user_id == FromUserName` 查询 `User.store_id`（`get_db_session(enable_tenant_isolation=False)`），未查到则使用 `"default"`。
- **联调**：配置好 `WECHAT_*` 与回调 URL 后，在企业微信应用内发送文本（如「今日数据怎么样」「用户画像」），应收到私域 Agent 的 nl_query 回复。
