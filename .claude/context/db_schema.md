# 数据库 Schema 参考

> 按需加载：当任务涉及数据模型变更或数据库查询时读取此文件。
> 模型源码：`apps/api-gateway/src/models/`

---

## 核心约定

- **ORM**: SQLAlchemy 2.0 async (asyncpg)
- **迁移**: Alembic sync (psycopg2)，`alembic/env.py` URL 转换不能删
- **金额**: DB 存分(fen, BigInteger)，API 返回元(yuan)。部分历史表用 `Numeric(10,2)` 存元
- **主键**: 新表用 `UUID(as_uuid=True)`，历史表 `String(50)`
- **外键**: 统一使用 UUID（不用 VARCHAR，历史教训已修复）
- **多租户**: 所有业务表必须包含 `store_id`（FK → stores.id），跨品牌表加 `brand_id`
- **时间戳**: 继承 `TimestampMixin`（`created_at`, `updated_at`）
- **注册**: 新模型必须在 `models/__init__.py` 中 import（Alembic autogenerate 依赖）

---

## 核心实体

### stores（门店）
| 列 | 类型 | 说明 |
|----|------|------|
| id | String(50) PK | 门店ID（如 STORE001） |
| name | String(100) | 门店名称 |
| code | String(20) UNIQUE | 门店编码 |
| brand_id | String(50) INDEX | 品牌ID（多品牌隔离） |
| manager_id | UUID | 店长ID |
| status | String(20) | active/inactive/renovating/preparing/closed |
| monthly_revenue_target | Numeric(12,2) | 月营业额目标 |
| cost_ratio_target | Float | 成本率目标 |
| labor_cost_ratio_target | Float | 人力成本率目标 |

### orders（订单）
| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | 订单ID |
| store_id | String(50) FK | 门店 |
| total_amount | Numeric(10,2) | 总金额（元） |
| discount_amount | Integer | 折扣（分） |
| final_amount | Integer | 实付（分） |
| status | String(20) | pending→confirmed→preparing→ready→served→completed/cancelled |
| waiter_id | String(50) INDEX | 服务员（绩效关联） |
| sales_channel | String(30) INDEX | 销售渠道 |

### order_items（订单明细）
| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| order_id | UUID FK | 订单 |
| unit_price | Numeric(10,2) | 单价（元） |
| subtotal | Numeric(10,2) | 小计（元） |
| food_cost_actual | Integer | BOM理论成本（分） |
| gross_margin | Numeric(6,4) | 毛利率 0-1 |

### employees（员工）
| 列 | 类型 | 说明 |
|----|------|------|
| id | String(50) PK | 员工ID（如 EMP001） |
| store_id | String(50) FK | 门店 |
| position | String(50) | waiter/chef/cashier/manager |
| skills | ARRAY(String) | 技能列表 |
| hire_date | Date | 入职日期 |

### dishes（菜品）
| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| store_id | String(50) FK | 门店 |
| code | String(50) UNIQUE | 菜品编码 |
| price | Numeric(10,2) | 售价（元） |
| cost | Numeric(10,2) | 成本价（元） |
| profit_margin | Numeric(5,2) | 毛利率(%) |
| dish_master_id | UUID FK | 集团主档关联 |
| category_id | UUID FK | 分类 |

### inventory_items（库存）
| 列 | 类型 | 说明 |
|----|------|------|
| id | String(50) PK | |
| store_id | String(50) FK | 门店 |
| current_stock | Numeric(10,3) | 当前库存量 |
| min_stock | Numeric(10,3) | 最低库存量 |
| unit_cost | Numeric(10,2) | 单位成本 |

---

## 人力管理域（Phase 8）

### labor_demand_forecasts
| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| store_id | String(50) FK | 门店 |
| forecast_date | Date | 预测日期 |
| predicted_customers | Integer | 预测客流 |
| by_position | JSON | 各岗位需求人数 |

### labor_cost_snapshots
| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| store_id | String(50) FK | 门店 |
| total_labor_cost_fen | BigInteger | 总人工成本（分） |
| labor_cost_rate | Numeric(5,4) | 人工成本率 |

### staffing_advices
| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| store_id | String(50) FK | 门店 |
| advice_date | Date | 建议日期 |
| status | Enum | pending/confirmed/rejected/expired |
| recommendation | JSON | 建议内容 |

### staffing_advice_confirmations
| 列 | 类型 | 说明 |
|----|------|------|
| id | UUID PK | |
| advice_id | UUID FK | 建议 |
| action | Enum | confirm/reject/modify |

---

## 宴会管理域（Phase 9-16）

### banquet_halls（宴会厅）
### banquet_customers（客户）
### banquet_leads（线索）+ lead_followup_records（跟进）
### banquet_quotes（报价）+ menu_packages（套餐）
### banquet_orders（订单）+ banquet_hall_bookings（预订）
### execution_templates（执行模板）+ execution_tasks（任务）
### banquet_payment_records（收款）+ banquet_contracts（合同）
### banquet_profit_snapshots（利润快照）+ banquet_kpi_daily（KPI）

> 宴会域模型复杂（24KB），详见 `src/models/banquet.py`

---

## 运营管理域

### action_plans（L5行动计划）
| status | DispatchStatus | pending/dispatched/executing/completed/expired |
| outcome | ActionOutcome | success/partial/failed/skipped |

### daily_workflows（每日工作流）
| status | WorkflowStatus | 工作流状态 |
| phases | JSON | 阶段列表 |

### knowledge_rules（知识规则）
| category | RuleCategory | 规则分类 |
| type | RuleType | 规则类型 |

---

## 财务域（FCT）

### fct_tax_records / fct_cash_flow_items / fct_budget_controls
### fct_petty_cash / fct_petty_cash_records / fct_approval_records
### vouchers / voucher_lines

> 财务域模型详见 `src/models/fct.py`（11KB）

---

## 集成域

### external_systems / sync_logs / pos_transactions
### supplier_orders / member_syncs / reservation_syncs

> 外部系统集成详见 `src/models/integration.py`（17KB）

---

## 常见查询模式

```sql
-- 多租户过滤（所有查询必须带）
WHERE store_id = :store_id

-- 跨品牌查询
WHERE brand_id = :brand_id

-- 时间范围（安全写法）
WHERE order_time >= :start_date
  AND order_time < :end_date

-- INTERVAL（安全写法，不在字符串内嵌入参数）
WHERE created_at >= NOW() - (:n * INTERVAL '1 day')

-- 分页（total 必须单独 COUNT）
SELECT COUNT(*) FROM orders WHERE store_id = :store_id  -- total
SELECT * FROM orders WHERE store_id = :store_id LIMIT :limit OFFSET :offset
```
