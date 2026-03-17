/**
 * IMChannelPage — IM 渠道管理（企微/钉钉/飞书）
 *
 * 统一管理三个 IM 渠道的 Webhook 推送配置、消息模板、推送记录。
 */
import React, { useState } from 'react';
import { ZCard, ZKpi, ZBadge, ZTable, ZButton, ZTabs } from '../design-system/components';
import type { ZTableColumn } from '../design-system/components';
import styles from './IMChannelPage.module.css';

// ── Mock 数据 ─────────────────────────────────────────────────

interface IMChannel {
  key: string;
  name: string;
  status: 'connected' | 'unconfigured' | 'error';
  todayPush: number;
  webhookUrl: string;
  iconClass: string;
}

const CHANNELS: IMChannel[] = [
  {
    key: 'wecom',
    name: '企业微信',
    status: 'connected',
    todayPush: 45,
    webhookUrl: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx-xxxx-****-****',
    iconClass: styles.iconWecom,
  },
  {
    key: 'dingtalk',
    name: '钉钉',
    status: 'unconfigured',
    todayPush: 0,
    webhookUrl: '',
    iconClass: styles.iconDingtalk,
  },
  {
    key: 'feishu',
    name: '飞书',
    status: 'connected',
    todayPush: 12,
    webhookUrl: 'https://open.feishu.cn/open-apis/bot/v2/hook/xxxx-****-****',
    iconClass: styles.iconFeishu,
  },
];

const STATUS_MAP: Record<string, { type: 'success' | 'default' | 'error'; text: string }> = {
  connected:    { type: 'success', text: '已连接' },
  unconfigured: { type: 'default', text: '未配置' },
  error:        { type: 'error',   text: '异常' },
};

// ── 消息模板 Mock ─────────────────────────────────────────────

interface TemplateMock {
  id: string;
  name: string;
  channel: string;
  msgType: string;
  usageCount: number;
  lastUsed: string;
  enabled: boolean;
}

const TEMPLATE_DATA: TemplateMock[] = [
  { id: 'T001', name: '日营收报告',     channel: '企业微信', msgType: '卡片消息', usageCount: 328,  lastUsed: '2026-03-17 08:00', enabled: true },
  { id: 'T002', name: '库存预警通知',   channel: '企业微信', msgType: '文本消息', usageCount: 156,  lastUsed: '2026-03-17 06:30', enabled: true },
  { id: 'T003', name: '排班变更提醒',   channel: '飞书',     msgType: '卡片消息', usageCount: 89,   lastUsed: '2026-03-16 15:20', enabled: true },
  { id: 'T004', name: '损耗异常告警',   channel: '企业微信', msgType: '文本消息', usageCount: 67,   lastUsed: '2026-03-16 11:45', enabled: true },
  { id: 'T005', name: 'AI决策建议推送', channel: '飞书',     msgType: '富文本',   usageCount: 45,   lastUsed: '2026-03-15 09:00', enabled: true },
  { id: 'T006', name: '宴会订单确认',   channel: '企业微信', msgType: '卡片消息', usageCount: 34,   lastUsed: '2026-03-14 17:30', enabled: false },
  { id: 'T007', name: '会员生日祝福',   channel: '钉钉',     msgType: '文本消息', usageCount: 0,    lastUsed: '-',                enabled: false },
  { id: 'T008', name: '周报汇总',       channel: '飞书',     msgType: '富文本',   usageCount: 12,   lastUsed: '2026-03-10 09:00', enabled: true },
];

const templateColumns: ZTableColumn<TemplateMock>[] = [
  { key: 'name',       title: '模板名称',   dataIndex: 'name' },
  {
    key: 'channel',
    title: '渠道',
    dataIndex: 'channel',
    render: (v: string) => {
      const cls = v === '企业微信' ? styles.badgeWecom : v === '钉钉' ? styles.badgeDingtalk : styles.badgeFeishu;
      return <span className={`${styles.channelBadge} ${cls}`}>{v}</span>;
    },
  },
  { key: 'msgType',    title: '消息类型',   dataIndex: 'msgType' },
  { key: 'usageCount', title: '使用次数',   dataIndex: 'usageCount', align: 'right' },
  { key: 'lastUsed',   title: '最后使用',   dataIndex: 'lastUsed' },
  {
    key: 'status',
    title: '状态',
    render: (_: unknown, row: TemplateMock) => (
      <ZBadge type={row.enabled ? 'success' : 'default'} text={row.enabled ? '启用' : '禁用'} />
    ),
  },
  {
    key: 'action',
    title: '操作',
    render: () => <ZButton size="sm" variant="ghost">编辑</ZButton>,
  },
];

// ── 推送记录 Mock ─────────────────────────────────────────────

interface PushRecord {
  id: string;
  time: string;
  channel: string;
  receiver: string;
  msgType: string;
  status: 'success' | 'failed' | 'pending';
  duration: string;
}

