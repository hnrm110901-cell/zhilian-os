/**
 * HR 服务层 — 业人一体化前端数据获取
 * 封装所有HR模块API调用
 */
import { apiClient } from './api';

// ── 类型定义 ──────────────────────────────────────────────────

export interface HRBFFData {
  store_id: string;
  overview: HROverview | null;
  efficiency: HREfficiency | null;
  positions: PositionDist[];
  expiring_contracts: ExpiringContract[];
  pending_leaves: number;
  active_jobs: number;
  recent_changes: EmployeeChangeItem[];
}

export interface HROverview {
  total_active_employees: number;
  month_onboard: number;
  month_resign: number;
  contracts_expiring_30d: number;
  pending_leave_requests: number;
  active_job_postings: number;
  attendance_rate_pct: number;
}

export interface HREfficiency {
  headcount: number;
  total_salary_yuan: number;
  revenue_yuan: number;
  hr_efficiency_ratio: number;
  per_capita_revenue_yuan: number;
  labor_cost_rate_pct: number;
}

export interface PositionDist {
  position: string;
  count: number;
}

export interface ExpiringContract {
  id: string;
  employee_id: string;
  employee_name: string;
  end_date: string;
  days_remaining: number;
  renewal_count: number;
}

export interface EmployeeChangeItem {
  id: string;
  employee_id: string;
  employee_name: string;
  change_type: string;
  effective_date: string;
  from_position: string | null;
  to_position: string | null;
}

// ── 薪酬 ──────────────────────────────────────────────────────

export interface SalaryStructure {
  id: string;
  employee_id: string;
  employee_name: string;
  salary_type: string;
  base_salary_fen: number;
  position_allowance_fen: number;
  is_active: boolean;
  effective_date: string;
}

export interface PayrollRecord {
  id: string;
  employee_id: string;
  employee_name: string;
  pay_month: string;
  status: string;
  gross_salary_fen: number;
  total_deduction_fen: number;
  net_salary_fen: number;
  tax_fen: number;
  social_insurance_fen: number;
  overtime_pay_fen: number;
  attendance_days: number | null;
  overtime_hours: number | null;
}

export interface PayrollSummary {
  total_headcount: number;
  total_gross_yuan: number;
  total_net_yuan: number;
  total_tax_yuan: number;
  total_social_yuan: number;
  total_overtime_yuan: number;
  avg_salary_yuan: number;
}

// ── 假勤 ──────────────────────────────────────────────────────

export interface LeaveRequest {
  id: string;
  employee_id: string;
  employee_name: string;
  leave_category: string;
  status: string;
  start_date: string;
  end_date: string;
  leave_days: number;
  reason: string;
}

export interface OvertimeRequest {
  id: string;
  employee_id: string;
  employee_name: string;
  overtime_type: string;
  status: string;
  work_date: string;
  hours: number;
  pay_rate: number;
}

// ── 招聘 ──────────────────────────────────────────────────────

export interface JobPosting {
  id: string;
  title: string;
  position: string;
  headcount: number;
  hired_count: number;
  status: string;
  salary_min_fen: number | null;
  salary_max_fen: number | null;
  urgent: boolean;
  candidate_count?: number;
}

export interface CandidateItem {
  id: string;
  name: string;
  stage: string;
  source: string;
  screening_score: number | null;
  interview_score: number | null;
}

export interface RecruitmentFunnel {
  stage: string;
  count: number;
}

// ── 绩效 ──────────────────────────────────────────────────────

export interface PerformanceReview {
  id: string;
  employee_id: string;
  employee_name: string;
  review_period: string;
  status: string;
  total_score: number | null;
  level: string | null;
  self_score: number | null;
  manager_score: number | null;
}

// ── 合同 ──────────────────────────────────────────────────────

export interface ContractItem {
  id: string;
  employee_id: string;
  employee_name: string;
  contract_no: string;
  contract_type: string;
  status: string;
  start_date: string;
  end_date: string | null;
  renewal_count: number;
}

// ── API 调用 ─────────────────────────────────────────────────

const HR_BASE = '/api/v1/hr';

