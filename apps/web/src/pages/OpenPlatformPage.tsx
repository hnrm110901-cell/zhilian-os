import React, { useState, useEffect, useCallback } from 'react';
import { Form, Input, message } from 'antd';
import { ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZSelect, ZTable, ZModal, ZEmpty } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './OpenPlatformPage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────────

interface Capability {
  level: number;
  key: string;
  name: string;
  description: string;
  tier_required: string;
}

interface TierInfo {
  tier: string;
  label: string;
  price_yuan: number;
  rate_limit_rpm: number;
  max_level: number;
}

interface PlatformStats {
  registered_developers: number;
  active_api_keys: number;
  total_capabilities: number;
  capability_levels: number;
}

interface RegisterResult {
  developer_id: string;
  api_key: string;
  api_secret: string;
  rate_limit_rpm: number;
  tier: string;
  message: string;
}

// ── Level badge ────────────────────────────────────────────────────────────────

const LEVEL_COLOR: Record<number, string> = {
  1: 'var(--text-secondary)',
  2: '#1677ff',
  3: '#fa8c16',
  4: '#722ed1',
};

const LEVEL_LABEL: Record<number, string> = {
  1: 'Level 1 · 数据同步',
  2: 'Level 2 · 智能决策',
  3: 'Level 3 · 营销能力',
  4: 'Level 4 · 高级能力',
};

const TIER_COLOR: Record<string, 'success' | 'warning' | 'error' | 'neutral'> = {
  free: 'neutral',
  basic: 'success',
  pro: 'warning',
  enterprise: 'error',
};

// ── Capability columns ─────────────────────────────────────────────────────────

const capColumns: ZTableColumn<Capability>[] = [
  {
    key: 'level',
    title: '层级',
    width: 170,
    render: (lvl) => (
      <span style={{ color: LEVEL_COLOR[lvl], fontWeight: 600, fontSize: 12 }}>
        {LEVEL_LABEL[lvl]}
      </span>
    ),
  },
  {
    key: 'name',
    title: '能力名称',
    render: (name, row) => (
      <div>
        <strong>{name}</strong>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{row.key}</div>
      </div>
    ),
  },
  {
    key: 'description',
    title: '描述',
    render: (desc) => <span style={{ color: 'var(--text-secondary)' }}>{desc}</span>,
  },
  {
    key: 'tier_required',
    title: '最低套餐',
    align: 'center',
    render: (tier) => {
      const labels: Record<string, string> = { free: '免费版', basic: '基础版', pro: '专业版', enterprise: '企业版' };
      return <ZBadge type={TIER_COLOR[tier] || 'neutral'} text={labels[tier] || tier} />;
    },
  },
];

// ── Tier columns ──────────────────────────────────────────────────────────────

const tierColumns: ZTableColumn<TierInfo>[] = [
  {
    key: 'label',
    title: '套餐',
    render: (label, row) => (
      <ZBadge type={TIER_COLOR[row.tier] || 'neutral'} text={label} />
    ),
  },
  {
    key: 'price_yuan',
    title: '月费',
    align: 'right',
    render: (v) => v === 0 ? <span style={{ color: 'var(--green)', fontWeight: 600 }}>免费</span>
      : <span style={{ color: 'var(--accent)', fontWeight: 600 }}>¥{v.toLocaleString()}/月</span>,
  },
  {
    key: 'rate_limit_rpm',
    title: '调用限制',
    align: 'center',
    render: (v) => `${v.toLocaleString()} 次/分钟`,
  },
  {
    key: 'max_level',
    title: '可访问层级',
    align: 'center',
    render: (v) => (
      <span style={{ color: LEVEL_COLOR[v], fontWeight: 600 }}>Level 1 ~ {v}</span>
    ),
  },
];

// ── Component ──────────────────────────────────────────────────────────────────

const TIER_OPTIONS = [
  { value: 'free', label: '免费版（Level 1，60次/分钟）' },
  { value: 'basic', label: '基础版（Level 1-2，300次/分钟）' },
  { value: 'pro', label: '专业版（Level 1-3，1000次/分钟）' },
  { value: 'enterprise', label: '企业版（全能力，5000次/分钟）' },
];