const PUSH_RECORDS: PushRecord[] = [
  { id: 'P001', time: '2026-03-17 08:00:12', channel: '企业微信', receiver: '全体店长', msgType: '日营收报告',   status: 'success', duration: '120ms' },
  { id: 'P002', time: '2026-03-17 07:45:03', channel: '企业微信', receiver: '王店长',   msgType: '库存预警',     status: 'success', duration: '89ms' },
  { id: 'P003', time: '2026-03-17 07:30:28', channel: '飞书',     receiver: '运营总监', msgType: 'AI决策建议',   status: 'success', duration: '156ms' },
  { id: 'P004', time: '2026-03-17 06:30:15', channel: '企业微信', receiver: '张厨师长', msgType: '库存预警',     status: 'success', duration: '95ms' },
  { id: 'P005', time: '2026-03-16 22:00:01', channel: '飞书',     receiver: '全体管理', msgType: '排班变更',     status: 'success', duration: '134ms' },
  { id: 'P006', time: '2026-03-16 18:30:45', channel: '企业微信', receiver: '李经理',   msgType: '损耗告警',     status: 'failed',  duration: '-' },
  { id: 'P007', time: '2026-03-16 15:20:11', channel: '飞书',     receiver: '全体店长', msgType: '排班变更',     status: 'success', duration: '112ms' },
  { id: 'P008', time: '2026-03-16 14:00:33', channel: '企业微信', receiver: '赵店长',   msgType: '宴会确认',     status: 'success', duration: '78ms' },
  { id: 'P009', time: '2026-03-16 11:45:22', channel: '企业微信', receiver: '王厨师长', msgType: '损耗告警',     status: 'success', duration: '101ms' },
  { id: 'P010', time: '2026-03-16 09:00:05', channel: '飞书',     receiver: '运营总监', msgType: '周报汇总',     status: 'pending', duration: '-' },
];

const pushColumns: ZTableColumn<PushRecord>[] = [
  { key: 'time',     title: '时间',   dataIndex: 'time', width: 170 },
  {
    key: 'channel',
    title: '渠道',
    dataIndex: 'channel',
    render: (v: string) => {
      const cls = v === '企业微信' ? styles.badgeWecom : v === '钉钉' ? styles.badgeDingtalk : styles.badgeFeishu;
      return <span className={`${styles.channelBadge} ${cls}`}>{v}</span>;
    },
  },
  { key: 'receiver', title: '接收人', dataIndex: 'receiver' },
  { key: 'msgType',  title: '消息类型', dataIndex: 'msgType' },
  {
    key: 'status',
    title: '状态',
    render: (_: unknown, row: PushRecord) => {
      const map: Record<string, { type: 'success' | 'error' | 'warning'; text: string }> = {
        success: { type: 'success', text: '成功' },
        failed:  { type: 'error',   text: '失败' },
        pending: { type: 'warning', text: '发送中' },
      };
      const cfg = map[row.status];
      return <ZBadge type={cfg.type} text={cfg.text} />;
    },
  },
  {
    key: 'duration',
    title: '耗时',
    dataIndex: 'duration',
    align: 'right',
    render: (v: string) => <span className={styles.durationCell}>{v}</span>,
  },
];

// ── 渠道Icon映射 ─────────────────────────────────────────────

const CHANNEL_ICON_LABEL: Record<string, string> = {
  wecom: '微',
  dingtalk: '钉',
  feishu: '飞',
};

// ── 渠道配置表单 Mock ──────────────────────────────────────────

interface ConfigFormState {
  wecom:    { webhookUrl: string; secret: string; callbackUrl: string };
  dingtalk: { webhookUrl: string; secret: string; callbackUrl: string };
  feishu:   { webhookUrl: string; secret: string; callbackUrl: string };
}

// ── 组件 ─────────────────────────────────────────────────────

