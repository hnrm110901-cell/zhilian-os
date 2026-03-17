import React from 'react';
import { ZCard, ZBadge } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './IoTDevicesPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface Device {
  id: string;
  deviceId: string;
  type: string;
  store: string;
  online: boolean;
  lastHeartbeat: string;
  firmware: string;
}

interface OfflineAlert {
  id: string;
  device: string;
  store: string;
  offlineTime: string;
  duration: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_DEVICES: Device[] = [
  { id: 'D001', deviceId: 'TEMP-S001-01', type: '温度传感器', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:14:58', firmware: 'v2.3.1' },
  { id: 'D002', deviceId: 'TEMP-S001-02', type: '温度传感器', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:14:55', firmware: 'v2.3.1' },
  { id: 'D003', deviceId: 'CAM-S001-01', type: '摄像头', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:14:50', firmware: 'v1.8.0' },
  { id: 'D004', deviceId: 'POS-S001-01', type: 'POS终端', store: '尝在一起·五一店', online: true, lastHeartbeat: '09:15:00', firmware: 'v5.2.0' },
  { id: 'D005', deviceId: 'TEMP-S002-01', type: '温度传感器', store: '尝在一起·万达店', online: false, lastHeartbeat: '08:30:12', firmware: 'v2.3.0' },
  { id: 'D006', deviceId: 'CAM-S002-01', type: '摄像头', store: '尝在一起·万达店', online: true, lastHeartbeat: '09:14:45', firmware: 'v1.8.0' },
  { id: 'D007', deviceId: 'POS-S002-01', type: 'POS终端', store: '尝在一起·万达店', online: true, lastHeartbeat: '09:14:52', firmware: 'v5.1.2' },
  { id: 'D008', deviceId: 'TEMP-S003-01', type: '温度传感器', store: '尝在一起·河西店', online: false, lastHeartbeat: '07:55:30', firmware: 'v2.2.0' },
];

const MOCK_OFFLINE_ALERTS: OfflineAlert[] = [
  { id: 'OA01', device: 'TEMP-S002-01', store: '尝在一起·万达店', offlineTime: '08:30:12', duration: '45min' },
  { id: 'OA02', device: 'TEMP-S003-01', store: '尝在一起·河西店', offlineTime: '07:55:30', duration: '1h20min' },
  { id: 'OA03', device: 'CAM-S003-02', store: '尝在一起·河西店', offlineTime: '06:10:00', duration: '3h05min' },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const IoTDevicesPage: React.FC = () => {
  const deviceColumns: ZTableColumn<Device>[] = [
    { key: 'deviceId', dataIndex: 'deviceId', title: '设备ID' },
    { key: 'type', dataIndex: 'type', title: '类型' },
    { key: 'store', dataIndex: 'store', title: '所属门店' },
    { key: 'online', dataIndex: 'online', title: '在线状态',
      render: (v: boolean) => (
        <ZBadge type={v ? 'success' : 'error'} text={v ? '在线' : '离线'} />
      ),
    },
    { key: 'lastHeartbeat', dataIndex: 'lastHeartbeat', title: '最后心跳' },
    { key: 'firmware', dataIndex: 'firmware', title: '固件版本' },
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
    { key: 'device', dataIndex: 'device', title: '设备' },
    { key: 'store', dataIndex: 'store', title: '门店' },
    { key: 'offlineTime', dataIndex: 'offlineTime', title: '离线时间' },
    { key: 'duration', dataIndex: 'duration', title: '持续时长',
      render: (v: string) => <span className={styles.durationCell}>{v}</span>,
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>IoT 设备管理</h2>
        <p>监控门店传感器、边缘网关与设备在线状态</p>
      </div>

      {/* 设备类型分布 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>设备类型分布</div>
        <div className={styles.cardGrid}>
          <ZCard>
            <div className={styles.deviceStat}>
              <div className={styles.deviceStatNum}>12</div>
              <div className={styles.deviceStatLabel}>温度传感器</div>
            </div>
          </ZCard>
          <ZCard>
            <div className={styles.deviceStat}>
              <div className={styles.deviceStatNum}>8</div>
              <div className={styles.deviceStatLabel}>摄像头</div>
            </div>
          </ZCard>
          <ZCard>
            <div className={styles.deviceStat}>
              <div className={styles.deviceStatNum}>32</div>
              <div className={styles.deviceStatLabel}>POS 终端</div>
            </div>
          </ZCard>
        </div>
      </div>

      {/* 设备列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>设备列表</div>
        <ZCard noPadding>
          <ZTable<Device>
            columns={deviceColumns}
            dataSource={MOCK_DEVICES}
            rowKey="id"
          />
        </ZCard>
      </div>

      {/* 离线告警 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>离线告警</div>
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
