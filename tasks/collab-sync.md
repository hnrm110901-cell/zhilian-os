# tasks/collab-sync.md — Claude × Codex 实时状态频道

> 每次开始/完成工作时更新此文件。这是双AI的对讲机。

---

## [Claude] 当前状态

**更新时间**: 2026-03-08 握手测试
**状态**: ✅ 握手测试通过，发现并修复 1 个契约不符 bug

**已完成（握手测试）**:
- ✅ 验证 workforce router 已注册到 main.py（11条路由全部就位）
- ✅ 验证 `api-contracts.md` 中 employee-health 接口与后端代码一致
- 🔧 **发现并修复 BUG** → `WorkforcePage.tsx` 前端缺少 `'critical'` 风险等级
  - `risk_level` 类型 `'high'|'medium'|'low'` → `'critical'|'high'|'medium'|'low'`
  - 高风险计数过滤器漏掉 critical 员工 → 已修复
  - 风险等级渲染缺少极高(magenta) → 已补充
- ✅ 更新 `api-contracts.md` risk_level 四级定义已正确记录

**正在做**: Phase 9 宴会 Agent 后端已完成，等待 Codex 构建前端

🆕 **[Phase 9 宴会 Agent 后端已上线 — 2026-03-08]**
- 新路由：`/api/v1/banquet-agent`（16个端点）
- 5个 Agent：跟进提醒/报价推荐/排期推荐/执行任务/宴会复盘
- 数据模型：18张表（L1-L5五层），见 `src/models/banquet.py`
- 迁移：`z35_banquet_agent_tables.py`（需执行 `alembic upgrade head`）
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
