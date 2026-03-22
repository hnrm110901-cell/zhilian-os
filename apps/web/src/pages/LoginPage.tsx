/**
 * LoginPage — 屯象OS 企业管理后台登录页
 *
 * 登录方式优先级：
 *   1. 企业微信扫码登录（主要，仅限屯象科技内部员工）
 *   2. 账号密码登录（备用）
 *   3. 手机验证码登录（备用）
 *
 * 修复记录（v2.0）：
 *   - 修复企业微信OAuth URL：personal WeChat → 企业微信网页扫码 (open.work.weixin.qq.com)
 *   - 修复OAuth回调路径：/api/auth/ → /api/v1/auth/
 *   - 新增 VITE_WECHAT_WORK_AGENT_ID 环境变量读取（企业微信必填）
 *   - OAuth/密码登录后跳转到 /platform
 */
import React, { useState, useEffect, useRef } from 'react';
import { Form, Input, message } from 'antd';
import {
  UserOutlined,
  LockOutlined,
  LoginOutlined,
  RocketOutlined,
  WechatOutlined,
  MobileOutlined,
  SafetyOutlined,
  ReloadOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import styles from './LoginPage.module.css';

// ── 登录方式 Tab ──────────────────────────────────────────
type LoginTab = 'wework' | 'password' | 'phone';

const LOGIN_TABS: { key: LoginTab; label: string; icon: React.ReactNode }[] = [
  { key: 'wework',   label: '企业微信',   icon: <WechatOutlined /> },
  { key: 'password', label: '密码登录',   icon: <KeyOutlined /> },
  { key: 'phone',    label: '手机验证码', icon: <MobileOutlined /> },
];

const LoginPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<LoginTab>('wework');
  const [loading, setLoading] = useState(false);
  const { login, setToken } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // ── OAuth 回调处理（企业微信授权后携带 code 返回） ────────────────
  useEffect(() => {
    const code     = searchParams.get('code');
    const authCode = searchParams.get('auth_code');
    const state    = searchParams.get('state');
    const provider = searchParams.get('provider');

    if ((code || authCode) && provider) {
      handleOAuthCallback(provider, code, authCode, state);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleOAuthCallback = async (
    provider: string,
    code: string | null,
    authCode: string | null,
    state: string | null
  ) => {
    setLoading(true);
    try {
      // ✅ 修复：使用正确的 /api/v1/ 路径（原来缺少 /v1/）
      const endpoint = `/api/v1/auth/oauth/${provider}/callback`;
      const payload =
        provider === 'dingtalk'
          ? { auth_code: authCode, state }
          : { code, state };

      const response = await axios.post(endpoint, payload);

      if (response.data.access_token) {
        await setToken(response.data.access_token, response.data.refresh_token);
        message.success('登录成功！');
        // ✅ 修复：登录后跳转到管理后台，而非根路由 /
        const redirect = state && state.startsWith('/') ? state : '/platform';
        setTimeout(() => navigate(redirect, { replace: true }), 400);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'OAuth 登录失败，请重试';
      message.error(detail);
      navigate('/login', { replace: true });
    } finally {
      setLoading(false);
    }
  };

  // ── 企业微信网页扫码登录 ──────────────────────────────
  const handleWechatWorkLogin = () => {
    const corpId  = import.meta.env.VITE_WECHAT_WORK_CORP_ID  || '';
    const agentId = import.meta.env.VITE_WECHAT_WORK_AGENT_ID || '';

    if (!corpId || !agentId) {
      message.warning('企业微信登录未配置，请联系管理员');
      return;
    }

    const redirectPath = searchParams.get('redirect') || '/platform';
    const redirectUri  = `${window.location.origin}/login?provider=wechat-work`;

    // ✅ 修复：企业微信网页扫码登录专用 URL
    // 需在企业微信管理后台 → 应用 → 企业微信授权登录 → 可信域名 中添加 admin.zlsjos.cn
    const authUrl = [
      'https://open.work.weixin.qq.com/wwopen/sso/qrConnect',
      `?appid=${corpId}`,
      `&agentid=${agentId}`,
      `&redirect_uri=${encodeURIComponent(redirectUri)}`,
      `&state=${encodeURIComponent(redirectPath)}`,
    ].join('');

    window.location.href = authUrl;
  };

  // ── 密码登录 ──────────────────────────────────────────
  const onPasswordFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const success = await login(values.username, values.password);
      if (success) {
        const explicit = searchParams.get('redirect');
        const fallback = (() => {
          const stored = localStorage.getItem('token');
          if (stored) {
            try {
              const payload = JSON.parse(atob(stored.split('.')[1]));
              if (payload.role === 'admin') return '/platform';
              if (payload.role === 'store_manager') return '/sm';
              if (payload.role === 'chef') return '/chef';
              if (payload.role === 'floor_manager') return '/floor';
              if (payload.role === 'headquarters') return '/hq';
            } catch { /* fallthrough */ }
          }
          return '/sm';
        })();
        const redirect = explicit && explicit !== '/' ? explicit : fallback;
        setTimeout(() => navigate(redirect, { replace: true }), 400);
      }
    } catch {
      message.error('登录失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const quickLogin = (username: string, password: string) => {
    onPasswordFinish({ username, password });
  };

  return (
    <div className={styles.page}>
      {/* 背景装饰 */}
      <div className={`${styles.blob} ${styles.blobTopRight}`} />
      <div className={`${styles.blob} ${styles.blobBottomLeft}`} />

      <div className={styles.card}>
        {/* Logo 区 */}
        <div className={styles.header}>
          <div className={styles.emoji}>🐘</div>
          <h1 className={styles.brand}>屯象OS</h1>
          <p className={styles.subtitle}>
            <RocketOutlined /> 企业管理后台
          </p>
        </div>

        {/* Tab 切换 */}
        <div className={styles.tabBar}>
          {LOGIN_TABS.map((tab) => (
            <button
              key={tab.key}
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* Tab 内容 */}
        <div className={styles.tabContent}>
          {activeTab === 'wework' && (
            <WechatWorkPanel loading={loading} onLogin={handleWechatWorkLogin} />
          )}
          {activeTab === 'password' && (
            <PasswordForm loading={loading} onFinish={onPasswordFinish} />
          )}
          {activeTab === 'phone' && (
            <PhoneForm
              loading={loading}
              setLoading={setLoading}
              setToken={setToken}
              navigate={navigate}
              redirectPath={searchParams.get('redirect') || '/platform'}
            />
          )}
        </div>

        {/* 快速登录 - 仅开发环境 */}
        {import.meta.env.DEV && (
          <>
            <div className={styles.divider}>
              <span>开发环境快速登录</span>
            </div>
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
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// ══════════════════════════════════════════════════════════════
//  企业微信扫码登录面板（主要登录方式）
// ══════════════════════════════════════════════════════════════
const WechatWorkPanel: React.FC<{
  loading: boolean;
  onLogin: () => void;
}> = ({ loading, onLogin }) => {
  const corpId  = import.meta.env.VITE_WECHAT_WORK_CORP_ID  || '';
  const agentId = import.meta.env.VITE_WECHAT_WORK_AGENT_ID || '';
  const isConfigured = !!(corpId && agentId);

  return (
    <div className={styles.weworkPanel}>
      <div className={styles.weworkIcon}>
        <WechatOutlined />
      </div>

      <div className={styles.weworkDesc}>
        使用<strong>企业微信</strong>扫码登录
        <br />
        <span className={styles.weworkHint}>仅限屯象科技内部员工</span>
      </div>

      <button
        className={styles.weworkBtn}
        onClick={onLogin}
        disabled={loading}
      >
        {loading ? (
          <><ReloadOutlined spin /> 跳转中...</>
        ) : (
          <><WechatOutlined /> 企业微信扫码登录</>
        )}
      </button>

      {!isConfigured && (
        <div className={styles.weworkWarning}>
          <strong>⚠️ 企业微信登录尚未激活</strong>，请完成以下配置后重新部署：
          <ol className={styles.weworkConfigList}>
            <li>
              在<a href="https://work.weixin.qq.com/wework_admin/frame#apps" target="_blank" rel="noopener noreferrer">企业微信管理后台</a>
              创建自建应用，获取 <code>CorpID</code>、<code>AgentID</code>、<code>Secret</code>
            </li>
            <li>应用详情 → 企业微信授权登录 → 可信域名添加 <code>admin.zlsjos.cn</code></li>
            <li>
              服务器 <code>.env.prod</code> 添加：<br />
              <code>WECHAT_CORP_ID=wx...</code><br />
              <code>WECHAT_CORP_SECRET=...</code><br />
              <code>WECHAT_AGENT_ID=...</code>
            </li>
            <li>
              前端 <code>.env.production</code> 添加：<br />
              <code>VITE_WECHAT_WORK_CORP_ID=wx...</code><br />
              <code>VITE_WECHAT_WORK_AGENT_ID=...</code>
            </li>
            <li>推送代码到 main 分支，GitHub Actions 自动重新部署</li>
          </ol>
        </div>
      )}

      <div className={styles.weworkSteps}>
        <div className={styles.weworkStep}>
          <span className={styles.stepNum}>1</span>
          <span>点击按钮</span>
        </div>
        <span className={styles.stepArrow}>→</span>
        <div className={styles.weworkStep}>
          <span className={styles.stepNum}>2</span>
          <span>企业微信扫码</span>
        </div>
        <span className={styles.stepArrow}>→</span>
        <div className={styles.weworkStep}>
          <span className={styles.stepNum}>3</span>
          <span>手机确认</span>
        </div>
      </div>
    </div>
  );
};

// ══════════════════════════════════════════════════════════════
//  密码登录表单
// ══════════════════════════════════════════════════════════════
const PasswordForm: React.FC<{
  loading: boolean;
  onFinish: (values: { username: string; password: string }) => void;
}> = ({ loading, onFinish }) => (
  <Form name="login" onFinish={onFinish} autoComplete="off" size="large">
    <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
      <Input
        prefix={<UserOutlined style={{ color: '#FF6B2C' }} />}
        placeholder="用户名"
        style={{ borderRadius: 8 }}
      />
    </Form.Item>
    <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
      <Input.Password
        prefix={<LockOutlined style={{ color: '#FF6B2C' }} />}
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
);

// ══════════════════════════════════════════════════════════════
//  手机验证码登录表单
// ══════════════════════════════════════════════════════════════
const PhoneForm: React.FC<{
  loading: boolean;
  setLoading: (v: boolean) => void;
  setToken: (accessToken: string, refreshToken: string) => Promise<void>;
  navigate: (path: string, opts?: object) => void;
  redirectPath: string;
}> = ({ loading, setLoading, setToken, navigate, redirectPath }) => {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  const startCountdown = () => {
    setCountdown(60);
    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) { if (timerRef.current) clearInterval(timerRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);
  };

  const handleSendCode = async () => {
    if (!phone || phone.length !== 11) { message.warning('请输入正确的11位手机号'); return; }
    try {
      await axios.post('/api/v1/auth/sms/send', { phone });
      message.success('验证码已发送');
      startCountdown();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '验证码发送失败');
    }
  };

  const handleSubmit = async () => {
    if (!phone || phone.length !== 11) { message.warning('请输入正确的11位手机号'); return; }
    if (!code || code.length !== 6)    { message.warning('请输入6位验证码'); return; }
    setLoading(true);
    try {
      const response = await axios.post('/api/v1/auth/sms/login', { phone, code });
      if (response.data.access_token) {
        await setToken(response.data.access_token, response.data.refresh_token);
        message.success('登录成功！');
        setTimeout(() => navigate(redirectPath, { replace: true }), 400);
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.phoneForm}>
      <div className={styles.phoneInputRow}>
        <span className={styles.phonePrefix}>+86</span>
        <input
          className={styles.phoneInput}
          type="tel"
          placeholder="请输入手机号"
          maxLength={11}
          value={phone}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
        />
      </div>
      <div className={styles.codeInputRow}>
        <input
          className={styles.codeInput}
          type="text"
          placeholder="6位验证码"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
        />
        <button className={styles.sendCodeBtn} disabled={countdown > 0} onClick={handleSendCode}>
          {countdown > 0 ? `${countdown}s` : '获取验证码'}
        </button>
      </div>
      <button className={styles.submitBtn} disabled={loading} onClick={handleSubmit}>
        <SafetyOutlined />
        {loading ? '登录中...' : '验证码登录'}
      </button>
    </div>
  );
};

export default LoginPage;
