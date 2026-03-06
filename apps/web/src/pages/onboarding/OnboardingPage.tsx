/**
 * OnboardingPage — 智链OS 企业诊断与数据入库向导
 * 路由: /onboarding
 * 4步流程: 欢迎 → 系统对接 → 数据导入 → 知识库构建 → 诊断报告
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ZButton, ZInput, ZCard, ZSkeleton, ZEmpty } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './OnboardingPage.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ImportRecord {
  name: string;
  required: boolean;
  description: string;
  status: 'pending' | 'previewed' | 'imported';
  row_count: number;
  download_url: string;
}

interface PreviewResult {
  data_type: string;
  name: string;
  total_rows: number;
  column_mapping: Record<string, string | null>;
  unmapped_columns: string[];
  missing_required_fields: string[];
  can_import: boolean;
  preview_rows: Record<string, string>[];
}

interface DiagnosticModule {
  health_score: number;
  label: string;
  color: string;
  insight: string;
  suggestions: (string | null)[];
  metrics: Record<string, unknown>;
}

interface DiagnosticReport {
  total_score: number;
  total_label: string;
  total_color: string;
  modules: Record<string, DiagnosticModule>;
  generated_at: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STEPS = ['欢迎', '系统对接', '数据导入', '构建知识库', '诊断报告'];

const POS_SYSTEMS = [
  { id: 'tiansi',    name: '天财商龙', icon: '🍽️', fields: ['api_key', 'app_secret', 'brand_id'] },
  { id: 'meituan',  name: '美团SaaS',  icon: '🦅', fields: ['app_id', 'app_secret'] },
  { id: 'pinzhi',   name: '品智',       icon: '📊', fields: ['api_token', 'store_code'] },
  { id: 'keruyun',  name: '客如云',     icon: '☁️', fields: ['client_id', 'client_secret'] },
  { id: 'aoweiwei', name: '傲其微',     icon: '🌟', fields: ['api_key'] },
  { id: 'yiding',   name: '易订',       icon: '📅', fields: ['token', 'shop_id'] },
];

const BUILD_STAGES = [
  { key: 'data_cleaning',     name: '数据清洗',   desc: '去重、格式标准化、异常值检测' },
  { key: 'kpi_calculation',   name: 'KPI计算',    desc: '计算客单价/毛利率/翻台率等核心指标' },
  { key: 'baseline_compare',  name: '基线对比',   desc: '与行业标准对比，标记偏离度' },
  { key: 'vector_embedding',  name: '语义嵌入',   desc: '菜品描述/评价文本向量化入库' },
  { key: 'knowledge_summary', name: '知识摘要',   desc: 'AI生成企业专属知识摘要' },
];

const COLOR_MAP: Record<string, string> = {
  green:  '#52c41a',
  blue:   '#1890ff',
  yellow: '#faad14',
  red:    '#ff4d4f',
  grey:   '#8c8c8c',
};

// ── Main component ─────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const [step, setStep]       = useState(0);
  const [storeId, setStoreId] = useState('');

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.logo}>智链OS</div>
        <div className={styles.progressBar}>
          {STEPS.map((name, i) => {
            const cls = i < step ? 'done' : i === step ? 'active' : '';
            return (
              <div key={i} className={`${styles.progressStep} ${cls ? styles[cls] : ''}`}>
                <div className={styles.stepDot}>{i < step ? '✓' : i + 1}</div>
                <span className={styles.stepName}>{name}</span>
              </div>
            );
          })}
        </div>
        <div style={{ width: 80 }} />
      </div>

      {/* Step content */}
      <div className={styles.content}>
        <div className={styles.inner}>
          {step === 0 && <WelcomeStep onNext={(sid) => { setStoreId(sid); setStep(1); }} />}
          {step === 1 && <ConnectStep storeId={storeId} onNext={() => setStep(2)} onSkip={() => setStep(2)} />}
          {step === 2 && <ImportStep  storeId={storeId} onNext={() => setStep(3)} />}
          {step === 3 && <BuildingStep storeId={storeId} onNext={() => setStep(4)} />}
          {step === 4 && <ReportStep  storeId={storeId} />}
        </div>
      </div>
    </div>
  );
}

