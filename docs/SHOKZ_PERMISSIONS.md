# Shokz耳机权限配置说明

智链OS为Shokz骨传导耳机提供了细粒度的权限控制，确保不同角色的用户只能访问其职责范围内的功能。

## 权限类型

### 1. voice:device:read
**查看语音设备权限**

允许用户查看Shokz设备信息和列表。

**适用API端点：**
- `GET /api/v1/voice/devices` - 列出所有设备
- `GET /api/v1/voice/devices/{device_id}` - 获取设备详情

**拥有此权限的角色：**
- 管理员 (admin)
- 店长 (store_manager)
- 店长助理 (assistant_manager)
- 楼面经理 (floor_manager)
- 领班 (team_leader)
- 服务员 (waiter)
- 厨师长 (head_chef)
- 档口负责人 (station_manager)
- 厨师 (chef)

### 2. voice:device:write
**配置语音设备权限**

允许用户注册、连接、断开Shokz设备。

**适用API端点：**
- `POST /api/v1/voice/devices/register` - 注册新设备
- `POST /api/v1/voice/devices/{device_id}/connect` - 连接设备
- `POST /api/v1/voice/devices/{device_id}/disconnect` - 断开设备

**拥有此权限的角色：**
- 管理员 (admin)
- 店长 (store_manager)
- 店长助理 (assistant_manager)
- 楼面经理 (floor_manager)
- 厨师长 (head_chef)

### 3. voice:device:delete
**删除语音设备权限**

允许用户删除已注册的Shokz设备。

**适用API端点：**
- `DELETE /api/v1/voice/devices/{device_id}` - 删除设备

**拥有此权限的角色：**
- 管理员 (admin)
- 店长 (store_manager)

### 4. voice:command
**使用语音命令权限**

允许用户通过Shokz设备发送语音命令。

**适用API端点：**
- `POST /api/v1/voice/command` - 处理语音命令
- `POST /api/v1/voice/command/upload` - 上传音频处理命令

**拥有此权限的角色：**
- 管理员 (admin)
- 店长 (store_manager)
- 店长助理 (assistant_manager)
- 楼面经理 (floor_manager)
- 领班 (team_leader)
- 服务员 (waiter)
- 厨师长 (head_chef)
- 档口负责人 (station_manager)
- 厨师 (chef)

### 5. voice:notification
**发送语音通知权限**

允许用户向Shokz设备发送语音通知。

**适用API端点：**
- `POST /api/v1/voice/notification` - 发送语音通知

**拥有此权限的角色：**
- 管理员 (admin)
- 店长 (store_manager)
- 店长助理 (assistant_manager)
- 楼面经理 (floor_manager)
- 厨师长 (head_chef)

## 角色权限矩阵

| 角色 | 查看设备 | 配置设备 | 删除设备 | 语音命令 | 语音通知 |
|------|---------|---------|---------|---------|---------|
| 管理员 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 店长 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 店长助理 | ✅ | ✅ | ❌ | ✅ | ✅ |
| 楼面经理 | ✅ | ✅ | ❌ | ✅ | ✅ |
| 领班 | ✅ | ❌ | ❌ | ✅ | ❌ |
| 服务员 | ✅ | ❌ | ❌ | ✅ | ❌ |
| 厨师长 | ✅ | ✅ | ❌ | ✅ | ✅ |
| 档口负责人 | ✅ | ❌ | ❌ | ✅ | ❌ |
| 厨师 | ✅ | ❌ | ❌ | ✅ | ❌ |

## 使用场景

### 场景1：前厅服务员使用耳机
**角色：** 服务员 (waiter)

**可以做：**
- 查看自己的耳机设备信息
- 使用语音命令查询订单、预订信息
- 接收来自系统的语音通知（被动接收）

**不能做：**
- 注册或配置新耳机
- 主动发送语音通知给其他人
- 删除设备

### 场景2：楼面经理管理前厅设备
**角色：** 楼面经理 (floor_manager)

**可以做：**
- 查看所有前厅设备
- 注册新的OpenComm 2设备
- 连接/断开设备
- 使用语音命令
- 向前厅员工发送语音通知

**不能做：**
- 删除设备（需要店长权限）
- 管理后厨设备（权限范围限制）

### 场景3：厨师长管理后厨设备
**角色：** 厨师长 (head_chef)

**可以做：**
- 查看所有后厨设备
- 注册新的OpenRun Pro 2设备
- 连接/断开设备
- 使用语音命令查询订单、库存
- 向后厨员工发送语音通知

**不能做：**
- 删除设备（需要店长权限）

### 场景4：店长全面管理
**角色：** 店长 (store_manager)

**可以做：**
- 所有Shokz设备相关操作
- 管理前厅和后厨所有设备
- 删除不再使用的设备
- 配置设备角色和权限

## 权限检查流程

1. **用户发起请求** → 携带JWT令牌
2. **API网关验证** → 检查令牌有效性
3. **权限中间件** → 验证用户角色是否拥有所需权限
4. **执行操作** → 权限通过后执行实际操作

## 错误响应

### 403 Forbidden - 权限不足
```json
{
  "detail": "权限不足: 需要 voice:device:write 权限"
}
```

### 401 Unauthorized - 未认证
```json
{
  "detail": "未提供有效的认证令牌"
}
```

## 自定义权限配置

如果需要为特定角色添加或移除Shokz权限，请修改：

**文件位置：** `/apps/api-gateway/src/core/permissions.py`

**示例：为客户经理添加语音通知权限**

```python
UserRole.CUSTOMER_MANAGER: {
    # ... 其他权限
    Permission.VOICE_NOTIFICATION,  # 添加此行
},
```

修改后需要重启API服务器使配置生效。

## 安全建议

1. **最小权限原则**：只授予用户完成工作所需的最小权限
2. **定期审计**：定期检查用户权限配置，移除不必要的权限
3. **设备绑定**：建议将设备与特定用户绑定，避免设备共享
4. **日志记录**：所有设备操作都会记录在审计日志中
5. **权限变更通知**：权限变更时应通知相关用户

## 常见问题

### Q: 为什么服务员不能注册设备？
A: 设备注册涉及系统配置，应由管理人员（楼面经理及以上）负责，确保设备正确配置和管理。

### Q: 如何临时授予某个用户更高权限？
A: 可以通过管理员账号在用户管理界面临时提升用户角色，或者为该用户创建临时的管理员账号。

### Q: 权限检查会影响性能吗？
A: 权限检查在内存中进行，性能影响极小（< 1ms），不会影响用户体验。

### Q: 可以为单个用户自定义权限吗？
A: 当前系统基于角色的权限控制（RBAC），如需为单个用户自定义权限，建议创建新的角色或使用用户组功能。

## 相关文档

- [Shokz集成报告](../SHOKZ_INTEGRATION_REPORT.md)
- [权限系统设计](./PERMISSIONS.md)
- [API文档](./API.md)
