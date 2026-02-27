# FCT 最小工作台对接说明

本文档说明如何通过现有 FCT API 实现**财务最小工作台**能力：凭证列表/详情、手工凭证、过账、总账余额/明细、资金录入。前端或第三方系统可按需调用以下接口组成工作台。

---

## 一、认证与基础路径

| 形态 | 认证 | 基础路径 |
|------|------|----------|
| **合并形态**（智链OS 内） | JWT + 权限 `FCT_READ` / `FCT_WRITE` | `GET/POST/PATCH` 需带智链OS 登录 Token；路径前缀 `/api/v1/fct` |
| **独立形态** | 请求头 `X-API-Key: <FCT_API_KEY>` | 独立服务根路径下同一路径，如 `/api/v1/fct` 或 `/api/v1` |

以下路径均相对于 FCT 前缀（如 `/api/v1/fct`）。

---

## 二、工作台核心接口一览

| 能力 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 凭证列表 | GET | `/vouchers` | 分页，可按 tenant_id、entity_id、start_date、end_date、status 筛选 |
| 凭证详情 | GET | `/vouchers/{voucher_id}` | 含分录 |
| **手工凭证创建** | POST | `/vouchers` | 见下请求体 |
| **凭证过账/状态变更** | PATCH | `/vouchers/{voucher_id}/status` | body: `{ "status": "posted" \| "rejected" \| "approved" }` |
| 总账余额 | GET | `/ledger/balances` | 按科目汇总（默认仅已过账），可选 `posted_only=false` |
| **总账明细** | GET | `/ledger/entries` | 按科目+主体+日期范围返回每条分录，支持 account_code 筛选 |
| 资金流水 | GET | `/cash/transactions` | 分页列表 |
| **资金录入** | POST | `/cash/transactions` | 收/付款录入，可选同时生成凭证 |

---

## 三、手工凭证创建（POST /vouchers）

**请求体（合并形态 Pydantic，独立形态 Dict 同结构）**：

```json
{
  "tenant_id": "T001",
  "entity_id": "STORE_001",
  "biz_date": "2025-02-26",
  "description": "计提工资",
  "lines": [
    { "account_code": "6602", "account_name": "管理费用", "debit": 10000, "credit": 0, "description": "工资" },
    { "account_code": "2211", "account_name": "应付职工薪酬", "debit": 0, "credit": 10000, "description": "应付工资" }
  ],
  "attachments": {}
}
```

- **lines**：至少一条；每条必填 `account_code`，`debit`/`credit` 至少一个非 0；借贷合计需平衡（尾差 ≤ 0.01 元）。
- 创建后凭证状态为 **draft**，需调 PATCH 过账后才会进入总账余额/明细。

---

## 四、凭证过账（PATCH /vouchers/{id}/status）

- **body**：`{ "status": "posted" }` 或 `"rejected"` / `"approved"`。
- **允许转换**：draft → posted / rejected；pending → approved / rejected；approved → posted。
- 过账后该凭证参与 `GET /ledger/balances`（默认 `posted_only=true`）与 `GET /ledger/entries`。

---

## 五、总账明细（GET /ledger/entries）

**Query 参数**：

| 参数 | 必填 | 说明 |
|------|------|------|
| tenant_id | 是 | 租户 id |
| entity_id | 否 | 主体/门店 |
| start_date | 否 | 起始日期 YYYY-MM-DD |
| end_date | 否 | 结束日期 |
| account_code | 否 | 科目编码，不传则全部科目 |
| posted_only | 否 | 默认 true，仅已过账 |
| skip, limit | 否 | 分页，默认 limit=500 |

**响应**：`{ "total": N, "entries": [ { "voucher_id", "voucher_no", "biz_date", "entity_id", "line_no", "account_code", "account_name", "debit", "credit", "description" }, ... ], "skip", "limit" }`。

---

## 六、资金录入（POST /cash/transactions）

**请求体**：

```json
{
  "tenant_id": "T001",
  "entity_id": "STORE_001",
  "tx_date": "2025-02-26",
  "amount": 5000.00,
  "direction": "in",
  "description": "门店交款",
  "ref_id": null,
  "generate_voucher": true
}
```

- **direction**：`in` 收款，`out` 付款。
- **generate_voucher**：为 true 时自动生成一张手工凭证（借/贷 银行存款 与 其他应付款），凭证为 draft，可再调 PATCH 过账。

**响应**：`{ "cash_transaction": { "id", "tx_date", "amount", "direction", ... }, "voucher": { ... } 或 null }`。

---

## 七、最小工作台页面建议

| 页面/模块 | 调用接口 | 说明 |
|-----------|----------|------|
| 凭证列表 | GET /vouchers | 表格展示，筛选 status=draft/posted、日期、主体 |
| 凭证详情 | GET /vouchers/{id} | 查看分录，提供「过账」按钮 → PATCH status=posted |
| 新建凭证 | POST /vouchers | 表单：日期、摘要、多行分录（科目、借、贷），校验平衡后提交 |
| 总账余额 | GET /ledger/balances | 按科目展示余额，可选 as_of_date、posted_only |
| 总账明细 | GET /ledger/entries | 按科目或日期范围查明细，可钻取到凭证 |
| 资金流水 | GET /cash/transactions | 列表；提供「录入」→ POST /cash/transactions |

以上接口合并形态与独立形态**契约一致**（独立形态请求体为 JSON Dict，字段相同）。实现时只需根据部署形态选择认证方式与 base URL。

---

*文档版本：v1.0 | 与 P0/P1 优先落地接口同步，供前端或第三方对接 FCT 最小工作台。*
