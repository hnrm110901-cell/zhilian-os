import React from 'react';
import { Progress } from 'antd';
import { ZCard, ZKpi, ZBadge, ZTable, ZTimeline, HealthRing } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import type { TimelineItem } from '../../design-system/components/ZTimeline';
import styles from './OpsHomePage.module.css';

/* TODO: GET /api/v1/bff/ops/dashboard */

/* ── Mock 数据 ── */

interface AlertItem {
  id: string;
  time: string;
  level: 'critical' | 'warning' | 'info';
  content: string;
  status: string;
}

const services = [
  { name: 'API Gateway', score: 98, latency: '12ms', status: 'success' as const },
  { name: 'Redis', score: 92, latency: '2ms', status: 'success' as const },
  { name: 'PostgreSQL', score: 95, latency: '8ms', status: 'success' as const },
  { name: 'Qdrant', score: 68, latency: '45ms', status: 'warning' as const },
];

const recentSyncTimeline: TimelineItem[] = [
  { key: '1', label: '长沙万达店 — 订单同步成功（230ms）', time: '14:32:05', status: 'done' },
  { key: '2', label: '株洲天元店 — 库存同步成功（185ms）', time: '14:28:11', status: 'done' },
  { key: '3', label: '湘潭步行街店 — 订单同步成功（312ms）', time: '14:25:40', status: 'done' },
  { key: '4', label: '长沙IFS店 — 菜单同步成功（156ms）', time: '14:20:03', status: 'done' },
  { key: '5', label: '衡阳雁峰店 — 订单同步超时（5002ms）', time: '14:15:22', status: 'current' },
];

const alerts: AlertItem[] = [
  { id: 'a1', time: '14:15:22', level: 'critical', content: '衡阳雁峰店 POS 连接超时', status: '待处理' },
  { id: 'a2', time: '13:45:00', level: 'warning', content: '株洲天元店订单数据延迟 >5min', status: '待处理' },
  { id: 'a3', time: '12:30:11', level: 'warning', content: 'Redis 内存使用率达 82%', status: '处理中' },
  { id: 'a4', time: '11:20:05', level: 'critical', content: 'Qdrant 向量索引重建失败', status: '待处理' },
];

/* ── 列定义 ── */

const alertColumns: ZTableColumn<AlertItem>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 100 },
  {
    key: 'level', dataIndex: 'level', title: '级别', width: 80,
    render: (v: string) => {
      const map: Record<string, 'critical' | 'warning' | 'info'> = {
        critical: 'critical', warning: 'warning', info: 'info',
      };
      const labelMap: Record<string, string> = { critical: '严重', warning: '警告', info: '信息' };
      return <ZBadge type={map[v] ?? 'default'} text={labelMap[v] ?? v} />;
    },
  },
  { key: 'content', dataIndex: 'content', title: '告警内容' },
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

      {/* KPI 区 — 4 个指标 */}
      <div className={styles.kpiRow}>
        <ZCard>
          <ZKpi label="活跃门店" value={12} changeLabel="较昨日" />
        </ZCard>
        <ZCard>
          <ZKpi label="POS连接率" value="94.5" unit="%" change={-0.3} changeLabel="较昨日" />
        </ZCard>
        <ZCard>
          <ZKpi label="数据同步成功率" value="99.2" unit="%" change={-0.1} changeLabel="较昨日" />
        </ZCard>
        <ZCard>
          <ZKpi label="今日告警" value={3} change={-2} changeLabel="较昨日" color="var(--red)" />
        </ZCard>
      </div>

      {/* 系统健康卡片 */}
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
                <ZBadge
                  type={s.score >= 90 ? 'success' : s.score >= 70 ? 'warning' : 'critical'}
                  text={s.score >= 90 ? '✅ 正常' : s.score >= 70 ? '⚠️ 注意' : '❌ 异常'}
                />
              </div>
              <div className={styles.healthBar}>
                <Progress
                  percent={s.score}
                  size="small"
                  strokeColor={s.score >= 90 ? 'var(--green)' : s.score >= 70 ? 'var(--amber)' : 'var(--red)'}
                  showInfo={false}
                />
              </div>
            </ZCard>
          ))}
        </div>
      </div>

      {/* 最近同步事件 + 待处理告警 */}
      <div className={styles.twoCol}>
        <div className={styles.section}>
          <ZCard title="最近同步事件（最新 5 条）">
            <ZTimeline items={recentSyncTimeline} />
          </ZCard>
        </div>
        <div className={styles.section}>
          <ZCard title="待处理告警">
            <ZTable<AlertItem> columns={alertColumns} data={alerts} rowKey="id" />
          </ZCard>
        </div>
      </div>
    </div>
  );
};

export default OpsHomePage;
