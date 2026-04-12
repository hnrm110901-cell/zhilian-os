# 屯象OS PostgreSQL RLS 策略审计 + 安全加固报告

> **审计日期**: 2026-03-27
> **审计范围**: 数据模型 tenant_id 覆盖率、RLS 策略完整性、RLS 绕过风险、Nginx 安全配置、端口暴露面
> **审计方式**: 静态代码分析（未连接实际数据库或扫描服务器端口）

---

## 1. 执行摘要

| 指标 | 数值 | 评估 |
|------|------|------|
| 模型文件总数（不含 base/mixins/\_\_init\_\_） | 162 | - |
| 含 store_id/tenant_id 的模型文件 | 130 | 80.2% |
| **缺少 store_id/tenant_id 的模型文件** | **32** | 需逐一评估 |
| RLS 策略覆盖表数（rls_001 + r01 + r04） | 21 | 偏低 |
| 严重安全发现 (CRITICAL) | 2 | 需立即修复 |
| 高风险发现 (HIGH) | 4 | 建议 1 周内修复 |
| 中风险发现 (MEDIUM) | 5 | 建议 1 个月内修复 |
| 低风险发现 (LOW) | 3 | 建议纳入常规迭代 |

---

## 2. RLS 策略覆盖率详情

### 2.1 已启用 RLS 的表

**来源: `rls_001_tenant_isolation.py`（19 张表，使用 `app.current_tenant`）**

| # | 表名 | RLS session 变量 | SELECT/INSERT/UPDATE/DELETE |
|---|------|-----------------|----------------------------|
| 1 | orders | `app.current_tenant` | 全覆盖 |
| 2 | order_items | `app.current_tenant` | 全覆盖 |
| 3 | reservations | `app.current_tenant` | 全覆盖 |
| 4 | inventory_items | `app.current_tenant` | 全覆盖 |
| 5 | inventory_transactions | `app.current_tenant` | 全覆盖 |
| 6 | schedules | `app.current_tenant` | 全覆盖 |
| 7 | employees | `app.current_tenant` | 全覆盖 |
| 8 | training_records | `app.current_tenant` | 全覆盖 |
| 9 | training_plans | `app.current_tenant` | 全覆盖 |
| 10 | service_feedbacks | `app.current_tenant` | 全覆盖 |
| 11 | complaints | `app.current_tenant` | 全覆盖 |
| 12 | tasks | `app.current_tenant` | 全覆盖 |
| 13 | notifications | `app.current_tenant` | 全覆盖 |
| 14 | pos_transactions | `app.current_tenant` | 全覆盖 |
| 15 | member_transactions | `app.current_tenant` | 全覆盖 |
| 16 | financial_records | `app.current_tenant` | 全覆盖 |
| 17 | supply_orders | `app.current_tenant` | 全覆盖 |
| 18 | reconciliation_records | `app.current_tenant` | 全覆盖 |

**来源: `r01_bom_tables.py`（2 张表，使用 `app.current_store_id`）**

| # | 表名 | RLS session 变量 | 覆盖范围 |
|---|------|-----------------|---------|
| 19 | bom_templates | `app.current_store_id` | 仅 SELECT（USING 子句） |
| 20 | bom_items | `app.current_store_id` | 仅 SELECT（USING 子句） |

**来源: `r04_waste_event_table.py`（1 张表，使用 `app.current_store_id`）**

| # | 表名 | RLS session 变量 | 覆盖范围 |
|---|------|-----------------|---------|
| 21 | waste_events | `app.current_store_id` | 仅 SELECT（USING 子句） |

**来源: `rls_002_brand_isolation.py`（品牌层 RLS，覆盖与 rls_001 相同的 18 张表）**
- 使用 `app.current_brand` session 变量
- 为 stores 和 users 表添加了 brand_id 列

### 2.2 RLS session 变量不一致 [CRITICAL-001]

**风险等级: CRITICAL**

| 迁移脚本 | 使用的 session 变量 | 应用代码设置的变量 |
|----------|-------------------|------------------|
| `rls_001_tenant_isolation.py` | `app.current_tenant` | `app.current_tenant` (tenant_filter.py:94) |
| `r01_bom_tables.py` | **`app.current_store_id`** | `app.current_tenant` (tenant_filter.py:94) |
| `r04_waste_event_table.py` | **`app.current_store_id`** | `app.current_tenant` (tenant_filter.py:94) |