export const hrService = {
  // ── BFF 聚合 ──
  async getDashboardBFF(storeId: string): Promise<HRBFFData> {
    return apiClient.get(`/api/v1/bff/hr/${storeId}`);
  },

  // ── 仪表盘 ──
  async getOverview(storeId: string): Promise<HROverview> {
    return apiClient.get(`${HR_BASE}/dashboard/overview?store_id=${storeId}`);
  },
  async getEfficiency(storeId: string): Promise<HREfficiency> {
    return apiClient.get(`${HR_BASE}/dashboard/hr-efficiency?store_id=${storeId}`);
  },
  async getPositionDistribution(storeId: string): Promise<{ items: PositionDist[] }> {
    return apiClient.get(`${HR_BASE}/dashboard/position-distribution?store_id=${storeId}`);
  },

  // ── 薪酬 ──
  async getPayrollList(storeId: string, month: string): Promise<{ items: PayrollRecord[] }> {
    return apiClient.get(`/api/v1/payroll/records?store_id=${storeId}&pay_month=${month}`);
  },
  async getPayrollSummary(storeId: string, month: string): Promise<PayrollSummary> {
    return apiClient.get(`/api/v1/payroll/summary?store_id=${storeId}&pay_month=${month}`);
  },
  async batchCalculatePayroll(storeId: string, month: string): Promise<{ calculated: number }> {
    return apiClient.post(`/api/v1/payroll/batch-calculate`, { store_id: storeId, pay_month: month });
  },

  // ── 假勤 ──
  async getLeaveRequests(storeId: string, status?: string): Promise<{ items: LeaveRequest[] }> {
    const params = new URLSearchParams({ store_id: storeId });
    if (status) params.append('status', status);
    return apiClient.get(`${HR_BASE}/leave/requests?${params}`);
  },
  async approveLeave(requestId: string, approverId: string): Promise<void> {
    return apiClient.post(`${HR_BASE}/leave/requests/${requestId}/approve`, { approver_id: approverId });
  },
  async rejectLeave(requestId: string, approverId: string, reason: string): Promise<void> {
    return apiClient.post(`${HR_BASE}/leave/requests/${requestId}/reject`, { approver_id: approverId, reason });
  },

  // ── 招聘 ──
  async getJobPostings(storeId: string): Promise<{ items: JobPosting[] }> {
    return apiClient.get(`${HR_BASE}/recruitment/jobs?store_id=${storeId}`);
  },
  async getCandidates(jobId: string): Promise<{ items: CandidateItem[] }> {
    return apiClient.get(`${HR_BASE}/recruitment/jobs/${jobId}/candidates`);
  },
  async getRecruitmentFunnel(storeId: string): Promise<{ items: RecruitmentFunnel[] }> {
    return apiClient.get(`${HR_BASE}/recruitment/funnel?store_id=${storeId}`);
  },

  // ── 绩效 ──
  async getPerformanceReviews(storeId: string, period?: string): Promise<{ items: PerformanceReview[] }> {
    const params = new URLSearchParams({ store_id: storeId });
    if (period) params.append('period', period);
    return apiClient.get(`${HR_BASE}/performance/reviews?${params}`);
  },

  // ── 合同 ──
  async getContracts(storeId: string): Promise<{ items: ContractItem[] }> {
    return apiClient.get(`${HR_BASE}/contracts?store_id=${storeId}`);
  },
  async getExpiringContracts(storeId: string, days = 60): Promise<{ items: ExpiringContract[] }> {
    return apiClient.get(`${HR_BASE}/contracts/expiring?store_id=${storeId}&days=${days}`);
  },

  // ── 员工变动 ──
  async getEmployeeChanges(storeId: string, limit = 20): Promise<{ items: EmployeeChangeItem[] }> {
    return apiClient.get(`${HR_BASE}/employee-changes?store_id=${storeId}&limit=${limit}`);
  },

  // ── 员工生命周期（试岗→入职→转正）──
  async startTrial(data: TrialData): Promise<{ employee_id: string; trial_end_date: string }> {
    return apiClient.post(`${HR_BASE}/lifecycle/trial`, data);
  },
  async confirmOnboard(data: OnboardData): Promise<{ employee_id: string; probation_end_date: string }> {
    return apiClient.post(`${HR_BASE}/lifecycle/onboard`, data);
  },
  async confirmProbationPass(data: ProbationPassData): Promise<{ employee_id: string; base_salary_yuan: number }> {
    return apiClient.post(`${HR_BASE}/lifecycle/probation-pass`, data);
  },

  // ── 提成 ──
  async getCommissionRules(storeId: string): Promise<{ items: CommissionRuleItem[] }> {
    return apiClient.get(`${HR_BASE}/commission/rules?store_id=${storeId}`);
  },
  async createCommissionRule(data: CommissionRuleData): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/commission/rules`, data);
  },
  async getCommissionRecords(storeId: string, payMonth: string): Promise<{ items: CommissionRecordItem[] }> {
    return apiClient.get(`${HR_BASE}/commission/records?store_id=${storeId}&pay_month=${payMonth}`);
  },

  // ── 奖惩 ──
  async getRewardPenalties(storeId: string, params?: { pay_month?: string; rp_type?: string; status?: string }): Promise<{ items: RewardPenaltyItem[] }> {
    const qs = new URLSearchParams({ store_id: storeId });
    if (params?.pay_month) qs.append('pay_month', params.pay_month);
    if (params?.rp_type) qs.append('rp_type', params.rp_type);
    if (params?.status) qs.append('status', params.status);
    return apiClient.get(`${HR_BASE}/reward-penalty?${qs}`);
  },
  async createRewardPenalty(data: RewardPenaltyData): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/reward-penalty`, data);
  },
  async approveRewardPenalty(id: string): Promise<void> {
    return apiClient.post(`${HR_BASE}/reward-penalty/${id}/approve`, {});
  },
  async rejectRewardPenalty(id: string, reason: string): Promise<void> {
    return apiClient.post(`${HR_BASE}/reward-penalty/${id}/reject?reason=${encodeURIComponent(reason)}`, {});
  },

  // ── 社保公积金 ──
  async getSocialInsuranceConfigs(year?: number): Promise<{ items: SocialInsuranceConfigItem[] }> {
    const qs = year ? `?effective_year=${year}` : '';
    return apiClient.get(`${HR_BASE}/social-insurance/configs${qs}`);
  },
  async createSocialInsuranceConfig(data: SocialInsuranceConfigData): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/social-insurance/configs`, data);
  },
  async getEmployeeInsurances(storeId: string, year?: number): Promise<{ items: EmployeeInsuranceItem[] }> {
    const qs = new URLSearchParams({ store_id: storeId });
    if (year) qs.append('effective_year', String(year));
    return apiClient.get(`${HR_BASE}/social-insurance/employees?${qs}`);
  },
  async setEmployeeInsurance(data: EmployeeInsuranceData): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/social-insurance/employees`, data);
  },

  // ── 员工成长旅程 ──
  async getSkillDefinitions(storeId: string, category?: string): Promise<{ items: SkillDefinitionItem[] }> {
    const qs = new URLSearchParams({ store_id: storeId });
    if (category) qs.append('category', category);
    return apiClient.get(`${HR_BASE}/growth/skills/definitions?${qs}`);
  },
  async getSkillGaps(employeeId: string, storeId: string): Promise<{ employee_name: string; position: string; gaps: SkillGapItem[]; readiness_pct: number }> {
    return apiClient.get(`${HR_BASE}/growth/skills/gaps/${employeeId}?store_id=${storeId}`);
  },
  async getCareerPaths(storeId: string, fromPosition?: string): Promise<{ items: CareerPathItem[] }> {
    const qs = new URLSearchParams({ store_id: storeId });
    if (fromPosition) qs.append('from_position', fromPosition);
    return apiClient.get(`${HR_BASE}/growth/career-paths?${qs}`);
  },
  async getPromotionReadiness(employeeId: string, storeId: string): Promise<unknown> {
    return apiClient.get(`${HR_BASE}/growth/promotion-readiness/${employeeId}?store_id=${storeId}`);
  },
  async getGrowthPlans(storeId: string, employeeId?: string, status?: string): Promise<{ items: GrowthPlanItem[] }> {
    const qs = new URLSearchParams({ store_id: storeId });
    if (employeeId) qs.append('employee_id', employeeId);
    if (status) qs.append('status', status);
    return apiClient.get(`${HR_BASE}/growth/plans?${qs}`);
  },
  async generateGrowthPlan(employeeId: string, storeId: string): Promise<{ plan_id: string; plan_name: string }> {
    return apiClient.post(`${HR_BASE}/growth/plans/generate/${employeeId}?store_id=${storeId}`, {});
  },
  async getMilestones(storeId: string, employeeId?: string, limit = 50): Promise<{ items: MilestoneItem[] }> {
    const qs = new URLSearchParams({ store_id: storeId, limit: String(limit) });
    if (employeeId) qs.append('employee_id', employeeId);
    return apiClient.get(`${HR_BASE}/growth/milestones?${qs}`);
  },
  async scanMilestones(storeId: string): Promise<{ triggered_count: number }> {
    return apiClient.post(`${HR_BASE}/growth/milestones/scan?store_id=${storeId}`, {});
  },
  async getWellbeingInsights(storeId: string): Promise<WellbeingInsights> {
    return apiClient.get(`${HR_BASE}/growth/wellbeing/insights?store_id=${storeId}`);
  },
  async getEmployeeJourney(employeeId: string): Promise<EmployeeJourney> {
    return apiClient.get(`${HR_BASE}/growth/journey/${employeeId}`);
  },

  // ── IM 通讯录同步 ──
  async getIMConfig(brandId: string): Promise<IMConfigResponse> {
    return apiClient.get(`/api/v1/merchants/${brandId}/im/config`);
  },
  async saveIMConfig(brandId: string, data: IMConfigData): Promise<{ brand_id: string; message: string }> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/config`, data);
  },
  async updateIMConfig(brandId: string, data: Partial<IMConfigData>): Promise<{ updated: boolean }> {
    return apiClient.put(`/api/v1/merchants/${brandId}/im/config`, data);
  },
  async testIMConnection(brandId: string): Promise<IMTestResult> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/test-connection`, {});
  },
  async triggerIMSync(brandId: string): Promise<IMSyncResult> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/sync`, {});
  },
  async getIMSyncLogs(brandId: string, limit = 20): Promise<{ items: IMSyncLogItem[] }> {
    return apiClient.get(`/api/v1/merchants/${brandId}/im/sync-logs?limit=${limit}`);
  },
  async getIMDepartments(brandId: string): Promise<IMDepartmentsResponse> {
    return apiClient.get(`/api/v1/merchants/${brandId}/im/departments`);
  },
  async updateDeptStoreMapping(brandId: string, mapping: Record<string, string>): Promise<{ message: string }> {
    return apiClient.put(`/api/v1/merchants/${brandId}/im/department-mapping`, { mapping });
  },
  async syncIMAttendance(brandId: string, days = 7): Promise<{ synced: number; errors: number; total_fetched: number }> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/attendance-sync?days=${days}`, {});
  },
  async sendSelfServiceCommand(imUserid: string, command: string, platform = 'wechat_work'): Promise<{ type: string; title?: string; content: string }> {
    return apiClient.post('/api/v1/im/self-service', { im_userid: imUserid, command, platform });
  },

  // Phase 4: 组织架构同步
  async syncOrgStructure(brandId: string, autoCreateStore = false): Promise<IMOrgSyncResult> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/org-sync`, { auto_create_store: autoCreateStore });
  },

  // Phase 4: 入职引导
  async triggerOnboarding(brandId: string, employeeId: string): Promise<IMOnboardingResult> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/onboarding/${employeeId}`, {});
  },

  // Phase 4: 里程碑通知
  async notifyMilestone(brandId: string, milestoneId: string): Promise<{ notified: boolean; employee_name?: string; milestone_type?: string; title?: string; error?: string }> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/notify-milestone/${milestoneId}`, {});
  },
  async sweepMilestones(brandId: string): Promise<{ total: number; notified: number; errors: number }> {
    return apiClient.post(`/api/v1/merchants/${brandId}/im/sweep-milestones`, {});
  },

  // ── 组织架构 ──
  async getOrganizations(brandId: string): Promise<{ items: OrganizationNode[] }> {
    return apiClient.get(`${HR_BASE}/organizations?brand_id=${brandId}`);
  },

  // ── 花名册导入 ──
  async previewRosterImport(brandId: string, file: File): Promise<ImportPreviewResult> {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post(`${HR_BASE}/import/roster/preview?brand_id=${brandId}`, formData);
  },
  async confirmRosterImport(brandId: string, file: File, storeId?: string): Promise<ImportConfirmResult> {
    const formData = new FormData();
    formData.append('file', file);
    const qs = storeId ? `&store_id=${storeId}` : '';
    return apiClient.post(`${HR_BASE}/import/roster/confirm?brand_id=${brandId}${qs}`, formData);
  },

  // ── 薪酬明细 ──
  async getPayrollDetail(employeeId: string, month: string): Promise<PayrollDetailResult> {
    return apiClient.get(`/api/v1/payroll/detail/${employeeId}/${month}`);
  },

  // ── 合规看板 ──
  async getComplianceDashboard(storeId: string): Promise<ComplianceDashboardData> {
    return apiClient.get(`${HR_BASE}/compliance/dashboard?store_id=${storeId}`);
  },
  async sendComplianceAlerts(storeId: string): Promise<{ sent: boolean; alerts?: string[] }> {
    return apiClient.post(`${HR_BASE}/compliance/send-alerts?store_id=${storeId}`, {});
  },

  // ── 离职回访 ──
  async getExitInterviews(storeId: string): Promise<{ items: ExitInterviewItem[] }> {
    return apiClient.get(`${HR_BASE}/exit-interviews?store_id=${storeId}`);
  },
  async createExitInterview(data: Record<string, unknown>): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/exit-interview`, data);
  },
  async getExitInsights(storeId: string, months?: number): Promise<ExitInsights> {
    const qs = months ? `&months=${months}` : '';
    return apiClient.get(`${HR_BASE}/exit-interview/insights?store_id=${storeId}${qs}`);
  },

  // ── 培训 ──
  async getTrainingCourses(brandId: string, category?: string): Promise<{ items: TrainingCourseItem[] }> {
    const qs = category ? `&category=${category}` : '';
    return apiClient.get(`${HR_BASE}/training/courses?brand_id=${brandId}${qs}`);
  },
  async createTrainingCourse(data: Record<string, unknown>): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/training/courses`, data);
  },
  async enrollCourse(courseId: string, employeeIds: string[], storeId: string): Promise<{ enrolled: number }> {
    return apiClient.post(`${HR_BASE}/training/courses/${courseId}/enroll?store_id=${storeId}&${employeeIds.map(id => `employee_ids=${id}`).join('&')}`, {});
  },
  async getMyCourses(employeeId: string): Promise<{ items: TrainingEnrollmentItem[] }> {
    return apiClient.get(`${HR_BASE}/training/my-courses?employee_id=${employeeId}`);
  },
  async getMentorships(storeId: string): Promise<{ items: MentorshipItem[] }> {
    return apiClient.get(`${HR_BASE}/training/mentorships?store_id=${storeId}`);
  },
  async createMentorship(data: Record<string, unknown>): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/training/mentorships`, data);
  },
  async getTrainingDashboard(brandId: string, storeId?: string): Promise<TrainingDashboardData> {
    const qs = storeId ? `&store_id=${storeId}` : '';
    return apiClient.get(`${HR_BASE}/training/dashboard?brand_id=${brandId}${qs}`);
  },
  async getCertificates(employeeId: string): Promise<{ items: Array<{ certificate_no: string; course_title: string; credits: number; score: number; certified_at: string }> }> {
    return apiClient.get(`${HR_BASE}/training/certificates?employee_id=${employeeId}`);
  },

  // ── 月报 ──
  async getMonthlyReport(storeId: string, month: string, brandId: string): Promise<MonthlyReportData> {
    return apiClient.get(`${HR_BASE}/report/monthly/${storeId}/${month}?brand_id=${brandId}`);
  },
  async getCrossStoreReport(brandId: string, month: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/report/cross-store/${brandId}/${month}`);
  },

  // ── 审批流 ──
  async getApprovalTemplates(brandId: string): Promise<{ items: ApprovalTemplateItem[] }> {
    return apiClient.get(`${HR_BASE}/approval/templates?brand_id=${brandId}`);
  },
  async createApprovalTemplate(data: Record<string, unknown>): Promise<{ success: boolean; template_id: string }> {
    return apiClient.post(`${HR_BASE}/approval/templates`, data);
  },
  async getPendingApprovals(approverId: string, brandId?: string): Promise<{ items: ApprovalInstanceItem[] }> {
    const qs = new URLSearchParams({ approver_id: approverId });
    if (brandId) qs.append('brand_id', brandId);
    return apiClient.get(`${HR_BASE}/approval/pending?${qs}`);
  },
  async submitApproval(data: Record<string, unknown>): Promise<{ success: boolean; instance_id: string }> {
    return apiClient.post(`${HR_BASE}/approval/submit`, data);
  },
  async approveInstance(instanceId: string, approverId: string, approverName: string, comment?: string): Promise<{ success: boolean }> {
    return apiClient.post(`${HR_BASE}/approval/${instanceId}/approve`, { approver_id: approverId, approver_name: approverName, comment });
  },
  async rejectInstance(instanceId: string, approverId: string, approverName: string, comment?: string): Promise<{ success: boolean }> {
    return apiClient.post(`${HR_BASE}/approval/${instanceId}/reject`, { approver_id: approverId, approver_name: approverName, comment });
  },
  async getApprovalHistory(instanceId: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/approval/history/${instanceId}`);
  },

  // ── 离职结算 ──
  async calculateSettlement(data: Record<string, unknown>): Promise<{ success: boolean; data: SettlementRecordItem }> {
    return apiClient.post(`${HR_BASE}/settlement/calculate`, data);
  },
  async createSettlement(data: Record<string, unknown>): Promise<{ success: boolean; data: SettlementRecordItem }> {
    return apiClient.post(`${HR_BASE}/settlement/create`, data);
  },
  async getSettlements(storeId: string, brandId: string, status?: string): Promise<{ data: { items: SettlementRecordItem[]; total: number } }> {
    const qs = new URLSearchParams({ store_id: storeId, brand_id: brandId });
    if (status) qs.append('status', status);
    return apiClient.get(`${HR_BASE}/settlement/list?${qs}`);
  },
  async getSettlement(id: string): Promise<{ data: SettlementRecordItem }> {
    return apiClient.get(`${HR_BASE}/settlement/${id}`);
  },
  async approveSettlement(id: string, approverId: string): Promise<{ success: boolean }> {
    return apiClient.post(`${HR_BASE}/settlement/${id}/approve`, { approver_id: approverId });
  },
  async markSettlementPaid(id: string, paidBy: string): Promise<{ success: boolean }> {
    return apiClient.post(`${HR_BASE}/settlement/${id}/pay`, { paid_by: paidBy });
  },

  // ── 工资条 ──
  async getPayslipPushStatus(storeId: string, payMonth: string): Promise<{ data: PayslipStatusItem[] }> {
    return apiClient.get(`${HR_BASE}/payslip/push-status?store_id=${storeId}&pay_month=${payMonth}`);
  },
  async pushPayslip(employeeId: string, payMonth: string, storeId: string): Promise<Record<string, unknown>> {
    return apiClient.post(`${HR_BASE}/payslip/${employeeId}/${payMonth}/push?store_id=${storeId}`, {});
  },
  async batchPushPayslips(storeId: string, payMonth: string): Promise<Record<string, unknown>> {
    return apiClient.post(`${HR_BASE}/payslip/batch-push`, { store_id: storeId, pay_month: payMonth });
  },
  async getPayslipData(employeeId: string, payMonth: string, storeId: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/payslip/${employeeId}/${payMonth}?store_id=${storeId}`);
  },

  // ── 业务规则 ──
  async getBusinessRules(brandId: string, category?: string): Promise<{ items: BusinessRuleItem[] }> {
    const qs = new URLSearchParams({ brand_id: brandId });
    if (category) qs.append('category', category);
    return apiClient.get(`${HR_BASE}/rules?${qs}`);
  },
  async createBusinessRule(data: Record<string, unknown>): Promise<BusinessRuleItem> {
    return apiClient.post(`${HR_BASE}/rules`, data);
  },
  async updateBusinessRule(id: string, data: Record<string, unknown>): Promise<BusinessRuleItem> {
    return apiClient.put(`${HR_BASE}/rules/${id}`, data);
  },
  async deleteBusinessRule(id: string): Promise<{ deleted: boolean }> {
    return apiClient.delete(`${HR_BASE}/rules/${id}`);
  },
  async getEffectiveRules(brandId: string, storeId: string, position?: string): Promise<Record<string, unknown>> {
    const qs = new URLSearchParams({ brand_id: brandId, store_id: storeId });
    if (position) qs.append('position', position);
    return apiClient.get(`${HR_BASE}/rules/effective?${qs}`);
  },
  async previewPayrollImpact(brandId: string, storeId: string, category: string, proposedRules: Record<string, unknown>): Promise<Record<string, unknown>> {
    return apiClient.post(`${HR_BASE}/rules/preview-payroll-impact?brand_id=${brandId}&store_id=${storeId}&category=${category}`, proposedRules);
  },
  async seedDefaultRules(brandId: string): Promise<{ seeded_count: number }> {
    return apiClient.post(`${HR_BASE}/rules/seed-defaults?brand_id=${brandId}`, {});
  },

  // ── 班次模板 ──
  async getShiftTemplates(brandId: string, storeId?: string): Promise<{ items: ShiftTemplateItem[] }> {
    const qs = new URLSearchParams({ brand_id: brandId });
    if (storeId) qs.append('store_id', storeId);
    return apiClient.get(`${HR_BASE}/attendance/shift-templates?${qs}`);
  },
  async createShiftTemplate(data: Record<string, unknown>): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/attendance/shift-templates`, data);
  },

  // ── 考勤规则 ──
  async getAttendanceRules(brandId: string, storeId?: string): Promise<{ items: AttendanceRuleItem[] }> {
    const qs = new URLSearchParams({ brand_id: brandId });
    if (storeId) qs.append('store_id', storeId);
    return apiClient.get(`${HR_BASE}/attendance/rules?${qs}`);
  },
  async createOrUpdateAttendanceRule(data: Record<string, unknown>): Promise<{ id: string; action: string }> {
    return apiClient.post(`${HR_BASE}/attendance/rules`, data);
  },

  // ── 员工自助 ──────────────────────────────────────────────────

  async getMyProfile(employeeId: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/self-service/my-profile?employee_id=${employeeId}`);
  },

  async getMyPayslip(employeeId: string, month: string, storeId: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/self-service/my-payslip/${month}?employee_id=${employeeId}&store_id=${storeId}`);
  },

  async getMyPayslips(employeeId: string): Promise<Record<string, unknown>[]> {
    return apiClient.get(`${HR_BASE}/self-service/my-payslips?employee_id=${employeeId}`);
  },

  async confirmMyPayslip(employeeId: string, month: string, storeId: string): Promise<{ success: boolean }> {
    return apiClient.post(`${HR_BASE}/self-service/my-payslip/${month}/confirm?employee_id=${employeeId}`, { store_id: storeId });
  },

  async getMyAttendance(employeeId: string, month: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/self-service/my-attendance/${month}?employee_id=${employeeId}`);
  },

  async getMyLeaves(employeeId: string): Promise<Record<string, unknown>[]> {
    return apiClient.get(`${HR_BASE}/self-service/my-leaves?employee_id=${employeeId}`);
  },

  async submitLeaveRequest(data: Record<string, unknown>): Promise<{ success: boolean; request_id: string }> {
    return apiClient.post(`${HR_BASE}/self-service/leave-request`, data);
  },

  async getMyLeaveBalance(employeeId: string): Promise<Record<string, unknown>[]> {
    return apiClient.get(`${HR_BASE}/self-service/my-leave-balance?employee_id=${employeeId}`);
  },

  async getMySelfServiceCourses(employeeId: string): Promise<Record<string, unknown>[]> {
    return apiClient.get(`${HR_BASE}/self-service/my-courses?employee_id=${employeeId}`);
  },

  async getMyContract(employeeId: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/self-service/my-contract?employee_id=${employeeId}`);
  },

  // ── 批量操作 ──────────────────────────────────────────────────

  async batchHire(data: { brand_id: string; employees: Record<string, unknown>[] }): Promise<{ success_count: number; failed: { index: number; name: string; error: string }[]; employee_ids: string[] }> {
    return apiClient.post(`${HR_BASE}/batch/hire`, data);
  },
  async batchTransfer(data: { transfers: Record<string, unknown>[] }): Promise<{ success_count: number; failed: Record<string, unknown>[] }> {
    return apiClient.post(`${HR_BASE}/batch/transfer`, data);
  },
  async batchSalaryAdjust(data: { adjustments: Record<string, unknown>[] }): Promise<{ success_count: number; failed: Record<string, unknown>[] }> {
    return apiClient.post(`${HR_BASE}/batch/salary-adjust`, data);
  },
  async batchPayslipPush(data: { store_id: string; pay_month: string; channel: string }): Promise<{ success_count: number; failed_count: number }> {
    return apiClient.post(`${HR_BASE}/batch/payslip-push`, data);
  },
  async batchPayrollCalculate(data: { store_ids: string[]; pay_month: string }): Promise<{ results: Record<string, unknown>[] }> {
    return apiClient.post(`${HR_BASE}/batch/payroll-calculate`, data);
  },
  async batchContractRenew(data: { employee_ids: string[]; new_end_date: string; contract_type?: string }): Promise<{ success_count: number; failed: Record<string, unknown>[] }> {
    return apiClient.post(`${HR_BASE}/batch/contract-renew`, data);
  },

  // ── 智能排班 ──────────────────────────────────────────────────

  async generateWeeklySchedule(storeId: string, weekStart: string, brandId: string): Promise<Record<string, unknown>> {
    return apiClient.post(`${HR_BASE}/scheduling/generate?store_id=${storeId}&week_start=${weekStart}&brand_id=${brandId}`, {});
  },
  async getWeeklySchedule(storeId: string, weekStart: string): Promise<Record<string, unknown>> {
    return apiClient.get(`${HR_BASE}/scheduling/weekly?store_id=${storeId}&week_start=${weekStart}`);
  },
  async publishSchedule(storeId: string, weekStart: string): Promise<{ success: boolean }> {
    return apiClient.post(`${HR_BASE}/scheduling/publish?store_id=${storeId}&week_start=${weekStart}`, {});
  },
  async getStaffingDemand(storeId: string): Promise<Record<string, unknown>[]> {
    return apiClient.get(`${HR_BASE}/scheduling/staffing-demand?store_id=${storeId}`);
  },
  async setStaffingDemand(data: Record<string, unknown>): Promise<{ id: string }> {
    return apiClient.post(`${HR_BASE}/scheduling/staffing-demand`, data);
  },

  // ── 审计日志 ──────────────────────────────────────────────────

  async getAuditLogs(params: { module?: string; operator_id?: string; start_date?: string; end_date?: string; page?: number; page_size?: number }): Promise<{ items: Record<string, unknown>[]; total: number }> {
    const qs = new URLSearchParams();
    if (params.module) qs.append('module', params.module);
    if (params.operator_id) qs.append('operator_id', params.operator_id);
    if (params.start_date) qs.append('start_date', params.start_date);
    if (params.end_date) qs.append('end_date', params.end_date);
    if (params.page) qs.append('page', String(params.page));
    if (params.page_size) qs.append('page_size', String(params.page_size));
    return apiClient.get(`${HR_BASE}/audit/logs?${qs}`);
  },
  async getResourceAuditHistory(resourceType: string, resourceId: string): Promise<Record<string, unknown>[]> {
    return apiClient.get(`${HR_BASE}/audit/history/${resourceType}/${resourceId}`);
  },

  // ── Excel导出 ──────────────────────────────────────────────────

  async exportMonthlyReport(storeId: string, month: string): Promise<Blob> {
    return apiClient.get(`${HR_BASE}/report/monthly/${storeId}/${month}/export`, { responseType: 'blob' });
  },
  async exportPayrollDetail(storeId: string, month: string): Promise<Blob> {
    return apiClient.get(`/api/v1/payroll/export/${storeId}/${month}`, { responseType: 'blob' });
  },
  async exportAttendanceReport(storeId: string, month: string): Promise<Blob> {
    return apiClient.get(`${HR_BASE}/attendance/export/${storeId}/${month}`, { responseType: 'blob' });
  },
  async exportRoster(storeId: string): Promise<Blob> {
    return apiClient.get(`${HR_BASE}/export/roster/${storeId}`, { responseType: 'blob' });
  },

  // ── 决策飞轮 ──
  async getFlywheelDashboard(storeId: string, brandId?: string): Promise<FlywheelDashboard> {
    const params = new URLSearchParams({ store_id: storeId });
    if (brandId) params.append('brand_id', brandId);
    return apiClient.get(`${HR_BASE}/decision-flywheel/dashboard/${storeId}?${params}`);
  },
  async getFlywheelDecisions(storeId: string, opts?: { type?: string; status?: string; limit?: number }): Promise<{ items: DecisionRecordItem[]; total: number }> {
    const params = new URLSearchParams({ store_id: storeId });
    if (opts?.type) params.append('decision_type', opts.type);
    if (opts?.status) params.append('status', opts.status);
    if (opts?.limit) params.append('limit', String(opts.limit));
    return apiClient.get(`${HR_BASE}/decision-flywheel/decisions/${storeId}?${params}`);
  },
  async recordFlywheelAction(decisionId: string, action: string, userId: string, note?: string): Promise<void> {
    return apiClient.post(`${HR_BASE}/decision-flywheel/${decisionId}/action`, {
      user_id: userId, action, note,
    });
  },
  async executeFlywheelDecision(decisionId: string, detail?: Record<string, unknown>): Promise<void> {
    return apiClient.post(`${HR_BASE}/decision-flywheel/${decisionId}/execute`, {
      execution_detail: detail,
    });
  },
  async getFlywheelCalibration(storeId: string): Promise<CalibrationResult> {
    return apiClient.get(`${HR_BASE}/decision-flywheel/calibration/${storeId}`);
  },

  // ── AI决策 ──
  async getTurnoverRisk(employeeId: string, storeId: string): Promise<TurnoverRiskResult> {
    return apiClient.get(`${HR_BASE}/ai/turnover-risk/${employeeId}?store_id=${storeId}`);
  },
  async scanStoreTurnover(storeId: string): Promise<StoreTurnoverScan> {
    return apiClient.get(`${HR_BASE}/ai/turnover-scan/${storeId}`);
  },
};

