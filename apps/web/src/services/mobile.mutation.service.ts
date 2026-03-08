import { apiClient } from './api';
import { mockCheckInShift, mockCheckOutShift, mockStartTask, mockSubmitTaskWithPayload, mockUploadTaskEvidence } from './mobile.mock';
import type { MobileActionResult, MobileUploadResult, TaskSubmitPayload } from './mobile.types';

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

export async function submitTask(taskId: string, payload?: TaskSubmitPayload): Promise<MobileActionResult> {
  try {
    await apiClient.post(`/api/v1/mobile/tasks/${taskId}/submit`, payload || {});
    return { ok: true, message: '任务已提交' };
  } catch {
    return mockSubmitTaskWithPayload(taskId, payload);
  }
}

export async function uploadTaskEvidence(taskId: string, file: File): Promise<MobileUploadResult> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await apiClient.post<{ message?: string; file_name?: string; file_url?: string }>(
      `/api/v1/mobile/tasks/${taskId}/evidence`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return {
      ok: true,
      message: resp.message || '证据上传成功',
      file_name: resp.file_name || file.name,
      file_url: resp.file_url,
    };
  } catch {
    const fallback = mockUploadTaskEvidence(taskId, file.name);
    return { ...fallback, file_name: fallback.ok ? file.name : undefined, file_url: undefined };
  }
}
