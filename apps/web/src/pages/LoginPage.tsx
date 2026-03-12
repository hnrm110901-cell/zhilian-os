import React, { useState, useEffect } from 'react';
import { Form, Input, message } from 'antd';
import { UserOutlined, LockOutlined, LoginOutlined, RocketOutlined, WechatOutlined } from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import styles from './LoginPage.module.css';

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const { login, setToken } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Handle OAuth callback
  useEffect(() => {
    const code     = searchParams.get('code');
    const authCode = searchParams.get('auth_code');
    const state    = searchParams.get('state');
    const provider = searchParams.get('provider');

    if ((code || authCode) && provider) {
      handleOAuthCallback(provider, code, authCode, state);
    }
  }, [searchParams]);

  const handleOAuthCallback = async (
    provider: string,
    code: string | null,
    authCode: string | null,
    state: string | null
  ) => {
    setLoading(true);
    try {
      const endpoint = `/api/auth/oauth/${provider}/callback`;
      const payload  = provider === 'dingtalk'
        ? { auth_code: authCode, state }
        : { code, state };

      const response = await axios.post(endpoint, payload);

      if (response.data.access_token) {
        setToken(response.data.access_token, response.data.refresh_token);
        message.success('登录成功！');
        setTimeout(() => navigate(state || '/'), 500);
      }
    } catch {
      message.error('OAuth登录失败，请重试');
      navigate('/login', { replace: true });
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthLogin = (provider: string) => {
    const state       = searchParams.get('redirect') || '/';
    const redirectUri = `${window.location.origin}/login?provider=${provider}`;
    let authUrl       = '';

    if (provider === 'wechat-work') {
      const appId = import.meta.env.VITE_WECHAT_WORK_CORP_ID || 'YOUR_CORP_ID';
      authUrl = `https://open.weixin.qq.com/connect/oauth2/authorize?appid=${appId}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=snsapi_base&state=${state}#wechat_redirect`;
    } else if (provider === 'feishu') {
      const appId = import.meta.env.VITE_FEISHU_APP_ID || 'YOUR_APP_ID';
      authUrl = `https://open.feishu.cn/open-apis/authen/v1/index?app_id=${appId}&redirect_uri=${encodeURIComponent(redirectUri)}&state=${state}`;
    } else if (provider === 'dingtalk') {
      const appId = import.meta.env.VITE_DINGTALK_APP_KEY || 'YOUR_APP_KEY';
      authUrl = `https://oapi.dingtalk.com/connect/oauth2/sns_authorize?appid=${appId}&response_type=code&scope=snsapi_login&state=${state}&redirect_uri=${encodeURIComponent(redirectUri)}`;
    }

    if (authUrl) window.location.href = authUrl;
  };

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const success = await login(values.username, values.password);
      if (success) {
        message.success('登录成功！');
        setTimeout(() => navigate(searchParams.get('redirect') || '/'), 500);
      } else {
        message.error('登录失败，请检查用户名和密码');
      }
    } catch {
      message.error('登录失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const quickLogin = (username: string, password: string) => {
    onFinish({ username, password });
  };

  return (
    <div className={styles.page}>
      {/* 背景装饰 */}
      <div className={`${styles.blob} ${styles.blobTopRight}`} />
      <div className={`${styles.blob} ${styles.blobBottomLeft}`} />

      <div className={styles.card}>
        {/* Logo 区 */}
        <div className={styles.header}>
          <div className={styles.emoji}>🍜</div>
          <h1 className={styles.brand}>屯象OS</h1>
          <p className={styles.subtitle}><RocketOutlined /> 餐饮人的好伙伴</p>
        </div>

        {/* 登录表单 */}
        <Form name="login" onFinish={onFinish} autoComplete="off" size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input
              prefix={<UserOutlined style={{ color: '#0AAF9A' }} />}
              placeholder="用户名"
              style={{ borderRadius: 8 }}
            />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password
              prefix={<LockOutlined style={{ color: '#0AAF9A' }} />}
              placeholder="密码"
              style={{ borderRadius: 8 }}
            />
          </Form.Item>
          <Form.Item>
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              <LoginOutlined />
              {loading ? '登录中...' : '登录'}
            </button>
          </Form.Item>
        </Form>

        {/* 快速登录 */}
        <div className={styles.divider}><span>快速登录</span></div>

        <div className={styles.quickList}>
          <button
            className={styles.quickCard}
            style={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' }}
            onClick={() => quickLogin('admin', 'admin123')}
          >
            <div>
              <div className={styles.quickName}>👑 管理员</div>
              <div className={styles.quickCred}>admin / admin123</div>
            </div>
            <LoginOutlined style={{ fontSize: 20 }} />
          </button>

          <button
            className={styles.quickCard}
            style={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' }}
            onClick={() => quickLogin('manager', 'manager123')}
          >
            <div>
              <div className={styles.quickName}>💼 店长</div>
              <div className={styles.quickCred}>manager / manager123</div>
            </div>
            <LoginOutlined style={{ fontSize: 20 }} />
          </button>

          <button
            className={styles.quickCard}
            style={{ background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)' }}
            onClick={() => quickLogin('staff', 'staff123')}
          >
            <div>
              <div className={styles.quickName}>👤 员工</div>
              <div className={styles.quickCred}>staff / staff123</div>
            </div>
            <LoginOutlined style={{ fontSize: 20 }} />
          </button>
        </div>

        {/* 企业账号登录 */}
        <div className={styles.divider}><span>企业账号登录</span></div>

        <div className={styles.oauthList}>
          <button
            className={styles.oauthBtn}
            style={{ background: '#07c160' }}
            onClick={() => handleOAuthLogin('wechat-work')}
          >
            <WechatOutlined /> 企业微信登录
          </button>
          <button
            className={styles.oauthBtn}
            style={{ background: '#00b96b' }}
            onClick={() => handleOAuthLogin('feishu')}
          >
            🪶 飞书登录
          </button>
          <button
            className={styles.oauthBtn}
            style={{ background: '#0089ff' }}
            onClick={() => handleOAuthLogin('dingtalk')}
          >
            💼 钉钉登录
          </button>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
