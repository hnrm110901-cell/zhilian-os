import React, { useState } from 'react';
import { Form, Input, message } from 'antd';
import { ZCard, ZBadge, ZButton, ZModal } from '../design-system/components';
import { apiClient, handleApiError } from '../services/api';
import styles from './ISVEcosystemPage.module.css';

// ── Static data ────────────────────────────────────────────────────────────────

const BENEFITS = [
  {
    icon: '🔌',
    title: '即插即用 API',
    desc: '14 个开放能力 Level 1-4，Free 套餐零门槛，5 分钟接入，沙箱即时测试。',
  },
  {
    icon: '💰',
    title: '收入分成',
    desc: '插件订阅收入最高 85% 归开发者（Enterprise 套餐），平台负责支付和结算。',
  },
  {
    icon: '📈',
    title: '百万级用户触达',
    desc: '直接接入全国餐饮连锁门店网络，无需自建销售渠道，专注产品开发。',
  },
  {
    icon: '🤝',
    title: '联合营销支持',
    desc: '优质 ISV 享受屯象官网首页推荐、行业峰会合作展位、联合案例宣传。',
  },
];

const TIER_COMPARISON = [
  {
    tier: 'free',
    label: '免费版',
    price: '¥0/月',
    rpm: '60 次/分钟',
    level: 'Level 1',
    revenue_share: '70%',
    badge: 'neutral' as const,
    highlight: false,
  },
  {
    tier: 'basic',
    label: '基础版',
    price: '¥999/月',
    rpm: '300 次/分钟',
    level: 'Level 1-2',
    revenue_share: '75%',
    badge: 'success' as const,
    highlight: false,
  },
  {
    tier: 'pro',
    label: '专业版',
    price: '¥2,999/月',
    rpm: '1,000 次/分钟',
    level: 'Level 1-3',
    revenue_share: '80%',
    badge: 'warning' as const,
    highlight: true,
  },
  {
    tier: 'enterprise',
    label: '企业版',
    price: '¥9,999/月',
    rpm: '5,000 次/分钟',
    level: 'Level 1-4',
    revenue_share: '85%',
    badge: 'error' as const,
    highlight: false,
  },
];

const CASE_STUDIES = [
  {
    name: '小象 ERP 连接器',
    company: '北京小象科技',
    category: '系统集成',
    desc: '将主流 ERP 系统（用友/金蝶/SAP）与屯象无缝打通，订单/库存双向同步。',
    installs: 320,
    rating: 4.8,
    tier: 'pro',
  },
  {
    name: '餐饮大数据看板',
    company: '上海数聚信息',
    category: '数据分析',
    desc: '基于屯象 Level 2 预测 API 构建多门店横向对比大屏，支持自定义指标。',
    installs: 180,
    rating: 4.6,
    tier: 'basic',
  },
  {
    name: '企微营销自动化',
    company: '深圳快客网络',
    category: '营销工具',
    desc: '接入 Level 3 客户画像 + 发券策略，自动化运营私域流量，ROI 提升 40%。',
    installs: 95,
    rating: 4.9,
    tier: 'pro',
  },
];

const PROCESS_STEPS = [
  { num: '01', title: '注册开发者账号', desc: '填写邮箱 + 公司信息，5 分钟完成注册，立刻获取沙箱 Key' },
  { num: '02', title: '完成邮箱验证', desc: '点击验证链接完成实名认证，解锁套餐升级申请资格' },
  { num: '03', title: '申请目标套餐', desc: '提交升级申请 + 使用说明，审核周期 1-3 个工作日' },
  { num: '04', title: '上线插件市场', desc: '通过审核后，插件发布至市场，开始产生收益分成' },
];

// ── Component ──────────────────────────────────────────────────────────────────

interface RegisterResult {
  developer_id: string;
  api_key: string;
  api_secret: string;
  rate_limit_rpm: number;
  tier: string;
}

