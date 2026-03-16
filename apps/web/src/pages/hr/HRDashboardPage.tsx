import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Badge, Button, Tag, Spin, Space, message, Tooltip, Empty,
} from 'antd';
import {
  TeamOutlined, DollarOutlined, ClockCircleOutlined, SafetyCertificateOutlined,
  CalendarOutlined, TrophyOutlined, BookOutlined, UserSwitchOutlined,
  FileProtectOutlined, InsuranceOutlined, RiseOutlined, AlertOutlined,
  AuditOutlined, FileTextOutlined, SettingOutlined, BulbOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  AppstoreOutlined, SolutionOutlined, ScheduleOutlined,
  IdcardOutlined, ImportOutlined, ApartmentOutlined, BarChartOutlined,
  WechatOutlined, ProfileOutlined, FundProjectionScreenOutlined,
  ThunderboltOutlined, WarningOutlined, ExclamationCircleOutlined,
  RightOutlined, UserAddOutlined, UserDeleteOutlined,
} from '@ant-design/icons';
import { hrService } from '../../services/hrService';
import type {
  HROverview, HREfficiency, ComplianceDashboardData, TrainingDashboardData,
  LeaveRequest, ApprovalInstanceItem, FlywheelDashboard, DecisionRecordItem,
} from '../../services/hrService';
import styles from './HRPages.module.css';

// ── 常量 ──────────────────────────────────────────────────────

const STORE_ID = () => localStorage.getItem('current_store_id') || 'STORE_001';
const BRAND_ID = () => localStorage.getItem('current_brand_id') || 'BRAND_001';
const OPERATOR_ID = () => localStorage.getItem('user_id') || 'USER_001';
const OPERATOR_NAME = () => localStorage.getItem('user_name') || '管理员';
const REFRESH_INTERVAL = 60_000;

// ── 模块导航配置 ──────────────────────────────────────────────

interface ModuleEntry {
  key: string;
  icon: React.ReactNode;
  label: string;
  desc: string;
  path: string;
  badgeField?: string;
}

const MODULE_GRID: ModuleEntry[] = [
  { key: 'roster', icon: <TeamOutlined />, label: '花名册', desc: '员工信息管理', path: '/employee-roster', badgeField: 'total_active' },
  { key: 'payroll', icon: <DollarOutlined />, label: '薪酬管理', desc: '工资核算发放', path: '/payroll' },
  { key: 'attendance', icon: <ClockCircleOutlined />, label: '考勤报表', desc: '打卡与出勤统计', path: '/attendance-report' },
  { key: 'leave', icon: <CalendarOutlined />, label: '请假管理', desc: '假条审批处理', path: '/leave-management', badgeField: 'pending_leaves' },
  { key: 'schedule', icon: <ScheduleOutlined />, label: '排班管理', desc: '智能排班调度', path: '/schedule' },
  { key: 'performance', icon: <TrophyOutlined />, label: '绩效考核', desc: '360度评价体系', path: '/performance-review' },
  { key: 'training', icon: <BookOutlined />, label: '培训认证', desc: '课程与技能认证', path: '/hr-training' },
  { key: 'mentorship', icon: <UserSwitchOutlined />, label: '师徒管理', desc: '带教与传帮带', path: '/mentorship' },
  { key: 'contract', icon: <FileProtectOutlined />, label: '合同管理', desc: '签约续约跟踪', path: '/contract-management', badgeField: 'contracts_expiring' },
  { key: 'insurance', icon: <InsuranceOutlined />, label: '社保管理', desc: '五险一金配置', path: '/social-insurance' },
  { key: 'commission', icon: <RiseOutlined />, label: '提成管理', desc: '销售提成规则', path: '/commission' },
  { key: 'reward', icon: <AlertOutlined />, label: '奖惩管理', desc: '奖惩记录审批', path: '/reward-penalty' },
  { key: 'settlement', icon: <AuditOutlined />, label: '离职结算', desc: '离职薪资结算', path: '/settlement' },
  { key: 'payslip', icon: <FileTextOutlined />, label: '工资条', desc: '工资条推送确认', path: '/payslip-management' },
  { key: 'approval', icon: <SolutionOutlined />, label: '审批管理', desc: '审批流模板配置', path: '/hr-approval' },
  { key: 'rules', icon: <SettingOutlined />, label: '业务规则', desc: '薪酬考勤规则', path: '/business-rules' },
  { key: 'recruitment', icon: <UserAddOutlined />, label: '招聘管理', desc: '职位与候选人', path: '/recruitment', badgeField: 'active_jobs' },
  { key: 'org', icon: <ApartmentOutlined />, label: '组织架构', desc: '部门层级管理', path: '/org-structure' },
  { key: 'compliance', icon: <SafetyCertificateOutlined />, label: '合规看板', desc: '证件合规预警', path: '/compliance' },
  { key: 'monthly', icon: <BarChartOutlined />, label: '月度报表', desc: '人力月度汇总', path: '/hr-monthly-report' },
  { key: 'import', icon: <ImportOutlined />, label: '花名册导入', desc: 'Excel批量导入', path: '/roster-import' },
  { key: 'shift', icon: <ProfileOutlined />, label: '班次模板', desc: '标准班次定义', path: '/shift-templates' },
  { key: 'att-rules', icon: <IdcardOutlined />, label: '考勤规则', desc: '打卡扣款规则', path: '/attendance-rules' },
  { key: 'im', icon: <WechatOutlined />, label: 'IM配置', desc: '企微飞书对接', path: '/im-config' },
];

