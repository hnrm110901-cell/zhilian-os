/**
 * PlatformAdminHome — 屯象OS 企业管理后台控制台首页
 *
 * 布局：5 个区块
 *   1. Hero KPI Bar  — 4 核心指标
 *   2. Mid Row       — Agent 运行状态表 + 系统健康卡（含趋势图）
 *   3. Merchant Grid — 3 种子商户卡（HealthRing + 今日订单 + 状态）
 *   4. Bottom Row    — 系统事件时间线 + AI 建议待审核
 */
import React, { useEffect, useState } from 'react';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  ArrowRightOutlined,
  ThunderboltOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  ZCard,
  ZKpi,
  ZBadge,
  ZTable,
  ZEmpty,
  HealthRing,
  ChartTrend,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './PlatformAdminHome.module.css';

// ── 类型定义 ────────────────────────────────────────────────────────────────

interface AgentStat {
  name: string;
  executions: number;
  successRate: number;   // 0-100
  avgResponseMs: number;
  status: 'running' | 'idle' | 'error';
}

interface MerchantCard {
  id: string;
  name: string;
  pos: string;
  stores: number;
  todayOrders: number;
  healthScore: number;   // 0-100
  status: '接入中' | '已上线' | '暂停';
}

interface SystemEvent {
  id: string;
  time: string;
  type: 'system' | 'merchant' | 'ai' | 'alert';
  content: string;
}

interface AiSuggestion {
  id: string;
  merchant: string;
  action: string;
  impact: string;
  confidence: number;   // 0-100
}

interface SystemStatus {
  api: 'ok' | 'error' | 'loading';
  db: 'ok' | 'error' | 'loading';
  redis: 'ok' | 'error' | 'loading';
}

// ── Mock 数据（POC 阶段占位值，待真实 API 接入后替换） ─────────────────────

const AGENT_STATS_MOCK: AgentStat[] = [
  { name: 'PerformanceAgent', executions: 423, successRate: 98.3, avgResponseMs: 1200, status: 'running' },
  { name: 'InventoryAgent',   executions: 312, successRate: 99.1, avgResponseMs:  820, status: 'running' },
  { name: 'OpsAgent',         executions: 187, successRate: 97.8, avgResponseMs: 1540, status: 'running' },
  { name: 'ScheduleAgent',    executions: 156, successRate: 100,  avgResponseMs:  610, status: 'running' },
  { name: 'OrderAgent',       executions: 134, successRate: 98.5, avgResponseMs:  930, status: 'running' },
];

const SEED_MERCHANTS: MerchantCard[] = [
  { id: 'czq', name: '尝在一起', pos: '品智收银', stores: 3, todayOrders: 142, healthScore: 78, status: '接入中' },
  { id: 'zqx', name: '最黔线',   pos: '品智收银', stores: 6, todayOrders: 287, healthScore: 82, status: '接入中' },
  { id: 'sgc', name: '尚宫厨',   pos: '品智收银', stores: 5, todayOrders: 195, healthScore: 71, status: '接入中' },
];

const EVENTS_MOCK: SystemEvent[] = [
  { id: 'e1', time: '10:32', type: 'system',   content: 'API 健康检查通过，响应 12ms' },
  { id: 'e2', time: '09:58', type: 'ai',       content: 'InventoryAgent 触发补货建议 3 条' },
  { id: 'e3', time: '09:15', type: 'merchant', content: '尝在一起完成数据全量同步' },
  { id: 'e4', time: '08:00', type: 'system',   content: '每日聚合任务完成，共处理 624 条订单' },
  { id: 'e5', time: '昨日',  type: 'alert',    content: 'Redis 连接抖动已自动恢复' },
];

const AI_SUGGESTIONS_MOCK: AiSuggestion[] = [
  { id: 's1', merchant: '尝在一起', action: '降低龙虾备货量 20%', impact: '节省 ¥2,400/周', confidence: 87 },
  { id: 's2', merchant: '最黔线',   action: '优化周末班次排期',   impact: '节省 ¥1,800/月', confidence: 91 },
  { id: 's3', merchant: '尚宫厨',   action: '调整午市主推菜品',   impact: '提升 ¥3,200/月', confidence: 85 },
];

const TREND_DATA = [
  { label: '3/7',  value: 98 },
  { label: '3/8',  value: 97 },
  { label: '3/9',  value: 99 },
  { label: '3/10', value: 98 },
  { label: '3/11', value: 96 },
  { label: '3/12', value: 99 },
  { label: '3/13', value: 100 },
];

// ── Agent 表格列定义 ─────────────────────────────────────────────────────────

