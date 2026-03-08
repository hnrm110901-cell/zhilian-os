export type ShiftStatus = 'upcoming' | 'ongoing' | 'completed' | 'canceled' | 'rest_day';
export type AttendanceStatus = 'not_checked_in' | 'checked_in' | 'checked_out' | 'late' | 'abnormal' | 'absent';
export type TaskPriority = 'p3_low' | 'p2_medium' | 'p1_high' | 'p0_urgent';
export type TaskStatus = 'pending' | 'in_progress' | 'submitted' | 'approved' | 'rejected' | 'expired' | 'completed';

export interface MobileShift {
  shift_id: string;
  shift_name: string;
  shift_date: string;
  start_time: string;
  end_time: string;
  position_name: string;
  shift_status: ShiftStatus;
  attendance_status: AttendanceStatus;
  related_task_count: number;
  can_check_in: boolean;
  can_check_out: boolean;
}

export interface MobileTask {
  task_id: string;
  task_title: string;
  task_type: string;
  priority: TaskPriority;
  task_status: TaskStatus;
  deadline_at: string;
  assignee_name: string;
  need_evidence: boolean;
  need_review: boolean;
}

export interface ShiftSummaryResponse {
  store_id: string;
  date: string;
  shifts: MobileShift[];
}

export interface TaskSummaryResponse {
  store_id: string;
  total: number;
  pending_count: number;
  expired_count: number;
  tasks: MobileTask[];
}