**影响**: `bom_templates`、`bom_items`、`waste_events` 三张表的 RLS 策略实际上**永远不生效**，因为应用层设置的是 `app.current_tenant`，而 RLS 策略检查的是 `app.current_store_id`（从未被设置），`current_setting(..., TRUE)` 在变量不存在时返回 NULL，导致策略条件始终不满足或始终满足（取决于 PostgreSQL 版本和 NULL 处理）。

**修复建议**: 将 `r01_bom_tables.py` 和 `r04_waste_event_table.py` 中的 `app.current_store_id` 统一改为 `app.current_tenant`，并创建新的迁移脚本执行 `DROP POLICY` + `CREATE POLICY`。

### 2.3 RLS 策略 NULL 绕过漏洞 [CRITICAL-002]

**风险等级: CRITICAL**

`rls_001_tenant_isolation.py` 中的策略包含以下条件：

```sql
USING (
    store_id = current_setting('app.current_tenant', TRUE)::text
    OR current_setting('app.current_tenant', TRUE) IS NULL
)
```

**问题**: 当 `app.current_tenant` 未设置（即 `current_setting` 返回 NULL）时，`OR ... IS NULL` 条件为 TRUE，**所有行对所有用户可见**。这意味着：
- 如果应用层忘记设置 tenant context（bug、新 API 端点遗漏等），RLS 将完全失效
- 数据库管理员直接连接 psql 时，所有数据暴露无遗

**修复建议**:
1. 移除 `OR current_setting('app.current_tenant', TRUE) IS NULL` 条件
2. 为超级管理员创建独立的 `BYPASSRLS` 角色
3. 应用层使用专用的非 BYPASSRLS 数据库角色连接

---

## 3. 缺少 tenant_id/store_id 的模型文件清单

以下 32 个模型文件中未发现 `store_id` 或 `tenant_id` 字段定义：

### 3.1 高风险（包含敏感业务数据）

| # | 模型文件 | 推测表名 | 风险等级 | 说明 |
|---|---------|---------|---------|------|
| 1 | `store.py` | stores | **HIGH** | 门店表本身作为租户实体，需 brand_id 隔离（rls_002 已补） |
| 2 | `org_permission.py` | org_permissions | **HIGH** | 权限映射，无租户隔离可导致越权 |
| 3 | `org_node.py` | org_nodes | **HIGH** | 组织架构节点，跨租户可泄露组织结构 |
| 4 | `org_config.py` | org_configs | **HIGH** | 组织配置，跨租户可泄露经营策略 |
| 5 | `person.py` / `hr/person.py` | persons | **HIGH** | 人员主数据（含身份信息），跨租户严重 |
| 6 | `person_contract.py` | person_contracts | **HIGH** | 合同数据，含薪资等敏感信息 |
| 7 | `bank_reconciliation.py` | bank_reconciliations | **HIGH** | 银行对账，财务数据跨租户极危险 |

### 3.2 中风险（包含业务运营数据）

| # | 模型文件 | 风险等级 | 说明 |
|---|---------|---------|------|
| 8 | `achievement.py` | MEDIUM | 成就/绩效数据 |
| 9 | `backup_job.py` | MEDIUM | 备份任务（可能含跨租户数据引用） |
| 10 | `behavior_pattern.py` | MEDIUM | 行为模式 |
| 11 | `channel_config.py` | MEDIUM | 渠道配置 |
| 12 | `export_job.py` | MEDIUM | 导出任务（可能导出跨租户数据） |
| 13 | `fct_advanced.py` | MEDIUM | 财务合并高级表 |
| 14 | `ingredient_mapping.py` | MEDIUM | 食材映射 |
| 15 | `ingredient_master.py` | MEDIUM | 食材主数据 |
| 16 | `member_rfm.py` | MEDIUM | 会员 RFM 分析 |
| 17 | `menu_rank.py` | MEDIUM | 菜品排行 |
| 18 | `purchase_order_item.py` | MEDIUM | 采购明细 |
| 19 | `supplier_intelligence.py` | MEDIUM | 供应商情报 |
| 20 | `weekly_review.py` | MEDIUM | 周报 |

