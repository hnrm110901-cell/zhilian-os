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
  Rate,
  Progress,
  List,
  Avatar,
} from 'antd';
import {
  CustomerServiceOutlined,
  SmileOutlined,
  MehOutlined,
  FrownOutlined,
  StarOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';

const { TabPane } = Tabs;

interface Review {
  review_id: string;
  customer_name: string;
  rating: number;
  comment: string;
  category: string;
  status: 'pending' | 'resolved' | 'ignored';
  created_at: string;
}

const ServicePage: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [reviews, setReviews] = useState<Review[]>([
    {
      review_id: 'REV_001',
      customer_name: '张三',
      rating: 5,
      comment: '服务态度很好，菜品也很美味！',
      category: '好评',
      status: 'resolved',
      created_at: new Date().toISOString(),
    },
    {
      review_id: 'REV_002',
      customer_name: '李四',
      rating: 3,
      comment: '上菜速度有点慢，希望改进。',
      category: '中评',
      status: 'pending',
      created_at: new Date().toISOString(),
    },
    {
      review_id: 'REV_003',
      customer_name: '王五',
      rating: 1,
      comment: '服务员态度差，菜品不新鲜！',
      category: '差评',
      status: 'pending',
      created_at: new Date().toISOString(),
    },
  ]);
  const [selectedReview, setSelectedReview] = useState<Review | null>(null);
  const [modalVisible, setModalVisible] = useState(false);

  // 分析服务质量
  const handleAnalyze = async (values: any) => {
    try {
      setLoading(true);

      const request = {
        action: 'analyze',
        store_id: values.store_id,
        date: values.date,
      };

      const response = await apiClient.callAgent('service', request);

      if (response.output_data.success) {
        message.success('服务质量分析完成');
        form.resetFields();
      } else {
        message.error(response.output_data.error || '分析失败');
      }
    } catch (error: any) {
      message.error(error.message || '分析失败');
    } finally {
      setLoading(false);
    }
  };

  // 查看详情
  const handleViewDetails = (record: Review) => {
    setSelectedReview(record);
    setModalVisible(true);
  };

  // 更新状态
  const handleUpdateStatus = (reviewId: string, newStatus: 'resolved' | 'ignored') => {
    setReviews(
      reviews.map((review) =>
        review.review_id === reviewId ? { ...review, status: newStatus } : review
      )
    );
    message.success('状态已更新');
  };

  const columns = [
    {
      title: '评价ID',
      dataIndex: 'review_id',
      key: 'review_id',
      width: 120,
    },
    {
      title: '客户姓名',
      dataIndex: 'customer_name',
      key: 'customer_name',
    },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      width: 150,
      render: (rating: number) => <Rate disabled value={rating} />,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (category: string) => {
        const colorMap: Record<string, string> = {
          好评: 'green',
          中评: 'orange',
          差评: 'red',
        };
        return <Tag color={colorMap[category]}>{category}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const statusMap: Record<string, { color: string; text: string }> = {
          pending: { color: 'orange', text: '待处理' },
          resolved: { color: 'green', text: '已处理' },
          ignored: { color: 'default', text: '已忽略' },
        };
        const config = statusMap[status] || statusMap.pending;
        return <Tag color={config.color}>{config.text}</Tag>;
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
      width: 200,
      render: (_: any, record: Review) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleViewDetails(record)}>
            详情
          </Button>
          {record.status === 'pending' && (
            <>
              <Button
                type="link"
                size="small"
                onClick={() => handleUpdateStatus(record.review_id, 'resolved')}
              >
                处理
              </Button>
              <Button
                type="link"
                size="small"
                onClick={() => handleUpdateStatus(record.review_id, 'ignored')}
              >
                忽略
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  // 统计数据
  const stats = {
    total: reviews.length,
    good: reviews.filter((r) => r.rating >= 4).length,
    medium: reviews.filter((r) => r.rating === 3).length,
    bad: reviews.filter((r) => r.rating <= 2).length,
    avgRating: (reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length).toFixed(1),
  };

  // 待处理差评
  const badReviews = reviews.filter((r) => r.rating <= 2 && r.status === 'pending');

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>服务质量Agent</h1>

      {/* 差评预警 */}
      {badReviews.length > 0 && (
        <Card
          style={{ marginBottom: 24, borderColor: '#ff4d4f' }}
          title={
            <span style={{ color: '#ff4d4f' }}>
              <FrownOutlined /> 差评预警: {badReviews.length}条待处理
            </span>
          }
        >
          <List
            dataSource={badReviews}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button
                    type="link"
                    onClick={() => handleUpdateStatus(item.review_id, 'resolved')}
                  >
                    立即处理
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<Avatar icon={<FrownOutlined />} style={{ backgroundColor: '#ff4d4f' }} />}
                  title={`${item.customer_name} - ${item.rating}星`}
                  description={item.comment}
                />
              </List.Item>
            )}
          />
        </Card>
      )}

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总评价数"
              value={stats.total}
              prefix={<CustomerServiceOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="好评"
              value={stats.good}
              valueStyle={{ color: '#52c41a' }}
              prefix={<SmileOutlined />}
              suffix={`/ ${stats.total}`}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="中评"
              value={stats.medium}
              valueStyle={{ color: '#faad14' }}
              prefix={<MehOutlined />}
              suffix={`/ ${stats.total}`}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均评分"
              value={stats.avgRating}
              valueStyle={{ color: '#1890ff' }}
              prefix={<StarOutlined />}
              suffix="/ 5.0"
            />
          </Card>
        </Col>
      </Row>

      {/* 满意度进度条 */}
      <Card style={{ marginBottom: 24 }}>
        <h3>客户满意度分布</h3>
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 16 }}>
            <span style={{ display: 'inline-block', width: 80 }}>好评 (4-5星)</span>
            <Progress
              percent={Math.round((stats.good / stats.total) * 100)}
              status="success"
              style={{ width: 'calc(100% - 100px)', display: 'inline-block' }}
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <span style={{ display: 'inline-block', width: 80 }}>中评 (3星)</span>
            <Progress
              percent={Math.round((stats.medium / stats.total) * 100)}
              status="normal"
              style={{ width: 'calc(100% - 100px)', display: 'inline-block' }}
            />
          </div>
          <div>
            <span style={{ display: 'inline-block', width: 80 }}>差评 (1-2星)</span>
            <Progress
              percent={Math.round((stats.bad / stats.total) * 100)}
              status="exception"
              style={{ width: 'calc(100% - 100px)', display: 'inline-block' }}
            />
          </div>
        </div>
      </Card>

      <Tabs defaultActiveKey="list">
        <TabPane tab="评价列表" key="list">
          <Card>
            <Table
              dataSource={reviews}
              columns={columns}
              rowKey="review_id"
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: '暂无评价记录' }}
            />
          </Card>
        </TabPane>

        <TabPane tab="质量分析" key="analyze">
          <Card>
            <Form form={form} layout="vertical" onFinish={handleAnalyze}>
              <Form.Item
                label="门店ID"
                name="store_id"
                rules={[{ required: true, message: '请输入门店ID' }]}
              >
                <Input placeholder="例如: store_001" />
              </Form.Item>

              <Form.Item
                label="分析日期"
                name="date"
                rules={[{ required: true, message: '请输入日期' }]}
              >
                <Input placeholder="例如: 2024-02-15" />
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    开始分析
                  </Button>
                  <Button onClick={() => form.resetFields()}>重置</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>
      </Tabs>

      {/* 评价详情Modal */}
      <Modal
        title="评价详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={600}
      >
        {selectedReview && (
          <div>
            <p>
              <strong>评价ID:</strong> {selectedReview.review_id}
            </p>
            <p>
              <strong>客户姓名:</strong> {selectedReview.customer_name}
            </p>
            <p>
              <strong>评分:</strong> <Rate disabled value={selectedReview.rating} />
            </p>
            <p>
              <strong>分类:</strong>{' '}
              <Tag
                color={
                  selectedReview.rating >= 4
                    ? 'green'
                    : selectedReview.rating === 3
                    ? 'orange'
                    : 'red'
                }
              >
                {selectedReview.category}
              </Tag>
            </p>
            <p>
              <strong>评价内容:</strong>
            </p>
            <Card style={{ backgroundColor: '#f5f5f5', marginBottom: 16 }}>
              {selectedReview.comment}
            </Card>
            <p>
              <strong>状态:</strong>{' '}
              <Tag
                color={
                  selectedReview.status === 'resolved'
                    ? 'green'
                    : selectedReview.status === 'pending'
                    ? 'orange'
                    : 'default'
                }
              >
                {selectedReview.status === 'resolved'
                  ? '已处理'
                  : selectedReview.status === 'pending'
                  ? '待处理'
                  : '已忽略'}
              </Tag>
            </p>
            <p>
              <strong>创建时间:</strong>{' '}
              {new Date(selectedReview.created_at).toLocaleString('zh-CN')}
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ServicePage;
