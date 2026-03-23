/**
 * 移动盘点
 * 路由：/sm/stocktake
 * 数据：/api/v1/stocktake/*
 */
import React, { useEffect, useState, useCallback } from 'react';
import { message } from 'antd';
import { ZCard, ZButton, ZBadge, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './MobileStocktake.module.css';

interface CountEntry {
  id: string;
  ingredient_name: string;
  system_qty: number;
  counted_qty: number | null;
  unit: string;
  location: string;
}

interface StocktakeSession {
  id: string;
  name: string;
  scope: string;
  status: string;
  created_at: string;
  total_items: number;
  counted_items: number;
  entries?: CountEntry[];
}

interface VarianceSummary {
  total_items: number;
  variance_count: number;
  impact_yuan: number;
}

const STORE_ID = localStorage.getItem('store_id') || '';

const SCOPE_OPTIONS = [
  { key: 'full', label: '全盘' },
  { key: 'category', label: '分类盘' },
  { key: 'spot', label: '抽盘' },
];

const STATUS_MAP: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'critical' }> = {
  draft: { label: '草稿', type: 'info' },
  in_progress: { label: '进行中', type: 'warning' },
  pending_review: { label: '待审核', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  cancelled: { label: '已取消', type: 'critical' },
};

export default function MobileStocktake() {
  const [sessions, setSessions] = useState<StocktakeSession[]>([]);
  const [loading, setLoading] = useState(true);

  /* 创建盘点 */
  const [showCreate, setShowCreate] = useState(false);
  const [scope, setScope] = useState('full');
  const [category, setCategory] = useState('');
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);
  const [submitting, setSubmitting] = useState(false);

  /* 盘点计数 */
  const [activeSession, setActiveSession] = useState<StocktakeSession | null>(null);
  const [entries, setEntries] = useState<CountEntry[]>([]);
  const [variance, setVariance] = useState<VarianceSummary | null>(null);

  /* 加载盘点列表 */
  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(`/api/v1/stocktake/sessions?store_id=${STORE_ID}`);
      setSessions(resp.sessions ?? []);
    } catch {
      message.error('加载盘点列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  /* 加载分类列表 */
  const loadCategories = async () => {
    try {
      const resp = await apiClient.get(`/api/v1/stocktake/categories?store_id=${STORE_ID}`);
      setCategories(resp.categories ?? []);
    } catch {
      message.error('加载分类失败');
    }
  };

  /* 创建盘点会话 */
  const handleCreate = async () => {
    if (scope === 'category' && !category) {
      message.error('请选择盘点分类');
      return;
    }
    setSubmitting(true);
    try {
      const resp = await apiClient.post('/api/v1/stocktake/sessions', {
        store_id: STORE_ID,
        scope,
        category_id: scope === 'category' ? category : undefined,
      });
      message.success('盘点已创建');
      setShowCreate(false);
      if (resp.session) {
        openSession(resp.session);
      } else {
        loadSessions();
      }
    } catch {
      message.error('创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  /* 打开盘点会话 */
  const openSession = async (session: StocktakeSession) => {
    try {
      const resp = await apiClient.get(`/api/v1/stocktake/sessions/${session.id}`);
      const detail = resp.session ?? { ...session, entries: [] };
      setActiveSession(detail);
      setEntries((detail.entries ?? []).map((e: CountEntry) => ({
        ...e,
        counted_qty: e.counted_qty ?? null,
      })));
      computeVariance(detail.entries ?? []);
    } catch {
      message.error('加载盘点详情失败');
    }
  };

  /* 更新实盘数量 */
  const updateCountedQty = (id: string, qty: number) => {
    const updated = entries.map(e => e.id === id ? { ...e, counted_qty: qty } : e);
    setEntries(updated);
    computeVariance(updated);
  };

  /* 保存单项 */
  const saveEntry = async (entry: CountEntry) => {
    if (!activeSession || entry.counted_qty === null) return;
    try {
      await apiClient.put(`/api/v1/stocktake/sessions/${activeSession.id}/entries/${entry.id}`, {
        counted_qty: entry.counted_qty,
      });
    } catch {
      message.error('保存失败');
    }
  };

  /* 计算差异汇总 */
  const computeVariance = (items: CountEntry[]) => {
    const counted = items.filter(e => e.counted_qty !== null);
    const withVariance = counted.filter(e => {
      if (e.system_qty === 0) return e.counted_qty !== 0;
      const deviation = Math.abs((e.counted_qty! - e.system_qty) / e.system_qty);
      return deviation > 0.05;
    });
    // 差异金额需要后端提供，此处先用计数代替
    setVariance({
      total_items: items.length,
      variance_count: withVariance.length,
      impact_yuan: 0,
    });
  };

  /* 获取差异金额（从后端） */
  const loadVarianceSummary = async () => {
    if (!activeSession) return;
    try {
      const resp = await apiClient.get(`/api/v1/stocktake/sessions/${activeSession.id}/variance`);
      if (resp.summary) {
        setVariance(resp.summary);
      }
    } catch {
      // 降级：使用前端计算的差异
    }
  };

  /* 提交审核 */
  const handleSubmitReview = async () => {
    if (!activeSession) return;
    const uncounted = entries.filter(e => e.counted_qty === null);
    if (uncounted.length > 0) {
      message.error(`还有 ${uncounted.length} 项未盘点，请完成后再提交`);
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post(`/api/v1/stocktake/sessions/${activeSession.id}/submit`);
      message.success('已提交审核');
      setActiveSession(null);
      loadSessions();
    } catch {
      message.error('提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  /* 差异指示器 */
  const getVarianceIndicator = (entry: CountEntry) => {
    if (entry.counted_qty === null) return null;
    if (entry.system_qty === 0) {
      return entry.counted_qty === 0
        ? <span className={styles.varianceMatch}>一致</span>
        : <span className={styles.varianceDeviation}>有差异</span>;
    }
    const deviation = Math.abs((entry.counted_qty - entry.system_qty) / entry.system_qty);
    if (deviation <= 0.05) {
      return <span className={styles.varianceMatch}>一致</span>;
    }
    return <span className={styles.varianceDeviation}>{(deviation * 100).toFixed(1)}%</span>;
  };

  const scopeLabel = (s: string) => SCOPE_OPTIONS.find(o => o.key === s)?.label ?? s;

  /* 创建盘点视图 */
  if (showCreate) {
    return (
      <div className={styles.overlay}>
        <div className={styles.overlayHeader}>
          <button className={styles.backBtn} onClick={() => setShowCreate(false)}>{'<'}</button>
          <span className={styles.overlayTitle}>新建盘点</span>
        </div>

        <div className={styles.formSection}>
          <div className={styles.field}>
            <label className={styles.label}>盘点范围 <span className={styles.required}>*</span></label>
            <div className={styles.scopeGrid}>
              {SCOPE_OPTIONS.map(opt => (
                <button
                  key={opt.key}
                  className={`${styles.scopeBtn} ${scope === opt.key ? styles.scopeActive : ''}`}
                  onClick={() => setScope(opt.key)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {scope === 'category' && (
            <div className={styles.field}>
              <label className={styles.label}>选择分类 <span className={styles.required}>*</span></label>
              <select
                className={styles.select}
                value={category}
                onChange={e => setCategory(e.target.value)}
              >
                <option value="">请选择</option>
                {categories.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className={styles.bottomBar}>
          <button className={styles.secondaryBtn} onClick={() => setShowCreate(false)}>取消</button>
          <button
            className={styles.submitBtn}
            onClick={handleCreate}
            disabled={submitting}
          >
            {submitting ? '创建中...' : '开始盘点'}
          </button>
        </div>
      </div>
    );
  }

  /* 盘点计数视图 */
  if (activeSession) {
    const statusInfo = STATUS_MAP[activeSession.status] ?? { label: activeSession.status, type: 'info' as const };
    const isReadonly = activeSession.status === 'pending_review' || activeSession.status === 'completed';
    return (
      <div className={styles.overlay}>
        <div className={styles.overlayHeader}>
          <button className={styles.backBtn} onClick={() => { setActiveSession(null); loadSessions(); }}>{'<'}</button>
          <span className={styles.overlayTitle}>{activeSession.name || '盘点详情'}</span>
          <ZBadge type={statusInfo.type} text={statusInfo.label} />
        </div>

        {/* 差异汇总 */}
        {variance && (
          <div className={styles.summaryCard}>
            <div className={styles.sectionTitle}>盘点汇总</div>
            <div className={styles.summaryGrid}>
              <div className={styles.summaryItem}>
                <span className={styles.summaryValue}>{variance.total_items}</span>
                <span className={styles.summaryLabel}>总项数</span>
              </div>
              <div className={styles.summaryItem}>
                <span className={variance.variance_count > 0 ? styles.summaryValueError : styles.summaryValue}>
                  {variance.variance_count}
                </span>
                <span className={styles.summaryLabel}>差异项</span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryValueAccent}>
                  ¥{variance.impact_yuan.toFixed(2)}
                </span>
                <span className={styles.summaryLabel}>差异金额</span>
              </div>
            </div>
          </div>
        )}

        {/* 盘点条目 */}
        <div className={styles.sectionTitle}>盘点明细（{scopeLabel(activeSession.scope)}）</div>
        {entries.length === 0 ? (
          <div className={styles.emptyWrap}>
            <ZEmpty title="暂无盘点项" description="该盘点会话没有需要盘点的食材" />
          </div>
        ) : (
          <div className={styles.countList}>
            {entries.map(entry => (
              <div key={entry.id} className={styles.countItem}>
                <div className={styles.countItemHeader}>
                  <span className={styles.countItemName}>{entry.ingredient_name}</span>
                  <span className={styles.countItemLocation}>{entry.location}</span>
                </div>
                <div className={styles.countItemBody}>
                  <div className={styles.countField}>
                    <span className={styles.countLabel}>系统数量</span>
                    <div className={styles.countSystemQty}>{entry.system_qty}</div>
                  </div>
                  <span className={styles.countUnit}>{entry.unit}</span>
                  <div className={styles.countField}>
                    <span className={styles.countLabel}>实盘数量</span>
                    {isReadonly ? (
                      <div className={styles.countSystemQty}>{entry.counted_qty ?? '--'}</div>
                    ) : (
                      <input
                        className={styles.countInput}
                        type="number"
                        min="0"
                        step="0.1"
                        placeholder="输入"
                        value={entry.counted_qty ?? ''}
                        onChange={e => {
                          const val = e.target.value === '' ? null : Number(e.target.value);
                          updateCountedQty(entry.id, val as number);
                        }}
                        onBlur={() => saveEntry(entry)}
                      />
                    )}
                  </div>
                  {getVarianceIndicator(entry)}
                </div>
              </div>
            ))}
          </div>
        )}

        {!isReadonly && (
          <div className={styles.bottomBar}>
            <button className={styles.secondaryBtn} onClick={loadVarianceSummary}>刷新汇总</button>
            <button
              className={styles.submitBtn}
              onClick={handleSubmitReview}
              disabled={submitting}
            >
              {submitting ? '提交中...' : '提交审核'}
            </button>
          </div>
        )}
      </div>
    );
  }

  /* 盘点列表视图 */
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>移动盘点</span>
        <button className={styles.createBtn} onClick={() => { setShowCreate(true); loadCategories(); }}>
          新建盘点
        </button>
      </div>

      {loading ? (
        <div className={styles.skeleton} />
      ) : sessions.length === 0 ? (
        <div className={styles.emptyWrap}>
          <ZEmpty title="暂无盘点记录" description="点击右上角新建盘点" />
        </div>
      ) : (
        <div className={styles.sessionList}>
          {sessions.map(session => {
            const statusInfo = STATUS_MAP[session.status] ?? { label: session.status, type: 'info' as const };
            return (
              <div key={session.id} className={styles.sessionCard} onClick={() => openSession(session)}>
                <div className={styles.sessionCardHeader}>
                  <span className={styles.sessionName}>{session.name}</span>
                  <ZBadge type={statusInfo.type} text={statusInfo.label} />
                </div>
                <div className={styles.sessionCardBody}>
                  <span className={styles.sessionScope}>{scopeLabel(session.scope)}</span>
                  <span className={styles.sessionProgress}>
                    {session.counted_items}/{session.total_items} 已盘
                  </span>
                </div>
                <div className={styles.sessionDate}>{session.created_at}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
