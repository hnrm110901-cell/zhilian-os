/**
 * OpsMonitoringPage — 智链OS 运维监控大屏
 *
 * 对应方案 第八章：总部一屏掌控所有门店
 * - 门店健康状态卡片（绿/黄/红）
 * - KPI 总览：设备在线率 / 网络可用率 / 系统可用率 / 食安达标率
 * - 活跃告警流
 * - 食安合规仪表盘
 * - 门店详情下钻（L1/L2/L3 三层）
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Statistic, Badge, Tag, Table, Button,
  Select, Spin, Alert, Typography, Space, Progress, Divider,
  Tooltip, Modal, Descriptions,
} from 'antd';
import {
  ReloadOutlined, WarningOutlined, CheckCircleOutlined,
  CloseCircleOutlined, DashboardOutlined, WifiOutlined,
  DatabaseOutlined, SafetyOutlined, RightOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import apiClient, { handleApiError } from '../services/api';

const { Title, Text } = Typography;
const { Option } = Select;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface LayerStatus {
  score: number;
  status: 'healthy' | 'warning' | 'critical';
  alert_count: number;
  [key: string]: unknown;
}

interface StoreDashboard {
  store_id: string;
  overall_status: 'healthy' | 'warning' | 'critical';
  overall_score: number;
  active_alerts: number;
  window_minutes: number;
  generated_at: string;
  layers: {
    l1_device: LayerStatus & { total_readings: number };
    l2_network: LayerStatus & { availability_pct: number };
    l3_system: LayerStatus & { uptime_pct: number; down_list: string[] };
  };
  food_safety: {
    total_checks: number;
    violations: number;
    compliance_rate_pct: number;
    status: string;
  };
  llm_summary?: string;
}

interface AlertRecord {
  store_id: string;
  component: string;
  description: string;
  severity: string;
  event_type: string;
  created_at: string;
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

const statusColor = (s: string) => {
  if (s === 'healthy') return '#52c41a';
  if (s === 'warning') return '#faad14';
  return '#ff4d4f';
};

const statusBadge = (s: string): 'success' | 'warning' | 'error' | 'default' => {
  if (s === 'healthy') return 'success';
  if (s === 'warning') return 'warning';
  return 'error';
};

const statusLabel = (s: string) => {
  if (s === 'healthy') return '正常';
  if (s === 'warning') return '告警';
  return '故障';
};

const severityTag = (sev: string) => {
  const map: Record<string, string> = {
    critical: 'red', high: 'orange', medium: 'gold', low: 'blue',
  };
  return <Tag color={map[sev] || 'default'}>{sev.toUpperCase()}</Tag>;
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const OpsMonitoringPage: React.FC = () => {
  const [storeIds, setStoreIds] = useState<string[]>([]);
  const [selectedStore, setSelectedStore] = useState<string>('');
  const [dashboard, setDashboard] = useState<StoreDashboard | null>(null);
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [windowMinutes, setWindowMinutes] = useState(30);
  const [lastRefresh, setLastRefresh] = useState<string>('');

  // 加载门店列表
  useEffect(() => {
    apiClient.get('/api/v1/stores?limit=50')
      .then(res => {
        const ids: string[] = (res.data?.items || res.data?.stores || []).map(
          (s: { id: string }) => s.id
        );
        setStoreIds(ids);
        if (ids.length > 0) setSelectedStore(ids[0]);
      })
      .catch(() => {
        // fallback：使用示例门店ID
        setStoreIds(['STORE001', 'STORE002', 'STORE003']);
        setSelectedStore('STORE001');
      });
  }, []);

  // 加载门店健康总览
  const loadDashboard = useCallback(async () => {
    if (!selectedStore) return;
    setLoading(true);
    try {
      const res = await apiClient.get(
        `/api/v1/ops/dashboard/${selectedStore}?window_minutes=${windowMinutes}`
      );
      setDashboard(res.data);
      setLastRefresh(dayjs().format('HH:mm:ss'));
    } catch (err) {
      handleApiError(err, '加载运维大屏失败');
    } finally {
      setLoading(false);
    }
  }, [selectedStore, windowMinutes]);

  // 加载活跃告警（复用已有 OpsEvents API）
  const loadAlerts = useCallback(async () => {
    if (!selectedStore) return;
    setAlertsLoading(true);
    try {
      const res = await apiClient.get(
        `/api/v1/ops/events?store_id=${selectedStore}&status=open&limit=20`
      );
      setAlerts(res.data?.items || res.data || []);
    } catch {
      setAlerts([]);
    } finally {
      setAlertsLoading(false);
    }
  }, [selectedStore]);

  useEffect(() => {
    if (selectedStore) {
      loadDashboard();
      loadAlerts();
    }
  }, [selectedStore, windowMinutes, loadDashboard, loadAlerts]);

  // ── 告警表格列 ────────────────────────────────────────────────────────────

  const alertColumns: ColumnsType<AlertRecord> = [
    {
      title: '级别',
      dataIndex: 'severity',
      width: 90,
      render: (v) => severityTag(v),
    },
    {
      title: '组件',
      dataIndex: 'component',
      width: 120,
      ellipsis: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'event_type',
      width: 110,
      render: (v) => <Tag>{v}</Tag>,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 90,
      render: (v) => dayjs(v).format('HH:mm:ss'),
    },
  ];

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  const l1 = dashboard?.layers.l1_device;
  const l2 = dashboard?.layers.l2_network;
  const l3 = dashboard?.layers.l3_system;
  const fs = dashboard?.food_safety;

  return (
    <div style={{ padding: 24, background: '#f0f2f5', minHeight: '100vh' }}>
      {/* 标题栏 */}
      <Row align="middle" justify="space-between" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <DashboardOutlined style={{ marginRight: 8 }} />
            运维监控大屏
          </Title>
          {lastRefresh && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              上次刷新: {lastRefresh}
            </Text>
          )}
        </Col>
        <Col>
          <Space>
            <Select value={selectedStore} onChange={setSelectedStore} style={{ width: 160 }}>
              {storeIds.map(id => <Option key={id} value={id}>{id}</Option>)}
            </Select>
            <Select value={windowMinutes} onChange={setWindowMinutes} style={{ width: 110 }}>
              <Option value={15}>最近15分钟</Option>
              <Option value={30}>最近30分钟</Option>
              <Option value={60}>最近1小时</Option>
              <Option value={1440}>最近24小时</Option>
            </Select>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => { loadDashboard(); loadAlerts(); }}
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        </Col>
      </Row>

      <Spin spinning={loading}>
        {/* ── 总体状态 + KPI卡片 ── */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {/* 总体健康 */}
          <Col xs={24} sm={6}>
            <Card bodyStyle={{ textAlign: 'center', padding: 20 }}>
              <Badge
                status={statusBadge(dashboard?.overall_status || 'healthy')}
                text={
                  <Text style={{
                    fontSize: 16, fontWeight: 600,
                    color: statusColor(dashboard?.overall_status || 'healthy'),
                  }}>
                    {statusLabel(dashboard?.overall_status || 'healthy')}
                  </Text>
                }
              />
              <Statistic
                value={dashboard?.overall_score ?? '--'}
                suffix="分"
                valueStyle={{
                  color: statusColor(dashboard?.overall_status || 'healthy'),
                  fontSize: 32,
                }}
              />
              <Text type="secondary">综合健康分</Text>
              <br />
              {(dashboard?.active_alerts ?? 0) > 0 && (
                <Tag color="red" style={{ marginTop: 8 }}>
                  <WarningOutlined /> {dashboard?.active_alerts} 条活跃告警
                </Tag>
              )}
            </Card>
          </Col>

          {/* L1 设备层 */}
          <Col xs={24} sm={6}>
            <Card
              title={<><DashboardOutlined style={{ color: '#1890ff' }} /> L1 设备层</>}
              bodyStyle={{ padding: 16 }}
            >
              <Progress
                percent={l1?.score ?? 100}
                strokeColor={statusColor(l1?.status || 'healthy')}
                size="small"
              />
              <Row style={{ marginTop: 8 }}>
                <Col span={12}><Statistic title="采集次数" value={l1?.total_readings ?? 0} /></Col>
                <Col span={12}><Statistic title="告警" value={l1?.alert_count ?? 0} valueStyle={{ color: '#ff4d4f' }} /></Col>
              </Row>
            </Card>
          </Col>

          {/* L2 网络层 */}
          <Col xs={24} sm={6}>
            <Card
              title={<><WifiOutlined style={{ color: '#52c41a' }} /> L2 网络层</>}
              bodyStyle={{ padding: 16 }}
            >
              <Progress
                percent={l2?.availability_pct ?? 100}
                strokeColor={statusColor(l2?.status || 'healthy')}
                size="small"
              />
              <Row style={{ marginTop: 8 }}>
                <Col span={12}><Statistic title="可用率" value={`${l2?.availability_pct ?? 100}%`} /></Col>
                <Col span={12}><Statistic title="告警" value={l2?.alert_count ?? 0} valueStyle={{ color: '#ff4d4f' }} /></Col>
              </Row>
            </Card>
          </Col>

          {/* L3 系统层 */}
          <Col xs={24} sm={6}>
            <Card
              title={<><DatabaseOutlined style={{ color: '#722ed1' }} /> L3 系统层</>}
              bodyStyle={{ padding: 16 }}
            >
              <Progress
                percent={l3?.uptime_pct ?? 100}
                strokeColor={statusColor(l3?.status || 'healthy')}
                size="small"
              />
              <Row style={{ marginTop: 8 }}>
                <Col span={12}><Statistic title="正常系统" value={`${(l3?.total_systems ?? 0) - (l3?.down_systems ?? 0)}/${l3?.total_systems ?? 0}`} /></Col>
                <Col span={12}><Statistic title="P0宕机" value={l3?.p0_down ?? 0} valueStyle={{ color: l3?.p0_down ? '#ff4d4f' : '#52c41a' }} /></Col>
              </Row>
              {(l3?.down_list?.length ?? 0) > 0 && (
                <div style={{ marginTop: 6 }}>
                  {l3!.down_list.map(s => <Tag key={s} color="red">{s}</Tag>)}
                </div>
              )}
            </Card>
          </Col>
        </Row>

        {/* ── 食安 + 告警流 ── */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          {/* 食安合规 */}
          <Col xs={24} sm={8}>
            <Card
              title={<><SafetyOutlined style={{ color: '#fa8c16' }} /> 食安合规</>}
              extra={
                <Button
                  type="link" size="small"
                  onClick={() => window.open(`/food-safety/${selectedStore}`, '_blank')}
                >
                  详情 <RightOutlined />
                </Button>
              }
            >
              <Row>
                <Col span={12} style={{ textAlign: 'center' }}>
                  <Progress
                    type="circle"
                    percent={fs?.compliance_rate_pct ?? 100}
                    strokeColor={fs?.violations ? '#ff4d4f' : '#52c41a'}
                    width={80}
                  />
                  <br />
                  <Text type="secondary">合规率</Text>
                </Col>
                <Col span={12}>
                  <Statistic
                    title="检测次数"
                    value={fs?.total_checks ?? 0}
                    style={{ marginBottom: 8 }}
                  />
                  <Statistic
                    title="违规次数"
                    value={fs?.violations ?? 0}
                    valueStyle={{ color: (fs?.violations ?? 0) > 0 ? '#ff4d4f' : '#52c41a' }}
                  />
                </Col>
              </Row>
              {(fs?.violations ?? 0) > 0 && (
                <Alert
                  type="error"
                  showIcon
                  message={`存在 ${fs?.violations} 条食安违规，请立即处置`}
                  style={{ marginTop: 12 }}
                />
              )}
            </Card>
          </Col>

          {/* 活跃告警 */}
          <Col xs={24} sm={16}>
            <Card
              title={<><WarningOutlined style={{ color: '#ff4d4f' }} /> 活跃告警</>}
              extra={
                <Button size="small" icon={<ReloadOutlined />} onClick={loadAlerts} loading={alertsLoading}>
                  刷新
                </Button>
              }
              bodyStyle={{ padding: 0 }}
            >
              <Table
                dataSource={alerts}
                columns={alertColumns}
                rowKey={(r, i) => `${r.created_at}-${i}`}
                size="small"
                pagination={false}
                scroll={{ y: 200 }}
                loading={alertsLoading}
                locale={{ emptyText: <CheckCircleOutlined style={{ color: '#52c41a' }} /> }}
              />
            </Card>
          </Col>
        </Row>

        {/* ── LLM 摘要 + 详情入口 ── */}
        {dashboard?.llm_summary && (
          <Card
            title="AI 运维建议"
            style={{ marginBottom: 16 }}
            extra={
              <Button type="primary" onClick={() => setDetailVisible(true)}>
                查看三层详情
              </Button>
            }
          >
            <Text style={{ whiteSpace: 'pre-wrap' }}>{dashboard.llm_summary}</Text>
          </Card>
        )}

        {!dashboard?.llm_summary && (
          <div style={{ textAlign: 'right', marginBottom: 16 }}>
            <Button type="primary" onClick={() => setDetailVisible(true)}>
              查看三层详情
            </Button>
          </div>
        )}
      </Spin>

      {/* ── 三层详情弹窗 ── */}
      <Modal
        title={`门店 ${selectedStore} — 三层健康详情`}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={null}
        width={700}
      >
        {dashboard ? (
          <>
            <Divider orientation="left">L1 设备层</Divider>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="健康分">{l1?.score}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor(l1?.status || 'healthy')}>{statusLabel(l1?.status || 'healthy')}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="采集条数">{l1?.total_readings}</Descriptions.Item>
              <Descriptions.Item label="告警条数">{l1?.alert_count}</Descriptions.Item>
            </Descriptions>

            <Divider orientation="left">L2 网络层</Divider>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="健康分">{l2?.score}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor(l2?.status || 'healthy')}>{statusLabel(l2?.status || 'healthy')}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="可用率">{l2?.availability_pct}%</Descriptions.Item>
              <Descriptions.Item label="不可达次数">{l2?.unavailable}</Descriptions.Item>
            </Descriptions>

            <Divider orientation="left">L3 系统层</Divider>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="健康分">{l3?.score}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor(l3?.status || 'healthy')}>{statusLabel(l3?.status || 'healthy')}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="正常系统">{(l3?.total_systems ?? 0) - (l3?.down_systems ?? 0)} / {l3?.total_systems}</Descriptions.Item>
              <Descriptions.Item label="P0宕机">{l3?.p0_down}</Descriptions.Item>
              {(l3?.down_list?.length ?? 0) > 0 && (
                <Descriptions.Item label="宕机系统" span={2}>
                  {l3!.down_list.map(s => <Tag key={s} color="red">{s}</Tag>)}
                </Descriptions.Item>
              )}
            </Descriptions>

            <Divider orientation="left">食安合规</Divider>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="合规率">{fs?.compliance_rate_pct}%</Descriptions.Item>
              <Descriptions.Item label="状态">
                {fs?.violations === 0
                  ? <Tag icon={<CheckCircleOutlined />} color="success">合规</Tag>
                  : <Tag icon={<CloseCircleOutlined />} color="error">违规</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="检测次数">{fs?.total_checks}</Descriptions.Item>
              <Descriptions.Item label="违规次数">{fs?.violations}</Descriptions.Item>
            </Descriptions>
          </>
        ) : (
          <Spin />
        )}
      </Modal>
    </div>
  );
};

export default OpsMonitoringPage;
