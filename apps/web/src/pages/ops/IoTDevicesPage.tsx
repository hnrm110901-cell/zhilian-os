import React, { useState } from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './IoTDevicesPage.module.css';

// TODO: GET /api/v1/ops/iot-devices/list
// TODO: GET /api/v1/ops/iot-devices/offline-alerts

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Device {
  id: string;
  deviceId: string;
  name: string;
  type: 'sensor' | 'camera' | 'pos' | 'gateway';
  store: string;
  online: boolean;
  lastHeartbeat: string;
  firmware: string;
  batteryLevel?: number;
}

interface OfflineAlert {
  id: string;
  device: string;
  store: string;
  offlineTime: string;
  duration: string;
  impact: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_DEVICES: Device[] = [
  { id: 'D001', deviceId: 'TEMP-S001-01', name: '冰柜温度传感器1', type: 'sensor', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:14:58', firmware: 'v2.3.1', batteryLevel: 85 },
  { id: 'D002', deviceId: 'TEMP-S001-02', name: '冷藏温度传感器', type: 'sensor', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:14:55', firmware: 'v2.3.1', batteryLevel: 72 },
  { id: 'D003', deviceId: 'CAM-S001-01', name: '厨房监控摄像', type: 'camera', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:14:50', firmware: 'v1.8.0' },
  { id: 'D004', deviceId: 'POS-S001-01', name: 'POS主收银台', type: 'pos', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:15:00', firmware: 'v5.2.0' },
  { id: 'D005', deviceId: 'GW-S001-01', name: '边缘网关', type: 'gateway', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:14:59', firmware: 'v3.1.0' },
  { id: 'D006', deviceId: 'TEMP-S002-01', name: '冰柜温度传感器1', type: 'sensor', store: '尝在一起·万达店', online: false, lastHeartbeat: '08:30:12', firmware: 'v2.3.0', batteryLevel: 12 },
  { id: 'D007', deviceId: 'CAM-S002-01', name: '厨房监控摄像', type: 'camera', store: '尝在一起·万达店', online: true, lastHeartbeat: '09:14:45', firmware: 'v1.8.0' },
  { id: 'D008', deviceId: 'POS-S002-01', name: 'POS收银台', type: 'pos', store: '尝在一起·万达店', online: true, lastHeartbeat: '09:14:52', firmware: 'v5.1.2' },
  { id: 'D009', deviceId: 'TEMP-S003-01', name: '冰柜温度传感器1', type: 'sensor', store: '尝在一起·河西店', online: false, lastHeartbeat: '07:55:30', firmware: 'v2.2.0', batteryLevel: 3 },
  { id: 'D010', deviceId: 'CAM-S003-02', name: '大堂监控摄像', type: 'camera', store: '尝在一起·河西店', online: false, lastHeartbeat: '06:10:00', firmware: 'v1.7.5' },
];

const MOCK_OFFLINE_ALERTS: OfflineAlert[] = [
  { id: 'OA01', device: 'TEMP-S002-01', store: '尝在一起·万达店', offlineTime: '08:30:12', duration: '45min', impact: '冰柜温度监控中断，食材损失风险' },
  { id: 'OA02', device: 'TEMP-S003-01', store: '尝在一起·河西店', offlineTime: '07:55:30', duration: '1h20min', impact: '低电量导致断联，需更换电池' },
  { id: 'OA03', device: 'CAM-S003-02', store: '尝在一起·河西店', offlineTime: '06:10:00', duration: '3h05min', impact: '大堂监控盲区，建议派人检查' },
];

const TYPE_LABELS: Record<Device['type'], string> = {
  sensor: '温度传感器',
  camera: '摄像头',
  pos: 'POS终端',
  gateway: '边缘网关',
};

const TYPE_COUNTS: Record<Device['type'], { count: number; online: number }> = {
  sensor: { count: 0, online: 0 },
  camera: { count: 0, online: 0 },
  pos: { count: 0, online: 0 },
  gateway: { count: 0, online: 0 },
};

MOCK_DEVICES.forEach((d) => {
  TYPE_COUNTS[d.type].count++;
  if (d.online) TYPE_COUNTS[d.type].online++;
});

// ── 组件 ─────────────────────────────────────────────────────────────────────

const IoTDevicesPage: React.FC = () => {
  const [typeFilter, setTypeFilter] = useState<Device['type'] | 'all'>('all');

  const onlineCount = MOCK_DEVICES.filter((d) => d.online).length;
  const offlineCount = MOCK_DEVICES.length - onlineCount;

  const filtered = typeFilter === 'all'
    ? MOCK_DEVICES
    : MOCK_DEVICES.filter((d) => d.type === typeFilter);

  const deviceColumns: ZTableColumn<Device>[] = [
    { key: 'deviceId', dataIndex: 'deviceId', title: '设备ID',
      render: (v: string) => <span className={styles.deviceId}>{v}</span>,
    },
    { key: 'name', dataIndex: 'name', title: '设备名称' },
    { key: 'type', dataIndex: 'type', title: '类型',
      render: (v: Device['type']) => <ZBadge type="info" text={TYPE_LABELS[v]} />,
    },
    { key: 'store', dataIndex: 'store', title: '所属门店' },
    { key: 'online', dataIndex: 'online', title: '在线状态',
      render: (v: boolean) => (
        <ZBadge type={v ? 'success' : 'error'} text={v ? '在线' : '离线'} />
      ),
    },
    { key: 'lastHeartbeat', dataIndex: 'lastHeartbeat', title: '最后心跳' },
    { key: 'firmware', dataIndex: 'firmware', title: '固件版本' },
    { key: 'batteryLevel', dataIndex: 'batteryLevel', title: '电量',
      render: (v?: number) => {
        if (v === undefined) return <span className={styles.naText}>—</span>;
        const cls = v < 20 ? styles.batteryLow : v < 50 ? styles.batteryMid : styles.batteryOk;
        return <span className={cls}>{v}%</span>;
      },
    },
    { key: 'actions', title: '操作',
      render: () => (
        <div className={styles.actionGroup}>
          <button className={styles.actionBtn}>详情</button>
          <button className={styles.actionBtn}>重启</button>
        </div>
      ),
    },
  ];

  const offlineColumns: ZTableColumn<OfflineAlert>[] = [
    { key: 'device', dataIndex: 'device', title: '设备',
      render: (v: string) => <span className={styles.deviceId}>{v}</span>,
    },
    { key: 'store', dataIndex: 'store', title: '门店' },
    { key: 'offlineTime', dataIndex: 'offlineTime', title: '离线时间' },
    { key: 'duration', dataIndex: 'duration', title: '持续时长',
      render: (v: string) => <span className={styles.durationCell}>{v}</span>,
    },
    { key: 'impact', dataIndex: 'impact', title: '影响说明' },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>IoT 设备管理</h2>
        <p>监控门店传感器、边缘网关与设备在线状态</p>
      </div>

      {/* 总览 KPI */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="设备总数" value={MOCK_DEVICES.length} /></ZCard>
        <ZCard><ZKpi label="在线设备" value={onlineCount} status="good" /></ZCard>
        <ZCard><ZKpi label="离线设备" value={offlineCount} status={offlineCount > 0 ? 'warning' : 'good'} /></ZCard>
        <ZCard><ZKpi label="在线率" value={((onlineCount / MOCK_DEVICES.length) * 100).toFixed(1)} unit="%" status="good" /></ZCard>
      </div>

      {/* 设备类型分布 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>设备类型分布</div>
        <div className={styles.cardGrid}>
          {(Object.entries(TYPE_COUNTS) as [Device['type'], { count: number; online: number }][]).map(([type, stat]) => (
            <ZCard
              key={type}
              className={`${styles.typeCard} ${typeFilter === type ? styles.typeCardActive : ''}`}
              onClick={() => setTypeFilter(typeFilter === type ? 'all' : type)}
            >
              <div className={styles.typeCardContent}>
                <div className={styles.typeNum}>{stat.count}</div>
                <div className={styles.typeLabel}>{TYPE_LABELS[type]}</div>
                <div className={styles.typeOnline}>
                  <span className={styles.onlineNum}>{stat.online}</span>
                  <span className={styles.onlineLbl}> 在线</span>
                  {stat.count - stat.online > 0 && (
                    <span className={styles.offlineNum}> / {stat.count - stat.online} 离线</span>
                  )}
                </div>
              </div>
            </ZCard>
          ))}
        </div>
      </div>

      {/* 设备列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>
          设备列表
          {typeFilter !== 'all' && (
            <span className={styles.filterTag}> — {TYPE_LABELS[typeFilter]}</span>
          )}
        </div>
        <ZCard noPadding>
          <ZTable<Device>
            columns={deviceColumns}
            dataSource={filtered}
            rowKey="id"
          />
        </ZCard>
      </div>

      {/* 离线告警 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>
          离线告警
          {offlineCount > 0 && (
            <span className={styles.alertBadge}>{offlineCount}</span>
          )}
        </div>
        <ZCard noPadding>
          <ZTable<OfflineAlert>
            columns={offlineColumns}
            dataSource={MOCK_OFFLINE_ALERTS}
            rowKey="id"
          />
        </ZCard>
      </div>
    </div>
  );
};

export default IoTDevicesPage;
