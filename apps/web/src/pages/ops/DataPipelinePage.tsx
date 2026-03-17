import React from 'react';
import { ZCard, ZKpi, ZBadge, ZTable, ZButton } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import styles from './DataPipelinePage.module.css';

/* ── Mock 数据 ── */

interface PosConnection {
  store: string;
  posType: string;
  status: string;
  lastSync: string;
  todayOrders: number;
}

interface SyncLog {
  time: string;
  store: string;
  syncType: string;
  result: string;
  duration: number;
  orderCount: number;
}

const posConnections: PosConnection[] = [
  { store: '长沙万达店', posType: '品智POS', status: '已连接', lastSync: '14:32:05', todayOrders: 186 },
  { store: '株洲天元店', posType: '天财商龙', status: '已连接', lastSync: '14:28:11', todayOrders: 142 },
  { store: '湘潭步行街店', posType: '品智POS', status: '已连接', lastSync: '14:25:40', todayOrders: 98 },
  { store: '衡阳雁峰店', posType: '客如云', status: '断开', lastSync: '12:15:22', todayOrders: 67 },
  { store: '岳阳步行街店', posType: '奥琦玮', status: '已连接', lastSync: '14:10:45', todayOrders: 123 },
  { store: '常德武陵店', posType: '美团SaaS', status: '同步中', lastSync: '14:05:18', todayOrders: 89 },
];

const syncLogs: SyncLog[] = [
  { time: '14:32:05', store: '长沙万达店', syncType: '订单增量', result: '成功', duration: 230, orderCount: 12 },
  { time: '14:28:11', store: '株洲天元店', syncType: '库存快照', result: '成功', duration: 185, orderCount: 0 },
  { time: '14:25:40', store: '湘潭步行街店', syncType: '订单增量', result: '成功', duration: 312, orderCount: 8 },
  { time: '14:20:03', store: '长沙IFS店', syncType: '菜单全量', result: '成功', duration: 1560, orderCount: 0 },
  { time: '14:15:22', store: '衡阳雁峰店', syncType: '订单增量', result: '超时', duration: 5002, orderCount: 0 },
  { time: '14:10:45', store: '岳阳步行街店', syncType: '订单增量', result: '成功', duration: 278, orderCount: 15 },
  { time: '14:05:18', store: '常德武陵店', syncType: '库存快照', result: '成功', duration: 198, orderCount: 0 },
  { time: '14:00:01', store: '长沙万达店', syncType: '会员同步', result: '成功', duration: 420, orderCount: 0 },
  { time: '13:55:30', store: '株洲天元店', syncType: '订单增量', result: '成功', duration: 245, orderCount: 10 },
  { time: '13:50:12', store: '湘潭步行街店', syncType: '订单增量', result: '成功', duration: 289, orderCount: 6 },
];

/* ── 列定义 ── */

const posColumns: ZTableColumn<PosConnection>[] = [
  { key: 'store', dataIndex: 'store', title: '门店名' },
  { key: 'posType', dataIndex: 'posType', title: 'POS类型', width: 110 },
  {
    key: 'status', dataIndex: 'status', title: '连接状态', width: 100,
    render: (v: string) => {
      const t = v === '已连接' ? 'success' : v === '同步中' ? 'warning' : 'critical';
      return <ZBadge type={t} text={v} />;
    },
  },
  { key: 'lastSync', dataIndex: 'lastSync', title: '最后同步', width: 100 },
  { key: 'todayOrders', dataIndex: 'todayOrders', title: '今日订单数', width: 100, align: 'right' },
  {
    key: 'action', title: '操作', width: 100,
    render: (_: unknown, row: PosConnection) => (
      <ZButton size="sm" variant="ghost" onClick={() => console.log('sync', row.store)}>
        手动同步
      </ZButton>
    ),
  },
];

const logColumns: ZTableColumn<SyncLog>[] = [
  { key: 'time', dataIndex: 'time', title: '时间', width: 100 },
  { key: 'store', dataIndex: 'store', title: '门店' },
  { key: 'syncType', dataIndex: 'syncType', title: '同步类型', width: 100 },
  {
    key: 'result', dataIndex: 'result', title: '结果', width: 80,
    render: (v: string) => (
      <ZBadge type={v === '成功' ? 'success' : 'critical'} text={v} />
    ),
  },
  { key: 'duration', dataIndex: 'duration', title: '耗时(ms)', width: 90, align: 'right' },
  { key: 'orderCount', dataIndex: 'orderCount', title: '订单数', width: 80, align: 'right' },
];

/* ── 页面组件 ── */

const DataPipelinePage: React.FC = () => {
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>POS数据管道</h1>
        <p className={styles.subtitle}>门店POS连接状态监控与数据同步管理</p>
      </div>

      {/* 数据质量 KPI */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="字段完整率" value="99.1" unit="%" change={0.2} changeLabel="较昨日" /></ZCard>
        <ZCard><ZKpi label="金额校验通过率" value="100" unit="%" /></ZCard>
        <ZCard><ZKpi label="重复订单率" value="0.02" unit="%" change={-0.01} changeLabel="较昨日" /></ZCard>
      </div>

      {/* POS 连接状态 */}
      <div className={styles.section}>
        <ZCard title="门店POS连接状态">
          {/* GET /api/v1/ops/pos-connections */}
          <ZTable<PosConnection> columns={posColumns} data={posConnections} rowKey="store" />
        </ZCard>
      </div>

      {/* 同步历史 */}
      <div className={styles.section}>
        <ZCard title="同步历史日志">
          {/* GET /api/v1/ops/sync-logs */}
          <ZTable<SyncLog> columns={logColumns} data={syncLogs} rowKey="time" />
        </ZCard>
      </div>
    </div>
  );
};

export default DataPipelinePage;
