# 屯象OS HR M3 — FK迁移 + C级预测 + WF-2排班优化

**版本**: v1.0
**日期**: 2026-03-17
**作者**: 微了一 + Claude
**状态**: 待实施
**上游依赖**: M1（z50-z52）, M2（z53-z55）已合并到 main

---

## 0. 背景与范围

M3 是 HR Foundation 里程碑的第三阶段（Week 8–11），承接 M2 的双写层和 Agent B级能力，完成三项独立任务：

| Chunk | 标签 | 核心内容 |
|-------|------|---------|
| A | z56 FK 迁移 | 将4张硬外键表从 `employee_id` 切换到 `assignment_id` |
| B | HRAgent v2 C级 | sklearn LogisticRegression 离职风险预测，冷启动降级 |
| C | WF-2 排班优化 | StaffingService：双数据源合并算力峰值+节省金额 |

三个 Chunk 相互独立，可按 A→B→C 顺序开发，每个 Chunk 单独可交付。

---

## 1. Chunk A：z56 FK 迁移

### 1.1 目标

将4张含 `ForeignKey("employees.id")` 硬约束的表新增 `assignment_id` 列，回填现有数据，为 M4 最终切割做准备。M3 **不删除**旧列，保持双写安全。

### 1.2 目标表（实际表名，以代码为准）

| 表名 | 当前列 | 新增列 | 备注 |
|------|--------|--------|------|
| `compliance_licenses` | `holder_employee_id VARCHAR(36)` | `holder_assignment_id UUID NULL` | 持证人 |
| `customer_ownerships` | `owner_employee_id VARCHAR(50)` | `owner_assignment_id UUID NULL` | 客户归属 |
| `shifts` | `employee_id VARCHAR(50)` | `assignment_id UUID NULL` | 排班（注意：不是 `schedules` 表）|
| `employee_metric_records` | `employee_id VARCHAR(50)` | `assignment_id UUID NULL` | 员工绩效（注意：不是 `employee_metrics` 表）|

> **关键说明**：`Schedule` 模型本身无 employee FK，只有 `Shift` 子模型才含 `employee_id`。`employee_metric_records` 是实际表名（不是 `employee_metrics`）。

### 1.3 迁移策略（Expand-then-Migrate，不停服）

```
步骤 1: ADD COLUMN（4张表各自新增 assignment_id UUID NULL）
步骤 2: 回填（通过 employee_id_map 桥接表，UPDATE JOIN）
步骤 3: CREATE INDEX CONCURRENTLY（后台，不锁表）
步骤 4: 验证（assert 回填覆盖率 >= 95%）
步骤 5: 不做 NOT NULL 约束（M4 才 DROP 旧列 + 加约束）
```

### 1.4 回填 SQL 逻辑

```sql
-- 示例：shifts 表回填
UPDATE shifts s
SET assignment_id = (
    SELECT ea.id
    FROM employee_id_map m
    JOIN employment_assignments ea ON ea.person_id = m.person_id
    WHERE m.legacy_employee_id = s.employee_id
      AND ea.status = 'active'
    ORDER BY ea.created_at DESC
    LIMIT 1
)
WHERE s.assignment_id IS NULL;
```

同样逻辑应用于另外3张表。

### 1.5 Alembic 迁移文件

- 文件名：`z56_fk_migration_to_assignment_id.py`
- 路径：`apps/api-gateway/alembic/versions/`
- `down_revision`：`z55_hr_knowledge_tables`

### 1.6 测试要求

- `test_z56_fk_migration.py`
- 验证：4张表均存在 `assignment_id` 列
- 验证：`shifts` 表回填行数 > 0（如果 `employee_id_map` 有数据）
- 验证：alembic upgrade/downgrade 往返无错误（需 mock DB，不依赖真实 PostgreSQL）
- **注意**：现有环境无 PostgreSQL，使用 SQLite in-memory + `render_as_batch=True` 方式测试，或直接 mock schema inspection

---

## 2. Chunk B：HRAgent v2 C级预测

### 2.1 目标

在现有 `RetentionRiskService`（B级规则引擎）基础上，叠加 sklearn LogisticRegression 机器学习层，实现 **C级预测干预**：提前14天预警潜在离职风险，并给出可操作的干预建议。

### 2.2 依赖声明

**必须先安装**：
```
scikit-learn>=1.4.0
joblib>=1.3.0
```

