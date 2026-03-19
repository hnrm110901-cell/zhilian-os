/**
 * 总部财务概览页
 * 路由：/hq/finance
 * 数据：GET /api/v1/fct/dashboard?store_id=&year=&month=
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  ZCard, ZKpi, ZButton, ZSkeleton, ZEmpty, ZSelect,
} from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './Finance.module.css';

interface StoreOption { value: string; label: string; }

interface FctDashboard {
  cash_flow?: {
    net_7d_yuan?:       number;
    net_7d?:            number;
  };
  tax?: {
    total_tax_yuan?:    number;
    total_tax?:         number;
    monthly_revenue?:   number;
    monthly_revenue_yuan?: number;
  };
  budget?: {
    overall?: {
      actual_yuan?:     number;
      actual?:          number;
      budget_yuan?:     number;
      budget?:          number;
      execution_pct?:   number;
    };
  };
}

// ¥ helper: prefer _yuan field, fallback to fen÷100
const y = (yuan?: number, fen?: number) =>
  yuan != null ? yuan : fen != null ? fen / 100 : null;

export default function HQFinance() {
  const [storeId,  setStoreId]  = useState<string>('');
  const [stores,   setStores]   = useState<StoreOption[]>([]);
  const [data,     setData]     = useState<FctDashboard | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  // Load store list from BFF hq
  useEffect(() => {
    apiClient.get('/api/v1/bff/hq').then(resp => {
      const ranking = resp.stores_health_ranking ?? [];
      if (ranking.length > 0) {
        const opts: StoreOption[] = ranking.map((s: any) => ({
          value: s.store_id,
          label: s.store_name || s.store_id,
        }));
        setStores(opts);
        setStoreId(opts[0].value);
      }
    }).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.get(`/api/v1/fct/${storeId}/dashboard`);
      setData(resp);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '数据加载失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  const net7d    = y(data?.cash_flow?.net_7d_yuan, data?.cash_flow?.net_7d);
  const totalTax = y(data?.tax?.total_tax_yuan, data?.tax?.total_tax);
  const revenue  = y(data?.tax?.monthly_revenue_yuan, data?.tax?.monthly_revenue);
  const actual   = y(data?.budget?.overall?.actual_yuan, data?.budget?.overall?.actual);
  const budget   = y(data?.budget?.overall?.budget_yuan, data?.budget?.overall?.budget);
  const execPct  = data?.budget?.overall?.execution_pct;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>财务概览</div>
        <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
      </div>

      <div className={styles.body}>
        {/* Store selector */}
        <div className={styles.storeBar}>
          <span className={styles.storeLabel}>门店：</span>
          <ZSelect
            value={storeId}
            onChange={(v) => setStoreId(String(v))}
            options={stores}
          />
        </div>

        {loading ? (
          <ZSkeleton rows={6} />
        ) : error ? (
          <ZEmpty icon="⚠️" title="加载失败" description={error} action={<ZButton size="sm" onClick={load}>重试</ZButton>} />
        ) : !data ? null : (
          <>
            {/* KPI grid */}
            <div className={styles.kpiGrid}>
              <ZCard>
                <ZKpi
                  value={net7d != null ? `¥${net7d.toLocaleString()}` : '—'}
                  label="近7日净现金流"
                  size="lg"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={revenue != null ? `¥${revenue.toLocaleString()}` : '—'}
                  label="本月营业额"
                  size="lg"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={totalTax != null ? `¥${totalTax.toLocaleString()}` : '—'}
                  label="应缴税额"
                  size="lg"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={execPct != null ? `${execPct.toFixed(1)}%` : '—'}
                  label="预算执行率"
                  size="lg"
                />
              </ZCard>
            </div>

            {/* Budget detail */}
            {data.budget?.overall && (
              <ZCard subtitle="预算执行详情">
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>实际支出</span>
                  <span className={styles.metaValue}>
                    {actual != null ? `¥${actual.toLocaleString()}` : '—'}
                  </span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>预算额</span>
                  <span className={styles.metaValue}>
                    {budget != null ? `¥${budget.toLocaleString()}` : '—'}
                  </span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>执行率</span>
                  <span className={execPct != null && execPct <= 100 ? styles.metaAccent : styles.metaValue}>
                    {execPct != null ? `${execPct.toFixed(1)}%` : '—'}
                  </span>
                </div>
              </ZCard>
            )}
          </>
        )}
      </div>
    </div>
  );
}
