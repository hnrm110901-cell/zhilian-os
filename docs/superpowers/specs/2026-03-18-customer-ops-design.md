# 屯象OS 顾客运营体系设计规格

> 基于天财商龙暖客系统对标分析，结合屯象OS现有能力（微生活CRM已通、私域Agent已有、企微集成已有），设计三阶段顾客运营功能。

## 已确认的设计决策

| # | 决策项 | 结论 |
|---|--------|------|
| 1 | 产品架构 | 通用组件 + 角色权限裁剪（服务员只读 → 客户经理完整 → 总部配置） |
| 2 | P1 识客范围 | 完整版：手动搜索 + 预订联动 + POS开单自动触发 |
| 3 | 画像载体 | 企微侧边栏（轻量版）+ 屯象App（完整版），共享BFF |
| 4 | P2 券体系 | 透传微生活券（金额类）+ 屯象自建服务券（体验类） |
| 5 | P3 人群筛选 | 预设人群包（6-8个）+ AI自然语言筛选（差异化） |
| 6 | P3 任务流转 | 总部创建 → 店长分配 → 员工执行 → 数据回流追踪 |

## 技术约定

以下约定与项目现有模型保持一致（参见 CLAUDE.md）：

- **主键**: 所有新表使用 `UUID` 主键（`id UUID PRIMARY KEY DEFAULT gen_random_uuid()`）
- **store_id**: `VARCHAR(50)` — 匹配 `stores.id` 类型（如 "STORE001"）
- **user FK**: `UUID` — 匹配 `users.id` 类型
- **consumer FK**: `UUID` — 使用 `consumer_id` 引用 `consumer_identities.id`，不直接用手机号做外键（经 `IdentityResolutionService.resolve()` 获取）
- **金额**: 数据库存分（fen），`INTEGER` 类型，展示时 `/100` 转元
- **迁移**: 每阶段通过 Alembic migration 创建表，不用裸 SQL

## 角色与权限矩阵

"总部"角色对应现有 `UserRole.ADMIN`。

| 功能 | 服务员 (WAITER) | 楼面经理/主管 (FLOOR_MANAGER/TEAM_LEADER) | 客户经理 (CUSTOMER_MANAGER) | 店长 (STORE_MANAGER) | 总部 (ADMIN) |
|------|--------|--------------|---------|------|------|
| 查看画像 | 只读（基础信息） | 只读（含偏好） | 完整（含消费记录） | 完整 | 完整+统计 |
| 搜索顾客 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 接收POS推送 | ✅ | ✅ | ✅ | ✅ | — |
| 发券 | — | ✅ | ✅ | ✅ | 批量 |
| 编辑标签 | — | — | ✅ | ✅ | ✅ |
| 查看ROI | — | — | 个人 | 门店 | 全域 |
| 创建营销任务 | — | — | — | — | ✅ |
| 分配任务 | — | — | — | ✅ | — |
| 执行任务 | — | ✅ | ✅ | ✅ | — |

---

## P1 · 到店识客画像

### 目标

让每个服务触点都"认识"顾客——员工在顾客到店时能即时看到身份、偏好、资产、关键节点四维信息，并获得AI生成的个性化服务话术。

### 系统架构

```
触发源
  ├── 手动搜索（手机号/会员码）
  ├── 今日预订列表（预订时间到达提醒）
  └── POS Webhook（开单自动推送，customer_phone 字段已存在于 pos_webhook.py payload）
         ↓
BFF: GET /api/v1/bff/member-profile/{store_id}/{phone}
         ↓ 聚合（并发调用，任一子源失败降级返回 null，不阻塞整体）
  ├── 微生活CRM → 等级/余额/积分/券（accountBasicsInfo API，已通）
  ├── 品智POS   → 消费记录/常点菜（订单查询 API，已通）
  ├── 私域引擎   → RFM/标签/生命周期（consumer_identities 表 + tags 字段）
  └── AI Agent   → 个性化话术（现有 LLM Agent 基础设施）
         ↓ 返回
  ├── 企微侧边栏 → 轻量画像卡
  └── 屯象App   → 完整画像页
```

