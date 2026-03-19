// 日清日结 + 周复盘 Mock 数据
// 场景覆盖：正常日 / 黄灯日 / 红灯亏损日 / 周复盘草稿 / 任务闭环

import type {
  StoreDailyMetric,
  StoreDailySettlement,
  WarningRecord,
  ActionTask,
  WeeklyReview,
  DataQualityCheckResponse,
} from '../types/dailyOps';

// ── 日经营数据 Mock ──────────────────────────────────────
export const dailyMetricsMockMap: Record<string, StoreDailyMetric> = {
  // 正常盈利日
  'STORE_001_2025-02-07': {
    storeId: 'STORE_001',
    storeName: '钟村店',
    bizDate: '2025-02-07',
    totalSalesAmount: 23880,
    actualReceiptsAmount: 20560,
    dineInSalesAmount: 17120,
    deliverySalesAmount: 3440,
    foodSalesAmount: 22150,
    beverageSalesAmount: 1230,
    otherSalesAmount: 500,
    foodCostAmount: 2420,
    laborCostAmount: 4900,
    totalDiscountAmount: 2150,
    grossProfitAmount: 13160,
    grossProfitRate: 0.5511,
    netProfitAmount: 6729.95,
    netProfitRate: 0.2818,
    foodCostRate: 0.1093,
    laborCostRate: 0.2052,
    discountRate: 0.09,
    dineInSalesRate: 0.8327,
    deliverySalesRate: 0.1673,
    frontStaffCount: 8,
    kitchenStaffCount: 10,
    totalStaffCount: 18,
    warningLevel: 'green',
  },
  // 红灯亏损日（成本+折扣双超红线）
  'STORE_001_2025-02-08': {
    storeId: 'STORE_001',
    storeName: '钟村店',
    bizDate: '2025-02-08',
    totalSalesAmount: 17250,
    actualReceiptsAmount: 14880,
    dineInSalesAmount: 11850,
    deliverySalesAmount: 3030,
    foodSalesAmount: 15880,
    beverageSalesAmount: 970,
    otherSalesAmount: 400,
    foodCostAmount: 8120,
    laborCostAmount: 3650,
    totalDiscountAmount: 2580,
    grossProfitAmount: 5200,
    grossProfitRate: 0.3014,
    netProfitAmount: -620,
    netProfitRate: -0.036,
    foodCostRate: 0.471,
    laborCostRate: 0.2116,
    discountRate: 0.1496,
    dineInSalesRate: 0.7964,
    deliverySalesRate: 0.2036,
    frontStaffCount: 8,
    kitchenStaffCount: 11,
    totalStaffCount: 19,
    warningLevel: 'red',
  },
  // 黄灯日（折扣偏高）
  'STORE_001_2025-02-09': {
    storeId: 'STORE_001',
    storeName: '钟村店',
    bizDate: '2025-02-09',
    totalSalesAmount: 28700,
    actualReceiptsAmount: 24780,
    dineInSalesAmount: 21480,
    deliverySalesAmount: 3300,
    foodSalesAmount: 26800,
    beverageSalesAmount: 1500,
    otherSalesAmount: 400,
    foodCostAmount: 4180,
    laborCostAmount: 5200,
    totalDiscountAmount: 3020,
    grossProfitAmount: 17620,
    grossProfitRate: 0.6139,
    netProfitAmount: 2905.98,
    netProfitRate: 0.1013,
    foodCostRate: 0.156,
    laborCostRate: 0.1812,
    discountRate: 0.1052,
    dineInSalesRate: 0.8668,
    deliverySalesRate: 0.1332,
    frontStaffCount: 8,
    kitchenStaffCount: 11,
    totalStaffCount: 19,
    warningLevel: 'yellow',
  },
};

export function getDailyMetricMock(storeId: string, bizDate: string): StoreDailyMetric {
  return (
    dailyMetricsMockMap[`${storeId}_${bizDate}`] ?? {
      storeId,
      storeName: '未知门店',
      bizDate,
      totalSalesAmount: 0,
      actualReceiptsAmount: 0,
      dineInSalesAmount: 0,
      deliverySalesAmount: 0,
      foodSalesAmount: 0,
      beverageSalesAmount: 0,
      otherSalesAmount: 0,
      foodCostAmount: 0,
      laborCostAmount: 0,
      totalDiscountAmount: 0,
      grossProfitAmount: 0,
      grossProfitRate: 0,
      netProfitAmount: 0,
      netProfitRate: 0,
      foodCostRate: 0,
      laborCostRate: 0,
      discountRate: 0,
      dineInSalesRate: 0,
      deliverySalesRate: 0,
      warningLevel: 'green',
    }
  );
}

