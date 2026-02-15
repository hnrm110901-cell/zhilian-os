import React, { useState } from 'react';
import { Form, Input, Button, Card, Space, Typography, Divider } from 'antd';
import { UserOutlined, LockOutlined, LoginOutlined } from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';

const { Title, Text } = Typography;

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    const success = await login(values.username, values.password);
    setLoading(false);

    if (success) {
      navigate('/');
    }
  };

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }}>
      <Card
        style={{
          width: 400,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          borderRadius: 8
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2} style={{ marginBottom: 8 }}>智链OS</Title>
          <Text type="secondary">餐饮行业智能管理系统</Text>
        </div>

        <Form
          name="login"
          onFinish={onFinish}
          autoComplete="off"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              icon={<LoginOutlined />}
              block
            >
              登录
            </Button>
          </Form.Item>
        </Form>

        <Divider>测试账号</Divider>

        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Card size="small" style={{ background: '#f5f5f5' }}>
            <Text strong>管理员: </Text>
            <Text copyable>admin / admin123</Text>
          </Card>
          <Card size="small" style={{ background: '#f5f5f5' }}>
            <Text strong>经理: </Text>
            <Text copyable>manager / manager123</Text>
          </Card>
          <Card size="small" style={{ background: '#f5f5f5' }}>
            <Text strong>员工: </Text>
            <Text copyable>staff / staff123</Text>
          </Card>
        </Space>
      </Card>
    </div>
  );
};

export default LoginPage;
