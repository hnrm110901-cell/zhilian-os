import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Table, Tag, Tabs, Badge, Empty, Spin, Descriptions, Button,
} from 'antd';
import {
  WifiOutlined, DesktopOutlined, BellOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useParams } from 'react-router-dom';
import { apiClient, handleApiError } from '../services/api';
import styles from './EdgeHubStorePage.module.css';

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface HubInfo {
  id:             string;
  storeId:        string;
  hubCode:        string;
  name:           string | null;
  status:         string;
  runtimeVersion: string | null;
  ipAddress:      string | null;
  lastHeartbeat:  string | null;
  cpuPct:         number | null;
  memPct:         number | null;
  diskPct:        number | null;
}

interface DeviceItem {
  id:          string;
  hubId:       string;
  storeId:     string;
  deviceCode:  string;
  deviceType:  string;
  name:        string | null;
  status:      string;
  lastSeen:    string | null;
  firmwareVer: string | null;
}

interface AlertItem {
  id:         string;
  level:      string;
  alertType:  string;
  message:    string | null;
  status:     string;
  createdAt:  string | null;
  resolvedAt: string | null;
}

// ── 常量 ──────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  online:   '#1A7A52',
  offline:  '#C53030',
  degraded: '#C8923A',
  upgrading:'#0AAF9A',
  error:    '#C53030',
};

const STATUS_LABEL: Record<string, string> = {
  online: '在线', offline: '离线', degraded: '降级', upgrading: '升级中', error: '异常',
};

const DEVICE_TYPE_LABEL: Record<string, string> = {
  headset: '耳机', printer: '打印机', kds: 'KDS', sensor: '传感器', camera: '摄像头', other: '其他',
};

const LEVEL_COLOR: Record<string, string> = { p1: 'red', p2: 'orange', p3: 'blue' };

// ── 主组件 ────────────────────────────────────────────────────────────────────

