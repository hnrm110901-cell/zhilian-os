import React, { useState } from 'react';
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
  Row,
  Col,
  Statistic,
  Progress,
  Alert,
} from 'antd';
import {
  InboxOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const { TabPane } = Tabs;

interface InventoryItem {
  item_id: string;
  name: string;
  category: string;
  current_stock: number;
  min_stock: number;
  max_stock: number;
  unit: string;
  status: 'normal' | 'low' | 'critical' | 'out';
  last_updated: string;
}

const InventoryPage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [inventory, setInventory] = useState<InventoryItem[]>([
    {
      item_id: 'INV_001',
      name: '大米',
      category: '主食',
      current_stock: 50,
      min_stock: 20,
      max_stock: 100,
      unit: 'kg',
      status: 'normal',
      last_updated: new Date().toISOString(),
    },
    {
      item_id: 'INV_002',
      name: '食用油',
      category: '调料',
      current_stock: 15,
      min_stock: 20,
      max_stock: 50,
      unit: 'L',
      status: 'low',
      last_updated: new Date().toISOString(),
    },
    {
      item_id: 'INV_003',
      name: '鸡蛋',
      category: '食材',
      current_stock: 5,
      min_stock: 30,
      max_stock: 100,
      unit: '盒',
      status: 'critical',
      last_updated: new Date().toISOString(),
    },
  ]);
  const [selectedItem, setSelectedItem] = useState<InventoryItem | null>(null);
  const [modalVisible, setModalVisible] = useState(false);

  // 检查库存
  const handleCheckInventory = async (values: any) => {
    try {
      setLoading(true);

      const request = {
        action: 'check',
        store_id: values.store_id,
        items: [values.item_name],
      };

      const response = await apiClient.callAgent('inventory', request);

      if (response.output_data.success) {
        message.success('库存检查完成');
        form.resetFields();
      } else {
        message.error(response.output_data.error || '库存检查失败');
      }
    } catch (error: any) {
      message.error(error.message || '库存检查失败');
    } finally {
      setLoading(false);
    }
  };

  // 查看详情
  const handleViewDetails = (record: InventoryItem) => {
    setSelectedItem(record);
    setModalVisible(true);
  };

  // 更新库存
  const handleUpdateStock = (itemId: string, newStock: number) => {
    setInventory(
      inventory.map((item) => {
        if (item.item_id === itemId) {
          let status: 'normal' | 'low' | 'critical' | 'out' = 'normal';
          if (newStock === 0) {
            status = 'out';
          } else if (newStock < item.min_stock * 0.5) {
            status = 'critical';
          } else if (newStock < item.min_stock) {
            status = 'low';
          }
          return { ...item, current_stock: newStock, status };
        }
        return item;
      })
    );
    message.success('库存已更新');
  };

  const columns = [
    {
      title: '物品ID',
      dataIndex: 'item_id',
      key: 'item_id',
      width: 120,
    },
    {
      title: '物品名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
    },
    {
      title: '当前库存',
      dataIndex: 'current_stock',
      key: 'current_stock',
      width: 120,
      render: (stock: number, record: InventoryItem) => (
        <span>
          {stock} {record.unit}
        </span>
      ),
    },
    {
      title: '库存状态',
      key: 'stock_level',
      width: 150,
      render: (_: any, record: InventoryItem) => {
        const percentage = (record.current_stock / record.max_stock) * 100;
        let status: 'success' | 'normal' | 'exception' = 'success';
        if (record.status === 'critical' || record.status === 'out') {
          status = 'exception';
        } else if (record.status === 'low') {
          status = 'normal';
        }
        return <Progress percent={Math.round(percentage)} status={status} size="small" />;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const statusConfig: Record<
          string,
          { color: string; text: string; icon: any }
        > = {
          normal: { color: 'green', text: '正常', icon: <CheckCircleOutlined /> },
          low: { color: 'orange', text: '偏低', icon: <WarningOutlined /> },
          critical: {
            color: 'red',
            text: '紧急',
            icon: <ExclamationCircleOutlined />,
          },
          out: { color: 'red', text: '缺货', icon: <ExclamationCircleOutlined /> },
        };
        const config = statusConfig[status] || statusConfig.normal;
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: InventoryItem) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleViewDetails(record)}>
            详情
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              const newStock = prompt('请输入新库存数量:', record.current_stock.toString());
              if (newStock !== null) {
                handleUpdateStock(record.item_id, parseInt(newStock));
              }
            }}
          >
            更新
          </Button>
        </Space>
      ),
    },
  ];

  // 统计数据
  const stats = {
    total: inventory.length,
    normal: inventory.filter((i) => i.status === 'normal').length,
    low: inventory.filter((i) => i.status === 'low').length,
    critical: inventory.filter((i) => i.status === 'critical' || i.status === 'out').length,
  };

  // 预警列表
  const alerts = inventory.filter((i) => i.status !== 'normal');

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>库存预警Agent</h1>

      {/* 预警提示 */}
      {alerts.length > 0 && (
        <Alert
          message={`库存预警: ${alerts.length}个物品需要补货`}
          description={
            <ul style={{ marginBottom: 0 }}>
              {alerts.map((item) => (
                <li key={item.item_id}>
                  {item.name}: 当前库存 {item.current_stock} {item.unit}, 最低库存{' '}
                  {item.min_stock} {item.unit}
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

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总物品数"
              value={stats.total}
              prefix={<InboxOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="库存正常"
              value={stats.normal}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="库存偏低"
              value={stats.low}
              valueStyle={{ color: '#faad14' }}
              prefix={<WarningOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="紧急补货"
              value={stats.critical}
              valueStyle={{ color: '#cf1322' }}
              prefix={<ExclamationCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Tabs defaultActiveKey="list">
        <TabPane tab="库存列表" key="list">
          <Card>
            <Table
              dataSource={inventory}
              columns={columns}
              rowKey="item_id"
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: '暂无库存记录' }}
            />
          </Card>
        </TabPane>

        <TabPane tab="库存检查" key="check">
          <Card>
            <Form form={form} layout="vertical" onFinish={handleCheckInventory}>
              <Form.Item
                label="门店ID"
                name="store_id"
                rules={[{ required: true, message: '请输入门店ID' }]}
              >
                <Input placeholder="例如: store_001" />
              </Form.Item>

              <Form.Item
                label="物品名称"
                name="item_name"
                rules={[{ required: true, message: '请输入物品名称' }]}
              >
                <Input placeholder="请输入物品名称" />
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    检查库存
                  </Button>
                  <Button onClick={() => form.resetFields()}>重置</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>
      </Tabs>

      {/* 库存详情Modal */}
      <Modal
        title="库存详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={600}
      >
        {selectedItem && (
          <div>
            <p>
              <strong>物品ID:</strong> {selectedItem.item_id}
            </p>
            <p>
              <strong>物品名称:</strong> {selectedItem.name}
            </p>
            <p>
              <strong>分类:</strong> {selectedItem.category}
            </p>
            <p>
              <strong>当前库存:</strong> {selectedItem.current_stock} {selectedItem.unit}
            </p>
            <p>
              <strong>最低库存:</strong> {selectedItem.min_stock} {selectedItem.unit}
            </p>
            <p>
              <strong>最大库存:</strong> {selectedItem.max_stock} {selectedItem.unit}
            </p>
            <p>
              <strong>状态:</strong>{' '}
              <Tag
                color={
                  selectedItem.status === 'normal'
                    ? 'green'
                    : selectedItem.status === 'low'
                    ? 'orange'
                    : 'red'
                }
              >
                {selectedItem.status}
              </Tag>
            </p>
            <p>
              <strong>库存率:</strong>{' '}
              <Progress
                percent={Math.round(
                  (selectedItem.current_stock / selectedItem.max_stock) * 100
                )}
                status={
                  selectedItem.status === 'normal'
                    ? 'success'
                    : selectedItem.status === 'low'
                    ? 'normal'
                    : 'exception'
                }
              />
            </p>
            <p>
              <strong>最后更新:</strong>{' '}
              {new Date(selectedItem.last_updated).toLocaleString('zh-CN')}
            </p>
            {selectedItem.status !== 'normal' && (
              <Alert
                message="补货建议"
                description={`建议补货数量: ${
                  selectedItem.max_stock - selectedItem.current_stock
                } ${selectedItem.unit}`}
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
