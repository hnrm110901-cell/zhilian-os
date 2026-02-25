import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Space,
  Badge,
  Tabs,
  Checkbox,
} from 'antd';
import {
  BellOutlined,
  SendOutlined,
  MailOutlined,
  MessageOutlined,
  WechatOutlined,
  MobileOutlined,
} from '@ant-design/icons';
import { apiClient } from '../services/api';
import { showSuccess, handleApiError } from '../utils/message';

const { TabPane } = Tabs;
const { TextArea } = Input;
const { Option } = Select;

const NotificationCenter: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any>({});
  const [unreadCount, setUnreadCount] = useState(0);
  const [sendModalVisible, setSendModalVisible] = useState(false);
  const [templateModalVisible, setTemplateModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [templateForm] = Form.useForm();

  useEffect(() => {
    loadNotifications();
    loadTemplates();
    loadUnreadCount();
  }, []);

  const loadNotifications = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/notifications');
      setNotifications(response.data || []);
    } catch (err: any) {
      handleApiError(err, '加载通知列表失败');
    } finally {
      setLoading(false);
    }
  };

  const loadTemplates = async () => {
    try {
      const response = await apiClient.get('/notifications/templates');
      setTemplates(response.data.templates || {});
    } catch (err: any) {
      handleApiError(err, '加载通知模板失败');
    }
  };

  const loadUnreadCount = async () => {
    try {
      const response = await apiClient.get('/notifications/unread-count');
      setUnreadCount(response.data.unread_count || 0);
    } catch (err: any) {
      handleApiError(err, '加载未读数量失败');
    }
  };

  const handleSendMultiChannel = async (values: any) => {
    try {
      await apiClient.post('/notifications/multi-channel', values);
      showSuccess('多渠道通知发送成功');
      setSendModalVisible(false);
      form.resetFields();
    } catch (err: any) {
      handleApiError(err, '发送通知失败');
    }
  };

  const handleSendTemplate = async (values: any) => {
    try {
      await apiClient.post('/notifications/template', values);
      showSuccess('模板通知发送成功');
      setTemplateModalVisible(false);
      templateForm.resetFields();
    } catch (err: any) {
      handleApiError(err, '发送模板通知失败');
    }
  };

  const handleMarkAsRead = async (notificationId: string) => {
    try {
      await apiClient.put(`/notifications/${notificationId}/read`);
      showSuccess('已标记为已读');
      loadNotifications();
      loadUnreadCount();
    } catch (err: any) {
      handleApiError(err, '标记失败');
    }
  };

  const handleMarkAllAsRead = async () => {
    try {
      await apiClient.put('/notifications/read-all');
      showSuccess('已全部标记为已读');
      loadNotifications();
      loadUnreadCount();
    } catch (err: any) {
      handleApiError(err, '标记失败');
    }
  };

  const handleDeleteNotification = async (notificationId: string) => {
    try {
      await apiClient.delete(`/notifications/${notificationId}`);
      showSuccess('通知已删除');
      loadNotifications();
      loadUnreadCount();
    } catch (err: any) {
      handleApiError(err, '删除失败');
    }
  };

  const notificationColumns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
    },
    {
      title: '内容',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => {
        const typeMap: any = {
          info: { color: 'blue', text: '信息' },
          warning: { color: 'orange', text: '警告' },
          error: { color: 'red', text: '错误' },
          success: { color: 'green', text: '成功' },
        };
        const t = typeMap[type] || { color: 'default', text: type };
        return <Tag color={t.color}>{t.text}</Tag>;
      },
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (priority: string) => {
        const priorityMap: any = {
          low: { color: 'default', text: '低' },
          normal: { color: 'blue', text: '普通' },
          high: { color: 'orange', text: '高' },
          urgent: { color: 'red', text: '紧急' },
        };
        const p = priorityMap[priority] || { color: 'default', text: priority };
        return <Tag color={p.color}>{p.text}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'is_read',
      key: 'is_read',
      render: (isRead: boolean) => (
        <Badge
          status={isRead ? 'default' : 'processing'}
          text={isRead ? '已读' : '未读'}
        />
      ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => (
        <Space>
          {!record.is_read && (
            <Button
              type="link"
              size="small"
              onClick={() => handleMarkAsRead(record.id)}
            >
              标记已读
            </Button>
          )}
          <Button
            type="link"
            size="small"
            danger
            onClick={() => handleDeleteNotification(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const channelIcons: any = {
    email: <MailOutlined />,
    sms: <MessageOutlined />,
    wechat: <WechatOutlined />,
    app_push: <MobileOutlined />,
  };

  const channelNames: any = {
    email: '邮件',
    sms: '短信',
    wechat: '微信',
    app_push: 'App推送',
  };

  return (
    <div>
      <h1 style={{ marginBottom: '24px' }}>
        <BellOutlined /> 通知中心
        {unreadCount > 0 && (
          <Badge count={unreadCount} style={{ marginLeft: '12px' }} />
        )}
      </h1>

      <Card>
        <Tabs defaultActiveKey="list">
          <TabPane tab="通知列表" key="list">
            <Space style={{ marginBottom: '16px' }}>
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={() => setSendModalVisible(true)}
              >
                发送多渠道通知
              </Button>
              <Button
                icon={<SendOutlined />}
                onClick={() => setTemplateModalVisible(true)}
              >
                发送模板通知
              </Button>
              <Button onClick={handleMarkAllAsRead}>全部标记为已读</Button>
            </Space>

            <Table
              columns={notificationColumns}
              dataSource={notifications}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="通知模板" key="templates">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
              {Object.entries(templates).map(([name, template]: [string, any]) => (
                <Card
                  key={name}
                  title={template.title}
                  size="small"
                  extra={
                    <Button
                      type="link"
                      size="small"
                      onClick={() => {
                        templateForm.setFieldsValue({ template_name: name });
                        setTemplateModalVisible(true);
                      }}
                    >
                      使用
                    </Button>
                  }
                >
                  <p style={{ fontSize: '12px', color: '#666' }}>{template.content}</p>
                  <div style={{ marginTop: '8px' }}>
                    <Space size="small">
                      {template.channels.map((ch: string) => (
                        <Tag key={ch} icon={channelIcons[ch]}>
                          {channelNames[ch]}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                  <div style={{ marginTop: '8px' }}>
                    <Tag color={template.priority === 'urgent' ? 'red' : 'blue'}>
                      {template.priority}
                    </Tag>
                  </div>
                </Card>
              ))}
            </div>
          </TabPane>
        </Tabs>
      </Card>

      {/* 发送多渠道通知模态框 */}
      <Modal
        title="发送多渠道通知"
        open={sendModalVisible}
        onCancel={() => setSendModalVisible(false)}
        footer={null}
        width={600}
      >
        <Form form={form} onFinish={handleSendMultiChannel} layout="vertical">
          <Form.Item
            name="channels"
            label="通知渠道"
            rules={[{ required: true, message: '请选择至少一个通知渠道' }]}
          >
            <Checkbox.Group>
              <Space direction="vertical">
                <Checkbox value="email">
                  <MailOutlined /> 邮件通知
                </Checkbox>
                <Checkbox value="sms">
                  <MessageOutlined /> 短信通知
                </Checkbox>
                <Checkbox value="wechat">
                  <WechatOutlined /> 微信通知
                </Checkbox>
                <Checkbox value="app_push">
                  <MobileOutlined /> App推送
                </Checkbox>
              </Space>
            </Checkbox.Group>
          </Form.Item>

          <Form.Item
            name="recipient"
            label="收件人"
            rules={[{ required: true, message: '请输入收件人' }]}
          >
            <Input placeholder="邮箱/手机号/OpenID/设备Token" />
          </Form.Item>

          <Form.Item
            name="title"
            label="通知标题"
            rules={[{ required: true, message: '请输入通知标题' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="content"
            label="通知内容"
            rules={[{ required: true, message: '请输入通知内容' }]}
          >
            <TextArea rows={4} />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                发送
              </Button>
              <Button onClick={() => setSendModalVisible(false)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 发送模板通知模态框 */}
      <Modal
        title="发送模板通知"
        open={templateModalVisible}
        onCancel={() => setTemplateModalVisible(false)}
        footer={null}
        width={600}
      >
        <Form form={templateForm} onFinish={handleSendTemplate} layout="vertical">
          <Form.Item
            name="template_name"
            label="选择模板"
            rules={[{ required: true, message: '请选择模板' }]}
          >
            <Select placeholder="选择通知模板">
              {Object.entries(templates).map(([name, template]: [string, any]) => (
                <Option key={name} value={name}>
                  {template.title}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="recipient"
            label="收件人"
            rules={[{ required: true, message: '请输入收件人' }]}
          >
            <Input placeholder="邮箱/手机号/OpenID/设备Token" />
          </Form.Item>

          <Form.Item
            name="template_vars"
            label="模板变量 (JSON格式)"
            rules={[{ required: true, message: '请输入模板变量' }]}
          >
            <TextArea
              rows={4}
              placeholder='{"order_id": "12345", "estimated_time": "30分钟"}'
            />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                发送
              </Button>
              <Button onClick={() => setTemplateModalVisible(false)}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default NotificationCenter;
