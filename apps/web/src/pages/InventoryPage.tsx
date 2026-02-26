import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Form, Input, Button, Table, Space, Tag, Tabs, Modal,
  Row, Col, Statistic, Progress, Alert, Select,
} from 'antd';
import {
  InboxOutlined, WarningOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined, ReloadOutlined, SearchOutlined,
} from '@ant-design/icons';
import apiClient from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { TabPane } = Tabs;
const { Option } = Select;

interface InventoryItem {
  id: string;
  store_id: string;
  name: string;
  category: string | null;
  unit: string | null;
  current_quantity: number;
  min_quantity: number;
  max_quantity: number | null;
  unit_cost: number | null;
  status: string | null;
}

const InventoryPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<InventoryItem | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const refreshInventory = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiClient.get(`/api/v1/inventory?store_id=${storeId}`);
      setInventory(Array.isArray(res) ? res : (res.data || []));
    } catch (error: any) {
      handleApiError(error, '加载库存失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    loadStores();
    refreshInventory();
  }, [loadStores, refreshInventory]);

  const handleCheckInventory = async (values: any) => {
    try {
      setLoading(true);
      const res = await apiClient.get(
        `/api/v1/inventory?store_id=${values.store_id}&low_stock_only=true`
      );
      const items = Array.isArray(res) ? res : (res.data || []);
      setInventory(items);
      showSuccess(`库存检查完成，发现 ${items.length} 个低库存物品`);
      form.resetFields();
    } catch (error: any) {
      handleApiError(error, '库存检查失败');
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetails = (record: InventoryItem) => {
    setSelectedItem(record);
    setModalVisible(true);
  };

  const handleUpdateStock = async (itemId: string, newStock: number) => {
    try {
      await apiClient.patch(`/api/v1/inventory/${itemId}`, { current_quantity: newStock });
      showSuccess('库存已更新');
      refreshInventory();
    } catch (error: any) {
      handleApiError(error, '更新库存失败');
    }
  };

  const columns = [
    { title: '物品ID', dataIndex: 'id', key: 'id', width: 120 },
    { title: '物品名称', dataIndex: 'name', key: 'name' },
    { title: '分类', dataIndex: 'category', key: 'category', width: 100 },
    {
      title: '当前库存',
      dataIndex: 'current_quantity',
      key: 'current_quantity',
      width: 120,
      render: (stock: number, record: InventoryItem) => (
        <span>{stock} {record.unit}</span>
      ),
    },
    {
      title: '库存状态',
      key: 'stock_level',
      width: 150,
      render: (_: any, record: InventoryItem) => {
        const max = record.max_quantity || record.min_quantity * 3;
        const percentage = Math.min(100, Math.round((record.current_quantity / max) * 100));
        let status: 'success' | 'normal' | 'exception' = 'success';
        if (record.status === 'critical' || record.status === 'out_of_stock') {
          status = 'exception';
        } else if (record.status === 'low') {
          status = 'normal';
        }
        return <Progress percent={percentage} status={status} size="small" />;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const statusConfig: Record<string, { color: string; text: string; icon: any }> = {
          normal: { color: 'green', text: '正常', icon: <CheckCircleOutlined /> },
          low: { color: 'orange', text: '偏低', icon: <WarningOutlined /> },
          critical: { color: 'red', text: '紧急', icon: <ExclamationCircleOutlined /> },
          out_of_stock: { color: 'red', text: '缺货', icon: <ExclamationCircleOutlined /> },
        };
        const config = statusConfig[status] || statusConfig.normal;
        return <Tag color={config.color} icon={config.icon}>{config.text}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: InventoryItem) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleViewDetails(record)}>详情</Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              const newStock = prompt('请输入新库存数量:', record.current_quantity.toString());
              if (newStock !== null) {
                handleUpdateStock(record.id, parseFloat(newStock));
              }
            }}
          >
            更新
          </Button>
        </Space>
      ),
    },
  ];

  const stats = {
    total: inventory.length,
    normal: inventory.filter((i) => i.status === 'normal').length,
    low: inventory.filter((i) => i.status === 'low').length,
    critical: inventory.filter((i) => i.status === 'critical' || i.status === 'out_of_stock').length,
  };

  const filteredInventory = inventory.filter((item) => {
    const matchesSearch =
      searchText === '' ||
      item.name.toLowerCase().includes(searchText.toLowerCase()) ||
      item.id.toLowerCase().includes(searchText.toLowerCase()) ||
      (item.category || '').toLowerCase().includes(searchText.toLowerCase());
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const alerts = inventory.filter((i) => i.status !== 'normal');

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>库存预警Agent</h1>
        <Space>
          <Select value={storeId} onChange={(v) => setStoreId(v)} style={{ width: 160 }}>
            {stores.length > 0 ? stores.map((s: any) => (
              <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
            )) : <Option value="STORE001">STORE001</Option>}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={refreshInventory} loading={loading}>刷新</Button>
        </Space>
      </div>

      {alerts.length > 0 && (
        <Alert
          message={`库存预警: ${alerts.length}个物品需要补货`}
          description={
            <ul style={{ marginBottom: 0 }}>
              {alerts.map((item) => (
                <li key={item.id}>
                  {item.name}: 当前库存 {item.current_quantity} {item.unit}，最低库存 {item.min_quantity} {item.unit}
                </li>
              ))}
            </ul>
          }
          type="warning"
          showIcon
          closable
          style={{ marginBottom: 24 }}
        />
      )}

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title="总物品数" value={stats.total} prefix={<InboxOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="库存正常" value={stats.normal} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="库存偏低" value={stats.low} valueStyle={{ color: '#faad14' }} prefix={<WarningOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="紧急补货" value={stats.critical} valueStyle={{ color: '#cf1322' }} prefix={<ExclamationCircleOutlined />} /></Card>
        </Col>
      </Row>

      <Tabs defaultActiveKey="list">
        <TabPane tab="库存列表" key="list">
          <Card>
            <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
              <Space>
                <Input
                  placeholder="搜索物品名称、ID或分类"
                  prefix={<SearchOutlined />}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  style={{ width: 300 }}
                  allowClear
                />
                <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }}>
                  <Select.Option value="all">全部状态</Select.Option>
                  <Select.Option value="normal">正常</Select.Option>
                  <Select.Option value="low">偏低</Select.Option>
                  <Select.Option value="critical">紧急</Select.Option>
                  <Select.Option value="out_of_stock">缺货</Select.Option>
                </Select>
              </Space>
              <span style={{ color: '#999' }}>共 {filteredInventory.length} 条记录</span>
            </Space>
            <Table
              dataSource={filteredInventory}
              columns={columns}
              rowKey="id"
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: inventory.length === 0 ? '暂无库存记录' : '没有符合条件的库存物品' }}
              loading={loading}
            />
          </Card>
        </TabPane>

        <TabPane tab="库存检查" key="check">
          <Card>
            <Form form={form} layout="vertical" onFinish={handleCheckInventory}>
              <Form.Item label="门店ID" name="store_id" rules={[{ required: true, message: '请输入门店ID' }]}>
                <Input placeholder="例如: STORE001" />
              </Form.Item>
              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={loading}>检查低库存</Button>
                  <Button onClick={() => form.resetFields()}>重置</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>
      </Tabs>

      <Modal
        title="库存详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[<Button key="close" onClick={() => setModalVisible(false)}>关闭</Button>]}
        width={600}
      >
        {selectedItem && (
          <div>
            <p><strong>物品ID:</strong> {selectedItem.id}</p>
            <p><strong>物品名称:</strong> {selectedItem.name}</p>
            <p><strong>分类:</strong> {selectedItem.category}</p>
            <p><strong>当前库存:</strong> {selectedItem.current_quantity} {selectedItem.unit}</p>
            <p><strong>最低库存:</strong> {selectedItem.min_quantity} {selectedItem.unit}</p>
            <p><strong>最大库存:</strong> {selectedItem.max_quantity} {selectedItem.unit}</p>
            <p>
              <strong>状态:</strong>{' '}
              <Tag color={selectedItem.status === 'normal' ? 'green' : selectedItem.status === 'low' ? 'orange' : 'red'}>
                {selectedItem.status}
              </Tag>
            </p>
            <p>
              <strong>库存率:</strong>{' '}
              <Progress
                percent={Math.round(
                  (selectedItem.current_quantity / (selectedItem.max_quantity || selectedItem.min_quantity * 3)) * 100
                )}
                status={selectedItem.status === 'normal' ? 'success' : selectedItem.status === 'low' ? 'normal' : 'exception'}
              />
            </p>
            {selectedItem.status !== 'normal' && (
              <Alert
                message="补货建议"
                description={`建议补货数量: ${(selectedItem.max_quantity || selectedItem.min_quantity * 3) - selectedItem.current_quantity} ${selectedItem.unit}`}
                type="info"
                showIcon
                style={{ marginTop: 16 }}
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default InventoryPage;
