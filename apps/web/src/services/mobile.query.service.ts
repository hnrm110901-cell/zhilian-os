import { apiClient } from './api';
import { mobileShiftsMock, mobileTasksMock } from './mobile.mock';
import type { ShiftSummaryResponse, TaskSummaryResponse } from './mobile.types';

const STORE_ID = localStorage.getItem('store_id') || 'STORE001';

export async function queryShiftSummary(date: string): Promise<ShiftSummaryResponse> {
  try {
    const resp = await apiClient.get<ShiftSummaryResponse>(`/api/v1/mobile/shifts/summary`, {
      params: { store_id: STORE_ID, date },
    });
    return resp;
  } catch {
    return { ...mobileShiftsMock, date };
  }
}

export async function queryTaskSummary(): Promise<TaskSummaryResponse> {
  try {
    const resp = await apiClient.get<TaskSummaryResponse>(`/api/v1/mobile/tasks/summary`, {
      params: { store_id: STORE_ID },
    });
    return resp;
  } catch {
    return mobileTasksMock;
  }
}
