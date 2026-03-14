/**
 * 接入配置管理页 — /platform/integrations
 *
 * 支持 7 种 API 系统类型（品智收银 / 奥琦玮微生活会员 / 奥琦玮供应链 /
 * 天财商龙收银 / 天财商龙会员 / 天财商龙云供应链 / 易订预订系统）的配置管理。
 * 复用后端 /api/v1/integrations/systems CRUD，无需后端改动。
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ZCard, ZBadge, ZButton, ZTable, ZAlert, ZDrawer, ZSelect, ZSkeleton,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import type { SelectOption } from '../../design-system/components/ZSelect';
import { apiClient } from '../../services/api';
import styles from './PlatformIntegrationsPage.module.css';

// ── 系统类型定义 ─────────────────────────────────────────────────────────────

interface FieldDef {
  key: string;          // 'api_key' | 'api_secret' | 'config.center_id' 等
  label: string;
  required: boolean;
  secret?: boolean;     // type="password"
  multiline?: boolean;  // textarea（RSA公钥）
  placeholder?: string;
  hint?: string;
}

interface SystemSchema {
  key: string;          // 唯一标识
  label: string;        // 显示名称
  type: 'pos' | 'member' | 'supplier' | 'reservation';
  provider: string;     // 存 DB provider 字段
  defaultEndpoint: string;
  description: string;
  authMode: string;     // 认证方式摘要
  fields: FieldDef[];
}

const SYSTEM_SCHEMAS: SystemSchema[] = [
  {
    key: 'pinzhi_pos',
    label: '品智收银',
    type: 'pos',
    provider: 'pinzhi',
    defaultEndpoint: 'https://www.pinzhitech.com',
    description: '品智 POS 收银系统，适用于尝在一起等餐饮连锁。',
    authMode: 'API Token 鉴权',
    fields: [
      { key: 'api_key', label: 'API Token', required: true, secret: true,
        placeholder: '请输入品智 API Token', hint: '在品智商户后台 > 开放平台 中获取' },
    ],
  },
  {
    key: 'aoqiwei_crm',
    label: '奥琦玮微生活会员',
    type: 'member',
    provider: 'aoqiwei_crm',
    defaultEndpoint: 'https://welcrm.com',
    description: '奥琦玮微生活会员系统（welcrm.com），适用于徐记海鲜等客户。',
    authMode: 'AppID + AppKey MD5 签名（递归 ksort + http_build_query）',
    fields: [
      { key: 'api_key', label: 'AppID', required: true,
        placeholder: '奥琦玮 CRM AppID' },
      { key: 'api_secret', label: 'AppKey（密钥）', required: true, secret: true,
        placeholder: '奥琦玮 CRM AppKey', hint: '仅参与签名计算，不随请求发送' },
    ],
  },
  {
    key: 'aoqiwei_supply',
    label: '奥琦玮供应链',
    type: 'supplier',
    provider: 'aoqiwei_supply',
    defaultEndpoint: 'https://openapi.acescm.cn',
    description: '奥琦玮供应链开放平台（openapi.acescm.cn）。',
    authMode: 'AppKey + AppSecret MD5 签名',
    fields: [
      { key: 'api_key', label: 'AppKey', required: true,
        placeholder: '奥琦玮供应链 AppKey' },
      { key: 'api_secret', label: 'AppSecret（密钥）', required: true, secret: true,
        placeholder: '奥琦玮供应链 AppSecret' },
    ],
  },
  {
    key: 'tiancai_pos',
    label: '天财商龙收银',
    type: 'pos',
    provider: 'tiancai_pos',
    defaultEndpoint: 'https://cysms.wuuxiang.com',
    description: '天财商龙（吾享）收银开放 API（cysms.wuuxiang.com）。',
    authMode: 'OAuth2 Token 换取（appid + accessid → access_token）',
    fields: [
      { key: 'api_key', label: 'AppID（Terminal ID）', required: true,
        placeholder: '天财商龙 AppID' },
      { key: 'api_secret', label: 'AccessID（授权ID）', required: true, secret: true,
        placeholder: '天财商龙 AccessID', hint: '用于获取 Token，同时作为请求 Header' },
      { key: 'config.center_id', label: '集团ID（centerId）', required: true,
        placeholder: '如：GRP_001', hint: '接口参数 centerId' },
      { key: 'config.shop_id', label: '门店ID（shopId）', required: true,
        placeholder: '如：SHOP_001', hint: '接口参数 shopId，精确到门店' },
    ],
  },
  {
    key: 'tiancai_crm',
    label: '天财商龙会员',
    type: 'member',
    provider: 'tiancai_crm',
    defaultEndpoint: 'https://scrm.wuuxiang.com',
    description: '天财商龙会员（scrm.wuuxiang.com/crm7api/），RSA 加密鉴权。',
    authMode: 'RSA 公钥加密（business_params → 加密 → sign 字段）',
    fields: [
      { key: 'config.product_id', label: 'ProductID', required: true,
        placeholder: '天财会员产品ID', hint: '由天财商龙提供' },
      { key: 'config.company_id', label: '集团ID', required: true,
        placeholder: 'Header: Tcsl-Shardingkey 值' },
      { key: 'config.shop_id', label: '门店ID', required: true,
        placeholder: '门店唯一标识' },
      { key: 'api_secret', label: 'RSA 公钥', required: true, multiline: true,
        placeholder: '-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----',
        hint: '天财商龙提供的 RSA 公钥，用于加密业务参数' },
    ],
  },
  {
    key: 'tiancai_supply',
    label: '天财商龙云供应链',
    type: 'supplier',
    provider: 'tiancai_supply',
    defaultEndpoint: 'https://fxscm.net',
    description: '天财商龙云供应链（fxscm.net），用户名密码鉴权。',
    authMode: '用户名 + 密码（Query 参数）',
    fields: [
      { key: 'api_key', label: '用户名', required: true,
        placeholder: '天财供应链用户名' },
      { key: 'api_secret', label: '密码', required: true, secret: true,
        placeholder: '天财供应链密码' },
    ],
  },
  {
    key: 'yiding_reservation',
    label: '易订预订系统',
    type: 'reservation',
    provider: 'yiding',
    defaultEndpoint: 'https://open.zhidianfun.com/yidingopen/',
    description: '易订餐饮预订系统（zhidianfun.com），支持预订管理、桌位同步、会员管理、账单数据同步。',
    authMode: 'Token 换取（appid + secret → access_token），Token 自动刷新',
    fields: [
      { key: 'api_key', label: 'AppID（应用ID）', required: true,
        placeholder: '易订 AppID', hint: '在易订商户后台 > 开放平台中获取' },
      { key: 'api_secret', label: 'Secret（应用密钥）', required: true, secret: true,
        placeholder: '易订 App Secret', hint: '用于换取 access_token，请妥善保管' },
    ],
  },
];

const SCHEMA_MAP: Record<string, SystemSchema> = Object.fromEntries(
  SYSTEM_SCHEMAS.map(s => [s.key, s])
);

// ── 工具函数 ──────────────────────────────────────────────────────────────────

const TYPE_LABEL: Record<string, string> = {
  pos: '收银POS', member: '会员CRM', supplier: '供应链', reservation: '预订系统',
};
const TYPE_BADGE: Record<string, 'info' | 'success' | 'warning' | 'default'> = {
  pos: 'info', member: 'success', supplier: 'warning', reservation: 'default',
};
const STATUS_LABEL: Record<string, string> = {
  active: '活跃', inactive: '未激活', error: '错误', testing: '测试中',
};
const STATUS_BADGE: Record<string, 'success' | 'default' | 'error' | 'warning'> = {
  active: 'success', inactive: 'default', error: 'error', testing: 'warning',
};

function relativeTime(ts: string | null | undefined): string {
  if (!ts) return '—';
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

function schemaKeyFromProvider(provider: string): string {
  return SYSTEM_SCHEMAS.find(s => s.provider === provider)?.key ?? '';
}

// ── 表单状态 ──────────────────────────────────────────────────────────────────

interface FormState {
  name: string;
  systemKey: string;
  api_endpoint: string;
  api_key: string;
  api_secret: string;
  [extraKey: string]: string;
}

const emptyForm = (): FormState => ({
  name: '', systemKey: '', api_endpoint: '', api_key: '', api_secret: '',
});

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function PlatformIntegrationsPage() {
  const [systems, setSystems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'pos' | 'member' | 'supplier' | 'reservation'>('all');

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [submitting, setSubmitting] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // 用于 secret 字段"已设置，留空不修改"模式
  const isEditing = editingId !== null;

  const loadSystems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/api/v1/integrations/systems');
      const raw = Array.isArray(res) ? res : (res?.systems ?? res?.data ?? []);
      setSystems(raw.filter(Boolean));
    } catch {
      setSystems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSystems(); }, [loadSystems]);

  // ── Tab 过滤 ──
  const filtered = activeTab === 'all' ? systems : systems.filter(s => s.type === activeTab);
  const counts = {
    all: systems.length,
    pos: systems.filter(s => s.type === 'pos').length,
    member: systems.filter(s => s.type === 'member').length,
    supplier: systems.filter(s => s.type === 'supplier').length,
    reservation: systems.filter(s => s.type === 'reservation').length,
  };

  // ── 打开新增 ──
  const openAdd = () => {
    setEditingId(null);
    setForm(emptyForm());
    setSaveError(null);
    setTestResult(null);
    setDrawerOpen(true);
  };

  // ── 打开编辑 ──
  const openEdit = (sys: any) => {
    const skKey = schemaKeyFromProvider(sys.provider);
    const configObj = sys.config ?? {};
    const extraFields: Record<string, string> = {};
    // 将 config.xxx 字段还原到 form key
    if (skKey && SCHEMA_MAP[skKey]) {
      SCHEMA_MAP[skKey].fields
        .filter(f => f.key.startsWith('config.'))
        .forEach(f => {
          const sub = f.key.slice(7);
          extraFields[sub] = configObj[sub] ?? '';
        });
    }
    setEditingId(sys.id ?? sys.system_id);
    setForm({
      name: sys.name ?? '',
      systemKey: skKey,
      api_endpoint: sys.api_endpoint ?? '',
      api_key: sys.api_key ?? '',
      api_secret: '',   // 密钥回显为空，留空则不覆盖
      ...extraFields,
    });
    setSaveError(null);
    setTestResult(null);
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    setEditingId(null);
    setForm(emptyForm());
    setSaveError(null);
    setTestResult(null);
  };

  // ── 字段变更 ──
  const setField = (key: string, val: string) =>
    setForm(prev => ({ ...prev, [key]: val }));

  // ── 系统类型选择 → 重置动态字段 ──
  const handleSchemaSelect = (val: any) => {
    const schema = SCHEMA_MAP[val as string];
    setForm(prev => ({
      ...emptyForm(),
      name: prev.name,
      systemKey: val as string,
      api_endpoint: schema?.defaultEndpoint ?? '',
    }));
  };

  // ── 构建提交 payload ──
  const buildPayload = () => {
    const schema = SCHEMA_MAP[form.systemKey];
    if (!schema) return null;

    const config: Record<string, string> = {};
    schema.fields
      .filter(f => f.key.startsWith('config.'))
      .forEach(f => {
        const sub = f.key.slice(7);
        if (form[sub]) config[sub] = form[sub];
      });

    const payload: Record<string, any> = {
      name: form.name.trim(),
      type: schema.type,
      provider: schema.provider,
      api_endpoint: form.api_endpoint || schema.defaultEndpoint,
    };
    if (form.api_key) payload.api_key = form.api_key;
    if (form.api_secret) payload.api_secret = form.api_secret;
    if (Object.keys(config).length) payload.config = config;
    if (!isEditing) payload.status = 'inactive';

    return payload;
  };

  // ── 保存 ──
  const handleSave = async () => {
    const schema = SCHEMA_MAP[form.systemKey];
    if (!schema) { setSaveError('请选择系统类型'); return; }
    if (!form.name.trim()) { setSaveError('配置名称不能为空'); return; }
    // 必填校验
    for (const f of schema.fields) {
      if (!f.required) continue;
      const val = f.key.startsWith('config.') ? form[f.key.slice(7)] : form[f.key as keyof FormState];
      if (!val && !(isEditing && f.secret)) {
        setSaveError(`"${f.label}" 为必填项`);
        return;
      }
    }

    const payload = buildPayload();
    if (!payload) return;

    setSubmitting(true);
    setSaveError(null);
    try {
      if (isEditing) {
        await apiClient.put(`/api/v1/integrations/systems/${editingId}`, payload);
      } else {
        await apiClient.post('/api/v1/integrations/systems', payload);
      }
      closeDrawer();
      loadSystems();
    } catch (err: any) {
      setSaveError(err?.message ?? '保存失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  // ── 测试连通 ──
  const handleTest = async (sysId: string) => {
    setTestingId(sysId);
    try {
      await apiClient.post(`/api/v1/integrations/systems/${sysId}/test`);
      setTestResult({ ok: true, msg: '连通测试成功' });
    } catch (err: any) {
      const msg = err?.status === 404 ? '该系统暂不支持连通测试' : (err?.message ?? '连通测试失败');
      setTestResult({ ok: false, msg });
    } finally {
      setTestingId(null);
    }
  };

  // ── 启停切换 ──
  const handleToggleStatus = async (sys: any) => {
    const nextStatus = sys.status === 'active' ? 'inactive' : 'active';
    try {
      await apiClient.put(`/api/v1/integrations/systems/${sys.id ?? sys.system_id}`, { status: nextStatus });
      loadSystems();
    } catch { /* silent */ }
  };

  // ── 当前选中 Schema ──
  const currentSchema = form.systemKey ? SCHEMA_MAP[form.systemKey] : null;

  // ── Table 列定义 ──
  const columns: ZTableColumn<any>[] = [
    {
      key: 'name',
      title: '配置名称',
      render: (row: any) => (
        <span className={styles.nameCell}>
          <span className={styles.nameText}>{row.name}</span>
          {row.store_id && <span className={styles.storeTag}>{row.store_id}</span>}
        </span>
      ),
    },
    {
      key: 'type',
      title: '系统类型',
      render: (row: any) => (
        <ZBadge type={TYPE_BADGE[row.type] ?? 'default'} text={TYPE_LABEL[row.type] ?? row.type} />
      ),
    },
    {
      key: 'provider',
      title: '服务商',
      render: (row: any) => {
        const schema = SYSTEM_SCHEMAS.find(s => s.provider === row.provider);
        return <span className={styles.providerTag}>{schema?.label ?? row.provider}</span>;
      },
    },
    {
      key: 'api_endpoint',
      title: 'API地址',
      render: (row: any) => (
        <span className={styles.endpoint} title={row.api_endpoint}>
          {row.api_endpoint ? row.api_endpoint.replace(/^https?:\/\//, '').slice(0, 40) : '—'}
        </span>
      ),
    },
    {
      key: 'status',
      title: '状态',
      render: (row: any) => (
        <ZBadge type={STATUS_BADGE[row.status] ?? 'default'} text={STATUS_LABEL[row.status] ?? row.status} />
      ),
    },
    {
      key: 'last_sync_at',
      title: '上次同步',
      render: (row: any) => (
        <span className={styles.timeCell}>{relativeTime(row.last_sync_at)}</span>
      ),
    },
    {
      key: 'actions',
      title: '操作',
      render: (row: any) => (
        <span className={styles.actionGroup}>
          <ZButton size="sm" variant="ghost" onClick={() => openEdit(row)}>编辑</ZButton>
          <ZButton
            size="sm"
            variant="ghost"
            onClick={() => handleTest(row.id ?? row.system_id)}
          >
            {testingId === (row.id ?? row.system_id) ? '测试中…' : '测试'}
          </ZButton>
          <ZButton
            size="sm"
            variant={row.status === 'active' ? 'ghost' : 'primary'}
            onClick={() => handleToggleStatus(row)}
          >
            {row.status === 'active' ? '停用' : '启用'}
          </ZButton>
        </span>
      ),
    },
  ];

  // ── Schema 选项 ──
  const schemaOptions: SelectOption[] = SYSTEM_SCHEMAS.map(s => ({
    value: s.key,
    label: `${s.label}（${TYPE_LABEL[s.type]}）`,
  }));

  // ── 渲染动态字段 ──
  const renderDynamicField = (field: FieldDef) => {
    const isConfigField = field.key.startsWith('config.');
    const formKey = isConfigField ? field.key.slice(7) : field.key;
    const value = (form as any)[formKey] ?? '';

    return (
      <div key={field.key} className={styles.fieldRow}>
        <label className={styles.fieldLabel}>
          {field.label}
          {field.required && <span className={styles.required}>*</span>}
        </label>
        {field.multiline ? (
          <textarea
            className={styles.textarea}
            value={value}
            onChange={e => setField(formKey, e.target.value)}
            placeholder={
              isEditing && field.secret
                ? '已设置（留空不修改）'
                : field.placeholder
            }
            rows={5}
          />
        ) : (
          <input
            className={styles.input}
            type={field.secret ? 'password' : 'text'}
            value={value}
            onChange={e => setField(formKey, e.target.value)}
            placeholder={
              isEditing && field.secret
                ? '已设置（留空不修改）'
                : field.placeholder
            }
            autoComplete={field.secret ? 'new-password' : 'off'}
          />
        )}
        {field.hint && <span className={styles.fieldHint}>{field.hint}</span>}
      </div>
    );
  };

  return (
    <div className={styles.page}>
      {/* ── 页头 ── */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>接入配置管理</h1>
          <p className={styles.pageSubtitle}>管理各商户与 POS / CRM / 供应链系统的 API 接入配置</p>
        </div>
        <ZButton variant="primary" size="md" onClick={openAdd}>
          ＋ 新增接入配置
        </ZButton>
      </div>

      {/* ── Tab 过滤栏 ── */}
      <div className={styles.tabBar}>
        {(['all', 'pos', 'member', 'supplier', 'reservation'] as const).map(tab => (
          <button
            key={tab}
            className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'all' ? '全部' : TYPE_LABEL[tab]}
            <span className={styles.tabCount}>{counts[tab]}</span>
          </button>
        ))}
      </div>

      {/* ── 主表格 ── */}
      <ZCard>
        {loading ? (
          <ZSkeleton rows={4} />
        ) : (
          <ZTable
            columns={columns}
            data={filtered}
            emptyText={activeTab === 'all' ? '暂无接入配置，点击右上角新增' : `暂无${TYPE_LABEL[activeTab]}接入配置`}
          />
        )}
      </ZCard>

      {/* ── 新增/编辑 Drawer ── */}
      <ZDrawer
        open={drawerOpen}
        onClose={closeDrawer}
        title={isEditing ? '编辑接入配置' : '新增接入配置'}
        width={520}
        footer={
          <div className={styles.drawerFooter}>
            <ZButton variant="ghost" onClick={closeDrawer}>取消</ZButton>
            <ZButton variant="primary" onClick={handleSave}>
              {submitting ? '保存中…' : '保存配置'}
            </ZButton>
          </div>
        }
      >
        <div className={styles.drawerBody}>
          {/* 错误提示 */}
          {saveError && (
            <div className={styles.schemaTip}>
              <ZAlert variant="error" title={saveError} />
            </div>
          )}

          {/* 测试结果提示 */}
          {testResult && (
            <div className={styles.schemaTip}>
              <ZAlert variant={testResult.ok ? 'success' : 'error'} title={testResult.msg} />
            </div>
          )}

          {/* 基本信息 */}
          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>
              配置名称<span className={styles.required}>*</span>
            </label>
            <input
              className={styles.input}
              type="text"
              value={form.name}
              onChange={e => setField('name', e.target.value)}
              placeholder="如：徐记海鲜-奥琦玮会员"
              autoComplete="off"
            />
            <span className={styles.fieldHint}>建议格式：商户名称-系统名称</span>
          </div>

          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>
              系统类型<span className={styles.required}>*</span>
            </label>
            <ZSelect
              options={schemaOptions}
              value={form.systemKey || null}
              onChange={handleSchemaSelect}
              placeholder="选择接入的 API 系统"
            />
          </div>

          {/* 系统认证说明 */}
          {currentSchema && (
            <div className={styles.schemaTip}>
              <ZAlert variant="info" title={currentSchema.label}>
                {currentSchema.description}
                <br />
                <strong>认证方式：</strong>{currentSchema.authMode}
              </ZAlert>
            </div>
          )}

          {/* API 地址（所有系统都有） */}
          {currentSchema && (
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>API 地址</label>
              <input
                className={styles.input}
                type="text"
                value={form.api_endpoint}
                onChange={e => setField('api_endpoint', e.target.value)}
                placeholder={currentSchema.defaultEndpoint}
                autoComplete="off"
              />
              <span className={styles.fieldHint}>
                默认：{currentSchema.defaultEndpoint}（一般无需修改）
              </span>
            </div>
          )}

          {/* 系统专属动态字段 */}
          {currentSchema && (
            <div className={styles.dynamicFields}>
              <div className={styles.sectionDivider}>凭据配置</div>
              {currentSchema.fields.map(renderDynamicField)}
            </div>
          )}

          {/* 新建提示 */}
          {!isEditing && currentSchema && (
            <div className={styles.schemaTip}>
              <ZAlert variant="warning" title='保存后默认为「未激活」状态'>
                请保存后点击"测试"验证连通性，确认无误后手动"启用"。
              </ZAlert>
            </div>
          )}
        </div>
      </ZDrawer>
    </div>
  );
}
