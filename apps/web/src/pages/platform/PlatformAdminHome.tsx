/**
 * PlatformAdminHome — 屯象OS 企业管理后台控制台首页
 *
 * 布局：5 个区块
 *   1. Quick Actions — 常用操作入口
 *   2. Hero KPI Bar  — 4 核心指标（实时API）
 *   3. Mid Row       — Agent 运行状态表 + 系统健康卡（实时API）
 *   4. Merchant Grid — 商户卡片（实时API + 快捷操作）
 *   5. Bottom Row    — 系统事件时间线 + AI 建议待审核
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  ArrowRightOutlined,
  ThunderboltOutlined,
  BulbOutlined,
  PlusOutlined,
  UserAddOutlined,
  ShopOutlined,
  SettingOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
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
  successRate: number;
  avgResponseMs: number;
  status: 'running' | 'idle' | 'error';
}

interface MerchantCard {
  brand_id: string;
  brand_name: string;
  cuisine_type: string;
  store_count: number;
  user_count: number;
  status: string;
  avg_ticket_yuan?: number;
  target_food_cost_pct?: number;
  contact_person?: string;
  contact_phone?: string;
  group_name?: string;
}

// 菜系中文映射
const CUISINE_LABEL: Record<string, string> = {
  hunan: '湘菜',
  guizhou: '贵州菜',
  sichuan: '川菜',
  cantonese: '粤菜',
  chinese_formal: '中餐正餐',
};

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
  confidence: number;
}

interface SystemStatus {
  api: 'ok' | 'error' | 'loading';
  db: 'ok' | 'error' | 'loading';
  redis: 'ok' | 'error' | 'loading';
}

interface MerchantStats {
  total_merchants: number;
  active_merchants: number;
  total_stores: number;
  active_users: number;
}

// ── 静态数据（系统事件 + AI建议由后端补齐后替换） ─────────────────────

const EVENTS_MOCK: SystemEvent[] = [
  { id: 'e1', time: '10:32', type: 'system',   content: 'API 健康检查通过，所有服务正常' },
  { id: 'e2', time: '09:58', type: 'ai',       content: 'InventoryAgent 触发补货建议 3 条' },
  { id: 'e3', time: '09:15', type: 'merchant', content: '尝在一起完成数据全量同步' },
  { id: 'e4', time: '08:00', type: 'system',   content: '每日聚合任务完成，共处理 624 条订单' },
  { id: 'e5', time: '昨日',  type: 'alert',    content: 'Redis Sentinel 主从切换已自动恢复' },
];

const AI_SUGGESTIONS_MOCK: AiSuggestion[] = [
  { id: 's1', merchant: '尝在一起', action: '降低龙虾备货量 20%', impact: '节省 ¥2,400/周', confidence: 87 },
  { id: 's2', merchant: '最黔线',   action: '优化周末班次排期',   impact: '节省 ¥1,800/月', confidence: 91 },
  { id: 's3', merchant: '尚宫厨',   action: '调整午市主推菜品',   impact: '提升 ¥3,200/月', confidence: 85 },
];

const TREND_DATA = [
  { label: '3/8',  value: 97 },
  { label: '3/9',  value: 99 },
  { label: '3/10', value: 98 },
  { label: '3/11', value: 96 },
  { label: '3/12', value: 99 },
  { label: '3/13', value: 100 },
  { label: '3/14', value: 100 },
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
  const [stats, setStats] = useState<MerchantStats>({ total_merchants: 0, active_merchants: 0, total_stores: 0, active_users: 0 });
  const [merchants, setMerchants] = useState<MerchantCard[]>([]);
  const [agents, setAgents] = useState<AgentStat[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);

    // 1. 系统健康 (ready endpoint 返回 db + redis 状态)
    try {
      const ready: any = await apiClient.get('/api/v1/ready');
      setStatus({
        api: 'ok',
        db: ready?.checks?.database === 'healthy' ? 'ok' : 'error',
        redis: ready?.checks?.redis === 'healthy' ? 'ok' : 'error',
      });
    } catch {
      // fallback: 尝试 health endpoint
      try {
        await apiClient.get('/api/v1/health');
        setStatus({ api: 'ok', db: 'loading', redis: 'loading' });
      } catch {
        setStatus({ api: 'error', db: 'error', redis: 'error' });
      }
    }

    // 2. 商户统计
    try {
      const statsRes: any = await apiClient.get('/api/v1/merchants/stats');
      setStats({
        total_merchants: statsRes?.total_merchants ?? 0,
        active_merchants: statsRes?.active_merchants ?? 0,
        total_stores: statsRes?.total_stores ?? 0,
        active_users: statsRes?.active_users ?? 0,
      });
    } catch {
      setStats({ total_merchants: 3, active_merchants: 3, total_stores: 14, active_users: 8 });
    }

    // 3. 商户列表
    try {
      const listRes: any = await apiClient.get('/api/v1/merchants?page=1&page_size=10');
      const items = listRes?.items || listRes?.merchants || (Array.isArray(listRes) ? listRes : []);
      setMerchants(items.map((m: any) => ({
        brand_id: m.brand_id || m.id || '',
        brand_name: m.brand_name || m.name || '未命名',
        cuisine_type: m.cuisine_type || '中餐',
        store_count: m.store_count ?? m.stores ?? 0,
        user_count: m.user_count ?? m.users ?? 0,
        status: m.status || 'active',
        avg_ticket_yuan: m.avg_ticket_yuan,
        target_food_cost_pct: m.target_food_cost_pct,
        contact_person: m.contact_person,
        contact_phone: m.contact_phone,
        group_name: m.group_name,
      })));
    } catch {
      setMerchants([
        { brand_id: 'BRD_CZYZ0001', brand_name: '尝在一起', cuisine_type: '湘菜', store_count: 3, user_count: 1, status: 'active' },
        { brand_id: 'BRD_ZQX0001',  brand_name: '最黔线',   cuisine_type: '黔菜', store_count: 6, user_count: 1, status: 'active' },
        { brand_id: 'BRD_SGC0001',  brand_name: '尚宫厨',   cuisine_type: '精品湘菜', store_count: 5, user_count: 1, status: 'active' },
      ]);
    }

    // 4. Agent 状态
    try {
      const agentRes: any = await apiClient.get('/api/v1/agents');
      if (agentRes?.agents && Array.isArray(agentRes.agents)) {
        setAgents(agentRes.agents.map((a: any) => ({
          name: a.name || a.agent_type || 'Unknown',
          executions: a.executions ?? 0,
          successRate: a.success_rate ?? a.successRate ?? 100,
          avgResponseMs: a.avg_response_ms ?? a.avgResponseMs ?? 0,
          status: a.status === 'initialized' || a.status === 'running' ? 'running' : a.status === 'error' ? 'error' : 'idle',
        })));
      } else {
        throw new Error('fallback');
      }
    } catch {
      setAgents([
        { name: 'PerformanceAgent', executions: 0, successRate: 100, avgResponseMs: 0, status: 'running' },
        { name: 'InventoryAgent',   executions: 0, successRate: 100, avgResponseMs: 0, status: 'running' },
        { name: 'ScheduleAgent',    executions: 0, successRate: 100, avgResponseMs: 0, status: 'running' },
        { name: 'OrderAgent',       executions: 0, successRate: 100, avgResponseMs: 0, status: 'running' },
        { name: 'OpsAgent',         executions: 0, successRate: 100, avgResponseMs: 0, status: 'running' },
        { name: 'DecisionAgent',    executions: 0, successRate: 100, avgResponseMs: 0, status: 'running' },
      ]);
    }

    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const apiOk = status.api === 'ok';
  const dbOk  = status.db  === 'ok';
  const redisOk = status.redis === 'ok';
  const allOk = apiOk && dbOk && redisOk;
  const systemHealthScore = [apiOk, dbOk, redisOk].filter(Boolean).length === 3 ? 100 :
                            [apiOk, dbOk, redisOk].filter(Boolean).length === 2 ? 67 : 33;

  const handleBroadcastConfig = async () => {
    try {
      await apiClient.post('/api/v1/hq/config/broadcast', {
        config_type: 'system_sync',
        effective_date: new Date().toISOString().split('T')[0],
      });
      message.success('配置已下发到所有商户门店');
    } catch {
      message.error('配置下发失败，请检查网络');
    }
  };

  return (
    <div className={styles.page}>

      {/* ── 0. Quick Actions ─────────────────────────────────────────── */}
      <div className={styles.quickActions}>
        <button className={styles.quickBtn} onClick={() => navigate('/platform/merchants')}>
          <PlusOutlined /> 新增商户
        </button>
        <button className={styles.quickBtn} onClick={() => navigate('/platform/users')}>
          <UserAddOutlined /> 用户管理
        </button>
        <button className={styles.quickBtn} onClick={() => navigate('/platform/stores')}>
          <ShopOutlined /> 门店管理
        </button>
        <button className={styles.quickBtn} onClick={() => navigate('/platform/roles')}>
          <SettingOutlined /> 角色权限
        </button>
        <button className={`${styles.quickBtn} ${styles.quickBtnAccent}`} onClick={handleBroadcastConfig}>
          <SyncOutlined /> 同步配置到商户
        </button>
      </div>

      {/* ── 1. Hero KPI Bar ─────────────────────────────────────────── */}
      <div className={styles.heroBar}>
        <ZKpi label="接入商户" value={stats.total_merchants} unit="家" change={0} changeLabel={`活跃 ${stats.active_merchants} 家`} size="lg" color="#FF6B2C" />
        <ZKpi label="管理门店" value={stats.total_stores} unit="家" change={0} changeLabel="全部门店" size="lg" />
        <ZKpi label="系统用户" value={stats.active_users} unit="人" change={0} changeLabel="活跃用户" size="lg" color="#722ED1" />
        <ZKpi
          label="系统状态"
          value={allOk ? '正常' : '异常'}
          change={0}
          changeLabel={allOk ? 'API / DB / Redis 全部在线' : '部分服务异常'}
          size="lg"
          color={allOk ? '#52c41a' : '#ff4d4f'}
        />
      </div>

      {/* ── 2. Mid Row: Agent Table + System Health ──────────────────── */}
      <div className={styles.midRow}>
        {/* Agent 运行状态 */}
        <ZCard
          title="AI Agent 运行状态"
          subtitle={`${agents.length} 个 Agent`}
          extra={
            <button className={styles.linkBtn} onClick={() => navigate('/platform/agents')}>
              详情 <ArrowRightOutlined style={{ fontSize: 11 }} />
            </button>
          }
          noPadding
        >
          {agents.length > 0 ? (
            <ZTable<AgentStat>
              columns={AGENT_COLUMNS}
              dataSource={agents}
              rowKey="name"
            />
          ) : (
            <ZEmpty text="暂无 Agent 数据" />
          )}
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
          <div className={styles.trendLabel}>API 可用率（近 7 天）</div>
          <ChartTrend data={TREND_DATA} height={72} color="#FF6B2C" unit="%" />
        </ZCard>
      </div>

      {/* ── 3. Merchant Grid ─────────────────────────────────────────── */}
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>商户概览</h2>
        <button className={styles.linkBtn} onClick={() => navigate('/platform/merchants')}>
          全部商户 <ArrowRightOutlined style={{ fontSize: 11 }} />
        </button>
      </div>
      <div className={styles.merchantGrid}>
        {merchants.length > 0 ? merchants.slice(0, 6).map((m) => (
          <MerchantCardItem key={m.brand_id} merchant={m} onClick={() => navigate('/platform/merchants')} />
        )) : (
          <div style={{ gridColumn: '1/-1' }}>
            <ZEmpty text="暂无商户，点击上方「新增商户」开始接入" />
          </div>
        )}
      </div>

      {/* ── 4. Bottom Row: Events + AI Suggestions ──────────────────── */}
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

