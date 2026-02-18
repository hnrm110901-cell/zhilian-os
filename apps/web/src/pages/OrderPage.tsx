import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Table,
  message,
  Space,
  Tag,
  Tabs,
  Modal,
  InputNumber,
  Row,
  Col,
  Statistic,
  Select,
} from 'antd';
import {
  ShoppingCartOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const { TabPane } = Tabs;

interface Order {
  order_id: string;
  store_id: string;
  table_number: string;
  status: string;
  items: any[];
  total_amount: number;
  created_at: string;
  updated_at: string;
}

const OrderPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // 初始加载订单数据
  useEffect(() => {
    loadOrders();
  }, []);

  // 加载订单列表
  const loadOrders = async () => {
    try {
      setLoading(true);
      // 这里可以调用API获取订单列表
      // const response = await apiClient.callAgent('order', { action: 'list' });
      // setOrders(response.output_data.orders || []);

      // 暂时使用模拟数据
      message.info('订单数据已加载');
    } catch (error: any) {
      message.error(error.message || '加载订单失败');
    } finally {
      setLoading(false);
    }
  };

  // 处理订单
  const handleProcessOrder = async (values: any) => {
    try {
      setLoading(true);

      const request = {
        action: 'process',
        order_id: values.order_id || `ORD_${Date.now()}`,
        order_data: {
          store_id: values.store_id,
          table_number: values.table_number,
          items: [
            {
              item_id: 'item_001',
              name: values.dish_name,
              quantity: values.quantity,
              price: values.price,
            },
          ],
        },
      };

      const response = await apiClient.callAgent('order', request);

      if (response.output_data.success) {
        message.success('订单处理成功');
        form.resetFields();

        // 添加到订单列表
        const newOrder: Order = {
          order_id: request.order_id,
          store_id: values.store_id,
          table_number: values.table_number,
          status: 'pending',
          items: request.order_data.items,
          total_amount: values.price * values.quantity,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setOrders([newOrder, ...orders]);
      } else {
        message.error(response.output_data.error || '订单处理失败');
      }
    } catch (error: any) {
      message.error(error.message || '订单处理失败');
    } finally {
      setLoading(false);
    }
  };

  // 查看订单详情
  const handleViewDetails = (record: Order) => {
    setSelectedOrder(record);
    setModalVisible(true);
  };

  // 更新订单状态
  const handleUpdateStatus = async (orderId: string, newStatus: string) => {
    try {
      const request = {
        action: 'update_status',
        order_id: orderId,
        status: newStatus,
      };

      const response = await apiClient.callAgent('order', request);

      if (response.output_data.success) {
        message.success('订单状态已更新');
        setOrders(
          orders.map((order) =>
            order.order_id === orderId ? { ...order, status: newStatus } : order
          )
        );
      } else {
        message.error(response.output_data.error || '状态更新失败');
      }
    } catch (error: any) {
      message.error(error.message || '状态更新失败');
    }
  };

  const columns = [
    {
      title: '订单ID',
      dataIndex: 'order_id',
      key: 'order_id',
      width: 180,
    },
    {
      title: '门店ID',
      dataIndex: 'store_id',
      key: 'store_id',
    },
    {
      title: '桌号',
      dataIndex: 'table_number',
      key: 'table_number',
      width: 100,
    },
    {
      title: '订单金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 120,
      render: (amount: number) => `¥${(amount / 100).toFixed(2)}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const statusConfig: Record<string, { color: string; text: string; icon: any }> = {
          pending: { color: 'orange', text: '待处理', icon: <ClockCircleOutlined /> },
          processing: { color: 'blue', text: '处理中', icon: <ShoppingCartOutlined /> },
          completed: { color: 'green', text: '已完成', icon: <CheckCircleOutlined /> },
          cancelled: { color: 'red', text: '已取消', icon: <CloseCircleOutlined /> },
        };
        const config = statusConfig[status] || statusConfig.pending;
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: 250,
      render: (_: any, record: Order) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleViewDetails(record)}>
            详情
          </Button>
          {record.status === 'pending' && (
            <Button
              type="link"
              size="small"
              onClick={() => handleUpdateStatus(record.order_id, 'processing')}
            >
              开始处理
            </Button>
          )}
          {record.status === 'processing' && (
            <Button
              type="link"
              size="small"
              onClick={() => handleUpdateStatus(record.order_id, 'completed')}
            >
              完成
            </Button>
          )}
          {(record.status === 'pending' || record.status === 'processing') && (
            <Button
              type="link"
              danger
              size="small"
              onClick={() => handleUpdateStatus(record.order_id, 'cancelled')}
            >
              取消
            </Button>
          )}
        </Space>
      ),
    },
  ];

  // 统计数据
  const stats = {
    total: orders.length,
    pending: orders.filter((o) => o.status === 'pending').length,
    processing: orders.filter((o) => o.status === 'processing').length,
    completed: orders.filter((o) => o.status === 'completed').length,
  };

  // 过滤订单
  const filteredOrders = orders.filter((order) => {
    const matchesSearch =
      searchText === '' ||
      order.order_id.toLowerCase().includes(searchText.toLowerCase()) ||
      order.store_id.toLowerCase().includes(searchText.toLowerCase()) ||
      order.table_number.toLowerCase().includes(searchText.toLowerCase());

    const matchesStatus = statusFilter === 'all' || order.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>订单协同Agent</h1>
        <Button
          icon={<ReloadOutlined />}
          onClick={loadOrders}
          loading={loading}
        >
          刷新
        </Button>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总订单数"
              value={stats.total}
              prefix={<ShoppingCartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="待处理"
              value={stats.pending}
              valueStyle={{ color: '#faad14' }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="处理中"
              value={stats.processing}
              valueStyle={{ color: '#1890ff' }}
              prefix={<ShoppingCartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已完成"
              value={stats.completed}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Tabs defaultActiveKey="create">
        <TabPane tab="创建订单" key="create">
          <Card>
            <Form form={form} layout="vertical" onFinish={handleProcessOrder}>
              <Form.Item
                label="门店ID"
                name="store_id"
                rules={[{ required: true, message: '请输入门店ID' }]}
              >
                <Input placeholder="例如: store_001" />
              </Form.Item>

              <Form.Item
                label="桌号"
                name="table_number"
                rules={[{ required: true, message: '请输入桌号' }]}
              >
                <Input placeholder="例如: A01" />
              </Form.Item>

              <Form.Item
                label="菜品名称"
                name="dish_name"
                rules={[{ required: true, message: '请输入菜品名称' }]}
              >
                <Input placeholder="请输入菜品名称" />
              </Form.Item>

              <Form.Item
                label="数量"
                name="quantity"
                rules={[
                  { required: true, message: '请输入数量' },
                  { type: 'number', min: 1, max: 99, message: '数量必须在1-99之间' }
                ]}
              >
                <InputNumber min={1} max={99} style={{ width: '100%' }} placeholder="请输入数量" />
              </Form.Item>

              <Form.Item
                label="单价(分)"
                name="price"
                rules={[
                  { required: true, message: '请输入单价' },
                  { type: 'number', min: 1, message: '单价必须大于0' }
                ]}
                tooltip="请输入以分为单位的价格，例如：3000表示30元"
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="例如: 3000 (30元)" />
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    创建订单
                  </Button>
                  <Button onClick={() => form.resetFields()}>重置</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>

        <TabPane tab="订单列表" key="list">
          <Card>
            <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
              <Space>
                <Input
                  placeholder="搜索订单ID、门店ID或桌号"
                  prefix={<SearchOutlined />}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  style={{ width: 300 }}
                  allowClear
                />
                <Select
                  value={statusFilter}
                  onChange={setStatusFilter}
                  style={{ width: 120 }}
                >
                  <Select.Option value="all">全部状态</Select.Option>
                  <Select.Option value="pending">待处理</Select.Option>
                  <Select.Option value="processing">处理中</Select.Option>
                  <Select.Option value="completed">已完成</Select.Option>
                  <Select.Option value="cancelled">已取消</Select.Option>
                </Select>
              </Space>
              <span style={{ color: '#999' }}>
                共 {filteredOrders.length} 条记录
              </span>
            </Space>
            <Table
              dataSource={filteredOrders}
              columns={columns}
              rowKey="order_id"
              pagination={{ pageSize: 10 }}
              locale={{
                emptyText: orders.length === 0
                  ? '暂无订单记录，请先创建订单'
                  : '没有符合条件的订单'
              }}
              loading={loading}
            />
          </Card>
        </TabPane>
      </Tabs>

      {/* 订单详情Modal */}
      <Modal
        title="订单详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={600}
      >
        {selectedOrder && (
          <div>
            <p>
              <strong>订单ID:</strong> {selectedOrder.order_id}
            </p>
            <p>
              <strong>门店ID:</strong> {selectedOrder.store_id}
            </p>
            <p>
              <strong>桌号:</strong> {selectedOrder.table_number}
            </p>
            <p>
              <strong>状态:</strong>{' '}
              <Tag
                color={
                  selectedOrder.status === 'completed'
                    ? 'green'
                    : selectedOrder.status === 'pending'
                    ? 'orange'
                    : selectedOrder.status === 'processing'
                    ? 'blue'
                    : 'red'
                }
              >
                {selectedOrder.status}
              </Tag>
            </p>
            <p>
              <strong>订单金额:</strong> ¥{(selectedOrder.total_amount / 100).toFixed(2)}
            </p>
            <p>
              <strong>菜品列表:</strong>
            </p>
            <ul>
              {selectedOrder.items.map((item: any, index: number) => (
                <li key={index}>
                  {item.name} × {item.quantity} - ¥{(item.price / 100).toFixed(2)}
                </li>
              ))}
            </ul>
            <p>
              <strong>创建时间:</strong>{' '}
              {new Date(selectedOrder.created_at).toLocaleString('zh-CN')}
            </p>
            <p>
              <strong>更新时间:</strong>{' '}
              {new Date(selectedOrder.updated_at).toLocaleString('zh-CN')}
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default OrderPage;