// ── IM 通讯录同步类型 ──

export interface IMConfigResponse {
  configured: boolean;
  brand_id: string;
  im_platform?: string;
  wechat_corp_id?: string;
  wechat_agent_id?: string;
  has_wechat_secret?: boolean;
  dingtalk_app_key?: string;
  dingtalk_agent_id?: string;
  has_dingtalk_secret?: boolean;
  sync_enabled?: boolean;
  auto_create_user?: boolean;
  auto_disable_user?: boolean;
  default_store_id?: string;
  department_store_mapping?: Record<string, string> | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_message?: string | null;
  last_sync_stats?: Record<string, number> | null;
}

export interface IMConfigData {
  brand_id: string;
  im_platform: string;
  wechat_corp_id?: string;
  wechat_corp_secret?: string;
  wechat_agent_id?: string;
  wechat_token?: string;
  wechat_encoding_aes_key?: string;
  dingtalk_app_key?: string;
  dingtalk_app_secret?: string;
  dingtalk_agent_id?: string;
  dingtalk_aes_key?: string;
  dingtalk_token?: string;
  sync_enabled?: boolean;
  auto_create_user?: boolean;
  auto_disable_user?: boolean;
  default_store_id?: string;
  department_store_mapping?: Record<string, string>;
}

export interface IMDepartmentItem {
  id: number;
  name: string;
  parentid: number | null;
}