const IMChannelPage: React.FC = () => {
  const [configForms, setConfigForms] = useState<ConfigFormState>({
    wecom:    { webhookUrl: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx-xxxx-xxxx-xxxx', secret: '••••••••', callbackUrl: 'https://api.zlsjos.cn/webhook/wecom' },
    dingtalk: { webhookUrl: '', secret: '', callbackUrl: '' },
    feishu:   { webhookUrl: 'https://open.feishu.cn/open-apis/bot/v2/hook/xxxx-xxxx-xxxx', secret: '••••••••', callbackUrl: 'https://api.zlsjos.cn/webhook/feishu' },
  });

  const handleConfigChange = (channel: keyof ConfigFormState, field: string, value: string) => {
    setConfigForms(prev => ({
      ...prev,
      [channel]: { ...prev[channel], [field]: value },
    }));
  };

  // ── 渠道配置Tab ──
  const renderConfigTab = () => {
    const configs: Array<{ key: keyof ConfigFormState; name: string; iconClass: string }> = [
      { key: 'wecom',    name: '企业微信', iconClass: styles.iconWecom },
      { key: 'dingtalk', name: '钉钉',     iconClass: styles.iconDingtalk },
      { key: 'feishu',   name: '飞书',     iconClass: styles.iconFeishu },
    ];
    return (
      <div className={styles.configGrid}>
        {configs.map(cfg => (
          <div key={cfg.key} className={styles.configCard}>
            <div className={styles.configCardTitle}>
              <span className={`${styles.configCardIcon} ${cfg.iconClass}`}>
                {CHANNEL_ICON_LABEL[cfg.key]}
              </span>
              {cfg.name}配置
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Webhook URL</label>
              <input
                className={styles.formInput}
                placeholder="请输入 Webhook 地址"
                value={configForms[cfg.key].webhookUrl}
                onChange={e => handleConfigChange(cfg.key, 'webhookUrl', e.target.value)}
              />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>Secret / Token</label>
              <input
                className={styles.formInput}
                type="password"
                placeholder="请输入签名密钥"
                value={configForms[cfg.key].secret}
                onChange={e => handleConfigChange(cfg.key, 'secret', e.target.value)}
              />
              <div className={styles.formHint}>用于消息签名验证，确保安全性</div>
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>回调地址</label>
              <input
                className={styles.formInput}
                placeholder="如 https://api.zlsjos.cn/webhook/..."
                value={configForms[cfg.key].callbackUrl}
                onChange={e => handleConfigChange(cfg.key, 'callbackUrl', e.target.value)}
              />
              <div className={styles.formHint}>用于接收平台回调事件</div>
            </div>
            <ZButton size="sm" variant="primary">保存配置</ZButton>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>IM 渠道管理</h1>
        <p className={styles.pageDesc}>统一管理企业微信、钉钉、飞书推送渠道，配置 Webhook 和消息模板</p>
      </div>

      {/* 渠道卡片 */}
      <div className={styles.channelGrid}>
        {CHANNELS.map(ch => {
          const statusCfg = STATUS_MAP[ch.status];
          return (
            <ZCard key={ch.key}>
              <div className={styles.channelCardHead}>
                <div className={styles.channelNameRow}>
                  <div className={`${styles.channelIcon} ${ch.iconClass}`}>
                    {CHANNEL_ICON_LABEL[ch.key]}
                  </div>
                  <span className={styles.channelName}>{ch.name}</span>
                </div>
                <ZBadge type={statusCfg.type} text={statusCfg.text} />
              </div>
              <div className={styles.channelMeta}>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>今日推送</span>
                  <span className={styles.metaValue}>{ch.todayPush} 条</span>
                </div>
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Webhook</span>
                  <span className={styles.webhookUrl}>
                    {ch.webhookUrl ? ch.webhookUrl.slice(0, 40) + '****' : '未配置'}
                  </span>
                </div>
              </div>
              <div className={styles.channelActions}>
                <ZButton size="sm" variant={ch.status === 'unconfigured' ? 'primary' : 'ghost'}>
                  {ch.status === 'unconfigured' ? '去配置' : '修改配置'}
                </ZButton>
                {ch.status === 'connected' && (
                  <ZButton size="sm" variant="ghost">发送测试</ZButton>
                )}
              </div>
            </ZCard>
          );
        })}
      </div>

      {/* Tab 区域 */}
      <div className={styles.tabSection}>
        <ZTabs
          items={[
            {
              key: 'templates',
              label: '消息模板',
              badge: TEMPLATE_DATA.length,
              children: (
                <ZTable<TemplateMock>
                  columns={templateColumns}
                  dataSource={TEMPLATE_DATA}
                  rowKey="id"
                />
              ),
            },
            {
              key: 'records',
              label: '推送记录',
              badge: PUSH_RECORDS.length,
              children: (
                <ZTable<PushRecord>
                  columns={pushColumns}
                  dataSource={PUSH_RECORDS}
                  rowKey="id"
                />
              ),
            },
            {
              key: 'config',
              label: '渠道配置',
              children: renderConfigTab(),
            },
          ]}
        />
      </div>

      {/* 推送效果统计 */}
      <div className={styles.statsSection}>
        <div className={styles.statsTitle}>推送效果统计</div>
        <div className={styles.statsGrid}>
          <ZCard>
            <ZKpi value="1,258" label="总推送数" unit="条" change={12.5} changeLabel="较上周" />
          </ZCard>
          <ZCard>
            <ZKpi value="99.2" label="送达率" unit="%" change={0.3} changeLabel="较上周" color="var(--accent)" />
          </ZCard>
          <ZCard>
            <ZKpi value="45.8" label="阅读率" unit="%" change={-2.1} changeLabel="较上周" />
          </ZCard>
        </div>
      </div>
    </div>
  );
};

export default IMChannelPage;
