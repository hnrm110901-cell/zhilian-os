import React, { useState, useCallback, useEffect } from 'react';
import { DatePicker } from 'antd';
import { FilePdfOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZSelect, ZTable,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';
import styles from './MonthlyReportPage.module.css';

const MonthlyReportPage: React.FC = () => {
  const [loading, setLoading]             = useState(false);
  const [stores, setStores]               = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState(localStorage.getItem('store_id') || 'STORE001');
  const [selectedMonth, setSelectedMonth] = useState(dayjs().subtract(1, 'month'));
  const [report, setReport]               = useState<any>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err: any) {
      handleApiError(err, '加载门店列表失败');
    }
  }, []);

  const loadReport = useCallback(async () => {
    if (!selectedStore) return;
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/reports/monthly/${selectedStore}`, {
        params: { year: selectedMonth.year(), month: selectedMonth.month() + 1 },
      });
      setReport(res.data);
    } catch (err: any) {
      handleApiError(err, '加载月报失败');
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [selectedStore, selectedMonth]);

  useEffect(() => { loadStores(); }, [loadStores]);
  useEffect(() => { loadReport(); }, [loadReport]);

  const handlePrintPdf = () => {
    const year = selectedMonth.year();
    const month = selectedMonth.month() + 1;
    window.open(
      `/api/v1/reports/monthly/${selectedStore}/html?year=${year}&month=${month}`,
      '_blank'
    );
  };

  const summary = report?.executive_summary;
  const chart   = report?.weekly_trend_chart;
  const top3    = report?.top3_decisions || [];

  const storeOptions = stores.length > 0
    ? stores.map((s: any) => ({ value: s.store_id || s.id, label: s.name || s.store_id || s.id }))
    : [{ value: 'STORE001', label: 'STORE001' }];

  const statusBadgeType = (s: string): 'critical' | 'warning' | 'success' =>
    s === 'critical' ? 'critical' : s === 'warning' ? 'warning' : 'success';

  const statusLabel = (s: string) =>
    s === 'critical' ? '超标' : s === 'warning' ? '偏高' : '正常';

  const statusColor = (s: string) =>
    s === 'critical' ? '#cf1322' : s === 'warning' ? '#d46b08' : '#389e0d';

  const chartOption = chart ? {
    tooltip: { trigger: 'axis' },
    legend: { data: ['成本率%', '营业额¥'], bottom: 0 },
    xAxis: { type: 'category', data: chart.x_axis },
    yAxis: [
      { type: 'value', name: '成本率%', axisLabel: { formatter: '{value}%' } },
      { type: 'value', name: '营业额¥', axisLabel: { formatter: (v: number) => `¥${(v / 10000).toFixed(0)}万` } },
    ],
    series: [
      {
        name: '成本率%',
        type: 'line',
        smooth: true,
        data: chart.cost_rate_data,
        yAxisIndex: 0,
        itemStyle: { color: '#C53030' },
        markLine: {
          data: [{ yAxis: 33, lineStyle: { color: '#faad14', type: 'dashed' }, label: { formatter: '警戒线33%' } }],
        },
      },
      {
        name: '营业额¥',
        type: 'bar',
        data: chart.revenue_data,
        yAxisIndex: 1,
        itemStyle: { color: '#0AAF9A', opacity: 0.4 },
      },
    ],
  } : null;

  const top3Columns: ZTableColumn<any>[] = [
    {
      key:    'rank',
      title:  '#',
      width:  48,
      align:  'center',
      render: (_: any, __: any, i: number) => (
        <ZBadge
          type={i === 0 ? 'critical' : i === 1 ? 'warning' : 'info'}
          text={`#${i + 1}`}
        />
      ),
    },
    { key: 'action', title: '执行动作' },
    {
      key:    'expected_saving_yuan',
      title:  '预期节省¥',
      align:  'right',
      render: (v: number) => (
        <strong style={{ color: '#389e0d' }}>
          ¥{(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
        </strong>
      ),
    },
    {
      key:    'outcome',
      title:  '实际结果',
      render: (v: string) => v || <span style={{ color: 'var(--text-secondary)' }}>待统计</span>,
    },
  ];

  return (
    <div className={styles.page}>
      {/* 控制栏 */}
      <div className={styles.toolbar}>
        <ZSelect
          value={selectedStore}
          options={storeOptions}
          onChange={(v) => setSelectedStore(v as string)}
          style={{ width: 160 }}
        />
        <DatePicker
          picker="month"
          value={selectedMonth}
          onChange={(d) => d && setSelectedMonth(d)}
          disabledDate={(d) => d && d.isAfter(dayjs())}
          style={{ width: 120 }}
        />
        <ZButton icon={<ReloadOutlined />} onClick={loadReport} disabled={loading}>刷新</ZButton>
        <ZButton
          variant="primary"
          icon={<FilePdfOutlined />}
          onClick={handlePrintPdf}
          disabled={!report}
        >
          打印 / 导出 PDF
        </ZButton>
      </div>

      {/* 主体 */}
      {loading ? (
        <ZSkeleton rows={10} block />
      ) : !report ? (
        <div className={styles.alertInfo}>暂无报告数据，请选择门店和月份后加载</div>
      ) : (
        <>
          {/* 状态横幅 */}
          {summary && (
            <div className={`${styles.alertBanner} ${styles[`alert_${summary.cost_rate_status}`]}`}>
              <strong>{summary.headline}</strong>
              <span style={{ marginLeft: 8, opacity: 0.8 }}>报告周期：{summary.period}</span>
            </div>
          )}

          {/* KPI 卡片 */}
          {summary && (
            <div className={styles.kpiGrid}>
              <ZCard>
                <ZKpi
                  value={`¥${(summary.revenue_yuan || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`}
                  label="月度营业额"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={(summary.actual_cost_pct ?? 0).toFixed(1)}
                  unit="%"
                  label="食材成本率"
                />
                <div style={{ marginTop: 6 }}>
                  <ZBadge
                    type={statusBadgeType(summary.cost_rate_status)}
                    text={statusLabel(summary.cost_rate_status)}
                  />
                </div>
              </ZCard>
              <ZCard>
                <ZKpi
                  value={`¥${(summary.waste_cost_yuan ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`}
                  label="损耗金额"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={(summary.decision_adoption_pct ?? 0).toFixed(1)}
                  unit="%"
                  label="决策采纳率"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={`¥${(summary.total_saving_yuan ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`}
                  label="决策节省¥"
                />
              </ZCard>
              <ZCard>
                <ZKpi
                  value={`${summary.decisions_approved ?? 0}/${summary.decisions_total ?? 0}`}
                  label="审批决策"
                />
              </ZCard>
            </div>
          )}

          {/* 经营叙事 */}
          {summary?.narrative && (
            <ZCard style={{ marginBottom: 14, background: 'rgba(26,122,82,0.08)', borderColor: 'rgba(26,122,82,0.3)' }}>
              <p style={{ fontSize: 13, lineHeight: 1.8, margin: 0, color: '#389e0d' }}>
                {summary.narrative}
              </p>
            </ZCard>
          )}

          {/* 趋势图 */}
          {chartOption && (
            <ZCard title="周成本率趋势" style={{ marginBottom: 14 }}>
              <ReactECharts option={chartOption} style={{ height: 260 }} />
            </ZCard>
          )}

          {/* Top3 决策 */}
          {top3.length > 0 && (
            <ZCard title="本月 Top3 节省决策">
              <ZTable
                columns={top3Columns}
                data={top3}
                rowKey={(_: any, i: number) => String(i)}
                emptyText="暂无决策数据"
              />
            </ZCard>
          )}
        </>
      )}
    </div>
  );
};

export default MonthlyReportPage;
