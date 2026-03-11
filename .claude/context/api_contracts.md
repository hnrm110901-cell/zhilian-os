# API 契约速查

> 按需加载：当任务涉及前后端接口对接时读取此文件。
> 完整契约详见 `tasks/api-contracts.md`（Claude ↔ Codex 握手文件）。

---

## BFF 聚合端点

### GET `/api/v1/bff/{role}/{store_id}`

| 角色 | 路由 | 首屏数据 |
|------|------|---------|
| `sm` | `/api/v1/bff/sm/{store_id}` | 今日营收/客流/成本率/待办/AI建议 |
| `chef` | `/api/v1/bff/chef/{store_id}` | 库存预警/损耗/采购建议/食材到期 |
| `floor` | `/api/v1/bff/floor/{store_id}` | 排队/预订/翻台率/服务评分 |
| `hq` | `/api/v1/bff/hq/{store_id}` | 多店营收对比/人力成本/决策建议 |

**规则：**
- 每个角色首屏只发 **1个 BFF 请求**
- 30s Redis 缓存 + `?refresh=true` 强制刷新
- 子调用失败 → 返回 `null`，前端用 `ZEmpty` 占位

---

## 通用约定

### 金额字段
- 数据库：存分（fen），`BigInteger`
- API 响应：返回元（yuan），`float` 保留2位小数
- 字段命名：`*_yuan` 或 `*_fen` 显式标注

### 分页
```typescript
interface PaginatedResponse<T> {
  items: T[];
  total: number;    // 真实总量（SELECT COUNT），不是当前页行数
  page: number;
  page_size: number;
}
```

### 多租户
- 所有业务端点必须包含 `store_id` 路径参数
- 跨店端点额外需要 `brand_id` 查询参数

### 错误响应
```typescript
interface ErrorResponse {
  detail: string;
  error_code?: string;
}
```
- 400: 参数校验失败
- 401: 未认证
- 403: 无权限（跨店访问）
- 404: 资源不存在
- 500: 服务端错误（含降级说明）

---

## 关键业务端点

### Workforce（人力管理）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/workforce/stores/{store_id}/employee-health` | 员工健康度/流失风险 |
| GET | `/api/v1/workforce/stores/{store_id}/labor-forecast` | 客流预测→人力需求 |
| GET | `/api/v1/workforce/stores/{store_id}/labor-cost` | 人工成本快照 |
| GET | `/api/v1/workforce/stores/{store_id}/staffing-advice` | 今日排班建议 |
| POST | `/api/v1/workforce/stores/{store_id}/staffing-advice/{id}/confirm` | 店长确认建议 |
| GET | `/api/v1/workforce/stores/{store_id}/labor-cost/ranking` | 跨店成本排名 |

### Banquet（宴会管理）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/banquet/stores/{store_id}/pipeline` | 宴会销售管线 |
| POST | `/api/v1/banquet/stores/{store_id}/leads` | 新建线索 |
| GET | `/api/v1/banquet/stores/{store_id}/quotations` | 报价列表 |
| POST | `/api/v1/banquet/stores/{store_id}/beo` | 生成BEO |
| GET | `/api/v1/banquet/stores/{store_id}/receivables` | 应收账款 |

### Action Plans（L5行动层）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/action-plans/stores/{store_id}` | 行动计划列表 |
| POST | `/api/v1/action-plans/stores/{store_id}/{id}/outcome` | 登记执行结果 |

---

## 前端数据获取规范

```typescript
// 正确：使用 apiClient
const resp = await apiClient.get('/api/v1/bff/sm/S001');

// 禁止：直接 fetch/axios，不引入 TanStack Query
```
