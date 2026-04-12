# 屯象OS v6 代码审计修复 — 开发计划明细

> 基于 2026-03-27 实际代码扫描结果制定，非估算。
> 目标仓库: /Users/lichun/tunxiang

---

## 审计数据修正

原方案基于初步审计，以下为代码扫描后的修正：

| 项目 | 原始判断 | 实际扫描结果 | 影响 |
|------|---------|------------|------|
| KMS salt硬编码 | P0 | KMS实现正确(env-based+PBKDF2+AES-256-GCM)。**真正P0: 3个商户.env含真实凭证已入git** | 风险类型变更 |
| 宽泛异常处理器 | 679个 | **1,898个** except Exception, 95%有日志, 1个静默吞没 | 数量更大但严重度分层 |
| 测试覆盖率 | 8% | **93.46%整体覆盖**，但POS适配器(10/42)和Agent包(19/34)严重不足 | 问题从"全面缺失"变为"关键缺口" |
| AsyncMock警告 | P1 | 4,111处使用, **未检测到deprecation警告** | 降级为非问题 |

---

## 优先级总览

```
Week 1-2   ████████ P0: 凭证清除 + 静默异常修复 + 关键路径异常收窄
Week 3-4   ██████   P1: 异常层级体系 + POS适配器测试 + Agent测试
Week 5-6   ██████   P1: 测试补全收尾 + RLS审计 + 端口最小化
Week 7-8   ████     P2: ModelRouter + pre-commit流水线
Week 9-10  ████     P2: Ontology快照 + broad except渐进收窄启动
Week 11+   ██       持续: 每周收窄异常 + 每月Ontology维护
```

---

## P0 — 阻断级（Week 1-2, 不可跳过）

### P0-1: 从git历史中清除泄露的商户凭证 [2天]

**问题**: 3个商户配置文件含真实API密钥已提交到git。

| 文件 | 泄露内容 | 客户 |
|------|---------|------|
| config/merchants/.env.czyz | 品智API Token + 奥琦玮App ID/Key | 尝在一起 |
| config/merchants/.env.zqx | 6个门店品智Token + 奥琦玮Key | 最黔线 |
| config/merchants/.env.sgc | 5个门店品智Token + 优惠券凭证 | 尚宫厨 |
| scripts/probe_pinzhi_v2.py:7 | 硬编码品智Token | 测试脚本 |

**执行步骤**:

```bash
# Step 1: 备份当前状态
git stash && git tag pre-cleanup-backup

# Step 2: 用git-filter-repo清除历史
pip install git-filter-repo
git filter-repo --path config/merchants/.env.czyz --invert-paths
git filter-repo --path config/merchants/.env.zqx --invert-paths
git filter-repo --path config/merchants/.env.sgc --invert-paths

# Step 3: 清除probe脚本中的硬编码token
# 替换为 TOKEN = os.getenv("PINZHI_PROBE_TOKEN")

# Step 4: 验证.gitignore生效
echo "config/merchants/.env.*" >> .gitignore  # 确认存在

# Step 5: 安装git-secrets
brew install git-secrets
git secrets --install
git secrets --register-aws  # 基础规则
# 添加自定义规则匹配品智/奥琦玮token格式
```

**后续动作**:
- [ ] 联系品智技术支持轮换所有已泄露Token
- [ ] 联系奥琦玮轮换App Key
- [ ] 将凭证迁移到腾讯云密钥管理服务
- [ ] 通知所有有仓库访问权限的人员

**验收**: `git log --all -p | grep -i "api_token\|app_key\|app_secret"` 返回空

---

### P0-2: 修复静默异常 + celery_tasks异常收窄 [3天]

**文件**: `apps/api-gateway/src/core/celery_tasks.py` (151个broad except, 含1个静默吞没)

**Day 1**: 修复静默吞没
```python
# 第1590行，当前:
except Exception: pass

# 修改为:
except Exception as e:
    logger.error("celery_task_silent_failure",
                 task_name=self.name, error=str(e),
                 exc_info=True)
    # 上报到结构化日志/Sentry
```

**Day 2-3**: 按任务类型收窄异常
- POS数据同步任务 → `except (ConnectionError, TimeoutError, POSAdapterError)`
- 定时报告生成任务 → `except (ValueError, DataValidationError)`
- 通知推送任务 → `except (WeComWebhookError, requests.HTTPError)`
- 每个收窄后运行 `pytest tests/ -k celery` 验证

**验收**: celery_tasks.py中 `except Exception` 数量从151降至<30

---

### P0-3: 收窄45个关键数据路径异常处理器 [5天]

**第一批 Day 1-2 (TIER 1 — 财务/POS对账, 15个)**:

