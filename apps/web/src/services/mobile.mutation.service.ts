import { apiClient } from './api';
import { mockCheckInShift, mockCheckOutShift, mockStartTask, mockSubmitTask } from './mobile.mock';
import type { MobileActionResult } from './mobile.types';

export async function checkInShift(shiftId: string): Promise<MobileActionResult> {
  try {
    await apiClient.post(`/api/v1/mobile/shifts/${shiftId}/check-in`, {});
    return { ok: true, message: '打卡成功' };
  } catch {
    return mockCheckInShift(shiftId);
  }
}

export async function checkOutShift(shiftId: string): Promise<MobileActionResult> {
  try {
    await apiClient.post(`/api/v1/mobile/shifts/${shiftId}/check-out`, {});
    return { ok: true, message: '下班打卡成功' };
  } catch {
    return mockCheckOutShift(shiftId);
  }
}

export async function startTask(taskId: string): Promise<MobileActionResult> {
  try {
    await apiClient.post(`/api/v1/mobile/tasks/${taskId}/start`, {});
    return { ok: true, message: '任务已开始' };
  } catch {
    return mockStartTask(taskId);
  }
}

export async function submitTask(taskId: string): Promise<MobileActionResult> {
  try {
    await apiClient.post(`/api/v1/mobile/tasks/${taskId}/submit`, {});
    return { ok: true, message: '任务已提交' };
  } catch {
    return mockSubmitTask(taskId);
  }
}
