import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Table, Tag, Badge, Input, Select, Space, Button,
  Tooltip, Empty, Spin, Row, Col, Drawer, Descriptions, List, Progress, message,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, WifiOutlined,
  DesktopOutlined, BellOutlined, LinkOutlined, InfoCircleOutlined, SyncOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiClient, handleApiError } from '../services/api';
import styles from './EdgeHubNodesPage.module.css';

const { Option } = Select;

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface NodeItem {
  id:              string;
  storeId:         string;
  hubCode:         string;
  name:            string | null;
  status:          string;
  runtimeVersion:  string | null;
  ipAddress:       string | null;
  lastHeartbeat:   string | null;
  cpuPct:          number | null;
  memPct:          number | null;
  diskPct:         number | null;
  deviceCount:     number;
  openAlertCount:  number;
}

interface PageMeta {
  page: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
}

// ── 常量 ──────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  online:   '#1A7A52',
  offline:  '#C53030',
  degraded: '#C8923A',
  upgrading:'#0AAF9A',
};

const STATUS_LABEL: Record<string, string> = {
  online: '在线', offline: '离线', degraded: '降级', upgrading: '升级中',
};

const LEVEL_COLOR: Record<string, string> = { p1: 'red', p2: 'orange', p3: 'blue' };

function resourceBar(pct: number | null) {
  if (pct === null) return '—';
  const color = pct >= 90 ? '#C53030' : pct >= 70 ? '#C8923A' : '#1A7A52';
  return (
    <span style={{ color, fontWeight: 600 }}>{pct.toFixed(1)}%</span>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

const EdgeHubNodesPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [nodes, setNodes]     = useState<NodeItem[]>([]);
  const [meta, setMeta]       = useState<PageMeta>({ page: 1, pageSize: 20, total: 0, hasMore: false });
  const [loading, setLoading] = useState(false);

  // 筛选状态 — 从 URL 初始化
  const [keyword, setKeyword]   = useState(() => searchParams.get('q')      ?? '');
  const [status,  setStatus]    = useState(() => searchParams.get('status')  ?? '');
  const [page,    setPage]      = useState(() => Number(searchParams.get('page') ?? '1'));
  const pageSize = 20;

  const isMount = useRef(true);

  // 详情抽屉
  const [drawerHubId, setDrawerHubId]   = useState<string | null>(null);
  const [drawerData,  setDrawerData]    = useState<any>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [inspecting, setInspecting]     = useState(false);
  const [metricsPoints, setMetricsPoints] = useState<any[]>([]);

  const fetchNodes = useCallback(async (pg = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(pg), pageSize: String(pageSize) });
      if (status)  params.set('status',  status);
      if (keyword) params.set('keyword', keyword);

      const resp = await apiClient.get(`/api/v1/edge-hub/nodes?${params}`);
      setNodes(((resp as any).data?.nodes) ?? []);
      setMeta((resp as any).meta ?? { page: pg, pageSize, total: 0, hasMore: false });
      setPage(pg);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  }, [keyword, status]);

  // 首次挂载用 URL 恢复的 page；后续筛选变化重置到第 1 页
  useEffect(() => {
    if (isMount.current) {
      isMount.current = false;
      fetchNodes(page);
    } else {
      fetchNodes(1);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword, status]);

  // URL 同步：筛选/翻页 → query string
  useEffect(() => {
    const p: Record<string, string> = {};
    if (keyword) p.q      = keyword;
    if (status)  p.status = status;
    if (page > 1) p.page  = String(page);
    setSearchParams(p, { replace: true });
  }, [keyword, status, page, setSearchParams]);

  const openNodeDrawer = async (hubId: string) => {
    setDrawerHubId(hubId);
    setDrawerData(null);
    setMetricsPoints([]);
    setDrawerLoading(true);
    try {
      const [detailResp, metricsResp] = await Promise.allSettled([
        apiClient.get(`/api/v1/edge-hub/nodes/${hubId}`),
        apiClient.get(`/api/v1/edge-hub/nodes/${hubId}/metrics?hours=24`),
      ]);
      if (detailResp.status === 'fulfilled')  setDrawerData((detailResp.value as any).data);
      if (metricsResp.status === 'fulfilled') setMetricsPoints(((metricsResp.value as any).data?.points) ?? []);
    } catch (err) {
      handleApiError(err);
    } finally {
      setDrawerLoading(false);
    }
  };

  const handleInspect = async () => {
    if (!drawerHubId) return;
    setInspecting(true);
    try {
      await apiClient.post(`/api/v1/edge-hub/nodes/${drawerHubId}/inspect`, {});
      message.success('巡检指令已下发');
      // 刷新抽屉数据
      const resp = await apiClient.get(`/api/v1/edge-hub/nodes/${drawerHubId}`);
      setDrawerData((resp as any).data);
    } catch (err) {
      handleApiError(err);
    } finally {
      setInspecting(false);
    }
  };

  // ── 统计行 ───────────────────────────────────────────────────────────────────
  const onlineCount   = nodes.filter(n => n.status === 'online').length;
  const offlineCount  = nodes.filter(n => n.status === 'offline').length;
  const degradedCount = nodes.filter(n => n.status === 'degraded').length;

  // ── 列定义 ───────────────────────────────────────────────────────────────────
  const columns = [
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => <Badge color={STATUS_COLOR[v] ?? '#d9d9d9'} text={STATUS_LABEL[v] ?? v} />,
    },
    {
      title: '主机编码', dataIndex: 'hubCode', width: 150,
      render: (v: string, r: NodeItem) => (
        <div>
          <code className={styles.hubCode}>{v}</code>
          {r.name && <div className={styles.hubName}>{r.name}</div>}
        </div>
      ),
    },
    {
      title: '门店', dataIndex: 'storeId', width: 100,
      render: (v: string) => (
        <Button
          type="link" size="small" icon={<LinkOutlined />}
          onClick={() => navigate(`/edge-hub/stores/${v}`)}
        >
          {v}
        </Button>
      ),
    },
    {
      title: 'IP 地址', dataIndex: 'ipAddress', width: 130,
      render: (v: string | null) => <code>{v ?? '—'}</code>,
    },
    {
      title: '版本', dataIndex: 'runtimeVersion', width: 90,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: 'CPU', dataIndex: 'cpuPct', width: 75,
      render: (v: number | null) => resourceBar(v),
      sorter: (a: NodeItem, b: NodeItem) => (a.cpuPct ?? 0) - (b.cpuPct ?? 0),
    },
    {
      title: '内存', dataIndex: 'memPct', width: 75,
      render: (v: number | null) => resourceBar(v),
      sorter: (a: NodeItem, b: NodeItem) => (a.memPct ?? 0) - (b.memPct ?? 0),
    },
    {
      title: '磁盘', dataIndex: 'diskPct', width: 75,
      render: (v: number | null) => resourceBar(v),
      sorter: (a: NodeItem, b: NodeItem) => (a.diskPct ?? 0) - (b.diskPct ?? 0),
    },
    {
      title: '设备', dataIndex: 'deviceCount', width: 65,
      render: (v: number) => <><DesktopOutlined /> {v}</>,
    },
    {
      title: '未解告警', dataIndex: 'openAlertCount', width: 80,
      render: (v: number) => v > 0 ? (
        <Tag color="red"><BellOutlined /> {v}</Tag>
      ) : <span className={styles.zero}>0</span>,
      sorter: (a: NodeItem, b: NodeItem) => a.openAlertCount - b.openAlertCount,
    },
    {
      title: '最后心跳', dataIndex: 'lastHeartbeat', width: 140,
      render: (v: string | null) => v ? (
        <Tooltip title={dayjs(v).format('YYYY-MM-DD HH:mm:ss')}>
          {dayjs(v).format('MM-DD HH:mm')}
        </Tooltip>
      ) : '—',
      sorter: (a: NodeItem, b: NodeItem) =>
        new Date(a.lastHeartbeat ?? 0).getTime() - new Date(b.lastHeartbeat ?? 0).getTime(),
    },
    {
      title: '操作', key: 'actions', width: 120, fixed: 'right' as const,
      render: (_: unknown, r: NodeItem) => (
        <Space size={4}>
          <Button
            type="link" size="small" icon={<InfoCircleOutlined />}
            onClick={() => openNodeDrawer(r.id)}
          >
            详情
          </Button>
          <Button
            type="link" size="small"
            onClick={() => navigate(`/edge-hub/stores/${r.storeId}`)}
          >
            门店
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>边缘节点管理</h2>
        <span className={styles.total}>共 {meta.total} 个节点</span>
      </div>

      {/* 快速统计 */}
      <Row gutter={[12, 12]} className={styles.statsRow}>
        <Col xs={8}>
          <Card size="small" className={styles.statCard}>
            <div className={styles.statNum} style={{ color: '#1A7A52' }}>{onlineCount}</div>
            <div className={styles.statLabel}>在线</div>
          </Card>
        </Col>
        <Col xs={8}>
          <Card size="small" className={styles.statCard}>
            <div className={styles.statNum} style={{ color: '#C53030' }}>{offlineCount}</div>
            <div className={styles.statLabel}>离线</div>
          </Card>
        </Col>
        <Col xs={8}>
          <Card size="small" className={styles.statCard}>
            <div className={styles.statNum} style={{ color: '#C8923A' }}>{degradedCount}</div>
            <div className={styles.statLabel}>降级</div>
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 */}
      <Card size="small" className={styles.filterCard}>
        <Space wrap>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索节点编码 / 门店 / 名称"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            style={{ width: 240 }}
            allowClear
          />
          <Select
            placeholder="全部状态"
            value={status || undefined}
            onChange={v => setStatus(v ?? '')}
            style={{ width: 130 }}
            allowClear
          >
            <Option value="online">在线</Option>
            <Option value="offline">离线</Option>
            <Option value="degraded">降级</Option>
            <Option value="upgrading">升级中</Option>
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => fetchNodes(page)}>刷新</Button>
        </Space>
      </Card>

      {/* 节点表格 */}
      <Spin spinning={loading}>
        <Card size="small" style={{ marginTop: 0 }}>
          {nodes.length === 0 && !loading ? (
            <Empty description="暂无节点数据" />
          ) : (
            <Table
              dataSource={nodes}
              columns={columns}
              rowKey="id"
              size="small"
              scroll={{ x: 1100 }}
              pagination={{
                current: page,
                pageSize,
                total: meta.total,
                showSizeChanger: false,
                size: 'small',
                onChange: fetchNodes,
              }}
              rowClassName={(r) => r.status === 'offline' ? styles.offlineRow : ''}
            />
          )}
        </Card>
      </Spin>

      {/* 节点详情抽屉 */}
      <Drawer
        title={drawerData ? `节点详情 — ${drawerData.hubCode}` : '节点详情'}
        open={!!drawerHubId}
        onClose={() => { setDrawerHubId(null); setDrawerData(null); }}
        width={560}
        destroyOnClose
        extra={
          <Button
            type="primary" size="small" icon={<SyncOutlined />}
            loading={inspecting}
            onClick={handleInspect}
          >
            触发巡检
          </Button>
        }
      >
        <Spin spinning={drawerLoading}>
          {drawerData ? (
            <>
              <Descriptions size="small" column={2} bordered style={{ marginBottom: 16 }}>
                <Descriptions.Item label="状态" span={2}>
                  <Badge
                    color={STATUS_COLOR[drawerData.status] ?? '#d9d9d9'}
                    text={STATUS_LABEL[drawerData.status] ?? drawerData.status}
                  />
                </Descriptions.Item>
                <Descriptions.Item label="IP 地址">{drawerData.ipAddress ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="版本">{drawerData.runtimeVersion ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="最后心跳" span={2}>
                  {drawerData.lastHeartbeat ? dayjs(drawerData.lastHeartbeat).format('YYYY-MM-DD HH:mm:ss') : '—'}
                </Descriptions.Item>
                {drawerData.cpuPct !== null && (
                  <Descriptions.Item label="CPU">
                    <Progress percent={Math.round(drawerData.cpuPct)} size="small" status={drawerData.cpuPct >= 90 ? 'exception' : 'normal'} />
                  </Descriptions.Item>
                )}
                {drawerData.memPct !== null && (
                  <Descriptions.Item label="内存">
                    <Progress percent={Math.round(drawerData.memPct)} size="small" status={drawerData.memPct >= 90 ? 'exception' : 'normal'} />
                  </Descriptions.Item>
                )}
                {drawerData.diskPct !== null && (
                  <Descriptions.Item label="磁盘">
                    <Progress percent={Math.round(drawerData.diskPct)} size="small" status={drawerData.diskPct >= 90 ? 'exception' : 'normal'} />
                  </Descriptions.Item>
                )}
              </Descriptions>

              {metricsPoints.length > 0 && (
                <>
                  <h4 style={{ margin: '12px 0 8px' }}>近24小时资源趋势</h4>
                  <ReactECharts
                    option={{
                      tooltip: { trigger: 'axis' },
                      legend: { data: ['CPU%', '内存%', '磁盘%'], bottom: 0, textStyle: { fontSize: 12 } },
                      grid: { left: 40, right: 16, top: 16, bottom: 36 },
                      xAxis: {
                        type: 'category',
                        data: metricsPoints.map((p: any) => p.timeLabel),
                        axisLabel: { fontSize: 10, interval: 3 },
                      },
                      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%', fontSize: 10 } },
                      series: [
                        { name: 'CPU%',  type: 'line', smooth: true, data: metricsPoints.map((p: any) => p.cpuPct),  itemStyle: { color: '#C53030' }, lineStyle: { width: 1.5 }, showSymbol: false },
                        { name: '内存%', type: 'line', smooth: true, data: metricsPoints.map((p: any) => p.memPct),  itemStyle: { color: '#0AAF9A' }, lineStyle: { width: 1.5 }, showSymbol: false },
                        { name: '磁盘%', type: 'line', smooth: true, data: metricsPoints.map((p: any) => p.diskPct), itemStyle: { color: '#1A7A52' }, lineStyle: { width: 1.5 }, showSymbol: false },
                      ],
                    }}
                    style={{ height: 180 }}
                  />
                </>
              )}

              <h4 style={{ marginBottom: 8 }}>设备列表（{drawerData.devices?.length ?? 0} 台）</h4>
              <List
                size="small"
                dataSource={drawerData.devices ?? []}
                renderItem={(d: any) => (
                  <List.Item>
                    <Space>
                      <Badge color={STATUS_COLOR[d.status] ?? '#d9d9d9'} />
                      <code>{d.deviceCode}</code>
                      <Tag>{d.deviceType}</Tag>
                      <span style={{ color: '#8c8c8c', fontSize: 12 }}>{d.name ?? ''}</span>
                    </Space>
                  </List.Item>
                )}
                style={{ marginBottom: 16 }}
              />

              <h4 style={{ marginBottom: 8 }}>近期告警（最多10条）</h4>
              <List
                size="small"
                dataSource={drawerData.recentAlerts ?? []}
                locale={{ emptyText: '暂无告警' }}
                renderItem={(a: any) => (
                  <List.Item>
                    <Space>
                      <Tag color={LEVEL_COLOR[a.level] ?? 'default'}>{a.level?.toUpperCase()}</Tag>
                      <span style={{ fontSize: 12 }}>{a.alertType?.replace(/_/g, ' ')}</span>
                      <Tag color={a.status === 'open' ? 'red' : 'green'}>{a.status === 'open' ? '未解决' : '已解决'}</Tag>
                    </Space>
                  </List.Item>
                )}
              />
            </>
          ) : !drawerLoading && <Empty description="无数据" />}
        </Spin>
      </Drawer>
    </div>
  );
};

export default EdgeHubNodesPage;