export interface IMDepartmentsResponse {
  brand_id: string;
  departments: IMDepartmentItem[];
  current_mapping: Record<string, string>;
}

export interface IMTestResult {
  connected: boolean;
  platform?: string;
  department_count?: number;
  message: string;
  error?: string;
}

export interface IMSyncResult {
  brand_id: string;
  platform: string;
  total_platform_members: number;
  added: number;
  updated: number;
  disabled: number;
  user_created: number;
  user_disabled: number;
  error_count: number;
  message: string;
}

export interface IMSyncLogItem {
  id: string;
  im_platform: string;
  trigger: string;
  status: string;
  message: string | null;
  total_platform_members: number;
  added_count: number;
  updated_count: number;
  disabled_count: number;
  user_created_count: number;
  user_disabled_count: number;
  error_count: number;
  started_at: string | null;
  finished_at: string | null;
}

// ── Phase 4 类型定义 ──

export interface IMOrgSyncResult {
  departments_total: number;
  matched: number;
  region_updated: number;
  stores_created: number;
  unmatched: Array<{ dept_id: number; dept_name: string; parent_name: string; path: string }>;
  error?: string;
}

export interface IMOnboardingResult {
  employee_id: string;
  employee_name: string;
  store_name: string;
  milestone_id: string | null;
  plan_id: string | null;
  total_tasks: number;
  im_sent: boolean;
  error?: string;
}

