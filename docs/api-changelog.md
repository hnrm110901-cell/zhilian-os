# API 变更日志

本文档记录智链OS API的所有重要变更。

## [1.0.0] - 2024-02-18

### 新增功能

#### 权限管理系统
- 添加基于角色的访问控制(RBAC)
- 支持13种角色类型
- 细粒度权限控制（agent、user、store、system）
- 新增 `GET /api/v1/auth/me/permissions` 端点获取用户权限

#### 令牌刷新机制
- 访问令牌有效期调整为30分钟
- 刷新令牌有效期设为7天
- 新增 `POST /api/v1/auth/refresh` 端点刷新访问令牌
- 令牌中添加类型字段区分访问令牌和刷新令牌

#### Agent权限保护
- 所有Agent端点添加权限检查
- `/agents/schedule` 需要 `agent:schedule:write` 权限
- `/agents/order` 需要 `agent:order:write` 权限
- `/agents/inventory` 需要 `agent:inventory:write` 权限
- `/agents/service` 需要 `agent:service:write` 权限
- `/agents/training` 需要 `agent:training:write` 权限
- `/agents/decision` 需要 `agent:decision:read` 权限
- `/agents/reservation` 需要 `agent:reservation:write` 权限

### 性能优化

#### 数据库查询优化
- 修复decision_service中的N+1查询问题
- 修复inventory_service中的N+1查询问题
- 添加数据库复合索引提升查询性能

#### API响应优化
- KPI报告生成速度提升约90%
- 库存补货提醒生成速度提升约85%
- 常见查询模式速度提升50-70%

### 文档改进

#### API文档完善
- 添加详细的端点描述和使用说明
- 添加请求/响应示例
- 添加错误响应说明
- 添加认证和权限要求说明
- 创建API使用指南文档
- 创建API变更日志

### 破坏性变更

#### 认证系统
- ⚠️ 访问令牌有效期从24小时缩短至30分钟
  - **影响**: 客户端需要实现令牌刷新机制
  - **迁移**: 使用刷新令牌定期更新访问令牌

#### Agent端点权限
- ⚠️ 所有Agent端点现在需要特定权限
  - **影响**: 非管理员用户可能无法访问某些Agent
  - **迁移**: 确保用户拥有所需权限，或使用管理员账户

### 已知问题

- 健康检查端点未检查数据库和Redis连接状态
- 缺少API速率限制
- 缺少请求日志记录

---

## [0.1.0] - 2024-02-17

### 初始版本

#### 核心功能
- 用户认证系统（登录、注册）
- 7个智能Agent系统
- 健康检查端点
- 基础CRUD操作

#### Agent系统
- ScheduleAgent - 智能排班
- OrderAgent - 订单协同
- InventoryAgent - 库存预警
- ServiceAgent - 服务质量
- TrainingAgent - 培训辅导
- DecisionAgent - 决策支持
- ReservationAgent - 预定宴会

#### 认证
- JWT访问令牌（24小时有效期）
- 基础用户角色（admin, manager, staff）

---

## 版本规范

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)规范：

- **主版本号**: 不兼容的API变更
- **次版本号**: 向下兼容的功能新增
- **修订号**: 向下兼容的问题修正

## 变更类型

- `新增功能`: 新增的功能或端点
- `性能优化`: 性能改进
- `文档改进`: 文档更新
- `破坏性变更`: 不向下兼容的变更
- `已知问题`: 当前版本的已知问题
- `安全修复`: 安全漏洞修复
- `Bug修复`: 问题修复
- `废弃`: 即将移除的功能

## 迁移指南

### 从 0.1.0 升级到 1.0.0

#### 1. 实现令牌刷新机制

**旧代码**:
```python
# 访问令牌24小时有效，无需刷新
headers = {"Authorization": f"Bearer {access_token}"}
```

**新代码**:
```python
# 访问令牌30分钟有效，需要刷新机制
def get_headers():
    if is_token_expired(access_token):
        refresh_access_token()
    return {"Authorization": f"Bearer {access_token}"}
```

#### 2. 检查用户权限

**旧代码**:
```python
# 所有认证用户都可以访问Agent
response = requests.post(
    f"{base_url}/agents/schedule",
    headers={"Authorization": f"Bearer {access_token}"},
    json=request_data
)
```

**新代码**:
```python
# 需要检查用户是否有相应权限
permissions = get_user_permissions()
if "agent:schedule:write" in permissions:
    response = requests.post(
        f"{base_url}/agents/schedule",
        headers={"Authorization": f"Bearer {access_token}"},
        json=request_data
    )
else:
    print("权限不足")
```

#### 3. 处理401错误

**新代码**:
```python
def make_request(url, data):
    response = requests.post(url, headers=get_headers(), json=data)

    if response.status_code == 401:
        # 尝试刷新令牌
        if refresh_access_token():
            # 重试请求
            response = requests.post(url, headers=get_headers(), json=data)
        else:
            # 刷新失败，需要重新登录
            login()

    return response
```

## 未来计划

### v1.1.0 (计划中)
- [ ] API速率限制
- [ ] 请求日志记录
- [ ] WebSocket支持
- [ ] 批量操作API

### v1.2.0 (计划中)
- [ ] GraphQL API
- [ ] API版本控制
- [ ] 数据导出API
- [ ] 高级过滤和排序

### v2.0.0 (规划中)
- [ ] 微服务架构重构
- [ ] gRPC支持
- [ ] 事件驱动架构
- [ ] 多租户支持
