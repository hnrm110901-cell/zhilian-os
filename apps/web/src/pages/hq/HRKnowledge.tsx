import React, { useCallback, useEffect, useState } from 'react';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty,
  ZTable, ZSelect,
} from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import apiClient from '../../services/api';
import styles from './HRKnowledge.module.css';

interface CaptureItem {
  id: string;
  person_id: string;
  person_name: string | null;
  trigger_type: string | null;
  context: string | null;
  action: string | null;
  result: string | null;
  quality_score: number | null;
  created_at: string | null;
}

interface ListResp {
  total: number;
  high_quality_count: number;
  this_month_count: number;
  items: CaptureItem[];
}

const TRIGGER_OPTIONS = [
  { label: '全部类型', value: '' },
  { label: '离职采集', value: 'exit' },
  { label: '月度复盘', value: 'monthly_review' },
  { label: '事件记录', value: 'incident' },
  { label: '入职引导', value: 'onboarding' },
  { label: '成长评议', value: 'growth_review' },
  { label: '人才评估', value: 'talent_assessment' },
  { label: '历史导入', value: 'legacy_import' },
];

const TRIGGER_LABELS: Record<string, string> = {
  exit: '离职采集',
  monthly_review: '月度复盘',
  incident: '事件记录',
  onboarding: '入职引导',
  growth_review: '成长评议',
  talent_assessment: '人才评估',
  legacy_import: '历史导入',
};

function qualityBadge(score: number | null): React.ReactNode {
  if (score == null) return <ZBadge type="info" text="未评分" />;
  if (score >= 0.8) return <ZBadge type="success" text={`${Math.round(score * 100)}分`} />;
  if (score >= 0.5) return <ZBadge type="warning" text={`${Math.round(score * 100)}分`} />;
  return <ZBadge type="critical" text={`${Math.round(score * 100)}分`} />;
}

export default function HQHrKnowledge() {
  const [data, setData] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggerType, setTriggerType] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { limit: 100 };
      if (triggerType) params.trigger_type = triggerType;
      const resp = await apiClient.get('/api/v1/hr/knowledge-captures', { params });
      setData(resp as ListResp);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [triggerType]);

  useEffect(() => { load(); }, [load]);

  const items = data?.items ?? [];
  const highQualityPct = data && data.total > 0
    ? Math.round((data.high_quality_count / data.total) * 100)
    : 0;

  const columns: ZTableColumn<CaptureItem>[] = [
    {
      key: 'person_name',
      title: '员工',
      render: (r) => r.person_name || '—',
    },
    {
      key: 'trigger_type',
      title: '触发类型',
      render: (r) => (
        <ZBadge type="info" text={TRIGGER_LABELS[r.trigger_type ?? ''] || r.trigger_type || '—'} />
      ),
    },
    {
      key: 'context',
      title: '内容摘要',
      render: (r) => {
        const preview = r.context || r.action || r.result || '—';
        return (
          <span className={styles.preview}>
            {preview.length > 60 ? preview.slice(0, 60) + '…' : preview}
          </span>
        );
      },
    },
    {
      key: 'quality_score',
      title: '质量评分',
      render: (r) => qualityBadge(r.quality_score),
    },
    {
      key: 'created_at',
      title: '采集时间',
      render: (r) =>
        r.created_at
          ? new Date(r.created_at).toLocaleDateString('zh-CN')
          : '—',
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>知识库管理</h2>
        <div className={styles.actions}>
          <ZSelect
            value={triggerType}
            onChange={(v) => setTriggerType(v as string)}
            options={TRIGGER_OPTIONS}
            placeholder="筛选类型"
          />
          <ZButton variant="ghost" size="sm" onClick={load}>刷新</ZButton>
        </div>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={5} /></div>
      ) : (
        <div className={styles.body}>
          {/* KPI 汇总行 */}
          <div className={styles.kpiRow}>
            <ZCard>
              <ZKpi value={data?.total ?? 0} label="采集总条目" unit="条" />
            </ZCard>
            <ZCard>
              <ZKpi value={`${highQualityPct}%`} label="高质量占比" unit="(≥0.8分)" />
            </ZCard>
            <ZCard>
              <ZKpi value={data?.this_month_count ?? 0} label="本月新增" unit="条" />
            </ZCard>
          </div>

          {/* 采集记录表格 */}
          <ZCard
            title="采集记录"
            extra={
              data
                ? <ZBadge type="info" text={`共${data.total}条`} />
                : undefined
            }
          >
            {items.length === 0 ? (
              <ZEmpty
                title="暂无采集记录"
                description="可通过离职访谈、月度复盘等触发知识采集"
              />
            ) : (
              <ZTable data={items} columns={columns} rowKey="id" />
            )}
          </ZCard>
        </div>
      )}
    </div>
  );
}