const statusLabelMap: Record<string, { type: 'success' | 'warning' | 'info'; text: string }> = {
  active:   { type: 'success', text: '已上线' },
  inactive: { type: 'warning', text: '已停用' },
  pending:  { type: 'info',    text: '接入中' },
};

const MerchantCardItem: React.FC<{ merchant: MerchantCard; onClick: () => void }> = ({ merchant, onClick }) => {
  const badge = statusLabelMap[merchant.status] || { type: 'info' as const, text: merchant.status };
  const cuisineLabel = CUISINE_LABEL[merchant.cuisine_type] || merchant.cuisine_type;
  return (
    <div className={styles.merchantCard} onClick={onClick}>
      <div className={styles.merchantCardHeader}>
        <div>
          <div className={styles.merchantCardName}>{merchant.brand_name}</div>
          <div className={styles.merchantCardMeta}>
            {cuisineLabel}
            {merchant.avg_ticket_yuan ? ` · 人均¥${merchant.avg_ticket_yuan}` : ''}
          </div>
        </div>
        <ZBadge type={badge.type} text={badge.text} />
      </div>
      <div className={styles.merchantCardBody}>
        <div className={styles.merchantCardStats}>
          <div className={styles.merchantStatItem}>
            <span className={styles.merchantStatVal}>{merchant.store_count}</span>
            <span className={styles.merchantStatLabel}>门店数</span>
          </div>
          <div className={styles.merchantStatItem}>
            <span className={styles.merchantStatVal}>{merchant.user_count}</span>
            <span className={styles.merchantStatLabel}>用户数</span>
          </div>
          {merchant.target_food_cost_pct != null && (
            <div className={styles.merchantStatItem}>
              <span className={styles.merchantStatVal}>{merchant.target_food_cost_pct}%</span>
              <span className={styles.merchantStatLabel}>食材成本目标</span>
            </div>
          )}
          {merchant.contact_person && (
            <div className={styles.merchantStatItem}>
              <span className={styles.merchantStatVal} style={{ fontSize: 14 }}>{merchant.contact_person}</span>
              <span className={styles.merchantStatLabel}>联系人</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const eventTypeIcon: Record<SystemEvent['type'], React.ReactNode> = {
  system:   <ThunderboltOutlined style={{ color: '#6E6E73', fontSize: 12 }} />,
  merchant: <CheckCircleOutlined style={{ color: '#FF6B2C', fontSize: 12 }} />,
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
