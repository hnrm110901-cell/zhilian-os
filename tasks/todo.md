# 任务清单

> 格式：- [ ] 待办 / - [x] 完成
> 每次会话开始时更新，完成后在底部添加评论。

---

## 进行中


---

## 已完成

- [x] 私域 Agent get_journeys 接入真实 DB（_fetch_journeys_from_db + _persist_journey_to_db）
- [x] 用户培训文档（docs/user-training-guide.md）

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
- [x] Phase 3 安全加固：SecurityHeadersMiddleware（防 XSS/点击劫持/MIME 嗅探/HSTS）
- [x] Phase 3 安全加固：CORS 配置环境感知（明确 methods/headers，不使用 *）
- [x] Phase 3 安全加固：Nginx SSL/TLS 配置（HTTP→HTTPS 重定向、TLS 1.2+、安全头、OCSP Stapling）
- [x] Phase 3 生产部署：Kubernetes 配置（namespace/configmap/secrets/api/web/postgres/redis/hpa/ingress）
- [x] Phase 3 性能优化：GZip 压缩中间件（minimum_size=1000）
- [x] Phase 3 生产部署：Prometheus 告警规则补充（Redis宕机/DB连接池耗尽/磁盘/Agent错误率）
- [x] P0-1 建立 Alembic 数据库迁移体系（env.py compare_type、URL转换、13个Phase3-8模型注册）
- [x] P0-2 私域Agent SQL bug修复（INTERVAL参数化）并移除 _generate_mock_customers 死代码
- [x] P0-3 菜单排名 MenuRanker 移除 _mock_ranking() 死代码，无DB时返回空列表
- [x] P0-4 门店记忆 StoreMemoryService 移除 _mock_peak_patterns() 死代码，无DB时返回空列表
- [x] P1-1 向量DB 移除 _generate_mock_embedding() 死代码（generate_embedding 已有零向量兜底）
- [x] P1-2 服务质量Agent _generate_mock_feedbacks 重命名为 _fetch_feedbacks_from_db
- [x] P1-3 README Phase 3 路线图状态同步（性能优化/安全加固/生产部署标记完成）
- [x] P2-1 补充服务层核心单元测试（MenuRanker/StoreMemoryService/VectorDbService 共3个测试文件）

---

## 评论

### 2026-02-26
- 所有8个 package agent 测试套件在独立运行时全部通过（共 235 个测试）
- 已知限制：多 agent 同时运行时存在 sys.path 污染问题（各 agent src/agent.py 互相覆盖），需独立运行
- 私域 Agent 增长能力当前返回 mock/demo 数据，待接入真实 DB 后替换

### 2026-03-04
- 完成所有 P0/P1/P2-1 优先级项目开发
- 清理 4 处死代码（_mock_ranking、_mock_peak_patterns、_generate_mock_embedding、_generate_mock_customers）
- 修复私域 Agent SQL INTERVAL 参数化 bug（生产级关键修复）
- 新增 3 个服务层单元测试文件，覆盖核心评分逻辑、异常检测、嵌入降级链路
### 2026-03-04（续）
- 私域 Agent 增长旅程接入真实 DB：新增 `_fetch_journeys_from_db` 和 `_persist_journey_to_db`，`get_journeys` 和 `trigger_journey` 均已替换 mock 数据
- 完成用户培训文档（docs/user-training-guide.md）：覆盖店长/总部/员工三类角色，含备战板操作、食材成本分析、企业微信指令速查等
- Phase 3 所有任务已全部完成
