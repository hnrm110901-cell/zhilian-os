// 岗位层级
export type JobLevel = 'hq' | 'region' | 'store' | 'kitchen' | 'support';
// 岗位分类
export type JobCategory = 'management' | 'front_of_house' | 'back_of_house' | 'support_dept';
// SOP类型
export type SOPType = 'pre_shift' | 'during_service' | 'peak_hour' | 'post_shift' | 'handover' | 'emergency';
// 成长记录类型
export type GrowthTraceType = 'hire' | 'transfer' | 'promote' | 'train_complete' | 'assess' | 'reward' | 'penalty' | 'resign' | 'job_change';

export interface SOPStep {
  step_no: number;
  action: string;
  standard: string;
  check_point: string;
}

export interface JobSOP {
  id: string;
  sop_type: SOPType;
  sop_name: string;
  steps: SOPStep[];
  duration_minutes: number;
  responsible_role: string;
  sort_order: number;
}

export interface KPITarget {
  name: string;
  description: string;
  unit: string;
}

export interface JobStandard {
  id: string;
  job_code: string;
  job_name: string;
  job_level: JobLevel;
  job_category: JobCategory;
  report_to_role: string;
  manages_roles: string;
  job_objective: string;
  responsibilities: string[];
  daily_tasks: string[];
  weekly_tasks: string[];
  monthly_tasks: string[];
  kpi_targets: KPITarget[];
  experience_years_min: number;
  education_requirement: string;
  skill_requirements: string[];
  common_issues: string[];
  industry_category: string;
  is_active: boolean;
  sort_order: number;
  sops?: JobSOP[];
}

export interface EmployeeJobBinding {
  id: string;
  employee_id: string;
  employee_name: string;
  store_id: string;
  job_standard_id: string;
  job_code: string;
  job_name: string;
  bound_at: string;
  is_active: boolean;
  notes?: string;
}

export interface GrowthTrace {
  id: string;
  employee_id: string;
  employee_name: string;
  store_id: string;
  trace_type: GrowthTraceType;
  trace_date: string;
  event_title: string;
  event_detail?: string;
  from_job_code?: string;
  from_job_name?: string;
  to_job_code?: string;
  to_job_name?: string;
  kpi_snapshot?: Record<string, number>;
  assessment_score?: number;
  is_milestone: boolean;
  created_by: string;
}

export interface KPIGapItem {
  name: string;
  target_description: string;
  unit: string;
  gap_level: 'good' | 'warning' | 'danger' | 'unknown';
  note?: string;
}

export interface KPIGapAnalysis {
  employee_id: string;
  employee_name: string;
  job_name: string;
  job_code: string;
  kpi_targets: KPIGapItem[];
  ai_suggestion?: string;
}

export interface StoreCoverage {
  store_id: string;
  covered_jobs: { job_code: string; job_name: string; employee_count: number }[];
  missing_jobs: { job_code: string; job_name: string }[];
}
