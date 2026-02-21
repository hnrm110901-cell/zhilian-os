import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Switch,
  message,
  Tabs,
  Space,
  Divider,
  Alert,
  Row,
  Col,
  Statistic,
} from 'antd';
import {
  WechatOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { usePermission } from '../hooks/usePermission';
import { useNavigate } from 'react-router-dom';
import enterpriseService from '../services/enterpriseIntegration';
import type { WeChatWorkConfig, FeishuConfig } from '../types/enterprise';

const { TabPane } = Tabs;
const { TextArea } = Input;

const EnterpriseIntegrationPage: React.FC = () => {
  const [wechatForm] = Form.useForm();
  const [feishuForm] = Form.useForm();
  const [testMessageForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ wechat: { enabled: false }, feishu: { enabled: false } });
  const { isAdmin } = usePermission();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isAdmin) {
      message.error('您没有权限访问此页面');
      navigate('/');
      return;
    }
    loadStatus();
  }, [isAdmin, navigate]);

  const loadStatus = () => {
    const currentStatus = enterpriseService.getStatus();
    setStatus(currentStatus);
  };

  const handleWeChatSave = async (values: WeChatWorkConfig) => {
    setLoading(true);
    try {
      enterpriseService.updateWeChatConfig(values);
      message.success('企业微信配置已保存');
      loadStatus();
    } catch (error) {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleFeishuSave = async (values: FeishuConfig) => {
    setLoading(true);
    try {
      enterpriseService.updateFeishuConfig(values);
      message.success('飞书配置已保存');
      loadStatus();
    } catch (error) {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleTestMessage = async (values: any) => {
    setLoading(true);
    try {
      const result = await enterpriseService.broadcastNotification({
        title: '测试消息',
        content: values.content,
        type: 'text',
      });

      if (result.wechat || result.feishu) {
        message.success('测试消息已发送');
      } else {
        message.warning('没有启用的平台');
      }
    } catch (error) {
      message.error('发送失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>企业集成</h1>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card>
            <Statistic
              title="企业微信"
              value={status.wechat.enabled ? '已启用' : '未启用'}
              prefix={<WechatOutlined />}
              valueStyle={{ color: status.wechat.enabled ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            <Statistic
              title="飞书"
              value={status.feishu.enabled ? '已启用' : '未启用'}
              prefix={status.feishu.enabled ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
              valueStyle={{ color: status.feishu.enabled ? '#3f8600' : '#cf1322' }}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs defaultActiveKey="1">
          <TabPane tab="企业微信" key="1">
            <Alert
              message="企业微信配置说明"
              description="请在企业微信管理后台获取以下配置信息。配置完成后，系统可以通过企业微信发送通知消息。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />

            <Form
              form={wechatForm}
              layout="vertical"
              onFinish={handleWeChatSave}
              initialValues={{
                enabled: false,
              }}
            >
              <Form.Item
                name="enabled"
                label="启用企业微信"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>

              <Form.Item
                name="corpId"
                label="企业ID (Corp ID)"
                rules={[{ required: true, message: '请输入企业ID' }]}
              >
                <Input placeholder="请输入企业ID" />
              </Form.Item>

              <Form.Item
                name="appId"
                label="应用ID (App ID)"
                rules={[{ required: true, message: '请输入应用ID' }]}
              >
                <Input placeholder="请输入应用ID" />
              </Form.Item>

              <Form.Item
                name="appSecret"
                label="应用密钥 (App Secret)"
                rules={[{ required: true, message: '请输入应用密钥' }]}
              >
                <Input.Password placeholder="请输入应用密钥" />
              </Form.Item>

              <Form.Item
                name="agentId"
                label="应用AgentId"
                rules={[{ required: true, message: '请输入AgentId' }]}
              >
                <Input placeholder="请输入AgentId" />
              </Form.Item>

              <Form.Item
                name="webhookUrl"
                label="Webhook URL (可选)"
              >
                <Input placeholder="请输入Webhook URL" />
              </Form.Item>

              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading}>
                  保存配置
                </Button>
              </Form.Item>
            </Form>
          </TabPane>

          <TabPane tab="飞书" key="2">
            <Alert
              message="飞书配置说明"
              description="请在飞书开放平台获取以下配置信息。配置完成后，系统可以通过飞书发送通知消息。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />

            <Form
              form={feishuForm}
              layout="vertical"
              onFinish={handleFeishuSave}
              initialValues={{
                enabled: false,
              }}
            >
              <Form.Item
                name="enabled"
                label="启用飞书"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>

              <Form.Item
                name="appId"
                label="应用ID (App ID)"
                rules={[{ required: true, message: '请输入应用ID' }]}
              >
                <Input placeholder="请输入应用ID" />
              </Form.Item>

              <Form.Item
                name="appSecret"
                label="应用密钥 (App Secret)"
                rules={[{ required: true, message: '请输入应用密钥' }]}
              >
                <Input.Password placeholder="请输入应用密钥" />
              </Form.Item>

              <Form.Item
                name="webhookUrl"
                label="Webhook URL (可选)"
              >
                <Input placeholder="请输入Webhook URL" />
              </Form.Item>

              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading}>
                  保存配置
                </Button>
              </Form.Item>
            </Form>
          </TabPane>

          <TabPane tab="测试消息" key="3">
            <Alert
              message="发送测试消息"
              description="向所有启用的平台发送测试消息，验证配置是否正确。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />

            <Form
              form={testMessageForm}
              layout="vertical"
              onFinish={handleTestMessage}
            >
              <Form.Item
                name="content"
                label="消息内容"
                rules={[{ required: true, message: '请输入消息内容' }]}
              >
                <TextArea
                  rows={4}
                  placeholder="请输入测试消息内容"
                />
              </Form.Item>

              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  icon={<SendOutlined />}
                >
                  发送测试消息
                </Button>
              </Form.Item>
            </Form>

            <Divider />

            <h3>快捷测试</h3>
            <Space>
              <Button
                onClick={() => {
                  enterpriseService.sendOrderNotification('ORD-001', '已完成');
                  message.info('订单通知已发送');
                }}
              >
                测试订单通知
              </Button>
              <Button
                onClick={() => {
                  enterpriseService.sendInventoryAlert('牛肉', 5);
                  message.info('库存预警已发送');
                }}
              >
                测试库存预警
              </Button>
              <Button
                onClick={() => {
                  enterpriseService.sendServiceAlert('REV-001', 2);
                  message.info('服务预警已发送');
                }}
              >
                测试服务预警
              </Button>
            </Space>
          </TabPane>

          <TabPane tab="使用文档" key="4">
            <Card title="企业微信配置步骤">
              <ol>
                <li>登录企业微信管理后台</li>
                <li>进入"应用管理" → "自建应用"</li>
                <li>创建新应用或选择现有应用</li>
                <li>获取 Corp ID、App ID、App Secret、Agent ID</li>
                <li>配置可信域名和IP白名单</li>
                <li>在本页面填写配置信息并启用</li>
              </ol>
            </Card>

            <Card title="飞书配置步骤" style={{ marginTop: 16 }}>
              <ol>
                <li>登录飞书开放平台</li>
                <li>创建企业自建应用</li>
                <li>获取 App ID 和 App Secret</li>
                <li>配置应用权限（消息发送、通讯录读取等）</li>
                <li>配置事件订阅和回调地址</li>
                <li>在本页面填写配置信息并启用</li>
              </ol>
            </Card>

            <Card title="功能说明" style={{ marginTop: 16 }}>
              <p><strong>支持的消息类型：</strong></p>
              <ul>
                <li>文本消息：简单的文本通知</li>
                <li>Markdown消息：支持格式化的富文本</li>
                <li>卡片消息：交互式卡片，支持按钮和链接</li>
              </ul>

              <p><strong>自动通知场景：</strong></p>
              <ul>
                <li>订单状态变更通知</li>
                <li>库存不足预警</li>
                <li>服务质量预警（差评提醒）</li>
                <li>排班变更通知</li>
                <li>培训提醒</li>
              </ul>
            </Card>
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default EnterpriseIntegrationPage;
