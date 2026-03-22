import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Row, Col, Statistic, Tag, Table, Empty, Spin, Badge, Progress, Button,
} from 'antd';
import {
  WifiOutlined, DesktopOutlined, BellOutlined, WarningOutlined, ReloadOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { Link } from 'react-router-dom';
import { apiClient, handleApiError } from '../services/api';
import styles from './EdgeHubDashboardPage.module.css';

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface DashboardCards {
  totalHubCount:      number;
  onlineHubCount:     number;
  hubOnlineRate:      number;
  hubStatusLevel:     string;
  totalDeviceCount:   number;
  onlineDeviceCount:  number;
  deviceOnlineRate:   number;
  deviceStatusLevel:  string;
  todayAlertCount:    number;
  todayP1AlertCount:  number;
  openAlertCount:     number;
}

interface RiskStore {
  storeId:         string;
  storeName:       string;
  edgeHubId:       string | null;
  runtimeStatus:   string;
  alertCount:      number;
  lastHeartbeatAt: string | null;
}

interface AlertItem {
  id:         string;
  storeId:    string;
  level:      string;
  alertType:  string;
  message:    string | null;
  status:     string;
  createdAt:  string | null;
}

// ── 常量 ──────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  online:   '#1A7A52',
  offline:  '#C53030',
  degraded: '#C8923A',
  upgrading:'#FF6B2C',
  normal:   '#1A7A52',
  warning:  '#C8923A',
  critical: '#C53030',
};