const OpenPlatformPage: React.FC = () => {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [tiers, setTiers] = useState<TierInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const [registerModal, setRegisterModal] = useState(false);
  const [registerLoading, setRegisterLoading] = useState(false);
  const [registerResult, setRegisterResult] = useState<RegisterResult | null>(null);
  const [registerForm] = Form.useForm();

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, capsRes, pricingRes] = await Promise.allSettled([
        apiClient.get('/api/v1/open/stats'),
        apiClient.get('/api/v1/open/capabilities'),
        apiClient.get('/api/v1/open/pricing'),
      ]);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
      if (capsRes.status === 'fulfilled') setCapabilities(capsRes.value.data.capabilities || []);
      if (pricingRes.status === 'fulfilled') setTiers(pricingRes.value.data.tiers || []);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleRegister = async (values: { name: string; email: string; company?: string; tier: string }) => {
    setRegisterLoading(true);
    try {
      const res = await apiClient.post('/api/v1/open/developers', values);
      setRegisterResult(res.data);
      loadAll();
    } catch (e) {
      handleApiError(e);
    } finally {
      setRegisterLoading(false);
    }
  };

  const handleCloseModal = () => {
    setRegisterModal(false);
    setRegisterResult(null);
    registerForm.resetFields();
  };

  const registerFooter = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
      <ZButton onClick={handleCloseModal}>关闭</ZButton>
      {!registerResult && (
        <ZButton variant="primary" disabled={registerLoading} onClick={() => registerForm.submit()}>
          {registerLoading ? '注册中…' : '立即注册'}
        </ZButton>
      )}
    </div>
  );

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>开放平台</h1>
          <p className={styles.pageSub}>ISV 接入 · API 能力开放 · 插件生态</p>
        </div>
        <div className={styles.headerActions}>
          <ZButton onClick={loadAll}>刷新</ZButton>
          <ZButton variant="primary" onClick={() => setRegisterModal(true)}>申请开发者账号</ZButton>
        </div>
      </div>

      {/* KPI Row */}
      <div className={styles.kpiGrid}>
        {loading ? (
          [...Array(4)].map((_, i) => <ZSkeleton key={i} height={88} />)
        ) : (
          <>
            <ZCard><ZKpi label="已注册开发者" value={stats?.registered_developers ?? '-'} unit="个" /></ZCard>
            <ZCard><ZKpi label="活跃 API Key" value={stats?.active_api_keys ?? '-'} unit="个" /></ZCard>
            <ZCard><ZKpi label="开放能力数" value={stats?.total_capabilities ?? '-'} unit="个" /></ZCard>
            <ZCard><ZKpi label="能力层级" value={stats?.capability_levels ?? 4} unit="级" /></ZCard>
          </>
        )}
      </div>

      {/* Capabilities + Pricing */}
      <div className={styles.twoCol}>
        <ZCard title="开放能力目录">
          {loading ? <ZSkeleton height={300} /> : (
            capabilities.length > 0
              ? <ZTable columns={capColumns} data={capabilities} rowKey="key" />
              : <ZEmpty text="暂无能力数据" />
          )}
        </ZCard>

        <ZCard title="套餐定价">
          {loading ? <ZSkeleton height={300} /> : (
            tiers.length > 0
              ? <ZTable columns={tierColumns} data={tiers} rowKey="tier" />
              : <ZEmpty text="暂无套餐数据" />
          )}
        </ZCard>
      </div>

      {/* Quick Start Guide */}
      <ZCard title="快速接入指南">
        <div className={styles.guideGrid}>
          <div className={styles.guideStep}>
            <div className={styles.stepNum}>01</div>
            <div className={styles.stepTitle}>注册开发者账号</div>
            <div className={styles.stepDesc}>点击右上角「申请开发者账号」，选择套餐，获取 API Key & Secret</div>
          </div>
          <div className={styles.guideStep}>
            <div className={styles.stepNum}>02</div>
            <div className={styles.stepTitle}>选择开放能力</div>
            <div className={styles.stepDesc}>按业务需求选择 Level 1-4 能力，Free 套餐已包含全部 Level 1 数据同步能力</div>
          </div>
          <div className={styles.guideStep}>
            <div className={styles.stepNum}>03</div>
            <div className={styles.stepTitle}>调用 API</div>
            <div className={styles.stepDesc}>请求头携带 X-API-Key，通过 HMAC-SHA256 签名验证，速率限制按套餐执行</div>
          </div>
          <div className={styles.guideStep}>
            <div className={styles.stepNum}>04</div>
            <div className={styles.stepTitle}>监控用量</div>
            <div className={styles.stepDesc}>开发者控制台查看调用量、错误率、响应延迟，支持 Webhook 回调通知</div>
          </div>
        </div>
      </ZCard>

      {/* Register Modal */}
      <ZModal
        open={registerModal}
        title="申请开发者账号"
        onClose={handleCloseModal}
        footer={registerFooter}
        width={520}
      >
        {!registerResult ? (
          <Form form={registerForm} layout="vertical" onFinish={handleRegister}>
            <Form.Item name="name" label="姓名 / 公司简称" rules={[{ required: true, message: '请输入姓名' }]}>
              <Input placeholder="例：张三 / 小象科技" />
            </Form.Item>
            <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
              <Input placeholder="dev@company.com" />
            </Form.Item>
            <Form.Item name="company" label="公司名称（选填）">
              <Input placeholder="例：北京小象餐饮科技有限公司" />
            </Form.Item>
            <Form.Item name="tier" label="接入套餐" initialValue="free" rules={[{ required: true }]}>
              <select className={styles.nativeSelect}>
                {TIER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Form.Item>
          </Form>
        ) : (
          <div className={styles.resultBox}>
            <div className={styles.resultAlert}>
              注册成功！请立即保存以下凭证，<strong>api_secret 关闭页面后将无法再查看</strong>
            </div>
            <div className={styles.credRow}>
              <span className={styles.credLabel}>Developer ID</span>
              <code className={styles.credValue}>{registerResult.developer_id}</code>
            </div>
            <div className={styles.credRow}>
              <span className={styles.credLabel}>API Key</span>
              <code className={styles.credValue}>{registerResult.api_key}</code>
            </div>
            <div className={styles.credRow}>
              <span className={styles.credLabel}>API Secret</span>
              <code className={styles.credValue} style={{ color: 'var(--accent)' }}>{registerResult.api_secret}</code>
            </div>
            <div className={styles.credRow}>
              <span className={styles.credLabel}>速率限制</span>
              <span>{registerResult.rate_limit_rpm.toLocaleString()} 次/分钟</span>
            </div>
            <div className={styles.credRow}>
              <span className={styles.credLabel}>套餐</span>
              <ZBadge type={TIER_COLOR[registerResult.tier] || 'neutral'} text={registerResult.tier} />
            </div>
          </div>
        )}
      </ZModal>
    </div>
  );
};

export default OpenPlatformPage;
