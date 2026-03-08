import type {
  MobileActionResult,
  MobileHomeSummaryResponse,
  MobileShift,
  MobileTask,
  ShiftSummaryResponse,
  TaskSummaryResponse,
} from './mobile.types';

const STORE_ID = localStorage.getItem('store_id') || 'STORE001';

const today = new Date().toISOString().slice(0, 10);

const initialShifts: MobileShift[] = [
  {
    shift_id: 'shift_001',
    shift_name: '午市班',
    shift_date: today,
    start_time: '10:00',
    end_time: '14:00',
    position_name: '楼面主管',
    shift_status: 'upcoming',
    attendance_status: 'not_checked_in',
    related_task_count: 3,
    can_check_in: true,
    can_check_out: false,
  },
  {
    shift_id: 'shift_002',
    shift_name: '晚市班',
    shift_date: today,
    start_time: '17:00',
    end_time: '21:30',
    position_name: '楼面主管',
    shift_status: 'upcoming',
    attendance_status: 'not_checked_in',
    related_task_count: 2,
    can_check_in: false,
    can_check_out: false,
  },
];

const initialTasks: MobileTask[] = [
  {
    task_id: 'task_001',
    task_title: '开市前巡检',
    task_type: 'inspection',
    priority: 'p1_high',
    task_status: 'pending',
    deadline_at: `${today}T10:30:00`,
    assignee_name: '李平',
    need_evidence: true,
    need_review: true,
    task_description: '开市前完成前厅、包厢、洗手间、收银区巡检并确认设备状态。',
    evidence_count: 0,
  },
  {
    task_id: 'task_002',
    task_title: '午市备货确认',
    task_type: 'replenishment',
    priority: 'p2_medium',
    task_status: 'in_progress',
    deadline_at: `${today}T11:00:00`,
    assignee_name: '李平',
    need_evidence: false,
    need_review: false,
    task_description: '核对重点菜品、酱料、酒水库存是否满足午市需求。',
    evidence_count: 0,
  },
  {
    task_id: 'task_003',
    task_title: '包厢服务复拍',
    task_type: 'service',
    priority: 'p2_medium',
    task_status: 'rejected',
    deadline_at: `${today}T15:00:00`,
    assignee_name: '李平',
    need_evidence: true,
    need_review: true,
    task_description: '因上一版照片不清晰，需要补拍包厢全景与台面细节。',
    reject_reason: '照片不清晰，请补拍包厢全景与台面细节。',
    evidence_count: 1,
  },
  {
    task_id: 'task_004',
    task_title: '催菜超时异常处置',
    task_type: 'incident_handle',
    priority: 'p0_urgent',
    task_status: 'expired',
    deadline_at: `${today}T09:40:00`,
    assignee_name: '李平',
    need_evidence: false,
    need_review: false,
    task_description: '联系后厨确认催菜原因并回填处理结果。',
    evidence_count: 0,
  },
];

const mockState: {
  shifts: MobileShift[];
  tasks: MobileTask[];
} = {
  shifts: JSON.parse(JSON.stringify(initialShifts)),
  tasks: JSON.parse(JSON.stringify(initialTasks)),
};

function clone<T>(data: T): T {
  return JSON.parse(JSON.stringify(data));
}

export function getMockShiftSummary(date: string): ShiftSummaryResponse {
  return {
    store_id: STORE_ID,
    date,
    shifts: clone(mockState.shifts).map((s) => ({ ...s, shift_date: date })),
  };
}

export function getMockTaskSummary(): TaskSummaryResponse {
  const tasks = clone(mockState.tasks);
  return {
    store_id: STORE_ID,
    total: tasks.length,
    pending_count: tasks.filter((t) => t.task_status === 'pending' || t.task_status === 'rejected').length,
    expired_count: tasks.filter((t) => t.task_status === 'expired').length,
    tasks,
  };
}