// ── 组织架构 ──

export interface OrganizationNode {
  id: string;
  name: string;
  code: string;
  parent_id: string | null;
  level: number;
  org_type: string;
  store_id: string | null;
  manager_id: string | null;
  sort_order: number;
}

// ── 花名册导入 ──

export interface ImportPreviewResult {
  total_rows: number;
  total_columns: number;
  matched_columns: number;
  unmatched_columns: string[];
  column_mapping: Record<string, string>;
  preview: Record<string, string | null>[];
}

export interface ImportConfirmResult {
  created: number;
  updated: number;
  skipped: number;
  errors: Array<{ row: number; error: string }>;
}

// ── 薪酬明细 ──

export interface SalaryItemDetail {
  item_name: string;
  item_category: string;
  amount_yuan: number;
  amount_fen: number;
  formula: string | null;
}

export interface PayrollDetailResult {
  employee_id: string;
  pay_month: string;
  items: SalaryItemDetail[];
  total_income_yuan: number;
  total_deduction_yuan: number;
  net_salary_yuan: number;
}

// ── 合规看板 ──

export interface ComplianceDashboardData {
  store_id: string;
  health_cert: {
    expired: number;
    critical: number;
    warning: number;
    items: ComplianceAlertItem[];
  };
  contract: {
    total: number;
    items: ComplianceAlertItem[];
  };
  id_card: {
    total: number;
    items: ComplianceAlertItem[];
  };
  overall_risk_level: string;
}

