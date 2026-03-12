import React, { useState, useEffect, useCallback } from 'react';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './ISVDashboardPage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────────

interface Developer {
  id: string;
  name: string;
  email: string;
  tier: string;
  status: string;
}

interface DevSummary {
  developer_id: string;
  name: string;
  tier: string;
  status: string;
  published_plugins: number;
  total_installs: number;
  total_earned_yuan: number;
  pending_earnings_yuan: number;
}

interface Plugin {
  id: string;
  name: string;
  slug: string;
  category: string;
  icon_emoji: string;
  status: string;
  tier_required: string;
  price_type: string;
  price_amount: number;
  install_count: number;
}

interface Settlement {
  id: string;
  period: string;
  installed_plugins: number;
  gross_revenue_yuan: number;
  share_pct: number;
  net_payout_yuan: number;
  status: string;
  settled_at: string | null;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const TIER_BADGE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  free: 'neutral', basic: 'success', pro: 'warning', enterprise: 'error',
};
const TIER_LABELS: Record<string, string> = {
  free: '免费版', basic: '基础版', pro: '专业版', enterprise: '企业版',
};
const STATUS_BADGE: Record<string, 'neutral' | 'warning' | 'success' | 'error'> = {
  pending: 'warning', approved: 'neutral', paid: 'success',
};
const STATUS_LABELS: Record<string, string> = {
  pending: '待审核', approved: '已审核', paid: '已付款',
};
const CAT_LABELS: Record<string, string> = {
  pos_integration: 'POS集成', erp_integration: 'ERP集成',
  marketing: '营销工具', analytics: '数据分析', operations: '运营管理',
};
const PLUGIN_STATUS_BADGE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  published: 'success', pending_review: 'warning', rejected: 'error', draft: 'neutral',
};
const PLUGIN_STATUS_LABELS: Record<string, string> = {
  published: '已上线', pending_review: '审核中', rejected: '已驳回', draft: '草稿',
};

// ── Plugin table columns ───────────────────────────────────────────────────────

const pluginColumns: ZTableColumn<Plugin>[] = [
  {
    key: 'name',
    title: '插件',
    render: (name, row) => (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 20 }}>{row.icon_emoji}</span>
        <div>
          <div style={{ fontWeight: 600 }}>{name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{row.slug}</div>
        </div>
      </div>
    ),
  },
  {
    key: 'category',
    title: '分类',
    render: (cat) => <ZBadge type="neutral" text={CAT_LABELS[cat] || cat} />,
  },
  {
    key: 'status',
    title: '状态',
    align: 'center',
    render: (s) => <ZBadge type={PLUGIN_STATUS_BADGE[s] || 'neutral'} text={PLUGIN_STATUS_LABELS[s] || s} />,
  },
  {
    key: 'install_count',
    title: '安装量',
    align: 'center',
    render: (n) => <span style={{ fontWeight: 700 }}>{n}</span>,
  },
  {
    key: 'price_type',
    title: '收费',
    align: 'center',
    render: (t, row) => t === 'free'
      ? <ZBadge type="success" text="免费" />
      : <span style={{ fontSize: 12 }}>¥{row.price_amount} / {t === 'subscription' ? '月' : '次'}</span>,
  },
];

// ── Settlement table columns ───────────────────────────────────────────────────

const settlementColumns: ZTableColumn<Settlement>[] = [
  {
    key: 'period',
    title: '结算周期',
    render: (p) => <span className={styles.periodTag}>{p}</span>,
  },
  { key: 'installed_plugins', title: '安装插件', align: 'center' },
  {
    key: 'gross_revenue_yuan',
    title: '总收入',
    align: 'right',
    render: (v) => <span className={styles.amountCell}>¥{Number(v).toFixed(2)}</span>,
  },
  { key: 'share_pct', title: '分成比例', align: 'center', render: (v) => `${v}%` },
  {
    key: 'net_payout_yuan',
    title: '应得分成',
    align: 'right',
    render: (v) => <span className={styles.amountCell} style={{ color: '#1A7A52' }}>¥{Number(v).toFixed(2)}</span>,
  },
  {
    key: 'status',
    title: '状态',
    align: 'center',
    render: (s) => <ZBadge type={STATUS_BADGE[s] || 'neutral'} text={STATUS_LABELS[s] || s} />,
  },
  {
    key: 'settled_at',
    title: '结算时间',
    render: (dt) => dt ? new Date(dt).toLocaleDateString('zh-CN') : '—',
  },
];

// ── Component ──────────────────────────────────────────────────────────────────

