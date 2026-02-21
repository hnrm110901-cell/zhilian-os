# 智链OS API 使用指南

## 概述

智链OS API Gateway 提供了完整的RESTful API接口，用于管理中餐连锁品牌门店的智能运营系统。

## 基础信息

- **Base URL**: `http://localhost/api/v1` (生产环境)
- **Base URL**: `http://localhost:8000/api/v1` (开发环境)
- **API文档**: `http://localhost/docs` (Swagger UI)
- **API文档**: `http://localhost/redoc` (ReDoc)
- **版本**: v1.0.0

## 认证

### 获取访问令牌

大部分API端点需要认证。首先需要登录获取访问令牌：

```bash
curl -X POST "http://localhost/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

响应示例：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

### 使用访问令牌

在后续请求中，在 `Authorization` 头中包含访问令牌：

```bash
curl -X GET "http://localhost/api/v1/auth/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 刷新令牌

访问令牌有效期为30分钟。过期后使用刷新令牌获取新的访问令牌：

```bash
curl -X POST "http://localhost/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

## 权限系统

### 角色类型

系统支持13种角色，每种角色拥有不同的权限：

| 角色 | 说明 | 权限范围 |
|------|------|----------|
| `admin` | 系统管理员 | 所有权限 |
| `store_manager` | 店长 | 门店所有运营权限 |
| `assistant_manager` | 店长助理 | 协助店长管理 |
| `floor_manager` | 楼面经理 | 前厅运营管理 |
| `customer_manager` | 客户经理 | 客户关系和预订 |
| `team_leader` | 领班 | 前厅基层管理 |
| `waiter` | 服务员 | 基础服务操作 |
| `head_chef` | 厨师长 | 后厨全面管理 |
| `station_manager` | 档口负责人 | 档口运营管理 |
| `chef` | 厨师 | 基础后厨操作 |
| `warehouse_manager` | 库管 | 库存管理 |
| `finance` | 财务 | 财务数据访问 |
| `procurement` | 采购 | 采购和库存 |

### 权限类型

权限采用 `资源:操作` 的格式：

- **Agent权限**: `agent:schedule:read`, `agent:order:write` 等
- **用户管理**: `user:read`, `user:write`, `user:delete`
- **门店管理**: `store:read`, `store:write`, `store:delete`
- **系统配置**: `system:config`, `system:logs`

### 查询用户权限

```bash
curl -X GET "http://localhost/api/v1/auth/me/permissions" \
  -H "Authorization: Bearer <access_token>"
```

## Agent系统

### 7个智能Agent

1. **ScheduleAgent** - 智能排班
2. **OrderAgent** - 订单协同
3. **InventoryAgent** - 库存预警
4. **ServiceAgent** - 服务质量
5. **TrainingAgent** - 培训辅导
6. **DecisionAgent** - 决策支持
7. **ReservationAgent** - 预定宴会

### 调用Agent示例

#### 生成决策报告

```bash
curl -X POST "http://localhost/api/v1/agents/decision" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "decision",
    "input_data": {
      "action": "generate_report",
      "params": {
        "store_id": "STORE_001",
        "start_date": "2024-02-01",
        "end_date": "2024-02-18"
      }
    }
  }'
```

#### 生成排班计划

```bash
curl -X POST "http://localhost/api/v1/agents/schedule" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "generate_schedule",
      "params": {
        "store_id": "STORE_001",
        "start_date": "2024-02-20",
        "end_date": "2024-02-26"
      }
    }
  }'
```

## 错误处理

### HTTP状态码

- `200 OK`: 请求成功
- `201 Created`: 资源创建成功
- `400 Bad Request`: 请求参数错误
- `401 Unauthorized`: 未认证或令牌无效
- `403 Forbidden`: 权限不足
- `404 Not Found`: 资源不存在
- `500 Internal Server Error`: 服务器内部错误

### 错误响应格式

```json
{
  "detail": "权限不足,需要以下权限之一: agent:schedule:write"
}
```

## 最佳实践

### 1. 令牌管理

- 安全存储访问令牌和刷新令牌
- 访问令牌过期前主动刷新
- 刷新令牌过期后要求用户重新登录
- 不要在URL中传递令牌

### 2. 错误处理

- 始终检查HTTP状态码
- 处理401错误时自动刷新令牌
- 处理403错误时提示用户权限不足
- 实现重试机制处理临时性错误

### 3. 性能优化

- 使用HTTP缓存头
- 批量请求时使用并发
- 避免频繁轮询，使用WebSocket或长轮询
- 合理设置请求超时时间

### 4. 安全建议

- 使用HTTPS传输
- 定期更新访问令牌
- 实现请求签名验证
- 记录和监控异常访问

## 示例代码

### Python

```python
import requests

class ZhilianOSClient:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.access_token = None
        self.refresh_token = None
        self.login(username, password)

    def login(self, username, password):
        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password}
        )
        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]

    def get_headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def get_decision_report(self, store_id, start_date, end_date):
        response = requests.post(
            f"{self.base_url}/agents/decision",
            headers=self.get_headers(),
            json={
                "agent_type": "decision",
                "input_data": {
                    "action": "generate_report",
                    "params": {
                        "store_id": store_id,
                        "start_date": start_date,
                        "end_date": end_date
                    }
                }
            }
        )
        return response.json()

# 使用示例
client = ZhilianOSClient("http://localhost/api/v1", "admin", "admin123")
report = client.get_decision_report("STORE_001", "2024-02-01", "2024-02-18")
print(report)
```

### JavaScript/TypeScript

```typescript
class ZhilianOSClient {
  private baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  async login(username: string, password: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
  }

  private getHeaders(): HeadersInit {
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.accessToken}`,
    };
  }

  async getDecisionReport(
    storeId: string,
    startDate: string,
    endDate: string
  ): Promise<any> {
    const response = await fetch(`${this.baseUrl}/agents/decision`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({
        agent_type: 'decision',
        input_data: {
          action: 'generate_report',
          params: { store_id: storeId, start_date: startDate, end_date: endDate },
        },
      }),
    });

    return response.json();
  }
}

// 使用示例
const client = new ZhilianOSClient('http://localhost/api/v1');
await client.login('admin', 'admin123');
const report = await client.getDecisionReport('STORE_001', '2024-02-01', '2024-02-18');
console.log(report);
```

## 支持

如有问题或建议，请联系：

- **邮箱**: support@zhilian-os.com
- **GitHub**: https://github.com/zhilian-os/api-gateway/issues
- **文档**: http://localhost/docs
