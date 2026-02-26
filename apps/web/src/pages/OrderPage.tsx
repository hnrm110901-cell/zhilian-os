import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Form, Input, Button, Table, Space, Tag, Tabs, Modal,
  InputNumber, Row, Col, Statistic, Select, DatePicker, Divider,
  Popconfirm, Alert,
} from 'antd';
import {
  ShoppingCartOutlined, ClockCircleOutlined, CheckCircleOutlined,
  CloseCircleOutlined, ReloadOutlined, SearchOutlined, PlusOutlined,
  DeleteOutlined, FireOutlined, CoffeeOutlined,
} from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import apiClient from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { TabPane } = Tabs;
const { Option } = Select;
const { RangePicker } = DatePicker;

interface OrderItem {
  item_id: string;
  item_name: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
  notes?: string;
}

interface Order {
  order_id: string;
  store_id: string;
  table_number: string;
  customer_name?: string;
  customer_phone?: string;
  status: string;
  total_amount: number;
  discount_amount: number;
  final_amount: number;
  items: OrderItem[];
  order_time: string;
  confirmed_at?: string;
  completed_at?: string;
  notes?: string;
}

const STATUS_CONFIG: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  pending:    { color: 'orange',  text: '待确认', icon: <ClockCircleOutlined /> },
  confirmed:  { color: 'blue',    text: '已确认', icon: <CheckCircleOutlined /> },
  preparing:  { color: 'purple',  text: '制作中', icon: <FireOutlined /> },
  ready:      { color: 'cyan',    text: '待上桌', icon: <CoffeeOutlined /> },
  served:     { color: 'geekblue',text: '已上桌', icon: <ShoppingCartOutlined /> },
  completed:  { color: 'green',   text: '已完成', icon: <CheckCircleOutlined /> },
  cancelled:  { color: 'red',     text: '已取消', icon: <CloseCircleOutlined /> },
};

const NEXT_STATUS: Record<string, { status: string; label: string }> = {
  pending:   { status: 'confirmed', label: '确认订单' },
  confirmed: { status: 'preparing', label: '开始制作' },
  preparing: { status: 'ready',     label: '制作完成' },
  ready:     { status: 'served',    label: '已上桌' },
  served:    { status: 'completed', label: '完成结账' },
};

const OrderPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [todayStats, setTodayStats] = useState<any>(null);
  const [activeOrders, setActiveOrders] = useState<Order[]>([]);
  const [statistics, setStatistics] = useState<any>(null);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [addItemsVisible, setAddItemsVisible] = useState(false);
  const [addItemsForm] = Form.useForm();
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<any[]>([]);
  const [statsRange, setStatsRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      setStores(res.data?.stores || res.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadTodayOverview = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/orders/today-overview?store_id=${storeId}`);
      setTodayStats(res.data?.stats || null);
      setActiveOrders(res.data?.active_orders || []);
    } catch (error: any) {
      handleApiError(error, '加载今日概览失败');
    }
  }, [storeId]);

  const loadOrders = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ store_id: storeId, limit: '200' });
      if (statusFilter !== 'all') params.append('status', statusFilter);
      const res = await apiClient.get(`/api/v1/orders?${params}`);
      setOrders(res.data?.orders || []);
    } catch (error: any) {
      handleApiError(error, '加载订单失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, statusFilter]);

  const loadStatistics = useCallback(async () => {
    try {
      const params = new URLSearchParams({ store_id: storeId });
      if (statsRange) {
        params.append('start_date', statsRange[0].format('YYYY-MM-DD'));
        params.append('end_date', statsRange[1].format('YYYY-MM-DD'));
      }
      const res = await apiClient.get(`/api/v1/orders/statistics?${params}`);
      setStatistics(res.data);
    } catch (error: any) {
      handleApiError(error, '加载统计失败');
    }
  }, [storeId, statsRange]);

  useEffect(() => {
    loadStores();
  }, [loadStores]);

  useEffect(() => {
    if (activeTab === 'overview') loadTodayOverview();
    else if (activeTab === 'list') loadOrders();
    else if (activeTab === 'stats') loadStatistics();
  }, [activeTab, loadTodayOverview, loadOrders, loadStatistics]);

  const handleCreateOrder = async (values: any) => {
    const items = (values.items || []).map((item: any) => ({
      item_id: item.item_id || `ITEM_${Date.now()}`,
      item_name: item.item_name,
      quantity: item.quantity,
      unit_price: Math.round(item.unit_price * 100),
      notes: item.notes,
    }));
    if (items.length === 0) return;
    try {
      setSubmitting(true);
      await apiClient.post('/api/v1/orders', {
        store_id: storeId,
        table_number: values.table_number,
        customer_name: values.customer_name,
        customer_phone: values.customer_phone,
        notes: values.notes,
        items,
      });
      showSuccess('订单创建成功');
      form.resetFields();
      loadTodayOverview();
    } catch (error: any) {
      handleApiError(error, '订单创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateStatus = async (orderId: string, status: string) => {
    try {
      await apiClient.patch(`/api/v1/orders/${orderId}/status`, { status });
      showSuccess('状态已更新');
      if (activeTab === 'overview') loadTodayOverview();
      else loadOrders();
    } catch (error: any) {
      handleApiError(error, '状态更新失败');
    }
  };

  const handleCancel = async (orderId: string) => {
    try {
      await apiClient.post(`/api/v1/orders/${orderId}/cancel`, { reason: '手动取消' });
      showSuccess('订单已取消');
      if (activeTab === 'overview') loadTodayOverview();
      else loadOrders();
    } catch (error: any) {
      handleApiError(error, '取消失败');
    }
  };

  const handleAddItems = async (values: any) => {
    if (!selectedOrder) return;
    const items = (values.items || []).map((item: any) => ({
      item_id: item.item_id || `ITEM_${Date.now()}`,
      item_name: item.item_name,
      quantity: item.quantity,
      unit_price: Math.round(item.unit_price * 100),
    }));
    try {
      await apiClient.post(`/api/v1/orders/${selectedOrder.order_id}/items`, { items });
      showSuccess('菜品已追加');
      setAddItemsVisible(false);
      addItemsForm.resetFields();
      loadOrders();
    } catch (error: any) {
      handleApiError(error, '追加失败');
    }
  };

  const renderStatusTag = (status: string) => {
    const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
    return <Tag color={cfg.color} icon={cfg.icon}>{cfg.text}</Tag>;
  };

  const renderActions = (record: Order) => {
    const next = NEXT_STATUS[record.status];
    const canCancel = ['pending', 'confirmed', 'preparing'].includes(record.status);
    return (
      <Space size="small">
        <Button type="link" size="small" onClick={() => { setSelectedOrder(record); setDetailVisible(true); }}>详情</Button>
        {next && (
          <Button type="link" size="small" onClick={() => handleUpdateStatus(record.order_id, next.status)}>
            {next.label}
          </Button>
        )}
        {record.status === 'confirmed' && (
          <Button type="link" size="small" onClick={() => { setSelectedOrder(record); setAddItemsVisible(true); }}>
            加菜
          </Button>
        )}
        {canCancel && (
          <Popconfirm title="确认取消此订单？" onConfirm={() => handleCancel(record.order_id)} okText="确认" cancelText="取消">
            <Button type="link" danger size="small">取消</Button>
          </Popconfirm>
        )}
      </Space>
    );
  };

  const columns = [
    { title: '订单ID', dataIndex: 'order_id', key: 'order_id', width: 200, ellipsis: true },
    { title: '桌号', dataIndex: 'table_number', key: 'table_number', width: 80 },
    { title: '客户', dataIndex: 'customer_name', key: 'customer_name', width: 100, render: (v: string) => v || '-' },
    {
      title: '金额',
      dataIndex: 'final_amount',
      key: 'final_amount',
      width: 100,
      render: (v: number) => `¥${Number(v).toFixed(2)}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: renderStatusTag,
    },
    {
      title: '下单时间',
      dataIndex: 'order_time',
      key: 'order_time',
      width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    { title: '操作', key: 'action', width: 260, render: (_: any, r: Order) => renderActions(r) },
  ];

  const filteredOrders = orders.filter((o) => {
    const matchSearch = !searchText ||
      o.order_id.toLowerCase().includes(searchText.toLowerCase()) ||
      (o.table_number || '').toLowerCase().includes(searchText.toLowerCase()) ||
      (o.customer_name || '').toLowerCase().includes(searchText.toLowerCase());
    return matchSearch;
  });

  const sb = todayStats?.status_breakdown || {};

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>订单协同Agent</h1>
        <Space>
          <Select value={storeId} onChange={(v) => setStoreId(v)} style={{ width: 160 }}>
            {stores.length > 0 ? stores.map((s: any) => (
              <Option key={s.store_id || s.id} value={s.store_id || s.id}>{s.name || s.store_id || s.id}</Option>
            )) : <Option value="STORE001">STORE001</Option>}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => {
            if (activeTab === 'overview') loadTodayOverview();
            else if (activeTab === 'list') loadOrders();
            else loadStatistics();
          }} loading={loading}>刷新</Button>
        </Space>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        {/* ── 今日概览 ── */}
        <TabPane tab="今日概览" key="overview">
          <Row gutter={16} style={{ marginBottom: 16 }}>
            {[
              { title: '今日总单', key: 'total_orders', color: undefined },
              { title: '待确认', key: 'pending', color: '#faad14' },
              { title: '制作中', key: 'preparing', color: '#722ed1' },
              { title: '待上桌', key: 'ready', color: '#13c2c2' },
              { title: '已完成', key: 'completed_orders', color: '#52c41a' },
              { title: '今日营收', key: 'total_revenue', color: '#1890ff', prefix: '¥' },
            ].map(({ title, key, color, prefix }) => (
              <Col span={4} key={key}>
                <Card size="small">
                  <Statistic
                    title={title}
                    value={key === 'total_revenue' ? (todayStats?.total_revenue || 0).toFixed(2) : (todayStats?.[key] ?? sb[key] ?? 0)}
                    valueStyle={color ? { color } : undefined}
                    prefix={prefix}
                  />
                </Card>
              </Col>
            ))}
          </Row>
          {activeOrders.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={`当前有 ${activeOrders.length} 笔进行中订单`}
              style={{ marginBottom: 16 }}
            />
          )}
          <Card title="进行中订单" size="small">
            <Table
              dataSource={activeOrders}
              columns={columns}
              rowKey="order_id"
              pagination={false}
              size="small"
              locale={{ emptyText: '暂无进行中订单' }}
            />
          </Card>
        </TabPane>

        {/* ── 订单管理 ── */}
        <TabPane tab="订单管理" key="list">
          <Row gutter={16}>
            <Col span={8}>
              <Card title="创建订单" size="small">
                <Form form={form} layout="vertical" onFinish={handleCreateOrder}>
                  <Form.Item label="桌号" name="table_number" rules={[{ required: true, message: '请输入桌号' }]}>
                    <Input placeholder="例如: A01" />
                  </Form.Item>
                  <Form.Item label="客户姓名" name="customer_name">
                    <Input placeholder="选填" />
                  </Form.Item>
                  <Form.Item label="联系电话" name="customer_phone">
                    <Input placeholder="选填" />
                  </Form.Item>
                  <Divider orientation="left" plain>菜品列表</Divider>
                  <Form.List name="items" initialValue={[{}]}>
                    {(fields, { add, remove }) => (
                      <>
                        {fields.map(({ key, name }) => (
                          <Card key={key} size="small" style={{ marginBottom: 8 }}
                            extra={fields.length > 1 && <DeleteOutlined onClick={() => remove(name)} style={{ color: 'red' }} />}>
                            <Form.Item name={[name, 'item_name']} rules={[{ required: true, message: '请输入菜品名' }]}>
                              <Input placeholder="菜品名称" />
                            </Form.Item>
                            <Row gutter={8}>
                              <Col span={12}>
                                <Form.Item name={[name, 'quantity']} rules={[{ required: true }]}>
                                  <InputNumber min={1} placeholder="数量" style={{ width: '100%' }} />
                                </Form.Item>
                              </Col>
                              <Col span={12}>
                                <Form.Item name={[name, 'unit_price']} rules={[{ required: true }]}>
                                  <InputNumber min={0.01} step={0.01} placeholder="单价(元)" style={{ width: '100%' }} />
                                </Form.Item>
                              </Col>
                            </Row>
                          </Card>
                        ))}
                        <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>添加菜品</Button>
                      </>
                    )}
                  </Form.List>
                  <Form.Item label="备注" name="notes" style={{ marginTop: 8 }}>
                    <Input.TextArea rows={2} placeholder="选填" />
                  </Form.Item>
                  <Form.Item>
                    <Space>
                      <Button type="primary" htmlType="submit" loading={submitting}>创建订单</Button>
                      <Button onClick={() => form.resetFields()}>重置</Button>
                    </Space>
                  </Form.Item>
                </Form>
              </Card>
            </Col>
            <Col span={16}>
              <Card size="small">
                <Space style={{ marginBottom: 12 }}>
                  <Input
                    placeholder="搜索订单ID/桌号/客户"
                    prefix={<SearchOutlined />}
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    style={{ width: 220 }}
                    allowClear
                  />
                  <Select value={statusFilter} onChange={(v) => setStatusFilter(v)} style={{ width: 120 }}>
                    <Option value="all">全部状态</Option>
                    {Object.entries(STATUS_CONFIG).map(([k, v]) => (
                      <Option key={k} value={k}>{v.text}</Option>
                    ))}
                  </Select>
                  <span style={{ color: '#999' }}>共 {filteredOrders.length} 条</span>
                </Space>
                <Table
                  dataSource={filteredOrders}
                  columns={columns}
                  rowKey="order_id"
                  pagination={{ pageSize: 10 }}
                  loading={loading}
                  size="small"
                  locale={{ emptyText: '暂无订单' }}
                />
              </Card>
            </Col>
          </Row>
        </TabPane>

        {/* ── 统计分析 ── */}
        <TabPane tab="统计分析" key="stats">
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space>
              <RangePicker onChange={(v) => setStatsRange(v as [Dayjs, Dayjs] | null)} />
              <Button type="primary" onClick={loadStatistics}>查询</Button>
            </Space>
          </Card>
          {statistics && (
            <Row gutter={16}>
              {[
                { title: '总订单数', value: statistics.total_orders },
                { title: '已完成', value: statistics.completed_orders, color: '#52c41a' },
                { title: '已取消', value: statistics.cancelled_orders, color: '#ff4d4f' },
                { title: '总营收', value: `¥${Number(statistics.total_revenue || 0).toFixed(2)}`, color: '#1890ff' },
                { title: '均单价', value: `¥${Number(statistics.average_order_value || 0).toFixed(2)}` },
              ].map(({ title, value, color }) => (
                <Col span={4} key={title}>
                  <Card size="small">
                    <Statistic title={title} value={value} valueStyle={color ? { color } : undefined} />
                  </Card>
                </Col>
              ))}
              <Col span={24} style={{ marginTop: 16 }}>
                <Card title="各状态分布" size="small">
                  <Row gutter={8}>
                    {Object.entries(statistics.status_breakdown || {}).map(([k, v]) => (
                      <Col span={3} key={k}>
                        <Statistic title={STATUS_CONFIG[k]?.text || k} value={v as number} />
                      </Col>
                    ))}
                  </Row>
                </Card>
              </Col>
            </Row>
          )}
        </TabPane>
      </Tabs>

      {/* 订单详情 Modal */}
      <Modal
        title="订单详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={<Button onClick={() => setDetailVisible(false)}>关闭</Button>}
        width={600}
      >
        {selectedOrder && (
          <div>
            <p><strong>订单ID:</strong> {selectedOrder.order_id}</p>
            <p><strong>桌号:</strong> {selectedOrder.table_number}</p>
            {selectedOrder.customer_name && <p><strong>客户:</strong> {selectedOrder.customer_name} {selectedOrder.customer_phone}</p>}
            <p><strong>状态:</strong> {renderStatusTag(selectedOrder.status)}</p>
            <p><strong>总金额:</strong> ¥{Number(selectedOrder.total_amount).toFixed(2)}</p>
            {selectedOrder.discount_amount > 0 && <p><strong>折扣:</strong> -¥{Number(selectedOrder.discount_amount).toFixed(2)}</p>}
            <p><strong>实付:</strong> ¥{Number(selectedOrder.final_amount).toFixed(2)}</p>
            {selectedOrder.notes && <p><strong>备注:</strong> {selectedOrder.notes}</p>}
            <Divider orientation="left" plain>菜品明细</Divider>
            <Table
              dataSource={selectedOrder.items}
              rowKey={(r, i) => `${r.item_id}_${i}`}
              pagination={false}
              size="small"
              columns={[
                { title: '菜品', dataIndex: 'item_name' },
                { title: '数量', dataIndex: 'quantity', width: 60 },
                { title: '单价', dataIndex: 'unit_price', width: 80, render: (v: number) => `¥${Number(v).toFixed(2)}` },
                { title: '小计', dataIndex: 'subtotal', width: 80, render: (v: number) => `¥${Number(v).toFixed(2)}` },
              ]}
            />
          </div>
        )}
      </Modal>

      {/* 加菜 Modal */}
      <Modal
        title={`加菜 - ${selectedOrder?.order_id}`}
        open={addItemsVisible}
        onCancel={() => { setAddItemsVisible(false); addItemsForm.resetFields(); }}
        onOk={() => addItemsForm.submit()}
        okText="确认追加"
      >
        <Form form={addItemsForm} onFinish={handleAddItems}>
          <Form.List name="items" initialValue={[{}]}>
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name }) => (
                  <Row key={key} gutter={8} align="middle">
                    <Col span={8}>
                      <Form.Item name={[name, 'item_name']} rules={[{ required: true }]}>
                        <Input placeholder="菜品名" />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item name={[name, 'quantity']} rules={[{ required: true }]}>
                        <InputNumber min={1} placeholder="数量" style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={7}>
                      <Form.Item name={[name, 'unit_price']} rules={[{ required: true }]}>
                        <InputNumber min={0.01} step={0.01} placeholder="单价(元)" style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      {fields.length > 1 && <DeleteOutlined onClick={() => remove(name)} style={{ color: 'red' }} />}
                    </Col>
                  </Row>
                ))}
                <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>添加</Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  );
};

export default OrderPage;