const ISVDashboardPage: React.FC = () => {
  const [developers, setDevelopers] = useState<Developer[]>([]);
  const [selectedDevId, setSelectedDevId] = useState('');

  const [devSummary, setDevSummary] = useState<DevSummary | null>(null);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);

  const [devsLoading, setDevsLoading] = useState(false);
  const [dataLoading, setDataLoading] = useState(false);

  // Load developer list on mount
  useEffect(() => {
    const loadDevs = async () => {
      setDevsLoading(true);
      try {
        const res = await apiClient.get('/api/v1/open/isv/admin/list', {
          params: { limit: '200', offset: '0' },
        });
        setDevelopers(res.data.developers || []);
      } catch (e) {
        handleApiError(e);
      } finally {
        setDevsLoading(false);
      }
    };
    loadDevs();
  }, []);

  const loadDevData = useCallback(async (devId: string) => {
    if (!devId) return;
    setDataLoading(true);
    setDevSummary(null);
    setPlugins([]);
    setSettlements([]);
    try {
      const [summaryRes, pluginsRes, settlementsRes] = await Promise.allSettled([
        apiClient.get(`/api/v1/revenue/developer/${devId}/summary`),
        apiClient.get(`/api/v1/revenue/developer/${devId}/plugins`),
        apiClient.get(`/api/v1/revenue/developer/${devId}/settlements`),
      ]);
      if (summaryRes.status === 'fulfilled') setDevSummary(summaryRes.value.data);
      if (pluginsRes.status === 'fulfilled') setPlugins(pluginsRes.value.data.plugins || []);
      if (settlementsRes.status === 'fulfilled') setSettlements(settlementsRes.value.data.settlements || []);
    } finally {
      setDataLoading(false);
    }
  }, []);

  const handleDevChange = (devId: string) => {
    setSelectedDevId(devId);
    loadDevData(devId);
  };

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>ISV 开发者看板</h1>
          <p className={styles.pageSub}>查看开发者的插件表现、安装量和收入分成情况</p>
        </div>
        <div className={styles.headerActions}>
          {selectedDevId && (
            <ZButton onClick={() => loadDevData(selectedDevId)}>刷新</ZButton>
          )}
        </div>
      </div>

      {/* Developer picker */}
      <ZCard title="选择开发者">
        <div className={styles.toolbar}>
          {devsLoading ? (
            <ZSkeleton height={36} />
          ) : (
            <select
              className={styles.devSelector}
              value={selectedDevId}
              onChange={e => handleDevChange(e.target.value)}
            >
              <option value="">— 请选择开发者 —</option>
              {developers.map(dev => (
                <option key={dev.id} value={dev.id}>
                  {dev.name} ({dev.email}) — {TIER_LABELS[dev.tier] || dev.tier}
                </option>
              ))}
            </select>
          )}
          {devSummary && (
            <div className={styles.tierBadgeRow}>
              <ZBadge type={TIER_BADGE[devSummary.tier] || 'neutral'} text={TIER_LABELS[devSummary.tier] || devSummary.tier} />
              <ZBadge type={devSummary.status === 'active' ? 'success' : 'error'} text={devSummary.status === 'active' ? '活跃' : '已暂停'} />
            </div>
          )}
        </div>
      </ZCard>

      {/* Empty state */}
      {!selectedDevId && (
        <div className={styles.emptyHint}>
          <span className={styles.emptyIcon}>📊</span>
          选择一个开发者以查看其插件表现和收入分成数据
        </div>
      )}

      {/* KPI */}
      {selectedDevId && (
        <>
          <div className={styles.kpiGrid}>
            {dataLoading ? (
              [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
            ) : devSummary ? (
              <>
                <ZCard><ZKpi label="已发布插件" value={devSummary.published_plugins} unit="个" /></ZCard>
                <ZCard><ZKpi label="累计安装量" value={devSummary.total_installs} unit="次" /></ZCard>
                <ZCard><ZKpi label="累计结算" value={`¥${devSummary.total_earned_yuan.toFixed(2)}`} /></ZCard>
                <ZCard><ZKpi label="待发放分成" value={`¥${devSummary.pending_earnings_yuan.toFixed(2)}`} /></ZCard>
              </>
            ) : null}
          </div>

          {/* Plugins */}
          <ZCard title={`插件列表（${plugins.length} 个）`}>
            {dataLoading ? (
              <ZSkeleton height={200} />
            ) : plugins.length > 0 ? (
              <ZTable columns={pluginColumns} data={plugins} rowKey="id" />
            ) : (
              <ZEmpty text="该开发者暂无插件" />
            )}
          </ZCard>

          {/* Settlements */}
          <ZCard title={`结算历史（${settlements.length} 条）`}>
            {dataLoading ? (
              <ZSkeleton height={200} />
            ) : settlements.length > 0 ? (
              <ZTable columns={settlementColumns} data={settlements} rowKey="id" />
            ) : (
              <ZEmpty text="暂无结算记录" />
            )}
          </ZCard>
        </>
      )}
    </div>
  );
};

export default ISVDashboardPage;
