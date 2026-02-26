import React, { useEffect, useState, useCallback } from 'react';
import { Card, Col, Row, Table, Button, Modal, Form, Input, Select, InputNumber, Tag, Space, Tabs, Statistic } from 'antd';
import {
  ShoppingOutlined,
  PlusOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { Option } = Select;
const { TabPane } = Tabs;
const { TextArea } = Input;

const SupplyChainManagement: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [suppliers, setSuppliers] = useState<any[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<any[]>([]);
  const [replenishmentSuggestions, setReplenishmentSuggestions] = useState<any[]>([]);
  const [supplierModalVisible, setSupplierModalVisible] = useState(false);
  const [orderModalVisible, setOrderModalVisible] = useState(false);
  const [quotes, setQuotes] = useState<any[]>([]);
  const [compareResult, setCompareResult] = useState<any>(null);
  const [selectedQuoteIds, setSelectedQuoteIds] = useState<string[]>([]);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [quoteForm] = Form.useForm();
  const [form] = Form.useForm();
  const [orderForm] = Form.useForm();

  const loadSuppliers = useCallback(async () => {
    try {
      const response = await apiClient.get('/supply-chain/suppliers');
      setSuppliers(response.data.suppliers || []);
    } catch (err: any) {
      handleApiError(err, '加载供应商失败');
    }
  }, []);

  const loadPurchaseOrders = useCallback(async () => {
    try {
      const response = await apiClient.get('/supply-chain/purchase-orders');
      setPurchaseOrders(response.data.orders || []);
    } catch (err: any) {
      handleApiError(err, '加载采购订单失败');
    }
  }, []);

  const loadReplenishmentSuggestions = useCallback(async () => {
    try {
      const response = await apiClient.get('/supply-chain/replenishment-suggestions');
      setReplenishmentSuggestions(response.data.suggestions || []);
    } catch (err: any) {
      handleApiError(err, '加载补货建议失败');
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        loadSuppliers(),
        loadPurchaseOrders(),
        loadReplenishmentSuggestions(),
      ]);
      setLoading(false);
    };
    loadData();
  }, [loadSuppliers, loadPurchaseOrders, loadReplenishmentSuggestions]);

  const handleCreateSupplier = async (values: any) => {
    try {
      await apiClient.post('/supply-chain/suppliers', values);
      setSupplierModalVisible(false);
      form.resetFields();
      loadSuppliers();
    } catch (err: any) {
      handleApiError(err, '创建供应商失败');
    }
  };

  const handleCreateOrder = async (values: any) => {
    try {
      await apiClient.post('/supply-chain/purchase-orders', values);
      setOrderModalVisible(false);
      orderForm.resetFields();
      loadPurchaseOrders();
    } catch (err: any) {
      handleApiError(err, '创建订单失败');
    }
  };

  const handleUpdateOrderStatus = async (orderId: string, status: string) => {
    const key = `order-${orderId}-${status}`;
    setActionLoading(prev => ({ ...prev, [key]: true }));
    try {
      await apiClient.patch(`/supply-chain/purchase-orders/${orderId}/status`, { status });
      loadPurchaseOrders();
    } catch (err: any) {
      handleApiError(err, '更新订单状态失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  // 供应商表格列
  const supplierColumns = [
    {
      title: '供应商名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '编码',
      dataIndex: 'code',
      key: 'code',
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      render: (category: string) => {
        const categoryMap: any = {
          food: '食材',
          beverage: '饮料',
          equipment: '设备',
          other: '其他',
        };
        return categoryMap[category] || category;
      },
    },
    {
      title: '联系人',
      dataIndex: 'contact_person',
      key: 'contact_person',
    },
    {
      title: '电话',
      dataIndex: 'phone',
      key: 'phone',
    },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      render: (rating: number) => `${rating.toFixed(1)} ⭐`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: any = {
          active: { color: 'green', text: '活跃' },
          inactive: { color: 'gray', text: '停用' },
          suspended: { color: 'red', text: '暂停' },
        };
        const s = statusMap[status] || { color: 'default', text: status };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
  ];

  // 采购订单表格列
  const orderColumns = [
    {
      title: '订单号',
      dataIndex: 'order_number',
      key: 'order_number',
    },
    {
      title: '供应商',
      dataIndex: 'supplier_id',
      key: 'supplier_id',
      render: (supplierId: string) => {
        const supplier = suppliers.find(s => s.id === supplierId);
        return supplier?.name || supplierId;
      },
    },
    {
      title: '金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      render: (amount: number) => `¥${(amount / 100).toFixed(2)}`,
    },
    {
      title: '商品数',
      dataIndex: 'items_count',
      key: 'items_count',
    },
    {
      title: '预计交货',
      dataIndex: 'expected_delivery',
      key: 'expected_delivery',
      render: (date: string) => date ? new Date(date).toLocaleDateString() : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: any = {
          pending: { color: 'orange', text: '待审批' },
          approved: { color: 'blue', text: '已审批' },
          ordered: { color: 'cyan', text: '已下单' },
          shipped: { color: 'purple', text: '已发货' },
          delivered: { color: 'green', text: '已送达' },
          completed: { color: 'success', text: '已完成' },
          cancelled: { color: 'red', text: '已取消' },
        };
        const s = statusMap[status] || { color: 'default', text: status };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => (
        <Space>
          {record.status === 'pending' && (
            <Button size="small" type="link" loading={actionLoading[`order-${record.id}-approved`]} onClick={() => handleUpdateOrderStatus(record.id, 'approved')}>
              审批
            </Button>
          )}
          {record.status === 'approved' && (
            <Button size="small" type="link" loading={actionLoading[`order-${record.id}-ordered`]} onClick={() => handleUpdateOrderStatus(record.id, 'ordered')}>
              下单
            </Button>
          )}
          {record.status === 'ordered' && (
            <Button size="small" type="link" loading={actionLoading[`order-${record.id}-shipped`]} onClick={() => handleUpdateOrderStatus(record.id, 'shipped')}>
              标记发货
            </Button>
          )}
        </Space>
      ),
    },
  ];

  // 补货建议表格列
  const suggestionColumns = [
    {
      title: '商品名称',
      dataIndex: 'item_name',
      key: 'item_name',
    },
    {
      title: '当前库存',
      dataIndex: 'current_quantity',
      key: 'current_quantity',
      render: (qty: number, record: any) => `${qty} ${record.unit}`,
    },
    {
      title: '安全库存',
      dataIndex: 'reorder_point',
      key: 'reorder_point',
      render: (qty: number, record: any) => `${qty} ${record.unit}`,
    },
    {
      title: '建议采购',
      dataIndex: 'suggested_quantity',
      key: 'suggested_quantity',
      render: (qty: number, record: any) => `${qty} ${record.unit}`,
    },
    {
      title: '预估成本',
      dataIndex: 'estimated_cost',
      key: 'estimated_cost',
      render: (cost: number) => `¥${(cost / 100).toFixed(2)}`,
    },
    {
      title: '紧急程度',
      dataIndex: 'urgency',
      key: 'urgency',
      render: (urgency: string) => {
        const urgencyMap: any = {
          high: { color: 'red', icon: <WarningOutlined />, text: '紧急' },
          medium: { color: 'orange', icon: <ClockCircleOutlined />, text: '一般' },
          low: { color: 'green', icon: <CheckCircleOutlined />, text: '正常' },
        };
        const u = urgencyMap[urgency] || { color: 'default', icon: null, text: urgency };
        return <Tag color={u.color} icon={u.icon}>{u.text}</Tag>;
      },
    },
  ];

  const handleRequestQuotes = async (values: any) => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/supply-chain/quotes/request', values);
      setQuotes(res.data.quotes || []);
      setSelectedQuoteIds([]);
      setCompareResult(null);
    } catch (err: any) {
      handleApiError(err, '请求报价失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCompareQuotes = async () => {
    if (selectedQuoteIds.length < 2) return;
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/supply-chain/quotes/compare', { quote_ids: selectedQuoteIds });
      setCompareResult(res.data);
    } catch (err: any) {
      handleApiError(err, '比较报价失败');
    } finally {
      setLoading(false);
    }
  };

  const quoteColumns = [
    { title: '供应商', dataIndex: 'supplier_name', key: 'supplier_name' },
    { title: '单价', dataIndex: 'unit_price', key: 'unit_price', render: (v: number) => `¥${v?.toFixed(2)}` },
    { title: '总价', dataIndex: 'total_price', key: 'total_price', render: (v: number) => `¥${v?.toFixed(2)}` },
    { title: '交货天数', dataIndex: 'delivery_days', key: 'delivery_days', render: (v: number) => `${v}天` },
    { title: '评分', dataIndex: 'score', key: 'score', render: (v: number) => v?.toFixed(1) },
    { title: '推荐', dataIndex: 'recommended', key: 'recommended', render: (v: boolean) => v ? <Tag color="green">推荐</Tag> : null },
  ];

  return (
    <div style={{ padding: '24px', background: '#f0f2f5', minHeight: '100vh' }}>
      <h1 style={{ marginBottom: '24px' }}>
        <ShoppingOutlined /> 供应链管理
      </h1>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="供应商总数"
              value={suppliers.length}
              prefix={<ShoppingOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="待审批订单"
              value={purchaseOrders.filter(o => o.status === 'pending').length}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="进行中订单"
              value={purchaseOrders.filter(o => ['approved', 'ordered', 'shipped'].includes(o.status)).length}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="补货提醒"
              value={replenishmentSuggestions.filter(s => s.urgency === 'high').length}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 主要内容 */}
      <Card>
        <Tabs defaultActiveKey="suppliers">
          <TabPane tab="供应商管理" key="suppliers">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setSupplierModalVisible(true)}
              style={{ marginBottom: '16px' }}
            >
              添加供应商
            </Button>
            <Table
              columns={supplierColumns}
              dataSource={suppliers}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="采购订单" key="orders">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setOrderModalVisible(true)}
              style={{ marginBottom: '16px' }}
            >
              创建采购订单
            </Button>
            <Table
              columns={orderColumns}
              dataSource={purchaseOrders}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="补货建议" key="suggestions">
            <Table
              columns={suggestionColumns}
              dataSource={replenishmentSuggestions}
              rowKey="item_id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>
          <TabPane tab="报价管理" key="quotes">
            <Row gutter={16}>
              <Col span={10}>
                <Card size="small" title="请求报价">
                  <Form form={quoteForm} layout="vertical" onFinish={handleRequestQuotes}>
                    <Form.Item name="material_id" label="物料ID" rules={[{ required: true }]}>
                      <Input placeholder="例：MAT001" />
                    </Form.Item>
                    <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
                      <InputNumber min={1} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="required_date" label="需求日期" rules={[{ required: true }]}>
                      <Input type="date" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>获取报价</Button>
                  </Form>
                </Card>
              </Col>
              <Col span={14}>
                {quotes.length > 0 && (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Table
                      columns={quoteColumns}
                      dataSource={quotes}
                      rowKey="quote_id"
                      size="small"
                      pagination={false}
                      rowSelection={{
                        selectedRowKeys: selectedQuoteIds,
                        onChange: (keys) => setSelectedQuoteIds(keys as string[]),
                      }}
                    />
                    <Button
                      type="primary"
                      disabled={selectedQuoteIds.length < 2}
                      onClick={handleCompareQuotes}
                    >
                      比较选中报价（{selectedQuoteIds.length}）
                    </Button>
                    {compareResult && (
                      <Card size="small" title="比较结果">
                        <pre style={{ fontSize: 12, margin: 0 }}>{JSON.stringify(compareResult, null, 2)}</pre>
                      </Card>
                    )}
                  </Space>
                )}
              </Col>
            </Row>
          </TabPane>
        </Tabs>
      </Card>

      {/* 添加供应商模态框 */}
      <Modal
        title="添加供应商"
        open={supplierModalVisible}
        onCancel={() => setSupplierModalVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateSupplier}>
          <Form.Item name="name" label="供应商名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code" label="供应商编码">
            <Input />
          </Form.Item>
          <Form.Item name="category" label="类别" initialValue="food">
            <Select>
              <Option value="food">食材</Option>
              <Option value="beverage">饮料</Option>
              <Option value="equipment">设备</Option>
              <Option value="other">其他</Option>
            </Select>
          </Form.Item>
          <Form.Item name="contact_person" label="联系人">
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input type="email" />
          </Form.Item>
          <Form.Item name="address" label="地址">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="payment_terms" label="付款条款" initialValue="net30">
            <Select>
              <Option value="net30">Net 30</Option>
              <Option value="net60">Net 60</Option>
              <Option value="cod">货到付款</Option>
            </Select>
          </Form.Item>
          <Form.Item name="delivery_time" label="交货时间（天）" initialValue={3}>
            <InputNumber min={1} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 创建采购订单模态框 */}
      <Modal
        title="创建采购订单"
        open={orderModalVisible}
        onCancel={() => setOrderModalVisible(false)}
        onOk={() => orderForm.submit()}
      >
        <Form form={orderForm} layout="vertical" onFinish={handleCreateOrder}>
          <Form.Item name="supplier_id" label="供应商" rules={[{ required: true }]}>
            <Select>
              {suppliers.filter(s => s.status === 'active').map(s => (
                <Option key={s.id} value={s.id}>{s.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="store_id" label="门店ID" rules={[{ required: true }]}>
            <Input placeholder="请输入门店ID" />
          </Form.Item>
          <Form.Item name="total_amount" label="总金额（元）" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="expected_delivery" label="预计交货时间">
            <Input type="date" />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SupplyChainManagement;
