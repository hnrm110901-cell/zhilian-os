# CONTEXT.md — Agents 层（Level 2）

> 仅在任务涉及 `packages/agents/` 时读取。
> 了解具体 Agent 职责后，再进入对应目录的 `src/agent.py`（Level 3）。

---

## Agent 层职责

将用户的自然语言指令（通过企微/飞书/API）转化为结构化的运营决策和执行动作。
每个 Agent 是独立的 Python 包，可单独测试和部署。

---

## 10 个 Agent 速查表

| Agent | 目录 | 核心职责 | 关键输入 | 关键输出 |
|-------|------|---------|---------|---------|
| **schedule** | `packages/agents/schedule/` | 智能排班：根据流量预测生成最优班次 | 历史订单、员工档案、节假日 | 排班方案、换班建议 |
| **order** | `packages/agents/order/` | 订单异常检测、催单、超时预警 | 实时订单流 | 异常报警、催单指令 |
| **inventory** | `packages/agents/inventory/` | 库存预警、自动补货建议、损耗分析 | 库存快照、销量历史 | 补货单、预警消息 |
| **private_domain** | `packages/agents/private_domain/` | 私域运营：RFM分析、流失预警、增长动作 | 会员行为数据 | AARRR 增长动作 |
| **service** | `packages/agents/service/` | 服务质量：差评分析、员工表现、满意度报告 | 客户反馈、员工绩效 | 服务质量报告 |
| **training** | `packages/agents/training/` | 员工培训：技能评估、学习路径推荐 | 员工档案、考核记录 | 培训计划 |
| **decision** | `packages/agents/decision/` | 综合决策：汇总多 Agent 信号生成经营建议 | 多 Agent 输出、外部因素 | 决策报告、行动计划 |
| **ops** | `packages/agents/ops/` *(service包内)* | 设备运维：故障预测、维保提醒 | 设备状态日志 | 维保工单、故障预警 |
| **performance** | *(service包内)* | 绩效分析：KPI达成、奖惩建议 | KPI数据、销售记录 | 绩效报告 |
| **reservation** | `packages/agents/reservation/` | 预订管理：容量优化、爽约预测 | 预订记录、历史数据 | 预订确认、容量建议 |

---

## 每个 Agent 包的统一结构

```
packages/agents/{domain}/
├── src/
│   ├── __init__.py
│   └── agent.py          ← Agent 实现（唯一必读文件）
├── tests/
│   ├── conftest.py       ← sys.path 修复（必须！防止 import 污染）
│   └── test_agent.py     ← 功能测试（~30-60 个用例）
└── README.md
```

**`agent.py` 统一接口约定：**
```python
class {Domain}Agent:
    def __init__(self, store_id: str, brand_id: str = None, db_engine=None)

    async def {main_action}(self, **kwargs) -> dict   # 主业务方法

    def _get_db_engine(self)      # 从环境变量读取 DB 连接
    def _fetch_{data}_from_db(self, ...)  # DB 查询（命名规范：fetch 不是 mock）
```

---

## Agent 调用链（从 API 到 Agent）

```
HTTP Request
  → apps/api-gateway/src/api/{route}.py
  → apps/api-gateway/src/services/agent_service.py   # 调度入口
  → apps/api-gateway/src/services/intent_router.py   # 意图识别
  → packages/agents/{domain}/src/agent.py            # 执行
  → PostgreSQL / Redis / Qdrant                      # 数据层
```

---

## 数据库连接模式（Agent 层）

Agent 层使用**同步 SQLAlchemy**（非 async），因为 Agent 是独立进程/包：

```python
# ✅ Agent 层的 DB 访问方式
from sqlalchemy import create_engine, text

def _get_db_engine(self):
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return None
    # Agent 层用 psycopg2（同步），不用 asyncpg
    sync_url = db_url.replace("+asyncpg", "")
    return create_engine(sync_url)

# 使用
with engine.connect() as conn:
    rows = conn.execute(text("SELECT ..."), params).fetchall()
```

**注意：** API Gateway 层用 async SQLAlchemy（asyncpg），Agent 层用 sync（psycopg2），不要混用。

---

## 测试注意事项

### sys.path 污染问题（已知约束）
- 每个 Agent 的 `src/agent.py` 路径相同，多 Agent 并行测试会互相覆盖
- **必须独立运行**：`pytest packages/agents/schedule/tests -v`（不能用 `pytest packages/agents/*/tests`）
- `conftest.py` 中有 `sys.path` 修复逻辑，不能删除

### Mock 策略
```python
# ✅ 无 DB 时的正确行为：返回样本数据（测试可用）或空列表
def _fetch_from_db(self):
    engine = self._get_db_engine()
    if engine:
        # 查DB...
        return rows
    # 无DB时：返回最小可用样本数据（仅用于测试）
    return self._sample_data()

# ❌ 错误：用 mock 方法名但实际接业务逻辑（已修复的历史问题）
def _generate_mock_xxx(self):  # 命名具有误导性，已重命名
```

---

## Private Domain Agent 特殊说明

增长 Action 处理器独立在 `growth_handlers.py`：
- 18 个 AARRR 增长动作（获客/激活/留存/变现/推荐）
- 动作通过 `action_type` 字段路由
- 测试在 `tests/test_growth_handlers.py`（独立于主 agent 测试）

---

## 新增 Agent 清单

当需要新建 Agent 时：
1. `packages/agents/{new_domain}/src/__init__.py`
2. `packages/agents/{new_domain}/src/agent.py`（按统一接口约定）
3. `packages/agents/{new_domain}/tests/conftest.py`（必须含 sys.path 修复）
4. `packages/agents/{new_domain}/tests/test_agent.py`
5. 在 `apps/api-gateway/src/services/agent_service.py` 注册新 Agent
6. 在 `apps/api-gateway/src/services/intent_router.py` 添加意图规则
