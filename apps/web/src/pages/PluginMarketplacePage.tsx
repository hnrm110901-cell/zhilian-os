import React, { useState, useEffect, useCallback } from 'react';
import { Form, Input, message } from 'antd';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZModal, ZEmpty,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './PluginMarketplacePage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────────

interface Plugin {
  id: string;
  name: string;
  slug: string;
  description: string;
  category: string;
  icon_emoji: string;
  version: string;
  status: string;
  tier_required: string;
  price_type: string;
  price_amount: number;
  install_count: number;
  developer_name: string;
  developer_company: string | null;
  tags: string[];
  webhook_url: string | null;
}

interface MarketplaceStats {
  published_plugins: number;
  pending_review: number;
  active_developers: number;
  total_installs: number;
  by_category: Record<string, number>;
  categories: Record<string, string>;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const TIER_BADGE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  free: 'neutral', basic: 'success', pro: 'warning', enterprise: 'error',
};
const TIER_LABELS: Record<string, string> = {
  free: '免费版', basic: '基础版', pro: '专业版', enterprise: '企业版',
};
const PRICE_LABELS: Record<string, string> = {
  free: '免费', per_call: '按量', subscription: '订阅',
};
const CAT_LABELS: Record<string, string> = {
  pos_integration: 'POS集成',
  erp_integration: 'ERP集成',
  marketing: '营销工具',
  analytics: '数据分析',
  operations: '运营管理',
};
const CATEGORIES = ['all', 'pos_integration', 'erp_integration', 'marketing', 'analytics', 'operations'];

// ── Admin pending table columns ────────────────────────────────────────────────

const makePendingColumns = (
  onReview: (plugin: Plugin, approved: boolean) => void,
): ZTableColumn<Plugin>[] => [
  {
    key: 'name',
    title: '插件',
    render: (name, row) => (
      <div>
        <span style={{ marginRight: 6 }}>{row.icon_emoji}</span>
        <span style={{ fontWeight: 600 }}>{name}</span>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginLeft: 6 }}>v{row.version}</span>
      </div>
    ),
  },
  { key: 'developer_name', title: '开发者' },
  {
    key: 'category',
    title: '分类',
    render: (cat) => <ZBadge type="neutral" text={CAT_LABELS[cat] || cat} />,
  },
  {
    key: 'tier_required',
    title: '所需套餐',
    align: 'center',
    render: (tier) => <ZBadge type={TIER_BADGE[tier] || 'neutral'} text={TIER_LABELS[tier] || tier} />,
  },
  {
    key: 'created_at',
    title: '提交时间',
    render: (dt) => dt ? new Date(dt).toLocaleDateString('zh-CN') : '—',
  },
  {
    key: 'id',
    title: '操作',
    render: (_, row) => (
      <div style={{ display: 'flex', gap: 6 }}>
        <ZButton variant="primary" onClick={() => onReview(row, true)}>批准</ZButton>
        <ZButton onClick={() => onReview(row, false)}>驳回</ZButton>
      </div>
    ),
  },
];

// ── Plugin card component ──────────────────────────────────────────────────────

interface PluginCardProps {
  plugin: Plugin;
  installed: boolean;
  onInstall: (id: string) => void;
  onUninstall: (id: string) => void;
  actionLoading: boolean;
}

