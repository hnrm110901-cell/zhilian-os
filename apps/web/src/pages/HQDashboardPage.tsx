import React, { useState, useEffect, useCallback } from 'react';
import { DatePicker } from 'antd';
import {
  ShopOutlined, ReloadOutlined, WarningOutlined,
  CheckCircleOutlined, HeartOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZTable, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import styles from './HQDashboardPage.module.css';

const DIM_LABEL: Record<string, string> = {
  revenue_completion: '营收完成率',
  table_turnover:     '翻台率',
  cost_rate:          '成本率',
  complaint_rate:     '客诉率',
  staff_efficiency:   '人效',
};

// ── Column definitions ────────────────────────────────────────────────────────

const storeColumns: ZTableColumn<any>[] = [
  {
    key: '_rank',
    title: '#',
    width: 48,
    render: (_: any, __: any, idx: number) => idx + 1,
  },
  { key: 'store_name', title: '门店' },
  {
    key: 'revenue',
    title: '昨日营收',
    align: 'right',
    render: (v: number) => `¥${(v / 100).toFixed(0)}`,
  },
  { key: 'orders', title: '订单数', align: 'right' },
  {
    key: 'health_score',
    title: '健康分',
    width: 120,
    render: (v: number) => {
      const pct = Math.min(100, Math.round(v || 0));
      const color = pct >= 80 ? 'var(--green)' : pct >= 60 ? '#faad14' : 'var(--red)';
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ flex: 1, height: 5, background: '#f0f0f0', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
          </div>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', minWidth: 24 }}>{pct}</span>
        </div>
      );
    },
  },
  {
    key: 'pending_approvals',
    title: '待审批',
    align: 'center',
    width: 72,
    render: (v: number) => v > 0
      ? <ZBadge type="warning" text={String(v)} />
      : <CheckCircleOutlined style={{ color: '#1A7A52' }} />,
  },
  {
    key: 'has_alert',
    title: '状态',
    width: 80,
    align: 'center',
    render: (v: boolean) => v
      ? <ZBadge type="critical" text="需关注" />
      : <ZBadge type="success" text="正常" />,
  },
];

