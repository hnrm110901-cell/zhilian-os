// 日清日结 + 周复盘 — TypeScript 类型定义
// 金额单位：元（API 层统一转换，DB 存分）

export type WarningLevel = 'green' | 'yellow' | 'red';
export type IssueType =
  | 'sales_drop'
  | 'food_cost_high'
  | 'discount_high'
  | 'labor_high'
  | 'delivery_profit_low'
  | 'data_quality_issue'
  | 'execution_issue'
  | 'complaint_issue';

// ── 日经营数据 ──────────────────────────────────────────
export interface StoreDailyMetric {
  storeId: string;
  storeName: string;
  bizDate: string; // yyyy-MM-dd
  // 销售（元）
  totalSalesAmount: number;
  actualReceiptsAmount: number;
  dineInSalesAmount: number;
  deliverySalesAmount: number;
  foodSalesAmount: number;
  beverageSalesAmount: number;
  otherSalesAmount: number;
  orderCount?: number;
  tableCount?: number;
  guestCount?: number;
  avgOrderPrice?: number;
  tableTurnoverRate?: number;
  // 成本（元）
  totalCostAmount?: number;
  foodCostAmount?: number;
  laborCostAmount?: number;
  lossCostAmount?: number;
  staffMealCostAmount?: number;
  // 费用（元）
  laborCostAmount2?: number;
  // 优惠（元）
  totalDiscountAmount: number;
  // 结果（率：0.0000~1.0000）
  grossProfitAmount?: number;
  grossProfitRate?: number;
  netProfitAmount?: number;
  netProfitRate?: number;
  foodCostRate?: number;
  laborCostRate?: number;
  discountRate?: number;
  dineInSalesRate?: number;
  deliverySalesRate?: number;
  // 人效
  frontStaffCount?: number;
  kitchenStaffCount?: number;
  totalStaffCount?: number;
  // 预警
  warningLevel: WarningLevel;
}

export interface DailyMetricSummary {
  storeId: string;
  bizDate: string;
  summary: string;
  warningCount: number;
  warningLevel: WarningLevel;
  majorIssueTypes: IssueType[];
}

// ── 日结单 ──────────────────────────────────────────────
export type SettlementStatus =
  | 'pending_collect'
  | 'pending_validate'
  | 'pending_confirm'
  | 'abnormal_wait_comment'
  | 'submitted'
  | 'pending_review'
  | 'approved'
  | 'returned'
  | 'closed';

export interface StoreDailySettlement {
  id?: string;
  settlementNo: string;
  storeId: string;
  bizDate: string;
  status: SettlementStatus;
  warningLevel: WarningLevel;
  warningCount: number;
  majorIssueTypes: IssueType[];
  autoSummary?: string;
  managerComment?: string;
  chefComment?: string;
  financeComment?: string;
  nextDayActionPlan?: string;
  nextDayFocusTargets?: Record<string, number>;
  submittedBy?: string;
  submittedAt?: string;
  reviewedBy?: string;
  reviewedAt?: string;
  reviewComment?: string;
  returnedReason?: string;
}

export interface SubmitSettlementPayload {
  storeId: string;
  bizDate: string;
  managerComment: string;
  chefComment?: string;
  nextDayActionPlan: string;
  nextDayFocusTargets?: Record<string, number>;
}

export interface ReviewSettlementPayload {
  settlementNo: string;
  action: 'approve' | 'return';
  reviewComment: string;
}

// ── 预警记录 ─────────────────────────────────────────────
export type WarningStatus = 'active' | 'linked_task' | 'explained' | 'resolved' | 'ignored';

export interface WarningRecord {
  id: string | number;
  ruleCode: string;
  ruleName: string;
  warningType: IssueType;
  metricCode: string;
  actualValue: number;
  baselineValue?: number;
  yellowThresholdValue?: string;
  redThresholdValue?: string;
  warningLevel: WarningLevel;
  status: WarningStatus;
}