### 3.3 低风险（配置/模板/知识库类，可能为全局共享）

| # | 模型文件 | 风险等级 | 说明 |
|---|---------|---------|------|
| 21 | `agent_config.py` | LOW | Agent 配置（可能全局共享） |
| 22 | `city_wage_config.py` | LOW | 城市工资配置（全局参考数据） |
| 23 | `dish_channel.py` | LOW | 菜品渠道 |
| 24 | `integration_hub.py` | LOW | 集成中心 |
| 25 | `job_sop.py` | LOW | 岗位 SOP 模板 |
| 26 | `job_standard.py` | LOW | 岗位标准 |
| 27 | `knowledge_capture.py` | LOW | 知识采集 |
| 28 | `knowledge_base/dish_knowledge.py` | LOW | 菜品知识库 |
| 29 | `knowledge_base/industry_dictionary.py` | LOW | 行业字典 |
| 30 | `knowledge_base/seed_data.py` | LOW | 种子数据 |
| 31 | `signal_routing_rule.py` | LOW | 信号路由规则 |
| 32 | `warning_rule.py` | LOW | 告警规则模板 |

### 3.4 HR 子模块（全部缺少 store_id/tenant_id）

| # | 模型文件 | 风险等级 | 说明 |
|---|---------|---------|------|
| 33 | `hr/approval_instance.py` | **HIGH** | 审批实例 |
| 34 | `hr/approval_template.py` | MEDIUM | 审批模板 |
| 35 | `hr/attendance_rule.py` | MEDIUM | 考勤规则 |
| 36 | `hr/employment_assignment.py` | **HIGH** | 用工分配 |
| 37 | `hr/employment_contract.py` | **HIGH** | 劳动合同 |
| 38 | `hr/leave_balance.py` | MEDIUM | 假期余额 |
| 39 | `hr/leave_request.py` | MEDIUM | 请假申请 |
| 40 | `hr/employee_id_map.py` | MEDIUM | 员工 ID 映射 |
| 41 | `hr/kpi_template.py` | LOW | KPI 模板 |
| 42 | `hr_knowledge/behavior_pattern.py` | LOW | 行为模式 |
| 43 | `hr_knowledge/hr_knowledge_rule.py` | LOW | HR 知识规则 |
| 44 | `hr_knowledge/knowledge_capture.py` | LOW | 知识采集 |
| 45 | `hr_knowledge/person_achievement.py` | MEDIUM | 个人成就 |
| 46 | `hr_knowledge/retention_signal.py` | MEDIUM | 留存信号 |
| 47 | `hr_knowledge/skill_node.py` | LOW | 技能节点 |

---

## 4. 应该有 RLS 但没有的表（按风险排序）

**当前已有 RLS 的表**: 21 张（rls_001 的 18 张 + bom_templates + bom_items + waste_events）

以下表含有 `store_id`/`tenant_id` 字段但**未被 RLS 策略覆盖**，需要增加 RLS：

### CRITICAL（必须有 RLS）

| 表/模型 | 理由 |
|---------|------|
| 所有 HR 模块表（attendance, leave, payroll, payslip, salary_item, commission, social_insurance 等） | 包含员工个人薪资、考勤等极敏感数据 |
| finance / financial_closing | 财务数据 |
| daily_settlement / payment_reconciliation / tri_reconciliation | 结算对账数据 |
| settlement | 结算数据 |
| sensitive_audit_log | 敏感操作日志（含敏感信息引用） |

### HIGH（应该有 RLS）

| 表/模型 | 理由 |
|---------|------|
| banquet / banquet_event_order / banquet_lifecycle / banquet_sales | 宴会业务全链路 |
| private_domain / member_lifecycle / member_check_in / member_dish_preference / coupon_distribution | 会员/私域数据 |
| dish / dish_master / dish_rd / meal_period / bom | 菜品经营数据 |
| cost_truth / price_benchmark | 成本/定价数据 |
| forecast / daily_report / daily_summary / daily_metric | 经营预测和报告 |
| kpi / performance_review / employee_growth / employee_metric | 绩效数据 |

### MEDIUM

