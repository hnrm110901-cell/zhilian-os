# 前后端认证集成指南

## 概述

智链OS现已完成前后端认证集成，实现了基于JWT令牌的用户认证和授权系统。

## 架构设计

### 后端 (FastAPI)
- **认证端点**: `/api/v1/auth/login`, `/api/v1/auth/me`
- **JWT令牌**: 使用HS256算法，24小时有效期
- **密码加密**: bcrypt哈希算法
- **权限控制**: 基于角色的访问控制(RBAC)

### 前端 (React)
- **认证上下文**: AuthContext提供全局认证状态
- **令牌管理**: localStorage持久化存储
- **自动刷新**: 页面加载时自动验证令牌
- **受保护路由**: ProtectedRoute组件保护需要认证的页面

## 用户角色

系统支持三种用户角色:

1. **ADMIN (管理员)**
   - 完全访问权限
   - 可管理用户
   - 可访问所有功能

2. **STORE_MANAGER (店长)**
   - 门店管理权限
   - 可查看报表
   - 可管理员工

3. **STAFF (员工)**
   - 基础操作权限
   - 可使用日常功能
   - 受限访问

## 快速开始

### 1. 初始化数据库用户

```bash
cd apps/api-gateway
python3 scripts/init_users.py
```

这将创建三个测试用户:
- `admin / admin123` (管理员)
- `manager / manager123` (店长)
- `staff / staff123` (员工)

### 2. 启动服务

```bash
# 启动后端
cd apps/api-gateway
uvicorn src.main:app --reload

# 启动前端
cd apps/web
npm run dev
```

### 3. 登录测试

访问 `http://localhost:5173/login` 使用测试账号登录。

## API使用

### 登录

```typescript
import { authAPI } from '@/utils/apiClient';

const response = await authAPI.login('admin', 'admin123');
// 返回: { access_token, token_type, expires_in, user }
```

### 获取当前用户

```typescript
const user = await authAPI.getCurrentUser();
// 返回: { id, username, email, full_name, role, store_id, is_active }
```

### 调用受保护的API

```typescript
import { apiClient } from '@/utils/apiClient';

// 自动添加Authorization头部
const data = await apiClient.get('/agents/schedule');
```

## 前端集成

### 使用认证上下文

```typescript
import { useAuth } from '@/contexts/AuthContext';

function MyComponent() {
  const { user, isAuthenticated, login, logout } = useAuth();

  if (!isAuthenticated) {
    return <div>请先登录</div>;
  }

  return (
    <div>
      <p>欢迎, {user?.full_name}</p>
      <button onClick={logout}>退出</button>
    </div>
  );
}
```

### 保护路由

```typescript
import ProtectedRoute from '@/components/ProtectedRoute';

<Route path="/admin" element={
  <ProtectedRoute requiredRole="admin">
    <AdminPage />
  </ProtectedRoute>
} />
```

## 安全特性

### 1. JWT令牌
- 使用HS256算法签名
- 包含用户ID、用户名、角色信息
- 24小时自动过期

### 2. 密码安全
- bcrypt哈希算法
- 自动加盐
- 不可逆加密

### 3. 令牌验证
- 每次请求验证令牌有效性
- 过期自动跳转登录页
- 无效令牌自动清除

### 4. HTTPS支持
- 生产环境强制HTTPS
- 防止令牌被窃取

## API端点

### 认证相关

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/v1/auth/login` | POST | 用户登录 | 否 |
| `/api/v1/auth/me` | GET | 获取当前用户 | 是 |
| `/api/v1/auth/me` | PUT | 更新用户信息 | 是 |
| `/api/v1/auth/change-password` | POST | 修改密码 | 是 |
| `/api/v1/auth/register` | POST | 注册用户 | 是(管理员) |

### Agent相关

所有Agent端点都需要认证:

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/agents/schedule` | POST | 排班Agent |
| `/api/v1/agents/order` | POST | 订单Agent |
| `/api/v1/agents/inventory` | POST | 库存Agent |
| `/api/v1/agents/service` | POST | 服务Agent |
| `/api/v1/agents/training` | POST | 培训Agent |
| `/api/v1/agents/decision` | POST | 决策Agent |
| `/api/v1/agents/reservation` | POST | 预定Agent |

## 错误处理

### 401 Unauthorized
- 令牌无效或过期
- 自动跳转到登录页

### 403 Forbidden
- 权限不足
- 跳转到未授权页面

### 400 Bad Request
- 用户名或密码错误
- 显示错误提示

## 开发建议

### 1. 令牌刷新
当前令牌有效期为24小时，建议实现自动刷新机制:

```typescript
// 在API客户端中添加令牌刷新逻辑
if (response.status === 401) {
  // 尝试刷新令牌
  await refreshToken();
  // 重试原请求
}
```

### 2. 记住我功能
可以添加"记住我"选项，延长令牌有效期:

```typescript
const login = async (username, password, rememberMe) => {
  // 如果rememberMe为true，使用更长的过期时间
};
```

### 3. 多设备登录
当前支持多设备同时登录，如需限制可以:
- 在数据库中记录活跃令牌
- 登录时使旧令牌失效

## 测试

### 单元测试
```bash
# 后端测试
cd apps/api-gateway
pytest tests/test_auth_service.py

# 前端测试
cd apps/web
npm test
```

### 集成测试
```bash
# API集成测试
pytest tests/test_api_integration.py
```

## 故障排查

### 问题: 登录后立即退出
**原因**: 令牌验证失败
**解决**: 检查后端SECRET_KEY配置

### 问题: 无法访问受保护路由
**原因**: 令牌未正确存储
**解决**: 检查localStorage中的token

### 问题: 401错误
**原因**: 令牌过期或无效
**解决**: 重新登录获取新令牌

## 下一步

- [ ] 实现令牌自动刷新
- [ ] 添加OAuth2.0支持
- [ ] 实现双因素认证(2FA)
- [ ] 添加登录日志记录
- [ ] 实现会话管理

## 参考资料

- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [JWT.io](https://jwt.io/)
- [React Context API](https://react.dev/reference/react/useContext)

---

**更新时间**: 2024-02-18
**版本**: 1.0.0
