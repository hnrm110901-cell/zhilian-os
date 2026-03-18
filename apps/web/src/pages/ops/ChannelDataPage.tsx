import React, { useState } from 'react';
import { ZCard, ZBadge, ZTable, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './ChannelDataPage.module.css';

/* ── Mock 数据 ── TODO: GET /api/v1/ops/channel-overview */

interface Channel {
  id: string;
  name: string;
  icon: string;
  todayOrders: number;
  todayGmv: number;
  rating: number;
  syncStatus: string;
  orderChange: number;
  gmvChange: number;
}

interface ChannelAnomaly {
  time: string;
  channel: string;
  type: string;
  description: string;
  status: string;
  impact: string;
}

interface TrendDay {
  date: string;
  meituan: number;
  eleme: number;
  douyin: number;
}

const channels: Channel[] = [
  { id: 'meituan', name: '美团外卖', icon: '🛵', todayOrders: 328, todayGmv: 21840, rating: 4.7, syncStatus: '已同步', orderChange: 8.2, gmvChange: 12.4 },
  { id: 'eleme', name: '饿了么', icon: '🦅', todayOrders: 215, todayGmv: 14320, rating: 4.6, syncStatus: '已同步', orderChange: -3.1, gmvChange: -1.8 },
  { id: 'douyin', name: '抖音', icon: '🎵', todayOrders: 86, todayGmv: 6450, rating: 4.8, syncStatus: '同步中', orderChange: 42.5, gmvChange: 38.9 },
  { id: 'dianping', name: '大众点评', icon: '⭐', todayOrders: 0, todayGmv: 0, rating: 4.5, syncStatus: '仅评分', orderChange: 0, gmvChange: 0 },
];

const trendDays: TrendDay[] = [
  { date: '3/12', meituan: 285, eleme: 198, douyin: 52 },
  { date: '3/13', meituan: 312, eleme: 221, douyin: 64 },
  { date: '3/14', meituan: 298, eleme: 208, douyin: 71 },
  { date: '3/15', meituan: 341, eleme: 235, douyin: 78 },
  { date: '3/16', meituan: 306, eleme: 194, douyin: 82 },
  { date: '3/17', meituan: 328, eleme: 215, douyin: 86 },
];

const anomalies: ChannelAnomaly[] = [
  { time: '14:20', channel: '美团外卖', type: '订单缺失', description: '13:00-13:30时段订单数异常偏低（仅5单）', status: '待确认', impact: '预估损失¥1,200' },
  { time: '13:05', channel: '饿了么', type: '金额异常', description: '订单#E20260317-089 金额为0元', status: '已处理', impact: '已退款¥68' },
  { time: '11:30', channel: '抖音', type: '同步延迟', description: '数据同步延迟超过15分钟', status: '处理中', impact: '影响实时监控' },
  { time: '10:15', channel: '美团外卖', type: '评价异常', description: '连续3条1星差评，疑似恶意评价', status: '待确认', impact: '评分下降风险' },
  { time: '09:00', channel: '饿了么', type: '订单重复', description: '检测到2笔疑似重复订单', status: '已处理', impact: '已撤销¥136' },
];

/* ── 列定义 ── */

const anomalyColumns: ZTableColumn<ChannelAnomaly>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 80 },
  { key: 'channel', dataIndex: 'channel', title: '渠道', width: 100 },
  {
    key: 'type', dataIndex: 'type', title: '类型', width: 90,
    render: (v: string) => {
      const t = v === '金额异常' || v === '订单重复' ? 'critical' : v === '同步延迟' ? 'warning' : 'default';
      return <ZBadge type={t} text={v} />;
    },
  },
  { key: 'description', dataIndex: 'description', title: '描述' },
  { key: 'impact', dataIndex: 'impact', title: '影响', width: 140, render: (v: string) => <span className={styles.impact}>{v}</span> },
  {
    key: 'status', dataIndex: 'status', title: '状态', width: 90,
    render: (v: string) => {
      const t = v === '已处理' ? 'success' : v === '处理中' ? 'warning' : 'default';
      return <ZBadge type={t} text={v} />;
    },
  },
];

/* ── 迷你趋势柱 ── */
const MiniBar: React.FC<{ value: number; max: number; color: string }> = ({ value, max, color }) => (
  <div className={styles.miniBarWrap}>
    <div className={styles.miniBar} style={{ width: `${Math.round((value / max) * 100)}%`, background: color }} />
    <span className={styles.miniBarVal}>{value}</span>
  </div>
);

/* ── 页面组件 ── */

