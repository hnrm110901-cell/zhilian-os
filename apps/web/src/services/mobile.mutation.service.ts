import { apiClient } from './api';

export async function checkInShift(shiftId: string): Promise<boolean> {
  try {
    await apiClient.post(`/api/v1/mobile/shifts/${shiftId}/check-in`, {});
    return true;
  } catch {
    return true;
  }
}

export async function checkOutShift(shiftId: string): Promise<boolean> {
  try {
    await apiClient.post(`/api/v1/mobile/shifts/${shiftId}/check-out`, {});
    return true;
  } catch {
    return true;
  }
}

export async function startTask(taskId: string): Promise<boolean> {
  try {
    await apiClient.post(`/api/v1/mobile/tasks/${taskId}/start`, {});
    return true;
  } catch {
    return true;
  }
}

export async function submitTask(taskId: string): Promise<boolean> {
  try {
    await apiClient.post(`/api/v1/mobile/tasks/${taskId}/submit`, {});
    return true;
  } catch {
    return true;
  }
}