### 降级策略

| 子源 | 不可用时降级 | 缓存TTL |
|------|-------------|---------|
| 微生活CRM | 返回 `assets: null`，前端用 ZEmpty 占位 | 5分钟 |
| 品智POS | 返回 `preferences: null` | 10分钟 |
| 私域引擎 | 返回基础 consumer_identity 数据 | 5分钟 |
| AI Agent | 不返回话术，不影响画像卡展示 | 不缓存 |

POS Webhook 触发时主动失效对应 consumer_id 的 Redis 缓存。

### 后端新增

- **BFF 接口**: `GET /api/v1/bff/member-profile/{store_id}/{phone}`
  - 先通过 `IdentityResolutionService.resolve(phone)` 获取 `consumer_id`
  - 并发聚合微生活会员信息、POS消费记录、私域标签
  - 调用AI Agent生成话术
  - 返回统一 `MemberProfile` 结构
  - 缓存策略：Redis 缓存5分钟，key = `member_profile:{consumer_id}`
- **多源聚合 Service**: `member_profile_aggregator.py`
  - 并发调用微生活 `accountBasicsInfo`、POS 消费记录查询、`consumer_identities` 标签
  - 任一子调用失败 → 降级返回 null（不阻塞整屏，符合 BFF 聚合规则）
- **AI 话术生成**: 调用现有 LLM Agent，输入画像数据，输出个性化服务话术
- **POS Webhook 识客扩展**: 在现有 `/api/v1/pos-webhook/{store_id}/pinzhi-order` handler 中
  - `customer_phone` 字段已存在于 payload model（pos_webhook.py:59）
  - 新增逻辑：resolve consumer_id → 预加载画像到 Redis → 推送通知到对应企微用户
- **今日预订顾客列表接口**: `GET /api/v1/bff/today-reservations/{store_id}`
  - 聚合预订系统数据 + 预加载画像

### 前端新增

- **MemberProfileCard**: 通用画像卡组件
  - 四维展示：身份（等级/标签）、偏好（常点菜/忌口）、资产（余额/积分/券）、节点（生日/纪念日）
  - 角色权限裁剪：服务员看基础版，客户经理看完整版
- **MemberSearchBar**: 搜索组件（手机号/会员码输入）
- **TodayReservations**: 今日预订列表组件（时间线视图）
- **各角色 Layout 入口适配**: 在 SM/Floor/HQ 等布局中集成搜索入口
- **企微 H5 侧边栏页面**: 轻量版画像卡，适配企微侧边栏规格（宽度200px），独立路由 `/wecom/member-profile`

### 数据模型

```sql
-- 识客事件记录
CREATE TABLE member_check_ins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    brand_id VARCHAR(50) NOT NULL,
    consumer_id UUID NOT NULL REFERENCES consumer_identities(id),
    trigger_type VARCHAR(20) NOT NULL,  -- 'manual_search' | 'reservation' | 'pos_webhook'
    staff_id UUID REFERENCES users(id),
    checked_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    profile_snapshot JSONB  -- 快照当时画像数据（结构同 BFF 响应）
);
CREATE INDEX idx_check_ins_consumer ON member_check_ins(consumer_id, checked_in_at DESC);
CREATE INDEX idx_check_ins_store ON member_check_ins(store_id, checked_in_at DESC);

-- 菜品偏好聚合（由POS订单定期聚合，Celery定时任务）
CREATE TABLE member_dish_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id UUID NOT NULL REFERENCES consumer_identities(id),
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    brand_id VARCHAR(50) NOT NULL,
    dish_name VARCHAR(100) NOT NULL,
    order_count INT NOT NULL DEFAULT 0,
    last_ordered_at TIMESTAMPTZ,
    is_favorite BOOLEAN DEFAULT FALSE,
    UNIQUE(consumer_id, store_id, dish_name)
);

-- 扩展 consumer_identities 表（tags 和 birth_date 已存在，仅新增2列）
ALTER TABLE consumer_identities ADD COLUMN dietary_restrictions JSONB DEFAULT '[]';
ALTER TABLE consumer_identities ADD COLUMN anniversary DATE;
```