// ── 飞轮健康度颜色映射 ──────────────────────────

const FLYWHEEL_HEALTH_CONFIG = {
  strong: { color: '#27AE60', label: '运转良好', bg: 'rgba(39,174,96,0.08)' },
  growing: { color: '#F2994A', label: '数据积累中', bg: 'rgba(242,153,74,0.08)' },
  cold: { color: 'rgba(255,255,255,0.38)', label: '待激活', bg: 'rgba(255,255,255,0.04)' },
};

const DECISION_TYPE_LABEL: Record<string, string> = {
  turnover_risk: '离职风险',
  schedule_optimize: '排班优化',
  salary_adjust: '薪资调整',
  growth_plan: '成长计划',
  compliance_alert: '合规预警',
  staffing_demand: '编制建议',
  training_recommend: '培训推荐',
};

// ── 主组件 ──────────────────────────────────────────────────────

const HRDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 数据状态
  const [overview, setOverview] = useState<HROverview | null>(null);
  const [efficiency, setEfficiency] = useState<HREfficiency | null>(null);
  const [compliance, setCompliance] = useState<ComplianceDashboardData | null>(null);
  const [training, setTraining] = useState<TrainingDashboardData | null>(null);
  const [pendingLeaves, setPendingLeaves] = useState<LeaveRequest[]>([]);
  const [approvals, setApprovals] = useState<ApprovalInstanceItem[]>([]);
  const [flywheel, setFlywheel] = useState<FlywheelDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [actioningId, setActioningId] = useState<string | null>(null);

  // 加载全部数据
  const loadData = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    const storeId = STORE_ID();
    const brandId = BRAND_ID();
    const operatorId = OPERATOR_ID();

    try {
      const [ov, eff, leaves, comp, train, appr, fw] = await Promise.all([
        hrService.getOverview(storeId).catch(() => null),
        hrService.getEfficiency(storeId).catch(() => null),
        hrService.getLeaveRequests(storeId, 'pending').catch(() => ({ items: [] })),
        hrService.getComplianceDashboard(storeId).catch(() => null),
        hrService.getTrainingDashboard(brandId, storeId).catch(() => null),
        hrService.getPendingApprovals(operatorId, brandId).catch(() => ({ items: [] })),
        hrService.getFlywheelDashboard(storeId, brandId).catch(() => null),
      ]);

      setOverview(ov);
      setEfficiency(eff);
      setPendingLeaves(leaves.items || []);
      setCompliance(comp);
      setTraining(train);
      setApprovals(appr.items || []);
      setFlywheel(fw);
    } catch {
      /* silent — 子请求各自已降级 */
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadData();
    timerRef.current = setInterval(() => loadData(false), REFRESH_INTERVAL);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loadData]);

  // ── 快捷审批操作 ──────────────────────────────────────────

  const handleApproveLeave = async (id: string) => {
    setApprovingId(id);
    try {
      await hrService.approveLeave(id, OPERATOR_ID());
      message.success('已批准');
      setPendingLeaves(prev => prev.filter(l => l.id !== id));
    } catch {
      message.error('操作失败');
    }
    setApprovingId(null);
  };

  const handleRejectLeave = async (id: string) => {
    setApprovingId(id);
    try {
      await hrService.rejectLeave(id, OPERATOR_ID(), '不符合要求');
      message.success('已驳回');
      setPendingLeaves(prev => prev.filter(l => l.id !== id));
    } catch {
      message.error('操作失败');
    }
    setApprovingId(null);
  };

  const handleApproveInstance = async (instanceId: string) => {
    setApprovingId(instanceId);
    try {
      await hrService.approveInstance(instanceId, OPERATOR_ID(), OPERATOR_NAME());
      message.success('已批准');
      setApprovals(prev => prev.filter(a => a.id !== instanceId));
    } catch {
      message.error('操作失败');
    }
    setApprovingId(null);
  };

  const handleRejectInstance = async (instanceId: string) => {
    setApprovingId(instanceId);
    try {
      await hrService.rejectInstance(instanceId, OPERATOR_ID(), OPERATOR_NAME(), '不符合要求');
      message.success('已驳回');
      setApprovals(prev => prev.filter(a => a.id !== instanceId));
    } catch {
      message.error('操作失败');
    }
    setApprovingId(null);
  };

  // ── 飞轮决策操作 ──────────────────────────────────────────

  const handleAcceptDecision = async (decision: DecisionRecordItem) => {
    setActioningId(decision.id);
    try {
      await hrService.recordFlywheelAction(decision.id, 'accept', OPERATOR_ID());
      await hrService.executeFlywheelDecision(decision.id);
      message.success('已采纳并执行');
      loadData(false);
    } catch {
      message.error('操作失败');
    }
    setActioningId(null);
  };

  const handleRejectDecision = async (decision: DecisionRecordItem) => {
    setActioningId(decision.id);
    try {
      await hrService.recordFlywheelAction(decision.id, 'reject', OPERATOR_ID());
      message.success('已标记为不采纳');
      loadData(false);
    } catch {
      message.error('操作失败');
    }
    setActioningId(null);
  };

  // ── 合规预警统计 ──────────────────────────────────────────

  const complianceCount = compliance
    ? (compliance.health_cert?.expired ?? 0)
      + (compliance.health_cert?.critical ?? 0)
      + (compliance.contract?.total ?? 0)
      + (compliance.id_card?.total ?? 0)
    : 0;

  // ── badge数量映射 ──────────────────────────────────────────

  const badgeCounts: Record<string, number> = {
    total_active: overview?.total_active_employees ?? 0,
    pending_leaves: pendingLeaves.length,
    contracts_expiring: overview?.contracts_expiring_30d ?? 0,
    active_jobs: overview?.active_job_postings ?? 0,
  };

  // ── 渲染 ──────────────────────────────────────────────────

  if (loading) {
    return (
      <div className={styles.page}>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
          <Spin size="large" tip="加载中..." />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page} style={{ maxWidth: 1400 }}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>人力作战台</h1>
          <p className={styles.pageDesc}>业人一体化 — 待办驱动、一站直达全部HR模块</p>
        </div>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => loadData()}
          style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.65)' }}
        >
          刷新
        </Button>
      </div>

      {/* ══════ Section 1: 待办中心 ══════ */}
      <Card
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#FF6B2C' }} />
            <span style={{ fontWeight: 700 }}>待办中心</span>
            <Badge
              count={pendingLeaves.length + approvals.length + complianceCount}
              style={{ backgroundColor: '#EB5757' }}
            />
          </Space>
        }
        bordered={false}
        style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12 }}
        headStyle={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
        bodyStyle={{ padding: '12px 16px', maxHeight: 420, overflow: 'auto' }}
      >
        {/* 请假审批 */}
        {pendingLeaves.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.45)', marginBottom: 8, fontWeight: 600 }}>
              待审请假 <Tag color="red">{pendingLeaves.length}</Tag>
            </div>
            {pendingLeaves.slice(0, 5).map(leave => (
              <div key={leave.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 12px', marginBottom: 4, borderRadius: 8,
                background: 'rgba(255,255,255,0.03)',
              }}>
                <div style={{ flex: 1 }}>
                  <span style={{ color: 'rgba(255,255,255,0.85)', fontWeight: 500 }}>
                    {leave.employee_name}
                  </span>
                  <Tag color="blue" style={{ marginLeft: 8 }}>{leave.leave_category}</Tag>
                  <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, marginLeft: 8 }}>
                    {leave.start_date} ~ {leave.end_date}（{leave.leave_days}天）
                  </span>
                </div>
                <Space size={4}>
                  <Button
                    type="primary" size="small"
                    icon={<CheckCircleOutlined />}
                    loading={approvingId === leave.id}
                    onClick={() => handleApproveLeave(leave.id)}
                    style={{ background: '#27AE60', borderColor: '#27AE60' }}
                  >
                    批准
                  </Button>
                  <Button
                    size="small" danger
                    icon={<CloseCircleOutlined />}
                    loading={approvingId === leave.id}
                    onClick={() => handleRejectLeave(leave.id)}
                  >
                    驳回
                  </Button>
                </Space>
              </div>
            ))}
            {pendingLeaves.length > 5 && (
              <Button type="link" size="small" onClick={() => navigate('/leave-management')} style={{ padding: 0 }}>
                查看全部 {pendingLeaves.length} 条 <RightOutlined />
              </Button>
            )}
          </div>
        )}

        {/* 通用审批 */}
        {approvals.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.45)', marginBottom: 8, fontWeight: 600 }}>
              待审流程 <Tag color="orange">{approvals.length}</Tag>
            </div>
            {approvals.slice(0, 5).map(appr => (
              <div key={appr.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 12px', marginBottom: 4, borderRadius: 8,
                background: 'rgba(255,255,255,0.03)',
              }}>
                <div style={{ flex: 1 }}>
                  <span style={{ color: 'rgba(255,255,255,0.85)', fontWeight: 500 }}>
                    {appr.applicant_name}
                  </span>
                  <Tag color="purple" style={{ marginLeft: 8 }}>{appr.business_type}</Tag>
                  <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, marginLeft: 8 }}>
                    {appr.summary || `${appr.template_code}`}
                  </span>
                  {appr.amount_fen != null && appr.amount_fen > 0 && (
                    <span style={{ color: '#FF6B2C', fontSize: 12, marginLeft: 8 }}>
                      ¥{(appr.amount_fen / 100).toLocaleString()}
                    </span>
                  )}
                </div>
                <Space size={4}>
                  <Button
                    type="primary" size="small"
                    icon={<CheckCircleOutlined />}
                    loading={approvingId === appr.id}
                    onClick={() => handleApproveInstance(appr.id)}
                    style={{ background: '#27AE60', borderColor: '#27AE60' }}
                  >
                    批准
                  </Button>
                  <Button
                    size="small" danger
                    icon={<CloseCircleOutlined />}
                    loading={approvingId === appr.id}
                    onClick={() => handleRejectInstance(appr.id)}
                  >
                    驳回
                  </Button>
                </Space>
              </div>
            ))}
            {approvals.length > 5 && (
              <Button type="link" size="small" onClick={() => navigate('/hr-approval')} style={{ padding: 0 }}>
                查看全部 {approvals.length} 条 <RightOutlined />
              </Button>
            )}
          </div>
        )}

        {/* 合规预警 */}
        {complianceCount > 0 && compliance && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.45)', marginBottom: 8, fontWeight: 600 }}>
              合规预警 <Tag color="volcano">{complianceCount}</Tag>
            </div>
            {(compliance.health_cert?.expired ?? 0) > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', padding: '8px 12px', marginBottom: 4,
                borderRadius: 8, background: 'rgba(235,87,87,0.08)', cursor: 'pointer',
              }} onClick={() => navigate('/compliance')}>
                <WarningOutlined style={{ color: '#EB5757', marginRight: 8 }} />
                <span style={{ color: 'rgba(255,255,255,0.85)' }}>
                  健康证已过期 <b style={{ color: '#EB5757' }}>{compliance.health_cert.expired}</b> 人
                </span>
                <RightOutlined style={{ marginLeft: 'auto', color: 'rgba(255,255,255,0.25)' }} />
              </div>
            )}
            {(compliance.health_cert?.critical ?? 0) > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', padding: '8px 12px', marginBottom: 4,
                borderRadius: 8, background: 'rgba(242,153,74,0.08)', cursor: 'pointer',
              }} onClick={() => navigate('/compliance')}>
                <ExclamationCircleOutlined style={{ color: '#F2994A', marginRight: 8 }} />
                <span style={{ color: 'rgba(255,255,255,0.85)' }}>
                  健康证即将过期 <b style={{ color: '#F2994A' }}>{compliance.health_cert.critical}</b> 人
                </span>
                <RightOutlined style={{ marginLeft: 'auto', color: 'rgba(255,255,255,0.25)' }} />
              </div>
            )}
            {(compliance.contract?.total ?? 0) > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', padding: '8px 12px', marginBottom: 4,
                borderRadius: 8, background: 'rgba(242,153,74,0.08)', cursor: 'pointer',
              }} onClick={() => navigate('/contract-management')}>
                <ExclamationCircleOutlined style={{ color: '#F2994A', marginRight: 8 }} />
                <span style={{ color: 'rgba(255,255,255,0.85)' }}>
                  合同即将到期 <b style={{ color: '#F2994A' }}>{compliance.contract.total}</b> 人
                </span>
                <RightOutlined style={{ marginLeft: 'auto', color: 'rgba(255,255,255,0.25)' }} />
              </div>
            )}
            {(compliance.id_card?.total ?? 0) > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', padding: '8px 12px', marginBottom: 4,
                borderRadius: 8, background: 'rgba(242,153,74,0.08)', cursor: 'pointer',
              }} onClick={() => navigate('/compliance')}>
                <ExclamationCircleOutlined style={{ color: '#F2994A', marginRight: 8 }} />
                <span style={{ color: 'rgba(255,255,255,0.85)' }}>
                  证件即将过期 <b style={{ color: '#F2994A' }}>{compliance.id_card.total}</b> 人
                </span>
                <RightOutlined style={{ marginLeft: 'auto', color: 'rgba(255,255,255,0.25)' }} />
              </div>
            )}
          </div>
        )}

        {/* 空态 */}
        {pendingLeaves.length === 0 && approvals.length === 0 && complianceCount === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ color: 'rgba(255,255,255,0.38)' }}>暂无待办事项</span>}
          />
        )}
      </Card>

      {/* ══════ Section 2: 人力概览 KPI Cards ══════ */}
      <Row gutter={[12, 12]}>
        <Col xs={12} sm={12} md={6}>
          <Card
            bordered={false}
            hoverable
            style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, cursor: 'pointer' }}
            bodyStyle={{ padding: '16px 20px' }}
            onClick={() => navigate('/employee-roster')}
          >
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>在职人数</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: 'rgba(255,255,255,0.92)' }}>
              {overview?.total_active_employees ?? '-'}
            </div>
            <Space size={12} style={{ marginTop: 4 }}>
              <span style={{ fontSize: 12, color: '#27AE60' }}>
                <UserAddOutlined /> 入职 {overview?.month_onboard ?? 0}
              </span>
              <span style={{ fontSize: 12, color: (overview?.month_resign ?? 0) > 0 ? '#EB5757' : 'rgba(255,255,255,0.38)' }}>
                <UserDeleteOutlined /> 离职 {overview?.month_resign ?? 0}
              </span>
            </Space>
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card
            bordered={false}
            hoverable
            style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, cursor: 'pointer' }}
            bodyStyle={{ padding: '16px 20px' }}
            onClick={() => navigate('/attendance-report')}
          >
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>出勤率</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#0AAF9A' }}>
              {overview?.attendance_rate_pct != null ? `${overview.attendance_rate_pct}%` : '-'}
            </div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginTop: 4 }}>
              <ClockCircleOutlined /> 本月迟到 {0} 次
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card
            bordered={false}
            hoverable
            style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, cursor: 'pointer' }}
            bodyStyle={{ padding: '16px 20px' }}
            onClick={() => navigate('/payroll')}
          >
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>本月人力成本</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: 'rgba(255,255,255,0.92)' }}>
              {efficiency?.total_salary_yuan != null
                ? `¥${efficiency.total_salary_yuan.toLocaleString()}`
                : '-'}
            </div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginTop: 4 }}>
              <FundProjectionScreenOutlined /> 人力成本率 {efficiency?.labor_cost_rate_pct ?? '-'}%
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card
            bordered={false}
            hoverable
            style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, cursor: 'pointer' }}
            bodyStyle={{ padding: '16px 20px' }}
            onClick={() => navigate('/training-dashboard')}
          >
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>培训完成率</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#0AAF9A' }}>
              {training?.completion_rate_pct != null ? `${training.completion_rate_pct}%` : '-'}
            </div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', marginTop: 4 }}>
              <SafetyCertificateOutlined /> 师徒培养中 {training?.active_mentorships ?? 0}
            </div>
          </Card>
        </Col>
      </Row>

      {/* ══════ Section 3: 快捷导航 ══════ */}
      <Card
        title={
          <Space>
            <AppstoreOutlined style={{ color: '#0AAF9A' }} />
            <span style={{ fontWeight: 700 }}>快捷导航</span>
            <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.38)', fontWeight: 400 }}>
              全部HR模块一键直达
            </span>
          </Space>
        }
        bordered={false}
        style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12 }}
        headStyle={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
        bodyStyle={{ padding: 16 }}
      >
        <Row gutter={[10, 10]}>
          {MODULE_GRID.map(mod => {
            const count = mod.badgeField ? badgeCounts[mod.badgeField] : undefined;
            return (
              <Col xs={12} sm={8} md={6} key={mod.key}>
                <Tooltip title={mod.desc}>
                  <div
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid rgba(255,255,255,0.06)',
                      transition: 'all .2s',
                    }}
                    onClick={() => navigate(mod.path)}
                    onMouseEnter={e => {
                      (e.currentTarget as HTMLDivElement).style.background = 'rgba(10,175,154,0.08)';
                      (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(10,175,154,0.25)';
                    }}
                    onMouseLeave={e => {
                      (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.03)';
                      (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(255,255,255,0.06)';
                    }}
                  >
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: 'rgba(10,175,154,0.12)', color: '#0AAF9A', fontSize: 18,
                      flexShrink: 0,
                    }}>
                      {mod.icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.85)' }}>
                        {mod.label}
                      </div>
                      <div style={{
                        fontSize: 11, color: 'rgba(255,255,255,0.35)',
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {mod.desc}
                      </div>
                    </div>
                    {count != null && count > 0 && (
                      <Badge
                        count={count}
                        size="small"
                        style={{
                          backgroundColor:
                            mod.key === 'leave' ? '#EB5757'
                            : mod.key === 'contract' ? '#F2994A'
                            : '#0AAF9A',
                        }}
                      />
                    )}
                  </div>
                </Tooltip>
              </Col>
            );
          })}
        </Row>
      </Card>

      {/* ══════ Section 4: 决策飞轮 — Palantir闭环 ══════ */}
      <Card
        title={
          <Space>
            <BulbOutlined style={{ color: '#FF6B2C' }} />
            <span style={{ fontWeight: 700 }}>决策飞轮</span>
            <Tag color="orange" style={{ fontSize: 11 }}>AI Palantir</Tag>
            {flywheel && (
              <Tag
                style={{
                  background: FLYWHEEL_HEALTH_CONFIG[flywheel.flywheel_health]?.bg,
                  color: FLYWHEEL_HEALTH_CONFIG[flywheel.flywheel_health]?.color,
                  borderColor: 'transparent',
                  fontSize: 11,
                }}
              >
                {FLYWHEEL_HEALTH_CONFIG[flywheel.flywheel_health]?.label}
              </Tag>
            )}
          </Space>
        }
        extra={flywheel && (
          <Space size={16} style={{ fontSize: 12 }}>
            <span style={{ color: 'rgba(255,255,255,0.45)' }}>
              总决策 <b style={{ color: 'rgba(255,255,255,0.85)' }}>{flywheel.total_decisions}</b>
            </span>
            <span style={{ color: 'rgba(255,255,255,0.45)' }}>
              采纳率 <b style={{ color: '#0AAF9A' }}>{(flywheel.acceptance_rate * 100).toFixed(0)}%</b>
            </span>
            {flywheel.calibration_summary && (
              <span style={{ color: 'rgba(255,255,255,0.45)' }}>
                预测准确率 <b style={{ color: '#27AE60' }}>{flywheel.calibration_summary.accuracy_pct.toFixed(0)}%</b>
              </span>
            )}
          </Space>
        )}
        bordered={false}
        style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12 }}
        headStyle={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
        bodyStyle={{ padding: '12px 16px' }}
      >
        {/* 待处理的AI决策建议 */}
        {flywheel?.recent_decisions && flywheel.recent_decisions.filter(d => d.status === 'pending').length > 0 ? (
          <Row gutter={[12, 12]}>
            {flywheel.recent_decisions
              .filter(d => d.status === 'pending')
              .slice(0, 6)
              .map(decision => {
                const impactYuan = decision.predicted_impact_fen
                  ? Math.abs(decision.predicted_impact_fen / 100)
                  : 0;
                const isRisk = decision.decision_type === 'turnover_risk' || decision.decision_type === 'compliance_alert';
                return (
                  <Col xs={24} md={8} key={decision.id}>
                    <div style={{
                      padding: 16, borderRadius: 10,
                      background: isRisk ? 'rgba(235,87,87,0.06)' : 'rgba(10,175,154,0.06)',
                      border: `1px solid ${isRisk ? 'rgba(235,87,87,0.15)' : 'rgba(10,175,154,0.15)'}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                        {isRisk ? <WarningOutlined style={{ color: '#EB5757' }} /> : <ThunderboltOutlined style={{ color: '#0AAF9A' }} />}
                        <span style={{ fontWeight: 600, color: 'rgba(255,255,255,0.85)', fontSize: 14 }}>
                          {DECISION_TYPE_LABEL[decision.decision_type] || decision.decision_type}
                        </span>
                        {decision.confidence != null && (
                          <Tag style={{ fontSize: 10, marginLeft: 'auto', borderColor: 'transparent', background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.45)' }}>
                            置信度 {(decision.confidence * 100).toFixed(0)}%
                          </Tag>
                        )}
                      </div>
                      {decision.target_name && (
                        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', marginBottom: 4 }}>
                          {decision.target_name}
                          {decision.risk_score != null && (
                            <Tag
                              color={decision.risk_score >= 80 ? 'red' : decision.risk_score >= 60 ? 'orange' : 'default'}
                              style={{ marginLeft: 6, fontSize: 10 }}
                            >
                              风险分 {decision.risk_score}
                            </Tag>
                          )}
                        </div>
                      )}
                      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', lineHeight: 1.6, marginBottom: 10 }}>
                        {decision.recommendation || decision.ai_analysis?.slice(0, 80) || '等待分析...'}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        {impactYuan > 0 && (
                          <span style={{ fontSize: 13, fontWeight: 600, color: '#FF6B2C' }}>
                            预期影响 ¥{impactYuan.toLocaleString()}
                          </span>
                        )}
                        <Space size={4} style={{ marginLeft: 'auto' }}>
                          <Button
                            size="small" type="primary"
                            icon={<CheckCircleOutlined />}
                            loading={actioningId === decision.id}
                            onClick={() => handleAcceptDecision(decision)}
                            style={{ background: '#27AE60', borderColor: '#27AE60', fontSize: 12 }}
                          >
                            采纳
                          </Button>
                          <Button
                            size="small"
                            loading={actioningId === decision.id}
                            onClick={() => handleRejectDecision(decision)}
                            style={{ fontSize: 12 }}
                          >
                            忽略
                          </Button>
                        </Space>
                      </div>
                    </div>
                  </Col>
                );
              })}
          </Row>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ color: 'rgba(255,255,255,0.38)' }}>暂无待处理的AI决策建议 — 运行离职风险扫描以激活飞轮</span>}
          />
        )}

        {/* 飞轮校准摘要 */}
        {flywheel?.calibration_summary && flywheel.calibration_summary.total_saved_yuan > 0 && (
          <div style={{
            marginTop: 12, padding: '10px 14px', borderRadius: 8,
            background: 'rgba(39,174,96,0.06)', border: '1px solid rgba(39,174,96,0.12)',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <SafetyCertificateOutlined style={{ color: '#27AE60', fontSize: 18 }} />
            <div style={{ flex: 1 }}>
              <span style={{ color: 'rgba(255,255,255,0.85)', fontSize: 13, fontWeight: 600 }}>
                飞轮累计节省 ¥{flywheel.calibration_summary.total_saved_yuan.toLocaleString()}
              </span>
              <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, marginLeft: 16 }}>
                预测偏差 {flywheel.calibration_summary.avg_deviation > 0 ? '+' : ''}{flywheel.calibration_summary.avg_deviation.toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default HRDashboardPage;