export function getMockHomeSummary(): MobileHomeSummaryResponse {
  const tasks = clone(mockState.tasks);
  const shifts = clone(mockState.shifts);
  return {
    store_id: STORE_ID,
    as_of: new Date().toISOString(),
    role_name: '店长',
    unread_alerts_count: tasks.filter((t) => t.task_status === 'expired').length,
    pending_approvals_count: 1,
    today_revenue_yuan: 28650,
    food_cost_pct: 31.8,
    waiting_count: 7,
    health_score: 82,
    health_level: 'good',
    weakest_dimension: '成本率',
    today_shift: shifts[0] || null,
    top_tasks: tasks
      .filter((t) => ['pending', 'in_progress', 'rejected', 'expired'].includes(t.task_status))
      .sort((a, b) => {
        const priorityWeight: Record<string, number> = { p0_urgent: 0, p1_high: 1, p2_medium: 2, p3_low: 3 };
        return (priorityWeight[a.priority] || 9) - (priorityWeight[b.priority] || 9);
      })
      .slice(0, 3),
  };
}

export function mockCheckInShift(shiftId: string): MobileActionResult {
  const shift = mockState.shifts.find((s) => s.shift_id === shiftId);
  if (!shift) return { ok: false, message: '班次不存在' };
  if (!shift.can_check_in) return { ok: false, message: '当前不在可打卡窗口' };
  if (shift.attendance_status !== 'not_checked_in') return { ok: false, message: '该班次已打卡' };
  shift.attendance_status = 'checked_in';
  shift.shift_status = 'ongoing';
  shift.can_check_in = false;
  shift.can_check_out = true;
  return { ok: true, message: '打卡成功' };
}

export function mockCheckOutShift(shiftId: string): MobileActionResult {
  const shift = mockState.shifts.find((s) => s.shift_id === shiftId);
  if (!shift) return { ok: false, message: '班次不存在' };
  if (!shift.can_check_out) return { ok: false, message: '当前不能下班打卡' };
  if (shift.attendance_status !== 'checked_in') return { ok: false, message: '请先上班打卡' };
  shift.attendance_status = 'checked_out';
  shift.shift_status = 'completed';
  shift.can_check_out = false;
  return { ok: true, message: '下班打卡成功' };
}

export function mockStartTask(taskId: string): MobileActionResult {
  const task = mockState.tasks.find((t) => t.task_id === taskId);
  if (!task) return { ok: false, message: '任务不存在' };
  if (!['pending', 'rejected'].includes(task.task_status)) {
    return { ok: false, message: `当前状态不可开始：${task.task_status}` };
  }
  task.task_status = 'in_progress';
  return { ok: true, message: '任务已开始' };
}

export function mockSubmitTask(taskId: string): MobileActionResult {
  const task = mockState.tasks.find((t) => t.task_id === taskId);
  if (!task) return { ok: false, message: '任务不存在' };
  if (!['in_progress', 'rejected'].includes(task.task_status)) {
    return { ok: false, message: `当前状态不可提交：${task.task_status}` };
  }
  task.task_status = task.need_review ? 'submitted' : 'completed';
  return { ok: true, message: task.need_review ? '任务已提交，等待审核' : '任务已完成' };
}

export function getMockTaskDetail(taskId: string): MobileTask | null {
  const task = mockState.tasks.find((t) => t.task_id === taskId);
  return task ? clone(task) : null;
}

export function mockSubmitTaskWithPayload(
  taskId: string,
  payload?: { evidence_note?: string; evidence_files?: string[] }
): MobileActionResult {
  const task = mockState.tasks.find((t) => t.task_id === taskId);
  if (!task) return { ok: false, message: '任务不存在' };
  if (!['in_progress', 'rejected'].includes(task.task_status)) {
    return { ok: false, message: `当前状态不可提交：${task.task_status}` };
  }
  const files = payload?.evidence_files || [];
  if (task.need_evidence && !payload?.evidence_note?.trim() && files.length === 0) {
    return { ok: false, message: '该任务要求证据，请填写说明或上传图片' };
  }
  task.evidence_count = (task.evidence_count || 0) + files.length;
  task.task_status = task.need_review ? 'submitted' : 'completed';
  task.reject_reason = undefined;
  return { ok: true, message: task.need_review ? '任务已提交，等待审核' : '任务已完成' };
}

export function mockUploadTaskEvidence(taskId: string, fileName: string): MobileActionResult {
  const task = mockState.tasks.find((t) => t.task_id === taskId);
  if (!task) return { ok: false, message: '任务不存在' };
  if (!fileName) return { ok: false, message: '文件名无效' };
  task.evidence_count = (task.evidence_count || 0) + 1;
  return { ok: true, message: '证据上传成功' };
}
