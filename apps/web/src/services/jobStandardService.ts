import apiClient from './api';
import type {
  JobStandard,
  GrowthTrace,
  GrowthTraceType,
  KPIGapAnalysis,
  StoreCoverage,
} from '../types/jobStandard';
import {
  mockJobStandardList,
  mockJobStandardDetail,
  mockGrowthTimeline,
  mockKPIGap,
  mockStoreCoverage,
} from '../mock/jobStandard.mock';

const USE_MOCK = true;

const mockDelay = (): Promise<void> => new Promise(r => setTimeout(r, 300));

export const jobStandardService = {
  async listStandards(params?: { level?: string; category?: string }): Promise<JobStandard[]> {
    if (USE_MOCK) {
      await mockDelay();
      let list = mockJobStandardList();
      if (params?.level) {
        list = list.filter(j => j.job_level === params.level);
      }
      if (params?.category) {
        list = list.filter(j => j.job_category === params.category);
      }
      return list;
    }
    return apiClient.get<JobStandard[]>('/api/v1/job-standards', { params });
  },

  async getStandardDetail(jobCode: string): Promise<JobStandard | null> {
    if (USE_MOCK) {
      await mockDelay();
      return mockJobStandardDetail(jobCode);
    }
    return apiClient.get<JobStandard | null>(`/api/v1/job-standards/${jobCode}`);
  },

  async searchStandards(keyword: string): Promise<JobStandard[]> {
    if (USE_MOCK) {
      await mockDelay();
      const lower = keyword.toLowerCase();
      return mockJobStandardList().filter(
        j =>
          j.job_name.includes(keyword) ||
          j.job_code.toLowerCase().includes(lower) ||
          j.job_objective.includes(keyword) ||
          j.responsibilities.some(r => r.includes(keyword)),
      );
    }
    return apiClient.get<JobStandard[]>('/api/v1/job-standards/search', {
      params: { q: keyword },
    });
  },

  async getGrowthTimeline(employeeId: string): Promise<GrowthTrace[]> {
    if (USE_MOCK) {
      await mockDelay();
      return mockGrowthTimeline(employeeId);
    }
    return apiClient.get<GrowthTrace[]>(`/api/v1/employees/${employeeId}/growth-timeline`);
  },

  async getKPIGap(employeeId: string, _storeId: string): Promise<KPIGapAnalysis> {
    if (USE_MOCK) {
      await mockDelay();
      return mockKPIGap(employeeId);
    }
    return apiClient.get<KPIGapAnalysis>(`/api/v1/employees/${employeeId}/kpi-gap`);
  },

  async getStoreCoverage(storeId: string): Promise<StoreCoverage> {
    if (USE_MOCK) {
      await mockDelay();
      return mockStoreCoverage(storeId);
    }
    return apiClient.get<StoreCoverage>(`/api/v1/stores/${storeId}/job-coverage`);
  },

  async addGrowthTrace(payload: {
    employee_id: string;
    employee_name: string;
    store_id: string;
    trace_type: GrowthTraceType;
    event_title: string;
    event_detail?: string;
    is_milestone?: boolean;
  }): Promise<GrowthTrace> {
    if (USE_MOCK) {
      await mockDelay();
      const newTrace: GrowthTrace = {
        id: `gt-${Date.now()}`,
        employee_id: payload.employee_id,
        employee_name: payload.employee_name,
        store_id: payload.store_id,
        trace_type: payload.trace_type,
        trace_date: new Date().toISOString().slice(0, 10),
        event_title: payload.event_title,
        event_detail: payload.event_detail,
        is_milestone: payload.is_milestone ?? false,
        created_by: '当前用户',
      };
      return newTrace;
    }
    return apiClient.post<GrowthTrace>(
      `/api/v1/employees/${payload.employee_id}/growth-timeline`,
      payload,
    );
  },
};