const ChannelDataPage: React.FC = () => {
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | '7d' | '30d'>('today');

  const totalOrders = channels.reduce((s, c) => s + c.todayOrders, 0);
  const totalGmv = channels.reduce((s, c) => s + c.todayGmv, 0);
  const pendingAnomalies = anomalies.filter(a => a.status === '待确认').length;
  const maxOrders = Math.max(...trendDays.map(d => Math.max(d.meituan, d.eleme, d.douyin)));

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>渠道数据</h1>
          <p className={styles.subtitle}>多销售渠道数据汇聚、GMV趋势对比与异常监控</p>
        </div>
        <div className={styles.periodSwitch}>
          {(['today', '7d', '30d'] as const).map(p => (
            <button
              key={p}
              className={`${styles.periodBtn} ${selectedPeriod === p ? styles.periodBtnActive : ''}`}
              onClick={() => setSelectedPeriod(p)}
            >
              {p === 'today' ? '今日' : p === '7d' ? '近7天' : '近30天'}
            </button>
          ))}
        </div>
      </div>

      {/* 汇总 KPI */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="今日总订单" value={totalOrders} change={5.8} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="今日总GMV" value={(totalGmv / 10000).toFixed(2)} unit="万元" prefix="¥" change={9.3} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="数据异常" value={pendingAnomalies} color="var(--red)" changeLabel="待确认" /></ZCard>
        <ZCard><ZKpi label="渠道接入数" value={4} changeLabel="个" /></ZCard>
      </div>

      {/* 渠道卡片 */}
      <div className={styles.channelGrid}>
        {/* TODO: GET /api/v1/ops/channel-overview */}
        {channels.map(ch => (
          <ZCard key={ch.id}>
            <div className={styles.channelHeader}>
              <span className={styles.channelIcon}>{ch.icon}</span>
              <span className={styles.channelName}>{ch.name}</span>
              <ZBadge
                type={ch.syncStatus === '已同步' ? 'success' : ch.syncStatus === '同步中' ? 'warning' : 'info'}
                text={ch.syncStatus}
              />
            </div>
            <div className={styles.channelMetrics}>
              <div className={styles.channelMetric}>
                <span className={styles.metricLabel}>今日订单</span>
                <span className={styles.metricValue}>{ch.todayOrders}</span>
                {ch.orderChange !== 0 && (
                  <span className={ch.orderChange > 0 ? styles.changeUp : styles.changeDown}>
                    {ch.orderChange > 0 ? '↑' : '↓'}{Math.abs(ch.orderChange)}%
                  </span>
                )}
              </div>
              <div className={styles.channelMetric}>
                <span className={styles.metricLabel}>今日GMV</span>
                <span className={styles.metricValue}>¥{ch.todayGmv.toLocaleString()}</span>
                {ch.gmvChange !== 0 && (
                  <span className={ch.gmvChange > 0 ? styles.changeUp : styles.changeDown}>
                    {ch.gmvChange > 0 ? '↑' : '↓'}{Math.abs(ch.gmvChange)}%
                  </span>
                )}
              </div>
              <div className={styles.channelMetric}>
                <span className={styles.metricLabel}>评分</span>
                <span className={styles.metricValue}>
                  {'⭐'.repeat(Math.floor(ch.rating))} {ch.rating}
                </span>
              </div>
            </div>
          </ZCard>
        ))}
      </div>

      {/* 趋势对比 */}
      <div className={styles.section}>
        <ZCard title="渠道订单趋势对比（近6天）">
          {/* TODO: GET /api/v1/ops/channel-trends?days=7 — 接入后替换为 ReactECharts */}
          <div className={styles.legend}>
            <span className={styles.legendDot} style={{ background: '#FF6B2C' }} />美团外卖
            <span className={styles.legendDot} style={{ background: '#00B2FF' }} />饿了么
            <span className={styles.legendDot} style={{ background: '#000' }} />抖音
          </div>
          <div className={styles.trendTable}>
            <div className={styles.trendHeader}>
              <span className={styles.trendDate}>日期</span>
              <span className={styles.trendChannel}>美团外卖</span>
              <span className={styles.trendChannel}>饿了么</span>
              <span className={styles.trendChannel}>抖音</span>
            </div>
            {trendDays.map(day => (
              <div key={day.date} className={styles.trendRow}>
                <span className={styles.trendDateVal}>{day.date}</span>
                <div className={styles.trendBarCell}>
                  <MiniBar value={day.meituan} max={maxOrders} color="#FF6B2C" />
                </div>
                <div className={styles.trendBarCell}>
                  <MiniBar value={day.eleme} max={maxOrders} color="#00B2FF" />
                </div>
                <div className={styles.trendBarCell}>
                  <MiniBar value={day.douyin} max={maxOrders} color="#333" />
                </div>
              </div>
            ))}
          </div>
        </ZCard>
      </div>

      {/* 数据异常 */}
      <div className={styles.section}>
        <ZCard title="数据异常">
          {/* TODO: GET /api/v1/ops/channel-anomalies */}
          <ZTable<ChannelAnomaly> columns={anomalyColumns} data={anomalies} rowKey="time" />
        </ZCard>
      </div>
    </div>
  );
};

export default ChannelDataPage;