| 表/模型 | 理由 |
|---------|------|
| marketing_campaign / marketing_task | 营销数据 |
| conversation / notification | 沟通记录 |
| audit_log / operation_audit_log / execution_audit | 审计日志 |
| queue / floor_plan / hall_showcase | 门店运营 |
| agent_okr / agent_collab / ops_flow_agent | Agent 数据 |

---

## 5. 可能绕过 RLS 的代码路径

### 5.1 ORM 层 tenant_filter 覆盖不完整 [HIGH-001]

**风险等级: HIGH**

`src/core/tenant_filter.py` 中 `TENANT_TABLES` 集合仅包含 18 张表，与 RLS 策略覆盖的表一致。但项目有 130+ 个模型含 store_id，意味着**绝大多数表既没有 RLS 保护，也没有 ORM 层自动过滤**。

**文件**: `/Users/lichun/tunxiang/apps/api-gateway/src/core/tenant_filter.py` 第 16-35 行

### 5.2 ORM 过滤器仅拦截 SELECT [HIGH-002]

**风险等级: HIGH**

`tenant_filter.py:52` 中 `receive_do_orm_execute` 检查 `orm_execute_state.is_select`，仅对 SELECT 查询注入过滤条件。INSERT / UPDATE / DELETE 操作不受 ORM 层保护，完全依赖 RLS（但 RLS 覆盖面也不足）。

### 5.3 disable_tenant_filter 无权限检查 [MEDIUM-001]

**风险等级: MEDIUM**

`tenant_filter.py:124` 的 `disable_tenant_filter()` 函数可被任何代码调用以禁用租户过滤，无权限验证。虽然目前只在 `TenantFilterContext.__aexit__` 中调用，但缺乏防护。

### 5.4 store_id 过滤检查使用字符串匹配 [MEDIUM-002]

**风险等级: MEDIUM**

`tenant_filter.py:121` 使用 `"store_id" in where_str.lower()` 做字符串匹配来判断是否已有 store_id 条件。这可以被列名包含 "store_id" 子串的其他条件误判为已过滤（如 `other_store_id`）。

### 5.5 未发现 SET ROLE / SECURITY DEFINER 绕过 [OK]

在整个 `src/` 目录中未搜索到 `SET ROLE`、`SET LOCAL`、`SECURITY DEFINER`、`BYPASSRLS` 等危险模式。

---

## 6. Nginx 安全审计

### 6.1 安全响应头 [OK - 大部分到位]

**文件**: `/Users/lichun/tunxiang/nginx/conf.d/snippets/security-headers.conf`

| Header | 状态 | 值 |
|--------|------|-----|
| Strict-Transport-Security | OK | `max-age=31536000; includeSubDomains; preload` |
| X-Frame-Options | OK | `DENY` |
| X-Content-Type-Options | OK | `nosniff` |
| X-XSS-Protection | OK | `1; mode=block` |
| Referrer-Policy | OK | `strict-origin-when-cross-origin` |
| Content-Security-Policy | **缺失** | Nginx 层未配置（仅在 FastAPI 中间件层有） |
| Permissions-Policy | **缺失** | Nginx 层未配置（仅在 FastAPI 中间件层有） |
| server_tokens | OK | `off` |

**风险等级**: MEDIUM-003 - CSP 和 Permissions-Policy 仅在应用层设置，如果请求不经过 FastAPI（如静态资源由 Nginx 直接服务），这些头将缺失。

### 6.2 Rate Limiting [HIGH-003]

**风险等级: HIGH**

Nginx 配置中**完全没有**速率限制（`limit_req_zone` / `limit_req` / `limit_conn`）。
- 虽然 FastAPI 层有 `RateLimitMiddleware`（`main.py:530`），但 Nginx 层缺乏保护意味着：
  - DDoS 攻击请求会全部打到应用层
  - 如果 FastAPI rate limiter 有 bug 或被绕过，没有二次防线

**修复建议**:
```nginx
# 在 nginx.conf http{} 块添加：
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
limit_conn_zone $binary_remote_addr zone=addr:10m;

# 在 API location 块添加：
limit_req zone=api burst=50 nodelay;
limit_conn addr 50;
```

### 6.3 CORS 配置 [MEDIUM-004]

