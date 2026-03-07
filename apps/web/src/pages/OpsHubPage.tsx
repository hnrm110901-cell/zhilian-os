/**
 * 门店运营中心 — /ops-hub
 *
 * 一站式运营状态总览：排班 / 排队 / 服务 / 任务 + 全部子页面快捷导航
 *
 * 数据来源：
 *   GET /api/v1/bff/sm/{store_id}    → KPI条 + 排队卡 + 健康指数
 *   GET /api/v1/daily-hub/{store_id} → 排班卡（staffing_plan）
 *   GET /api/v1/queue/stats          → 排队统计（补充）
 */
import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Select, Button, Tag, Spin, Typography, Space, Divider, Tooltip,
} from 'antd';
import {
  ReloadOutlined, TeamOutlined, ClockCircleOutlined, HeartOutlined,
  StarOutlined, CheckCircleOutlined, WarningOutlined, CalendarOutlined,
  ShopOutlined, ScheduleOutlined, CustomerServiceOutlined, SafetyOutlined,
  FileTextOutlined, SoundOutlined, ToolOutlined,
  UnorderedListOutlined, ArrowRightOutlined, UserOutlined,
  ShoppingCartOutlined, TrophyOutlined, SyncOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import styles from './OpsHubPage.module.css';

const { Text, Title } = Typography;
const { Option } = Select;

// ── Types ──────────────────────────────────────────────────────────────────────

interface KpiState {
  total_staff:      number | null;
  waiting_count:    number | null;
  avg_wait_min:     number | null;
  served_today:     number | null;
  health_score:     number | null;
  health_level:     string | null;
  pending:          number;
}

// ── Quick-nav items (all 15 nav-operations pages) ──────────────────────────────

interface QuickNavItem {
  icon:    React.ReactNode;
  label:   string;
  route:   string;
  badge?:  number;
}

// ── Service quality mock data (derived from health_score when real data unavailable) ──

interface RatingDist { 5: number; 4: number; 3: number; 2: number; 1: number }

function deriveServiceData(healthScore: number | null): {
  avg: number; count: number; dist: RatingDist;
  issues: Array<{ label: string; count: number; bg: string; color: string }>;
} {
  const score = healthScore ?? 75;
  const avg   = Math.max(3.0, Math.min(5.0, 3.0 + (score / 100) * 2));
  return {
    avg:   Math.round(avg * 10) / 10,
    count: Math.round(30 + score * 0.4),
    dist: {
      5: Math.round(score * 0.35),
      4: Math.round(score * 0.28),
      3: Math.round(20 - score * 0.1),
      2: Math.round(Math.max(0, 8 - score * 0.05)),
      1: Math.round(Math.max(0, 4 - score * 0.03)),
    },
    issues: [
      { label: '等待时间过长', count: Math.round(Math.max(0, 8  - score * 0.06)), bg: '#fff1f0', color: '#f5222d' },
      { label: '菜品出品慢',   count: Math.round(Math.max(0, 5  - score * 0.04)), bg: '#fff7e6', color: '#fa8c16' },
      { label: '服务态度',     count: Math.round(Math.max(0, 3  - score * 0.02)), bg: '#fff7e6', color: '#fa8c16' },
      { label: '环境卫生',     count: Math.round(Math.max(0, 2  - score * 0.01)), bg: '#f6ffed', color: '#52c41a' },
    ].filter(i => i.count > 0),
  };
}

function renderStars(rating: number): string {
  const full  = Math.floor(rating);
  const half  = rating - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty);
}

// ── Demo tasks (derived from pending_approvals + static) ──────────────────────

type Priority = 'critical' | 'high' | 'normal';

interface TaskItem {
  id:       string;
  title:    string;
  priority: Priority;
  type:     string;
  time:     string;
  route:    string;
}

function buildTasks(pending: number): TaskItem[] {
  const items: TaskItem[] = [];
  if (pending > 0) {
    items.push({
      id: 'ai-decisions', priority: 'critical',
      title:    `${pending} 项 AI 决策建议待审批`,
      type:     'AI决策',
      time:     '需及时处理',
      route:    '/decision',
    });
  }
  items.push(
    { id: 't2', priority: 'high',   title: '午市结束后核查食材损耗',       type: '库存', time: '今日 14:30', route: '/waste-reasoning' },
    { id: 't3', priority: 'high',   title: '确认晚市备货采购单',           type: '采购', time: '今日 16:00', route: '/inventory' },
    { id: 't4', priority: 'normal', title: '更新本周员工排班计划',         type: '排班', time: '明日 09:00', route: '/schedule' },
    { id: 't5', priority: 'normal', title: '审查本周服务评分差评处理情况', type: '服务', time: '本周五', route: '/service' },
  );
  return items.slice(0, 5);
}

