# API文档

## 概述

智链OS API Gateway提供RESTful API接口，支持任务管理、对账、通知等核心业务功能。

**Base URL**: `http://localhost:8000/api/v1`

**认证方式**: Bearer Token (JWT)

## 认证

所有API请求需要在Header中包含JWT Token:

```
Authorization: Bearer <your_jwt_token>
```

### 获取Token

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password"
  }'
```

响应:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

## 任务管理 API

### 1. 创建任务

创建新的任务并可选择指派给特定用户。

**端点**: `POST /tasks`

**请求体**:
```json
{
  "title": "检查库存",
  "content": "检查所有商品的库存情况，确保没有缺货",
  "assignee_id": "550e8400-e29b-41d4-a716-446655440000",
  "category": "库存管理",
  "priority": "high",
  "due_at": "2026-02-25T18:00:00Z"
}
```

**参数说明**:
- `title` (必填): 任务标题，1-200字符
- `content` (必填): 任务详细内容
- `assignee_id` (可选): 指派人的UUID
- `category` (可选): 任务类别（如：开店流程、关店流程、卫生检查等）
- `priority` (可选): 优先级，可选值: `low`, `normal`, `high`, `urgent`，默认`normal`
- `due_at` (可选): 截止时间，ISO 8601格式

**curl示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "检查库存",
    "content": "检查所有商品的库存情况",
    "priority": "high",
    "due_at": "2026-02-25T18:00:00Z"
  }'
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "title": "检查库存",
    "content": "检查所有商品的库存情况",
    "status": "pending",
    "priority": "high",
    "store_id": "store_001",
    "creator_id": "550e8400-e29b-41d4-a716-446655440000",
    "assignee_id": null,
    "due_at": "2026-02-25T18:00:00Z",
    "created_at": "2026-02-21T10:00:00Z",
    "updated_at": "2026-02-21T10:00:00Z"
  },
  "message": "任务创建成功"
}
```

---

### 2. 获取任务列表

获取当前用户相关的任务列表，支持按状态、优先级、分配人筛选。

**端点**: `GET /tasks`

**查询参数**:
- `status` (可选): 任务状态，可选值: `pending`, `in_progress`, `completed`, `cancelled`, `overdue`
- `priority` (可选): 优先级，可选值: `low`, `normal`, `high`, `urgent`
- `assignee_id` (可选): 指派人ID
- `skip` (可选): 跳过记录数，默认0
- `limit` (可选): 返回记录数，默认20

**curl示例**:
```bash
# 获取所有待处理任务
curl -X GET "http://localhost:8000/api/v1/tasks?status=pending" \
  -H "Authorization: Bearer <token>"

# 获取高优先级任务
curl -X GET "http://localhost:8000/api/v1/tasks?priority=high&limit=10" \
  -H "Authorization: Bearer <token>"
```

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "title": "检查库存",
      "status": "pending",
      "priority": "high",
      "due_at": "2026-02-25T18:00:00Z",
      "created_at": "2026-02-21T10:00:00Z"
    }
  ],
  "total": 1
}
```

---

### 3. 获取任务详情

获取指定任务的详细信息。

**端点**: `GET /tasks/{task_id}`

**curl示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "title": "检查库存",
    "content": "检查所有商品的库存情况",
    "status": "pending",
    "priority": "high",
    "store_id": "store_001",
    "creator_id": "550e8400-e29b-41d4-a716-446655440000",
    "assignee_id": null,
    "due_at": "2026-02-25T18:00:00Z",
    "started_at": null,
    "completed_at": null,
    "result": null,
    "attachments": null,
    "created_at": "2026-02-21T10:00:00Z",
    "updated_at": "2026-02-21T10:00:00Z"
  }
}
```

---

### 4. 更新任务状态

更新任务的状态（如开始、完成、取消等）。

**端点**: `PUT /tasks/{task_id}/status`

**请求体**:
```json
{
  "status": "in_progress"
}
```

**状态说明**:
- `pending`: 待处理
- `in_progress`: 进行中
- `completed`: 已完成
- `cancelled`: 已取消
- `overdue`: 已逾期

**curl示例**:
```bash
curl -X PUT "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000/status" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_progress"
  }'
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "in_progress",
    "started_at": "2026-02-21T11:00:00Z",
    "updated_at": "2026-02-21T11:00:00Z"
  },
  "message": "任务状态更新成功"
}
```

