import React, { useState, useCallback, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, Statistic, Row, Col, Modal, Form, Input, Select } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, BarChartOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;

const StoreManagementPage: React.FC = () => {
  const [stores, setStores] = useState<any[]>([]);
  const [storeCount, setStoreCount] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [formVisible, setFormVisible] = useState(false);
  const [statsVisible, setStatsVisible] = useState(false);
  const [editingStore, setEditingStore] = useState<any>(null);
  const [storeStats, setStoreStats] = useState<any>(null);
  const [form] = Form.useForm();

  const loadStores = useCallback(async () => {
    setLoading(true);
    try {
      const [storesRes, countRes] = await Promise.allSettled([
        apiClient.get('/stores'),
        apiClient.get('/stores-count'),
      ]);
      if (storesRes.status === 'fulfilled') setStores(storesRes.value.data?.stores || storesRes.value.data || []);
      if (countRes.status === 'fulfilled') setStoreCount(countRes.value.data);
    } catch (err: any) {
      handleApiError(err, '加载门店列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadStores(); }, [loadStores]);

  const openCreate = () => {
    setEditingStore(null);
    form.resetFields();
    setFormVisible(true);
  };

  const openEdit = (record: any) => {
    setEditingStore(record);
    form.setFieldsValue(record);
    setFormVisible(true);
  };

  const viewStats = async (record: any) => {
    try {
      const res = await apiClient.get(`/stores/${record.store_id || record.id}/stats`);
      setStoreStats({ ...res.data, name: record.name });
      setStatsVisible(true);
    } catch (err: any) {
      handleApiError(err, '加载门店统计失败');
    }
  };

  const deleteStore = async (record: any) => {
    Modal.confirm({
      title: `确认删除门店「${record.name}」？`,
      onOk: async () => {
        try {
          await apiClient.delete(`/stores/${record.store_id || record.id}`);
          showSuccess('删除成功');
          loadStores();
        } catch (err: any) {
          handleApiError(err, '删除失败');
        }
      },
    });
  };

  const submitForm = async (values: any) => {
    try {
      if (editingStore) {
        await apiClient.put(`/stores/${editingStore.store_id || editingStore.id}`, values);
        showSuccess('更新成功');
      } else {
        await apiClient.post('/stores', values);
        showSuccess('创建成功');
      }
      setFormVisible(false);
      loadStores();
    } catch (err: any) {
      handleApiError(err, editingStore ? '更新失败' : '创建失败');
    }
  };

  const columns: ColumnsType<any> = [
    { title: '门店ID', dataIndex: 'store_id', key: 'store_id' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '城市', dataIndex: 'city', key: 'city' },
    { title: '地区', dataIndex: 'region', key: 'region' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'active' ? 'green' : 'orange'}>{v === 'active' ? '运营中' : v || '-'}</Tag> },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<BarChartOutlined />} onClick={() => viewStats(record)}>统计</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteStore(record)}>删除</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="门店总数" value={storeCount?.total || stores.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="运营中" value={storeCount?.active || stores.filter((s: any) => s.status === 'active').length} /></Card></Col>
        <Col span={6}><Card><Statistic title="地区数" value={storeCount?.regions || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="城市数" value={storeCount?.cities || 0} /></Card></Col>
      </Row>

      <Card
        title="门店列表"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增门店</Button>}
      >
        <Table columns={columns} dataSource={stores} rowKey={(r) => r.store_id || r.id} loading={loading} />
      </Card>

      <Modal
        title={editingStore ? '编辑门店' : '新增门店'}
        open={formVisible}
        onCancel={() => setFormVisible(false)}
        onOk={() => form.submit()}
        okText="保存"
      >
        <Form form={form} layout="vertical" onFinish={submitForm}>
          <Form.Item name="store_id" label="门店ID" rules={[{ required: !editingStore }]}>
            <Input disabled={!!editingStore} />
          </Form.Item>
          <Form.Item name="name" label="门店名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="city" label="城市"><Input /></Form.Item>
          <Form.Item name="region" label="地区"><Input /></Form.Item>
          <Form.Item name="status" label="状态">
            <Select>
              <Option value="active">运营中</Option>
              <Option value="inactive">停用</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={`门店统计：${storeStats?.name || ''}`} open={statsVisible} onCancel={() => setStatsVisible(false)} footer={null}>
        {storeStats && (
          <Row gutter={16}>
            <Col span={12}><Card><Statistic title="今日营收" prefix="¥" value={(storeStats.today_revenue || 0).toFixed(2)} /></Card></Col>
            <Col span={12}><Card><Statistic title="今日订单" value={storeStats.today_orders || 0} /></Card></Col>
            <Col span={12} style={{ marginTop: 12 }}><Card><Statistic title="月营收" prefix="¥" value={(storeStats.month_revenue || 0).toFixed(2)} /></Card></Col>
            <Col span={12} style={{ marginTop: 12 }}><Card><Statistic title="月订单" value={storeStats.month_orders || 0} /></Card></Col>
          </Row>
        )}
      </Modal>
    </div>
  );
};

export default StoreManagementPage;
