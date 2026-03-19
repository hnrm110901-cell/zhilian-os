// 日清日结 + 周复盘 Service 层
// 使用项目约定的 apiClient（非 TanStack Query）
// USE_MOCK = true 时使用 Mock 数据，切换为 false 接真实 API
//
// 注意：apiClient.get<T>() / post<T>() 直接返回 T（非 {data: T}），
// 因为 APIClient.request<T>() 内部直接 return response.json()

import { apiClient } from '../utils/apiClient';
import {
  getDailyMetricMock,
  getDailySettlementMock,
  getWarningsMock,
  getActionTasksMock,
  getWeeklyReviewMock,
  getDataQualityMock,
} from '../mock/dailyOps.mock';
import type {
  StoreDailyMetric,
  DailyMetricSummary,
  StoreDailySettlement,
  SubmitSettlementPayload,
  ReviewSettlementPayload,
  WarningRecord,
  WarningRule,
  ActionTask,
  SubmitTaskPayload,
  ReviewTaskPayload,
  WeeklyReview,
  WeeklyReviewItem,
  SubmitWeeklyReviewPayload,
  DataQualityCheckResponse,
} from '../types/dailyOps';

// 控制开关：切换 true→false 即接真实 API
const USE_MOCK = true;
const MOCK_DELAY_MS = 300;

function mockDelay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_DELAY_MS));
}

// ── 日经营数据 ──────────────────────────────────────────────
export const dailyMetricsService = {
  async getByDate(storeId: string, bizDate: string): Promise<StoreDailyMetric> {
    if (USE_MOCK) return mockDelay(getDailyMetricMock(storeId, bizDate));
    return apiClient.get<StoreDailyMetric>(
      `/api/v1/store-daily-metrics/${storeId}?bizDate=${bizDate}`,
    );
  },

  async getSummary(storeId: string, bizDate: string): Promise<DailyMetricSummary> {
    if (USE_MOCK) {
      const metric = getDailyMetricMock(storeId, bizDate);
      return mockDelay({
        storeId,
        bizDate,
        summary:
          metric.warningLevel === 'red'
            ? '今日销售、成本或折扣存在明显异常，请立即复盘。'
            : metric.warningLevel === 'yellow'
              ? '今日部分指标接近预警阈值，请关注。'
              : '今日经营整体正常，请关注明日营业准备。',
        warningCount: metric.warningLevel === 'red' ? 3 : metric.warningLevel === 'yellow' ? 1 : 0,
        warningLevel: metric.warningLevel,
        majorIssueTypes:
          metric.warningLevel === 'red' ? ['food_cost_high', 'discount_high', 'sales_drop'] : [],
      } as DailyMetricSummary);
    }
    return apiClient.get<DailyMetricSummary>(
      `/api/v1/store-daily-metrics/${storeId}/summary?bizDate=${bizDate}`,
    );
  },
};

// ── 日结单 ──────────────────────────────────────────────────
export const dailySettlementService = {
  async getDetail(storeId: string, bizDate: string): Promise<StoreDailySettlement> {
    if (USE_MOCK) return mockDelay(getDailySettlementMock(storeId, bizDate));
    return apiClient.get<StoreDailySettlement>(
      `/api/v1/daily-settlements/${storeId}?bizDate=${bizDate}`,
    );
  },

  async submit(
    payload: SubmitSettlementPayload,
  ): Promise<{ success: boolean; settlementNo: string; status: string }> {
    if (USE_MOCK) {
      return mockDelay({
        success: true,
        settlementNo: `DS${payload.bizDate.replaceAll('-', '')}${payload.storeId}`,
        status: 'pending_review',
      });
    }
    return apiClient.post<{ success: boolean; settlementNo: string; status: string }>(
      '/api/v1/daily-settlements/submit',
      payload,
    );
  },

  async review(
    payload: ReviewSettlementPayload,
  ): Promise<{ success: boolean; status: string }> {
    if (USE_MOCK) {
      return mockDelay({
        success: true,
        status: payload.action === 'approve' ? 'approved' : 'returned',
      });
    }
    return apiClient.post<{ success: boolean; status: string }>(
      '/api/v1/daily-settlements/review',
      payload,
    );
  },
};