---

### 5. 完成任务

标记任务为已完成，可以添加结果和附件。

**端点**: `POST /tasks/{task_id}/complete`

**请求体**:
```json
{
  "result": "库存检查完成，所有商品库存正常",
  "attachments": "[\"https://example.com/report.pdf\"]"
}
```

**curl示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000/complete" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "result": "库存检查完成，所有商品库存正常"
  }'
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "completed",
    "result": "库存检查完成，所有商品库存正常",
    "completed_at": "2026-02-21T12:00:00Z",
    "updated_at": "2026-02-21T12:00:00Z"
  },
  "message": "任务已完成"
}
```

---

### 6. 指派任务

将任务指派给特定用户。

**端点**: `POST /tasks/{task_id}/assign`

**请求体**:
```json
{
  "assignee_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**curl示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000/assign" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "assignee_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "assignee_id": "550e8400-e29b-41d4-a716-446655440000",
    "updated_at": "2026-02-21T10:30:00Z"
  },
  "message": "任务指派成功"
}
```

---

### 7. 删除任务

删除指定的任务（软删除）。

**端点**: `DELETE /tasks/{task_id}`

**curl示例**:
```bash
curl -X DELETE "http://localhost:8000/api/v1/tasks/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

**响应**:
```json
{
  "success": true,
  "message": "任务删除成功"
}
```

---

## 对账管理 API

### 1. 执行对账

执行POS系统与实际订单的对账操作。

**端点**: `POST /reconciliation/perform`

**请求体**:
```json
{
  "reconciliation_date": "2026-02-20",
  "threshold": 2.0
}
```

**参数说明**:
- `reconciliation_date` (可选): 对账日期，默认为昨天
- `threshold` (可选): 差异阈值百分比，默认2%，范围0-100

**curl示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/reconciliation/perform" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "reconciliation_date": "2026-02-20",
    "threshold": 2.0
  }'
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "789e4567-e89b-12d3-a456-426614174000",
    "store_id": "store_001",
    "reconciliation_date": "2026-02-20",
    "pos_total_amount": 50000,
    "pos_order_count": 120,
    "pos_transaction_count": 125,
    "actual_total_amount": 49800,
    "actual_order_count": 119,
    "actual_transaction_count": 124,
    "diff_amount": 200,
    "diff_ratio": 0.4,
    "diff_order_count": 1,
    "diff_transaction_count": 1,
    "status": "matched",
    "alert_sent": "false",
    "created_at": "2026-02-21T02:00:00Z"
  },
  "message": "对账完成"
}
```

**状态说明**:
- `pending`: 待处理
- `matched`: 匹配（差异在阈值内）
- `mismatched`: 不匹配（差异超过阈值）
- `confirmed`: 已确认
- `investigating`: 调查中

---

### 2. 获取对账记录列表

获取对账记录列表，支持按状态和日期筛选。

**端点**: `GET /reconciliation/records`

**查询参数**:
- `status` (可选): 对账状态
- `start_date` (可选): 开始日期
- `end_date` (可选): 结束日期
- `skip` (可选): 跳过记录数，默认0
- `limit` (可选): 返回记录数，默认20

**curl示例**:
```bash
# 获取所有不匹配的对账记录
curl -X GET "http://localhost:8000/api/v1/reconciliation/records?status=mismatched" \
  -H "Authorization: Bearer <token>"

# 获取指定日期范围的对账记录
curl -X GET "http://localhost:8000/api/v1/reconciliation/records?start_date=2026-02-01&end_date=2026-02-20" \
  -H "Authorization: Bearer <token>"
```

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "id": "789e4567-e89b-12d3-a456-426614174000",
      "store_id": "store_001",
      "reconciliation_date": "2026-02-20",
      "status": "matched",
      "diff_amount": 200,
      "diff_ratio": 0.4,
      "created_at": "2026-02-21T02:00:00Z"
    }
  ],
  "total": 1
}
```

---

### 3. 获取对账记录详情

获取指定对账记录的详细信息。

**端点**: `GET /reconciliation/records/{record_id}`

