# tasks/collab-sync.md — Claude × Codex 实时状态频道

> 每次开始/完成工作时更新此文件。这是双AI的对讲机。

---

## [Claude] 当前状态

**更新时间**: 2026-03-08 接口补全
**状态**: ✅ Phase 9 + 接口补全全部完成

**已完成（Phase 9 总结）**:
- ✅ 握手测试通过，发现并修复 WorkforcePage `risk_level` 缺 critical 级别 BUG
- ✅ 数据模型 `apps/api-gateway/src/models/banquet.py`：18张表，9个枚举，L1-L5五层架构
- ✅ Alembic迁移 `z35_banquet_agent_tables.py`（`alembic upgrade head` 可执行）
- ✅ 16个API端点 `/api/v1/banquet-agent`：宴会厅/客户/线索/订单 CRUD + 4个Agent + 驾驶舱
- ✅ 5个Agent全部实现：FollowupAgent/QuotationAgent/SchedulingAgent/ExecutionAgent/ReviewAgent
- ✅ **22个单元测试全部通过** (`pytest packages/agents/banquet/tests/test_agent.py` → 22 passed)
- ✅ 接口契约发布至 `tasks/api-contracts.md` → "Banquet Agent Phase 9" 节

**最新补充（接口补全）**:
- ✅ `GET /workforce/stores/{store_id}/shift-fairness-detail`：班次公平性详细分布（供员工健康Tab柱状图）
- ✅ `PATCH /banquet-agent/stores/{store_id}/leads/{lead_id}/stage`：线索阶段推进+跟进记录
- ✅ `GET /bff/banquet/{store_id}`：宴会首屏BFF（30s缓存，4数据并行聚合）

**正在做**: 等待 Codex 构建 Phase 9 宴会前端

🆕 **[Phase 9 宴会 Agent — 2026-03-08 全部完成]**
- 新路由：`/api/v1/banquet-agent`（16个端点）
- 5个 Agent：跟进提醒/报价推荐/排期推荐/执行任务/宴会复盘
- 数据模型：18张表（L1-L5五层），见 `src/models/banquet.py`
- 迁移：`z35_banquet_agent_tables.py`（需执行 `alembic upgrade head`）
- 测试：`packages/agents/banquet/tests/test_agent.py` → **22 passed**
- 全部接口契约：`tasks/api-contracts.md` → "Banquet Agent" 节

**需要 Codex 的任务**:

### 🔴 P0 — 验收 WorkforcePage 员工健康 Tab（握手后首个任务）
> 文件: `apps/web/src/pages/WorkforcePage.tsx`
> 接口: `GET /api/v1/workforce/stores/{store_id}/employee-health`

需要实现：
- 员工流失风险排名列表（按 risk_score_90d 降序）
  - 每行：姓名 · 职位 · 风险等级Badge（红/橙/黄/绿）· 离职替换成本¥ · 主要风险因子标签
  - 点击展开：详细风险因子 + 班次公平性数据
- 班次公平性分布图（水平条形图，high/medium/low_unfairness 三档）
- 公平指数大数字 + 趋势箭头（fairness_index 0-100）
- 骨架屏加载态（ZSkeleton）

### 🟡 P1 — 人力建议确认卡（Phase 8 Month 1 UI 补强）
> 文件: `apps/web/src/pages/sm/Home.tsx`（或新建 `StaffingAdviceCard.tsx`）
> 接口: `POST /api/v1/workforce/stores/{store_id}/staffing-advice/confirm`

需要实现：
- 今日/明日人力建议卡片（来自企微推送，在APP内也可操作）
- 展示：建议排班人数 · 分岗位明细 · 预估成本¥ · 置信度
- 操作：✅ 一键确认 / ✏️ 修改人数 / ❌ 拒绝+填原因
- 确认后显示成功 Toast + 刷新卡片状态

### 🟡 P2 — 总部人工成本排名（hq/ 路由）
> 文件: `apps/web/src/pages/hq/Home.tsx` 或新建 `LaborRankingCard.tsx`
> 接口: `GET /api/v1/workforce/multi-store/labor-ranking`

需要实现：
- 多店人工成本率排名表（含排名变化箭头）
- 与品牌均值对比色彩编码（超出警戒线飘红）

---

## [Codex] 当前状态

**更新时间**: 待接入
**状态**: ⏳ 等待 Codex 接入

```
# Codex 接入后请填写：
## [Codex] 当前状态
**更新时间**: YYYY-MM-DD
**正在做**:
**已完成**:
**依赖Claude的接口**: （如有，列出接口路径 + 缺什么字段）
**发现的接口问题**: （如有，@Claude 请修复）
```

---

## 历史协作记录

| 日期 | Claude动作 | Codex动作 | 备注 |
|------|-----------|----------|------|
| 2026-03-08 | 握手初始化，整理接口契约 | 待接入 | Phase 8 后端完成 |
| 2026-03-08 | **握手测试**：发现+修复 WorkforcePage risk_level 缺 critical 级别 | 需跑前端测试验收 | BUG来源：契约与实现不一致 |
| 2026-03-08 | **Phase 9 完成**：18张表+5个Agent+16个接口+22个测试全绿 | 待构建宴会前端 | commit: e0dcb57 |
| 2026-03-08 | **接口补全**：shift-fairness-detail + lead-stage + BFF/banquet | 宴会首屏可一次性加载 | commit: 14d7199 |
