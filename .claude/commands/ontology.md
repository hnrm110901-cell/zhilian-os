检查智链OS Ontology对象的完整性和一致性：$ARGUMENTS

## 背景

智链OS采用四层Ontology架构：Perception → Ontology → Reasoning → Action
所有业务功能必须先映射到Ontology对象，再实现Service层。

## 检查流程

1. **扫描模型层**：读取 `apps/api-gateway/src/models/` 中所有模型文件，提取实体清单
2. **扫描服务层**：读取 `apps/api-gateway/src/services/` 中的服务文件，提取服务与模型的映射关系
3. **扫描Agent层**：读取 `packages/agents/*/src/agent.py`，提取Agent依赖的数据结构
4. **交叉验证**：

### 一致性检查
- [ ] 每个Model是否在 `models/__init__.py` 中注册（Alembic依赖）
- [ ] 每个Model的外键是否使用UUID类型（非VARCHAR，历史教训）
- [ ] Service层引用的Model是否都存在
- [ ] Agent层使用的数据结构是否与Model/Schema对齐
- [ ] API路由的请求/响应Schema是否与Service返回值匹配

### 领域完整性检查
- [ ] 核心实体（Store/Order/Employee/Dish/Inventory）是否有完整的CRUD路由
- [ ] 金额字段是否标注单位（分/元）
- [ ] 时间字段是否使用 `server_default=func.now()`
- [ ] 多租户字段（brand_id + store_id）是否在所有业务表中存在

## 输出

```
## Ontology 健康报告

### 实体总览
| 实体 | 模型文件 | 服务文件 | API路由 | Agent引用 | 状态 |

### 问题清单
1. [严重程度] 问题描述 → 建议修复方案

### 建议
- 需要补充的Ontology对象
- 需要对齐的Schema差异
```