// ── Step 0: Welcome ────────────────────────────────────────────────────────────

function WelcomeStep({ onNext }: { onNext: (storeId: string) => void }) {
  const [storeId, setStoreId] = useState('');

  return (
    <>
      <p style={{ fontSize: 13, color: 'var(--accent)', fontWeight: 600, marginBottom: 8 }}>
        开始之前
      </p>
      <h1 className={styles.stepTitle}>让我们先了解您的企业</h1>
      <p className={styles.stepSub}>
        填写品牌信息并导入历史经营数据，智链OS将在15分钟内完成企业数字体检，
        生成专属诊断报告，让所有AI Agent从第一天起就真正「认识」您的店。
      </p>

      <ZCard>
        <div style={{ padding: '8px 0' }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
            您的主门店ID（可在系统管理中查看）
          </p>
          <ZInput
            placeholder="例如：S001"
            value={storeId}
            onChange={(v) => setStoreId(v)}
          />
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8 }}>
            也可以稍后在设置中修改
          </p>
        </div>
      </ZCard>

      <div className={styles.actions}>
        <span />
        <ZButton
          variant="primary"
          onClick={() => onNext(storeId || 'S001')}
        >
          开始诊断 →
        </ZButton>
      </div>
    </>
  );
}

// ── Step 1: Connect ────────────────────────────────────────────────────────────