### BFF 响应结构

```json
{
  "consumer_id": "550e8400-e29b-41d4-a716-446655440000",
  "identity": {
    "name": "刘女士",
    "phone": "138****1234",
    "level": "储值2000",
    "tags": ["高频客", "VIP"],
    "lifecycle_stage": "活跃期"
  },
  "preferences": {
    "favorite_dishes": [
      {"name": "特色江蟹生", "count": 12},
      {"name": "冰淇淋打蛋", "count": 8}
    ],
    "dietary_restrictions": ["不吃香菜"],
    "preferred_seating": "包间"
  },
  "assets": {
    "balance_fen": 126000,
    "balance_display": "¥1,260.00",
    "points": 3800,
    "available_coupons": [
      {"name": "宠粉日8折券", "expires": "2026-03-25"}
    ]
  },
  "milestones": {
    "birthday": "2026-03-22",
    "birthday_upcoming": true,
    "last_visit": "2026-03-10",
    "total_visits": 28,
    "member_since": "2024-06-15"
  },
  "ai_script": "刘姐欢迎！包间给您留好了，今天江蟹特别新鲜。另外看到您本周生日，我们准备了小礼物🎁"
}
```

> 注：`assets` 可能为 `null`（CRM不可用时），`preferences` 可能为 `null`（POS不可用时），`ai_script` 可能为 `null`（LLM不可用时）。前端用 ZEmpty 组件处理。

---

## P2 · 发券 + ROI 追踪

### 目标

让每次发券都可衡量——员工在画像页直接选券发送，系统自动追踪核销并计算ROI，支持个人/门店/品牌三级统计。

### 券体系双轨制

#### 微生活券（透传，金额类）

- 拉取可用券列表：调用已通的微生活 `coupon_list` API（member_service.py 已有 `coupon_list()` 方法）
- 画像页选券 → 调用 `coupon_use` API 发放（member_service.py 已有 `coupon_use()` 方法）
- 核销由POS收银完成，屯象通过POS Webhook回调获取核销事件
- 屯象记录：谁发的 / 发给谁 / 何时核销 / 关联订单

#### 屯象服务券（自建，体验类）

- 场景：赠小菜、新品试吃、生日惊喜——不涉及收银核销
- 员工手动确认核销（"已送达"按钮）
- 状态机：`created → sent → used → expired`
  - `created → sent`: 发放给顾客时（由 distributed_by 用户触发）
  - `sent → used`: 员工点击"已送达"确认（由 confirmed_by 用户触发）
  - `sent → expired`: 超过 expires_at 时间（Celery 定时任务检查，每小时一次）
  - `created → expired`: 同上

### 数据模型