// ── 预警规则 ─────────────────────────────────────────────
export interface WarningRule {
  id: string;
  ruleCode: string;
  ruleName: string;
  businessScope: 'store' | 'region' | 'brand';
  metricCode: string;
  compareOperator: 'gt' | 'gte' | 'lt' | 'lte' | 'between';
  yellowThreshold?: string;
  redThreshold?: string;
  isMandatoryComment: boolean;
  isAutoTask: boolean;
  enabled: boolean;
}

// ── 整改任务 ─────────────────────────────────────────────
export type TaskStatus =
  | 'generated'
  | 'pending_handle'
  | 'submitted'
  | 'pending_review'
  | 'rectifying'
  | 'closed'
  | 'returned'
  | 'repeated'
  | 'canceled';

export interface ActionTask {
  id: string | number;
  taskNo: string;
  storeId: string;
  bizDate: string;
  taskType: string;
  taskTitle: string;
  taskDescription?: string;
  severityLevel: 'yellow' | 'red';
  assigneeId?: string;
  assigneeRole?: 'store_manager' | 'chef' | 'area_manager';
  reviewerId?: string;
  dueAt?: string;
  status: TaskStatus;
  submitComment?: string;
  reviewComment?: string;
  isRepeatedIssue: boolean;
  repeatCount: number;
}

export interface SubmitTaskPayload {
  submitComment: string;
  attachments?: Array<{ name: string; url: string }>;
}

export interface ReviewTaskPayload {
  action: 'approve' | 'return';
  reviewComment: string;
}

// ── 周复盘 ───────────────────────────────────────────────
export type WeeklyReviewStatus =
  | 'draft'
  | 'pending_submit'
  | 'submitted'
  | 'pending_review'
  | 'approved'
  | 'returned'
  | 'archived';

export interface WeeklyReview {
  id?: string;
  reviewNo: string;
  reviewScope: 'store' | 'region' | 'hq';
  scopeId: string;
  weekStartDate: string;
  weekEndDate: string;
  salesTargetAmount?: number;
  actualSalesAmount?: number;
  targetAchievementRate?: number;
  grossProfitRate?: number;
  netProfitRate?: number;
  profitDayCount?: number;
  lossDayCount?: number;
  abnormalDayCount?: number;
  costAbnormalDayCount?: number;
  discountAbnormalDayCount?: number;
  laborAbnormalDayCount?: number;
  submittedTaskCount?: number;
  closedTaskCount?: number;
  pendingTaskCount?: number;
  repeatedIssueCount?: number;
  systemSummary?: string;
  managerSummary?: string;
  nextWeekPlan?: string;
  nextWeekFocusTargets?: {
    foodCostRateTarget?: number;
    discountRateTarget?: number;
    laborCostRateTarget?: number;
    netProfitRateTarget?: number;
  };
  status: WeeklyReviewStatus;
  submittedBy?: string;
  submittedAt?: string;
}

export interface WeeklyReviewItem {
  id?: string;
  weeklyReviewId: string;
  itemType: IssueType;
  title: string;
  description?: string;
  relatedDates?: string[];
  rootCause?: string;
  correctiveAction?: string;
  ownerId?: string;
  ownerRole?: string;
  dueDate?: string;
  status: 'pending' | 'in_progress' | 'done';
}

export interface SubmitWeeklyReviewPayload {
  weekStartDate: string;
  weekEndDate: string;
  managerSummary: string;
  nextWeekPlan: string;
  nextWeekFocusTargets?: Record<string, number>;
}

// ── 数据质量 ─────────────────────────────────────────────
export interface DataQualityCheckItem {
  checkCode: string;
  checkName: string;
  checkResult: 'pass' | 'warn' | 'fail';
  errorMessage?: string;
}

export interface DataQualityCheckResponse {
  storeId: string;
  bizDate: string;
  overallResult: 'pass' | 'warn' | 'fail';
  checks: DataQualityCheckItem[];
}
