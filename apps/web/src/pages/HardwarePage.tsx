import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Statistic, Row, Col, Select, Tabs, Descriptions, Alert, Input, List, Space, Popconfirm, Drawer, Timeline, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

export const getNetworkModeMeta = (networkMode?: string) => {
  switch (networkMode) {
    case 'cloud':
      return { color: 'blue', label: '云端模式' };
    case 'edge':
      return { color: 'gold', label: '边缘模式' };
    case 'hybrid':
      return { color: 'purple', label: '混合模式' };
    default:
      return { color: 'default', label: networkMode || '-' };
  }
};

export const getNodeStatusMeta = (status?: string) => {
  switch (status) {
    case 'online':
      return { color: 'green', label: '在线' };
    case 'syncing':
      return { color: 'processing', label: '同步中' };
    case 'error':
      return { color: 'red', label: '异常' };
    case 'offline':
      return { color: 'default', label: '离线' };
    default:
      return { color: 'default', label: status || '-' };
  }
};

export const getShokzStatusMeta = (status?: string) => {
  switch (status) {
    case 'connected':
      return { color: 'green', label: '已连接' };
    case 'pairing':
      return { color: 'processing', label: '配对中' };
    case 'charging':
      return { color: 'blue', label: '充电中' };
    case 'low_battery':
      return { color: 'orange', label: '低电量' };
    case 'disconnected':
      return { color: 'default', label: '未连接' };
    default:
      return { color: 'default', label: status || '-' };
  }
};

export const formatIsoDateTime = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
};

export const summarizeDeploymentCost = (payload: any) => {
  const summary = payload?.summary || {};
  return {
    hardwareCost: Number(summary.total_hardware_cost || 0),
    implementationCost: Number(summary.total_implementation_cost || 0),
    totalCost: Number(summary.total_cost_per_store || 0),
    deploymentTimeHours: Number(summary.deployment_time_hours || 0),
    roiMonths: summary.roi_months ?? '-',
    recommendedNodes: 1,
    recommendedShokz: 2,
  };
};

export const getChecklistStatusMeta = (passed?: boolean) => passed
  ? { color: 'green', label: '通过' }
  : { color: 'orange', label: '待处理' };

