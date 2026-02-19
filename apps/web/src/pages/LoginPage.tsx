import React, { useState } from 'react';
import { Form, Input, Button, Card, Space, Typography, Divider, message } from 'antd';
import { UserOutlined, LockOutlined, LoginOutlined, RocketOutlined } from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useSearchParams } from 'react-router-dom';

const { Title, Text } = Typography;

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const success = await login(values.username, values.password);

      if (success) {
        message.success('登录成功！');
        // 获取重定向路径，如果没有则默认跳转到首页
        const redirect = searchParams.get('redirect') || '/';
        setTimeout(() => {
          navigate(redirect);
        }, 500);
      } else {
        message.error('登录失败，请检查用户名和密码');
      }
    } catch (error) {
      message.error('登录失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const quickLogin = (username: string, password: string) => {
    onFinish({ username, password });
  };

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* 背景装饰 */}
      <div style={{
        position: 'absolute',
        top: '-50%',
        right: '-10%',
        width: '600px',
        height: '600px',
        background: 'rgba(255, 255, 255, 0.1)',
        borderRadius: '50%',
        filter: 'blur(60px)',
      }} />
      <div style={{
        position: 'absolute',
        bottom: '-30%',
        left: '-10%',
        width: '500px',
        height: '500px',
        background: 'rgba(255, 255, 255, 0.1)',
        borderRadius: '50%',
        filter: 'blur(60px)',
      }} />

      <Card
        style={{
          width: 450,
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          borderRadius: 16,
          position: 'relative',
          zIndex: 1,
          animation: 'fadeInUp 0.6s ease-out',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            fontSize: 48,
            marginBottom: 16,
            animation: 'bounce 2s infinite',
          }}>
            🍜
          </div>
          <Title level={2} style={{ marginBottom: 8, color: '#667eea' }}>
            智链OS
          </Title>
          <Text type="secondary" style={{ fontSize: 16 }}>
            <RocketOutlined /> 餐饮行业智能管理系统
          </Text>
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
              prefix={<UserOutlined style={{ color: '#667eea' }} />}
              placeholder="用户名"
              style={{ borderRadius: 8 }}
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#667eea' }} />}
              placeholder="密码"
              style={{ borderRadius: 8 }}
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              icon={<LoginOutlined />}
              block
              style={{
                height: 48,
                borderRadius: 8,
                fontSize: 16,
                fontWeight: 500,
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                border: 'none',
              }}
            >
              {loading ? '登录中...' : '登录'}
            </Button>
          </Form.Item>
        </Form>

        <Divider style={{ margin: '24px 0' }}>快速登录</Divider>

        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Card
            size="small"
            hoverable
            onClick={() => quickLogin('admin', 'admin123')}
            style={{
              background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.3s',
            }}
          >
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text strong style={{ color: 'white', fontSize: 16 }}>👑 管理员</Text>
                <br />
                <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 12 }}>
                  admin / admin123
                </Text>
              </div>
              <LoginOutlined style={{ color: 'white', fontSize: 20 }} />
            </Space>
          </Card>

          <Card
            size="small"
            hoverable
            onClick={() => quickLogin('manager', 'manager123')}
            style={{
              background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.3s',
            }}
          >
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text strong style={{ color: 'white', fontSize: 16 }}>💼 店长</Text>
                <br />
                <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 12 }}>
                  manager / manager123
                </Text>
              </div>
              <LoginOutlined style={{ color: 'white', fontSize: 20 }} />
            </Space>
          </Card>

          <Card
            size="small"
            hoverable
            onClick={() => quickLogin('staff', 'staff123')}
            style={{
              background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.3s',
            }}
          >
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text strong style={{ color: 'white', fontSize: 16 }}>👤 员工</Text>
                <br />
                <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 12 }}>
                  staff / staff123
                </Text>
              </div>
              <LoginOutlined style={{ color: 'white', fontSize: 20 }} />
            </Space>
          </Card>
        </Space>

        <style>{`
          @keyframes fadeInUp {
            from {
              opacity: 0;
              transform: translateY(30px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }

          @keyframes bounce {
            0%, 100% {
              transform: translateY(0);
            }
            50% {
              transform: translateY(-10px);
            }
          }
        `}</style>
      </Card>
    </div>
  );
};

export default LoginPage;