const healthColumns: ZTableColumn<any>[] = [
  {
    key: 'rank',
    title: '#',
    width: 48,
    render: (v: number) => (
      <span style={{
        fontWeight: 700,
        color: v === 1 ? '#f5a623' : v === 2 ? '#9b9b9b' : v === 3 ? '#cd7f32' : 'var(--text-secondary)',
      }}>{v}</span>
    ),
  },
  { key: 'store_name', title: '门店' },
  {
    key: 'score',
    title: '综合健康分',
    width: 140,
    render: (v: number, row: any) => {
      const pct = Math.min(100, Math.round(v || 0));
      const color = row.level === 'excellent' ? '#1A7A52'
        : row.level === 'good'    ? '#0AAF9A'
        : row.level === 'warning' ? '#faad14'
        : '#C53030';
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 80, height: 5, background: '#f0f0f0', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
          </div>
          <strong style={{ fontSize: 13 }}>{pct}</strong>
        </div>
      );
    },
  },
  {
    key: 'level_label',
    title: '状态',
    width: 80,
    align: 'center',
    render: (v: string, row: any) => {
      const type =
        row.level === 'excellent' ? 'success'
        : row.level === 'good'    ? 'info'
        : row.level === 'warning' ? 'warning'
        : 'critical';
      return <ZBadge type={type as any} text={v} />;
    },
  },
  {
    key: 'weakest_label',
    title: '最弱维度',
    render: (v: string | null) => v
      ? <ZBadge type="warning" text={v} />
      : <CheckCircleOutlined style={{ color: '#1A7A52' }} />,
  },
  {
    key: 'revenue_yuan',
    title: '营收',
    align: 'right',
    render: (v: number) => `¥${(v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`,
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

const HQDashboardPage: React.FC = () => {
  const [loading, setLoading]           = useState(false);
  const [healthLoading, setHealthLoading] = useState(false);
  const [targetDate, setTargetDate]     = useState<Dayjs>(dayjs().subtract(1, 'day'));
  const [data, setData]                 = useState<any>(null);
  const [healthData, setHealthData]     = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/hq/dashboard', {
        params: { target_date: targetDate.format('YYYY-MM-DD') },
      });
      setData(res);
    } catch (err: any) {
      handleApiError(err, '加载总部看板失败');
    } finally {
      setLoading(false);
    }
  }, [targetDate]);

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const res = await apiClient.get('/api/v1/stores/health', {
        params: { target_date: targetDate.format('YYYY-MM-DD') },
      });
      setHealthData(res.data);
    } catch {
      // 健康评分非核心，静默降级
    } finally {
      setHealthLoading(false);
    }
  }, [targetDate]);

  useEffect(() => {
    load();
    loadHealth();
  }, [load, loadHealth]);

  const summary      = data?.summary      || {};
  const storeMetrics = data?.store_metrics || [];
  const alertStores  = data?.alert_stores  || [];
  const healthStores = healthData?.stores  || [];
  const healthSummary = healthData?.summary || {};

  const top10 = storeMetrics.slice(0, 10);
  const barOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: top10.map((s: any) => s.store_name), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', name: '营收（分）' },
    series: [{
      type: 'bar',
      data: top10.map((s: any) => s.revenue),
      itemStyle: { color: 'var(--accent)' },
    }],
  };

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <h2 className={styles.pageTitle}><ShopOutlined /> 总部跨店看板</h2>
        <div className={styles.headerActions}>
          <DatePicker
            value={targetDate}
            onChange={(v) => v && setTargetDate(v)}
            allowClear={false}
            disabledDate={(d) => d.isAfter(dayjs())}
          />
          <ZButton icon={<ReloadOutlined />} onClick={() => { load(); loadHealth(); }}>刷新</ZButton>
        </div>
      </div>

      {/* 预警 Banner */}
      {alertStores.length > 0 && (
        <div className={`${styles.alertBar} ${styles.alertWarning}`} style={{ marginBottom: 16 }}>
          <WarningOutlined style={{ marginRight: 8 }} />
          <strong>{alertStores.length} 家门店需要关注：</strong>
          {alertStores.map((s: any) => `${s.store_name}（待审批 ${s.pending_approvals} 项）`).join('、')}
        </div>
      )}

      {/* KPI 概览 */}
      {loading ? (
        <ZSkeleton rows={2} block style={{ marginBottom: 14 }} />
      ) : (
        <div className={styles.kpiGrid} style={{ marginBottom: 14 }}>
          <ZCard>
            <ZKpi value={summary.total_stores || 0} unit="家" label="门店总数" />
          </ZCard>
          <ZCard>
            <ZKpi
              value={`¥${((summary.total_revenue || 0) / 100).toFixed(0)}`}
              label="昨日总营收"
            />
          </ZCard>
          <ZCard>
            <ZKpi value={summary.total_orders || 0} unit="单" label="昨日总订单" />
          </ZCard>
          <ZCard>
            <ZKpi
              value={summary.total_pending_approvals || 0}
              unit="项"
              label="待审批决策"
            />
          </ZCard>
        </div>
      )}

      {/* 营收柱状图 + 门店列表 */}
      {loading ? (
        <ZSkeleton rows={6} block style={{ marginBottom: 14 }} />
      ) : (
        <div className={styles.chartRow} style={{ marginBottom: 14 }}>
          <ZCard title="营收排名 TOP10">
            <ReactECharts option={barOption} style={{ height: 280 }} />
          </ZCard>
          <ZCard title={`门店列表（${storeMetrics.length} 家）`}>
            <ZTable
              columns={storeColumns}
              data={storeMetrics}
              rowKey="store_id"
              emptyText="暂无门店数据"
            />
          </ZCard>
        </div>
      )}

      {/* 门店健康度排名 */}
      <ZCard title={
        <span><HeartOutlined style={{ color: '#1A7A52', marginRight: 6 }} />门店健康度排名</span>
      }>
        <div className={styles.healthSummaryTags} style={{ marginBottom: 12 }}>
          {healthSummary.critical  > 0 && <ZBadge type="critical" text={`危险 ${healthSummary.critical} 家`} />}
          {healthSummary.warning   > 0 && <ZBadge type="warning"  text={`需关注 ${healthSummary.warning} 家`} />}
          {healthSummary.good      > 0 && <ZBadge type="info"     text={`良好 ${healthSummary.good} 家`} />}
          {healthSummary.excellent > 0 && <ZBadge type="success"  text={`优秀 ${healthSummary.excellent} 家`} />}
        </div>
        {healthLoading ? (
          <ZSkeleton rows={4} block />
        ) : healthStores.length === 0 ? (
          <ZEmpty description="暂无健康评分数据" />
        ) : (
          <ZTable
            columns={healthColumns}
            data={healthStores}
            rowKey="store_id"
            emptyText="暂无数据"
          />
        )}
      </ZCard>
    </div>
  );
};

export default HQDashboardPage;
