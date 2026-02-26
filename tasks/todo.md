# 任务清单

> 格式：- [ ] 待办 / - [x] 完成
> 每次会话开始时更新，完成后在底部添加评论。

---

## 进行中


---

## 已完成

- [x] 检查所有 agent 完整性与稳定性（预定/排班/订单/私域/服务/库存/培训/绩效/决策/运维）
- [x] 补充 private_domain agent 的 test_agent.py（56个测试）
- [x] 补充 performance_agent 功能测试（38个测试）
- [x] 补充 ops_agent 功能测试（33个测试）
- [x] 将 mock 数据方法替换为真实 DB 服务调用（private_domain / training / schedule）
- [x] 排班 agent 流量预测接入历史订单数据
- [x] 修复 service/decision/reservation/order/inventory/training agent 预存在的测试失败
- [x] 为所有 package agent 测试目录添加 conftest.py（sys.path 修复）
- [x] 新增私域运营 18个增长 action（AARRR 框架）
- [x] 企微 webhook 接入私域 Agent 对话（P0/P1）
- [x] 生成智链OS功能明细思维导图

---

## 评论

### 2026-02-26
- 所有8个 package agent 测试套件在独立运行时全部通过（共 235 个测试）
- 已知限制：多 agent 同时运行时存在 sys.path 污染问题（各 agent src/agent.py 互相覆盖），需独立运行
- 私域 Agent 增长能力当前返回 mock/demo 数据，待接入真实 DB 后替换