// ── 预警记录 ────────────────────────────────────────────────
export const warningService = {
  async listByDate(storeId: string, bizDate: string): Promise<WarningRecord[]> {
    if (USE_MOCK) return mockDelay(getWarningsMock(storeId, bizDate));
    const result = await apiClient.get<{ warnings: WarningRecord[] }>(
      `/api/v1/warnings/${storeId}?bizDate=${bizDate}`,
    );
    return result.warnings;
  },

  async listRules(): Promise<WarningRule[]> {
    if (USE_MOCK) return mockDelay([]);
    const result = await apiClient.get<{ items: WarningRule[] }>('/api/v1/warning-rules');
    return result.items;
  },
};

// ── 整改任务 ────────────────────────────────────────────────
export const actionTaskService = {
  async list(filters: {
    storeId?: string;
    bizDate?: string;
    status?: string;
    assigneeId?: string;
  }): Promise<ActionTask[]> {
    if (USE_MOCK) return mockDelay(getActionTasksMock(filters));
    const search = new URLSearchParams();
    if (filters.storeId) search.set('storeId', filters.storeId);
    if (filters.bizDate) search.set('bizDate', filters.bizDate);
    if (filters.status) search.set('status', filters.status);
    if (filters.assigneeId) search.set('assigneeId', filters.assigneeId);
    const result = await apiClient.get<{ items: ActionTask[] }>(
      `/api/v1/action-tasks?${search.toString()}`,
    );
    return result.items;
  },

  async submit(
    taskId: string | number,
    payload: SubmitTaskPayload,
  ): Promise<{ success: boolean; taskId: string | number; status: string }> {
    if (USE_MOCK) {
      return mockDelay({ success: true, taskId, status: 'pending_review' });
    }
    return apiClient.post<{ success: boolean; taskId: string | number; status: string }>(
      `/api/v1/action-tasks/${taskId}/submit`,
      payload,
    );
  },

  async review(
    taskId: string | number,
    payload: ReviewTaskPayload,
  ): Promise<{ success: boolean; taskId: string | number; status: string }> {
    if (USE_MOCK) {
      return mockDelay({
        success: true,
        taskId,
        status: payload.action === 'approve' ? 'rectifying' : 'returned',
      });
    }
    return apiClient.post<{ success: boolean; taskId: string | number; status: string }>(
      `/api/v1/action-tasks/${taskId}/review`,
      payload,
    );
  },

  async close(
    taskId: string | number,
    closeComment: string,
  ): Promise<{ success: boolean }> {
    if (USE_MOCK) return mockDelay({ success: true });
    return apiClient.post<{ success: boolean }>(
      `/api/v1/action-tasks/${taskId}/close`,
      { closeComment },
    );
  },
};

// ── 周复盘 ──────────────────────────────────────────────────
export const weeklyReviewService = {
  async getStoreReview(
    storeId: string,
    weekStartDate: string,
    weekEndDate: string,
  ): Promise<WeeklyReview> {
    if (USE_MOCK) return mockDelay(getWeeklyReviewMock(storeId, weekStartDate, weekEndDate));
    return apiClient.get<WeeklyReview>(
      `/api/v1/weekly-reviews/store/${storeId}?weekStartDate=${weekStartDate}&weekEndDate=${weekEndDate}`,
    );
  },

  async submitStoreReview(
    storeId: string,
    payload: SubmitWeeklyReviewPayload,
  ): Promise<{ success: boolean; status: string }> {
    if (USE_MOCK) {
      return mockDelay({ success: true, status: 'pending_review' });
    }
    return apiClient.post<{ success: boolean; status: string }>(
      `/api/v1/weekly-reviews/store/${storeId}/submit`,
      payload,
    );
  },

  async getItems(reviewId: string): Promise<WeeklyReviewItem[]> {
    if (USE_MOCK) return mockDelay([]);
    const result = await apiClient.get<{ items: WeeklyReviewItem[] }>(
      `/api/v1/weekly-reviews/${reviewId}/items`,
    );
    return result.items;
  },
};

// ── 数据质量 ────────────────────────────────────────────────
export const dataQualityService = {
  async getByDate(storeId: string, bizDate: string): Promise<DataQualityCheckResponse> {
    if (USE_MOCK) return mockDelay(getDataQualityMock(storeId, bizDate));
    return apiClient.get<DataQualityCheckResponse>(
      `/api/v1/data-quality-checks/${storeId}?bizDate=${bizDate}`,
    );
  },
};