```sql
-- 屯象服务券模板
CREATE TABLE service_voucher_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,           -- "赠送小菜券"
    voucher_type VARCHAR(20) NOT NULL,     -- 'complimentary_dish' | 'tasting' | 'birthday_gift'
    description TEXT,
    valid_days INT NOT NULL DEFAULT 7,
    created_by UUID REFERENCES users(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 服务券实例
CREATE TABLE service_vouchers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES service_voucher_templates(id),
    consumer_id UUID NOT NULL REFERENCES consumer_identities(id),
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    brand_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'created',  -- created | sent | used | expired
    issued_by UUID NOT NULL REFERENCES users(id),
    used_at TIMESTAMPTZ,
    confirmed_by UUID REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_vouchers_consumer ON service_vouchers(consumer_id, status);
CREATE INDEX idx_vouchers_store ON service_vouchers(store_id, status);

-- 发券记录（统一，含微生活券和服务券）
CREATE TABLE coupon_distributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    brand_id VARCHAR(50) NOT NULL,
    consumer_id UUID NOT NULL REFERENCES consumer_identities(id),
    coupon_source VARCHAR(20) NOT NULL,    -- 'weishenghuo' | 'service_voucher'
    coupon_id VARCHAR(100) NOT NULL,       -- 微生活券ID 或 service_vouchers.id::text
    coupon_name VARCHAR(100) NOT NULL,
    coupon_value_fen INT DEFAULT 0,        -- 券面值（分），服务券为0
    distributed_by UUID NOT NULL REFERENCES users(id),
    distributed_at TIMESTAMPTZ DEFAULT NOW()
    -- marketing_task_id 在 P3 阶段通过 ALTER TABLE ADD COLUMN 添加
);
CREATE INDEX idx_distributions_consumer ON coupon_distributions(consumer_id, distributed_at DESC);
CREATE INDEX idx_distributions_store ON coupon_distributions(store_id, distributed_at DESC);

-- 核销记录
CREATE TABLE coupon_redemptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distribution_id UUID NOT NULL REFERENCES coupon_distributions(id),
    order_id VARCHAR(100),                 -- 关联POS订单号
    order_amount_fen INT,                  -- 订单金额（分）
    redeemed_at TIMESTAMPTZ DEFAULT NOW()
);

-- ROI 日汇总
CREATE TABLE coupon_roi_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    brand_id VARCHAR(50) NOT NULL,
    staff_id UUID REFERENCES users(id),
    distributed_count INT DEFAULT 0,
    distributed_value_fen INT DEFAULT 0,    -- 发放总面值（分）
    redeemed_count INT DEFAULT 0,
    redeemed_value_fen INT DEFAULT 0,       -- 核销总面值（分）
    driven_gmv_fen INT DEFAULT 0,           -- 带动GMV（分）
    UNIQUE(date, store_id, staff_id)
);
```

### 后端新增

- **发券接口**: `POST /api/v1/bff/member-profile/{store_id}/distribute-coupon`
  - 请求体: `{ "consumer_id": "uuid", "coupon_source": "weishenghuo|service_voucher", "coupon_id": "str" }`
  - 微生活券 → 调用 `member_service.coupon_use()`；服务券 → 创建 `service_vouchers` 记录
  - 同时写入 `coupon_distributions`
  - 返回: `{ "distribution_id": "uuid", "success": true }`
- **核销回调处理**: 扩展 POS Webhook handler，匹配核销事件到 `coupon_distributions` 记录
- **服务券核销**: `POST /api/v1/bff/member-profile/{store_id}/confirm-service-voucher/{voucher_id}`
  - 更新 `service_vouchers.status` = 'used'，记录 `confirmed_by` 和 `used_at`
- **ROI 看板接口**: `GET /api/v1/bff/coupon-roi/{store_id}?staff_id=&date_from=&date_to=&group_by=staff|store|brand`
  - 返回: `{ "distributed_count": N, "distributed_value_display": "¥X", "redeemed_count": N, "roi_rate": 0.XX, "driven_gmv_display": "¥X" }`
- **过期券处理**: Celery 定时任务（每小时），将超时的 `service_vouchers` 状态更新为 'expired'

### 前端新增

- **CouponSelector**: 券选择弹窗（微生活券列表 + 服务券模板），嵌入 MemberProfileCard 的"发券"按钮
- **CouponHistory**: 发券记录列表（按 consumer_id 查询）
- **ROIDashboard**: ROI看板组件（三级视图切换：个人/门店/品牌）

---

## P3 · 总部营销任务下发

### 目标

让总部策略落地到每个门店——总部创建人群包、绑定话术和券、下发到指定门店，门店接收分配给员工执行，全程数据追踪。

### 任务流转

```
总部 (ADMIN)               店长 (STORE_MANAGER)        楼面/客户经理              数据回流
① 创建任务                   ② 接收 & 分配              ③ 执行触达                ④ 效果追踪
  选人群条件                   收到任务推送               查看分配的顾客列表          触达率 / 核销率
  → 绑话术模板 + 券            → 查看本店目标顾客          → 企微发消息/发券           → 带动GMV
  → 设截止时间                → 分配给员工               → 标记已执行               → 门店排名
  → 选下发门店                → 监控进度                 → 记录反馈                 → 员工贡献
```

### 人群筛选能力

#### 预设人群包（覆盖80%场景）