// ── 日结单 Mock ──────────────────────────────────────────
export const dailySettlementMockMap: Record<string, StoreDailySettlement> = {
  'STORE_001_2025-02-08': {
    settlementNo: 'DS20250208STORE001',
    storeId: 'STORE_001',
    bizDate: '2025-02-08',
    status: 'abnormal_wait_comment',
    warningLevel: 'red',
    warningCount: 3,
    majorIssueTypes: ['food_cost_high', 'discount_high', 'sales_drop'],
    autoSummary:
      '今日菜品成本率 47.1%（红线 35%），折扣率 14.96%（红线 12%），净利为负 ¥-620，需提交说明并制定明日整改计划。',
    managerComment: '',
    chefComment: '',
    financeComment: '',
    nextDayActionPlan: '',
  },
  'STORE_001_2025-02-07': {
    settlementNo: 'DS20250207STORE001',
    storeId: 'STORE_001',
    bizDate: '2025-02-07',
    status: 'approved',
    warningLevel: 'green',
    warningCount: 0,
    majorIssueTypes: [],
    autoSummary: '今日经营整体正常，成本率与净利率表现健康。',
    managerComment: '晚市表现较好，翻台效率较高。',
    chefComment: '备货与报损控制正常。',
    financeComment: '',
    nextDayActionPlan: '维持周末高峰备货节奏。',
    submittedBy: 'EMP_SM_001',
    submittedAt: '2025-02-07 22:45:00',
    reviewedBy: 'EMP_AM_001',
    reviewedAt: '2025-02-08 09:30:00',
    reviewComment: '日结说明完整。',
  },
  'STORE_001_2025-02-09': {
    settlementNo: 'DS20250209STORE001',
    storeId: 'STORE_001',
    bizDate: '2025-02-09',
    status: 'pending_confirm',
    warningLevel: 'yellow',
    warningCount: 1,
    majorIssueTypes: ['discount_high'],
    autoSummary: '今日折扣率 10.52% 略超黄线，其他指标正常，请确认后提交。',
    managerComment: '',
    chefComment: '',
    nextDayActionPlan: '',
  },
};

export function getDailySettlementMock(storeId: string, bizDate: string): StoreDailySettlement {
  return (
    dailySettlementMockMap[`${storeId}_${bizDate}`] ?? {
      settlementNo: `DS${bizDate.replaceAll('-', '')}${storeId}`,
      storeId,
      bizDate,
      status: 'pending_confirm',
      warningLevel: 'green',
      warningCount: 0,
      majorIssueTypes: [],
      autoSummary: '今日数据正常。',
      managerComment: '',
      chefComment: '',
      nextDayActionPlan: '',
    }
  );
}

// ── 预警记录 Mock ─────────────────────────────────────────
export const warningMockMap: Record<string, WarningRecord[]> = {
  'STORE_001_2025-02-08': [
    {
      id: 1,
      ruleCode: 'FOOD_COST_RATE_HIGH',
      ruleName: '菜品成本率过高',
      warningType: 'food_cost_high',
      metricCode: 'food_cost_rate',
      actualValue: 0.471,
      baselineValue: 0.33,
      yellowThresholdValue: '0.33',
      redThresholdValue: '0.35',
      warningLevel: 'red',
      status: 'linked_task',
    },
    {
      id: 2,
      ruleCode: 'DISCOUNT_RATE_HIGH',
      ruleName: '折扣率过高',
      warningType: 'discount_high',
      metricCode: 'discount_rate',
      actualValue: 0.1496,
      baselineValue: 0.1,
      yellowThresholdValue: '0.10',
      redThresholdValue: '0.12',
      warningLevel: 'red',
      status: 'linked_task',
    },
    {
      id: 3,
      ruleCode: 'NET_PROFIT_RATE_LOW',
      ruleName: '净利率过低',
      warningType: 'sales_drop',
      metricCode: 'net_profit_rate',
      actualValue: -0.036,
      baselineValue: 0.08,
      yellowThresholdValue: '0.08',
      redThresholdValue: '0.00',
      warningLevel: 'red',
      status: 'active',
    },
  ],
  'STORE_001_2025-02-09': [
    {
      id: 4,
      ruleCode: 'DISCOUNT_RATE_HIGH',
      ruleName: '折扣率过高',
      warningType: 'discount_high',
      metricCode: 'discount_rate',
      actualValue: 0.1052,
      baselineValue: 0.1,
      yellowThresholdValue: '0.10',
      redThresholdValue: '0.12',
      warningLevel: 'yellow',
      status: 'active',
    },
  ],
};

export function getWarningsMock(storeId: string, bizDate: string): WarningRecord[] {
  return warningMockMap[`${storeId}_${bizDate}`] ?? [];
}