const EdgeHubStorePage: React.FC = () => {
  const { storeId = '' } = useParams<{ storeId: string }>();

  const [hubs, setHubs]       = useState<HubInfo[]>([]);
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [alerts, setAlerts]   = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    if (!storeId) return;
    setLoading(true);
    try {
      const [hubResp, devResp, alertResp] = await Promise.allSettled([
        apiClient.get(`/api/v1/edge-hub/stores/${storeId}`),
        apiClient.get(`/api/v1/edge-hub/stores/${storeId}/devices`),
        apiClient.get(`/api/v1/edge-hub/stores/${storeId}/alerts?pageSize=50`),
      ]);
      if (hubResp.status === 'fulfilled')   setHubs(((hubResp.value as any).data?.hubs) ?? []);
      if (devResp.status === 'fulfilled')   setDevices(((devResp.value as any).data?.devices) ?? []);
      if (alertResp.status === 'fulfilled') setAlerts(((alertResp.value as any).data?.list) ?? []);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const hub = hubs[0] ?? null;

  // ── 设备列 ───────────────────────────────────────────────────────────────────
  const deviceColumns = [
    {
      title: '设备编码', dataIndex: 'deviceCode', width: 140,
      render: (v: string) => <code>{v}</code>,
    },
    {
      title: '类型', dataIndex: 'deviceType', width: 90,
      render: (v: string) => <Tag>{DEVICE_TYPE_LABEL[v] ?? v}</Tag>,
    },
    {
      title: '名称', dataIndex: 'name', width: 140,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => (
        <Badge color={STATUS_COLOR[v] ?? '#d9d9d9'} text={STATUS_LABEL[v] ?? v} />
      ),
    },
    {
      title: '最后在线', dataIndex: 'lastSeen', width: 150,
      render: (v: string | null) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
    {
      title: '固件版本', dataIndex: 'firmwareVer', width: 100,
      render: (v: string | null) => v ?? '—',
    },
  ];

  // ── 告警列 ───────────────────────────────────────────────────────────────────
  const alertColumns = [
    {
      title: '级别', dataIndex: 'level', width: 70,
      render: (v: string) => <Tag color={LEVEL_COLOR[v] ?? 'default'}>{v.toUpperCase()}</Tag>,
    },
    {
      title: '类型', dataIndex: 'alertType', width: 160,
      render: (v: string) => v.replace(/_/g, ' '),
    },
    { title: '描述', dataIndex: 'message', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => (
        <Tag color={v === 'open' ? 'red' : 'green'}>{v === 'open' ? '未解决' : '已解决'}</Tag>
      ),
    },
    {
      title: '发生时间', dataIndex: 'createdAt', width: 150,
      render: (v: string | null) => v ? dayjs(v).format('MM-DD HH:mm:ss') : '—',
    },
  ];

  const onlineDevices  = devices.filter(d => d.status === 'online').length;
  const offlineDevices = devices.filter(d => d.status === 'offline' || d.status === 'error').length;
  const openAlerts     = alerts.filter(a => a.status === 'open').length;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>门店边缘详情 — {storeId}</h2>
        <Button icon={<ReloadOutlined />} size="small" onClick={fetchAll} loading={loading}>
          刷新
        </Button>
      </div>

      <Spin spinning={loading}>
        {/* 主机概要 */}
        {hub ? (
          <Card
            title={<><WifiOutlined style={{ color: STATUS_COLOR[hub.status] }} /> 边缘主机</>}
            size="small"
            className={styles.hubCard}
            extra={<Badge color={STATUS_COLOR[hub.status]} text={STATUS_LABEL[hub.status] ?? hub.status} />}
          >
            <Descriptions size="small" column={{ xs: 2, sm: 3, md: 4 }}>
              <Descriptions.Item label="主机编码">{hub.hubCode}</Descriptions.Item>
              <Descriptions.Item label="IP 地址">{hub.ipAddress ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="运行版本">{hub.runtimeVersion ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="最后心跳">
                {hub.lastHeartbeat ? dayjs(hub.lastHeartbeat).format('MM-DD HH:mm:ss') : '—'}
              </Descriptions.Item>
              {hub.cpuPct !== null && (
                <Descriptions.Item label="CPU">{hub.cpuPct.toFixed(1)}%</Descriptions.Item>
              )}
              {hub.memPct !== null && (
                <Descriptions.Item label="内存">{hub.memPct.toFixed(1)}%</Descriptions.Item>
              )}
              {hub.diskPct !== null && (
                <Descriptions.Item label="磁盘">{hub.diskPct.toFixed(1)}%</Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        ) : (
          !loading && <Card size="small"><Empty description="该门店暂无边缘主机数据" /></Card>
        )}

        {/* 统计摘要行 */}
        <Row gutter={[12, 12]} className={styles.summaryRow}>
          <Col xs={8}>
            <Card size="small" className={styles.summaryCard}>
              <div className={styles.summaryNum} style={{ color: '#1A7A52' }}>{onlineDevices}</div>
              <div className={styles.summaryLabel}>设备在线</div>
            </Card>
          </Col>
          <Col xs={8}>
            <Card size="small" className={styles.summaryCard}>
              <div className={styles.summaryNum} style={{ color: offlineDevices > 0 ? '#C53030' : undefined }}>
                {offlineDevices}
              </div>
              <div className={styles.summaryLabel}>设备离线/异常</div>
            </Card>
          </Col>
          <Col xs={8}>
            <Card size="small" className={styles.summaryCard}>
              <div className={styles.summaryNum} style={{ color: openAlerts > 0 ? '#C8923A' : undefined }}>
                {openAlerts}
              </div>
              <div className={styles.summaryLabel}>未解决告警</div>
            </Card>
          </Col>
        </Row>

        {/* 设备 & 告警 Tabs */}
        <Tabs
          defaultActiveKey="devices"
          items={[
            {
              key: 'devices',
              label: <><DesktopOutlined /> 设备列表 ({devices.length})</>,
              children: (
                <Table
                  dataSource={devices}
                  columns={deviceColumns}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 20, size: 'small' }}
                  rowClassName={(r) => r.status !== 'online' ? styles.offlineRow : ''}
                />
              ),
            },
            {
              key: 'alerts',
              label: (
                <span>
                  <BellOutlined /> 告警记录 ({alerts.length})
                  {openAlerts > 0 && (
                    <Tag color="red" style={{ marginLeft: 4 }}>{openAlerts}</Tag>
                  )}
                </span>
              ),
              children: (
                <Table
                  dataSource={alerts}
                  columns={alertColumns}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 20, size: 'small' }}
                />
              ),
            },
          ]}
        />
      </Spin>
    </div>
  );
};

export default EdgeHubStorePage;