export interface ComplianceAlertItem {
  employee_id: string;
  employee_name: string;
  position?: string;
  days_remaining: number;
  level: string;
  health_cert_expiry?: string;
  end_date?: string;
  id_card_expiry?: string;
}

// ── 离职回访 ──

export interface ExitInterviewItem {
  id: string;
  employee_id: string;
  employee_name: string | null;
  resign_date: string;
  resign_reason: string;
  resign_detail: string | null;
  interview_date: string | null;
  current_status: string | null;
  willing_to_return: string | null;
  interviewer: string | null;
}

export interface ExitInsights {
  period_months: number;
  total_exits: number;
  reason_distribution: Record<string, number>;
  willing_to_return: Record<string, number>;
  monthly_trend: Record<string, number>;
  ai_suggestion: string;
  return_rate_pct: number;
}

// ── 培训 ──

export interface TrainingCourseItem {
  id: string;
  title: string;
  description: string | null;
  category: string;
  course_type: string;
  applicable_positions: string[] | null;
  duration_minutes: number;
  pass_score: number;
  credits: number;
  is_mandatory: boolean;
  content_url: string | null;
}

export interface TrainingEnrollmentItem {
  enrollment_id: string;
  course_id: string;
  course_title: string;
  category: string;
  course_type: string;
  status: string;
  progress_pct: number;
  score: number | null;
  certificate_no: string | null;
  enrolled_at: string | null;
  completed_at: string | null;
  credits: number;
  is_mandatory: boolean;
}

