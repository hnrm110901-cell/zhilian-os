/**
 * 预订数据分析仪表板 — 8维度深度分析
 * 总览KPI / 趋势折线 / 渠道ROI / 高峰热力图 / 客户洞察 / No-Show风险 / 营收影响 / 取消分析
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Select, DatePicker, Tabs, Tag, Table, Tooltip, Spin, Empty, message } from 'antd';
import {
  BarChartOutlined, LineChartOutlined, HeatMapOutlined, TeamOutlined,
  WarningOutlined, DollarOutlined, CloseCircleOutlined, RiseOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { apiClient } from '../utils/apiClient';
import styles from './ReservationAnalyticsPage.module.css';

const { RangePicker } = DatePicker;

interface Overview {
  total_reservations: number;
  avg_daily: number;
  total_guests: number;
  avg_party_size: number;
  confirmation_rate: number;
  cancellation_rate: number;
  no_show_rate: number;
  completion_rate: number;
  status_breakdown: Record<string, number>;
  type_distribution: Record<string, number>;
}

interface ChannelData {
  channel: string;
  count: number;
  commission_yuan: number;
  conversion_rate: number;
  percentage: number;
  cost_per_reservation: number;
}

interface TrendDay {
  date: string;
  total: number;
  confirmed: number;
  cancelled: number;
  no_show: number;
  completed: number;
  guests: number;
}

interface HeatmapPoint {
  day: number;
  day_name: string;
  hour: number;
  count: number;
}

interface RiskItem {
  reservation_id: string;
  customer_name: string;
  customer_phone: string;
  party_size: number;
  time: string;
  risk_score: number;
  risk_level: string;
  history_visits: number;
  history_no_shows: number;
  suggestion: string;
}

const CHANNEL_NAMES: Record<string, string> = {
  meituan: '美团', dianping: '大众点评', douyin: '抖音', wechat: '微信',
  phone: '电话', walk_in: '到店', referral: '推荐', yiding: '易订',
  mini_program: '小程序', other: '其他', xiaohongshu: '小红书',
};

const ReservationAnalyticsPage: React.FC = () => {
  const [storeId, setStoreId] = useState('S001');
  const [days, setDays] = useState(30);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [loading, setLoading] = useState(false);

  // Data states
  const [overview, setOverview] = useState<Overview | null>(null);
  const [channels, setChannels] = useState<ChannelData[]>([]);
  const [trend, setTrend] = useState<TrendDay[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapPoint[]>([]);
  const [heatmapPeak, setHeatmapPeak] = useState<HeatmapPoint | null>(null);
  const [customerData, setCustomerData] = useState<any>(null);
  const [riskData, setRiskData] = useState<{ reservations: RiskItem[]; high_risk_count: number } | null>(null);
  const [revenueData, setRevenueData] = useState<any>(null);
  const [cancelData, setCancelData] = useState<any>(null);

  const getParams = useCallback(() => {
    if (dateRange) {
      return `store_id=${storeId}&start=${dateRange[0].format('YYYY-MM-DD')}&end=${dateRange[1].format('YYYY-MM-DD')}`;
    }
    return `store_id=${storeId}&days=${days}`;
  }, [storeId, days, dateRange]);

  const loadData = useCallback(async () => {
    setLoading(true);
    const params = getParams();
    try {
      const [ov, ch, tr, hm, cu, rv, ca] = await Promise.allSettled([
        apiClient.get<any>(`/reservation-analytics/overview?${params}`),
        apiClient.get<any>(`/reservation-analytics/channel-roi?${params}`),
        apiClient.get<any>(`/reservation-analytics/daily-trend?store_id=${storeId}&days=${days}`),
        apiClient.get<any>(`/reservation-analytics/peak-heatmap?${params}`),
        apiClient.get<any>(`/reservation-analytics/customer-insights?${params}`),
        apiClient.get<any>(`/reservation-analytics/revenue-impact?${params}`),
        apiClient.get<any>(`/reservation-analytics/cancellation-deep?${params}`),
      ]);

      if (ov.status === 'fulfilled') setOverview(ov.value);
      if (ch.status === 'fulfilled') setChannels(ch.value.channels || []);
      if (tr.status === 'fulfilled') setTrend(tr.value.trend || []);
      if (hm.status === 'fulfilled') {
        setHeatmap(hm.value.heatmap || []);
        setHeatmapPeak(hm.value.peak);
      }
      if (cu.status === 'fulfilled') setCustomerData(cu.value);
      if (rv.status === 'fulfilled') setRevenueData(rv.value);
      if (ca.status === 'fulfilled') setCancelData(ca.value);
    } catch (e: any) {
      message.error('加载分析数据失败');
    }
    // Load risk separately (different params)
    try {
      const risk = await apiClient.get<any>(`/reservation-analytics/no-show-risk?store_id=${storeId}`);
      setRiskData(risk);
    } catch {}
    setLoading(false);
  }, [getParams, storeId, days]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Trend Chart ────────────────────────────────────
  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['总预订', '已确认', '已完成', '已取消', 'No-Show'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: trend.map(t => t.date.slice(5)) },
    yAxis: { type: 'value' },
    series: [
      { name: '总预订', type: 'line', data: trend.map(t => t.total), smooth: true, lineStyle: { width: 2 } },
      { name: '已确认', type: 'line', data: trend.map(t => t.confirmed), smooth: true, lineStyle: { width: 1.5 } },
      { name: '已完成', type: 'line', data: trend.map(t => t.completed), smooth: true, color: '#52c41a' },
      { name: '已取消', type: 'line', data: trend.map(t => t.cancelled), smooth: true, color: '#ff4d4f', lineStyle: { type: 'dashed' } },
      { name: 'No-Show', type: 'line', data: trend.map(t => t.no_show), smooth: true, color: '#faad14', lineStyle: { type: 'dotted' } },
    ],
  };

  // ── Heatmap Chart ──────────────────────────────────
  const dayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`);
  const heatmapData = heatmap.map(h => [h.hour, h.day, h.count]);
  const maxCount = Math.max(...heatmap.map(h => h.count), 1);

  const heatmapOption = {
    tooltip: { formatter: (p: any) => `${dayNames[p.data[1]]} ${p.data[0]}:00 — ${p.data[2]}笔预订` },
    grid: { left: 60, right: 40, top: 10, bottom: 40 },
    xAxis: { type: 'category', data: hours, splitArea: { show: true } },
    yAxis: { type: 'category', data: dayNames },
    visualMap: { min: 0, max: maxCount, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#f0f0f0', '#ffe0cc', '#0AAF9A'] } },
    series: [{ type: 'heatmap', data: heatmapData, label: { show: false } }],
  };

  // ── Channel Bar Chart ──────────────────────────────
  const channelOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 80, right: 40, top: 10, bottom: 30 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: channels.map(c => CHANNEL_NAMES[c.channel] || c.channel) },
    series: [{
      type: 'bar',
      data: channels.map(c => c.count),
      itemStyle: { color: '#0AAF9A', borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', formatter: '{c}笔' },
    }],
  };

  // ── Cancellation Pie ───────────────────────────────
  const cancelAdvance = cancelData?.advance_distribution || {};
  const cancelPieOption = {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: Object.entries(cancelAdvance).filter(([_, v]) => (v as number) > 0).map(([k, v]) => ({ name: k, value: v })),
      label: { formatter: '{b}: {c}' },
      itemStyle: { borderRadius: 4 },
    }],
  };

  // ── Risk Table Columns ─────────────────────────────
  const riskColumns = [
    { title: '时间', dataIndex: 'time', width: 70 },
    { title: '客户', dataIndex: 'customer_name', width: 80 },
    { title: '人数', dataIndex: 'party_size', width: 60 },
    {
      title: '风险',
      dataIndex: 'risk_level',
      width: 70,
      render: (level: string) => {
        const cls = level === 'high' ? styles.riskHigh : level === 'medium' ? styles.riskMedium : styles.riskLow;
        const text = level === 'high' ? '高' : level === 'medium' ? '中' : '低';
        return <span className={cls}>{text} ({level === 'high' ? '!' : ''})</span>;
      },
    },
    { title: '分数', dataIndex: 'risk_score', width: 60 },
    { title: '历史到店', dataIndex: 'history_visits', width: 80 },
    { title: '历史No-Show', dataIndex: 'history_no_shows', width: 100 },
    { title: '建议', dataIndex: 'suggestion', ellipsis: true },
  ];

  return (
    <Spin spinning={loading}>
      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <span className={styles.title}>预订数据分析</span>
          <div className={styles.controls}>
            <Select value={storeId} onChange={setStoreId} style={{ width: 140 }}
              options={[
                { value: 'S001', label: '尝在一起' },
                { value: 'S002', label: '尚宫厨' },
                { value: 'S003', label: '最黔线' },
              ]}
            />
            <Select value={days} onChange={setDays} style={{ width: 100 }}
              options={[
                { value: 7, label: '近7天' },
                { value: 14, label: '近14天' },
                { value: 30, label: '近30天' },
                { value: 90, label: '近90天' },
              ]}
            />
            <RangePicker
              value={dateRange}
              onChange={(val) => setDateRange(val as any)}
              allowClear
              placeholder={['开始日期', '结束日期']}
            />
          </div>
        </div>

        {/* KPI Row */}
        {overview && (
          <div className={styles.kpiRow}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>总预订量</div>
              <div className={styles.kpiValue}>{overview.total_reservations}</div>
              <div className={styles.kpiSub}>日均 {overview.avg_daily} 笔</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>确认率</div>
              <div className={styles.kpiValue}>{overview.confirmation_rate}%</div>
              <div className={styles.kpiSub}>完成率 {overview.completion_rate}%</div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>取消率</div>
              <div className={`${styles.kpiValue} ${overview.cancellation_rate > 15 ? styles.kpiDown : ''}`}>
                {overview.cancellation_rate}%
              </div>
              <div className={styles.kpiSub}>
                {overview.status_breakdown?.cancelled || 0} 笔取消
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>No-Show率</div>
              <div className={`${styles.kpiValue} ${overview.no_show_rate > 10 ? styles.kpiDown : ''}`}>
                {overview.no_show_rate}%
              </div>
              <div className={styles.kpiSub}>
                {overview.status_breakdown?.no_show || 0} 笔未到
              </div>
            </div>
            <div className={styles.kpiCard}>
              <div className={styles.kpiLabel}>平均桌位</div>
              <div className={styles.kpiValue}>{overview.avg_party_size}</div>
              <div className={styles.kpiSub}>总客流 {overview.total_guests} 人</div>
            </div>
          </div>
        )}

        {/* Trend + Channel */}
        <div className={styles.chartsGrid}>
          <div className={`${styles.chartCard} ${styles.chartFull}`}>
            <div className={styles.chartTitle}>
              <LineChartOutlined /> 预订趋势（{days}天）
            </div>
            {trend.length > 0 ? (
              <ReactECharts option={trendOption} style={{ height: 300 }} />
            ) : (
              <Empty description="暂无趋势数据" />
            )}
          </div>

          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>
              <BarChartOutlined /> 渠道来源分布
            </div>
            {channels.length > 0 ? (
              <ReactECharts option={channelOption} style={{ height: 280 }} />
            ) : (
              <Empty description="暂无渠道数据" />
            )}
          </div>

          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>
              <DollarOutlined /> 渠道 ROI 明细
            </div>
            {channels.length > 0 ? (
              <div>
                {channels.map(ch => (
                  <div key={ch.channel} className={styles.channelBar}>
                    <span className={styles.channelName}>{CHANNEL_NAMES[ch.channel] || ch.channel}</span>
                    <div className={styles.channelBarInner}>
                      <div
                        className={styles.channelBarFill}
                        style={{ width: `${ch.percentage}%` }}
                      >
                        {ch.count}笔
                      </div>
                    </div>
                    <span className={styles.channelStats}>
                      转化{ch.conversion_rate}% | ¥{ch.cost_per_reservation}/单
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <Empty description="暂无数据" />
            )}
          </div>
        </div>

        {/* Heatmap + Customer + Revenue */}
        <div className={styles.chartsGrid}>
          <div className={`${styles.chartCard} ${styles.chartFull}`}>
            <div className={styles.chartTitle}>
              <HeatMapOutlined /> 高峰时段热力图
              {heatmapPeak && (
                <Tag color="volcano">
                  最高峰: {heatmapPeak.day_name} {heatmapPeak.hour}:00 ({heatmapPeak.count}笔)
                </Tag>
              )}
            </div>
            {heatmap.length > 0 ? (
              <ReactECharts option={heatmapOption} style={{ height: 260 }} />
            ) : (
              <Empty description="暂无热力图数据" />
            )}
          </div>

          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>
              <TeamOutlined /> 客户洞察
            </div>
            {customerData ? (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                  <div>
                    <div className={styles.kpiLabel}>独立客户数</div>
                    <div style={{ fontSize: 24, fontWeight: 600 }}>{customerData.total_unique_customers}</div>
                  </div>
                  <div>
                    <div className={styles.kpiLabel}>人均到店</div>
                    <div style={{ fontSize: 24, fontWeight: 600 }}>{customerData.avg_visits_per_customer}次</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  <Tag color="green">新客 {customerData.new_customers} ({customerData.new_rate}%)</Tag>
                  <Tag color="blue">回头客 {customerData.returning_customers} ({customerData.returning_rate}%)</Tag>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Tag>高频客户 {customerData.frequent_customers}</Tag>
                  <Tag>大桌客户 {customerData.big_party_customers}</Tag>
                </div>
              </div>
            ) : (
              <Empty description="暂无数据" />
            )}
          </div>

          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>
              <DollarOutlined /> 营收影响
            </div>
            {revenueData ? (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                  <div>
                    <div className={styles.kpiLabel}>完成预订</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>{revenueData.completed_reservations}笔</div>
                    <div className={styles.kpiSub}>{revenueData.completed_guests}位客人</div>
                  </div>
                  <div>
                    <div className={styles.kpiLabel}>预均消费</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>¥{revenueData.avg_budget_yuan}</div>
                  </div>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <Tag color="red">取消损失 ¥{revenueData.cancelled_loss_yuan} ({revenueData.cancelled_count}笔)</Tag>
                  <Tag color="orange">No-Show损失 ¥{revenueData.no_show_loss_yuan} ({revenueData.no_show_count}笔)</Tag>
                </div>
                <div style={{ fontSize: 18, fontWeight: 600, color: '#ff4d4f' }}>
                  总损失: ¥{revenueData.total_loss_yuan}
                </div>
                <div style={{ marginTop: 12, fontSize: 13, color: '#666' }}>
                  <BulbOutlined style={{ color: '#0AAF9A' }} /> {revenueData.recovery_suggestion}
                </div>
              </div>
            ) : (
              <Empty description="暂无数据" />
            )}
          </div>
        </div>

        {/* Cancellation + No-Show Risk */}
        <div className={styles.chartsGrid}>
          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>
              <CloseCircleOutlined /> 取消深度分析
            </div>
            {cancelData && cancelData.total_cancelled > 0 ? (
              <div>
                <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
                  <Tag color="red">取消 {cancelData.total_cancelled} 笔</Tag>
                  <Tag>损失 ¥{cancelData.total_lost_yuan}</Tag>
                  <Tag>均桌位 {cancelData.avg_party_size}</Tag>
                </div>
                <div className={styles.chartTitle} style={{ fontSize: 13 }}>取消提前量分布</div>
                <ReactECharts option={cancelPieOption} style={{ height: 200 }} />
                <ul className={styles.insightsList}>
                  {cancelData.insights?.map((insight: string, i: number) => (
                    <li key={i}><BulbOutlined style={{ color: '#0AAF9A' }} /> {insight}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <Empty description="当期无取消预订" />
            )}
          </div>

          <div className={styles.chartCard}>
            <div className={styles.chartTitle}>
              <WarningOutlined /> No-Show 风险预测（明日）
              {riskData && <Tag color="red">{riskData.high_risk_count} 高风险</Tag>}
            </div>
            {riskData && riskData.reservations.length > 0 ? (
              <Table
                dataSource={riskData.reservations}
                columns={riskColumns}
                rowKey="reservation_id"
                size="small"
                pagination={false}
                scroll={{ y: 300 }}
              />
            ) : (
              <Empty description="明日暂无预订" />
            )}
          </div>
        </div>
      </div>
    </Spin>
  );
};

export default ReservationAnalyticsPage;
