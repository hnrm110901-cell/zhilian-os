import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Statistic, Row, Col, Select, Tabs, Descriptions, Alert, Space, Popconfirm, Drawer, Timeline, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const HardwarePage: React.FC = () => {
  const [edgeNodes, setEdgeNodes] = useState<any[]>([]);
  const [shokzDevices, setShokzDevices] = useState<any[]>([]);
  const [deploymentCost, setDeploymentCost] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [auditDrawerOpen, setAuditDrawerOpen] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [recoveryDrawerOpen, setRecoveryDrawerOpen] = useState(false);
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [nodeAuditLogs, setNodeAuditLogs] = useState<any[]>([]);
  const [recoveryGuide, setRecoveryGuide] = useState<any>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.stores || res || []);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [nodesRes, devicesRes, costRes] = await Promise.allSettled([
        apiClient.get(`/api/v1/hardware/edge-node/store/${storeId}`),
        apiClient.get(`/api/v1/hardware/shokz/store/${storeId}`),
        apiClient.get('/api/v1/hardware/deployment/total-cost'),
      ]);
      if (nodesRes.status === 'fulfilled') setEdgeNodes(nodesRes.value?.nodes || nodesRes.value || []);
      if (devicesRes.status === 'fulfilled') setShokzDevices(devicesRes.value?.devices || devicesRes.value || []);
      if (costRes.status === 'fulfilled') setDeploymentCost(costRes.value);
    } catch (err: any) {
      handleApiError(err, '加载硬件数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadStores(); loadData(); }, [loadStores, loadData]);

  const syncNode = async (node: any) => {
    try {
      await apiClient.post(`/api/v1/hardware/edge-node/${node.node_id || node.id}/sync`);
      showSuccess('同步成功');
      loadData();
    } catch (err: any) {
      handleApiError(err, '同步失败');
    }
  };

  const refreshCredentialStatus = async (node: any) => {
    try {
      await apiClient.get(`/api/v1/hardware/edge-node/${node.node_id || node.id}/credential-status`);
      showSuccess('凭证状态已刷新');
      loadData();
    } catch (err: any) {
      handleApiError(err, '刷新凭证状态失败');
    }
  };

  const rotateSecret = async (node: any) => {
    try {
      await apiClient.post(`/api/v1/hardware/edge-node/${node.node_id || node.id}/rotate-secret`);
      showSuccess('凭证已轮换，边缘节点需使用新密钥继续上报');
      loadData();
    } catch (err: any) {
      handleApiError(err, '轮换凭证失败');
    }
  };

  const revokeSecret = async (node: any) => {
    try {
      await apiClient.post(`/api/v1/hardware/edge-node/${node.node_id || node.id}/revoke-secret`);
      showSuccess('凭证已吊销，节点下次上报会进入重注册流程');
      loadData();
    } catch (err: any) {
      handleApiError(err, '吊销凭证失败');
    }
  };

  const viewAuditLogs = async (node: any) => {
    const nodeId = node.node_id || node.id;
    setSelectedNode(node);
    setAuditDrawerOpen(true);
    setAuditLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/hardware/edge-node/${nodeId}/audit-logs`);
      setNodeAuditLogs(res.logs || []);
    } catch (err: any) {
      handleApiError(err, '加载审计记录失败');
      setNodeAuditLogs([]);
    } finally {
      setAuditLoading(false);
    }
  };

  const viewRecoveryGuide = async (node: any) => {
    const nodeId = node.node_id || node.id;
    setSelectedNode(node);
    setRecoveryDrawerOpen(true);
    setRecoveryLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/hardware/edge-node/${nodeId}/recovery-guide`);
      setRecoveryGuide(res);
    } catch (err: any) {
      handleApiError(err, '加载恢复指引失败');
      setRecoveryGuide(null);
    } finally {
      setRecoveryLoading(false);
    }
  };

  const nodeColumns: ColumnsType<any> = [
    { title: '节点ID', dataIndex: 'node_id', key: 'node_id', render: (v: string, r: any) => v || r.id },
    { title: '名称', dataIndex: 'device_name', key: 'device_name', render: (v: string, r: any) => v || r.name || '-' },
    {
      title: '网络模式', dataIndex: 'network_mode', key: 'mode',
      render: (v: string) => <Tag color={v === 'cloud' ? 'blue' : v === 'edge' ? 'orange' : 'purple'}>{v || '-'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => {
        const color = v === 'online' ? 'green' : v === 'syncing' ? 'gold' : v === 'error' ? 'red' : 'default';
        const text = v === 'online' ? '在线' : v === 'syncing' ? '同步中' : v === 'error' ? '异常' : '离线';
        return <Tag color={color}>{text}</Tag>;
      },
    },
    {
      title: '凭证状态', dataIndex: 'credential_ok', key: 'credential_ok',
      render: (_: boolean, record: any) => {
        const credential = record.credential_status || {};
        if (!credential.device_secret_active) {
          return <Tag color="red">需重注册</Tag>;
        }
        if (!credential.device_secret_persisted) {
          return <Tag color="gold">未持久化</Tag>;
        }
        return <Tag color="green">正常</Tag>;
      },
    },
    { title: '最后心跳', dataIndex: ['credential_status', 'last_heartbeat'], key: 'heartbeat', render: (v: string) => v || '-' },
    {
      title: '最近凭证操作', key: 'audit_summary',
      render: (_: any, record: any) => {
        const summary = record.audit_summary || {};
        if (!summary.available) {
          return <Tag>审计不可用</Tag>;
        }
        if (!summary.latest_action) {
          return <Tag>暂无记录</Tag>;
        }
        const color = summary.latest_action === 'edge_node_secret_revoke'
          ? 'red'
          : summary.latest_action === 'edge_node_secret_rotate'
            ? 'orange'
            : 'green';
        const text = summary.latest_action === 'edge_node_secret_revoke'
          ? '最近吊销'
          : summary.latest_action === 'edge_node_secret_rotate'
            ? '最近轮换'
            : '最近注册';
        return (
          <Space direction="vertical" size={2}>
            <Tag color={color}>{text}</Tag>
            <span style={{ color: '#666', fontSize: 12 }}>{summary.latest_at || '-'}</span>
          </Space>
        );
      },
    },
    {
      title: '离线队列', key: 'offline_queue',
      render: (_: any, record: any) => {
        const queueDepth = record.pending_status_queue ?? record.credential_status?.pending_status_queue ?? 0;
        const lastError = record.last_queue_error ?? record.credential_status?.last_queue_error;
        if (queueDepth > 0) {
          return (
            <Space direction="vertical" size={2}>
              <Tag color="orange">{`积压 ${queueDepth}`}</Tag>
              <span style={{ color: '#666', fontSize: 12 }}>{lastError || '等待恢复补发'}</span>
            </Space>
          );
        }
        return <Tag color="green">无积压</Tag>;
      },
    },
    {
      title: '资源', key: 'resources',
      render: (_: any, record: any) => (
        <Space size={4}>
          <Tag>{record.cpu_usage != null ? `CPU ${record.cpu_usage}%` : 'CPU -'}</Tag>
          <Tag>{record.memory_usage != null ? `内存 ${record.memory_usage}%` : '内存 -'}</Tag>
          <Tag>{record.temperature != null ? `温度 ${record.temperature}°C` : '温度 -'}</Tag>
        </Space>
      ),
    },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Space wrap>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => syncNode(record)}>同步</Button>
          <Button size="small" onClick={() => refreshCredentialStatus(record)}>状态</Button>
          <Button size="small" onClick={() => viewRecoveryGuide(record)}>恢复指引</Button>
          <Button size="small" onClick={() => viewAuditLogs(record)}>审计记录</Button>
          <Button size="small" onClick={() => rotateSecret(record)}>轮换密钥</Button>
          <Popconfirm
            title="吊销当前节点凭证？"
            description="吊销后节点当前密钥将失效，下次上报会触发重注册。"
            onConfirm={() => revokeSecret(record)}
            okText="吊销"
            cancelText="取消"
          >
            <Button size="small" danger>吊销密钥</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const shokzColumns: ColumnsType<any> = [
    { title: '设备ID', dataIndex: 'device_id', key: 'device_id', render: (v: string, r: any) => v || r.id },
    { title: '设备型号', dataIndex: 'model', key: 'model' },
    { title: '绑定员工', dataIndex: 'employee_name', key: 'employee', render: (v: string) => v || '-' },
    {
      title: '连接状态', dataIndex: 'connected', key: 'connected',
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '已连接' : '未连接'}</Tag>,
    },
    { title: '电量', dataIndex: 'battery_level', key: 'battery', render: (v: number) => v != null ? `${v}%` : '-' },
  ];

  const tabItems = [
    {
      key: 'edge',
      label: '边缘节点（树莓派）',
      children: (
        <Card loading={loading}>
          <Alert
            type="info"
            showIcon
            message="红色“需重注册”表示节点凭证已失效或被吊销；可先查看状态，再决定轮换或重注册。"
            style={{ marginBottom: 16 }}
          />
          <Table columns={nodeColumns} dataSource={edgeNodes} rowKey={(r, i) => r.node_id || r.id || String(i)} />
        </Card>
      ),
    },
    {
      key: 'shokz',
      label: 'Shokz 骨传导设备',
      children: (
        <Card loading={loading}>
          <Table columns={shokzColumns} dataSource={shokzDevices} rowKey={(r, i) => r.device_id || r.id || String(i)} />
        </Card>
      ),
    },
    {
      key: 'cost',
      label: '部署成本',
      children: deploymentCost ? (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}><Card><Statistic title="硬件总成本" prefix="¥" value={(deploymentCost.hardware_cost || 0).toFixed(0)} /></Card></Col>
            <Col span={6}><Card><Statistic title="安装成本" prefix="¥" value={(deploymentCost.installation_cost || 0).toFixed(0)} /></Card></Col>
            <Col span={6}><Card><Statistic title="维护成本/年" prefix="¥" value={(deploymentCost.annual_maintenance || 0).toFixed(0)} /></Card></Col>
            <Col span={6}><Card><Statistic title="总部署成本" prefix="¥" value={(deploymentCost.total_cost || 0).toFixed(0)} /></Card></Col>
          </Row>
          <Card title="推荐配置">
            <Descriptions bordered column={2}>
              <Descriptions.Item label="树莓派数量">{deploymentCost.recommended_nodes || '-'} 台</Descriptions.Item>
              <Descriptions.Item label="Shokz设备数量">{deploymentCost.recommended_shokz || '-'} 台</Descriptions.Item>
              <Descriptions.Item label="预计回收周期">{deploymentCost.payback_months || '-'} 个月</Descriptions.Item>
              <Descriptions.Item label="预计年节省">¥{(deploymentCost.annual_savings || 0).toFixed(0)}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Alert message="硬件部署可显著提升离线可用性和语音交互体验" type="info" style={{ marginTop: 16 }} />
        </div>
      ) : <Card loading={loading} />,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
          {stores.length > 0 ? stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          )) : <Option value="STORE001">门店001</Option>}
        </Select>
      </div>
      <Tabs items={tabItems} />
      <Drawer
        title={`节点恢复指引${selectedNode ? ` · ${selectedNode.device_name || selectedNode.node_id || selectedNode.id}` : ''}`}
        placement="right"
        width={560}
        open={recoveryDrawerOpen}
        onClose={() => setRecoveryDrawerOpen(false)}
      >
        <Alert
          type={recoveryGuide?.requires_rebootstrap ? 'warning' : 'info'}
          showIcon
          style={{ marginBottom: 16 }}
          message={recoveryGuide?.requires_rebootstrap ? '当前节点需要重新走 bootstrap 注册。' : '当前节点凭证仍有效，优先按指引排查配置和网络。'}
        />
        <Descriptions bordered column={1} size="small" style={{ marginBottom: 16 }}>
          <Descriptions.Item label="服务名">{recoveryGuide?.service_name || 'zhilian-edge-node.service'}</Descriptions.Item>
          <Descriptions.Item label="配置文件">{recoveryGuide?.config_file || '/etc/zhilian-edge/edge-node.env'}</Descriptions.Item>
          <Descriptions.Item label="状态文件">{recoveryGuide?.state_file || '/var/lib/zhilian-edge/node_state.json'}</Descriptions.Item>
          <Descriptions.Item label="Bootstrap">
            <Tag color={recoveryGuide?.bootstrap_token_configured ? 'green' : 'red'}>
              {recoveryGuide?.bootstrap_token_configured ? '已配置' : '未配置'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="必需环境变量">
            <Space wrap>
              {(recoveryGuide?.required_env || []).map((item: string) => <Tag key={item}>{item}</Tag>)}
            </Space>
          </Descriptions.Item>
        </Descriptions>
        <Typography.Title level={5}>恢复步骤</Typography.Title>
        <Timeline
          style={{ marginBottom: 16 }}
          pending={recoveryLoading ? '加载中...' : undefined}
          items={(recoveryGuide?.steps || []).map((step: string, index: number) => ({
            children: `${index + 1}. ${step}`,
          }))}
        />
        <Typography.Title level={5}>安装命令模板</Typography.Title>
        <Typography.Paragraph
          copyable={recoveryGuide?.installer_command_template ? { text: recoveryGuide.installer_command_template } : false}
          style={{ whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12, borderRadius: 8, marginBottom: 0 }}
        >
          {recoveryGuide?.installer_command_template || '加载中...'}
        </Typography.Paragraph>
      </Drawer>
      <Drawer
        title={`节点审计记录${selectedNode ? ` · ${selectedNode.device_name || selectedNode.node_id || selectedNode.id}` : ''}`}
        placement="right"
        width={520}
        open={auditDrawerOpen}
        onClose={() => setAuditDrawerOpen(false)}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="这里展示树莓派节点的注册、凭证轮换、凭证吊销等运维动作，便于排查设备重新配对和凭证异常。"
        />
        <Timeline
          pending={auditLoading ? '加载中...' : undefined}
          items={nodeAuditLogs.map((log: any) => ({
            color:
              log.action === 'edge_node_secret_revoke' ? 'red' :
                log.action === 'edge_node_secret_rotate' ? 'orange' :
                  'green',
            children: (
              <div>
                <div style={{ fontWeight: 600 }}>{log.description || log.action}</div>
                <div style={{ color: '#666', marginTop: 4 }}>
                  {log.created_at || '-'} · {log.username || log.user_id || 'system'}
                </div>
                <div style={{ marginTop: 4 }}>
                  <Tag>{log.action}</Tag>
                  <Tag>{log.status || 'success'}</Tag>
                </div>
              </div>
            ),
          }))}
        />
      </Drawer>
    </div>
  );
};

export default HardwarePage;
