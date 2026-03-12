import React, { useState, useEffect, useCallback } from 'react';
import { ZCard, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty, ZModal } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './WebhookManagementPage.module.css';

// ── Types ───────────────────────────────────────────────────────────────────

interface WebhookSub {
  id: string;
  developer_id: string;
  endpoint_url: string;
  events: string[];
  status: 'active' | 'paused';
  description: string | null;
  failure_count: number;
  last_triggered_at: string | null;
  created_at: string | null;
  secret_hash: string;
}

interface DeliveryLog {
  id: string;
  subscription_id: string;
  event_type: string;
  payload_size: number | null;
  status: string;
  http_status: number | null;
  attempts: number;
  delivered_at: string | null;
  error_message: string | null;
  created_at: string | null;
}

interface SupportedEvent {
  type: string;
  description: string;
}

// ── Constants ────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, 'success' | 'warning' | 'neutral' | 'error'> = {
  active:    'success',
  paused:    'warning',
  pending:   'neutral',
  delivered: 'success',
  failed:    'error',
};

// ── Columns ──────────────────────────────────────────────────────────────────

const deliveryColumns: ZTableColumn<DeliveryLog>[] = [
  {
    key: 'event_type',
    title: '事件类型',
    render: (v) => <code className={styles.eventCode}>{v}</code>,
  },
  {
    key: 'status',
    title: '状态',
    align: 'center',
    render: (v) => <ZBadge type={STATUS_BADGE[v] || 'neutral'} text={v} />,
  },
  {
    key: 'http_status',
    title: 'HTTP',
    align: 'center',
    render: (v) => v ? (
      <span style={{ fontWeight: 700, color: v < 300 ? '#1A7A52' : '#C53030' }}>{v}</span>
    ) : <span style={{ color: 'var(--text-secondary)' }}>—</span>,
  },
  {
    key: 'attempts',
    title: '重试次数',
    align: 'center',
    render: (v) => <span>{v}</span>,
  },
  {
    key: 'payload_size',
    title: '大小',
    align: 'right',
    render: (v) => v ? <span className={styles.mono}>{v} B</span> : '—',
  },
  {
    key: 'created_at',
    title: '创建时间',
    render: (v) => v ? <span className={styles.mono}>{v.slice(0, 16).replace('T', ' ')}</span> : '—',
  },
];

// ── Component ────────────────────────────────────────────────────────────────

const DEVELOPER_ID = localStorage.getItem('developer_id') || 'dev-demo-001';