| 人群包 | 筛选逻辑 |
|--------|---------|
| 近一周生日 | `consumer_identities.birth_date` 匹配未来7天 |
| 30天未消费 | `member_check_ins.checked_in_at` 最近记录 > 30天前，且总到店 > 3次 |
| 储值余额<50 | 微生活CRM余额 < 5000分 且 > 0 |
| 高价值VIP | 微生活等级 IN ('金卡','钻石') OR 累计消费 > 1000000分 |
| 首单新客 | 总到店 = 1 且 首次到店 < 30天前 |
| 消费下降 | 近30天到店频次 < 前30天到店频次 * 0.5 |
| 沉睡会员 | 最近到店 > 90天前 |
| 储值到期提醒 | 微生活储值卡到期 < 30天 |

#### AI 自然语言筛选（覆盖20%长尾）

- 用户输入自然语言描述目标人群
- AI Agent 解析为 SQL WHERE 条件（基于现有 `intent_router` 能力扩展）
- 预览匹配人数 → 用户确认 → 创建人群快照

### P3 阶段迁移（关联P2）

```sql
-- P3 migration: 在 coupon_distributions 表上添加营销任务关联
ALTER TABLE coupon_distributions ADD COLUMN marketing_task_id UUID;
-- FK 在 marketing_tasks 表创建后再添加
```

### 数据模型

```sql
-- 营销任务
CREATE TABLE marketing_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    audience_type VARCHAR(20) NOT NULL,     -- 'preset' | 'ai_query'
    audience_config JSONB NOT NULL,          -- {"preset_id": "birthday_week"} 或 {"ai_query": "...", "sql_where": "..."}
    script_template TEXT,                    -- 话术模板
    coupon_config JSONB,                     -- {"source": "weishenghuo", "coupon_id": "..."} 或 {"source": "service_voucher", "template_id": "..."}
    status VARCHAR(20) DEFAULT 'draft',      -- draft | published | in_progress | completed | cancelled
    deadline TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES users(id),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 添加 coupon_distributions 的 FK（在 marketing_tasks 表创建后）
ALTER TABLE coupon_distributions
    ADD CONSTRAINT fk_distributions_task
    FOREIGN KEY (marketing_task_id) REFERENCES marketing_tasks(id);

-- 目标人群快照
CREATE TABLE marketing_task_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES marketing_tasks(id),
    consumer_id UUID NOT NULL REFERENCES consumer_identities(id),
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    profile_snapshot JSONB,                  -- 筛选时的画像快照（结构同 BFF 响应）
    UNIQUE(task_id, consumer_id, store_id)
);

-- 门店分配
CREATE TABLE marketing_task_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES marketing_tasks(id),
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    assigned_to UUID REFERENCES users(id),   -- 具体执行人（店长分配后填入）
    target_count INT DEFAULT 0,
    completed_count INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',    -- pending | assigned | in_progress | completed
    assigned_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
CREATE INDEX idx_assignments_task ON marketing_task_assignments(task_id, status);

-- 执行记录
CREATE TABLE marketing_task_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES marketing_task_assignments(id),
    target_id UUID NOT NULL REFERENCES marketing_task_targets(id),
    executor_id UUID NOT NULL REFERENCES users(id),
    action_type VARCHAR(20) NOT NULL,        -- 'wechat_msg' | 'coupon' | 'call' | 'in_store'
    action_detail JSONB,
    distribution_id UUID REFERENCES coupon_distributions(id),  -- 关联发券
    feedback TEXT,
    executed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 效果统计（日汇总）
CREATE TABLE marketing_task_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES marketing_tasks(id),
    store_id VARCHAR(50) NOT NULL REFERENCES stores(id),
    date DATE NOT NULL,
    target_count INT DEFAULT 0,
    reached_count INT DEFAULT 0,
    coupon_distributed INT DEFAULT 0,
    coupon_redeemed INT DEFAULT 0,
    driven_gmv_fen INT DEFAULT 0,            -- 带动GMV（分）
    UNIQUE(task_id, store_id, date)
);
```

### 后端新增

- **任务 CRUD**: `POST/GET/PUT /api/v1/hq/marketing-tasks`
  - 创建: `{ "title": "str", "audience_type": "preset|ai_query", "audience_config": {}, "script_template": "str", "coupon_config": {}, "deadline": "datetime", "store_ids": ["STORE001"] }`
  - 列表: 支持 `?status=` 筛选
