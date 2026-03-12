import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Table, Tag, Input, Select, Space, Button,
  Tooltip, Empty, Spin, Popconfirm, message, Row, Col,
  Drawer, Descriptions, Badge, Timeline,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, CheckCircleOutlined, InfoCircleOutlined,
  BellOutlined, RiseOutlined, StopOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useSearchParams } from 'react-router-dom';
import { apiClient, handleApiError } from '../services/api';
import styles from './EdgeHubAlertsPage.module.css';

const { Option } = Select;

// ── 类型 ──────────────────────────────────────────────────────────────────────

interface AlertItem {
  id:         string;
  storeId:    string;
  hubId:      string | null;
  deviceId:   string | null;
  level:      string;
  alertType:  string;
  message:    string | null;
  status:     string;
  resolvedAt: string | null;
  createdAt:  string | null;
}

interface PageMeta {
  page: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
}

// ── 常量 ──────────────────────────────────────────────────────────────────────

const LEVEL_COLOR: Record<string, string>  = { p1: 'red', p2: 'orange', p3: 'blue' };
const LEVEL_LABEL: Record<string, string>  = { p1: 'P1 严重', p2: 'P2 重要', p3: 'P3 一般' };

const ALERT_TYPES = [
  'headset_offline', 'hub_disconnect', 'device_error',
  'high_cpu', 'high_memory', 'firmware_outdated',
];

// ── 主组件 ────────────────────────────────────────────────────────────────────

const EdgeHubAlertsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const [alerts, setAlerts]       = useState<AlertItem[]>([]);
  const [meta, setMeta]           = useState<PageMeta>({ page: 1, pageSize: 20, total: 0, hasMore: false });
  const [loading, setLoading]     = useState(false);
  const [resolving, setResolving] = useState<string | null>(null);

  // 批量操作
  const [selectedIds,   setSelectedIds]   = useState<string[]>([]);
  const [bulkActioning, setBulkActioning] = useState<string | null>(null);

  // 详情抽屉
  const [drawerAlert, setDrawerAlert]   = useState<AlertItem | null>(null);
  const [actioning,   setActioning]     = useState<string | null>(null);

  // 筛选状态 — 从 URL 初始化
  const [keyword,   setKeyword]   = useState(() => searchParams.get('q')      ?? '');
  const [status,    setStatus]    = useState(() => searchParams.get('status')  ?? '');
  const [level,     setLevel]     = useState(() => searchParams.get('level')   ?? '');
  const [storeId,   setStoreId]   = useState(() => searchParams.get('store')   ?? '');
  const [page,      setPage]      = useState(() => Number(searchParams.get('page') ?? '1'));
  const pageSize = 20;

  const isMount = useRef(true);

  const fetchAlerts = useCallback(async (pg = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(pg), pageSize: String(pageSize) });
      if (status)  params.set('status',  status);
      if (level)   params.set('level',   level);
      if (storeId) params.set('store_id', storeId);

      const resp = await apiClient.get(`/api/v1/edge-hub/alerts?${params}`);
      let items: AlertItem[] = ((resp as any).data?.list) ?? [];

      // 客户端过滤关键词（alertType / message / storeId）
      if (keyword) {
        const kw = keyword.toLowerCase();
        items = items.filter(
          a =>
            a.alertType.includes(kw) ||
            a.storeId.toLowerCase().includes(kw) ||
            (a.message ?? '').toLowerCase().includes(kw)
        );
      }

      setAlerts(items);
      setMeta((resp as any).meta ?? { page: pg, pageSize, total: 0, hasMore: false });
      setPage(pg);
    } catch (err) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  }, [keyword, status, level, storeId]);

  // 首次挂载用 URL 恢复的 page；后续筛选变化重置到第 1 页
  useEffect(() => {
    if (isMount.current) {
      isMount.current = false;
      fetchAlerts(page);
    } else {
      fetchAlerts(1);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, level, storeId]);

  // URL 同步：筛选/翻页 → query string
  useEffect(() => {
    const p: Record<string, string> = {};
    if (keyword) p.q      = keyword;
    if (status)  p.status = status;
    if (level)   p.level  = level;
    if (storeId) p.store  = storeId;
    if (page > 1) p.page  = String(page);
    setSearchParams(p, { replace: true });
  }, [keyword, status, level, storeId, page, setSearchParams]);

  const handleBulkAction = async (action: 'resolve' | 'ignore') => {
    if (selectedIds.length === 0) return;
    setBulkActioning(action);
    try {
      const resp = await apiClient.post('/api/v1/edge-hub/alerts/bulk-action', {
        alert_ids: selectedIds,
        action,
      });
      const affected = (resp as any).data?.affected ?? selectedIds.length;
      message.success(`已${action === 'resolve' ? '解决' : '忽略'} ${affected} 条告警`);
      setSelectedIds([]);
      await fetchAlerts(page);
    } catch (err) {
      handleApiError(err);
    } finally {
      setBulkActioning(null);
    }
  };

  const handleResolve = async (alertId: string) => {
    setResolving(alertId);
    try {
      await apiClient.patch(`/api/v1/edge-hub/alerts/${alertId}/resolve`, {});
      message.success('告警已标记为已解决');
      await fetchAlerts(page);
      if (drawerAlert?.id === alertId) setDrawerAlert(prev => prev ? { ...prev, status: 'resolved' } : null);
    } catch (err) {
      handleApiError(err);
    } finally {
      setResolving(null);
    }
  };

  const handleAlertAction = async (alertId: string, action: 'ignore' | 'escalate') => {
    setActioning(action);
    try {
      const resp = await apiClient.patch(`/api/v1/edge-hub/alerts/${alertId}/${action}`, {});
      const updated = (resp as any).data as AlertItem;
      message.success(action === 'ignore' ? '告警已忽略' : '告警已升级');
      setDrawerAlert(updated);
      await fetchAlerts(page);
    } catch (err) {
      handleApiError(err);
    } finally {
      setActioning(null);
    }
  };

  // ── 快速统计 ─────────────────────────────────────────────────────────────────
  const p1Count    = alerts.filter(a => a.level === 'p1' && a.status === 'open').length;
  const p2Count    = alerts.filter(a => a.level === 'p2' && a.status === 'open').length;
  const openCount  = alerts.filter(a => a.status === 'open').length;

  // ── 列定义 ───────────────────────────────────────────────────────────────────
  const columns = [
    {
      title: '级别', dataIndex: 'level', width: 100,
      render: (v: string) => <Tag color={LEVEL_COLOR[v] ?? 'default'}>{LEVEL_LABEL[v] ?? v.toUpperCase()}</Tag>,
    },
    {
      title: '门店', dataIndex: 'storeId', width: 100,
    },
    {
      title: '告警类型', dataIndex: 'alertType', width: 170,
      render: (v: string) => (
        <code className={styles.alertType}>{v.replace(/_/g, ' ')}</code>
      ),
    },
    {
      title: '描述', dataIndex: 'message', ellipsis: true,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => (
        <Tag color={v === 'open' ? 'red' : v === 'resolved' ? 'green' : 'default'}>
          {v === 'open' ? '未解决' : v === 'resolved' ? '已解决' : v}
        </Tag>
      ),
    },
    {
      title: '发生时间', dataIndex: 'createdAt', width: 140,
      render: (v: string | null) => v ? (
        <Tooltip title={dayjs(v).format('YYYY-MM-DD HH:mm:ss')}>
          {dayjs(v).format('MM-DD HH:mm')}
        </Tooltip>
      ) : '—',
      sorter: (a: AlertItem, b: AlertItem) =>
        new Date(a.createdAt ?? 0).getTime() - new Date(b.createdAt ?? 0).getTime(),
    },
    {
      title: '解决时间', dataIndex: 'resolvedAt', width: 130,
      render: (v: string | null) => v ? dayjs(v).format('MM-DD HH:mm') : '—',
    },
    {
      title: '操作', key: 'actions', width: 130, fixed: 'right' as const,
      render: (_: unknown, r: AlertItem) => (
        <Space size={4}>
          <Button
            type="link" size="small" icon={<InfoCircleOutlined />}
            onClick={() => setDrawerAlert(r)}
          >
            详情
          </Button>
          {r.status === 'open' && (
            <Popconfirm
              title="确认标记此告警为已解决？"
              onConfirm={() => handleResolve(r.id)}
              okText="确认" cancelText="取消"
            >
              <Button
                type="link" size="small" icon={<CheckCircleOutlined />}
                loading={resolving === r.id}
              >
                解决
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>告警管理</h2>
        <span className={styles.total}>共 {meta.total} 条告警</span>
      </div>

      {/* 快速统计 */}
      <Row gutter={[12, 12]} className={styles.statsRow}>
        <Col xs={8}>
          <Card size="small" className={styles.statCard}>
            <div className={styles.statNum} style={{ color: '#C53030' }}>{p1Count}</div>
            <div className={styles.statLabel}>P1 严重（未解决）</div>
          </Card>
        </Col>
        <Col xs={8}>
          <Card size="small" className={styles.statCard}>
            <div className={styles.statNum} style={{ color: '#C8923A' }}>{p2Count}</div>
            <div className={styles.statLabel}>P2 重要（未解决）</div>
          </Card>
        </Col>
        <Col xs={8}>
          <Card size="small" className={styles.statCard}>
            <div className={styles.statNum} style={{ color: openCount > 0 ? '#0AAF9A' : '#1A7A52' }}>{openCount}</div>
            <div className={styles.statLabel}>未解决总数</div>
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 */}
      <Card size="small" className={styles.filterCard}>
        <Space wrap>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索告警类型 / 门店 / 描述"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            onPressEnter={() => fetchAlerts(1)}
            style={{ width: 240 }}
            allowClear
          />
          <Select
            placeholder="全部级别"
            value={level || undefined}
            onChange={v => setLevel(v ?? '')}
            style={{ width: 120 }}
            allowClear
          >
            <Option value="p1">P1 严重</Option>
            <Option value="p2">P2 重要</Option>
            <Option value="p3">P3 一般</Option>
          </Select>
          <Select
            placeholder="全部状态"
            value={status || undefined}
            onChange={v => setStatus(v ?? '')}
            style={{ width: 120 }}
            allowClear
          >
            <Option value="open">未解决</Option>
            <Option value="resolved">已解决</Option>
            <Option value="ignored">已忽略</Option>
          </Select>
          <Input
            placeholder="按门店ID过滤"
            value={storeId}
            onChange={e => setStoreId(e.target.value)}
            style={{ width: 140 }}
            allowClear
          />
          <Button icon={<ReloadOutlined />} onClick={() => fetchAlerts(page)}>刷新</Button>
        </Space>
      </Card>

      {/* 告警表格 */}
      <Spin spinning={loading}>
        <Card size="small" style={{ marginTop: 0 }}>
          {/* 批量操作栏 */}
          {selectedIds.length > 0 && (
            <div className={styles.bulkBar}>
              <span className={styles.bulkCount}>已选 {selectedIds.length} 条</span>
              <Space size={8}>
                <Popconfirm
                  title={`确认批量解决 ${selectedIds.length} 条告警？`}
                  onConfirm={() => handleBulkAction('resolve')}
                  okText="确认" cancelText="取消"
                >
                  <Button
                    size="small" type="primary" icon={<CheckCircleOutlined />}
                    loading={bulkActioning === 'resolve'}
                  >
                    批量解决
                  </Button>
                </Popconfirm>
                <Popconfirm
                  title={`确认批量忽略 ${selectedIds.length} 条告警？`}
                  onConfirm={() => handleBulkAction('ignore')}
                  okText="确认" cancelText="取消"
                >
                  <Button
                    size="small" icon={<StopOutlined />}
                    loading={bulkActioning === 'ignore'}
                  >
                    批量忽略
                  </Button>
                </Popconfirm>
                <Button size="small" onClick={() => setSelectedIds([])}>取消选择</Button>
              </Space>
            </div>
          )}
          {alerts.length === 0 && !loading ? (
            <Empty description="暂无告警数据" />
          ) : (
            <Table
              dataSource={alerts}
              columns={columns}
              rowKey="id"
              size="small"
              scroll={{ x: 1000 }}
              rowSelection={{
                selectedRowKeys: selectedIds,
                onChange: (keys) => setSelectedIds(keys as string[]),
                getCheckboxProps: (r: AlertItem) => ({
                  disabled: r.status !== 'open',
                }),
              }}
              pagination={{
                current: page,
                pageSize,
                total: meta.total,
                showSizeChanger: false,
                size: 'small',
                onChange: fetchAlerts,
              }}
              rowClassName={(r) => {
                if (r.level === 'p1' && r.status === 'open') return styles.p1Row;
                if (r.status === 'resolved') return styles.resolvedRow;
                return '';
              }}
            />
          )}
        </Card>
      </Spin>

      {/* 告警详情抽屉 */}
      <Drawer
        title={drawerAlert ? `告警详情 — ${drawerAlert.id.slice(0, 8)}…` : '告警详情'}
        open={!!drawerAlert}
        onClose={() => setDrawerAlert(null)}
        width={480}
        destroyOnClose
        extra={
          drawerAlert?.status === 'open' && (
            <Space>
              <Button
                size="small"
                loading={actioning === 'ignore'}
                onClick={() => handleAlertAction(drawerAlert!.id, 'ignore')}
              >
                忽略
              </Button>
              <Button
                size="small" danger
                loading={actioning === 'escalate'}
                onClick={() => handleAlertAction(drawerAlert!.id, 'escalate')}
              >
                升级
              </Button>
              <Button
                type="primary" size="small"
                loading={resolving === drawerAlert!.id}
                onClick={() => handleResolve(drawerAlert!.id)}
              >
                标记已解决
              </Button>
            </Space>
          )
        }
      >
        {drawerAlert && (<>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="级别">
              <Tag color={LEVEL_COLOR[drawerAlert.level] ?? 'default'}>
                {LEVEL_LABEL[drawerAlert.level] ?? drawerAlert.level.toUpperCase()}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={drawerAlert.status === 'open' ? 'red' : 'green'}>
                {drawerAlert.status === 'open' ? '未解决' : '已解决'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="门店">{drawerAlert.storeId}</Descriptions.Item>
            <Descriptions.Item label="告警类型">
              <code>{drawerAlert.alertType.replace(/_/g, ' ')}</code>
            </Descriptions.Item>
            <Descriptions.Item label="描述">{drawerAlert.message ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="Hub ID">{drawerAlert.hubId ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="设备 ID">{drawerAlert.deviceId ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="发生时间">
              {drawerAlert.createdAt ? dayjs(drawerAlert.createdAt).format('YYYY-MM-DD HH:mm:ss') : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="解决时间">
              {drawerAlert.resolvedAt ? dayjs(drawerAlert.resolvedAt).format('YYYY-MM-DD HH:mm:ss') : '—'}
            </Descriptions.Item>
          </Descriptions>

          <h4 style={{ margin: '16px 0 8px' }}>告警时间轴</h4>
          <Timeline
            items={[
              {
                dot: <BellOutlined style={{ color: LEVEL_COLOR[drawerAlert.level] ?? '#0AAF9A' }} />,
                children: (
                  <span>
                    <Tag color={LEVEL_COLOR[drawerAlert.level]}>{LEVEL_LABEL[drawerAlert.level] ?? drawerAlert.level.toUpperCase()}</Tag>
                    告警产生
                    <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>
                      {drawerAlert.createdAt ? dayjs(drawerAlert.createdAt).format('YYYY-MM-DD HH:mm:ss') : '—'}
                    </div>
                  </span>
                ),
              },
              ...(drawerAlert.level === 'p1' ? [{
                dot: <RiseOutlined style={{ color: '#C53030' }} />,
                children: <span><Tag color="red">P1</Tag> 已升级至最高级别</span>,
              }] : []),
              ...(drawerAlert.status !== 'open' ? [{
                dot: drawerAlert.status === 'resolved'
                  ? <CheckCircleOutlined style={{ color: '#1A7A52' }} />
                  : <StopOutlined style={{ color: '#8c8c8c' }} />,
                children: (
                  <span>
                    <Tag color={drawerAlert.status === 'resolved' ? 'green' : 'default'}>
                      {drawerAlert.status === 'resolved' ? '已解决' : '已忽略'}
                    </Tag>
                    <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>
                      {drawerAlert.resolvedAt ? dayjs(drawerAlert.resolvedAt).format('YYYY-MM-DD HH:mm:ss') : ''}
                    </div>
                  </span>
                ),
              }] : [{
                dot: <BellOutlined style={{ color: '#C8923A' }} />,
                color: 'orange',
                children: <span><Tag color="mint">处理中</Tag> 等待处理…</span>,
              }]),
            ]}
          />
        </>)}
      </Drawer>
    </div>
  );
};

export default EdgeHubAlertsPage;