const WebhookManagementPage: React.FC = () => {
  const [subs, setSubs] = useState<WebhookSub[]>([]);
  const [supportedEvents, setSupportedEvents] = useState<SupportedEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [deliveryModal, setDeliveryModal] = useState<WebhookSub | null>(null);
  const [deliveries, setDeliveries] = useState<DeliveryLog[]>([]);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliSummary, setDeliSummary] = useState<Record<string, number>>({});

  // form state
  const [formUrl, setFormUrl] = useState('');
  const [formSecret, setFormSecret] = useState('');
  const [formEvents, setFormEvents] = useState<string[]>([]);
  const [formDesc, setFormDesc] = useState('');
  const [formSaving, setFormSaving] = useState(false);

  const loadSubs = useCallback(async () => {
    setLoading(true);
    try {
      const [subRes, evRes] = await Promise.allSettled([
        apiClient.get('/api/v1/webhooks/subscriptions', { params: { developer_id: DEVELOPER_ID } }),
        apiClient.get('/api/v1/webhooks/events'),
      ]);
      if (subRes.status === 'fulfilled') setSubs(subRes.value.data.subscriptions || []);
      if (evRes.status === 'fulfilled') setSupportedEvents(evRes.value.data.events || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSubs(); }, [loadSubs]);

  const toggleStatus = async (sub: WebhookSub) => {
    const newStatus = sub.status === 'active' ? 'paused' : 'active';
    try {
      await apiClient.put(`/api/v1/webhooks/subscriptions/${sub.id}`, { status: newStatus }, {
        params: { developer_id: DEVELOPER_ID },
      });
      loadSubs();
    } catch (e) { handleApiError(e); }
  };

  const deleteSub = async (sub: WebhookSub) => {
    if (!window.confirm(`确认删除 Webhook：${sub.endpoint_url}？`)) return;
    try {
      await apiClient.delete(`/api/v1/webhooks/subscriptions/${sub.id}`, {
        params: { developer_id: DEVELOPER_ID },
      });
      loadSubs();
    } catch (e) { handleApiError(e); }
  };

  const pingSub = async (sub: WebhookSub) => {
    try {
      await apiClient.post(`/api/v1/webhooks/subscriptions/${sub.id}/ping`, null, {
        params: { developer_id: DEVELOPER_ID },
      });
      alert('Ping 已发送，请检查您的端点日志');
    } catch (e) { handleApiError(e); }
  };

  const openDeliveries = async (sub: WebhookSub) => {
    setDeliveryModal(sub);
    setDeliveryLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/webhooks/subscriptions/${sub.id}/deliveries`, {
        params: { developer_id: DEVELOPER_ID, limit: 20 },
      });
      setDeliveries(res.data.deliveries || []);
      setDeliSummary(res.data.summary || {});
    } catch (e) { handleApiError(e); }
    finally { setDeliveryLoading(false); }
  };

  const createSub = async () => {
    if (!formUrl.startsWith('https://')) {
      alert('endpoint_url 必须使用 HTTPS'); return;
    }
    if (formEvents.length === 0) {
      alert('请至少选择一个事件类型'); return;
    }
    setFormSaving(true);
    try {
      await apiClient.post('/api/v1/webhooks/subscriptions', {
        developer_id: DEVELOPER_ID,
        endpoint_url: formUrl,
        secret: formSecret || 'default-secret',
        events: formEvents,
        description: formDesc || null,
      });
      setCreateModal(false);
      setFormUrl(''); setFormSecret(''); setFormEvents([]); setFormDesc('');
      loadSubs();
    } catch (e) { handleApiError(e); }
    finally { setFormSaving(false); }
  };

  const toggleEvent = (ev: string) => {
    setFormEvents(prev =>
      prev.includes(ev) ? prev.filter(e => e !== ev) : [...prev, ev]
    );
  };

  // ── Summary stats ──────────────────────────────────────────────────────────
  const totalActive  = subs.filter(s => s.status === 'active').length;
  const totalPaused  = subs.filter(s => s.status === 'paused').length;
  const totalFailing = subs.filter(s => s.failure_count > 0).length;

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Webhook 事件订阅</h1>
          <p className={styles.pageSub}>订阅平台事件，实时接收插件安装、结算审批、评分等通知</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={loadSubs}>刷新</ZButton>
          <ZButton onClick={() => setCreateModal(true)}>+ 新建 Webhook</ZButton>
        </div>
      </div>

      {/* Stats bar */}
      <div className={styles.statsRow}>
        <div className={styles.statItem}>
          <span className={styles.statNum}>{subs.length}</span>
          <span className={styles.statLabel}>总订阅</span>
        </div>
        <div className={styles.statItem}>
          <span className={`${styles.statNum} ${styles.statGreen}`}>{totalActive}</span>
          <span className={styles.statLabel}>活跃</span>
        </div>
        <div className={styles.statItem}>
          <span className={`${styles.statNum} ${styles.statOrange}`}>{totalPaused}</span>
          <span className={styles.statLabel}>已暂停</span>
        </div>
        <div className={styles.statItem}>
          <span className={`${styles.statNum} ${totalFailing > 0 ? styles.statRed : ''}`}>{totalFailing}</span>
          <span className={styles.statLabel}>失败订阅</span>
        </div>
      </div>

      {/* Subscription cards */}
      {loading ? (
        <ZSkeleton height={200} />
      ) : subs.length === 0 ? (
        <ZCard>
          <ZEmpty text="暂无 Webhook 订阅，点击「新建 Webhook」开始" />
        </ZCard>
      ) : (
        <div className={styles.subList}>
          {subs.map(sub => (
            <ZCard key={sub.id}>
              <div className={styles.subHeader}>
                <div className={styles.subLeft}>
                  <ZBadge type={STATUS_BADGE[sub.status] || 'neutral'} text={sub.status === 'active' ? '活跃' : '已暂停'} />
                  <code className={styles.subUrl}>{sub.endpoint_url}</code>
                </div>
                <div className={styles.subActions}>
                  <ZButton onClick={() => pingSub(sub)}>Ping</ZButton>
                  <ZButton onClick={() => openDeliveries(sub)}>投递历史</ZButton>
                  <ZButton onClick={() => toggleStatus(sub)}>
                    {sub.status === 'active' ? '暂停' : '启用'}
                  </ZButton>
                  <ZButton onClick={() => deleteSub(sub)}>删除</ZButton>
                </div>
              </div>

              {sub.description && (
                <p className={styles.subDesc}>{sub.description}</p>
              )}

              <div className={styles.eventTags}>
                {sub.events.map(ev => (
                  <code key={ev} className={styles.eventTag}>{ev}</code>
                ))}
              </div>

              <div className={styles.subMeta}>
                <span>Secret: <code>{sub.secret_hash}</code></span>
                {sub.failure_count > 0 && (
                  <span className={styles.failCount}>⚠ 失败次数: {sub.failure_count}</span>
                )}
                {sub.last_triggered_at && (
                  <span>最近触发: {sub.last_triggered_at.slice(0, 16).replace('T', ' ')}</span>
                )}
              </div>
            </ZCard>
          ))}
        </div>
      )}

      {/* Supported events reference */}
      {supportedEvents.length > 0 && (
        <ZCard title="支持的事件类型">
          <div className={styles.eventsGrid}>
            {supportedEvents.map(ev => (
              <div key={ev.type} className={styles.eventRefItem}>
                <code className={styles.eventCode}>{ev.type}</code>
                <span className={styles.eventRefDesc}>{ev.description}</span>
              </div>
            ))}
          </div>
        </ZCard>
      )}

      {/* Create Modal */}
      <ZModal
        open={createModal}
        title="新建 Webhook 订阅"
        onClose={() => { setCreateModal(false); }}
        footer={
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <ZButton onClick={() => setCreateModal(false)}>取消</ZButton>
            <ZButton onClick={createSub} disabled={formSaving}>
              {formSaving ? '保存中…' : '保存'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Endpoint URL <span className={styles.required}>*</span></label>
          <input
            className={styles.formInput}
            placeholder="https://your-server.com/webhook"
            value={formUrl}
            onChange={e => setFormUrl(e.target.value)}
          />
          <span className={styles.formHint}>必须使用 HTTPS</span>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>签名密钥 (Secret)</label>
          <input
            className={styles.formInput}
            placeholder="用于验证请求真实性（X-Zhilian-Signature）"
            value={formSecret}
            onChange={e => setFormSecret(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>订阅事件 <span className={styles.required}>*</span></label>
          <div className={styles.checkboxGrid}>
            {supportedEvents.map(ev => (
              <label key={ev.type} className={styles.checkboxItem}>
                <input
                  type="checkbox"
                  checked={formEvents.includes(ev.type)}
                  onChange={() => toggleEvent(ev.type)}
                />
                <span>
                  <code className={styles.eventCode}>{ev.type}</code>
                  <span className={styles.checkboxDesc}> — {ev.description}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel}>描述（可选）</label>
          <input
            className={styles.formInput}
            placeholder="用途说明"
            value={formDesc}
            onChange={e => setFormDesc(e.target.value)}
          />
        </div>
      </ZModal>

      {/* Delivery History Modal */}
      <ZModal
        open={!!deliveryModal}
        title={deliveryModal ? `投递历史 — ${deliveryModal.endpoint_url.slice(0, 50)}` : ''}
        onClose={() => setDeliveryModal(null)}
        footer={<ZButton onClick={() => setDeliveryModal(null)}>关闭</ZButton>}
      >
        {deliveryLoading ? (
          <ZSkeleton height={200} />
        ) : (
          <>
            <div className={styles.deliSummary}>
              {Object.entries(deliSummary).map(([status, cnt]) => (
                <div key={status} className={styles.deliStat}>
                  <ZBadge type={STATUS_BADGE[status] || 'neutral'} text={status} />
                  <span className={styles.deliCnt}>{cnt}</span>
                </div>
              ))}
            </div>
            {deliveries.length > 0 ? (
              <ZTable columns={deliveryColumns} data={deliveries} rowKey="id" />
            ) : (
              <ZEmpty text="暂无投递记录" />
            )}
          </>
        )}
      </ZModal>
    </div>
  );
};

export default WebhookManagementPage;