function ConnectStep({ storeId, onNext, onSkip }: { storeId: string; onNext: () => void; onSkip: () => void }) {
  const [selected, setSelected]     = useState<string | null>(null);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [loading, setLoading]       = useState(false);
  const [connected, setConnected]   = useState<string | null>(null);
  const [error, setError]           = useState('');

  const selectedPOS = POS_SYSTEMS.find(p => p.id === selected);

  const handleConnect = async () => {
    if (!selected) return;
    setLoading(true);
    setError('');
    try {
      await apiClient.post(`/api/v1/onboarding/connect/${selected}?store_id=${storeId}`, credentials);
      setConnected(selected);
    } catch (e: any) {
      setError(e?.response?.data?.detail || '连接失败，请检查凭证后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h1 className={styles.stepTitle}>连接现有系统</h1>
      <p className={styles.stepSub}>
        选择您正在使用的POS或SaaS系统，智链OS将自动拉取历史数据用于诊断分析。
        如无以上系统，可跳过此步骤，手动导入数据。
      </p>

      <div className={styles.posGrid}>
        {POS_SYSTEMS.map(pos => (
          <div
            key={pos.id}
            className={`${styles.posCard} ${selected === pos.id ? styles.posCardSelected : ''}`}
            onClick={() => { setSelected(pos.id); setCredentials({}); setConnected(null); setError(''); }}
          >
            <div className={styles.posIcon}>{pos.icon}</div>
            <div className={styles.posName}>{pos.name}</div>
            {connected === pos.id && (
              <div className={`${styles.posStatus} ${styles.connected}`}>已连接 ✓</div>
            )}
          </div>
        ))}
      </div>

      {/* Credential form */}
      {selectedPOS && !connected && (
        <div className={styles.credForm}>
          <div className={styles.credTitle}>输入 {selectedPOS.name} API 凭证</div>
          {selectedPOS.fields.map(field => (
            <div key={field} style={{ marginBottom: 10 }}>
              <div className={styles.credLabel}>{field}</div>
              <ZInput
                placeholder={`请输入 ${field}`}
                value={credentials[field] || ''}
                onChange={(v) =>
                  setCredentials(prev => ({ ...prev, [field]: v }))
                }
              />
            </div>
          ))}
          {error && <p style={{ color: 'var(--red, #ff4d4f)', fontSize: 12, marginTop: 8 }}>{error}</p>}
          <div style={{ marginTop: 16 }}>
            <ZButton variant="primary" onClick={handleConnect} disabled={loading}>
              {loading ? '连接中…' : '测试并连接'}
            </ZButton>
          </div>
        </div>
      )}

      {connected && (
        <div className={styles.connectedBanner}>
          ✓ {POS_SYSTEMS.find(p => p.id === connected)?.name} 连接成功，历史数据将在后台同步
        </div>
      )}

      <div className={styles.actions}>
        <ZButton variant="ghost" size="sm" onClick={onSkip}>跳过此步骤</ZButton>
        <ZButton variant="primary" onClick={onNext}>下一步 →</ZButton>
      </div>
    </>
  );
}

// ── Step 2: Import ─────────────────────────────────────────────────────────────

function ImportStep({ storeId, onNext }: { storeId: string; onNext: () => void }) {
  const [templates, setTemplates]   = useState<Record<string, ImportRecord>>({});
  const [loading, setLoading]       = useState(true);
  const [preview, setPreview]       = useState<PreviewResult | null>(null);
  const [previewType, setPreviewType] = useState<string>('');
  const [uploading, setUploading]   = useState<string>('');
  const [confirming, setConfirming] = useState<string>('');
  const fileRef = useRef<HTMLInputElement>(null);
  const pendingType = useRef<string>('');

  const load = useCallback(async () => {
    try {
      const resp = await apiClient.get(`/api/v1/onboarding/import/templates?store_id=${storeId}`);
      const map: Record<string, ImportRecord> = {};
      for (const t of resp.data.templates) map[t.data_type] = t;
      setTemplates(map);
    } catch { /* use empty */ }
    setLoading(false);
  }, [storeId]);

  useEffect(() => { load(); }, [load]);

  const handleUploadClick = (dtype: string) => {
    pendingType.current = dtype;
    fileRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const dtype = pendingType.current;
    if (!file || !dtype) return;
    e.target.value = '';

    setUploading(dtype);
    setPreview(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const resp = await apiClient.post(
        `/api/v1/onboarding/import/${dtype}/preview?store_id=${storeId}`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setPreview(resp.data);
      setPreviewType(dtype);
    } catch (err: any) {
      alert(`上传失败: ${err?.response?.data?.detail || '请检查文件格式'}`);
    } finally {
      setUploading('');
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setConfirming(previewType);
    try {
      const form = new FormData();
      // Re-upload the file — browser doesn't retain File objects
      // Instead we use the cached mapping from the preview call
      // The API uses the saved column_mapping from the preview step
      const resp = await apiClient.post(
        `/api/v1/onboarding/import/${previewType}/confirm?store_id=${storeId}`,
        {},
      );
      alert(`✓ 导入成功：${resp.data.imported} 行`);
      setPreview(null);
      load();
    } catch (err: any) {
      alert(`导入失败: ${err?.response?.data?.detail || '请重试'}`);
    } finally {
      setConfirming('');
    }
  };

  const requiredTypes = Object.entries(templates).filter(([, t]) => t.required);
  const requiredDone  = requiredTypes.every(([, t]) => t.status === 'imported');

  if (loading) return <ZSkeleton rows={6} />;

  return (
    <>
      <h1 className={styles.stepTitle}>导入历史数据</h1>
      <p className={styles.stepSub}>
        下载模板 → 填写数据 → 上传文件。标记<span style={{ color: 'var(--accent)' }}>「必填」</span>
        的4种数据是诊断报告的基础；其他数据导入越多，诊断越精准。
      </p>

      <input ref={fileRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleFileChange} />

      <div className={styles.importGrid}>
        {Object.entries(templates).map(([dtype, tpl]) => (
          <div
            key={dtype}
            className={`${styles.importCard} ${tpl.required ? styles.importCardRequired : ''} ${tpl.status === 'imported' ? styles.importCardDone : ''}`}
          >
            <div className={styles.importMeta}>
              <div className={styles.importName}>{dtype} {tpl.name}</div>
              <div className={styles.importInfo}>
                {tpl.status === 'imported'
                  ? `已导入 ${tpl.row_count} 行`
                  : tpl.description.slice(0, 20) + '…'}
              </div>
            </div>
            <div className={styles.importActions}>
              {tpl.required && <span className={styles.requiredBadge}>必填</span>}
              {tpl.status === 'imported' && <span className={styles.doneBadge}>✓ 已完成</span>}
              <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                <ZButton
                  size="sm"
                  variant="ghost"
                  onClick={() => window.open(`/api/v1/onboarding/import/${dtype}/template`, '_blank')}
                >
                  模板
                </ZButton>
                <ZButton
                  size="sm"
                  variant={tpl.status === 'imported' ? 'ghost' : 'primary'}
                  onClick={() => handleUploadClick(dtype)}
                  disabled={uploading === dtype}
                >
                  {uploading === dtype ? '…' : tpl.status === 'imported' ? '重传' : '上传'}
                </ZButton>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Preview panel */}
      {preview && (
        <ZCard subtitle={`预览：${preview.name}（${preview.total_rows} 行）`}>
          <div className={styles.mappingRow}>
            {Object.entries(preview.column_mapping).map(([src, tgt]) => (
              <span
                key={src}
                className={`${styles.mappingPill} ${!tgt ? styles.mappingPillMissing : ''}`}
              >
                {src} → {tgt || '未识别'}
              </span>
            ))}
          </div>
          {preview.missing_required_fields.length > 0 && (
            <p style={{ color: 'var(--red, #ff4d4f)', fontSize: 12 }}>
              缺少必填字段: {preview.missing_required_fields.join(', ')}
            </p>
          )}
          <div className={styles.previewWrap}>
            <table className={styles.previewTable}>
              <thead>
                <tr>
                  {Object.keys(preview.preview_rows[0] || {}).map(col => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.preview_rows.map((row, i) => (
                  <tr key={i}>
                    {Object.values(row).map((v, j) => <td key={j}>{v}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <ZButton variant="ghost" size="sm" onClick={() => setPreview(null)}>取消</ZButton>
            <ZButton
              variant="primary"
              size="sm"
              onClick={handleConfirm}
              disabled={!preview.can_import || !!confirming}
            >
              {confirming ? '导入中…' : `确认导入 ${preview.total_rows} 行`}
            </ZButton>
          </div>
        </ZCard>
      )}

      <div className={styles.actions}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {requiredDone ? '✓ 必填数据已完成' : '请先完成4种必填数据导入'}
        </span>
        <ZButton variant="primary" onClick={onNext} disabled={!requiredDone}>
          开始构建知识库 →
        </ZButton>
      </div>
    </>
  );
}

// ── Step 3: Building ───────────────────────────────────────────────────────────

function BuildingStep({ storeId, onNext }: { storeId: string; onNext: () => void }) {
  const [currentStage, setCurrentStage] = useState('');
  const [status, setStatus]             = useState('');
  const [error, setError]               = useState('');
  const [started, setStarted]           = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const poll = useCallback(async () => {
    try {
      const resp = await apiClient.get(`/api/v1/onboarding/build/progress?store_id=${storeId}`);
      const data = resp.data;
      setStatus(data.status);
      setCurrentStage(data.stage || '');
      if (data.status === 'completed') {
        clearTimeout(pollRef.current);
      } else if (data.status === 'in_progress') {
        pollRef.current = setTimeout(poll, 3000);
      }
    } catch { /* ignore */ }
  }, [storeId]);

  useEffect(() => {
    const start = async () => {
      if (started) return;
      setStarted(true);
      try {
        await apiClient.post(`/api/v1/onboarding/build?store_id=${storeId}`);
        poll();
      } catch (e: any) {
        setError(e?.response?.data?.detail || '启动失败');
      }
    };
    start();
    return () => clearTimeout(pollRef.current);
  }, [storeId, started, poll]);

  const stageIndex = BUILD_STAGES.findIndex(s => s.key === currentStage);

  return (
    <>
      <h1 className={styles.stepTitle}>正在构建知识库</h1>
      <p className={styles.stepSub}>
        智链OS正在分析您的历史数据，构建企业专属知识图谱。全程约5-15分钟，请稍候。
      </p>

      {error ? (
        <ZEmpty title="构建失败" description={error} />
      ) : (
        <div className={styles.stageList}>
          {BUILD_STAGES.map((stage, i) => {
            const isDone   = status === 'completed' || (stageIndex > i);
            const isActive = stageIndex === i && status === 'in_progress';
            return (
              <div
                key={stage.key}
                className={`${styles.stageItem} ${isDone ? styles.done : ''} ${isActive ? styles.active : ''}`}
              >
                <div className={styles.stageDot} />
                <div>
                  <div className={styles.stageName}>{stage.name}</div>
                  <div className={styles.stageDesc}>{stage.desc}</div>
                </div>
                {isDone   && <span style={{ marginLeft: 'auto', color: 'var(--green)', fontSize: 16 }}>✓</span>}
                {isActive && <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--accent)' }}>处理中…</span>}
              </div>
            );
          })}
        </div>
      )}

      <div className={styles.actions}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {status === 'completed' ? '知识库构建完成！' : status === 'in_progress' ? '构建中，请勿关闭页面…' : '正在启动…'}
        </span>
        <ZButton variant="primary" onClick={onNext} disabled={status !== 'completed'}>
          查看诊断报告 →
        </ZButton>
      </div>
    </>
  );
}

// ── Step 4: Report ─────────────────────────────────────────────────────────────

function ReportStep({ storeId }: { storeId: string }) {
  const [report, setReport]   = useState<DiagnosticReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);

  useEffect(() => {
    apiClient.get(`/api/v1/onboarding/diagnostic?store_id=${storeId}`)
      .then(r => setReport(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [storeId]);

  const handleComplete = async () => {
    setCompleting(true);
    try {
      await apiClient.post(`/api/v1/onboarding/complete?store_id=${storeId}`);
      window.location.href = '/';
    } catch {
      setCompleting(false);
    }
  };

  if (loading) return <ZSkeleton rows={8} />;
  if (!report) return <ZEmpty title="诊断报告生成中" description="请稍候片刻后刷新" action={<ZButton size="sm" onClick={() => window.location.reload()}>刷新</ZButton>} />;

  const scoreColor = COLOR_MAP[report.total_color] || '#8c8c8c';

  return (
    <>
      <h1 className={styles.stepTitle}>您的企业诊断报告</h1>
      <p className={styles.stepSub}>基于您的历史数据，AI已完成全方位体检。以下是关键发现。</p>

      {/* Hero score */}
      <div className={styles.reportHero}>
        <div className={styles.scoreCircle} style={{ borderColor: scoreColor, color: scoreColor }}>
          <span className={styles.scoreNumber}>{report.total_score}</span>
          <span className={styles.scoreUnit}>综合健康分</span>
        </div>
        <div className={styles.scoreMeta}>
          <div className={styles.scoreLabel} style={{ color: scoreColor }}>{report.total_label}</div>
          <div className={styles.scoreDesc}>
            基于8个维度综合评分。绿色（90+）代表优秀，黄色（50-69）代表需关注，红色（49以下）代表风险。
            <br />生成时间：{new Date(report.generated_at).toLocaleString('zh-CN')}
          </div>
          <div style={{ marginTop: 12 }}>
            <ZButton
              size="sm"
              variant="ghost"
              onClick={() => window.open(`/api/v1/onboarding/diagnostic/pdf?store_id=${storeId}`, '_blank')}
            >
              下载PDF报告
            </ZButton>
          </div>
        </div>
      </div>

      {/* 8 module cards */}
      <div className={styles.moduleGrid}>
        {Object.entries(report.modules).map(([name, mod]) => {
          const color = COLOR_MAP[mod.color] || '#8c8c8c';
          return (
            <div key={name} className={styles.moduleCard} style={{ borderLeftColor: color }}>
              <div className={styles.moduleHeader}>
                <span className={styles.moduleName}>{name}</span>
                <span className={styles.moduleScore} style={{ color }}>{mod.health_score}</span>
              </div>
              <div className={styles.moduleInsight}>{mod.insight}</div>
              {mod.suggestions?.[0] && (
                <div className={styles.moduleSuggestion}>→ {mod.suggestions[0]}</div>
              )}
            </div>
          );
        })}
      </div>

      <div className={styles.actions}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          完成后，各AI Agent将基于您的历史数据开始工作
        </span>
        <ZButton variant="primary" onClick={handleComplete} disabled={completing}>
          {completing ? '初始化中…' : '开始使用智链OS 🎉'}
        </ZButton>
      </div>
    </>
  );
}