export interface MentorshipItem {
  id: string;
  target_position: string;
  mentor_id: string;
  mentor_name: string | null;
  apprentice_id: string;
  apprentice_name: string | null;
  enrolled_at: string;
  training_start: string | null;
  training_end: string | null;
  expected_review_date: string | null;
  actual_review_date: string | null;
  review_result: string | null;
  reward_yuan: number;
  status: string;
}

export interface TrainingDashboardData {
  total_courses: number;
  total_enrollments: number;
  enrollment_by_status: Record<string, number>;
  completion_rate_pct: number;
  total_credits_earned: number;
  mentorship_stats: Record<string, number>;
  active_mentorships: number;
  completed_mentorships: number;
}

// ── 月报 ──

export interface MonthlyReportData {
  store_id: string;
  brand_id: string;
  pay_month: string;
  salary_changes: {
    new_count: number;
    resignation_count: number;
    adjustment_count: number;
    new_employees: Array<{ id: string; name: string; position: string; hire_date: string }>;
    resignations: Array<{ employee_id: string; name: string; effective_date: string }>;
  };
  headcount_inventory: {
    total_headcount: number;
    by_position: Record<string, number>;
    by_employment_type: Record<string, number>;
  };
  mentorship_summary: {
    active_count: number;
    completed_this_month: number;
    total_reward_yuan: number;
  };
  hourly_worker_attendance: {
    total_workers: number;
    total_days: number;
    total_pay_yuan: number;
  };
  exit_interview_summary: {
    total_exits: number;
    interviewed_count: number;
    reason_distribution: Record<string, number>;
    interview_rate_pct: number;
  };
  hr_summary: {
    highlights: string[];
    concerns: string[];
    next_month_plans: string[];
    turnover_rate_pct: number;
  };
}

// ── 新增类型定义 ──

export interface TrialData {
  store_id: string;
  employee_id: string;
  name: string;
  position: string;
  hire_date: string;
  phone?: string;
  email?: string;
  wechat_userid?: string;
  trial_days?: number;
}

export interface OnboardData {
  employee_id: string;
  effective_date?: string;
  probation_months?: number;
  probation_salary_pct?: number;
  base_salary_fen: number;
  position_allowance_fen?: number;
  meal_allowance_fen?: number;
  transport_allowance_fen?: number;
  social_insurance_fen?: number;
  housing_fund_fen?: number;
  special_deduction_fen?: number;
  contract_no?: string;
}

export interface ProbationPassData {
  employee_id: string;
  effective_date?: string;
  base_salary_fen?: number;
  performance_coefficient?: number;
}

export interface CommissionRuleItem {
  id: string;
  name: string;
  commission_type: string;
  calc_method: string;
  applicable_positions: string[] | null;
  fixed_amount_yuan: number;
  rate_pct: number;
  tiered_rules: unknown[] | null;
  is_active: boolean;
  effective_date: string;
  expire_date: string | null;
}

export interface CommissionRuleData {
  store_id: string;
  name: string;
  commission_type: string;
  calc_method: string;
  applicable_positions?: string[];
  fixed_amount_fen?: number;
  rate_pct?: number;
  tiered_rules?: unknown[];
  effective_date: string;
}

export interface CommissionRecordItem {
  id: string;
  employee_id: string;
  employee_name: string;
  pay_month: string;
  rule_id: string;
  base_amount_yuan: number;
  base_quantity: number;
  commission_yuan: number;
}

export interface RewardPenaltyItem {
  id: string;
  employee_id: string;
  employee_name: string;
  rp_type: 'reward' | 'penalty';
  category: string;
  status: string;
  amount_yuan: number;
  pay_month: string;
  incident_date: string;
  description: string;
  evidence: string[] | null;
}

export interface RewardPenaltyData {
  store_id: string;
  employee_id: string;
  rp_type: 'reward' | 'penalty';
  category: string;
  amount_fen: number;
  incident_date: string;
  description: string;
  pay_month?: string;
}

export interface SocialInsuranceConfigItem {
  id: string;
  region_code: string;
  region_name: string;
  effective_year: number;
  base_floor_yuan: number;
  base_ceiling_yuan: number;
  pension_employer_pct: number;
  pension_employee_pct: number;
  medical_employer_pct: number;
  medical_employee_pct: number;
  unemployment_employer_pct: number;
  unemployment_employee_pct: number;
  injury_employer_pct: number;
  maternity_employer_pct: number;
  housing_fund_employer_pct: number;
  housing_fund_employee_pct: number;
  total_employer_pct: number;
  total_employee_pct: number;
}

export interface SocialInsuranceConfigData {
  region_code: string;
  region_name: string;
  effective_year: number;
  base_floor_fen: number;
  base_ceiling_fen: number;
  pension_employer_pct?: number;
  pension_employee_pct?: number;
  medical_employer_pct?: number;
  medical_employee_pct?: number;
  unemployment_employer_pct?: number;
  unemployment_employee_pct?: number;
  injury_employer_pct?: number;
  maternity_employer_pct?: number;
  housing_fund_employer_pct?: number;
  housing_fund_employee_pct?: number;
}

export interface EmployeeInsuranceItem {
  id: string;
  employee_id: string;
  employee_name: string;
  position: string;
  region_name: string;
  effective_year: number;
  personal_base_yuan: number;
  has_pension: boolean;
  has_medical: boolean;
  has_unemployment: boolean;
  has_housing_fund: boolean;
  housing_fund_pct_override: number | null;
}

export interface EmployeeInsuranceData {
  store_id: string;
  employee_id: string;
  config_id: string;
  effective_year: number;
  personal_base_fen: number;
  has_pension?: boolean;
  has_medical?: boolean;
  has_unemployment?: boolean;
  has_injury?: boolean;
  has_maternity?: boolean;
  has_housing_fund?: boolean;
  housing_fund_pct_override?: number;
}

// ── 员工成长旅程 ──────────────────────────────────────────

export interface SkillDefinitionItem {
  id: string;
  skill_name: string;
  skill_category: string;
  applicable_positions: string[] | null;
  required_level: string;
  promotion_weight: number;
  description: string | null;
}

export interface SkillGapItem {
  skill_name: string;
  category: string;
  required_level: string;
  current_level: string | null;
  current_score: number;
  gap: string;
}

export interface CareerPathItem {
  id: string;
  path_name: string;
  from_position: string;
  to_position: string;
  min_tenure_months: number;
  min_performance_score: number;
  salary_increase_pct: number;
  description: string | null;
}

export interface MilestoneItem {
  id: string;
  employee_id: string;
  employee_name: string;
  milestone_type: string;
  title: string;
  description: string | null;
  achieved_at: string;
  badge_icon: string | null;
  reward_yuan: number;
}