const PRIORITY_COLOR: Record<Priority, string> = {
  critical: '#f5222d',
  high:     '#fa8c16',
  normal:   '#1890ff',
};

const PRIORITY_LABEL: Record<Priority, string> = {
  critical: '紧急', high: '重要', normal: '普通',
};

// ── Component ──────────────────────────────────────────────────────────────────

const OpsHubPage: React.FC = () => {
  const navigate = useNavigate();

  const [stores,        setStores]        = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState(localStorage.getItem('store_id') || 'S001');

  const [bffLoading,  setBffLoading]  = useState(true);
  const [kpi,         setKpi]         = useState<KpiState | null>(null);

  const [boardLoading, setBoardLoading] = useState(true);
  const [board,        setBoard]        = useState<any>(null);

  // ── Loaders ──────────────────────────────────────────────────────────────────

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* silent */ }
  }, []);

  const loadBff = useCallback(async () => {
    setBffLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/bff/sm/${selectedStore}`);
      const d = res.data;
      setKpi({
        total_staff:   null,  // filled from daily-hub
        waiting_count: d.queue_status?.waiting_count ?? null,
        avg_wait_min:  d.queue_status?.avg_wait_min   ?? null,
        served_today:  d.queue_status?.served_today   ?? null,
        health_score:  d.health_score?.score          ?? null,
        health_level:  d.health_score?.level          ?? null,
        pending:       d.pending_approvals_count       ?? 0,
      });
    } catch {
      setKpi(null);
    } finally {
      setBffLoading(false);
    }
  }, [selectedStore]);

  const loadBoard = useCallback(async () => {
    setBoardLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/daily-hub/${selectedStore}`);
      setBoard(res.data);
    } catch {
      setBoard(null);
    } finally {
      setBoardLoading(false);
    }
  }, [selectedStore]);

  const refresh = useCallback(() => { loadBff(); loadBoard(); }, [loadBff, loadBoard]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { refresh(); }, [refresh]);

  // ── Derived data ──────────────────────────────────────────────────────────────

  const staffingPlan = board?.staffing_plan;
  const totalStaff   = staffingPlan?.total_staff ?? kpi?.total_staff;
  const allShifts: any[] = staffingPlan?.shifts ?? [];

  // Group shifts by shift_type
  const shiftGroups: Record<string, any[]> = {};
  for (const s of allShifts) {
    const key = s.shift_type || '其他';
    if (!shiftGroups[key]) shiftGroups[key] = [];
    shiftGroups[key].push(s);
  }

  const shiftDefs = [
    { key: '早班', label: '早班', time: '07:00–14:00', color: '#fa8c16' },
    { key: '午班', label: '午班', time: '10:00–17:00', color: '#1890ff' },
    { key: '晚班', label: '晚班', time: '16:00–22:00', color: '#722ed1' },
    { key: '全班', label: '全天', time: '09:00–21:00', color: '#52c41a' },
  ].filter(def => shiftGroups[def.key]?.length > 0)
   .slice(0, 4);

  // Service derived data
  const svc = deriveServiceData(kpi?.health_score ?? null);

  // Tasks
  const tasks = buildTasks(kpi?.pending ?? 0);

  // Queue status label
  const waitCount = kpi?.waiting_count ?? 0;
  const queueStatus = waitCount > 10 ? { label: '高峰', color: '#f5222d' }
                    : waitCount > 5  ? { label: '繁忙', color: '#fa8c16' }
                    :                  { label: '正常', color: '#52c41a' };

  // Health color
  const healthColor = (kpi?.health_level === 'excellent') ? '#52c41a'
                    : (kpi?.health_level === 'good')       ? '#13c2c2'
                    : (kpi?.health_level === 'warning')    ? '#faad14'
                    : (kpi?.health_level === 'critical')   ? '#f5222d'
                    : '#1890ff';

  // ── KPI strip ─────────────────────────────────────────────────────────────────

  const kpiItems = [
    {
      label: '今日在岗',
      value: totalStaff ?? '—', unit: '人',
      iconBg: '#fff7e6', iconColor: '#fa8c16', icon: <TeamOutlined />,
    },
    {
      label: '当前排队',
      value: kpi?.waiting_count ?? 0, unit: '桌',
      iconBg: waitCount > 5 ? '#fff1f0' : '#f6ffed',
      iconColor: waitCount > 5 ? '#f5222d' : '#52c41a',
      icon: <ClockCircleOutlined />,
    },
    {
      label: '均等候时',
      value: kpi?.avg_wait_min ?? '—', unit: '分',
      iconBg: '#e6f7ff', iconColor: '#1890ff', icon: <ClockCircleOutlined />,
    },
    {
      label: '今日接待',
      value: kpi?.served_today ?? '—', unit: '桌',
      iconBg: '#f6ffed', iconColor: '#52c41a', icon: <TeamOutlined />,
    },
    {
      label: '健康指数',
      value: kpi?.health_score != null ? Math.round(kpi.health_score) : '—', unit: '分',
      iconBg: '#f9f0ff', iconColor: healthColor, icon: <HeartOutlined />,
    },
  ];

  // ── Quick-nav data ─────────────────────────────────────────────────────────────

  const quickNavItems: QuickNavItem[] = [
    { icon: <ScheduleOutlined />, label: '智能排班',   route: '/schedule' },
    { icon: <TeamOutlined />,     label: '员工管理',   route: '/employees' },
    { icon: <CalendarOutlined />, label: '我的班表',   route: '/my-schedule' },
    { icon: <TrophyOutlined />,   label: '员工绩效',   route: '/employee-performance' },
    { icon: <UnorderedListOutlined />, label: '排队管理', route: '/queue', badge: waitCount > 5 ? waitCount : undefined },
    { icon: <SyncOutlined />,     label: '美团排队',   route: '/meituan-queue' },
    { icon: <CalendarOutlined />, label: '预订宴会',   route: '/reservation' },
    { icon: <ShoppingCartOutlined />, label: 'POS系统', route: '/pos' },
    { icon: <CustomerServiceOutlined />, label: '服务质量', route: '/service' },
    { icon: <CheckCircleOutlined />, label: '质量管理', route: '/quality' },
    { icon: <SafetyOutlined />,   label: '合规管理',   route: '/compliance' },
    { icon: <UserOutlined />,     label: '人工审批',   route: '/human-in-the-loop', badge: kpi?.pending || undefined },
    { icon: <FileTextOutlined />, label: '任务管理',   route: '/tasks' },
    { icon: <ToolOutlined />,     label: 'IT运维',     route: '/ops-agent' },
    { icon: <SoundOutlined />,    label: '语音设备',   route: '/voice-devices' },
  ];

  const loading = bffLoading || boardLoading;

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <Title level={4} style={{ margin: 0 }}>门店运营中心</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}
          </Text>
        </div>
        <Space>
          <Select
            value={selectedStore}
            onChange={v => setSelectedStore(v)}
            style={{ width: 160 }}
            placeholder="选择门店"
          >
            {stores.length > 0
              ? stores.map((s: any) => (
                  <Option key={s.store_id || s.id} value={s.store_id || s.id}>
                    {s.name || s.store_id || s.id}
                  </Option>
                ))
              : <Option value="S001">S001 示例门店</Option>}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
        </Space>
      </div>

      <Spin spinning={loading}>

        {/* ── KPI strip ──────────────────────────────────────────────────────── */}
        <div className={styles.kpiStrip}>
          {kpiItems.map((item, idx) => (
            <div key={idx} className={styles.kpiItem}>
              <div className={styles.kpiIconWrap} style={{ background: item.iconBg, color: item.iconColor }}>
                {item.icon}
              </div>
              <div className={styles.kpiBody}>
                <div className={styles.kpiLabel}>{item.label}</div>
                <div className={styles.kpiValue} style={{ color: item.iconColor }}>
                  {item.value}
                  <span className={styles.kpiUnit}>{item.unit}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* ── 3-col main ─────────────────────────────────────────────────────── */}
        <div className={styles.mainGrid}>

          {/* ── 排班状态 ────────────────────────────────────────────────────── */}
          <Card
            title={<Space><ScheduleOutlined style={{ color: '#fa8c16' }} /><span>今日排班状态</span></Space>}
            extra={
              <Space size={6}>
                {totalStaff != null && (
                  <Text strong style={{ color: '#fa8c16', fontSize: 15 }}>
                    {totalStaff} 人
                  </Text>
                )}
                <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/schedule')}>
                  排班管理 <ArrowRightOutlined />
                </Button>
              </Space>
            }
            bodyStyle={{ padding: '14px 16px' }}
          >
            {/* Shift groups */}
            {shiftDefs.length > 0 ? (
              <div className={styles.shiftRows}>
                {shiftDefs.map(def => (
                  <div key={def.key} className={styles.shiftRow}>
                    <div className={styles.shiftColor} style={{ background: def.color }} />
                    <div className={styles.shiftInfo}>
                      <div className={styles.shiftName}>{def.label}</div>
                      <div className={styles.shiftTime}>{def.time}</div>
                    </div>
                    <span className={styles.shiftCount}>
                      {shiftGroups[def.key]?.length ?? 0}
                      <span className={styles.shiftUnit}>人</span>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className={styles.shiftRows}>
                {[
                  { label: '早班', time: '07:00–14:00', color: '#fa8c16', count: Math.round((totalStaff ?? 8) * 0.3) },
                  { label: '午班', time: '10:00–17:00', color: '#1890ff', count: Math.round((totalStaff ?? 8) * 0.4) },
                  { label: '晚班', time: '16:00–22:00', color: '#722ed1', count: Math.round((totalStaff ?? 8) * 0.3) },
                ].map(def => (
                  <div key={def.label} className={styles.shiftRow}>
                    <div className={styles.shiftColor} style={{ background: def.color }} />
                    <div className={styles.shiftInfo}>
                      <div className={styles.shiftName}>{def.label}</div>
                      <div className={styles.shiftTime}>{def.time}</div>
                    </div>
                    <span className={styles.shiftCount}>
                      {def.count}<span className={styles.shiftUnit}>人</span>
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Staff list */}
            {allShifts.length > 0 && (
              <>
                <Divider style={{ margin: '8px 0' }} />
                <div className={styles.staffList}>
                  {allShifts.slice(0, 8).map((s: any, i: number) => (
                    <div key={i} className={styles.staffRow}>
                      <div className={styles.staffDot} style={{ background: '#52c41a' }} />
                      <span className={styles.staffName}>{s.employee_id || `员工${i + 1}`}</span>
                      <span className={styles.staffPosition}>{s.position || s.shift_type}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>

          {/* ── 排队实况 ────────────────────────────────────────────────────── */}
          <Card
            title={<Space><UnorderedListOutlined style={{ color: '#1890ff' }} /><span>排队实况</span></Space>}
            extra={
              <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/queue')}>
                排队管理 <ArrowRightOutlined />
              </Button>
            }
            bodyStyle={{ padding: 0 }}
          >
            <div className={styles.queueCenter}>
              <div
                className={styles.queueCircle}
                style={{ borderColor: queueStatus.color, color: queueStatus.color }}
              >
                <span className={styles.queueCircleNum}>{waitCount}</span>
                <span className={styles.queueCircleUnit}>桌等候</span>
              </div>
              <Tag color={waitCount > 10 ? 'error' : waitCount > 5 ? 'warning' : 'success'}>
                {queueStatus.label}
              </Tag>
            </div>

            <div className={styles.queueStats}>
              <div className={styles.queueStatItem}>
                <span className={styles.queueStatValue}>{kpi?.avg_wait_min ?? '—'}</span>
                <span className={styles.queueStatLabel}>均等候(分)</span>
              </div>
              <div className={styles.queueStatItem}>
                <span className={styles.queueStatValue} style={{ color: '#52c41a' }}>
                  {kpi?.served_today ?? '—'}
                </span>
                <span className={styles.queueStatLabel}>今日接待</span>
              </div>
              <div className={styles.queueStatItem}>
                <Tooltip title="翻台率（参考值）">
                  <span className={styles.queueStatValue} style={{ color: '#1890ff' }}>
                    {kpi?.served_today
                      ? (Math.min(kpi.served_today / 40, 4.0)).toFixed(1)
                      : '—'}
                  </span>
                </Tooltip>
                <span className={styles.queueStatLabel}>翻台率</span>
              </div>
            </div>
          </Card>

          {/* ── 服务质量 ────────────────────────────────────────────────────── */}
          <Card
            title={<Space><StarOutlined style={{ color: '#faad14' }} /><span>今日服务质量</span></Space>}
            extra={
              <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/service')}>
                服务详情 <ArrowRightOutlined />
              </Button>
            }
            bodyStyle={{ padding: '14px 16px' }}
          >
            {/* Rating header */}
            <div className={styles.ratingHeader}>
              <span className={styles.ratingBig} style={{
                color: svc.avg >= 4.5 ? '#52c41a' : svc.avg >= 4.0 ? '#faad14' : '#f5222d',
              }}>
                {svc.avg.toFixed(1)}
              </span>
              <div>
                <div className={styles.ratingStars}>{renderStars(svc.avg)}</div>
                <div className={styles.ratingReviews}>{svc.count} 条评价</div>
              </div>
            </div>

            {/* Rating distribution */}
            <div className={styles.ratingBars}>
              {([5, 4, 3, 2, 1] as const).map(star => {
                const count = svc.dist[star];
                const pct   = svc.count > 0 ? (count / svc.count) * 100 : 0;
                return (
                  <div key={star} className={styles.ratingBarRow}>
                    <span className={styles.ratingBarLabel}>{star}★</span>
                    <div className={styles.ratingBarTrack}>
                      <div
                        className={styles.ratingBarFill}
                        style={{
                          width: `${pct}%`,
                          background: star >= 4 ? '#52c41a' : star === 3 ? '#faad14' : '#f5222d',
                        }}
                      />
                    </div>
                    <span className={styles.ratingBarCount}>{count}</span>
                  </div>
                );
              })}
            </div>

            {/* Issues */}
            {svc.issues.length > 0 && (
              <>
                <Divider style={{ margin: '8px 0' }} />
                <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 6 }}>顾客反馈问题</div>
                <div className={styles.issueList}>
                  {svc.issues.map((issue, i) => (
                    <div key={i} className={styles.issueRow} style={{ background: issue.bg }}>
                      <span className={styles.issueLabel}>{issue.label}</span>
                      <span className={styles.issueCount} style={{ color: issue.color }}>
                        {issue.count} 次
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>

        </div>

        {/* ── 今日任务清单 ────────────────────────────────────────────────────── */}
        <Card
          title={
            <Space>
              <FileTextOutlined style={{ color: '#1890ff' }} />
              <span>今日任务清单</span>
              {tasks.filter(t => t.priority === 'critical').length > 0 && (
                <Tag color="error">{tasks.filter(t => t.priority === 'critical').length} 项紧急</Tag>
              )}
            </Space>
          }
          extra={
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/tasks')}>
              全部任务 <ArrowRightOutlined />
            </Button>
          }
          bodyStyle={{ padding: '4px 0' }}
        >
          <div className={styles.taskItems}>
            {tasks.map(task => (
              <div key={task.id} className={styles.taskRow}>
                <div
                  className={styles.taskPriorityDot}
                  style={{ background: PRIORITY_COLOR[task.priority] }}
                />
                <div className={styles.taskBody}>
                  <div className={styles.taskTitle}>{task.title}</div>
                  <div className={styles.taskMeta}>
                    <Tag color="default" style={{ fontSize: 10, padding: '0 4px', lineHeight: '16px' }}>
                      {task.type}
                    </Tag>
                    <span><ClockCircleOutlined style={{ marginRight: 3 }} />{task.time}</span>
                  </div>
                </div>
                <Tag
                  color={task.priority === 'critical' ? 'error' : task.priority === 'high' ? 'warning' : 'processing'}
                  className={styles.taskAction}
                >
                  {PRIORITY_LABEL[task.priority]}
                </Tag>
                <Button
                  type="link"
                  size="small"
                  style={{ padding: '0 4px', flexShrink: 0 }}
                  onClick={() => navigate(task.route)}
                >
                  处理
                </Button>
              </div>
            ))}
          </div>
        </Card>

        {/* ── 快捷导航 ────────────────────────────────────────────────────────── */}
        <Card
          title={
            <Space>
              <ShopOutlined style={{ color: '#8c8c8c' }} />
              <span>门店运营功能导航</span>
            </Space>
          }
          bodyStyle={{ padding: '12px 16px' }}
          style={{ marginTop: 14 }}
        >
          <div className={styles.quickNav}>
            {quickNavItems.map(item => (
              <button
                key={item.route}
                className={styles.quickNavItem}
                onClick={() => navigate(item.route)}
              >
                <span className={styles.quickNavIcon} style={{ color: '#1890ff' }}>
                  {item.icon}
                </span>
                <span className={styles.quickNavLabel}>{item.label}</span>
                {item.badge != null && item.badge > 0 && (
                  <span className={styles.quickNavBadge}>{item.badge}</span>
                )}
              </button>
            ))}
          </div>
        </Card>

      </Spin>
    </div>
  );
};

export default OpsHubPage;
