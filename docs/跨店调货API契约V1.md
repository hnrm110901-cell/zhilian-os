# 跨店调货 API 契约 V1

更新时间：2026-03-08  
适用范围：`/api/v1/inventory/transfer-*`

## 1. 目标

提供跨店调货「申请 -> 审批执行/驳回 -> 列表查询」最小闭环接口契约，统一前后端字段与状态语义。

## 2. 状态机

- `pending`：已提交，待审批
- `executed`：审批通过并已执行库存调拨
- `rejected`：审批拒绝，不执行库存变更

状态流转：

1. 申请创建：`pending`
2. 批准执行：`pending -> executed`
3. 驳回：`pending -> rejected`

## 3. 接口清单

### 3.1 创建调货申请

- `POST /api/v1/inventory/transfer-request?store_id={source_store_id}`
- Body：

```json
{
  "source_item_id": "inv-src-1",
  "target_store_id": "S002",
  "target_item_id": "inv-tgt-1",
  "quantity": 8,
  "reason": "晚高峰补货"
}
```

- Response `201`：

```json
{
  "decision_id": "dec-1",
  "status": "pending_approval",
  "transfer": {
    "workflow": "inventory_transfer",
    "source_store_id": "S001",
    "target_store_id": "S002",
    "source_item_id": "inv-src-1",
    "target_item_id": "inv-tgt-1",
    "item_name": "鸡腿",
    "unit": "kg",
    "quantity": 8,
    "reason": "晚高峰补货",
    "requested_by": "u-1"
  }
}
```

### 3.2 查询调货申请列表

- `GET /api/v1/inventory/transfer-requests?store_id=&status=&limit=`
- Query：
  - `store_id`（可选）：按来源或目标门店过滤
  - `status`（可选）：`pending|executed|rejected`
  - `limit`（可选）：默认 `50`

- Response `200`：

```json
{
  "total": 1,
  "items": [
    {
      "decision_id": "dec-1",
      "status": "pending",
      "source_store_id": "S001",
      "target_store_id": "S002",
      "source_item_id": "inv-src-1",
      "target_item_id": "inv-tgt-1",
      "item_name": "鸡腿",
      "quantity": 8,
      "unit": "kg",
      "reason": "晚高峰补货",
      "manager_feedback": null,
      "created_at": "2026-03-08T10:00:00",
      "approved_at": null,
      "executed_at": null
    }
  ]
}
```

### 3.3 批准并执行调货

- `POST /api/v1/inventory/transfer-requests/{decision_id}/approve`
- Body：

```json
{
  "manager_feedback": "同意调货"
}
```

- Response `200`：

```json
{
  "success": true,
  "decision_id": "dec-1",
  "status": "executed",
  "source_new_quantity": 12,
  "target_new_quantity": 11
}
```

### 3.4 驳回调货申请

- `POST /api/v1/inventory/transfer-requests/{decision_id}/reject`
- Body：

```json
{
  "manager_feedback": "本店库存也紧张"
}
```

- Response `200`：

```json
{
  "success": true,
  "decision_id": "dec-1",
  "status": "rejected"
}
```

## 4. 关键业务规则

1. `quantity` 必须 `> 0`。
2. `target_store_id` 不能与来源 `store_id` 相同。
3. 创建申请阶段会校验来源库存是否足够。
4. 批准执行阶段会再次校验来源库存，避免申请到执行之间库存变化导致负库存。
5. 批准执行会写入两条 `TRANSFER` 流水：
   - 来源门店 `quantity = -X`
   - 目标门店 `quantity = +X`

## 5. 错误语义（常见）

- `400`：参数不合法或业务不满足（如库存不足、重复审批）
- `404`：调货申请或库存项不存在
- `500`：服务内部错误