- **人群预览**: `POST /api/v1/hq/audience-preview`
  - 请求: `{ "audience_type": "preset|ai_query", "audience_config": {}, "store_ids": [] }`
  - 返回: `{ "total_count": N, "by_store": [{"store_id": "S001", "count": N}] }`
- **AI 人群查询**: `POST /api/v1/hq/audience-ai-query`
  - 请求: `{ "natural_language": "找出最近60天没来消费但之前月均消费3次以上的老顾客" }`
  - 返回: `{ "sql_where": "...", "explanation": "...", "preview_count": N }`
- **任务下发**: `POST /api/v1/hq/marketing-tasks/{id}/publish`
  - 创建 `marketing_task_targets` 快照 + `marketing_task_assignments` 分配记录
  - 发送通知到各门店店长
- **店长分配**: `POST /api/v1/sm/marketing-tasks/{assignment_id}/assign`
  - 请求: `{ "assigned_to": "user_uuid" }`
- **执行记录**: `POST /api/v1/bff/marketing-tasks/{assignment_id}/execute`
  - 请求: `{ "target_id": "uuid", "action_type": "wechat_msg|coupon", "action_detail": {}, "feedback": "str" }`
- **效果看板**: `GET /api/v1/hq/marketing-task-stats/{task_id}?store_id=`
  - 返回: `{ "overview": {"target": N, "reached": N, "reach_rate": 0.XX}, "by_store": [...], "by_staff": [...] }`

### 前端新增

- **TaskCreator**: 总部任务创建页（人群选择 + 话术编辑 + 券绑定 + 门店选择），路由 `/hq/marketing-tasks/create`
- **AIAudienceInput**: AI自然语言人群筛选组件（文本输入 → 调用预览 → 显示匹配数）
- **TaskList**: 任务列表（按角色显示不同视图），路由 `/hq/marketing-tasks`、`/sm/marketing-tasks`
- **TaskAssignment**: 店长任务分配页，路由 `/sm/marketing-tasks/{id}/assign`
- **TaskExecution**: 员工执行页（顾客列表 + 操作按钮），路由 `/floor/marketing-tasks/{id}`
- **TaskDashboard**: 效果追踪看板，嵌入 `/hq/marketing-tasks/{id}` 详情页

### AI 差异化能力

- 自然语言 → 人群查询（基于 intent_router 扩展）
- AI 生成话术模板（输入人群特征 + 活动主题，输出话术）
- 智能推荐最佳触达时间（基于 member_check_ins 历史时段分析）
- 自动生成执行复盘报告

---

## 交付时间线

| 阶段 | 时长 | 核心交付物 |
|------|------|-----------|
| P1 · 识客画像 | 3周 | 后端BFF + App画像页 + 企微侧边栏 + POS触发 |
| P2 · 发券+ROI | 2周 | 发券交互 + 服务券 + ROI看板 |
| P3 · 营销任务 | 3周 | 总部创建 + AI筛选 + 下发执行 + 追踪看板 |

## 技术栈

- **前端**: React + TypeScript + Vite（现有）
- **后端**: FastAPI + SQLAlchemy（现有）
- **企微H5**: 同前端技术栈，独立路由 `/wecom/*`
- **AI**: 现有 LLM Agent 基础设施
- **缓存**: Redis（画像缓存，key = `member_profile:{consumer_id}`）
- **数据库**: PostgreSQL（现有），新表通过 Alembic migration 创建
- **定时任务**: Celery（服务券过期检查、菜品偏好聚合、ROI日汇总）

## 依赖关系

- P1 无外部依赖，基于已通的微生活CRM + 品智POS API + 现有 consumer_identities 表
- P2 依赖 P1（画像页内嵌发券入口），微生活券API已通（member_service.py 已有方法）
- P3 依赖 P1+P2（画像筛选 + 发券能力），需扩展 /hq 路由，P3 migration 补充 coupon_distributions 的 marketing_task_id 列
