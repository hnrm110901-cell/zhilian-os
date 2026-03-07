/**
 * 经营作战台 — /daily-hub
 *
 * 布局：
 *   顶部  全局 KPI 条（6 指标：营收 / 成本率 / 接待 / 排队 / 健康 / 待处理）
 *   左列  今日经营节奏（班前/午市/午收/晚备/晚市/日结，当前阶段高亮）
 *   右列  异常事件 + 经营机会双列 + AI Top3 决策推荐
 *   右侧  AI 协作抽屉（常驻，按钮唤起）
 *
 * 数据来源：
 *   GET /api/v1/bff/sm/{store_id}    → KPI 条（实时聚合）
 *   GET /api/v1/daily-hub/{store_id} → 明日预测 / 备战板
 *   GET /api/v1/decisions/top3       → AI 决策建议
 *   GET /api/v1/stores               → 门店选择器
 */
import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Row, Col, Card, Select, Button, Tag, Spin, Typography,
  Space, Divider, Drawer, Badge,
} from 'antd';
import {
  ReloadOutlined, WarningOutlined, BulbOutlined, RobotOutlined,
  ClockCircleOutlined, DollarOutlined, TeamOutlined, ShoppingOutlined,
  HeartOutlined, BellOutlined, CheckCircleOutlined, ThunderboltOutlined,
  RiseOutlined, FireOutlined, StarOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import styles from './DailyHubPage.module.css';

const { Text, Title } = Typography;
const { Option } = Select;

// ── Types ──────────────────────────────────────────────────────────────────────

interface KpiState {
  today_revenue_yuan:  number | null;
  food_cost_pct:       number | null;
  food_cost_status:    'ok' | 'warning' | 'critical' | null;
  served_today:        number | null;
  waiting_count:       number | null;
  health_score:        number | null;
  health_level:        string | null;
  pending_approvals:   number;
  unread_alerts:       number;
}

// ── Ops phases ─────────────────────────────────────────────────────────────────

interface OpsPhase {
  key:     string;
  label:   string;
  startH:  number;
  endH:    number;
  icon:    React.ReactNode;
  tasks:   string[];
  risks:   string[];
  aiTip:   string;
}

const OPS_PHASES: OpsPhase[] = [
  {
    key: 'pre_shift', label: '班前准备', startH: 6, endH: 10.5,
    icon: '🌅',
    tasks:  ['核对今日备货到位情况', '确认排班员工到岗', '设备与环境巡检'],
    risks:  ['备货不足', '员工缺勤'],
    aiTip:  '建议优先确认食材到位，提前锁定今日菜品供应清单。',
  },
  {
    key: 'lunch_peak', label: '午市中', startH: 10.5, endH: 14,
    icon: '☀️',
    tasks:  ['监控出品速度与超时预警', '跟进实时排队状态', '抽查服务质量评分'],
    risks:  ['出品超时', '排队超阈值', '退菜率升高'],
    aiTip:  '高峰期注意翻台节奏，目标今日翻台 2.8 次，催台优先级高于新接待。',
  },
  {
    key: 'lunch_close', label: '午市收尾', startH: 14, endH: 16,
    icon: '🌤',
    tasks:  ['午餐营业数据初盘', '记录午盘食材损耗', '安排清洁与补货'],
    risks:  ['损耗超标'],
    aiTip:  '利用午休空档提前做晚市备货补单，避免晚高峰断货风险。',
  },
  {
    key: 'dinner_prep', label: '晚市备战', startH: 16, endH: 17.5,
    icon: '🌇',
    tasks:  ['晚市备货二次核对', '班次交接与任务交代', '菜品预处理确认'],
    risks:  ['人手不足', '食材缺口'],
    aiTip:  '今日预约 12 桌，建议提前备料 20% 冗余，防晚市突发爆单。',
  },
  {
    key: 'dinner_peak', label: '晚市中', startH: 17.5, endH: 21,
    icon: '🌆',
    tasks:  ['实时监控订单与出品', '主动服务巡场', '动态排队管理与预期沟通'],
    risks:  ['服务评分下降', '退菜率过高', '等待超 30 分钟'],
    aiTip:  '重点关注 18:00–19:30 高峰期，评分低于 4.5 及时介入处理。',
  },
  {
    key: 'daily_close', label: '日结复盘', startH: 21, endH: 30,
    icon: '🌙',
    tasks:  ['汇总今日营业数据', '损耗上报与核销', '明日备货预订确认'],
    risks:  [],
    aiTip:  'AI 已生成今日经营快报，建议发送给区域经理，并触发明日备货建议。',
  },
];

function getCurrentPhaseKey(): string {
  const h = new Date().getHours() + new Date().getMinutes() / 60;
  return (OPS_PHASES.find(p => h >= p.startH && h < p.endH) ?? OPS_PHASES[OPS_PHASES.length - 1]).key;
}

// ── Formatting helpers ─────────────────────────────────────────────────────────

function fmtRevenue(v: number | null): string {
  if (v == null) return '—';
  if (v >= 10000) return (v / 10000).toFixed(1);
  return String(Math.round(v));
}
function fmtRevenueUnit(v: number | null): string {
  if (v == null) return '';
  return v >= 10000 ? '万元' : '元';
}

// ── Component ──────────────────────────────────────────────────────────────────

const DailyHubPage: React.FC = () => {
  const navigate = useNavigate();

  const [stores,        setStores]        = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState(localStorage.getItem('store_id') || 'S001');

  const [kpiLoading,  setKpiLoading]  = useState(true);
  const [kpi,         setKpi]         = useState<KpiState | null>(null);

  const [boardLoading, setBoardLoading] = useState(true);
  const [board,        setBoard]        = useState<any>(null);

  const [decisionsLoading, setDecisionsLoading] = useState(true);
  const [decisions,        setDecisions]        = useState<any[]>([]);

  const [aiOpen,         setAiOpen]         = useState(false);
  const [currentPhaseKey] = useState(getCurrentPhaseKey);
  const [selectedPhaseKey, setSelectedPhaseKey] = useState(currentPhaseKey);

  // ── Loaders ──────────────────────────────────────────────────────────────────

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* silent */ }
  }, []);

  const loadKpi = useCallback(async () => {
    setKpiLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/bff/sm/${selectedStore}`);
      const d = res.data;
      setKpi({
        today_revenue_yuan: d.today_revenue_yuan?.revenue_yuan ?? null,
        food_cost_pct:      d.food_cost_summary?.actual_cost_pct ?? null,
        food_cost_status:   d.food_cost_summary?.variance_status ?? null,
        served_today:       d.queue_status?.served_today ?? null,
        waiting_count:      d.queue_status?.waiting_count ?? null,
        health_score:       d.health_score?.score ?? null,
        health_level:       d.health_score?.level ?? null,
        pending_approvals:  d.pending_approvals_count ?? 0,
        unread_alerts:      d.unread_alerts_count ?? 0,
      });
    } catch {
      setKpi(null);
    } finally {
      setKpiLoading(false);
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

  const loadDecisions = useCallback(async () => {
    setDecisionsLoading(true);
    try {
      const res = await apiClient.get('/api/v1/decisions/top3', {
        params: { store_id: selectedStore },
      });
      setDecisions(res.data?.decisions || []);
    } catch {
      setDecisions([]);
    } finally {
      setDecisionsLoading(false);
    }
  }, [selectedStore]);

  const refresh = useCallback(() => {
    loadKpi();
    loadBoard();
    loadDecisions();
  }, [loadKpi, loadBoard, loadDecisions]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { refresh(); }, [refresh]);

  // ── Derive anomalies from live data ──────────────────────────────────────────

  type Severity = 'critical' | 'warning' | 'info';
  interface AnomalyItem {
    id:           string;
    severity:     Severity;
    title:        string;
    detail:       string;
    action_label: string;
    action_to:    string;
  }

  const anomalies: AnomalyItem[] = [
    ...(kpi?.unread_alerts && kpi.unread_alerts > 0 ? [{
      id: 'alerts', severity: 'critical' as Severity,
      title:        `${kpi.unread_alerts} 条运营告警待处理`,
      detail:       '包含服务质量、库存等异常事件，需立即查看',
      action_label: '查看告警', action_to: '/sm/alerts',
    }] : []),
    ...(kpi?.food_cost_status === 'critical' ? [{
      id: 'cost-critical', severity: 'critical' as Severity,
      title:        `食材成本率 ${kpi.food_cost_pct?.toFixed(1)}% 超标`,
      detail:       '超出目标值，建议立即核查损耗原因',
      action_label: '分析原因', action_to: '/waste-reasoning',
    }] : kpi?.food_cost_status === 'warning' ? [{
      id: 'cost-warning', severity: 'warning' as Severity,
      title:        `食材成本率 ${kpi.food_cost_pct?.toFixed(1)}% 偏高`,
      detail:       '接近预警阈值，建议关注损耗情况',
      action_label: '查看分析', action_to: '/waste-reasoning',
    }] : []),
    ...((kpi?.pending_approvals ?? 0) > 0 ? [{
      id: 'pending', severity: 'warning' as Severity,
      title:        `${kpi!.pending_approvals} 项 AI 决策待审批`,
      detail:       'AI 已完成分析，等待人工确认后执行',
      action_label: '去审批', action_to: '/decision',
    }] : []),
    ...((kpi?.waiting_count ?? 0) > 8 ? [{
      id: 'queue', severity: 'warning' as Severity,
      title:        `当前排队 ${kpi!.waiting_count} 桌`,
      detail:       '等候人数较多，建议关注翻台效率与催台',
      action_label: '查看排队', action_to: '/queue',
    }] : []),
    // Demo items shown when no real data is available
    ...(kpi === null ? [
      {
        id: 'demo-1', severity: 'critical' as Severity,
        title:        '备货告急：三文鱼库存不足',
        detail:       '剩余 2kg，预计 17:00 前耗尽，影响晚市主菜',
        action_label: '紧急补货', action_to: '/inventory',
      },
      {
        id: 'demo-2', severity: 'warning' as Severity,
        title:        '食材成本率 38.2% 超标',
        detail:       '超出目标 3.2%，主要损耗来自炸鸡腿和牛肉',
        action_label: '查看分析', action_to: '/waste-reasoning',
      },
      {
        id: 'demo-3', severity: 'info' as Severity,
        title:        '员工张伟今日迟到 15 分钟',
        detail:       '已触发服务质量风险预警，请关注午市出品质量',
        action_label: '查看详情', action_to: '/employees',
      },
    ] : []),
  ];

  interface OpportunityItem {
    id:           string;
    type:         'upsell' | 'member' | 'restock' | 'copy_best';
    title:        string;
    detail:       string;
    expected_gain: string;
    action_label: string;
    action_to:    string;
  }

  const opportunities: OpportunityItem[] = [
    ...(decisions.slice(0, 2).map((d: any) => ({
      id:           `decision-${d.rank}`,
      type:         'upsell' as const,
      title:        d.title,
      detail:       d.action,
      expected_gain: `节省 ¥${d.net_benefit_yuan?.toLocaleString() ?? '—'}`,
      action_label: '去处理',
      action_to:    '/decision',
    }))),
    {
      id: 'opp-member', type: 'member' as const,
      title:        '180 位沉默会员适合唤醒',
      detail:       '超过 45 天未消费，匹配"首次回归"优惠券策略，转化预期 18%',
      expected_gain: '预计唤醒 30+ 人',
      action_label: '生成触达方案', action_to: '/wechat-triggers',
    },
    {
      id: 'opp-copy', type: 'copy_best' as const,
      title:        '朝阳门店翻台策略可复制',
      detail:       '催菜优化使翻台率提升 0.4 次，适合在相似客流门店推广',
      expected_gain: '+¥12,000/月',
      action_label: '查看方案', action_to: '/cross-store-insights',
    },
  ];

  // ── Color helpers ─────────────────────────────────────────────────────────────

  const severityColor = (s: Severity) =>
    ({ critical: '#f5222d', warning: '#fa8c16', info: '#1890ff' }[s]);
  const severityBg = (s: Severity) =>
    ({ critical: '#fff1f0', warning: '#fff7e6', info: '#e6f7ff' }[s]);
  const severityTagColor = (s: Severity) =>
    ({ critical: 'error', warning: 'warning', info: 'processing' }[s] as any);
  const severityLabel = (s: Severity) =>
    ({ critical: '紧急', warning: '关注', info: '提示' }[s]);

  const opportunityColor = (t: string) =>
    ({ upsell: '#722ed1', member: '#13c2c2', restock: '#fa8c16', copy_best: '#52c41a' }[t] ?? '#1890ff');

  // ── KPI strip items ───────────────────────────────────────────────────────────

  const kpiItems = [
    {
      label: '今日营收',
      value: fmtRevenue(kpi?.today_revenue_yuan ?? null),
      unit:  fmtRevenueUnit(kpi?.today_revenue_yuan ?? null),
      icon:  <DollarOutlined />,
      color: '#1890ff',
      badge: null,
    },
    {
      label: '食材成本率',
      value: kpi?.food_cost_pct != null ? kpi.food_cost_pct.toFixed(1) : '—',
      unit:  '%',
      icon:  <ShoppingOutlined />,
      color: kpi?.food_cost_status === 'critical' ? '#f5222d'
           : kpi?.food_cost_status === 'warning'  ? '#fa8c16'
           : '#52c41a',
      badge: kpi?.food_cost_status === 'critical' ? { text: '超标', type: 'error' as const }
           : kpi?.food_cost_status === 'warning'  ? { text: '偏高', type: 'warning' as const }
           : null,
    },
    {
      label: '今日接待',
      value: kpi?.served_today != null ? String(kpi.served_today) : '—',
      unit:  '桌',
      icon:  <TeamOutlined />,
      color: '#13c2c2',
      badge: null,
    },
    {
      label: '当前排队',
      value: kpi?.waiting_count != null ? String(kpi.waiting_count) : '0',
      unit:  '桌',
      icon:  <ClockCircleOutlined />,
      color: (kpi?.waiting_count ?? 0) > 8 ? '#fa8c16' : '#52c41a',
      badge: null,
    },
    {
      label: '健康指数',
      value: kpi?.health_score != null ? String(Math.round(kpi.health_score)) : '—',
      unit:  '分',
      icon:  <HeartOutlined />,
      color: (kpi?.health_score ?? 100) >= 80 ? '#52c41a'
           : (kpi?.health_score ?? 100) >= 60 ? '#faad14' : '#f5222d',
      badge: null,
    },
    {
      label: '待处理事项',
      value: String((kpi?.pending_approvals ?? 0) + (kpi?.unread_alerts ?? 0)),
      unit:  '项',
      icon:  <BellOutlined />,
      color: ((kpi?.pending_approvals ?? 0) + (kpi?.unread_alerts ?? 0)) > 0 ? '#f5222d' : '#52c41a',
      badge: ((kpi?.pending_approvals ?? 0) + (kpi?.unread_alerts ?? 0)) > 0
             ? { text: '需处理', type: 'error' as const } : null,
    },
  ];

  // ── Phase data ────────────────────────────────────────────────────────────────

  const selectedPhase = OPS_PHASES.find(p => p.key === selectedPhaseKey) ?? OPS_PHASES[0];

  // ── AI suggestions (derived) ──────────────────────────────────────────────────

  const aiSuggestions = [
    decisions[0]?.title ?? '确认今日食材到位情况，核查缺货风险',
    (kpi?.pending_approvals ?? 0) > 0
      ? `审批 ${kpi!.pending_approvals} 项 AI 决策建议（预期节省明显）`
      : '生成今日晚市备货补单，避免断货',
    '查看服务评分趋势，重点关注差评原因',
  ];

  const forecast   = board?.tomorrow_forecast;
  const isLoading  = kpiLoading || boardLoading;

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <Title level={4} style={{ margin: 0 }}>经营作战台</Title>
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
          <Button
            type="primary"
            icon={<RobotOutlined />}
            onClick={() => setAiOpen(true)}
          >
            AI 协作
          </Button>
        </Space>
      </div>

      {/* ── KPI strip ───────────────────────────────────────────────────────── */}
      <Spin spinning={kpiLoading} size="small">
        <div className={styles.kpiStrip}>
          {kpiItems.map((item, idx) => (
            <div key={idx} className={styles.kpiStripItem}>
              <div className={styles.kpiStripIcon} style={{ color: item.color }}>
                {item.icon}
              </div>
              <div className={styles.kpiStripBody}>
                <div className={styles.kpiStripLabel}>{item.label}</div>
                <div className={styles.kpiStripValue} style={{ color: item.color }}>
                  {item.value}
                  <span className={styles.kpiStripUnit}>{item.unit}</span>
                </div>
              </div>
              {item.badge && (
                <Tag color={item.badge.type} className={styles.kpiStripBadge}>
                  {item.badge.text}
                </Tag>
              )}
            </div>
          ))}
        </div>
      </Spin>

      {/* ── Main content ────────────────────────────────────────────────────── */}
      <Row gutter={16} style={{ marginTop: 16 }}>

        {/* ── 经营节奏 timeline ─────────────────────────────────────────────── */}
        <Col xs={24} lg={7}>
          <Card
            title={
              <Space>
                <ClockCircleOutlined style={{ color: '#1890ff' }} />
                <span>今日经营节奏</span>
                <Tag color="blue">
                  {OPS_PHASES.find(p => p.key === currentPhaseKey)?.label}
                </Tag>
              </Space>
            }
            className={styles.card}
            bodyStyle={{ padding: '14px 16px' }}
          >
            {/* Phase selector */}
            <div className={styles.phaseNav}>
              {OPS_PHASES.map(phase => (
                <button
                  key={phase.key}
                  className={[
                    styles.phaseBtn,
                    phase.key === currentPhaseKey  ? styles.phaseBtnCurrent  : '',
                    phase.key === selectedPhaseKey ? styles.phaseBtnSelected : '',
                  ].join(' ')}
                  onClick={() => setSelectedPhaseKey(phase.key)}
                >
                  <span>{phase.icon}</span>
                  {phase.label}
                </button>
              ))}
            </div>

            {/* Phase detail */}
            <div className={styles.phaseDetail}>
              {/* Tasks */}
              <div className={styles.phaseSection}>
                <div className={styles.phaseSectionTitle}>
                  <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  待办任务
                </div>
                {selectedPhase.tasks.map((t, i) => (
                  <div key={i} className={styles.phaseItem}>
                    <span className={styles.phaseDot} style={{ background: '#52c41a' }} />
                    {t}
                  </div>
                ))}
              </div>

              {/* Risks */}
              {selectedPhase.risks.length > 0 && (
                <div className={styles.phaseSection}>
                  <div className={styles.phaseSectionTitle}>
                    <WarningOutlined style={{ color: '#fa8c16' }} />
                    风险提示
                  </div>
                  {selectedPhase.risks.map((r, i) => (
                    <div key={i} className={styles.phaseItem}>
                      <span className={styles.phaseDot} style={{ background: '#fa8c16' }} />
                      {r}
                    </div>
                  ))}
                </div>
              )}

              {/* AI tip */}
              <div className={styles.aiTip}>
                <RobotOutlined style={{ color: '#722ed1', flexShrink: 0, marginTop: 2 }} />
                <span>{selectedPhase.aiTip}</span>
              </div>
            </div>

            {/* Tomorrow preview (if board loaded) */}
            {forecast && (
              <>
                <Divider style={{ margin: '14px 0 10px' }} />
                <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 6 }}>明日预测</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span style={{ fontSize: 18, fontWeight: 700, color: '#262626' }}>
                    ¥{((forecast.total_predicted_revenue ?? 0) / 100).toFixed(0)}
                  </span>
                  <span style={{ fontSize: 12, color: '#8c8c8c' }}>预计营收</span>
                </div>
                {forecast.weather && (
                  <Tag color="blue" style={{ marginTop: 6 }}>
                    {forecast.weather.condition} {forecast.weather.temperature}°C
                  </Tag>
                )}
                {forecast.holiday && (
                  <Tag color="red" style={{ marginTop: 6 }}>{forecast.holiday.name}</Tag>
                )}
              </>
            )}
          </Card>
        </Col>

        {/* ── Right column ──────────────────────────────────────────────────── */}
        <Col xs={24} lg={17}>
          <Spin spinning={isLoading}>

            {/* ── 异常事件 + 经营机会 ─────────────────────────────────────── */}
            <Row gutter={16}>
              {/* Anomaly events */}
              <Col xs={24} md={12}>
                <Card
                  title={
                    <Space>
                      <WarningOutlined style={{ color: '#f5222d' }} />
                      <span>异常事件</span>
                      {anomalies.length > 0 && (
                        <Badge
                          count={anomalies.length}
                          style={{ backgroundColor: '#f5222d' }}
                        />
                      )}
                    </Space>
                  }
                  className={styles.card}
                  bodyStyle={{ padding: '4px 0' }}
                >
                  {anomalies.length === 0 ? (
                    <div className={styles.emptyState}>
                      <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 28 }} />
                      <div>运营正常，暂无异常</div>
                    </div>
                  ) : (
                    anomalies.map(a => (
                      <div
                        key={a.id}
                        className={styles.eventCard}
                        style={{
                          borderLeftColor: severityColor(a.severity),
                          background:      severityBg(a.severity),
                        }}
                      >
                        <div className={styles.eventCardHeader}>
                          <Text strong style={{ fontSize: 13, color: severityColor(a.severity), flex: 1 }}>
                            {a.title}
                          </Text>
                          <Tag color={severityTagColor(a.severity)}>
                            {severityLabel(a.severity)}
                          </Tag>
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>{a.detail}</Text>
                        <Button
                          type="link"
                          size="small"
                          className={styles.eventCardAction}
                          style={{ color: severityColor(a.severity) }}
                          onClick={() => navigate(a.action_to)}
                        >
                          {a.action_label} →
                        </Button>
                      </div>
                    ))
                  )}
                </Card>
              </Col>

              {/* Business opportunities */}
              <Col xs={24} md={12}>
                <Card
                  title={
                    <Space>
                      <BulbOutlined style={{ color: '#52c41a' }} />
                      <span>经营机会</span>
                    </Space>
                  }
                  className={styles.card}
                  bodyStyle={{ padding: '4px 0' }}
                >
                  {opportunities.length === 0 ? (
                    <div className={styles.emptyState}>
                      <BulbOutlined style={{ color: '#faad14', fontSize: 28 }} />
                      <div>AI 正在分析经营机会…</div>
                    </div>
                  ) : (
                    opportunities.map(o => (
                      <div
                        key={o.id}
                        className={styles.eventCard}
                        style={{ borderLeftColor: opportunityColor(o.type) }}
                      >
                        <div className={styles.eventCardHeader}>
                          <Text strong style={{ fontSize: 13, flex: 1 }}>{o.title}</Text>
                          <Tag color="purple">{o.expected_gain}</Tag>
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>{o.detail}</Text>
                        <Button
                          type="link"
                          size="small"
                          className={styles.eventCardAction}
                          style={{ color: opportunityColor(o.type) }}
                          onClick={() => navigate(o.action_to)}
                        >
                          {o.action_label} →
                        </Button>
                      </div>
                    ))
                  )}
                </Card>
              </Col>
            </Row>

            {/* ── AI Top3 决策推荐 ──────────────────────────────────────────── */}
            <Card
              title={
                <Space>
                  <ThunderboltOutlined style={{ color: '#faad14' }} />
                  <span>今日 AI 决策推荐</span>
                  <Tag color="gold">Top 3</Tag>
                </Space>
              }
              extra={
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={loadDecisions}
                  loading={decisionsLoading}
                >
                  刷新
                </Button>
              }
              style={{ marginTop: 16 }}
              className={styles.card}
              bodyStyle={{ padding: 16 }}
            >
              <Spin spinning={decisionsLoading}>
                {decisions.length === 0 && !decisionsLoading ? (
                  <div className={styles.emptyState} style={{ padding: '24px 0' }}>
                    <ThunderboltOutlined style={{ color: '#faad14', fontSize: 28 }} />
                    <div>AI 正在分析中，暂无决策推荐</div>
                  </div>
                ) : (
                  <div className={styles.decisionsGrid}>
                    {decisions.map((d: any) => {
                      const rankColor = d.rank === 1 ? '#f5222d' : d.rank === 2 ? '#fa8c16' : '#1890ff';
                      return (
                        <div
                          key={d.rank}
                          className={styles.decisionCard}
                          style={{ borderTop: `3px solid ${rankColor}` }}
                        >
                          <div className={styles.decisionCardHeader}>
                            <Tag color={d.rank === 1 ? 'red' : d.rank === 2 ? 'orange' : 'blue'}>
                              #{d.rank}
                            </Tag>
                            <Tag color={
                              d.source === 'inventory' ? 'orange'
                              : d.source === 'food_cost' ? 'blue' : 'purple'
                            }>
                              {d.source === 'inventory' ? '库存'
                              : d.source === 'food_cost' ? '成本' : '综合'}
                            </Tag>
                            <Tag color={
                              d.execution_difficulty === 'low'    ? 'success'
                              : d.execution_difficulty === 'high' ? 'error' : 'warning'
                            }>
                              {d.execution_difficulty === 'low'   ? '易执行'
                              : d.execution_difficulty === 'high' ? '较复杂' : '中等'}
                            </Tag>
                          </div>

                          <div className={styles.decisionCardTitle}>{d.title}</div>
                          <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }}>
                            {d.action}
                          </Text>

                          <div className={styles.decisionCardMeta}>
                            <span style={{ color: '#52c41a', fontWeight: 700, fontSize: 14 }}>
                              ¥{d.net_benefit_yuan?.toLocaleString() ?? '—'}
                            </span>
                            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
                              置信度 {d.confidence_pct?.toFixed(0)}%
                            </span>
                          </div>

                          <Button
                            type={d.rank === 1 ? 'primary' : 'default'}
                            size="small"
                            icon={<RiseOutlined />}
                            block
                            onClick={() => navigate('/decision')}
                          >
                            去审批
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Spin>
            </Card>

            {/* ── Board quick-stat strip ────────────────────────────────────── */}
            {board && (
              <div className={styles.boardStrip}>
                <div className={styles.boardStripItem}>
                  <span className={styles.boardStripIcon}>📋</span>
                  <div className={styles.boardStripBody}>
                    <div className={styles.boardStripLabel}>采购待处理</div>
                    <div className={styles.boardStripValue}>
                      {board.purchase_order?.length ?? 0}
                      <span style={{ fontSize: 13, fontWeight: 400, color: '#8c8c8c' }}> 项</span>
                    </div>
                    <div className={styles.boardStripSub}>
                      <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }}
                        onClick={() => navigate('/inventory')}>查看采购清单 →</Button>
                    </div>
                  </div>
                </div>

                <div className={styles.boardStripItem}>
                  <span className={styles.boardStripIcon}>👥</span>
                  <div className={styles.boardStripBody}>
                    <div className={styles.boardStripLabel}>今日排班</div>
                    <div className={styles.boardStripValue}>
                      {board.staffing_plan?.total_staff ?? 0}
                      <span style={{ fontSize: 13, fontWeight: 400, color: '#8c8c8c' }}> 人</span>
                    </div>
                    <div className={styles.boardStripSub}>
                      <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }}
                        onClick={() => navigate('/schedule')}>查看排班 →</Button>
                    </div>
                  </div>
                </div>

                <div className={styles.boardStripItem}>
                  <span className={styles.boardStripIcon}>📊</span>
                  <div className={styles.boardStripBody}>
                    <div className={styles.boardStripLabel}>昨日健康指数</div>
                    <div className={styles.boardStripValue}>
                      {board.yesterday_review?.health_score ?? '—'}
                      <span style={{ fontSize: 13, fontWeight: 400, color: '#8c8c8c' }}> 分</span>
                    </div>
                    <div className={styles.boardStripSub}>
                      <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }}
                        onClick={() => navigate('/kpi-dashboard')}>查看详情 →</Button>
                    </div>
                  </div>
                </div>
              </div>
            )}

          </Spin>
        </Col>
      </Row>

      {/* ── AI 协作抽屉 ──────────────────────────────────────────────────────── */}
      <Drawer
        title={
          <Space>
            <RobotOutlined style={{ color: '#722ed1' }} />
            <span>AI 协作助手</span>
          </Space>
        }
        placement="right"
        width={380}
        open={aiOpen}
        onClose={() => setAiOpen(false)}
      >
        <div className={styles.aiPanel}>
          <div className={styles.aiSuggestionsTitle}>今天建议你先处理这 3 件事</div>
          <div className={styles.aiSuggestions}>
            {aiSuggestions.map((text, i) => (
              <div key={i} className={styles.aiSuggestionItem}>
                <div
                  className={styles.aiSuggestionRank}
                  style={{ background: i === 0 ? '#f5222d' : i === 1 ? '#fa8c16' : '#1890ff' }}
                >
                  {i + 1}
                </div>
                <div className={styles.aiSuggestionText}>{text}</div>
              </div>
            ))}
          </div>

          <Divider />

          <div className={styles.aiActionsTitle}>快捷动作</div>
          {[
            { icon: <FireOutlined />,    label: '一键生成今日巡店清单',      to: '/compliance'   },
            { icon: <StarOutlined />,    label: '生成今日经营简报',          to: '/daily-hub'    },
            { icon: <BulbOutlined />,    label: '分析门店利润下降原因',      to: '/waste-reasoning' },
            { icon: <TeamOutlined />,    label: '派发晚市备战任务给店长',    to: '/tasks'        },
            { icon: <RiseOutlined />,    label: '查看跨店可复制经营动作',    to: '/cross-store-insights' },
          ].map((item, i) => (
            <Button
              key={i}
              block
              icon={item.icon}
              className={styles.aiActionBtn}
              style={{ textAlign: 'left', marginBottom: 8, height: 40 }}
              onClick={() => { setAiOpen(false); navigate(item.to); }}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </Drawer>

    </div>
  );
};

export default DailyHubPage;