| 文件 | except Exception数 | 替换策略 |
|------|-------------------|---------|
| reconcile_service.py | 9 | POSAdapterError, ReconciliationMismatchError |
| payment_reconcile_service.py | 4 | ValueError, xlrd.XLRDError |
| bank_reconcile_service.py | 2 | ConnectionError, DataValidationError |

**第二批 Day 3-4 (TIER 2 — 客户数据, 17个)**:

| 文件 | except Exception数 | 替换策略 |
|------|-------------------|---------|
| customer360_service.py | 7 | DatabaseError, CacheConnectionError |
| member_context_store.py | 5 | redis.RedisError, json.JSONDecodeError |
| member_profile_aggregator.py | 4 | KeyError, DataValidationError |
| member_service.py | 1 | DatabaseError |

**第三批 Day 5 (TIER 3 — 订单/库存/财务, 13个)**:

| 文件 | except Exception数 | 替换策略 |
|------|-------------------|---------|
| order_service.py | 5 | POSAdapterError, ValueError |
| finance_health_service.py | 4 | ZeroDivisionError, DataValidationError |
| labor_cost_service.py | 3 | ValueError, KeyError |
| inventory_service.py | 1 | DatabaseError |

**每批完成后**: `pytest tests/ -v --tb=short` 全量运行确认无regression

---

## P1 — 基础加固（Week 3-6）

### P1-3: 自定义异常层级体系 [1天, Week 3第一天]

> 此任务排在P1-1/P1-2之前，因为测试编写需要引用这些异常类型。

**新建文件**: `apps/api-gateway/src/core/exceptions.py`

```python
class TunxiangBaseError(Exception):
    """屯象OS基础异常"""
    def __init__(self, message: str, context: dict = None):
        self.context = context or {}
        super().__init__(message)

class ExternalAPIError(TunxiangBaseError):
    """外部API调用异常"""

class POSAdapterError(ExternalAPIError):
    """POS适配器异常(品智/奥琦玮/美团)"""

class WeComWebhookError(ExternalAPIError):
    """企业微信Webhook异常"""

class DataValidationError(TunxiangBaseError):
    """数据校验异常"""

class ReconciliationMismatchError(DataValidationError):
    """对账不一致异常"""

class TenantIsolationError(TunxiangBaseError):
    """租户隔离违规(安全事件)"""

class BusinessRuleError(TunxiangBaseError):
    """业务规则违规"""

class MarginViolationError(BusinessRuleError):
    """毛利底线违规"""

class FoodSafetyError(BusinessRuleError):
    """食安合规违规"""

class ServiceTimeoutError(BusinessRuleError):
    """出餐时限违规"""
```

---

### P1-1: POS适配器测试补全 [5天, Week 3-4]

**当前状态**:

| 适配器 | 源文件数 | 测试文件数 | 客户 |
|--------|---------|-----------|------|
| pinzhi | ~6 | 1 | 尝在一起(最高优先) |
| aoqiwei | ~6 | 2 | 徐记海鲜 |
| meituan-saas | ~5 | 1 | 通用 |
| tiancai-shanglong | ~5 | 1 | 通用 |
| 其他4个 | ~20 | 5 | — |

**品智适配器测试用例设计** (目标≥8个):

```python
# packages/api-adapters/pinzhi/tests/test_adapter.py

class TestPinzhiAdapter:
    # 正常路径
    async def test_fetch_orders_returns_normalized_data(self)
    async def test_fetch_menu_items_maps_to_dish_model(self)
    async def test_multi_store_token_isolation(self)

    # 边界条件
    async def test_empty_order_list_returns_empty_not_error(self)
    async def test_pagination_handles_large_dataset(self)

    # 错误处理
    async def test_expired_token_triggers_refresh(self)
    async def test_api_timeout_raises_pos_adapter_error(self)
    async def test_malformed_response_raises_data_validation_error(self)
```

**Claude Code prompt模板**:
```
以下是 packages/api-adapters/pinzhi/src/adapter.py 的代码。
请生成pytest测试，覆盖：
1. 正常数据拉取和格式转换路径
2. Token过期/刷新机制
3. 空数据和异常响应的边界处理
4. 多门店Token隔离验证
使用POSAdapterError作为预期异常类型。
不要mock适配器内部逻辑，只mock HTTP请求层。
每个测试必须有明确的业务断言。
```

---

### P1-2: Agent包测试补全 [5天, Week 4-5]

**优先级**:

| Agent | 当前测试 | 目标测试数 | 原因 |
|-------|---------|-----------|------|
| decision | 1 | ≥6 | 经营建议质量核心 |
| inventory | 1 | ≥5 | 食材损耗=利润 |
| performance | 1 | ≥5 | 对客演示核心 |
| schedule | 1 | ≥4 | 人效优化 |
| private_domain | 5 | ≥8 | 补充边界case |