const ISVEcosystemPage: React.FC = () => {
  const [applyModal, setApplyModal] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);
  const [applyResult, setApplyResult] = useState<RegisterResult | null>(null);
  const [applyForm] = Form.useForm();

  const handleApply = async (values: { name: string; email: string; company: string; tier: string }) => {
    setApplyLoading(true);
    try {
      const res = await apiClient.post('/api/v1/open/developers', values);
      setApplyResult(res.data);
      message.success('开发者账号注册成功！');
    } catch (e) {
      handleApiError(e);
    } finally {
      setApplyLoading(false);
    }
  };

  const closeModal = () => {
    setApplyModal(false);
    setApplyResult(null);
    applyForm.resetFields();
  };

  const applyFooter = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
      <ZButton onClick={closeModal}>关闭</ZButton>
      {!applyResult && (
        <ZButton variant="primary" disabled={applyLoading} onClick={() => applyForm.submit()}>
          {applyLoading ? '注册中…' : '立即加入'}
        </ZButton>
      )}
    </div>
  );

  return (
    <div className={styles.page}>
      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.heroBadge}>
            <ZBadge type="success" text="现已开放 · 首批 ISV 特权" />
          </div>
          <h1 className={styles.heroTitle}>
            加入屯象 ISV 生态<br />
            <span className={styles.heroAccent}>把 AI 能力卖给 5 万家餐厅</span>
          </h1>
          <p className={styles.heroDesc}>
            屯象开放平台为第三方开发者提供 14 个 AI 能力 API，覆盖数据同步、智能决策、营销自动化、
            知识库查询四大层级。你只需专注产品，我们负责市场。
          </p>
          <div className={styles.heroActions}>
            <ZButton variant="primary" onClick={() => setApplyModal(true)}>
              立即申请开发者账号
            </ZButton>
            <ZButton onClick={() => window.open('/developer-docs', '_self')}>
              查看 API 文档
            </ZButton>
          </div>
          <div className={styles.heroStats}>
            {[
              { value: '14', label: '开放 API 能力' },
              { value: '4', label: 'Level 层级' },
              { value: '85%', label: '最高收入分成' },
              { value: '5min', label: '接入耗时' },
            ].map(s => (
              <div key={s.label} className={styles.heroStat}>
                <div className={styles.heroStatValue}>{s.value}</div>
                <div className={styles.heroStatLabel}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Benefits */}
      <ZCard title="为什么选择屯象开放平台">
        <div className={styles.benefitsGrid}>
          {BENEFITS.map(b => (
            <div key={b.title} className={styles.benefitItem}>
              <div className={styles.benefitIcon}>{b.icon}</div>
              <div className={styles.benefitTitle}>{b.title}</div>
              <div className={styles.benefitDesc}>{b.desc}</div>
            </div>
          ))}
        </div>
      </ZCard>

      {/* Process */}
      <ZCard title="接入流程">
        <div className={styles.processSteps}>
          {PROCESS_STEPS.map((step, idx) => (
            <React.Fragment key={step.num}>
              <div className={styles.processStep}>
                <div className={styles.processNum}>{step.num}</div>
                <div className={styles.processTitle}>{step.title}</div>
                <div className={styles.processDesc}>{step.desc}</div>
              </div>
              {idx < PROCESS_STEPS.length - 1 && <div className={styles.processArrow}>→</div>}
            </React.Fragment>
          ))}
        </div>
      </ZCard>

      {/* Tier Comparison */}
      <ZCard title="套餐对比">
        <div className={styles.tierGrid}>
          {TIER_COMPARISON.map(t => (
            <div key={t.tier} className={`${styles.tierCard} ${t.highlight ? styles.tierHighlight : ''}`}>
              {t.highlight && <div className={styles.tierRecommended}>推荐</div>}
              <ZBadge type={t.badge} text={t.label} />
              <div className={styles.tierPrice}>{t.price}</div>
              <div className={styles.tierFeatures}>
                <div className={styles.tierFeature}>
                  <span className={styles.featureIcon}>⚡</span>
                  <span>{t.rpm}</span>
                </div>
                <div className={styles.tierFeature}>
                  <span className={styles.featureIcon}>🔓</span>
                  <span>可用 {t.level}</span>
                </div>
                <div className={styles.tierFeature}>
                  <span className={styles.featureIcon}>💰</span>
                  <span>分成 {t.revenue_share}</span>
                </div>
              </div>
              <ZButton
                variant={t.highlight ? 'primary' : undefined}
                onClick={() => setApplyModal(true)}
                style={{ width: '100%', marginTop: 12 }}
              >
                选择此套餐
              </ZButton>
            </div>
          ))}
        </div>
      </ZCard>

      {/* Case Studies */}
      <ZCard title="合作案例">
        <div className={styles.caseGrid}>
          {CASE_STUDIES.map(c => (
            <div key={c.name} className={styles.caseCard}>
              <div className={styles.caseHeader}>
                <div>
                  <div className={styles.caseName}>{c.name}</div>
                  <div className={styles.caseCompany}>{c.company}</div>
                </div>
                <ZBadge type="neutral" text={c.category} />
              </div>
              <p className={styles.caseDesc}>{c.desc}</p>
              <div className={styles.caseMeta}>
                <span>📦 {c.installs} 门店安装</span>
                <span>⭐ {c.rating}</span>
                <ZBadge
                  type={c.tier === 'pro' ? 'warning' : 'success'}
                  text={c.tier === 'pro' ? '专业版' : '基础版'}
                />
              </div>
            </div>
          ))}
        </div>
      </ZCard>

      {/* CTA */}
      <div className={styles.ctaBanner}>
        <div className={styles.ctaText}>
          <div className={styles.ctaTitle}>准备好了吗？5 分钟开始构建</div>
          <div className={styles.ctaDesc}>首批 ISV 享受 3 个月 Pro 套餐免费试用 + 专属技术对接支持</div>
        </div>
        <ZButton variant="primary" onClick={() => setApplyModal(true)}>
          立即申请开发者账号
        </ZButton>
      </div>

      {/* Apply Modal */}
      <ZModal open={applyModal} title="申请开发者账号" onClose={closeModal} footer={applyFooter} width={480}>
        {!applyResult ? (
          <Form form={applyForm} layout="vertical" onFinish={handleApply}>
            <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
              <Input placeholder="张三" />
            </Form.Item>
            <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
              <Input placeholder="dev@company.com" />
            </Form.Item>
            <Form.Item name="company" label="公司名称" rules={[{ required: true, message: '请输入公司名称' }]}>
              <Input placeholder="北京小象科技有限公司" />
            </Form.Item>
            <Form.Item name="tier" label="起始套餐" initialValue="free">
              <select className={styles.select}>
                <option value="free">免费版（Level 1，¥0/月）</option>
                <option value="basic">基础版（Level 1-2，¥999/月）</option>
                <option value="pro">专业版（Level 1-3，¥2,999/月）</option>
                <option value="enterprise">企业版（全能力，¥9,999/月）</option>
              </select>
            </Form.Item>
          </Form>
        ) : (
          <div className={styles.resultBox}>
            <div className={styles.resultAlert}>
              注册成功！<strong>api_secret 关闭后不可再查</strong>，请立即保存。
            </div>
            {[
              ['开发者 ID', applyResult.developer_id],
              ['API Key', applyResult.api_key],
              ['API Secret', applyResult.api_secret],
              ['套餐', applyResult.tier],
              ['速率', `${applyResult.rate_limit_rpm} 次/分钟`],
            ].map(([label, value]) => (
              <div key={label} className={styles.credRow}>
                <span className={styles.credLabel}>{label}</span>
                <code className={styles.credValue}>{value}</code>
              </div>
            ))}
            <p className={styles.nextStep}>
              下一步：前往 <a onClick={() => { closeModal(); window.open('/developer-docs', '_self'); }}>开发者文档</a> 查看接入指南
            </p>
          </div>
        )}
      </ZModal>
    </div>
  );
};

export default ISVEcosystemPage;