const HardwarePage: React.FC = () => {
  const [edgeNodes, setEdgeNodes] = useState<any[]>([]);
  const [shokzDevices, setShokzDevices] = useState<any[]>([]);
  const [deploymentCost, setDeploymentCost] = useState<any>(null);
  const [commissioning, setCommissioning] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoadingKey, setActionLoadingKey] = useState<string | null>(null);
  const [storeId, setStoreId] = useState(localStorage.getItem('store_id') || '');
  const [stores, setStores] = useState<any[]>([]);
  const [auditDrawerOpen, setAuditDrawerOpen] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [recoveryDrawerOpen, setRecoveryDrawerOpen] = useState(false);
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [nodeAuditLogs, setNodeAuditLogs] = useState<any[]>([]);
  const [recoveryGuide, setRecoveryGuide] = useState<any>(null);
  const [testVoiceText, setTestVoiceText] = useState('测试播报：请确认 Shokz 耳机已连接，后厨催单联调开始。');

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

  const loadCommissioning = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/hardware/shokz/store/${storeId}/commissioning-diagnostic`);
      setCommissioning(res.commissioning || null);
    } catch (err: any) {
      handleApiError(err, '加载联调诊断失败');
    }
  }, [storeId]);

  useEffect(() => {
    loadCommissioning();
  }, [loadCommissioning]);

  const runDeviceAction = async (actionKey: string, action: () => Promise<void>, successMessage: string) => {
    setActionLoadingKey(actionKey);
    try {
      await action();
      showSuccess(successMessage);
      await Promise.all([loadData(), loadCommissioning()]);
    } catch (err: any) {
      handleApiError(err, '设备联调失败');
    } finally {
      setActionLoadingKey(null);
    }
  };

  const connectShokz = async (deviceId: string) => runDeviceAction(
    `connect:${deviceId}`,
    async () => {
      await apiClient.post(`/api/v1/hardware/shokz/${deviceId}/connect`);
    },
    '已下发连接指令'
  );

  const disconnectShokz = async (deviceId: string) => runDeviceAction(
    `disconnect:${deviceId}`,
    async () => {
      await apiClient.post(`/api/v1/hardware/shokz/${deviceId}/disconnect`);
    },
    '已下发断开指令'
  );

  const testVoiceOutput = async (deviceId: string) => runDeviceAction(
    `voice:${deviceId}`,
    async () => {
      await apiClient.post(
        `/api/v1/hardware/shokz/${deviceId}/voice-output?text=${encodeURIComponent(testVoiceText)}&priority=high`
      );
    },
    '测试播报已下发'
  );

  const nodeColumns: ColumnsType<any> = [
    { title: '节点ID', dataIndex: 'node_id', key: 'node_id', render: (v: string, r: any) => v || r.id },
    { title: '名称', dataIndex: 'device_name', key: 'device_name', render: (v: string, r: any) => v || r.name || '-' },
    {
      title: '网络模式', dataIndex: 'network_mode', key: 'mode',
      render: (v: string) => {
        const meta = getNetworkModeMeta(v);
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => {
        const meta = getNodeStatusMeta(v);
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: '凭证状态',
      dataIndex: 'credential_ok',
      key: 'credential_ok',
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
    {
      title: '待补发队列',
      dataIndex: 'pending_status_queue',
      key: 'pending_status_queue',
      render: (v: number) => v ?? 0,
    },
    {
      title: '最后心跳',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string) => formatIsoDateTime(v),
    },
    {
      title: '最近凭证操作',
      key: 'audit_summary',
      render: (_: any, record: any) => {
        const summary = record.audit_summary || {};
        if (!summary.available) return <Tag>审计不可用</Tag>;
        if (!summary.latest_action) return <Tag>暂无记录</Tag>;
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
            <span style={{ color: '#666', fontSize: 12 }}>{formatIsoDateTime(summary.latest_at)}</span>
          </Space>
        );
      },
    },
    {
      title: '离线队列',
      key: 'offline_queue',
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
    { title: '设备名称', dataIndex: 'device_name', key: 'device_name', render: (v: string) => v || '-' },
    { title: '设备型号', dataIndex: 'device_model', key: 'device_model', render: (v: string) => v || '-' },
    { title: '绑定角色', dataIndex: 'user_role', key: 'user_role', render: (v: string) => v || '-' },
    { title: '绑定员工', dataIndex: 'user_id', key: 'user_id', render: (v: string) => v || '-' },
    {
      title: '连接状态', dataIndex: 'status', key: 'status',
      render: (v: string) => {
        const meta = getShokzStatusMeta(v);
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    { title: '电量', dataIndex: 'battery_level', key: 'battery', render: (v: number) => v != null ? `${v}%` : '-' },
    { title: '信号强度', dataIndex: 'signal_strength', key: 'signal_strength', render: (v: number) => v != null ? `${v} dBm` : '-' },
    {
      title: '联调动作',
      key: 'actions',
      render: (_: unknown, record: any) => (
        <Space wrap>
          <Button
            size="small"
            loading={actionLoadingKey === `connect:${record.device_id}`}
            onClick={() => connectShokz(record.device_id)}
          >
            连接
          </Button>
          <Button
            size="small"
            loading={actionLoadingKey === `disconnect:${record.device_id}`}
            onClick={() => disconnectShokz(record.device_id)}
          >
            断开
          </Button>
          <Button
            size="small"
            type="primary"
            loading={actionLoadingKey === `voice:${record.device_id}`}
            onClick={() => testVoiceOutput(record.device_id)}
          >
            测试播报
          </Button>
        </Space>
      ),
    },
  ];

  const costSummary = summarizeDeploymentCost(deploymentCost);

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
            <Col span={6}><Card><Statistic title="硬件总成本" prefix="¥" value={costSummary.hardwareCost} precision={0} /></Card></Col>
            <Col span={6}><Card><Statistic title="实施成本" prefix="¥" value={costSummary.implementationCost} precision={0} /></Card></Col>
            <Col span={6}><Card><Statistic title="部署时长" suffix="小时" value={costSummary.deploymentTimeHours} precision={1} /></Card></Col>
            <Col span={6}><Card><Statistic title="单店总成本" prefix="¥" value={costSummary.totalCost} precision={0} /></Card></Col>
          </Row>
          <Card title="推荐配置">
            <Descriptions bordered column={2}>
              <Descriptions.Item label="树莓派数量">{costSummary.recommendedNodes} 台</Descriptions.Item>
              <Descriptions.Item label="Shokz设备数量">{costSummary.recommendedShokz} 台</Descriptions.Item>
              <Descriptions.Item label="预计回收周期">{costSummary.roiMonths} 个月</Descriptions.Item>
              <Descriptions.Item label="交付模式">远程预配置 + 到店蓝牙配对</Descriptions.Item>
            </Descriptions>
          </Card>
          <Alert message="硬件部署可显著提升离线可用性和语音交互体验" type="info" style={{ marginTop: 16 }} />
        </div>
      ) : <Card loading={loading} />,
    },
    {
      key: 'commissioning',
      label: '设备联调/验收',
      children: (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card>
                <Statistic title="验收状态" value={commissioning?.ready ? '通过' : '待处理'} valueStyle={{ color: commissioning?.ready ? '#389e0d' : '#d48806' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title="在线节点" value={commissioning?.summary?.edge_nodes_online || 0} suffix={`/ ${commissioning?.summary?.edge_nodes_total || 0}`} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title="已连接耳机" value={commissioning?.summary?.shokz_connected || 0} suffix={`/ ${commissioning?.summary?.shokz_total || 0}`} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title="已登记目标 MAC" value={commissioning?.summary?.target_macs_registered || 0} suffix={`/ ${commissioning?.summary?.target_macs_total || 0}`} />
              </Card>
            </Col>
          </Row>

          <Card title="联调动作" style={{ marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Input.TextArea
                rows={3}
                value={testVoiceText}
                onChange={(event) => setTestVoiceText(event.target.value)}
                placeholder="请输入测试播报文本"
              />
              <Alert
                type="info"
                message="连接正常且有效的标准"
                description="必须同时满足：树莓派在线、凭证有效、Shokz 已连接、离线队列无积压、测试播报能成功下发。"
                showIcon
              />
            </Space>
          </Card>

          <Card title="验收检查清单" style={{ marginBottom: 16 }}>
            <List
              dataSource={commissioning?.checklist || []}
              renderItem={(item: any) => {
                const meta = getChecklistStatusMeta(item.passed);
                return (
                  <List.Item>
                    <Space direction="vertical" size={0}>
                      <Space>
                        <strong>{item.label}</strong>
                        <Tag color={meta.color}>{meta.label}</Tag>
                      </Space>
                      <span>{item.detail}</span>
                    </Space>
                  </List.Item>
                );
              }}
            />
          </Card>

          <Card title="目标耳机 MAC">
            <Descriptions bordered column={1}>
              <Descriptions.Item label="目标 MAC">{(commissioning?.target_macs || []).join(', ') || '-'}</Descriptions.Item>
              <Descriptions.Item label="未登记 / 未发现">{(commissioning?.missing_target_macs || []).join(', ') || '无'}</Descriptions.Item>
            </Descriptions>
          </Card>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Select value={storeId} onChange={setStoreId} style={{ width: 160 }}>
          {stores.length > 0 ? stores.map((s: any) => (
            <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
          )) : null}
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
            children: (
              <Space direction="vertical" size={0}>
                <strong>{log.action}</strong>
                <span>{log.description || '-'}</span>
                <span style={{ color: '#666', fontSize: 12 }}>{formatIsoDateTime(log.created_at)}</span>
              </Space>
            ),
          }))}
        />
      </Drawer>
    </div>
  );
};

export default HardwarePage;
