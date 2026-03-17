import React from 'react';
import { ZCard, ZBadge, ZTable } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './ChannelDataPage.module.css';

/* ── Mock 数据 ── */

interface Channel {
  name: string;
  todayOrders: number;
  rating: number;
  syncStatus: string;
}

interface ChannelAnomaly {
  time: string;
  channel: string;
  type: string;
  description: string;
  status: string;
}

const channels: Channel[] = [
  { name: '美团外卖', todayOrders: 328, rating: 4.7, syncStatus: '已同步' },
  { name: '饿了么', todayOrders: 215, rating: 4.6, syncStatus: '已同步' },
  { name: '抖音', todayOrders: 86, rating: 4.8, syncStatus: '同步中' },
  { name: '大众点评', todayOrders: 0, rating: 4.5, syncStatus: '仅评分' },
];

const anomalies: ChannelAnomaly[] = [
  { time: '14:20', channel: '美团外卖', type: '订单缺失', description: '13:00-13:30时段订单数异常偏低', status: '待确认' },
  { time: '13:05', channel: '饿了么', type: '金额异常', description: '订单#E20260317-089 金额为0', status: '已处理' },
  { time: '11:30', channel: '抖音', type: '同步延迟', description: '数据同步延迟超过15分钟', status: '处理中' },
  { time: '10:15', channel: '美团外卖', type: '评价异常', description: '连续3条1星差评，疑似恶意评价', status: '待确认' },
  { time: '09:00', channel: '饿了么', type: '订单重复', description: '检测到2笔疑似重复订单', status: '已处理' },
];

/* ── 列定义 ── */

const anomalyColumns: ZTableColumn<ChannelAnomaly>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 80 },
  { key: 'channel', dataIndex: 'channel', title: '渠道', width: 100 },
  { key: 'type', dataIndex: 'type', title: '类型', width: 90 },
  { key: 'description', dataIndex: 'description', title: '描述' },
  {
    key: 'status', dataIndex: 'status', title: '状态', width: 90,
    render: (v: string) => {
      const t = v === '已处理' ? 'success' : v === '处理中' ? 'warning' : 'default';
      return <ZBadge type={t} text={v} />;
    },
  },
];

/* ── 页面组件 ── */

const ChannelDataPage: React.FC = () => {
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>渠道数据</h1>
        <p className={styles.subtitle}>多销售渠道数据汇聚与异常监控</p>
      </div>

      {/* 渠道卡片 */}
      <div className={styles.channelGrid}>
        {channels.map(ch => (
          <ZCard key={ch.name}>
            <div className={styles.channelName}>
              <span>{ch.name}</span>
              <ZBadge
                type={ch.syncStatus === '已同步' ? 'success' : ch.syncStatus === '同步中' ? 'warning' : 'info'}
                text={ch.syncStatus}
              />
            </div>
            <div className={styles.channelMetric}>
              <span className={styles.channelMetricLabel}>今日订单</span>
              <span className={styles.channelMetricValue}>{ch.todayOrders}</span>
            </div>
            <div className={styles.channelMetric}>
              <span className={styles.channelMetricLabel}>评分</span>
              <span className={styles.channelMetricValue}>{ch.rating}</span>
            </div>
          </ZCard>
        ))}
      </div>

      {/* 渠道趋势 */}
      <div className={styles.section}>
        <ZCard title="渠道趋势对比">
          {/* GET /api/v1/ops/channel-trends — 接入后替换为 ChartTrend / ReactECharts */}
          <div className={styles.chartPlaceholder}>
            图表区域 — 各渠道近7日订单趋势对比
          </div>
        </ZCard>
      </div>

      {/* 数据异常 */}
      <div className={styles.section}>
        <ZCard title="数据异常">
          {/* GET /api/v1/ops/channel-anomalies */}
          <ZTable<ChannelAnomaly> columns={anomalyColumns} data={anomalies} rowKey="time" />
        </ZCard>
      </div>
    </div>
  );
};

export default ChannelDataPage;
