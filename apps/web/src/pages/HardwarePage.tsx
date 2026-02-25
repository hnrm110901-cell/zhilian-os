import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Statistic, Row, Col, Select, Tabs, Descriptions, Alert } from 'antd';
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

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [nodesRes, devicesRes, costRes] = await Promise.allSettled([
        apiClient.get(`/hardware/edge-node/store/${storeId}`),
        apiClient.get(`/hardware/shokz/store/${storeId}`),
        apiClient.get('/hardware/deployment/total-cost'),
      ]);
      if (nodesRes.status === 'fulfilled') setEdgeNodes(nodesRes.value.data?.nodes || nodesRes.value.data || []);
      if (devicesRes.status === 'fulfilled') setShokzDevices(devicesRes.value.data?.devices || devicesRes.value.data || []);
      if (costRes.status === 'fulfilled') setDeploymentCost(costRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载硬件数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadStores(); loadData(); }, [loadStores, loadData]);

  const syncNode = async (node: any) => {
    try {
      await apiClient.post(`/hardware/edge-node/${node.node_id || node.id}/sync`);
      showSuccess('同步成功');
      loadData();
    } catch (err: any) {
      handleApiError(err, '同步失败');
    }
  };

  const nodeColumns: ColumnsType<any> = [
    { title: '节点ID', dataIndex: 'node_id', key: 'node_id', render: (v: string, r: any) => v || r.id },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '网络模式', dataIndex: 'network_mode', key: 'mode',
      render: (v: string) => <Tag color={v === 'online' ? 'green' : v === 'offline' ? 'red' : 'orange'}>{v || '-'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'red'}>{v === 'active' ? '在线' : '离线'}</Tag>,
    },
    { title: '最后同步', dataIndex: 'last_sync', key: 'sync', render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Button size="small" icon={<ReloadOutlined />} onClick={() => syncNode(record)}>同步</Button>
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
    </div>
  );
};

export default HardwarePage;