const AGENT_COLUMNS: ZTableColumn<AgentStat>[] = [
  {
    key: 'name',
    dataIndex: 'name',
    title: 'Agent',
    render: (v: string) => <span className={styles.agentName}>{v}</span>,
  },
  {
    key: 'executions',
    dataIndex: 'executions',
    title: '今日调用',
    align: 'right',
    width: 90,
  },
  {
    key: 'successRate',
    dataIndex: 'successRate',
    title: '成功率',
    align: 'right',
    width: 80,
    render: (v: number) => (
      <span style={{ color: v >= 99 ? '#52c41a' : v >= 95 ? '#faad14' : '#ff4d4f', fontWeight: 600 }}>
        {v.toFixed(1)}%
      </span>
    ),
  },
  {
    key: 'avgResponseMs',
    dataIndex: 'avgResponseMs',
    title: '均响应',
    align: 'right',
    width: 80,
    render: (v: number) => <span className={styles.responseMs}>{v >= 1000 ? `${(v/1000).toFixed(1)}s` : `${v}ms`}</span>,
  },
  {
    key: 'status',
    dataIndex: 'status',
    title: '状态',
    align: 'center',
    width: 80,
    render: (v: string) => (
      <ZBadge type={v === 'running' ? 'success' : v === 'error' ? 'critical' : 'default'} text={v === 'running' ? '运行中' : v === 'error' ? '异常' : '空闲'} />
    ),
  },
];

// ── 主组件 ──────────────────────────────────────────────────────────────────

const PlatformAdminHome: React.FC = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<SystemStatus>({ api: 'loading', db: 'loading', redis: 'loading' });
  const [merchantCount, setMerchantCount] = useState<number>(3);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    // API 健康
    try {
      const resp = await apiClient.get('/api/v1/health');
      const data = resp.data;
      setStatus({
        api: 'ok',
        db: data.database === 'connected' ? 'ok' : 'error',
        redis: data.redis === 'connected' ? 'ok' : 'error',
      });
    } catch {
      setStatus({ api: 'error', db: 'error', redis: 'error' });
    }
    // 商户数量
    try {
      const resp = await apiClient.get('/api/v1/merchants?page=1&page_size=1');
      setMerchantCount(resp.data?.total ?? resp.data?.length ?? 3);
    } catch {
      setMerchantCount(3);
    }
    setLoading(false);
  };

  const apiOk = status.api === 'ok';
  const dbOk  = status.db  === 'ok';
  const redisOk = status.redis === 'ok';
  const systemHealthScore = [apiOk, dbOk, redisOk].filter(Boolean).length === 3 ? 100 :
                            [apiOk, dbOk, redisOk].filter(Boolean).length === 2 ? 67 : 33;

  return (
    <div className={styles.page}>

      {/* ── 1. Hero KPI Bar ─────────────────────────────────────────────── */}
      <div className={styles.heroBar}>
        <ZKpi label="接入商户" value={merchantCount} unit="家" change={0} changeLabel="POC 种子期" size="lg" color="#0AAF9A" />
        <ZKpi label="今日 AI 决策" value={1247} change={12.3} changeLabel="较昨日" size="lg" />
        <ZKpi label="成本节约率" value="2.3" unit="%" change={0.2} changeLabel="较上月" size="lg" color="#52c41a" />
        <ZKpi label="系统续费率" value="100" unit="%" change={0} changeLabel="本季" size="lg" color="#007AFF" />
      </div>

      {/* ── 2. Mid Row: Agent Table + System Health ──────────────────────── */}
      <div className={styles.midRow}>
        {/* Agent 运行状态 */}
        <ZCard
          title="AI Agent 运行状态"
          subtitle="今日累计"
          extra={
            <button className={styles.linkBtn} onClick={() => navigate('/platform/agents')}>
              详情 <ArrowRightOutlined style={{ fontSize: 11 }} />
            </button>
          }
          noPadding
        >
          <ZTable<AgentStat>
            columns={AGENT_COLUMNS}
            dataSource={AGENT_STATS_MOCK}
            rowKey="name"
          />
        </ZCard>

        {/* 系统健康 */}
        <ZCard
          title="系统健康"
          extra={
            <button className={styles.refreshIconBtn} onClick={fetchData} title="刷新">
              <ReloadOutlined style={{ fontSize: 13 }} />
            </button>
          }
        >
          <div className={styles.healthCenter}>
            <HealthRing score={systemHealthScore} size={72} label="综合健康" />
          </div>
          <div className={styles.statusList}>
            <StatusRow label="API 服务"  status={status.api} />
            <StatusRow label="PostgreSQL" status={status.db} />
            <StatusRow label="Redis"      status={status.redis} />
          </div>
          <div className={styles.trendLabel}>API 响应率（近 7 天）</div>
          <ChartTrend data={TREND_DATA} height={72} color="#0AAF9A" unit="%" />
        </ZCard>
      </div>

      {/* ── 3. Merchant Grid ─────────────────────────────────────────────── */}
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>种子商户状态</h2>
        <button className={styles.linkBtn} onClick={() => navigate('/platform/merchants')}>
          全部商户 <ArrowRightOutlined style={{ fontSize: 11 }} />
        </button>
      </div>
      <div className={styles.merchantGrid}>
        {SEED_MERCHANTS.map((m) => (
          <MerchantCardItem key={m.id} merchant={m} onClick={() => navigate('/platform/merchants')} />
        ))}
      </div>

      {/* ── 4. Bottom Row: Events + AI Suggestions ──────────────────────── */}
      <div className={styles.bottomRow}>
        {/* 系统事件时间线 */}
        <ZCard title="系统事件" subtitle="今日">
          {EVENTS_MOCK.length === 0 ? (
            <ZEmpty text="暂无事件" />
          ) : (
            <div className={styles.timeline}>
              {EVENTS_MOCK.map((e) => (
                <EventItem key={e.id} event={e} />
              ))}
            </div>
          )}
        </ZCard>

        {/* AI 建议待审核 */}
        <ZCard
          title="AI 建议待审核"
          extra={<ZBadge type="accent" text={`${AI_SUGGESTIONS_MOCK.length} 条`} />}
        >
          {AI_SUGGESTIONS_MOCK.length === 0 ? (
            <ZEmpty text="暂无待审核建议" />
          ) : (
            <div className={styles.suggestionList}>
              {AI_SUGGESTIONS_MOCK.map((s) => (
                <SuggestionItem key={s.id} suggestion={s} />
              ))}
            </div>
          )}
        </ZCard>
      </div>

    </div>
  );
};