**每个Agent必须覆盖**:
1. Agent初始化和LangGraph状态转换
2. 核心决策逻辑的happy path
3. 三条硬约束校验(毛利底线/食安/出餐时限)
4. 输入异常时的降级处理
5. DecisionLog留痕验证

---

### P1-4: 服务器端口最小化 + RLS审计 [3天, Week 5-6]

**端口审计** (42.194.229.21):
```bash
# 当前开放端口扫描
nmap -sS 42.194.229.21

# 目标：仅保留
# 80/443 (Nginx)
# 8000 (FastAPI, 仅通过Nginx反代)
# Tailscale端口 (Mac mini连接)
```

**RLS审计**:
```sql
-- 检查所有表是否启用RLS
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public' AND rowsecurity = false;

-- 检查RLS策略完整性
SELECT * FROM pg_policies;
```

**渗透测试**: 编写测试用例，用tenant_A的session尝试查询tenant_B的数据。

---

## P2 — 架构演进（Week 7-10+）

### P2-4: pre-commit安全扫描流水线 [1天, Week 7]

**.pre-commit-config.yaml**:
```yaml
repos:
  - repo: https://github.com/awslabs/git-secrets
    hooks:
      - id: git-secrets
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.7
    hooks:
      - id: bandit
        args: [-r, apps/api-gateway/src/, -ll]
```

### P2-2: ModelRouter统一模型调用层 [3天, Week 7-8]

**Step 1**: 盘点当前所有Claude API直接调用位置
```bash
grep -rn "anthropic\|claude\|Anthropic" apps/api-gateway/src/ --include="*.py"
```

**Step 2**: 建立ModelRouter (v1配置字典版)
- 文件: `apps/api-gateway/src/core/model_router.py`
- 统一调用接口 + 成本计量 + 调用日志

**Step 3**: 逐步迁移(不一次性改完)

### P2-3: Ontology快照机制 [2天框架, Week 9-10]

**每客户一个快照文件**: `shared/ontology/snapshots/{customer_code}.md`

**月度consolidation流程**: 用Claude审查快照，标记过期规则，合并矛盾。

### P2-1: broad except渐进收窄 [持续, Week 10+]

**节奏**: 每周处理1个高频模块(10+exception的23个文件)
**追踪**: 每月统计broad except总数，目标每季度下降20%

---

## 时间线甘特图

```
         Week 1    Week 2    Week 3    Week 4    Week 5    Week 6
P0-1     ████
P0-2     ░░░░░░████████
P0-3               ░░░░░░████████████████
                              ↓ Hard Gate: P0全部关闭才能接真实客户数据
P1-3                       ██
P1-1                       ░░████████████████
P1-2                                 ████████████████
P1-4                                           ████████████

         Week 7    Week 8    Week 9    Week 10   Week 11+
P2-4     ██
P2-2     ████████████
P2-3                       ████████
P2-1                                 ████████  ░░░░░░░░→ (持续)
```

---

## Hard Gate（不可绕过的关卡）

### Gate 1: Week 2结束
- [ ] 商户凭证从git历史完全清除
- [ ] 所有已泄露Token已轮换
- [ ] 静默异常吞没已修复
- **不通过则**: 不允许接入任何新客户数据

### Gate 2: Week 6结束
- [ ] 45个关键路径异常已收窄
- [ ] 品智适配器测试≥8个且全通过
- [ ] RLS审计完成，无租户隔离漏洞
- **不通过则**: 不允许向尝在一起交付正式报告

### Gate 3: Week 10结束
- [ ] ModelRouter上线，所有AI调用经过统一层
- [ ] pre-commit安全扫描配置完成
- [ ] Ontology快照框架建立
- **不通过则**: 不允许申请Mythos早期访问

---

## CLAUDE.md 追加约束（建议立即加入）

```markdown
## 审计修复期特别约束（2026-03 至 2026-06）

### 代码修改红线
- 修改 except Exception 时，必须同时添加对应的pytest测试
- 新增POS适配器代码必须附带≥3个测试用例
- 禁止在config/merchants/目录下提交任何文件

### 提交前检查清单
- [ ] git-secrets扫描通过
- [ ] 涉及的P1模块pytest通过
- [ ] 无新增broad except（用ruff规则限制）
```

---

## 每日工作节奏（单人开发优化）

```
09:00  读CLAUDE.md + 检查昨日上下文
09:15  选择当天任务（严格按优先级，不跳级）
09:30  Plan Mode审查 → 确认变更范围
10:00  执行开发
12:00  午间：跑一轮pytest确认上午工作
14:00  继续开发
17:00  提交前: git-secrets + pytest P0模块
17:30  更新任务状态 + 记录经验教训
```

---

*本文档基于2026-03-27代码扫描数据。随修复进展更新。*