export interface GrowthPlanItem {
  id: string;
  employee_id: string;
  employee_name: string;
  plan_name: string;
  status: string;
  target_position: string | null;
  progress_pct: number;
  total_tasks: number;
  completed_tasks: number;
  mentor_name: string | null;
  ai_generated: boolean;
  target_date: string | null;
}

export interface WellbeingInsights {
  period: string;
  total_submissions: number;
  avg_overall: number;
  dimensions: Record<string, number>;
  trend: Array<{ period: string; avg: number }>;
  care_warnings: Array<{ employee_id: string; employee_name: string; score: number }>;
}

export interface EmployeeJourney {
  employee: {
    id: string;
    name: string;
    position: string;
    hire_date: string;
    tenure_days: number;
  };
  timeline: Array<{
    date: string;
    type: string;
    title: string;
    description: string | null;
  }>;
  milestones: MilestoneItem[];
  skill_radar: Array<{
    skill_name: string;
    category: string;
    score: number;
    level: string;
  }>;
  growth_plans: GrowthPlanItem[];
  wellbeing: {
    latest_period: string | null;
    overall_score: number;
    dimensions: Record<string, number>;
  } | null;
}

// ── 审批流 ──────────────────────────────────────────────

export interface ApprovalTemplateItem {
  id: string;
  brand_id: string;
  template_code: string;
  template_name: string;
  approval_chain: unknown[];
  amount_thresholds: unknown[];
  description: string | null;
}

export interface ApprovalInstanceItem {
  id: string;
  template_code: string;
  business_type: string;
  business_id: string;
  applicant_id: string;
  applicant_name: string;
  status: string;
  current_level: number;
  amount_fen: number | null;
  summary: string | null;
  deadline: string | null;
  created_at: string | null;
}

// ── 离职结算 ──────────────────────────────────────────────

export interface SettlementRecordItem {
  id: string;
  store_id: string;
  brand_id: string;
  employee_id: string;
  employee_name: string;
  separation_type: string;
  last_work_date: string | null;
  separation_date: string | null;
  work_days_last_month: number;
  last_month_salary_fen: number;
  last_month_salary_yuan: number;
  unused_annual_days: number;
  annual_leave_compensation_fen: number;
  annual_leave_compensation_yuan: number;
  annual_leave_calc_method: string;
  service_years_x10: number;
  compensation_months_x10: number;
  compensation_base_fen: number;
  economic_compensation_fen: number;
  economic_compensation_yuan: number;
  compensation_type: string;
  overtime_pay_fen: number;
  overtime_pay_yuan: number;
  bonus_fen: number;
  bonus_yuan: number;
  deduction_fen: number;
  deduction_yuan: number;
  deduction_detail: string;
  total_payable_fen: number;
  total_payable_yuan: number;
  handover_items: unknown[];
  handover_completed: boolean;
  status: string;
  paid_at: string | null;
  paid_by: string | null;
  remark: string;
  created_at: string | null;
  updated_at: string | null;
}

// ── 工资条 ──────────────────────────────────────────────

export interface PayslipStatusItem {
  employee_id: string;
  employee_name: string;
  pay_month: string;
  push_status: string;
  pushed_at: string | null;
  confirmed: boolean;
  confirmed_at: string | null;
}

// ── 业务规则 ──────────────────────────────────────────────

export interface BusinessRuleItem {
  id: string;
  brand_id: string;
  store_id: string | null;
  position: string | null;
  employment_type: string | null;
  category: string;
  rule_name: string;
  rules_json: Record<string, unknown>;
  priority: number;
  is_active: boolean;
  description: string | null;
}

// ── 班次模板 ──────────────────────────────────────────────

export interface ShiftTemplateItem {
  id: string;
  brand_id: string;
  store_id: string | null;
  name: string;
  code: string;
  start_time: string | null;
  end_time: string | null;
  is_cross_day: boolean;
  break_minutes: number;
  min_work_hours: number | null;
  late_threshold_minutes: number;
  early_leave_threshold_minutes: number;
  applicable_positions: string[];
  is_active: boolean;
  sort_order: number;
}

// ── 决策飞轮 ──────────────────────────────────────────────

export interface DecisionRecordItem {
  id: string;
  store_id: string;
  decision_type: string;
  module: string;
  source: string;
  target_type: string;
  target_id: string | null;
  target_name: string | null;
  recommendation: string;
  risk_score: number | null;
  confidence: number | null;
  predicted_impact_fen: number | null;
  ai_analysis: string | null;
  user_action: string | null;
  user_action_at: string | null;
  executed: boolean;
  executed_at: string | null;
  status: string;
  actual_impact_fen: number | null;
  deviation_pct: number | null;
  created_at: string;
}

export interface FlywheelDashboard {
  total_decisions: number;
  acceptance_rate: number;
  decisions_by_type: { type: string; count: number; acceptance_rate: number }[];
  decisions_by_status: Record<string, number>;
  recent_decisions: DecisionRecordItem[];
  calibration_summary: {
    accuracy_pct: number;
    total_saved_yuan: number;
    avg_deviation: number;
  } | null;
  flywheel_health: 'strong' | 'growing' | 'cold';
}

export interface CalibrationResult {
  total_decisions: number;
  accuracy_by_type: Record<string, { count: number; avg_deviation_pct: number; accuracy: number }>;
  calibration_insights: string | null;
  total_predicted_yuan: number;
  total_actual_yuan: number;
}

export interface TurnoverRiskResult {
  risk_score: number;
  risk_level: string;
  signals: { signal: string; detail: string; weight: number }[];
  ai_analysis: string | null;
  recommendations: { action: string; expected_impact_yuan: number; confidence: number }[];
  replacement_cost_yuan: number;
  data_source: string;
}

export interface StoreTurnoverScan {
  store_id: string;
  total_active: number;
  high_risk_count: number;
  medium_risk_count: number;
  at_risk_employees: { employee_id: string; employee_name: string; position: string; risk_score: number; risk_level: string }[];
  store_analysis: string | null;
  store_recommendations: { action: string; expected_impact_yuan: number; confidence: number; affected_count: number }[];
  total_replacement_cost_yuan: number;
}

// ── 考勤规则 ──────────────────────────────────────────────

export interface AttendanceRuleItem {
  id: string;
  brand_id: string;
  store_id: string | null;
  employment_type: string | null;
  clock_methods: string[];
  gps_fence_enabled: boolean;
  gps_latitude: number | null;
  gps_longitude: number | null;
  gps_radius_meters: number;
  late_deduction_fen: number;
  late_deduction_yuan: number;
  absent_deduction_fen: number;
  absent_deduction_yuan: number;
  early_leave_deduction_fen: number;
  early_leave_deduction_yuan: number;
  weekday_overtime_rate: number;
  weekend_overtime_rate: number;
  holiday_overtime_rate: number;
  work_hour_type: string;
  monthly_standard_hours: number;
  is_active: boolean;
}