const LEVEL_COLOR: Record<string, string> = {
  p1: 'red',
  p2: 'orange',
  p3: 'blue',
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const REFRESH_SECONDS = 30;

const EdgeHubDashboardPage: React.FC = () => {
  const [cards, setCards]       = useState<DashboardCards | null>(null);
  const [riskStores, setRisk]   = useState<RiskStore[]>([]);
  const [alerts, setAlerts]     = useState<AlertItem[]>([]);
  const [loading, setLoading]   = useState(false);
  const [refreshedAt, setRefreshedAt] = useState<string>('');
  const [countdown, setCountdown]     = useState(REFRESH_SECONDS);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryResp, riskResp, alertResp] = await Promise.allSettled([
        apiClient.get('/api/v1/edge-hub/dashboard/summary?dateRange=today'),
        apiClient.get('/api/v1/edge-hub/dashboard/risk-stores?dateRange=today&pageSize=10'),
        apiClient.get('/api/v1/edge-hub/dashboard/recent-alerts?limit=20'),
      ]);

      if (summaryResp.status === 'fulfilled') {
        const d = (summaryResp.value as any).data;
        setCards(d.cards);
        setRefreshedAt(d.refreshedAt ?? '');
      }
      if (riskResp.status === 'fulfilled') {
        setRisk(((riskResp.value as any).data?.list) ?? []);
      }
      if (alertResp.status === 'fulfilled') {
        setAlerts(((alertResp.value as any).data?.list) ?? []);
      }
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
      setCountdown(REFRESH_SECONDS);
    }
  }, []);

  // 首次加载
  useEffect(() => { fetchAll(); }, [fetchAll]);

  // 30 秒自动刷新
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          fetchAll();
          return REFRESH_SECONDS;
        }
        return prev - 1;
      });
    }, 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [fetchAll]);

  // ── 告警分布饼图 ─────────────────────────────────────────────────────────────
  const p1 = alerts.filter(a => a.level === 'p1').length;
  const p2 = alerts.filter(a => a.level === 'p2').length;
  const p3 = alerts.filter(a => a.level === 'p3').length;

  const alertPieOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      data: [
        { name: 'P1 严重', value: p1, itemStyle: { color: '#C53030' } },
        { name: 'P2 重要', value: p2, itemStyle: { color: '#C8923A' } },
        { name: 'P3 一般', value: p3, itemStyle: { color: '#FF6B2C' } },
      ],
      label: { show: false },
    }],
  };

  // ── 异常门店列 ────────────────────────────────────────────────────────────────
  const riskColumns = [
    {
      title: '门店', dataIndex: 'storeId', width: 120,
      render: (v: string) => (
        <Link to={`/edge-hub/stores/${v}`}>{v}</Link>
      ),
    },
    {
      title: '状态', dataIndex: 'runtimeStatus', width: 90,
      render: (v: string) => (
        <Badge color={STATUS_COLOR[v] ?? '#d9d9d9'} text={v} />
      ),
    },
    {
      title: '告警数', dataIndex: 'alertCount', width: 80,
      render: (v: number) => <span style={{ color: v > 0 ? '#C53030' : undefined, fontWeight: 600 }}>{v}</span>,
    },
    {
      title: '最后心跳', dataIndex: 'lastHeartbeatAt', width: 160,
      render: (v: string | null) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
  ];

  // ── 今日告警列 ────────────────────────────────────────────────────────────────
  const alertColumns = [
    {
      title: '级别', dataIndex: 'level', width: 70,
      render: (v: string) => <Tag color={LEVEL_COLOR[v] ?? 'default'}>{v.toUpperCase()}</Tag>,
    },
    { title: '门店', dataIndex: 'storeId', width: 100 },
    {
      title: '类型', dataIndex: 'alertType', width: 160,
      render: (v: string) => v.replace(/_/g, ' '),
    },
    { title: '描述', dataIndex: 'message', ellipsis: true },
    {
      title: '时间', dataIndex: 'createdAt', width: 130,
      render: (v: string | null) => v ? dayjs(v).format('HH:mm:ss') : '—',
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => (
        <Tag color={v === 'open' ? 'red' : 'green'}>{v === 'open' ? '未解决' : '已解决'}</Tag>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>Edge Hub 总览工作台</h2>
        <div className={styles.headerRight}>
          {refreshedAt && (
            <span className={styles.refreshTime}>
              刷新于 {dayjs(refreshedAt).format('HH:mm:ss')}
            </span>
          )}
          <span className={styles.countdown}>{countdown}s</span>
          <Button
            size="small" icon={<ReloadOutlined />}
            loading={loading}
            onClick={fetchAll}
          >
            刷新
          </Button>
        </div>
      </div>

      <Spin spinning={loading}>
        {/* KPI 卡片 */}
        <Row gutter={[16, 16]} className={styles.kpiRow}>
          <Col xs={12} sm={6}>
            <Card className={styles.kpiCard}>
              <Statistic
                title={<><WifiOutlined /> 边缘主机在线率</>}
                value={cards?.hubOnlineRate ?? 0}
                suffix="%"
                precision={1}
                valueStyle={{ color: STATUS_COLOR[cards?.hubStatusLevel ?? 'normal'] }}
              />
              <div className={styles.kpiSub}>
                {cards?.onlineHubCount ?? 0} / {cards?.totalHubCount ?? 0} 台在线
              </div>
              <Progress
                percent={cards?.hubOnlineRate ?? 0}
                showInfo={false}
                strokeColor={STATUS_COLOR[cards?.hubStatusLevel ?? 'normal']}
                size="small"
                style={{ marginTop: 4 }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className={styles.kpiCard}>
              <Statistic
                title={<><DesktopOutlined /> 设备在线率</>}
                value={cards?.deviceOnlineRate ?? 0}
                suffix="%"
                precision={1}
                valueStyle={{ color: STATUS_COLOR[cards?.deviceStatusLevel ?? 'normal'] }}
              />
              <div className={styles.kpiSub}>
                {cards?.onlineDeviceCount ?? 0} / {cards?.totalDeviceCount ?? 0} 台在线
              </div>
              <Progress
                percent={cards?.deviceOnlineRate ?? 0}
                showInfo={false}
                strokeColor={STATUS_COLOR[cards?.deviceStatusLevel ?? 'normal']}
                size="small"
                style={{ marginTop: 4 }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className={styles.kpiCard}>
              <Statistic
                title={<><BellOutlined /> 今日告警</>}
                value={cards?.todayAlertCount ?? 0}
                valueStyle={{ color: (cards?.todayAlertCount ?? 0) > 0 ? '#C8923A' : undefined }}
              />
              <div className={styles.kpiSub}>
                P1严重: {cards?.todayP1AlertCount ?? 0} 条
              </div>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className={styles.kpiCard}>
              <Statistic
                title={<><WarningOutlined /> 未解决告警</>}
                value={cards?.openAlertCount ?? 0}
                valueStyle={{ color: (cards?.openAlertCount ?? 0) > 0 ? '#C53030' : undefined }}
              />
              <div className={styles.kpiSub}>需要处理</div>
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]}>
          {/* 异常门店排行 */}
          <Col xs={24} lg={14}>
            <Card title="异常门店排行" size="small" className={styles.tableCard}>
              {riskStores.length === 0 ? (
                <Empty description="暂无异常门店" />
              ) : (
                <Table
                  dataSource={riskStores}
                  columns={riskColumns}
                  rowKey="storeId"
                  size="small"
                  pagination={false}
                />
              )}
            </Card>
          </Col>

          {/* 告警级别分布 */}
          <Col xs={24} lg={10}>
            <Card title="今日告警分布" size="small" className={styles.chartCard}>
              {alerts.length === 0 ? (
                <Empty description="暂无告警" />
              ) : (
                <ReactECharts option={alertPieOption} style={{ height: 220 }} />
              )}
            </Card>
          </Col>
        </Row>

        {/* 今日告警列表 */}
        <Card title="今日告警列表" size="small" style={{ marginTop: 16 }}>
          {alerts.length === 0 ? (
            <Empty description="今日暂无告警" />
          ) : (
            <Table
              dataSource={alerts}
              columns={alertColumns}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 10, size: 'small' }}
            />
          )}
        </Card>
      </Spin>
    </div>
  );
};

export default EdgeHubDashboardPage;