在 `apps/api-gateway/requirements.txt`（或 `pyproject.toml`）中添加上述依赖。**实施前验证已安装**：
```bash
python3 -c "import sklearn, joblib; print('OK')"
```

### 2.3 特征工程

| 特征名 | 来源 | 说明 |
|--------|------|------|
| `tenure_days` | `employment_assignments.start_date` | 在职天数 |
| `achievement_count` | `person_achievements` | 近90天成就数量 |
| `recent_signal_avg` | `retention_signals` | 近30天留任信号均值（0-1）|
| `achievement_velocity` | `person_achievements` | 近30天 / 前30天 成就比率 |

目标变量：`is_high_risk`（1 = 30天内离职，0 = 未离职）

### 2.4 冷启动策略

| 条件 | 策略 |
|------|------|
| 标记样本 < 50 | 使用多因子启发式规则（与 B级 RetentionRiskService 相同逻辑）|
| 标记样本 >= 50 | 训练 LogisticRegression，替换启发式规则 |
| 模型文件不存在 | 自动回退到 B级 heuristic，不抛错误 |

### 2.5 模型管理

- **序列化格式**：joblib（`.pkl` 文件）
- **存储位置**：Redis key `hr:retention_model:{store_id}` → 字节流
- **TTL**：7天（由 Celery 周训练任务续期）
- **版本字段**：模型元数据附带 `trained_at` 时间戳 + `sample_count`

### 2.6 Celery 定时训练任务

```python
# 触发时间：每周日 02:00 UTC
@app.task
def retrain_retention_model_weekly():
    """遍历所有 active store，各自训练模型，存入 Redis"""
    ...
```

### 2.7 预测输出格式

```python
{
    "person_id": "uuid...",
    "risk_score": 0.72,           # 0.0-1.0
    "risk_level": "high",         # low/medium/high
    "prediction_source": "ml",    # ml / heuristic
    "model_trained_at": "2026-03-17T02:00:00Z",
    "sample_count": 127,
    "top_features": [
        {"name": "recent_signal_avg", "contribution": -0.31},
        {"name": "tenure_days", "contribution": 0.18}
    ],
    "intervention": {
        "action": "安排一对一面谈",
        "estimated_impact": "降低离职概率 23%",
        "confidence": 0.68,
        "deadline": "2026-03-31"
    }
}
```

### 2.8 HRAgent v2 集成

在 `apps/api-gateway/src/agents/hr_agent.py` 中：

- `_diagnose_staffing_placeholder` 替换为实际调用 `StaffingService`（见 Chunk C）
- 新增 `_predict_retention_risk(person_id, store_id)` 方法：先查 Redis 取模型 → 运行预测 → 返回结构化建议
- `handle_intent("retention_risk")` 路由到 ML 预测路径（有模型时）或 B级 heuristic（冷启动时）

### 2.9 新增文件

| 文件 | 职责 |
|------|------|
| `apps/api-gateway/src/services/hr/retention_ml_service.py` | ML 训练 + 预测 + Redis 存取 |
| `apps/api-gateway/src/celery_tasks/hr_ml_tasks.py` | Celery 定时训练任务 |
| `apps/api-gateway/tests/test_retention_ml_service.py` | 单元测试（mock sklearn/Redis）|

### 2.10 测试要求

- 冷启动路径：样本 < 50 时返回 heuristic 结果，`prediction_source == "heuristic"`
- ML路径：mock 50+ 样本，验证返回 `prediction_source == "ml"`
- Redis 缺失：模型不存在时不抛异常，自动 fallback
- 所有测试不依赖真实 sklearn 训练（mock `LogisticRegression.predict_proba`）

---

## 3. Chunk C：WF-2 排班优化（StaffingService）

### 3.1 目标

实现 `StaffingService.diagnose_staffing(store_id, date)` 方法，分析指定门店的排班健康度，输出峰值时段、人力缺口、预估可节省金额。

### 3.2 双数据源融合

| 数据源 | 权重 | 说明 |
|--------|------|------|
| `orders` 实时小时聚合 | 40% | 近7天每小时订单量，代表近期流量模式 |
| `daily_metrics` 历史均值 | 60% | 近30天同星期均值，代表稳定趋势 |

**融合逻辑**：
```python
fused_demand[hour] = 0.4 * recent_orders[hour] + 0.6 * historical_avg[hour]
```

### 3.3 输出格式

