import React from 'react';
import { ZCard, ZKpi, ZBadge, ZTable, HealthRing } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './OpsHomePage.module.css';

/* ── Mock 数据 ── */

interface SyncEvent {
  time: string;
  store: string;
  type: string;
  result: string;
  duration: number;
}

interface AlertItem {
  time: string;
  level: string;
  content: string;
  status: string;
}

const syncEvents: SyncEvent[] = [
  { time: '14:32:05', store: '长沙万达店', type: '订单同步', result: '成功', duration: 230 },
  { time: '14:28:11', store: '株洲天元店', type: '库存同步', result: '成功', duration: 185 },
  { time: '14:25:40', store: '湘潭步行街店', type: '订单同步', result: '成功', duration: 312 },
  { time: '14:20:03', store: '长沙IFS店', type: '菜单同步', result: '成功', duration: 156 },
  { time: '14:15:22', store: '衡阳雁峰店', type: '订单同步', result: '失败', duration: 5002 },
  { time: '14:10:45', store: '岳阳步行街店', type: '订单同步', result: '成功', duration: 278 },
  { time: '14:05:18', store: '常德武陵店', type: '库存同步', result: '成功', duration: 198 },
  { time: '14:00:01', store: '长沙万达店', type: '会员同步', result: '成功', duration: 420 },
];

const alerts: AlertItem[] = [
  { time: '14:15:22', level: 'critical', content: '衡阳雁峰店 POS 连接超时', status: '待处理' },
  { time: '13:45:00', level: 'warning', content: '株洲天元店订单数据延迟 >5min', status: '待处理' },
  { time: '12:30:11', level: 'warning', content: 'Redis 内存使用率达 82%', status: '处理中' },
  { time: '11:20:05', level: 'critical', content: 'Qdrant 向量索引重建失败', status: '待处理' },
  { time: '10:05:33', level: 'info', content: '每日数据备份完成', status: '已完成' },
];

const services = [
  { name: 'API Gateway', score: 98, latency: '12ms' },
  { name: 'Redis', score: 92, latency: '2ms' },
  { name: 'PostgreSQL', score: 95, latency: '8ms' },
  { name: 'Qdrant', score: 78, latency: '45ms' },
];

/* ── 列定义 ── */

const syncColumns: ZTableColumn<SyncEvent>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 100 },
  { key: 'store', dataIndex: 'store', title: '门店' },
  { key: 'type', dataIndex: 'type', title: '类型', width: 100 },
  {
    key: 'result', dataIndex: 'result', title: '结果', width: 80,
    render: (v: string) => (
      <ZBadge type={v === '成功' ? 'success' : 'critical'} text={v} />
    ),
  },
  { key: 'duration', dataIndex: 'duration', title: '耗时(ms)', width: 100, align: 'right' },
];

const alertColumns: ZTableColumn<AlertItem>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 100 },
  {
    key: 'level', dataIndex: 'level', title: '级别', width: 80,
    render: (v: string) => {
      const map: Record<string, 'critical' | 'warning' | 'info'> = { critical: 'critical', warning: 'warning', info: 'info' };
      return <ZBadge type={map[v] || 'default'} text={v === 'critical' ? '严重' : v === 'warning' ? '警告' : '信息'} />;
    },
  },
  { key: 'content', dataIndex: 'content', title: '内容' },
  {
    key: 'status', dataIndex: 'status', title: '状态', width: 90,
    render: (v: string) => {
      const t = v === '已完成' ? 'success' : v === '处理中' ? 'warning' : 'default';
      return <ZBadge type={t} text={v} />;
    },
  },
];

/* ── 页面组件 ── */

const OpsHomePage: React.FC = () => {
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>运维控制台</h1>
        <p className={styles.subtitle}>系统运行状态总览与告警管理</p>
      </div>

      {/* KPI 区 */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="活跃门店数" value={32} change={3.2} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="POS连接率" value="96.8" unit="%" change={0.5} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="数据同步成功率" value="99.2" unit="%" change={-0.1} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="今日告警数" value={3} change={-2} changeLabel="较昨日" color="var(--red)" /></ZCard>
      </div>

      {/* 系统健康 */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>系统健康</h2>
        <div className={styles.healthGrid}>
          {services.map(s => (
            <ZCard key={s.name}>
              <div className={styles.serviceCard}>
                <HealthRing score={s.score} size={56} strokeWidth={6} />
                <div className={styles.serviceInfo}>
                  <div className={styles.serviceName}>{s.name}</div>
                  <div className={styles.serviceLatency}>延迟 {s.latency}</div>
                </div>
                <ZBadge type={s.score >= 90 ? 'success' : s.score >= 70 ? 'warning' : 'critical'} text={s.score >= 90 ? '正常' : s.score >= 70 ? '注意' : '异常'} />
              </div>
            </ZCard>
          ))}
        </div>
      </div>

      {/* 同步事件 + 告警 */}
      <div className={styles.twoCol}>
        <div className={styles.section}>
          <ZCard title="最近同步事件">
            {/* GET /api/v1/ops/sync-events */}
            <ZTable<SyncEvent> columns={syncColumns} data={syncEvents} rowKey="time" />
          </ZCard>
        </div>
        <div className={styles.section}>
          <ZCard title="待处理告警">
            {/* GET /api/v1/ops/alerts?status=pending */}
            <ZTable<AlertItem> columns={alertColumns} data={alerts} rowKey="time" />
          </ZCard>
        </div>
      </div>
    </div>
  );
};

export default OpsHomePage;