// ── 子组件 ──────────────────────────────────────────────────────────────────

const StatusRow: React.FC<{ label: string; status: 'ok' | 'error' | 'loading' }> = ({ label, status }) => {
  const icon =
    status === 'ok'      ? <CheckCircleOutlined  style={{ color: '#52c41a', fontSize: 14 }} /> :
    status === 'error'   ? <CloseCircleOutlined  style={{ color: '#ff4d4f', fontSize: 14 }} /> :
                           <ClockCircleOutlined  style={{ color: '#faad14', fontSize: 14 }} />;
  return (
    <div className={styles.statusRow}>
      {icon}
      <span className={styles.statusRowLabel}>{label}</span>
      <span className={styles.statusRowVal}>
        {status === 'ok' ? '正常' : status === 'error' ? '异常' : '检测中'}
      </span>
    </div>
  );
};

const MerchantCardItem: React.FC<{ merchant: MerchantCard; onClick: () => void }> = ({ merchant, onClick }) => (
  <div className={styles.merchantCard} onClick={onClick}>
    <div className={styles.merchantCardHeader}>
      <div>
        <div className={styles.merchantCardName}>{merchant.name}</div>
        <div className={styles.merchantCardMeta}>{merchant.pos} · {merchant.stores} 家门店</div>
      </div>
      <ZBadge type={merchant.status === '已上线' ? 'success' : merchant.status === '暂停' ? 'warning' : 'info'} text={merchant.status} />
    </div>
    <div className={styles.merchantCardBody}>
      <HealthRing score={merchant.healthScore} size={64} label="健康度" />
      <div className={styles.merchantCardStats}>
        <div className={styles.merchantStatItem}>
          <span className={styles.merchantStatVal}>{merchant.todayOrders}</span>
          <span className={styles.merchantStatLabel}>今日订单</span>
        </div>
        <div className={styles.merchantStatItem}>
          <span className={styles.merchantStatVal} style={{ color: '#0AAF9A' }}>{merchant.stores}</span>
          <span className={styles.merchantStatLabel}>门店数</span>
        </div>
      </div>
    </div>
  </div>
);

const eventTypeIcon: Record<SystemEvent['type'], React.ReactNode> = {
  system:   <ThunderboltOutlined style={{ color: '#6E6E73', fontSize: 12 }} />,
  merchant: <CheckCircleOutlined style={{ color: '#0AAF9A', fontSize: 12 }} />,
  ai:       <BulbOutlined        style={{ color: '#722ED1', fontSize: 12 }} />,
  alert:    <ClockCircleOutlined style={{ color: '#faad14', fontSize: 12 }} />,
};

const EventItem: React.FC<{ event: SystemEvent }> = ({ event }) => (
  <div className={styles.eventItem}>
    <div className={styles.eventDot}>{eventTypeIcon[event.type]}</div>
    <div className={styles.eventMeta}>
      <span className={styles.eventTime}>{event.time}</span>
      <span className={styles.eventContent}>{event.content}</span>
    </div>
  </div>
);

const SuggestionItem: React.FC<{ suggestion: AiSuggestion }> = ({ suggestion }) => (
  <div className={styles.suggestionItem}>
    <div className={styles.suggestionTop}>
      <span className={styles.suggestionMerchant}>{suggestion.merchant}</span>
      <ZBadge type="info" text={`置信度 ${suggestion.confidence}%`} />
    </div>
    <div className={styles.suggestionAction}>{suggestion.action}</div>
    <div className={styles.suggestionImpact}>{suggestion.impact}</div>
  </div>
);

export default PlatformAdminHome;
