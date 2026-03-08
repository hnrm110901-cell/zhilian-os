# tasks/collab-sync.md — Claude × Codex 实时状态频道

> 每次开始/完成工作时更新此文件。这是双AI的对讲机。

---

## [Claude] 当前状态

**更新时间**: 2026-03-08
**状态**: ✅ 握手就绪

**已完成（本次握手）**:
- 整理并发布 Phase 8 全部 Workforce API 接口契约 → `tasks/api-contracts.md`
- 确认 `employee-health` 接口已包含 `replacement_cost_yuan` 字段（¥离职成本，月薪×50%）
- 后端 Phase 8 Month 1/2/3 全部 [x] 完成

**正在做**:
- 等待 Codex 接入，准备协同开发 Phase 8 前端

**接口变更说明**:
- `/api/v1/workforce/stores/{id}/employee-health` 响应包含完整 TypeScript Schema，见 `tasks/api-contracts.md`
- 所有¥字段均已是**元（float）**，前端直接展示，无需÷100

**需要 Codex 的任务**:

### 🔴 P0 — WorkforcePage 员工健康 Tab（Phase 8 Month 2 遗留）
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