// ── 整改任务 Mock ────────────────────────────────────────
export const actionTasksMockList: ActionTask[] = [
  {
    id: 1,
    taskNo: 'TASK_20250208_001',
    storeId: 'STORE_001',
    bizDate: '2025-02-08',
    taskType: 'food_cost_review',
    taskTitle: '菜品成本率异常复盘',
    taskDescription: '2月8日成本率达47.1%，超过红线35%，需立即排查报损和备货。',
    severityLevel: 'red',
    assigneeId: 'EMP_CHEF_001',
    assigneeRole: 'chef',
    reviewerId: 'EMP_AM_001',
    dueAt: '2025-02-09 11:00:00',
    status: 'pending_handle',
    submitComment: '',
    reviewComment: '',
    isRepeatedIssue: true,
    repeatCount: 2,
  },
  {
    id: 2,
    taskNo: 'TASK_20250208_002',
    storeId: 'STORE_001',
    bizDate: '2025-02-08',
    taskType: 'discount_review',
    taskTitle: '折扣率异常复盘',
    taskDescription: '2月8日折扣率14.96%，超过红线12%，需说明折扣原因。',
    severityLevel: 'red',
    assigneeId: 'EMP_SM_001',
    assigneeRole: 'store_manager',
    reviewerId: 'EMP_AM_001',
    dueAt: '2025-02-09 11:00:00',
    status: 'submitted',
    submitComment: '晚市平台活动叠加门店临时优惠，导致折扣率偏高，已暂停临时优惠。',
    reviewComment: '',
    isRepeatedIssue: false,
    repeatCount: 0,
  },
];

export function getActionTasksMock(filters?: {
  storeId?: string;
  bizDate?: string;
  status?: string;
  assigneeId?: string;
}): ActionTask[] {
  return actionTasksMockList.filter((task) => {
    if (filters?.storeId && task.storeId !== filters.storeId) return false;
    if (filters?.bizDate && task.bizDate !== filters.bizDate) return false;
    if (filters?.status && task.status !== filters.status) return false;
    if (filters?.assigneeId && task.assigneeId !== filters.assigneeId) return false;
    return true;
  });
}

// ── 周复盘 Mock ──────────────────────────────────────────
export const weeklyReviewMockMap: Record<string, WeeklyReview> = {
  'STORE_001_2025-02-03_2025-02-09': {
    reviewNo: 'WR_STORE001_2025W06',
    reviewScope: 'store',
    scopeId: 'STORE_001',
    weekStartDate: '2025-02-03',
    weekEndDate: '2025-02-09',
    salesTargetAmount: 140000,
    actualSalesAmount: 128500,
    targetAchievementRate: 0.9179,
    grossProfitRate: 0.442,
    netProfitRate: 0.102,
    profitDayCount: 5,
    lossDayCount: 1,
    abnormalDayCount: 3,
    costAbnormalDayCount: 2,
    discountAbnormalDayCount: 2,
    laborAbnormalDayCount: 0,
    submittedTaskCount: 4,
    closedTaskCount: 2,
    pendingTaskCount: 2,
    repeatedIssueCount: 1,
    systemSummary:
      '本周销售 ¥128,500，未达目标（差距 ¥11,500）。成本与折扣异常主要集中在周三和周六，其中周六出现净利为负（-¥620）。海鲜报损偏高为本周核心问题，已复发 2 次。',
    managerSummary: '',
    nextWeekPlan: '',
    nextWeekFocusTargets: {
      foodCostRateTarget: 0.32,
      discountRateTarget: 0.1,
      laborCostRateTarget: 0.19,
    },
    status: 'draft',
  },
};

export function getWeeklyReviewMock(
  storeId: string,
  weekStartDate: string,
  weekEndDate: string,
): WeeklyReview {
  return (
    weeklyReviewMockMap[`${storeId}_${weekStartDate}_${weekEndDate}`] ?? {
      reviewNo: `WR_${storeId}_${weekStartDate}`,
      reviewScope: 'store',
      scopeId: storeId,
      weekStartDate,
      weekEndDate,
      status: 'draft',
      systemSummary: '周数据汇总中...',
    }
  );
}

// ── 数据质量 Mock ─────────────────────────────────────────
export const dataQualityMockMap: Record<string, DataQualityCheckResponse> = {
  'STORE_001_2025-02-08': {
    storeId: 'STORE_001',
    bizDate: '2025-02-08',
    overallResult: 'fail',
    checks: [
      { checkCode: 'SALES_SPLIT_CHECK', checkName: '销售拆分校验', checkResult: 'pass' },
      {
        checkCode: 'DISCOUNT_RATE_RANGE',
        checkName: '折扣率范围校验',
        checkResult: 'fail',
        errorMessage: '折扣率 14.96% 超过红线 12%',
      },
      {
        checkCode: 'FOOD_COST_RATE_RANGE',
        checkName: '菜品成本率范围校验',
        checkResult: 'fail',
        errorMessage: '菜品成本率 47.1% 超过红线 35%',
      },
      { checkCode: 'RECEIPTS_SPLIT_CHECK', checkName: '实收构成校验', checkResult: 'pass' },
    ],
  },
};

export function getDataQualityMock(storeId: string, bizDate: string): DataQualityCheckResponse {
  return (
    dataQualityMockMap[`${storeId}_${bizDate}`] ?? {
      storeId,
      bizDate,
      overallResult: 'pass',
      checks: [],
    }
  );
}