```python
{
    "store_id": "STORE001",
    "analysis_date": "2026-03-17",
    "peak_hours": [12, 13, 18, 19],         # 需求量 > 均值 + 1σ 的时段
    "understaffed_hours": [12, 18],         # 排班人数 < 建议人数 的时段
    "overstaffed_hours": [9, 15],           # 排班人数 > 建议人数+1 的时段
    "recommended_headcount": {              # 每小时建议人数
        "9": 2, "10": 3, "12": 5, ...
    },
    "estimated_savings_yuan": 380.00,       # 减少过剩排班可节省的人力成本（元）
    "confidence": 0.75,
    "data_freshness": {
        "orders_latest": "2026-03-16T23:59:00Z",
        "daily_metrics_days": 28
    }
}
```

### 3.4 建议人数算法

```python
# 每小时需求系数 = fused_demand[hour] / avg_demand_per_staff
# 建议人数 = ceil(需求系数) + 1 (缓冲)
# 节省成本 = Σ max(0, actual_headcount[hour] - recommended[hour]) * hourly_wage
```

`hourly_wage` 默认 25.0 元/小时（可通过 `store.config` 覆盖）。

### 3.5 Celery 触发任务

```python
# 触发时间：每周一 06:00 UTC（生成本周排班建议）
@app.task
def trigger_staffing_analysis_weekly():
    """遍历所有 active store，生成排班诊断，存入 Redis 缓存"""
    ...
```

Redis key：`hr:staffing_diagnosis:{store_id}:{date}` TTL 24小时。

### 3.6 HRAgent 集成

`hr_agent.py` 的 `handle_intent("staffing")` 方法：
1. 调用 `StaffingService.diagnose_staffing(store_id, today)`
2. 若 Redis 缓存命中直接返回
3. 格式化为 Agent 友好的自然语言推荐 + 数字摘要

### 3.7 新增文件

| 文件 | 职责 |
|------|------|
| `apps/api-gateway/src/services/hr/staffing_service.py` | 核心分析逻辑 |
| `apps/api-gateway/src/celery_tasks/hr_staffing_tasks.py` | Celery 触发任务 |
| `apps/api-gateway/tests/test_staffing_service.py` | 单元测试 |

### 3.8 测试要求

- `orders` 数据为空时：降级到纯 `daily_metrics` 历史均值（权重升为 100%）
- `daily_metrics` 也为空时：返回 `{"confidence": 0.0, "data_freshness": {...}}`，不抛错
- 正常路径：验证 `peak_hours`、`estimated_savings_yuan > 0` 计算正确
- 所有测试使用 mock SQLAlchemy session，不依赖真实 PostgreSQL

---

## 4. 整体依赖与顺序

```
M2（已合并 main）
  └── Chunk A：z56 FK 迁移
        └── Chunk B：HRAgent v2 C级预测（依赖 assignment_id 可用）
              └── Chunk C：WF-2 StaffingService（依赖 HRAgent 接口定义）
```

> Chunk B 和 C 的 StaffingService 可并行开发，但 HRAgent 集成需等 C 的接口确定后完成。

---

## 5. 技术约束

| 约束 | 说明 |
|------|------|
| Python 版本 | 3.11+（项目标准）|
| SQLAlchemy | 2.0 Column-style，async session |
| 测试框架 | pytest + pytest-asyncio |
| 日志 | structlog（与 M2 一致）|
| 新依赖 | `scikit-learn>=1.4.0`、`joblib>=1.3.0` 必须加入 requirements |
| 无 PostgreSQL | CI 测试不依赖真实 DB，全部使用 mock 或 SQLite |
| 金额单位 | `estimated_savings_yuan` 单位为元（保留2位小数），DB 可存分但 API 返回元 |

---

## 6. 验收标准

| Chunk | 验收标准 |
|-------|---------|
| A | `alembic upgrade z56` 成功；4张表均有 `assignment_id` 列；回填覆盖率 ≥ 95% |
| B | 冷启动时 `prediction_source == "heuristic"`；有数据时 `prediction_source == "ml"`；Celery 任务可被调度 |
| C | `diagnose_staffing()` 返回含 `peak_hours`/`estimated_savings_yuan` 的完整结构；`orders` 为空时优雅降级 |
| 整体 | `pytest apps/api-gateway/tests/ -v` 新增测试全部通过；`pnpm run build`（前端）无破坏性错误 |