**curl示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/reconciliation/records/789e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "789e4567-e89b-12d3-a456-426614174000",
    "store_id": "store_001",
    "reconciliation_date": "2026-02-20",
    "pos_total_amount": 50000,
    "pos_order_count": 120,
    "actual_total_amount": 49800,
    "actual_order_count": 119,
    "diff_amount": 200,
    "diff_ratio": 0.4,
    "status": "matched",
    "discrepancies": [],
    "notes": null,
    "resolution": null,
    "alert_sent": "false",
    "created_at": "2026-02-21T02:00:00Z",
    "updated_at": "2026-02-21T02:00:00Z"
  }
}
```

---

### 4. 确认对账记录

确认对账记录并添加解决方案说明。

**端点**: `POST /reconciliation/records/{record_id}/confirm`

**请求体**:
```json
{
  "resolution": "差异已核实，为退款订单导致"
}
```

**curl示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/reconciliation/records/789e4567-e89b-12d3-a456-426614174000/confirm" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "resolution": "差异已核实，为退款订单导致"
  }'
```

**响应**:
```json
{
  "success": true,
  "data": {
    "id": "789e4567-e89b-12d3-a456-426614174000",
    "status": "confirmed",
    "resolution": "差异已核实，为退款订单导致",
    "confirmed_by": "550e8400-e29b-41d4-a716-446655440000",
    "confirmed_at": "2026-02-21T10:00:00Z",
    "updated_at": "2026-02-21T10:00:00Z"
  },
  "message": "对账记录已确认"
}
```

---

## 错误响应

所有API在发生错误时返回统一的错误格式:

```json
{
  "detail": "错误描述信息"
}
```

**常见HTTP状态码**:
- `200`: 成功
- `400`: 请求参数错误
- `401`: 未认证或Token无效
- `403`: 无权限访问
- `404`: 资源不存在
- `500`: 服务器内部错误

---

## 通知集成

任务和对账系统会自动通过企业微信发送通知:

### 任务通知
- **任务创建**: 通知被指派人
- **任务完成**: 通知创建人

### 对账通知
- **对账异常**: 当差异超过阈值时，通知门店管理员

---

## 速率限制

API请求受到速率限制保护:
- 每个用户每分钟最多100个请求
- 超过限制将返回429状态码

---

## 完整示例

### Python示例

```python
import requests

# 配置
BASE_URL = "http://localhost:8000/api/v1"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# 创建任务
task_data = {
    "title": "检查库存",
    "content": "检查所有商品的库存情况",
    "priority": "high",
    "due_at": "2026-02-25T18:00:00Z"
}

response = requests.post(
    f"{BASE_URL}/tasks",
    json=task_data,
    headers=headers
)

task = response.json()["data"]
print(f"任务创建成功: {task['id']}")

# 获取任务列表
response = requests.get(
    f"{BASE_URL}/tasks?status=pending",
    headers=headers
)

tasks = response.json()["data"]
print(f"待处理任务数: {len(tasks)}")

# 执行对账
reconciliation_data = {
    "reconciliation_date": "2026-02-20",
    "threshold": 2.0
}

response = requests.post(
    f"{BASE_URL}/reconciliation/perform",
    json=reconciliation_data,
    headers=headers
)

record = response.json()["data"]
print(f"对账完成，状态: {record['status']}")
```

### JavaScript示例

```javascript
const BASE_URL = 'http://localhost:8000/api/v1';
const TOKEN = 'your_jwt_token_here';

const headers = {
  'Authorization': `Bearer ${TOKEN}`,
  'Content-Type': 'application/json'
};

// 创建任务
async function createTask() {
  const response = await fetch(`${BASE_URL}/tasks`, {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({
      title: '检查库存',
      content: '检查所有商品的库存情况',
      priority: 'high',
      due_at: '2026-02-25T18:00:00Z'
    })
  });

  const data = await response.json();
  console.log('任务创建成功:', data.data.id);
}

// 获取任务列表
async function getTasks() {
  const response = await fetch(`${BASE_URL}/tasks?status=pending`, {
    headers: headers
  });

  const data = await response.json();
  console.log('待处理任务数:', data.data.length);
}

// 执行对账
async function performReconciliation() {
  const response = await fetch(`${BASE_URL}/reconciliation/perform`, {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({
      reconciliation_date: '2026-02-20',
      threshold: 2.0
    })
  });

  const data = await response.json();
  console.log('对账完成，状态:', data.data.status);
}
```

---

## 更多信息

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/health
- **Prometheus指标**: http://localhost:8000/metrics
