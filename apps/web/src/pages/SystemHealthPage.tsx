import React, { useState, useCallback, useEffect } from 'react';
import { Card, Row, Col, Tag, Table, Badge, Button, Space, Descriptions, Spin, Alert } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  HeartOutlined,
  ApiOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

interface HealthStatus {
  status: string;
  timestamp?: string;
  version?: string;
  environment?: string;
  uptime_seconds?: number;
  database?: string;
  redis?: string;
  message_queue?: string;
}

interface AgentStatus {
  agent_id: string;
  agent_type: string;
  status: string;
  store_id?: string;
  last_heartbeat?: string;
  tasks_completed?: number;
}

interface ExternalSystem {
  system_name: string;
  status: string;
  last_check?: string;
  response_time_ms?: number;
  error_message?: string;
}

const statusColor: Record<string, string> = {
  healthy: 'green', ok: 'green', connected: 'green', running: 'green', active: 'green',
  degraded: 'orange', warning: 'orange', slow: 'orange',
  unhealthy: 'red', error: 'red', disconnected: 'red', failed: 'red', stopped: 'red',
};

const statusIcon = (s: string) => {
  const c = statusColor[s?.toLowerCase()] || 'default';
  if (c === 'green') return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
  if (c === 'red') return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
  return <HeartOutlined style={{ color: '#faad14' }} />;
};

const SystemHealthPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [externalSystems, setExternalSystems] = useState<ExternalSystem[]>([]);
  const [readyStatus, setReadyStatus] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [healthRes, agentsRes, externalRes, readyRes, liveRes] = await Promise.allSettled([
        apiClient.get('/health'),
        apiClient.get('/agents'),
        apiClient.get('/external-systems'),
        apiClient.get('/ready'),
        apiClient.get('/live'),
      ]);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value.data);
      if (agentsRes.status === 'fulfilled') setAgents(agentsRes.value.data?.agents || agentsRes.value.data || []);
      if (externalRes.status === 'fulfilled') setExternalSystems(externalRes.value.data?.systems || externalRes.value.data || []);
      if (readyRes.status === 'fulfilled') setReadyStatus(readyRes.value.data?.status || 'ok');
      if (liveRes.status === 'fulfilled') setLiveStatus(liveRes.value.data?.status || 'ok');
    } catch (err) {
      handleApiError(err, '加载系统健康状态失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const agentColumns = [
    { title: 'Agent ID', dataIndex: 'agent_id', key: 'agent_id', ellipsis: true },
    { title: '类型', dataIndex: 'agent_type', key: 'agent_type' },
    { title: '门店', dataIndex: 'store_id', key: 'store_id', render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={statusColor[s?.toLowerCase()] || 'default'}>{s}</Tag>,
    },
    { title: '完成任务', dataIndex: 'tasks_completed', key: 'tasks_completed', render: (v: number) => v ?? '-' },
    { title: '最后心跳', dataIndex: 'last_heartbeat', key: 'last_heartbeat', render: (v: string) => v ? new Date(v).toLocaleString() : '-' },
  ];

  const extColumns = [
    { title: '系统名称', dataIndex: 'system_name', key: 'system_name' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={statusColor[s?.toLowerCase()] || 'default'}>{s}</Tag>,
    },
    { title: '响应时间', dataIndex: 'response_time_ms', key: 'response_time_ms', render: (v: number) => v != null ? `${v} ms` : '-' },
    { title: '最后检查', dataIndex: 'last_check', key: 'last_check', render: (v: string) => v ? new Date(v).toLocaleString() : '-' },
    { title: '错误信息', dataIndex: 'error_message', key: 'error_message', render: (v: string) => v ? <span style={{ color: '#ff4d4f' }}>{v}</span> : '-' },
  ];

  const overallStatus = health?.status?.toLowerCase();
  const isHealthy = overallStatus === 'healthy' || overallStatus === 'ok';

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={loadAll} loading={loading}>刷新</Button>
      </Space>

      {health && !isHealthy && (
        <Alert type="error" message={`系统状态异常: ${health.status}`} style={{ marginBottom: 16 }} showIcon />
      )}

      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>{statusIcon(health?.status || '')}</div>
                <div style={{ fontWeight: 600, fontSize: 16 }}>系统健康</div>
                <Tag color={statusColor[health?.status?.toLowerCase() || ''] || 'default'} style={{ marginTop: 4 }}>
                  {health?.status || '加载中'}
                </Tag>
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}><ApiOutlined style={{ color: readyStatus === 'ok' ? '#52c41a' : '#faad14' }} /></div>
                <div style={{ fontWeight: 600, fontSize: 16 }}>就绪探针</div>
                <Badge status={readyStatus === 'ok' ? 'success' : 'warning'} text={readyStatus || '检查中'} />
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}><HeartOutlined style={{ color: liveStatus === 'ok' ? '#52c41a' : '#faad14' }} /></div>
                <div style={{ fontWeight: 600, fontSize: 16 }}>存活探针</div>
                <Badge status={liveStatus === 'ok' ? 'success' : 'warning'} text={liveStatus || '检查中'} />
              </div>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}><RobotOutlined style={{ color: '#1677ff' }} /></div>
                <div style={{ fontWeight: 600, fontSize: 16 }}>活跃 Agent</div>
                <div style={{ fontSize: 24, color: '#1677ff' }}>{agents.length}</div>
              </div>
            </Card>
          </Col>
        </Row>

        {health && (
          <Card title="系统详情" style={{ marginTop: 16 }}>
            <Descriptions column={{ xs: 1, sm: 2, md: 3 }} bordered size="small">
              <Descriptions.Item label="版本">{health.version || '-'}</Descriptions.Item>
              <Descriptions.Item label="环境">{health.environment || '-'}</Descriptions.Item>
              <Descriptions.Item label="运行时长">{health.uptime_seconds != null ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m` : '-'}</Descriptions.Item>
              <Descriptions.Item label="数据库">
                <Tag color={statusColor[health.database?.toLowerCase() || ''] || 'default'}>{health.database || '-'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Redis">
                <Tag color={statusColor[health.redis?.toLowerCase() || ''] || 'default'}>{health.redis || '-'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="消息队列">
                <Tag color={statusColor[health.message_queue?.toLowerCase() || ''] || 'default'}>{health.message_queue || '-'}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        <Card title="Agent 状态" style={{ marginTop: 16 }}>
          <Table
            columns={agentColumns}
            dataSource={agents}
            rowKey={(r, i) => r.agent_id || String(i)}
            size="small"
            pagination={{ pageSize: 10 }}
            locale={{ emptyText: '暂无 Agent 数据' }}
          />
        </Card>

        <Card title="外部系统" style={{ marginTop: 16 }}>
          <Table
            columns={extColumns}
            dataSource={externalSystems}
            rowKey={(r, i) => r.system_name || String(i)}
            size="small"
            pagination={false}
            locale={{ emptyText: '暂无外部系统数据' }}
          />
        </Card>
      </Spin>
    </div>
  );
};

export default SystemHealthPage;
