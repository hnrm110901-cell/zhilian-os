/**
 * PlatformAdminHome — 屯象OS 企业管理后台控制台首页
 */
import React, { useEffect, useState } from 'react';
import {
  ShopOutlined,
  ApiOutlined,
  RobotOutlined,
  UserOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../services/apiClient';
import styles from './PlatformAdminHome.module.css';

// ── 类型 ───────────────────────────────────────────────────────
interface SystemStatus {
  api: 'ok' | 'error' | 'loading';
  db: 'ok' | 'error' | 'loading';
  redis: 'ok' | 'error' | 'loading';
}

interface Stat {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ReactNode;
  color: string;
  path: string;
}

// ── 组件 ───────────────────────────────────────────────────────
const PlatformAdminHome: React.FC = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<SystemStatus>({
    api: 'loading',
    db: 'loading',
    redis: 'loading',
  });
  const [merchantCount, setMerchantCount] = useState<number | null>(null);

  useEffect(() => {
    checkSystemStatus();
  }, []);

  const checkSystemStatus = async () => {
    try {
      const resp = await apiClient.get('/api/v1/health');
      const data = resp.data;
      setStatus({
        api: 'ok',
        db: data.database === 'connected' ? 'ok' : 'error',
        redis: data.redis === 'connected' ? 'ok' : 'error',
      });
    } catch {
      setStatus({ api: 'error', db: 'error', redis: 'error' });
    }

    try {
      const resp = await apiClient.get('/api/v1/merchants?page=1&page_size=1');
      setMerchantCount(resp.data?.total ?? resp.data?.length ?? 3);
    } catch {
      setMerchantCount(3); // 已知种子数据
    }
  };

  const STATS: Stat[] = [
    {
      label: '接入商户',
      value: merchantCount ?? '--',
      sub: '尝在一起 / 最黔线 / 尚宫厨',
      icon: <ShopOutlined />,
      color: '#0AAF9A',
      path: '/platform/merchants',
    },
    {
      label: 'API 集成',
      value: 7,
      sub: '品智 / 奥琦玮 / 美团 / 一订…',
      icon: <ApiOutlined />,
      color: '#1677FF',
      path: '/platform/integrations',
    },
    {
      label: '活跃 Agent',
      value: 15,
      sub: '运行中，覆盖全业务域',
      icon: <RobotOutlined />,
      color: '#722ED1',
      path: '/platform/agents',
    },
    {
      label: '系统用户',
      value: '--',
      sub: '管理员 / 店长 / 厨师长…',
      icon: <UserOutlined />,
      color: '#FA8C16',
      path: '/platform/settings',
    },
  ];

  const QUICK_ACTIONS = [
    { label: '添加新商户', desc: '接入品牌 / 门店 / API', path: '/platform/merchants', color: '#0AAF9A' },
    { label: '灰度配置', desc: '特性开关 / 版本灰度', path: '/platform/feature-flags', color: '#722ED1' },
    { label: 'Agent 调试', desc: '配置 / 测试 / 日志', path: '/platform/agents', color: '#1677FF' },
    { label: '系统监控', desc: '服务状态 / 告警', path: '/platform/monitoring', color: '#FA8C16' },
  ];

  return (
    <div className={styles.page}>
      {/* 欢迎语 */}
      <div className={styles.welcome}>
        <h1 className={styles.title}>🐘 屯象OS 企业管理后台</h1>
        <p className={styles.subtitle}>
          系统迭代 · 测试验证 · 灰度发布 · 商户配置 · 工具管理
        </p>
      </div>

      {/* 系统状态栏 */}
      <div className={styles.statusBar}>
        <span className={styles.statusLabel}>系统状态</span>
        <StatusDot label="API 服务" status={status.api} />
        <StatusDot label="数据库" status={status.db} />
        <StatusDot label="Redis" status={status.redis} />
        <button className={styles.refreshBtn} onClick={checkSystemStatus}>
          刷新
        </button>
      </div>

      {/* 统计卡片 */}
      <div className={styles.statsGrid}>
        {STATS.map((s) => (
          <button
            key={s.label}
            className={styles.statCard}
            onClick={() => navigate(s.path)}
          >
            <div className={styles.statIcon} style={{ background: `${s.color}18`, color: s.color }}>
              {s.icon}
            </div>
            <div className={styles.statBody}>
              <div className={styles.statValue}>{s.value}</div>
              <div className={styles.statLabel}>{s.label}</div>
              {s.sub && <div className={styles.statSub}>{s.sub}</div>}
            </div>
            <ArrowRightOutlined className={styles.statArrow} />
          </button>
        ))}
      </div>

      {/* 快捷操作 */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>快捷操作</h2>
        <div className={styles.quickGrid}>
          {QUICK_ACTIONS.map((a) => (
            <button
              key={a.label}
              className={styles.quickCard}
              onClick={() => navigate(a.path)}
            >
              <div className={styles.quickDot} style={{ background: a.color }} />
              <div>
                <div className={styles.quickLabel}>{a.label}</div>
                <div className={styles.quickDesc}>{a.desc}</div>
              </div>
              <ArrowRightOutlined className={styles.quickArrow} />
            </button>
          ))}
        </div>
      </div>

      {/* 种子客户状态 */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>种子客户接入状态</h2>
        <div className={styles.merchantTable}>
          <MerchantRow
            name="尝在一起"
            pos="品智收银"
            crm="奥琦玮 1275413383"
            stores={3}
            status="接入中"
          />
          <MerchantRow
            name="最黔线"
            pos="品智收银"
            crm="奥琦玮 1827518239"
            stores={6}
            status="接入中"
          />
          <MerchantRow
            name="尚宫厨（心传）"
            pos="品智收银"
            crm="奥琦玮 1549254243"
            stores={5}
            status="接入中"
          />
        </div>
      </div>
    </div>
  );
};

// ── 子组件 ─────────────────────────────────────────────────────
const StatusDot: React.FC<{ label: string; status: 'ok' | 'error' | 'loading' }> = ({ label, status }) => {
  const icon =
    status === 'ok' ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> :
    status === 'error' ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> :
    <ClockCircleOutlined style={{ color: '#faad14' }} />;

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#6E6E73' }}>
      {icon} {label}
    </span>
  );
};

const MerchantRow: React.FC<{
  name: string;
  pos: string;
  crm: string;
  stores: number;
  status: string;
}> = ({ name, pos, crm, stores, status }) => (
  <div className={styles.merchantRow}>
    <div className={styles.merchantName}>{name}</div>
    <div className={styles.merchantCell}>{pos}</div>
    <div className={styles.merchantCell}>{crm}</div>
    <div className={styles.merchantCell}>{stores} 家门店</div>
    <div className={styles.merchantStatus}>{status}</div>
  </div>
);

export default PlatformAdminHome;