const PluginCard: React.FC<PluginCardProps> = ({ plugin, installed, onInstall, onUninstall, actionLoading }) => (
  <div className={styles.pluginCard}>
    <div className={styles.pluginCardTop}>
      <div className={styles.pluginIcon}>{plugin.icon_emoji}</div>
      <div className={styles.pluginMeta}>
        <p className={styles.pluginName}>{plugin.name}</p>
        <p className={styles.pluginDev}>{plugin.developer_name}{plugin.developer_company ? ` · ${plugin.developer_company}` : ''}</p>
        <div className={styles.pluginBadges}>
          <ZBadge type="neutral" text={CAT_LABELS[plugin.category] || plugin.category} />
          <ZBadge type={TIER_BADGE[plugin.tier_required] || 'neutral'} text={TIER_LABELS[plugin.tier_required] || plugin.tier_required} />
          {plugin.price_type !== 'free' && (
            <ZBadge type="warning" text={PRICE_LABELS[plugin.price_type] || plugin.price_type} />
          )}
        </div>
      </div>
    </div>
    <p className={styles.pluginDesc}>{plugin.description || '暂无描述'}</p>
    <div className={styles.pluginFooter}>
      <span className={styles.pluginInstallCount}>
        {plugin.install_count.toLocaleString()} 次安装
        {installed && <span className={styles.installedBadge} style={{ marginLeft: 8 }}>✓ 已安装</span>}
      </span>
      {installed ? (
        <ZButton onClick={() => onUninstall(plugin.id)} disabled={actionLoading}>卸载</ZButton>
      ) : (
        <ZButton variant="primary" onClick={() => onInstall(plugin.id)} disabled={actionLoading}>安装</ZButton>
      )}
    </div>
  </div>
);

// ── Page component ─────────────────────────────────────────────────────────────

