import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, Modal, Form, Input, Select, Tabs, Alert } from 'antd';
import { ShoppingOutlined, DatabaseOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;

const ModelMarketplacePage: React.FC = () => {
  const [models, setModels] = useState<any[]>([]);
  const [myModels, setMyModels] = useState<any[]>([]);
  const [networkEffect, setNetworkEffect] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [purchaseVisible, setPurchaseVisible] = useState(false);
  const [contributeVisible, setContributeVisible] = useState(false);
  const [selectedModel, setSelectedModel] = useState<any>(null);
  const [storeId] = useState('STORE001');
  const [contributeForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [modelsRes, myRes, netRes] = await Promise.allSettled([
        apiClient.get('/model-marketplace/models'),
        apiClient.get(`/model-marketplace/my-models/${storeId}`),
        apiClient.get('/model-marketplace/network-effect'),
      ]);
      if (modelsRes.status === 'fulfilled') setModels(modelsRes.value.data?.models || modelsRes.value.data || []);
      if (myRes.status === 'fulfilled') setMyModels(myRes.value.data?.models || myRes.value.data || []);
      if (netRes.status === 'fulfilled') setNetworkEffect(netRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载模型市场失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => { loadData(); }, [loadData]);

  const purchaseModel = async () => {
    try {
      await apiClient.post('/model-marketplace/purchase', { store_id: storeId, model_id: selectedModel?.model_id || selectedModel?.id });
      showSuccess('购买成功');
      setPurchaseVisible(false);
      loadData();
    } catch (err: any) {
      handleApiError(err, '购买失败');
    }
  };

  const contributeData = async (values: any) => {
    try {
      await apiClient.post('/model-marketplace/contribute-data', { store_id: storeId, ...values });
      showSuccess('数据贡献成功');
      setContributeVisible(false);
      contributeForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '贡献失败');
    }
  };

  const marketColumns: ColumnsType<any> = [
    { title: '模型名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => <Tag>{v || '-'}</Tag> },
    { title: '描述', dataIndex: 'description', key: 'desc', ellipsis: true },
    { title: '价格', dataIndex: 'price', key: 'price', render: (v: number) => v === 0 ? <Tag color="green">免费</Tag> : `¥${(v || 0).toFixed(2)}` },
    { title: '评分', dataIndex: 'rating', key: 'rating', render: (v: number) => v ? `${v.toFixed(1)} ⭐` : '-' },
    {
      title: '操作', key: 'action',
      render: (_: any, record: any) => (
        <Button size="small" type="primary" icon={<ShoppingOutlined />} onClick={() => { setSelectedModel(record); setPurchaseVisible(true); }}>购买</Button>
      ),
    },
  ];

  const myModelColumns: ColumnsType<any> = [
    { title: '模型名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => <Tag>{v || '-'}</Tag> },
    { title: '购买日期', dataIndex: 'purchased_at', key: 'date' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'active' ? 'green' : 'orange'}>{v === 'active' ? '使用中' : v}</Tag> },
  ];

  const tabItems = [
    {
      key: 'market',
      label: '模型市场',
      children: (
        <Card loading={loading}>
          <Table columns={marketColumns} dataSource={models} rowKey={(r, i) => r.model_id || r.id || String(i)} />
        </Card>
      ),
    },
    {
      key: 'my',
      label: '我的模型',
      children: (
        <Card loading={loading}>
          <Table columns={myModelColumns} dataSource={myModels} rowKey={(r, i) => r.model_id || r.id || String(i)} />
        </Card>
      ),
    },
    {
      key: 'network',
      label: '网络效应',
      children: networkEffect ? (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}><Card><Statistic title="参与门店数" value={networkEffect.participating_stores || 0} /></Card></Col>
            <Col span={6}><Card><Statistic title="贡献数据量" value={networkEffect.total_data_points || 0} /></Card></Col>
            <Col span={6}><Card><Statistic title="模型准确率" suffix="%" value={((networkEffect.model_accuracy || 0) * 100).toFixed(1)} /></Card></Col>
            <Col span={6}><Card><Statistic title="平均提升" suffix="%" value={((networkEffect.avg_improvement || 0) * 100).toFixed(1)} /></Card></Col>
          </Row>
          <Alert message="越多门店参与，模型越精准，所有参与者共同受益" type="info" />
        </div>
      ) : <Card loading={loading} />,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, textAlign: 'right' }}>
        <Space>
          <Button icon={<DatabaseOutlined />} onClick={() => setContributeVisible(true)}>贡献数据</Button>
        </Space>
      </div>
      <Tabs items={tabItems} />

      <Modal title={`购买模型：${selectedModel?.name}`} open={purchaseVisible} onCancel={() => setPurchaseVisible(false)} onOk={purchaseModel} okText="确认购买">
        <p>价格：{selectedModel?.price === 0 ? '免费' : `¥${(selectedModel?.price || 0).toFixed(2)}`}</p>
        <p>{selectedModel?.description}</p>
      </Modal>

      <Modal title="贡献数据" open={contributeVisible} onCancel={() => { setContributeVisible(false); contributeForm.resetFields(); }} onOk={() => contributeForm.submit()} okText="提交">
        <Form form={contributeForm} layout="vertical" onFinish={contributeData}>
          <Form.Item name="data_type" label="数据类型" rules={[{ required: true }]}>
            <Select>
              <Option value="orders">订单数据</Option>
              <Option value="inventory">库存数据</Option>
              <Option value="customer">客户数据</Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述"><TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ModelMarketplacePage;
