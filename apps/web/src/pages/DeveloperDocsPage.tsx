import React, { useState, useEffect, useCallback } from 'react';
import { Form, Input } from 'antd';
import { ZCard, ZBadge, ZButton, ZSkeleton, ZModal, ZEmpty } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './DeveloperDocsPage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────────

interface RequestParam {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

interface Endpoint {
  level: number;
  key: string;
  name: string;
  method: string;
  path: string;
  description: string;
  tier_required: string;
  request_params: RequestParam[];
  response_example: Record<string, unknown>;
  code_examples: { python: string; nodejs: string; curl: string };
}

interface AuthStep {
  step: number;
  title: string;
  description: string;
  headers?: { name: string; value: string; description: string }[];
  error_codes?: { code: number; message: string; reason: string }[];
  code_python?: string;
  code_nodejs?: string;
}

interface SandboxResult {
  developer_id: string;
  api_key: string;
  api_secret: string;
  rate_limit_rpm: number;
  note: string;
  base_url: string;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const LEVEL_NAMES: Record<number, string> = {
  1: 'Level 1 · 数据同步',
  2: 'Level 2 · 智能决策',
  3: 'Level 3 · 营销能力',
  4: 'Level 4 · 高级能力',
};

const LEVEL_COLORS: Record<number, string> = {
  1: 'var(--text-secondary)',
  2: '#FF6B2C',
  3: '#C8923A',
  4: '#722ed1',
};

const TIER_BADGE: Record<string, 'neutral' | 'success' | 'warning' | 'error'> = {
  free: 'neutral', basic: 'success', pro: 'warning', enterprise: 'error',
};

const TIER_LABELS: Record<string, string> = {
  free: '免费', basic: '基础版', pro: '专业版', enterprise: '企业版',
};

const METHOD_COLORS: Record<string, string> = {
  GET: '#1A7A52', POST: '#FF6B2C', PUT: '#C8923A', DELETE: '#C53030', PATCH: '#722ed1',
};

const TABS = [
  { key: 'quickstart', label: '快速开始' },
  { key: '1', label: 'Level 1 · 数据' },
  { key: '2', label: 'Level 2 · 决策' },
  { key: '3', label: 'Level 3 · 营销' },
  { key: '4', label: 'Level 4 · 高级' },
  { key: 'sdk', label: 'SDK 示例' },
];

// ── Sub-components ─────────────────────────────────────────────────────────────

const CodeBlock: React.FC<{ code: string }> = ({ code }) => (
  <pre className={styles.codeBlock}><code>{code}</code></pre>
);

const CodeTabs: React.FC<{ examples: { python: string; nodejs: string; curl: string } }> = ({ examples }) => {
  const [lang, setLang] = useState<'python' | 'nodejs' | 'curl'>('python');
  return (
    <div>
      <div className={styles.langTabs}>
        {(['python', 'nodejs', 'curl'] as const).map(l => (
          <button
            key={l}
            className={`${styles.langTab} ${lang === l ? styles.langTabActive : ''}`}
            onClick={() => setLang(l)}
          >
            {l === 'nodejs' ? 'Node.js' : l === 'curl' ? 'cURL' : 'Python'}
          </button>
        ))}
      </div>
      <CodeBlock code={examples[lang]} />
    </div>
  );
};

const EndpointCard: React.FC<{ ep: Endpoint }> = ({ ep }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.endpointCard}>
      <div className={styles.endpointHeader} onClick={() => setOpen(v => !v)} style={{ cursor: 'pointer' }}>
        <div className={styles.endpointLeft}>
          <span className={styles.methodBadge} style={{ background: METHOD_COLORS[ep.method] || '#888' }}>
            {ep.method}
          </span>
          <code className={styles.endpointPath}>{ep.path}</code>
          <span className={styles.endpointName}>{ep.name}</span>
        </div>
        <div className={styles.endpointRight}>
          <ZBadge type={TIER_BADGE[ep.tier_required] || 'neutral'} text={TIER_LABELS[ep.tier_required] || ep.tier_required} />
          <span className={styles.chevron}>{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div className={styles.endpointBody}>
          <p className={styles.endpointDesc}>{ep.description}</p>

          {ep.request_params.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>请求参数</div>
              <table className={styles.paramsTable}>
                <thead>
                  <tr>
                    <th>参数</th><th>类型</th><th>必填</th><th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {ep.request_params.map(p => (
                    <tr key={p.name}>
                      <td><code className={styles.paramName}>{p.name}</code></td>
                      <td><span className={styles.paramType}>{p.type}</span></td>
                      <td>{p.required ? <span style={{ color: 'var(--red)' }}>是</span> : '否'}</td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{p.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className={styles.section}>
            <div className={styles.sectionTitle}>响应示例</div>
            <CodeBlock code={JSON.stringify(ep.response_example, null, 2)} />
          </div>

          <div className={styles.section}>
            <div className={styles.sectionTitle}>代码示例</div>
            <CodeTabs examples={ep.code_examples} />
          </div>
        </div>
      )}
    </div>
  );
};

// ── SDK page ───────────────────────────────────────────────────────────────────

const PYTHON_SDK = `# pip install requests
import requests, hmac, hashlib, time, json
from typing import Optional

class ZhilianClient:
    """屯象开放平台 Python SDK"""

    def __init__(self, api_key: str, api_secret: str, sandbox: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = (
            "https://sandbox.zhilian-os.com/v1" if sandbox
            else "https://api.zhilian-os.com/v1"
        )

    def _sign(self, body: str) -> dict:
        ts = str(int(time.time()))
        sig = hmac.new(self.api_secret.encode(), f"{ts}:{body}".encode(), hashlib.sha256).hexdigest()
        return {"X-API-Key": self.api_key, "X-Timestamp": ts, "X-Signature": sig,
                "Content-Type": "application/json"}

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        headers = self._sign("")
        resp = requests.get(f"{self.base_url}{path}", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: dict) -> dict:
        body = json.dumps(data)
        headers = self._sign(body)
        resp = requests.post(f"{self.base_url}{path}", data=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

# 使用示例
client = ZhilianClient("zlos_your_api_key", "your_secret", sandbox=True)

# Level 1: 同步订单
result = client.post("/open/data/orders", {
    "orders": [{"order_id": "ORD001", "store_id": "STORE001", "total_amount": 188.0, "status": "completed"}]
})

# Level 2: 销量预测
prediction = client.get("/open/ai/predict-sales", {"store_id": "STORE001", "date": "2026-03-08"})

# Level 3: 发券策略
strategy = client.post("/open/marketing/coupon-strategy", {
    "scenario": "traffic_decline", "target_segment": "at_risk", "store_id": "STORE001"
})`;

const NODEJS_SDK = `// npm install axios
const axios = require('axios');
const crypto = require('crypto');

class ZhilianClient {
  constructor(apiKey, apiSecret, sandbox = false) {
    this.apiKey = apiKey;
    this.apiSecret = apiSecret;
    this.baseUrl = sandbox
      ? 'https://sandbox.zhilian-os.com/v1'
      : 'https://api.zhilian-os.com/v1';
  }

  _sign(body = '') {
    const ts = Math.floor(Date.now() / 1000).toString();
    const sig = crypto.createHmac('sha256', this.apiSecret)
      .update(\`\${ts}:\${body}\`).digest('hex');
    return { 'X-API-Key': this.apiKey, 'X-Timestamp': ts, 'X-Signature': sig,
             'Content-Type': 'application/json' };
  }

  async get(path, params = {}) {
    const { data } = await axios.get(\`\${this.baseUrl}\${path}\`,
      { params, headers: this._sign() });
    return data;
  }

  async post(path, body) {
    const raw = JSON.stringify(body);
    const { data } = await axios.post(\`\${this.baseUrl}\${path}\`, raw,
      { headers: this._sign(raw) });
    return data;
  }
}

// 使用示例
const client = new ZhilianClient('zlos_your_api_key', 'your_secret', true /* sandbox */);

// Level 1: 同步会员
await client.post('/open/data/members', {
  members: [{ phone: '13800138000', name: '张三', points: 500 }]
});

// Level 3: 客户画像
const profile = await client.get('/open/marketing/customer/13800138000/profile');`;

// ── Main Component ─────────────────────────────────────────────────────────────

const DeveloperDocsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('quickstart');
  const [endpointsByLevel, setEndpointsByLevel] = useState<Record<string, Endpoint[]>>({});
  const [authGuide, setAuthGuide] = useState<{ title: string; steps: AuthStep[] } | null>(null);
  const [loading, setLoading] = useState(false);

  const [sandboxModal, setSandboxModal] = useState(false);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [sandboxResult, setSandboxResult] = useState<SandboxResult | null>(null);
  const [sandboxForm] = Form.useForm();

  const [sdkLang, setSdkLang] = useState<'python' | 'nodejs'>('python');

  const loadDocs = useCallback(async () => {
    setLoading(true);
    try {
      const [endRes, authRes] = await Promise.allSettled([
        apiClient.get('/api/v1/open/docs/endpoints'),
        apiClient.get('/api/v1/open/docs/auth-guide'),
      ]);
      if (endRes.status === 'fulfilled') {
        const byLevel: Record<string, Endpoint[]> = {};
        Object.entries(endRes.value.data.by_level || {}).forEach(([lvl, info]: [string, any]) => {
          byLevel[lvl] = info.endpoints || [];
        });
        setEndpointsByLevel(byLevel);
      }
      if (authRes.status === 'fulfilled') setAuthGuide(authRes.value.data);
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  const handleSandboxRegister = async (values: { name: string; email: string }) => {
    setSandboxLoading(true);
    try {
      const res = await apiClient.post('/api/v1/open/sandbox/register', values);
      setSandboxResult(res.data);
    } catch (e) {
      handleApiError(e);
    } finally {
      setSandboxLoading(false);
    }
  };

  const closeSandbox = () => {
    setSandboxModal(false);
    setSandboxResult(null);
    sandboxForm.resetFields();
  };

  const sandboxFooter = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
      <ZButton onClick={closeSandbox}>关闭</ZButton>
      {!sandboxResult && (
        <ZButton variant="primary" disabled={sandboxLoading} onClick={() => sandboxForm.submit()}>
          {sandboxLoading ? '创建中…' : '创建沙箱账号'}
        </ZButton>
      )}
    </div>
  );

  // ── Render tabs ──────────────────────────────────────────────────────────────

  const renderQuickStart = () => (
    <div className={styles.quickStartGrid}>
      {/* Auth guide */}
      <ZCard title="鉴权方式">
        {loading ? <ZSkeleton height={200} /> : authGuide ? (
          <div className={styles.authSteps}>
            {authGuide.steps.map(step => (
              <div key={step.step} className={styles.authStep}>
                <div className={styles.authStepNum}>{step.step}</div>
                <div className={styles.authStepContent}>
                  <div className={styles.authStepTitle}>{step.title}</div>
                  <div className={styles.authStepDesc}>{step.description}</div>
                  {step.code_python && (
                    <div style={{ marginTop: 8 }}>
                      <CodeTabs examples={{ python: step.code_python, nodejs: step.code_nodejs || '', curl: '' }} />
                    </div>
                  )}
                  {step.headers && (
                    <table className={styles.paramsTable} style={{ marginTop: 8 }}>
                      <thead><tr><th>Header</th><th>示例值</th><th>说明</th></tr></thead>
                      <tbody>
                        {step.headers.map(h => (
                          <tr key={h.name}>
                            <td><code className={styles.paramName}>{h.name}</code></td>
                            <td><code style={{ fontSize: 12 }}>{h.value}</code></td>
                            <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{h.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {step.error_codes && (
                    <table className={styles.paramsTable} style={{ marginTop: 8 }}>
                      <thead><tr><th>状态码</th><th>含义</th><th>原因</th></tr></thead>
                      <tbody>
                        {step.error_codes.map(e => (
                          <tr key={e.code}>
                            <td><span style={{ color: '#C53030', fontWeight: 600 }}>{e.code}</span></td>
                            <td>{e.message}</td>
                            <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{e.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : <ZEmpty text="暂无鉴权说明" />}
      </ZCard>

      {/* Sandbox quick-start */}
      <ZCard title="沙箱环境">
        <div className={styles.sandboxGuide}>
          <div className={styles.sandboxBanner}>
            <div className={styles.sandboxIcon}>🏖️</div>
            <div>
              <div className={styles.sandboxTitle}>免费沙箱，5分钟接入</div>
              <div className={styles.sandboxDesc}>沙箱环境与生产隔离，所有接口返回真实结构的模拟数据，不影响正式数据。</div>
            </div>
          </div>
          <div className={styles.sandboxFeatures}>
            {[
              { icon: '🔑', label: '即申即用', desc: '邮箱注册，立刻获取 zlos_sbx_ 前缀 API Key' },
              { icon: '📦', label: '全能力可用', desc: 'Level 1-4 全部接口均开放沙箱调用' },
              { icon: '🛡️', label: '完全隔离', desc: 'Sandbox 基础 URL 与生产分开，零污染' },
              { icon: '⚡', label: '60次/分钟', desc: '足够开发调试使用，限速符合 Free 套餐' },
            ].map(f => (
              <div key={f.label} className={styles.sandboxFeatureItem}>
                <span className={styles.sandboxFeatureIcon}>{f.icon}</span>
                <div>
                  <div className={styles.sandboxFeatureLabel}>{f.label}</div>
                  <div className={styles.sandboxFeatureDesc}>{f.desc}</div>
                </div>
              </div>
            ))}
          </div>
          <ZButton variant="primary" onClick={() => setSandboxModal(true)} style={{ marginTop: 16, width: '100%' }}>
            申请沙箱账号
          </ZButton>
        </div>
      </ZCard>
    </div>
  );

  const renderLevel = (level: string) => {
    const endpoints = endpointsByLevel[level] || [];
    const lvlNum = parseInt(level);
    return (
      <div>
        <div className={styles.levelHeader} style={{ borderLeftColor: LEVEL_COLORS[lvlNum] }}>
          <span style={{ color: LEVEL_COLORS[lvlNum], fontWeight: 700 }}>{LEVEL_NAMES[lvlNum]}</span>
          <span className={styles.levelCount}>{endpoints.length} 个接口</span>
        </div>
        {loading ? <ZSkeleton height={200} /> : (
          endpoints.length > 0
            ? <div className={styles.endpointList}>{endpoints.map(ep => <EndpointCard key={ep.key} ep={ep} />)}</div>
            : <ZEmpty text="暂无接口数据" />
        )}
      </div>
    );
  };

  const renderSdk = () => (
    <div>
      <div className={styles.sdkHeader}>
        <div className={styles.sdkBtns}>
          {(['python', 'nodejs'] as const).map(l => (
            <button
              key={l}
              className={`${styles.langTab} ${sdkLang === l ? styles.langTabActive : ''}`}
              onClick={() => setSdkLang(l)}
            >
              {l === 'nodejs' ? 'Node.js' : 'Python'}
            </button>
          ))}
        </div>
        <span className={styles.sdkNote}>包含认证封装 + Level 1-3 使用示例</span>
      </div>
      <CodeBlock code={sdkLang === 'python' ? PYTHON_SDK : NODEJS_SDK} />
      <div className={styles.sdkRoadmap}>
        <div className={styles.sectionTitle} style={{ marginBottom: 12 }}>SDK 路线图</div>
        <div className={styles.sdkRoadmapGrid}>
          {[
            { lang: 'Python', status: '✅ 可用', note: 'pip install zhilian-sdk（即将上线）' },
            { lang: 'Node.js', status: '✅ 可用', note: 'npm install @zhilian/sdk（即将上线）' },
            { lang: 'Java', status: '🚧 开发中', note: 'Maven/Gradle，Q2 2026 发布' },
            { lang: 'Go', status: '📋 规划中', note: 'go get github.com/zhilian/sdk，Q3 2026' },
          ].map(s => (
            <div key={s.lang} className={styles.sdkItem}>
              <div className={styles.sdkItemLang}>{s.lang}</div>
              <div>{s.status}</div>
              <div className={styles.sdkItemNote}>{s.note}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>开发者文档</h1>
          <p className={styles.pageSub}>API 参考 · 鉴权指南 · SDK · 沙箱环境</p>
        </div>
        <div className={styles.headerActions}>
          <ZBadge type="success" text="v1.0 稳定版" />
          <ZButton onClick={() => setSandboxModal(true)} variant="primary">申请沙箱账号</ZButton>
        </div>
      </div>

      {/* Tab bar */}
      <div className={styles.tabBar}>
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className={styles.tabContent}>
        {activeTab === 'quickstart' && renderQuickStart()}
        {['1', '2', '3', '4'].includes(activeTab) && renderLevel(activeTab)}
        {activeTab === 'sdk' && renderSdk()}
      </div>

      {/* Sandbox modal */}
      <ZModal
        open={sandboxModal}
        title="申请沙箱账号"
        onClose={closeSandbox}
        footer={sandboxFooter}
        width={480}
      >
        {!sandboxResult ? (
          <Form form={sandboxForm} layout="vertical" onFinish={handleSandboxRegister}>
            <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>
              沙箱账号免费，与生产完全隔离，适合开发测试使用。
            </p>
            <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
              <Input placeholder="例：张开发" />
            </Form.Item>
            <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
              <Input placeholder="dev@company.com" />
            </Form.Item>
          </Form>
        ) : (
          <div className={styles.credResultBox}>
            <div className={styles.resultAlert}>
              沙箱账号创建成功！<strong>api_secret 关闭后不可再查</strong>，请立即保存。
            </div>
            {[
              ['API Key', sandboxResult.api_key],
              ['API Secret', sandboxResult.api_secret],
              ['Sandbox URL', sandboxResult.base_url],
              ['速率限制', `${sandboxResult.rate_limit_rpm} 次/分钟`],
            ].map(([label, value]) => (
              <div key={label} className={styles.credRow}>
                <span className={styles.credLabel}>{label}</span>
                <code className={styles.credValue}>{value}</code>
              </div>
            ))}
          </div>
        )}
      </ZModal>
    </div>
  );
};

export default DeveloperDocsPage;
