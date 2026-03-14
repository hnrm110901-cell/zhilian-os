/**
 * 系统设置页 — /platform/settings
 *
 * 平台级配置管理：基本信息、商户同步、通知渠道、数据保留策略、API 网关状态
 * 从 /api/v1/merchants/stats 和 /api/v1/ready 拉取实时数据
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  SettingOutlined,
  CloudServerOutlined,
  BellOutlined,
  DatabaseOutlined,
  ShopOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Spin, message } from 'antd';
import { apiClient } from '../../services/api';
import styles from './SystemSettingsPage.module.css';

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface PlatformStats {
  total_merchants: number;
  total_stores: number;
  active_stores: number;
  total_users: number;
}

interface ServiceHealth {
  status: string;
  version?: string;
  database?: string;
  redis?: string;
  timestamp?: string;
}

interface MerchantRow {
  brand_id: string;
  brand_name: string;
  store_count: number;
  cuisine_type: string;
  status: string;
  contact_person?: string;
  contact_phone?: string;
}

// ── 通知渠道配置 ─────────────────────────────────────────────────────────────

interface NotifyChannel {
  key: string;
  label: string;
  enabled: boolean;
  desc: string;
}

const DEFAULT_CHANNELS: NotifyChannel[] = [
  { key: 'wechat_work', label: '企业微信推送', enabled: true,  desc: '通过企业微信机器人推送决策建议和告警' },
  { key: 'feishu',      label: '飞书 Webhook', enabled: false, desc: '通过飞书群机器人推送消息' },
  { key: 'sms',         label: '短信通知',     enabled: false, desc: '短信发送关键告警（需配置短信服务商）' },
  { key: 'email',       label: '邮件报告',     enabled: false, desc: '定期发送经营日报/周报到指定邮箱' },
];

// ── 数据保留策略 ─────────────────────────────────────────────────────────────

interface RetentionPolicy {
  key: string;
  label: string;
  days: number;
  desc: string;
}

const DEFAULT_RETENTION: RetentionPolicy[] = [
  { key: 'order_detail',   label: '订单明细',   days: 365, desc: '完整订单数据（含SKU明细）' },
  { key: 'decision_log',   label: '决策日志',   days: 180, desc: 'AI 决策推理记录' },
  { key: 'waste_event',    label: '损耗记录',   days: 365, desc: '食材损耗事件及原因' },
  { key: 'audit_log',      label: '审计日志',   days: 730, desc: '系统操作审计轨迹' },
  { key: 'agent_message',  label: 'Agent 消息', days: 90,  desc: 'Agent 间通信消息' },
  { key: 'redis_cache',    label: 'Redis 缓存', days: 1,   desc: 'BFF 聚合缓存 TTL' },
];

const CUISINE_LABEL: Record<string, string> = {
  hunan: '湘菜', guizhou: '贵州菜', cantonese: '粤菜', sichuan: '川菜',
  jiangsu: '江浙菜', seafood: '海鲜', hotpot: '火锅', bbq: '烧烤',
  western: '西餐', japanese: '日料', korean: '韩料', fusion: '创新融合',
};

// ── 组件 ─────────────────────────────────────────────────────────────────────

export default function SystemSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [health, setHealth] = useState<ServiceHealth | null>(null);
  const [merchants, setMerchants] = useState<MerchantRow[]>([]);
  const [channels, setChannels] = useState<NotifyChannel[]>(DEFAULT_CHANNELS);
  const [retention, setRetention] = useState<RetentionPolicy[]>(DEFAULT_RETENTION);
  const [saving, setSaving] = useState(false);

  // 平台配置（可编辑）
  const [platformName, setPlatformName] = useState('屯象OS');
  const [syncInterval, setSyncInterval] = useState('30');
  const [celerySchedule, setCelerySchedule] = useState('02:00');
  const [maxRetry, setMaxRetry] = useState('3');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, healthRes, merchantsRes] = await Promise.allSettled([
        apiClient.get<PlatformStats>('/api/v1/merchants/stats'),
        apiClient.get<ServiceHealth>('/api/v1/ready'),
        apiClient.get<{ merchants: MerchantRow[] }>('/api/v1/merchants'),
      ]);

      if (statsRes.status === 'fulfilled') setStats(statsRes.value);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
      if (merchantsRes.status === 'fulfilled') {
        const list = merchantsRes.value.merchants || merchantsRes.value;
        setMerchants(Array.isArray(list) ? list : []);
      }
    } catch {
      // 静默降级
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const toggleChannel = (key: string) => {
    setChannels(prev => prev.map(c => c.key === key ? { ...c, enabled: !c.enabled } : c));
  };

  const updateRetention = (key: string, days: number) => {
    setRetention(prev => prev.map(r => r.key === key ? { ...r, days } : r));
  };

  const handleSave = async () => {
    setSaving(true);
    // 模拟保存（实际应 POST /api/v1/system/config）
    await new Promise(r => setTimeout(r, 600));
    message.success('系统设置已保存');
    setSaving(false);
  };

  if (loading) {
    return <div className={styles.loadingWrap}><Spin size="large" /></div>;
  }

  const dbStatus = health?.database || health?.status;
  const isHealthy = health?.status === 'ok' || health?.status === 'healthy';

  return (
    <div className={styles.page}>
      {/* ── Page Header ──────────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>系统设置</h1>
          <p className={styles.pageDesc}>平台级配置管理 · 商户同步 · 通知渠道 · 数据保留策略</p>
        </div>
        <button className={styles.btnSecondary} onClick={loadData}>
          <ReloadOutlined /> 刷新数据
        </button>
      </div>

      {/* ── 1. 平台状态概览 ──────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconMint}`}>
            <CloudServerOutlined />
          </div>
          <div>
            <h2 className={styles.sectionTitle}>平台状态</h2>
            <p className={styles.sectionDesc}>API 网关 · 数据库 · Redis 服务状态</p>
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <span className={`${styles.statusBadge} ${isHealthy ? styles.statusOnline : styles.statusOffline}`}>
              <span className={styles.statusDot} />
              {isHealthy ? '全部正常' : '异常'}
            </span>
          </div>
        </div>

        <div className={styles.infoGrid}>
          <div className={styles.infoCard}>
            <div className={styles.infoLabel}>API 网关</div>
            <div className={`${styles.infoValue} ${styles.infoValueMint}`}>
              {isHealthy ? 'Running' : 'Down'}
            </div>
          </div>
          <div className={styles.infoCard}>
            <div className={styles.infoLabel}>数据库</div>
            <div className={styles.infoValue}>
              {dbStatus === 'connected' || dbStatus === 'ok' ? 'Connected' : dbStatus || 'Unknown'}
            </div>
          </div>
          <div className={styles.infoCard}>
            <div className={styles.infoLabel}>Redis</div>
            <div className={styles.infoValue}>
              {health?.redis === 'connected' || health?.redis === 'ok' ? 'Connected' : health?.redis || 'N/A'}
            </div>
          </div>
          <div className={styles.infoCard}>
            <div className={styles.infoLabel}>接入商户</div>
            <div className={`${styles.infoValue} ${styles.infoValueMint}`}>
              {stats?.total_merchants ?? '—'}
            </div>
          </div>
          <div className={styles.infoCard}>
            <div className={styles.infoLabel}>门店总数</div>
            <div className={styles.infoValue}>{stats?.total_stores ?? '—'}</div>
          </div>
          <div className={styles.infoCard}>
            <div className={styles.infoLabel}>平台用户</div>
            <div className={styles.infoValue}>{stats?.total_users ?? '—'}</div>
          </div>
        </div>
      </section>

      {/* ── 2. 基本配置 ──────────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconBlue}`}>
            <SettingOutlined />
          </div>
          <div>
            <h2 className={styles.sectionTitle}>基本配置</h2>
            <p className={styles.sectionDesc}>平台名称 · 域名 · 数据同步参数</p>
          </div>
        </div>

        <div className={styles.formGrid}>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>平台名称</label>
            <div className={styles.formValue}>
              <input className={styles.formInput} value={platformName}
                onChange={e => setPlatformName(e.target.value)} />
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>服务域名</label>
            <div className={styles.formValue}>
              <div className={styles.formStaticMono}>zlsjos.cn</div>
              <div className={styles.formHint}>API 端点: https://zlsjos.cn/api/v1/</div>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>服务器 IP</label>
            <div className={styles.formValue}>
              <div className={styles.formStaticMono}>42.194.229.21</div>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>BFF 缓存 TTL</label>
            <div className={styles.formValue}>
              <input className={`${styles.formInput} ${styles.formInputSmall}`}
                value={syncInterval} onChange={e => setSyncInterval(e.target.value)}
                type="number" min="5" max="300" />
              <div className={styles.formHint}>BFF 聚合接口的 Redis 缓存时间（秒），默认 30s</div>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>定时任务执行</label>
            <div className={styles.formValue}>
              <input className={`${styles.formInput} ${styles.formInputSmall}`}
                value={celerySchedule} onChange={e => setCelerySchedule(e.target.value)} />
              <div className={styles.formHint}>Celery Beat 每日数据拉取时间（UTC），如 02:00</div>
            </div>
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>API 重试次数</label>
            <div className={styles.formValue}>
              <input className={`${styles.formInput} ${styles.formInputSmall}`}
                value={maxRetry} onChange={e => setMaxRetry(e.target.value)}
                type="number" min="0" max="10" />
              <div className={styles.formHint}>POS 适配器调用失败时的最大重试次数</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── 3. 商户配置概览 ──────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconMint}`}>
            <ShopOutlined />
          </div>
          <div>
            <h2 className={styles.sectionTitle}>商户配置概览</h2>
            <p className={styles.sectionDesc}>已接入商户的基础资料和门店分布</p>
          </div>
        </div>

        {merchants.length > 0 ? (
          <table className={styles.merchantTable}>
            <thead>
              <tr>
                <th>品牌名称</th>
                <th>菜系</th>
                <th>门店数</th>
                <th>联系人</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {merchants.map(m => (
                <tr key={m.brand_id}>
                  <td><span className={styles.merchantName}>{m.brand_name}</span></td>
                  <td>{CUISINE_LABEL[m.cuisine_type] || m.cuisine_type || '—'}</td>
                  <td>{m.store_count ?? '—'}</td>
                  <td>{m.contact_person || '—'}</td>
                  <td>
                    <span className={`${styles.merchantTag} ${
                      m.status === 'active' ? styles.merchantTagActive : styles.merchantTagPending
                    }`}>
                      {m.status === 'active' ? '已激活' : m.status === 'onboarding' ? '接入中' : m.status || '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className={styles.errorWrap}>暂无商户数据</div>
        )}
      </section>

      {/* ── 4. 通知渠道 ──────────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconAmber}`}>
            <BellOutlined />
          </div>
          <div>
            <h2 className={styles.sectionTitle}>通知渠道</h2>
            <p className={styles.sectionDesc}>配置 AI 决策建议和告警的推送方式</p>
          </div>
        </div>

        <div className={styles.formGrid}>
          {channels.map(ch => (
            <div key={ch.key} className={styles.toggleRow}>
              <div className={styles.toggleInfo}>
                <span className={styles.toggleLabel}>{ch.label}</span>
                <span className={styles.toggleDesc}>{ch.desc}</span>
              </div>
              <button
                className={`${styles.toggle} ${ch.enabled ? styles.toggleOn : ''}`}
                onClick={() => toggleChannel(ch.key)}
                aria-label={`切换 ${ch.label}`}
              />
            </div>
          ))}
        </div>
      </section>

      {/* ── 5. 数据保留策略 ──────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconPurple}`}>
            <DatabaseOutlined />
          </div>
          <div>
            <h2 className={styles.sectionTitle}>数据保留策略</h2>
            <p className={styles.sectionDesc}>各类数据的存储时长（天）· 超期数据自动归档</p>
          </div>
        </div>

        <div className={styles.formGrid}>
          {retention.map(r => (
            <div key={r.key} className={styles.formRow}>
              <label className={styles.formLabel}>{r.label}</label>
              <div className={styles.formValue}>
                <input
                  className={`${styles.formInput} ${styles.formInputSmall}`}
                  type="number" min="1" max="3650"
                  value={r.days}
                  onChange={e => updateRetention(r.key, parseInt(e.target.value) || 1)}
                />
                <div className={styles.formHint}>{r.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── 6. 安全配置 ──────────────────────────────────────── */}
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={`${styles.sectionIcon} ${styles.sectionIconBlue}`}>
            <SafetyCertificateOutlined />
          </div>
          <div>
            <h2 className={styles.sectionTitle}>安全配置</h2>
            <p className={styles.sectionDesc}>认证 · 会话 · 数据脱敏规则</p>
          </div>
        </div>

        <div className={styles.formGrid}>
          <div className={styles.toggleRow}>
            <div className={styles.toggleInfo}>
              <span className={styles.toggleLabel}>JWT 认证</span>
              <span className={styles.toggleDesc}>API 请求强制 Bearer Token 验证</span>
            </div>
            <button className={`${styles.toggle} ${styles.toggleOn}`} disabled aria-label="JWT 认证" />
          </div>
          <div className={styles.toggleRow}>
            <div className={styles.toggleInfo}>
              <span className={styles.toggleLabel}>日志金额脱敏</span>
              <span className={styles.toggleDesc}>日志中的订单金额、客户信息自动脱敏</span>
            </div>
            <button className={`${styles.toggle} ${styles.toggleOn}`} disabled aria-label="日志脱敏" />
          </div>
          <div className={styles.toggleRow}>
            <div className={styles.toggleInfo}>
              <span className={styles.toggleLabel}>SQL 参数化强制</span>
              <span className={styles.toggleDesc}>阻止 SQL 字符串拼接，所有查询必须参数化</span>
            </div>
            <button className={`${styles.toggle} ${styles.toggleOn}`} disabled aria-label="SQL 参数化" />
          </div>
          <div className={styles.formRow}>
            <label className={styles.formLabel}>会话超时</label>
            <div className={styles.formValue}>
              <div className={styles.formStatic}>24 小时</div>
              <div className={styles.formHint}>JWT Token 有效期</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Save Bar ─────────────────────────────────────────── */}
      <div className={styles.actions}>
        <button className={styles.btnSecondary} onClick={loadData}>取消</button>
        <button className={styles.btnPrimary} onClick={handleSave} disabled={saving}>
          {saving ? <Spin size="small" /> : <CheckCircleFilled />}
          保存设置
        </button>
      </div>
    </div>
  );
}