const PluginMarketplacePage: React.FC = () => {
  const storeId = localStorage.getItem('store_id') || 'STORE001';

  const [stats, setStats] = useState<MarketplaceStats | null>(null);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');

  // Installed plugin IDs for this store
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [actionLoading, setActionLoading] = useState(false);

  // Admin review
  const [pendingPlugins, setPendingPlugins] = useState<Plugin[]>([]);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [reviewModal, setReviewModal] = useState(false);
  const [reviewTarget, setReviewTarget] = useState<Plugin | null>(null);
  const [reviewApproved, setReviewApproved] = useState(true);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewForm] = Form.useForm();

  // Submit plugin
  const [submitModal, setSubmitModal] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitForm] = Form.useForm();

  const loadStats = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/marketplace/stats');
      setStats(res.data);
    } catch (e) {
      handleApiError(e);
    }
  }, []);

  const loadPlugins = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (activeCategory !== 'all') params.category = activeCategory;
      if (search) params.search = search;
      const res = await apiClient.get('/api/v1/marketplace/plugins', { params });
      setPlugins(res.data.plugins || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [activeCategory, search]);

  const loadInstalled = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/marketplace/stores/${storeId}/plugins`);
      const ids = new Set<string>((res.data.plugins || []).map((p: Plugin) => p.id));
      setInstalledIds(ids);
    } catch {
      // silent
    }
  }, [storeId]);

  const loadPending = useCallback(async () => {
    setPendingLoading(true);
    try {
      const res = await apiClient.get('/api/v1/marketplace/admin/plugins');
      setPendingPlugins(res.data.plugins || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setPendingLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
    loadInstalled();
    loadPending();
  }, [loadStats, loadInstalled, loadPending]);

  useEffect(() => {
    loadPlugins();
  }, [loadPlugins]);

  const handleInstall = async (pluginId: string) => {
    setActionLoading(true);
    try {
      await apiClient.post(`/api/v1/marketplace/stores/${storeId}/install/${pluginId}`);
      message.success('插件安装成功');
      setInstalledIds(prev => new Set([...prev, pluginId]));
      loadStats();
    } catch (e) {
      handleApiError(e);
    } finally {
      setActionLoading(false);
    }
  };

  const handleUninstall = async (pluginId: string) => {
    setActionLoading(true);
    try {
      await apiClient.delete(`/api/v1/marketplace/stores/${storeId}/install/${pluginId}`);
      message.success('插件已卸载');
      setInstalledIds(prev => { const s = new Set(prev); s.delete(pluginId); return s; });
      loadStats();
    } catch (e) {
      handleApiError(e);
    } finally {
      setActionLoading(false);
    }
  };

  const openReviewModal = (plugin: Plugin, approved: boolean) => {
    setReviewTarget(plugin);
    setReviewApproved(approved);
    reviewForm.resetFields();
    setReviewModal(true);
  };

  const handleReviewSubmit = async (values: { note?: string }) => {
    if (!reviewTarget) return;
    setReviewLoading(true);
    try {
      await apiClient.post(`/api/v1/marketplace/admin/plugins/${reviewTarget.id}/review`, {
        approved: reviewApproved,
        note: values.note,
      });
      message.success(reviewApproved ? '已批准插件上线' : '已驳回申请');
      setReviewModal(false);
      reviewForm.resetFields();
      loadPending();
      loadStats();
    } catch (e) {
      handleApiError(e);
    } finally {
      setReviewLoading(false);
    }
  };

  const handleSubmitPlugin = async (values: {
    developer_id: string;
    name: string;
    slug: string;
    description: string;
    category: string;
    tier_required: string;
    price_type: string;
    webhook_url?: string;
  }) => {
    setSubmitLoading(true);
    try {
      await apiClient.post('/api/v1/marketplace/plugins', {
        ...values,
        price_amount: 0,
        tags: [],
      });
      message.success('插件已提交审核！');
      setSubmitModal(false);
      submitForm.resetFields();
      loadPending();
      loadStats();
    } catch (e) {
      handleApiError(e);
    } finally {
      setSubmitLoading(false);
    }
  };

  const pendingColumns = makePendingColumns(openReviewModal);

  const reviewFooter = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
      <ZButton onClick={() => setReviewModal(false)}>取消</ZButton>
      <ZButton
        variant={reviewApproved ? 'primary' : undefined}
        disabled={reviewLoading}
        onClick={() => reviewForm.submit()}
      >
        {reviewLoading ? '提交中…' : (reviewApproved ? '确认批准' : '确认驳回')}
      </ZButton>
    </div>
  );

  const submitFooter = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
      <ZButton onClick={() => { setSubmitModal(false); submitForm.resetFields(); }}>取消</ZButton>
      <ZButton variant="primary" disabled={submitLoading} onClick={() => submitForm.submit()}>
        {submitLoading ? '提交中…' : '提交审核'}
      </ZButton>
    </div>
  );

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>插件市场</h1>
          <p className={styles.pageSub}>发现并安装 ISV 提供的集成插件，扩展屯象OS的能力边界</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={() => { loadPlugins(); loadStats(); loadPending(); }}>刷新</ZButton>
          <ZButton onClick={() => setSubmitModal(true)}>提交插件</ZButton>
        </div>
      </div>

      {/* KPI */}
      <div className={styles.kpiGrid}>
        {loading && !stats ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : (
          <>
            <ZCard><ZKpi label="已上线插件" value={stats?.published_plugins ?? 0} unit="个" /></ZCard>
            <ZCard><ZKpi label="累计安装" value={stats?.total_installs ?? 0} unit="次" /></ZCard>
            <ZCard><ZKpi label="活跃开发者" value={stats?.active_developers ?? 0} unit="位" /></ZCard>
            <ZCard><ZKpi label="待审核" value={stats?.pending_review ?? 0} unit="个" /></ZCard>
          </>
        )}
      </div>

      {/* Plugin list */}
      <ZCard
        title={`插件列表（${total} 个）`}
        extra={
          <div className={styles.toolbar}>
            <input
              className={styles.searchInput}
              placeholder="搜索插件名称或描述…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                className={`${styles.categoryPill} ${activeCategory === cat ? styles.categoryPillActive : ''}`}
                onClick={() => setActiveCategory(cat)}
              >
                {cat === 'all' ? '全部' : CAT_LABELS[cat] || cat}
              </button>
            ))}
          </div>
        }
      >
        {loading ? (
          <ZSkeleton height={280} />
        ) : plugins.length > 0 ? (
          <div className={styles.pluginGrid}>
            {plugins.map(plugin => (
              <PluginCard
                key={plugin.id}
                plugin={plugin}
                installed={installedIds.has(plugin.id)}
                onInstall={handleInstall}
                onUninstall={handleUninstall}
                actionLoading={actionLoading}
              />
            ))}
          </div>
        ) : (
          <ZEmpty text="暂无符合条件的插件" />
        )}
      </ZCard>

      {/* Admin: pending review */}
      {(pendingPlugins.length > 0 || pendingLoading) && (
        <ZCard title={`待审核插件（${pendingPlugins.length} 个）`}>
          {pendingLoading ? (
            <ZSkeleton height={200} />
          ) : (
            <ZTable columns={pendingColumns} data={pendingPlugins} rowKey="id" />
          )}
        </ZCard>
      )}

      {/* Review modal */}
      <ZModal
        open={reviewModal}
        title={`${reviewApproved ? '批准' : '驳回'}插件：${reviewTarget?.name}`}
        onClose={() => { setReviewModal(false); reviewForm.resetFields(); }}
        footer={reviewFooter}
        width={440}
      >
        {reviewTarget && (
          <div style={{ marginBottom: 16, padding: '10px 0', borderBottom: '1px solid var(--border-color, #f0f0f0)' }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 24 }}>{reviewTarget.icon_emoji}</span>
              <div>
                <div style={{ fontWeight: 600 }}>{reviewTarget.name} <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>v{reviewTarget.version}</span></div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{reviewTarget.developer_name}</div>
              </div>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>{reviewTarget.description}</p>
          </div>
        )}
        <Form form={reviewForm} layout="vertical" onFinish={handleReviewSubmit}>
          <Form.Item
            name="note"
            label="审核意见"
            rules={[{ required: !reviewApproved, message: '驳回时必须填写审核意见' }]}
          >
            <Input.TextArea rows={3} placeholder={reviewApproved ? '可选：填写上线备注' : '必填：说明驳回原因'} />
          </Form.Item>
        </Form>
      </ZModal>

      {/* Submit plugin modal */}
      <ZModal
        open={submitModal}
        title="提交插件"
        onClose={() => { setSubmitModal(false); submitForm.resetFields(); }}
        footer={submitFooter}
        width={520}
      >
        <Form form={submitForm} layout="vertical" onFinish={handleSubmitPlugin}>
          <Form.Item name="developer_id" label="开发者 ID" rules={[{ required: true }]}>
            <Input placeholder="dev_xxxxxxxxxxxxxxxx" />
          </Form.Item>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Form.Item name="name" label="插件名称" rules={[{ required: true }]}>
              <Input placeholder="例：美团订单同步" />
            </Form.Item>
            <Form.Item name="slug" label="标识符（小写）" rules={[{ required: true, pattern: /^[a-z0-9-]+$/, message: '只允许小写字母、数字和连字符' }]}>
              <Input placeholder="例：meituan-order-sync" />
            </Form.Item>
          </div>
          <Form.Item name="description" label="插件描述" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="简要说明插件功能和适用场景" />
          </Form.Item>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <Form.Item name="category" label="分类" initialValue="operations" rules={[{ required: true }]}>
              <select className={styles.nativeSelect}>
                <option value="pos_integration">POS集成</option>
                <option value="erp_integration">ERP集成</option>
                <option value="marketing">营销工具</option>
                <option value="analytics">数据分析</option>
                <option value="operations">运营管理</option>
              </select>
            </Form.Item>
            <Form.Item name="tier_required" label="最低套餐" initialValue="free" rules={[{ required: true }]}>
              <select className={styles.nativeSelect}>
                <option value="free">免费版</option>
                <option value="basic">基础版</option>
                <option value="pro">专业版</option>
                <option value="enterprise">企业版</option>
              </select>
            </Form.Item>
            <Form.Item name="price_type" label="收费方式" initialValue="free" rules={[{ required: true }]}>
              <select className={styles.nativeSelect}>
                <option value="free">免费</option>
                <option value="per_call">按量计费</option>
                <option value="subscription">按月订阅</option>
              </select>
            </Form.Item>
          </div>
          <Form.Item name="webhook_url" label="Webhook 回调地址">
            <Input placeholder="https://your-service.com/webhook（可选）" />
          </Form.Item>
        </Form>
      </ZModal>
    </div>
  );
};

export default PluginMarketplacePage;