**风险等级: MEDIUM**

**文件**: `/Users/lichun/tunxiang/apps/api-gateway/src/core/config.py` 第 169 行

当前 CORS 配置 `allow_origins` 默认值为 `["http://localhost:3000", "http://localhost:5173"]`，这在开发环境可以，但生产环境需确认已通过环境变量覆盖为实际域名（如 `https://admin.zlsjos.cn`）。`allow_credentials=True` 与过于宽松的 origins 组合可能导致 CSRF 攻击。

### 6.4 /metrics 端点访问控制 [OK]

**文件**: `/Users/lichun/tunxiang/nginx/conf.d/default.conf` 第 57-62 行

`/metrics` 端点已限制为内网访问（10.0.0.0/8、172.16.0.0/12、192.168.0.0/16），配置合理。

### 6.5 未匹配 Host 处理 [OK]

**文件**: `/Users/lichun/tunxiang/nginx/conf.d/default.conf` 第 131-138 行

未匹配的 Host 返回 444（直接关闭连接），配置合理。

### 6.6 SSL/TLS 配置 [OK]

**文件**: `/Users/lichun/tunxiang/nginx/conf.d/snippets/ssl-common.conf`

- TLSv1.2 + TLSv1.3（已禁用 TLSv1.0/1.1）
- OCSP Stapling 已启用
- session_tickets off（防止前向安全性降级）
- 使用强密码套件

### 6.7 X-Tenant-ID 头注入信任问题 [HIGH-004]

**风险等级: HIGH**

Nginx 通过 `proxy_set_header X-Tenant-ID $tenant_id` 注入租户标识，但需确认：
1. 后端是否信任来自 Nginx 的 `X-Tenant-ID`，且忽略客户端可能伪造的同名 header
2. 对于 `api.zlsjos.cn`（第 126 行），`$tenant_id` 来自 `map` 默认值 `platform_admin`，所有通过 API 域名的请求都会获得 `platform_admin` 权限

---

## 7. 端口最小化建议

### 7.1 生产环境 (`docker-compose.prod.yml`) 端口暴露分析

| 服务 | 映射端口 | 是否需要对外 | 建议 |
|------|---------|------------|------|
| nginx | 80:80, 443:443 | 是 | 保留（HTTP 重定向 + HTTPS） |
| web | 3001:80 | **否** | 移除，应仅通过 Nginx 代理访问 |
| api-gateway | 8000:8000 | **否** | 移除，应仅通过 Nginx 代理访问 |
| redis | 6380:6379 | **否** | 移除，仅容器网络内部访问 |
| redis-sentinel-1 | 26379:26379 | **否** | 移除 |
| redis-sentinel-2 | 26380:26379 | **否** | 移除 |
| redis-sentinel-3 | 26381:26379 | **否** | 移除 |

**风险等级**: HIGH-005 - 生产环境直接暴露 API (8000)、前端 (3001)、Redis (6380)、Sentinel (26379-26381) 端口，攻击者可绕过 Nginx 直接访问。

### 7.2 开发环境 (`docker-compose.yml`) 端口暴露

| 服务 | 映射端口 | 说明 |
|------|---------|------|
| postgres | 5432:5432 | 开发可接受 |
| redis | 6379:6379 | 开发可接受 |
| neo4j | 7687:7687, 7474:7474 | 开发可接受 |
| qdrant | 6333:6333, 6334:6334 | 开发可接受 |
| prometheus | 9090:9090 | 开发可接受 |
| grafana | 3000:3000 | 开发可接受 |

开发环境端口暴露可接受，但需确保这些端口不会在服务器 42.194.229.21 的防火墙上开放。

### 7.3 服务器 42.194.229.21 应开放端口建议

| 端口 | 协议 | 用途 | 来源限制 |
|------|------|------|---------|
| 80 | TCP | HTTP (重定向到 HTTPS) | 0.0.0.0/0 |
| 443 | TCP | HTTPS (主入口) | 0.0.0.0/0 |
| 22 | TCP | SSH 管理 | 仅运维 IP 白名单 |

**所有其他端口应在云防火墙/安全组中关闭。**

---

## 8. 修复优先级清单

### P0 - 立即修复（CRITICAL，影响数据隔离）

