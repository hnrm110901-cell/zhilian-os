import React, { useState, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Tabs, Table, Tag, Space, Button, Form,
  Input, Select, Spin, Typography, Descriptions, InputNumber, Modal, Avatar
} from 'antd';
import {
  AppstoreOutlined, UserAddOutlined, ShopOutlined, ApiOutlined, DollarOutlined
} from '@ant-design/icons';
import { apiClient, handleApiError, showSuccess } from '../utils/api';

const { Title, Text } = Typography;
const { Option } = Select;

interface Plugin {
  plugin_id: string;
  name: string;
  description: string;
  category: string;
  version: string;
  price: number;
  installs: number;
  rating: number;
  status: string;
}

interface Developer {
  developer_id: string;
  api_key: string;
  api_secret: string;
  rate_limit: number;
}

const tierColor: Record<string, string> = { free: 'default', basic: 'blue', pro: 'purple', enterprise: 'gold' };
const statusColor: Record<string, string> = { approved: 'green', pending: 'orange', rejected: 'red' };

const OpenPlatformPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [developer, setDeveloper] = useState<Developer | null>(null);
  const [submitResult, setSubmitResult] = useState<Record<string, unknown> | null>(null);
  const [devForm] = Form.useForm();
  const [pluginForm] = Form.useForm();
  const [category, setCategory] = useState<string | undefined>(undefined);

  const loadMarketplace = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (category) params.set('category', category);
      params.set('sort_by', 'installs');
      const res = await apiClient.get(`/api/v1/platform/marketplace?${params}`);
      setPlugins(res.data.plugins || []);
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  }, [category]);

  const handleRegisterDev = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/platform/developer/register', values);
      setDeveloper(res.data);
      showSuccess('开发者注册成功');
      devForm.resetFields();
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const handleSubmitPlugin = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      const res = await apiClient.post('/api/v1/platform/plugin/submit', values);
      setSubmitResult(res.data);
      showSuccess('插件提交成功，等待审核');
      pluginForm.resetFields();
    } catch (err) { handleApiError(err); }
    finally { setLoading(false); }
  };

  const pluginColumns = [
    {
      title: '插件', key: 'name',
      render: (_: unknown, r: Plugin) => (
        <Space>
          <Avatar icon={<AppstoreOutlined />} style={{ background: '#1890ff' }} size="small" />
          <div>
            <div style={{ fontWeight: 500 }}>{r.name}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>{r.description}</Text>
          </div>
        </Space>
      ),
    },
    { title: '分类', dataIndex: 'category', key: 'category', render: (v: string) => <Tag>{v}</Tag> },
    { title: '版本', dataIndex: 'version', key: 'version' },
    {
      title: '价格', dataIndex: 'price', key: 'price',
      render: (v: number) => v === 0 ? <Tag color="green">免费</Tag> : `¥${v}/月`,
    },
    { title: '安装数', dataIndex: 'installs', key: 'installs' },
    { title: '评分', dataIndex: 'rating', key: 'rating', render: (v: number) => v?.toFixed(1) },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{v}</Tag>,
    },
  ];

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Title level={4} style={{ margin: 0 }}>开放平台</Title>

        <Card>
          <Tabs
            items={[
              {
                key: 'marketplace',
                label: '插件市场',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Space>
                      <Select
                        placeholder="筛选分类"
                        allowClear
                        style={{ width: 160 }}
                        onChange={setCategory}
                      >
                        <Option value="analytics">数据分析</Option>
                        <Option value="marketing">营销工具</Option>
                        <Option value="operations">运营管理</Option>
                        <Option value="integration">系统集成</Option>
                      </Select>
                      <Button type="primary" icon={<AppstoreOutlined />} onClick={loadMarketplace}>
                        加载插件市场
                      </Button>
                    </Space>
                    <Table
                      dataSource={plugins}
                      columns={pluginColumns}
                      rowKey="plugin_id"
                      size="small"
                      pagination={{ pageSize: 10 }}
                    />
                  </Space>
                ),
              },
              {
                key: 'register',
                label: '开发者注册',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={devForm} layout="vertical" onFinish={handleRegisterDev}>
                        <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
                          <Input placeholder="开发者姓名" />
                        </Form.Item>
                        <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
                          <Input placeholder="developer@example.com" />
                        </Form.Item>
                        <Form.Item name="company" label="公司（可选）">
                          <Input placeholder="公司名称" />
                        </Form.Item>
                        <Form.Item name="tier" label="套餐" initialValue="free">
                          <Select>
                            {['free', 'basic', 'pro', 'enterprise'].map(t => (
                              <Option key={t} value={t}>
                                <Tag color={tierColor[t]}>{t.toUpperCase()}</Tag>
                              </Option>
                            ))}
                          </Select>
                        </Form.Item>
                        <Button type="primary" htmlType="submit" icon={<UserAddOutlined />}>注册开发者</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      {developer && (
                        <Card size="small" title="注册成功 — 请妥善保存以下凭证">
                          <Descriptions column={1} size="small">
                            <Descriptions.Item label="开发者ID">{developer.developer_id}</Descriptions.Item>
                            <Descriptions.Item label="API Key">
                              <Text code copyable>{developer.api_key}</Text>
                            </Descriptions.Item>
                            <Descriptions.Item label="API Secret">
                              <Text code copyable>{developer.api_secret}</Text>
                            </Descriptions.Item>
                            <Descriptions.Item label="速率限制">{developer.rate_limit} 次/分钟</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      )}
                    </Col>
                  </Row>
                ),
              },
              {
                key: 'submit',
                label: '提交插件',
                children: (
                  <Row gutter={24}>
                    <Col span={12}>
                      <Form form={pluginForm} layout="vertical" onFinish={handleSubmitPlugin}>
                        <Form.Item name="developer_id" label="开发者ID" rules={[{ required: true }]}>
                          <Input placeholder="注册后获得的开发者ID" />
                        </Form.Item>
                        <Form.Item name="name" label="插件名称" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="description" label="描述" rules={[{ required: true }]}>
                          <Input.TextArea rows={3} />
                        </Form.Item>
                        <Form.Item name="category" label="分类" rules={[{ required: true }]}>
                          <Select>
                            <Option value="analytics">数据分析</Option>
                            <Option value="marketing">营销工具</Option>
                            <Option value="operations">运营管理</Option>
                            <Option value="integration">系统集成</Option>
                          </Select>
                        </Form.Item>
                        <Form.Item name="version" label="版本" initialValue="1.0.0" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="price" label="月费（元，0为免费）" initialValue={0}>
                          <InputNumber min={0} style={{ width: '100%' }} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit" icon={<ShopOutlined />}>提交审核</Button>
                      </Form>
                    </Col>
                    <Col span={12}>
                      {submitResult && (
                        <Card size="small" title="提交结果">
                          <Descriptions column={1} size="small">
                            <Descriptions.Item label="插件ID">{String(submitResult.plugin_id)}</Descriptions.Item>
                            <Descriptions.Item label="状态">
                              <Tag color={statusColor[String(submitResult.status)] || 'default'}>{String(submitResult.status)}</Tag>
                            </Descriptions.Item>
                            <Descriptions.Item label="分成比例">{String(submitResult.revenue_share)}</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      )}
                    </Col>
                  </Row>
                ),
              },
            ]}
          />
        </Card>
      </Space>
    </Spin>
  );
};

export default OpenPlatformPage;