| ID | 发现 | 修复动作 |
|----|------|---------|
| CRITICAL-001 | BOM/废弃事件表 RLS 使用错误 session 变量 | 创建新迁移，将 `app.current_store_id` 改为 `app.current_tenant` |
| CRITICAL-002 | RLS NULL 绕过：未设置 tenant 时所有数据可见 | 移除 `OR ... IS NULL` 条件，为管理员创建 BYPASSRLS 角色 |

### P1 - 1 周内修复（HIGH）

| ID | 发现 | 修复动作 |
|----|------|---------|
| HIGH-001 | ORM tenant_filter 仅覆盖 18 张表 | 扩大 `TENANT_TABLES` 覆盖范围至所有含 store_id 的表 |
| HIGH-002 | ORM 过滤器仅拦截 SELECT | 增加 INSERT/UPDATE/DELETE 的 tenant_id 自动注入 |
| HIGH-003 | Nginx 无 rate limiting | 添加 `limit_req_zone` 和 `limit_req` 配置 |
| HIGH-004 | X-Tenant-ID 头信任问题 | 确保后端仅接受 Nginx 注入的 header，清除客户端传入的同名 header |
| HIGH-005 | 生产 docker-compose 暴露过多端口 | 移除 web(3001), api(8000), redis(6380), sentinel(26379-26381) 的端口映射 |

### P2 - 1 个月内修复（MEDIUM）

| ID | 发现 | 修复动作 |
|----|------|---------|
| MEDIUM-001 | disable_tenant_filter 无权限检查 | 增加调用者角色校验 |
| MEDIUM-002 | store_id 过滤使用字符串匹配 | 改用 AST 级别的条件检查 |
| MEDIUM-003 | Nginx 层缺 CSP / Permissions-Policy | 在 security-headers.conf 中添加 |
| MEDIUM-004 | CORS 生产环境配置需确认 | 确认环境变量已覆盖为实际域名 |
| MEDIUM-005 | 32 个模型缺少 tenant_id/store_id | 按 3.1-3.4 中的风险等级逐步添加 |

### P3 - 纳入常规迭代（LOW）

| ID | 发现 | 修复动作 |
|----|------|---------|
| LOW-001 | 为所有新增的含 store_id 表创建 RLS 策略 | 建立 CI 检查：新表必须附带 RLS 迁移 |
| LOW-002 | RLS 品牌隔离策略覆盖不足 | 逐步扩大 rls_002 覆盖范围 |
| LOW-003 | 知识库/配置类表的租户隔离评估 | 评估是否需要品牌级隔离而非门店级 |

---

## 9. 架构层面建议

### 9.1 建立多层防御体系

```
Layer 1: Nginx（rate limit + header 注入 + 端口封锁）
Layer 2: FastAPI 中间件（认证 + 权限 + tenant context 设置）
Layer 3: ORM 过滤器（自动注入 WHERE store_id = ?）
Layer 4: PostgreSQL RLS（数据库层强制隔离，最后防线）
```

当前 Layer 1 和 Layer 4 均有显著缺口，Layer 3 覆盖率仅 ~11%（18/162）。

### 9.2 建议引入 CI 自动化检查

1. **新模型检查**: 每个新增的模型文件必须包含 `store_id` 或 `tenant_id` 字段（或标注为全局表）
2. **RLS 覆盖检查**: 每个含 `store_id` 的迁移脚本必须附带 `ENABLE ROW LEVEL SECURITY` + `CREATE POLICY`
3. **Session 变量一致性检查**: 所有 RLS 策略必须使用 `app.current_tenant`（不允许使用其他变量名）

### 9.3 建议使用独立数据库角色

| 角色 | 属性 | 用途 |
|------|------|------|
| `app_user` | NOINHERIT, 不含 BYPASSRLS | 应用层连接使用 |
| `app_admin` | BYPASSRLS | 迁移、管理员操作 |
| `app_readonly` | NOINHERIT, 不含 BYPASSRLS | 只读查询、报表 |

当前系统似乎使用单一数据库用户 `zhilian`，未区分角色。

---

*报告结束。此审计基于静态代码分析，未连接实际数据库或扫描服务器端口。建议在修复后进行渗透测试验证。*
